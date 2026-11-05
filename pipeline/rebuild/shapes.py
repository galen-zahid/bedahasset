"""Rebuild step 2: give every region a clean fill and a clean shape.

Fill:  solid colour (snapped to the design palette) or a 2-stop linear gradient.
Shape: the simplest primitive that matches the region (like a designer would draw it):
       rect / rounded rect (pill) / circle / ellipse / polygon / stroke (line with round caps)
       and only if nothing fits, a smooth pen-tool Bezier outline.
"""
from __future__ import annotations

import math

import cv2
import numpy as np


def _hex(c) -> str:
    c = np.clip(np.asarray(c, np.float64), 0, 1)
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


def _f(v) -> str:
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


# ------------------------------------------------------------------------------- fill
def fit_fill(img: np.ndarray, sl, m: np.ndarray, valid: np.ndarray, W: int, H: int, c):
    """img float 0..1 (smoothed, text removed). Returns dict(kind, color|stops, rmse, texture)."""
    sub = img[sl]
    use = m & valid[sl]
    er = cv2.erode(use.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    if er.sum() >= max(20, 0.3 * use.sum()):
        use = er
    if use.sum() < 3:
        use = m
    ys, xs = np.nonzero(use)
    px = sub[ys, xs].astype(np.float64)
    gy, gx = ys + sl[0].start, xs + sl[1].start
    solid = np.median(px, 0)
    rmse_s = float(np.sqrt(((px - solid) ** 2).mean()))
    out = {"kind": "solid", "color": solid, "rmse": rmse_s, "median": solid}
    if len(px) < c.grad_min_px:
        return out
    X = np.stack([np.ones(len(gx)), gx / W, gy / H], 1)
    beta, *_ = np.linalg.lstsq(X, px, rcond=None)
    rmse_l = float(np.sqrt(((X @ beta - px) ** 2).mean()))
    out["rmse"] = min(rmse_s, rmse_l)
    if rmse_l > c.grad_gain * rmse_s:
        return out
    # direction of strongest change, stops at the 1st / 99th percentile of the region
    G = beta[1:].T * np.array([1 / W, 1 / H])
    _, _, vt = np.linalg.svd(G)
    d = vt[0]
    proj = gx * d[0] + gy * d[1]
    p0, p1 = np.percentile(proj, [1, 99])
    cx, cy = gx.mean(), gy.mean()
    off = cx * d[0] + cy * d[1]
    ends = []
    for p in (p0, p1):
        x, y = cx + (p - off) * d[0], cy + (p - off) * d[1]
        ends.append((x, y, np.clip(np.array([1, x / W, y / H]) @ beta, 0, 1)))
    if np.abs(ends[0][2] - ends[1][2]).max() < c.grad_min_delta:
        return out
    out.update(kind="linear", stops=ends, rmse=rmse_l)
    # multi-stop: rendered panels brighten and darken again along the same direction
    K = int(c.grad_max_stops)
    if K > 2 and len(px) >= c.grad_multi_min_px:
        t = np.clip((proj - p0) / max(p1 - p0, 1e-6), 0, 1)
        knots = np.linspace(0, 1, K)
        # piecewise-linear least squares in t (hat basis)
        Bm = np.maximum(0, 1 - np.abs(t[:, None] - knots[None]) * (K - 1))
        cols, *_ = np.linalg.lstsq(Bm, px, rcond=None)
        rmse_m = float(np.sqrt(((Bm @ cols - px) ** 2).mean()))
        if rmse_m < c.grad_multi_gain * rmse_l:
            out["mid"] = [(float(k), np.clip(col, 0, 1)) for k, col in zip(knots, cols)]
            out["stops"] = [(ends[0][0], ends[0][1], np.clip(cols[0], 0, 1)),
                            (ends[1][0], ends[1][1], np.clip(cols[-1], 0, 1))]
            out["rmse"] = rmse_m
    return out


def snap_palette(fills, areas, tol):
    """One palette for the whole design: near-identical solid colours (and gradient stops)
    become exactly the same colour, weighted by area."""
    cols, w = [], []
    for f, a in zip(fills, areas):
        if f["kind"] == "solid":
            cols.append(f["color"])
            w.append(a)
        else:
            for s in f["stops"]:
                cols.append(s[2])
                w.append(a * 0.25)
    if not cols:
        return []
    cols, w = np.array(cols), np.array(w, np.float64)
    lab = cv2.cvtColor(cols.astype(np.float32)[None], cv2.COLOR_RGB2Lab)[0]
    order = np.argsort(-w)
    centers, members = [], []
    for i in order:
        for k, cidx in enumerate(centers):
            if np.linalg.norm(lab[i] - lab[cidx]) < tol:
                members[k].append(i)
                break
        else:
            centers.append(i)
            members.append([i])
    palette = []
    for mem in members:
        mem = np.array(mem)
        palette.append((cols[mem] * w[mem, None]).sum(0) / w[mem].sum())
    palette = np.array(palette)
    pal_lab = cv2.cvtColor(palette.astype(np.float32)[None], cv2.COLOR_RGB2Lab)[0]

    def snap(col):
        l = cv2.cvtColor(np.asarray(col, np.float32)[None, None], cv2.COLOR_RGB2Lab)[0, 0]
        dd = np.linalg.norm(pal_lab - l, axis=1)
        j = dd.argmin()
        return palette[j] if dd[j] < tol else np.asarray(col)

    for f in fills:
        if f["kind"] == "solid":
            f["color"] = snap(f["color"])
        else:
            f["stops"] = [(x, y, snap(col)) for x, y, col in f["stops"]]
            if f.get("mid"):
                f["mid"] = [(o, snap(col)) for o, col in f["mid"]]
    return palette


def fill_attr(f, gid: str):
    """(fill attribute, defs xml)"""
    if f["kind"] == "solid":
        return f'fill="{_hex(f["color"])}"', ""
    (x1, y1, c1), (x2, y2, c2) = f["stops"]
    stops = f.get("mid") or [(0.0, c1), (1.0, c2)]
    st = "".join(f'<stop offset="{o:.3f}" stop-color="{_hex(col)}"/>' for o, col in stops)
    defs = (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{_f(x1)}" y1="{_f(y1)}" '
            f'x2="{_f(x2)}" y2="{_f(y2)}">{st}</linearGradient>')
    return f'fill="url(#{gid})"', defs


# ------------------------------------------------------------------------------ shapes
def _iou(a, b) -> float:
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def _rounded_rect_pts(cx, cy, w, h, ang, r, n=10):
    r = max(0.0, min(r, w / 2, h / 2))
    pts = []
    for qx, qy, a0 in ((w / 2 - r, -h / 2 + r, -90), (w / 2 - r, h / 2 - r, 0),
                       (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180)):
        for t in np.linspace(a0, a0 + 90, n if r > 0 else 1):
            pts.append((qx + r * math.cos(math.radians(t)), qy + r * math.sin(math.radians(t))))
    pts = np.array(pts)
    ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    rot = np.stack([pts[:, 0] * ca - pts[:, 1] * sa, pts[:, 0] * sa + pts[:, 1] * ca], 1)
    return rot + [cx, cy]


def _draw_poly(shape, pts):
    m = np.zeros(shape, np.uint8)
    cv2.fillPoly(m, [np.round(np.asarray(pts) * 8).astype(np.int32)], 1, cv2.LINE_8, 3)
    return m.astype(bool)


def _fit_rect(m, cnt, c):
    (cx, cy), (w, h), ang = cv2.minAreaRect(cnt)
    if w < 2 or h < 2:
        return None
    area = m.sum()
    best = None
    deficit = max(w * h - area, 0.0)
    for r in sorted({0.0, math.sqrt(deficit / (4 - math.pi)) if deficit > 0 else 0.0}):
        pts = _rounded_rect_pts(cx, cy, w, h, ang, r)
        iou = _iou(m, _draw_poly(m.shape, pts - 0.5))
        if best is None or iou > best[0] + 0.003:
            best = (iou, r)
    iou, r = best
    if iou < c.iou_rect:
        return None
    # normalise to an upright description when the angle is ~0 / ~90
    k = round(ang / 90.0)
    if abs(ang - 90 * k) < c.axis_snap_deg:
        if k % 2:
            w, h = h, w
        ang = 0.0
    return ("rect", dict(cx=cx, cy=cy, w=w, h=h, ang=ang, r=r), iou)


def _fit_ellipse(m, cnt, c):
    if len(cnt) < 5:
        return None
    (cx, cy), (a, b), ang = cv2.fitEllipse(cnt)
    if a < 3 or b < 3:
        return None
    e = np.zeros(m.shape, np.uint8)
    cv2.ellipse(e, ((cx, cy), (a, b), ang), 1, -1)
    iou = _iou(m, e.astype(bool))
    if iou < c.iou_ellipse:
        return None
    return ("ellipse", dict(cx=cx, cy=cy, rx=a / 2, ry=b / 2, ang=ang), iou)


def _fit_polygon(m, cnt, c):
    peri = cv2.arcLength(cnt, True)
    a = cv2.approxPolyDP(cnt, max(c.poly_eps, c.poly_eps_frac * peri), True).reshape(-1, 2)
    if len(a) < 3 or len(a) > c.poly_max_vertices:
        return None
    iou = _iou(m, _draw_poly(m.shape, a.astype(np.float64)))
    if iou < c.iou_polygon:
        return None
    return ("polygon", dict(pts=a.astype(np.float64) + 0.5), iou)


def _trace_skeleton(sk):
    """Ordered points of a skeleton with exactly 2 ends and no branch, else None."""
    from scipy import ndimage as ndi

    nb = ndi.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - 1
    nb[~sk] = 0
    ends = np.argwhere(sk & (nb == 1))
    if len(ends) != 2 or (sk & (nb >= 3)).sum() > 2:
        return None
    path = [tuple(ends[0])]
    seen = {path[0]}
    H, W = sk.shape
    while True:
        y, x = path[-1]
        nxt = None
        for dy, dx in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            p = (y + dy, x + dx)
            if 0 <= p[0] < H and 0 <= p[1] < W and sk[p] and p not in seen:
                nxt = p
                break
        if nxt is None:
            break
        path.append(nxt)
        seen.add(nxt)
    if len(path) < 0.8 * sk.sum():
        return None
    return np.array(path)[:, ::-1].astype(np.float64)  # (x, y)


def _fit_stroke(m, c):
    from skimage.morphology import skeletonize

    dt = cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5)
    if dt.max() * 2 > c.stroke_max_width:
        return None
    sk = skeletonize(m)
    L = int(sk.sum())
    if L < 3:
        return None
    w = max(1.0, 2 * float(np.median(dt[sk])) - 1)
    if L < c.stroke_min_aspect * w:
        return None
    pts = _trace_skeleton(sk)
    if pts is None:
        return None
    a = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), c.stroke_eps, False).reshape(-1, 2)
    if len(a) < 2:
        return None
    r = np.zeros(m.shape, np.uint8)
    cv2.polylines(r, [np.round(a * 8).astype(np.int32)], False, 1, int(round(w)), cv2.LINE_8, 3)
    rr = r.astype(bool)
    err = (rr ^ m).sum() / max(L, 1)
    iou = _iou(m, rr)
    if iou < c.iou_stroke or err > c.stroke_max_err_px:
        return None
    return ("stroke", dict(pts=a.astype(np.float64) + 0.5, w=w), iou)


def _smooth_open(a, corner_deg):
    """Catmull-Rom -> cubic Bezier through the points, keeping sharp corners sharp."""
    n = len(a)
    if n == 2:
        return f"M{_f(a[0][0])} {_f(a[0][1])} L{_f(a[1][0])} {_f(a[1][1])}"
    cos_c = math.cos(math.radians(corner_deg))
    corner = np.zeros(n, bool)
    corner[0] = corner[-1] = True
    for i in range(1, n - 1):
        u, v = a[i] - a[i - 1], a[i + 1] - a[i]
        nu, nv = np.linalg.norm(u), np.linalg.norm(v)
        if nu and nv and (u @ v) / (nu * nv) < cos_c:
            corner[i] = True
    s = [f"M{_f(a[0][0])} {_f(a[0][1])}"]
    for i in range(n - 1):
        p0, p1, p2 = a[max(i - 1, 0)], a[i], a[i + 1]
        p3 = a[min(i + 2, n - 1)]
        c1 = p1 if corner[i] else p1 + (p2 - p0) / 6
        c2 = p2 if corner[i + 1] else p2 - (p3 - p1) / 6
        s.append(f"C{_f(c1[0])} {_f(c1[1])} {_f(c2[0])} {_f(c2[1])} {_f(p2[0])} {_f(p2[1])}")
    return " ".join(s)


def bezier_outline(m, eps, corner_deg, smooth):
    """Pen-tool outline (outer contours and holes) of a mask, local coordinates."""
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    cos_c = math.cos(math.radians(corner_deg))
    for cnt in cnts:
        p = cnt.reshape(-1, 2).astype(np.float64) + 0.5
        if len(p) < 6:
            continue
        if smooth > 0 and len(p) > 12:
            r = int(3 * smooth)
            k = np.exp(-0.5 * (np.arange(-r, r + 1) / smooth) ** 2)
            k /= k.sum()
            pw = np.vstack([p[-r:], p, p[:r]])
            p = np.stack([np.convolve(pw[:, i], k, "valid") for i in range(2)], 1)
        a = cv2.approxPolyDP(p.astype(np.float32).reshape(-1, 1, 2), eps, True).reshape(-1, 2).astype(np.float64)
        n = len(a)
        if n < 3:
            continue
        corner = np.zeros(n, bool)
        for i in range(n):
            u, v = a[i] - a[i - 1], a[(i + 1) % n] - a[i]
            nu, nv = np.linalg.norm(u), np.linalg.norm(v)
            if nu and nv and (u @ v) / (nu * nv) < cos_c:
                corner[i] = True
        seg = [f"M{_f(a[0][0])} {_f(a[0][1])}"]
        for i in range(n):
            p0, p1, p2, p3 = a[i - 1], a[i], a[(i + 1) % n], a[(i + 2) % n]
            c1 = p1 if corner[i] else p1 + (p2 - p0) / 6
            c2 = p2 if corner[(i + 1) % n] else p2 - (p3 - p1) / 6
            seg.append(f"C{_f(c1[0])} {_f(c1[1])} {_f(c2[0])} {_f(c2[1])} {_f(p2[0])} {_f(p2[1])}")
        parts.append(" ".join(seg) + " Z")
    return " ".join(parts)


def is_line(m: np.ndarray, c) -> bool:
    """Connector-like: thin and long (may end in a dot or fork), whatever its exact shape."""
    from skimage.morphology import skeletonize

    if m.sum() < 30:
        return False
    dt = cv2.distanceTransform(np.pad(m, 1).astype(np.uint8), cv2.DIST_L2, 5)
    sk = skeletonize(np.pad(m, 1))
    L = int(sk.sum())
    if L < c.line_min_len:
        return False
    w = 2 * float(np.median(dt[sk])) - 1
    if w > c.stroke_max_width or L < c.stroke_min_aspect * 1.5 * max(w, 1):
        return False
    return m.sum() <= 1.6 * L * max(w, 1)  # mostly line (a dot at the end is fine)


def fit_shape(m: np.ndarray, c, allow_stroke=True):
    """m: filled region mask (local crop). Returns (kind, params, iou)."""
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if len(cnts) == 1 and len(cnts[0]) >= 4:
        cnt = cnts[0]
        if allow_stroke:
            s = _fit_stroke(m, c)
            if s:
                return s
        cands = [f for f in (_fit_rect(m, cnt, c), _fit_ellipse(m, cnt, c)) if f]
        if cands:
            return max(cands, key=lambda t: t[2])
        p = _fit_polygon(m, cnt, c)
        if p:
            return p
    return ("path", {}, 1.0)


def shape_xml(kind, p, m, ox, oy, fill, c, extra=""):
    """SVG element in canvas coordinates."""
    if kind == "rect":
        x, y = p["cx"] - p["w"] / 2 + ox, p["cy"] - p["h"] / 2 + oy
        rx = f' rx="{_f(p["r"])}"' if p["r"] >= 0.75 else ""
        tr = (f' transform="rotate({_f(p["ang"])} {_f(p["cx"] + ox)} {_f(p["cy"] + oy)})"'
              if abs(p["ang"]) > 0.01 else "")
        return f'<rect x="{_f(x)}" y="{_f(y)}" width="{_f(p["w"])}" height="{_f(p["h"])}"{rx}{tr} {fill}{extra}/>'
    if kind == "ellipse":
        cx, cy = p["cx"] + ox, p["cy"] + oy
        if abs(p["rx"] - p["ry"]) < max(1.0, 0.03 * max(p["rx"], p["ry"])):
            return f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{_f((p["rx"] + p["ry"]) / 2)}" {fill}{extra}/>'
        return (f'<ellipse cx="{_f(cx)}" cy="{_f(cy)}" rx="{_f(p["rx"])}" ry="{_f(p["ry"])}" '
                f'transform="rotate({_f(p["ang"])} {_f(cx)} {_f(cy)})" {fill}{extra}/>')
    if kind == "polygon":
        pts = " ".join(f"{_f(x + ox)},{_f(y + oy)}" for x, y in p["pts"])
        return f'<polygon points="{pts}" {fill}{extra}/>'
    if kind == "stroke":
        d = _smooth_open(p["pts"] + [ox, oy], c.corner_deg)
        col = fill.replace("fill=", "stroke=")
        return (f'<path d="{d}" fill="none" {col} stroke-width="{_f(p["w"])}" '
                f'stroke-linecap="round" stroke-linejoin="round"{extra}/>')
    d = bezier_outline(m, c.anchor_eps, c.corner_deg, c.smooth)
    if not d:
        return ""
    return f'<path transform="translate({ox} {oy})" fill-rule="evenodd" d="{d}" {fill}{extra}/>'


def occluded_bands(R, text_mask, H, W, c, s_u8=None, orig=None):
    """A stripe / panel running BEHIND text is cut into pieces by the letters. Pieces of the same
    colour that together form one straight band (fitted on the visible pixels only) become ONE
    rotated rectangle that continues under the text."""
    import math

    near = cv2.dilate(text_mask.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool)
    known = ~text_mask

    def L(col):
        return cv2.cvtColor(np.asarray(col, np.float32)[None, None], cv2.COLOR_RGB2Lab)[0, 0]

    bgc = L(R[0]["fill"]["color"] if R[0]["fill"]["kind"] == "solid" else R[0]["fill"]["stops"][0][2])

    def col_of(r):
        return r["fill"]["color"] if r["fill"]["kind"] == "solid" else r["fill"]["median"]

    pool = [r for r in R if r is not R[0] and np.linalg.norm(L(col_of(r)) - bgc) > c.band_color_tol]
    cands = [r for r in pool if near[r["sl"]][r["m"]].any()]  # paper is no stripe
    # one family of colour (a faded part of the same stripe is lighter) = one group
    labs = [L(col_of(r)) for r in cands]
    groups = {}
    order = sorted(range(len(cands)), key=lambda i: -cands[i]["area"])
    heads = []
    for i in order:
        for h in heads:
            if np.linalg.norm(labs[i] - labs[h]) < c.band_color_tol:
                groups[h].append(cands[i])
                break
        else:
            heads.append(i)
            groups[i] = [cands[i]]
    out_new, gone = [], set()
    for rs in groups.values():
        rs = [r for r in rs if r["area"] >= 30]
        if not rs:
            continue

        def pts_of(r):
            ys_, xs_ = np.nonzero(r["m"])
            return np.stack([xs_ + r["sl"][1].start, ys_ + r["sl"][0].start], 1).astype(np.float64)

        # direction from the longest piece, then keep only pieces lying in that strip (robust to
        # other shapes of the same colour, e.g. orange letters next to an orange stripe)
        seed = max(rs, key=lambda r: max(r["sl"][0].stop - r["sl"][0].start, r["sl"][1].stop - r["sl"][1].start))
        P = pts_of(seed)
        if len(P) < 50:
            continue
        mu = P.mean(0)
        _, _, vt = np.linalg.svd(P - mu, full_matrices=False)
        u, v = vt[0], vt[1]
        pv = (P - mu) @ v
        lo, hi = np.percentile(pv, [1, 99])
        pad = 0.15 * (hi - lo) + 2
        fam = [r for r in pool if r["area"] >= 30
               and np.linalg.norm(L(col_of(r)) - L(col_of(seed))) < c.band_color_tol]
        keep = []
        for r in fam:
            q = (pts_of(r) - mu) @ v
            if ((q >= lo - pad) & (q <= hi + pad)).mean() >= 0.8:
                keep.append(r)
        rs = keep
        P = np.vstack([pts_of(r) for r in rs])
        if len(P) < c.band_min_px:
            continue
        V = np.zeros((H, W), bool)
        for r in rs:
            V[r["sl"]] |= r["m"]
        lab_img = _lab_image(s_u8) if s_u8 is not None else None
        fb = fit_band(V, pts_of(seed), known, text_mask, H, W, c, lab_img, L(col_of(seed)))
        if fb is None:
            continue
        Rm, poly, sl, iou, V = fb["Rm"], fb["poly"], fb["sl"], fb["iou"], fb["V"]
        # a stripe behind text only passes over background, never over other shapes
        others = np.zeros((H, W), bool)
        ids_ = {id(r) for r in rs}
        for r in R:
            if r is R[0] or id(r) in ids_:
                continue
            others[r["sl"]] |= r["m"]
        if (Rm & others & known & ~V).sum() > c.band_max_cover * Rm.sum():
            continue
        base = min(rs, key=lambda r: r["z"])
        nr = dict(base)
        # colour: the solid ink of the stripe = the most saturated half of its visible pixels
        src = orig if orig is not None else s_u8.astype(np.float32) / 255.0
        pix = src[V & Rm & known]
        if len(pix) > 50:
            labp = cv2.cvtColor(pix.astype(np.float32)[None], cv2.COLOR_RGB2Lab)[0]
            chroma = np.hypot(labp[:, 1], labp[:, 2])
            col = np.median(pix[chroma >= np.percentile(chroma, 50)], 0)
        else:
            col = col_of(seed)
        nr["fill"] = dict(kind="solid", color=col, rmse=0, median=col)
        nr.update(sl=sl, m=Rm[sl], filled=Rm[sl], area=int(Rm.sum()), farea=int(Rm.sum()),
                  shape=("polygon", dict(pts=poly - [sl[1].start, sl[0].start]), iou),
                  line=False, bg=False, stripe=True)
        out_new.append(nr)
        gone |= {id(r) for r in rs}
        # blotches sitting inside the stripe (faded / grunge bits) become part of it; their
        # difference is drawn by the effect layer
        gone |= absorb_into_stripe(R, Rm, nr["area"], gone, c, nr["fill"]["color"])
    if not out_new:
        return R, 0
    R2 = [r for r in R if id(r) not in gone] + out_new
    R2.sort(key=lambda r: r["z"])
    for z, r in enumerate(R2):
        r["z"] = z
    return R2, len(out_new)


def _clip_poly(pts, W, H):
    """Sutherland-Hodgman clip of a polygon to the canvas rectangle."""
    def clip(poly, inside, inter):
        out = []
        for i in range(len(poly)):
            a, b = poly[i - 1], poly[i]
            ia, ib = inside(a), inside(b)
            if ib:
                if not ia:
                    out.append(inter(a, b))
                out.append(b)
            elif ia:
                out.append(inter(a, b))
        return out

    def ix(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return np.array([x, a[1] + t * (b[1] - a[1])])

    def iy(a, b, y):
        t = (y - a[1]) / (b[1] - a[1])
        return np.array([a[0] + t * (b[0] - a[0]), y])

    p = [np.asarray(q, np.float64) for q in pts]
    for inside, inter in ((lambda q: q[0] >= 0, lambda a, b: ix(a, b, 0)),
                          (lambda q: q[0] <= W, lambda a, b: ix(a, b, W)),
                          (lambda q: q[1] >= 0, lambda a, b: iy(a, b, 0)),
                          (lambda q: q[1] <= H, lambda a, b: iy(a, b, H))):
        p = clip(p, inside, inter)
        if not p:
            break
    return np.array(p) if p else np.asarray(pts, np.float64)


def _lab_image(s_u8):
    lab = cv2.cvtColor(s_u8, cv2.COLOR_RGB2Lab).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    return lab


def _why(tag, loc):
    import logging
    keys = ("iou", "Wd", "wd0", "i0", "i1", "nbins", "reach0", "reach1")
    logging.getLogger("split").debug("    fit_band stop %s %s", tag, {k: (round(float(loc[k]), 2) if isinstance(loc.get(k), (int, float, np.floating, np.integer)) else loc.get(k)) for k in keys if k in loc})
    return None


def fit_band(V, seed_pts, known, occluder, H, W, c, lab_img=None, ref=None, min_iou=None, min_occl=0.02,
             taken=None, min_aspect=3.0, chroma_frac=None):
    """Fit ONE straight stripe (two straight long edges, ends off-canvas when it leaves the
    canvas) to the visible stripe pixels V. seed_pts give its direction and width. Pixels of the
    stripe colour in the image (lab_img vs ref) are added. Returns dict or None."""
    P = np.asarray(seed_pts, np.float64)
    if len(P) < 50:
        return _why("r1", locals())
    mu = P.mean(0)
    _, _, vt = np.linalg.svd(P - mu, full_matrices=False)
    u = vt[0] if vt[0][0] >= 0 else -vt[0]
    v = np.array([-u[1], u[0]])
    pv_seed = (P - mu) @ v
    wd0 = np.percentile(pv_seed, 99) - np.percentile(pv_seed, 1)
    yy, xx = np.mgrid[0:H, 0:W]
    if taken is not None:
        V = V & ~taken
        known = known & ~taken
    Vk = V
    if lab_img is not None and ref is not None:
        Vk = V | (ink_match(lab_img, ref, c, chroma_frac) & known)
    # refine direction / width from ALL stripe pixels along the seed's path, not one piece
    wd_seed = wd0
    for _ in range(2):
        qx, qy = (xx - mu[0]).astype(np.float32), (yy - mu[1]).astype(np.float32)
        qv = qx * v[0] + qy * v[1]
        sel = Vk & (np.abs(qv - np.median(pv_seed)) <= 0.9 * wd0 + 4)
        ys2, xs2 = np.nonzero(sel)
        if len(xs2) < 100:
            break
        P2 = np.stack([xs2, ys2], 1).astype(np.float64)
        mu = P2.mean(0)
        _, _, vt = np.linalg.svd(P2 - mu, full_matrices=False)
        u = vt[0] if vt[0][0] >= 0 else -vt[0]
        v = np.array([-u[1], u[0]])
        pv_seed = (P2 - mu) @ v
        wd0 = min(np.percentile(pv_seed, 98) - np.percentile(pv_seed, 2), 1.5 * wd_seed)
    qx, qy = (xx - mu[0]).astype(np.float32), (yy - mu[1]).astype(np.float32)
    qv = qx * v[0] + qy * v[1]
    qu = qx * u[0] + qy * u[1]
    strip = np.abs(qv - np.median(pv_seed)) <= 0.9 * wd0 + 4
    if lab_img is not None and ref is not None:
        Vimg = ink_match(lab_img, ref, c, chroma_frac) & strip & known
        Vimg = cv2.morphologyEx(Vimg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
        V = V | Vimg
    # --- walk along the stripe from the seed: it goes on while its pixels are visible (or it is
    #     hidden behind the subject/text) and stops where the strip is visible but empty
    step = 12.0
    su = qu[strip]
    if not len(su):
        return _why("r2", locals())
    lo_u, hi_u = float(su.min()), float(su.max())
    nbins = int((hi_u - lo_u) / step) + 1
    bi = np.clip(((qu - lo_u) / step).astype(np.int32), 0, nbins - 1)
    tot = np.bincount(bi[strip], minlength=nbins)
    kn = np.bincount(bi[strip & known], minlength=nbins)
    vv = np.bincount(bi[strip & V], minlength=nbins)
    good = (vv >= 0.25 * np.maximum(kn, 1)) | (kn < 0.25 * np.maximum(tot, 1))
    good &= tot > 0
    start = int(np.clip((np.median(P @ u - mu @ u) - lo_u) / step, 0, nbins - 1))
    if not good[start]:
        cand = np.nonzero(good)[0]
        if not len(cand):
            return _why("r3", locals())
        start = int(cand[np.argmin(np.abs(cand - start))])
    gap = int(c.band_gap_bins)
    i0 = start
    miss = 0
    while i0 - 1 >= 0 and miss <= gap:
        i0 -= 1
        miss = 0 if good[i0] else miss + 1
    i0 += miss
    i1 = start
    miss = 0
    while i1 + 1 < nbins and miss <= gap:
        i1 += 1
        miss = 0 if good[i1] else miss + 1
    i1 -= miss
    run_u0, run_u1 = lo_u + i0 * step, lo_u + (i1 + 1) * step
    # the run leaves the canvas at an end when stripe pixels near that end touch the canvas frame
    frame = np.zeros((H, W), bool)
    frame[:6, :] = frame[-6:, :] = True
    frame[:, :6] = frame[:, -6:] = True
    core = np.abs(qv - np.median(pv_seed)) <= 0.6 * wd0
    need = max(10, int(0.3 * wd0))
    reach0 = i0 == 0 or int((V & frame & core & (bi >= i0) & (bi <= i0 + 3)).sum()) >= need
    reach1 = i1 == nbins - 1 or int((V & frame & core & (bi <= i1) & (bi >= i1 - 3)).sum()) >= need
    inrun = strip & (qu >= run_u0) & (qu <= run_u1)
    ys_, xs_ = np.nonzero(V & inrun)
    if len(xs_) < c.band_min_px:
        return _why("r4", locals())
    pu = qu[ys_, xs_].astype(np.float64)
    pv = qv[ys_, xs_].astype(np.float64)
    nb = max(6, min(48, int((run_u1 - run_u0) / 20)))
    edges = np.linspace(pu.min(), pu.max(), nb + 1)
    bu, top, bot, tok, bok = [], [], [], [], []
    for i in range(nb):
        sel = (pu >= edges[i]) & (pu < edges[i + 1])
        if sel.sum() < 20:
            continue
        um = pu[sel].mean()
        t_, b_ = np.percentile(pv[sel], 2), np.percentile(pv[sel], 98)
        bu.append(um)
        top.append(t_)
        bot.append(b_)
        # an edge only counts where we SEE it: just outside it is visible background, not a
        # letter / the subject (there the stripe may simply continue under the occluder)
        okt = okb = True
        for dv, lst in ((-6.0, "t"), (6.0, "b")):
            vv_ = (t_ if lst == "t" else b_) + dv
            px_ = mu + um * u + vv_ * v
            xi, yi = int(round(px_[0])), int(round(px_[1]))
            vis = 0 <= xi < W and 0 <= yi < H and known[yi, xi] and not V[yi, xi]
            # beyond the canvas edge we cannot see where the stripe ends: not an edge
            if lst == "t":
                okt = vis
            else:
                okb = vis
        tok.append(okt)
        bok.append(okb)
    if len(bu) < 4:
        return _why("r5", locals())
    bu, top, bot = map(np.array, (bu, top, bot))
    tok, bok = np.array(tok), np.array(bok)
    # best evidence: cross-sections of the stripe with NOTHING in front of them
    occ_u = qu[strip & ~known]
    clear = []
    for um in bu:
        i = np.searchsorted(edges, um) - 1
        lo_, hi_ = edges[max(i, 0)], edges[min(i + 1, len(edges) - 1)]
        clear.append(not ((occ_u >= lo_ - 6) & (occ_u < hi_ + 6)).any())
    clear = np.array(clear)
    if clear.sum() >= 3:
        tok = tok & clear
        bok = bok & clear
    if tok.sum() < 2:
        tok[:] = True
    if bok.sum() < 2:
        bok[:] = True

    # a stripe is a parallelogram: both long edges share ONE slope; fit it robustly on the
    # visible edge points only
    xs_all = np.concatenate([bu[tok], bu[bok]])
    ys_all = np.concatenate([top[tok], bot[bok]])
    is_t = np.concatenate([np.ones(tok.sum(), bool), np.zeros(bok.sum(), bool)])
    keep_ = np.ones(len(xs_all), bool)
    k_ = dt_ = db = 0.0
    for _ in range(4):
        A = np.stack([xs_all, is_t.astype(float), (~is_t).astype(float)], 1)
        sol, *_ = np.linalg.lstsq(A[keep_], ys_all[keep_], rcond=None)
        k_, dt_, db = sol
        res = ys_all - A @ sol
        mad = np.median(np.abs(res[keep_])) + 1e-6
        nk = np.abs(res) <= 2.5 * mad + 2.0
        if nk.sum() < 4 or (nk == keep_).all():
            break
        keep_ = nk
    kt = kb = k_
    far = 2.0 * (H + W)
    # ends = where the stripe is last SEEN (hidden stretches only bridge between seen parts; the
    # cut behind an occluder is invisible anyway)
    u0 = -far if reach0 else max(run_u0, np.percentile(pu, 1))
    u1 = far if reach1 else min(run_u1, np.percentile(pu, 99))
    Wd = float(db - dt_) if "db" in dir() else float(np.median(bot - top))
    if Wd > c.band_max_width_frac * min(H, W):  # a stripe is slim; a big panel is not a stripe
        return _why("wide", locals())
    if Wd < 4 or (u1 - u0) < min_aspect * Wd:
        return _why("r6", locals())
    # ends: a cut can be slanted (a parallelogram button): measure where the stripe ends at
    # each height across it, fit that line (only for visible, in-canvas ends)
    uL_t = uL_b = u0
    uR_t = uR_b = u1
    # look a bit past where the walk stopped: a slanted tip is only partly filled
    ext = 1.5 * max(db - dt_, 1.0)
    ya, xa = np.nonzero(V & strip & known)
    pua = qu[ya, xa].astype(np.float64)
    pva = qv[ya, xa].astype(np.float64)
    frac_a = (pva - (kt * pua + dt_)) / max(db - dt_, 1e-6)
    inb_a = (frac_a >= 0) & (frac_a <= 1) & (pua >= u0 - ext) & (pua <= u1 + ext)
    for side in (0, 1):
        if (side == 0 and u0 <= -far / 2) or (side == 1 and u1 >= far / 2):
            continue
        # just past this end: is it visible background? (behind a person the cut is unknown)
        ue_ = u0 - 8 if side == 0 else u1 + 8
        mid = (dt_ + db) / 2 + kt * ue_
        pe = mu + ue_ * u + mid * v
        xe, ye = int(round(pe[0])), int(round(pe[1]))
        if not (0 <= xe < W and 0 <= ye < H) or not known[ye, xe] or occluder[ye, xe]:
            continue
        fr, ue = [], []
        for j in range(8):
            selj = inb_a & (frac_a >= j / 8) & (frac_a < (j + 1) / 8)
            selj &= (pua <= u0 + ext) if side == 0 else (pua >= u1 - ext)
            if selj.sum() < 5:
                continue
            fr.append((j + 0.5) / 8)
            ue.append(np.percentile(pua[selj], 1) if side == 0 else np.percentile(pua[selj], 99))
        if len(fr) >= 4:
            bb, aa = np.polyfit(np.array(fr), np.array(ue), 1)
            if abs(bb) < 2.0 * Wd:  # sane slant only
                if side == 0:
                    uL_t, uL_b = aa, aa + bb
                else:
                    uR_t, uR_b = aa, aa + bb
    corners = np.array([mu + uu * u + (k_ * uu + d_) * v
                        for uu, k_, d_ in ((uL_t, kt, dt_), (uR_t, kt, dt_), (uR_b, kb, db), (uL_b, kb, db))])
    Rm = np.zeros((H, W), np.uint8)
    cv2.fillPoly(Rm, [np.round(corners * 8).astype(np.int32)], 1, cv2.LINE_8, 3)
    Rm = Rm.astype(bool)
    if not Rm.any():
        return _why("r7", locals())
    inter = (Rm & V).sum()
    span = inrun & (qu >= u0) & (qu <= u1)
    union = ((Rm | (V & span)) & known).sum()
    iou = inter / max(union, 1)
    near_occ = cv2.dilate(Rm.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool) & occluder
    if iou < (c.band_iou if min_iou is None else min_iou) or near_occ.sum() < min_occl * Rm.sum():
        return _why("r8", locals())
    y2, x2 = np.nonzero(Rm)
    sl = (slice(y2.min(), y2.max() + 1), slice(x2.min(), x2.max() + 1))
    return dict(Rm=Rm, poly=_clip_poly(corners, W, H), sl=sl, iou=iou, V=V, width=Wd, inter=int(inter),
                mu=mu, u=u, v=v, k=kt, dt=dt_, db=db, u0=max(u0, -far / 2), u1=min(u1, far / 2))


def stripe_color(src, V, Rm, known, q=50):
    pix = src[V & Rm & known]
    if len(pix) <= 50:
        return None
    labp = cv2.cvtColor(pix.astype(np.float32)[None], cv2.COLOR_RGB2Lab)[0]
    chroma = np.hypot(labp[:, 1], labp[:, 2])
    return np.median(pix[chroma >= np.percentile(chroma, q)], 0)


def photo_stripes(R, s_u8, img, occluder, photo, H, W, c):
    """Accent-colour stripes (e.g. orange bars) running behind the photo subject -> clean vector
    stripes. Simple and stable: blobs of the stripe colour -> group the ones lying on one line
    (seen left and right of the person) -> one parallelogram per group."""
    import math

    lab = _lab_image(s_u8)
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    hot = (chroma > c.stripe_min_chroma) & ~occluder
    if hot.sum() < c.band_min_px:
        return R, 0
    px = lab[hot].astype(np.float32)
    if len(px) > 40000:
        px = px[np.random.default_rng(0).choice(len(px), 40000, False)]
    k = 3
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, labl, centers = cv2.kmeans(px, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labl.ravel(), minlength=k)
    known = ~occluder
    new, gone = [], set()
    used = np.zeros((H, W), bool)
    log_ = __import__("logging").getLogger("split")
    for j in np.argsort(-counts):
        if counts[j] < 0.05 * len(px):
            continue
        ref = centers[j]
        ink = ink_match(lab, ref, c, c.stripe_chroma_frac) & known & ~used
        m = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        kc = int(c.stripe_close_px) | 1
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kc, kc)))
        n, cl, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        blobs, small = [], []
        for i in range(1, n):
            if st[i, cv2.CC_STAT_AREA] < c.stripe_bit_px:
                continue
            if st[i, cv2.CC_STAT_AREA] < c.band_min_px:
                ys, xs = np.nonzero(cl == i)
                P = np.stack([xs, ys], 1).astype(np.float64)
                small.append(dict(P=P, mu=P.mean(0)))
                continue
            ys, xs = np.nonzero(cl == i)
            P = np.stack([xs, ys], 1).astype(np.float64)
            mu = P.mean(0)
            _, _, vt = np.linalg.svd(P - mu, full_matrices=False)
            u = vt[0] if vt[0][0] >= 0 else -vt[0]
            v = np.array([-u[1], u[0]])
            pu, pv = (P - mu) @ u, (P - mu) @ v
            Lb = np.percentile(pu, 99) - np.percentile(pu, 1)
            Wb = np.percentile(pv, 98) - np.percentile(pv, 2)
            fill = len(P) / max(Lb * Wb, 1)
            log_.debug("  blob pita? %d px L%.0f W%.0f isi %.2f", len(P), Lb, Wb, fill)
            if Wb < c.stripe_min_width or Lb < c.stripe_min_aspect * Wb or fill < c.stripe_min_fill:
                small.append(dict(P=P, mu=mu))
                continue
            blobs.append(dict(P=P, mu=mu, u=u, ang=math.atan2(u[1], u[0]), W=Wb))
        # pieces of one stripe (left and right of the person): same direction, same line
        groups = []
        for bl in sorted(blobs, key=lambda b: -len(b["P"])):
            for g in groups:
                g0 = g[0]
                dang = abs((bl["ang"] - g0["ang"] + math.pi / 2) % math.pi - math.pi / 2)
                d = bl["mu"] - g0["mu"]
                off = abs(d @ np.array([-g0["u"][1], g0["u"][0]]))
                if dang < math.radians(c.stripe_merge_deg) and off < 0.6 * max(g0["W"], bl["W"]):
                    g.append(bl)
                    break
            else:
                groups.append([bl])
        # small visible bits of a stripe (between an elbow and the body) extend it
        for sb in small:
            for g in groups:
                g0 = g[0]
                d = sb["mu"] - g0["mu"]
                if abs(d @ np.array([-g0["u"][1], g0["u"][0]])) < 0.5 * g0["W"]:
                    g.append(dict(sb, u=g0["u"], ang=g0["ang"], W=g0["W"]))
                    break
        for g in groups:
            P = np.vstack([b["P"] for b in g])
            mu = P.mean(0)
            _, _, vt = np.linalg.svd(P - mu, full_matrices=False)
            u = vt[0] if vt[0][0] >= 0 else -vt[0]
            v = np.array([-u[1], u[0]])
            pu, pv = (P - mu) @ u, (P - mu) @ v
            t0, t1 = np.percentile(pv, 2), np.percentile(pv, 98)
            u0, u1 = np.percentile(pu, 0.5), np.percentile(pu, 99.5)
            far = 2.0 * (H + W)
            for side in (0, 1):
                ue = u0 if side == 0 else u1
                sel = np.abs(pu - ue) < 12
                ex, ey = P[sel, 0], P[sel, 1]
                sn = c.stripe_edge_snap  # ends this close to the canvas edge (behind a rack post) reach it
                if len(ex) and (ex.min() <= sn or ey.min() <= sn or ex.max() >= W - 1 - sn or ey.max() >= H - 1 - sn):
                    if side == 0:
                        u0 = -far
                    else:
                        u1 = far
            corners = np.array([mu + a_ * u + b_ * v for a_, b_ in ((u0, t0), (u1, t0), (u1, t1), (u0, t1))])
            Rm = np.zeros((H, W), np.uint8)
            cv2.fillPoly(Rm, [np.round(corners * 8).astype(np.int32)], 1, cv2.LINE_8, 3)
            Rm = Rm.astype(bool)
            if not Rm.any():
                continue
            col = stripe_color(img, ink, Rm, known, q=75)  # the lit ink, not its shadowed half
            if col is None:
                continue
            y2, x2 = np.nonzero(Rm)
            sl = (slice(y2.min(), y2.max() + 1), slice(x2.min(), x2.max() + 1))
            poly = _clip_poly(corners, W, H)
            new.append(dict(id=-1, sl=sl, m=Rm[sl], filled=Rm[sl], area=int(Rm.sum()), farea=int(Rm.sum()),
                            fill=dict(kind="solid", color=col, rmse=0, median=col), border=True,
                            shape=("polygon", dict(pts=poly - [sl[1].start, sl[0].start]), 1.0),
                            line=False, bg=False, stripe=True, z=len(R) + len(new),
                            ink=ink_match(lab, ref, c, c.stripe_chroma_frac)))
            used |= cv2.dilate(Rm.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
            gone |= absorb_into_stripe(R, Rm, int(Rm.sum()), gone, c, col)
    if not new:
        return R, 0
    # stripes of (almost) the same ink get exactly one colour: the most saturated one
    labs = [cv2.cvtColor(np.asarray(r["fill"]["color"], np.float32)[None, None], cv2.COLOR_RGB2Lab)[0, 0] for r in new]
    for i, r in enumerate(new):
        same = [j for j in range(len(new)) if np.linalg.norm(labs[i] - labs[j]) < c.stripe_same_color]
        best = max(same, key=lambda j: np.hypot(labs[j][1], labs[j][2]))
        r["fill"] = dict(new[best]["fill"])
    R2 = [r for r in R if id(r) not in gone] + new
    for z, r in enumerate(R2):
        r["z"] = z
    return R2, len(new)


def _merge_collinear(stripes, lab, img, known, occluder, H, W, c):
    """Two pieces of ONE stripe (seen left and right of a person) become one stripe."""
    import math

    def geom(r):
        p = r["shape"][1]["pts"] + [r["sl"][1].start, r["sl"][0].start]
        P = np.asarray(p, np.float64)
        ctr = P.mean(0)
        # long axis from the polygon's longest side
        best = None
        for i in range(len(P)):
            d = P[(i + 1) % len(P)] - P[i]
            if best is None or np.linalg.norm(d) > np.linalg.norm(best):
                best = d
        ang = math.atan2(best[1], best[0]) % math.pi
        return ctr, ang

    changed = True
    while changed and len(stripes) > 1:
        changed = False
        for i in range(len(stripes)):
            for j in range(i + 1, len(stripes)):
                a, b = stripes[i], stripes[j]
                ca, aa = geom(a)
                cb, ab = geom(b)
                dang = abs((aa - ab + math.pi / 2) % math.pi - math.pi / 2)
                if dang > math.radians(c.stripe_merge_deg):
                    continue
                d = cb - ca
                ux = np.array([math.cos(aa), math.sin(aa)])
                off = abs(d[0] * -ux[1] + d[1] * ux[0])
                wa = a["area"] / max(np.linalg.norm(d), 1)
                if off > 0.6 * max(a["shape"][1].get("w", 0) or 0, 60):
                    continue
                V = np.zeros((H, W), bool)
                for r in (a, b):
                    V[r["sl"]] |= r["m"]
                V &= ink_match(lab, cv2.cvtColor(np.asarray(a["fill"]["color"], np.float32)[None, None],
                                                  cv2.COLOR_RGB2Lab)[0, 0] * [100 / 255, 1, 1] - [0, 128, 128]
                               if False else _ref_of(a, lab), c, c.stripe_chroma_frac) | V
                ys, xs = np.nonzero(V)
                f = fit_band(V, np.stack([xs, ys], 1), known, occluder, H, W, c, lab, _ref_of(a, lab),
                             min_iou=c.stripe_iou * 0.8, min_occl=0, min_aspect=c.stripe_min_aspect,
                             chroma_frac=c.stripe_chroma_frac)
                if f is None:
                    continue
                Rm, sl = f["Rm"], f["sl"]
                m = dict(a)
                m.update(sl=sl, m=Rm[sl], filled=Rm[sl], area=int(Rm.sum()), farea=int(Rm.sum()),
                         shape=("polygon", dict(pts=f["poly"] - [sl[1].start, sl[0].start]), f["iou"]),
                         ink=a.get("ink"))
                stripes = [r for k, r in enumerate(stripes) if k not in (i, j)] + [m]
                changed = True
                break
            if changed:
                break
    return stripes


def _ref_of(r, lab):
    ys, xs = np.nonzero(r["m"])
    px = lab[ys + r["sl"][0].start, xs + r["sl"][1].start]
    ch = np.hypot(px[:, 1], px[:, 2])
    return np.median(px[ch >= np.percentile(ch, 50)], 0)


def absorb_into_stripe(R, Rm, band_area, gone, c, col=None):
    """Bits that belong to a stripe disappear into it: anything mostly inside it, and small bits
    (torn grunge edges, faded patches) hugging it. Their detail lives in the effect layer."""
    out = set()
    k = int(c.band_hug_px) * 2 + 1
    Rd = cv2.dilate(Rm.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(bool)
    k2 = 3 * k
    Rf = cv2.dilate(Rm.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k2, k2))).astype(bool)
    for r in R:
        if r is R[0] or id(r) in gone or r.get("stripe") or r["area"] >= band_area:
            continue
        inside = Rm[r["sl"]][r["m"]].mean()
        hug = Rd[r["sl"]][r["m"]].mean()
        if inside >= c.band_absorb or (hug >= 0.6 and r["area"] < c.band_bits_frac * band_area):
            out.add(id(r))
        elif col is not None and r["area"] < c.band_bits_frac * band_area and Rf[r["sl"]][r["m"]].mean() >= 0.6:
            rc = r["fill"]["color"] if r["fill"]["kind"] == "solid" else r["fill"]["median"]
            lc = cv2.cvtColor(np.asarray([rc, col], np.float32)[None], cv2.COLOR_RGB2Lab)[0]
            if np.linalg.norm(lc[0] - lc[1]) < 1.5 * c.band_color_tol:  # torn bits of the same ink
                out.add(id(r))
    return out


def ink_match(lab_img, ref, c, chroma_frac=None):
    """Pixels of the same ink as ref under any lighting: same hue, enough colour. (A stripe in
    a photo is lighter in the light and darker in the shadow, but stays orange.)"""
    a, b = lab_img[..., 1], lab_img[..., 2]
    ch = np.hypot(a, b)
    rch = float(np.hypot(ref[1], ref[2]))
    if rch < 15:  # neutral ink (black / white stripe): fall back to plain colour distance
        return np.linalg.norm(lab_img - ref, axis=-1) < c.band_pix_tol
    hue = np.degrees(np.arctan2(b, a))
    rh = np.degrees(np.arctan2(ref[2], ref[1]))
    dh = np.abs((hue - rh + 180) % 360 - 180)
    cf = c.band_min_chroma_frac if chroma_frac is None else chroma_frac
    return (dh < c.band_hue_tol) & (ch >= max(cf * rch, 12))


def thin_rules(img_u8, text_mask, H, W, c, photo=None):
    """Thin straight rules (1-6 px divider lines next to small text, underlines): too thin to
    become a region, so they are found directly and rebuilt as ONE straight line each."""
    gray = img_u8.astype(np.float32).mean(-1)
    bg = cv2.medianBlur(img_u8, 21).astype(np.float32).mean(-1)
    contrast = np.abs(gray - bg) > c.rule_contrast
    out = []
    L = int(c.rule_min_len)
    for horiz in (True, False):
        k = np.ones((1, L), np.uint8) if horiz else np.ones((L, 1), np.uint8)
        m = cv2.morphologyEx(contrast.astype(np.uint8), cv2.MORPH_OPEN, k)
        n, cl, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
        for i in range(1, n):
            x, y, w, h = st[i, :4]
            length, thick = (w, h) if horiz else (h, w)
            if thick > c.rule_max_thick or length < L:
                continue
            comp = cl == i
            if (comp & text_mask).mean() > 0.5 * comp.mean():  # mostly letters (an "I" stroke)
                continue
            if photo is not None and (comp & photo).any():
                continue
            # a rule lies ON a plain background: the same colour on both sides of it; the edge
            # of a shape has different colours on its two sides
            d = int(thick) + 4
            f32 = img_u8.astype(np.float32)
            if horiz:
                a_ = f32[max(y - d, 0), x:x + w]
                b_ = f32[min(y + h - 1 + d, H - 1), x:x + w]
            else:
                a_ = f32[y:y + h, max(x - d, 0)]
                b_ = f32[y:y + h, min(x + w - 1 + d, W - 1)]
            ys0, xs0 = np.nonzero(comp)
            ink_ = np.median(f32[ys0, xs0], 0)
            side = np.abs(np.median(a_, 0) - np.median(b_, 0)).max()
            if side > c.rule_side_tol or np.abs(np.median(a_, 0) - ink_).max() < c.rule_contrast:
                continue
            ys, xs = np.nonzero(comp)
            px_ = img_u8[ys, xs].astype(np.float32)
            dif = np.abs(px_.mean(-1) - bg[ys, xs])
            col = np.median(px_[dif >= np.percentile(dif, 70)], 0) / 255.0  # the ink, not its AA rim
            th = float(comp.sum()) / max(length, 1)
            if horiz:
                yc = float(np.median(ys)) + 0.5
                pts = np.array([[x, yc], [x + w, yc]], np.float64)
            else:
                xc = float(np.median(xs)) + 0.5
                pts = np.array([[xc, y], [xc, y + h]], np.float64)
            pad = int(np.ceil(th)) + 2
            sl = (slice(max(y - pad, 0), min(y + h + pad, H)), slice(max(x - pad, 0), min(x + w + pad, W)))
            mm = np.zeros((sl[0].stop - sl[0].start, sl[1].stop - sl[1].start), bool)
            local = pts - [sl[1].start, sl[0].start]
            cv2.line(mm.view(np.uint8), tuple(np.round(local[0]).astype(int)), tuple(np.round(local[1]).astype(int)),
                     1, max(1, int(round(th))))
            out.append(dict(id=-2, sl=sl, m=mm.astype(bool), filled=mm.astype(bool), area=int(mm.sum()),
                            farea=int(mm.sum()), fill=dict(kind="solid", color=col, rmse=0, median=col),
                            border=False, shape=("stroke", dict(pts=local, w=max(1.0, th)), 1.0),
                            line=True, bg=False, rule=True))
    return out


def _crisp(f, lab, ref, known, H, W, c):
    """A printed stripe has sharp long edges; a glow fades out softly."""
    ch = np.hypot(lab[..., 1], lab[..., 2])
    rch = float(np.hypot(ref[1], ref[2]))
    mu, u, v = f["mu"], f["u"], f["v"]
    diffs = []
    for d_, sgn in ((f["dt"], -1.0), (f["db"], 1.0)):
        for t in np.linspace(f["u0"], f["u1"], 40):
            e = d_ + f["k"] * t
            pin = mu + t * u + (e - sgn * 5) * v
            pout = mu + t * u + (e + sgn * 5) * v
            xi, yi, xo, yo = int(pin[0]), int(pin[1]), int(pout[0]), int(pout[1])
            if 0 <= xi < W and 0 <= yi < H and 0 <= xo < W and 0 <= yo < H and known[yi, xi] and known[yo, xo]:
                diffs.append(ch[yi, xi] - ch[yo, xo])
    if len(diffs) < 6:
        return True
    import logging
    logging.getLogger('split').debug('  tepi pita: %.2f x chroma', float(np.median(diffs)) / max(rch, 1))
    return float(np.median(diffs)) >= c.stripe_edge_contrast * rch

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


def fit_band(V, seed_pts, known, occluder, H, W, c, lab_img=None, ref=None, min_iou=None, min_occl=0.02):
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
    qx, qy = (xx - mu[0]).astype(np.float32), (yy - mu[1]).astype(np.float32)
    qv = qx * v[0] + qy * v[1]
    qu = qx * u[0] + qy * u[1]
    strip = np.abs(qv - np.median(pv_seed)) <= 0.9 * wd0 + 4
    if lab_img is not None and ref is not None:
        Vimg = ink_match(lab_img, ref, c) & strip & known
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
    bu, top, bot = [], [], []
    for i in range(nb):
        sel = (pu >= edges[i]) & (pu < edges[i + 1])
        if sel.sum() < 20:
            continue
        bu.append(pu[sel].mean())
        top.append(np.percentile(pv[sel], 3))
        bot.append(np.percentile(pv[sel], 97))
    if len(bu) < 4:
        return _why("r5", locals())
    bu, top, bot = map(np.array, (bu, top, bot))

    def robust_line(x, y):
        keep_ = np.ones(len(x), bool)
        k_, d_ = np.polyfit(x, y, 1)
        for _ in range(3):
            k_, d_ = np.polyfit(x[keep_], y[keep_], 1)
            res = y - (k_ * x + d_)
            mad = np.median(np.abs(res[keep_])) + 1e-6
            nk = np.abs(res) <= 2.5 * mad + 1.5
            if nk.sum() < 3:
                break
            keep_ = nk
        return k_, d_

    kt, dt_ = robust_line(bu, top)
    kb, db = robust_line(bu, bot)
    # occlusion only makes a stripe look narrower: push each edge out to its outer envelope
    q = float(c.band_envelope)
    dt_ += min(0.0, float(np.percentile(top - (kt * bu + dt_), 100 * q)))
    db += max(0.0, float(np.percentile(bot - (kb * bu + db), 100 * (1 - q))))
    far = 2.0 * (H + W)
    hidden = kn < 0.25 * np.maximum(tot, 1)  # bins where the stripe is behind the subject/text
    u0 = -far if reach0 else (run_u0 if hidden[i0:i0 + 2].any() else max(run_u0, np.percentile(pu, 2)))
    u1 = far if reach1 else (run_u1 if hidden[max(i1 - 1, 0):i1 + 1].any() else min(run_u1, np.percentile(pu, 98)))
    Wd = float(np.median(bot - top))
    if Wd < 4 or (u1 - u0) < 3 * Wd:
        return _why("r6", locals())
    corners = np.array([mu + uu * u + (k_ * uu + d_) * v
                        for uu, k_, d_ in ((u0, kt, dt_), (u1, kt, dt_), (u1, kb, db), (u0, kb, db))])
    Rm = np.zeros((H, W), np.uint8)
    cv2.fillPoly(Rm, [np.round(corners * 8).astype(np.int32)], 1, cv2.LINE_8, 3)
    Rm = Rm.astype(bool)
    if not Rm.any():
        return _why("r7", locals())
    inter = (Rm & V).sum()
    span = inrun & (qu >= u0) & (qu <= u1)
    union = ((Rm | (V & span)) & known).sum()
    iou = inter / max(union, 1)
    if iou < (c.band_iou if min_iou is None else min_iou) or (Rm & occluder).sum() < min_occl * Rm.sum():
        return _why("r8", locals())
    y2, x2 = np.nonzero(Rm)
    sl = (slice(y2.min(), y2.max() + 1), slice(x2.min(), x2.max() + 1))
    return dict(Rm=Rm, poly=_clip_poly(corners, W, H), sl=sl, iou=iou, V=V, width=Wd, inter=int(inter))


def stripe_color(src, V, Rm, known):
    pix = src[V & Rm & known]
    if len(pix) <= 50:
        return None
    labp = cv2.cvtColor(pix.astype(np.float32)[None], cv2.COLOR_RGB2Lab)[0]
    chroma = np.hypot(labp[:, 1], labp[:, 2])
    return np.median(pix[chroma >= np.percentile(chroma, 50)], 0)


def photo_stripes(R, s_u8, img, occluder, photo, H, W, c):
    """Accent-colour stripes (e.g. orange bars) partly hidden by the photo subject -> clean vector
    stripes. Colours are found in the image itself: the dominant strongly saturated colours."""
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
    for j in np.argsort(-counts):
        if counts[j] < 0.05 * len(px):
            continue
        ref = centers[j]
        V = ink_match(lab, ref, c) & known & ~used
        V = cv2.morphologyEx(V.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
        for _ in range(int(c.stripe_max)):
            Vc = cv2.morphologyEx(V.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
            n, cl, st, _ = cv2.connectedComponentsWithStats(Vc, connectivity=8)
            if n <= 1:
                break
            order = np.argsort(-st[1:, cv2.CC_STAT_AREA]) + 1
            fb = None
            for i in order[:8]:  # the stripe that explains the most stripe pixels wins
                if st[i, cv2.CC_STAT_AREA] < c.band_min_px:
                    break
                ys, xs = np.nonzero(cl == i)
                f = fit_band(V, np.stack([xs, ys], 1), known, occluder, H, W, c, lab, ref,
                             min_iou=c.stripe_iou, min_occl=c.stripe_min_hidden)
                import logging
                logging.getLogger("split").debug("  pita? seed %d px -> %s", len(xs), None if f is None else
                                                 (round(f["iou"], 2), round(f["width"]), f["inter"]))
                if f is not None and f["width"] >= c.stripe_min_width and (fb is None or f["inter"] > fb["inter"]):
                    fb = f
            if fb is None:
                break
            Rm = fb["Rm"]
            col = stripe_color(img, fb["V"], Rm, known)
            if col is None:
                break
            sl = fb["sl"]
            new.append(dict(id=-1, sl=sl, m=Rm[sl], filled=Rm[sl], area=int(Rm.sum()), farea=int(Rm.sum()),
                            fill=dict(kind="solid", color=col, rmse=0, median=col), border=True,
                            shape=("polygon", dict(pts=fb["poly"] - [sl[1].start, sl[0].start]), fb["iou"]),
                            line=False, bg=False, stripe=True, z=len(R) + len(new),
                            ink=ink_match(lab, ref, c)))
            used |= cv2.dilate(Rm.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
            V &= ~used
            gone |= absorb_into_stripe(R, Rm, int(Rm.sum()), gone, c, col)
    if not new:
        return R, 0
    R2 = [r for r in R if id(r) not in gone] + new
    for z, r in enumerate(R2):
        r["z"] = z
    return R2, len(new)


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


def ink_match(lab_img, ref, c):
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
    return (dh < c.band_hue_tol) & (ch >= max(c.band_min_chroma_frac * rch, 12))

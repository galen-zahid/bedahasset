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
    return palette


def fill_attr(f, gid: str):
    """(fill attribute, defs xml)"""
    if f["kind"] == "solid":
        return f'fill="{_hex(f["color"])}"', ""
    (x1, y1, c1), (x2, y2, c2) = f["stops"]
    defs = (f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{_f(x1)}" y1="{_f(y1)}" '
            f'x2="{_f(x2)}" y2="{_f(y2)}"><stop offset="0" stop-color="{_hex(c1)}"/>'
            f'<stop offset="1" stop-color="{_hex(c2)}"/></linearGradient>')
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

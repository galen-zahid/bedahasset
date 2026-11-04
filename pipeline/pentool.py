"""Pen-tool style vectors: clean pieces, smooth Bezier outlines, one fill per piece.

A designer rebuilding a flat design with the pen tool makes one shape per colour area, with
few anchor points and smooth curves, filled with a solid colour or a simple gradient. This
module does the same automatically:

1. pieces     the area is split into pieces that each have ONE fill. Start from small regions
              (palette components for vector art, superpixels for rendered backgrounds) and
              greedily merge neighbours while one linear colour model c(x,y) = a + b*x + c*y
              still explains both -> flat areas stay separate, gradient bands become one piece.
2. fill       per piece: solid colour, or a 2-stop linear gradient when the colour really
              changes across the piece (Canva edits solid SVG colours reliably; gradient stops
              are also written to pieces.csv to re-apply them in Canva if needed).
3. outline    contour -> light smoothing -> few anchors (Douglas-Peucker) -> cubic Bezier
              through the anchors (Catmull-Rom tangents), sharp corners kept as corners.
"""
from __future__ import annotations

import heapq
import io
import logging

import cv2
import numpy as np

from . import matting
from .gradients import _Stats

log = logging.getLogger("split")


# ----------------------------------------------------------------------------- pieces
def _stats(img, labels, n):
    H, W = labels.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    X = np.stack([np.ones_like(xx), xx / W, yy / H], -1).reshape(-1, 3)
    Y = img.reshape(-1, 3).astype(np.float64)
    lab = labels.ravel()
    order = np.argsort(lab, kind="stable")
    lab_s = lab[order]
    bounds = np.searchsorted(lab_s, np.arange(n + 1))
    st = {}
    for i in range(n):
        idx = order[bounds[i]:bounds[i + 1]]
        if len(idx) == 0:
            continue
        Xi, Yi = X[idx], Y[idx]
        st[i] = _Stats(Xi.T @ Xi, Xi.T @ Yi, (Yi * Yi).sum(0), len(idx))
    return st


def merge_pieces(img, labels, merge_tol, min_px, max_pieces, color_join=0.15):
    """labels: int map, -1 = outside. Returns (labels 0..k-1 / -1, betas, sizes)."""
    n = int(labels.max()) + 1
    if n <= 0:
        return labels, {}, {}
    st = _stats(img, np.where(labels < 0, n, labels), n + 1)
    st.pop(n, None)
    adj = set()
    for d0, d1 in ((labels[:, :-1], labels[:, 1:]), (labels[:-1, :], labels[1:, :])):
        m = (d0 != d1) & (d0 >= 0) & (d1 >= 0)
        p = np.stack([d0[m], d1[m]], 1)
        p.sort(1)
        adj.update(map(tuple, np.unique(p, axis=0)))
    parent = {i: i for i in st}
    # anti-alias rims: 1-2 px wide slivers of an in-between colour -> always merged away
    lab_c = np.where(labels < 0, n, labels)
    pad = np.pad(lab_c, 1, constant_values=n + 1)
    inner = np.ones_like(lab_c, bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            inner &= pad[1 + dy:1 + dy + lab_c.shape[0], 1 + dx:1 + dx + lab_c.shape[1]] == lab_c
    area = np.bincount(lab_c.ravel(), minlength=n + 2)
    core = np.bincount(lab_c[inner].ravel(), minlength=n + 2)
    thin = {i for i in st if core[i] < 0.25 * area[i]}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    nb = {i: set() for i in st}
    for a, b in adj:
        if a in nb and b in nb:
            nb[a].add(b)
            nb[b].add(a)
    # phase 1 (fast, no model): tiny pieces and anti-alias slivers join the neighbour with the
    # closest mean colour, smallest first
    mean = {i: st[i].xty[0] / st[i].n for i in st}
    for i in sorted(st, key=lambda i: st[i].n):
        if find(i) != i or not (st[i].n < min_px or i in thin):
            continue
        cands = {find(x) for x in nb[i]} - {i}
        if not cands:
            continue
        j = min(cands, key=lambda x: np.abs(mean[x] - mean[i]).max())
        st[j] = st[j] + st[i]
        mean[j] = st[j].xty[0] / st[j].n
        parent[i] = j
        nb[j] = ({find(x) for x in nb[j] | nb[i]}) - {j}
        thin.discard(j) if st[j].n >= min_px and j not in thin else None
    alive_ids = [i for i in st if find(i) == i]
    st = {i: st[i] for i in alive_ids}
    nb = {i: {find(x) for x in nb[i]} - {i} for i in alive_ids}
    thin = set()
    sse = {i: s.sse()[0] for i, s in st.items()}
    adj = {tuple(sorted((a, b))) for a in nb for b in nb[a]}

    def cost(a, b):
        j = st[a] + st[b]
        # error added per pixel of the SMALLER piece: a thin dark line on a white page is
        # expensive to absorb, two bands of the same gradient are cheap
        c = (j.sse()[0] - sse[a] - sse[b]) / min(st[a].n, st[b].n)
        if min(st[a].n, st[b].n) < min_px or a in thin or b in thin:  # tiny / rim slivers
            c -= 1e3
        else:  # different colours (dark line on a page) never become one gradient piece
            ma, mb = st[a].xty[0] / st[a].n, st[b].xty[0] / st[b].n
            if np.abs(ma - mb).max() > color_join:
                c += 1e3
        return c

    heap = [(cost(a, b), a, b) for a, b in adj if a in st and b in st]
    heapq.heapify(heap)
    alive = len(st)
    while heap and alive > 1:
        cst, a, b = heapq.heappop(heap)
        a, b = find(a), find(b)
        if a == b:
            continue
        cur = cost(a, b)
        if abs(cur - cst) > 1e-12:
            heapq.heappush(heap, (cur, a, b))
            continue
        if cur > merge_tol and (alive <= max_pieces or cur > 500):
            break
        if (st[b].n > st[a].n and a not in thin) or (b not in thin and a in thin):
            a, b = b, a  # keep the solid (non-sliver, larger) piece as the root
        st[a] = st[a] + st[b]
        sse[a] = st[a].sse()[0]
        parent[b] = a
        alive -= 1
        nb[a] = ({find(x) for x in nb[a] | nb[b]}) - {a}
        for x in nb[a]:
            nb[x].discard(b)
            nb[x].add(a)
            heapq.heappush(heap, (cost(a, x), a, x))
    roots = sorted({find(i) for i in st}, key=lambda r: -st[r].n)
    rix = {r: k for k, r in enumerate(roots)}
    remap = np.full(n + 1, -1, np.int32)
    for i in parent:
        remap[i] = rix[find(i)]
    out = remap[np.where(labels < 0, n, labels)]
    betas = {k: st[r].sse()[1] for k, r in enumerate(roots)}
    sizes = {k: st[r].n for k, r in enumerate(roots)}
    return out, betas, sizes


def palette_components(rgb, mask, max_colors, min_px):
    """Initial pieces for vector art: palette colour x connected component (keeps thin lines)."""
    pix = rgb[mask].astype(np.float32)
    k = int(min(max_colors, max(2, len(np.unique((pix * 16).astype(np.int32), axis=0)))))
    sample = pix if len(pix) <= 40000 else pix[np.random.default_rng(0).choice(len(pix), 40000, False)]
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.002)
    _, _, centers = cv2.kmeans(sample, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    pal = np.full(mask.shape, -1, np.int32)
    pal[mask] = np.linalg.norm(pix[:, None, :] - centers[None], axis=-1).argmin(1)
    labels = np.full(mask.shape, -1, np.int32)
    nxt = 0
    for j in range(k):
        n, lab = cv2.connectedComponents((pal == j).astype(np.uint8), connectivity=8)
        sel = lab > 0
        labels[sel] = lab[sel] - 1 + nxt
        nxt += n - 1
    return labels


# ------------------------------------------------------------------------------- fill
def piece_fill(beta, m, W, H, min_delta):
    """('solid', c) or ('linear', (x1, y1, c1), (x2, y2, c2)) for one piece."""
    ys, xs = np.nonzero(m)
    Gm = beta[1:].T * np.array([1 / W, 1 / H])
    _, _, vt = np.linalg.svd(Gm)
    d = vt[0]
    proj = xs * d[0] + ys * d[1]
    p0, p1 = np.percentile(proj, [1, 99])
    cx, cy = xs.mean(), ys.mean()
    off = cx * d[0] + cy * d[1]
    ends = []
    for p in (p0, p1):
        x, y = cx + (p - off) * d[0], cy + (p - off) * d[1]
        ends.append((x, y, np.clip(np.array([1, x / W, y / H]) @ beta, 0, 1)))
    if np.abs(ends[0][2] - ends[1][2]).max() < min_delta:
        c = np.clip(np.array([1, cx / W, cy / H]) @ beta, 0, 1)
        return ("solid", c)
    return ("linear", ends[0], ends[1])


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(float(v) * 255)) for v in c)


# ---------------------------------------------------------------------------- outline
def bezier_d(mask, eps=1.2, corner_deg=55.0, smooth=1.0, min_len=6) -> str:
    """Pen-tool outline of a mask (outer contours + holes) as an SVG path 'd'."""
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    cos_c = np.cos(np.radians(corner_deg))
    for cnt in cnts:
        p = cnt.reshape(-1, 2).astype(np.float64)
        if len(p) < min_len:
            continue
        if smooth > 0 and len(p) > 12:
            r = int(3 * smooth)
            k = np.exp(-0.5 * (np.arange(-r, r + 1) / smooth) ** 2)
            k /= k.sum()
            pw = np.vstack([p[-r:], p, p[:r]])
            p = np.stack([np.convolve(pw[:, i], k, "valid") for i in range(2)], 1)
        a = cv2.approxPolyDP(p.astype(np.float32).reshape(-1, 1, 2), eps, True).reshape(-1, 2)
        n = len(a)
        if n < 3:
            continue
        corner = np.zeros(n, bool)
        for i in range(n):
            u, v = a[i] - a[i - 1], a[(i + 1) % n] - a[i]
            nu, nv = np.linalg.norm(u), np.linalg.norm(v)
            if nu > 0 and nv > 0 and (u @ v) / (nu * nv) < cos_c:
                corner[i] = True
        seg = [f"M{a[0][0]:.1f} {a[0][1]:.1f}"]
        for i in range(n):
            p0, p1, p2, p3 = a[i - 1], a[i], a[(i + 1) % n], a[(i + 2) % n]
            c1 = p1 if corner[i] else p1 + (p2 - p0) / 6
            c2 = p2 if corner[(i + 1) % n] else p2 - (p3 - p1) / 6
            seg.append(f"C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {p2[0]:.1f} {p2[1]:.1f}")
        parts.append(" ".join(seg) + " Z")
    return " ".join(parts)


# -------------------------------------------------------------------------------- svg
def pieces_to_svg(labels, betas, W, H, cfg, ids=None, base_fill_mask=None):
    """SVG text + per-piece rows. Big pieces first; each grown 1px (no seams)."""
    c = cfg.pentool
    defs, body, rows = [], [], []
    ids = sorted(betas, key=lambda k: -(labels == k).sum()) if ids is None else ids
    for gi, k in enumerate(ids):
        m = labels == k
        if not m.any():
            continue
        f = piece_fill(betas[k], m, W, H, c.gradient_min_delta)
        grow = matting.dilate(m, int(c.overlap_px))
        if base_fill_mask is not None:
            grow &= base_fill_mask
        d = bezier_d(grow, c.anchor_eps, c.corner_deg, c.smooth)
        if not d:
            continue
        if f[0] == "solid":
            fill = _hex(f[1])
            rows.append({"piece": gi + 1, "fill": "solid", "color1": fill, "color2": "",
                         "angle_deg": ""})
        else:
            (x1, y1, c1), (x2, y2, c2) = f[1], f[2]
            gid = f"g{gi}"
            defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{x1:.1f}" '
                        f'y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"><stop offset="0" '
                        f'stop-color="{_hex(c1)}"/><stop offset="1" stop-color="{_hex(c2)}"/>'
                        f'</linearGradient>')
            fill = f"url(#{gid})"
            ang = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            rows.append({"piece": gi + 1, "fill": "gradient", "color1": _hex(c1),
                         "color2": _hex(c2), "angle_deg": round(ang, 1)})
        body.append(f'<path id="piece_{gi + 1:02d}" fill="{fill}" fill-rule="evenodd" d="{d}"/>')
    svg = (f'<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">\n' + (f"<defs>{''.join(defs)}</defs>\n" if defs else "")
           + "\n".join(body) + "\n</svg>\n")
    return svg, rows


def render_svg(svg: str, W: int, H: int):
    """SVG -> (rgb float, alpha float) exactly as a browser/Canva draws it."""
    import resvg_py
    from PIL import Image

    im = Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg)))).convert("RGBA")
    if im.size != (W, H):
        im = im.resize((W, H))
    a = np.asarray(im).astype(np.float32) / 255.0
    return a[..., :3], a[..., 3]


# ---------------------------------------------------------------------------- drivers
def vectorize_element(rgb, alpha, cfg):
    """One vector element -> (svg, rows, rgb, alpha) of the clean pen-tool version."""
    c = cfg.pentool
    H, W = alpha.shape
    m = alpha > 0.5
    # drop stray specks far from the element (text remnants, dust): keep components that are a
    # real part of it
    n_, lab_, st_, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
    if n_ > 2:
        big = st_[1:, 4].max()
        keep = st_[:, 4] >= c.min_part_frac * big
        keep[0] = False
        m = keep[lab_]
        alpha = np.where(m | (alpha <= 0.5), alpha, 0).astype(np.float32)
    ys, xs = np.nonzero(m)
    if len(xs) < 30:
        return None
    pad = 4
    x0, y0 = max(xs.min() - pad, 0), max(ys.min() - pad, 0)
    x1, y1 = min(xs.max() + pad + 1, W), min(ys.max() + pad + 1, H)
    cr, cm = rgb[y0:y1, x0:x1], m[y0:y1, x0:x1]
    lab = palette_components(cr, cm, int(c.max_colors), int(c.min_piece_px))
    lab, betas, sizes = merge_pieces(cr, lab, c.merge_tol, int(c.min_piece_px), int(c.max_pieces),
                                     c.color_join)
    full = np.full((H, W), -1, np.int32)
    full[y0:y1, x0:x1] = lab
    fit_betas = {}
    for k, b in betas.items():  # crop coords -> canvas coords
        bw, bh = x1 - x0, y1 - y0
        a0 = b[0] - b[1] * x0 / bw - b[2] * y0 / bh
        fit_betas[k] = np.stack([a0, b[1] * W / bw, b[2] * H / bh])
    svg, rows = pieces_to_svg(full, fit_betas, W, H, cfg, base_fill_mask=matting.dilate(m, 1))
    r_rgb, r_a = render_svg(svg, W, H)
    iou = float(((r_a > 0.5) & m).sum() / max(((r_a > 0.5) | m).sum(), 1))
    # fidelity of the piece INTERIORS (edges excluded): flat art is reproduced almost exactly,
    # photographic shading is not
    inside = matting.erode((r_a > 0.5) & m, 3)
    if inside.sum() < 50:
        inside = (r_a > 0.5) & m
    rms = float(np.median(np.abs(r_rgb[inside] - rgb[inside]).max(-1))) if inside.any() else 1.0
    return svg, rows, r_rgb, r_a, iou, rms


def vectorize_background(plate, cfg):
    """Graphic background -> list of pieces [(svg, row, rgb, alpha)] + one effects layer."""
    from .glow import color_to_alpha
    from .gradients import _fit_regions, segment

    c, g = cfg.pentool, cfg.gradients
    H, W = plate.shape[:2]
    s = g.work_size / max(H, W)
    small = cv2.resize(plate, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    g["max_shapes"] = int(c.bg_max_pieces)
    lab_s, _ = segment(small, cfg)
    n = int(lab_s.max()) + 1
    labels = cv2.resize(lab_s.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    for k in range(n):  # smooth the staircase of the upscaled label map
        m = (labels == k).astype(np.float32)
        labels[cv2.GaussianBlur(m, (0, 0), g.edge_smooth / s) > 0.5] = k
    stats, _ = _fit_regions(plate, labels)
    betas = {k: st.sse()[1] for k, st in stats.items()}
    order = sorted(betas, key=lambda k: -(labels == k).sum())
    pieces = []
    acc = np.zeros((H, W, 3), np.float32)
    for i, k in enumerate(order):
        m = labels == k
        if i == 0:
            m = np.ones_like(m)  # bottom piece fills the whole canvas: no gaps anywhere
        sub = np.where(m, k, -1)
        svg, rows = pieces_to_svg(sub, {k: betas[k]}, W, H, cfg)
        rgb, a = render_svg(svg, W, H)
        acc = acc * (1 - a[..., None]) + rgb * a[..., None]
        row = rows[0] if rows else {}
        pieces.append((svg, row, rgb, a))
    fx_a, fx_rgb = color_to_alpha(plate, acc)
    fx_a = np.where(fx_a < 1.0 / 255, 0, fx_a).astype(np.float32)
    err = float(np.sqrt(((acc - plate) ** 2).mean()))
    if err < g.flat_rms:  # flat background: the pieces ARE the background, no effects layer
        fx_a = np.zeros_like(fx_a)
    log.info("  pen tool background: %d potongan (%d gradien, %d solid), rms %.3f, efek %.0f%% kanvas",
             len(pieces), sum(1 for p in pieces if p[1].get("fill") == "gradient"),
             sum(1 for p in pieces if p[1].get("fill") == "solid"), err, 100 * (fx_a > 0.05).mean())
    return pieces, (fx_rgb, fx_a)

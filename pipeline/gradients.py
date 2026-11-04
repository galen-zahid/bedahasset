"""Step: rebuild a graphic background as editable gradient shapes + effect layers.

Graphic designs (rendered gradients, swooshes, glossy ribbons) are not photos: they are built
from a handful of gradient-filled shapes plus glow / reflection effects. This step recovers
that structure:

1. superpixels (SLIC) are merged greedily while ONE linear gradient still explains both
   neighbours (merge cost = increase of the least-squares error of a joint linear colour model
   c(x, y) = a + b*x + c*y). The number of shapes adapts to the image.
2. every final region -> an SVG path filled with a linearGradient (direction = main direction
   of the fitted colour change, stops = model colours at the region's extent).
3. what the gradients do not explain is split into effect layers, normal blend only:
     shadow      low-frequency darkening (black with alpha)
     glow        low-frequency light (colour-to-alpha against the shading so far)
     reflection  sharp highlights and fine detail (minimal colour-to-alpha) -> exact rebuild
If the background needs too many shapes to be explained (a photo), the step is skipped.
"""
from __future__ import annotations

import heapq
import logging
from pathlib import Path

import cv2
import numpy as np

from . import matting
from .glow import color_to_alpha

log = logging.getLogger("split")


class _Stats:
    __slots__ = ("xtx", "xty", "yty", "n")

    def __init__(self, xtx, xty, yty, n):
        self.xtx, self.xty, self.yty, self.n = xtx, xty, yty, n

    def __add__(self, o):
        return _Stats(self.xtx + o.xtx, self.xty + o.xty, self.yty + o.yty, self.n + o.n)

    def sse(self, ridge=1e-6):
        beta = np.linalg.solve(self.xtx + ridge * np.eye(3), self.xty)
        return float(self.yty.sum() - (self.xty * beta).sum()), beta


def _fit_regions(img: np.ndarray, labels: np.ndarray):
    H, W = labels.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    X = np.stack([np.ones_like(xx), xx / W, yy / H], -1).reshape(-1, 3)
    Y = img.reshape(-1, 3).astype(np.float64)
    lab = labels.ravel()
    n = lab.max() + 1
    stats = {}
    for i in range(n):
        idx = lab == i
        if not idx.any():
            continue
        Xi, Yi = X[idx], Y[idx]
        stats[i] = _Stats(Xi.T @ Xi, Xi.T @ Yi, (Yi * Yi).sum(0), int(idx.sum()))
    return stats, X


def _adjacency(labels):
    a = set()
    for d0, d1 in ((labels[:, :-1], labels[:, 1:]), (labels[:-1, :], labels[1:, :])):
        m = d0 != d1
        pairs = np.stack([d0[m], d1[m]], 1)
        pairs.sort(1)
        a.update(map(tuple, np.unique(pairs, axis=0)))
    return a


def segment(img: np.ndarray, cfg, valid: np.ndarray | None = None):
    """Greedy RAG merge of SLIC superpixels under a linear-gradient model.
    Returns (labels HxW int, list of region ids, betas dict) or None if it is a photo."""
    from skimage.segmentation import slic

    c = cfg.gradients
    H, W = img.shape[:2]
    sp = slic(img, n_segments=int(c.superpixels), compactness=c.compactness, start_label=0,
              channel_axis=2)
    stats, _ = _fit_regions(img, sp)
    adj = _adjacency(sp)
    parent = {i: i for i in stats}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sse = {i: s.sse()[0] for i, s in stats.items()}
    nbrs = {i: set() for i in stats}
    for a, b in adj:
        nbrs[a].add(b)
        nbrs[b].add(a)
    heap = []

    def cost(a, b):
        j = stats[a] + stats[b]
        return (j.sse()[0] - sse[a] - sse[b]) / j.n

    for a, b in adj:
        heapq.heappush(heap, (cost(a, b), a, b))
    alive = len(stats)
    while heap and alive > c.min_shapes:
        cst, a, b = heapq.heappop(heap)
        if find(a) != a or find(b) != b or a == b:
            continue
        cur = cost(a, b)
        if abs(cur - cst) > 1e-12:  # stale entry
            heapq.heappush(heap, (cur, a, b))
            continue
        small = min(stats[a].n, stats[b].n) < c.min_region_frac * H * W
        if cur > c.merge_tol and not small and alive <= c.max_shapes:
            break
        # merge b into a
        stats[a] = stats[a] + stats[b]
        sse[a] = stats[a].sse()[0]
        parent[b] = a
        alive -= 1
        nbrs[a] |= nbrs[b]
        nbrs[a] = {find(x) for x in nbrs[a]} - {a}
        for x in nbrs[a]:
            nbrs[x] = {find(y) for y in nbrs[x]} - {x}
            nbrs[x].add(a)
            heapq.heappush(heap, (cost(a, x), a, x))
    roots = sorted({find(i) for i in stats}, key=lambda r: -stats[r].n)
    remap = np.zeros(sp.max() + 1, np.int32)
    for i in stats:
        remap[i] = roots.index(find(i))
    labels = remap[sp]
    betas = {k: stats[r].sse()[1] for k, r in enumerate(roots)}
    return labels, betas


def render(labels, betas, H, W):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    X = np.stack([np.ones_like(xx), xx / W, yy / H], -1)
    out = np.zeros((H, W, 3), np.float32)
    for k, b in betas.items():
        m = labels == k
        out[m] = X[m] @ b.astype(np.float32)
    return np.clip(out, 0, 1)


def _gradient_line(beta, m, H, W):
    """SVG linearGradient endpoints + stop colours for one region's linear colour model."""
    G = beta[1:].T * np.array([1 / W, 1 / H])  # 3 channels x (d/dx, d/dy) in pixel units
    u, s, vt = np.linalg.svd(G)
    d = vt[0]
    ys, xs = np.nonzero(m)
    proj = xs * d[0] + ys * d[1]
    p0, p1 = np.percentile(proj, [0, 100])
    cx, cy = xs.mean(), ys.mean()
    off = cx * d[0] + cy * d[1]
    pts = []
    for p in (p0, p1):
        x, y = cx + (p - off) * d[0], cy + (p - off) * d[1]
        col = np.clip(np.array([1, x / W, y / H]) @ beta, 0, 1)
        pts.append((x, y, col))
    return pts


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(float(v) * 255)) for v in c)


def _path(mask, eps):
    cnts, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts = []
    for cnt in cnts:
        ap = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(ap) >= 3:
            parts.append("M" + " L".join(f"{x} {y}" for x, y in ap) + " Z")
    return " ".join(parts)


def decompose(plate: np.ndarray, cfg, out_dir: Path):
    """Returns dict with layers + svg path, or None when the background is photographic."""
    c = cfg.gradients
    H, W = plate.shape[:2]
    s = c.work_size / max(H, W)
    small = cv2.resize(plate, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    res = segment(small, cfg)
    if res is None:
        return None
    lab_s, betas = res
    n = len(betas)
    approx = render(lab_s, betas, *lab_s.shape)
    err = float(np.sqrt(((approx - small) ** 2).mean()))
    labels = cv2.resize(lab_s.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    # smooth region borders a little (pixel staircase from the upscaled label map)
    for k in range(n):
        m = (labels == k).astype(np.float32)
        labels[cv2.GaussianBlur(m, (0, 0), c.edge_smooth / s) > 0.5] = k
    # re-fit at full resolution so the gradients are exact for the final regions
    stats, _ = _fit_regions(plate, labels)
    betas = {k: st.sse()[1] for k, st in stats.items()}
    # raster of EXACTLY what the SVG shows: each region = 2-stop gradient along its line
    lines = {k: _gradient_line(betas[k], labels == k, H, W) for k in betas}
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    G = np.zeros((H, W, 3), np.float32)
    for k, ((x1, y1, c1), (x2, y2, c2)) in lines.items():
        m = labels == k
        dx, dy = x2 - x1, y2 - y1
        t = ((xx[m] - x1) * dx + (yy[m] - y1) * dy) / max(dx * dx + dy * dy, 1e-6)
        t = np.clip(t, 0, 1)[:, None]
        G[m] = (1 - t) * c1 + t * c2

    # SVG: biggest region first, as the canvas base; others on top (1px overlap -> no seams)
    defs, body = [], []
    order = sorted(betas, key=lambda k: -(labels == k).sum())
    for i, k in enumerate(order):
        m = labels == k
        (x1, y1, c1), (x2, y2, c2) = lines[k]
        gid = f"g{i}"
        defs.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{x1:.1f}" '
                    f'y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}"><stop offset="0" stop-color="{_hex(c1)}"/>'
                    f'<stop offset="1" stop-color="{_hex(c2)}"/></linearGradient>')
        shape = f'M0 0 L{W} 0 L{W} {H} L0 {H} Z' if i == 0 else _path(matting.dilate(m, 1), c.svg_epsilon)
        body.append(f'<path fill="url(#{gid})" d="{shape}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
           f'<defs>{"".join(defs)}</defs>\n' + "\n".join(body) + "\n</svg>\n")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "01_background_gradients.svg").write_text(svg, encoding="utf-8")

    # effects (normal blend, stacked in this order):
    #   shadow      soft darkening            glow   soft coloured light
    #   reflection  sharp bright highlights   detail small leftovers (hide it for a cleaner look)
    LUM = np.array([0.299, 0.587, 0.114], np.float32)
    sig = c.effect_sigma
    low = cv2.GaussianBlur(plate, (0, 0), sig)
    Lg, Ll = G @ LUM, low @ LUM
    sh_a = np.clip(1 - Ll / np.maximum(Lg, 1e-3), 0, c.max_effect_alpha).astype(np.float32)
    sh_a = np.where(sh_a < c.min_effect_alpha, 0, sh_a).astype(np.float32)
    X1 = G * (1 - sh_a[..., None])
    gl_a, gl_rgb = color_to_alpha(low, X1, brighten_only=True)
    gl_a = np.where(gl_a < c.min_effect_alpha, 0, np.clip(gl_a, 0, c.max_effect_alpha)).astype(np.float32)
    X2 = X1 * (1 - gl_a[..., None]) + gl_rgb * gl_a[..., None]
    rf_a, rf_rgb = color_to_alpha(plate, X2, brighten_only=True)
    lift = (plate @ LUM) - (X2 @ LUM)
    rf_a = np.where(lift > c.reflection_min_lift, rf_a, 0).astype(np.float32)
    rf_a = matting.feather(rf_a, 0.7)
    X3 = X2 * (1 - rf_a[..., None]) + rf_rgb * rf_a[..., None]
    dt_a, dt_rgb = color_to_alpha(plate, X3)
    dt_a = np.where(dt_a < 1.0 / 255, 0, dt_a).astype(np.float32)
    if err < c.flat_rms:  # near-flat background: effect layers would only hold noise
        sh_a[:] = 0
        gl_a[:] = 0
        rf_a[:] = 0
        dt_a, dt_rgb = color_to_alpha(plate, G)
        dt_a = np.where(dt_a < c.min_effect_alpha, 0, dt_a).astype(np.float32)
    log.info("  gradien: %d bidang gradien (rms %.3f) | shadow %.0f%%, glow %.0f%%, reflection %.0f%%, "
             "detail %.0f%% kanvas", n, err, 100 * (sh_a > 0.05).mean(), 100 * (gl_a > 0.05).mean(),
             100 * (rf_a > 0.05).mean(), 100 * (dt_a > 0.05).mean())
    black = np.zeros_like(plate)
    return {
        "gradient_rgb": G, "n_shapes": n, "svg": "vectors/01_background_gradients.svg",
        "effects": [("shadow", black, sh_a), ("glow", gl_rgb, gl_a), ("reflection", rf_rgb, rf_a),
                    ("detail", dt_rgb, dt_a)],
    }

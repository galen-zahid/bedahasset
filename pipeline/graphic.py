"""Step: graphic (non-photo) background -> clean editable layers.

  01_bg_NN_*.png/.svg   gradient / solid pieces (pen tool), bottom piece fills the canvas
  01_fx_light.png       ONE soft light & shade layer over the whole canvas (glow, vignette)
  01_fx_highlight.png   ONE layer with the sharp highlights (reflections, light streaks)
  03_accent_NN_*.png/.svg  thin graphic strokes in an accent colour (gold arrows / lines),
                        one solid-colour SVG per accent colour -> recolour in one click

Effects are measured against a heavily smoothed version of the background, so they are
general soft light / sharp shine, not blocky leftovers that follow the piece outlines.
Inpainted areas (where text was) are smoothed first: no blotches behind headlines.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import matting
from .glow import _hsv, _hue_dist, color_to_alpha
from .pentool import _hex, pieces_to_svg, render_svg

log = logging.getLogger("split")
LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def smooth_inpainted(plate, inp_mask, sigma):
    """Blotches from inpainting large text on smooth graphics -> smooth fill from around."""
    if not inp_mask.any():
        return plate
    known = (~inp_mask).astype(np.float32)
    num = cv2.GaussianBlur(plate * known[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(known, (0, 0), sigma)[..., None]
    fill = np.where(den > 1e-3, num / np.maximum(den, 1e-3), cv2.GaussianBlur(plate, (0, 0), sigma))
    w = matting.feather(matting.dilate(inp_mask, 3).astype(np.float32), 3)[..., None]
    return (plate * (1 - w) + fill * w).astype(np.float32)


def find_accents(plate, exclude, cfg):
    """Saturated colours that differ from the dominant background hue (gold on blue)."""
    c = cfg.graphic
    H, W = plate.shape[:2]
    h, s, v = _hsv(plate)
    sat = (s > c.accent_min_sat) & (v > c.accent_min_val) & ~exclude
    if sat.sum() < 100:
        return []
    hist, edges = np.histogram(h[sat], bins=36, range=(0, 360), weights=(s * v)[sat])
    dom = (edges[hist.argmax()] + 5)
    out = []
    taken = np.zeros_like(sat)
    for b in np.argsort(-hist):
        hue = edges[b] + 5
        if hist[b] <= 0 or _hue_dist(np.array([hue]), dom)[0] < c.accent_min_hue_gap:
            continue
        if any(_hue_dist(np.array([hue]), o)[0] < 30 for o, _ in out):
            continue
        m = sat & (_hue_dist(h, hue) < c.accent_hue_tol) & ~taken
        n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, 4] >= c.accent_min_part_px
        m = keep[lab]
        if m.sum() < c.accent_min_frac * H * W:
            continue
        taken |= m
        out.append((hue, m))
        if len(out) >= c.max_accents:
            break
    return out


def decompose(plate, img, inp_mask, exclude, models, cfg):
    from .background import clean_plate
    from .gradients import _fit_regions, segment

    c, g, pc = cfg.graphic, cfg.gradients, cfg.pentool
    H, W = plate.shape[:2]
    base = smooth_inpainted(plate, inp_mask, c.inpaint_smooth)

    # --- accent strokes (removed from the base, one solid-colour layer per colour)
    accents = []
    acc_masks = find_accents(base, exclude | inp_mask, cfg)
    if acc_masks:
        allm = np.zeros((H, W), bool)
        for _, m in acc_masks:
            allm |= m
        base = clean_plate(base, matting.dilate(allm, 3), models, cfg)
        for hue, m in acc_masks:
            px = plate[m]
            col = np.median(px[(px @ LUMA) >= np.percentile(px @ LUMA, 50)], axis=0)
            shape = matting.dilate(m, 1)
            lab = np.where(shape, 0, -1)
            svg, _ = pieces_to_svg(lab, {0: np.array([col, np.zeros(3), np.zeros(3)])}, W, H, cfg)
            rgb, a = render_svg(svg, W, H)
            accents.append((svg, _hex(col), rgb, a))
            log.info("  aksen: warna %s, %d px -> 1 layer SVG solid", _hex(col), int(m.sum()))

    # --- gradient / solid pieces on the cleaned base
    s = g.work_size / max(H, W)
    small = cv2.resize(base, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    g["max_shapes"] = int(pc.bg_max_pieces)
    lab_s, _ = segment(small, cfg)
    n = int(lab_s.max()) + 1
    labels = cv2.resize(lab_s.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    for k in range(n):
        m = (labels == k).astype(np.float32)
        labels[cv2.GaussianBlur(m, (0, 0), g.edge_smooth / s) > 0.5] = k
    stats, _ = _fit_regions(base, labels)
    betas = {k: st.sse()[1] for k, st in stats.items()}
    order = sorted(betas, key=lambda k: -(labels == k).sum())
    pieces = []
    acc = np.zeros((H, W, 3), np.float32)
    for i, k in enumerate(order):
        m = np.ones((H, W), bool) if i == 0 else labels == k
        svg, rows = pieces_to_svg(np.where(m, k, -1), {k: betas[k]}, W, H, cfg)
        rgb, a = render_svg(svg, W, H)
        acc = acc * (1 - a[..., None]) + rgb * a[..., None]
        pieces.append((svg, rows[0] if rows else {}, rgb, a))

    # --- effects: general soft light + sharp highlights
    effects = []
    err = float(np.sqrt(((acc - base) ** 2).mean()))
    if err >= g.flat_rms:
        soft = cv2.GaussianBlur(base, (0, 0), c.light_sigma)
        la, lrgb = color_to_alpha(soft, acc)
        la = cv2.GaussianBlur(la, (0, 0), c.light_sigma / 2)
        lrgb = cv2.GaussianBlur(lrgb, (0, 0), c.light_sigma / 2)
        la = np.where(la < c.min_alpha, 0, np.clip(la, 0, c.max_alpha)).astype(np.float32)
        X = acc * (1 - la[..., None]) + lrgb * la[..., None]
        L = base @ LUMA
        top = L - cv2.morphologyEx(L, cv2.MORPH_OPEN, matting.disk(int(c.highlight_px)))
        hm = matting.feather((top > c.highlight_min).astype(np.float32), 1.0)
        ha, hrgb = color_to_alpha(base, X, brighten_only=True)
        ha = np.where(ha * hm < c.min_alpha, 0, ha * hm).astype(np.float32)
        if la.max() > 0:
            effects.append(("light", lrgb.astype(np.float32), la))
        if ha.max() > 0:
            effects.append(("highlight", hrgb.astype(np.float32), ha))
    log.info("  grafis: %d potongan bg, %d aksen, efek: %s (rms bg %.3f)", len(pieces), len(accents),
             ", ".join(e[0] for e in effects) or "-", err)
    return pieces, effects, accents

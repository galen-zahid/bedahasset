"""Step: dust / chalk / sparks overlay (bright, low-saturation, small blobs).

Same decomposition idea as glow: C = (1 - a) * B + a * P with P the particle colour and
B the local background (morphological opening), so removing them from the plate and
stacking the overlay back is lossless.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import matting
from .glow import color_to_alpha, recombine_base
from .imageio import to_u8

LUMA = np.array([0.299, 0.587, 0.114], np.float32)

log = logging.getLogger("split")


def _cloud(plate, cand, excl, models, cfg):
    """Dense dust/chalk clouds: regions with a high density of particle specks.
    Base under the cloud = LaMa inpaint, cloud = brighten-only colour-to-alpha against it."""
    from .background import clean_plate

    c = cfg.particles.cloud
    H, W = cand.shape
    dens = cv2.GaussianBlur(cand.astype(np.float32), (0, 0), c.density_sigma)
    reg = (dens > c.density_threshold) & ~excl
    n, lab, st, _ = cv2.connectedComponentsWithStats(reg.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        w, h, a = st[i, 2], st[i, 3], st[i, 4]
        if a < c.min_area_frac * H * W:
            continue
        if max(w, h) / max(min(w, h), 1) > c.max_aspect:  # racks (tall) / floor bands (wide)
            continue
        keep[i] = True
    reg = keep[lab]
    if not reg.any():
        return None, None, plate
    soft = matting.feather(matting.dilate(reg, int(c.density_sigma)).astype(np.float32), c.density_sigma / 2)
    B = clean_plate(plate, soft > 0.05, models, cfg)
    a, G = color_to_alpha(plate, B, brighten_only=True)
    chroma = G.max(-1) - G.min(-1)
    a = a * soft * np.clip(1 - (chroma - c.max_chroma) / 0.1, 0, 1) * ~excl
    a = np.clip(a, 0, cfg.particles.max_alpha).astype(np.float32)
    a[a < 1.0 / 255] = 0
    log.info("  particles: awan debu/kapur %d px", int((a > 0.05).sum()))
    return G, a, recombine_base(plate, B, G, a)


def extract_particles(plate: np.ndarray, subject_alpha: np.ndarray, text_mask: np.ndarray, cfg,
                      models=None):
    c = cfg.particles
    luma = (plate @ np.array([0.299, 0.587, 0.114], np.float32)).astype(np.float32)
    k = matting.disk(int(c.tophat_px))
    opened = cv2.morphologyEx(plate, cv2.MORPH_OPEN, k)  # local background without small bright stuff
    opened = cv2.GaussianBlur(opened, (0, 0), 1.0)
    luma_bg = (opened @ np.array([0.299, 0.587, 0.114], np.float32)).astype(np.float32)
    tophat = luma - luma_bg
    chroma = plate.max(-1) - plate.min(-1)

    cand = (tophat > c.min_contrast) & (chroma < c.max_chroma) & (luma > c.min_luma)
    cand &= ~matting.dilate(subject_alpha > 0.02, int(c.subject_dilate_px))
    cand &= ~text_mask
    cand_all = cand.copy()  # before size filtering: dense clouds merge into big blobs
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    area = stats[:, cv2.CC_STAT_AREA]
    long_side = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    # thin long streaks are edge highlights of equipment / frames, not dust
    streak = (long_side >= c.streak_min_len) & (area / np.maximum(long_side, 1) < c.streak_max_width)
    keep[1:] = (area[1:] <= c.max_blob_area) & ~streak[1:]
    cand = keep[lab]
    if cand.sum() < c.min_pixels:
        log.info("  particles: tidak cukup partikel (%d px) -> skip", int(cand.sum()))
        return None, None, plate, 0

    # local background = plate with the blobs inpainted away (keeps surrounding texture,
    # unlike a morphological opening which leaves dark holes)
    support = matting.dilate(cand, 1)
    B = cv2.inpaint(to_u8(plate), matting.dilate(support, 1).astype(np.uint8), 3,
                    cv2.INPAINT_TELEA).astype(np.float32) / 255.0
    a, G = color_to_alpha(plate, B, brighten_only=True)
    if c.color is not None:  # fixed particle colour (easier to recolour); alpha from luminance
        P = np.array(c.color, np.float32)
        lb = B @ LUMA
        a = np.clip(((plate @ LUMA) - lb) / np.maximum(float(P @ LUMA) - lb, 1e-3), 0, 1)
        G = np.broadcast_to(P, plate.shape).astype(np.float32)
    w = matting.feather(support.astype(np.float32), 0.5)
    a = np.clip(a * w, 0, c.max_alpha).astype(np.float32)
    a[a < 1.0 / 255] = 0
    base = recombine_base(plate, B, G, a)
    n_blobs = int(keep.sum())
    log.info("  particles: %d blob, %d px", n_blobs, int(cand.sum()))
    G = np.ascontiguousarray(G)

    if c.cloud.enabled and models is not None:
        excl = matting.dilate(subject_alpha > 0.02, int(c.subject_dilate_px)) | text_mask
        cg, ca, base = _cloud(base, cand_all, excl, models, cfg)
        if ca is not None:  # merge: specks OVER cloud, as one pre-baked layer
            a_out = a + ca * (1 - a)
            G = (G * a[..., None] + cg * (ca * (1 - a))[..., None]) / np.maximum(a_out, 1e-6)[..., None]
            a = a_out.astype(np.float32)
    return G.astype(np.float32), a, base, n_blobs

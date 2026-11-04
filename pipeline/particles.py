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


def cloud_region(orig: np.ndarray, models, cfg):
    """Soft weight (0..1) of large dust / chalk / smoke clouds, or None.

    CLIPSeg (text prompts) says WHERE a cloud is; the blurred, dilated seed is a soft weight,
    so there is never a hard region border. Computed before inpainting so the cloud area is
    cleaned in the same LaMa pass as the subject (one pass = no smudgy double-inpaint)."""
    c = cfg.particles.cloud
    if not (cfg.particles.enabled and c.enabled):
        return None
    H, W = orig.shape[:2]
    p = models.text_seg(to_u8(orig), c.prompts)
    pmax = float(p.max())
    if pmax < c.min_prob:
        log.info("  cloud: tidak ada awan debu/kapur (clipseg max %.2f)", pmax)
        return None
    seed = p >= c.rel_threshold * pmax
    frac = seed.sum() / (H * W)
    if frac < c.min_area_frac or frac > c.max_area_frac:
        log.info("  cloud: kandidat %.1f%% kanvas di luar batas -> skip", 100 * frac)
        return None
    sig = c.grow_frac * float(np.hypot(H, W))
    soft = cv2.GaussianBlur(matting.dilate(seed, int(sig)).astype(np.float32), (0, 0), sig)
    log.info("  cloud: region %.1f%% kanvas (clipseg max %.2f)", 100 * (soft > 0.05 * soft.max()).mean(), pmax)
    return np.clip(soft / max(soft.max(), 1e-6), 0, 1).astype(np.float32)


def _cloud(orig, plate, soft, excl, cfg):
    """Cloud = brighten-only colour-to-alpha of the ORIGINAL against the inpainted plate,
    limited to low-saturation pixels brighter than their surroundings. Returns the new base
    for the cloud area (exact: original where there is no cloud)."""
    c = cfg.particles.cloud
    a, G = color_to_alpha(orig, plate, brighten_only=True)
    L = orig @ LUMA
    floor = cv2.GaussianBlur(cv2.erode(L, matting.disk(15)), (0, 0), 15)
    haze = np.clip(((L - floor) - c.min_lift) / max(c.lift_soft, 1e-3), 0, 1)
    chroma = G.max(-1) - G.min(-1)
    lowsat = np.clip(1 - (chroma - c.max_chroma) / 0.1, 0, 1)
    a_full = np.clip(a * soft * haze * lowsat, 0, cfg.particles.max_alpha).astype(np.float32)
    a_full[a_full < 1.0 / 255] = 0
    # the background keeps the clean LaMa plate over the whole cloud area: mixing "original
    # minus cloud" with LaMa leaves visible seams (e.g. along the subject silhouette)
    base = plate
    # the overlay sits ABOVE the subject -> subject-shaped hole
    hole = cv2.GaussianBlur(matting.dilate(excl, 2).astype(np.float32), (0, 0), 1.5)
    a_out = (a_full * (1 - hole)).astype(np.float32)
    log.info("  particles: awan debu/kapur %d px", int((a_out > 0.05).sum()))
    return G, a_out, base.astype(np.float32)


def extract_particles(plate: np.ndarray, subject_alpha: np.ndarray, text_mask: np.ndarray, cfg,
                      orig=None, cloud_soft=None):
    c = cfg.particles
    cg = ca = None
    if cloud_soft is not None and orig is not None:
        excl = matting.dilate(subject_alpha > 0.02, int(c.subject_dilate_px)) | text_mask
        cg, ca, plate = _cloud(orig, plate, cloud_soft, excl, cfg)
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
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    area = stats[:, cv2.CC_STAT_AREA]
    long_side = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    # thin long streaks are edge highlights of equipment / frames, not dust
    streak = (long_side >= c.streak_min_len) & (area / np.maximum(long_side, 1) < c.streak_max_width)
    keep[1:] = (area[1:] <= c.max_blob_area) & ~streak[1:]
    cand = keep[lab]
    if cand.sum() < c.min_pixels:
        log.info("  particles: tidak cukup bintik partikel (%d px)", int(cand.sum()))
        if ca is not None:
            return cg, ca, plate, 0
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

    if ca is not None:  # merge: specks OVER cloud, as one pre-baked layer
        a_out = a + ca * (1 - a)
        G = (G * a[..., None] + cg * (ca * (1 - a))[..., None]) / np.maximum(a_out, 1e-6)[..., None]
        a = a_out.astype(np.float32)
    return G.astype(np.float32), a, base, n_blobs

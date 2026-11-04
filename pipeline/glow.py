"""Step: accent-colour glow/light as a pre-baked transparent overlay.

Every pixel C in the glow area is decomposed into a neutral base B and a coloured light G
with alpha a, such that  C = (1 - a) * B + a * G  (normal "over" blending, which is all
Canva supports). The glow layer gets (G, a); the background plate gets B. Stacking them
back reproduces the original exactly (except where a is clipped at max_alpha).
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import matting

log = logging.getLogger("split")


def _hsv(img):
    hsv = cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2HSV)  # H 0..360, S,V 0..1
    return hsv[..., 0], hsv[..., 1], hsv[..., 2]


def _hue_dist(h, h0):
    d = np.abs(h - h0) % 360.0
    return np.minimum(d, 360.0 - d)


def detect_accent(img: np.ndarray, exclude: np.ndarray, cfg):
    """Dominant saturated hue outside the subject. Returns (hue_deg, rgb) or None."""
    c = cfg.glow
    h, s, v = _hsv(img)
    m = (s > c.min_saturation) & (v > c.min_value) & ~exclude
    if m.sum() < c.min_pixels_frac * m.size:
        return None
    wts = (s * v)[m]
    hist, edges = np.histogram(h[m], bins=72, range=(0, 360), weights=wts)
    hist = np.convolve(np.r_[hist[-2:], hist, hist[:2]], np.ones(5) / 5, "valid")  # circular
    peak = (edges[hist.argmax()] + 2.5)
    near = _hue_dist(h[m], peak) < 15
    ang = np.radians(h[m][near])
    hue = float(np.degrees(np.arctan2((np.sin(ang) * wts[near]).sum(),
                                      (np.cos(ang) * wts[near]).sum())) % 360)
    # representative accent colour: strongest pixels of that hue
    pix = img[m][near]
    sv = (s[m] * v[m])[near]
    rgb = np.median(pix[sv >= np.percentile(sv, 75)], axis=0)
    return hue, rgb


def color_to_alpha(C: np.ndarray, B: np.ndarray, brighten_only: bool = False):
    """GIMP-style colour-to-alpha against a per-pixel base B.

    Finds the minimal alpha a and in-gamut colour G with C = (1 - a) * B + a * G.
    """
    eps = 1e-4
    up = np.where(C > B, (C - B) / np.maximum(1 - B, eps), 0)
    dn = np.where(C < B, (B - C) / np.maximum(B, eps), 0) if not brighten_only else 0 * C
    a = np.clip(np.maximum(up, dn).max(-1), 0, 1)
    G = B + (C - B) / np.maximum(a, eps)[..., None]
    return a.astype(np.float32), np.clip(G, 0, 1).astype(np.float32)


def recombine_base(C, B, G, a):
    """Base under an overlay (G, a) such that over(base, G, a) == C (convex blend of C and B)."""
    a3 = a[..., None]
    base = (C - a3 * G) / np.maximum(1 - a3, 1e-4)
    base = np.where(a3 > 0.999, B, base)
    return np.clip(base, 0, 1).astype(np.float32)


def smooth_base(img: np.ndarray, weight: np.ndarray, sigma: float) -> np.ndarray:
    """Normalized convolution: blur of img using only pixels with low weight (non-glow)."""
    wb = np.clip(1 - weight * 2, 0, 1).astype(np.float32)
    num = cv2.GaussianBlur(img * wb[..., None], (0, 0), sigma)
    den = cv2.GaussianBlur(wb, (0, 0), sigma)[..., None]
    fallback = np.median(img[wb > 0.5], axis=0) if (wb > 0.5).any() else img.reshape(-1, 3).min(0)
    t = np.clip(den / 0.05, 0, 1)
    return (np.where(den > 1e-4, num / np.maximum(den, 1e-4), fallback) * t
            + fallback * (1 - t)).astype(np.float32)


def lama_base(plate: np.ndarray, weight: np.ndarray, models, cfg) -> np.ndarray:
    """Inpaint the strongly coloured areas so the base under the glow keeps scene texture."""
    from .background import clean_plate

    m = matting.dilate(weight > 0.25, 3)
    return clean_plate(plate, m, models, cfg)


def extract_glow(orig: np.ndarray, plate: np.ndarray, subject_alpha: np.ndarray, cfg, models=None):
    """Returns (glow_rgb, glow_alpha, new_plate, info) or (None, None, plate, info)."""
    c = cfg.glow
    excl = matting.dilate(subject_alpha > 0.02, int(c.subject_dilate_px))
    acc = detect_accent(orig, excl, cfg)
    if acc is None:
        log.info("  glow: tidak ada warna aksen dominan -> skip")
        return None, None, plate, {"accent_hue": None}
    hue, acc_rgb = acc
    log.info("  glow: accent hue %.0f deg, rgb %s", hue, np.round(acc_rgb * 255).astype(int).tolist())

    h, _, _ = _hsv(plate)
    chroma = plate.max(-1) - plate.min(-1)
    w_hue = np.clip(1 - (_hue_dist(h, hue) - c.hue_tol_deg) / max(c.hue_soft_deg, 1e-3), 0, 1)
    w_chr = np.clip((chroma - c.min_chroma) / max(c.chroma_soft, 1e-3), 0, 1)
    weight = (w_hue * w_chr).astype(np.float32)
    weight = cv2.GaussianBlur(weight, (0, 0), 0.7)

    # what the scene would look like without the coloured light
    if c.base_mode == "lama" and models is not None:
        B = lama_base(plate, weight, models, cfg)
    else:
        B = smooth_base(plate, weight, c.base_blur_px)
    if c.color_mode == "accent":
        G0 = (acc_rgb / max(acc_rgb.max(), 1e-6)).astype(np.float32)
        G = np.broadcast_to(G0, plate.shape).astype(np.float32)
        d = G - B
        a = ((plate - B) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-4)
        a = np.clip(a, 0, 1)
    else:
        a, G = color_to_alpha(plate, B)
    a = np.minimum(a * weight, c.max_alpha).astype(np.float32)
    a[a < 1.0 / 255] = 0
    if (a > 0.05).sum() < c.min_pixels_frac * a.size * 0.25:
        log.info("  glow: area terlalu kecil -> skip")
        return None, None, plate, {"accent_hue": hue}
    base = recombine_base(plate, B, G, a)
    info = {"accent_hue": round(hue, 1),
            "accent_hex": "#%02X%02X%02X" % tuple(int(round(x * 255)) for x in acc_rgb)}
    return G, a, base, info

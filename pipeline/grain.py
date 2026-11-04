"""Step: estimate the original's noise level and bake a grain + vignette overlay.

Canva has no blend modes, so grain is encoded as white (brighten) / black (darken) pixels
with per-pixel alpha calibrated against the local luminance of the design.
"""
from __future__ import annotations

import cv2
import numpy as np

LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def estimate_noise(img: np.ndarray, exclude: np.ndarray | None = None) -> float:
    """Robust grain sigma (0..1 scale) from high-pass residual in flat regions."""
    g = (img @ LUMA).astype(np.float32)
    hp = g - cv2.GaussianBlur(g, (0, 0), 1.5)
    gx = cv2.Sobel(cv2.GaussianBlur(g, (0, 0), 2.0), cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(cv2.GaussianBlur(g, (0, 0), 2.0), cv2.CV_32F, 0, 1)
    grad = np.hypot(gx, gy)
    flat = grad < np.percentile(grad, 40)
    if exclude is not None:
        flat &= ~exclude
    vals = hp[flat] if flat.sum() > 1000 else hp.ravel()
    return float(1.4826 * np.median(np.abs(vals - np.median(vals))))


def make_noise(shape, sigma: float, size_px: float, mono: bool, rng) -> np.ndarray:
    h, w = shape
    ch = 1 if mono else 3
    n = rng.standard_normal((h, w, ch)).astype(np.float32)
    if size_px > 0:
        n = cv2.GaussianBlur(n, (0, 0), size_px)
        if n.ndim == 2:
            n = n[..., None]
        n /= max(n.std(), 1e-6)
    return n * sigma


def regrain(plate: np.ndarray, region: np.ndarray, sigma: float, cfg) -> np.ndarray:
    """Add matching synthetic grain inside the (smooth) inpainted region of the plate."""
    rng = np.random.default_rng(cfg.grain.seed + 7)
    n = make_noise(region.shape, sigma, cfg.grain.size_px, cfg.grain.monochrome, rng)
    w = cv2.GaussianBlur(region.astype(np.float32), (0, 0), 2.0)[..., None]
    return np.clip(plate + n * w, 0, 1).astype(np.float32)


def grain_overlay(base_rgb: np.ndarray, sigma: float, cfg):
    """Return (rgb, alpha) for the grain+vignette overlay."""
    c = cfg.grain
    h, w = base_rgb.shape[:2]
    rng = np.random.default_rng(c.seed)
    n = make_noise((h, w), sigma * c.strength, c.size_px, True, rng)[..., 0]
    B = cv2.GaussianBlur((base_rgb @ LUMA).astype(np.float32), (0, 0), 3.0)

    # grain: white with alpha a raises by a*(1-B); black lowers by a*B
    pos = n > 0
    ga = np.where(pos, n / np.maximum(1 - B, 0.05), -n / np.maximum(B, 0.05))
    ga = np.clip(ga, 0, 0.5).astype(np.float32)
    gc = np.where(pos[..., None], 1.0, 0.0).astype(np.float32) * np.ones(3, np.float32)

    # vignette: black with radial alpha
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / np.sqrt(2)
    t = np.clip((r - c.vignette_radius) / max(1 - c.vignette_radius, 1e-3), 0, 1)
    va = (c.vignette_strength * t * t * (3 - 2 * t)).astype(np.float32)

    # merge grain OVER vignette into one RGBA (Porter-Duff over)
    a = ga + va * (1 - ga)
    rgb = (gc * ga[..., None] + 0.0 * va[..., None] * (1 - ga[..., None])) / np.maximum(a, 1e-6)[..., None]
    return rgb.astype(np.float32), a.astype(np.float32)

"""Mask/alpha refinement: guided filter, levels, feather, island removal, color decontamination."""
from __future__ import annotations

import cv2
import numpy as np


def _box(x: np.ndarray, r: int) -> np.ndarray:
    return cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1), normalize=True,
                         borderType=cv2.BORDER_REFLECT)


def guided_filter(guide: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    """Color guided filter (He et al. 2010). guide HxWx3 float, p HxW float."""
    I = guide.astype(np.float32)
    p = p.astype(np.float32)
    mean_I = _box(I, r)
    mean_p = _box(p, r)
    mean_Ip = _box(I * p[..., None], r)
    cov_Ip = mean_Ip - mean_I * mean_p[..., None]

    # covariance of I (3x3 per pixel)
    var = np.empty(I.shape[:2] + (3, 3), np.float32)
    for i in range(3):
        for j in range(i, 3):
            v = _box(I[..., i] * I[..., j], r) - mean_I[..., i] * mean_I[..., j]
            var[..., i, j] = v
            var[..., j, i] = v
    var += eps * np.eye(3, dtype=np.float32)
    a = np.linalg.solve(var, cov_Ip[..., None])[..., 0]  # HxWx3
    b = mean_p - (a * mean_I).sum(-1)
    return (_box(a, r) * I).sum(-1) + _box(b, r)


def levels(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)


def feather(a: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return a
    return cv2.GaussianBlur(a, (0, 0), sigma)


def remove_islands(a: np.ndarray, min_area: int, thr: float = 0.05) -> np.ndarray:
    m = (a > thr).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_area
    return a * keep[lab]


def fill_holes(a: np.ndarray, max_hole: int, thr: float = 0.5) -> np.ndarray:
    """Fill small fully-enclosed holes in the hard mask."""
    inv = (a < thr).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    small = np.zeros(n, bool)
    small[1:] = stats[1:, cv2.CC_STAT_AREA] < max_hole
    out = a.copy()
    out[small[lab]] = 1.0
    return out


def refine_alpha(img: np.ndarray, alpha: np.ndarray, radius: int, eps: float,
                 lo: float, hi: float, feather_px: float, min_island: int) -> np.ndarray:
    a = guided_filter(img, alpha, radius, eps)
    a = levels(a, lo, hi)
    a = remove_islands(a, min_island)
    a = feather(a, feather_px)
    return np.clip(a, 0, 1).astype(np.float32)


def disk(r: int) -> np.ndarray:
    r = max(int(round(r)), 0)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def dilate(m: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return m
    return cv2.dilate(m.astype(np.uint8), disk(r)).astype(bool) if m.dtype == bool \
        else cv2.dilate(m, disk(r))


def erode(m: np.ndarray, r: int) -> np.ndarray:
    if r <= 0:
        return m
    return cv2.erode(m.astype(np.uint8), disk(r)).astype(bool) if m.dtype == bool \
        else cv2.erode(m, disk(r))


def decontaminate(img: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Estimate pure foreground colors at semi-transparent edges (removes bg color halo)."""
    from pymatting import estimate_foreground_ml

    F = estimate_foreground_ml(img.astype(np.float64), alpha.astype(np.float64))
    F = np.clip(F, 0, 1).astype(np.float32)
    # opaque pixels keep original color exactly
    solid = alpha >= 0.999
    F[solid] = img[solid]
    return F

"""Step: restack all layers, diff image and SSIM vs original."""
from __future__ import annotations

import cv2
import numpy as np
from skimage.metrics import structural_similarity


def over(dst: np.ndarray, rgb: np.ndarray, alpha: np.ndarray, opacity: float = 1.0) -> np.ndarray:
    a = (alpha * opacity)[..., None]
    return dst * (1 - a) + rgb * a


def recomposite(layers) -> np.ndarray:
    """layers: list of dicts with rgb, alpha (None for opaque), z_order, suggested_opacity."""
    out = None
    for L in sorted(layers, key=lambda d: d["z_order"]):
        if L.get("rgb") is None:
            continue
        if out is None:
            out = L["rgb"].copy()
            continue
        out = over(out, L["rgb"], L["alpha"], L.get("suggested_opacity", 1.0))
    return np.clip(out, 0, 1)


def ssim_scores(orig: np.ndarray, comp: np.ndarray, exclude: np.ndarray | None = None):
    s, smap = structural_similarity(orig, comp, channel_axis=2, data_range=1.0, full=True)
    smap = smap.mean(-1)
    s_ex = float(smap[~exclude].mean()) if exclude is not None and exclude.any() else float(s)
    return float(s), s_ex


def diff_image(orig: np.ndarray, comp: np.ndarray, gain: float) -> np.ndarray:
    d = np.abs(orig - comp).max(-1)
    d = np.clip(d * gain, 0, 1)
    heat = cv2.applyColorMap((d * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
    return cv2.cvtColor(heat, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

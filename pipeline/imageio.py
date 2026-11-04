"""Image load/save helpers. Internal format: float32 RGB 0..1, alpha float32 0..1."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def load_rgb(path: Path) -> np.ndarray:
    im = Image.open(path)
    im.load()
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        a = np.asarray(im, dtype=np.float32) / 255.0
        rgb = a[..., :3] * a[..., 3:4]  # flatten transparent pixels over black
        return rgb.astype(np.float32)
    return np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0


def to_u8(x: np.ndarray) -> np.ndarray:
    return (np.clip(x, 0, 1) * 255.0 + 0.5).astype(np.uint8)


def save_rgb(path: Path, rgb: np.ndarray) -> None:
    Image.fromarray(to_u8(rgb), "RGB").save(path, optimize=False, compress_level=6)


def save_rgba(path: Path, rgb: np.ndarray, alpha: np.ndarray) -> None:
    rgba = np.dstack([to_u8(rgb), to_u8(alpha)])
    rgba[rgba[..., 3] == 0, :3] = 0  # keep fully transparent pixels clean
    Image.fromarray(rgba, "RGBA").save(path, optimize=False, compress_level=6)


def save_gray(path: Path, g: np.ndarray) -> None:
    Image.fromarray(to_u8(g), "L").save(path)


def bbox(alpha: np.ndarray, thr: float):
    ys, xs = np.where(alpha > thr)
    if len(xs) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)

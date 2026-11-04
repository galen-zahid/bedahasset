"""Step: clean background plate - remove subject, fg objects and text, inpaint with LaMa."""
from __future__ import annotations

import cv2
import numpy as np

from . import matting
from .imageio import to_u8


def inpaint_mask(sal: np.ndarray, raw: np.ndarray, text_mask: np.ndarray, fg_union, cfg,
                 exclude: np.ndarray | None = None) -> np.ndarray:
    c = cfg.background
    m = (sal > 0.02) | (raw > c.raw_threshold)  # include faint hair strands -> no leftovers
    if exclude is not None:
        m &= ~exclude
    if fg_union is not None:
        m |= fg_union > 0.02
    m = matting.dilate(m, int(c.dilate_px))
    m |= matting.dilate(text_mask, int(c.text_extra_dilate_px))
    return m


def restore_original(plate: np.ndarray, img: np.ndarray, inp_mask: np.ndarray, sal, raw,
                     fg_union, keep_mask: np.ndarray, cfg) -> np.ndarray:
    """The big inpaint mask is only needed so LaMa has no subject/hair to extend. Pixels that
    are clearly background (far enough from the subject, not text) get their original value
    back, e.g. the gaps between arms and legs."""
    r = int(cfg.background.restore_beyond_px)
    if r <= 0:
        return plate, np.zeros(inp_mask.shape, bool)
    core = (sal > 0.02) | (raw > cfg.background.raw_threshold)
    if fg_union is not None:
        core |= fg_union > 0.02
    near = matting.dilate(core, int(cfg.background.restore_strict_px))
    core = matting.dilate(core, r)
    restore = inp_mask & ~core & ~keep_mask
    # close to the subject only restore pixels that look like what LaMa put there: fine hair
    # wisps / edge spill that BiRefNet missed differ strongly and stay inpainted
    diff = np.abs(img - plate).max(-1)
    restore &= ~near | (diff < cfg.background.restore_max_diff)
    restore = cv2.morphologyEx(restore.astype(np.uint8), cv2.MORPH_OPEN, matting.disk(2)).astype(bool)
    w = matting.feather(restore.astype(np.float32), 2.0) * (~core & ~keep_mask)
    out = plate * (1 - w[..., None]) + img * w[..., None]
    return out.astype(np.float32), w > 0.5


def clean_plate(img: np.ndarray, mask: np.ndarray, models, cfg) -> np.ndarray:
    c = cfg.background
    if not mask.any():
        return img.copy()
    H, W = mask.shape
    src, m = img, mask
    scale = 1.0
    if c.lama_max_side and max(H, W) > c.lama_max_side:
        scale = c.lama_max_side / max(H, W)
        src = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        m = cv2.resize(mask.astype(np.uint8), (src.shape[1], src.shape[0]),
                       interpolation=cv2.INTER_NEAREST).astype(bool)
    out = models.inpaint(to_u8(src), (m * 255).astype(np.uint8)).astype(np.float32) / 255.0
    if scale != 1.0:
        out = cv2.resize(out, (W, H), interpolation=cv2.INTER_CUBIC)
    # paste only inside the mask, feathered, so untouched pixels stay bit-exact
    w = matting.feather(mask.astype(np.float32), c.paste_feather_px)
    w = np.maximum(w, mask.astype(np.float32))[..., None]
    return (img * (1 - w) + out * w).astype(np.float32)

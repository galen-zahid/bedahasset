"""Step: main subject matte (rembg / BiRefNet) + edge refinement."""
from __future__ import annotations

import numpy as np

from . import matting
from .imageio import to_u8


def salient_alpha(img: np.ndarray, models, cfg):
    """Refined soft matte of everything salient (subject + objects held/near it), plus the
    raw model output (used for a generous inpaint mask that also catches faint hair)."""
    c = cfg.subject
    raw = models.salient_mask(to_u8(img))
    h, w = raw.shape
    a = matting.refine_alpha(img, raw, c.guided_radius, c.guided_eps, c.alpha_lo, c.alpha_hi,
                             c.feather_px, int(c.min_island_frac * h * w))
    return a, raw


def plate_matting(C: np.ndarray, B: np.ndarray, a: np.ndarray, F: np.ndarray,
                  min_contrast: float, max_grow: float, ambiguous_choke: float = 0.0) -> np.ndarray:
    """Known-background matting on the soft edge band.

    With the clean plate B and an estimate of the foreground colour F, the true alpha of
    an edge pixel is the projection of (C - B) onto (F - B). Pixels that actually look like
    the background get low alpha -> no dark/light fringe when placed on a new background.
    """
    band = (a > 0) & (a < 0.999)
    d = F - B
    den = (d * d).sum(-1)
    proj = ((C - B) * d).sum(-1) / np.maximum(den, 1e-6)
    valid = band & (den > min_contrast ** 2)
    out = a.copy()
    out[valid] = np.clip(np.minimum(proj[valid], a[valid] + max_grow), 0, 1)
    # where subject and background look alike (dark hair on dark bg) alpha is undecidable:
    # choke it a bit so it does not turn into a smoky fringe on a light background
    amb = band & ~valid
    if ambiguous_choke > 0:
        out[amb] = np.clip((a[amb] - ambiguous_choke) / (1 - ambiguous_choke), 0, 1)
    return out


def subject_layer(img: np.ndarray, sal: np.ndarray, fg_union, plate, cfg):
    """Subject alpha = salient minus (slightly eroded) foreground objects, edges re-matted
    against the clean plate, colours decontaminated."""
    c = cfg.subject
    a = sal.copy()
    if fg_union is not None and fg_union.max() > 0:
        core = matting.erode((fg_union > 0.5).astype(np.uint8),
                             int(cfg.foreground.edge_erode_px)).astype(np.float32)
        core = matting.feather(core, 1.0)
        a = a * (1.0 - core)
    h, w = a.shape
    if not c.decontaminate:
        return img, a.astype(np.float32)
    F = matting.decontaminate(img, a)
    if c.plate_matting and plate is not None:
        a = plate_matting(img, plate, a, F, c.plate_min_contrast, c.plate_max_grow,
                          c.ambiguous_choke)
        a = matting.remove_islands(a, int(c.min_island_frac * h * w))
        F = matting.decontaminate(img, a)
    return F, a.astype(np.float32)


def edge_refine_object(img, alpha, plate, cfg):
    """Same edge treatment for foreground objects."""
    c = cfg.subject
    if not c.decontaminate:
        return img, alpha
    F = matting.decontaminate(img, alpha)
    if c.plate_matting and plate is not None:
        alpha = plate_matting(img, plate, alpha, F, c.plate_min_contrast, c.plate_max_grow,
                              c.ambiguous_choke)
        F = matting.decontaminate(img, alpha)
    return F, alpha.astype(np.float32)

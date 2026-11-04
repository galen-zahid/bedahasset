"""Step: split the subject matte into separate elements (assets, shapes) instead of one layer.

1. Thin links (connector lines, a barbell bar, arrows) are cut with a morphological opening
   whose radius scales with the canvas; every remaining blob is one element.
2. What the opening removed is either a sizeable piece of its own (a connector line -> its
   own "shape" element) or a small fringe (hair strands, edges) -> returned to the nearest
   element.
3. Soft alpha (anti-aliased edges, hair) is assigned to the nearest element, so the elements
   stacked together give exactly the original subject layer.

Each element is classified:
  asset_large / asset_small    photographic object (person, car, food, product)
  vector_large / vector_icon   illustration (no photo texture)
  shape                        flat, few-colour piece (line, connector, badge, simple icon)
"""
from __future__ import annotations

import logging

import cv2
import numpy as np
from scipy import ndimage

from . import matting

log = logging.getLogger("split")


def _flatness(rgb: np.ndarray, m: np.ndarray) -> float:
    """Fraction of the element covered by its 4 dominant colours (1.0 = perfectly flat)."""
    pix = (rgb[m] * 255).astype(np.uint8)
    if len(pix) < 30:
        return 1.0
    if len(pix) > 20000:
        pix = pix[np.random.default_rng(0).choice(len(pix), 20000, replace=False)]
    q = (pix // 24).astype(np.int32)  # coarse colour buckets
    key = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    _, counts = np.unique(key, return_counts=True)
    return float(np.sort(counts)[::-1][:4].sum() / len(key))


def split_elements(rgb: np.ndarray, alpha: np.ndarray, cfg):
    """Return a list of {alpha, kind, area, bbox} whose alphas sum to `alpha`."""
    c = cfg.elements
    H, W = alpha.shape
    hard = alpha > 0.5
    if not c.enabled or hard.sum() < 50:
        return [{"alpha": alpha, "kind": "asset_large", "area": int(hard.sum())}]
    diag = float(np.hypot(H, W))
    r = max(1, int(round(c.link_cut_frac * diag)))
    opened = cv2.morphologyEx(hard.astype(np.uint8), cv2.MORPH_OPEN, matting.disk(r)).astype(bool)
    n, lab = cv2.connectedComponents(opened.astype(np.uint8), connectivity=8)
    min_area = c.min_area_frac * H * W
    # drop tiny blobs from the seed set (they are fringe, not elements)
    areas = np.bincount(lab.ravel(), minlength=n)
    seeds = np.zeros_like(lab)
    k = 0
    for i in range(1, n):
        if areas[i] >= min_area:
            k += 1
            seeds[lab == i] = k
    # pieces cut away by the opening: big ones become their own (shape) elements
    resid = hard & (seeds == 0)
    nr, rlab = cv2.connectedComponents(resid.astype(np.uint8), connectivity=8)
    rareas = np.bincount(rlab.ravel(), minlength=nr)
    for i in range(1, nr):
        if rareas[i] >= c.min_link_area_frac * H * W:
            k += 1
            seeds[rlab == i] = k
    if k <= 1:
        return [{"alpha": alpha, "kind": _classify(rgb, hard, H, W, c), "area": int(hard.sum())}]
    # every subject pixel (incl. soft edges) goes to the nearest seed
    _, (iy, ix) = ndimage.distance_transform_edt(seeds == 0, return_indices=True)
    owner = seeds[iy, ix]
    owner[alpha <= 0] = 0
    out = []
    for j in range(1, k + 1):
        m = owner == j
        a = np.where(m, alpha, 0).astype(np.float32)
        hm = m & hard
        if hm.sum() == 0:
            continue
        out.append({"alpha": a, "kind": _classify(rgb, hm, H, W, c), "area": int(hm.sum())})
    out.sort(key=lambda e: -e["area"])
    kinds = {}
    for e in out:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    log.info("  elemen: subject dipecah jadi %d (%s)", len(out),
             ", ".join(f"{v} {k}" for k, v in kinds.items()))
    return out


def _texture(rgb, m) -> float:
    """Median fine-detail energy. Photos carry sensor noise / micro texture; vectors do not."""
    m = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    if m.sum() < 30:
        return 0.0
    L = (rgb @ np.array([0.299, 0.587, 0.114], np.float32)).astype(np.float32)
    hp = np.abs(L - cv2.GaussianBlur(L, (0, 0), 1.0))
    return float(np.median(hp[m]))


def _classify(rgb, m, H, W, c) -> str:
    frac = m.sum() / (H * W)
    large = frac >= c.large_frac
    if _texture(rgb, m) >= c.photo_texture:  # photographic
        return "asset_large" if large else "asset_small"
    if not large and _flatness(rgb, m) >= c.flat_shape_threshold:
        return "shape"  # flat, few colours: line, connector, badge, simple icon
    return "vector_large" if large else "vector_icon"

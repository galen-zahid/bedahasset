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


def _grid_points(m: np.ndarray, n: int):
    """Up to n well-spread points inside mask m (farthest-point sampling on the interior)."""
    inner = cv2.erode(m.astype(np.uint8), matting.disk(5)).astype(bool)
    ys, xs = np.nonzero(inner if inner.sum() > 50 else m)
    if len(xs) == 0:
        return []
    pts = np.c_[xs, ys].astype(np.float32)
    if len(pts) > 6000:
        pts = pts[np.random.default_rng(0).choice(len(pts), 6000, replace=False)]
    dt = cv2.distanceTransform((inner if inner.sum() > 50 else m).astype(np.uint8), cv2.DIST_L2, 5)
    first = np.unravel_index(np.argmax(dt), dt.shape)
    chosen = [np.array([first[1], first[0]], np.float32)]
    d = np.linalg.norm(pts - chosen[0], axis=1)
    for _ in range(n - 1):
        k = int(np.argmax(d))
        if d[k] < 8:
            break
        chosen.append(pts[k])
        d = np.minimum(d, np.linalg.norm(pts - pts[k], axis=1))
    return [(float(x), float(y)) for x, y in chosen]


def sam_split(predict, alpha: np.ndarray, elem_mask: np.ndarray, cfg):
    """Split one element into whole objects using SAM point prompts.

    For each prompt the LARGEST of SAM's 3 masks that stays inside the element (does not leak
    into the background) and is confident is taken as "the whole object under this point".
    Masks that are mostly inside a bigger kept mask are parts of it and are dropped.
    Returns a list of masks (>= 2) or None when the element is one object."""
    c = cfg.elements
    area = elem_mask.sum()
    pts = _grid_points(elem_mask, int(c.sam_points))
    if len(pts) < 2:
        return None
    masks, scores = predict(pts)
    cands = []
    for p in range(masks.shape[0]):
        best = None
        for k in range(masks.shape[1]):
            mk = masks[p, k]
            ma = mk.sum()
            if ma == 0 or scores[p, k] < c.sam_min_score:
                continue
            inside = (mk & elem_mask).sum() / ma
            if inside < c.sam_min_inside or ma < c.sam_min_part * area:
                continue
            if best is None or ma > best.sum():
                best = mk & elem_mask
        if best is not None:
            cands.append(best)
    if len(cands) < 2:
        return None
    cands.sort(key=lambda m: -m.sum())
    objs = []
    for m in cands:
        if any((m & o).sum() / m.sum() > c.sam_part_overlap for o in objs):
            continue  # a part of (or the same as) an object we already have
        objs.append(m)
    if len(objs) < 2:
        return None
    covered = np.any(objs, axis=0).sum() / area
    if covered < c.sam_min_cover:
        return None
    return objs


def split_elements(rgb: np.ndarray, alpha: np.ndarray, cfg, predict=None):
    """Return a list of {alpha, kind, area} whose alphas sum to `alpha`."""
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
    # SAM: split elements whose objects touch / overlap (person + barbell, two people)
    if predict is not None and c.sam:
        k2 = k
        for j in range(1, k + 1):
            em = (seeds == j)
            if em.sum() < c.sam_min_elem_frac * H * W:
                continue
            objs = sam_split(predict, alpha, em | (hard & matting.dilate(em, r + 1)), cfg)
            if not objs:
                continue
            seeds[em] = 0
            for o in objs:
                k2 += 1
                seeds[o & em & (seeds == 0)] = k2
            log.info("  elemen: SAM memisahkan 1 elemen jadi %d objek", len(objs))
        if k2 != k:  # relabel compactly
            ids = [i for i in np.unique(seeds) if i > 0]
            remap = np.zeros(seeds.max() + 1, seeds.dtype)
            for new_i, old_i in enumerate(ids, 1):
                remap[old_i] = new_i
            seeds = remap[seeds]
            k = len(ids)
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

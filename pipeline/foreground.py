"""Step: objects in FRONT of the subject, via Depth Anything V2 + connected components.

Only salient pixels (from the subject matte) are considered, so the floor plane - which is
also "near" in depth - is never picked up as a foreground object.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import matting

log = logging.getLogger("split")


def find_foreground(img: np.ndarray, sal: np.ndarray, depth: np.ndarray | None, cfg):
    """Return list of dicts {alpha, depth_mean} sorted far->near, plus union alpha."""
    c = cfg.foreground
    h, w = sal.shape
    if depth is None:
        return [], None
    hard = sal > cfg.subject.hard_threshold
    if hard.sum() < 100:
        return [], None
    ref = float(np.median(depth[hard]))
    cand = hard & (depth > ref + c.depth_margin)
    cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_OPEN, matting.disk(3))
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, matting.disk(5))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    min_area = c.min_area_frac * h * w
    out = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < min_area:
            continue
        if area > c.max_area_frac_of_salient * hard.sum():
            log.info("  fg component %d terlalu besar (%.0f%% salient) -> itu subject, skip",
                     i, 100 * area / hard.sum())
            continue
        bx, by, bw, bh = stats[i, :4]
        touches = bx <= c.edge_px or by <= c.edge_px or bx + bw >= w - c.edge_px or by + bh >= h - c.edge_px
        if c.require_frame_edge and not touches:
            # a real "in front of the subject" object (plate, shoulder, leaf) is cropped by the
            # frame; a near-depth blob in the middle is a depth artefact on a graphic/illustration
            log.info("  fg kandidat di tengah frame (area %d px) -> bukan objek depan, skip", area)
            continue
        comp = (lab == i).astype(np.float32)
        comp = matting.fill_holes(comp, int(0.002 * h * w))
        # inner edge (vs subject) from depth -> snap to image edges; outer edge from salient matte
        soft = matting.guided_filter(img, comp, c.guided_radius, 1e-3)
        soft = matting.levels(soft, 0.4, 0.6)
        a = np.clip(np.minimum(soft, sal), 0, 1)
        a = matting.feather(a, cfg.subject.feather_px)
        dm = float(depth[lab == i].mean())
        out.append({"alpha": a.astype(np.float32), "depth_mean": dm, "area": int(area)})
        log.info("  fg object: area=%d px, depth=%.2f (subject ref %.2f)", area, dm, ref)
    out.sort(key=lambda d: d["depth_mean"])  # far first -> lower z
    union = np.max([o["alpha"] for o in out], axis=0) if out else None
    return out, union


def reassign_slivers(subj_rgb, subj_a, fg_layers, cfg):
    """Thin strips of the subject hugging a foreground object's edge are almost always the
    object's own rim (depth is blurry at boundaries). Move them from the subject to that object
    so the subject layer has no stray outline and the recomposite stays complete."""
    c = cfg.foreground
    if not fg_layers or c.sliver_px <= 0:
        return subj_rgb, subj_a, fg_layers
    hard = (subj_a > 0.1).astype(np.uint8)  # low threshold: also catch faint chalk-dust rims
    opened = cv2.morphologyEx(hard, cv2.MORPH_OPEN, matting.disk(int(c.sliver_px)))
    thin = hard.astype(bool) & ~opened.astype(bool)
    out = []
    moved_total = 0
    for rgb, a in fg_layers:
        near = matting.dilate(a > 0.5, int(c.sliver_px) * 3)
        sl = thin & near
        # keep only thin pieces that actually touch this object
        n, lab, st, _ = cv2.connectedComponentsWithStats(sl.astype(np.uint8), connectivity=8)
        touch = matting.dilate(a > 0.3, 2)
        keep = np.zeros(n, bool)
        for i in range(1, n):
            keep[i] = touch[lab == i].any()
        sl = keep[lab]
        if sl.any():
            w = matting.feather(matting.dilate(sl, 1).astype(np.float32), 0.7) * (subj_a > 0)
            moved = subj_a * w
            new_a = a + moved * (1 - a)
            rgb = (rgb * a[..., None] + subj_rgb * (moved * (1 - a))[..., None]) / \
                np.maximum(new_a, 1e-6)[..., None]
            subj_a = subj_a * (1 - w)
            a = new_a.astype(np.float32)
            moved_total += int(sl.sum())
        out.append((rgb.astype(np.float32), a))
    if moved_total:
        log.info("  %d px sliver tepi foreground dipindah dari subject ke foreground", moved_total)
    return subj_rgb, subj_a.astype(np.float32), out

"""Step: "magic wand" edges and "pen tool" SVG for flat / vector elements.

magic_wand_alpha  vector art has crisp, flat-colour edges. Near the element outline the alpha is
                  rebuilt from how different each pixel is from the clean background (like a
                  magic-wand selection of the background, with anti-aliasing), instead of the
                  soft photo-style matte.
trace_svg         every flat element is traced into an SVG: its colours are quantized and each
                  colour region becomes a filled path (outer contours + holes, even-odd fill).
                  Canva accepts SVG uploads and lets you change each colour of the SVG. The SVG
                  uses the full canvas as viewBox, so it aligns 1:1 when placed at x=0, y=0.
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from . import matting

log = logging.getLogger("split")


def magic_wand_alpha(img: np.ndarray, plate: np.ndarray, alpha: np.ndarray, cfg) -> np.ndarray:
    """Crisp alpha for vector art: inside a band around the outline, a pixel belongs to the
    element when its colour differs from the clean background (tolerance like a magic wand)."""
    c = cfg.vectorize
    hard = alpha > 0.5
    if hard.sum() == 0:
        return alpha
    band = matting.dilate(hard, int(c.wand_band_px)) & ~matting.erode(hard, int(c.wand_band_px))
    diff = np.abs(img - plate).max(-1)
    wand = np.clip((diff - c.wand_tol_lo) / max(c.wand_tol_hi - c.wand_tol_lo, 1e-3), 0, 1)
    out = alpha.copy()
    out[band] = wand[band]
    # never open holes deep inside the element (an outline colour equal to the background)
    out[matting.erode(hard, int(c.wand_band_px))] = np.maximum(
        out[matting.erode(hard, int(c.wand_band_px))], alpha[matting.erode(hard, int(c.wand_band_px))])
    return out.astype(np.float32)


def complete_with_sam(predict, img, rgb, alpha, others, cfg):
    """Vector icons: let SAM outline the whole object (it sees an icon as one thing, including
    dark details in the background colour), then take that outline as the element's shape."""
    from .elements import _grid_points

    c = cfg.vectorize
    hard = alpha > 0.5
    if predict is None or hard.sum() < 200:
        return rgb, alpha
    pts = _grid_points(hard, int(c.sam_points))
    if not pts:
        return rgb, alpha
    masks, scores = predict(pts)
    zone = matting.dilate(hard, int(c.sam_grow_px))
    best = None
    for p in range(masks.shape[0]):
        for k in range(masks.shape[1]):
            mk = masks[p, k]
            if scores[p, k] < c.sam_min_score or mk.sum() == 0:
                continue
            if (mk & zone).sum() / mk.sum() < 0.97:  # leaks outside the element -> background
                continue
            if (mk & hard).sum() / max(mk.sum(), 1) < 0.5:
                continue
            best = mk if best is None else (best | mk)
    if best is None:
        return rgb, alpha
    add = best & ~hard & ~others
    if not add.any():
        return rgb, alpha
    a = alpha.copy()
    a[add] = 1.0
    out = rgb.copy()
    out[add] = img[add]
    return out, a.astype(np.float32)


def fill_enclosed_holes(img: np.ndarray, rgb: np.ndarray, alpha: np.ndarray, cfg):
    """Vector art often has dark details (text lines, chart bars) in the same colour as the
    background; the matte then punches them out. Fully enclosed holes that are small relative
    to the element are filled back with the original pixels (Photoshop-like "fill holes")."""
    c = cfg.vectorize
    hard = alpha > 0.5
    if hard.sum() < 50:
        return rgb, alpha
    inv = (~hard).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
    H, W = hard.shape
    border = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    limit = c.max_hole_frac * hard.sum()
    fill = np.zeros_like(hard)
    for i in range(1, n):
        if i in border or st[i, 4] > limit:
            continue
        fill |= lab == i
    # vector art has no background colour mixed in: the whole interior (filled silhouette minus
    # a 1px rim) is opaque and keeps the ORIGINAL colours; only the rim stays anti-aliased
    solid = matting.erode(hard | fill, 1)
    a = alpha.copy()
    a[solid] = 1.0
    out = rgb.copy()
    out[solid] = img[solid]
    return out, a.astype(np.float32)


def _hex(c) -> str:
    r, g, b = (int(round(float(v) * 255)) for v in c)
    return f"#{r:02x}{g:02x}{b:02x}"


def _contours_to_path(mask: np.ndarray, eps: float) -> tuple[str, list]:
    cnts, hier = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    parts, polys = [], []
    for cnt in cnts:
        if len(cnt) < 3:
            continue
        ap = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(ap) < 3:
            continue
        polys.append(ap)
        parts.append("M" + " L".join(f"{x} {y}" for x, y in ap) + " Z")
    return " ".join(parts), polys


def _vtracer_svg(rgb, alpha, path, cfg):
    """Bezier tracing (vtracer) of a palette-flattened crop -> full-canvas SVG."""
    import io
    import re

    import vtracer
    from PIL import Image

    c = cfg.vectorize
    H, W = alpha.shape
    m = alpha > 0.5
    ys, xs = np.nonzero(m)
    pad = 2
    x0, y0 = max(xs.min() - pad, 0), max(ys.min() - pad, 0)
    x1, y1 = min(xs.max() + pad + 1, W), min(ys.max() + pad + 1, H)
    crop = (np.clip(rgb[y0:y1, x0:x1], 0, 1) * 255).astype(np.uint8)
    mm = m[y0:y1, x0:x1]
    pix = crop[mm].astype(np.float32)
    k = int(min(c.svg_max_colors, max(2, len(np.unique((pix // 16).astype(np.int32), axis=0)))))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    sample = pix if len(pix) <= 40000 else pix[np.random.default_rng(0).choice(len(pix), 40000, False)]
    _, _, centers = cv2.kmeans(sample, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    lab = np.linalg.norm(crop.reshape(-1, 1, 3).astype(np.float32) - centers[None], axis=-1).argmin(1)
    flat = centers[lab].reshape(crop.shape).astype(np.uint8)
    flat = cv2.medianBlur(flat, 3)
    rgba = np.dstack([flat, (mm * 255).astype(np.uint8)])
    rgba[~mm] = 0
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, "PNG")
    svg = vtracer.convert_raw_image_to_svg(
        buf.getvalue(), img_format="png", colormode="color", hierarchical="stacked", mode="spline",
        filter_speckle=int(c.vt_filter_speckle), color_precision=6,
        layer_difference=int(c.vt_layer_difference), corner_threshold=60, length_threshold=4.0,
        max_iterations=10, splice_threshold=45, path_precision=2)
    inner = re.sub(r"^.*?<svg[^>]*>", "", svg, flags=re.S).rsplit("</svg>", 1)[0]
    out = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
           f'<g transform="translate({x0},{y0})">{inner}</g>\n</svg>\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out, encoding="utf-8")
    return {"colors": int(len(centers)), "paths": inner.count("<path"), "iou": 1.0, "engine": "vtracer"}


def trace_svg(rgb: np.ndarray, alpha: np.ndarray, path: Path, cfg) -> dict:
    """Trace one element to an SVG. Returns stats {colors, paths, iou}."""
    c = cfg.vectorize
    if (alpha > 0.5).sum() < 20:
        return {}
    if c.engine == "vtracer":
        try:
            return _vtracer_svg(rgb, alpha, path, cfg)
        except ImportError:
            log.warning("  vtracer tidak terpasang, pakai tracing dasar (pip install vtracer)")
    H, W = alpha.shape
    m = alpha > 0.5
    if m.sum() < 20:
        return {}
    pix = rgb[m].astype(np.float32)
    k = int(min(c.svg_max_colors, max(1, len(np.unique((pix * 32).astype(np.int32), axis=0)))))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.2)
    sample = pix if len(pix) <= 40000 else pix[np.random.default_rng(0).choice(len(pix), 40000, False)]
    _, _, centers = cv2.kmeans(sample, k, None, crit, 3, cv2.KMEANS_PP_CENTERS)
    # merge near-duplicate colours
    keep = []
    for cc in centers:
        if all(np.abs(cc - o).max() > c.svg_merge_tol for o in keep):
            keep.append(cc)
    centers = np.array(keep, np.float32)
    lab = np.full((H, W), -1, np.int32)
    d = np.linalg.norm(rgb[m][:, None, :] - centers[None], axis=-1)
    lab[m] = d.argmin(1)
    # clean speckles per colour, then paint big regions first (they sit behind)
    regions = []
    for j in range(len(centers)):
        mj = lab == j
        # drop only isolated specks (thin lines stay: no morphological opening)
        nn, ll, ss, _ = cv2.connectedComponentsWithStats(mj.astype(np.uint8), connectivity=8)
        if nn > 1:
            ok = ss[:, 4] >= c.svg_min_region_px
            ok[0] = False
            mj = ok[ll]
        if not mj.any():
            continue
        regions.append((int(mj.sum()), centers[j], mj))
    regions.sort(key=lambda r: -r[0])
    body = []
    n_paths = 0
    # base: the whole silhouette in the dominant colour, so no gap / hole can ever show inside
    if regions:
        d_attr, polys = _contours_to_path(m, c.svg_epsilon)
        if d_attr:
            body.append(f'<path fill="{_hex(regions[0][1])}" fill-rule="evenodd" d="{d_attr}"/>')
            n_paths += len(polys)
        regions = regions[1:]
    for i, (_, col, mj) in enumerate(regions):
        mg = matting.dilate(mj, 1) & m if c.svg_grow_px else mj  # overlap neighbours by 1px
        d_attr, polys = _contours_to_path(mg, c.svg_epsilon)
        if not d_attr:
            continue
        n_paths += len(polys)
        body.append(f'<path fill="{_hex(col)}" fill-rule="evenodd" d="{d_attr}"/>')
    # verify: rasterize the simplified outline (holes respected) and compare with the element
    cnts, hier = cv2.findContours(m.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    rast = np.zeros((H, W), np.uint8)
    if hier is not None:
        for idx, cnt in enumerate(cnts):
            ap = cv2.approxPolyDP(cnt, c.svg_epsilon, True)
            cv2.fillPoly(rast, [ap], 0 if hier[0][idx][3] >= 0 else 1)
    iou = float((rast.astype(bool) & m).sum() / max((rast.astype(bool) | m).sum(), 1))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">\n' + "\n".join(body) + "\n</svg>\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")
    return {"colors": len(regions) + 1, "paths": n_paths, "iou": round(iou, 4)}


def rect_svg(corners, color, opacity: float, W: int, H: int, path: Path) -> None:
    """A rotated rectangle (stripe base) as a one-path SVG."""
    pts = " L".join(f"{x:.1f} {y:.1f}" for x, y in corners)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">\n'
           f'<path fill="{_hex(color)}" fill-opacity="{opacity:.2f}" d="M{pts} Z"/>\n</svg>\n')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(svg, encoding="utf-8")

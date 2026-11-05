"""Rebuild step 1: cut the (text-free) design into colour regions.

Regions are separated only where the colour changes ABRUPTLY (an edge), so a smooth gradient
stays one region and an anti-aliased edge never becomes its own sliver:

    flat pixels (low colour gradient) -> connected seeds -> watershed fills the edge pixels.

Photo areas (texture everywhere, no flat pixels) are detected first and kept out of the
vector rebuild (they stay photos).
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage as ndi


def remove_text(img_u8: np.ndarray, text_mask: np.ndarray, text_colors=()):
    """Paint every text blob with the colour of the 'paper' it is printed on (median of the
    original pixels that are clearly not ink), so the shapes underneath come out whole.
    Returns (image, own_paper): own_paper = blobs whose paper differs from everything around
    them (text filling a pill/button) -> they may form their own region."""
    out = cv2.inpaint(img_u8, text_mask.astype(np.uint8), 5, cv2.INPAINT_TELEA) if text_mask.any() \
        else img_u8.copy()
    own = np.zeros(text_mask.shape, bool)
    if not text_mask.any():
        return out, own
    n, blobs = cv2.connectedComponents(text_mask.astype(np.uint8), connectivity=8)
    f = img_u8.astype(np.float32)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    for i, sl in enumerate(ndi.find_objects(blobs), 1):
        if sl is None:
            continue
        b = blobs[sl] == i
        cy, cx = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
        ink = None
        for (x, y, w, h), col in text_colors:
            if x - 4 <= cx <= x + w + 4 and y - 4 <= cy <= y + h + 4:
                ink = col
        if ink is None:
            continue
        px = f[sl][b]
        far = np.abs(px - ink).sum(1) > 150
        if far.sum() < 0.15 * b.sum():
            continue
        paper = np.median(px[far], 0)
        ys = slice(max(sl[0].start - 5, 0), sl[0].stop + 5)
        xs = slice(max(sl[1].start - 5, 0), sl[1].stop + 5)
        bb = blobs[ys, xs] == i
        ring = cv2.dilate(bb.astype(np.uint8), k).astype(bool) & ~text_mask[ys, xs]
        rp = f[ys, xs][ring]
        near = (np.abs(rp - paper).sum(1) < 60).mean() if len(rp) else 0
        if near < 0.3:  # the paper is not around the blob: text fills its own box
            sub = out[sl]
            sub[b] = paper.astype(np.uint8)
            own[sl] |= b
    return out, own


def smooth(img_u8: np.ndarray, c) -> np.ndarray:
    """Edge-preserving smoothing: kills grain / JPEG noise, keeps edges sharp."""
    s = img_u8
    for _ in range(int(c.smooth_passes)):
        s = cv2.bilateralFilter(s, int(c.smooth_d), float(c.smooth_sigma_color), float(c.smooth_sigma_space))
    return s


def color_gradient(s_u8: np.ndarray) -> np.ndarray:
    """Per-pixel colour change in Lab units per pixel (max over channels)."""
    lab = cv2.cvtColor(s_u8, cv2.COLOR_RGB2Lab).astype(np.float32)
    lab[..., 0] *= 100.0 / 255.0
    lab[..., 1:] -= 128.0
    g = np.zeros(lab.shape[:2], np.float32)
    for ch in range(3):
        gx = cv2.Scharr(lab[..., ch], cv2.CV_32F, 1, 0) / 16.0
        gy = cv2.Scharr(lab[..., ch], cv2.CV_32F, 0, 1) / 16.0
        g = np.maximum(g, np.sqrt(gx * gx + gy * gy))
    return g


def photo_mask(grad: np.ndarray, text_mask: np.ndarray, c) -> np.ndarray:
    """Photo = no flat pixels in the neighbourhood (texture everywhere). Graphics, even busy
    icons with many lines, are mostly flat between their edges."""
    H, W = grad.shape
    flat = (grad < c.flat_grad).astype(np.float32)
    flat[text_mask] = 1.0  # text is never a photo
    k = int(c.photo_window) | 1
    frac = cv2.blur(flat, (k, k))
    m = frac < c.photo_flat_frac
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k // 2 | 1, k // 2 | 1)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= c.photo_min_frac * H * W
    out = keep[lab]
    return ndi.binary_fill_holes(out) if out.any() else out


def segment(s_u8: np.ndarray, grad: np.ndarray, exclude: np.ndarray, c, no_seed=None, text_colors=()) -> np.ndarray:
    """Label image (0 = excluded/photo, 1..n regions). no_seed: pixels (text) that never start a
    region; they are flooded from the surrounding regions."""
    from skimage.segmentation import watershed

    H, W = grad.shape
    flat = (grad < c.flat_grad) & ~exclude
    if no_seed is not None:
        flat &= ~no_seed
    # thin lines have few flat pixels: also accept "locally flattest" pixels as seeds
    n, seeds = cv2.connectedComponents(flat.astype(np.uint8), connectivity=4)
    sizes = np.bincount(seeds.ravel(), minlength=n)
    small = sizes < c.min_seed_px
    small[0] = False
    seeds[small[seeds]] = 0
    lab = watershed(grad, seeds, mask=~exclude)
    if no_seed is not None and no_seed.any():
        lab = _fill_text(lab, no_seed & ~exclude, s_u8, text_colors)
    lab = merge_small(lab, s_u8, c.min_region_px)
    return relabel(lab)


def _fill_text(lab, text, s_u8, text_colors):
    """Each text blob takes the region it is printed on: of the regions around the blob, the
    one whose colour is most different from the letters (not a thin outline of the same ink),
    among those that surround a fair share of it."""
    n, blobs = cv2.connectedComponents(text.astype(np.uint8), connectivity=8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    img = s_u8.astype(np.float32)
    for i, sl in enumerate(ndi.find_objects(blobs), 1):
        if sl is None:
            continue
        ys = slice(max(sl[0].start - 4, 0), sl[0].stop + 4)
        xs = slice(max(sl[1].start - 4, 0), sl[1].stop + 4)
        b = blobs[ys, xs] == i
        ring = cv2.dilate(b.astype(np.uint8), k).astype(bool) & ~text[ys, xs]
        v = lab[ys, xs][ring]
        ok = v > 0
        v = v[ok]
        if not len(v):
            continue
        cnt = np.bincount(v)
        cands = [j for j in np.nonzero(cnt)[0] if cnt[j] >= 0.15 * len(v)] or [int(cnt.argmax())]
        ink = None
        cy, cx = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
        for (x, y, w, h), col in text_colors:
            if x - 4 <= cx <= x + w + 4 and y - 4 <= cy <= y + h + 4:
                ink = col
        if ink is None or len(cands) == 1:
            best = cands[0] if len(cands) == 1 else int(cnt.argmax())
        else:
            ring_px = img[ys, xs][ring][ok]
            best = max(cands, key=lambda j: np.abs(ring_px[v == j].mean(0) - ink).sum())
        sub = lab[ys, xs]
        sub[b] = best
    return lab


def relabel(lab: np.ndarray) -> np.ndarray:
    u = np.unique(lab)
    u = u[u > 0]
    remap = np.zeros(lab.max() + 1, np.int32)
    remap[u] = np.arange(1, len(u) + 1)
    return remap[lab]


def merge_small(lab: np.ndarray, s_u8: np.ndarray, min_px: int) -> np.ndarray:
    """Regions smaller than min_px join the neighbour with the closest colour."""
    lab = lab.copy()
    img = s_u8.astype(np.float32)
    for _ in range(3):
        n = lab.max() + 1
        sizes = np.bincount(lab.ravel(), minlength=n)
        small = np.nonzero((sizes > 0) & (sizes < min_px))[0]
        small = small[small > 0]
        if not len(small):
            break
        means = np.stack([np.bincount(lab.ravel(), img[..., ch].ravel(), n) for ch in range(3)], 1)
        means /= np.maximum(sizes, 1)[:, None]
        objs = ndi.find_objects(lab)
        for r in small:
            sl = objs[r - 1]
            if sl is None:
                continue
            ys = slice(max(sl[0].start - 1, 0), sl[0].stop + 1)
            xs = slice(max(sl[1].start - 1, 0), sl[1].stop + 1)
            sub = lab[ys, xs]
            m = sub == r
            ring = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & ~m
            nb = sub[ring]
            nb = nb[(nb > 0) & (nb != r)]
            if not len(nb):
                continue
            cand = np.unique(nb)
            best = cand[np.abs(means[cand] - means[r]).sum(1).argmin()]
            sub[m] = best
    return lab


def region_masks(lab: np.ndarray):
    """[(id, slice, mask_in_slice)] for every region."""
    out = []
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        if sl is None:
            continue
        out.append((i, sl, lab[sl] == i))
    return out


def split_thin(lab: np.ndarray, c) -> np.ndarray:
    """Same-colour shapes that touch are one region (a pill + its connector lines). Cut it:
    thick core (survives an opening) and every thin, long branch become separate regions."""
    from skimage.morphology import skeletonize

    r = int(c.split_thin_px)
    if r <= 0:
        return lab
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    lab = lab.copy()
    nxt = lab.max() + 1
    for rid, sl in enumerate(ndi.find_objects(lab), 1):
        if sl is None:
            continue
        ys = slice(max(sl[0].start - r - 1, 0), sl[0].stop + r + 1)
        xs = slice(max(sl[1].start - r - 1, 0), sl[1].stop + r + 1)
        sub = lab[ys, xs]
        m = sub == rid
        area = m.sum()
        if area < c.split_min_thick:
            continue
        thick = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k).astype(bool)
        n, tl, st, _ = cv2.connectedComponentsWithStats(thick.astype(np.uint8), connectivity=8)
        big = np.zeros(n, bool)
        big[1:] = st[1:, cv2.CC_STAT_AREA] >= c.split_min_thick
        thick = big[tl]
        if not thick.any() or thick.sum() > 0.97 * area:
            continue
        thin = m & ~thick
        n, cl = cv2.connectedComponents(thin.astype(np.uint8), connectivity=8)
        cut = False
        for i in range(1, n):
            ci = cl == i
            if ci.sum() < 30:
                continue
            L = skeletonize(ci).sum()
            if L >= c.line_min_len and ci.sum() <= 2.5 * L * (2 * r + 1):
                sub[ci] = nxt
                nxt += 1
                cut = True
        if not cut:
            sub[m] = rid
    return lab


def photo_from_regions(lab, sf, text_mask, c):
    """Photo = where the rebuild needs many small, irregular, non-flat regions (a vector design
    is made of few clean shapes). The photo boundary follows region edges."""
    H, W = lab.shape
    n = lab.max() + 1
    area = np.bincount(lab.ravel(), minlength=n).astype(np.float64)
    from ..pentool import _stats

    # rough vector version (each region = its best linear gradient) vs the image; the error is
    # blurred: texture/grain averages out, photo content (faces, light, objects) stays
    st = _stats(sf, lab, n)
    beta = np.zeros((n, 3, 3))
    for i, s_ in st.items():
        beta[i] = s_.sse()[1]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    B = beta[lab].astype(np.float32)
    pred = B[:, :, 0] + B[:, :, 1] * (xx / W)[..., None] + B[:, :, 2] * (yy / H)[..., None]
    res = (sf - pred).astype(np.float32)
    res[text_mask] = 0
    # band-pass: fine grain (< blur) and smooth rendered lighting (> 4x blur) are not photo
    sg = float(c.photo_blur)
    band = cv2.GaussianBlur(res, (0, 0), sg) - cv2.GaussianBlur(res, (0, 0), 4 * sg)
    errb = cv2.GaussianBlur(np.abs(band).mean(-1), (0, 0), 2 * sg)
    hot = errb > c.photo_err
    rough = np.bincount(lab[hot].ravel(), minlength=n) >= 0.3 * np.maximum(area, 1)
    rough &= area >= 50
    small = area < c.photo_small_px
    sol = np.ones(n)
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        if sl is None or not small[i]:
            continue
        m = (lab[sl] == i).astype(np.uint8)
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if cnts:
            hull = cv2.contourArea(cv2.convexHull(np.vstack(cnts)))
            sol[i] = area[i] / max(hull, 1)
    cand = rough | (small & (sol < c.photo_solidity))
    cand[0] = False
    px = cand[lab] & ~text_mask
    k = int(c.photo_window) | 1
    dens = cv2.blur(px.astype(np.float32), (k, k))
    zone = dens > c.photo_density
    zone = cv2.morphologyEx(zone.astype(np.uint8), cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))).astype(bool)
    inside = np.bincount(lab[zone].ravel(), minlength=n) / np.maximum(area, 1)
    is_photo = inside >= 0.5
    is_photo[0] = False
    photo = is_photo[lab]
    nn, cl, st, _ = cv2.connectedComponentsWithStats(photo.astype(np.uint8), connectivity=8)
    keep = np.zeros(nn, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= c.photo_min_frac * H * W
    photo = keep[cl]
    if photo.any():
        # smooth, closed photo outline: bays and islands between photo parts belong to the photo
        kk = int(c.photo_close) | 1
        pc = cv2.morphologyEx(photo.astype(np.uint8), cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kk, kk))).astype(bool)
        pc = ndi.binary_fill_holes(pc)  # incl. text printed on the photo (removed later)
        # whole regions only: a region mostly swallowed by the closed outline joins the photo
        frac = np.bincount(lab[pc].ravel(), minlength=n) / np.maximum(area, 1)
        join = frac >= 0.5
        join[0] = False
        photo = photo | join[lab] | (pc & (lab == 0))
        photo = ndi.binary_fill_holes(photo)
    return photo

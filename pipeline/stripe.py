"""Step: graphic accent stripes that run BEHIND the subject -> one editable layer each.

A stripe is a straight band of the accent colour that is cut into pieces by the subject.
The pieces are grouped by collinearity (the union of the pieces is thinnest along the band
direction), the band rectangle is fitted, and the hidden part behind the subject is filled
with LaMa in band-aligned (rotated) space so the grunge texture continues. The geometry is
also exported (shapes.csv) so the band can be rebuilt as a native rotated rectangle in Canva.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import matting
from .glow import _hsv, _hue_dist, detect_accent
from .imageio import to_u8

log = logging.getLogger("split")


def _thinnest(pts: np.ndarray, coarse_step: float = 1.0):
    """Direction (deg, 0..180) along which the point set is thinnest across; returns
    (theta, width, n_lo, n_hi) with n = projection on the normal."""
    def width(th):
        t = np.radians(th)
        n = pts @ np.array([-np.sin(t), np.cos(t)], np.float32)
        lo, hi = np.percentile(n, [1, 99])
        return hi - lo, lo, hi

    best = min(np.arange(0, 180, coarse_step), key=lambda th: width(th)[0])
    fine = min(np.arange(best - coarse_step, best + coarse_step, 0.1), key=lambda th: width(th)[0])
    w, lo, hi = width(fine)
    return float(fine % 180), float(w), float(lo), float(hi)


def _sample(pts: np.ndarray, k: int = 4000) -> np.ndarray:
    if len(pts) <= k:
        return pts
    return pts[np.random.default_rng(0).choice(len(pts), k, replace=False)]


def find_stripes(img: np.ndarray, sal: np.ndarray, text_mask: np.ndarray, fg_union, cfg):
    """Return list of stripe dicts (geometry + masks)."""
    c = cfg.stripe
    H, W = sal.shape
    occl = sal > 0.02
    if fg_union is not None:
        occl |= fg_union > 0.02
    acc = detect_accent(img, matting.dilate(occl, 4) | text_mask, cfg)
    if acc is None:
        return [], None
    hue, acc_rgb = acc
    h, s, v = _hsv(img)
    m = (_hue_dist(h, hue) < c.hue_tol_deg) & (s > c.min_saturation) & (v > c.min_value)
    m &= ~matting.dilate(occl, 1) & ~matting.dilate(text_mask, 2)
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, matting.disk(2))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    comps = [i for i in np.argsort(-st[:, 4]) if i > 0 and st[i, 4] >= c.min_piece_frac * H * W]
    pts_of = {i: _sample(np.c_[np.nonzero(lab == i)[::-1]].astype(np.float32)) for i in comps}
    wid_of = {i: _thinnest(pts_of[i], 2.0)[1] for i in comps}

    stripes, used = [], set()
    for i in comps:
        if i in used:
            continue
        group = [i]
        for j in comps:
            if j == i or j in used:
                continue
            u = np.vstack([pts_of[k] for k in group + [j]])
            w_u = _thinnest(u, 2.0)[1]
            if w_u <= c.collinear_tol * max(max(wid_of[k] for k in group), wid_of[j]):
                group.append(j)
        P = np.vstack([np.c_[np.nonzero(lab == k)[::-1]].astype(np.float32) for k in group])
        th, width, n_lo, n_hi = _thinnest(_sample(P, 8000))
        t = np.radians(th)
        d = np.array([np.cos(t), np.sin(t)], np.float32)
        nv = np.array([-np.sin(t), np.cos(t)], np.float32)
        tp = P @ d
        t_lo, t_hi = np.percentile(tp, [0.2, 99.8])
        length = t_hi - t_lo
        if length < c.min_elongation * width or width < 4:
            continue
        # rectangle polygon
        corners = np.array([d * a + nv * b for a, b in
                            [(t_lo, n_lo), (t_hi, n_lo), (t_hi, n_hi), (t_lo, n_hi)]], np.float32)
        rect = np.zeros((H, W), np.uint8)
        cv2.fillPoly(rect, [np.round(corners).astype(np.int32)], 1)
        rect = rect.astype(bool)
        behind = (rect & occl).sum() / max(rect.sum(), 1)
        if behind < c.min_behind_frac:
            log.info("  stripe kandidat (%.0f deg, %dpx) tidak lewat di belakang subject -> skip",
                     th, width)
            continue
        used.update(group)
        stripes.append({"theta": th, "width": width, "length": length, "rect": rect,
                        "corners": corners, "t": (t_lo, t_hi), "n": (n_lo, n_hi),
                        "accent_hue": hue, "pieces": len(group)})
        log.info("  stripe: %.1f deg, tebal %d px, panjang %d px, %d potongan, %.0f%% di belakang subject",
                 th, width, length, len(group), 100 * behind)
        if len(stripes) >= c.max_stripes:
            break
    return stripes, m.astype(bool)


def visible_mask(stripe, acc_mask: np.ndarray, occl: np.ndarray, cfg) -> np.ndarray:
    """Pixels of the stripe that are visible in the design (incl. its dark grunge specks)."""
    c = cfg.stripe
    rect = stripe["rect"]
    vis = acc_mask & matting.dilate(rect, 2)
    vis = cv2.morphologyEx(vis.astype(np.uint8), cv2.MORPH_CLOSE, matting.disk(int(c.close_px))).astype(bool)
    vis = matting.fill_holes(vis.astype(np.float32), int(c.max_hole_px)) > 0.5
    return vis & matting.dilate(rect, 1) & ~occl


def build_layer(img: np.ndarray, plate: np.ndarray, stripe, vis: np.ndarray, occl: np.ndarray,
                models, cfg):
    """Editable stripe = ONE flat colour G + a grunge texture carried by alpha.

    Visible pixels: alpha from  C = (1 - a) * plate + a * G  (plate = clean background).
    Hidden / contaminated pixels (behind the subject, hair spill): alpha synthesized with
    LaMa in band-aligned (rotated) space so the texture continues along the band.
    Nothing of the photo (rack posts, hair, window) travels with the stripe when moved."""
    c = cfg.stripe
    H, W = vis.shape
    rect = stripe["rect"]
    vis = vis & ~matting.dilate(occl, int(c.subject_clearance_px))
    if vis.sum() < 50:
        return None, None, None
    # flat stripe colour: the bright, saturated core of the visible band
    pix = img[vis]
    lum = pix @ np.array([0.299, 0.587, 0.114], np.float32)
    G = np.median(pix[lum >= np.percentile(lum, 70)], axis=0).astype(np.float32)
    d = G[None, None] - plate
    a = ((img - plate) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-4)
    a = np.clip(a, 0, 1).astype(np.float32)
    # keep only the fine grunge: large shapes in alpha are photo structures (rack posts, window)
    # seen through the band, and those already live in the background underneath
    if c.texture_sigma > 0:
        w = vis.astype(np.float32)
        lo = cv2.GaussianBlur(a * w, (0, 0), c.texture_sigma) / np.maximum(
            cv2.GaussianBlur(w, (0, 0), c.texture_sigma), 1e-4)
        base_op = float(np.median(a[vis]))
        a = np.clip(base_op + (a - lo), 0, 1).astype(np.float32)

    th = stripe["theta"]
    M = cv2.getRotationMatrix2D((W / 2, H / 2), th, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nW, nH = int(H * sin + W * cos) + 2, int(H * cos + W * sin) + 2
    M[0, 2] += nW / 2 - W / 2
    M[1, 2] += nH / 2 - H / 2
    rot = lambda x, interp: cv2.warpAffine(x, M, (nW, nH), flags=interp)  # noqa: E731
    r_a = rot(a, cv2.INTER_LINEAR)
    r_rect = rot(rect.astype(np.uint8), cv2.INTER_NEAREST).astype(bool)
    r_vis = rot(vis.astype(np.uint8), cv2.INTER_NEAREST).astype(bool)
    ys, xs = np.nonzero(r_rect)
    pad = 8
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, nH)
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, nW)
    ca = r_a[y0:y1, x0:x1]
    cv_ = r_vis[y0:y1, x0:x1]
    med = float(np.median(ca[cv_]))
    canvas = np.where(cv_, ca, med)
    hole = r_rect[y0:y1, x0:x1] & ~cv_
    if hole.any():
        g3 = np.repeat(canvas[..., None], 3, -1)
        hm = matting.dilate(hole, 2)
        filled = models.inpaint(to_u8(g3), (hm * 255).astype(np.uint8)).astype(np.float32).mean(-1) / 255.0
        canvas = np.where(hm, filled, canvas)
    r_full = np.zeros((nH, nW), np.float32)
    r_full[y0:y1, x0:x1] = canvas
    back = cv2.warpAffine(r_full, cv2.invertAffineTransform(M), (W, H), flags=cv2.INTER_LINEAR)
    alpha_tex = np.where(vis, a, back)
    shape = matting.feather(rect.astype(np.float32), 0.6)
    shape[matting.erode(rect, 1)] = 1.0
    alpha = np.clip(alpha_tex * shape, 0, 1).astype(np.float32)
    rgb = np.broadcast_to(G, img.shape).astype(np.float32)
    log.info("  stripe layer: warna %s, opacity rata-rata %.2f",
             "#%02X%02X%02X" % tuple(int(round(float(x) * 255)) for x in G), float(alpha[rect].mean()))
    return rgb, alpha, G


def _synth_along_band(src: np.ndarray, rect: np.ndarray, known: np.ndarray, theta: float,
                      fill, models) -> np.ndarray:
    """Fill rect & ~known of an RGB image with LaMa in band-aligned (rotated) space, using only
    the known band pixels as context (everything else = fill colour), so the band texture
    continues along the band. Returns a full-size image (only rect & ~known is new)."""
    H, W = rect.shape
    M = cv2.getRotationMatrix2D((W / 2, H / 2), theta, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nW, nH = int(H * sin + W * cos) + 2, int(H * cos + W * sin) + 2
    M[0, 2] += nW / 2 - W / 2
    M[1, 2] += nH / 2 - H / 2
    rot = lambda x, interp: cv2.warpAffine(x, M, (nW, nH), flags=interp)  # noqa: E731
    r_src = rot(src, cv2.INTER_LINEAR)
    r_rect = rot(rect.astype(np.uint8), cv2.INTER_NEAREST).astype(bool)
    r_known = rot(known.astype(np.uint8), cv2.INTER_NEAREST).astype(bool)
    ys, xs = np.nonzero(r_rect)
    pad = 8
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad + 1, nH)
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad + 1, nW)
    ck = r_known[y0:y1, x0:x1] & r_rect[y0:y1, x0:x1]  # context = known BAND pixels only
    canvas = np.where(ck[..., None], r_src[y0:y1, x0:x1], np.asarray(fill, np.float32))
    hole = r_rect[y0:y1, x0:x1] & ~ck
    if hole.any():
        hm = matting.dilate(hole, 2) & ~matting.erode(ck, 1)
        filled = models.inpaint(to_u8(canvas), (hm * 255).astype(np.uint8)).astype(np.float32) / 255.0
        canvas = np.where(hm[..., None], filled, canvas)
    r_full = np.zeros((nH, nW, 3), np.float32)
    r_full[y0:y1, x0:x1] = canvas
    back = cv2.warpAffine(r_full, cv2.invertAffineTransform(M), (W, H), flags=cv2.INTER_LINEAR)
    return np.where(known[..., None], src, back).astype(np.float32)


def build_layered(img: np.ndarray, plate: np.ndarray, stripe, vis: np.ndarray,
                  matte: np.ndarray, models, cfg, top_rgb=None, top_a=None):
    """Two stacked layers that reproduce the reference 1:1:

      1. base    = solid rectangle, ONE colour G at ONE opacity o (rebuildable natively)
      2. grunge  = overlay (E, e) = minimal colour-to-alpha of the reference C against
                   "background + base", i.e.  C = (1 - e) * X1 + e * E  exactly.

    Where the stripe is hidden by the subject the reference is synthesized along the band
    first, so the stack stays complete when the subject is moved."""
    from .glow import color_to_alpha

    rect = stripe["rect"]
    vis_core = vis & ~matting.dilate(matte, int(cfg.stripe.subject_clearance_px))
    if vis_core.sum() < 50:
        return None
    pix = img[vis_core]
    lum = pix @ np.array([0.299, 0.587, 0.114], np.float32)
    G = np.median(pix[lum >= np.percentile(lum, 70)], axis=0).astype(np.float32)
    # base opacity: typical coverage of the band over the clean background
    d = G[None, None] - plate
    a_ls = ((img - plate) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-4)
    o = float(np.clip(np.median(a_ls[vis_core]), 0.2, 1.0))
    # quantize to what Canva's transparency slider / an 8-bit PNG can represent
    o = round(o * 100) / 100

    shape = matting.feather(rect.astype(np.float32), 0.6)
    shape[matting.erode(rect, 1)] = 1.0
    base_a = (shape * o).astype(np.float32)
    base_a = np.round(base_a * 255) / 255  # what will actually be stored in the PNG
    X1 = plate * (1 - base_a[..., None]) + G * base_a[..., None]

    # target under the subject stack: the reference itself where nothing covers it; behind a
    # semi-transparent edge the exact un-mixed value U = (C - a*F) / (1 - a); behind solid
    # subject (nothing visible) synthesized along the band
    target = img.copy()
    solid = rect & matte
    if top_a is not None:
        ta = top_a[..., None]
        U = (img - ta * top_rgb) / np.maximum(1 - ta, 1e-3)
        semi = rect & (top_a > 1.0 / 255) & (top_a < 0.9)
        target = np.where(semi[..., None], np.clip(U, 0, 1), target)
        solid = rect & (top_a >= 0.9)
    if solid.any():
        target = _synth_along_band(target, rect, ~solid, stripe["theta"], G, models)
    C = target
    e, E = color_to_alpha(C, X1)
    inside = matting.dilate(rect, 1)
    e = (e * inside).astype(np.float32)
    # re-solve E against the 8-bit quantized alpha so the stack stays exact after saving
    eq = np.round(e * 255) / 255
    E = np.where(eq[..., None] > 1e-3,
                 X1 + (C - X1) / np.maximum(eq, 1e-3)[..., None], X1)
    E = np.clip(E, 0, 1).astype(np.float32)
    stack = X1 * (1 - eq[..., None]) + E * eq[..., None]
    if top_a is not None:
        stack = stack * (1 - top_a[..., None]) + top_rgb * top_a[..., None]
        check = rect & (top_a < 0.9)
    else:
        check = rect & ~matte
    err = np.abs(stack - img)[check]
    log.info("  stripe berlapis: base %s opacity %.2f | grunge alpha rata-rata %.2f | "
             "error vs referensi maks %.4f",
             "#%02X%02X%02X" % tuple(int(round(float(x) * 255)) for x in G), o,
             float(eq[rect].mean()), float(err.max()) if err.size else 0.0)
    return {"base_rgb": np.broadcast_to(G, img.shape).astype(np.float32), "base_a": base_a,
            "grunge_rgb": E, "grunge_a": eq.astype(np.float32), "color": G, "opacity": o}


def canva_geometry(stripe, color, opacity: float = 1.0) -> dict:
    """Rotated-rectangle parameters for rebuilding the band as a native Canva shape."""
    corners = stripe["corners"]
    cx, cy = corners.mean(0)
    L, Wd = stripe["length"], stripe["width"]
    return {
        "shape": "rectangle",
        "cx": round(float(cx), 1), "cy": round(float(cy), 1),
        "canva_x": round(float(cx - L / 2), 1), "canva_y": round(float(cy - Wd / 2), 1),
        "canva_w": round(float(L), 1), "canva_h": round(float(Wd), 1),
        "canva_rotation_deg": round(float(stripe["theta"]), 1),
        "color_hex": "#%02X%02X%02X" % tuple(int(round(float(x) * 255)) for x in color),
        "canva_transparency_pct": int(round(opacity * 100)),
        "corners": [[round(float(a), 1), round(float(b), 1)] for a, b in corners],
    }

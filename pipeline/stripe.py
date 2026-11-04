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


def _blur_along_band(arr: np.ndarray, weight: np.ndarray, theta: float, sigma: float) -> np.ndarray:
    """Normalized 1-D Gaussian blur along the band direction (across-band detail is kept)."""
    H, W = arr.shape
    M = cv2.getRotationMatrix2D((W / 2, H / 2), theta, 1.0)
    cos, sin = abs(M[0, 0]), abs(M[0, 1])
    nW, nH = int(H * sin + W * cos) + 2, int(H * cos + W * sin) + 2
    M[0, 2] += nW / 2 - W / 2
    M[1, 2] += nH / 2 - H / 2
    ra = cv2.warpAffine((arr * weight).astype(np.float32), M, (nW, nH))
    rw = cv2.warpAffine(weight.astype(np.float32), M, (nW, nH))
    k = int(sigma * 3) * 2 + 1
    ra = cv2.GaussianBlur(ra, (k, 1), sigma)
    rw = cv2.GaussianBlur(rw, (k, 1), sigma)
    Minv = cv2.invertAffineTransform(M)
    num = cv2.warpAffine(ra, Minv, (W, H))
    den = cv2.warpAffine(rw, Minv, (W, H))
    return num / np.maximum(den, 1e-4)


def build_layered(img: np.ndarray, plate: np.ndarray, stripe, vis: np.ndarray,
                  matte: np.ndarray, models, cfg, top_rgb=None, top_a=None):
    """Stripe as 3 stacked NORMAL-blend layers (any Canva plan), reproducing the reference:

      base    solid rectangle, colour G, constant opacity o              (..._base.png)
      grunge  SAME colour G, per-pixel opacity = the orange specks       (..._grunge.png)
      shade   thin dark/light "depth" layer for what a normal-blend stripe cannot explain,
              e.g. rack posts that stay dark *through* the stripe        (..._shade.png)

    Stripe coverage a(x) = smooth variation ALONG the band (segments can be more or less
    transparent) + fine grunge. Anything crossing the band (posts, window) is not in a(x);
    it goes, together with any other residual, into the optional shade layer, so that
    clean background + base + grunge + shade == reference.
    """
    from .glow import color_to_alpha

    c = cfg.stripe
    rect = stripe["rect"]
    vis_core = vis & ~matting.dilate(matte, int(c.subject_clearance_px))
    if vis_core.sum() < 50:
        return None
    pix = img[vis_core]
    lum = pix @ np.array([0.299, 0.587, 0.114], np.float32)
    G = np.median(pix[lum >= np.percentile(lum, 70)], axis=0).astype(np.float32)
    G = np.round(G * 255) / 255

    # target under everything that sits above the stripe (subject / fg)
    target = img.copy()
    solid = rect & matte
    if top_a is not None:
        ta = top_a[..., None]
        U = (img - ta * top_rgb) / np.maximum(1 - ta, 1e-3)
        semi = rect & (top_a > 1.0 / 255) & (top_a < 0.9)
        target = np.where(semi[..., None], np.clip(U, 0, 1), target)
        solid = rect & (top_a >= 0.9)
    known = rect & ~solid

    # measured coverage vs the stripe-free plate -> smooth along band + fine grunge
    d = G[None, None] - plate
    a_ls = np.clip(((target - plate) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-4), 0, 1)
    w = vis_core.astype(np.float32)  # clean stripe pixels only
    sig_c = c.coverage_sigma
    a_along = cv2.GaussianBlur(a_ls * w, (0, 0), sig_c) / np.maximum(
        cv2.GaussianBlur(w, (0, 0), sig_c), 1e-4)
    # far from any visible stripe pixel (behind the body) fall back to the band median
    cover = cv2.GaussianBlur(w, (0, 0), sig_c)
    med = float(np.median(a_ls[vis_core]))
    t_ = np.clip(cover / 0.05, 0, 1)
    a_along = a_along * t_ + med * (1 - t_)
    lo = cv2.GaussianBlur(a_ls * w, (0, 0), c.texture_sigma) / np.maximum(
        cv2.GaussianBlur(w, (0, 0), c.texture_sigma), 1e-4)
    grunge = np.where(vis_core, a_ls - lo, 0)
    a_tex = np.clip(a_along + grunge, c.min_alpha, c.max_alpha).astype(np.float32)
    # behind the subject: the smooth along-band coverage continues (no blocky synthesis)
    a_tex = np.where(solid, np.clip(a_along, c.min_alpha, c.max_alpha), a_tex)

    # base + grunge (both colour G)
    shape = matting.feather(rect.astype(np.float32), 0.6)
    shape[matting.erode(rect, 1)] = 1.0
    o = round(float(np.percentile(a_tex[known], c.base_percentile)) * 100) / 100
    base_a = np.round(shape * o * 255) / 255
    e = np.round(np.clip((a_tex - o) / max(1 - o, 1e-3), 0, 1) * shape * 255) / 255
    a_tot = base_a + e * (1 - base_a)

    # background under the visible stripe: the scene seen THROUGH the stripe (dark beams,
    # bright window) as LUMINANCE only, un-mixed from the reference, applied to the clean
    # plate's colour. Grey-level un-mixing cannot produce the orange/teal patches of a full
    # RGB un-mix, and none of the photo ends up in the stripe layers.
    LUMA = np.array([0.299, 0.587, 0.114], np.float32)
    Cl, Gl, Pl = target @ LUMA, float(G @ LUMA), plate @ LUMA
    Bl = np.clip((Cl - a_tot * Gl) / np.maximum(1 - a_tot, 1e-3), 0, 1)
    Bl = matting.guided_filter(np.repeat(Cl[..., None], 3, -1), Bl, 2, 1e-4)  # tame noise gain
    ratio = np.clip(Bl / np.maximum(Pl, 0.02), 0, c.max_luma_gain)
    B_scene = np.clip(plate * ratio[..., None], 0, 1)
    # where the plate is near black, ratio is unstable -> use neutral grey of that luminance
    dark = (Pl < 0.02)[..., None]
    B_scene = np.where(dark, np.clip(Bl, 0, 1)[..., None].repeat(3, -1), B_scene)
    B_scene = np.round(B_scene * 255) / 255
    B = np.where(known[..., None], B_scene, plate).astype(np.float32)
    if c.shade:  # with a shade layer the residual goes there and the background stays clean
        B = plate
    X2 = B * (1 - a_tot[..., None]) + G * a_tot[..., None]

    # shade: whatever is left (only where B had to be clipped), minimal colour-to-alpha
    sh_a, sh_rgb = color_to_alpha(target, X2)
    sh_a = np.where(known & (np.abs(target - X2).max(-1) > c.shade_min_diff), sh_a, 0)
    if not c.shade:
        sh_a = np.zeros_like(sh_a)
    sh_a = np.round(sh_a * 255) / 255
    sh_rgb = np.where(sh_a[..., None] > 1e-3,
                      X2 + (target - X2) / np.maximum(sh_a, 1e-3)[..., None], X2)
    sh_rgb = np.clip(sh_rgb, 0, 1).astype(np.float32)

    stack = X2 * (1 - sh_a[..., None]) + sh_rgb * sh_a[..., None]
    if top_a is not None:
        stack = stack * (1 - top_a[..., None]) + top_rgb * top_a[..., None]
    err = np.abs(stack - img)[known]
    log.info("  stripe 3 layer: %s | base opacity %.2f | grunge rata-rata %.2f | shade %.1f%% strip | "
             "error vs referensi maks %.4f (rata-rata %.5f)",
             "#%02X%02X%02X" % tuple(int(round(float(x) * 255)) for x in G), o,
             float(e[rect].mean()), 100 * float((sh_a[rect] > 0).mean()),
             float(err.max()) if err.size else 0.0, float(err.mean()) if err.size else 0.0)
    rgb = np.broadcast_to(G, img.shape).astype(np.float32)
    return {"base_rgb": rgb, "base_a": base_a.astype(np.float32),
            "grunge_rgb": rgb, "grunge_a": e.astype(np.float32),
            "shade_rgb": sh_rgb, "shade_a": sh_a.astype(np.float32),
            "bg_under": B, "bg_mask": known, "color": G, "opacity": o}


def build_multiply(img: np.ndarray, plate: np.ndarray, stripe, vis: np.ndarray,
                   matte: np.ndarray, models, cfg, top_rgb=None, top_a=None):
    """Stripe as it behaves in the reference: an orange layer in MULTIPLY blend.

        C = S * (1 - a + a*G)        (per channel; S = scene behind the stripe)

    Fitting this per pixel separates cleanly: a (how orange) is almost constant per stripe
    segment, S holds the scene (window, beams) without any orange. S is further split into
    S = S_low * T, where T are the small dark grunge specks:

      01_background           S_low under the stripe (scene, no orange, no specks)
      04_stripe_NN_base       colour G, MULTIPLY, opacity a (smooth, per segment)
      04_stripe_NN_grunge     BLACK specks, NORMAL blend, opacity 1 - T
                              (black + normal == multiply by T, so no blend mode needed)
    """
    c = cfg.stripe
    rect = stripe["rect"]
    LUMA = np.array([0.299, 0.587, 0.114], np.float32)
    vis_core = vis & ~matting.dilate(matte, int(c.subject_clearance_px))
    if vis_core.sum() < 50:
        return None
    pix = img[vis_core]
    lum = pix @ LUMA
    G = np.median(pix[lum >= np.percentile(lum, 70)], axis=0).astype(np.float32)
    G = np.round(G / max(G.max(), 1e-3) * 255) / 255  # brightest version of the hue

    target = img.copy()
    solid = rect & matte
    if top_a is not None:
        ta = top_a[..., None]
        U = (img - ta * top_rgb) / np.maximum(1 - ta, 1e-3)
        semi = rect & (top_a > 1.0 / 255) & (top_a < 0.9)
        target = np.where(semi[..., None], np.clip(U, 0, 1), target)
        solid = rect & (top_a >= 0.9)
    known = rect & ~solid

    # 1. per-pixel multiply fit (grid over a, closed form for neutral s)
    Cb = target[known]
    best = np.full(len(Cb), 1e9, np.float32)
    a_px = np.zeros(len(Cb), np.float32)
    s_px = np.zeros(len(Cb), np.float32)
    for a in np.linspace(0, 1, 101, dtype=np.float32):
        f = 1 - a + a * G
        sv = np.clip((Cb @ f) / float(f @ f), 0, None)
        err = ((Cb - sv[:, None] * f) ** 2).sum(1)
        m = err < best
        best[m], a_px[m], s_px[m] = err[m], a, sv[m]
    A = np.zeros(rect.shape, np.float32)
    A[known] = a_px
    Sv = np.zeros(rect.shape, np.float32)
    Sv[known] = s_px
    rel = known & (Sv > c.mult_min_scene)  # in near-black pixels a is undetermined

    # 2. smooth coverage per segment (no scene structure), filled behind the subject
    w = rel.astype(np.float32)
    sig = c.coverage_sigma
    num, den = cv2.GaussianBlur(A * w, (0, 0), sig), cv2.GaussianBlur(w, (0, 0), sig)
    num2, den2 = cv2.GaussianBlur(A * w, (0, 0), sig * 4), cv2.GaussianBlur(w, (0, 0), sig * 4)
    med = float(np.median(A[rel])) if rel.any() else 1.0
    a_s = np.where(den > 0.02, num / np.maximum(den, 1e-4),
                   np.where(den2 > 0.005, num2 / np.maximum(den2, 1e-4), med))
    a_s = np.clip(a_s, 0, 1).astype(np.float32)
    shape = matting.feather(rect.astype(np.float32), 0.6)
    shape[matting.erode(rect, 1)] = 1.0
    base_a = np.round(a_s * shape * 255) / 255

    # 3. scene behind the stripe: exact division, then split off the grunge specks
    f = 1 - base_a[..., None] + base_a[..., None] * G
    S = np.clip(target / np.maximum(f, 1e-3), 0, 1)
    if c.neutral_scene:  # scene keeps its brightness but takes the colour cast of the clean plate
        pb = cv2.GaussianBlur(plate, (0, 0), 15)
        tint = pb / np.maximum(pb @ LUMA, 1e-3)[..., None]
        tint = np.clip(tint / np.maximum(tint.max(-1, keepdims=True), 1e-3) *
                       np.minimum(tint.max(-1, keepdims=True), 1.3), 0, 2)
        S = np.where(known[..., None], np.clip((S @ LUMA)[..., None] * tint, 0, 1), S)
    L = S @ LUMA
    env = cv2.GaussianBlur(cv2.dilate(L, matting.disk(int(c.speck_px))), (0, 0), c.speck_px / 2)
    T = np.clip(L / np.maximum(env, 1e-3), 0, 1)
    g_a = np.where(known, 1 - T, 0).astype(np.float32)
    g_a[g_a < c.speck_min] = 0
    # specks are blob-like; thin long lines (window frame edges, hair strands) are photo
    # detail -> they stay in the background (S_low absorbs them, the stack stays exact)
    g_a[matting.dilate(matte, int(c.subject_clearance_px))] = 0
    ink = (g_a > c.line_min_alpha).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    if n > 1:
        long_side = np.maximum(st[:, 2], st[:, 3]).astype(np.float32)
        line = (long_side >= c.line_min_len) & (st[:, 4] / np.maximum(long_side, 1) < c.line_max_width)
        big = st[:, 4] > c.speck_max_area  # large connected dark shapes = structure, not specks
        line = line | big
        line[0] = False
        g_a[matting.dilate(line[lab], 1)] = 0
    if solid.any():  # continue the speck texture behind the subject
        g3 = _synth_along_band(np.repeat(g_a[..., None], 3, -1), rect, ~solid, stripe["theta"],
                               [0.0] * 3, models)
        g_a = np.where(solid, g3.mean(-1), g_a)
    g_a = np.round(np.clip(g_a, 0, 1) * shape * 255) / 255
    S_low = np.clip(S / np.maximum(1 - g_a, 1e-3)[..., None], 0, 1)
    B = np.where(known[..., None], S_low, plate).astype(np.float32)
    B = np.round(B * 255) / 255

    stack = B * (1 - base_a[..., None]) + B * G * base_a[..., None]  # multiply
    stack = stack * (1 - g_a[..., None])  # black specks, normal
    if top_a is not None:
        stack = stack * (1 - top_a[..., None]) + top_rgb * top_a[..., None]
    err = np.abs(stack - img)[known]
    log.info("  stripe multiply: %s | opacity base %.2f (median) | bercak %.0f%% strip | "
             "error vs referensi rata-rata %.2f/255, maks %.0f/255",
             "#%02X%02X%02X" % tuple(int(round(float(x) * 255)) for x in G), med,
             100 * float((g_a[rect] > 0.05).mean()), 255 * float(err.mean()), 255 * float(err.max()))
    return {"base_rgb": np.broadcast_to(G, img.shape).astype(np.float32), "base_a": base_a.astype(np.float32),
            "grunge_rgb": np.zeros_like(img), "grunge_a": g_a.astype(np.float32),
            "bg_under": B, "bg_mask": known, "color": G, "opacity": round(med, 2)}


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

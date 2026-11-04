"""Step: OCR text blocks (EasyOCR) -> text.csv rows + glyph mask for inpainting.

Text is never exported as an image layer; it is masked and removed from the background so it
can be recreated as native Canva text.
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

from . import matting
from .imageio import to_u8

log = logging.getLogger("split")


def _hex(rgb) -> str:
    r, g, b = (int(round(float(v) * 255)) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _glyph_mask(img: np.ndarray, poly: np.ndarray, pad: int, tol: float):
    """Split the text box into text vs background by 2-means in Lab.

    The cluster that dominates the box border is background; the other is the text.
    Returns (glyph mask full-size bool, text color rgb, ok flag).
    """
    H, W = img.shape[:2]
    x, y, w, h = cv2.boundingRect(poly)
    x0, y0 = max(x - pad, 0), max(y - pad, 0)
    x1, y1 = min(x + w + pad, W), min(y + h + pad, H)
    crop = img[y0:y1, x0:x1]
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2Lab).reshape(-1, 3)

    inside = np.zeros((H, W), np.uint8)
    cv2.fillPoly(inside, [poly], 1)
    inside_c = inside[y0:y1, x0:x1].astype(bool)

    samples = lab[inside_c.ravel()].astype(np.float32)
    if len(samples) < 20:
        return None, None, False
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
    _, labels, centers = cv2.kmeans(samples, 2, None, crit, 3, cv2.KMEANS_PP_CENTERS)

    # border ring of the (unpadded) box decides which cluster is background
    ring = inside_c & ~matting.erode(inside_c, max(2, h // 12))
    d_all = np.linalg.norm(lab[:, None, :] - centers[None], axis=-1)  # N x 2
    ring_lab = d_all[ring.ravel()].argmin(1)
    bg_k = int(np.bincount(ring_lab, minlength=2).argmax())
    tx_k = 1 - bg_k

    sep = float(np.linalg.norm(centers[0] - centers[1]))
    d_tx, d_bg = d_all[:, tx_k], d_all[:, bg_k]
    glyph = (d_tx < d_bg) & (d_tx < tol * sep)
    glyph = glyph.reshape(crop.shape[:2])
    # keep only connected pieces that mostly belong to THIS box (padding may reach neighbours)
    n, lab_cc, stats, _ = cv2.connectedComponentsWithStats(glyph.astype(np.uint8), connectivity=8)
    if n > 1:
        ins = np.bincount(lab_cc.ravel(), weights=inside_c.ravel(), minlength=n)
        keep = ins / np.maximum(stats[:, cv2.CC_STAT_AREA], 1) >= 0.5
        keep[0] = False
        glyph = keep[lab_cc]
    cov = glyph[inside_c].mean()
    ok = sep > 12 and 0.03 < cov < 0.85

    col = np.median(crop[glyph], axis=0) if glyph.any() else crop.reshape(-1, 3).mean(0)
    full = np.zeros((H, W), bool)
    full[y0:y1, x0:x1] = glyph
    return full, col, ok


def _second_pass(reader, glyph: np.ndarray, poly: np.ndarray, heights, thins):
    """Re-recognize from a clean black-on-white binarized crop at several scales/stroke
    weights (heavy display fonts read much better slightly thinned). Best confidence wins."""
    x, y, w, h = cv2.boundingRect(poly)
    pad = max(4, h // 6)
    H, W = glyph.shape
    x0, y0, x1, y1 = max(x - pad, 0), max(y - pad, 0), min(x + w + pad, W), min(y + h + pad, H)
    g = glyph[y0:y1, x0:x1].astype(np.uint8)  # no closing: it glues tight display letters
    bw0 = np.where(g > 0, 0, 255).astype(np.uint8)
    best = None
    for hh in heights:
        s = hh / bw0.shape[0]
        bw = cv2.resize(bw0, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        for t in thins:
            b = cv2.dilate(bw, np.ones((t + 1, t + 1), np.uint8)) if t else bw
            b = cv2.copyMakeBorder(b, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
            try:
                res = reader.recognize(b, detail=1)
            except Exception as e:  # noqa: BLE001
                log.debug("second pass failed: %s", e)
                continue
            if res and (best is None or res[0][2] > best[1]):
                best = (res[0][1].strip(), float(res[0][2]))
    return best


def _find_container(img: np.ndarray, rect, glyph: np.ndarray, cfg):
    """Look for a button / pill / box that tightly encloses a text block.

    Returns (filled mask bool HxW, info dict) or (None, None).
    """
    c = cfg.text.container
    H, W = img.shape[:2]
    x, y, w, h = rect
    mx, my = int(c.search_margin_x * h), int(c.search_margin_y * h)
    x0, y0, x1, y1 = max(x - mx, 0), max(y - my, 0), min(x + w + mx, W), min(y + h + my, H)
    crop = img[y0:y1, x0:x1]
    lab = cv2.cvtColor(crop, cv2.COLOR_RGB2Lab)
    gx = cv2.Sobel(lab, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(lab, cv2.CV_32F, 0, 1)
    mag = np.sqrt((gx ** 2 + gy ** 2).sum(-1))
    edges = (mag > c.edge_threshold).astype(np.uint8)
    edges[matting.dilate(glyph[y0:y1, x0:x1], 2)] = 0
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    tx0, ty0, tx1, ty1 = x - x0, y - y0, x - x0 + w, y - y0 + h
    best = None
    for cnt in cnts:
        rx, ry, rw, rh = cv2.boundingRect(cnt)
        if not (rx <= tx0 + 2 and ry <= ty0 + 2 and rx + rw >= tx1 - 2 and ry + rh >= ty1 - 2):
            continue
        if rw * rh > c.max_area_mult * w * h or rw * rh < 1.05 * w * h:
            continue
        hull = cv2.convexHull(cnt)
        if cv2.contourArea(hull) / float(rw * rh) < c.min_rectangularity:
            continue
        if best is None or rw * rh < best[1]:
            best = (hull, rw * rh)
    if best is None:
        return None, None
    fill = np.zeros(crop.shape[:2], np.uint8)
    cv2.drawContours(fill, [best[0]], -1, 1, thickness=-1)
    fill = cv2.dilate(fill, matting.disk(1)).astype(bool)
    ring = fill & ~matting.erode(fill, 3)
    inner = matting.erode(fill, 4) & ~matting.dilate(glyph[y0:y1, x0:x1], 2)
    full = np.zeros((H, W), bool)
    full[y0:y1, x0:x1] = fill
    bx, by, bw_, bh = cv2.boundingRect(full.astype(np.uint8))
    fill_c = np.median(crop[inner], axis=0) if inner.any() else np.median(crop[fill], axis=0)
    rp = crop[ring]
    if len(rp):  # border = ring pixels that differ most from the fill (thin strokes)
        d = np.linalg.norm(rp - fill_c, axis=1)
        border_c = np.median(rp[d >= np.percentile(d, 75)], axis=0)
        border_hex = _hex(border_c) if d.max() > 0.08 else ""
    else:
        border_hex = ""
    return full, {"box_x": bx, "box_y": by, "box_w": bw_, "box_h": bh,
                  "box_fill_hex": _hex(fill_c), "box_border_hex": border_hex}


def detect_text(img: np.ndarray, models, sal: np.ndarray, cfg):
    """Returns (blocks, text_mask, ui_elements). ui_elements: list of {rgb, alpha, info}."""
    c = cfg.text
    H, W = img.shape[:2]
    mask = np.zeros((H, W), bool)
    blocks, ui = [], []
    if not c.enabled:
        return blocks, mask, ui
    u8 = to_u8(img)
    results = models.ocr.readtext(u8)
    hard_sal = sal > cfg.subject.hard_threshold
    for box, txt, conf in results:
        poly = np.array(box, dtype=np.int32).reshape(-1, 1, 2)
        if conf < c.min_confidence:
            log.info("  text skip (conf %.2f): %r", conf, txt)
            continue
        inside = np.zeros((H, W), np.uint8)
        cv2.fillPoly(inside, [poly], 1)
        inside = inside.astype(bool)
        if inside.sum() == 0:
            continue
        angle = float(np.degrees(np.arctan2(box[1][1] - box[0][1], box[1][0] - box[0][0])))
        ov = hard_sal[inside].mean()
        on_subject = ov > c.max_subject_overlap
        if on_subject and not (conf >= c.design_text_min_conf and abs(angle) <= c.design_text_max_angle):
            log.info("  text skip (%.0f%% di atas subject, bagian dari foto): %r", 100 * ov, txt)
            continue
        x, y, w, h = cv2.boundingRect(poly)
        pad = int(round(c.pad_frac * h))
        glyph, col, ok = _glyph_mask(img, poly, pad, c.color_tol)
        method = "glyph"
        if not ok or glyph is None:
            glyph = matting.dilate(inside, pad // 2)  # fallback: mask the (padded) box
            col = col if col is not None else img[inside].mean(0)
            method = "box"

        if c.second_pass and method == "glyph":
            sp = _second_pass(models.ocr, glyph, poly, c.second_pass_heights, c.second_pass_thin)
            if sp and sp[1] > conf + 0.02:
                log.info("  text 2nd pass: %r (%.2f) -> %r (%.2f)", txt, conf, sp[0], sp[1])
                txt, conf = sp
        if c.fix_text and method == "glyph":
            fixed = _fix_text(txt, glyph, (x, y, w, h), pad, c)
            if fixed != txt:
                log.info("  text fix (geometri glyph): %r -> %r", txt, fixed)
                txt = fixed

        # glyph extent -> font size
        rows = np.where(glyph[y:y + h].sum(1) > max(2, 0.01 * w))[0]
        gh = int(rows.max() - rows.min() + 1) if len(rows) else h
        gx, gy, gw, ghh = cv2.boundingRect(glyph.astype(np.uint8))
        if gw == 0:
            gx, gy, gw, ghh = x, y, w, h
        b = {
            "id": len(blocks) + 1, "text": txt, "confidence": round(float(conf), 3),
            "x": int(gx), "y": int(gy), "w": int(gw), "h": int(ghh),
            "ocr_bbox": [int(x), int(y), int(w), int(h)],
            "color_hex": _hex(col), "glyph_height_px": gh,
            "est_font_size_px": int(round(gh / c.cap_height_ratio)),
            "is_upper": txt.upper() == txt, "angle_deg": round(angle, 1), "mask_method": method,
        }

        # button / pill around the text -> separate UI element, removed from subject + bg
        if c.container.enabled and h <= c.container.max_text_height_frac * H:
            cmask, info = _find_container(img, (x, y, w, h), glyph, cfg)
            if cmask is not None:
                b.update(info)
                fill = np.array([int(info["box_fill_hex"][i:i + 2], 16) for i in (1, 3, 5)]) / 255.0 \
                    if info["box_fill_hex"] else None
                ui_rgb = img.copy()
                if fill is not None:  # erase the text inside the button with its flat fill
                    gl = matting.dilate(glyph, 3) & matting.erode(cmask, 4)
                    soft = matting.feather(gl.astype(np.float32), 0.8)[..., None]
                    ui_rgb = ui_rgb * (1 - soft) + fill.astype(np.float32) * soft
                a = matting.feather(cmask.astype(np.float32), 0.6)
                ui.append({"rgb": ui_rgb, "alpha": a, "text_id": b["id"], "mask": cmask})
                mask |= cmask
                log.info("  ui box di sekitar %r: %s fill=%s border=%s", txt,
                         [info["box_x"], info["box_y"], info["box_w"], info["box_h"]],
                         info["box_fill_hex"], info["box_border_hex"])

        if not on_subject:
            glyph &= ~hard_sal  # never cut into the photo subject
        blocks.append(b)
        mask |= glyph
        log.info("  text: %r conf=%.2f color=%s ~%dpx", txt, conf, b["color_hex"], b["est_font_size_px"])
    if c.decor.enabled:
        dm, decor = _find_decor(img, blocks, mask | hard_sal, cfg)
        mask |= dm
        for d in decor:
            d["id"] = len(blocks) + 1
            blocks.append(d)
    mask = matting.dilate(mask, int(c.dilate_px))
    return blocks, mask, ui


def _find_decor(img: np.ndarray, blocks, taken: np.ndarray, cfg):
    """Small graphic marks next to small text on the same line (dividers "/", "|", rules
    "----", bullets) that OCR does not read. Matched by colour to the line's text colours."""
    c = cfg.text.decor
    H, W = img.shape[:2]
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2Lab)
    out = np.zeros((H, W), bool)
    found = []
    small = [b for b in blocks if b["h"] <= cfg.text.container.max_text_height_frac * H
             and "box_x" not in b]
    for b in small:
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        y0, y1 = max(int(y - c.band_pad * h), 0), min(int(y + h + c.band_pad * h), H)
        sx0, sx1 = int(x - c.search_x * h), int(x + w + c.search_x * h)
        # analyse a wider strip so marks crossing the search window are kept whole
        x0, x1 = max(int(x - 3 * c.search_x * h), 0), min(int(x + w + 3 * c.search_x * h), W)
        # colours of all small text on this line
        cols = [_rgb(o["color_hex"]) for o in small if abs((o["y"] + o["h"] / 2) - (y + h / 2)) < h]
        cols_lab = cv2.cvtColor(np.array([cols], np.float32), cv2.COLOR_RGB2Lab)[0]
        crop = lab[y0:y1, x0:x1]
        d = np.min(np.linalg.norm(crop[:, :, None, :] - cols_lab[None, None], axis=-1), axis=-1)
        L = crop[..., 0]
        contrast = np.abs(L - np.median(L)) > c.line_contrast
        free = ~taken[y0:y1, x0:x1] & ~out[y0:y1, x0:x1]
        # thin straight rules (often gradient-coloured) + marks matching the text colour
        lines = np.zeros_like(contrast)
        nl, ll, sl, _ = cv2.connectedComponentsWithStats((contrast & free).astype(np.uint8), connectivity=8)
        for j in range(1, nl):
            lw, lh, la = sl[j, 2], sl[j, 3], sl[j, 4]
            long_, thin = max(lw, lh), min(lw, lh)
            if long_ >= h and thin <= c.line_max_thickness * h and la >= 0.6 * long_ * max(thin, 1) * 0.5:
                lines |= ll == j
        cand = (((d < c.color_tol) | lines) & free)
        n, labcc, st, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), connectivity=8)
        for i in range(1, n):
            area = st[i, cv2.CC_STAT_AREA]
            cx, cy, cw, ch = st[i, :4]
            if area < c.min_area or area > c.max_area_h2 * h * h:
                continue
            if cy == 0 or cy + ch >= y1 - y0:  # touches band edge -> part of something bigger
                continue
            if x0 + cx > sx1 or x0 + cx + cw < sx0:  # not near this text block
                continue
            comp = labcc == i
            sub_m = np.zeros((H, W), bool)
            sub_m[y0:y1, x0:x1] = comp
            label = _decor_label(comp[cy:cy + ch, cx:cx + cw])
            col = np.median(img[sub_m], axis=0)
            if label == "[line]":  # rules often fade out at the ends: extend along the axis
                ext = int(c.line_extend * h)
                sub_m = cv2.dilate(sub_m.astype(np.uint8), np.ones((1, 2 * ext + 1), np.uint8)).astype(bool)
            out |= sub_m
            found.append({"text": label, "confidence": "",
                          "x": int(x0 + cx), "y": int(y0 + cy),
                          "w": int(cw), "h": int(ch), "color_hex": _hex(col),
                          "mask_method": "decor"})
            log.info("  decor dekat %r: bbox %s %s", b["text"], [int(x0 + cx), int(y0 + cy), int(cw), int(ch)],
                     _hex(col))
    return out, found


def _rgb(hexs: str):
    return [int(hexs[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]


JUNK_EDGE = "~`'^_|\"´‘’“”,; "


def _runs(cols: np.ndarray):
    """Start/end (exclusive) of consecutive True runs."""
    d = np.diff(np.r_[0, cols.astype(np.int8), 0])
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _fix_text(txt: str, glyph: np.ndarray, rect, pad: int, c) -> str:
    """Repair typical OCR slips on display type using the glyph geometry:
    junk characters at the ends, missing word spaces, mixed case on all-caps text and
    '.' read as ':'."""
    H, W = glyph.shape
    x, y, w, h = rect
    x0, x1 = max(x - pad, 0), min(x + w + pad, W)
    g = glyph[y:y + h, x0:x1]
    runs = [r for r in _runs(g.sum(0) > 0) if r[1] - r[0] >= 1]
    t = txt.strip(JUNK_EDGE) or txt
    if len(runs) < 2:
        return t
    rows = np.where(g.sum(1) > 0)[0]
    gh = rows.max() - rows.min() + 1
    info = []
    for a, b in runs:
        rr = np.where(g[:, a:b].sum(1) > 0)[0]
        info.append((a, b, rr.min(), rr.max()))
    full = [r for r in info if (r[3] - r[2] + 1) >= 0.5 * gh]  # letters, not punctuation

    # trailing punctuation: a lone small blob on the baseline is '.', two stacked blobs ':'
    la, lb, lt, lbm = info[-1]
    if (lbm - lt + 1) < 0.4 * gh and (lb - la) < 0.6 * np.median([r[1] - r[0] for r in info]):
        n_blobs = len(_runs(g[:, la:lb].sum(1) > 0))
        p = "." if n_blobs == 1 else ":"
        if t[-1:] in ".:;,":
            t = t[:-1] + p
        else:
            t = t + p

    # all caps: every letter-run spans the same top and bottom line
    if len(full) >= 2 and any(ch.isupper() for ch in t):
        tops = np.array([r[2] for r in full])
        bots = np.array([r[3] for r in full])
        if np.ptp(tops) <= c.caps_tolerance * gh and np.ptp(bots) <= c.caps_tolerance * gh:
            t = t.upper()

    # word spaces from unusually wide gaps
    gaps = [(info[i + 1][0] - info[i][1], info[i][1], info[i + 1][0]) for i in range(len(info) - 1)]
    widths = np.array([gp[0] for gp in gaps], float)
    thr = max(c.space_gap_mult * np.median(widths), c.space_min_frac * gh)
    word_gaps = [gp for gp in gaps if gp[0] > thr]
    if len(word_gaps) > t.count(" "):
        core = t.replace(" ", "")
        trail = ""
        while core and not core[-1].isalnum():
            trail, core = core[-1] + trail, core[:-1]
        letters = [r for r in info if (r[3] - r[2] + 1) >= 0.5 * gh]
        if len(letters) == len(core):  # one run per character: exact split
            starts = [r[0] for r in letters]
            cut = sorted({sum(1 for s0 in starts if s0 < gp[2]) for gp in word_gaps})
        else:  # proportional
            xa, xb = info[0][0], letters[-1][1] if letters else info[-1][1]
            cut = sorted({int(round(len(core) * ((gp[1] + gp[2]) / 2 - xa) / max(xb - xa, 1)))
                          for gp in word_gaps})
        parts, prev = [], 0
        for k in cut:
            if 0 < k < len(core):
                parts.append(core[prev:k])
                prev = k
        parts.append(core[prev:])
        t = " ".join(p for p in parts if p) + trail
    return t


def _decor_label(m: np.ndarray) -> str:
    """Name a small graphic mark: '/', '\\', '|', '[line]' or '[decor]'."""
    h, w = m.shape
    if w >= 4 * h:
        return "[line]"
    if h >= 1.5 * w:
        ys, xs = np.nonzero(m)
        if len(xs) > 3 and w >= 3:
            top = xs[ys < h / 2].mean() if (ys < h / 2).any() else 0
            bot = xs[ys >= h / 2].mean() if (ys >= h / 2).any() else 0
            if top - bot > 0.25 * w:
                return "/"
            if bot - top > 0.25 * w:
                return "\\"
        return "|"
    return "[decor]"

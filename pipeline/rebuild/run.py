"""Automatic REBUILD of one design (no Claude needed):

    text (OCR, removed) -> regions (edges only) -> fill + primitive shape per region
    -> objects (one SVG per icon / shape / line colour) -> photos stay photos
    -> ONE general effect layer for what vectors cannot express -> Canva package.
"""
from __future__ import annotations

import copy
import json
import logging
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

from .. import matting
from ..config import Cfg
from ..imageio import load_rgb, to_u8
from . import package, regions, shapes

log = logging.getLogger("split")


def _text_cfg(cfg):
    c = Cfg(copy.deepcopy(dict(cfg)))
    c["text"]["container"]["enabled"] = False  # pills/buttons are shapes here, not text
    c["text"]["decor"]["enabled"] = False      # small marks are vectorised, not text
    return c


def _block_mask(img, b, cfg):
    """Glyph blob of one text block (used when some OCR hits were dropped)."""
    from .. import text as textmod

    H, W = img.shape[:2]
    x, y, w, h = b["ocr_bbox"]
    poly = np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.int32).reshape(-1, 1, 2)
    pad = int(round(cfg.text.pad_frac * h))
    glyph, _, ok = textmod._glyph_mask(img, poly, pad, cfg.text.color_tol)
    if not ok or glyph is None:
        glyph = np.zeros((H, W), bool)
        glyph[y:y + h, x:x + w] = True
    r = max(2, int(round(cfg.text.inpaint_close_frac * h)))
    m = cv2.morphologyEx(glyph.astype(np.uint8), cv2.MORPH_CLOSE, matting.disk(r)).astype(bool)
    return matting.dilate(m, int(cfg.text.dilate_px))


def _touches_border(sl, H, W):
    return sl[0].start == 0 or sl[1].start == 0 or sl[0].stop == H or sl[1].stop == W


def process_rebuild(path: Path, out_root: Path, models, cfg) -> dict:
    c = cfg.rebuild
    name = path.stem
    final = out_root / name
    tmp = out_root / f".{name}.partial"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        info = _run(path, tmp, models, cfg, c)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    from ..runner import _replace_dir

    _replace_dir(tmp, final)
    return info


def _run(path, out, models, cfg, c):
    T, t0 = {}, time.time()
    img = load_rgb(path)
    H, W = img.shape[:2]
    u8 = to_u8(img)
    log.info("  %dx%d  mode=rebuild", W, H)

    # ---------------------------------------------------------------- 1. text
    blocks, text_mask = [], np.zeros((H, W), bool)
    text_zone = np.zeros((H, W), bool)
    if c.text and models is not None:
        from .. import text as textmod

        blocks, blob_mask, _, glyphs = textmod.detect_text(img, models, np.zeros((H, W), np.float32),
                                                           _text_cfg(cfg), return_glyphs=True)
        def _is_text(b):
            t = str(b["text"]).strip()
            n = sum(ch.isalnum() for ch in t)
            # "No", "Hi" are words; "2", "7s", "$" read off icons are not
            return n >= c.text_min_chars or (n == 2 and t.isalpha() and b["confidence"] >= 0.9)

        keep = [b for b in blocks if _is_text(b)]
        for b in blocks:
            if b not in keep:
                log.info("  bukan teks (terlalu pendek, kemungkinan ikon): %r", b["text"])
        text_mask = blob_mask
        if c.text_mask_mode == "glyph":
            # only the letters themselves are removed: what shows between them (a stripe, a
            # panel edge) stays and is continued under the letters
            area = np.zeros((H, W), bool)
            shadow_area = np.zeros((H, W), bool)
            text_mask = np.zeros((H, W), bool)
            for b in keep:
                x, y, w, h = b["ocr_bbox"]
                p = int(round(cfg.text.pad_frac * h)) + 2
                box = np.zeros((H, W), bool)
                box[max(y - p, 0):y + h + p, max(x - p, 0):x + w + p] = True
                area |= box
                # letters + their drop shadow / glow (grows with the letter size), only when the
                # letters really have one: the band just outside differs from further out
                g = glyphs & box
                # thin rules on the same line ("—— TRAINING NOTES / 002") are graphics, not letters
                ncc, gcl, gst, _ = cv2.connectedComponentsWithStats(g.astype(np.uint8), connectivity=8)
                for j in range(1, ncc):
                    ww_, hh_ = gst[j, cv2.CC_STAT_WIDTH], gst[j, cv2.CC_STAT_HEIGHT]
                    if (ww_ >= 4 * hh_ and hh_ <= 0.3 * b["h"]) or (hh_ >= 4 * ww_ and ww_ <= 0.3 * b["h"] and hh_ > 1.5 * b["h"]):
                        g[gcl == j] = False
                r = int(c.text_glyph_dilate)
                rs = int(round(c.text_shadow_frac * b["h"]))
                if rs > 2 and g.any():
                    gray = u8.astype(np.float32).mean(-1)
                    d1 = matting.dilate(g, r + rs) & ~matting.dilate(g, r)
                    d2 = matting.dilate(g, r + 3 * rs) & ~matting.dilate(g, r + 2 * rs) & box
                    if d1.any() and d2.any() and abs(np.median(gray[d1]) - np.median(gray[d2])) > c.text_shadow_min:
                        r += rs
                        shadow_area |= box  # this block has a drop shadow / glow
                text_mask |= matting.dilate(g, r)
            # zone around the letters (their drop shadow / glow): nothing there but text
            text_zone = matting.dilate(blob_mask & shadow_area, int(c.text_zone_px)) & ~text_mask
        elif len(keep) != len(blocks):  # rebuild the mask from the kept blocks only
            text_mask = np.zeros((H, W), bool)
            for b in keep:
                text_mask |= _block_mask(img, b, cfg)
        if len(keep) != len(blocks):
            blocks = keep
            for i, b in enumerate(blocks, 1):
                b["id"] = i
        text_mask = matting.dilate(text_mask, int(c.text_extra_dilate))
        if c.text_reread and blocks:
            from . import textfix

            bv_path = Path(out).parent / "_brand_words.json"
            try:
                bv = json.loads(bv_path.read_text(encoding="utf-8")) if bv_path.exists() else {}
            except Exception:  # noqa: BLE001
                bv = {}
            blocks = textfix.reread(blocks, u8, glyphs, models, c, batch_vocab=bv)
            for b in blocks:  # remember this design's logo words for the next designs
                if b["y"] < c.text_logo_top * H and b["h"] < c.text_logo_max_h * H:
                    for tk in str(b["text"]).split():
                        if tk.isalpha() and len(tk) >= 4:
                            bv[tk.lower()] = bv.get(tk.lower(), 0) + 1
            try:
                bv_path.write_text(json.dumps(bv), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
    T["text"] = time.time() - t0

    # ---------------------------------------------------------------- 2. regions
    tcols = [((b["x"], b["y"], b["w"], b["h"]), np.array([int(b["color_hex"][i:i + 2], 16) for i in (1, 3, 5)]))
             for b in blocks]
    clean, own_paper = regions.remove_text(u8, text_mask, tcols)
    s = regions.smooth(clean, c)
    grad = regions.color_gradient(s)
    sf = s.astype(np.float32) / 255.0
    lab = regions.segment(s, grad, np.zeros((H, W), bool), c, no_seed=text_mask & ~own_paper,
                          text_colors=tcols if c.text_mask_mode != "glyph" else None)
    if c.merge_tol > 0:  # texture / banding: neighbours one gradient explains become one region
        from ..pentool import merge_pieces

        m_, _, _ = merge_pieces(sf, lab - 1, c.merge_tol, c.min_region_px, 10 ** 9, c.color_join,
                                max_both=c.merge_max_both * H * W)
        lab = m_ + 1
    lab = regions.relabel(regions.split_thin(lab, c))
    photo = regions.photo_from_regions(lab, sf, text_mask, c) if c.photos else np.zeros((H, W), bool)
    sal = None
    if photo.any() and c.photo_subject and models is not None:
        # the photo subject (athlete + what they hold: barbell, plates) is photo as a whole,
        # even its dark low-contrast parts
        try:
            sal = models.salient_mask(u8)
        except Exception as e:  # noqa: BLE001
            log.warning("  subject foto tidak bisa dipisah (%s)", e)
        if sal is not None:
            sm = sal > 0.5
            n_, cl_ = cv2.connectedComponents(sm.astype(np.uint8), connectivity=8)
            near = matting.dilate(photo, 5)
            hit = np.bincount(cl_[near & sm].ravel(), minlength=n_)
            size = np.bincount(cl_.ravel(), minlength=n_)
            keep = (hit >= 0.2 * size) & (np.arange(n_) > 0)
            add = keep[cl_] & ~photo & ~text_mask
            # design accents the matte grabbed too (the orange outline of a button): flat,
            # strongly coloured regions stay vector
            labc = cv2.cvtColor(s, cv2.COLOR_RGB2Lab).astype(np.float32)
            chroma_img = np.hypot(labc[..., 1] - 128, labc[..., 2] - 128)
            for rid in np.unique(lab[add]):
                if rid == 0:
                    continue
                rm = lab == rid
                px_ = sf[rm]
                flat = px_.std(0).max() < c.subject_flat_std
                if flat or (chroma_img[rm].mean() > c.subject_accent_chroma and px_.std(0).max() < 0.06) or \
                        shapes.is_line(rm, c):
                    add &= ~rm
            photo |= add
            photo = ndi.binary_fill_holes(photo)
    if photo.mean() >= c.photo_bg_takeover:
        # a photo design: big background areas that continue the photo (dim gym behind the
        # headline) are photo too, not a flat colour + a ghost in the effect layer
        took = 0
        ring_k = np.ones((5, 5), np.uint8)
        for rid, sl_, m_ in regions.region_masks(lab):
            area_ = m_.sum()
            if area_ < c.photo_bg_min_frac * H * W:
                continue
            full_ = np.zeros((H, W), bool)
            full_[sl_] = m_
            edge_ = cv2.dilate(full_.astype(np.uint8), ring_k).astype(bool) & ~full_
            contact = (edge_ & photo).sum() / max(edge_.sum(), 1)
            if contact >= c.photo_bg_contact:
                photo |= full_
                took += 1
        if took:
            photo = ndi.binary_fill_holes(photo)
            log.info("  %d bidang background ikut jadi foto (desain foto)", took)
    if photo.any():
        # UI on top of a photo (a button, a badge): a flat region with a clean geometric shape is
        # design, not photo, even where it sits on the photo
        freed = 0
        for rid, sl_, m_ in regions.region_masks(lab):
            if m_.sum() < c.photo_ui_min_px or not photo[sl_][m_].mean() > 0.5:
                continue
            sel_ = m_ & ~matting.dilate(text_mask, 3)[sl_]
            px_ = sf[sl_][sel_] if sel_.sum() > 50 else sf[sl_][m_]
            spread = (np.percentile(px_, 90, axis=0) - np.percentile(px_, 10, axis=0)).max()
            if spread >= c.photo_ui_flat:
                continue
            fm = ndi.binary_fill_holes(m_)
            kind = shapes.fit_shape(fm, c, allow_stroke=False)[0]
            if kind in ("rect", "ellipse", "polygon"):
                # with its border (a thin outline ring around the button)
                full_ = np.zeros((H, W), bool)
                full_[sl_] = fm
                photo &= ~matting.dilate(full_, int(c.photo_ui_border_px))
                freed += 1
        if freed:
            log.info("  %d bidang UI (tombol/badge) di atas foto tetap vektor", freed)
    if photo.mean() > c.photo_max_frac:  # (almost) all photo: nothing to vectorise but keep a base
        log.info("  hampir seluruh gambar adalah foto")
    lab[photo] = 0
    lab = regions.relabel(lab)
    valid = ~text_mask
    T["regions"] = time.time() - t0
    log.info("  %d bidang warna, foto %.0f%% kanvas", lab.max(), 100 * photo.mean())

    # ---------------------------------------------------------------- 3. fills + shapes
    R = []
    photo_d = matting.dilate(photo, 2)
    for rid, sl, m in regions.region_masks(lab):
        filled = ndi.binary_fill_holes(m) if c.fill_holes else m
        if photo.any():
            filled &= ~photo_d[sl] | m  # never cover a photo through a filled hole
        f = shapes.fit_fill(sf, sl, m, valid, W, H, c)
        R.append(dict(id=rid, sl=sl, m=m, filled=filled, area=int(m.sum()), farea=int(filled.sum()),
                      fill=f, border=_touches_border(sl, H, W)))
    R.sort(key=lambda r: -r["farea"])  # big below, small on top -> holes never show
    if not R:  # pure photo: a plain base colour under the photo layers
        bgc = np.median(img.reshape(-1, 3), 0)
        full = np.ones((H, W), bool)
        R.append(dict(id=0, sl=(slice(0, H), slice(0, W)), m=full, filled=full, area=H * W, farea=H * W,
                      fill=dict(kind="solid", color=bgc, rmse=0, median=bgc), border=True))
    base = R[0]
    for z, r in enumerate(R):
        r["z"] = z
        # the base is a background only when it is one (big); in a full-photo design the
        # biggest vector shape is just a shape (a button)
        is_bg = (r is base and (r["farea"] >= c.bg_min_frac * H * W or not photo.any())) or \
            (r["border"] and r["farea"] >= c.bg_min_frac * H * W)
        r["bg"] = is_bg
        if r is base and r["farea"] >= 0.5 * H * W:
            r["shape"] = ("canvas", {}, 1.0)
        else:
            r["shape"] = shapes.fit_shape(r["filled"], c, allow_stroke=not is_bg)
        r["line"] = (not is_bg) and shapes.is_line(r["filled"], c)
        if r["line"] and r["fill"]["kind"] != "solid":  # lines are drawn with one colour
            r["fill"] = dict(kind="solid", color=r["fill"]["median"], rmse=r["fill"]["rmse"])
    if photo.any():
        # small irregular bits right next to the photo are photo detail (equipment, lights in a
        # dark corner), not design shapes
        near = matting.dilate(photo, int(c.photo_absorb_dist))
        keep_r = []
        for r in R:
            col_ = r["fill"]["color"] if r["fill"]["kind"] == "solid" else r["fill"]["median"]
            lab_ = _lab(col_)
            dull = np.hypot(lab_[1], lab_[2]) < c.photo_dull_chroma  # grey / brown leftovers
            if (not r["bg"] and r["area"] < c.photo_absorb_px and r["shape"][0] in ("path", "polygon")
                    and not r.get("line") and (near[r["sl"]][r["m"]].mean() >= 0.3 or dull)):
                photo[r["sl"]] |= r["m"]
                lab[r["sl"]][r["m"]] = 0
            else:
                keep_r.append(r)
        if len(keep_r) != len(R):
            log.info("  %d serpihan kecil di tepi foto dikembalikan ke foto", len(R) - len(keep_r))
            R = keep_r
            for z, r in enumerate(R):
                r["z"] = z
    if c.rules:
        rules = shapes.thin_rules(u8, text_mask, H, W, c, photo)
        if rules:
            # regions that were only a piece of such a rule are replaced by it
            rm = np.zeros((H, W), bool)
            for q in rules:
                rm[q["sl"]] |= matting.dilate(q["m"], 2)
            R = [r for r in R if r["bg"] or rm[r["sl"]][r["m"]].mean() < 0.7] + rules
            for z, r in enumerate(R):
                r["z"] = z
            log.info("  %d garis tipis lurus", len(rules))
    palette = shapes.snap_palette([r["fill"] for r in R], [r["area"] for r in R], c.palette_tol)
    if c.bands and text_mask.any():
        R, nb = shapes.occluded_bands(R, text_mask, H, W, c, s, img)
        if nb:
            log.info("  %d pita/bidang di belakang teks disambung", nb)
    T["shapes"] = time.time() - t0
    kinds = {}
    for r in R:
        kinds[r["shape"][0]] = kinds.get(r["shape"][0], 0) + 1
    log.info("  bentuk: %s | palet %d warna", ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())), len(palette))

    # ---------------------------------------------------------------- 4. photos
    photos = []
    pimg = img
    if photo.any():
        # text printed on a photo is removed from it (it comes back as native text)
        ptxt = text_mask & photo
        if ptxt.any():
            if models is not None and c.photo_text_lama:
                pimg = models.inpaint(u8, (matting.dilate(ptxt, 3) * 255).astype(np.uint8)).astype(np.float32) / 255.0
            else:
                pimg = np.where(ptxt[..., None], clean.astype(np.float32) / 255.0, img)
        photos = package.photo_layers(pimg, photo, models if c.photo_subject else None, cfg, sal=sal)

    # stripes running behind the photo subject (the athlete) become vector stripes between the
    # photo background and the subject
    subj = next((p_["alpha"] for p_ in photos if p_["name"] == "photo_subject"), None)
    if c.photo_stripes and subj is not None and any(p_["name"] == "photo_background" for p_ in photos):
        R, ns = shapes.photo_stripes(R, s, img, (subj > 0.3) | text_mask, photo, H, W, c)
        if ns:
            log.info("  %d pita di belakang subject foto -> vektor", ns)
            # what stands IN FRONT of a stripe in the photo (rack posts, equipment) is cut out of
            # the photo as its own layer above the stripe, so the stripe can be a whole shape
            front = np.zeros((H, W), bool)
            stripe_area = np.zeros((H, W), bool)
            for r in R:
                if r.get("stripe") and r.get("ink") is not None:
                    full = np.zeros((H, W), bool)
                    full[r["sl"]] = r["m"]
                    stripe_area |= full
                    # faded / torn ink of the same stripe just past its clean edges and ends
                    stripe_area |= r["ink"] & matting.dilate(full, int(c.stripe_bg_reach_px))
                    front |= full & photo & ~r["ink"] & (subj < 0.5)
                    r.pop("ink")
            front = cv2.morphologyEx(front.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
            if front.sum() > 200:
                bgp = next(p_ for p_ in photos if p_["name"] == "photo_background")
                a_ = matting.feather(front.astype(np.float32), 0.7) * bgp["alpha"]
                photos.insert([p_["name"] for p_ in photos].index("photo_subject"),
                              dict(name="photo_front", rgb=bgp["rgb"], alpha=a_, where="top"))
            # the printed stripe is removed from the photo background: the vector stripe replaces
            # it, so recolouring the stripe leaves no orange behind
            if models is not None and stripe_area.any():
                bgp = next(p_ for p_ in photos if p_["name"] == "photo_background")
                # ONE inpaint of person + stripe from the original: a two-pass fill would copy the
                # stripe's orange into the person's hole
                hole = (matting.dilate(stripe_area, int(c.stripe_bg_clear_px)) |
                        matting.dilate(subj > c.subject_hole_thr, int(c.subject_hole_px))) & photo
                bgp["rgb"] = models.inpaint(to_u8(pimg), (hole * 255).astype(np.uint8)).astype(np.float32) / 255.0
                log.info("  pita lama dihapus dari foto background")

    # ---------------------------------------------------------------- 5. objects
    objects = group_objects(R, H, W, c, photo)
    log.info("  %d objek vektor", len(objects))

    # ---------------------------------------------------------------- 6. write + effects
    target = img if not c.fx_from_smoothed else np.where(photo[..., None], pimg if photo.any() else img, sf)
    info = package.write(out, path, img, W, H, R, objects, photos, blocks, text_mask, lab, c, target,
                         text_zone=text_zone & ~photo)
    T["total"] = time.time() - t0
    info["timing_s"] = {k: round(v, 1) for k, v in T.items()}
    (out / "manifest.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("  SSIM rebuild: %.3f (vektor saja %.3f) | %d layer | %.0f dtk",
             info["ssim"], info["ssim_vectors_only"], len(info["layers"]), T["total"])
    return info


def group_objects(R, H, W, c, photo=None):
    """One object = one Canva layer.
    - big shapes touching the canvas edge: background pieces (one layer each)
    - an object = a top-level shape + every shape lying ON it (contained in its outline)
    - top-level shapes that share a long edge are one object (book cover + pages)
    - long free lines (connectors) are their own layer, one layer per colour"""
    bgs = [r for r in R if r["bg"]]
    stripes = [r for r in R if r.get("stripe") and not r["bg"]]
    fg = [r for r in R if not r["bg"] and not r.get("stripe")]
    owner = np.zeros((H, W), np.int32)  # top-most filled shape per pixel so far (by z)
    parent = {}
    for r in fg:  # R is sorted big -> small
        sub = owner[r["sl"]][r["m"]]
        sub = sub[sub > 0]
        if len(sub):
            cand = np.bincount(sub)
            p = int(cand.argmax())
            if cand[p] >= c.contain_frac * r["area"]:
                parent[r["z"] + 1] = p
        o = owner[r["sl"]]
        o[r["filled"]] = r["z"] + 1

    def root(k):
        while k in parent:
            k = parent[k]
        return k

    byz = {r["z"] + 1: r for r in fg}
    # a free-standing patch with the background colour (a gap enclosed by lines) adds nothing
    base = R[0]
    if base["fill"]["kind"] == "solid" and base["shape"][0] == "canvas":
        bl = _lab(base["fill"]["color"])
        under = np.zeros((H, W), bool)  # anything between the base and the shapes
        for r in bgs[1:]:
            under[r["sl"]] |= r["filled"]
        if photo is not None:
            under |= matting.dilate(photo, 3)
        drop = [k for k, r in byz.items() if k not in parent and r["fill"]["kind"] == "solid"
                and np.linalg.norm(_lab(r["fill"]["color"]) - bl) < c.palette_tol * 1.5
                and not under[r["sl"]][r["filled"]].any()]
        for k in drop:
            del byz[k]
            for ch, pk in list(parent.items()):
                if pk == k:
                    del parent[ch]
    # candidates for "line" layers: thin & long, not a plain bar (bars stay shapes)
    cand = {k for k, r in byz.items() if k not in parent and r["line"] and (r["shape"][0] != "rect" or r.get("rule"))}
    tops = [k for k in byz if k not in parent]
    top_lab = np.zeros((H, W), np.int32)
    for k in sorted(tops):
        r = byz[k]
        t = top_lab[r["sl"]]
        t[r["filled"]] = k
    if c.group_gap_px > 0 and len(tops) > 1:  # shapes a hair apart (a thin outline) still touch
        dist, idx = ndi.distance_transform_edt(top_lab == 0, return_indices=True)
        grown = top_lab[idx[0], idx[1]]
        top_lab = np.where((top_lab == 0) & (dist <= c.group_gap_px), grown, top_lab)
    cnt, per = {}, {}
    for a_, b_ in ((top_lab[:, :-1], top_lab[:, 1:]), (top_lab[:-1, :], top_lab[1:, :])):
        m = a_ != b_
        for x in (a_[m], b_[m]):
            u, n = np.unique(x, return_counts=True)
            for uu, nn in zip(u, n):
                per[uu] = per.get(uu, 0) + nn
        pr = np.stack([a_[m], b_[m]], 1)
        pr = pr[(pr > 0).all(1)]
        pr.sort(1)
        if len(pr):
            u, n = np.unique(pr, axis=0, return_counts=True)
            for (x, y), nn in zip(u, n):
                cnt[(x, y)] = cnt.get((x, y), 0) + nn
    # a connector touches things only at its ends; a rim/outline hugs a shape along its length
    hug = {}
    for (x, y), nn in cnt.items():
        hug[x] = hug.get(x, 0) + nn
        hug[y] = hug.get(y, 0) + nn
    lset = {k for k in cand if byz[k].get("rule") or hug.get(k, 0) < c.line_max_contact * per.get(k, 1)}
    lines = [byz[k] for k in sorted(lset)]
    uf = {k: k for k in tops if k not in lset}

    def find(k):
        while uf[k] != k:
            uf[k] = uf[uf[k]]
            k = uf[k]
        return k

    if c.group_contact < 1:
        for (x, y), nn in sorted(cnt.items(), key=lambda t: -t[1]):
            if x in lset or y in lset:  # lines never glue things together
                continue
            if x in uf and y in uf and nn >= c.group_contact * min(per.get(x, 1), per.get(y, 1)):
                uf[find(y)] = find(x)
    groups = {}
    for k, r in byz.items():
        if k in lset:
            continue
        rt = root(k)
        if rt in lset:  # shape sitting on a line: belongs to that line
            continue
        groups.setdefault(find(rt), []).append(r)
    objs = [dict(kind="background" if (r is R[0] and r["farea"] >= 0.5 * H * W) else "bg_shape", regions=[r])
            for r in bgs]
    objs += [dict(kind="stripe", regions=[r]) for r in stripes]
    for rs in groups.values():
        x0 = min(r["sl"][1].start for r in rs)
        x1 = max(r["sl"][1].stop for r in rs)
        y0 = min(r["sl"][0].start for r in rs)
        y1 = max(r["sl"][0].stop for r in rs)
        frac = (x1 - x0) * (y1 - y0) / (W * H)
        kind = "shape" if len(rs) == 1 else ("icon" if frac < c.icon_max_frac else "graphic")
        objs.append(dict(kind=kind, regions=rs))
    if c.lines_by_color:
        by = {}
        for r in lines:
            by.setdefault(shapes.fill_attr(r["fill"], "x")[0], []).append(r)
        for rs in by.values():
            objs.append(dict(kind="lines", regions=rs))
    else:
        for r in lines:
            objs.append(dict(kind="line", regions=[r]))
    for o in objs:
        o["regions"].sort(key=lambda r: r["z"])
        o["z"] = min(r["z"] for r in o["regions"])
    objs.sort(key=lambda o: (o["kind"] not in ("background", "bg_shape"), o["z"]))
    return objs


def _lab(col):
    return cv2.cvtColor(np.asarray(col, np.float32)[None, None], cv2.COLOR_RGB2Lab)[0, 0]


def _stroke_len(r):
    p = r["shape"][1].get("pts")
    if p is None:
        return 0.0
    return float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())

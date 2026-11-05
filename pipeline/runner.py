"""Orchestrates all steps for one design."""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

import numpy as np

from . import background, composite, elements, foreground, gradients, graphic, pentool, vectorize, glow, grain, manifest, particles, stripe, subject, text
from . import matting
from .imageio import load_rgb, save_rgb

log = logging.getLogger("split")

DONE_MARKER = "manifest.json"


def _replace_dir(tmp: Path, final: Path) -> None:
    """Move the finished output into place. On Windows a folder that is open in Explorer (or a
    file previewed) cannot be deleted/renamed for a moment, so retry before giving up."""
    for attempt in range(10):
        try:
            if final.exists():
                shutil.rmtree(final)
            tmp.rename(final)
            return
        except PermissionError:
            time.sleep(1.0 + attempt)
    alt = final.with_name(final.name + "_baru")
    if alt.exists():
        shutil.rmtree(alt, ignore_errors=True)
    tmp.rename(alt)
    log.warning("folder %s sedang dipakai program lain; hasil disimpan di %s", final, alt)


def is_done(out_dir: Path) -> bool:
    return (out_dir / DONE_MARKER).exists()


def process(path: Path, out_root: Path, models, cfg) -> dict:
    tmp = out_root / f".{path.stem}.partial"
    try:
        return _process(path, out_root, models, cfg)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)  # never leave half-written output behind
        raise


def _process(path: Path, out_root: Path, models, cfg) -> dict:
    name = path.stem
    final = out_root / name
    tmp = out_root / f".{name}.partial"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    T = {}
    t0 = time.time()

    def tick(k):
        nonlocal t0
        T[k] = round(time.time() - t0, 1)
        t0 = time.time()
        if os.environ.get("BEDAH_MEMLOG"):
            import resource

            log.info("  [mem] setelah %s: puncak %.2f GB", k,
                     resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6)

    img = load_rgb(path)
    H, W = img.shape[:2]
    log.info("[%s] %dx%d", name, W, H)

    # 1. salient matte (subject + things attached to it)
    sal, raw = subject.salient_alpha(img, models, cfg)
    tick("matte")

    # 2. text + UI boxes (before depth: a CTA button glued to the subject must leave the matte)
    blocks, text_mask, ui = text.detect_text(img, models, sal, cfg)
    for u in ui:
        sal = sal * (1 - matting.dilate(u["mask"], 2).astype(np.float32))
    sal, raw = subject.sanitize_salient(sal, raw, text_mask, cfg)
    tick("ocr")

    # 3. foreground objects by depth
    fgs, fg_union = [], None
    if cfg.foreground.enabled:
        depth = models.depth((img * 255).astype(np.uint8))
        fgs, fg_union = foreground.find_foreground(img, sal, depth, cfg)
    tick("depth")

    # 3b. accent stripes behind the subject + 3c. dust cloud region (both removed in the
    #     SAME LaMa pass as the subject: one pass = no smudgy double-inpaint)
    stripes, stripe_vis = [], []
    occl = sal > 0.02
    if fg_union is not None:
        occl |= fg_union > 0.02
    occl |= text_mask  # text also sits on top of a stripe
    if cfg.stripe.enabled:
        stripes, acc_mask = stripe.find_stripes(img, sal, text_mask, fg_union, cfg)
        stripe_vis = [stripe.visible_mask(s_, acc_mask, occl, cfg) for s_ in stripes]
    cloud_soft = particles.cloud_region(img, models, cfg)
    tick("stripe+cloud")

    # 4. clean plate
    ui_mask = np.zeros_like(text_mask)
    for u in ui:
        ui_mask |= u["mask"]
    inp_mask = background.inpaint_mask(sal, raw, text_mask, fg_union, cfg, exclude=ui_mask)
    extra = np.zeros_like(inp_mask)
    for s_, v in zip(stripes, stripe_vis):
        extra |= matting.dilate(v, int(cfg.stripe.dilate_px))
        if cfg.stripe.mode in ("layered", "multiply", "canva"):  # whole band stripe-free in the bg
            extra |= matting.dilate(s_["rect"], int(cfg.stripe.dilate_px))
    if cloud_soft is not None:
        extra |= cloud_soft > 0.05
    inp_mask |= extra
    plate = background.clean_plate(img, inp_mask, models, cfg)
    keep = matting.dilate(text_mask, int(cfg.background.text_extra_dilate_px) + 2) | extra
    plate = background.fix_dark_smears(plate, inp_mask, cfg, img, text_mask)
    plate, restored = background.restore_original(plate, img, inp_mask, sal, raw, fg_union, keep, cfg)
    inp_mask &= ~restored
    if cfg.background.smooth_inpainted_px > 0:  # soften LaMa's patchwork, then regrain below
        r_ = int(cfg.background.smooth_inpainted_px)
        sm = np.stack([matting.guided_filter(plate, plate[..., i], r_, 1e-3) for i in range(3)], -1)
        w_ = matting.feather(inp_mask.astype(np.float32), 2.0)[..., None]
        plate = np.clip(plate * (1 - w_) + sm * w_, 0, 1).astype(np.float32)
    sigma = grain.estimate_noise(img, exclude=inp_mask)
    if cfg.background.regrain_inpainted:
        plate = grain.regrain(plate, inp_mask, sigma, cfg)
    tick("inpaint")

    # 5. subject + fg layers, edges re-matted against the plate
    subj_rgb, subj_a = subject.subject_layer(img, sal, fg_union, plate, cfg)
    fg_layers = [subject.edge_refine_object(img, o["alpha"], plate, cfg) for o in fgs]
    subj_rgb, subj_a, fg_layers = foreground.reassign_slivers(subj_rgb, subj_a, fg_layers, cfg)
    if cfg.foreground.merge_touching and fg_layers:  # held / attached objects stay one asset
        keep = []
        for rgb_f, a_f in fg_layers:
            if (matting.dilate(a_f > 0.5, 4) & (subj_a > 0.5)).sum() > 50:
                na = a_f + subj_a * (1 - a_f)
                subj_rgb = (rgb_f * a_f[..., None] + subj_rgb * (subj_a * (1 - a_f))[..., None]) / \
                    np.maximum(na, 1e-6)[..., None]
                subj_a = na.astype(np.float32)
                log.info("  foreground menempel ke subject -> digabung jadi satu asset")
            else:
                keep.append((rgb_f, a_f))
        fg_layers = keep
    tick("subject")

    # 6. glow (from plate, so subject/text never leak in)
    glow_rgb = glow_a = None
    ginfo = {}
    if cfg.glow.enabled:
        glow_rgb, glow_a, plate, ginfo = glow.extract_glow(img, plate, sal, cfg, models)

    # 7. particles (+ dust cloud, measured on the original against the clean plate)
    plate_pre = plate.copy()
    part_rgb = part_a = None
    n_blobs = 0
    if cfg.particles.enabled:
        part_rgb, part_a, plate, n_blobs = particles.extract_particles(
            plate, sal, text_mask, cfg, orig=img, cloud_soft=cloud_soft)

    # 7b. stripe layers, built on the FINAL plate so the stack reproduces the reference.
    #     Inside a stripe the particles overlay is cleared (the stripe grunge carries it).
    stripe_layers, shapes = [], []
    band = np.zeros(img.shape[:2], bool)
    for s_ in stripes:
        band |= matting.dilate(s_["rect"], 2)
    if band.any():
        plate = np.where(band[..., None], plate_pre, plate)
        if part_a is not None:
            part_a = part_a * ~band
    plate = np.round(np.clip(plate, 0, 1) * 255) / 255  # exactly what 01_background.png stores
    # everything that will sit ABOVE the stripe, flattened (subject, then fg objects)
    top_a = subj_a.copy()
    top_p = subj_rgb * subj_a[..., None]
    for rgb_f, a_f in fg_layers:
        top_p = top_p * (1 - a_f[..., None]) + rgb_f * a_f[..., None]
        top_a = top_a * (1 - a_f) + a_f
    top_rgb = top_p / np.maximum(top_a, 1e-6)[..., None]
    for k, (s_, v) in enumerate(zip(stripes, stripe_vis), 1):
        if cfg.stripe.mode in ("layered", "multiply", "canva"):
            build = {"multiply": stripe.build_multiply, "canva": stripe.build_canva,
                     "layered": stripe.build_layered}[cfg.stripe.mode]
            res = build(img, plate, s_, v, occl, models, cfg, top_rgb, top_a)
            if res is None:
                continue
            if "bg_under" in res:  # the scene seen THROUGH the stripe belongs to the background
                plate = np.where(res["bg_mask"][..., None], res["bg_under"], plate)
            stripe_layers.append((f"stripe_{k:02d}_base", f"04_stripe_{k:02d}_base.png",
                                  res["base_rgb"], res["base_a"]))
            if "depth_a" in res and cfg.pentool.effects_layer:  # one texture layer, not two
                da, ga = res["depth_a"][..., None], res["grunge_a"][..., None]
                ta = da + ga * (1 - da)
                # grunge is drawn on top of depth: over(depth, grunge)
                trgb = (res["depth_rgb"] * da * (1 - ga) + res["grunge_rgb"] * ga) / np.maximum(ta, 1e-6)
                stripe_layers.append((f"stripe_{k:02d}_texture", f"04_stripe_{k:02d}_texture.png",
                                      trgb.astype(np.float32), ta[..., 0].astype(np.float32)))
            else:
                if "depth_a" in res:
                    stripe_layers.append((f"stripe_{k:02d}_depth", f"04_stripe_{k:02d}_depth.png",
                                          res["depth_rgb"], res["depth_a"]))
                stripe_layers.append((f"stripe_{k:02d}_grunge", f"04_stripe_{k:02d}_grunge.png",
                                      res["grunge_rgb"], res["grunge_a"]))
            if "shade_a" in res and res["shade_a"].max() > 0:
                stripe_layers.append((f"stripe_{k:02d}_shade", f"04_stripe_{k:02d}_shade.png",
                                      res["shade_rgb"], res["shade_a"]))
            shapes.append({"id": k, "layer_file": f"04_stripe_{k:02d}_base.png",
                           "overlay_file": f"04_stripe_{k:02d}_grunge.png",
                           "depth_file": f"04_stripe_{k:02d}_depth.png" if "depth_a" in res else "",
                           "shade_file": f"04_stripe_{k:02d}_shade.png"
                           if "shade_a" in res and res["shade_a"].max() > 0 else "",
                           "blend_mode": "multiply" if cfg.stripe.mode == "multiply" else "normal",
                           **stripe.canva_geometry(s_, res["color"], res["opacity"])})
        else:
            rgb, a_, col = stripe.build_layer(img, plate, s_, v, occl, models, cfg)
            if rgb is None:
                continue
            stripe_layers.append((f"stripe_{k:02d}", f"04_stripe_{k:02d}.png", rgb, a_))
            shapes.append({"id": k, "layer_file": f"04_stripe_{k:02d}.png",
                           **stripe.canva_geometry(s_, col)})
    tick("overlays")

    # 8. grain overlay
    grain_rgb = grain_a = None
    if cfg.grain.enabled:
        grain_rgb, grain_a = grain.grain_overlay(plate, sigma, cfg)

    # ---- assemble layer list (z: bg 0, glow 1, subject 2, fg 3.., text, particles, grain)
    layers = [{"layer": "background", "file": "01_background.png", "type": "bg",
               "rgb": plate, "alpha": None, "z_order": 0}]
    z = 1
    if glow_a is not None:
        layers.append({"layer": "glow", "file": "04_glow.png", "type": "overlay",
                       "rgb": glow_rgb, "alpha": glow_a, "z_order": z})
        z += 1
    for lname, fname, rgb, a in stripe_layers:
        layers.append({"layer": lname, "file": fname,
                       "type": "overlay" if lname.endswith(("grunge", "shade", "depth", "texture")) else "shape",
                       "blend_mode": "multiply" if (cfg.stripe.mode == "multiply"
                                                    and lname.endswith("base")) else "normal",
                       "rgb": rgb, "alpha": a, "z_order": z})
        z += 1
    els = []
    if subj_a.max() > 0:  # graphic designs may have no separable subject
        predict = None
        if cfg.elements.enabled and cfg.elements.sam:
            try:
                predict = models.sam_session((img * 255).astype(np.uint8))
            except Exception as e:  # noqa: BLE001 - SAM is an improvement, never a blocker
                log.warning("  SAM tidak tersedia (%s), pakai pemecahan dasar", e)
        els = elements.split_elements(subj_rgb, subj_a, cfg, predict)
        if cfg.vectorize.enabled:  # magic-wand edges for flat/vector elements
            hards = [e["alpha"] > 0.5 for e in els]
            for i_, e in enumerate(els):
                if e["kind"] in ("shape", "vector_icon", "vector_large"):
                    others = np.zeros_like(hards[i_])
                    for j_, h_ in enumerate(hards):
                        if j_ != i_:
                            others |= h_
                    subj_rgb, e["alpha"] = vectorize.complete_with_sam(
                        predict, img, subj_rgb, e["alpha"], others, cfg)
                    a_ = vectorize.magic_wand_alpha(img, plate, e["alpha"], cfg)
                    e["alpha"] = np.where(others, e["alpha"], a_).astype(np.float32)
                    subj_rgb, e["alpha"] = vectorize.fill_enclosed_holes(img, subj_rgb, e["alpha"], cfg)
                    e["alpha"] = np.where(others & (e["alpha"] < 1), e["alpha"], e["alpha"])
                    subj_rgb = np.where((e["alpha"] > 0)[..., None] & (subj_a == 0)[..., None],
                                        img, subj_rgb)
        if len(els) == 1:
            layers.append({"layer": "subject", "file": "02_subject.png", "type": "subject",
                           "category": els[0]["kind"], "rgb": subj_rgb, "alpha": subj_a,
                           "z_order": z})
            z += 1
        else:
            for k, e in enumerate(els, 1):
                layers.append({"layer": f"element_{k:02d}_{e['kind']}",
                               "file": f"02_element_{k:02d}_{e['kind']}.png", "type": "subject",
                               "category": e["kind"], "rgb": subj_rgb, "alpha": e["alpha"],
                               "z_order": z})
                z += 1
            # the whole subject in one file, for convenience (not part of the stack)
            extra_dir = tmp / "extra"
            extra_dir.mkdir(exist_ok=True)
            from .imageio import save_rgba
            save_rgba(extra_dir / "02_subject_all.png", subj_rgb, subj_a)
    for i, (rgb, a) in enumerate(fg_layers, 1):
        layers.append({"layer": f"foreground_{i:02d}", "file": f"03_foreground_{i:02d}.png",
                       "type": "fg", "rgb": rgb, "alpha": a, "z_order": z})
        z += 1
    for i, u in enumerate(ui, 1):
        layers.append({"layer": f"ui_{i:02d} (box of text_{u['text_id']:02d})",
                       "file": f"07_ui_{i:02d}.png", "type": "ui",
                       "rgb": u["rgb"], "alpha": u["alpha"], "z_order": z})
        z += 1
    for b in blocks:
        layers.append({"layer": f"text_{b['id']:02d}: {b['text']}", "file": "", "type": "text",
                       "x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"], "z_order": z,
                       "suggested_opacity": 1.0, "crop_file": "", "rgb": None})
        z += 1
    if part_a is not None:
        layers.append({"layer": "particles", "file": "05_particles.png", "type": "overlay",
                       "rgb": part_rgb, "alpha": part_a, "z_order": z})
        z += 1
    if grain_a is not None:
        layers.append({"layer": "grain", "file": "06_grain.png", "type": "overlay",
                       "rgb": grain_rgb, "alpha": grain_a, "z_order": z,
                       "suggested_opacity": cfg.grain.suggested_opacity})
    for L in layers:
        L.setdefault("suggested_opacity", 1.0)

    piece_rows = []
    # graphic background -> editable gradient shapes + effects (photo designs keep the PNG)
    photo_design = bool(fg_layers) or any(L.get("category", "").startswith("asset") for L in layers)
    if cfg.gradients.enabled and photo_design:
        log.info("  gradien: desain foto -> background tetap PNG")
    elif cfg.gradients.enabled:
        ui_ex = np.zeros(plate.shape[:2], bool)
        for u in ui:
            ui_ex |= matting.dilate(u["mask"], 4)
        bg_pieces, fx, accents = graphic.decompose(plate, img, inp_mask, ui_ex, models, cfg)
        (tmp / "extra").mkdir(exist_ok=True)
        (tmp / "vectors").mkdir(exist_ok=True)
        save_rgb(tmp / "extra" / "01_background_flat.png", plate)
        new_layers = []
        for i_, (svg_, row_, rgb_, a_) in enumerate(bg_pieces, 1):
            fn = f"01_bg_{i_:02d}_{row_.get('fill', 'solid')}"
            (tmp / "vectors" / f"{fn}.svg").write_text(svg_, encoding="utf-8")
            new_layers.append({"layer": fn, "file": f"{fn}.png", "type": "bg" if i_ == 1 else "shape",
                               "category": "gradient" if row_.get("fill") == "gradient" else "shape",
                               "rgb": rgb_, "alpha": None if i_ == 1 else a_, "z_order": i_ - 1,
                               "svg_file": f"vectors/{fn}.svg", "pentool": True})
            piece_rows.append({"svg_file": f"vectors/{fn}.svg", **row_})
        for name_, rgb_, a_ in fx:
            new_layers.append({"layer": f"fx_{name_}", "file": f"01_fx_{name_}.png", "type": "overlay",
                               "category": "effect", "rgb": rgb_, "alpha": a_,
                               "z_order": len(new_layers), "suggested_opacity": 1.0})
        for j_, (svg_, hex_, rgb_, a_) in enumerate(accents, 1):
            fn = f"03_accent_{j_:02d}"
            (tmp / "vectors" / f"{fn}.svg").write_text(svg_, encoding="utf-8")
            new_layers.append({"layer": f"accent_{j_:02d} ({hex_})", "file": f"{fn}.png",
                               "type": "shape", "category": "shape", "rgb": rgb_, "alpha": a_,
                               "z_order": len(new_layers), "svg_file": f"vectors/{fn}.svg",
                               "pentool": True})
            piece_rows.append({"svg_file": f"vectors/{fn}.svg", "piece": 1, "fill": "solid",
                               "color1": hex_})
        for L in layers[1:]:
            L["z_order"] += len(new_layers)
        layers = new_layers + layers[1:]
    if cfg.vectorize.enabled:  # "pen tool": SVG for every flat / vector layer
        vec_cats = ("shape", "vector_icon", "vector_large")

        def _cat(L):
            return L.get("category") or manifest.CATEGORY.get(L["type"], "")

        def _a_in(L):
            return L["alpha"] * ~matting.dilate(text_mask, 2) if L["type"] == "subject" else L["alpha"]

        palette = None
        if cfg.pentool.enabled:  # one palette for the whole design -> consistent colours
            items = [(L["rgb"], _a_in(L) > 0.5) for L in layers
                     if L.get("alpha") is not None and L.get("file") and not L.get("pentool")
                     and _cat(L) in vec_cats and not L["layer"].endswith("_base")]
            if items:
                palette = pentool.design_palette(items, int(cfg.pentool.palette_colors),
                                                 cfg.pentool.palette_merge)
                log.info("  palet desain: %s", " ".join(pentool._hex(c_) for c_ in palette))
        out_layers = []
        for L in layers:
            if L.get("alpha") is None or not L.get("file") or L.get("pentool"):
                out_layers.append(L)
                continue
            cat = _cat(L)
            svg = Path("vectors") / (Path(L["file"]).stem + ".svg")
            if L["layer"].endswith("_base") and L["type"] == "shape":
                sh = next((s_ for s_ in shapes if s_.get("layer_file") == L["file"]), None)
                if sh:
                    vectorize.rect_svg(sh["corners"], [int(sh["color_hex"][i:i + 2], 16) / 255
                                                       for i in (1, 3, 5)],
                                       sh.get("canva_transparency_pct", 100) / 100, W, H, tmp / svg)
                    L["svg_file"] = svg.as_posix()
                out_layers.append(L)
            elif cat in vec_cats and cfg.pentool.enabled:
                objs = pentool.vectorize_objects(L["rgb"], _a_in(L), cfg, palette)
                if objs and max(o[5] for o in objs) > cfg.pentool.max_interior_err:
                    # a shaded vector shape (shadow, gradient badge): try again with gradients
                    objs = pentool.vectorize_objects(L["rgb"], _a_in(L), cfg, palette, True)
                if objs and max(o[5] for o in objs) > cfg.pentool.max_interior_err:
                    # needs more shades than the shared palette: own palette for this element
                    objs = pentool.vectorize_objects(L["rgb"], _a_in(L), cfg, None, True)
                if objs and max(o[5] for o in objs) > cfg.pentool.max_interior_err:
                    L["category"] = "asset_large"  # photographic -> stays PNG
                    log.info("  pen tool: %s terlalu foto -> tetap PNG", L["file"])
                    objs = []
                if not objs:
                    out_layers.append(L)
                    continue
                stem = Path(L["file"]).stem
                for oi, (svg_, rows_, rgb_, a_, iou_, _) in enumerate(objs, 1):
                    st_ = stem if len(objs) == 1 else f"{stem}_{oi:02d}"
                    sv = Path("vectors") / f"{st_}.svg"
                    (tmp / sv).parent.mkdir(parents=True, exist_ok=True)
                    (tmp / sv).write_text(svg_, encoding="utf-8")
                    ncol = len({r_["color1"] for r_ in rows_})
                    kind = L.get("category") or cat
                    if L["type"] == "subject" and len(objs) > 1:
                        kind = "vector_icon" if a_.mean() < 0.02 else kind
                        if ncol == 1 and all(r_["fill"] == "solid" for r_ in rows_):
                            kind = "shape"
                    out_layers.append({**L, "layer": f"{L['layer']}_{oi:02d}" if len(objs) > 1 else L["layer"],
                                       "file": f"{st_}.png", "rgb": rgb_, "alpha": a_,
                                       "svg_file": sv.as_posix(), "category": kind})
                    for rr in rows_:
                        piece_rows.append({"svg_file": sv.as_posix(), **rr})
                log.info("  pen tool: %s -> %d objek, %d potongan", stem, len(objs),
                         sum(len(o[1]) for o in objs))
            else:
                out_layers.append(L)
        layers = out_layers
    for i_, L in enumerate(sorted(layers, key=lambda L: L["z_order"])):
        L["z_order"] = i_  # unique, consecutive stacking order
    rows = manifest.write_layers(tmp, layers, cfg)
    manifest.write_text_csv(tmp, blocks)
    manifest.write_shapes_csv(tmp, shapes)
    manifest.write_pieces_csv(tmp, piece_rows)

    # ---- verification
    comp = composite.recomposite(layers)
    comp_ng = composite.recomposite([L for L in layers if L["layer"] != "grain"])
    save_rgb(tmp / "preview_recomposite.png", comp)
    save_rgb(tmp / "preview_diff.png", composite.diff_image(img, comp, cfg.output.diff_gain))
    s_all, s_notext = composite.ssim_scores(img, comp, text_mask)
    s_ng, s_ng_notext = composite.ssim_scores(img, comp_ng, text_mask)
    tick("write")

    meta = {
        "source": str(path.name), "width": W, "height": H, "device": models.device,
        "ssim": round(s_all, 4),
        "ssim_excluding_text": round(s_notext, 4),
        "ssim_without_grain": round(s_ng, 4),
        "ssim_without_grain_excluding_text": round(s_ng_notext, 4),
        "noise_sigma": round(sigma, 4),
        "accent": ginfo, "particle_blobs": n_blobs, "foreground_objects": len(fg_layers),
        "text_blocks": len(blocks), "ui_elements": len(ui), "stripes": shapes, "timings_s": T,
        "note": "Stack layers by z_order at x=0,y=0 (full-size files). Text is not an image: "
                "recreate rows of text.csv as native Canva text.",
    }
    manifest.write_manifest(tmp, rows, meta)
    _replace_dir(tmp, final)
    if cfg.output.get("contact_sheet", True):
        try:
            from .contact_sheet import build
            build(final, path, out_root / f"{name}_sheet.png")
        except Exception as e:  # noqa: BLE001 - a preview must never fail a design
            log.warning("  contact sheet gagal: %s", e)
    log.info("[%s] selesai: SSIM %.4f (tanpa teks %.4f, tanpa grain %.4f) | %s",
             name, s_all, s_notext, s_ng, T)
    return meta

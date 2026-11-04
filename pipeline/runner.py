"""Orchestrates all steps for one design."""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import numpy as np

from . import background, composite, foreground, glow, grain, manifest, particles, subject, text
from . import matting
from .imageio import load_rgb, save_rgb

log = logging.getLogger("split")

DONE_MARKER = "manifest.json"


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
    tick("ocr")

    # 3. foreground objects by depth
    fgs, fg_union = [], None
    if cfg.foreground.enabled:
        depth = models.depth((img * 255).astype(np.uint8))
        fgs, fg_union = foreground.find_foreground(img, sal, depth, cfg)
    tick("depth")

    # 4. clean plate
    ui_mask = np.zeros_like(text_mask)
    for u in ui:
        ui_mask |= u["mask"]
    inp_mask = background.inpaint_mask(sal, raw, text_mask, fg_union, cfg, exclude=ui_mask)
    plate = background.clean_plate(img, inp_mask, models, cfg)
    keep = matting.dilate(text_mask, int(cfg.background.text_extra_dilate_px) + 2)
    plate, restored = background.restore_original(plate, img, inp_mask, sal, raw, fg_union, keep, cfg)
    inp_mask &= ~restored
    sigma = grain.estimate_noise(img, exclude=inp_mask)
    if cfg.background.regrain_inpainted:
        plate = grain.regrain(plate, inp_mask, sigma, cfg)
    tick("inpaint")

    # 5. subject + fg layers, edges re-matted against the plate
    subj_rgb, subj_a = subject.subject_layer(img, sal, fg_union, plate, cfg)
    fg_layers = [subject.edge_refine_object(img, o["alpha"], plate, cfg) for o in fgs]
    subj_rgb, subj_a, fg_layers = foreground.reassign_slivers(subj_rgb, subj_a, fg_layers, cfg)
    tick("subject")

    # 6. glow (from plate, so subject/text never leak in)
    glow_rgb = glow_a = None
    ginfo = {}
    if cfg.glow.enabled:
        glow_rgb, glow_a, plate, ginfo = glow.extract_glow(img, plate, sal, cfg, models)

    # 7. particles
    part_rgb = part_a = None
    n_blobs = 0
    if cfg.particles.enabled:
        part_rgb, part_a, plate, n_blobs = particles.extract_particles(plate, sal, text_mask, cfg, models)
    tick("overlays")

    # 8. grain overlay
    grain_rgb = grain_a = None
    if cfg.grain.enabled:
        grain_rgb, grain_a = grain.grain_overlay(img, sigma, cfg)

    # ---- assemble layer list (z: bg 0, glow 1, subject 2, fg 3.., text, particles, grain)
    layers = [{"layer": "background", "file": "01_background.png", "type": "bg",
               "rgb": plate, "alpha": None, "z_order": 0}]
    z = 1
    if glow_a is not None:
        layers.append({"layer": "glow", "file": "04_glow.png", "type": "overlay",
                       "rgb": glow_rgb, "alpha": glow_a, "z_order": z})
        z += 1
    layers.append({"layer": "subject", "file": "02_subject.png", "type": "subject",
                   "rgb": subj_rgb, "alpha": subj_a, "z_order": z})
    z += 1
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

    rows = manifest.write_layers(tmp, layers, cfg)
    manifest.write_text_csv(tmp, blocks)

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
        "text_blocks": len(blocks), "ui_elements": len(ui), "timings_s": T,
        "note": "Stack layers by z_order at x=0,y=0 (full-size files). Text is not an image: "
                "recreate rows of text.csv as native Canva text.",
    }
    manifest.write_manifest(tmp, rows, meta)
    if final.exists():
        shutil.rmtree(final)
    tmp.rename(final)
    log.info("[%s] selesai: SSIM %.4f (tanpa teks %.4f, tanpa grain %.4f) | %s",
             name, s_all, s_notext, s_ng, T)
    return meta

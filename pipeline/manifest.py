"""Step: write layer PNGs, crops, manifest.csv/json and text.csv."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .imageio import bbox, save_rgb, save_rgba

FIELDS = ["layer", "file", "type", "blend_mode", "x", "y", "w", "h", "z_order", "suggested_opacity",
          "crop_file"]


def write_layers(out: Path, layers, cfg):
    crops = out / "crops"
    crops.mkdir(parents=True, exist_ok=True)
    thr = cfg.output.crop_alpha_threshold
    rows = []
    for L in layers:
        if L["type"] == "text":
            rows.append({k: L.get(k, "") for k in FIELDS})
            continue
        f = out / L["file"]
        if L["alpha"] is None:
            save_rgb(f, L["rgb"])
            h, w = L["rgb"].shape[:2]
            x, y = 0, 0
            crop_file = ""
        else:
            save_rgba(f, L["rgb"], L["alpha"])
            bb = bbox(L["alpha"], thr) or (0, 0, 0, 0)
            x, y, w, h = bb
            crop_file = f"crops/{f.stem}_crop.png"
            if w and h:
                save_rgba(out / crop_file, L["rgb"][y:y + h, x:x + w], L["alpha"][y:y + h, x:x + w])
        rows.append({"layer": L["layer"], "file": L["file"], "type": L["type"],
                     "blend_mode": L.get("blend_mode", "normal"), "x": x, "y": y,
                     "w": w, "h": h, "z_order": L["z_order"],
                     "suggested_opacity": L.get("suggested_opacity", 1.0),
                     "crop_file": crop_file})
    rows.sort(key=lambda r: r["z_order"])
    return rows


def write_manifest(out: Path, rows, meta: dict):
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    with open(out / "manifest.json", "w", encoding="utf-8") as f:
        json.dump({**meta, "layers": rows}, f, indent=2, ensure_ascii=False)


def write_text_csv(out: Path, blocks):
    fields = ["id", "text", "confidence", "x", "y", "w", "h", "color_hex", "est_font_size_px",
              "glyph_height_px", "is_upper", "angle_deg", "ocr_bbox", "mask_method",
              "box_x", "box_y", "box_w", "box_h", "box_fill_hex", "box_border_hex"]
    with open(out / "text.csv", "w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel-friendly
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for b in blocks:
            w.writerow({k: b.get(k, "") for k in fields})


def write_shapes_csv(out: Path, shapes):
    """Geometry of graphic shapes (stripes) to rebuild them natively in Canva."""
    if not shapes:
        return
    fields = ["id", "layer_file", "depth_file", "overlay_file", "shade_file", "blend_mode", "shape", "canva_x", "canva_y", "canva_w",
              "canva_h", "canva_rotation_deg", "color_hex", "canva_transparency_pct", "cx", "cy",
              "corners"]
    with open(out / "shapes.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in shapes:
            w.writerow({k: s.get(k, "") for k in fields})

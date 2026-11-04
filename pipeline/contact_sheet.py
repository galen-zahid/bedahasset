"""Contact sheet of one processed design: every layer of the output folder on one page.

    python tools/contact_sheet.py out/<design> [original.png] [-o sheet.png]
    python tools/contact_sheet.py out            # every design in out/ -> out/<design>_sheet.png

Transparent layers are shown on a checkerboard; overlays on black; SVG files (vectors/) are
rasterized with a minimal path renderer (M/L/Z, even-odd) so no extra dependency is needed.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TILE_W = 260


def _font(size):
    for p in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _checker(w, h):
    a = np.indices((h, w)).sum(0) // 10 % 2
    return Image.fromarray(np.where(a[..., None], 205, 160).astype(np.uint8).repeat(3, 2))


def _on(im: Image.Image, bg="checker"):
    im = im.convert("RGBA")
    base = _checker(*im.size).convert("RGBA") if bg == "checker" else Image.new("RGBA", im.size, bg)
    base.alpha_composite(im)
    return base.convert("RGB")


def render_svg(path: Path) -> Image.Image:
    try:  # full SVG renderer (gradients, Bezier curves, transforms)
        import io

        import resvg_py

        return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_path=str(path))))).convert("RGBA")
    except ImportError:
        pass
    s = path.read_text(encoding="utf-8")
    W = int(re.search(r'width="(\d+)"', s).group(1))
    H = int(re.search(r'height="(\d+)"', s).group(1))
    out = np.zeros((H, W, 4), np.uint8)
    for m in re.finditer(r'<path fill="#([0-9a-fA-F]{6})"(?: fill-opacity="([\d.]+)")?[^>]*d="([^"]+)"', s):
        col = [int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)]
        op = float(m.group(2) or 1)
        mask = np.zeros((H, W), np.uint8)
        for sub in m.group(3).split("M")[1:]:
            pts = np.array([[float(v) for v in p.split()] for p in sub.replace("Z", "").split("L")
                            if p.strip()], np.float32)
            layer = np.zeros((H, W), np.uint8)
            cv2.fillPoly(layer, [np.round(pts).astype(np.int32)], 1)
            mask ^= layer  # even-odd
        a = (mask * 255 * op).astype(np.uint8)
        sel = a > 0
        out[sel, :3] = col
        out[sel, 3] = np.maximum(out[sel, 3], a[sel])
    return Image.fromarray(out, "RGBA")


def build(d: Path, original: Path | None, dst: Path):
    rows = list(csv.DictReader(open(d / "manifest.csv", encoding="utf-8")))
    tiles = []
    if original and original.exists():
        tiles.append(("ORIGINAL", Image.open(original).convert("RGB"), "referensi"))
    tiles.append(("preview_recomposite", Image.open(d / "preview_recomposite.png").convert("RGB"),
                  "semua layer (tanpa teks)"))
    for r in sorted(rows, key=lambda r: int(r["z_order"])):
        if not r["file"]:
            continue
        im = Image.open(d / r["file"])
        bg = (0, 0, 0, 255) if r["layer"].startswith(("particles", "grain")) else "checker"
        if r["type"] == "bg":
            bg = None
        sub = f'{r["category"]}  z={r["z_order"]}' + (f'  op={r["suggested_opacity"]}'
                                                       if r["suggested_opacity"] != "1.0" else "")
        tiles.append((r["file"], im.convert("RGB") if bg is None else _on(im, bg), sub))
    vec = sorted((d / "vectors").glob("*.svg")) if (d / "vectors").exists() else []
    if vec:
        size = tiles[-1][1].size
        acc = Image.new("RGBA", size, (255, 255, 255, 255))
        for v in vec:
            if "background_gradients" in v.name:
                tiles.append(("vectors/01_background_gradients.svg",
                              render_svg(v).convert("RGB").resize(size), "bidang gradien (SVG)"))
                continue
            im = render_svg(v)
            if im.size != size:
                im = im.resize(size)
            acc.alpha_composite(im)
        tiles.append((f"vectors/*.svg ({len(vec)})", acc.convert("RGB"),
                      "semua SVG elemen di atas putih"))
    W0, H0 = tiles[0][1].size
    th = int(H0 * TILE_W / W0)
    cols = 6
    nrows = (len(tiles) + cols - 1) // cols
    f1, f2 = _font(13), _font(11)
    texts = []
    tpath = d / "text.csv"
    if tpath.exists():
        for t in csv.DictReader(open(tpath, encoding="utf-8-sig")):
            texts.append(f'{t["text"]}   {t["color_hex"]}  ~{t["est_font_size_px"] or "-"}px  @({t["x"]},{t["y"]})')
    text_h = 22 + 15 * len(texts)
    sheet = Image.new("RGB", (cols * TILE_W, 34 + nrows * (th + 34) + text_h), (18, 18, 18))
    dr = ImageDraw.Draw(sheet)
    dr.text((8, 8), f"{d.name}   ({len(tiles)} panel)", fill=(255, 220, 120), font=_font(16))
    for i, (name, im, sub) in enumerate(tiles):
        x, y = (i % cols) * TILE_W, 34 + (i // cols) * (th + 34)
        sheet.paste(im.resize((TILE_W - 6, th - 6 * th // TILE_W)), (x + 3, y + 30))
        dr.text((x + 4, y + 1), name[:38], fill=(240, 240, 240), font=f1)
        dr.text((x + 4, y + 16), sub[:42], fill=(150, 200, 255), font=f2)
    y = 34 + nrows * (th + 34)
    dr.text((8, y), "TEKS (text.csv, dibuat ulang sebagai teks native):", fill=(255, 220, 120), font=f1)
    for k, t in enumerate(texts):
        dr.text((8, y + 18 + 15 * k), t[:170], fill=(220, 220, 220), font=f2)
    sheet.save(dst)
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("original", type=Path, nargs="?")
    ap.add_argument("-o", "--out", type=Path)
    a = ap.parse_args(argv)
    if (a.folder / "manifest.csv").exists():
        print(build(a.folder, a.original, a.out or a.folder.with_name(a.folder.name + "_sheet.png")))
        return 0
    for d in sorted(p for p in a.folder.iterdir() if (p / "manifest.csv").exists()):
        print(build(d, None, a.folder / f"{d.name}_sheet.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

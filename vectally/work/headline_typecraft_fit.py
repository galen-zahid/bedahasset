"""Fit headline S01-S04 ke instance font brand untuk TypeCraft.

League Gothic (wdth) dan Archivo (wdth, wght, italic + shear tambahan) — keluarga
font brand yang sama, dibuat instance statis karena bentuk sumber tidak natural.
Skala hanya proporsional (tanpa stretch), jadi hasilnya bisa dipasang via TypeCraft
lalu di-resize proporsional di Canva. Output: outputs/VECTALLY-hybrid/HEADLINE-TYPECRAFT-FIT.json
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import s01_s05_display_fit as F  # noqa: E402

ROOT = F.ROOT
LG = ROOT / "outputs/VECTALLY-teks-native/fonts/leaguegothic-LeagueGothic[wdth].ttf"
AR = ROOT / "outputs/VECTALLY-hybrid/archivo-variable/Archivo[wdth,wght].ttf"
ARI = ROOT / "outputs/VECTALLY-hybrid/archivo-variable/Archivo-Italic[wdth,wght].ttf"
OUT = ROOT / "outputs/VECTALLY-hybrid/HEADLINE-TYPECRAFT-FIT.json"
BASE = 200

# (code, text, family)
WORDS = [
    ("S01", "THE BOOKS", "lg"), ("S01", "STORY.", "lg"),
    ("S02", "WHAT'S", "ar"), ("S02", "HARDER", "ar"), ("S02", "TO", "ar"), ("S02", "TRACK?", "ar"),
    ("S03", "WHICH", "ari"), ("S03", "REPORT", "ari"), ("S03", "SHOWS", "ari"), ("S03", "PROFIT?", "ari"),
    ("S04", "IT'S THE", "ar"), ("S04", "PROFIT &", "ar"), ("S04", "LOSS.", "ar"),
]


def font(path, axes, size=BASE):
    f = ImageFont.truetype(str(path), size)
    f.set_variation_by_axes(axes)
    return f


def render(f, text, ls, shear, angle):
    w = int(f.getlength(text) + abs(ls) * BASE * len(text) + BASE * 2)
    img = Image.new("L", (w, BASE * 3), 0)
    d = ImageDraw.Draw(img)
    x = BASE
    for ch in text:
        d.text((x, BASE), ch, font=f, fill=255)
        x += f.getlength(ch) + ls * BASE
    if shear:
        img = img.transform(img.size, Image.AFFINE, (1, shear, -shear * img.size[1] / 2, 0, 1, 0), Image.BILINEAR)
    if angle:
        img = img.rotate(angle, expand=True, resample=Image.BILINEAR)
    m = np.array(img) > 127
    g, _ = F.crop(m)
    return g


def score(glyph, target):
    th, tw = target.shape
    gh, gw = glyph.shape
    s = th / gh
    small = np.array(Image.fromarray(glyph).resize((max(1, int(gw * s)), th), Image.BILINEAR)) > 0
    return F.iou(small, target), small.shape[1] / tw


def target_for(code, text, cache):
    item = next(i for i in F.ITEMS if i[0] == code and i[1] == text)
    if code not in cache:
        cache[code] = np.array(Image.open(glob.glob(str(ROOT / f"sources/VECTALLY/Story/*{code}_*"))[0]).convert("RGB"))
    m = F.source_mask(cache[code], item[2], item[3])
    t, box = F.crop(m)
    half = np.array(Image.fromarray(t).resize((max(1, t.shape[1] // 2), max(1, t.shape[0] // 2)), Image.BILINEAR)) > 0
    return half, [int(v) for v in box]


def grid(fam):
    if fam == "lg":
        for wd in (75, 77, 79, 81, 84, 88):
            yield (LG, [wd]), {"wdth": wd}, 0
    else:
        path = ARI if fam == "ari" else AR
        shears = (0, 0.06, 0.12, 0.18) if fam == "ari" else (0,)
        for wd in (62, 66, 70, 75, 80, 87, 95):
            for wg in (800, 900):
                for sh in shears:
                    # Archivo variable axes order: wght, wdth
                    yield (path, [wg, wd]), {"wdth": wd, "wght": wg, "extraShear": sh}, sh


def main():
    cache, rows = {}, []
    for code, text, fam in WORDS:
        target, box = target_for(code, text, cache)
        best = None
        angles = (0, 2, 4, 6, 8, 10) if fam == "ari" else (0,)
        for (path, axes), params, sh in grid(fam):
            f = font(path, axes)
            for ls in (-0.03, -0.015, 0, 0.015, 0.03):
                for ang in angles:
                    g = render(f, text, ls, sh, ang)
                    iou, wr = score(g, target)
                    if best is None or iou > best["iou"]:
                        best = {"iou": round(float(iou), 3), "widthRatio": round(float(wr), 3), "ls": ls, "angleCcw": ang, **params}
        rows.append({"code": code, "text": text, "family": fam, "inkBox": box, "best": best})
        print(code, text.ljust(10), best, flush=True)
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

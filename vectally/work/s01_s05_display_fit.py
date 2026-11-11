"""Fit lokal kandidat font untuk display copy S01-S05.

Membaca sumber PNG, mengambil komponen tinta per ROI, lalu mencari font,
sudut, letter spacing, dan ukuran. Tidak menulis paket dan tidak menyentuh Canva.
Skor IoU hanya alat pilih kandidat, bukan bukti fidelity akhir.
"""
import glob
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "outputs/VECTALLY-teks-native/fonts"
OUT = ROOT / "outputs/VECTALLY-story-repair/DISPLAY-FIT.json"
K = 941 / 380
LIGHT, DARK = (244, 247, 250), (9, 21, 34)

ITEMS = [
    ("S01", "THE BOOKS", (18, 82, 270, 180), LIGHT, 0),
    ("S01", "STORY.", (155, 497, 366, 625), LIGHT, 0),
    ("S02", "WHAT'S", (183, 55, 368, 108), DARK, 0),
    ("S02", "HARDER", (173, 110, 368, 163), DARK, 0),
    ("S02", "TO", (18, 452, 92, 505), DARK, 0),
    ("S02", "TRACK?", (18, 506, 208, 560), DARK, 0),
    ("S03", "VECTALLY", (22, 20, 135, 42), DARK, 0),
    ("S03", "WHICH", (25, 75, 165, 122), DARK, 0),
    ("S03", "REPORT", (22, 110, 208, 165), DARK, 0),
    ("S03", "SHOWS", (135, 140, 368, 240), DARK, 0),
    ("S03", "PROFIT?", (12, 435, 368, 552), DARK, 0),
    ("S03", "OR", (165, 320, 205, 348), DARK, 0),
    ("S04", "VECTALLY", (22, 20, 165, 48), DARK, 0),
    ("S04", "IT'S THE", (20, 85, 150, 118), DARK, 0),
    ("S04", "PROFIT &", (95, 140, 370, 208), DARK, 0),
    ("S04", "LOSS.", (15, 418, 375, 537), DARK, 0),
    ("S05", "VECTALLY", (25, 28, 148, 60), DARK, 0),
    ("S05", "GOT A", (15, 108, 150, 147), DARK, 0),
    ("S05", "BOOKKEEPING", (5, 160, 66, 455), DARK, 90),
    ("S05", "QUESTION?", (112, 500, 372, 563), DARK, 0),
]


def var(path, axes):
    def make(size):
        f = ImageFont.truetype(str(path), size)
        f.set_variation_by_axes(axes)
        return f
    return make


def plain(path):
    return lambda size: ImageFont.truetype(str(path), size)


CANDS = {
    "League Gothic": var(FONTS / "leaguegothic-LeagueGothic[wdth].ttf", [100]),
    "Archivo Black": plain(FONTS / "archivoblack-ArchivoBlack-Regular.ttf"),
    "Asap bold": var(FONTS / "asap-Asap[wdth,wght].ttf", [700, 100]),
    "Asap bold italic": var(FONTS / "asap-Asap-Italic[wdth,wght].ttf", [700, 100]),
    "Asap Condensed bold": var(FONTS / "asap-Asap[wdth,wght].ttf", [700, 75]),
}
BASE = 160


def render(make, text, ls):
    font = make(BASE)
    pad = BASE
    width = int(font.getlength(text) + abs(ls) * BASE * len(text) + pad * 2)
    img = Image.new("L", (width, BASE * 3), 0)
    draw = ImageDraw.Draw(img)
    for i, ch in enumerate(text):
        x = pad + font.getlength(text[:i]) + ls * BASE * i
        draw.text((x, BASE), ch, font=font, fill=255)
    return img


def crop(mask):
    ys, xs = np.where(mask)
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1], (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def source_mask(rgb, roi, color):
    dist = np.abs(rgb.astype(int) - np.array(color)).sum(axis=2)
    ink = dist < 110
    lab, count = ndi.label(ink)
    x0, y0, x1, y1 = [int(v * K) for v in roi]
    keep = np.zeros_like(ink)
    for i, (sl, cm) in enumerate(zip(ndi.find_objects(lab), ndi.center_of_mass(ink, lab, range(1, count + 1))), 1):
        area = (lab[sl] == i).sum()
        if area > 12 and x0 <= cm[1] <= x1 and y0 <= cm[0] <= y1:
            keep[sl] |= lab[sl] == i
    return keep


def iou(a, b):
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
    pa, pb = np.zeros((h, w), bool), np.zeros((h, w), bool)
    pa[(h - a.shape[0]) // 2:(h - a.shape[0]) // 2 + a.shape[0], (w - a.shape[1]) // 2:(w - a.shape[1]) // 2 + a.shape[1]] = a
    pb[(h - b.shape[0]) // 2:(h - b.shape[0]) // 2 + b.shape[0], (w - b.shape[1]) // 2:(w - b.shape[1]) // 2 + b.shape[1]] = b
    return (pa & pb).sum() / max(1, (pa | pb).sum())


def fit(target, text, base_angle):
    th, tw = target.shape
    results = {}
    for name, make in CANDS.items():
        best = None
        for ls in (-0.04, -0.02, 0, 0.02, 0.04):
            base = render(make, text, ls)
            for delta in range(-12, 13):
                angle = base_angle + delta
                rot = np.array(base.rotate(angle, expand=True, resample=Image.BILINEAR)) > 127
                glyph, _ = crop(rot)
                gh, gw = glyph.shape
                for scale in {th / gh, tw / gw, (th / gh + tw / gw) / 2}:
                    size = (max(1, int(gw * scale)), max(1, int(gh * scale)))
                    small = np.array(Image.fromarray(glyph).resize(size, Image.BILINEAR)) > 0
                    score = iou(small, target)
                    if best is None or score > best["iou"]:
                        best = {"iou": round(float(score), 4), "angleCcw": angle, "ls": ls, "fontSize": round(BASE * scale * 2, 1), "wRatio": round(gw * scale * 2 / (tw * 2), 3), "hRatio": round(gh * scale * 2 / (th * 2), 3)}
        results[name] = best
    return results


def main():
    report, cache = [], {}
    for code, text, roi, color, angle in ITEMS:
        if code not in cache:
            path = glob.glob(str(ROOT / f"sources/VECTALLY/Story/*{code}_*"))[0]
            cache[code] = np.array(Image.open(path).convert("RGB"))
        mask = source_mask(cache[code], roi, color)
        if not mask.any():
            report.append({"code": code, "text": text, "error": "no ink"})
            print(code, text, "NO INK")
            continue
        target, box = crop(mask)
        half = np.array(Image.fromarray(target).resize((max(1, target.shape[1] // 2), max(1, target.shape[0] // 2)), Image.BILINEAR)) > 0
        fits = fit(half, text, angle)
        ranked = sorted(fits.items(), key=lambda kv: -kv[1]["iou"])
        report.append({"code": code, "text": text, "inkBox": [int(v) for v in box], "fits": fits})
        print(code, text.ljust(12), box, " | ".join(f"{k} {v['iou']:.3f} a{v['angleCcw']} ls{v['ls']} s{v['fontSize']}" for k, v in ranked[:3]))
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("saved", OUT)


if __name__ == "__main__":
    main()

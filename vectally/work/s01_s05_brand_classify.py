"""Klasifikasi headline S01-S05 memakai font brand saja.

Font: League Gothic dan Archivo Black. Glyph dipaskan ke kotak tinta sumber,
sehingga rasio lebar dan kemiringan yang dibutuhkan terbaca. Rasio mendekati 1
tanpa kemiringan berarti bisa native; selain itu kandidat TypeCraft.
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import s01_s05_display_fit as F  # noqa: E402

BRAND = {"League Gothic": F.CANDS["League Gothic"], "Archivo Black": F.CANDS["Archivo Black"]}
EXTRA = [("S03", "WHICH"), ("S03", "REPORT"), ("S03", "SHOWS"), ("S03", "PROFIT?")]
SKIP = {"VECTALLY", "OR"}
SHEARS = (0, 0.08, 0.14, 0.2, 0.26, 0.32)
OUT = F.ROOT / "outputs/VECTALLY-story-repair/BRAND-CLASSIFY.json"


def best(target, text, base):
    th, tw = target.shape
    res = {}
    for name, make in BRAND.items():
        glyph0 = F.render(make, text, 0)
        top = None
        for shear in SHEARS:
            img = glyph0.transform(glyph0.size, Image.AFFINE, (1, shear, -shear * glyph0.size[1] / 2, 0, 1, 0), Image.BILINEAR) if shear else glyph0
            for delta in range(-12, 13, 2):
                angle = base + delta
                glyph, _ = F.crop(np.array(img.rotate(angle, expand=True, resample=Image.BILINEAR)) > 127)
                gh, gw = glyph.shape
                small = np.array(Image.fromarray(glyph).resize((tw, th), Image.BILINEAR)) > 0
                score = float((small & target).sum() / max(1, (small | target).sum()))
                if top is None or score > top["iou"]:
                    top = {"iou": round(score, 3), "shear": shear, "angleCcw": angle, "xRatio": round((tw / gw) / (th / gh), 3)}
        res[name] = top
    return res


def main():
    rows, cache = [], {}
    for code, text, roi, color, angle in F.ITEMS:
        if text in SKIP:
            continue
        if code not in cache:
            cache[code] = np.array(Image.open(glob.glob(str(F.ROOT / f"sources/VECTALLY/Story/*{code}_*"))[0]).convert("RGB"))
        mask = F.source_mask(cache[code], roi, color)
        if not mask.any():
            continue
        target, box = F.crop(mask)
        half = np.array(Image.fromarray(target).resize((max(1, target.shape[1] // 2), max(1, target.shape[0] // 2)), Image.BILINEAR)) > 0
        fits = best(half, text, angle)
        rows.append({"code": code, "text": text, "inkBox": [int(v) for v in box], "fits": fits})
        print(code, text.ljust(12), " | ".join(f"{k[:7]} iou {v['iou']} x{v['xRatio']} sh{v['shear']} a{v['angleCcw']}" for k, v in fits.items()), flush=True)
    OUT.write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

"""Buat instance statis Archivo untuk headline TypeCraft S02-S04 (OFL, tanpa RFN).

Shear tambahan dibakar ke outline (miring dari baseline), nama font unik supaya
tidak bentrok dengan Archivo asli di Canva.
"""
from pathlib import Path

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "outputs/VECTALLY-hybrid/archivo-variable"
OUT = ROOT / "outputs/VECTALLY-hybrid/headline-fonts"
OUT.mkdir(exist_ok=True)

SPECS = [
    # family, italic, wdth, wght, extra shear
    ("Archivo VX W66 800", False, 66, 800, 0.0),     # S02
    ("Archivo VX W87 800", False, 87, 800, 0.0),     # S04 IT'S THE
    ("Archivo VX W62 800", False, 62, 800, 0.0),     # S04 PROFIT &
    ("Archivo VX W66 900", False, 66, 900, 0.0),     # S04 LOSS.
    ("Archivo VX Slant W84 800", True, 84, 800, 0.12),  # S03 WHICH/REPORT
    ("Archivo VX Slant W64 900", True, 64, 900, 0.18),  # S03 SHOWS/PROFIT?
]


def shear_font(f, k):
    gs = f.getGlyphSet()
    glyf = f["glyf"]
    for name in f.getGlyphOrder():
        rec = DecomposingRecordingPen(gs)
        gs[name].draw(rec)
        pen = TTGlyphPen(None)
        rec.replay(TransformPen(pen, (1, 0, k, 1, 0, 0)))
        g = pen.glyph()
        g.recalcBounds(glyf)
        glyf[name] = g
    f["post"].italicAngle = f["post"].italicAngle - round(k * 57.3, 1)


def main():
    for fam, italic, wd, wg, sh in SPECS:
        src = SRC / ("Archivo-Italic[wdth,wght].ttf" if italic else "Archivo[wdth,wght].ttf")
        f = instantiateVariableFont(TTFont(src), {"wdth": wd, "wght": wg})
        if sh:
            shear_font(f, sh)
        ps = fam.replace(" ", "")
        for rec in f["name"].names:
            if rec.nameID in (1, 16):
                rec.string = fam
            elif rec.nameID in (2, 17):
                rec.string = "Regular"
            elif rec.nameID == 4:
                rec.string = fam + " Regular"
            elif rec.nameID == 6:
                rec.string = ps
            elif rec.nameID == 3:
                rec.string = ps + ";vectally-instance"
        if "STAT" in f:
            del f["STAT"]
        out = OUT / (ps + ".ttf")
        f.save(out)
        print(out.name, out.stat().st_size)


if __name__ == "__main__":
    main()

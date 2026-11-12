"""Pratinjau paket VECTALLY LENGKAP (shape + teks font brand) berdampingan dengan sumber.

QA_SHEET batch hanya menggambar shape; skrip ini menambahkan teks supaya perbandingan dengan
referensi jujur. Teks headline digambar dengan font di paket (fontRef) dan, sebagai pembanding,
League Gothic (font display utama VECTALLY).
Pemakaian: python preview_with_text.py <paket.json> <sumber.png> <out.png>
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_package_svg as R  # noqa: E402

FONTS = HERE.parent / "outputs/VECTALLY-teks-native/fonts"
ASAP, ARCHIVO_BLACK, LEAGUE_GOTHIC = "YAFdJr0OaFw:0", "YACgEZulLoA:0", "YACgEZ1OEPI:0"


def font_for(e, size, headline_font):
    ref = e.get("fontRef")
    if str(e.get("name", "")).startswith("HEADLINE_TYPECRAFT") and headline_font == "league":
        ref = LEAGUE_GOTHIC
    if ref == ARCHIVO_BLACK:
        return ImageFont.truetype(str(FONTS / "archivoblack-ArchivoBlack-Regular.ttf"), size)
    if ref == LEAGUE_GOTHIC:
        return ImageFont.truetype(str(FONTS / "leaguegothic-LeagueGothic[wdth].ttf"), size)
    f = ImageFont.truetype(str(FONTS / "asap-Asap[wdth,wght].ttf"), size)
    try:
        f.set_variation_by_axes([100, 700 if e.get("fontWeight") == "bold" else 400])
    except Exception:  # noqa: BLE001
        pass
    return f


def texts(es, ox=0, oy=0):
    for e in es:
        if e.get("type") == "group":
            yield from texts(e["children"], ox + e["left"], oy + e["top"])
        elif e.get("type") == "text":
            yield e, ox + e["left"], oy + e["top"]


def full(pkg, headline_font):
    im = R.render(pkg)
    d = ImageDraw.Draw(im)
    for e, x, y in texts(pkg["elements"]):
        size = int(e.get("fontSize", 20))
        f = font_for(e, size, headline_font)
        d.multiline_text((x, y), e.get("text", ""), font=f, fill=e.get("color", "#000000"), spacing=int(size * 0.1))
    return im


def main(pkg_path, src_path, out_path):
    pkg = json.load(open(pkg_path, encoding="utf-8"))
    W, H = pkg["width"], pkg["height"]
    src = Image.open(src_path).convert("RGB").resize((W, H))
    panels = [("SUMBER", src), ("PAKET (font di paket)", full(pkg, "pkg")), ("headline League Gothic", full(pkg, "league"))]
    tw = 420
    th = int(tw * H / W)
    sheet = Image.new("RGB", (tw * 3 + 20, th + 30), "white")
    d = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(panels):
        sheet.paste(im.resize((tw, th)), (i * (tw + 10), 30))
        d.text((i * (tw + 10) + 4, 8), label, fill="black")
    sheet.save(out_path)


if __name__ == "__main__":
    main(*sys.argv[1:4])

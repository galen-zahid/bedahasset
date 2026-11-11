"""Tambah display copy native ke kandidat S02, S04, S05 sebagai paket baru.

Memakai hasil DISPLAY-FIT.json. Paket lama tidak ditimpa. Posisi vertikal masih
estimasi dan harus dikoreksi dari export Canva sesungguhnya setelah impor.
S01 dan S03 sengaja tidak dibuat karena font/transform belum tercapai secara native.
"""
import json
from pathlib import Path

from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
REPAIR = ROOT / "outputs/VECTALLY-story-repair"
FONTS = ROOT / "outputs/VECTALLY-teks-native/fonts"
DARK = "#091522"
FACES = {
    "Asap Condensed bold": ("Asap Condensed", "YAD1fmY3NpE:0", "bold", "normal"),
    "Asap bold": ("Asap", "YAFdJr0OaFw:0", "bold", "normal"),
    "Asap bold italic": ("Asap", "YAFdJr0OaFw:0", "bold", "italic"),
    "Archivo Black": ("Archivo Black", "YACgEZulLoA:0", "normal", "normal"),
}
LOCAL = {
    "Asap Condensed bold": ("asap-Asap[wdth,wght].ttf", [700, 75]),
    "Asap bold": ("asap-Asap[wdth,wght].ttf", [700, 100]),
    "Asap bold italic": ("asap-Asap-Italic[wdth,wght].ttf", [700, 100]),
    "Archivo Black": ("archivoblack-ArchivoBlack-Regular.ttf", None),
}
BASES = {
    "S02": "ASSETS_NORMAL_COPY_PACKAGE.json",
    "S04": "ASSETS_NORMAL_COPY_PACKAGE.json",
    "S05": "ASSETS_AND_BODY_PACKAGE.json",
}
# VECTALLY adalah wordmark: tetap Archivo Black seperti S01/S02.
PICK = {
    ("S02", "WHAT'S"): "Asap Condensed bold",
    ("S02", "HARDER"): "Asap Condensed bold",
    ("S02", "TO"): "Asap Condensed bold",
    ("S02", "TRACK?"): "Asap Condensed bold",
    ("S04", "VECTALLY"): "Archivo Black",
    ("S04", "IT'S THE"): "Asap bold",
    ("S04", "PROFIT &"): "Asap Condensed bold",
    ("S04", "LOSS."): "Asap Condensed bold",
    ("S05", "VECTALLY"): "Archivo Black",
    ("S05", "GOT A"): "Asap bold",
    ("S05", "BOOKKEEPING"): "Asap bold italic",
    ("S05", "QUESTION?"): "Asap bold italic",
}


def text_width(face, text, size, ls):
    name, axes = LOCAL[face]
    font = ImageFont.truetype(str(FONTS / name), 200)
    if axes:
        font.set_variation_by_axes(axes)
    return font.getlength(text) * size / 200 + ls * size * len(text)


def validate(elements, catalogue):
    faces = {f["ref"]: {(w["weight"], s) for w in f["weights"] for s in w["styles"]} for f in catalogue["fonts"]}
    for e in elements:
        if e.get("type") == "text" and (e["fontWeight"], e["fontStyle"]) not in faces[e["fontRef"]]:
            raise SystemExit(f"FONT_VARIANT_UNAVAILABLE {e['name']}")


def main():
    fit = {(r["code"], r["text"]): r for r in json.loads((REPAIR / "DISPLAY-FIT.json").read_text(encoding="utf-8"))}
    catalogue = json.loads((ROOT / "handoff/FONT_CATALOGUE.json").read_text(encoding="utf-8"))
    for code, base in BASES.items():
        package = json.loads((REPAIR / code / base).read_text(encoding="utf-8"))
        added = []
        for (c, text), face in PICK.items():
            if c != code:
                continue
            row = fit[(c, text)]
            best = row["fits"][face]
            family, ref, weight, style = FACES[face]
            x0, y0, x1, y1 = row["inkBox"]
            size = round(best["fontSize"] * 2) / 2
            width = round(text_width(face, text, size, best["ls"]) + 24)
            element = {
                "type": "text", "name": f"{code} - {text} display native", "text": text,
                "fontFamily": family, "fontRef": ref, "fontSize": size,
                "left": round((x0 + x1) / 2 - width / 2, 2),
                "top": round((y0 + y1) / 2 - size / 2, 2),
                "width": width, "color": DARK, "fontWeight": weight, "fontStyle": style,
                "letterSpacingEm": best["ls"], "lineHeightEm": 1,
            }
            if best["angleCcw"]:
                element["rotation"] = -best["angleCcw"]
            added.append(element)
        validate(added, catalogue)
        package["elements"].extend(added)
        package["source"] = f"{code} - ASET, COPY, DAN DISPLAY NATIVE - KANDIDAT"
        summary = package.get("summary") or {}
        summary["text"] = summary.get("text", 0) + len(added)
        package["summary"] = summary
        package["warnings"] = list(package.get("warnings") or []) + ["Display copy kandidat: posisi vertikal estimasi, wajib dikoreksi dari export Canva."]
        out = REPAIR / code / "ASSETS_DISPLAY_COPY_PACKAGE.json"
        if out.exists():
            raise SystemExit(f"Sudah ada, tidak ditimpa: {out}")
        out.write_text(json.dumps(package, ensure_ascii=False), encoding="utf-8")
        print(code, "added", len(added), "elements", len(package["elements"]), out.name)
        for e in added:
            print("  ", e["text"].ljust(12), e["fontFamily"], e["fontWeight"], e["fontStyle"], e["fontSize"], "L", e["left"], "T", e["top"], "W", e["width"], "rot", e.get("rotation", 0))


if __name__ == "__main__":
    main()

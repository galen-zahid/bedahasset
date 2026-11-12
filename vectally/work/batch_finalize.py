"""Finalisasi batch VECTALLY: hasil `split.py --mode rebuild` -> paket siap impor Canva.

Dijalankan oleh Render-Vectally.ps1, bukan manual. Per desain:
  1. Geometri: semua shape diproses ulang dengan mesin smooth_native_paths (pipeline Claude
     yang sudah direview Codex): garis lurus, sudut, lubang, kurva minimal, tanpa gerigi.
  2. Font brand: teks OCR diberi font brand VECTALLY (Asap / Archivo Black / League Gothic),
     tanpa Asap Condensed. Headline besar ditandai `HEADLINE_TYPECRAFT` untuk diganti TypeCraft.
  3. Story S01-S05 memakai paket kurasi yang sudah ada bila tersedia (tidak dibatch ulang).
  4. QA: pratinjau shape vs sumber + IoU kasar, contact sheet per keluarga, ringkasan CSV.

Tidak menimpa apa pun: folder tujuan harus belum berisi file yang sama.
Pemakaian: python batch_finalize.py <rebuild_root> <final_root> <sources_root>
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import smooth_native_paths as S  # noqa: E402
import render_package_svg as R  # noqa: E402

ROOT = HERE.parent
FAMILIES = ("Feed", "Story", "Highlight")
ASAP, ARCHIVO_BLACK, LEAGUE_GOTHIC = "YAFdJr0OaFw:0", "YACgEZulLoA:0", "YACgEZ1OEPI:0"
CURATED = {
    "S01": ROOT / "outputs/VECTALLY-story-repair/S01/ASSETS_GEOM3_PACKAGE.json",
    "S02": ROOT / "outputs/VECTALLY-story-repair/S02/ASSETS_OBJECT_PACKAGE.json",
    "S03": ROOT / "outputs/VECTALLY-story-repair/S03/ASSETS_OBJECT_PACKAGE.json",
    "S04": ROOT / "outputs/VECTALLY-story-repair/S04/ASSETS_OBJECT_PACKAGE.json",
    "S05": ROOT / "outputs/VECTALLY-story-repair/S05/ASSETS_OBJECT_PACKAGE.json",
}


def code_of(name):
    part = name.split("_")
    return part[1] if len(part) > 1 and part[0].upper() == "VECTALLY" else name.split(".")[0]


def brand_font(e):
    """Font brand untuk teks OCR. Mengembalikan True bila kandidat headline TypeCraft."""
    text = e.get("text", "").strip()
    letters = [c for c in text if c.isalpha()]
    caps = bool(letters) and sum(c.isupper() for c in letters) >= 0.8 * len(letters)
    size = e.get("fontSize", 0)
    e.pop("fontFamily", None)
    if text.upper() == "VECTALLY":
        e.update(fontRef=ARCHIVO_BLACK, fontWeight="normal", fontStyle="normal", letterSpacingEm=-0.02)
        return False
    if caps and size >= 70:
        e.update(fontRef=ARCHIVO_BLACK, fontWeight="normal", fontStyle="normal",
                 name=f"HEADLINE_TYPECRAFT {text[:30]}")
        return True
    e.update(fontRef=ASAP, fontWeight="bold" if caps else "normal", fontStyle="normal")
    return False


def walk_text(es, out):
    for e in es:
        if e.get("type") == "group":
            walk_text(e["children"], out)
        elif e.get("type") == "text":
            if e.get("fontFamily") == "Asap Condensed" or e.get("fontRef") in (None, ""):
                out.append(brand_font(e))


def has_rotated_shape(es):
    for e in es:
        if e.get("type") == "group" and has_rotated_shape(e["children"]):
            return True
        if e.get("type") == "shape" and e.get("rotation"):
            return True
    return False


def qa(pkg, src_png):
    """IoU kasar: piksel non-latar sumber vs render shape paket (teks tidak dirender)."""
    W, H = pkg["width"], pkg["height"]
    src = np.asarray(Image.open(src_png).convert("RGB").resize((W, H)), dtype=np.int16)
    if has_rotated_shape(pkg["elements"]):
        return None, Image.fromarray(src.astype(np.uint8))
    ren = np.asarray(R.render(pkg).resize((W, H)), dtype=np.int16)
    diff = np.abs(src - ren).sum(axis=2)
    score = float((diff < 60).mean())
    return round(score, 3), Image.fromarray(ren.astype(np.uint8))


def finalize(pkg_path, dst, code):
    pkg = json.load(open(pkg_path, encoding="utf-8"))
    log, heads = [], []
    S.walk(pkg["elements"], log)
    walk_text(pkg["elements"], heads)
    pkg["source"] = f"{code} - VECTALLY BATCH (geometri Codex+Claude, font brand)"
    json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    status = {}
    for _, s in log:
        status[s.split()[0]] = status.get(s.split()[0], 0) + 1
    return pkg, status, sum(heads)


def main(rebuild_root, final_root, sources_root):
    rebuild_root, final_root, sources_root = Path(rebuild_root), Path(final_root), Path(sources_root)
    for fam in FAMILIES:
        srcs = sorted((sources_root / fam).glob("*.png"))
        if not srcs:
            continue
        out = final_root / fam
        out.mkdir(parents=True, exist_ok=True)
        rows, tiles = [], []
        for i, src in enumerate(srcs, 1):
            code = code_of(src.name)
            dst = out / f"{i:02d}_{code}.json"
            if dst.exists():
                print(f"[{fam}] {code} sudah ada, dilewati", flush=True)
                continue
            curated = CURATED.get(code)
            if fam == "Story" and curated and curated.exists():
                pkg = json.load(open(curated, encoding="utf-8"))
                json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
                status, heads, origin = {"kurasi": 1}, 0, "kurasi S01-S05"
            else:
                pkg_path = rebuild_root / fam / src.stem / "CANVA_PACKAGE.json"
                if not pkg_path.exists():
                    rows.append({"no": i, "code": code, "status": "BELUM_DIRENDER", "file": ""})
                    print(f"[{fam}] {code} BELUM DIRENDER: {pkg_path}", flush=True)
                    continue
                pkg, status, heads = finalize(pkg_path, dst, code)
                origin = "batch"
            score, preview = qa(pkg, src)
            rows.append({"no": i, "code": code, "status": "SIAP_IMPOR", "origin": origin,
                         "shapeStatus": json.dumps(status), "headlineTypeCraft": heads,
                         "pixelMatch": score, "file": dst.name})
            print(f"[{fam}] {code} siap impor | {status} | headline TypeCraft {heads} | match {score}", flush=True)
            a = Image.open(src).convert("RGB").resize((240, int(240 * pkg["height"] / pkg["width"])))
            b = preview.resize(a.size)
            t = Image.new("RGB", (a.width * 2 + 6, a.height + 22), "white")
            t.paste(a, (0, 22)), t.paste(b, (a.width + 6, 22))
            ImageDraw.Draw(t).text((4, 4), f"{code}  match {score}", fill="black")
            tiles.append(t)
        if tiles:
            cols = 4
            w, h = max(t.width for t in tiles), max(t.height for t in tiles)
            sheet = Image.new("RGB", (cols * w, -(-len(tiles) // cols) * h), "white")
            for k, t in enumerate(tiles):
                sheet.paste(t, ((k % cols) * w, (k // cols) * h))
            n = len(list(out.glob("QA_SHEET*.png")))
            sheet.save(out / (f"QA_SHEET_{n + 1}.png" if n else "QA_SHEET.png"))
        if rows:
            report = out / "QA_RINGKASAN.csv"
            new = not report.exists()
            with open(report, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["no", "code", "status", "origin", "shapeStatus",
                                                  "headlineTypeCraft", "pixelMatch", "file"])
                if new:
                    w.writeheader()
                w.writerows(rows)


if __name__ == "__main__":
    main(*sys.argv[1:4])

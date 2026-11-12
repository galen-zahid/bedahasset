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


TEXT_COLORS = []


def _rgb(h):
    h = (h or "#000000").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) >= 6 else (0, 0, 0)


def near_text_color(hexcol, limit=120):
    c = _rgb(hexcol)
    return any(sum(abs(a - b) for a, b in zip(c, _rgb(t))) <= limit for t in TEXT_COLORS)


def text_boxes(es):
    """Kotak headline; baris yang bertumpuk (jarak antarbaris kecil) digabung jadi satu blok."""
    boxes = []
    for e in es:
        if e.get("type") == "text" and e.get("fontSize", 0) >= 40:
            h = e.get("height") or e["fontSize"] * 1.25 * (e.get("text", "").count("\n") + 1)
            boxes.append([e["left"] - 6, e["top"] - 6, e["left"] + e["width"] + 6, e["top"] + h + 6, e["fontSize"]])
            TEXT_COLORS.append(e.get("color", "#000000"))
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                xover = min(a[2], b[2]) - max(a[0], b[0]) > 0
                gap = max(a[1], b[1]) - min(a[3], b[3])
                if xover and gap <= 0.6 * max(a[4], b[4]):
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]), max(a[4], b[4])]
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    return [tuple(b[:4]) for b in boxes]


def drop_text_ghosts(es, boxes, src, ox=0, oy=0):
    """Sisa huruf yang gagal dihapus OCR (bentuk >= 85% di dalam blok headline, warnanya mirip teks
    atau menutup >= 30% blok) diwarnai ulang dengan warna latar di sekelilingnya. Tidak dibuang,
    karena bentuk itu sering menambal lubang di latar."""
    n = 0
    for e in es:
        x0, y0 = ox + e["left"], oy + e["top"]
        if e.get("type") == "group":
            n += drop_text_ghosts(e["children"], boxes, src, x0, y0)
        elif e.get("type") == "shape":
            x1, y1, area = x0 + e["width"], y0 + e["height"], max(1.0, e["width"] * e["height"])
            inside = min(1.0, sum(max(0, min(x1, b[2]) - max(x0, b[0])) * max(0, min(y1, b[3]) - max(y0, b[1]))
                                  for b in boxes) / area) if boxes else 0
            block = max(((b[2] - b[0]) * (b[3] - b[1]) for b in boxes), default=1)
            if inside >= 0.85 and (near_text_color(e["paths"][0]["fill"].get("color")) or area >= 0.3 * block):
                col = ring_color(src, x0, y0, x1, y1)
                for p in e["paths"]:
                    p["fill"]["color"] = col
                n += 1
    return n


def ring_color(src, x0, y0, x1, y1, pad=10):
    """Median warna sumber di cincin tepat di luar kotak (warna latar sekitar)."""
    H, W = src.shape[:2]
    X0, Y0, X1, Y1 = [int(max(0, min(v, lim))) for v, lim in ((x0 - pad, W), (y0 - pad, H), (x1 + pad, W), (y1 + pad, H))]
    ring = np.concatenate([src[Y0:Y0 + pad, X0:X1].reshape(-1, 3), src[max(Y1 - pad, 0):Y1, X0:X1].reshape(-1, 3),
                           src[Y0:Y1, X0:X0 + pad].reshape(-1, 3), src[Y0:Y1, max(X1 - pad, 0):X1].reshape(-1, 3)])
    if not len(ring):
        return "#000000"
    m = np.median(ring, axis=0).astype(int)
    return "#%02x%02x%02x" % tuple(m)


def _alnum(t):
    return "".join(ch for ch in t.upper() if ch.isalnum())


def _respace(ocr, words):
    """Teks OCR dengan spasi disusun ulang sesuai batas kata judul (tanda baca OCR dipertahankan)."""
    bounds, n = set(), 0
    for w in words[:-1]:
        n += len(w)
        bounds.add(n)
    out, k = "", 0
    for ch in ocr:
        if ch == " ":
            continue
        if ch.isalnum():
            if k in bounds and out and out[-1].isalnum():
                out += " "
            k += 1
        out += ch
    return out


def fix_headlines(es, src_png):
    """Koreksi headline OCR memakai judul di nama file sumber (VECTALLY_A12_Reports_Arrive_Too_Late):
    spasi nyasar ('NUMBER S' -> 'NUMBERS') dan salah baca ('ARRIMDIHTE.' -> 'ARRIVE TOO LATE.')."""
    import difflib
    words = [w.upper() for w in Path(src_png).stem.split("_")[2:] if w]
    if not words:
        return []
    heads = []
    walk_heads(es, 0, 0, heads)
    heads.sort(key=lambda t: t[0])
    notes, start = [], 0
    for i, (_, e) in enumerate(heads):
        ocr = e.get("text", "")
        letters = _alnum(ocr)
        if not letters:
            continue
        spans = [(j, k) for j in range(start, len(words)) for k in range(j + 1, len(words) + 1)]
        exact = [(j, k) for j, k in spans if "".join(words[j:k]) == letters]
        if exact:
            j, k = exact[0]
            new = _respace(ocr, words[j:k])
        else:
            scored = [(difflib.SequenceMatcher(None, letters, "".join(words[j:k])).ratio(), j, k) for j, k in spans]
            if not scored:
                continue
            r, j, k = max(scored)
            if r < 0.5:
                notes.append(f"headline OCR '{ocr}' tidak cocok judul, cek manual")
                continue
            if i == len(heads) - 1 and k < len(words):
                r2 = difflib.SequenceMatcher(None, letters, "".join(words[j:])).ratio()
                if r2 >= 0.45:
                    k = len(words)
            tail = ocr[len(ocr.rstrip(".,!?:;")):]
            new = " ".join(words[j:k]) + tail
        if new != ocr:
            notes.append(f"headline '{ocr}' -> '{new}' (dari judul file)")
            e["text"] = new
            e["name"] = f"HEADLINE_TYPECRAFT {new[:30]}"
        start = k
    return notes


def walk_heads(es, ox, oy, out):
    for e in es:
        if e.get("type") == "group":
            walk_heads(e["children"], ox + e["left"], oy + e["top"], out)
        elif e.get("type") == "text" and str(e.get("name", "")).startswith("HEADLINE_TYPECRAFT"):
            out.append((oy + e["top"], e))


def finalize(pkg_path, dst, code, src_png):
    pkg = json.load(open(pkg_path, encoding="utf-8"))
    TEXT_COLORS.clear()
    src = np.asarray(Image.open(src_png).convert("RGB").resize((pkg["width"], pkg["height"])))
    ghosts = drop_text_ghosts(pkg["elements"], text_boxes(pkg["elements"]), src)
    if ghosts:
        pkg.setdefault("warnings", []).append(f"{ghosts} shape sisa huruf di area headline diwarnai ulang ke warna latar")
    log, heads = [], []
    S.walk(pkg["elements"], log)
    walk_text(pkg["elements"], heads)
    notes = fix_headlines(pkg["elements"], src_png)
    if notes:
        pkg.setdefault("warnings", []).extend(notes)
        print(f"  [{code}] " + " | ".join(notes))
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
                pkg, status, heads = finalize(pkg_path, dst, code, src)
                origin = "batch"
            score, preview = qa(pkg, src)
            # skor tanpa teks; < 0.70 biasanya berarti segmentasi rusak (objek terpotong) -> perbaiki manual
            st = "SIAP_IMPOR" if score is None or score >= 0.70 else "CEK_MANUAL"
            rows.append({"no": i, "code": code, "status": st, "origin": origin,
                         "shapeStatus": json.dumps(status), "headlineTypeCraft": heads,
                         "pixelMatch": score, "file": dst.name})
            print(f"[{fam}] {code} {'siap impor' if st == 'SIAP_IMPOR' else 'CEK MANUAL'} | {status} | headline TypeCraft {heads} | match {score}", flush=True)
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

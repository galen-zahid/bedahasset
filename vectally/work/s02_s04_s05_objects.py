"""Rakit ulang objek S02, S04, S05 yang masih cacat setelah audit zoom.

S02: ikon kecil dipas dari PNG sumber, bukan dari poligon lama.
S04: tumpukan koin dari elips: badan, muka atas, dan pita.
S05: bingkai sudut sebagai poligon lurus.
Objek yang sudah lolos audit tidak disentuh. Paket lama tidak ditimpa.
"""
import glob
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import render_package_svg as R  # noqa: E402
import smooth_native_paths as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/VECTALLY-story-repair"
K = 0.5523


def load(code):
    return json.load(open(OUT / code / "ASSETS_GEOM3_PACKAGE.json", encoding="utf-8"))


def save(code, pkg):
    dst = OUT / code / "ASSETS_OBJECT_PACKAGE.json"
    if dst.exists():
        raise SystemExit(f"Sudah ada, tidak ditimpa: {dst}")
    json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)


def set_path(e, d):
    e["viewBox"] = dict(left=0, top=0, width=e["width"], height=e["height"])
    e["paths"] = [dict(e["paths"][0], d=d)]


def f(*v):
    return " ".join(f"{x:.2f}" for x in v)


def half(cx, cy, rx, ry, top):
    """Setengah elips dari kiri ke kanan. top=True lewat atas."""
    s = -1 if top else 1
    return (f"C{f(cx - rx, cy + s * K * ry, cx - K * rx, cy + s * ry, cx, cy + s * ry)}"
            f"C{f(cx + K * rx, cy + s * ry, cx + rx, cy + s * K * ry, cx + rx, cy)}")


def half_back(cx, cy, rx, ry):
    """Setengah elips bawah dari kanan ke kiri."""
    return (f"C{f(cx + rx, cy + K * ry, cx + K * rx, cy + ry, cx, cy + ry)}"
            f"C{f(cx - K * rx, cy + ry, cx - rx, cy + K * ry, cx - rx, cy)}")


def body(w, h, ry):
    cx, rx = w / 2, w / 2
    return f"M{f(0, ry)}" + half(cx, ry, rx, ry, True) + f"L{f(w, h - ry)}" + half_back(cx, h - ry, rx, ry) + "Z"


def top_face(w, h):
    cx, cy, rx, ry = w / 2, h / 2, w / 2, h / 2
    return f"M{f(0, cy)}" + half(cx, cy, rx, ry, True) + half_back(cx, cy, rx, ry) + "Z"


def band(e, ry, thick):
    """Pita silinder: wilayah antara dua setengah elips identik, tebal vertikal konstan sampai dinding."""
    w, h = e["width"], e["height"]
    cx, rx = w / 2, w / 2
    side = h - ry
    yc = side - thick
    e["top"] += yc
    e["height"] = h - yc
    set_path(e, f"M{f(0, 0)}L{f(0, thick)}" + half(cx, thick, rx, ry, False) + f"L{f(w, 0)}" + half_back(cx, 0, rx, ry) + "Z")


def near(pkg, x, y, w, h):
    for e, ax, ay in R.leaves(pkg["elements"]):
        if abs(ax - x) < 1.5 and abs(ay - y) < 1.5 and abs(e["width"] - w) < 2 and abs(e["height"] - h) < 2:
            return e
    raise SystemExit(f"Shape tidak ketemu: {x},{y},{w},{h}")


def source_alpha(e, x, y, src):
    """Alpha subpiksel dari PNG: proyeksi warna antara kertas lokal dan warna tinta."""
    pad, ss = 4, S.SS
    shape_alpha, _ = S.rasterize(e)
    x0, y0 = int(round(x)) - pad, int(round(y)) - pad
    w, h = e["width"] + 2 * pad, e["height"] + 2 * pad
    crop = src[max(0, y0):y0 + h, max(0, x0):x0 + w].astype(np.float32)
    up = cv2.resize(crop, (shape_alpha.shape[1], shape_alpha.shape[0]), interpolation=cv2.INTER_CUBIC)
    near_ink = cv2.dilate((shape_alpha >= 128).astype(np.uint8), np.ones((4 * ss, 4 * ss), np.uint8)) > 0
    ring = cv2.dilate(near_ink.astype(np.uint8), np.ones((2 * ss, 2 * ss), np.uint8)) > 0
    paper = np.median(up[~near_ink] if (~near_ink).any() else up[ring], axis=0)
    ink = np.median(up[shape_alpha >= 200], axis=0)
    axis = ink - paper
    t = ((up - paper) @ axis) / max(1e-6, float(axis @ axis))
    alpha = np.clip(t, 0, 1) * 255
    alpha[~near_ink] = 0
    return alpha.astype(np.uint8), pad


def refit(pkg, src, needle):
    done = []
    for e, x, y in R.leaves(pkg["elements"]):
        if needle not in e.get("name", ""):
            continue
        node, status = S.smooth(e, source_alpha(e, x, y, src))
        e.update(node)
        done.append((e["name"][-28:], status.split(" iou")[0]))
    return done


def main():
    pkg = load("S02")
    src = np.array(Image.open(glob.glob(str(ROOT / "sources/VECTALLY/Story/*S02_*"))[0]).convert("RGB"))
    for row in refit(pkg, src, "ikon atau detail"):
        print(row)
    pkg["source"] = "S02 - OBJEK BERSIH, FONT BRAND - HEADLINE MENYUSUL"
    save("S02", pkg)

    pkg = load("S04")
    for ox, oy, ow, oh, ory, tx, ty, tw, th, bands, band_ry, thick in [
        (44.625, 593.75, 219, 290, 67.25, 58, 608, 192, 106, [(57.625, 693.625, 192, 72), (57.625, 746.625, 192, 71), (57.625, 798.625, 192, 71)], 53, 38),
        (359.75, 632.25, 214, 250, 69, 372.625, 644.75, 189, 113, [(372.625, 734.625, 189, 78), (372.625, 791.625, 189, 77)], 56.5, 42),
    ]:
        set_path(near(pkg, ox, oy, ow, oh), body(ow, oh, ory))
        set_path(near(pkg, tx, ty, tw, th), top_face(tw, th))
        for bx, by, bw, bh in bands:
            band(near(pkg, bx, by, bw, bh), band_ry, thick)
    pkg["source"] = "S04 - OBJEK BERSIH, FONT BRAND - HEADLINE MENYUSUL"
    save("S04", pkg)

    pkg = load("S05")
    set_path(near(pkg, 396, 319, 498, 270), "M1 0L1 19L480 19L480 270L498 270L498 0Z")
    set_path(near(pkg, 36.625, 1149.75, 221, 233), "M0 0L0 233L221 233L221 213L19 213L19 0Z")
    pkg["source"] = "S05 - OBJEK BERSIH, FONT BRAND"
    save("S05", pkg)
    print("ok")


if __name__ == "__main__":
    main()

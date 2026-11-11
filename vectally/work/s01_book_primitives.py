"""Gambar ulang donut, checklist, dan garis tengah buku S01 sebagai geometri bersih.

Koordinat diukur dari sumber. Semua busur dikonversi ke cubic karena perintah
path selain M/L/C/Z belum teruji di importer.
Pemakaian: s01_book_primitives.py SMOOTH.json OUT.json
"""
import glob
import json
import math
import os
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def arc(c, rx, ry, rot, t0, t1):
    """Busur elips sebagai list segmen cubic dalam koordinat halaman."""
    n = max(1, math.ceil(abs(t1 - t0) / (math.pi / 4)))
    step = (t1 - t0) / n
    k = 4 / 3 * math.tan(step / 4)
    cr, sr = math.cos(rot), math.sin(rot)
    def pt(x, y):
        return np.array([c[0] + x * cr - y * sr, c[1] + x * sr + y * cr])
    out = []
    for i in range(n):
        a, b = t0 + i * step, t0 + (i + 1) * step
        p0 = (rx * math.cos(a), ry * math.sin(a))
        p3 = (rx * math.cos(b), ry * math.sin(b))
        p1 = (p0[0] - k * rx * math.sin(a), p0[1] + k * ry * math.cos(a))
        p2 = (p3[0] + k * rx * math.sin(b), p3[1] - k * ry * math.cos(b))
        out.append((pt(*p1), pt(*p2), pt(*p3)))
    return out


def param(e, p):
    c, rx, ry, rot = e
    d = np.array(p) - c
    x = d[0] * math.cos(rot) + d[1] * math.sin(rot)
    y = -d[0] * math.sin(rot) + d[1] * math.cos(rot)
    return math.atan2(y / ry, x / rx)


def on(e, t):
    c, rx, ry, rot = e
    x, y = rx * math.cos(t), ry * math.sin(t)
    return np.array([c[0] + x * math.cos(rot) - y * math.sin(rot), c[1] + x * math.sin(rot) + y * math.cos(rot)])


def shape(name, color, start, segs):
    """segs berisi titik (garis) atau tuple 3 titik (cubic), koordinat halaman."""
    pts = [np.array(start)]
    cubic = lambda s: isinstance(s, tuple) and len(s) == 3
    for s in segs:
        pts += [np.array(p) for p in s] if cubic(s) else [np.array(s)]
    pts = np.array(pts)
    x0, y0 = np.floor(pts.min(0) - 0.0)
    x1, y1 = np.ceil(pts.max(0))
    f = lambda p: f"{p[0] - x0:.2f} {p[1] - y0:.2f}"
    d = "M" + f(start)
    for s in segs:
        d += "C" + " ".join(f(p) for p in s) if cubic(s) else "L" + f(s)
    w, h = int(x1 - x0), int(y1 - y0)
    return dict(type="shape", name=name, left=float(x0), top=float(y0), width=w, height=h,
                viewBox=dict(left=0, top=0, width=w, height=h),
                paths=[dict(d=d + "Z", fill=dict(color=color))])


def sector(name, color, outer, inner, o0, o1, i0, i1, sign):
    a0, a1 = param(outer, o0), param(outer, o1)
    b0, b1 = param(inner, i0), param(inner, i1)
    fix = lambda s, e: e + 2 * math.pi * sign if (e - s) * sign < 0 else e
    a1, b1 = fix(a0, a1), fix(b0, b1)
    segs = arc(outer[0], outer[1], outer[2], outer[3], a0, a1)
    segs = list(segs) + [on(inner, b1)] + arc(inner[0], inner[1], inner[2], inner[3], b1, b0)
    return shape(name, color, on(outer, a0), segs)


def fit_donut():
    src = np.array(Image.open(glob.glob(str(ROOT / "sources/VECTALLY/Story/*S01_*"))[0]).convert("RGB")).astype(int)
    x0, y0, x1, y1 = 680, 930, 815, 1057
    roi = src[y0:y1, x0:x1]
    paper = np.abs(roi - np.array([243, 246, 250])).sum(2) < 60
    ink = (~paper).astype(np.uint8)
    ink = cv2.morphologyEx(ink, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, hier = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    root = max((i for i, h in enumerate(hier[0]) if h[3] < 0), key=lambda i: cv2.contourArea(cnts[i]))
    kids = [i for i, h in enumerate(hier[0]) if h[3] == root]
    hole = max(kids, key=lambda i: cv2.contourArea(cnts[i]))
    def ell(c):
        (cx, cy), (a, b), ang = cv2.fitEllipse(c)
        return (np.array([cx + x0, cy + y0]), a / 2, b / 2, math.radians(ang))
    return ell(cnts[root]), ell(cnts[hole])


def check(dx, dy, tag):
    o = lambda x, y: (x + dx, y + dy)
    c = np.array(o(670.4, 1080.4))
    circle = shape(f"Checklist {tag} - lingkaran", "#09df9a", c + [14.8, 0], arc(c, 14.8, 14.1, 0, 0, 2 * math.pi))
    a, b = np.array(o(691.8, 1060.0)), np.array(o(698.1, 1065.2))
    m, r = (a + b) / 2, float(np.linalg.norm(b - a) / 2)
    t0 = math.atan2(*(a - m)[::-1])
    tail = shape(f"Checklist {tag} - ekor", "#08886b", o(681.25, 1071.0), [a] + arc(m, r, r, 0, t0, t0 + math.pi) + [o(685.0, 1075.6)])
    tick = shape(f"Checklist {tag} - centang", "#05373c", o(662.5, 1075.9), [o(669.6, 1081.9), o(681.25, 1071.0), o(685.0, 1075.6), o(669.4, 1090.25), o(659.75, 1079.1)])
    return circle, tail, tick


def rel(e, g):
    e = dict(e)
    e["left"] -= g["left"]
    e["top"] -= g["top"]
    return e


def main(src, dst):
    if os.path.exists(dst):
        raise SystemExit(f"Sudah ada, tidak ditimpa: {dst}")
    pkg = json.load(open(src, encoding="utf-8"))
    book = next(e for e in pkg["elements"] if e.get("type") == "group" and e["name"].startswith("Buku terbuka"))
    outer, inner = fit_donut()
    print("outer", outer, "inner", inner)
    gap_top_p = ((756.7, 942.3), (753.3, 969.0))
    gap_top_g = ((761.0, 941.7), (756.0, 967.7))
    right = ((804.0, 993.0), (776.0, 994.7))
    gap_bot_d = ((739.3, 1047.0), (743.7, 1020.3))
    gap_bot_p = ((735.0, 1046.7), (739.3, 1020.3))
    purple = sector("Donut - segmen ungu", "#bb9efd", outer, inner, gap_top_p[0], gap_bot_p[0], gap_top_p[1], gap_bot_p[1], -1)
    green = sector("Donut - segmen hijau", "#09e3a3", outer, inner, gap_top_g[0], right[0], gap_top_g[1], right[1], 1)
    dark = sector("Donut - segmen hijau tua", "#09a97e", outer, inner, right[0], gap_bot_d[0], right[1], gap_bot_d[1], 1)
    c1, t1, k1 = check(0, 0, "1")
    c2, t2, k2 = check(-8, 44.2, "2")
    crease = shape("Buku - garis tengah atas", "#050e1e", (653.6, 958), [(656.9, 958), (653.9, 978), (650.6, 978)])
    swap = {"Buku - segmen grafik ungu": [purple], "Buku - aksen hijau 1": [green, dark], "Buku - aksen hijau 6": [c1, t1, k1],
            "Buku - aksen hijau 7": [c2, t2, k2], "Buku - tinta centang 1": [], "Buku - tinta centang 2": [], "Buku - tinta centang 3": [],
            "Buku - garis dan tinta 1": [crease]}
    done, kids = set(), []
    for child in book["children"]:
        name = child.get("name")
        if name in swap:
            kids += [rel(x, book) for x in swap[name]]
            done.add(name)
        else:
            kids.append(child)
    missing = set(swap) - done
    if missing:
        raise SystemExit(f"Shape tidak ketemu: {missing}")
    book["children"] = kids
    pkg["source"] = "S01 - ASET BERSIH, COPY NATIVE - KANDIDAT"
    json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("ok children", len(kids))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

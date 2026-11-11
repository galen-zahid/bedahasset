"""Bangun ulang objek S03 dari pengukuran PNG sumber, per objek.

Kartu = quad berjari-jari dari perpotongan sisi terukur. Batang, garis, plus,
minus = primitive. Sapuan hijau = dua tepi polinomial dari mask sumber lewat
native_clean_quad. Teks dan urutan layer dari paket lama dipertahankan.
Pemakaian: s03_objects.py OUT.json
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

sys.path.insert(0, str(Path(__file__).parent))
from s01_book_primitives import arc, shape  # noqa: E402
from native_clean_quad import clean_quad  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "outputs/VECTALLY-story-repair/S03"


def P(x, y):
    """Koordinat grid ukur 2x ke koordinat halaman."""
    return np.array([55 + x / 2, 500 + y / 2], float)


def meet(a1, a2, b1, b2):
    d1, d2 = a2 - a1, b2 - b1
    t = ((b1 - a1)[0] * d2[1] - (b1 - a1)[1] * d2[0]) / (d1[0] * d2[1] - d1[1] * d2[0])
    return a1 + d1 * t


def rquad(name, color, verts, r):
    """Poligon cembung dengan radius sama di tiap sudut."""
    n = len(verts)
    unit = lambda v: v / np.linalg.norm(v)
    segs, start = [], None
    for i in range(n):
        v, prev, nxt = verts[i], verts[i - 1], verts[(i + 1) % n]
        u, w = unit(v - prev), unit(nxt - v)
        theta = math.acos(max(-1, min(1, float(np.dot(u, w)))))
        t = r * math.tan(theta / 2)
        a, b = v - u * t, v + w * t
        k = 4 / 3 * math.tan(theta / 4) * r
        if start is None:
            start = a
        else:
            segs.append(a)
        segs.append((a + u * k, b - w * k, b))
    return shape(name, color, start, segs)


def bar(name, color, p, q, thick, cap=None):
    """Batang dari garis tengah. cap=None berarti ujung bulat penuh."""
    u = (q - p) / np.linalg.norm(q - p)
    v = np.array([-u[1], u[0]]) * thick / 2
    return rquad(name, color, [p + v, q + v, q - v, p - v], thick / 2 * 0.98 if cap is None else cap)


def cross(name, color, c, hu, hv, t):
    """Tanda plus sebagai satu bentuk. hu, hv = setengah panjang lengan."""
    u, v = hu / np.linalg.norm(hu), hv / np.linalg.norm(hv)
    a, b = u * t / 2, v * t / 2
    pts = [c - hu + b, c - a + b, c - a + hv, c + a + hv, c + a + b, c + hu + b, c + hu - b, c + a - b, c + a - hv, c - a - hv, c - a - b, c - hu - b]
    return shape(name, color, pts[0], pts[1:])


def card(name, top, right, bottom, left, r):
    verts = [meet(*left, *top), meet(*top, *right), meet(*right, *bottom), meet(*bottom, *left)]
    return rquad(name, "#f3f5fa", verts, r)


def sweep(node, src):
    """Sapuan: tepi atas dan bawah dipas polinomial dari mask sumber."""
    x, y, w, h = int(node["left"]), int(node["top"]), node["width"], node["height"]
    roi = np.abs(src.astype(int) - np.array([10, 226, 139])).sum(2) < 120
    mask = np.zeros(roi.shape, np.uint8)
    mask[max(0, y - 3):y + h + 3, max(0, x - 3):x + w + 3] = roi[max(0, y - 3):y + h + 3, max(0, x - 3):x + w + 3]
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask)
    mask = (lab == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))).astype(np.uint8)
    out, meta = clean_quad(node, mask, min_iou=0.9)
    print(node["name"], meta)
    return out


def regroup(group, parts):
    texts = []
    for c in group["children"]:
        if c.get("type") == "text":
            c = dict(c)
            c["left"] += group["left"]
            c["top"] += group["top"]
            texts.append(c)
    x0 = min(p["left"] for p in parts)
    y0 = min(p["top"] for p in parts)
    x1 = max(p["left"] + p["width"] for p in parts)
    y1 = max(p["top"] + p["height"] for p in parts)
    group.update(left=x0, top=y0, width=x1 - x0, height=y1 - y0)
    kids = []
    for p in parts + texts:
        p = dict(p)
        p["left"] -= x0
        p["top"] -= y0
        kids.append(p)
    group["children"] = kids


def main(dst):
    if os.path.exists(dst):
        raise SystemExit(f"Sudah ada, tidak ditimpa: {dst}")
    pkg = json.load(open(R / "ASSETS_PARTIAL_COPY_PACKAGE.json", encoding="utf-8"))
    src = np.array(Image.open(glob.glob(str(ROOT / "sources/VECTALLY/Story/*S03_*"))[0]).convert("RGB"))
    L1, L2, GR, DK = "#c9baf7", "#c8b9f7", "#7ce8bf", "#6f639f"
    ink = "#091522"
    pl = next(e for e in pkg["elements"] if e.get("name", "").startswith("Lembar Profit"))
    bs = next(e for e in pkg["elements"] if e.get("name", "").startswith("Lembar Balance"))
    regroup(pl, [
        card("Kartu Profit and Loss - kertas utuh", (P(150, 303), P(670, 228)), (P(705, 270), P(685, 1000)), (P(650, 1032), P(60, 1100)), (P(24, 1060), P(115, 345)), 20),
        rquad("Profit and Loss - batang 1", L1, [P(152, 627), P(484, 580), P(484, 628), P(152, 675)], 8),
        rquad("Profit and Loss - batang 2", L1, [P(140, 730), P(477, 682), P(477, 730), P(140, 777)], 8),
        rquad("Profit and Loss - batang 3", L2, [P(128, 832), P(471, 785), P(471, 833), P(128, 880)], 8),
        rquad("Profit and Loss - batang total", GR, [P(107, 981), P(611, 913), P(611, 965), P(107, 1028)], 9),
        cross("Profit and Loss - tanda plus", ink, P(598, 586), (P(622, 581) - P(574, 591)) / 2, (P(602, 611) - P(594, 561)) / 2, 4.6),
        bar("Profit and Loss - tanda minus", ink, P(573, 692), P(615, 685), 4.6, 0.6),
        bar("Profit and Loss - garis total", ink, P(120, 928), P(612, 862), 3.2),
    ])
    regroup(bs, [
        card("Kartu Balance Sheet - kertas utuh", (P(1075, 248), P(1590, 330)), (P(1630, 370), P(1518, 1085)), (P(1480, 1110), P(895, 1018)), (P(872, 985), P(1035, 280)), 20),
        bar("Balance Sheet - batang gelap kiri", DK, P(1041, 591), P(1204, 618), 16.5),
        bar("Balance Sheet - batang gelap kanan", DK, P(1341, 632), P(1506, 661), 16.5),
        rquad("Balance Sheet - batang kiri 1", L1, [P(1012, 657), P(1200, 680), P(1197, 730), P(1006, 706)], 7),
        rquad("Balance Sheet - batang kiri 2", L1, [P(990, 748), P(1181, 771), P(1176, 823), P(985, 797)], 7),
        rquad("Balance Sheet - batang kiri 3", L1, [P(970, 840), P(1163, 863), P(1158, 917), P(964, 886)], 7),
        rquad("Balance Sheet - batang kanan 1", L1, [P(1316, 698), P(1505, 725), P(1501, 775), P(1311, 746)], 7),
        rquad("Balance Sheet - batang kanan 2", L1, [P(1298, 790), P(1490, 815), P(1484, 868), P(1293, 840)], 7),
        rquad("Balance Sheet - batang kanan 3", L1, [P(1280, 883), P(1475, 908), P(1470, 962), P(1275, 934)], 7),
        bar("Balance Sheet - pemisah kolom", ink, P(1277, 589), P(1201, 995), 3.0, 0.3),
    ])
    for i, e in enumerate(pkg["elements"]):
        name = e.get("name", "")
        if name.startswith("Garis penegas"):
            pkg["elements"][i] = sweep(e, src)
        elif name.startswith("Pilihan OR"):
            c = P(819.5, 650)
            circle = shape("Pilihan OR - lingkaran", "#0be18b", c + [66.75, 0], arc(c, 66.75, 68.5, 0, 0, 2 * math.pi))
            for t in e["children"]:
                if t.get("type") == "text":
                    t.update(fontFamily="Asap", fontRef="YAFdJr0OaFw:0", fontWeight="bold", fontStyle="italic", fontSize=63, letterSpacingEm=-0.04, rotation=4)
            regroup(e, [circle])
    pkg["source"] = "S03 - OBJEK DIBANGUN DARI SUMBER - HEADLINE MENYUSUL"
    pkg["summary"] = {"shape": 23, "group": 3, "text": 6, "image": 0}
    json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("ok")


if __name__ == "__main__":
    main(sys.argv[1])

"""Gambar ulang jaringan konektor S01: jalur garis berjari-jari, pil, dan titik.

Jalur diukur dari sumber. Tiap cabang dibentuk dari sisi offset konstan sehingga
ketebalan rata dan tikungan benar-benar busur. Semua bagian tetap satu grup.
Pemakaian: s01_connector.py IN.json OUT.json
"""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from s01_book_primitives import arc, shape  # noqa: E402

COLOR = "#06e29e"


def unit(v):
    return v / np.linalg.norm(v)


def normal(u):
    return np.array([u[1], -u[0]])


def side(way, radii, off):
    """Satu sisi offset. Hasil: titik awal dan daftar segmen."""
    way = [np.array(p, float) for p in way]
    if len(radii) != len(way) - 2:
        raise ValueError("Jumlah radius harus sama dengan jumlah tikungan")
    gaps = [float(np.linalg.norm(b - a)) for a, b in zip(way, way[1:])]
    if min(gaps) <= 0:
        raise ValueError("Ada titik jalur yang berulang")
    dirs = [unit(b - a) for a, b in zip(way, way[1:])]
    cuts = [0.0] * len(way)
    for i, r in enumerate(radii):
        dot = float(np.dot(dirs[i], dirs[i + 1]))
        if abs(dot) >= 0.9999:
            raise ValueError("Tikungan 0 atau 180 derajat tidak didukung")
        if r <= abs(off):
            raise ValueError("Radius dalam harus positif")
        cuts[i + 1] = r * math.tan(math.acos(dot) / 2)
    for i, g in enumerate(gaps):
        if cuts[i] + cuts[i + 1] > g:
            raise ValueError("Radius tidak muat di segmen jalur")
    start = way[0] + normal(dirs[0]) * off
    segs = []
    for i, r in enumerate(radii):
        u, v, c = dirs[i], dirs[i + 1], way[i + 1]
        theta = math.acos(max(-1, min(1, float(np.dot(u, v)))))
        t = r * math.tan(theta / 2)
        cross = u[0] * v[1] - u[1] * v[0]
        toward = np.array([-u[1], u[0]]) * (1 if cross > 0 else -1)
        center = c - u * t + toward * r
        a = c - u * t + normal(u) * off
        b = c + v * t + normal(v) * off
        radius = float(np.linalg.norm(a - center))
        k = 4 / 3 * math.tan(theta / 4) * radius
        segs += [a, (a + u * k, b - v * k, b)]
    segs.append(way[-1] + normal(dirs[-1]) * off)
    return start, segs


def stroke(name, way, radii, width):
    s1, a = side(way, radii, width / 2)
    s2, b = side(way[::-1], radii[::-1], width / 2)
    return shape(name, COLOR, s1, a + [s2] + b)


def circle(name, c, r):
    c = np.array(c, float)
    return shape(name, COLOR, c + [r, 0], arc(c, r, r, 0, 0, 2 * math.pi))


def pill(name, x0, y0, x1, y1):
    r = (y1 - y0) / 2
    left, right = np.array([x0 + r, y0 + r]), np.array([x1 - r, y0 + r])
    segs = arc(right, r, r, 0, -math.pi / 2, math.pi / 2) + [(x0 + r, y1)] + arc(left, r, r, 0, math.pi / 2, 3 * math.pi / 2)
    return shape(name, COLOR, (x1 - r, y0), segs)


def main(src, dst):
    if os.path.exists(dst):
        raise SystemExit(f"Sudah ada, tidak ditimpa: {dst}")
    pkg = json.load(open(src, encoding="utf-8"))
    group = next(e for e in pkg["elements"] if e.get("name", "").startswith("Jaringan konektor"))
    parts = [
        stroke("Konektor - cabang dokumen atas", [(272.5, 583), (342.5, 583), (342.5, 699), (410, 699), (410, 735)], [25, 30, 22], 8),
        stroke("Konektor - cabang dokumen kiri", [(181, 657), (181, 707), (292, 707), (322, 752.5), (366, 752.5)], [20, 30, 30], 8),
        stroke("Konektor - cabang struk", [(201, 813.5), (248, 813.5), (272, 776), (362, 776)], [22, 22], 8),
        stroke("Konektor - cabang grafik", [(453, 644), (453, 692), (435, 712), (435, 735)], [14, 14], 8),
        stroke("Konektor - jalur ke buku", [(475, 812), (475, 889), (660, 889), (660, 945)], [38, 38], 19.5),
        pill("Panel TELL A", 359, 729, 656, 817.5),
        circle("Konektor - titik dokumen kiri", (181, 657.5), 14),
        circle("Konektor - titik grafik", (453, 644), 14),
        circle("Konektor - titik struk", (201, 813.5), 14),
        circle("Konektor - titik buku", (659, 941), 19),
    ]
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
    children = []
    for p in parts + texts:
        p = dict(p)
        p["left"] -= x0
        p["top"] -= y0
        children.append(p)
    group["children"] = children
    json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    print("konektor", len(parts), "bagian, grup", x0, y0, x1 - x0, y1 - y0, "teks", len(texts))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

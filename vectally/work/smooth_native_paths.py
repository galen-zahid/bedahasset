"""Ubah path poligon berjejak piksel menjadi kurva Bezier native.

Tiap shape dirender 4x, diblur ringan agar tangga piksel hilang, lalu konturnya
dipas dengan cubic Bezier dan sudut asli dipertahankan. Lubang tetap memakai
jembatan lebar-nol karena path native hanya boleh satu M. Shape ditolak dan
dibiarkan kalau bentuknya bergeser melewati gerbang IoU.

Pemakaian: smooth_native_paths.py IN.json OUT.json
"""
import io
import json
import math
import os
import sys

import cv2
import numpy as np
import resvg_py
from PIL import Image

SS = 4
MAX_BYTES = 1850


def rasterize(e):
    w, h, vb = e["width"], e["height"], e["viewBox"]
    pad = 4
    body = "".join(f'<path d="{p["d"]}" fill="#000"/>' for p in e["paths"])
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{(w + 2 * pad) * SS}" height="{(h + 2 * pad) * SS}" '
           f'viewBox="{-pad} {-pad} {w + 2 * pad} {h + 2 * pad}"><g transform="scale({w / vb["width"]} {h / vb["height"]}) '
           f'translate({-vb["left"]} {-vb["top"]})">{body}</g></svg>')
    alpha = np.array(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("RGBA"))[:, :, 3]
    return alpha, pad


def corners(pts, win, angle):
    n = len(pts)
    a = pts - np.roll(pts, win, axis=0)
    b = np.roll(pts, -win, axis=0) - pts
    cos = (a * b).sum(1) / np.maximum(1e-6, np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    turn = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    idx = []
    for i in np.argsort(-turn):
        if turn[i] < angle:
            break
        if all(min(abs(i - j), n - abs(i - j)) > win for j in idx):
            idx.append(int(i))
    return sorted(idx)


def bez(c, t):
    t = t[:, None]
    return (1 - t) ** 3 * c[0] + 3 * (1 - t) ** 2 * t * c[1] + 3 * (1 - t) * t ** 2 * c[2] + t ** 3 * c[3]


def generate(p, u, t1, t2):
    b0, b1, b2, b3 = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u ** 2 * (1 - u), u ** 3
    a1, a2 = b1[:, None] * t1, b2[:, None] * t2
    tmp = p - ((b0 + b1)[:, None] * p[0] + (b2 + b3)[:, None] * p[-1])
    c11, c12, c22 = (a1 * a1).sum(), (a1 * a2).sum(), (a2 * a2).sum()
    x1, x2 = (a1 * tmp).sum(), (a2 * tmp).sum()
    det = c11 * c22 - c12 * c12
    seg = np.linalg.norm(p[-1] - p[0])
    if abs(det) < 1e-9:
        al = ar = seg / 3
    else:
        al, ar = (x1 * c22 - x2 * c12) / det, (c11 * x2 - c12 * x1) / det
    if al < 1e-3 * seg or ar < 1e-3 * seg:
        al = ar = seg / 3
    return np.array([p[0], p[0] + t1 * al, p[-1] + t2 * ar, p[-1]])


def fit(p, tol, t1=None, t2=None, depth=0):
    if len(p) < 3:
        return [np.array([p[0], p[0] + (p[-1] - p[0]) / 3, p[0] + 2 * (p[-1] - p[0]) / 3, p[-1]])]
    k = min(4, len(p) - 1)
    unit = lambda v: v / max(1e-6, np.linalg.norm(v))
    t1 = unit(p[k] - p[0]) if t1 is None else t1
    t2 = unit(p[-1 - k] - p[-1]) if t2 is None else t2
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    u = d / max(1e-6, d[-1])
    c = generate(p, u, t1, t2)
    err = np.linalg.norm(bez(c, u) - p, axis=1)
    if err.max() <= tol or depth > 12 or len(p) < 8:
        return [c]
    i = int(np.clip(err.argmax(), 2, len(p) - 3))
    tc = unit(p[max(0, i - k)] - p[min(len(p) - 1, i + k)])
    return fit(p[: i + 1], tol, t1, tc, depth + 1) + fit(p[i:], tol, -tc, t2, depth + 1)


def _line(p):
    """Garis least-squares: titik tengah dan arah satuan."""
    c = p.mean(0)
    v = np.linalg.svd(p - c)[2][0]
    return c, v


def _meet(a, b, near):
    (c1, v1), (c2, v2) = a, b
    det = v1[0] * -v2[1] + v2[0] * v1[1]
    if abs(det) < 0.05:
        return near
    d = c2 - c1
    t = (d[0] * -v2[1] + v2[0] * d[1]) / det
    p = c1 + v1 * t
    return p if np.linalg.norm(p - near) <= 3.5 else near


def _project(line, p):
    c, v = line
    return c + v * np.dot(p - c, v)


def fit_loop(pts, tol, win):
    """Rekonstruksi: sisi lurus jadi garis sejati, sudut dari perpotongan, sisanya sedikit kurva."""
    n = len(pts)
    grid = np.round(pts * SS).astype(np.int32)
    index = {}
    for i, g in enumerate(map(tuple, grid.tolist())):
        index.setdefault(g, i)
    approx = cv2.approxPolyDP(grid.reshape(-1, 1, 2), 1.0 * SS, True).reshape(-1, 2)
    verts = sorted({index[tuple(a)] for a in approx.tolist()})
    m = len(verts)
    if m < 3:
        return fit_loop_curve(pts, tol, win)
    vec = [pts[verts[(i + 1) % m]] - pts[verts[i]] for i in range(m)]
    length = [float(np.linalg.norm(v)) for v in vec]

    def turn(i):  # sudut di verts[i], antara edge i-1 dan edge i
        a, b = vec[i - 1], vec[i]
        c = np.dot(a, b) / max(1e-6, np.linalg.norm(a) * np.linalg.norm(b))
        return math.degrees(math.acos(max(-1, min(1, c))))

    straight = []
    for i in range(m):
        prev_ok = turn(i) >= 22 or length[i] >= 2.2 * length[i - 1]
        next_ok = turn((i + 1) % m) >= 22 or length[i] >= 2.2 * length[(i + 1) % m]
        straight.append(length[i] >= 10 and prev_ok and next_ok)
    if not any(straight):
        return fit_loop_curve(pts, tol, win)

    def span(a, b):
        return pts[np.arange(a, b + 1 if b >= a else b + n + 1) % n]

    lines = {}
    for i in range(m):
        if straight[i]:
            seg = span(verts[i], verts[(i + 1) % m])
            k = max(1, len(seg) // 8)
            lines[i] = _line(seg[k:-k] if len(seg) > 2 * k + 2 else seg)

    def node(i):  # posisi verts[i] setelah dibersihkan
        p, a, b = pts[verts[i]], (i - 1) % m, i
        if a in lines and b in lines:
            return _meet(lines[a], lines[b], p)
        if a in lines:
            return _project(lines[a], p)
        if b in lines:
            return _project(lines[b], p)
        return p

    first = next(i for i in range(m) if straight[i])
    start = node(first)
    out, i, done = [], first, 0
    while done < m:
        if straight[i]:
            out.append(("L", node((i + 1) % m)))
            i, done = (i + 1) % m, done + 1
            continue
        j, steps = i, 0
        while not straight[j] and steps < m - done:
            j, steps = (j + 1) % m, steps + 1
        seg = span(verts[i], verts[j]).copy()
        seg[0], seg[-1] = node(i), node(j)
        cuts = [0] + [c for c in _inner_corners(seg, win)] + [len(seg) - 1]
        for a, b in zip(cuts, cuts[1:]):
            t1 = -lines[(i - 1) % m][1] * 0 if False else None
            out += [("C", c) for c in fit(seg[a:b + 1], tol, t1, None)]
        i, done = j, done + steps
    return start, out


def _inner_corners(seg, win):
    n = len(seg)
    if n < 2 * win + 3:
        return []
    a = seg[win:-win] - seg[:-2 * win]
    a = a[: n - 2 * win]
    idx = np.arange(win, n - win)
    before = seg[idx] - seg[idx - win]
    after = seg[idx + win] - seg[idx]
    cos = (before * after).sum(1) / np.maximum(1e-6, np.linalg.norm(before, axis=1) * np.linalg.norm(after, axis=1))
    turn = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    found = []
    for k in np.argsort(-turn):
        if turn[k] < 45:
            break
        i = int(idx[k])
        if all(abs(i - j) > win for j in found):
            found.append(i)
    return sorted(found)


def fit_loop_curve(pts, tol, win):
    cs = corners(pts, win, 42)
    if not cs:
        cs = [0, len(pts) // 2]
    out = []
    for a, b in zip(cs, cs[1:] + [cs[0] + len(pts)]):
        seg = pts[np.arange(a, b + 1) % len(pts)]
        chord = seg[-1] - seg[0]
        length = np.linalg.norm(chord)
        if length > 0:
            dev = np.abs(np.cross(seg - seg[0], chord / length)).max()
            if dev <= max(1.6, tol * 1.2):
                out.append(("L", seg[-1]))
                continue
        out += [("C", c) for c in fit(seg, tol)]
    return pts[cs[0]], out


def fmt(v):
    s = f"{v:.1f}"
    s = s.rstrip("0").rstrip(".") if "." in s else s
    return "0" if s in ("-0", "") else s


def emit(cur, seg):
    kind, data = seg
    if kind == "L":
        d = data - cur
        return "l" + fmt(d[0]) + " " + fmt(d[1]), cur + np.round(d, 1)
    rel = data[1:] - cur
    txt = "c" + " ".join(fmt(x) for x in rel.ravel())
    return txt, cur + np.round(rel[2], 1)


def to_path(outer, holes, tol, win):
    """Satu M. Tiap lubang dicapai lewat jembatan garis lebar-nol dari kontur luar."""
    start, segs = fit_loop(outer, tol, win)
    cur = np.round(start, 1)
    parts = ["M" + fmt(cur[0]) + " " + fmt(cur[1])]
    pending = list(holes)
    for seg in segs:
        txt, cur = emit(cur, seg)
        parts.append(txt)
        if not pending:
            continue
        here = cur.copy()
        near = [h for h in pending if np.linalg.norm(h - here, axis=1).min() < 1e9]
        h = min(near, key=lambda q: np.linalg.norm(q - here, axis=1).min())
        if seg is segs[-1] or np.linalg.norm(h - here, axis=1).min() <= min(np.linalg.norm(q - here, axis=1).min() for q in pending):
            if seg is not segs[-1] and len(segs) > len(pending) and np.linalg.norm(h - here, axis=1).min() > 40:
                continue
            pending.remove(h)
            i = int(np.linalg.norm(h - here, axis=1).argmin())
            loop = np.roll(h, -i, axis=0)
            hs, hsegs = fit_loop(loop, tol, win)
            back = cur.copy()
            d = hs - cur
            parts.append("l" + fmt(d[0]) + " " + fmt(d[1]))
            cur = cur + np.round(d, 1)
            for s in hsegs:
                txt, cur = emit(cur, s)
                parts.append(txt)
            d = hs - cur
            if np.abs(d).max() > 0.04:
                parts.append("l" + fmt(d[0]) + " " + fmt(d[1]))
                cur = cur + np.round(d, 1)
            d = back - cur
            parts.append("l" + fmt(d[0]) + " " + fmt(d[1]))
            cur = cur + np.round(d, 1)
    return "".join(parts) + "Z" if not pending else None


def smooth(e):
    if any(c in e["paths"][0]["d"] for c in "Cc") or len(e["paths"]) != 1 or e["width"] * e["height"] > 900000:
        return e, "skip"
    alpha, pad = rasterize(e)
    source = alpha >= 128
    area = int(source.sum())
    if area < 40 * SS * SS:
        return e, "tiny"
    ext, _ = cv2.findContours(source.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    big = max(ext, key=cv2.contourArea)
    thick = area / max(1.0, cv2.arcLength(big, True)) / SS
    gate = 0.93 if thick >= 5 else 0.8
    rect = cv2.minAreaRect(big)
    rw, rh = rect[1]
    is_bar = rw * rh > 0 and min(rw, rh) / max(rw, rh) <= 0.33 and area / (rw * rh) >= 0.8
    if len(ext) == 1 and (is_bar or (rw * rh > 0 and area / (rw * rh) >= 0.985)):
        # Batang dan garis: pakai persegi miring bersih, bukan jejak tepi.
        box = cv2.boxPoints(rect) / SS - pad
        d = "M" + "L".join(f"{fmt(x)} {fmt(y)}" for x, y in box) + "Z"
        node = dict(e)
        node["viewBox"] = dict(left=0, top=0, width=e["width"], height=e["height"])
        node["paths"] = [dict(e["paths"][0], d=d)]
        got, _ = rasterize(node)
        got = got >= 128
        score = (got & source).sum() / max(1, (got | source).sum())
        if score >= 0.72:
            return node, f"smooth rect iou{score:.3f}"
    for sigma in (0.8, 1.2, 0.5):
        blur = cv2.GaussianBlur(alpha.astype(np.float32), (0, 0), sigma * SS)
        mask = (blur >= 127.5).astype(np.uint8)
        cnts, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        if hier is None:
            continue
        roots = [i for i, h in enumerate(hier[0]) if h[3] < 0]
        if len(roots) != 1:
            continue
        holes_i, child = [], hier[0][roots[0]][2]
        while child >= 0:
            if cv2.contourArea(cnts[child]) > 6 * SS * SS:
                holes_i.append(child)
            child = hier[0][child][0]
        conv = lambda c: (c.reshape(-1, 2).astype(float) + 0.5) / SS - pad
        outer, holes = conv(cnts[roots[0]]), [conv(cnts[i]) for i in holes_i]
        # Toleransi kasar dulu: makin sedikit kurva, makin bersih tepinya.
        for tol in (1.4, 1.1, 0.85, 0.6, 1.8, 2.4):
            d = to_path(outer, holes, tol, 3 * SS)
            if d is None or len(d.encode()) > MAX_BYTES:
                continue
            node = dict(e)
            node["viewBox"] = dict(left=0, top=0, width=e["width"], height=e["height"])
            node["paths"] = [dict(e["paths"][0], d=d)]
            got, _ = rasterize(node)
            got = got >= 128
            score = (got & source).sum() / max(1, (got | source).sum())
            if score >= (gate if tol <= 1.4 else 0.75):
                return node, f"smooth sigma{sigma} tol{tol} iou{score:.3f} {len(d)}B"
    return e, "rejected"


def walk(es, log):
    for i, e in enumerate(es):
        if e.get("type") == "group":
            walk(e["children"], log)
        elif e.get("type") == "shape":
            es[i], status = smooth(e)
            log.append((e.get("name", "")[:44], status))


def main(src, dst):
    if os.path.exists(dst):
        raise SystemExit(f"Sudah ada, tidak ditimpa: {dst}")
    pkg = json.load(open(src, encoding="utf-8"))
    log = []
    walk(pkg["elements"], log)
    json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    kinds = {}
    for _, s in log:
        kinds[s.split()[0]] = kinds.get(s.split()[0], 0) + 1
    print(kinds)
    for n, s in log:
        if not s.startswith("smooth") and s != "skip":
            print("  ", n, s)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

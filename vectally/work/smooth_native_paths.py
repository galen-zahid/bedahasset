"""Ubah path poligon berjejak piksel menjadi kurva Bezier native.

Tiap shape dirender 4x, diblur ringan agar tangga piksel hilang, lalu konturnya
dipas dengan cubic Bezier dan sudut asli dipertahankan. Lubang tetap memakai
jembatan lebar-nol karena path native hanya boleh satu M. Shape ditolak dan
dibiarkan kalau bentuknya bergeser melewati gerbang IoU.

Pemakaian: smooth_native_paths.py IN.json OUT.json
"""
import io
import json
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


def fit_loop(pts, tol, win):
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
    for sigma in (1.3, 1.0, 0.75, 0.5):
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

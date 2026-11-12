"""CANVA_PACKAGE.json: everything the CUSBE Canva app needs to assemble the design with NATIVE
Canva elements (shapes, text) and images, in z-order, at exact coordinates.

Canva Apps SDK shape limits (addElementAtPoint, type "shape"):
  - 1..30 paths, each with ONE "M", closed, no Q commands, solid hex fill
  - at most 6 distinct fill colours, combined path data <= 2 kB
Vector objects that do not fit (or need a real gradient) are split or sent as an image, and the
reason is written to the package's "warnings".
"""
from __future__ import annotations

import base64
import io
import json
import logging
import math

import cv2
import numpy as np
from PIL import Image

from . import shapes

log = logging.getLogger("split")

MAX_PATHS = 30
MAX_COLORS = 6
MAX_D = 1900  # stay under the 2 kB limit


def _hex(c):
    return shapes._hex(c)


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _poly_d(pts):
    pts = np.asarray(pts, np.float64)
    return "M" + " L".join(f"{_f(x)} {_f(y)}" for x, y in pts) + " Z"


def _outline_ds(m, ox, oy, eps, corner_deg, smooth):
    """Pen-tool outline, one closed sub-path per outer contour (Canva: one M per path)."""
    cnts, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = []
    cos_c = math.cos(math.radians(corner_deg))
    for cnt in cnts:
        p = cnt.reshape(-1, 2).astype(np.float64) + 0.5
        if len(p) < 6:
            continue
        if smooth > 0 and len(p) > 12:
            r = int(3 * smooth)
            k = np.exp(-0.5 * (np.arange(-r, r + 1) / smooth) ** 2)
            k /= k.sum()
            pw = np.vstack([p[-r:], p, p[:r]])
            p = np.stack([np.convolve(pw[:, i], k, "valid") for i in range(2)], 1)
        a = cv2.approxPolyDP(p.astype(np.float32).reshape(-1, 1, 2), eps, True).reshape(-1, 2).astype(np.float64)
        n = len(a)
        if n < 3:
            continue
        a += [ox, oy]
        corner = np.zeros(n, bool)
        for i in range(n):
            u, v = a[i] - a[i - 1], a[(i + 1) % n] - a[i]
            nu, nv = np.linalg.norm(u), np.linalg.norm(v)
            if nu and nv and (u @ v) / (nu * nv) < cos_c:
                corner[i] = True
        seg = [f"M{_f(a[0][0])} {_f(a[0][1])}"]
        for i in range(n):
            p0, p1, p2, p3 = a[i - 1], a[i], a[(i + 1) % n], a[(i + 2) % n]
            c1 = p1 if corner[i] else p1 + (p2 - p0) / 6
            c2 = p2 if corner[(i + 1) % n] else p2 - (p3 - p1) / 6
            seg.append(f"C{_f(c1[0])} {_f(c1[1])} {_f(c2[0])} {_f(c2[1])} {_f(p2[0])} {_f(p2[1])}")
        out.append(" ".join(seg) + " Z")
    return out


def _region_color(r):
    f = r["fill"]
    if f["kind"] == "solid":
        return np.asarray(f["color"]), 0.0
    stops = [s[2] for s in f["stops"]] + [col for _, col in (f.get("mid") or [])]
    stops = np.asarray(stops)
    return stops.mean(0), float(np.abs(stops.max(0) - stops.min(0)).max())


def region_paths(r, W, H, c, eps_scale=1.0):
    """[(d, hex)] in CANVAS coordinates, or None if the region cannot be a native shape."""
    kind, p, _ = r["shape"]
    col, spread = _region_color(r)
    if spread > c.canva_max_gradient:  # a real gradient: Canva shapes are solid only
        if not c.get("canva_never_image", False):
            return None
        # mode tanpa PNG: gradien jadi warna solid rata-rata (tetap shape native)
    hx = _hex(col)
    sl = r["sl"]
    oy, ox = sl[0].start, sl[1].start
    if kind == "canvas":
        return [(f"M0 0 L{W} 0 L{W} {H} L0 {H} Z", hx)]
    if kind == "rect":
        pts = shapes._rounded_rect_pts(p["cx"], p["cy"], p["w"], p["h"], p["ang"], p["r"], n=5 if p["r"] >= 0.75 else 1)
        return [(_poly_d(pts + [ox, oy]), hx)]
    if kind == "ellipse":
        t = np.linspace(0, 2 * np.pi, 33)[:-1]
        a = math.radians(p["ang"])
        x = p["rx"] * np.cos(t)
        y = p["ry"] * np.sin(t)
        pts = np.stack([x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)], 1) + [p["cx"] + ox, p["cy"] + oy]
        return [(_poly_d(pts), hx)]
    if kind == "polygon":
        return [(_poly_d(np.asarray(p["pts"]) + [ox, oy]), hx)]
    if kind == "stroke":
        from shapely.geometry import LineString

        line = LineString(np.asarray(p["pts"]) + [ox, oy])
        poly = line.buffer(p["w"] / 2, quad_segs=4, cap_style="round", join_style="round")
        poly = poly.simplify(0.4 * eps_scale)
        geoms = getattr(poly, "geoms", [poly])
        return [(_poly_d(np.asarray(g.exterior.coords)[:-1]), hx) for g in geoms]
    ds = _outline_ds(r["filled"], ox, oy, c.anchor_eps * eps_scale, c.corner_deg, c.smooth)
    return [(d, hx) for d in ds] or None


def _bbox_of(ds):
    nums = []
    for d, _ in ds:
        v = [float(t) for t in d.replace("M", " ").replace("L", " ").replace("C", " ").replace("Z", " ").split()]
        nums += v
    xs, ys = np.array(nums[0::2]), np.array(nums[1::2])
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def _shape_el(name, ds, W, H):
    x0, y0, x1, y1 = _bbox_of(ds)
    x0, y0 = max(x0, -W), max(y0, -H)
    w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    return {"type": "shape", "name": name,
            "paths": [{"d": d, "fill": {"color": col}} for d, col in ds],
            "viewBox": {"left": round(x0, 2), "top": round(y0, 2), "width": round(w, 2), "height": round(h, 2)},
            "left": round(x0, 2), "top": round(y0, 2), "width": round(w, 2), "height": round(h, 2)}


def _fits(ds):
    return (len(ds) <= MAX_PATHS and len({c for _, c in ds}) <= MAX_COLORS
            and sum(len(d) for d, _ in ds) <= MAX_D)


def _chunks(ds):
    """Split a too-big object into several native shapes, each within Canva's limits."""
    out, cur = [], []
    for item in ds:
        if len(item[0]) > MAX_D:
            return None
        trial = cur + [item]
        if _fits(trial):
            cur = trial
        else:
            if cur:
                out.append(cur)
            cur = [item]
    if cur:
        out.append(cur)
    return out


def _png_data_url(path, bbox=None):
    im = Image.open(path).convert("RGBA")
    if bbox is not None:
        x, y, w, h = bbox
        im = im.crop((x, y, x + w, y + h))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _split_region_paths(r, W, H, c, depth=0):
    """Bidang yang outline-nya melebihi batas 2 kB dibelah dua (sumbu terpanjang, tumpang 2 px
    supaya tidak ada celah) berulang sampai tiap keping muat. Warna sama, jadi tetap tampak utuh."""
    m = r["filled"]
    ys, xs = np.nonzero(m)
    if not len(ys):
        return []
    for scale in (1.0, 2.0, 3.5):
        pr = region_paths(dict(r, shape=("path", None, None)), W, H, c, eps_scale=scale)
        if pr and all(len(d) <= MAX_D for d, _ in pr):
            return pr
    if depth >= 10:
        return None
    a, b = dict(r), dict(r)
    if ys.max() - ys.min() >= xs.max() - xs.min():
        mid = (ys.min() + ys.max()) // 2
        ma, mb = m.copy(), m.copy()
        ma[mid + 2:, :] = False
        mb[:max(mid - 1, 0), :] = False
    else:
        mid = (xs.min() + xs.max()) // 2
        ma, mb = m.copy(), m.copy()
        ma[:, mid + 2:] = False
        mb[:, :max(mid - 1, 0)] = False
    out = []
    for part, mm in ((a, ma), (b, mb)):
        part["filled"] = mm
        got = _split_region_paths(part, W, H, c, depth + 1)
        if got is None:
            return None
        out += got
    return out


def _never_image_elements(L, regs, W, H, c, warnings):
    """Mode VECTALLY tanpa PNG: 1 path = 1 shape (bisa dirapikan mesin smooth), dibungkus 1 grup
    per objek. Bidang yang path-nya terlalu panjang dicoba lagi tanpa lubang (bentuk di atasnya
    menutup lubang itu), lalu disederhanakan bertahap."""
    from scipy import ndimage as _ndi
    kids, lost = [], 0
    for k, r in enumerate(regs):
        got = None
        for variant in (r, dict(r, filled=_ndi.binary_fill_holes(r["filled"]))):
            for scale in (1.0, 2.0, 3.5, 6.0, 10.0, 16.0):
                pr = region_paths(variant, W, H, c, eps_scale=scale)
                if pr and all(len(d) <= MAX_D for d, _ in pr):
                    got = pr
                    break
            if got:
                break
        if not got:
            # terakhir: potong bidang (tanpa lubang) jadi beberapa keping yang masing-masing muat
            got = _split_region_paths(dict(r, filled=_ndi.binary_fill_holes(r["filled"])), W, H, c)
        if not got:
            lost += 1
            continue
        for j, item in enumerate(got):
            kids.append(_shape_el(f"{L['name']}_r{k + 1}_{j + 1}", [item], W, H))
    if lost:
        warnings.append(f"{L['name']}: {lost} bidang terlalu rumit untuk shape dan DILEWATI (cek QA)")
    if len(kids) <= 1:
        return kids
    x0 = min(e["left"] for e in kids); y0 = min(e["top"] for e in kids)
    x1 = max(e["left"] + e["width"] for e in kids); y1 = max(e["top"] + e["height"] for e in kids)
    for e in kids:
        e["left"] = round(e["left"] - x0, 2); e["top"] = round(e["top"] - y0, 2)
    return [{"type": "group", "name": L["name"], "left": round(x0, 2), "top": round(y0, 2),
             "width": round(x1 - x0, 2), "height": round(y1 - y0, 2), "children": kids}]


def vector_layer_elements(L, W, H, c, out, warnings):
    """Native shape element(s) for one vector layer, or an image fallback."""
    regs = sorted([r for r in L["regions"] if not r.get("_drop")], key=lambda r: r["z"])
    never = bool(c.get("canva_never_image", False))
    if never:
        return _never_image_elements(L, regs, W, H, c, warnings)
    for scale in (1.0, 2.0, 3.5):
        ds, ok = [], True
        for r in regs:
            pr = region_paths(r, W, H, c, eps_scale=scale)
            if pr is None:
                ok = False
                break
            ds += pr
        if not ok:
            break
        if not ds:
            return []
        if _fits(ds):
            return [_shape_el(L["name"], ds, W, H)]
        parts = _chunks(ds)
        if parts and len(parts) <= c.canva_max_split:
            if scale == 1.0 and len(parts) > 1:
                continue  # first try a simpler outline that may fit in one shape
            warnings.append(f"{L['name']}: dipecah jadi {len(parts)} shape (batas Canva 30 path / 6 warna / 2 kB)")
            return [_shape_el(f"{L['name']}_{i + 1}", p, W, H) for i, p in enumerate(parts)]
    reason = "gradien" if not ok else "terlalu rumit"
    warnings.append(f"{L['name']}: dikirim sebagai gambar ({reason}), warnanya tidak bisa diganti per bagian")
    x, y, w, h = L["bbox"]
    return [{"type": "image", "name": L["name"], "dataUrl": _png_data_url(out / "layers" / f"{L['name']}.png", L["bbox"]),
             "left": x, "top": y, "width": w, "height": h}]


def text_element(b):
    size = int(b["canva_font_size"])
    text = str(b["text"])
    letters = [ch for ch in text if ch.isalpha()]
    caps = bool(letters) and sum(ch.isupper() for ch in letters) >= 0.8 * len(letters)
    nl = text.count("\n") + 1
    return {"type": "text", "name": f"text_{b['id']}", "text": text,
            "left": int(b["x"]), "top": int(round(b["y"] - 0.2 * size)),
            "width": int(round(max(b["w"] * 1.12, size * 1.2))),
            "fontSize": max(1, min(size, 1000)), "color": str(b["color_hex"]).lower(),
            "fontWeight": "bold" if caps or b["h"] / nl > 60 else "normal", "textAlign": "start"}


def _cover_glyphs(layers, blocks, text_mask, W, H):
    """Mode tanpa PNG: piksel huruf (yang kini jadi teks native) diberikan ke bidang yang paling
    menguasai kotak teks itu, supaya tidak ada lubang/bekas bentuk huruf lama di bawah teks Canva."""
    regs = [(li, r) for li, L in enumerate(layers) if L["type"] == "vector"
            for r in L["regions"] if r["shape"][0] != "canvas"]
    # bercak sisa hapusan huruf: bidang kecil yang >= 60% berada di atas piksel huruf dibuang
    # (tempatnya ditutup bidang latar di bawah, yang menerima piksel huruf di bawah ini)
    for _, r in regs:
        sl, m = r["sl"], r["filled"]
        tm = text_mask[sl[0].start:sl[0].start + m.shape[0], sl[1].start:sl[1].start + m.shape[1]]
        if tm.shape == m.shape and m.any() and m.sum() < 0.02 * W * H and (tm & m).sum() >= 0.6 * m.sum():
            r["_drop"] = True
    regs = [(li, r) for li, r in regs if not r.get("_drop")]
    for b in blocks:
        x, y, w, h = [int(v) for v in b.get("ocr_bbox", (b["x"], b["y"], b["w"], b["h"]))]
        p = max(4, int(0.15 * h))
        X0, Y0, X1, Y1 = max(x - p, 0), max(y - p, 0), min(x + w + p, W), min(y + h + p, H)
        g = text_mask[Y0:Y1, X0:X1]
        if not g.any():
            continue
        cand = []
        for li, r in regs:
            sl, m = r["sl"], r["filled"]
            ys0, xs0 = max(Y0, sl[0].start), max(X0, sl[1].start)
            ys1, xs1 = min(Y1, sl[0].start + m.shape[0]), min(X1, sl[1].start + m.shape[1])
            if ys1 <= ys0 or xs1 <= xs0:
                continue
            sub = m[ys0 - sl[0].start:ys1 - sl[0].start, xs0 - sl[1].start:xs1 - sl[1].start]
            n = int((sub & ~g[ys0 - Y0:ys1 - Y0, xs0 - X0:xs1 - X0]).sum())
            if n:
                cand.append((li, r.get("z", 0), n, r))
        if not cand:
            continue
        # bidang latar = layer paling BAWAH yang cukup menguasai kotak, supaya objek di atasnya
        # (jam, ikon) tidak tertutup piksel huruf yang ditambahkan
        top = max(n for _, _, n, _ in cand)
        best = min((c_ for c_ in cand if c_[2] >= 0.3 * top), key=lambda t: (t[0], t[1]))[3]
        sl, m = best["sl"], best["filled"]
        ny0, nx0 = min(sl[0].start, Y0), min(sl[1].start, X0)
        ny1, nx1 = max(sl[0].start + m.shape[0], Y1), max(sl[1].start + m.shape[1], X1)
        big = np.zeros((ny1 - ny0, nx1 - nx0), bool)
        big[sl[0].start - ny0:sl[0].start - ny0 + m.shape[0], sl[1].start - nx0:sl[1].start - nx0 + m.shape[1]] = m
        big[Y0 - ny0:Y1 - ny0, X0 - nx0:X1 - nx0] |= g
        best["filled"] = big
        best["sl"] = (slice(ny0, ny1), slice(nx0, nx1))
        if best["shape"][0] != "path":
            best["shape"] = ("path", None, None)


def write(out, src, W, H, layers, blocks, c, text_mask=None):
    els, warnings = [], []
    if c.get("canva_never_image", False) and blocks and text_mask is not None:
        _cover_glyphs(layers, blocks, text_mask, W, H)
    for L in layers:
        if L["type"] == "vector":
            els += vector_layer_elements(L, W, H, c, out, warnings)
        else:
            x, y, w, h = L["bbox"]
            els.append({"type": "image", "name": L["name"],
                        "dataUrl": _png_data_url(out / "canva" / L["file"].split("/")[-1]),
                        "left": x, "top": y, "width": w, "height": h})
    for b in blocks:
        els.append(text_element(b))
    warnings.append("font asli tidak bisa dikenali: teks memakai font bawaan Canva, ganti font sesuai selera")
    n_shape = sum(e["type"] == "shape" for e in els)
    n_img = sum(e["type"] == "image" for e in els)
    n_txt = sum(e["type"] == "text" for e in els)
    pkg = {"format": "cusbe-canva-package", "version": 1, "source": src.name,
           "width": W, "height": H, "elements": els, "warnings": warnings,
           "summary": {"shape": n_shape, "image": n_img, "text": n_txt}}
    (out / "CANVA_PACKAGE.json").write_text(json.dumps(pkg, ensure_ascii=False), encoding="utf-8")
    log.info("  paket Canva: %d shape asli, %d gambar, %d teks", n_shape, n_img, n_txt)
    return pkg

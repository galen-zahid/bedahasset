"""Mesin inventory VECTALLY: inventory JSON (keputusan semantik) -> paket Canva native per benda.

Pembagian kerja (metode Codex, tanpa resep Python per desain):
  - Inventory (ditulis sekali per desain oleh AI/manusia): daftar benda belakang->depan, ROI kasar,
    titik contoh warna badan (seeds), cara fit badan, dan area teks yang dikecualikan.
  - Mesin ini (otomatis, tanpa AI): mengukur badan utuh dari piksel sumber di dalam ROI, melanjutkan
    bagian tertutup sesuai jenis fit, menentukan pemilik tiap piksel menurut urutan z, lalu detail
    (warna lain di atas badan) menjadi child grup benda itu.

Format inventory (lihat vectally/inventory/*.json):
{
  "source": "path PNG (relatif ke D:/bedahasset/vectally atau absolut)",
  "background": [x, y],                 # titik contoh warna latar
  "objects": [                          # urutan = belakang -> depan
    {"id": "map_hijau", "roi": [x0,y0,x1,y1] | [[x,y],...], "seeds": [[x,y],...],
     "fit": "auto|hull|poly:N|rect|ellipse", "tol": 14, "details": true},
    ...
  ],
  "text": [ {"roi": [...], "seed": [x,y]} ]   # tinta teks: tidak jadi badan/detail
}
Pemakaian: python inventory_engine.py <inventory.json> <out_dir>
"""
import io
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import resvg_py
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MAX_D = 1850          # batas byte path yang lolos impor Canva
MIN_DETAIL = 30       # px; detail lebih kecil dibuang (debu anti-alias)


# ------------------------------------------------------------------ util warna / mask
def lab(img_rgb):
    return cv2.cvtColor(img_rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2Lab)


def hexc(rgb):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def roi_mask(roi, H, W):
    m = np.zeros((H, W), np.uint8)
    if isinstance(roi[0], (int, float)):
        x0, y0, x1, y1 = roi
        m[max(0, int(y0)):int(y1), max(0, int(x0)):int(x1)] = 1
    else:
        cv2.fillPoly(m, [np.array(roi, np.int32)], 1)
    return m.astype(bool)


def fill_holes(m):
    p = np.pad(m.astype(np.uint8), 1)
    cv2.floodFill(p, None, (0, 0), 2)
    return (p[1:-1, 1:-1] != 2)


def keep_seeded(m, seeds):
    n, lab_, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    keep = np.zeros(n, bool)
    for x, y in seeds:
        if 0 <= y < m.shape[0] and 0 <= x < m.shape[1] and lab_[y, x] > 0:
            keep[lab_[y, x]] = True
    if not keep.any() and n > 1:  # seed jatuh di tepi: ambil komponen terbesar
        keep[1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))] = True
    return keep[lab_]


# ------------------------------------------------------------------ path
def fmt(v):
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def poly_d(pts):
    return "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in pts) + " Z"


def ellipse_d(cx, cy, rx, ry, ang):
    k = 0.5523
    ca, sa = math.cos(ang), math.sin(ang)
    P = lambda x, y: (cx + x * ca - y * sa, cy + x * sa + y * ca)  # noqa: E731
    q = [P(rx, 0), P(rx, k * ry), P(k * rx, ry), P(0, ry), P(-k * rx, ry), P(-rx, k * ry), P(-rx, 0),
         P(-rx, -k * ry), P(-k * rx, -ry), P(0, -ry), P(k * rx, -ry), P(rx, -k * ry), P(rx, 0)]
    d = f"M{fmt(q[0][0])} {fmt(q[0][1])}"
    for i in range(1, 13, 3):
        d += " C" + " ".join(f"{fmt(a)} {fmt(b)}" for a, b in q[i:i + 3])
    return d + " Z"


def contour_d(cnt, eps0=1.0):
    eps = eps0
    while True:
        q = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2).astype(float)
        if len(q) < 3:
            return None
        d = poly_d(q)
        if len(d) <= MAX_D or eps > 6:
            return d
        eps *= 1.35


def raster(d, H, W):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}"><path d="{d}" fill="#000"/></svg>'
    a = np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("RGBA"))[:, :, 3]
    return a >= 128


def fit_shape(mask, how, H, W):
    """Badan -> daftar path d (koordinat absolut) + mask hasil fit."""
    m8 = mask.astype(np.uint8)
    cnts, _ = cv2.findContours(m8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnts = [c for c in cnts if cv2.contourArea(c) >= MIN_DETAIL]
    if not cnts:
        return [], np.zeros((H, W), bool)
    allp = np.vstack(cnts)
    ds = []
    if how == "ellipse" and len(allp) >= 5:
        (cx, cy), (a, b), ang = cv2.fitEllipse(allp)
        ds = [ellipse_d(cx, cy, a / 2, b / 2, math.radians(ang))]
    elif how == "rect":
        ds = [poly_d(cv2.boxPoints(cv2.minAreaRect(allp)))]
    elif how == "hull" or how.startswith("poly"):
        hull = cv2.convexHull(allp)
        if how.startswith("poly"):
            n = int(how.split(":")[1])
            eps = 1.0
            q = cv2.approxPolyDP(hull, eps, True)
            while len(q) > n and eps < 200:
                eps *= 1.25
                q = cv2.approxPolyDP(hull, eps, True)
            hull = q
        ds = [poly_d(hull.reshape(-1, 2))]
    else:  # auto: siluet yang terlihat, tepi dirapikan
        for c in cnts:
            d = contour_d(c, 1.4)
            if d:
                ds.append(d)
    fm = np.zeros((H, W), bool)
    for d in ds:
        fm |= raster(d, H, W)
    return ds, fm


# ------------------------------------------------------------------ paket
def shape_el(name, d, color):
    nums = [float(v) for v in __import__("re").findall(r"-?\d+(?:\.\d+)?", d)]
    xs, ys = nums[0::2], nums[1::2]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
    return dict(type="shape", name=name, viewBox=dict(left=x0, top=y0, width=w, height=h),
                left=x0, top=y0, width=w, height=h, paths=[dict(d=d, fill=dict(color=color))])


def group_el(name, children):
    x0 = min(c["left"] for c in children)
    y0 = min(c["top"] for c in children)
    x1 = max(c["left"] + c["width"] for c in children)
    y1 = max(c["top"] + c["height"] for c in children)
    for c in children:
        c["left"] -= x0
        c["top"] -= y0
    return dict(type="group", name=name, left=x0, top=y0, width=x1 - x0, height=y1 - y0, children=children)


# ------------------------------------------------------------------ mesin
def build(inv_path, out_dir):
    inv = json.loads(Path(inv_path).read_text(encoding="utf-8"))
    src = Path(inv["source"])
    if not src.is_absolute():
        src = ROOT / src
    rgb = np.asarray(Image.open(src).convert("RGB"))
    H, W = rgb.shape[:2]
    flat = cv2.pyrMeanShiftFiltering(np.ascontiguousarray(rgb), 5, 12)   # gradien/noise diratakan
    L = lab(flat)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # tinta teks: dikecualikan dari badan dan detail
    textpix = np.zeros((H, W), bool)
    for t in inv.get("text", []):
        r = roi_mask(t["roi"], H, W)
        c = L[t["seed"][1], t["seed"][0]]
        textpix |= r & (np.linalg.norm(L - c, axis=2) < t.get("tol", 20))
    textpix = cv2.dilate(textpix.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0

    bx, by = inv["background"]
    bg_col = np.median(flat[np.linalg.norm(L - L[by, bx], axis=2) < 6], 0)
    objs = inv["objects"]
    fits, cols, report = [], [], []
    for o in objs:
        r = roi_mask(o["roi"], H, W)
        tol = o.get("tol", 14)
        seedL = [L[y, x] for x, y in o["seeds"]]
        match = np.zeros((H, W), bool)
        for c in seedL:
            match |= np.linalg.norm(L - c, axis=2) < tol
        m = r & (match | textpix)
        m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)) > 0
        m = keep_seeded(m & r, o["seeds"])
        m = fill_holes(m) & r if o.get("fill_holes", True) else m
        if o.get("fit") == "roi":  # garis tepi ditulis di inventory (benda putih di atas latar putih)
            ds = [poly_d(o["roi"])] if not isinstance(o["roi"][0], (int, float)) else [
                poly_d([(o["roi"][0], o["roi"][1]), (o["roi"][2], o["roi"][1]), (o["roi"][2], o["roi"][3]), (o["roi"][0], o["roi"][3])])]
            fm = raster(ds[0], H, W)
        else:
            ds, fm = fit_shape(m, o.get("fit", "auto"), H, W)
        fm &= r if o.get("clip_roi", True) else fm
        sel = m & ~textpix
        col = np.median(flat[sel], 0) if sel.sum() > 20 else flat[o["seeds"][0][1], o["seeds"][0][0]]
        fits.append((ds, fm))
        cols.append(col)
        report.append(dict(id=o["id"], fit=o.get("fit", "auto"), visible_px=int(m.sum()), body_px=int(fm.sum()),
                           paths=len(ds), color=hexc(col)))

    # pemilik piksel = benda paling depan yang badannya menutup piksel itu
    owner = np.full((H, W), -1, np.int32)
    for i, (_, fm) in enumerate(fits):
        owner[fm] = i

    # kuantisasi warna untuk detail
    samp = L.reshape(-1, 3)[:: 17].astype(np.float32)
    K = inv.get("detail_colors", 20)
    _, _, centers = cv2.kmeans(samp, K, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5),
                               3, cv2.KMEANS_PP_CENTERS)
    dist = np.stack([np.linalg.norm(L - c, axis=2) for c in centers], 0)
    qlab = np.argmin(dist, 0)
    qlab = cv2.medianBlur(qlab.astype(np.uint8), 5)

    elements = [shape_el("Latar", poly_d([(0, 0), (W, 0), (W, H), (0, H)]), hexc(bg_col))]
    for i, o in enumerate(objs):
        ds, fm = fits[i]
        if not ds:
            continue
        col = cols[i]
        kids = [shape_el(f"{o['id']}_badan_{k + 1}", d, hexc(col)) for k, d in enumerate(ds)]
        if o.get("details", True):
            own = (owner == i)
            own = cv2.erode(own.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            diff = np.linalg.norm(L - lab(np.array([[col]], np.uint8))[0, 0], axis=2) > o.get("detail_tol", 16)
            dm = own & diff & ~textpix
            parts = []
            for q in np.unique(qlab[dm]):
                mq = (dm & (qlab == q)).astype(np.uint8)
                mq = cv2.morphologyEx(mq, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
                cnts, _ = cv2.findContours(mq, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
                for c in cnts:
                    a = cv2.contourArea(c)
                    if a < MIN_DETAIL or a / max(1.0, cv2.arcLength(c, True)) < 0.9:  # terlalu tipis = garis tepi AA
                        continue
                    cm = np.zeros((H, W), np.uint8)
                    cv2.drawContours(cm, [c], -1, 1, -1)
                    dcol = hexc(np.median(flat[(cm > 0) & dm], 0)) if ((cm > 0) & dm).sum() > 5 else hexc(flat[c[0][0][1], c[0][0][0]])
                    # primitif bila cocok: persegi miring atau elips
                    rect = cv2.minAreaRect(c)
                    rw, rh = rect[1]
                    d = None
                    if rw * rh > 0 and a / (rw * rh) > 0.92:
                        d = poly_d(cv2.boxPoints(rect))
                    elif len(c) >= 5:
                        (ex, ey), (ea, eb), ang = cv2.fitEllipse(c)
                        if ea * eb > 0 and abs(a / (math.pi * ea * eb / 4) - 1) < 0.05:
                            dd = ellipse_d(ex, ey, ea / 2, eb / 2, math.radians(ang))
                            got = raster(dd, H, W)
                            if (got & (cm > 0)).sum() / max(1, (got | (cm > 0)).sum()) > 0.9:
                                d = dd
                    d = d or contour_d(c, 1.0)
                    if d:
                        parts.append((a, shape_el(f"{o['id']}_detail", d, dcol)))
            parts.sort(key=lambda t: -t[0])          # besar dulu, kecil di atasnya
            for k, (_, e) in enumerate(parts):
                e["name"] = f"{o['id']}_detail_{k + 1}"
                kids.append(e)
            report[i]["details"] = len(parts)
        elements.append(group_el(o.get("name", o["id"]), kids) if len(kids) > 1 else kids[0])

    pkg = dict(format="cusbe-canva-package", version=1, source=f"{inv.get('code', src.stem)} - VECTALLY inventory engine",
               width=W, height=H, elements=elements,
               summary=dict(shape=sum(1 for _ in leaves(elements)), group=sum(1 for e in elements if e["type"] == "group"),
                            text=0, image=0),
               warnings=["Artwork tanpa copy; teks native ditambahkan pada tahap teks."])
    (out / "CANVA_PACKAGE.json").write_text(json.dumps(pkg, ensure_ascii=False), encoding="utf-8")
    (out / "BUILD_REPORT.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    sys.path.insert(0, str(HERE))
    import render_package_svg as R
    R.render(pkg).save(out / "ARTWORK.png")
    return pkg, report


def leaves(es):
    for e in es:
        if e["type"] == "group":
            yield from leaves(e["children"])
        else:
            yield e


if __name__ == "__main__":
    pkg, rep = build(sys.argv[1], sys.argv[2])
    print(json.dumps(pkg["summary"]))
    for r in rep:
        print(r)

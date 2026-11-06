"""Rebuild step 3: photos, the ONE effect layer, and the Canva package.

out/<design>/
    canva/            1 file per layer, cropped to the object (drag these into Canva)
    vectors/          the same vector layers as full-canvas SVG (stack 1:1 at x=0,y=0)
    layers/           every layer as full-canvas PNG
    CANVA_IMPORT.pdf  the whole design in one file: Canva -> Upload -> PDF = editable layers
    scene.svg         everything (vectors + photos + text) for Figma / Illustrator
    text.csv          native text: words, position, colour, suggested Canva font size
    manifest.csv/json layer list (file, position, size, z order, colours)
    preview.png       original | rebuild,   sheet.png all layers
    CARA_IMPORT_CANVA.txt
"""
from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .. import matting
from ..imageio import to_u8
from . import shapes

log = logging.getLogger("split")


# ------------------------------------------------------------------------------ photos
def photo_layers(img, photo, models, cfg, sal=None):
    """Photo areas stay photos. With models: person/product (subject) split from the photo
    background, the hole behind the subject inpainted."""
    H, W = photo.shape
    a = matting.feather(photo.astype(np.float32), 0.8)
    out = []
    if models is not None:
        try:
            if sal is None:
                sal = models.salient_mask(to_u8(img))
            subj = np.clip(sal, 0, 1) * photo
            if (subj > 0.5).sum() > 0.01 * H * W:
                # generous hole: hair wisps, soft shadow and chalk dust go too (no ghost of the person)
                pc = cfg.rebuild
                hole = matting.dilate(subj > pc.subject_hole_thr, int(pc.subject_hole_px)) & photo
                bg = models.inpaint(to_u8(img), (hole * 255).astype(np.uint8)).astype(np.float32) / 255.0
                rest = photo & ~(subj > 0.5)
                if rest.sum() > 0.02 * H * W:
                    out.append(dict(name="photo_background", rgb=bg, alpha=a, where="bottom"))
                    out.append(dict(name="photo_subject", rgb=matting.decontaminate(img, subj), alpha=subj,
                                    where="top"))
                else:
                    out.append(dict(name="photo_subject", rgb=img, alpha=np.maximum(subj, a * (subj > 0.02)),
                                    where="top"))
                return out
        except Exception as e:  # noqa: BLE001
            log.warning("  pemisahan subject foto gagal (%s); foto jadi 1 layer", e)
    # big separate photos get their own layer; every small piece goes into one shared layer
    n, lab, st, _ = cv2.connectedComponentsWithStats(photo.astype(np.uint8))
    big = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= 0.05 * H * W]
    rest = np.isin(lab, [i for i in range(1, n) if i not in big])
    for k, i in enumerate(big, 1):
        out.append(dict(name=f"photo_{k}", rgb=img, alpha=a * (lab == i), where="bottom"))
    if rest.any():
        out.append(dict(name="photo_bits" if big else "photo", rgb=img, alpha=a * rest, where="bottom"))
    return out


# ------------------------------------------------------------------------------- svg
def _svg(W, H, body, defs=""):
    d = f"<defs>{defs}</defs>\n" if defs else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">\n{d}{body}\n</svg>\n')


def region_xml(r, W, H, c):
    kind, p, _ = r["shape"]
    fill, defs = shapes.fill_attr(r["fill"], f"g{r['z']}")
    if kind == "canvas":
        return f'<rect width="{W}" height="{H}" {fill}/>', defs
    sl = r["sl"]
    oy, ox = sl[0].start, sl[1].start
    m = r["filled"]
    if kind == "path" and c.overlap_px > 0:  # neighbours overlap a hair: no seams in Canva
        pad = int(c.overlap_px) + 1
        m = matting.dilate(np.pad(m, pad), int(c.overlap_px))
        ox, oy = ox - pad, oy - pad
    return shapes.shape_xml(kind, p, m, ox, oy, fill, c), defs


def object_svg(o, W, H, c):
    body, defs = [], []
    for r in o["regions"]:
        x, d = region_xml(r, W, H, c)
        if x:
            body.append(x)
            if d:
                defs.append(d)
    return _svg(W, H, "\n".join(body), "".join(defs))


def crop_svg(svg, bb):
    x, y, w, h = bb
    return re.sub(r'width="\d+" height="\d+" viewBox="0 0 \d+ \d+"',
                  f'width="{w}" height="{h}" viewBox="{x} {y} {w} {h}"', svg, count=1)


def render(svg, W, H):
    import resvg_py

    im = Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg)))).convert("RGBA")
    a = np.asarray(im, np.float32) / 255.0
    return a[..., :3], a[..., 3]  # PNG from resvg = straight (not premultiplied) alpha


def _over(dst, rgb, a):
    return dst * (1 - a[..., None]) + rgb * a[..., None]


def _bbox(a, thr=0.004, pad=1):
    ys, xs = np.nonzero(a > thr)
    if not len(xs):
        return None
    H, W = a.shape
    x0, y0 = max(int(xs.min()) - pad, 0), max(int(ys.min()) - pad, 0)
    x1, y1 = min(int(xs.max()) + 1 + pad, W), min(int(ys.max()) + 1 + pad, H)
    return x0, y0, x1 - x0, y1 - y0


# --------------------------------------------------------------------------- effects
def effect_layer(orig, base, lab, text_mask, c, text_zone=None, clean_zone=None):
    """The ONE general effect layer: the smallest-alpha overlay (normal blend) that turns the
    vector + photo rebuild into the original: glows, soft shadows, texture, sheen."""
    O, B = orig.astype(np.float64), base.astype(np.float64)
    up = np.where(O > B, (O - B) / np.maximum(1 - B, 1e-4), 0)
    dn = np.where(O < B, (B - O) / np.maximum(B, 1e-4), 0)
    a = np.clip(np.maximum(up, dn).max(-1), 0, 1)
    a[a < c.fx_min_alpha] = 0
    edges = np.zeros(lab.shape, bool)
    edges[:, 1:] |= lab[:, 1:] != lab[:, :-1]
    edges[1:, :] |= lab[1:, :] != lab[:-1, :]
    a[matting.dilate(edges, int(c.fx_edge_px))] = 0          # no outlines of mismatched edges
    a[matting.dilate(text_mask, 2)] = 0                      # text is native in Canva
    if text_zone is not None:
        a[text_zone] = 0
    if clean_zone is not None:  # rebuilt stripes stay clean: no copied grunge / torn bits on them
        a[clean_zone] = 0
    if c.fx_open_px > 0:  # thin leftovers = outlines of shapes, not effects
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(c.fx_open_px) + 1,) * 2)
        keep = cv2.morphologyEx((a > 0).astype(np.uint8), cv2.MORPH_OPEN, k)
        keep = cv2.dilate(keep, k).astype(bool)
        a[~keep] = 0
    n, cl, st, _ = cv2.connectedComponentsWithStats((a > 0).astype(np.uint8), connectivity=8)
    small = st[:, cv2.CC_STAT_AREA] < c.fx_min_px
    small[0] = False
    a[small[cl]] = 0
    safe = np.maximum(a, 1e-4)[..., None]
    rgb = np.clip(B + (O - B) / safe, 0, 1)
    if text_zone is not None and text_zone.any():
        # around the letters the effect (glow, sheen) simply continues from its surroundings;
        # the letters' own shadow is not copied
        hole = (text_zone | matting.dilate(text_mask, 2)).astype(np.uint8)
        H, W = a.shape
        sw, sh = max(W // 4, 1), max(H // 4, 1)
        pm = np.dstack([rgb * a[..., None], a[..., None]]).astype(np.float32)
        small = cv2.resize(pm, (sw, sh), interpolation=cv2.INTER_AREA)
        hs = cv2.resize(hole, (sw, sh), interpolation=cv2.INTER_NEAREST)
        filled = np.dstack([cv2.inpaint(to_u8(small[..., i]), hs, 5, cv2.INPAINT_TELEA) for i in range(4)])
        up = cv2.resize(filled, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        hb = hole.astype(bool)
        a = np.where(hb, np.clip(up[..., 3], 0, 1), a)
        rgb = np.where(hb[..., None], np.clip(up[..., :3] / np.maximum(up[..., 3:4], 1e-3), 0, 1), rgb)
        a[a < c.fx_min_alpha] = 0
    return rgb.astype(np.float32), a.astype(np.float32)


# ------------------------------------------------------------------------------ text
_FONTS = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]


def _font(size):
    for f in _FONTS:
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _bbox_lines(f, lines):
    ws = [f.getbbox(s)[2] - f.getbbox(s)[0] for s in lines if s] or [0]
    return max(ws)


def fit_text(b):
    """Font size so the text fills its box width (what to type in Canva's size field)."""
    lines = [s for s in str(b["text"]).split("\n") if s] or [" "]
    nl = len(lines)
    size = max(6, int(b.get("est_font_size_px", b["h"] / max(nl, 1))))
    for _ in range(6):
        f = _font(size)
        wmax = _bbox_lines(f, lines)
        if wmax <= 0:
            break
        new = int(round(size * b["w"] / wmax))
        new = int(np.clip(new, 0.5 * size, 2.0 * size))
        if nl > 1:  # several lines must also fit the box height
            new = min(new, int(b["h"] / (nl * 1.15)) + 1)
        if abs(new - size) <= 1:
            size = new
            break
        size = new
    return max(6, size)


def draw_text(canvas_u8, blocks):
    im = Image.fromarray(canvas_u8)
    d = ImageDraw.Draw(im)
    for b in blocks:
        size = b.get("canva_font_size") or fit_text(b)
        f = _font(size)
        lines = str(b["text"]).split("\n")
        y = b["y"]
        step = b["h"] / max(len(lines), 1)
        for ln in lines:
            if ln:
                bb = f.getbbox(ln)
                d.text((b["x"] - bb[0], y - bb[1]), ln, font=f, fill=b["color_hex"])
            y += step
    return np.asarray(im)


# ------------------------------------------------------------------------------- pdf
_CMD = re.compile(r"([MLCZ])([^MLCZ]*)")


def _pdf_path(cv, d, ox=0.0, oy=0.0):
    p = cv.beginPath()
    for cmd, args in _CMD.findall(d):
        v = [float(t) for t in args.replace(",", " ").split()]
        if cmd == "M":
            p.moveTo(v[0] + ox, v[1] + oy)
        elif cmd == "L":
            p.lineTo(v[0] + ox, v[1] + oy)
        elif cmd == "C":
            p.curveTo(v[0] + ox, v[1] + oy, v[2] + ox, v[3] + oy, v[4] + ox, v[5] + oy)
        else:
            p.close()
    return p


def _rl_color(col):
    from reportlab.lib.colors import Color

    col = np.clip(np.asarray(col, np.float64), 0, 1)
    return Color(*col)


def _pdf_region(cv, r, W, H, c):
    kind, p, _ = r["shape"]
    f = r["fill"]
    sl = r["sl"]
    oy, ox = sl[0].start, sl[1].start
    cv.saveState()
    if kind == "canvas":
        path = cv.beginPath()
        path.rect(0, 0, W, H)
    elif kind == "rect":
        cv.translate(p["cx"] + ox, p["cy"] + oy)
        cv.rotate(p["ang"])
        path = cv.beginPath()
        if p["r"] >= 0.75:
            path.roundRect(-p["w"] / 2, -p["h"] / 2, p["w"], p["h"], p["r"])
        else:
            path.rect(-p["w"] / 2, -p["h"] / 2, p["w"], p["h"])
    elif kind == "ellipse":
        cv.translate(p["cx"] + ox, p["cy"] + oy)
        cv.rotate(p["ang"])
        path = cv.beginPath()
        path.ellipse(-p["rx"], -p["ry"], 2 * p["rx"], 2 * p["ry"])
    elif kind == "polygon":
        path = cv.beginPath()
        pts = p["pts"]
        path.moveTo(pts[0][0] + ox, pts[0][1] + oy)
        for x, y in pts[1:]:
            path.lineTo(x + ox, y + oy)
        path.close()
    elif kind == "stroke":
        d = shapes._smooth_open(p["pts"] + [ox, oy], c.corner_deg)
        path = _pdf_path(cv, d)
        col = f["color"] if f["kind"] == "solid" else np.mean([s[2] for s in f["stops"]], 0)
        cv.setStrokeColor(_rl_color(col))
        cv.setLineWidth(p["w"])
        cv.setLineCap(1)
        cv.setLineJoin(1)
        cv.drawPath(path, stroke=1, fill=0)
        cv.restoreState()
        return
    else:
        m = r["filled"]
        pad = int(c.overlap_px) + 1
        if c.overlap_px > 0:
            m = matting.dilate(np.pad(m, pad), int(c.overlap_px))
            ox, oy = ox - pad, oy - pad
        d = shapes.bezier_outline(m, c.anchor_eps, c.corner_deg, c.smooth)
        if not d:
            cv.restoreState()
            return
        path = _pdf_path(cv, d, ox, oy)
    if f["kind"] == "solid":
        cv.setFillColor(_rl_color(f["color"]))
        cv.drawPath(path, stroke=0, fill=1, fillMode=1)
    else:
        (x1, y1, c1), (x2, y2, c2) = f["stops"]
        cv.clipPath(path, stroke=0, fill=0, fillMode=1)
        stops = f.get("mid") or [(0.0, c1), (1.0, c2)]
        cv.linearGradient(x1, y1, x2, y2, [_rl_color(col) for _, col in stops],
                          [o for o, _ in stops], extend=True)
    cv.restoreState()


def write_pdf(path, W, H, layers, blocks, c):
    """Whole design as one PDF (vectors stay vectors, photos are images, text is text)."""
    from reportlab.pdfgen import canvas as rlc
    from reportlab.lib.utils import ImageReader

    cv = rlc.Canvas(str(path), pagesize=(W, H))
    cv.transform(1, 0, 0, -1, 0, H)  # SVG-like coordinates (y down)
    for L in layers:
        if L["type"] == "vector":
            for r in L["regions"]:
                if r["fill"]["kind"] == "linear" and r["shape"][0] in ("rect", "ellipse"):
                    r = dict(r, shape=("path", {}, 1.0))  # gradients need canvas coordinates
                _pdf_region(cv, r, W, H, c)
        else:
            x, y, w, h = L["bbox"]
            rgba = Image.open(L["png_crop"])
            cv.saveState()
            cv.translate(x, y + h)
            cv.scale(1, -1)
            cv.drawImage(ImageReader(rgba), 0, 0, w, h, mask="auto")
            cv.restoreState()
    for b in blocks:
        cv.saveState()
        size = b["canva_font_size"]
        cv.translate(b["x"], b["y"] + b["h"])
        cv.scale(1, -1)
        cv.setFillColor(_rl_color(np.array([int(b["color_hex"][i:i + 2], 16) for i in (1, 3, 5)]) / 255))
        cv.setFont("Helvetica-Bold", size)
        lines = str(b["text"]).split("\n")
        step = b["h"] / max(len(lines), 1)
        for i_, ln in enumerate(lines):
            cv.drawString(0, (len(lines) - 1 - i_) * step, ln)
        cv.restoreState()
    cv.showPage()
    cv.save()


# ----------------------------------------------------------------------------- write
def write(out: Path, src: Path, img, W, H, R, objects, photos, blocks, text_mask, lab, c, target=None,
          text_zone=None):
    from skimage.metrics import structural_similarity

    for d in ("canva", "vectors", "layers"):
        (out / d).mkdir(exist_ok=True)
    seq = []  # (type, name, data)
    bgs = [o for o in objects if o["kind"] in ("background", "bg_shape")]
    rest = [o for o in objects if o not in bgs]
    for o in bgs:
        seq.append(("vector", o))
    for p in photos:
        if p["where"] == "bottom":
            seq.append(("photo", p))
    for o in rest:
        seq.append(("vector", o))
    for p in photos:
        if p["where"] == "top":
            seq.append(("photo", p))

    counters, layers = {}, []
    acc = np.zeros((H, W, 3), np.float32)
    for t, o in seq:
        z = len(layers)
        if t == "vector":
            kind = o["kind"]
            counters[kind] = counters.get(kind, 0) + 1
            nm = kind if kind == "background" else f"{kind}_{counters[kind]}"
            svg = object_svg(o, W, H, c)
            rgb, a = render(svg, W, H)
        else:
            nm, rgb, a = o["name"], o["rgb"], o["alpha"]
            svg = None
        bb = _bbox(a)
        if bb is None:
            continue
        name = f"{z:02d}_{nm}"
        acc = _over(acc, rgb, a)
        L = dict(name=name, type=t, z=z, bbox=bb)
        _save_png(out / "layers" / f"{name}.png", rgb, a)
        x, y, w, h = bb
        if t == "vector":
            (out / "vectors" / f"{name}.svg").write_text(svg, encoding="utf-8")
            (out / "canva" / f"{name}.svg").write_text(crop_svg(svg, bb), encoding="utf-8")
            L.update(regions=o["regions"], file=f"canva/{name}.svg", colors=_colors(o["regions"]))
        else:
            _save_png(out / "canva" / f"{name}.png", rgb[y:y + h, x:x + w], a[y:y + h, x:x + w])
            L.update(file=f"canva/{name}.png", png_crop=out / "canva" / f"{name}.png", colors="")
        layers.append(L)

    vec_only = acc.copy()
    clean_zone = None
    st_regs = [r for r in R if r.get("stripe") or r.get("rule")]
    if st_regs:
        clean_zone = np.zeros((H, W), bool)
        for r in st_regs:
            clean_zone[r["sl"]] |= r["m"]
        big = np.zeros((H, W), bool)
        for r in st_regs:
            if r.get("stripe"):
                big[r["sl"]] |= r["m"]
        clean_zone = matting.dilate(big, int(c.stripe_clean_px)) | matting.dilate(clean_zone, 3)
    fx_rgb, fx_a = effect_layer(img if target is None else target, acc, lab, text_mask, c, text_zone, clean_zone)
    if c.effects and fx_a.sum() > c.fx_min_total * H * W:
        z = len(layers)
        name = f"{z:02d}_effects"
        bb = _bbox(fx_a)
        _save_png(out / "layers" / f"{name}.png", fx_rgb, fx_a)
        x, y, w, h = bb
        _save_png(out / "canva" / f"{name}.png", fx_rgb[y:y + h, x:x + w], fx_a[y:y + h, x:x + w])
        layers.append(dict(name=name, type="effect", z=z, bbox=bb, file=f"canva/{name}.png",
                           png_crop=out / "canva" / f"{name}.png", colors=""))
        acc = _over(acc, fx_rgb, fx_a)

    # ---- text
    for b in blocks:
        b["canva_font_size"] = fit_text(b)
    tm = matting.dilate(text_mask if text_zone is None else (text_mask | text_zone), 1)[..., None]
    final_cmp = np.where(tm, img, acc)    # text area: what native text will show
    vec_cmp = np.where(tm, img, vec_only)
    ssim = structural_similarity(img, final_cmp, channel_axis=2, data_range=1.0)
    ssim_v = structural_similarity(img, vec_cmp, channel_axis=2, data_range=1.0)

    shown = draw_text(to_u8(acc), blocks)
    prev = np.full((H, 2 * W + 20, 3), 24, np.uint8)
    prev[:, :W] = to_u8(img)
    prev[:, W + 20:] = shown
    Image.fromarray(prev).save(out / "preview.png")
    _sheet(out, layers, W, H)

    with open(out / "text.csv", "w", newline="", encoding="utf-8-sig") as f:
        w_ = csv.writer(f)
        w_.writerow(["id", "text", "x", "y", "w", "h", "color_hex", "canva_font_size", "est_font_size_px",
                     "angle_deg"])
        for b in blocks:
            w_.writerow([b["id"], b["text"], b["x"], b["y"], b["w"], b["h"], b["color_hex"],
                         b["canva_font_size"], b.get("est_font_size_px", ""), b.get("angle_deg", 0)])
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8-sig") as f:
        w_ = csv.writer(f)
        w_.writerow(["z_order", "layer", "type", "canva_file", "svg_full", "png_full", "x", "y", "w", "h", "colors"])
        for L in layers:
            x, y, w, h = L["bbox"]
            w_.writerow([L["z"], L["name"], L["type"], L["file"],
                         f"vectors/{L['name']}.svg" if L["type"] == "vector" else "",
                         f"layers/{L['name']}.png", x, y, w, h, L["colors"]])
    _scene_svg(out, layers, blocks, W, H)
    try:
        write_pdf(out / "CANVA_IMPORT.pdf", W, H, layers, blocks, c)
    except Exception as e:  # noqa: BLE001
        log.warning("  PDF gagal dibuat: %s", e)
    _guide(out, src, W, H, layers, blocks)
    try:
        from . import canva_package

        canva_package.write(out, src, W, H, layers, blocks, c)
    except Exception as e:  # noqa: BLE001
        log.warning("  CANVA_PACKAGE.json gagal dibuat: %s", e)
    return {
        "source": src.name, "mode": "rebuild", "width": W, "height": H,
        "ssim": round(float(ssim), 4), "ssim_vectors_only": round(float(ssim_v), 4),
        "layers": [{k: (v if k != "bbox" else list(v)) for k, v in L.items()
                    if k in ("name", "type", "z", "bbox", "file", "colors")} for L in layers],
        "text": [{k: b[k] for k in ("id", "text", "x", "y", "w", "h", "color_hex", "canva_font_size")}
                 for b in blocks],
    }


def _colors(regs):
    seen = []
    for r in regs:
        f = r["fill"]
        cs = [f["color"]] if f["kind"] == "solid" else [s[2] for s in f["stops"]]
        for col in cs:
            h = shapes._hex(col)
            if h not in seen:
                seen.append(h)
    return " ".join(seen[:8])


def _save_png(path, rgb, a):
    rgba = np.dstack([to_u8(rgb), to_u8(a)])
    rgba[rgba[..., 3] == 0, :3] = 0
    Image.fromarray(rgba, "RGBA").save(path, compress_level=6)


def _scene_svg(out, layers, blocks, W, H):
    body, defs = [], []
    for L in layers:
        if L["type"] == "vector":
            s = (out / "vectors" / f"{L['name']}.svg").read_text(encoding="utf-8")
            inner = s.split("viewBox=", 1)[1].split(">", 1)[1].rsplit("</svg>", 1)[0]
            inner = re.sub(r'id="g(\d+)"', lambda m: f'id="{L["name"]}_g{m.group(1)}"', inner)
            inner = re.sub(r'url\(#g(\d+)\)', lambda m: f'url(#{L["name"]}_g{m.group(1)})', inner)
            body.append(f'<g id="{L["name"]}">{inner}</g>')
        else:
            x, y, w, h = L["bbox"]
            body.append(f'<image id="{L["name"]}" x="{x}" y="{y}" width="{w}" height="{h}" '
                        f'xlink:href="{L["file"]}"/>')
    for b in blocks:
        lines = [ln.replace("&", "&amp;").replace("<", "&lt;") for ln in str(b["text"]).split("\n")]
        step = b["h"] / max(len(lines), 1)
        spans = "".join(f'<tspan x="{b["x"]}" y="{b["y"] + (i + 1) * step:.0f}">{ln}</tspan>' for i, ln in enumerate(lines))
        body.append(f'<text font-family="Arial" font-weight="bold" font-size="{b["canva_font_size"]}" '
                    f'fill="{b["color_hex"]}">{spans}</text>')
    (out / "scene.svg").write_text(_svg(W, H, "\n".join(body)), encoding="utf-8")


def _sheet(out, layers, W, H):
    tw = 260
    th = int(tw * H / W)
    cols = 4
    rows = (len(layers) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 10) + 10, rows * (th + 34) + 10), (235, 235, 235))
    d = ImageDraw.Draw(sheet)
    f = _font(13)
    checker = np.indices((th, tw)).sum(0) // 10 % 2
    chk = Image.fromarray(np.where(checker[..., None], 205, 250).astype(np.uint8).repeat(3, -1))
    for i, L in enumerate(layers):
        x0 = 10 + (i % cols) * (tw + 10)
        y0 = 10 + (i // cols) * (th + 34)
        im = Image.open(out / "layers" / f"{L['name']}.png").resize((tw, th))
        tile = chk.copy()
        tile.paste(im, (0, 0), im)
        sheet.paste(tile, (x0, y0))
        d.text((x0, y0 + th + 4), f"{L['name']} [{L['type']}]", font=f, fill=(20, 20, 20))
    sheet.save(out / "sheet.png")


def _guide(out, src, W, H, layers, blocks):
    L = [f"REBUILD: {src.name}   ukuran kanvas {W} x {H} px", "",
         "CARA 1 (paling cepat): Canva > Upload > pilih CANVA_IMPORT.pdf > klik hasilnya.",
         "  Canva membuka PDF sebagai desain yang bisa diedit (bentuk, foto, teks terpisah).",
         "  Font akan diganti Canva -> ganti font teks sesuai selera.", "",
         "CARA 2 (layer per objek, warna SVG bisa diganti):",
         f"  1. Buat desain baru: Custom size {W} x {H} px.",
         "  2. Upload semua file di folder canva\\ (drag sekaligus).",
         "  3. Masukkan sesuai urutan di bawah (nomor kecil = paling bawah).",
         "     Atur posisi lewat Position > Advanced (X, Y, W, H) sesuai angka di bawah.",
         "  4. Tambah teks (lihat daftar teks), warna & ukuran sudah disarankan.", "",
         "URUTAN LAYER (bawah -> atas):"]
    for l in layers:
        x, y, w, h = l["bbox"]
        L.append(f"  {l['z']:02d}  {l['file']:<38} X={x:<5} Y={y:<5} W={w:<5} H={h:<5} {l['colors']}")
    L += ["", "TEKS (paling atas):"]
    for b in blocks:
        L.append(f"  \"{b['text']}\"  X={b['x']} Y={b['y']} W={b['w']}  warna {b['color_hex']}  "
                 f"ukuran {b['canva_font_size']}")
    (out / "CARA_IMPORT_CANVA.txt").write_text("\n".join(L) + "\n", encoding="utf-8")

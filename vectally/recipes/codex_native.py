"""Tahap teks native gaya Codex (BuildNative), DISALIN dan disesuaikan dari
VECTALLY_CODEX_TOOLKIT_20261112/engine/vectally_collection.py (FONTS, fit_text, svg_text) dan
vectally_approved_native.py (export).

Huruf yang di Build berupa outline dari sumber diganti teks Canva yang bisa diketik.
Perubahan dari Codex: folder font/hasil relatif ke vectally/, kotak teks bisa diukur langsung
dari sumber (measure_box, rotasi di sekitar pusat seperti Canva), dan teks bisa ditandai
kandidat TypeCraft (miring/italic yang tidak bisa ditiru teks biasa).
"""
import gzip
import html
import json
import math
from pathlib import Path

import cv2
import numpy as np
import resvg_py
from PIL import ImageFont

HERE = Path(__file__).resolve().parent
FONTROOT = HERE.parent / 'outputs' / 'VECTALLY-teks-native' / 'fonts'
FONTS = {
    'League Gothic': ('YACgEZ1OEPI:0', next(FONTROOT.glob('leaguegothic-*.ttf'))),
    'Archivo Black': ('YACgEZulLoA:0', next(FONTROOT.glob('archivoblack-*.ttf'))),
    'Asap': ('YAFdJr0OaFw:0', next(FONTROOT.glob('asap-Asap[[]wdth,wght].ttf'))),
}


def txt(word, box, font='League Gothic', color='#091522', angle=0, parent=None, typecraft=None):
    return dict(word=word, box=box, font=font, color=color, angle=angle, parent=parent, typecraft=typecraft)


def measure_box(rgb, mode, polygon):
    """Kotak tinta huruf di dalam poligon: (x, y, w, h, sudut) dengan rotasi di sekitar pusat."""
    im = rgb.astype(int)
    if mode == 'white':
        m = im.min(2) > 200
    elif mode == 'dark':
        m = im.max(2) < 90
    elif mode == 'green':
        m = (im[:, :, 1] > 150) & (im[:, :, 0] < 90) & (im[:, :, 1] > im[:, :, 2] + 30)
    else:
        raise ValueError(mode)
    keep = np.zeros(m.shape, np.uint8)
    cv2.fillPoly(keep, [np.array(polygon, np.int32)], 1)
    ys, xs = np.nonzero(m & keep.astype(bool))
    (cx, cy), (w, h), a = cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32))
    if h > w:  # sisi panjang = arah baris teks
        w, h, a = h, w, a - 90
    if a < -45:
        a += 180
    if a > 45:
        a -= 180
    return (round(cx - w / 2, 2), round(cy - h / 2, 2), round(w, 2), round(h, 2), round(a, 2))


def fit_text(t, f, box, color, rotation=0, weight='normal'):
    # Sama dengan Codex: ukuran huruf dari tinggi/lebar tinta, posisi dikoreksi offset bbox glyph.
    x, y, w, h = box[:4]
    ref, file = FONTS[f]
    ft = ImageFont.truetype(str(file), 100)
    bb = ft.getbbox(t)
    size = min(h * 100 / max(1, bb[3] - bb[1]), w * 100 / max(1, ft.getlength(t)))
    size = round(size, 3)
    sf = size / 100
    return dict(type='text', name=t, text=t, fontName=f, fontRef=ref, fontSize=size,
                left=round(x - bb[0] * sf, 4), top=round(y - bb[1] * sf, 4), width=round(w + 2, 4),
                height=round(size * 1.22, 4), color=color, fontWeight=weight, rotation=rotation)


def svg_text(e):
    f = e['fontName']
    base = e['top'] + e['fontSize'] * (.98 if f == 'League Gothic' else .95)
    cx, cy = e['left'] + e['width'] / 2, e['top'] + e['height'] / 2
    return (f'<text x="{e["left"]}" y="{base}" font-family="{f}" font-size="{e["fontSize"]}" fill="{e["color"]}" '
            f'transform="rotate({e.get("rotation", 0)} {cx} {cy})">{html.escape(e["text"])}</text>')


def export_native(scene, texts, out):
    """Paket: aset scene (tanpa aset 'lettering') + teks native. Teks ber-parent masuk grup bendanya."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    elements, sv, records = [], [], []

    def shape(p, name):
        import re
        ns = list(map(float, re.findall(r'-?\d+(?:\.\d+)?', p['d'])))
        xs, ys = ns[::2], ns[1::2]
        x0, y0 = min(xs), min(ys)
        ww, hh = max(xs) - x0, max(ys) - y0
        assert ww > 0 and hh > 0 and len(p['d']) < 1900, (name, len(p['d']))
        return dict(type='shape', name=name, left=x0, top=y0, width=ww, height=hh,
                    viewBox=dict(left=x0, top=y0, width=ww, height=hh), paths=[dict(d=p['d'], fill=dict(color=p['color']))])

    for a in scene.assets:
        if a['kind'] == 'lettering':
            continue
        es = [shape(p, f'{a["id"]}_{j}') for j, p in enumerate(a['parts'])]
        sv.extend(f'<path d="{p["d"]}" fill="{p["color"]}"/>' for p in a['parts'])
        for t in texts:
            if t['parent'] == a['id']:
                e = fit_text(t['word'], t['font'], t['box'], t['color'], t['angle'])
                es.append(e)
                sv.append(svg_text(e))
        x = min(e['left'] for e in es)
        y = min(e['top'] for e in es)
        xx = max(e['left'] + e['width'] for e in es)
        yy = max(e['top'] + e['height'] for e in es)
        for e in es:
            e['left'] -= x
            e['top'] -= y
        if len(es) == 1:
            e = es[0]
            e['left'] += x
            e['top'] += y
            e['name'] = a['name']
        else:
            e = dict(type='group', name=a['name'], left=x, top=y, width=xx - x, height=yy - y, children=es)
        elements.append(e)
        records.append(dict(id=a['id'], name=a['name'], parts=len(es), native_text=sum(c['type'] == 'text' for c in es)))
    for t in texts:
        if t['parent'] is None and not t.get('typecraft'):  # teks TypeCraft dibuat robot di Canva, bukan di paket
            e = fit_text(t['word'], t['font'], t['box'], t['color'], t['angle'])
            elements.append(e)
            sv.append(svg_text(e))

    def count(es, k):
        return sum((e['type'] == k) + count(e.get('children', []), k) for e in es)

    pkg = dict(format='cusbe-canva-package', version=2, source=f'{scene.code} - RESEP - TEKS NATIVE', width=1122, height=1402,
               elements=elements, summary={k: count(elements, k) for k in ['shape', 'text', 'group', 'image']},
               warnings=['Artwork dari resep terukur; teks native League Gothic/Archivo Black/Asap.',
                         'Teks bertanda TYPECRAFT perlu distorsi TypeCraft (miring/italic) di Canva.'])
    for e in elements:
        if e['type'] == 'group' and any(c['type'] == 'text' for c in e['children']):
            e['height'] = 'auto'
    raw = json.dumps(pkg, ensure_ascii=False).encode()
    (out / 'CANVA_PACKAGE.json').write_bytes(raw)
    (out / 'package.gz').write_bytes(gzip.compress(raw))
    scene_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="1122" height="1402">' + ''.join(sv) + '</svg>'
    (out / 'preview.svg').write_text(scene_svg, encoding='utf8')
    (out / 'preview.png').write_bytes(bytes(resvg_py.svg_to_bytes(svg_string=scene_svg, font_files=[str(v[1]) for v in FONTS.values()],
                                                                   skip_system_fonts=True)))
    (out / 'inventory.json').write_text(json.dumps(dict(objects=records, texts=texts), ensure_ascii=False, indent=2), encoding='utf8')
    (out / 'QA.json').write_text(json.dumps(dict(stage='LOCAL_PENDING_CANVA', **pkg['summary'], native_text=True,
                                                 typecraft=[t['word'] for t in texts if t.get('typecraft')]), indent=2))
    print(scene.code, 'NATIVE', pkg['summary'])
    return pkg

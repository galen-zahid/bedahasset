"""Ukur 4 titik sudut (TL, TR, BR, BL) tinta headline dari sumber untuk TypeCraft "Distorsi kustom",
lalu buat pratinjau lokal: teks League Gothic Condensed diregangkan ke quad itu (sama seperti TypeCraft).

Pemakaian: python typecraft_quads.py <code>   (spesifikasi headline ada di HEADLINES)
Hasil: outputs/VECTALLY-resep/<code>-NATIVE/TYPECRAFT_JOB.json + TYPECRAFT_PREVIEW.png
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LG = next((ROOT / 'outputs' / 'VECTALLY-teks-native' / 'fonts').glob('leaguegothic-*.ttf'))

HEADLINES = {
    'A09': dict(source='VECTALLY_A09_Three_Signs_Your_Books_Need_Attention.png', items=[
        dict(text='SIGNS', mode='white', color='#fdfdfd', roi=[[478, 470], [1062, 268], [1062, 612], [478, 806]]),
        dict(text='YOUR BOOKS', mode='green', color='#1ef7b2', roi=[[484, 790], [806, 676], [814, 782], [492, 894]]),
        dict(text='NEED', rect=True, mode='dark', color='#011423', roi=[[110, 915], [570, 915], [570, 1130], [110, 1130]]),
        dict(text='ATTENTION.', rect=True, mode='white', color='#fdfdfd', roi=[[100, 1125], [1075, 1125], [1075, 1360], [100, 1360]]),
    ]),
}


def ink(rgb, mode, roi):
    im = rgb.astype(int)
    m = {'white': im.min(2) > 200, 'dark': im.max(2) < 90,
         'green': (im[:, :, 1] > 150) & (im[:, :, 0] < 90) & (im[:, :, 1] > im[:, :, 2] + 30)}[mode]
    keep = np.zeros(m.shape, np.uint8)
    cv2.fillPoly(keep, [np.array(roi, np.int32)], 1)
    return m & keep.astype(bool)


def quad(mask):
    """Quad minimal (4 titik) yang memuat tinta: convex hull disederhanakan ke 4 titik, urut TL,TR,BR,BL."""
    ys, xs = np.nonzero(mask)
    hull = cv2.convexHull(np.stack([xs, ys], 1).astype(np.int32))
    eps = 1.0
    q = cv2.approxPolyDP(hull, eps, True)
    while len(q) > 4:
        eps *= 1.15
        q = cv2.approxPolyDP(hull, eps, True)
    q = q.reshape(-1, 2).astype(float)
    if len(q) < 4:  # cadangan: kotak miring minimum
        q = cv2.boxPoints(cv2.minAreaRect(np.stack([xs, ys], 1).astype(np.float32)))
    # perbesar sedikit dari pusat supaya quad menutupi tinta (approxPolyDP bisa memotong sudut)
    c = q.mean(0)
    s = q[:, 0] + q[:, 1]
    d = q[:, 0] - q[:, 1]
    tl, br = q[np.argmin(s)], q[np.argmax(s)]
    tr, bl = q[np.argmax(d)], q[np.argmin(d)]
    return [[round(float(x), 1), round(float(y), 1)] for x, y in (tl, tr, br, bl)], c


def render_word(text, color):
    ft = ImageFont.truetype(str(LG), 400)
    try:
        ft.set_variation_by_axes([75])  # League Gothic Condensed
    except Exception:  # noqa: BLE001
        pass
    bb = ft.getbbox(text)
    im = Image.new('RGBA', (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - bb[0], 2 - bb[1]), text, font=ft, fill=color)
    return im


def warp_onto(base, word, q):
    w, h = word.size
    M = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), np.float32(q))
    arr = cv2.warpPerspective(np.array(word), M, base.size, flags=cv2.INTER_LINEAR)
    base.alpha_composite(Image.fromarray(arr))


def main(code):
    spec = HEADLINES[code]
    rgb = np.array(Image.open(ROOT / 'sources' / 'VECTALLY' / 'Feed' / spec['source']).convert('RGB'))
    out = ROOT / 'outputs' / 'VECTALLY-resep' / f'{code}-NATIVE'
    base = Image.open(out / 'preview.png').convert('RGBA')
    warps = []
    for it in spec['items']:
        m = ink(rgb, it['mode'], it['roi'])
        if it.get('rect'):  # teks lurus: kotak tinta tegak, tidak dimiringkan
            ys, xs = np.nonzero(m)
            q = [[float(xs.min()), float(ys.min())], [float(xs.max() + 1), float(ys.min())], [float(xs.max() + 1), float(ys.max() + 1)], [float(xs.min()), float(ys.max() + 1)]]
        else:
            q, _ = quad(m)
        warps.append(dict(text=it['text'], color=it['color'], font='League Gothic Condensed Regular', quad=q,
                          bbox=[min(p[0] for p in q), min(p[1] for p in q), max(p[0] for p in q), max(p[1] for p in q)]))
        warp_onto(base, render_word(it['text'], it['color']), q)
        print(it['text'], q)
    base.convert('RGB').save(out / 'TYPECRAFT_PREVIEW.png')
    (out / 'TYPECRAFT_JOB.json').write_text(json.dumps(dict(code=code, warps=warps), indent=2), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1])

"""Alat ukur resep: daftar poligon kandidat (titik sudut) per warna dari PNG sumber.
Hasilnya dipakai sebagai bahan menulis resep eksplisit gaya Codex, bukan resep itu sendiri.
Pemakaian: python measure.py <png> <out_overlay.png> <mode> [eps] [minarea]   mode: dark|purple|white|green
"""
import sys, json
import numpy as np, cv2
from PIL import Image, ImageDraw

def mask(rgb, mode):
    r, g, b = [rgb[:, :, i].astype(int) for i in range(3)]
    if mode == 'dark': return rgb.max(2) < 70
    if mode == 'white': return rgb.min(2) > 225
    if mode == 'purple': return (b > 150) & (b > g + 40) & (r > 60) & (r < 215)
    if mode == 'green': return (g > 150) & (r < 90) & (g > b + 30)
    raise ValueError(mode)

def main(src, out, mode, eps=3.0, minarea=250):
    rgb = np.array(Image.open(src).convert('RGB'))
    m = cv2.morphologyEx(mask(rgb, mode).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, hier = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    im = Image.fromarray((rgb * 0.45 + 140).astype(np.uint8)); d = ImageDraw.Draw(im)
    res = []
    for i, c in enumerate(cnts):
        if hier[0][i][3] >= 0 or cv2.contourArea(c) < float(minarea): continue
        q = cv2.approxPolyDP(c, float(eps), True).reshape(-1, 2).tolist()
        k = len(res); res.append(q)
        d.line([tuple(p) for p in q] + [tuple(q[0])], fill=(255, 0, 0), width=2)
        cx = sum(p[0] for p in q) / len(q); cy = sum(p[1] for p in q) / len(q)
        d.text((cx, cy), str(k), fill=(255, 255, 0))
    im.save(out)
    for k, q in enumerate(res): print(k, len(q), json.dumps(q))

if __name__ == '__main__':
    main(*sys.argv[1:])

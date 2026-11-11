"""QA headline TypeCraft S01-S04: export Canva vs sumber, per kata.

Mask tinta diambil dengan ROI dan warna yang sama (F.source_mask) dari sumber dan export.
Laporan: IoU, selisih tepi kiri/atas/kanan/bawah (px), plus contact sheet berdampingan.
"""
import glob
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import s01_s05_display_fit as F  # noqa: E402

ROOT = F.ROOT
QA = ROOT / "work/headline_qa"
WORDS = [("S01", "THE BOOKS"), ("S01", "STORY."), ("S02", "WHAT'S"), ("S02", "HARDER"), ("S02", "TO"), ("S02", "TRACK?"),
         ("S03", "WHICH"), ("S03", "REPORT"), ("S03", "SHOWS"), ("S03", "PROFIT?"),
         ("S04", "IT'S THE"), ("S04", "PROFIT &"), ("S04", "LOSS.")]


def box(m):
    ys, xs = np.nonzero(m)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


def main():
    rows, tiles = [], []
    for code, text in WORDS:
        item = next(i for i in F.ITEMS if i[0] == code and i[1] == text)
        src = np.array(Image.open(glob.glob(str(ROOT / f"sources/VECTALLY/Story/*{code}_*"))[0]).convert("RGB").resize((941, 1672)))
        exp = np.array(Image.open(QA / f"final_{code}.png").convert("RGB").resize((941, 1672)))
        ms, me = F.source_mask(src, item[2], item[3]), F.source_mask(exp, item[2], item[3])
        if not me.any():
            rows.append({"code": code, "text": text, "error": "no ink in export"})
            continue
        bs, be = box(ms), box(me)
        iou = float((ms & me).sum() / max(1, (ms | me).sum()))
        edge = [be[k] - bs[k] for k in range(4)]
        rows.append({"code": code, "text": text, "iou": round(iou, 3), "srcBox": bs, "exportBox": be, "edgeDelta": edge, "maxEdge": max(map(abs, edge))})
        print(code, text.ljust(10), "IoU", round(iou, 3), "edge", edge, flush=True)
        x0, y0 = min(bs[0], be[0]) - 6, min(bs[1], be[1]) - 6
        x1, y1 = max(bs[2], be[2]) + 6, max(bs[3], be[3]) + 6
        a = src[max(0, y0):y1, max(0, x0):x1]
        b = exp[max(0, y0):y1, max(0, x0):x1]
        ov = np.zeros_like(a)
        ov[..., 0] = (ms[max(0, y0):y1, max(0, x0):x1] * 255)
        ov[..., 1] = (me[max(0, y0):y1, max(0, x0):x1] * 255)
        tiles.append(np.concatenate([a, b, ov], 1))
    W = max(t.shape[1] for t in tiles)
    sheet = np.concatenate([np.pad(t, ((4, 4), (0, W - t.shape[1]), (0, 0)), constant_values=255) for t in tiles], 0)
    Image.fromarray(sheet.astype(np.uint8)).save(QA / "HEADLINE_QA_SHEET.png")
    (QA / "HEADLINE_QA.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

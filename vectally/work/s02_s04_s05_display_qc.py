"""Bandingkan ink headline export Canva dengan sumber untuk S02, S04, S05."""
import glob
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from s01_s05_display_fit import ITEMS, K, ROOT, source_mask  # noqa: E402

PAGES = {"S02": "p2.png", "S04": "p3.png", "S05": "p4.png"}


def box(mask):
    ys, xs = np.where(mask)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def main(folder):
    folder = Path(folder)
    out, sheets = [], []
    for code, name in PAGES.items():
        src = Image.open(glob.glob(str(ROOT / f"sources/VECTALLY/Story/*{code}_*"))[0]).convert("RGB")
        got = Image.open(folder / name).convert("RGB").resize(src.size)
        sheets.append((src, got))
        a, b = np.array(src), np.array(got)
        for c, text, roi, color, _ in ITEMS:
            if c != code:
                continue
            wide = (roi[0] - 8, roi[1] - 8, roi[2] + 8, roi[3] + 8)
            ms, mg = source_mask(a, roi, color), source_mask(b, wide, color)
            if not mg.any():
                print(code, text, "TIDAK ADA TINTA DI EXPORT")
                out.append({"code": code, "text": text, "error": "no ink"})
                continue
            bs, bg = box(ms), box(mg)
            dx = (bs[0] + bs[2]) / 2 - (bg[0] + bg[2]) / 2
            dy = (bs[1] + bs[3]) / 2 - (bg[1] + bg[3]) / 2
            iou = (ms & mg).sum() / max(1, (ms | mg).sum())
            row = {"code": code, "text": text, "src": bs, "got": bg, "dx": dx, "dy": dy, "iouInPlace": round(float(iou), 3), "wRatio": round((bg[2] - bg[0]) / (bs[2] - bs[0]), 3), "hRatio": round((bg[3] - bg[1]) / (bs[3] - bs[1]), 3)}
            out.append(row)
            print(code, text.ljust(12), "dx", dx, "dy", dy, "iou", row["iouInPlace"], "w", row["wRatio"], "h", row["hRatio"])
    w, h = 300, 533
    sheet = Image.new("RGB", (w * 6 + 50, h), "white")
    for i, (s, g) in enumerate(sheets):
        sheet.paste(s.resize((w, h)), (i * (2 * w + 25), 0))
        sheet.paste(g.resize((w, h)), (i * (2 * w + 25) + w, 0))
    sheet.save(folder / "contact.jpg", quality=84)
    (folder / "metrics.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])

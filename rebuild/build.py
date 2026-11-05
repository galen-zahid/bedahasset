"""Turn a hand rebuild (rebuild/<design>.py with OBJECTS) into a layer package:

    python rebuild/build.py vectally_s01 in/VECTALLY_S01.png out/rebuild/VECTALLY_S01 [pipeline_out_dir]

Writes vectors/<obj>.svg, <obj>.png (rendered from the SVG, full canvas), manifest.csv,
scene.svg (all objects), preview.png (original | rebuild) and copies text.csv from the
automatic pipeline output when given.
"""
import csv
import importlib
import io
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def render(svg_text):
    import resvg_py
    from PIL import Image

    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg_text)))).convert("RGBA")


def main(mod_name, original, out, auto_dir=None):
    from PIL import Image

    mod = importlib.import_module(mod_name)
    out = Path(out)
    mod.main(out)
    rows, acc = [], None
    for z, (name, s) in enumerate(mod.OBJECTS.items()):
        im = render(s)
        im.save(out / f"{name}.png")
        acc = im.copy() if acc is None else (acc.alpha_composite(im) or acc)
        a = im.getchannel("A")
        bb = a.getbbox() or (0, 0, 0, 0)
        rows.append({"layer": name, "file": f"{name}.png", "svg_file": f"vectors/{name}.svg",
                     "x": bb[0], "y": bb[1], "w": bb[2] - bb[0], "h": bb[3] - bb[1], "z_order": z})
    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    if auto_dir and (Path(auto_dir) / "text.csv").exists():
        shutil.copy(Path(auto_dir) / "text.csv", out / "text.csv")
    o = Image.open(original).convert("RGB")
    prev = Image.new("RGB", (o.width * 2 + 20, o.height), (20, 20, 20))
    prev.paste(o, (0, 0))
    prev.paste(acc.convert("RGB"), (o.width + 20, 0))
    prev.save(out / "preview.png")
    print(f"{len(rows)} layer, preview -> {out / 'preview.png'}")


if __name__ == "__main__":
    main(*sys.argv[1:])

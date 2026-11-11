"""Render shape paket CANVA ke PNG untuk inspeksi tepi. Teks tidak dirender."""
import io, json, sys
import resvg_py
from PIL import Image

def leaves(es, ox=0, oy=0):
    for e in es:
        if e.get("type") == "group":
            yield from leaves(e["children"], ox + e["left"], oy + e["top"])
        elif e.get("type") == "shape":
            yield e, ox + e["left"], oy + e["top"]

def svg(pkg, scale):
    W, H = pkg["width"], pkg["height"]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W*scale}" height="{H*scale}" viewBox="0 0 {W} {H}">']
    for e, x, y in leaves(pkg["elements"]):
        if e.get("rotation"):
            raise ValueError(f"Rotasi shape belum didukung renderer: {e.get('name')}")
        vb = e["viewBox"]; sx = e["width"] / vb["width"]; sy = e["height"] / vb["height"]
        out.append(f'<g transform="translate({x} {y}) scale({sx} {sy}) translate({-vb["left"]} {-vb["top"]})">')
        for p in e["paths"]:
            c = p["fill"]["color"] if isinstance(p["fill"].get("color"), str) else p["fill"].get("color", {}).get("color", "#000")
            out.append(f'<path d="{p["d"]}" fill="{c}"/>')
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)

def render(pkg, scale=1):
    return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg(pkg, scale)))).convert("RGB")

if __name__ == "__main__":
    pkg = json.load(open(sys.argv[1], encoding="utf-8"))
    render(pkg, float(sys.argv[3]) if len(sys.argv) > 3 else 1).save(sys.argv[2])

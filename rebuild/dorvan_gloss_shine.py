"""Hand rebuild of DORVAN "Gloss isn't just Shine" from an empty canvas (1122x1402).

Vector objects (one SVG each, recolorable in Canva) + ONE general effect PNG
(texture + soft light), text is native Canva text (see TEXT).

    python rebuild/build.py dorvan_gloss_shine in/DORVAN_gloss_shine.png out/rebuild/DORVAN_gloss_shine
"""
from pathlib import Path

W, H = 1122, 1402
BG = "#f0f6fe"
NAVY = "#011a37"
GOLD = "#e4b346"
BLUE_DARK = "#0a4c96"
BLUE_MID = "#2a78c4"
BLUE_LIGHT = "#8cc4f6"
WHITE = "#ffffff"


def svg(body, defs=""):
    d = f"<defs>{defs}</defs>" if defs else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
            f'version="1.1" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{d}\n{body}\n</svg>\n')


def lin(id_, x1, y1, x2, y2, stops):
    s = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
    return (f'<linearGradient id="{id_}" gradientUnits="userSpaceOnUse" x1="{x1}" y1="{y1}" '
            f'x2="{x2}" y2="{y2}">{s}</linearGradient>')


CREST = "M300 632 C470 628 560 688 700 735 C820 776 950 808 1122 822"
OBJECTS = {}

OBJECTS["00_background"] = svg(f'<rect width="{W}" height="{H}" fill="{BG}"/>')

# ---- lower-left blue panel (below the wave crest), fades to light at the bottom
OBJECTS["01_panel_lower"] = svg(
    f'<path d="M0 690 C100 668 200 640 300 632 C470 628 560 688 700 735 C820 776 950 808 1122 822 '
    f'L1122 878 C960 886 820 898 700 921 C560 950 400 1020 300 1068 C200 1105 100 1145 0 1160 Z" fill="url(#lo)"/>',
    lin("lo", 200, 650, 420, 1120, [(0, "#0753a0"), (0.45, "#3f8bd6"), (1, "#cfe6fc")]))

# ---- upper-right blue panel (window side)
OBJECTS["02_panel_upper"] = svg(
    f'<path d="M300 636 L1122 393 L1122 822 C950 808 820 776 700 735 C560 688 470 628 300 632 Z" fill="url(#up)"/>',
    lin("up", 800, 470, 900, 820, [(0, "#0a4a92"), (0.55, "#3b86d0"), (1, "#9ccdf9")]))

# ---- glossy edges: crest band + white sheen lines (one layer, recolorable)
OBJECTS["03_gloss_edges"] = svg(
    f'<path d="M300 640 C470 636 560 696 700 743 C820 784 950 816 1122 830" fill="none" stroke="url(#cr)" '
    f'stroke-width="22" stroke-linecap="round"/>'
    f'<g fill="none" stroke="{WHITE}" stroke-linecap="round">'
    f'<path d="M300 628 C470 624 560 684 700 731 C820 772 950 804 1122 818" stroke-width="5"/>'
    f'<path d="M0 694 C100 672 200 646 300 636" stroke-width="4" opacity="0.9"/>'
    f'<path d="M420 600 L1122 398" stroke-width="3" opacity="0.55"/>'
    f'<path d="M560 952 C700 916 860 892 1122 880" stroke-width="4" opacity="0.8"/></g>',
    lin("cr", 300, 640, 1122, 830, [(0, "#1f6fc0"), (0.5, "#4a9be6"), (1, "#bfe2ff")]))

# ---- window reflection (4+1 panes)
PANES = [
    [(565, 660), (607, 629), (717, 624), (675, 672)],
    [(700, 672), (745, 612), (887, 607), (830, 687)],
    [(617, 622), (668, 573), (772, 557), (728, 612)],
    [(752, 606), (800, 555), (962, 505), (930, 587)],
    [(940, 586), (995, 495), (1122, 462), (1122, 540)],
]
OBJECTS["04_window_reflection"] = svg(
    f'<g fill="{WHITE}">' + "".join(
        '<path d="M' + " L".join(f"{x} {y}" for x, y in p) + ' Z"/>' for p in PANES) + "</g>")

# ---- top-right swoosh: blue sliver + gold line
OBJECTS["05_swoosh_top"] = svg(
    '<path d="M480 138 C640 78 820 22 1010 0 L1122 0 L1122 6 C900 20 700 70 480 138 Z" fill="url(#st)"/>'
    f'<path d="M564 118 C680 78 790 44 894 24" fill="none" stroke="{GOLD}" stroke-width="5" stroke-linecap="round"/>',
    lin("st", 480, 138, 1122, 0, [(0, "#4f95dc"), (1, "#0b4fa0")]))

# ---- bottom-left swoosh: dark navy band + gold line
OBJECTS["06_swoosh_bottom"] = svg(
    '<path d="M0 1200 C150 1262 300 1330 540 1402 L0 1402 Z" fill="url(#sb)"/>'
    f'<path d="M0 1165 C140 1225 280 1300 420 1362" fill="none" stroke="{GOLD}" stroke-width="6" stroke-linecap="round"/>',
    lin("sb", 0, 1200, 200, 1402, [(0, "#0a5cb4"), (0.35, "#012b5f"), (1, "#01214a")]))

# ---- gold arrows (ONE layer, solid gold -> recolor in one click)
OBJECTS["07_arrows_gold"] = svg(
    f'<g fill="none" stroke="{GOLD}" stroke-width="9" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M160 195 L605 625 L905 368"/>'
    '<path d="M60 590 L298 818 C330 800 345 772 375 770 C410 768 425 792 455 784 C480 777 495 758 515 746"/>'
    '</g>'
    f'<g fill="{GOLD}"><path d="M926 350 L878 362 L905 392 Z"/>'
    '<path d="M532 736 L497 735 L513 762 Z"/>'
    '<path d="M610 632 L578 618 L596 600 Z"/><path d="M302 824 L272 810 L288 792 Z"/></g>')

# ---- gold accents: // logo slashes, side bars, SHINE period
OBJECTS["08_accents_gold"] = svg(
    f'<g fill="{GOLD}">'
    '<path d="M81 56 L97 56 L79 94 L63 94 Z"/><path d="M106 56 L122 56 L104 94 L88 94 Z"/>'
    '<path d="M82 364 L91 364 L42 546 L33 546 Z"/>'
    '<path d="M1048 1143 L1089 1143 L1080 1186 L1039 1186 Z"/>'
    '<path d="M480 1222 L488 1222 L455 1316 L447 1316 Z"/></g>')

# ---- callouts (pill + leader line + dot); label text is native Canva text
OBJECTS["09_callout_reflection"] = svg(
    f'<rect x="490" y="377" width="229" height="61" rx="30.5" fill="{WHITE}" stroke="{NAVY}" stroke-width="3"/>'
    f'<line x1="628" y1="438" x2="601" y2="580" stroke="{NAVY}" stroke-width="3"/>'
    f'<circle cx="601" cy="585" r="9" fill="{WHITE}" stroke="{NAVY}" stroke-width="5"/>')
OBJECTS["10_callout_surface"] = svg(
    f'<rect x="59" y="941" width="323" height="67" rx="33.5" fill="{WHITE}" stroke="{NAVY}" stroke-width="3"/>'
    f'<line x1="282" y1="890" x2="238" y2="941" stroke="{NAVY}" stroke-width="3"/>'
    f'<circle cx="285" cy="884" r="9" fill="{WHITE}" stroke="{NAVY}" stroke-width="5"/>')

# Native text for Canva (left, top, width, size, color, align)
TEXT = [
    ("DORVAN", 128, 50, 300, 46, NAVY, "start"),
    ("GLOSS", 355, 140, 740, 200, NAVY, "start"),
    ("ISN'T\nJUST", 70, 355, 300, 100, NAVY, "start"),
    ("REFLECTION", 490, 388, 229, 28, NAVY, "center"),
    ("SURFACE TEXTURE", 59, 954, 323, 28, NAVY, "center"),
    ("SHINE", 400, 995, 660, 205, NAVY, "start"),
    ("Surface texture affects how\nsharply reflections appear.", 509, 1212, 570, 38, NAVY, "start"),
]


def effects_png(path):
    """ONE general effect layer: fine surface texture + soft light (glows, wisps)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter

    rng = np.random.default_rng(7)
    a = np.zeros((H, W), np.float32)
    # fine speckle texture over the lower panel
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon(
        [(0, 690), (300, 632), (700, 735), (1122, 822), (1122, 878), (700, 921), (300, 1068), (0, 1160)], fill=255)
    m = np.asarray(mask.filter(ImageFilter.GaussianBlur(25)), np.float32) / 255
    n = rng.random((H, W)).astype(np.float32)
    n = np.asarray(Image.fromarray((n * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    a += np.clip((n - 0.5) * 4, 0, 1) * 0.22 * m
    # soft wisps (smeared reflection) + glows at the arrow hits
    lt = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(lt)
    for x0, y0 in [(330, 820), (400, 800), (465, 790), (525, 805)]:
        for k in range(5):  # wavy streaks
            d.line([(x0 + 10 + 8 * (k % 2), y0 + 26 * k), (x0 + 18 - 8 * (k % 2), y0 + 26 * (k + 1))], fill=170, width=22)
    for cx, cy, r in [(605, 625, 40), (300, 820, 30)]:
        d.ellipse([cx - r, cy - r / 3, cx + r, cy + r / 3], fill=255)
    a += np.asarray(lt.filter(ImageFilter.GaussianBlur(14)), np.float32) / 255
    a = np.clip(a, 0, 1)
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., :3] = 255
    rgba[..., 3] = (a * 255).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(path)


RASTERS = {"11_effects_light_texture": effects_png}


def main(out):
    out = Path(out)
    (out / "vectors").mkdir(parents=True, exist_ok=True)
    for name, s in OBJECTS.items():
        (out / "vectors" / f"{name}.svg").write_text(s, encoding="utf-8")
    inner = [s.split("viewBox=", 1)[1].split(">", 1)[1].rsplit("</svg>", 1)[0] for s in OBJECTS.values()]
    (out / "scene.svg").write_text(svg("\n".join(f"<g>{b}</g>" for b in inner)), encoding="utf-8")

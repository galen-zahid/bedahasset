"""Hand rebuild of VECTALLY_S01 ("The Books Tell A Story") from an empty canvas.

Every object is drawn with clean primitives (rects, circles, round-capped strokes, Bezier
paths) measured from the reference, one SVG per object, all on the full 941x1672 canvas so they
stack 1:1 at x=0, y=0. Text is NOT drawn: it is rebuilt as native Canva text (see text.csv).

    python rebuild/vectally_s01.py OUT_DIR
"""
import sys
from pathlib import Path

W, H = 941, 1672
BG = "#0c1421"
WHITE = "#f6f8fc"
PURPLE = "#b99cfc"
PURPLE_FOLD = "#9c84e6"
PURPLE_EDGE = "#7f6fc4"
NAVY = "#131a2a"
GREEN = "#06e3a0"
SHADOW_A = "#4a4673"
SHADOW_B = "#2b2c4a"
SKEW = -6.8  # all documents are drawn in the same oblique view


def svg(body, defs=""):
    d = f"<defs>{defs}</defs>" if defs else ""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
            f'version="1.1" width="{W}" height="{H}" viewBox="0 0 {W} {H}">{d}\n{body}\n</svg>\n')


def doc(x, y, transform_extra=""):
    return f'transform="translate({x},{y}) skewY({SKEW}){transform_extra}"'


def lines(x0, x1, ys, w=7, color=NAVY):
    return "".join(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{color}" stroke-width="{w}" '
                   f'stroke-linecap="round"/>' for y in ys)


GRAD = (f'<linearGradient id="sh" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{SHADOW_A}"/>'
        f'<stop offset="1" stop-color="{SHADOW_B}"/></linearGradient>')

OBJECTS = {}

OBJECTS["00_background"] = svg(f'<rect width="{W}" height="{H}" fill="{BG}"/>')

OBJECTS["01_header_bar"] = svg(f'<rect x="47" y="157" width="222" height="9" fill="{GREEN}"/>')

OBJECTS["02_shadow_bands"] = svg(
    '<g fill="url(#sh)">'
    '<path d="M0 600 L80 590 L80 632 L0 641 Z"/>'
    '<path d="M522 560 L635 542 L612 640 L498 670 Z"/>'
    '<path d="M0 823 L56 813 L56 851 L0 862 Z"/>'
    '<path d="M152 950 L230 941 L230 1012 L115 1034 Z"/>'
    '</g>', GRAD)

# ---- document with "$"
OBJECTS["03_icon_invoice"] = svg(
    f'<g {doc(68, 487)}>'
    f'<path d="M0 0 H160 L204 40 V191 H0 Z" fill="{WHITE}"/>'
    f'<path d="M160 0 L204 40 H160 Z" fill="{PURPLE}"/>'
    f'<rect x="27" y="31" width="76" height="10" rx="2" fill="{PURPLE}"/>'
    + lines(30, 115, [72, 94, 116, 138]) +
    f'<path d="M171 86 C171 76 146 74 146 90 C146 106 175 102 175 120 C175 136 146 136 144 124" '
    f'fill="none" stroke="{PURPLE}" stroke-width="11" stroke-linecap="round"/>'
    f'<line x1="160" y1="70" x2="160" y2="146" stroke="{PURPLE}" stroke-width="9" stroke-linecap="round"/>'
    '</g>')

# ---- purple card with bar chart
OBJECTS["04_icon_chart"] = svg(
    f'<g {doc(362, 497)}>'
    f'<path d="M6 150 H166 V160 H14 Z" fill="{PURPLE_EDGE}"/>'
    f'<path d="M0 0 H132 L166 30 V152 H0 Z" fill="{PURPLE}"/>'
    f'<path d="M132 0 L166 30 H132 Z" fill="{PURPLE_FOLD}"/>'
    f'<rect x="40" y="27" width="70" height="10" rx="2" fill="{NAVY}"/>'
    f'<g fill="{NAVY}"><rect x="46" y="108" width="15" height="20"/><rect x="71" y="96" width="15" height="32"/>'
    f'<rect x="96" y="78" width="15" height="50"/><rect x="121" y="55" width="15" height="73"/></g>'
    '</g>')

# ---- purple receipt
zig = " ".join(f"L{145 - i * 12.08:.1f} {160 if i % 2 == 0 else 172}" for i in range(13))
OBJECTS["05_icon_receipt"] = svg(
    f'<g {doc(50, 745)}>'
    f'<path d="M0 0 H124 L145 22 V160 {zig} L0 160 Z" fill="{PURPLE}"/>'
    f'<path d="M124 0 L145 22 H124 Z" fill="{PURPLE_FOLD}"/>'
    + lines(22, 82, [30, 55, 80, 105, 130]) + lines(106, 124, [55, 80, 105, 130]) +
    '</g>')

# ---- document with pie chart
OBJECTS["06_icon_pie_doc"] = svg(
    f'<g {doc(228, 863)}>'
    f'<path d="M0 0 H155 L177 22 V160 H0 Z" fill="{WHITE}"/>'
    f'<path d="M155 0 L177 22 H155 Z" fill="{PURPLE}"/>'
    + lines(25, 128, [30], w=8) +
    f'<circle cx="57" cy="97" r="35" fill="{PURPLE}"/>'
    f'<path d="M57 97 V62 A35 35 0 0 1 92 97 Z" fill="{NAVY}"/>'
    f'<path d="M57 97 L92 97 A35 35 0 0 1 75 127 Z" fill="{NAVY}"/>'
    + lines(110, 150, [80, 98, 116], w=7) +
    '</g>')

# ---- green connectors (one object each)
STROKE = f'fill="none" stroke="{GREEN}" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"'
STROKE13 = STROKE.replace('stroke-width="11"', 'stroke-width="13"')
OBJECTS["07_connector_invoice_bottom"] = svg(
    f'<path d="M181 657 V683 Q181 705 203 705 H284 Q306 705 321 722 L343 749 Q358 768 380 768" {STROKE}/>'
    f'<circle cx="181" cy="657" r="14" fill="{GREEN}"/>')
OBJECTS["08_connector_invoice_side"] = svg(
    f'<path d="M272 582 H318 Q342 582 342 606 V670 Q342 700 372 703 H392 Q410 705 410 728 V745" {STROKE}/>')
OBJECTS["09_connector_chart"] = svg(
    f'<path d="M452 640 V688 Q452 708 438 716 Q432 722 432 742" {STROKE}/>'
    f'<circle cx="452" cy="640" r="14" fill="{GREEN}"/>')
OBJECTS["10_connector_receipt"] = svg(
    f'<path d="M200 815 H243 Q260 815 268 799 L277 786 Q288 772 308 772 H362" {STROKE}/>'
    f'<circle cx="200" cy="815" r="14" fill="{GREEN}"/>')
OBJECTS["11_connector_book"] = svg(
    f'<path d="M470 815 V865 Q470 890 495 890 H630 Q656 890 657 918 V935" {STROKE13}/>'
    f'<circle cx="657" cy="938" r="18" fill="{GREEN}"/>')
OBJECTS["12_bracket"] = svg(
    f'<path d="M380 1105 H303 Q265 1105 265 1145 V1255 Q265 1294 303 1294 H368" fill="none" '
    f'stroke="{GREEN}" stroke-width="20" stroke-linecap="butt" stroke-linejoin="round"/>')
OBJECTS["13_sparkles"] = svg(
    f'<g stroke="{GREEN}" stroke-width="9" stroke-linecap="round">'
    '<line x1="751" y1="812" x2="755" y2="853"/><line x1="787" y1="855" x2="810" y2="782"/>'
    '<line x1="820" y1="862" x2="857" y2="824"/></g>')

# ---- TELL A pill (text is native Canva text on top)
OBJECTS["14_pill"] = svg(f'<rect x="358" y="735" width="298" height="82" rx="41" fill="{GREEN}"/>')

# ---- open book
OBJECTS["15_book"] = svg(
    # back pages + cover
    f'<path d="M868 925 L905 955 L882 1182 L860 1170 Z" fill="{PURPLE_EDGE}"/>'
    f'<path d="M430 980 L645 960 L870 905 L895 930 L880 1185 Q760 1190 650 1210 Q620 1222 600 1226 '
    f'Q580 1222 560 1212 Q450 1200 350 1218 Z" fill="{PURPLE}"/>'
    # pages
    f'<path d="M443 955 Q545 935 650 948 L600 1198 Q500 1170 385 1178 Z" fill="{WHITE}" stroke="{NAVY}" stroke-width="5" stroke-linejoin="round"/>'
    f'<path d="M650 948 Q760 915 872 900 L852 1150 Q720 1160 600 1198 Z" fill="{WHITE}" stroke="{NAVY}" stroke-width="5" stroke-linejoin="round"/>'
    # left page: bar chart + lines
    f'<g fill="{GREEN}"><path d="M466 1045 L485 1043 L479 1066 L460 1068 Z"/><path d="M500 1030 L519 1028 L509 1066 L490 1068 Z"/>'
    f'<path d="M535 1005 L554 1003 L540 1064 L521 1066 Z"/><path d="M574 972 L596 970 L576 1062 L554 1064 Z"/></g>'
    f'<g stroke="{NAVY}" stroke-width="7" stroke-linecap="round"><line x1="455" y1="1091" x2="585" y2="1088"/>'
    '<line x1="450" y1="1113" x2="580" y2="1110"/><line x1="445" y1="1136" x2="545" y2="1133"/></g>'
    # right page: donut + checks + lines
    f'<circle cx="750" cy="985" r="42" fill="none" stroke="{PURPLE}" stroke-width="30"/>'
    f'<path d="M752 943 A42 42 0 0 1 772 1021" fill="none" stroke="{GREEN}" stroke-width="30"/>'
    f'<g fill="{GREEN}"><circle cx="672" cy="1080" r="14"/><circle cx="666" cy="1120" r="14"/></g>'
    f'<g fill="none" stroke="{NAVY}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M664 1079 L670 1086 L684 1070"/><path d="M658 1119 L664 1126 L678 1110"/></g>'
    f'<g stroke="{NAVY}" stroke-width="7" stroke-linecap="round"><line x1="705" y1="1075" x2="805" y2="1068"/>'
    '<line x1="702" y1="1097" x2="800" y2="1090"/><line x1="700" y1="1120" x2="770" y2="1115"/>'
    '<line x1="698" y1="1142" x2="790" y2="1136"/></g>')

OBJECTS["16_side_bar"] = svg(f'<rect x="44" y="1370" width="8" height="177" fill="{GREEN}"/>')


def main(out):
    out = Path(out)
    (out / "vectors").mkdir(parents=True, exist_ok=True)
    for name, s in OBJECTS.items():
        (out / "vectors" / f"{name}.svg").write_text(s, encoding="utf-8")
    # one combined file (all objects, in order) for previews / Figma-Illustrator users
    inner = []
    for s in OBJECTS.values():
        body = s.split("viewBox=", 1)[1].split(">", 1)[1].rsplit("</svg>", 1)[0]
        inner.append(f"<g>{body}</g>")
    (out / "scene.svg").write_text(svg("\n".join(inner)), encoding="utf-8")
    print(f"{len(OBJECTS)} objek -> {out / 'vectors'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/rebuild/VECTALLY_S01")

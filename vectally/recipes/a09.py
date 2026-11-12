"""Resep A09 gaya Codex: badan benda ditulis eksplisit dari ukuran sumber, huruf di-outline dari sumber.

Poligon pecahan diukur dengan measure.py (approxPolyDP eps 3 pada warna sumber) lalu dipilih per benda.
Kartu ikon dan isinya ditulis sebagai primitif (roundrect miring, elips, garis).
Jalankan: python recipes/a09.py   -> outputs/VECTALLY-resep/A09/
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codex_scene import Scene, poly, path, ellipse, rect, N  # noqa: E402

BG = '#02f598'
PU = '#9e67fa'
PU2 = '#7845ec'
DK = '#011423'
WH = '#fdfdfd'
GF = '#01d47c'
GR = '#1ef7b2'
IP = '#9a6cf6'


def rrot(cx, cy, w, h, ang, r, c):
    """Roundrect miring: sudut membulat (kubik) diputar ang derajat di sekitar pusat."""
    t = math.radians(ang)
    co, si = math.cos(t), math.sin(t)
    P = lambda x, y: (cx + x * co - y * si, cy + x * si + y * co)  # noqa: E731
    k = r * 0.55228475
    hw, hh = w / 2, h / 2
    seq = [('M', [(-hw + r, -hh)]), ('L', [(hw - r, -hh)]), ('C', [(hw - r + k, -hh), (hw, -hh + r - k), (hw, -hh + r)]),
           ('L', [(hw, hh - r)]), ('C', [(hw, hh - r + k), (hw - r + k, hh), (hw - r, hh)]),
           ('L', [(-hw + r, hh)]), ('C', [(-hw + r - k, hh), (-hw, hh - r + k), (-hw, hh - r)]),
           ('L', [(-hw, -hh + r)]), ('C', [(-hw, -hh + r - k), (-hw + r - k, -hh), (-hw + r, -hh)])]
    d = ''
    for cmd, pts in seq:
        d += cmd + ' '.join(f'{X:.1f} {Y:.1f}' for X, Y in (P(*p) for p in pts)) + ' '
    return path(d + 'Z', c)


def bar(x0, y0, x1, y1, w, c):
    """Garis tebal w sebagai poligon (stroke dijadikan fill)."""
    L = math.hypot(x1 - x0, y1 - y0) or 1
    nx, ny = -(y1 - y0) / L * w / 2, (x1 - x0) / L * w / 2
    return poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], c)


def arcband(cx, cy, rx, ry, a0, a1, w, c, n=40):
    """Busur tipis (garis lengkung) sebagai pita tertutup."""
    angs = [math.radians(a0 + (a1 - a0) * i / n) for i in range(n + 1)]
    out = [(cx + (rx + w / 2) * math.cos(t), cy + (ry + w / 2) * math.sin(t)) for t in angs]
    inn = [(cx + (rx - w / 2) * math.cos(t), cy + (ry - w / 2) * math.sin(t)) for t in reversed(angs)]
    return poly([(round(x, 1), round(y, 1)) for x, y in out + inn], c)


def a09():
    s = Scene('A09', 'VECTALLY_A09_Three_Signs_Your_Books_Need_Attention.png', BG)

    # ---- pecahan latar (diukur, sisi lurus)
    s.add('RAYS_UNGU', 'Pecahan ungu latar', 'ornament', [
        poly([[0, 138], [0, 225], [155, 349], [157, 310]], PU),
        poly([[939, 0], [846, 2], [700, 242], [684, 214], [551, 124], [573, 153], [587, 191], [590, 227], [582, 277], [670, 339], [706, 261]], PU),
        poly([[1039, 247], [629, 430], [993, 287], [999, 288], [991, 308], [1018, 300]], PU),
        poly([[1121, 308], [1068, 337], [1056, 450], [1121, 426]], PU),
        poly([[99, 647], [0, 713], [0, 762]], PU),
        poly([[753, 690], [650, 732], [744, 699]], PU),
        poly([[966, 621], [938, 631], [936, 619], [835, 658], [810, 673], [909, 641], [862, 759], [439, 924], [439, 930], [909, 762]], PU),
        poly([[781, 909], [574, 1060], [568, 1099], [554, 1118], [577, 1125]], PU)])
    s.add('RAYS_GELAP', 'Pecahan gelap latar', 'ornament', [
        poly([[730, 54], [814, 54], [845, 0], [752, 0]], DK),
        poly([[810, 58], [727, 58], [666, 201], [690, 218], [700, 237]], DK),
        poly([[1121, 123], [956, 247], [965, 278], [1121, 210]], DK),
        poly([[841, 187], [706, 266], [713, 290], [713, 328], [707, 356], [689, 400], [734, 381], [819, 226], [810, 225], [824, 218]], DK),
        poly([[953, 251], [850, 328], [958, 281]], DK),
        poly([[0, 227], [0, 302], [144, 386], [153, 350]], DK),
        poly([[419, 316], [137, 428], [251, 488], [259, 439], [357, 400], [379, 387], [403, 357]], DK),
        poly([[183, 519], [1, 574], [0, 648]], DK),
        poly([[384, 567], [374, 557], [356, 556], [285, 582], [245, 562], [135, 609], [192, 629], [207, 625], [340, 672], [360, 655], [372, 633]], DK),
        poly([[906, 644], [765, 691], [806, 671], [743, 701], [620, 742], [480, 796], [473, 820], [446, 812], [248, 890], [316, 909], [465, 855], [453, 916], [861, 758]], DK),
        poly([[157, 865], [116, 849], [77, 811], [0, 904], [0, 939]], DK),
        poly([[816, 818], [774, 812], [685, 844], [625, 996]], DK),
        poly([[131, 1135], [0, 1245], [0, 1401], [52, 1401], [104, 1347]], DK)])

    # ---- plat gelap SIGNS (badan utuh, huruf di atasnya)
    s.add('PLAT_SIGNS', 'Plat gelap SIGNS', 'label', [
        poly([[576, 453], [996, 289], [1041, 245], [1121, 306], [1066, 339], [1040, 578], [441, 805], [503, 498], [530, 488], [530, 472]], DK)])

    # ---- angka 3 tiga dimensi: ekstrusi ungu, sisi hijau dalam, muka putih
    roi3 = [[50, 700], [130, 330], [160, 200], [460, 95], [565, 105], [705, 235], [705, 305], [565, 455], [525, 470], [478, 620], [462, 840], [260, 915], [55, 890]]
    s.add('ANGKA3', 'Angka 3 (3D)', 'numeral', [
        poly([[668, 345], [666, 339], [580, 278], [566, 308], [540, 344], [506, 379], [479, 399], [571, 455], [613, 424]], DK),
        *s.ink((40, 90, 715, 925), PU2, 'purple', None, [roi3], minarea=60),
        poly([[439, 245], [299, 299], [296, 305], [298, 313], [293, 316], [279, 364], [295, 363], [420, 313], [436, 266]], GF),
        *s.ink((40, 90, 715, 925), WH, 'white', None, [roi3], minarea=60)], 'Muka putih, ekstrusi ungu dan sisi hijau satu grup.')

    # ---- huruf (outline dari sumber; diganti teks native/TypeCraft di tahap teks)
    s.add('T_SIGNS', 'SIGNS', 'lettering', s.ink((470, 270, 1062, 812), WH, 'white', DK, [[[478, 470], [1062, 268], [1062, 612], [478, 806]]]))
    s.add('T_BOOKS', 'YOUR BOOKS', 'lettering', s.ink((478, 690, 815, 900), GR, 'green', DK, [[[484, 790], [806, 676], [814, 782], [492, 894]]]))
    s.add('T_NEED', 'NEED', 'lettering', s.ink((110, 915, 570, 1130), DK, 'dark', BG))
    s.add('T_ATTENTION', 'ATTENTION.', 'lettering', s.ink((100, 1125, 1075, 1360), WH, 'white', BG))

    # ---- kartu ikon (roundrect miring) dan isinya (primitif terukur)
    s.add('KARTU1', 'Kartu ikon grafik', 'icon', [
        rrot(999, 790, 107, 104, 9.6, 11, DK),
        poly([[957, 791], [971, 790], [972, 818], [958, 819]], IP),
        poly([[974, 778], [990, 776], [992, 820], [976, 822]], GR),
        poly([[995, 760], [1010, 758], [1011, 824], [997, 825]], GR),
        ellipse(1026.7, 788.7, 23, 23, DK), ellipse(1026.7, 788.7, 20, 20, IP),
        bar(1018, 780, 1035, 797, 5, DK), bar(1035, 780, 1018, 797, 5, DK)])
    s.add('KARTU2', 'Kartu ikon dokumen', 'icon', [
        rrot(946, 925, 109, 102, 8.9, 11, DK),
        bar(913, 893, 976, 901, 4, GR), bar(912, 893, 910, 957, 4, GR), bar(910, 957, 946, 961, 4, GR), bar(976, 901, 975, 932, 4, GR),
        poly([[947, 889], [954, 889], [954, 900], [947, 900]], GR),
        bar(931, 911, 961, 917, 4, GR), bar(931, 924, 958, 928, 4, GR), bar(926, 938, 948, 941, 4, GR),
        ellipse(971, 951, 21, 21, DK), ellipse(971, 951, 18.3, 18.3, IP),
        bar(969.5, 941, 971, 953, 4, DK), bar(971, 953, 977.7, 954, 4, DK)])
    s.add('KARTU3', 'Kartu ikon jam', 'icon', [
        rrot(864.5, 1052.5, 108.5, 100, 9.5, 11, DK),
        poly([[823, 1054], [836, 1053], [836, 1086], [823, 1087]], IP),
        poly([[837, 1042], [855, 1040], [856, 1086], [838, 1087]], GR),
        poly([[857, 1024], [871, 1022], [872, 1088], [858, 1089]], GR),
        ellipse(890.7, 1062.7, 22, 22, DK), ellipse(890.7, 1062.7, 19.3, 19.3, IP),
        bar(890.7, 1051, 892, 1066, 4, DK), bar(892, 1066, 900.7, 1067.7, 4, DK)])
    s.add('PENGHUBUNG', 'Garis penghubung dan titik', 'connector', [
        arcband(955, 875, 105, 230, -95, 110, 2.2, DK), ellipse(1047, 982, 10, 10, WH),
        arcband(870, 300, 92, 95, -88, 0, 2.2, DK), bar(800, 216, 862, 207, 2.2, DK),
        poly([[858, 198], [881, 205], [858, 213]], WH)])
    s.add('GARIS_PUTIH', 'Garis putih tipis kiri', 'ornament', [bar(0, 892, 79, 807, 3, WH)])

    # ---- header
    s.add('HEADER', 'Logo VECTALLY, garis, ///', 'brand', [
        *s.ink((70, 40, 272, 78), DK, 'dark', BG), ellipse(277, 64.4, 3.5, 3.5, '#7a55f0'),
        rect(310, 55, 660, 2, '#0b2a2a'), *s.ink((990, 40, 1058, 72), DK, 'dark', BG)])
    return s


if __name__ == '__main__':
    a09().export()

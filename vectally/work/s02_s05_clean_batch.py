"""Bangun ASSETS_CLEAN_PACKAGE S02-S05: tepi bersih dan hanya font brand.

Asap Condensed dibuang karena di luar daftar brand; headline itu menyusul lewat
TypeCraft. Label OR S03 dipindah ke Asap bold italic. Paket lama tidak ditimpa.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import smooth_native_paths as S  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "outputs/VECTALLY-story-repair"
SRC = {"S02": "ASSETS_DISPLAY_COPY_PACKAGE.json", "S03": "ASSETS_PARTIAL_COPY_PACKAGE.json",
       "S04": "ASSETS_DISPLAY_COPY_PACKAGE.json", "S05": "ASSETS_DISPLAY_COPY_PACKAGE.json"}


FIX = {"S04": {"VECTALLY": (58.5, 48.25), "IT'S THE": (54, 198)},
       "S05": {"VECTALLY": (62.5, 73.5), "GOT A": (42.5, 243.25), "BOOKKEEPING": (-288.5, 678.5), "QUESTION?": (280, 1235.5)}}


def clean_text(es):
    out = []
    for e in es:
        if e.get("type") == "group":
            e["children"] = clean_text(e["children"])
        if e.get("type") == "text" and e.get("fontFamily") == "Asap Condensed":
            if e["text"] != "OR":
                continue
            e.update(fontFamily="Asap", fontRef="YAFdJr0OaFw:0", fontWeight="bold", fontStyle="italic",
                     fontSize=63, letterSpacingEm=-0.04, rotation=4)
        out.append(e)
    return out


def count(es):
    n = 0
    for e in es:
        n += count(e["children"]) if e.get("type") == "group" else int(e.get("type") == "text")
    return n


for code, name in SRC.items():
    dst = R / code / "ASSETS_GEOM_PACKAGE.json"
    if dst.exists():
        raise SystemExit(f"Sudah ada, tidak ditimpa: {dst}")
    pkg = json.load(open(R / code / name, encoding="utf-8"))
    log = []
    S.walk(pkg["elements"], log)
    pkg["elements"] = clean_text(pkg["elements"])
    for e in pkg["elements"]:
        if e.get("type") == "text" and e["text"] in FIX.get(code, {}):
            e["left"], e["top"] = FIX[code][e["text"]]
    pkg["source"] = f"{code} - ASET BERSIH, FONT BRAND - HEADLINE TYPECRAFT MENYUSUL"
    pkg.setdefault("summary", {})["text"] = count(pkg["elements"])
    json.dump(pkg, open(dst, "w", encoding="utf-8"), ensure_ascii=False)
    kinds = {}
    for _, s in log:
        kinds[s.split()[0]] = kinds.get(s.split()[0], 0) + 1
    print(code, kinds, "text", pkg["summary"]["text"], [n for n, s in log if s == "rejected"], flush=True)

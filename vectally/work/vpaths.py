"""Portable paths for the VECTALLY recipes (replaces the old Windows-only D:/ and C:/ paths).

Every recipe imports this module first. It:
  - resolves the repository root (env VECTALLY_ROOT, default: parent of work/)
  - resolves the source PNG folder (env VECTALLY_SOURCES, default: <root>/sources/VECTALLY)
  - makes <root> the working directory, so the recipes' relative output paths
    (outputs/VECTALLY-...) land in the repository, exactly as the PowerShell runner did
  - gives a font for REPORT LABELS only (contact sheets). Design copy never uses it:
    design fonts come from outputs/VECTALLY-teks-native/fonts and are validated separately.
"""
import os
from pathlib import Path

ROOT = Path(os.environ.get("VECTALLY_ROOT") or Path(__file__).resolve().parent.parent).resolve()
VSRC = Path(os.environ.get("VECTALLY_SOURCES") or ROOT / "sources" / "VECTALLY").resolve()
VSRC_ = VSRC.as_posix()

_REPORT_FONTS = [
    os.environ.get("VECTALLY_REPORT_FONT", ""),
    "C:/Windows/Fonts/segoeuib.ttf",  # original Windows runner
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
REPORT_FONT_ = next((f for f in _REPORT_FONTS if f and Path(f).is_file()), None)
if REPORT_FONT_ is None:
    raise SystemExit("Tidak ada font untuk LABEL LAPORAN. Set VECTALLY_REPORT_FONT ke file .ttf.")

if not VSRC.is_dir():
    raise SystemExit(f"Folder sumber tidak ditemukan: {VSRC} (set VECTALLY_SOURCES)")

os.chdir(ROOT)

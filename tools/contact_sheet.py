"""Rebuild contact sheets for already processed designs:  python tools/contact_sheet.py out"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.contact_sheet import main  # noqa: E402

sys.exit(main())

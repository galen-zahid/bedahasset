"""Split flattened AI-generated social feed designs into editable layers for Canva.

Usage:
    python split.py in/ out/            # batch all PNGs in folder
    python split.py in/x.png out/       # single file
    python split.py in/ out/ --force    # re-process even if already done
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
import warnings
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
warnings.filterwarnings("ignore")

log = logging.getLogger("split")


def setup_logging(out_root: Path):
    out_root.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(out_root / "log.txt", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.setLevel(logging.INFO)
    log.handlers[:] = [fh, sh]
    log.propagate = False
    for noisy in ("transformers", "huggingface_hub", "PIL", "numba", "easyocr"):
        logging.getLogger(noisy).setLevel(logging.ERROR)


def collect(inp: Path):
    if inp.is_file():
        return [inp]
    return sorted(p for p in inp.iterdir() if p.is_file() and p.suffix.lower() == ".png")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="folder of PNGs or a single PNG")
    ap.add_argument("output", type=Path, help="output folder")
    ap.add_argument("--config", type=Path, default=None, help="path to config.yaml")
    ap.add_argument("--force", action="store_true", help="re-process designs already done")
    args = ap.parse_args(argv)

    setup_logging(args.output)
    if not args.input.exists():
        log.error("input tidak ditemukan: %s", args.input)
        return 2

    from pipeline.config import load_config
    from pipeline.runner import is_done, process

    cfg = load_config(args.config)
    files = collect(args.input)
    log.info("=== %d file PNG di %s ===", len(files), args.input)
    todo = []
    for f in files:
        if not args.force and is_done(args.output / f.stem):
            log.info("skip (sudah selesai): %s", f.name)
        else:
            todo.append(f)
    if not todo:
        log.info("tidak ada yang perlu diproses")
        return 0

    from pipeline.models import Models

    models = Models(cfg)
    ok, failed = 0, []
    t_all = time.time()
    for i, f in enumerate(todo, 1):
        log.info("--- (%d/%d) %s", i, len(todo), f.name)
        try:
            process(f, args.output, models, cfg)
            ok += 1
        except KeyboardInterrupt:
            log.warning("dihentikan user")
            break
        except Exception as e:  # one bad file must not stop the batch
            failed.append(f.name)
            log.error("GAGAL %s: %s\n%s", f.name, e, traceback.format_exc())
    log.info("=== selesai: %d ok, %d gagal, %.0fs ===", ok, len(failed), time.time() - t_all)
    if failed:
        log.info("gagal: %s", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

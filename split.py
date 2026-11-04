"""Split flattened AI-generated social feed designs into editable layers for Canva.

Usage:
    python split.py in out                   # batch every PNG/JPG in a folder
    python split.py in\\x.png out            # single file
    python split.py in out --force           # re-process designs already done
    python split.py --download-models        # only download / verify the AI models
    python split.py --check                  # check the installation
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

warnings.filterwarnings("ignore")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # noisy on Windows
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
for _s in (sys.stdout, sys.stderr):  # Windows consoles (cp1252/cp437) must never crash a run
    try:
        _s.reconfigure(errors="replace")
    except Exception:  # noqa: BLE001
        pass

log = logging.getLogger("split")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def setup_logging(out_root: Path | None):
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    handlers = []
    if out_root is not None:
        out_root.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(out_root / "log.txt", encoding="utf-8")
        fh.setFormatter(fmt)
        handlers.append(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    handlers.append(sh)
    log.setLevel(logging.INFO)
    log.handlers[:] = handlers
    log.propagate = False
    for noisy in ("transformers", "huggingface_hub", "PIL", "numba", "easyocr", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.ERROR)


def apply_cache_dir(cfg):
    """Optional: keep every model cache in one folder (e.g. on a drive with free space)."""
    d = cfg.get("cache_dir") or os.environ.get("BEDAH_CACHE")
    if not d:
        return
    d = Path(d).expanduser().resolve()
    for var, sub in (("HF_HOME", "hf"), ("TORCH_HOME", "torch"), ("REMBG_HOME", "rembg"),
                     ("EASYOCR_MODULE_PATH", "easyocr")):
        os.environ.setdefault(var, str(d / sub))
    log.info("cache model: %s", d)


def collect(inp: Path):
    if inp.is_file():
        return [inp]
    return sorted(p for p in inp.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT)


def check_install(cfg) -> int:
    import importlib
    import shutil

    ok = True
    log.info("Python %s (%s)", sys.version.split()[0], sys.executable)
    if sys.version_info[:2] != (3, 11):
        log.warning("disarankan Python 3.11")
    for mod in ("numpy", "cv2", "PIL", "skimage", "yaml", "torch", "rembg", "onnxruntime",
                "pymatting", "transformers", "easyocr", "simple_lama_inpainting", "requests"):
        try:
            m = importlib.import_module(mod)
            log.info("  ok  %-24s %s", mod, getattr(m, "__version__", ""))
        except Exception as e:  # noqa: BLE001
            ok = False
            log.error("  X   %-24s %s", mod, e)
    try:
        import torch

        log.info("GPU CUDA: %s", "ya" if torch.cuda.is_available() else "tidak (pakai CPU)")
    except Exception:  # noqa: BLE001
        pass
    home = Path.home()
    free = shutil.disk_usage(home).free / 1e9
    log.info("ruang kosong di drive %s: %.1f GB (model butuh ~2 GB)", home.anchor, free)
    if free < 3:
        log.warning("ruang disk tipis; set cache_dir di config.yaml ke drive lain")
    log.info("instalasi %s", "OK" if ok else "BELUM LENGKAP")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, nargs="?", help="folder berisi gambar, atau satu file")
    ap.add_argument("output", type=Path, nargs="?", help="folder output")
    ap.add_argument("--config", type=Path, default=None, help="path ke config.yaml")
    ap.add_argument("--force", action="store_true", help="proses ulang desain yang sudah selesai")
    ap.add_argument("--download-models", action="store_true", help="hanya download/cek model AI")
    ap.add_argument("--check", action="store_true", help="cek instalasi")
    args = ap.parse_args(argv)

    from pipeline.config import load_config

    if args.check or args.download_models:
        setup_logging(None)
        cfg = load_config(args.config)
        apply_cache_dir(cfg)
        if args.check:
            return check_install(cfg)
        from pipeline.download import ensure_models

        ensure_models(cfg)
        return 0

    if args.input is None or args.output is None:
        ap.print_help()
        return 2
    args.input, args.output = args.input.resolve(), args.output.resolve()
    setup_logging(args.output)
    if not args.input.exists():
        log.error("input tidak ditemukan: %s", args.input)
        return 2

    from pipeline.runner import is_done, process

    cfg = load_config(args.config)
    apply_cache_dir(cfg)
    files = collect(args.input)
    log.info("=== %d gambar di %s ===", len(files), args.input)
    todo = []
    for f in files:
        if not args.force and is_done(args.output / f.stem):
            log.info("skip (sudah selesai): %s", f.name)
        else:
            todo.append(f)
    if not todo:
        log.info("tidak ada yang perlu diproses")
        return 0

    try:
        from pipeline.download import ensure_models

        ensure_models(cfg)
    except Exception as e:  # noqa: BLE001
        log.error("model AI belum lengkap: %s\nJalankan lagi (download akan dilanjutkan).", e)
        return 3

    from pipeline.models import Models

    models = Models(cfg)
    ok, failed = 0, []
    t_all = time.time()
    for i, f in enumerate(todo, 1):
        log.info("--- (%d/%d) %s", i, len(todo), f.name)
        t0 = time.time()
        try:
            process(f, args.output, models, cfg)
            ok += 1
            done = time.time() - t_all
            eta = done / i * (len(todo) - i)
            log.info("    %.0f dtk | sisa perkiraan %.0f menit", time.time() - t0, eta / 60)
        except KeyboardInterrupt:
            log.warning("dihentikan user (yang sudah selesai tidak akan diulang)")
            break
        except Exception as e:  # one bad file must not stop the batch
            failed.append(f.name)
            log.error("GAGAL %s: %s\n%s", f.name, e, traceback.format_exc())
    log.info("=== selesai: %d ok, %d gagal, %.0f menit ===", ok, len(failed),
             (time.time() - t_all) / 60)
    if failed:
        log.info("gagal: %s", ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Robust first-run model download: resumable, retried, checksum-verified.

The libraries' own downloaders restart from zero when a connection drops (a 1 GB model on a
flaky line never finishes) and some accept a half-written file afterwards. This module fetches
every model into the exact place each library looks for it, so they find it and never
download themselves.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("split")

BIREFNET_URL = ("https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
                "BiRefNet-general-epoch_244.onnx")
BIREFNET_MD5 = "7a35a0141cbbc80de11d9c9a28f52697"
LAMA_URL = ("https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/"
            "big-lama.pt")


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, md5: str | None = None, attempts: int = 60) -> Path:
    """Download url -> dest, resuming a partial `dest.part` after every dropped connection."""
    import requests

    dest = Path(dest)
    if dest.exists() and dest.stat().st_size > 0:
        if md5 is None or _md5(dest) == md5:
            return dest
        log.warning("file model rusak/tidak lengkap, download ulang: %s", dest)
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    total = None
    last_print = 0.0
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=(15, 60),
                              allow_redirects=True) as r:
                if r.status_code == 416:  # already complete
                    break
                r.raise_for_status()
                if have and r.status_code != 206:  # server ignored Range -> restart
                    have = 0
                    part.unlink(missing_ok=True)
                length = int(r.headers.get("Content-Length", 0))
                total = have + length if length else total
                with open(part, "ab") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                        have += len(chunk)
                        now = time.time()
                        if now - last_print > 5:
                            last_print = now
                            pct = f"{100 * have / total:5.1f}%" if total else ""
                            log.info("  %s  %s  %.0f / %.0f MB", dest.name, pct, have / 1e6,
                                     (total or 0) / 1e6)
            if total is None or have >= total:
                break
        except Exception as e:  # noqa: BLE001 - network hiccups: wait and resume
            wait = min(30, 2 * attempt)
            log.warning("  koneksi putus (%s), lanjut lagi dalam %ds (percobaan %d/%d)",
                        type(e).__name__, wait, attempt, attempts)
            time.sleep(wait)
    else:
        raise RuntimeError(f"gagal download {url} setelah {attempts} percobaan")
    if md5 is not None and _md5(part) != md5:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"checksum salah untuk {dest.name}; jalankan lagi untuk download ulang")
    os.replace(part, dest)
    return dest


def _retry(fn, what: str, attempts: int = 10):
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == attempts:
                raise
            wait = min(30, 3 * i)
            log.warning("  %s gagal (%s), coba lagi dalam %ds (%d/%d)", what, type(e).__name__,
                        wait, i, attempts)
            time.sleep(wait)


def ensure_models(cfg) -> None:
    """Make sure every model the config needs is present locally (downloads only if missing)."""
    # 1. BiRefNet (rembg)
    if cfg.subject.rembg_model == "birefnet-general":
        from rembg.sessions.birefnet_general import BiRefNetSessionGeneral

        fname = "birefnet-general.onnx"
        existing = BiRefNetSessionGeneral.resolve_existing(fname)
        dest = Path(existing) if existing else Path(BiRefNetSessionGeneral.model_dir()) / fname
        if not (dest.exists() and dest.stat().st_size > 900_000_000):
            log.info("download model BiRefNet (~970 MB) -> %s", dest)
        fetch(BIREFNET_URL, dest, BIREFNET_MD5)

    # 2. LaMa
    from simple_lama_inpainting.utils.util import get_cache_path_by_url

    lama = Path(os.environ.get("LAMA_MODEL") or get_cache_path_by_url(LAMA_URL))
    if not lama.exists():
        log.info("download model LaMa (~200 MB) -> %s", lama)
    fetch(LAMA_URL, lama)

    # 3. HuggingFace models (hub resumes partial files itself; we only retry)
    from huggingface_hub import snapshot_download

    repos = []
    if cfg.foreground.enabled:
        repos.append(cfg.foreground.depth_model)
    if cfg.particles.enabled and cfg.particles.cloud.enabled:
        repos.append(cfg.particles.cloud.model)
    if cfg.elements.enabled and cfg.elements.sam:
        repos.append(cfg.elements.sam_model)
    for repo in repos:
        try:
            snapshot_download(repo, local_files_only=True)
            continue
        except Exception:  # noqa: BLE001 - not cached yet
            pass
        log.info("download model %s", repo)
        _retry(lambda r=repo: snapshot_download(r), repo)

    # 4. EasyOCR (small zips, its own downloader; retried)
    if cfg.text.enabled:
        import easyocr

        _retry(lambda: easyocr.Reader(list(cfg.text.languages), gpu=False, verbose=False),
               "EasyOCR")
    log.info("semua model siap")

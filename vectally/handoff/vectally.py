"""Cross-platform VECTALLY runner (Python port of handoff/Vectally.ps1, SAME jobs.json).

    python3 handoff/vectally.py Status
    python3 handoff/vectally.py Doctor
    python3 handoff/vectally.py Audit
    python3 handoff/vectally.py BuildGraphics --codes S03 S04
    python3 handoff/vectally.py BuildGraphics --all-supported
    python3 handoff/vectally.py Compose --codes S04
    python3 handoff/vectally.py Compare --codes S06
    python3 handoff/vectally.py Verify --codes S03      # rebuild into a scratch copy, compare with the committed package

Environment:
    VECTALLY_PYTHON   interpreter for the recipes (default: <root>/.venv python, else this one)
    VECTALLY_SOURCES  folder with Feed/Story/Highlight PNGs (default: <root>/sources/VECTALLY)
    VECTALLY_ROOT     repository root (default: parent of handoff/)

Same behaviour as the PowerShell runner: recipes run in order from the repo root, the output
folder is backed up before BuildGraphics/Compose, every log goes to handoff/runs/<time>-<action>,
and a candidate package that fails the package/font audit stops the run (exit 2). It never
imports to Canva, uploads fonts or publishes the app. Exit 0 is NOT a 1:1 / buyer certification.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

HANDOFF = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("VECTALLY_ROOT") or HANDOFF.parent).resolve()
MANIFEST = HANDOFF / "jobs.json"
CATALOGUE = HANDOFF / "FONT_CATALOGUE.json"
sys.path.insert(0, str(HANDOFF))
from audit_package import audit  # noqa: E402

ACTION_FIELD = {"BuildGraphics": "build", "Compose": "compose", "Compare": "compare", "Verify": "build"}


def python_exe() -> str:
    env = os.environ.get("VECTALLY_PYTHON")
    if env:
        return env
    for cand in (ROOT / ".venv/bin/python", ROOT / ".venv/Scripts/python.exe"):
        if cand.is_file():
            return str(cand)
    return sys.executable


def inside_root(rel: str) -> Path:
    full = (ROOT / rel).resolve()
    if ROOT not in full.parents and full != ROOT:
        raise SystemExit(f"Path di luar workspace ditolak: {rel}")
    return full


def run_dir(action: str) -> Path:
    d = HANDOFF / "runs" / f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}-{action}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_step(step: dict, log: Path, env: dict) -> None:
    script = inside_root(step["script"])
    if not script.is_file():
        raise SystemExit(f"Script hilang: {script}")
    engine = python_exe() if step["engine"] == "python" else (shutil.which("node") or "node")
    cmd = [engine, str(script), *step.get("args", [])]
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"$ {' '.join(cmd)}\n")
        fh.flush()
        proc = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, env=env)
    if proc.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-1500:]
        raise SystemExit(f"Proses gagal (exit {proc.returncode}): {script}\n{tail}\nLog: {log}")


def package_audit(paths: list[Path], output: Path) -> int:
    cat = json.loads(CATALOGUE.read_text(encoding="utf-8-sig"))
    res = [audit(p, cat) for p in paths]
    output.write_text(json.dumps(dict(packages=res, finalVerified=False,
                                      notice="PASS struktural bukan bukti 1:1, objek lengkap, atau buyer PASS."),
                                 indent=2, ensure_ascii=False), encoding="utf-8")
    bad = [r for r in res if r["errors"]]
    for r in bad:
        print(f"  BLOCKER {Path(r['path']).relative_to(ROOT)}: {r['errors'][:3]}{' ...' if len(r['errors']) > 3 else ''}")
    return 2 if bad else 0


def cmd_status(_a) -> int:
    rows = list(csv.DictReader((HANDOFF / "VECTALLY_STATUS.csv").open(encoding="utf-8-sig")))
    for phase, n in Counter(r["phase"] for r in rows).most_common():
        print(f"  {phase:45s} {n}")
    print(f"{len(rows)} sumber; finalVerified={sum(r['finalVerified'] == 'True' for r in rows)}. "
          "Tidak ada pernyataan 100% final. Baca REPORT_VECTALLY.md dan STATE.json.")
    return 0


def cmd_doctor(_a) -> int:
    py = python_exe()
    r = subprocess.run([py, "-c", "import sys,cv2,numpy,PIL,resvg_py,scipy,fontTools;print(sys.executable)"],
                       capture_output=True, text=True)
    print("python:", r.stdout.strip() or r.stderr.strip()[-300:])
    print("node:  ", shutil.which("node") or "TIDAK ADA")
    print("pwsh:  ", shutil.which("pwsh") or "tidak ada (runner Python ini dipakai)")
    src = Path(os.environ.get("VECTALLY_SOURCES") or ROOT / "sources/VECTALLY")
    print("sumber:", src, "ada" if src.is_dir() else "TIDAK ADA")
    print("Canva tidak dibuka atau diubah.")
    return 0 if r.returncode == 0 and shutil.which("node") and src.is_dir() else 1


def cmd_audit(_a) -> int:
    d = run_dir("Audit")
    sources = json.loads((HANDOFF / "CLOUD_SOURCES.json").read_text(encoding="utf-8"))["sources"]
    checks = []
    for s in sources:
        p = ROOT / s["path"]
        ok = p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == s["sha256"]
        checks.append(dict(code=s["code"], path=s["path"], exists=p.is_file(), hashMatches=ok))
    (d / "SOURCE_AUDIT.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    jobs = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    code = package_audit([ROOT / r["outputDir"] / r["candidatePackage"] for r in jobs["recipes"]],
                         d / "PACKAGE_AUDIT.json")
    bad = sum(not c["hashMatches"] for c in checks)
    print(f"Sumber: {len(checks)}; bermasalah: {bad}. Laporan: {d.relative_to(ROOT)}")
    print("Font Asap heavy pada kandidat S06 memang harus menghasilkan blocker.")
    return 2 if bad or code else 0


def select(action: str, a) -> tuple[list[dict], list[str]]:
    jobs = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    field = ACTION_FIELD[action]
    recipes = [r for r in jobs["recipes"] if r.get(field)]
    supported = [r["code"] for r in recipes]
    codes = supported if a.all_supported else (a.codes or [])
    if a.all_supported and a.codes:
        raise SystemExit("Pilih --codes atau --all-supported, jangan keduanya.")
    if not codes:
        raise SystemExit(f"Sebutkan --codes. Yang didukung untuk {action}: {', '.join(supported)}")
    for c in codes:
        if c not in supported:
            raise SystemExit(f"Belum ada resep {action} untuk {c}. Tidak akan menebak atau mengganti metode.")
    return recipes, codes


def cmd_recipe(action: str, a) -> int:
    recipes, codes = select(action, a)
    d = run_dir(action)
    env = dict(os.environ, VECTALLY_ROOT=str(ROOT), PYTHONDONTWRITEBYTECODE="1")
    seen = set()
    for code in codes:
        r = next(x for x in recipes if x["code"] == code)
        out = inside_root(r["outputDir"])
        if action in ("BuildGraphics", "Compose") and out.exists():
            shutil.copytree(out, d / "backup" / code)
        for step in r[ACTION_FIELD[action]]:
            key = json.dumps(step, sort_keys=True)
            if key in seen:  # S03/S04 share one builder
                continue
            seen.add(key)
            print(f"  {code}: {step['script']} {' '.join(step.get('args', []))}")
            run_step(step, d / f"{code}.log", env)
        if action in ("BuildGraphics", "Compose"):
            pkg = out / (r["graphicsPackage"] if action == "BuildGraphics" else r["candidatePackage"])
            if package_audit([pkg], d / f"{code}-package-audit.json"):
                print(f"Paket {code} diblokir audit. Tidak ada unggahan Canva. Lihat {d.relative_to(ROOT)}")
                return 2
    print(f"Selesai: {', '.join(codes)}. Laporan: {d.relative_to(ROOT)}")
    print("Ini bukan sertifikasi final. Impor Canva, ekspor aktual, pemeriksaan visual dan buyer test tetap diperlukan.")
    return 0


def _canon(p: Path):
    return json.loads(p.read_text(encoding="utf-8-sig"))


def _leaves(e, out, addr=""):
    if isinstance(e, dict):
        for k, v in e.items():
            _leaves(v, out, f"{addr}/{k}")
    elif isinstance(e, list):
        for i, v in enumerate(e):
            _leaves(v, out, f"{addr}[{i}]")
    else:
        out[addr] = e


def _render_equivalent(old: Path, new: Path, report: Path) -> bool:
    """True when the only differences are path 'd' strings that rasterise to identical pixels."""
    code = (
        "import json,sys,io,numpy as np,resvg_py\n"
        "from PIL import Image\n"
        "a,b,items=json.loads(sys.stdin.read())\n"
        "out=[]\n"
        "for vb,da,db in items:\n"
        "  m=[]\n"
        "  for d in (da,db):\n"
        "    w,h=int(vb['width'])+4,int(vb['height'])+4\n"
        "    s=f'<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"{w}\" height=\"{h}\" viewBox=\"{vb[\"left\"]-2} {vb[\"top\"]-2} {w} {h}\"><path d=\"{d}\" fill=\"#000\"/></svg>'\n"
        "    m.append(np.asarray(Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=s)))).convert('RGBA'))[...,3]>127)\n"
        "  out.append(int((m[0]^m[1]).sum()))\n"
        "print(json.dumps(out))\n")
    A, B = {}, {}
    _leaves(_canon(old), A)
    _leaves(_canon(new), B)
    diff = [k for k in set(A) | set(B) if A.get(k) != B.get(k)]
    if not diff or any(not k.endswith("/d") for k in diff):
        report.write_text(json.dumps(dict(nonPathDifferences=[k for k in diff if not k.endswith("/d")]), indent=2))
        return False
    pa, pb = _canon(old), _canon(new)
    items = []
    for k in diff:
        node_path = k.rsplit("/paths[", 1)[0]
        node = pa
        for part in node_path.strip("/").replace("[", "/[").split("/"):
            if part:
                node = node[int(part[1:-1])] if part.startswith("[") else node[part]
        items.append([node["viewBox"], A[k], B[k]])
    r = subprocess.run([python_exe(), "-c", code], input=json.dumps([None, None, items]),
                       capture_output=True, text=True)
    if r.returncode:
        report.write_text(r.stderr)
        return False
    px = json.loads(r.stdout)
    report.write_text(json.dumps(dict(differingPaths=diff, differingPixels=px), indent=2))
    return all(p == 0 for p in px)


def cmd_verify(a) -> int:
    """Rebuild in a throw-away copy of the repo and compare packages with the committed ones."""
    recipes, codes = select("Verify", a)
    d = run_dir("Verify")
    tmp = d / "workspace"
    for sub in ("work", "outputs"):
        shutil.copytree(ROOT / sub, tmp / sub)
    env = dict(os.environ, VECTALLY_ROOT=str(tmp),
               VECTALLY_SOURCES=os.environ.get("VECTALLY_SOURCES") or str(ROOT / "sources/VECTALLY"),
               PYTHONDONTWRITEBYTECODE="1")
    report, seen, worst = [], set(), 0
    for code in codes:
        r = next(x for x in recipes if x["code"] == code)
        for step in r["build"]:
            key = json.dumps(step, sort_keys=True)
            if key not in seen:
                seen.add(key)
                st = dict(step, script=str(tmp / step["script"]))
                cmd = [python_exe() if st["engine"] == "python" else "node", st["script"], *st.get("args", [])]
                with (d / f"{code}.log").open("a") as fh:
                    rc = subprocess.run(cmd, cwd=tmp, stdout=fh, stderr=subprocess.STDOUT, env=env).returncode
                if rc:
                    raise SystemExit(f"{code}: build gagal (exit {rc}), lihat {d / (code + '.log')}")
        name = r["graphicsPackage"]
        old, new = ROOT / r["outputDir"] / name, tmp / r["outputDir"] / name
        same = old.is_file() and new.is_file() and _canon(old) == _canon(new)
        ident = old.is_file() and new.is_file() and old.read_bytes() == new.read_bytes()
        render = None if same else _render_equivalent(old, new, d / f"{code}-render-check.json")
        report.append(dict(code=code, package=name, identicalBytes=ident, identicalJson=same,
                           renderEquivalent=render))
        label = "IDENTIK" if ident else "JSON SAMA" if same else \
            "SETARA RENDER (urutan titik path beda, piksel sama)" if render else "BERBEDA"
        print(f"  {code}: {name} {label}")
        worst = worst or (0 if same or render else 1)
    (d / "VERIFY.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"Laporan: {d.relative_to(ROOT)}")
    return worst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["Status", "Doctor", "Audit", "BuildGraphics", "Compose", "Compare", "Verify"])
    ap.add_argument("--codes", nargs="*")
    ap.add_argument("--all-supported", action="store_true")
    a = ap.parse_args()
    if a.action == "Status":
        return cmd_status(a)
    if a.action == "Doctor":
        return cmd_doctor(a)
    if a.action == "Audit":
        return cmd_audit(a)
    if a.action == "Verify":
        return cmd_verify(a)
    return cmd_recipe(a.action, a)


if __name__ == "__main__":
    raise SystemExit(main())

"""Siapkan job robot Canva untuk satu kode: salin paket NATIVE ke folder upload gateway (allowlist),
gabungkan quad TypeCraft, tulis JOB.json. Diadaptasi dari prepare_a07_fresh.py milik Codex.

Pemakaian: python prepare_job.py A09 [--box-json koreksi.json]
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_UPLOADS = Path('D:/Codex/cusbe-remote-mcp/uploads/vectally-recipes')


def walk(es):
    for e in es:
        if e['type'] == 'group':
            yield from walk(e['children'])
        else:
            yield e


def main(code, box_json=None):
    nat = ROOT / 'outputs' / 'VECTALLY-resep' / f'{code}-NATIVE'
    pkg = json.loads((nat / 'CANVA_PACKAGE.json').read_text(encoding='utf-8'))
    for e in walk(pkg['elements']):
        if e['type'] == 'text':
            e['fontFamily'] = e['fontName']  # sama dengan persiapan Codex untuk importer
    tc = json.loads((nat / 'TYPECRAFT_JOB.json').read_text(encoding='utf-8'))
    out = ROOT / 'outputs' / 'VECTALLY-canva' / code
    out.mkdir(parents=True, exist_ok=True)
    local = out / f'{code}_NATIVE_PACKAGE.json'
    local.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding='utf-8')
    GATEWAY_UPLOADS.mkdir(parents=True, exist_ok=True)
    stage = GATEWAY_UPLOADS / local.name
    shutil.copy2(local, stage)
    corr = json.loads(Path(box_json).read_text(encoding='utf-8')) if box_json else {}
    warps = []
    for w in tc['warps']:
        x0, y0, x1, y1 = w['bbox']
        box = corr.get(w['text']) or {'Lebar': round(x1 - x0, 1), 'X': round(x0, 1), 'Y': round(y0, 1)}
        warps.append(dict(text=w['text'], color=w['color'], quad=w['quad'], box=box, targetBBox=w['bbox']))
    s = pkg['summary']
    job = dict(code=code, packageFile=str(stage), packageSha256=hashlib.sha256(stage.read_bytes()).hexdigest(),
               expected=dict(native_shape=s['shape'], native_text=s['text']), warps=warps,
               createUrl='https://www.canva.com/design/editor/shell?create&width=1122&height=1402&units=px&ui=e30',
               downloadDirectory='D:/download', fidelity='NOT_TESTED')
    (out / 'JOB.json').write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(job=str(out / 'JOB.json'), package=str(stage), warps=[(w['text'], w['box']) for w in warps]), indent=1))


if __name__ == '__main__':
    a = sys.argv[1:]
    main(a[0], a[a.index('--box-json') + 1] if '--box-json' in a else None)

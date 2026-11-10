from pathlib import Path
import csv
import json
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "handoff"
rows = json.loads((ROOT / "outputs/VECTALLY-lengkap/progress.json").read_text())
font_report = json.loads((ROOT / "outputs/VECTALLY-native-font-runtime/S06_FONT_CATALOGUE.json").read_text())
fonts = font_report["fonts"] + [{
    "ref": "YAD1fmY3NpE:0", "name": "Asap Condensed",
    "weights": [
        {"weight": "normal", "styles": ["normal", "italic"]},
        {"weight": "bold", "styles": ["normal"]},
    ],
    "provenance": "Observed requestFontSelection response in importer v4; metadata only, never inserted."
}]
(OUT / "FONT_CATALOGUE.json").write_text(json.dumps({
    "observedDate": "2026-11-10",
    "notice": "Snapshot katalog akun saat audit, bukan daftar universal Canva.",
    "fonts": fonts
}, indent=2), encoding="utf-8")

stories = {
    "S01": (9, 76, 6, 6, "THE BOOKS dan STORY belum dipasang; body/label native, kertas/buku sudah diperbaiki."),
    "S02": (8, 42, 8, 6, "Headline utama belum dipasang; label native berada dalam grup aset; teks putih diperbaiki."),
    "S03": (10, 22, 2, 0, "Dua laporan utuh dan ornamen; semua copy masih belum dipasang."),
    "S04": (11, 24, 6, 4, "Tiga caption dan satu paragraf native; brand serta headline belum dipasang."),
    "S05": (3, 5, 0, 1, "Bingkai/aksen dan body prototype; headline belum dipasang; satu gradien native berhasil diuji."),
    "S06": (13, 47, 3, 8, "Semua copy native, tetapi varian Asap heavy tidak tersedia; fidelity gagal dan impor ulang diblokir v4."),
}
feed_drafts = {"A03", "A07", "A20", "A27", "A45"}
snapshots = []
for old in rows:
    code = old["code"]
    item = dict(code=code, family=old["family"], source=old["source"],
                width=old["width"], height=old["height"], sha256=old["sha256"],
                legacyStatus=old["status"], finalVerified=False)
    if code in stories:
        page, shapes, groups, texts, note = stories[code]
        item.update(phase="STORY_PROTOTYPE_NOT_FINAL", prototypePage=page,
                    nativeShapes=shapes, nativeGroups=groups, nativeText=texts, notes=note)
    elif code in feed_drafts:
        item.update(phase="FEED_CANVA_DRAFT_NOT_FINAL",
                    notes="Artwork sebelumnya diterima pengguna; native text pernah diverifikasi. Bukan bukti seluruh transform/font 1:1 atau buyer PASS final.")
    elif old["family"] == "Highlight":
        item.update(phase="HIGHLIGHT_NATIVE_DRAFT_PENDING_FINAL_QA",
                    notes="Geometri native sudah diekspor; gradien, simbol yang berfungsi sebagai copy, dan buyer QA final belum ditutup.")
    else:
        item.update(phase="NOT_READY",
                    notes="Belum memiliki kandidat native terbaru yang layak final; file eksperimen lama bukan hasil selesai.")
    snapshots.append(item)
state = dict(
    schemaVersion=1, createdUtc=datetime.now(timezone.utc).isoformat(),
    goalStatus="paused", task="HANDOFF_ONLY; no asset rebuild or Canva mutation requested now",
    scope=dict(total=84, Feed=48, Story=30, Highlight=6, editGuideAdditionalPage=True),
    counts=dict(uniqueSourcesWithCanvaDraft=17, notReady=67, finalCertified=0),
    mainDesign="https://www.canva.com/design/DAHaawX9Fm8/q-iGCT-epdpWj0UB7AXKGA/edit",
    prototypeDesign="https://www.canva.com/design/DAHabUK1x7c/XAKU7ev4LnkxUjedsUkoGw/edit",
    mainPages=11, prototypePages=20,
    currentPrototypePage=13,
    currentImporter="CUSBE Native Importer — audit font v4; private draft; 1306698-byte bundle saved",
    currentLoadedPackage="QA MUST REJECT UNSUPPORTED ASAp HEAVY V1; font-picker metadata changed selected package font to Asap Condensed. DO NOT ASSEMBLE THIS PROBE.",
    criticalFindings=[
        "Asap YAFdJr0OaFw:0 provides normal/medium/semibold/bold, no heavy.",
        "Asap Condensed YAD1fmY3NpE:0 provides normal/bold, no heavy.",
        "Archivo Black YACgEZulLoA:0 provides normal style only; Black is already the family design.",
        "SDK textRegions can retain requested heavy even when the available font catalogue has no heavy face. That field alone does not prove correct rendering.",
        "v4 now checks actual font weight/style availability for BOTH v1 and v2 packages before adding elements/pages.",
        "Unsupported Asap heavy v1 runtime probe rejected; page counter stayed 13/20.",
        "Native custom League Gothic wdth75 upload was not achieved. Static named instances exist locally and in TypeCraft only.",
        "S06 body second text wrapped at width441. Public Position width600 restored one-line height68.5.",
        "Source contour IoU and local-to-Canva MAE cannot certify whole-object semantics or source image fidelity."
    ],
    remaining=[
        "43 Feed and 24 Story sources not ready.",
        "Finish headlines/labels of existing partial Story candidates.",
        "Resolve exact supported native font faces and condensed/warped typography under approved hybrid policy.",
        "Restore and verify source gradients; grain/texture fidelity not complete.",
        "Repeat final whole-object move/recolor tests and text edit tests.",
        "Create final EDIT GUIDE, consolidate all84 in one correct design, and verify the actual final link and user access."
    ],
    sources=snapshots,
)
(OUT / "STATE.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
fields = ["code","family","phase","finalVerified","prototypePage","nativeShapes","nativeGroups","nativeText","width","height","source","sha256","notes","legacyStatus"]
with (OUT / "VECTALLY_STATUS.csv").open("w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(snapshots)
print(json.dumps({"sources": len(snapshots), "draftSources": 17, "notReady": 67, "finalCertified": 0}))

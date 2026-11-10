"""Bundle handoff context without credentials, node_modules, venv or source PNG archive."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime, timezone
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parent.parent
HANDOFF = ROOT / "handoff"
APP = Path("D:/cusbe-importer")

app_files = [
    "AGENTS.md", "package.json", "tsconfig.json", ".nvmrc",
    "src/index.tsx", "src/intents/design_editor/index.tsx",
    "src/intents/design_editor/app.tsx",
    "src/intents/design_editor/inspection.ts",
    "src/intents/design_editor/native_repair.ts",
]
for name in app_files:
    source = APP / name
    if source.is_file():
        dest = HANDOFF / "app-source" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
(HANDOFF / "app-source/README.md").write_text(
    "Snapshot kode app yang relevan, bukan instalasi lengkap. App hidup berada di D:/cusbe-importer.\n"
    "node_modules, environment variables dan kredensial tidak disertakan. "
    "Bundel v4 terakhir disertakan dalam outputs/VECTALLY-native-font-runtime.\n",
    encoding="utf-8",
)
briefs = {
    "INITIAL_REQUEST.txt": Path("C:/Users/HP/.codex/attachments/18f48766-8c71-49bf-b55a-4e267d71de16/Pasted text.txt"),
    "HYBRID_APPROVED.txt": Path("C:/Users/HP/.codex/attachments/a8384cb7-041b-4d34-a6b0-23e80577091f/Pasted text.txt"),
}
missing_briefs = []
for name, source in briefs.items():
    if source.is_file():
        dest = HANDOFF / "briefs" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    else:
        missing_briefs.append(str(source))

latest = sorted((HANDOFF / "runs").glob("*-Audit"))[-1]
source_audit = json.loads((latest / "SOURCE_AUDIT.json").read_text(encoding="utf-8-sig"))
package_audit = json.loads((latest / "PACKAGE_AUDIT.json").read_text(encoding="utf-8-sig"))
verification = {
    "observedUtc": datetime.now(timezone.utc).isoformat(),
    "goalRemainsPaused": True,
    "statusCommand": "PASS",
    "doctorCommand": "PASS: existing Python dependencies and Node found",
    "sourceFilesChecked": len(source_audit),
    "sourceHashFailures": sum(not row["exists"] or not row["hashMatches"] for row in source_audit),
    "candidatePackagesChecked": package_audit["packageCount"],
    "candidatePackagesWithBlockers": package_audit["packagesWithErrors"],
    "expectedAuditExitCode": 2,
    "blockers": [dict(path=p["path"], errors=p["errors"]) for p in package_audit["packages"] if p["errors"]],
    "rebuildExecutedDuringHandoff": False,
    "canvaMutatedDuringHandoff": False,
    "buildComposeRunnerExecutedDuringHandoff": False,
    "missingOriginalBriefs": missing_briefs,
    "finalVisualOrBuyerCertification": False,
}
assert verification["sourceFilesChecked"] == 84
assert verification["sourceHashFailures"] == 0
assert verification["candidatePackagesWithBlockers"] == 1
assert all("S06" in p["path"] for p in verification["blockers"])
(HANDOFF / "VERIFICATION.json").write_text(json.dumps(verification, indent=2, ensure_ascii=False), encoding="utf-8")

files = set()
for path in HANDOFF.rglob("*"):
    if path.is_file() and "__pycache__" not in path.parts and "backup" not in path.parts:
        files.add(path)
work_files = [
    "native_component_builder.py", "native_contour_path.py", "native_clean_quad.py",
    "normalize_native_package.py", "vectally_story_s01_repair.py",
    "vectally_story_s02_repair.py", "vectally_story_s03_s04_repair.py",
    "vectally_story_s05_repair.py", "vectally_story_s06_repair.py",
    "s01_normalize.py", "s01_whole_object_isolation.py",
    "s01_actual_export_audit.py", "s01_repaired_export_audit.py",
    "s01_buyer_vector_test_verify.py", "s02_merge_normal_copy.cjs",
    "s04_merge_normal_copy.cjs", "s06_merge_native_copy.cjs",
    "story_normal_copy_fit.py", "story_normal_copy_fit_s04.py",
    "story_s06_native_copy_fit.py", "story_s03_s04_isolation.py",
    "story_prototype19_export_audit.py", "s06_actual_text_audit.py",
    "s05_actual_assets_audit.py", "s05_purple_gradient_fit.py",
    "league_width_instances.py", "league_width_names.py",
]
work_files += [f"vectally_highlight_h0{index}_repair.py" for index in range(1, 7)]
for name in work_files:
    path = ROOT / "work" / name
    if path.is_file():
        files.add(path)
files.add(ROOT / "outputs/VECTALLY-lengkap/progress.json")
for code in ["S01", "S02", "S03", "S04", "S05", "S06"]:
    folder = ROOT / "outputs/VECTALLY-story-repair" / code
    files.update(folder.glob("*.json"))
    # Explicitly selected actual exports/reviews. Avoid duplicating every historical PNG.
    for name in [
        "CANVA_FLOW_REPAIRED_NORMAL_COPY.png", "CANVA_WHITE_NATIVE.png",
        "CANVA_ASSETS.png", "CANVA_NORMAL_COPY.png", "CANVA_ALL_NATIVE.png",
        "CANVA_ASSETS_BODY.png", "CANVA_NATIVE_GRADIENT.png",
        "CONTACT-SOURCE-CANVA.png", "WHOLE-OBJECT-ISOLATION.png",
    ]:
        if (folder / name).is_file():
            files.add(folder / name)
for name in ["CONTACT-SOURCE-CANVA-S01-S02.png", "CONTACT-SOURCE-CANVA-S03-S04.png",
             "WHOLE-OBJECT-S03-S04.png"]:
    files.add(ROOT / "outputs/VECTALLY-story-repair" / name)
for folder in (ROOT / "outputs/VECTALLY-highlight-repair").iterdir():
    if folder.is_dir():
        files.update(p for p in folder.glob("*.json") if "before-" not in p.name)
for folder in [ROOT / "outputs/VECTALLY-native-font-runtime",
               ROOT / "outputs/VECTALLY-native-spacing"]:
    files.update(folder.glob("*.json"))
for name in ["app-font-audit.js.gz", "app-font-validator-v4.js.gz"]:
    path = ROOT / "outputs/VECTALLY-native-font-runtime" / name
    if path.is_file():
        files.add(path)
for path in (ROOT / "outputs/VECTALLY-teks-native/fonts").iterdir():
    if path.suffix in {".ttf", ".txt"}:
        files.add(path)
for path in (ROOT / "outputs/VECTALLY-hybrid/font-identification").glob("*.ttf"):
    files.add(path)
for folder in ["calibration-02", "calibration-03", "calibration-04", "calibration-05", "native-affine-probe"]:
    files.update((ROOT / "outputs/VECTALLY-hybrid" / folder).glob("*METRICS*.json"))
    files.update((ROOT / "outputs/VECTALLY-hybrid" / folder).glob("*CHECKPOINT*.json"))
for code in ["A07", "A20", "A27", "A45"]:
    files.add(ROOT / "outputs/VECTALLY-4-aset-utuh" / code / "CANVA_PACKAGE.json")

entries = []
for path in sorted(files):
    if not path.is_file():
        continue
    assert path.suffix.lower() != ".env"
    relative = path.relative_to(ROOT).as_posix()
    entries.append(dict(path=relative, size=path.stat().st_size,
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
manifest_path = HANDOFF / "BUNDLE_FILES.json"
manifest_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
archive = ROOT / "outputs/VECTALLY_CLAUDE_HANDOFF_20261110.zip"
if archive.exists():
    archive = archive.with_name("VECTALLY_CLAUDE_HANDOFF_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".zip")
with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as zip_file:
    for entry in entries:
        zip_file.write(ROOT / entry["path"], entry["path"])
    zip_file.write(manifest_path, manifest_path.relative_to(ROOT).as_posix())
with ZipFile(archive) as zip_file:
    assert zip_file.testzip() is None
    assert "handoff/CLAUDE_START.md" in zip_file.namelist()
    for entry in entries:
        assert hashlib.sha256(zip_file.read(entry["path"])).hexdigest() == entry["sha256"]
result = dict(archive=str(archive), files=len(entries) + 1,
              bytes=archive.stat().st_size,
              sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
              zipIntegrity="PASS", allFileHashesVerified=True,
              sourcePNGsIncluded=False, runtimeDependenciesIncluded=False)
(HANDOFF / "ARCHIVE_RESULT.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))

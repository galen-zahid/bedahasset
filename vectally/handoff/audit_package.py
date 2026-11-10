"""Read-only checks on real packages. This never certifies visual/buyer completion."""
from pathlib import Path
import argparse
import json
import math
import re


def audit(path, catalogue):
    errors, warnings = [], []
    counts = dict(shape=0, group=0, text=0, image=0)
    used_fonts = []
    if not path.is_file():
        return dict(path=str(path), errors=["PACKAGE_MISSING"], warnings=[],
                    finalVerified=False, counts=counts)
    try:
        package = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as exc:
        return dict(path=str(path), errors=[f"INVALID_JSON: {exc}"], warnings=[],
                    finalVerified=False, counts=counts)
    if package.get("format") != "cusbe-canva-package":
        errors.append("INVALID_PACKAGE_FORMAT")
    fonts = catalogue.get("fonts", [])

    def visit(element, address, parent_group=False):
        kind = element.get("type")
        if kind not in counts:
            errors.append(f"{address}: UNKNOWN_ELEMENT_TYPE {kind}")
            return
        counts[kind] += 1
        for field in ("left", "top", "width"):
            value = element.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append(f"{address}: INVALID_{field.upper()}")
        if isinstance(element.get("width"), (int, float)) and element["width"] <= 0:
            errors.append(f"{address}: NONPOSITIVE_WIDTH")
        if kind != "text":
            height = element.get("height")
            if not isinstance(height, (int, float)) or not math.isfinite(height) or height <= 0:
                errors.append(f"{address}: INVALID_HEIGHT")
        if kind == "group":
            children = element.get("children", [])
            if parent_group:
                errors.append(f"{address}: NESTED_GROUP_NOT_PORTABLE_IN_CURRENT_WORKFLOW")
            if len(children) < 2:
                errors.append(f"{address}: GROUP_REQUIRES_TWO_REAL_CHILDREN")
            if element.get("rotation", 0):
                warnings.append(f"{address}: GROUP_ROTATION_REQUIRES_TRANSFORM_REVIEW")
            for index, child in enumerate(children):
                visit(child, f"{address}/{index}", True)
        elif kind == "shape":
            if not element.get("paths"):
                errors.append(f"{address}: EMPTY_SHAPE")
            for index, item in enumerate(element.get("paths", [])):
                data = item.get("d", "")
                label = f"{address}/path{index}"
                if len(data.encode("utf-8")) > 1850:
                    errors.append(f"{label}: EXCEEDS_WORKFLOW_PATH_BUDGET_1850_BYTES")
                if len(re.findall("[Mm]", data)) != 1:
                    errors.append(f"{label}: EXPECTED_ONE_MOVE")
                commands = set(re.findall("[A-DF-Za-df-z]", data))
                unsupported = commands - set("MmLlHhVvCcZz")
                if unsupported:
                    errors.append(f"{label}: CONVERT_UNTESTED_COMMANDS_TO_C {sorted(unsupported)}")
                if not re.search("[Zz]$", data.strip()):
                    errors.append(f"{label}: OPEN_FILL_CONTOUR")
                if not re.fullmatch("#[0-9a-fA-F]{6}", item.get("fill", {}).get("color", "")):
                    warnings.append(f"{label}: FILL_REQUIRES_NATIVE_RUNTIME_REVIEW")
        elif kind == "image":
            warnings.append(f"{address}: RASTER_OR_APP_MEDIA_NEEDS_SEMANTIC_AND_BUYER_REVIEW")
        elif kind == "text":
            ref, family = element.get("fontRef"), element.get("fontFamily")
            font = next((f for f in fonts if ref and f["ref"] == ref), None)
            if font is None and family:
                font = next((f for f in fonts if f["name"].casefold() == family.casefold()), None)
            weight, style = element.get("fontWeight", "normal"), element.get("fontStyle", "normal")
            used_fonts.append(dict(address=address, text=element.get("text", ""),
                                   ref=ref, family=family, weight=weight, style=style))
            if font is None:
                warnings.append(f"{address}: FONT_CATALOGUE_UNKNOWN_VERIFY_IN_CANVA")
            elif not any(f["weight"] == weight and style in f["styles"] for f in font["weights"]):
                errors.append(f"{address}: FONT_VARIANT_UNAVAILABLE {font['name']} {weight}/{style}")

    for index, element in enumerate(package.get("elements", [])):
        visit(element, str(index))
    if package.get("summary") != counts:
        warnings.append("SUMMARY_DIFFERS_FROM_ACTUAL_ELEMENTS")
    return dict(path=str(path), source=package.get("source"), counts=counts,
                errors=errors, warnings=warnings, fonts=used_fonts,
                structuralAndKnownFontChecksPassed=not errors,
                sourceFidelity="NOT_CERTIFIED", buyerQA="NOT_CERTIFIED",
                finalVerified=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--catalogue", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--packages", nargs="*")
    args = parser.parse_args()
    root = Path(args.root)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
    catalogue = json.loads(Path(args.catalogue).read_text(encoding="utf-8-sig"))
    paths = [Path(p) for p in args.packages] if args.packages else [
        root / r["outputDir"] / r["candidatePackage"] for r in manifest["recipes"]
    ]
    results = [audit(p if p.is_absolute() else root / p, catalogue) for p in paths]
    report = dict(packages=results, packageCount=len(results),
                  packagesWithErrors=sum(bool(r["errors"]) for r in results),
                  finalVerified=False,
                  notice="PASS struktural bukan bukti 1:1, objek lengkap, atau buyer PASS.")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(dict(packageCount=report["packageCount"],
                          packagesWithErrors=report["packagesWithErrors"],
                          report=str(output), finalVerified=False)))
    return 2 if report["packagesWithErrors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Portable, stdlib-only audit; supports extracted sources or a cloud-input ZIP."""
from pathlib import Path
from zipfile import ZipFile
import argparse
import hashlib
import json
from audit_package import audit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    sources = json.loads((root / "handoff/CLOUD_SOURCES.json").read_text(encoding="utf-8"))["sources"]
    checks = []
    archive = ZipFile(args.archive) if args.archive else None
    try:
        for source in sources:
            try:
                data = archive.read(source["path"]) if archive else (root / source["path"]).read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                checks.append(dict(code=source["code"], exists=True, hashMatches=actual == source["sha256"]))
            except (OSError, KeyError):
                checks.append(dict(code=source["code"], exists=False, hashMatches=False))
    finally:
        if archive:
            archive.close()
    jobs = json.loads((root / "handoff/jobs.json").read_text())
    catalogue = json.loads((root / "handoff/FONT_CATALOGUE.json").read_text())
    packages = [audit(root / job["outputDir"] / job["candidatePackage"], catalogue) for job in jobs["recipes"]]
    report = dict(
        sourceCount=len(checks),
        sourceFailures=sum(not check["hashMatches"] for check in checks),
        sources=checks,
        packages=packages,
        packagesWithBlockers=sum(bool(package["errors"]) for package in packages),
        finalVerified=False,
        notice="Exit2 untuk blocker paket/font adalah hasil audit, bukan sertifikasi final.",
    )
    destination = root / "handoff/CLOUD_AUDIT_RESULT.json"
    destination.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({key:report[key] for key in ["sourceCount","sourceFailures","packagesWithBlockers","finalVerified"]}))
    return 2 if report["sourceFailures"] or report["packagesWithBlockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

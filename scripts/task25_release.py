"""TASK-25: assemble and verify reproducible ZIP from a validated Git commit.

This tool only builds an archive; Moodle submission and co-author review must
be performed by humans.  '--validated-by' values are human attestations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

REQUIRED = ("source_snapshot", "clean_install", "cpp_build", "cpp_tests",
            "python_tests", "real_integration", "image_report",
            "benchmark_evidence", "figures_report")
ATTACHMENTS = ("validation.json", "validation.md", "integration/execution.json",
               "integration/images.json")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def valid_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name and not name.startswith("/") and "\\" not in name
                and all(part not in ("", ".", "..") for part in path.parts))


def verify_release(path: Path) -> dict:
    """All archived files except the manifest are SHA-256 authenticated."""
    with zipfile.ZipFile(path) as archive:
        require_names = {"release_manifest.json"}
        names = archive.namelist()
        if len(names) != len(set(names)) or not all(valid_name(n.rstrip("/")) for n in names):
            raise ValueError("Invalid or duplicate archive paths")
        if not require_names <= set(names):
            raise ValueError("Missing release_manifest.json")
        manifest = json.loads(archive.read("release_manifest.json"))
        if manifest.get("schema_version") != 1 or manifest.get("task") != "TASK-25":
            raise ValueError("Invalid release manifest")
        entries = manifest.get("sha256", {})
        actual = {name for name in names if not name.endswith("/") and name != "release_manifest.json"}
        if actual != set(entries):
            raise ValueError("Release file list differs from manifest")
        for name in sorted(actual):
            if hash_bytes(archive.read(name)) != entries[name]:
                raise ValueError(f"SHA-256 mismatch: {name}")
        return {"status": "PASS", "files": len(entries), "source_sha": manifest["git_sha"],
                "validators": manifest.get("validated_by", []), "draft": manifest.get("draft", False)}


def assemble(source: Path, report_path: Path, output: Path, validators: list[str],
             *, draft: bool = False) -> dict:
    source, report_path, output = source.resolve(), report_path.resolve(), output.resolve()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or any(report.get("checks", {}).get(k, {}).get("status") != "PASS" for k in REQUIRED):
        raise ValueError("A full TASK-25 validation with all checks PASS is required")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if report.get("git_sha") != revision:
        raise ValueError("Validation targets another commit: re-run clean validation")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip():
        raise ValueError("Working tree has uncommitted changes")
    validators = [name.strip() for name in validators if name.strip()]
    if not draft and (len(validators) != 2 or len(set(validators)) != 2):
        raise ValueError("Final release requires two distinct --validated-by declarations")
    if draft and len(validators) > 2:
        raise ValueError("At most two validators may be listed")
    inputs = {name: report_path.parent / name for name in ATTACHMENTS}
    for name, path in inputs.items():
        if not path.is_file():
            raise ValueError(f"Missing validation attachment: {name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite release: {output}")
    with tempfile.TemporaryDirectory(prefix="task25-archive-") as temp:
        destination = Path(temp) / "package.zip"
        with destination.open("wb") as stream:
            subprocess.run(["git", "archive", "--format=zip", "HEAD"], cwd=source,
                           stdout=stream, check=True)
        with zipfile.ZipFile(destination, "a", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as archive:
            existing = set(archive.namelist())
            if any(f"validation/{name}" in existing for name in inputs):
                raise ValueError("Git archive unexpectedly contains validation attachments")
            for name, path in inputs.items():
                archive.write(path, f"validation/{name}")
            names = [n for n in archive.namelist() if not n.endswith("/")]
            hashes = {name: hash_bytes(archive.read(name)) for name in names}
            manifest = {
                "schema_version": 1, "task": "TASK-25",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "git_sha": revision, "draft": draft,
                "validated_by": validators, "moodle_uploaded": False,
                "validation_status": "PASS",
                "sha256": dict(sorted(hashes.items())),
            }
            archive.writestr("release_manifest.json", json.dumps(manifest,
                ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        result = verify_release(destination)
        destination.replace(output)
    checksum = output.with_suffix(output.suffix + ".sha256")
    checksum.write_text(f"{hash_bytes(output.read_bytes())}  {output.name}\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--validation", type=Path,
                        default=Path("results/task25/verification/validation.json"))
    parser.add_argument("--output", type=Path, default=Path("results/task25/final-project.zip"))
    parser.add_argument("--validated-by", action="append", default=[],
                        help="Name of an actual member who has personally verified the release")
    parser.add_argument("--draft", action="store_true", help="Archive before two-person sign-off")
    parser.add_argument("--verify", type=Path, help="Only verify this existing release ZIP")
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify_release(args.verify)
        else:
            result = assemble(args.source, args.validation, args.output,
                              args.validated_by, draft=args.draft)
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile,
            json.JSONDecodeError) as exc:
        parser.exit(1, f"TASK-25 release error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

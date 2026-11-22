"""Publish verified TASK-18 measured evidence from results/ into versioned docs.

Never fabricates measurements: the source must be a completed saturation run
containing the six expected scenarios and their individual raw evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

from monitoring.saturation import ROOT, REPORT_COLUMNS, render_report

EVIDENCE_FILES = (
    "scenario.json", "requests.csv", "summary.json", "samples.csv", "reconstructions.csv"
)


def sha256(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _check_data(source: Path, report: dict) -> list[tuple[str, int, Path]]:
    if report.get("schema_version") != 1:
        raise ValueError("Unsupported TASK-18 report schema")
    cfg = report.get("config")
    if not isinstance(cfg, dict) or not isinstance(report.get("environment"), dict):
        raise ValueError("Missing experiment configuration or measured environment")
    if report.get("errors"):
        raise ValueError("Experiment contains errors; review the run before publishing")
    levels = cfg.get("levels")
    if not isinstance(levels, (list, tuple)) or not levels or any(
        type(n) is not int or n <= 0 for n in levels
    ) or len(levels) != len(set(levels)):
        raise ValueError("Invalid experiment levels")
    results = report.get("results")
    if not isinstance(results, list):
        raise ValueError("Missing experiment results")
    expected = {(impl, level) for impl in ("python", "cpp") for level in levels}
    actual = {(r["implementation"], r["signals_per_client"]) for r in results}
    if len(results) != len(actual) or expected != actual:
        raise ValueError(f"Incomplete or duplicate scenarios. Missing: {sorted(expected - actual)}; "
                         f"unexpected: {sorted(actual - expected)}")
    if cfg.get("model_id") in (None, "") or cfg.get("workers") is None or cfg.get("queue_capacity") is None:
        raise ValueError("Incomplete workload settings")

    evidence_paths = []
    for row in results:
        impl, volume = row["implementation"], row["signals_per_client"]
        attempt = 3 * volume
        if row.get("attempted") != attempt or row.get("clients") != 3:
            raise ValueError(f"Invalid number of attempts for {impl}/{volume}")
        summary = sum(row.get(field, 0) for field in (
            "accepted_http_202", "queue_full_http_503", "unexpected_responses", "transport_errors"
        ))
        if summary != attempt:
            raise ValueError(f"Attempts do not match HTTP/transport outcomes for {impl}/{volume}")
        directory = source / impl / f"signals-{volume}-per-client"
        for name in EVIDENCE_FILES:
            if not (directory / name).is_file():
                raise FileNotFoundError(f"Missing raw evidence: {directory / name}")
        scenario = json.loads((directory / "scenario.json").read_text(encoding="utf-8"))
        for field in ("attempted", "accepted_http_202", "queue_full_http_503",
                      "implementation", "signals_per_client", "queue_peak", "peak_cpu_percent"):
            if scenario.get(field) != row.get(field):
                raise ValueError(f"Mismatch in {directory}/scenario.json: {field}")
        summary_json = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        if summary_json.get("implementation") != impl:
            raise ValueError(f"Mismatched TASK-16 collector implementation at {directory}")
        with (directory / "requests.csv").open(newline="", encoding="utf-8") as f:
            attempts = list(csv.DictReader(f))
        if len(attempts) != attempt:
            raise ValueError(f"Mismatched requests.csv row count at {directory}")
        accepted = sum(r["http_status"] == "202" and bool(r["request_id"]) for r in attempts)
        rejected = sum(r["http_status"] == "503" and r["error_code"] == "QUEUE_FULL" for r in attempts)
        if (accepted, rejected) != (row["accepted_http_202"], row["queue_full_http_503"]):
            raise ValueError(f"Mismatched HTTP responses in requests.csv at {directory}")
        evidence_paths.append((impl, volume, directory))

    for name in ("report.json", "report.csv"):
        if not (source / name).is_file():
            raise FileNotFoundError(f"Missing aggregate evidence: {source / name}")
    with (source / "report.csv").open(newline="", encoding="utf-8") as stream:
        csv_rows = list(csv.DictReader(stream))
    if len(csv_rows) != len(results):
        raise ValueError("report.csv row count differs from report.json")
    json_rows = {(r["implementation"], r["signals_per_client"]): r for r in results}
    for csv_row in csv_rows:
        try:
            key = csv_row["implementation"], int(csv_row["signals_per_client"])
            expected = json_rows[key]
            for field in ("attempted", "accepted_http_202", "queue_full_http_503"):
                if int(csv_row[field]) != expected[field]:
                    raise ValueError(f"Mismatch between report.csv and report.json: {key}/{field}")
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid report.csv field or scenario") from exc
    return evidence_paths


def publish(source: Path, destination: Path, *, expect_model: str | None = None) -> Path:
    """Copy measured evidence; fail rather than silently replacing earlier runs."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    report = json.loads((source / "report.json").read_text(encoding="utf-8"))
    paths = _check_data(source, report)
    if expect_model and report["config"]["model_id"] != expect_model:
        raise ValueError(f"Expected model {expect_model}, got {report['config']['model_id']}")
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"Destination is not empty: {destination}")
    if destination == source or source in destination.parents:
        raise ValueError("Destination must be separate from the source run")

    destination.mkdir(parents=True, exist_ok=True)
    files = {}
    for impl, volume, directory in paths:
        target_dir = destination / "evidence" / impl / f"signals-{volume}-per-client"
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in EVIDENCE_FILES:
            source_file = directory / filename
            target = target_dir / filename
            shutil.copy2(source_file, target)
            files[str(target.relative_to(destination))] = sha256(target)

    shutil.copy2(source / "report.csv", destination / "report.csv")
    files["report.csv"] = sha256(destination / "report.csv")
    # Use the original hardware facts, never the machine publishing the files.
    public_report = deepcopy(report)
    catalog = Path(public_report["config"]["catalog"])
    if catalog.is_absolute():
        try:
            public_report["config"]["catalog"] = str(catalog.relative_to(ROOT.resolve()))
        except ValueError:
            # The absolute path may contain a username; retain model name and
            # schema information without publishing a private local path.
            public_report["config"]["catalog"] = f"[external catalog] {catalog.name}"
    (destination / "report.json").write_text(json.dumps(
        public_report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    files["report.json"] = sha256(destination / "report.json")
    (destination / "report.md").write_text(render_report(public_report), encoding="utf-8")
    files["report.md"] = sha256(destination / "report.md")
    (destination / "manifest.json").write_text(json.dumps({
        "schema_version": 1,
        "source_run_name": source.name,
        "original_report_sha256": sha256(source / "report.json"),
        "files_sha256": files,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination / "report.md"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path,
                        help="Existing results/saturation/run-*/ with real measured data")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "docs" / "tests" / "results" / "task-18")
    parser.add_argument("--expect-model", default=None,
                        help="Refuse publishing a different model (e.g. task18_dense_512)")
    args = parser.parse_args()
    result = publish(args.run_directory, args.output, expect_model=args.expect_model)
    print(f"Published measured TASK-18 report: {result}")


if __name__ == "__main__":
    main()

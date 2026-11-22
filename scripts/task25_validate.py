"""TASK-25: auditable final validation using a clean, committed source snapshot.

No benchmark numbers are regenerated here. Historical TASK-21 evidence is
validated separately from a fresh real-server end-to-end functional test.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LEVELS = (15, 30, 60)
IMPLEMENTATIONS = ("python", "cpp")
CHARTS = (
    "cpu_comparison.png", "memory_comparison.png",
    "total_execution_time.png", "mean_reconstruction_time.png",
    "image_counts.png",
)
RUN_FILES = ("scenario.json", "summary.json", "requests.csv", "samples.csv", "reconstructions.csv")
CHECK_NAMES = ("source_snapshot", "clean_install", "cpp_build", "cpp_tests",
               "python_tests", "real_integration", "image_report", "benchmark_evidence", "figures_report")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def json_file(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"JSON is not an object: {path}")
    return value


def csv_file(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_png(path: Path) -> None:
    """Verify PNG framing and CRC32 of every chunk, not just existence."""
    import zlib
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"), f"Bad PNG header: {path}")
    position, seen_ihdr, seen_iend = 8, False, False
    while position < len(data):
        require(position + 12 <= len(data), f"Truncated PNG chunk: {path}")
        length = int.from_bytes(data[position:position+4], "big")
        kind = data[position+4:position+8]
        end = position + 12 + length
        require(end <= len(data), f"Truncated PNG data: {path}")
        payload = data[position+8:position+8+length]
        crc = int.from_bytes(data[position+8+length:end], "big")
        require(zlib.crc32(kind + payload) & 0xffffffff == crc, f"PNG CRC mismatch: {path}")
        if not seen_ihdr:
            require(kind == b"IHDR" and length == 13, f"Missing PNG IHDR: {path}")
            width, height = struct.unpack(">II", payload[:8])
            require(width > 0 and height > 0, f"Empty PNG: {path}")
            seen_ihdr = True
        if kind == b"IEND":
            require(length == 0 and end == len(data), f"Invalid PNG IEND: {path}")
            seen_iend = True
            break
        position = end
    require(seen_ihdr and seen_iend, f"Incomplete PNG: {path}")


def verify_benchmark(root: Path) -> dict:
    """Check TASK-21 plan hash, every run and raw HTTP/CGNR evidence."""
    folder = root / "docs/tests/task-21-evidence"
    comparison = json_file(folder / "comparison.json")
    plan = json_file(folder / "plan.json")
    config = comparison["config"]
    require(tuple(config["levels"]) == LEVELS, "TASK-21 levels mismatch")
    require(config["repeats"] == 3, "TASK-21 expected three repetitions")
    require(config["model_id"] == plan["model_id"], "TASK-21 model mismatch")
    require(plan["clients"] == 3 and plan["max_signals_per_client"] == 60,
            "TASK-21 plan does not contain 3 x 60 signals")
    expected_digest = hashlib.sha256(json.dumps(
        {k: v for k, v in plan.items() if k != "sha256"},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    require(plan["sha256"] == expected_digest == comparison["plan_sha256"],
            "TASK-21 plan SHA-256 mismatch")
    require(not comparison.get("errors"), "TASK-21 benchmark has errors")
    require(len(comparison["runs"]) == 18, "TASK-21 must have 18 runs")
    require(len(comparison["comparison"]) == 3, "TASK-21 must have 3 compared levels")
    expected_keys = {(impl, level, repeat) for impl in IMPLEMENTATIONS
                     for level in LEVELS for repeat in range(1, 4)}
    observed = {}
    fingerprints = {}
    for run in comparison["runs"]:
        key = (run["implementation"], run["signals_per_client"], run["repeat"])
        require(key in expected_keys and key not in observed, f"Duplicate or unexpected TASK-21 run: {key}")
        level = key[1]
        expected = 3 * level
        for field, target in (("planned", expected), ("accepted", expected),
                              ("finished", expected), ("rejected", 0), ("failed", 0),
                              ("transport_errors", 0), ("unexpected", 0)):
            require(run[field] == target, f"TASK-21 {key}: {field} != {target}")
        require(run["workload_complete"] is True and run["valid"] is True,
                f"TASK-21 incomplete/invalid: {key}")
        require(run["plan_sha256"] == expected_digest, f"TASK-21 run plan mismatch: {key}")
        directory = folder / "runs" / key[0] / f"level-{level}" / f"repeat-{key[2]}"
        for name in RUN_FILES:
            require((directory / name).is_file(), f"Missing TASK-21 evidence: {directory / name}")
            fingerprints[str((directory / name).relative_to(root))] = sha256(directory / name)
        scenario = json_file(directory / "scenario.json")
        summary = json_file(directory / "summary.json")
        for field in ("planned", "accepted", "finished", "valid", "workload_complete",
                      "plan_sha256", "implementation", "signals_per_client", "repeat"):
            require(scenario[field] == run[field], f"TASK-21 {key}: scenario {field} mismatch")
        require(summary["workload_complete"] is True
                and summary["completed_count"] == expected and summary["failed_count"] == 0,
                f"TASK-21 {key}: collector incomplete")
        requests = csv_file(directory / "requests.csv")
        jobs = csv_file(directory / "reconstructions.csv")
        samples = csv_file(directory / "samples.csv")
        require(len(requests) == len(jobs) == expected and len(samples) >= 2,
                f"TASK-21 {key}: invalid CSV lengths")
        require(all(str(r["http_status"]) == "202" for r in requests),
                f"TASK-21 {key}: non-202 requests")
        require(all(row["status"] == "completed" for row in jobs),
                f"TASK-21 {key}: unfinished job")
        request_ids = {row["request_id"] for row in requests}
        job_ids = {row["request_id"] for row in jobs}
        require(len(request_ids) == expected and request_ids == job_ids and "" not in request_ids,
                f"TASK-21 {key}: job identifiers inconsistent")
        counts = Counter(row["client_id"] for row in requests)
        require(counts == {f"task21-client-{i}": level for i in range(1, 4)},
                f"TASK-21 {key}: not three clients with equal signal counts")
        observed[key] = run
    require(set(observed) == expected_keys, "TASK-21 missing run combinations")
    for row in comparison["comparison"]:
        level = row["signals_per_client"]
        require(level in LEVELS and row["total_signals"] == 3 * level
                and row["paired_valid"] == 3 and row["comparable"] is True,
                f"TASK-21 level {level} not comparable")
    require({row["signals_per_client"] for row in comparison["comparison"]} == set(LEVELS),
            "TASK-21 duplicate compared levels")
    for name in ("comparison.json", "comparison.csv", "comparison.md", "plan.json", "runs.csv"):
        require((folder / name).is_file(), f"Missing TASK-21 artifact: {name}")
        fingerprints[str((folder / name).relative_to(root))] = sha256(folder / name)
    require(len(csv_file(folder / "runs.csv")) == 18, "TASK-21 runs.csv must have 18 rows")
    require(len(csv_file(folder / "comparison.csv")) == 3, "TASK-21 comparison.csv must have 3 rows")
    return {"status": "PASS", "runs": 18, "paired_levels": list(LEVELS),
            "plan_sha256": expected_digest, "files": fingerprints}


def verify_figures(root: Path) -> dict:
    """Validate existing TASK-23 technical report and published TASK-22 plots."""
    base = root / "docs/reports/task-23"
    report = base / "relatorio-tecnico-comparativo.md"
    require(report.is_file(), "TASK-23 report missing")
    content = report.read_text(encoding="utf-8")
    require("CGNR" in content and "TASK-21" in content, "TASK-23 report missing key sections")
    fingerprints = {str(report.relative_to(root)): sha256(report)}
    for level in LEVELS:
        directory = base / "figures" / f"level-{level}"
        manifest = json_file(directory / "plots_manifest.json")
        require(manifest["schema_version"] == 1, f"Invalid plots manifest for level {level}")
        sources = manifest["sources"]
        require(len(sources) == 6 and all(f"level-{level}" in s for s in sources),
                f"Incorrect TASK-22 plot sources at level {level}")
        versions = {row["implementation"]: row for row in manifest["versions"]}
        require(set(versions) == set(IMPLEMENTATIONS), f"Missing plot implementation at {level}")
        for impl in IMPLEMENTATIONS:
            row = versions[impl]
            require(row["runs"] == 3 and row["completed_count"] == 9 * level
                    and row["failed_count"] == 0 and row["workload_complete"] is True,
                    f"TASK-22 figure data incomplete: {impl}, level={level}")
        require(set(manifest["charts"].values()) == set(CHARTS),
                f"TASK-22 missing chart names at level {level}")
        fingerprints[str((directory / "plots_manifest.json").relative_to(root))] = sha256(directory / "plots_manifest.json")
        for filename in CHARTS:
            path = directory / filename
            verify_png(path)
            fingerprints[str(path.relative_to(root))] = sha256(path)
    # Markdown image links must resolve from the report's own directory.
    import re
    for destination in re.findall(r"!\[[^]]*\]\(([^)]+)\)", content):
        require((report.parent / destination).is_file(), f"Broken TASK-23 figure link: {destination}")
    # Verify that saturation evidence is published and valid (without conflating it with benchmark).
    baseline = json_file(root / "docs/tests/results/task-18/report.json")
    require(len(baseline["results"]) == 6 and not baseline.get("errors"),
            "TASK-18 baseline incomplete")
    admission = json_file(root / "docs/tests/results/task-19/comparison.json")
    require(len(admission["comparisons"]) == 12 and not admission.get("errors")
            and admission.get("validation_status") == "passed",
            "TASK-19 report missing or incomplete")
    for row in admission["comparisons"]:
        require(all(row[k] is True for k in ("before_stable", "after_stable", "before_complete", "after_complete")),
                "TASK-19 includes unstable/incomplete result")
    for path in (root / "docs/tests/results/task-18/report.json",
                 root / "docs/tests/results/task-19/comparison.json"):
        fingerprints[str(path.relative_to(root))] = sha256(path)
    return {"status": "PASS", "figures": len(LEVELS) * len(CHARTS),
            "report": str(report.relative_to(root)), "files": fingerprints}


def verify_image_report(execution_path: Path, image_path: Path) -> dict:
    execution, images = json_file(execution_path), json_file(image_path)
    require(execution["schema_version"] == images["schema_version"] == 1,
            "Bad integration report schema")
    require(execution["status"] == images["experiment_status"] == "completed",
            "Incomplete integration experiment")
    require(execution["client_count"] == 3 and execution["total_signals"] == 45
            and execution["total_http_submissions"] == 90,
            "Expected 3 clients, 15 signals each, both servers")
    require(len(execution["clients"]) == 3, "Expected exactly three clients")
    pairs = set()
    for client_id, client in execution["clients"].items():
        require(client["client_id"] == client_id and client["status"] == "completed"
                and client["signal_count"] == 15 and len(client["submissions"]) == 15,
                f"Invalid client {client_id}")
        for record in client["submissions"]:
            pair = (client_id, record["signal_id"])
            require(pair not in pairs, f"Duplicate client signal: {pair}")
            pairs.add(pair)
    require(len(pairs) == 45, "Expected 45 distinct signals")
    require(images["image_count"] == images["total_records"] == 90
            and images["failed_count"] == images["pending_count"] == 0,
            "Expected 90 complete reconstructed images")
    records = images["reconstructions"]
    require(len(records) == 90, "Missing reconstructed records")
    seen = set()
    vectors = {}
    counts = Counter()
    for record in records:
        impl = record["implementation"]
        pair = (record["client_id"], record["signal_id"])
        key = (impl, pair)
        require(impl in IMPLEMENTATIONS and pair in pairs and key not in seen,
                f"Unexpected/duplicate reconstruction {key}")
        require(record["status"] == "completed" and record["model_id"] == "demo_identity_3",
                f"Failed reconstruction {key}")
        require(record["metadata"]["client_id"] == pair[0]
                and record["metadata"]["signal_id"] == pair[1],
                f"Inconsistent reconstruction metadata {key}")
        vector = record["image"]["vector"]
        require(record["image"]["shape"] == [1, 3] and len(vector) == 3,
                f"Invalid reconstructed shape: {key}")
        import math
        require(all(type(x) in (float, int) and math.isfinite(x) for x in vector),
                f"Nonfinite reconstructed value: {key}")
        seen.add(key)
        counts[impl] += 1
        vectors[key] = vector
    require(counts == {"python": 45, "cpp": 45}, "Each server must reconstruct 45 images")
    for pair in pairs:
        require(("python", pair) in vectors and ("cpp", pair) in vectors,
                f"Missing paired reconstruction: {pair}")
        for left, right in zip(vectors[("python", pair)], vectors[("cpp", pair)]):
            require(abs(left - right) <= 1e-5 + 1e-5 * abs(right),
                    f"Python/C++ numeric discrepancy: {pair}")
    return {"status": "PASS", "clients": 3, "signals_per_client": 15,
            "images_python": 45, "images_cpp": 45, "image_count": 90,
            "files": {"execution.json": sha256(execution_path), "images.json": sha256(image_path)}}


def execute_step(name: str, command: list[str], cwd: Path, logs: Path,
                 env: dict[str, str], timeout: int) -> dict:
    logs.mkdir(parents=True, exist_ok=True)
    logfile = logs / f"{name}.log"
    started = time.monotonic()
    with logfile.open("w", encoding="utf-8") as stream:
        try:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout, check=False)
            code = result.returncode
            reason = None
        except (OSError, subprocess.TimeoutExpired) as exc:
            code = None
            reason = f"{type(exc).__name__}: {exc}"
    return {"status": "PASS" if code == 0 else "FAIL", "exit_code": code,
            "command": command, "duration_seconds": round(time.monotonic()-started, 3),
            "log": str(logfile), "error": reason}


def check_files(root: Path) -> dict:
    checks = ("CMakeLists.txt", "pyproject.toml", "uv.lock", ".python-version", "README.md",
              "models/catalog.json", "server/python/reconstruction_server.py",
              "server/cpp/reconstruction_server.cpp", "tests/integration/test_task20_full_flow.py")
    for entry in checks:
        require((root / entry).is_file(), f"Missing required project file: {entry}")
    return {"status": "PASS", "files": {entry: sha256(root / entry) for entry in checks}}


def save_report(report: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "validation.json").write_text(json.dumps(report, indent=2,
        ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# TASK-25 — Validação final", "",
             f"- Gerado: `{report['generated_at_utc']}`",
             f"- Commit: `{report.get('git_sha', 'N/D')}`",
             f"- Estado automatizado: **{report['status']}**", "",
             "| Verificação | Estado | Observação |", "| --- | --- | --- |"]
    for name in CHECK_NAMES:
        result = report["checks"].get(name, {"status": "NOT_RUN"})
        details = result.get("error") or result.get("message") or ""
        lines.append(f"| `{name}` | {result['status']} | {str(details).replace('|', '/')} |")
    lines.extend(["", "## Etapas manuais pendentes", "",
                  "- [ ] Segundo integrante executou a validação e confirmou o funcionamento.",
                  "- [ ] Ambos os integrantes conferiram o pacote final e a versão entregue.",
                  "- [ ] Arquivo final enviado ao Moodle e recibo de entrega preservado.", "",
                  "Os itens manuais **não** são considerados concluídos automaticamente.", ""])
    (directory / "validation.md").write_text("\n".join(lines), encoding="utf-8")


def validate(source: Path, output: Path, *, evidence_only: bool = False,
             skip_full_suite: bool = False) -> dict:
    source, output = source.resolve(), output.resolve()
    require(not (source / ".git").is_file(), "Source must be a normal Git checkout")
    output.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict] = {}
    report = {"schema_version": 1, "task": "TASK-25", "generated_at_utc": now(),
              "source": str(source), "environment": platform.platform(),
              "git_sha": None, "status": "FAIL", "checks": checks,
              "manual": {"second_member_validated": False, "moodle_uploaded": False}}
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
        report["git_sha"] = head
        changes = subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip()
        require(not changes or evidence_only, "Commit modifications first: git status --porcelain is not empty")
        if evidence_only:
            checks["source_snapshot"] = check_files(source)
            root = source
            for key, func in (("benchmark_evidence", verify_benchmark), ("figures_report", verify_figures)):
                try:
                    checks[key] = func(root)
                except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    checks[key] = {"status": "FAIL", "error": str(exc)}
            report["status"] = "PARTIAL" if all(x["status"] == "PASS" for x in checks.values()) else "FAIL"
            return report

        with tempfile.TemporaryDirectory(prefix="task25-clean-") as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            archive_path = Path(temporary) / "source.zip"
            with archive_path.open("wb") as output_stream:
                process = subprocess.run(["git", "archive", "--format=zip", "HEAD"],
                                         cwd=source, stdout=output_stream, check=False)
            require(process.returncode == 0, "git archive failed")
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(root)
            checks["source_snapshot"] = check_files(root)
            env = os.environ.copy()
            env.update(OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MPLBACKEND="Agg")
            logs = output / "logs"
            steps = [
                ("clean_install", ["uv", "sync", "--locked"], 600),
                ("cpp_build", ["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_TESTING=ON"], 600),
            ]
            for key, cmd, timeout in steps:
                checks[key] = execute_step(key, cmd, root, logs, env, timeout)
                if checks[key]["status"] != "PASS":
                    return report
            build = execute_step("cpp_build_compile", ["cmake", "--build", "build", "-j", "4"], root, logs, env, 1200)
            checks["cpp_build"]["compile"] = build
            if build["status"] != "PASS":
                checks["cpp_build"]["status"] = "FAIL"
                return report
            checks["cpp_tests"] = execute_step("cpp_tests", ["ctest", "--test-dir", "build", "--output-on-failure"], root, logs, env, 600)
            if checks["cpp_tests"]["status"] != "PASS":
                return report
            if not skip_full_suite:
                checks["python_tests"] = execute_step("python_tests", ["uv", "run", "--locked", "python", "-m", "pytest", "tests/", "-q", "--tb=short"], root, logs, env, 1800)
                if checks["python_tests"]["status"] != "PASS":
                    return report
            else:
                checks["python_tests"] = {"status": "SKIPPED", "message": "Explicit --skip-full-suite"}
            basetemp = root / "task25-pytest"
            checks["real_integration"] = execute_step(
                "real_integration", ["uv", "run", "--locked", "python", "-m", "pytest",
                "tests/integration/test_task20_full_flow.py", "-v", "--tb=short",
                "--basetemp", str(basetemp)], root, logs, env, 300)
            if checks["real_integration"]["status"] != "PASS":
                return report
            artifacts = list(basetemp.rglob("images.json"))
            require(len(artifacts) == 1, "Expected one persisted TASK-20 images.json")
            imgs = artifacts[0]
            execution = imgs.with_name("execution.json")
            require(execution.is_file(), "TASK-20 execution.json not persisted")
            saved = output / "integration"
            saved.mkdir(exist_ok=True)
            shutil.copy2(imgs, saved / "images.json")
            shutil.copy2(execution, saved / "execution.json")
            try:
                checks["image_report"] = verify_image_report(saved / "execution.json", saved / "images.json")
            except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                checks["image_report"] = {"status": "FAIL", "error": str(exc)}
                return report
            for key, func in (("benchmark_evidence", verify_benchmark), ("figures_report", verify_figures)):
                try:
                    checks[key] = func(root)
                except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    checks[key] = {"status": "FAIL", "error": str(exc)}
            required = (key for key in CHECK_NAMES if not (skip_full_suite and key == "python_tests"))
            passed = all(checks.get(key, {}).get("status") == "PASS" for key in required)
            report["status"] = ("PARTIAL" if skip_full_suite else "PASS") if passed else "FAIL"
            return report
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError, zipfile.BadZipFile) as exc:
        checks.setdefault("source_snapshot", {"status": "FAIL", "error": str(exc)})
        report["error"] = str(exc)
        return report
    finally:
        save_report(report, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("results/task25/verification"))
    parser.add_argument("--only-evidence", action="store_true")
    parser.add_argument("--skip-full-suite", action="store_true", help="Not acceptable for FINAL sign-off")
    args = parser.parse_args()
    report = validate(args.source, args.output, evidence_only=args.only_evidence,
                      skip_full_suite=args.skip_full_suite)
    print(f"TASK-25: {report['status']}; report: {args.output / 'validation.md'}")
    for check, item in report["checks"].items():
        print(f"  {check}: {item['status']}")
    return 0 if report["status"] in ("PASS", "PARTIAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())

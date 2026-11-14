"""TASK-22: testes do gerador de gráficos comparativos."""

import csv
import json

import pytest

from monitoring.plots import (
    CHARTS,
    generate_plots,
    load_experiments,
    load_samples,
)


def write_run(directory, implementation, *, completed=2,
              complete=True, missing_duration=False):
    directory.mkdir()

    summary = {
        "schema_version": 1,
        "implementation": implementation,
        "received_count": completed,
        "completed_count": completed,
        "failed_count": 0,
        "workload_complete": complete,
        "inflight_at_start": 0,
        "unfinished_count_at_end": 0,
    }

    (directory / "summary.json").write_text(
        json.dumps(summary),
        encoding="utf-8",
    )

    with (directory / "samples.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "elapsed_ms",
                "cpu_percent",
                "memory_rss_bytes",
                "queue_size",
            ],
        )
        writer.writeheader()
        writer.writerows([
            {
                "elapsed_ms": 0,
                "cpu_percent": "",
                "memory_rss_bytes": 1048576,
                "queue_size": 0,
            },
            {
                "elapsed_ms": 100,
                "cpu_percent": 50,
                "memory_rss_bytes": 2097152,
                "queue_size": 2,
            },
            {
                "elapsed_ms": 400,
                "cpu_percent": 75,
                "memory_rss_bytes": 3145728,
                "queue_size": 0,
            },
        ])

    with (directory / "reconstructions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "request_id",
                "status",
                "created_at",
                "finished_at",
                "execution_time_ms",
            ],
        )
        writer.writeheader()

        for index in range(completed):
            writer.writerow({
                "request_id": f"{implementation}-{index}",
                "status": "completed",
                "created_at": "2026-01-01T00:00:00Z",
                "finished_at": "2026-01-01T00:00:02Z",
                "execution_time_ms": (
                    "" if missing_duration and index == 0
                    else 10 + index * 20
                ),
            })

    return directory


def test_generates_five_pngs_and_manifest(tmp_path):
    python_run = write_run(tmp_path / "python", "python")
    cpp_run = write_run(tmp_path / "cpp", "cpp")

    output = tmp_path / "plots"
    manifest = generate_plots([python_run, cpp_run], output)

    assert manifest["schema_version"] == 1
    assert manifest["task"] == "TASK-22"
    assert len(manifest["sources"]) == 2
    assert len(manifest["charts"]) == 5

    for filename in CHARTS.values():
        path = output / filename
        assert path.is_file()
        assert path.stat().st_size > 1000
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    stored = json.loads(
        (output / "plots_manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert stored == manifest
    assert [
        row["implementation"]
        for row in stored["versions"]
    ] == ["cpp", "python"]

    assert all(
        row["completed_count"] == 2
        for row in stored["versions"]
    )
    assert all(
        row["mean_reconstruction_time_ms"] == 20
        for row in stored["versions"]
    )
    assert all(
        row["total_execution_time_ms"] == 2000
        for row in stored["versions"]
    )


def test_missing_duration_keeps_null_statistic(tmp_path):
    python_run = write_run(
        tmp_path / "python",
        "python",
        missing_duration=True,
    )
    cpp_run = write_run(tmp_path / "cpp", "cpp")

    manifest = generate_plots(
        [python_run, cpp_run],
        tmp_path / "plots",
    )

    python_row = next(
        row for row in manifest["versions"]
        if row["implementation"] == "python"
    )

    assert python_row["workload_complete"] is False
    assert python_row["mean_reconstruction_time_ms"] is None
    assert python_row["total_execution_time_ms"] is None
    assert python_row["completed_count"] == 2


def test_requires_both_implementations(tmp_path):
    python_run = write_run(tmp_path / "python", "python")

    with pytest.raises(ValueError, match="Python e C"):
        load_experiments([python_run])


def test_rejects_duplicate_run_directories(tmp_path):
    python_run = write_run(tmp_path / "python", "python")
    cpp_run = write_run(tmp_path / "cpp", "cpp")

    with pytest.raises(ValueError, match="distintos"):
        load_experiments([python_run, cpp_run, python_run])


@pytest.mark.parametrize("field,value", [
    ("cpu_percent", "-2"),
    ("cpu_percent", "nan"),
    ("memory_rss_bytes", "-1"),
    ("memory_rss_bytes", "1.5"),
    ("elapsed_ms", "-10"),
])
def test_rejects_invalid_samples(tmp_path, field, value):
    directory = write_run(tmp_path / "python", "python")
    path = directory / "samples.csv"

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    rows[1][field] = value

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError):
        load_samples(directory)


def test_multiple_runs_per_implementation(tmp_path):
    python_a = write_run(tmp_path / "python-a", "python")
    python_b = write_run(tmp_path / "python-b", "python")
    cpp_run = write_run(tmp_path / "cpp", "cpp")

    manifest = generate_plots(
        [python_a, python_b, cpp_run],
        tmp_path / "plots",
    )

    versions = {
        row["implementation"]: row
        for row in manifest["versions"]
    }

    assert versions["python"]["runs"] == 2
    assert versions["python"]["completed_count"] == 4
    assert versions["python"]["mean_reconstruction_time_ms"] == 20
    assert versions["python"]["total_execution_time_ms"] == 4000

    assert versions["cpp"]["runs"] == 1
    assert versions["cpp"]["completed_count"] == 2

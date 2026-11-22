"""TASK-19: comparison never conflates acceptance with execution throughput."""

import csv
import json

import pytest

from monitoring.task19_compare import compare_rows, write_comparison


def sample(**changes):
    row = {
        "implementation": "python", "signals_per_client": 15,
        "clients": 3, "attempted": 45,
        "accepted_http_202": 6, "queue_full_http_503": 39,
        "unexpected_responses": 0, "transport_errors": 0,
        "workers": 1, "queue_capacity": 2, "admission_limit": 3,
        "queue_peak": 2, "peak_cpu_percent": 210.0,
        "peak_memory_rss_bytes": 65000000, "stable": True,
        "workload_complete": True, "throughput_images_per_second": 20.0,
    }
    row.update(changes)
    return row


def test_paired_comparison_and_evidence_files(tmp_path):
    before = sample()
    after = sample(accepted_http_202=35, queue_full_http_503=10,
                   workers=2, queue_capacity=8, admission_limit=6,
                   queue_peak=4, throughput_images_per_second=25.0)
    row = compare_rows(before, after, repeat=1)
    assert row["accepted_delta"] == 29
    assert row["rejected_delta"] == -29
    assert row["rejection_change_pp"] == pytest.approx(-64.444, abs=0.001)
    assert row["after_admission_limit"] == 6
    write_comparison([row], tmp_path, [], model_id="task18_dense_512")
    assert json.loads((tmp_path / "comparison.json").read_text())["comparisons"] == [row]
    with (tmp_path / "comparison.csv").open() as stream:
        assert len(list(csv.DictReader(stream))) == 1
    md = (tmp_path / "comparison.md").read_text()
    assert "202" in md and "503" in md and "não" in md


def test_incomplete_window_does_not_claim_throughput():
    before = sample(workload_complete=False)
    after = sample(accepted_http_202=40, queue_full_http_503=5,
                   workload_complete=False)
    row = compare_rows(before, after, repeat=1)
    assert row["before_throughput"] is None
    assert row["after_throughput"] is None


@pytest.mark.parametrize("overrides", [
    {"implementation": "cpp"}, {"signals_per_client": 30},
    {"attempted": 90}, {"clients": 2},
    {"accepted_http_202": 100}, {"queue_full_http_503": True},
])
def test_mismatched_or_invalid_runs_are_rejected(overrides):
    with pytest.raises(ValueError):
        compare_rows(sample(), sample(**overrides), repeat=1)

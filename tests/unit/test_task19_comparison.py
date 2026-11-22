"""TASK-19: comparison never conflates acceptance with execution throughput."""

import csv
import json

import pytest

from monitoring.task19_compare import compare_rows, write_comparison, campaign_errors


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


def test_complete_campaign_validation_and_report_status(tmp_path):
    row = compare_rows(sample(), sample(), repeat=1)
    failures = campaign_errors([row], [])
    assert failures == []
    write_comparison([row], tmp_path, failures, model_id="task18_dense_512")
    result = json.loads((tmp_path / "comparison.json").read_text())
    assert result["validation_status"] == "passed"
    assert "APROVADA" in (tmp_path / "comparison.md").read_text()


def test_stable_but_incomplete_campaign_fails_and_remains_diagnosable(tmp_path):
    before = sample(workload_complete=False, stable=True)
    after = sample(accepted_http_202=40, queue_full_http_503=5, stable=True)
    row = compare_rows(before, after, repeat=2)
    failures = campaign_errors([row], [])
    assert failures == ["Incomplete workload: python 15/client repeat 2 before"]
    assert row["before_throughput"] is None
    write_comparison([row], tmp_path, failures, model_id="task18_dense_512")
    result = json.loads((tmp_path / "comparison.json").read_text())
    assert result["validation_status"] == "failed"
    assert "FALHOU" in (tmp_path / "comparison.md").read_text()
    assert result["comparisons"] == [row]


def test_mixed_campaign_fails_for_all_unstable_and_incomplete_pairs():
    a = compare_rows(sample(), sample(stable=False, workload_complete=False), repeat=1)
    b = compare_rows(sample(workload_complete=False), sample(), repeat=2)
    errors = campaign_errors([a, b], ["Missing pair: cpp 15 repeat 1"])
    assert len(errors) == 4
    assert any("after" in message and "Unstable" in message for message in errors)
    assert any("after" in message and "Incomplete" in message for message in errors)
    assert any("before" in message and "Incomplete" in message for message in errors)
    assert errors[0].startswith("Missing pair")


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


@pytest.mark.parametrize("complete,expected_code", [(True, 0), (False, 1)])
def test_cli_exit_code_requires_complete_campaign(monkeypatch, tmp_path, complete, expected_code):
    """Regression: stable=True cannot hide an incomplete TASK-16 collection."""
    import sys
    from contextlib import contextmanager
    import monitoring.task19_compare as module

    class DummySettings:
        def __init__(self, **values):
            self.__dict__.update(values)

    def dummy_replace(value, **changes):
        return DummySettings(**{**vars(value), **changes})

    @contextmanager
    def fake_server(implementation, settings, directory, **kwargs):
        yield "http://example.invalid", 1234, object()

    def fake_scenario(implementation, url, pid, level, settings, directory, **kwargs):
        return sample(implementation=implementation, signals_per_client=level,
                      workload_complete=complete, stable=True,
                      workers=settings.workers, queue_capacity=settings.queue_capacity,
                      accepted_http_202=6, queue_full_http_503=39)

    monkeypatch.setattr(module, "Settings", DummySettings)
    monkeypatch.setattr(module, "replace", dummy_replace)
    monkeypatch.setattr(module, "_parse_signal", lambda path: (1.0, 2.0, 3.0))
    monkeypatch.setattr(module, "launch_server", fake_server)
    monkeypatch.setattr(module, "run_scenario", fake_scenario)
    monkeypatch.setattr(sys, "argv", [
        "task19_compare", "--implementations", "python", "--levels", "15",
        "--catalog", str(tmp_path / "catalog.json"),
        "--signal-file", str(tmp_path / "signal.json"),
        "--output", str(tmp_path / "campaign"),
    ])
    assert module.main() == expected_code
    result = json.loads((tmp_path / "campaign" / "comparison.json").read_text())
    assert result["validation_status"] == ("passed" if complete else "failed")
    assert (not result["errors"]) is complete

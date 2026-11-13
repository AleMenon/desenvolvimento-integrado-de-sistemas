"""TASK-16 - Python server metrics registry contract tests."""

import pytest

from server.python.performance_metrics import PerformanceMetrics


def test_lifecycle_counts_and_individual_times():
    registry = PerformanceMetrics()
    registry.accepted("req-1", "cliente-1", "sinal-1", "model-01")
    registry.accepted("req-2", "cliente-2", "sinal-2", "model-01")
    initial = registry.snapshot()
    assert initial["schema_version"] == 1
    assert initial["implementation"] == "python"
    assert initial["received_count"] == 2
    assert initial["queue_size"] == 2
    assert initial["running_count"] == 0

    registry.started("req-1")
    assert registry.snapshot()["queue_size"] == 1
    assert registry.snapshot()["running_count"] == 1
    registry.finished("req-1", success=True, iterations=2, converged=True,
                      stop_reason="tolerance_reached", execution_time_ms=12.5)
    registry.started("req-2")
    registry.finished("req-2", success=False, stop_reason="reconstruction_failed",
                      execution_time_ms=8.0)
    summary = registry.snapshot()
    assert summary["queue_size"] == 0
    assert summary["running_count"] == 0
    assert summary["completed_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["mean_reconstruction_time_ms"] == 12.5
    assert 0 <= summary["queue_mean"] <= 2
    assert summary["queue_mode"] in {0, 1, 2}

    jobs = {job["request_id"]: job for job in registry.reconstructions()["reconstructions"]}
    assert jobs["req-1"]["status"] == "completed"
    assert jobs["req-1"]["iterations"] == 2
    assert jobs["req-1"]["execution_time_ms"] == 12.5
    assert jobs["req-1"]["finished_at"].endswith("Z")
    assert jobs["req-2"]["status"] == "failed"


def test_invalid_transitions_are_rejected():
    registry = PerformanceMetrics()
    registry.accepted("a", "c", "s", "m")
    with pytest.raises(ValueError, match="unique"):
        registry.accepted("a", "c", "s", "m")
    with pytest.raises(ValueError, match="Only running"):
        registry.finished("a", success=True)
    registry.started("a")
    with pytest.raises(ValueError, match="Only queued"):
        registry.started("a")
    registry.finished("a", success=True)
    with pytest.raises(ValueError, match="Only running"):
        registry.finished("a", success=False)


def test_same_schema_for_both_server_types():
    a = PerformanceMetrics("python")
    b = PerformanceMetrics("cpp")
    assert set(a.snapshot()) == set(b.snapshot())
    assert set(a.reconstructions()) == set(b.reconstructions())
    assert a.reconstructions()["reconstructions"] == b.reconstructions()["reconstructions"]

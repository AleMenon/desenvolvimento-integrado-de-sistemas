"""TASK-15: bounded FIFO accounting independent of HTTP and CGNR timing."""

import time

import pytest

from server.python.queue_control import QueueControl


def test_queue_stats_and_terminal_retention():
    ctl = QueueControl(queue_capacity=2, worker_count=2, max_retained_results=2)
    jobs = {f"req-{i}": {"status": "completed"} for i in range(3)}
    for pending in (1, 2, 1):
        ctl.accepted(pending)
    ctl.rejected()
    ctl.started()
    ctl.started()
    ctl.finished("req-0", success=True, jobs=jobs)
    ctl.finished("req-1", success=False, jobs=jobs)
    ctl.started()
    ctl.finished("req-2", success=True, jobs=jobs)

    snapshot = ctl.snapshot(0, jobs)
    assert snapshot["queue_policy"] == "fifo"
    assert snapshot["queue_size"] == 0
    assert snapshot["queue_peak"] == 2
    assert snapshot["worker_count"] == 2
    assert snapshot["running_count"] == 0
    assert snapshot["accepted_count"] == 3
    assert snapshot["completed_count"] == 2
    assert snapshot["failed_count"] == 1
    assert snapshot["rejected_count"] == 1
    assert snapshot["retained_results"] == 2
    assert snapshot["evicted_count"] == 1
    assert "req-0" not in jobs
    assert "req-1" in jobs and "req-2" in jobs


def test_ttl_evicts_only_finished_jobs():
    ctl = QueueControl(max_retained_results=10, result_ttl_seconds=0.02)
    jobs = {"finished": {"status": "completed"}, "queued": {"status": "queued"}}
    ctl.started()
    ctl.finished("finished", success=True, jobs=jobs)
    time.sleep(0.04)
    snapshot = ctl.snapshot(1, jobs)
    assert "finished" not in jobs
    assert "queued" in jobs
    assert snapshot["completed_count"] == 1
    assert snapshot["evicted_count"] == 1


@pytest.mark.parametrize("kwargs", [
    {"queue_capacity": 0}, {"queue_capacity": True},
    {"worker_count": 0}, {"worker_count": 33},
    {"max_retained_results": -1},
    {"result_ttl_seconds": 0}, {"result_ttl_seconds": float("nan")},
])
def test_reject_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        QueueControl(**kwargs)

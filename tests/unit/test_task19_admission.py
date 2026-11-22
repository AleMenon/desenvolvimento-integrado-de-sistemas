"""TASK-19: atomic in-flight admissions and preserved lifetime counters."""

import pytest

from server.python.queue_control import QueueControl


def test_inflight_limit_is_independent_of_queue_capacity():
    ctl = QueueControl(queue_capacity=8, worker_count=2, max_inflight=3)
    jobs = {f"r-{i}": {"status": "completed"} for i in range(3)}
    assert ctl.can_admit()
    ctl.accepted(1)
    ctl.started()
    ctl.accepted(1)
    ctl.started()
    ctl.accepted(1)
    assert not ctl.can_admit()
    ctl.rejected(admission=True)
    snapshot = ctl.snapshot(1, jobs)
    assert snapshot["admission_limit"] == 3
    assert snapshot["inflight_count"] == 3
    assert snapshot["running_count"] == 2
    assert snapshot["rejected_count"] == 1
    assert snapshot["admission_rejected_count"] == 1
    assert snapshot["accepted_count"] == 3
    ctl.finished("r-0", success=True, jobs=jobs)
    assert ctl.can_admit()
    assert ctl.snapshot(1, jobs)["inflight_count"] == 2
    ctl.finished("r-1", success=False, jobs=jobs)
    ctl.started()
    ctl.finished("r-2", success=True, jobs=jobs)
    final = ctl.snapshot(0, jobs)
    assert final["inflight_count"] == 0
    assert final["completed_count"] == 2
    assert final["failed_count"] == 1
    assert final["accepted_count"] == 3


def test_default_limit_preserves_task15_behavior():
    ctl = QueueControl(queue_capacity=2, worker_count=3)
    assert ctl.max_inflight == 5
    assert ctl.snapshot(0, {})["admission_limit"] == 5


@pytest.mark.parametrize("max_inflight", [0, -1, 11, True, 1.5, "2"])
def test_invalid_admission_limit(max_inflight):
    with pytest.raises(ValueError):
        QueueControl(queue_capacity=8, worker_count=2, max_inflight=max_inflight)


def test_counters_stay_monotonic_during_retention():
    ctl = QueueControl(queue_capacity=4, worker_count=1, max_inflight=2,
                       max_retained_results=1)
    jobs = {"r-1": {"status": "completed"}, "r-2": {"status": "completed"}}
    for request_id in list(jobs):
        ctl.accepted(1)
        ctl.started()
        ctl.finished(request_id, success=True, jobs=jobs)
    state = ctl.snapshot(0, jobs)
    assert state["completed_count"] == 2
    assert state["accepted_count"] == 2
    assert state["evicted_count"] == 1
    assert state["inflight_count"] == 0

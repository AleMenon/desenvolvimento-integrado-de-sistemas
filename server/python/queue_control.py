"""Bounded FIFO reconstruction queue accounting shared by the Python server.

The service holds its own lock while calling these methods.  Completed result
retention does not affect the lifetime counters used to assess saturation.
"""

from collections import deque
from math import isfinite
from time import monotonic


class QueueControl:
    """Track capacity, concurrent workers, saturation and bounded results."""

    def __init__(
        self,
        *,
        queue_capacity=64,
        worker_count=1,
        max_inflight=None,
        max_retained_results=1024,
        result_ttl_seconds=3600.0,
    ):
        for name, value, lower, upper in (
            ("queue_capacity", queue_capacity, 1, 100_000),
            ("worker_count", worker_count, 1, 32),
            ("max_retained_results", max_retained_results, 1, 100_000),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{name} must be an integer between {lower} and {upper}")
        if (
            type(result_ttl_seconds) not in (int, float)
            or not isfinite(result_ttl_seconds)
            or result_ttl_seconds <= 0
        ):
            raise ValueError("result_ttl_seconds must be finite and positive")

        if max_inflight is None:
            max_inflight = queue_capacity + worker_count
        if (type(max_inflight) is not int or
                not 1 <= max_inflight <= queue_capacity + worker_count):
            raise ValueError("max_inflight must be between 1 and queue_capacity + worker_count")
        self.queue_capacity = queue_capacity
        self.worker_count = worker_count
        self.max_inflight = max_inflight
        self.inflight_count = 0
        self.admission_rejected_count = 0
        self.max_retained_results = max_retained_results
        self.result_ttl_seconds = float(result_ttl_seconds)
        self.accepted_count = 0
        self.completed_count = 0
        self.failed_count = 0
        self.rejected_count = 0
        self.running_count = 0
        self.queue_peak = 0
        self.evicted_count = 0
        self._finished = deque()  # (monotonic completion time, request_id)

    def can_admit(self):
        # One atomic accounting counter for both queued and running jobs.
        # The server holds its lock while calling accepted/finished/can_admit;
        # this avoids a race while a worker removes a job from queue.Queue.
        return self.inflight_count < self.max_inflight

    def accepted(self, queue_size):
        if not self.can_admit():
            raise AssertionError("admission limit exceeded")
        self.inflight_count += 1
        self.accepted_count += 1
        self.queue_peak = max(self.queue_peak, queue_size)

    def rejected(self, *, admission=False):
        self.rejected_count += 1
        if admission:
            self.admission_rejected_count += 1

    def started(self):
        self.running_count += 1
        if self.running_count > self.worker_count:
            raise AssertionError("running reconstruction count exceeds workers")

    def finished(self, request_id, *, success, jobs):
        if self.running_count <= 0:
            raise AssertionError("finished without a running reconstruction")
        self.running_count -= 1
        if self.inflight_count <= 0:
            raise AssertionError("finished without an accepted reconstruction")
        self.inflight_count -= 1
        if success:
            self.completed_count += 1
        else:
            self.failed_count += 1
        self._finished.append((monotonic(), request_id))
        return self.prune(jobs)

    def prune(self, jobs):
        evicted_ids = []
        now = monotonic()
        while self._finished:
            completed_at, request_id = self._finished[0]
            if (
                len(self._finished) <= self.max_retained_results
                and now - completed_at < self.result_ttl_seconds
            ):
                break
            self._finished.popleft()
            job = jobs.get(request_id)
            if job is not None and job["status"] in ("completed", "failed"):
                del jobs[request_id]
                self.evicted_count += 1
                evicted_ids.append(request_id)
        return evicted_ids

    def snapshot(self, queue_size, jobs):
        self.prune(jobs)
        return {
            "implementation": "python",
            "queue_policy": "fifo",
            "queue_capacity": self.queue_capacity,
            "queue_size": queue_size,
            "queue_peak": self.queue_peak,
            "worker_count": self.worker_count,
            "admission_limit": self.max_inflight,
            "inflight_count": self.inflight_count,
            "admission_rejected_count": self.admission_rejected_count,
            "running_count": self.running_count,
            "accepted_count": self.accepted_count,
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "rejected_count": self.rejected_count,
            "retained_results": len(self._finished),
            "evicted_count": self.evicted_count,
        }

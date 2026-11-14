"""Thread-safe metrics registry for a Python reconstruction server (TASK-16).

Integrate with TASK-12's request queue: accepted -> started -> completed/failed.
The GET /metrics and GET /metrics/reconstructions handlers should return
``snapshot()`` and ``reconstructions()`` respectively.
"""

from collections import defaultdict
import math
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class PerformanceMetrics:
    """In-process job counters and time-weighted queue statistics.

    Uses monotonic clocks for durations; wall clock only for ISO 8601 timestamps.
    A job may only transition queued -> running -> completed/failed.
    """

    def __init__(self, implementation: str = "python") -> None:
        if not implementation:
            raise ValueError("implementation is required")
        self.implementation = implementation
        self._lock = RLock()
        self._started = monotonic()
        self._queue_changed = self._started
        self._queue_area = 0.0
        self._queue_durations: dict[int, float] = defaultdict(float, {0: 0.0})
        self._queue_size = 0
        self._jobs: dict[str, dict[str, Any]] = {}
        self._running_starts: dict[str, float] = {}
        self._completed_count = 0
        self._failed_count = 0
        self._running_count = 0
        self._completed_duration_ms = 0.0

    def _accrue_queue(self, now: float) -> None:
        elapsed = max(0.0, now - self._queue_changed)
        self._queue_area += self._queue_size * elapsed
        self._queue_durations[self._queue_size] += elapsed
        self._queue_changed = now

    def accepted(self, request_id: str, client_id: str, signal_id: str, model_id: str) -> None:
        with self._lock:
            if not request_id or request_id in self._jobs:
                raise ValueError("request_id must be unique and non-empty")
            self._accrue_queue(monotonic())
            self._jobs[request_id] = {
                "request_id": request_id,
                "client_id": client_id,
                "signal_id": signal_id,
                "model_id": model_id,
                "algorithm": "cgnr",
                "status": "queued",
                "created_at": utc_now(),
                "started_at": None,
                "finished_at": None,
                "execution_time_ms": None,
                "iterations": None,
                "converged": None,
                "stop_reason": None,
            }
            self._queue_size += 1

    def started(self, request_id: str) -> None:
        with self._lock:
            job = self._jobs[request_id]
            if job["status"] != "queued":
                raise ValueError("Only queued jobs can start")
            now = monotonic()
            self._accrue_queue(now)
            self._queue_size -= 1
            job["status"] = "running"
            job["started_at"] = utc_now()
            self._running_starts[request_id] = now
            self._running_count += 1

    def finished(
        self,
        request_id: str,
        *,
        success: bool,
        iterations: int | None = None,
        converged: bool | None = None,
        stop_reason: str | None = None,
        execution_time_ms: float | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs[request_id]
            if job["status"] != "running":
                raise ValueError("Only running jobs can finish")
            start = self._running_starts[request_id]
            elapsed = (monotonic() - start) * 1000 if execution_time_ms is None else execution_time_ms
            if elapsed < 0 or not math.isfinite(elapsed):
                raise ValueError("execution_time_ms must be finite and nonnegative")
            del self._running_starts[request_id]
            self._running_count -= 1
            if success:
                self._completed_count += 1
                self._completed_duration_ms += elapsed
            else:
                self._failed_count += 1
            job.update({
                "status": "completed" if success else "failed",
                "finished_at": utc_now(),
                "execution_time_ms": float(elapsed),
                "iterations": iterations,
                "converged": converged,
                "stop_reason": stop_reason,
            })

    def snapshot(self) -> dict:
        with self._lock:
            now = monotonic()
            self._accrue_queue(now)
            uptime = max(0.0, now - self._started)
            queue_mode = min(self._queue_durations, key=lambda v: (-self._queue_durations[v], v))
            return {
                "schema_version": 1,
                "implementation": self.implementation,
                "timestamp_utc": utc_now(),
                "uptime_ms": uptime * 1000,
                "received_count": len(self._jobs),
                "completed_count": self._completed_count,
                "failed_count": self._failed_count,
                "running_count": self._running_count,
                "queue_size": self._queue_size,
                "queue_mean": self._queue_area / uptime if uptime > 0 else 0.0,
                "queue_mode": queue_mode,
                "mean_reconstruction_time_ms": (
                    self._completed_duration_ms / self._completed_count
                    if self._completed_count else None
                ),
            }

    def reconstructions(self) -> dict:
        with self._lock:
            return {
                "schema_version": 1,
                "implementation": self.implementation,
                "reconstructions": [job.copy() for job in self._jobs.values()],
            }

"""TASK-16: common process and HTTP metrics collector for Python and C++.

The collector runs *outside* the server under measurement and uses the same
/metrics API for both implementations.  CPU and RSS are sampled via psutil.
"""

import argparse
import csv
import json
import math
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psutil
import requests


SAMPLE_COLUMNS = (
    "timestamp_utc", "elapsed_ms", "cpu_percent", "memory_rss_bytes",
    "queue_size", "running_count", "received_count", "completed_count", "failed_count",
)
RECONSTRUCTION_COLUMNS = (
    "request_id", "client_id", "signal_id", "model_id", "algorithm", "status",
    "created_at", "started_at", "finished_at", "execution_time_ms",
    "iterations", "converged", "stop_reason",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Collector:
    def __init__(self, base_url: str, pid: int, output_dir: Path, interval: float = 0.1,
                 timeout: float = 2.0) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be http(s)")
        if interval <= 0 or not math.isfinite(interval):
            raise ValueError("interval must be finite and positive")
        if timeout <= 0 or not math.isfinite(timeout):
            raise ValueError("timeout must be finite and positive")
        self.url = base_url.rstrip("/")
        self.process = psutil.Process(pid)
        self.output_dir = Path(output_dir)
        self.interval = interval
        self.timeout = timeout
        self.samples: list[dict] = []
        self.initial: dict | None = None
        self.final: dict | None = None
        self._previous_cpu: float | None = None
        self._previous_time: float | None = None

    def _get(self, endpoint: str) -> dict:
        response = requests.get(f"{self.url}{endpoint}", timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError(f"Invalid TASK-16 API response at {endpoint}")
        return data

    def _process_resources(self) -> tuple[float, int]:
        """Aggregate the monitored process and all current child processes.

        CPU time is cumulative user+system seconds; RSS is sum of per-process RSS.
        RSS may double-count shared pages; use the same convention for both servers.
        """
        try:
            children = self.process.children(recursive=True)
            processes = [self.process, *children]
        except psutil.Error:
            processes = [self.process]
        cpu_seconds = 0.0
        memory_bytes = 0
        seen = set()
        for process in processes:
            try:
                if process.pid in seen:
                    continue
                seen.add(process.pid)
                cpu = process.cpu_times()
                cpu_seconds += cpu.user + cpu.system
                memory_bytes += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return cpu_seconds, memory_bytes

    def _sample(self, since: float, moment: float, metrics: dict) -> None:
        cpu_time, rss = self._process_resources()
        percentage = None
        if self._previous_cpu is not None and self._previous_time is not None:
            delta_time = moment - self._previous_time
            if delta_time > 0:
                percentage = max(0.0, (cpu_time - self._previous_cpu) / delta_time * 100)
        self._previous_cpu, self._previous_time = cpu_time, moment
        self.samples.append({
            "timestamp_utc": utc_now(),
            "elapsed_ms": (moment - since) * 1000,
            "cpu_percent": percentage,
            "memory_rss_bytes": rss,
            "queue_size": metrics["queue_size"],
            "running_count": metrics["running_count"],
            "received_count": metrics["received_count"],
            "completed_count": metrics["completed_count"],
            "failed_count": metrics["failed_count"],
        })

    def run(self, duration: float | None = None) -> dict:
        """Monitor for `duration` seconds, or until Ctrl+C when omitted.

        Exports even when stopped with Ctrl+C; a failed HTTP request propagates
        rather than silently producing incomplete/comparable-looking metrics.
        """
        if duration is not None and (duration <= 0 or not math.isfinite(duration)):
            raise ValueError("duration must be finite and positive")
        initial = self._get("/metrics")
        self.initial = initial
        begin_timestamp = datetime.now(timezone.utc)
        start = time.monotonic()
        self._sample(start, start, initial)
        next_sample = start + self.interval
        try:
            while True:
                now = time.monotonic()
                if duration is not None and now - start >= duration:
                    break
                time.sleep(max(0, min(next_sample - now, (start + duration - now) if duration is not None else self.interval)))
                now = time.monotonic()
                if duration is not None and now - start >= duration:
                    break
                response = self._get("/metrics")
                self._sample(start, now, response)
                next_sample += self.interval
                if next_sample < now:
                    next_sample = now + self.interval
        except KeyboardInterrupt:
            pass
        # Take final sample and job list while the server still runs.
        finish_snapshot = self._get("/metrics")
        end = time.monotonic()
        end_timestamp = datetime.now(timezone.utc)
        self._sample(start, end, finish_snapshot)
        self.final = finish_snapshot
        jobs = self._get("/metrics/reconstructions")
        if jobs.get("implementation") != initial.get("implementation") or finish_snapshot.get("implementation") != initial.get("implementation"):
            raise ValueError("Metrics returned by incompatible implementations")
        reconstructions = []
        for job in jobs.get("reconstructions", []):
            if job.get("status") not in ("completed", "failed") or not job.get("finished_at"):
                continue
            finished_at = utc_parse(job["finished_at"])
            if begin_timestamp <= finished_at <= end_timestamp:
                reconstructions.append({key: job.get(key) for key in RECONSTRUCTION_COLUMNS})
        return self.export(end - start, reconstructions)

    def export(self, elapsed: float, reconstructions: list[dict]) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with (self.output_dir / "samples.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=SAMPLE_COLUMNS)
            writer.writeheader()
            writer.writerows(self.samples)
        reconstructions = sorted(reconstructions,
                                 key=lambda j: (j.get("created_at") or "", j.get("request_id") or ""))
        with (self.output_dir / "reconstructions.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=RECONSTRUCTION_COLUMNS)
            writer.writeheader()
            writer.writerows(reconstructions)
        assert self.initial is not None and self.final is not None
        completed = self.final["completed_count"] - self.initial["completed_count"]
        failed = self.final["failed_count"] - self.initial["failed_count"]
        received = self.final["received_count"] - self.initial["received_count"]
        times = [float(j["execution_time_ms"]) for j in reconstructions
                 if j["status"] == "completed" and j["execution_time_ms"] is not None]
        sample_queues = [sample["queue_size"] for sample in self.samples]
        peak_cpus = [sample["cpu_percent"] for sample in self.samples if sample["cpu_percent"] is not None]
        most_common_queue = Counter(sample_queues)
        inflight_at_start = self.initial["queue_size"] + self.initial["running_count"]
        unfinished_at_end = self.final["queue_size"] + self.final["running_count"]
        # A duration/throughput value is only comparable for a complete workload.
        # If collection cuts through a job, report counts/samples but not a
        # misleading duration computed from the small finished subset.
        workload_complete = (
            received > 0
            and inflight_at_start == 0
            and unfinished_at_end == 0
            and received == completed + failed
            and len(reconstructions) == completed + failed
        )
        workload_duration_ms = None
        if workload_complete:
            first_arrival = min(utc_parse(job["created_at"]) for job in reconstructions)
            final_completion = max(utc_parse(job["finished_at"]) for job in reconstructions)
            workload_duration_ms = max(0.0, (final_completion - first_arrival).total_seconds() * 1000)
        summary = {
            "schema_version": 1,
            "implementation": self.initial["implementation"],
            "total_execution_time_ms": workload_duration_ms,
            "workload_complete": workload_complete,
            "inflight_at_start": inflight_at_start,
            "monitoring_window_ms": elapsed * 1000,
            "received_count": received,
            "completed_count": completed,
            "failed_count": failed,
            "unfinished_count_at_end": unfinished_at_end,
            "mean_reconstruction_time_ms": sum(times) / len(times) if times else None,
            "images_per_second": (completed * 1000 / workload_duration_ms)
                if workload_duration_ms and completed else None,
            "peak_cpu_percent": max(peak_cpus, default=None),
            "peak_memory_rss_bytes": max((s["memory_rss_bytes"] for s in self.samples), default=0),
            "queue_mean_sampled": sum(sample_queues) / len(sample_queues) if sample_queues else 0.0,
            "queue_mode_sampled": min((q for q, n in most_common_queue.items() if n == max(most_common_queue.values())), default=0),
            "server_queue_mean_since_start": self.final["queue_mean"],
            "server_queue_mode_since_start": self.final["queue_mode"],
            "sample_interval_seconds": self.interval,
            "reconstruction_rows_exported": len(reconstructions),
            "cpu_definition": "100 percent per logical CPU core, process + current descendants",
            "memory_definition": "RSS bytes summed across process and current descendants",
        }
        (self.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
        return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="TASK-16 - CPU, RAM, queue and job metrics collector")
    parser.add_argument("--url", required=True, help="URL of the Python or C++ server")
    parser.add_argument("--pid", type=int, required=True, help="PID of the server process")
    parser.add_argument("--output", required=True, type=Path, help="Destination directory")
    parser.add_argument("--interval", default=0.1, type=float, help="Sampling period in seconds")
    parser.add_argument("--duration", default=None, type=float, help="Optional duration; Ctrl+C otherwise")
    args = parser.parse_args()
    summary = Collector(args.url, args.pid, args.output, args.interval).run(args.duration)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""End-to-end collector tests against the common metrics HTTP contract.

The fake HTTP endpoints use the Python registry to verify the independent
collector without requiring native libraries in a unit-test environment.
"""

import csv
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from monitoring.collect import Collector
from server.python.performance_metrics import PerformanceMetrics


@pytest.mark.parametrize("implementation", ["python", "cpp"])
def test_collector_exports_compatible_files(tmp_path, implementation):
    registry = PerformanceMetrics(implementation)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/metrics":
                body = registry.snapshot()
            elif self.path == "/metrics/reconstructions":
                body = registry.reconstructions()
            else:
                self.send_error(404)
                return
            payload = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output_dir = tmp_path / implementation
    collector = Collector(f"http://127.0.0.1:{server.server_port}", os.getpid(), output_dir, interval=0.02)
    try:
        worker = threading.Thread(target=collector.run, args=(0.25,))
        worker.start()
        time.sleep(0.06)
        registry.accepted("req-1", "client", "signal", "model")
        time.sleep(0.05)
        registry.started("req-1")
        time.sleep(0.04)
        registry.finished("req-1", success=True, iterations=1,
                          converged=True, stop_reason="tolerance_reached",
                          execution_time_ms=9.25)
        worker.join(timeout=5)
        assert not worker.is_alive()
        summary = json.loads((output_dir / "summary.json").read_text())
        assert summary["implementation"] == implementation
        assert summary["completed_count"] == 1
        assert summary["received_count"] == 1
        assert summary["failed_count"] == 0
        assert summary["monitoring_window_ms"] >= 200
        assert summary["total_execution_time_ms"] is not None
        assert summary["total_execution_time_ms"] > 0
        assert summary["total_execution_time_ms"] < summary["monitoring_window_ms"]
        assert summary["mean_reconstruction_time_ms"] == 9.25
        assert summary["peak_memory_rss_bytes"] > 0
        assert summary["queue_mode_sampled"] in (0, 1)
        with (output_dir / "samples.csv").open() as stream:
            samples = list(csv.DictReader(stream))
        assert len(samples) > 2
        assert any(row["queue_size"] == "1" for row in samples)
        assert all(int(row["memory_rss_bytes"]) > 0 for row in samples)
        with (output_dir / "reconstructions.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 1
        assert rows[0]["execution_time_ms"] == "9.25"
        assert rows[0]["request_id"] == "req-1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

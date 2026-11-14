"""TASK-16 C++ actual executable API + external process monitor.

Build the TASK-13/16 server before running this test. The test is skipped if
its binary is not available in the checkout.
"""

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests

from concurrent.futures import ThreadPoolExecutor
from monitoring.collect import Collector
from server.python.performance_metrics import PerformanceMetrics


ROOT = Path(__file__).resolve().parents[2]
SERVER = Path(os.environ.get("CPP_SERVER_BIN", str(ROOT / "build" / "reconstruction_server")))


@pytest.mark.skipif(not SERVER.is_file(), reason="Compile reconstruction_server with CMake first")
def test_cpp_server_metrics_are_exportable(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with subprocess.Popen(
        [str(SERVER.resolve()), "--host", "127.0.0.1", "--port", str(port),
         "--catalog", str(ROOT / "models" / "catalog.json")],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    ) as process:
        base_url = f"http://127.0.0.1:{port}"
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise AssertionError(process.stderr.read().decode())
                try:
                    if requests.get(base_url + "/health", timeout=0.2).ok:
                        break
                except requests.RequestException:
                    time.sleep(0.05)
            else:
                pytest.fail("C++ server did not start")

            metrics = requests.get(base_url + "/metrics", timeout=3).json()
            assert metrics["implementation"] == "cpp"
            assert metrics["schema_version"] == 1
            assert metrics["received_count"] == 0
            assert set(metrics) == set(PerformanceMetrics().snapshot())
            assert isinstance(metrics["queue_mean"], (int, float))
            collector = Collector(base_url, process.pid, tmp_path / "cpp", interval=0.02)
            # Use an external thread to send requests during the measurement window.
            def load():
                time.sleep(0.08)
                for i in range(10):
                    response = requests.post(base_url + "/reconstructions", json={
                        "client_id": "c", "signal_id": f"sig-{i}",
                        "model_id": "demo_identity_3", "algorithm": "cgnr",
                        "signal": [1.0, 2.0, 3.0],
                        "parameters": {"max_iterations": 10, "tolerance": 1e-8},
                    }, timeout=3)
                    assert response.status_code == 202
                    identifier = response.json()["request_id"]
                    for _ in range(100):
                        state = requests.get(f"{base_url}/reconstructions/{identifier}", timeout=3).json()
                        if state["status"] == "completed":
                            break
                        assert state["status"] != "failed"
                        time.sleep(0.01)
                    else:
                        raise AssertionError("reconstruction did not finish")

            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(load)
                summary = collector.run(duration=1.5)
                pending.result(timeout=5)
            assert summary["implementation"] == "cpp"
            assert summary["completed_count"] == 10
            last_metrics = requests.get(base_url + "/metrics", timeout=3).json()
            assert last_metrics["completed_count"] == 10
            assert last_metrics["queue_size"] == 0
            jobs = requests.get(base_url + "/metrics/reconstructions", timeout=3).json()
            assert len(jobs["reconstructions"]) == 10
            assert set(jobs["reconstructions"][0]) == {
                "request_id", "client_id", "signal_id", "model_id", "algorithm", "status",
                "created_at", "started_at", "finished_at", "execution_time_ms",
                "iterations", "converged", "stop_reason",
            }
            assert summary["mean_reconstruction_time_ms"] is not None
            assert (tmp_path / "cpp" / "reconstructions.csv").exists()
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


@pytest.mark.skipif(not SERVER.is_file(), reason="Compile reconstruction_server with CMake first")
def test_cpp_metrics_measure_actual_concurrent_queue(tmp_path):
    """Five concurrent POSTs while CGNR worker is gated; no timing races."""
    gate = tmp_path / "cgnr-worker-blocked.lock"
    gate.touch()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    # Test hook is supplied by the latest TASK-13 and BUILD_TESTING=ON.
    env["TASK13_TEST_GATE_FILE"] = str(gate)
    with subprocess.Popen(
        [str(SERVER.resolve()), "--host", "127.0.0.1", "--port", str(port),
         "--catalog", str(ROOT / "models" / "catalog.json"),
         "--queue-capacity", "8"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env,
    ) as process:
        url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError(process.stderr.read().decode())
                try:
                    if requests.get(url + "/health", timeout=0.2).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.02)
            else:
                pytest.fail("C++ server did not start")

            collector = Collector(url, process.pid, tmp_path / "cpp-concurrent", interval=0.02)

            def submit(index):
                response = requests.post(url + "/reconstructions", json={
                    "client_id": f"client-{index}", "signal_id": f"signal-{index}",
                    "model_id": "demo_identity_3", "algorithm": "cgnr",
                    "signal": [1.0, 2.0, 3.0],
                    "parameters": {"max_iterations": 10, "tolerance": 1e-8},
                }, timeout=3)
                assert response.status_code == 202
                return response.json()["request_id"]

            with ThreadPoolExecutor(max_workers=6) as pool:
                monitoring = pool.submit(collector.run, 1.15)
                # Ensure collection's initial snapshot precedes the load.
                deadline = time.monotonic() + 3
                while (collector.initial is None or not collector.samples) and time.monotonic() < deadline:
                    time.sleep(0.005)
                assert collector.initial is not None and collector.samples
                submissions = [pool.submit(submit, i) for i in range(5)]
                ids = [task.result(timeout=4) for task in submissions]
                assert len(set(ids)) == 5

                deadline = time.monotonic() + 3
                observed = None
                while time.monotonic() < deadline:
                    observed = requests.get(url + "/metrics", timeout=2).json()
                    if observed["queue_size"] == 4 and observed["running_count"] == 1:
                        break
                    time.sleep(0.01)
                else:
                    pytest.fail(
                        f"queue not held by test hook: {observed}. "
                        "Merge the latest task-13 and build with -DBUILD_TESTING=ON"
                    )
                # Keep queue occupied long enough to dominate the sampling window.
                time.sleep(0.7)
                waiting = requests.get(url + "/metrics", timeout=2).json()
                assert waiting["queue_size"] == 4
                assert waiting["running_count"] == 1
                assert waiting["queue_mean"] > 0
                assert waiting["queue_mode"] == 4
                gate.unlink()

                deadline = time.monotonic() + 5
                for request_id in ids:
                    while time.monotonic() < deadline:
                        state = requests.get(
                            f"{url}/reconstructions/{request_id}", timeout=2
                        ).json()["status"]
                        if state == "completed":
                            break
                        assert state != "failed"
                        time.sleep(0.01)
                    else:
                        pytest.fail("reconstruction did not finish")
                summary = monitoring.result(timeout=5)

            assert summary["workload_complete"] is True
            assert summary["received_count"] == 5
            assert summary["completed_count"] == 5
            assert summary["unfinished_count_at_end"] == 0
            assert summary["queue_mean_sampled"] > 0
            assert summary["queue_mode_sampled"] == 4
            assert summary["server_queue_mean_since_start"] > 0
            assert summary["server_queue_mode_since_start"] == 4
            assert summary["total_execution_time_ms"] is not None
            assert summary["images_per_second"] is not None
        finally:
            gate.unlink(missing_ok=True)
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

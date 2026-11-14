"""TASK-15: real C++ server, FIFO queue, saturation and bounded retention.

Requires BUILD_TESTING=ON so the TASK-13 test gate is enabled.  The gate is
held by a file, not by timing guesses about matrix multiplication.
"""

import os
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
SERVER = Path(os.environ.get("CPP_SERVER_BIN", str(ROOT / "build" / "reconstruction_server")))


@contextmanager
def start_server(*, args=(), gate=None):
    if not SERVER.is_file():
        pytest.skip(f"compile reconstruction_server first: {SERVER}")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    if gate is not None:
        env["TASK13_TEST_GATE_FILE"] = str(gate)
    process = subprocess.Popen(
        [str(SERVER), "--host", "127.0.0.1", "--port", str(port),
         "--catalog", str(ROOT / "models" / "catalog.json"), *args],
        env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail(process.stderr.read().decode())
            try:
                if requests.get(url + "/health", timeout=0.4).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.02)
        else:
            pytest.fail("C++ server did not start")
        yield url
    finally:
        if gate is not None:
            gate.unlink(missing_ok=True)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()


def post(url, index):
    return requests.post(url + "/reconstructions", json={
        "client_id": f"client-{index}", "signal_id": f"signal-{index}",
        "model_id": "demo_identity_3", "algorithm": "cgnr",
        "signal": [1.0, 2.0, 3.0],
        "parameters": {"max_iterations": 10, "tolerance": 1e-8},
    }, timeout=4)


def poll(url, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = requests.get(url + "/queue", timeout=3).json()
        if predicate(last):
            return last
        time.sleep(0.01)
    pytest.fail(f"queue condition not reached: {last}")


def test_cpp_queue_workers_and_saturation(tmp_path):
    gate = tmp_path / "worker-gate.lock"
    gate.touch()
    with start_server(args=("--workers", "2", "--queue-capacity", "2"), gate=gate) as url:
        with ThreadPoolExecutor(max_workers=2) as executor:
            running = list(executor.map(lambda i: post(url, i), range(2)))
        assert [r.status_code for r in running] == [202] * 2
        poll(url, lambda x: x["running_count"] == 2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            queued = list(executor.map(lambda i: post(url, i), range(2, 4)))
        assert [r.status_code for r in queued] == [202] * 2
        ids = [r.json()["request_id"] for r in (*running, *queued)]
        stats = poll(url, lambda x: x["running_count"] == 2 and x["queue_size"] == 2)
        assert stats["worker_count"] == 2
        assert stats["queue_peak"] == 2
        assert stats["accepted_count"] == 4
        rejected = post(url, 4)
        assert rejected.status_code == 503
        assert rejected.json()["error"]["code"] == "QUEUE_FULL"
        assert requests.get(url + "/queue").json()["rejected_count"] == 1
        gate.unlink()
        stats = poll(url, lambda x: x["completed_count"] == 4)
        assert stats["running_count"] == stats["queue_size"] == 0
        for identifier in ids:
            assert requests.get(f"{url}/reconstructions/{identifier}/result").status_code == 200


def test_cpp_history_bound_does_not_change_lifetime_counters():
    with start_server(args=("--max-retained-results", "2")) as url:
        ids = []
        for i in range(3):
            response = post(url, i)
            assert response.status_code == 202
            identifier = response.json()["request_id"]
            ids.append(identifier)
            poll(url, lambda x: x["completed_count"] == i + 1)
        status = requests.get(url + "/queue").json()
        assert status["completed_count"] == 3
        assert status["accepted_count"] == 3
        assert status["retained_results"] == 2
        assert status["evicted_count"] == 1
        assert requests.get(f"{url}/reconstructions/{ids[0]}").status_code == 404
        expired = requests.get(f"{url}/reconstructions/{ids[0]}/result", timeout=3)
        assert expired.status_code == 404
        assert expired.json()["error"]["code"] == "REQUEST_NOT_FOUND"
        assert requests.get(f"{url}/reconstructions/{ids[2]}/result").status_code == 200
        # TASK-16 retains lifetime counts but cannot export evicted job rows.
        metrics = requests.get(url + "/metrics", timeout=3).json()
        assert metrics["received_count"] == metrics["completed_count"] == 3
        records = requests.get(url + "/metrics/reconstructions", timeout=3).json()
        assert len(records["reconstructions"]) == 2

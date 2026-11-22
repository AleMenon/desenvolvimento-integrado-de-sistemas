"""TASK-19: real services reject overload without losing accepted tasks."""

import os
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import requests

import server.python.reconstruction_server as module

ROOT = Path(__file__).resolve().parents[2]
SERVER = Path(os.environ.get("CPP_SERVER_BIN", str(ROOT / "build" / "reconstruction_server")))


def payload(index):
    return {
        "client_id": "task19", "signal_id": f"signal-{index}",
        "model_id": "demo_identity_3", "algorithm": "cgnr",
        "signal": [1.0, 2.0, 3.0],
        "parameters": {"max_iterations": 10, "tolerance": 1e-8},
    }


def wait(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("Timed out waiting for worker transition")


def test_python_admission_ceiling_with_concurrent_workers(monkeypatch):
    gate = threading.Event()
    both_started = threading.Event()
    lock = threading.Lock()
    count = 0
    original = module.cgnr

    def blocked(*args, **kwargs):
        nonlocal count
        with lock:
            count += 1
            if count == 2:
                both_started.set()
        if not gate.wait(timeout=8):
            raise TimeoutError("CGNR test worker gate timed out")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "cgnr", blocked)
    service = module.ReconstructionService(
        "models/catalog.json", queue_capacity=8, worker_count=2,
        max_inflight=3,
    )
    try:
        first, second = service.submit(payload(1)), service.submit(payload(2))
        assert first[1] == second[1] == 202
        assert both_started.wait(6)
        third = service.submit(payload(3))
        assert third[1] == 202
        rejected, status = service.submit(payload(4))
        assert status == 503 and rejected["error"]["code"] == "QUEUE_FULL"
        snapshot = service.queue_snapshot()
        assert snapshot["admission_limit"] == 3
        assert snapshot["inflight_count"] == 3
        assert snapshot["running_count"] == 2
        assert snapshot["queue_size"] == 1
        assert snapshot["admission_rejected_count"] == 1
        assert snapshot["accepted_count"] == 3
        gate.set()
        wait(lambda: service.queue_snapshot()["completed_count"] == 3)
        after = service.queue_snapshot()
        assert after["inflight_count"] == after["queue_size"] == 0
        assert after["rejected_count"] == 1
        assert service.metrics.snapshot()["received_count"] == 3
    finally:
        gate.set()
        service.shutdown()


@pytest.mark.skipif(not SERVER.is_file(), reason="Compile C++ server before test")
def test_cpp_admission_ceiling_with_test_gate(tmp_path):
    gate = tmp_path / "task19-cpp-gate.lock"
    gate.touch()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["TASK13_TEST_GATE_FILE"] = str(gate)
    process = subprocess.Popen([
        str(SERVER.resolve()), "--host", "127.0.0.1", "--port", str(port),
        "--catalog", str(ROOT / "models" / "catalog.json"),
        "--workers", "2", "--queue-capacity", "8", "--max-inflight", "3",
    ], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            try:
                if requests.get(base + "/health", timeout=0.3).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.02)
        else:
            pytest.fail("C++ server did not start")

        def post(i):
            return requests.post(base + "/reconstructions", json=payload(i), timeout=4)

        r1, r2 = post(1), post(2)
        assert r1.status_code == r2.status_code == 202
        wait(lambda: requests.get(base + "/queue", timeout=2).json()["running_count"] == 2)
        r3 = post(3)
        assert r3.status_code == 202
        r4 = post(4)
        assert r4.status_code == 503
        assert r4.json()["error"]["code"] == "QUEUE_FULL"
        assert r4.headers.get("Retry-After") == "1"
        state = requests.get(base + "/queue", timeout=2).json()
        assert state["admission_limit"] == state["inflight_count"] == 3
        assert state["admission_rejected_count"] == 1
        gate.unlink()
        wait(lambda: requests.get(base + "/queue", timeout=2).json()["completed_count"] == 3)
        state = requests.get(base + "/queue", timeout=2).json()
        assert state["inflight_count"] == 0
        assert state["accepted_count"] == 3
    finally:
        gate.unlink(missing_ok=True)
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()

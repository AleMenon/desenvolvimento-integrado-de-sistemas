"""TASK-15: concurrency, capacity, retirement and normal-shutdown invariants."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import server.python.reconstruction_server as module


def request(i):
    return {
        "client_id": f"client-{i % 3}", "signal_id": f"signal-{i}",
        "model_id": "demo_identity_3", "algorithm": "cgnr",
        "signal": [1.0, 2.0, 3.0],
        "parameters": {"max_iterations": 10, "tolerance": 1e-8},
    }


def wait_for(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("condition was not met within timeout")


def test_workers_are_bounded_and_pending_queue_rejects_overflow(monkeypatch):
    original = module.cgnr
    gate = threading.Event()
    running = 0
    lock = threading.Lock()
    started = threading.Event()

    def gated_cgnr(*args, **kwargs):
        nonlocal running
        with lock:
            running += 1
            if running == 2:
                started.set()
        if not gate.wait(5):
            raise TimeoutError("test gate was not released")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "cgnr", gated_cgnr)
    service = module.ReconstructionService(
        "models/catalog.json", queue_capacity=2, worker_count=2,
    )
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            answers = list(executor.map(lambda i: service.submit(request(i)), range(2)))
        assert all(code == 202 for _, code in answers)
        assert started.wait(5)
        queued = [service.submit(request(i)) for i in range(2, 4)]
        assert all(code == 202 for _, code in queued)
        refused, code = service.submit(request(4))
        assert code == 503
        assert refused["error"]["code"] == "QUEUE_FULL"
        stats = service.queue_snapshot()
        assert stats["worker_count"] == stats["running_count"] == 2
        assert stats["queue_size"] == stats["queue_peak"] == 2
        assert stats["accepted_count"] == 4
        assert stats["rejected_count"] == 1
        assert all(service.get_job(result["request_id"]) for result, _ in answers + queued)
    finally:
        gate.set()
        service.shutdown()
    stats = service.queue_snapshot()
    assert stats["running_count"] == stats["queue_size"] == 0
    assert stats["completed_count"] == 4
    assert stats["failed_count"] == 0


def test_drain_on_normal_shutdown_does_not_discard_accepted_jobs(monkeypatch):
    original = module.cgnr
    gate = threading.Event()
    started = threading.Event()

    def gated(*args, **kwargs):
        started.set()
        if not gate.wait(5):
            raise TimeoutError("test gate was not released")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "cgnr", gated)
    service = module.ReconstructionService("models/catalog.json", queue_capacity=3)
    try:
        first, status = service.submit(request(0))
        assert status == 202
        assert started.wait(5)
        remaining = [service.submit(request(i)) for i in range(1, 3)]
        assert all(status == 202 for _, status in remaining)
        with ThreadPoolExecutor(max_workers=1) as pool:
            shutdown_future = pool.submit(service.shutdown)
            wait_for(lambda: service.stopping.is_set())
            refused, status = service.submit(request(3))
            assert status == 503
            assert refused["error"]["code"] == "SERVER_SHUTTING_DOWN"
            gate.set()
            shutdown_future.result(timeout=8)
        assert service.queue_snapshot()["completed_count"] == 3
        for accepted, _ in [(first, 202), *remaining]:
            assert service.get_job(accepted["request_id"])["status"] == "completed"
    finally:
        gate.set()
        service.shutdown()


def test_retained_results_are_bounded_without_resetting_counters():
    service = module.ReconstructionService(
        "models/catalog.json", queue_capacity=4,
        max_retained_results=2, result_ttl_seconds=60,
    )
    try:
        ids = []
        for i in range(3):
            accepted, status = service.submit(request(i))
            assert status == 202
            ids.append(accepted["request_id"])
            wait_for(lambda: service.get_job(ids[-1])["status"] == "completed")
        stats = service.queue_snapshot()
        assert stats["accepted_count"] == stats["completed_count"] == 3
        assert stats["retained_results"] == 2
        assert stats["evicted_count"] == 1
        # TASK-16 counters must survive eviction of its per-job history.
        assert service.metrics.snapshot()["received_count"] == 3
        assert service.metrics.snapshot()["completed_count"] == 3
        assert len(service.metrics.reconstructions()["reconstructions"]) == 2
        assert service.get_job(ids[0]) is None
        assert service.get_job(ids[-1])["status"] == "completed"
    finally:
        service.shutdown()


def test_three_clients_45_reconstructions_without_lost_accepted_tasks():
    service = module.ReconstructionService(
        "models/catalog.json", queue_capacity=64, worker_count=3,
    )
    try:
        def send(client):
            return [service.submit(request(client * 15 + i)) for i in range(15)]

        with ThreadPoolExecutor(max_workers=3) as executor:
            submissions = [item for batch in executor.map(send, range(3)) for item in batch]
        assert len(submissions) == 45
        assert all(status == 202 for _, status in submissions)
        ids = [response["request_id"] for response, _ in submissions]
        assert len(set(ids)) == 45
        wait_for(lambda: service.queue_snapshot()["completed_count"] == 45)
        assert service.queue_snapshot()["accepted_count"] == 45
        assert service.queue_snapshot()["rejected_count"] == 0
        assert all(service.get_job(request_id)["status"] == "completed" for request_id in ids)
    finally:
        service.shutdown()

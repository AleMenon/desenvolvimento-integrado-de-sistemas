"""Testes de robustez do serviço de reconstrução da TASK-12."""

import threading
import time

import pytest

import server.python.reconstruction_server as module


def payload(signal=None, **overrides):
    data = {
        "client_id": "cliente",
        "signal_id": "sinal",
        "model_id": "demo_identity_3",
        "algorithm": "cgnr",
        "signal": [1.0, 2.0, 3.0] if signal is None else signal,
        "parameters": {
            "max_iterations": 10,
            "tolerance": 1e-8,
        },
    }
    data.update(overrides)
    return data


@pytest.fixture
def service():
    instance = module.ReconstructionService(
        "models/catalog.json",
        queue_capacity=1,
    )
    try:
        yield instance
    finally:
        instance.shutdown()


@pytest.mark.parametrize(
    "parameters",
    [
        {"max_iterations": True, "tolerance": 1e-8},
        {"max_iterations": 0, "tolerance": 1e-8},
        {"max_iterations": 11, "tolerance": 1e-8},
        {"max_iterations": 10, "tolerance": 0},
        {"max_iterations": 10, "tolerance": True},
        {"max_iterations": 10, "tolerance": float("inf")},
    ],
)
def test_invalid_parameters(service, parameters):
    response, status = service.submit(
        payload(parameters=parameters)
    )
    assert status == 400
    assert response["error"]["code"] == "INVALID_PARAMETERS"


def test_worker_failure_is_recorded(service, monkeypatch):
    def broken_cgnr(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(module, "cgnr", broken_cgnr)

    response, status = service.submit(payload())

    assert status == 202
    request_id = response["request_id"]

    deadline = time.monotonic() + 5

    while time.monotonic() < deadline:
        job = service.get_job(request_id)

        if job["status"] == "failed":
            assert job["error"]["code"] == (
                "RECONSTRUCTION_FAILED"
            )
            assert job["finished_at"] is not None
            return

        time.sleep(0.01)

    pytest.fail("A falha do worker não foi registrada.")


def test_queue_capacity(service, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    original_cgnr = module.cgnr

    def blocking_cgnr(*args, **kwargs):
        started.set()

        if not release.wait(timeout=5):
            raise RuntimeError("Timeout do teste")

        return original_cgnr(*args, **kwargs)

    monkeypatch.setattr(module, "cgnr", blocking_cgnr)

    try:
        first, first_status = service.submit(
            payload(signal_id="primeiro")
        )

        assert first_status == 202
        assert started.wait(timeout=5)

        second, second_status = service.submit(
            payload(signal_id="segundo")
        )

        assert second_status == 202

        third, third_status = service.submit(
            payload(signal_id="terceiro")
        )

        assert third_status == 503
        assert third["error"]["code"] == "QUEUE_FULL"
        assert first["request_id"] != second["request_id"]

    finally:
        release.set()


def test_reject_submission_after_shutdown(service):
    service.shutdown()

    response, status = service.submit(payload())

    assert status == 503
    assert response["error"]["code"] == (
        "SERVER_SHUTTING_DOWN"
    )


def test_zero_signal_reconstruction(service):
    response, status = service.submit(
        payload(signal=[0.0, 0.0, 0.0])
    )

    assert status == 202

    request_id = response["request_id"]
    deadline = time.monotonic() + 5

    while time.monotonic() < deadline:
        job = service.get_job(request_id)

        if job["status"] == "completed":
            result = job["result"]
            assert result["result"]["vector"] == [
                0.0, 0.0, 0.0
            ]
            assert result["metadata"]["converged"] is True
            assert result["metadata"]["iterations"] == 0
            return

        assert job["status"] != "failed"
        time.sleep(0.01)

    pytest.fail("Reconstrução do sinal nulo não terminou.")

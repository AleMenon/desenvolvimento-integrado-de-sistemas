"""Integração real das métricas TASK-16 com o servidor TASK-12."""

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from server.python import reconstruction_server


def payload(signal=None):
    return {
        "client_id": "cliente-metricas",
        "signal_id": "sinal-metricas",
        "model_id": "demo_identity_3",
        "algorithm": "cgnr",
        "signal": [1.0, 2.0, 3.0] if signal is None else signal,
        "parameters": {
            "max_iterations": 10,
            "tolerance": 1e-8,
        },
    }


def wait_for_job(client, request_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/reconstructions/{request_id}")
        assert response.status_code == 200
        job = response.json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.01)
    pytest.fail("Reconstrução não terminou")


def metric_job(client, request_id):
    response = client.get("/metrics/reconstructions")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 1
    matches = [
        item for item in data["reconstructions"]
        if item["request_id"] == request_id
    ]
    assert len(matches) == 1
    return matches[0]


def test_metrics_complete_reconstruction():
    app = reconstruction_server.create_app()
    with TestClient(app) as client:
        before = client.get("/metrics").json()
        assert before["implementation"] == "python"
        assert before["received_count"] == 0

        response = client.post("/reconstructions", json=payload())
        assert response.status_code == 202
        request_id = response.json()["request_id"]

        job = wait_for_job(client, request_id)
        assert job["status"] == "completed"

        after = client.get("/metrics").json()
        assert after["received_count"] == 1
        assert after["completed_count"] == 1
        assert after["failed_count"] == 0
        assert after["running_count"] == 0
        assert after["queue_size"] == 0

        record = metric_job(client, request_id)
        assert record["status"] == "completed"
        assert record["converged"] is True
        assert record["stop_reason"] == "tolerance_reached"
        assert record["execution_time_ms"] >= 0


def test_metrics_numerical_breakdown(monkeypatch):
    def fake_cgnr(matrix, signal, **kwargs):
        return {
            "solution": np.zeros(3),
            "iterations": 0,
            "converged": False,
            "stop_reason": "numerical_breakdown",
            "residual_norm": 1.0,
            "normal_residual_norm": 1.0,
        }

    monkeypatch.setattr(reconstruction_server, "cgnr", fake_cgnr)

    app = reconstruction_server.create_app()
    with TestClient(app) as client:
        response = client.post("/reconstructions", json=payload())
        assert response.status_code == 202
        request_id = response.json()["request_id"]

        job = wait_for_job(client, request_id)
        assert job["status"] == "failed"
        assert job["error"]["code"] == "NUMERICAL_BREAKDOWN"

        summary = client.get("/metrics").json()
        assert summary["received_count"] == 1
        assert summary["completed_count"] == 0
        assert summary["failed_count"] == 1
        assert summary["running_count"] == 0
        assert summary["queue_size"] == 0

        record = metric_job(client, request_id)
        assert record["status"] == "failed"
        assert record["stop_reason"] == "numerical_breakdown"
        assert record["execution_time_ms"] >= 0


def test_metrics_generic_failure(monkeypatch):
    def failing_cgnr(matrix, signal, **kwargs):
        raise RuntimeError("Falha simulada no CGNR")

    monkeypatch.setattr(reconstruction_server, "cgnr", failing_cgnr)

    app = reconstruction_server.create_app()
    with TestClient(app) as client:
        response = client.post("/reconstructions", json=payload())
        assert response.status_code == 202
        request_id = response.json()["request_id"]

        job = wait_for_job(client, request_id)
        assert job["status"] == "failed"
        assert job["error"]["code"] == "RECONSTRUCTION_FAILED"

        summary = client.get("/metrics").json()
        assert summary["received_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["completed_count"] == 0

        record = metric_job(client, request_id)
        assert record["status"] == "failed"
        assert record["stop_reason"] == "reconstruction_failed"
        assert record["execution_time_ms"] >= 0


def test_metrics_rejected_request_not_counted():
    app = reconstruction_server.create_app()
    with TestClient(app) as client:
        bad = payload()
        bad["model_id"] = "modelo-inexistente"

        response = client.post("/reconstructions", json=bad)
        assert response.status_code == 404

        summary = client.get("/metrics").json()
        assert summary["received_count"] == 0
        assert summary["completed_count"] == 0
        assert summary["failed_count"] == 0
        assert client.get("/metrics/reconstructions").json()[
            "reconstructions"
        ] == []


def test_metrics_multiple_reconstructions():
    app = reconstruction_server.create_app()
    with TestClient(app) as client:
        ids = []
        for index in range(5):
            body = payload()
            body["signal_id"] = f"sinal-{index}"
            response = client.post("/reconstructions", json=body)
            assert response.status_code == 202
            ids.append(response.json()["request_id"])

        for request_id in ids:
            assert wait_for_job(client, request_id)["status"] == "completed"

        summary = client.get("/metrics").json()
        assert summary["received_count"] == 5
        assert summary["completed_count"] == 5
        assert summary["failed_count"] == 0
        assert summary["queue_size"] == 0
        assert summary["running_count"] == 0

        records = client.get("/metrics/reconstructions").json()[
            "reconstructions"
        ]
        assert len(records) == 5
        assert {r["request_id"] for r in records} == set(ids)

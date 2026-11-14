"""Testes do relatório de imagens — TASK-14."""

import json

import pytest

from client.image_report import (
    collect_reconstruction,
    generate_image_report,
    save_image_report,
)


class FakeClient:
    def __init__(self, implementation, failed=False):
        self.implementation = implementation
        self.failed = failed

    def get_status(self, request_id):
        return {
            "request_id": request_id,
            "status": "failed" if self.failed else "completed",
            "client_id": "cliente-01",
            "signal_id": "sinal-001",
            "algorithm": "cgnr",
            "started_at": "2026-01-01T10:00:00Z",
            "finished_at": "2026-01-01T10:00:01Z",
            "error": {"code": "NUMERICAL_BREAKDOWN"}
            if self.failed else None,
        }

    def get_result(self, request_id):
        return {
            "request_id": request_id,
            "status": "completed",
            "result": {
                "vector": [1.0, 2.0, 3.0],
                "shape": [1, 3],
            },
            "metadata": {
                "client_id": "cliente-01",
                "signal_id": "sinal-001",
                "model_id": "demo",
                "algorithm": "cgnr",
                "implementation": self.implementation,
                "started_at": "2026-01-01T10:00:00Z",
                "finished_at": "2026-01-01T10:00:01Z",
                "iterations": 2,
                "converged": True,
                "stop_reason": "tolerance_reached",
                "execution_time_ms": 1.5,
            },
        }


@pytest.fixture
def experiment():
    return {
        "status": "completed",
        "clients": {
            "cliente-01": {
                "submissions": [{
                    "position": 0,
                    "model_id": "demo",
                    "signal_id": "sinal-001",
                    "python_request_id": "python-001",
                    "cpp_request_id": "cpp-001",
                }],
            },
        },
    }


def test_report_contains_both_images(experiment):
    def factory(_client_id):
        return FakeClient("python"), FakeClient("cpp")

    report = generate_image_report(
        experiment,
        factory,
        experiment_id="experimento-01",
    )

    assert report["experiment_id"] == "experimento-01"
    assert report["image_count"] == 2
    assert report["failed_count"] == 0
    assert report["total_records"] == 2

    implementations = {
        item["implementation"]
        for item in report["reconstructions"]
    }

    assert implementations == {"python", "cpp"}

    for item in report["reconstructions"]:
        assert item["image"]["vector"] == [1.0, 2.0, 3.0]
        assert item["image"]["shape"] == [1, 3]
        assert item["metadata"]["iterations"] == 2
        assert item["metadata"]["algorithm"] == "cgnr"
        assert item["metadata"]["started_at"]
        assert item["metadata"]["finished_at"]


def test_save_and_reload_report(experiment, tmp_path):
    report = generate_image_report(
        experiment,
        lambda _: (FakeClient("python"), FakeClient("cpp")),
        experiment_id="experimento-02",
    )

    path = tmp_path / "experimento-02" / "images.json"
    save_image_report(report, path)

    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved == report
    assert len(saved["reconstructions"]) == 2


def test_failed_reconstruction_is_preserved(experiment):
    report = generate_image_report(
        experiment,
        lambda _: (
            FakeClient("python"),
            FakeClient("cpp", failed=True),
        ),
    )

    assert report["image_count"] == 1
    assert report["failed_count"] == 1
    assert report["total_records"] == 2

    failure = next(
        entry for entry in report["reconstructions"]
        if entry["status"] == "failed"
    )

    assert failure["image"] is None
    assert failure["error"]["code"] == "NUMERICAL_BREAKDOWN"


def test_pending_reconstruction_is_preserved():
    class PendingClient:
        def get_status(self, request_id):
            return {
                "request_id": request_id,
                "status": "running",
                "client_id": "cliente-01",
                "signal_id": "sinal-001",
                "algorithm": "cgnr",
            }

    record = collect_reconstruction(
        PendingClient(), "req-01",
        max_polls=2,
        poll_interval=0,
    )

    assert record["status"] == "pending"
    assert record["image"] is None
    assert record["error"]["code"] == "POLL_LIMIT_REACHED"

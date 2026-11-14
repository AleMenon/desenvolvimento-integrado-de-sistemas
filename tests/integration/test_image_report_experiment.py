"""TASK-14: relatório completo de um experimento da TASK-11."""

import json
import threading
from uuid import uuid4

import numpy as np

from client.concurrent_experiment import run_concurrent_experiment
from client.image_report import generate_image_report, save_image_report
from client.signal_preparation import create_plan


def test_report_preserves_all_90_reconstructed_images(tmp_path):
    """Três clientes, 15 sinais cada, reconstruídos por dois servidores."""

    stored = {"python": {}, "cpp": {}}
    lock = threading.Lock()

    class FakeServerClient:
        def __init__(self, implementation):
            self.implementation = implementation

        def get_model(self, model_id):
            return {
                "model_id": model_id,
                "rows": 3,
                "columns": 3,
                "image_shape": [1, 3],
                "version": "1.0",
            }

        def submit_signal(
            self, client_id, signal_id, model_id, signal, **kwargs
        ):
            request_id = f"{self.implementation}-{uuid4()}"

            with lock:
                stored[self.implementation][request_id] = {
                    "client_id": client_id,
                    "signal_id": signal_id,
                    "model_id": model_id,
                    "signal": list(signal),
                }

            return request_id

        def get_status(self, request_id):
            record = stored[self.implementation][request_id]

            return {
                "request_id": request_id,
                "status": "completed",
                "client_id": record["client_id"],
                "signal_id": record["signal_id"],
                "algorithm": "cgnr",
                "started_at": "2026-01-01T10:00:00Z",
                "finished_at": "2026-01-01T10:00:01Z",
            }

        def get_result(self, request_id):
            record = stored[self.implementation][request_id]

            return {
                "request_id": request_id,
                "status": "completed",
                "result": {
                    "vector": record["signal"],
                    "shape": [1, 3],
                },
                "metadata": {
                    "client_id": record["client_id"],
                    "signal_id": record["signal_id"],
                    "model_id": record["model_id"],
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

    def factory(_client_id):
        return FakeServerClient("python"), FakeServerClient("cpp")

    files = []

    for index in range(3):
        path = tmp_path / f"signal-{index}.csv"
        np.savetxt(path, [index + 1.0, 2.0, 3.0], delimiter=",")
        files.append(path)

    plans = {
        f"cliente-{index:02d}": create_plan(
            {"demo": files},
            seed=100 + index,
            count=15,
        )
        for index in range(1, 4)
    }

    experiment = run_concurrent_experiment(
        plans,
        factory,
        seed=42,
        min_interval=0,
        max_interval=0,
    )

    assert experiment["client_count"] == 3
    assert experiment["total_signals"] == 45
    assert experiment["total_http_submissions"] == 90

    report = generate_image_report(
        experiment,
        factory,
        experiment_id="experimento-task-14",
        poll_interval=0,
    )

    assert report["experiment_id"] == "experimento-task-14"
    assert report["image_count"] == 90
    assert report["total_records"] == 90
    assert report["failed_count"] == 0
    assert report["pending_count"] == 0

    assert len(stored["python"]) == 45
    assert len(stored["cpp"]) == 45

    records = report["reconstructions"]

    assert len({
        (item["implementation"], item["request_id"])
        for item in records
    }) == 90

    assert {
        item["client_id"] for item in records
    } == set(plans)

    for item in records:
        original = stored[item["implementation"]][item["request_id"]]

        assert item["experiment_id"] == "experimento-task-14"
        assert item["client_id"] == original["client_id"]
        assert item["signal_id"] == original["signal_id"]
        assert item["model_id"] == original["model_id"]
        assert item["image"]["vector"] == original["signal"]
        assert item["image"]["shape"] == [1, 3]

        metadata = item["metadata"]
        assert metadata["algorithm"] == "cgnr"
        assert metadata["iterations"] == 2
        assert metadata["started_at"]
        assert metadata["finished_at"]

    destination = tmp_path / "reports" / "experiment.json"
    save_image_report(report, destination)

    reloaded = json.loads(destination.read_text(encoding="utf-8"))

    assert reloaded == report
    assert len(reloaded["reconstructions"]) == 90

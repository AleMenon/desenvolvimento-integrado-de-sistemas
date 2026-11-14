"""Testes da execução concorrente de clientes — TASK-11."""

import json
import threading

import numpy as np
import pytest

from client.concurrent_experiment import (
    run_concurrent_experiment,
    save_experiment_log,
)
from client.signal_preparation import create_plan


class FakeClient:
    def __init__(self, requests, lock, server_name):
        self.requests = requests
        self.lock = lock
        self.server_name = server_name

    def get_model(self, model_id):
        return {
            "model_id": model_id,
            "rows": 3,
            "columns": 3,
            "image_shape": [1, 3],
            "version": "1.0",
        }

    def submit_signal(
        self,
        client_id,
        signal_id,
        model_id,
        signal,
        **kwargs,
    ):
        record = {
            "client_id": client_id,
            "signal_id": signal_id,
            "model_id": model_id,
            "signal": list(signal),
            "parameters": kwargs,
        }

        with self.lock:
            self.requests[self.server_name].append(record)
            index = len(self.requests[self.server_name])

        return f"{self.server_name}-{index}"


@pytest.fixture
def plans(tmp_path):
    files = []

    for index in range(3):
        path = tmp_path / f"signal-{index}.csv"
        np.savetxt(
            path,
            [index + 1.0, 2.0, 3.0],
            delimiter=",",
        )
        files.append(path)

    return {
        f"cliente-{index:02d}": create_plan(
            {"demo": files},
            seed=100 + index,
            count=15,
        )
        for index in range(1, 4)
    }


@pytest.fixture
def fake_environment():
    requests = {
        "python": [],
        "cpp": [],
    }
    lock = threading.Lock()

    def factory(_client_id):
        return (
            FakeClient(requests, lock, "python"),
            FakeClient(requests, lock, "cpp"),
        )

    return factory, requests


def test_three_clients_send_45_signals(
    plans,
    fake_environment,
):
    factory, requests = fake_environment

    report = run_concurrent_experiment(
        plans,
        factory,
        seed=42,
        min_interval=0,
        max_interval=0,
    )

    assert report["client_count"] == 3
    assert report["total_signals"] == 45
    assert report["total_http_submissions"] == 90

    assert len(requests["python"]) == 45
    assert len(requests["cpp"]) == 45

    assert all(
        result["signal_count"] == 15
        for result in report["clients"].values()
    )

    for client_id in plans:
        python_records = [
            record
            for record in requests["python"]
            if record["client_id"] == client_id
        ]

        cpp_records = [
            record
            for record in requests["cpp"]
            if record["client_id"] == client_id
        ]

        assert len(python_records) == 15
        assert python_records == cpp_records
        assert len({
            record["signal_id"]
            for record in python_records
        }) == 15


def test_random_intervals_are_reproducible(
    plans,
    fake_environment,
):
    factory, _ = fake_environment

    first = run_concurrent_experiment(
        plans,
        factory,
        seed=123,
        min_interval=0.01,
        max_interval=0.05,
        sleep_fn=lambda _: None,
    )

    second = run_concurrent_experiment(
        plans,
        factory,
        seed=123,
        min_interval=0.01,
        max_interval=0.05,
        sleep_fn=lambda _: None,
    )

    for client_id in plans:
        first_delays = [
            record["delay_seconds"]
            for record in first["clients"][client_id][
                "submissions"
            ]
        ]

        second_delays = [
            record["delay_seconds"]
            for record in second["clients"][client_id][
                "submissions"
            ]
        ]

        assert first_delays == second_delays
        assert first_delays[0] == 0
        assert all(
            0.01 <= delay <= 0.05
            for delay in first_delays[1:]
        )


def test_reject_less_than_three_clients(
    plans,
    fake_environment,
):
    factory, _ = fake_environment

    with pytest.raises(ValueError, match="três clientes"):
        run_concurrent_experiment(
            dict(list(plans.items())[:2]),
            factory,
        )


def test_reject_less_than_15_signals(
    plans,
    fake_environment,
):
    factory, _ = fake_environment

    plans["cliente-01"]["sequence"] = (
        plans["cliente-01"]["sequence"][:14]
    )

    with pytest.raises(ValueError, match="15 sinais"):
        run_concurrent_experiment(
            plans,
            factory,
        )


def test_save_experiment_log(
    plans,
    fake_environment,
    tmp_path,
):
    factory, _ = fake_environment

    report = run_concurrent_experiment(
        plans,
        factory,
        min_interval=0,
        max_interval=0,
    )

    destination = tmp_path / "logs" / "experiment.json"

    save_experiment_log(report, destination)

    saved = json.loads(
        destination.read_text(encoding="utf-8")
    )

    assert saved["total_signals"] == 45
    assert saved["total_http_submissions"] == 90
    assert len(saved["clients"]) == 3


def test_signal_ids_unique_across_clients(
    plans,
    fake_environment,
):
    factory, requests = fake_environment

    report = run_concurrent_experiment(
        plans,
        factory,
        min_interval=0,
        max_interval=0,
    )

    python_ids = [
        record["signal_id"]
        for record in requests["python"]
    ]

    cpp_ids = [
        record["signal_id"]
        for record in requests["cpp"]
    ]

    assert len(python_ids) == 45
    assert len(set(python_ids)) == 45
    assert sorted(python_ids) == sorted(cpp_ids)

    for client_id, result in report["clients"].items():
        assert all(
            record["signal_id"].startswith(f"{client_id}:")
            for record in result["submissions"]
        )


def test_clients_really_run_concurrently(plans):
    """Os três clientes precisam alcançar a mesma barreira."""

    barrier = threading.Barrier(3, timeout=5)
    lock = threading.Lock()
    requests = {"python": [], "cpp": []}

    class SynchronizedClient(FakeClient):
        def get_model(self, model_id):
            if self.server_name == "python":
                barrier.wait()
            return super().get_model(model_id)

    def factory(_client_id):
        return (
            SynchronizedClient(requests, lock, "python"),
            SynchronizedClient(requests, lock, "cpp"),
        )

    report = run_concurrent_experiment(
        plans,
        factory,
        min_interval=0,
        max_interval=0,
    )

    assert report["total_signals"] == 45
    assert report["total_http_submissions"] == 90


def test_partial_failure_preserves_confirmed_requests(plans):
    lock = threading.Lock()
    requests = {"python": [], "cpp": []}

    class FailingClient(FakeClient):
        def submit_signal(
            self,
            client_id,
            signal_id,
            model_id,
            signal,
            **kwargs,
        ):
            if (
                client_id == "cliente-02"
                and self.server_name == "cpp"
                and signal_id.endswith("-002")
            ):
                raise ConnectionError("falha simulada no C++")

            return super().submit_signal(
                client_id,
                signal_id,
                model_id,
                signal,
                **kwargs,
            )

    def factory(_client_id):
        return (
            FakeClient(requests, lock, "python"),
            FailingClient(requests, lock, "cpp"),
        )

    from client.concurrent_experiment import ConcurrentExperimentError

    with pytest.raises(ConcurrentExperimentError) as captured:
        run_concurrent_experiment(
            plans,
            factory,
            min_interval=0,
            max_interval=0,
        )

    error = captured.value

    assert "cliente-02" in error.errors
    assert error.results["cliente-01"]["status"] == "completed"
    assert error.results["cliente-03"]["status"] == "completed"

    partial = error.results["cliente-02"]["submissions"]

    assert len(partial) == 3
    assert partial[0]["python_request_id"]
    assert partial[0]["cpp_request_id"]
    assert partial[1]["python_request_id"]
    assert partial[1]["cpp_request_id"]
    assert partial[2]["python_request_id"]
    assert partial[2]["cpp_request_id"] is None


def test_save_partial_experiment_after_failure(
    plans,
    tmp_path,
):
    from client.concurrent_experiment import (
        ConcurrentExperimentError,
    )

    lock = threading.Lock()
    requests = {"python": [], "cpp": []}

    class FailingClient(FakeClient):
        def submit_signal(
            self,
            client_id,
            signal_id,
            model_id,
            signal,
            **kwargs,
        ):
            if (
                client_id == "cliente-02"
                and self.server_name == "cpp"
                and signal_id.endswith("-002")
            ):
                raise ConnectionError("falha simulada")

            return super().submit_signal(
                client_id,
                signal_id,
                model_id,
                signal,
                **kwargs,
            )

    def factory(_client_id):
        return (
            FakeClient(requests, lock, "python"),
            FailingClient(requests, lock, "cpp"),
        )

    with pytest.raises(ConcurrentExperimentError) as captured:
        run_concurrent_experiment(
            plans,
            factory,
            min_interval=0,
            max_interval=0,
        )

    error = captured.value

    destination = tmp_path / "results" / "partial.json"

    save_experiment_log(error, destination)

    report = json.loads(
        destination.read_text(encoding="utf-8")
    )

    assert report["status"] == "failed"
    assert report["client_count"] == 3
    assert report["total_signals"] == 33
    assert report["total_http_submissions"] == 65
    assert "cliente-02" in report["errors"]

    assert report["clients"]["cliente-01"]["signal_count"] == 15
    assert report["clients"]["cliente-03"]["signal_count"] == 15

    partial = report["clients"]["cliente-02"]["submissions"]

    assert len(partial) == 3
    assert partial[0]["python_request_id"]
    assert partial[0]["cpp_request_id"]
    assert partial[1]["python_request_id"]
    assert partial[1]["cpp_request_id"]
    assert partial[2]["python_request_id"]
    assert partial[2]["cpp_request_id"] is None


def test_partial_failure_has_execution_metadata(plans):
    from client.concurrent_experiment import ConcurrentExperimentError

    lock = threading.Lock()
    requests = {"python": [], "cpp": []}

    class FailingClient(FakeClient):
        def submit_signal(
            self, client_id, signal_id, model_id, signal, **kwargs
        ):
            if (
                client_id == "cliente-02"
                and self.server_name == "cpp"
                and signal_id.endswith("-002")
            ):
                raise ConnectionError("falha simulada")

            return super().submit_signal(
                client_id, signal_id, model_id, signal, **kwargs
            )

    def factory(_client_id):
        return (
            FakeClient(requests, lock, "python"),
            FailingClient(requests, lock, "cpp"),
        )

    with pytest.raises(ConcurrentExperimentError) as captured:
        run_concurrent_experiment(
            plans, factory, min_interval=0, max_interval=0
        )

    failed = captured.value.report["clients"]["cliente-02"]

    assert failed["status"] == "failed"
    assert failed["started_at"].endswith("Z")
    assert failed["finished_at"].endswith("Z")
    assert failed["duration_seconds"] >= 0
    assert failed["signal_count"] == 3
    assert "ConnectionError" in captured.value.errors["cliente-02"]


def test_client_factory_failure_preserves_other_clients(plans):
    from client.concurrent_experiment import ConcurrentExperimentError

    lock = threading.Lock()
    requests = {"python": [], "cpp": []}

    def factory(client_id):
        if client_id == "cliente-02":
            raise RuntimeError("falha ao criar cliente")

        return (
            FakeClient(requests, lock, "python"),
            FakeClient(requests, lock, "cpp"),
        )

    with pytest.raises(ConcurrentExperimentError) as captured:
        run_concurrent_experiment(
            plans, factory, min_interval=0, max_interval=0
        )

    report = captured.value.report

    assert report["status"] == "failed"
    assert report["total_signals"] == 30
    assert report["total_http_submissions"] == 60
    assert report["clients"]["cliente-02"]["signal_count"] == 0
    assert report["clients"]["cliente-01"]["signal_count"] == 15
    assert report["clients"]["cliente-03"]["signal_count"] == 15
    assert "falha ao criar cliente" in report["errors"]["cliente-02"]

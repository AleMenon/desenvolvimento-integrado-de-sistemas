"""TASK-14: relatório com servidores HTTP Python e C++ reais."""

import json
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest
import requests

from client.concurrent_experiment import run_concurrent_experiment
from client.image_report import generate_image_report, save_image_report
from client.reconstruction_client import ReconstructionClient
from client.signal_preparation import create_plan


ROOT = Path(__file__).resolve().parents[2]
CPP_SERVER = ROOT / "build" / "reconstruction_server"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def running_process(command):
    """Inicia processo HTTP e encerra ao terminar o teste."""
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    command = [str(arg) for arg in command(port)]

    environment = os.environ.copy()
    environment["OPENBLAS_NUM_THREADS"] = "1"
    environment["OMP_NUM_THREADS"] = "1"

    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    try:
        deadline = time.monotonic() + 15

        while time.monotonic() < deadline:
            if process.poll() is not None:
                details = process.stderr.read().decode(
                    errors="replace"
                )
                raise RuntimeError(
                    f"Servidor encerrou antes de iniciar: {details}"
                )

            try:
                response = requests.get(
                    f"{url}/health", timeout=0.3
                )
                if response.status_code == 200:
                    break
            except requests.RequestException:
                pass

            time.sleep(0.05)
        else:
            raise RuntimeError(
                f"Servidor não iniciou: {command}"
            )

        yield url

    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        process.stderr.close()


@pytest.fixture(scope="module")
def real_servers():
    if not CPP_SERVER.is_file():
        pytest.fail(
            "Compile build/reconstruction_server antes deste teste."
        )

    with running_process(
        lambda port: [
            sys.executable,
            "-m",
            "uvicorn",
            "server.python.reconstruction_server:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "error",
        ]
    ) as python_url:

        with running_process(
            lambda port: [
                CPP_SERVER,
                "--host", "127.0.0.1",
                "--port", str(port),
                "--catalog", ROOT / "models" / "catalog.json",
            ]
        ) as cpp_url:

            yield python_url, cpp_url


def test_report_with_90_real_http_reconstructions(
    real_servers, tmp_path
):
    python_url, cpp_url = real_servers

    def factory(_client_id):
        return (
            ReconstructionClient(python_url, timeout=10),
            ReconstructionClient(cpp_url, timeout=10),
        )

    signal_files = []

    for index in range(3):
        path = tmp_path / f"signal-{index}.csv"

        np.savetxt(
            path,
            [index + 1.0, 2.0, 3.0],
            delimiter=",",
        )

        signal_files.append(path)

    plans = {
        f"cliente-{index:02d}": create_plan(
            {"demo_identity_3": signal_files},
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
        experiment_id="task-14-real-http",
        max_polls=200,
        poll_interval=0.02,
    )

    assert report["image_count"] == 90
    assert report["total_records"] == 90
    assert report["failed_count"] == 0
    assert report["pending_count"] == 0

    records = report["reconstructions"]

    assert len(records) == 90

    assert sum(
        item["implementation"] == "python"
        for item in records
    ) == 45

    assert sum(
        item["implementation"] == "cpp"
        for item in records
    ) == 45

    assert len({
        (item["implementation"], item["request_id"])
        for item in records
    }) == 90

    for item in records:
        assert item["status"] == "completed"
        assert item["experiment_id"] == "task-14-real-http"

        image = item["image"]
        metadata = item["metadata"]

        assert image["shape"] == [1, 3]
        assert len(image["vector"]) == 3
        assert np.isfinite(image["vector"]).all()

        assert metadata["client_id"] == item["client_id"]
        assert metadata["signal_id"] == item["signal_id"]
        assert metadata["model_id"] == item["model_id"]
        assert metadata["algorithm"] == "cgnr"

        assert isinstance(metadata["iterations"], int)
        assert 0 <= metadata["iterations"] <= 10

        assert metadata["started_at"]
        assert metadata["finished_at"]
        assert metadata["execution_time_ms"] >= 0

    destination = (
        tmp_path / "reports" / "task-14-real-http.json"
    )

    save_image_report(report, destination)

    restored = json.loads(
        destination.read_text(encoding="utf-8")
    )

    assert restored == report
    assert len(restored["reconstructions"]) == 90

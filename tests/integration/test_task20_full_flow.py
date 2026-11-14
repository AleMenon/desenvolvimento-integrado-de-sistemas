"""TASK-20: integração completa com servidores Python e C++ reais."""

import json
import os
import socket
import subprocess
import sys
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
import requests

from client.concurrent_experiment import (
    run_concurrent_experiment,
    save_experiment_log,
)
from client.image_report import generate_image_report, save_image_report
from client.reconstruction_client import ReconstructionClient
from client.signal_preparation import create_plan, prepare_entry


ROOT = Path(__file__).resolve().parents[2]
CPP_SERVER = ROOT / "build" / "reconstruction_server"

CLIENT_COUNT = 3
SIGNALS_PER_CLIENT = 15
SIGNAL_COUNT = CLIENT_COUNT * SIGNALS_PER_CLIENT
EXPECTED_IMAGES = SIGNAL_COUNT * 2

SOURCE_VECTORS = (
    np.array([1.0, 2.0, 3.0]),
    np.array([2.0, 2.0, 3.0]),
    np.array([3.0, 2.0, 3.0]),
)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def utc_timestamp(value):
    assert isinstance(value, str) and value
    timestamp = datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )
    assert timestamp.tzinfo is not None
    return timestamp


@contextmanager
def running_server(command, environment=None):
    """Inicia um servidor HTTP real e encerra o processo após o teste."""

    port = free_port()
    url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"

    if environment:
        env.update(environment)

    process = subprocess.Popen(
        [str(arg) for arg in command(port)],
        cwd=ROOT,
        env=env,
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
                pytest.fail(
                    f"Servidor encerrou antes de iniciar: {details}"
                )

            try:
                response = requests.get(
                    f"{url}/health",
                    timeout=0.4,
                )
                if response.status_code == 200:
                    break
            except requests.RequestException:
                pass

            time.sleep(0.05)
        else:
            pytest.fail(f"Servidor não iniciou: {url}")

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


@pytest.fixture
def real_servers():
    """Inicializa servidores com filas e retenção suficientes."""

    if not CPP_SERVER.is_file():
        pytest.fail(
            "Compile build/reconstruction_server antes do teste."
        )

    python_environment = {
        "RECONSTRUCTION_WORKERS": "2",
        "RECONSTRUCTION_QUEUE_CAPACITY": "64",
        "RECONSTRUCTION_MAX_RESULTS": "128",
        "RECONSTRUCTION_RESULT_TTL_SECONDS": "3600",
    }

    with running_server(
        lambda port: [
            sys.executable,
            "-m",
            "uvicorn",
            "server.python.reconstruction_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        environment=python_environment,
    ) as python_url:

        with running_server(
            lambda port: [
                CPP_SERVER,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--catalog",
                ROOT / "models" / "catalog.json",
                "--workers",
                "2",
                "--queue-capacity",
                "64",
                "--max-retained-results",
                "128",
                "--result-ttl-seconds",
                "3600",
            ],
        ) as cpp_url:

            yield {
                "python": python_url,
                "cpp": cpp_url,
            }


def test_task20_complete_integration(real_servers, tmp_path):
    """Valida 3 clientes, 45 sinais e 90 reconstruções reais."""

    def client_factory(_client_id):
        return (
            ReconstructionClient(real_servers["python"], timeout=10),
            ReconstructionClient(real_servers["cpp"], timeout=10),
        )

    # Preparação de sinais — TASK-10.
    signal_files = []

    for index, vector in enumerate(SOURCE_VECTORS):
        filename = tmp_path / f"signal-{index}.csv"

        np.savetxt(
            filename,
            vector,
            delimiter=",",
        )

        signal_files.append(filename)

    plans = {
        f"cliente-{index:02d}": create_plan(
            {"demo_identity_3": signal_files},
            seed=100 + index,
            count=SIGNALS_PER_CLIENT,
        )
        for index in range(1, CLIENT_COUNT + 1)
    }

    # Execução simultânea — TASK-11.
    experiment = run_concurrent_experiment(
        plans,
        client_factory,
        seed=42,
        min_interval=0,
        max_interval=0,
        max_iterations=10,
        tolerance=1e-8,
    )

    assert experiment["schema_version"] == 1
    assert experiment["status"] == "completed"
    assert experiment["errors"] == {}

    assert experiment["client_count"] == CLIENT_COUNT
    assert experiment["total_signals"] == SIGNAL_COUNT
    assert experiment["total_http_submissions"] == EXPECTED_IMAGES

    assert set(experiment["clients"]) == set(plans)

    expected_pairs = set()
    submitted_ids = {
        "python": set(),
        "cpp": set(),
    }

    # Verificação de clientes, sinais e solicitações.
    for client_id, client_data in experiment["clients"].items():
        assert client_data["client_id"] == client_id
        assert client_data["status"] == "completed"
        assert client_data["signal_count"] == SIGNALS_PER_CLIENT

        submissions = client_data["submissions"]

        assert len(submissions) == SIGNALS_PER_CLIENT
        assert {
            item["position"] for item in submissions
        } == set(range(SIGNALS_PER_CLIENT))

        for submission in submissions:
            signal_id = submission["signal_id"]

            assert isinstance(signal_id, str)
            assert signal_id.startswith(f"{client_id}:")
            assert submission["model_id"] == "demo_identity_3"

            pair = (client_id, signal_id)

            assert pair not in expected_pairs
            expected_pairs.add(pair)

            for implementation in ("python", "cpp"):
                request_id = submission[
                    f"{implementation}_request_id"
                ]

                assert isinstance(request_id, str)
                assert request_id

                assert request_id not in submitted_ids[
                    implementation
                ]

                submitted_ids[implementation].add(request_id)

    assert len(expected_pairs) == SIGNAL_COUNT

    for implementation in ("python", "cpp"):
        assert len(submitted_ids[implementation]) == SIGNAL_COUNT

    # Recuperação das imagens — TASK-14.
    report = generate_image_report(
        experiment,
        client_factory,
        experiment_id="task-20-complete-integration",
        max_polls=300,
        poll_interval=0.02,
    )

    assert report["schema_version"] == 1
    assert report["experiment_id"] == "task-20-complete-integration"
    assert report["experiment_status"] == "completed"

    assert report["image_count"] == EXPECTED_IMAGES
    assert report["total_records"] == EXPECTED_IMAGES
    assert report["failed_count"] == 0
    assert report["pending_count"] == 0

    records = report["reconstructions"]

    assert len(records) == EXPECTED_IMAGES

    by_signal = defaultdict(dict)
    implementation_counts = Counter()

    # Integridade de cada resultado recebido.
    for record in records:
        implementation = record["implementation"]
        client_id = record["client_id"]
        signal_id = record["signal_id"]
        request_id = record["request_id"]

        assert implementation in ("python", "cpp")
        assert record["status"] == "completed"
        assert record["model_id"] == "demo_identity_3"

        assert (client_id, signal_id) in expected_pairs
        assert request_id in submitted_ids[implementation]

        assert record["experiment_id"] == (
            "task-20-complete-integration"
        )

        metadata = record["metadata"]

        assert metadata["client_id"] == client_id
        assert metadata["signal_id"] == signal_id
        assert metadata["model_id"] == "demo_identity_3"
        assert metadata["algorithm"] == "cgnr"

        assert type(metadata["iterations"]) is int
        assert 0 <= metadata["iterations"] <= 10

        started = utc_timestamp(metadata["started_at"])
        finished = utc_timestamp(metadata["finished_at"])

        assert finished >= started
        assert metadata["execution_time_ms"] >= 0

        image = record["image"]

        assert image["shape"] == [1, 3]

        reconstructed = np.asarray(
            image["vector"],
            dtype=float,
        )

        assert reconstructed.shape == (3,)
        assert np.isfinite(reconstructed).all()

        # A TASK-10 aplica ganho antes de enviar o sinal.
        # O modelo identidade deve reconstruir o vetor preparado,
        # não os valores originais do arquivo CSV.
        position = record["position"]
        entry = plans[client_id]["sequence"][position]

        expected_signal_id = (
            f"{client_id}:{entry['signal_id']}-{position:03d}"
        )

        assert signal_id == expected_signal_id
        assert record["model_id"] == entry["model_id"]

        expected_vector = prepare_entry(entry)

        np.testing.assert_allclose(
            reconstructed,
            expected_vector,
            rtol=1e-5,
            atol=1e-5,
            err_msg=(
                f"Imagem incorreta para "
                f"{implementation}/{client_id}/{signal_id}"
            ),
        )

        pair = (client_id, signal_id)

        assert implementation not in by_signal[pair]

        by_signal[pair][implementation] = reconstructed
        implementation_counts[implementation] += 1

    assert implementation_counts == {
        "python": SIGNAL_COUNT,
        "cpp": SIGNAL_COUNT,
    }

    assert set(by_signal) == expected_pairs

    # Python e C++ devem retornar a mesma reconstrução
    # para cada identificação de sinal.
    for pair, images in by_signal.items():
        assert set(images) == {"python", "cpp"}

        np.testing.assert_allclose(
            images["python"],
            images["cpp"],
            rtol=1e-5,
            atol=1e-5,
            err_msg=f"Resultados divergentes para {pair}",
        )

    # Controle de filas — TASK-15.
    # Contadores de desempenho — TASK-16.
    for implementation, url in real_servers.items():
        queue_response = requests.get(
            f"{url}/queue",
            timeout=5,
        )
        queue_response.raise_for_status()

        queue_state = queue_response.json()

        assert queue_state["implementation"] == implementation
        assert queue_state["queue_policy"] == "fifo"

        assert queue_state["worker_count"] == 2
        assert queue_state["queue_capacity"] == 64

        assert queue_state["accepted_count"] == SIGNAL_COUNT
        assert queue_state["completed_count"] == SIGNAL_COUNT

        assert queue_state["failed_count"] == 0
        assert queue_state["rejected_count"] == 0

        assert queue_state["queue_size"] == 0
        assert queue_state["running_count"] == 0

        assert queue_state["evicted_count"] == 0
        assert queue_state["retained_results"] == SIGNAL_COUNT

        metrics_response = requests.get(
            f"{url}/metrics",
            timeout=5,
        )
        metrics_response.raise_for_status()

        metrics = metrics_response.json()

        assert metrics["implementation"] == implementation
        assert metrics["received_count"] == SIGNAL_COUNT
        assert metrics["completed_count"] == SIGNAL_COUNT
        assert metrics["failed_count"] == 0

        history_response = requests.get(
            f"{url}/metrics/reconstructions",
            timeout=5,
        )
        history_response.raise_for_status()

        history = history_response.json()

        assert history["implementation"] == implementation
        assert len(history["reconstructions"]) == SIGNAL_COUNT

    # Persistência e integridade dos relatórios.
    reports_dir = tmp_path / "reports"

    execution_path = reports_dir / "execution.json"
    images_path = reports_dir / "images.json"

    save_experiment_log(
        experiment,
        execution_path,
    )

    save_image_report(
        report,
        images_path,
    )

    assert execution_path.is_file()
    assert images_path.is_file()

    saved_execution = json.loads(
        execution_path.read_text(encoding="utf-8")
    )

    saved_images = json.loads(
        images_path.read_text(encoding="utf-8")
    )

    assert saved_execution == experiment
    assert saved_images == report

    assert saved_execution["client_count"] == 3
    assert saved_execution["total_signals"] == 45
    assert saved_execution["total_http_submissions"] == 90

    assert saved_images["image_count"] == 90
    assert saved_images["total_records"] == 90

    assert len(saved_images["reconstructions"]) == 90

    print(
        "\nTASK-20 VALIDADA:"
        "\n3 clientes simultâneos"
        "\n45 sinais enviados a cada implementação"
        "\n90 reconstruções reais recuperadas"
        "\n90 imagens válidas"
        "\n2 relatórios persistidos e conferidos"
        "\nFilas e métricas verificadas"
    )

"""Integração HTTP do servidor Python real da TASK-12."""

import threading
import time

import numpy as np
import pytest
import requests
import uvicorn

from client.reconstruction_client import (
    CommunicationError,
    ReconstructionClient,
)
from server.python.reconstruction_server import create_app


@pytest.fixture(scope="module")
def server_url():
    """Inicia um servidor Uvicorn real em uma porta livre."""

    app = create_app("models/catalog.json")

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=0,
        log_level="error",
        access_log=False,
        lifespan="on",
    )

    server = uvicorn.Server(config)

    thread = threading.Thread(
        target=server.run,
        name="task12-http-test-server",
        daemon=True,
    )

    thread.start()

    try:
        deadline = time.monotonic() + 10

        while not server.started:
            if not thread.is_alive():
                raise RuntimeError(
                    "O servidor Uvicorn encerrou antes de iniciar."
                )

            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Tempo esgotado ao iniciar o Uvicorn."
                )

            time.sleep(0.01)

        sockets = [
            sock
            for instance in server.servers
            for sock in instance.sockets
        ]

        assert sockets, "O servidor não abriu uma porta HTTP."

        port = sockets[0].getsockname()[1]

        yield f"http://127.0.0.1:{port}"

    finally:
        server.should_exit = True
        thread.join(timeout=10)

        if thread.is_alive():
            raise RuntimeError(
                "O servidor HTTP não encerrou corretamente."
            )


@pytest.fixture
def client(server_url):
    return ReconstructionClient(
        server_url,
        timeout=5.0,
    )


def test_health(client):
    response = client.health()

    assert response["status"] == "ok"


def test_list_models(client):
    response = client.list_models()

    assert isinstance(response["models"], list)

    model = next(
        model
        for model in response["models"]
        if model["model_id"] == "demo_identity_3"
    )

    assert model["rows"] == 3
    assert model["columns"] == 3
    assert model["image_shape"] == [1, 3]
    assert model["data_type"] == "float64"


def test_get_model(client):
    model = client.get_model("demo_identity_3")

    assert model["model_id"] == "demo_identity_3"
    assert model["rows"] == 3
    assert model["columns"] == 3
    assert len(model["checksum_sha256"]) == 64


def test_reconstruct_identity_matrix(client):
    """CGNR deve reconstruir exatamente um sistema identidade."""

    signal = np.array(
        [2.0, -3.0, 5.0],
        dtype=np.float64,
    )

    response = client.reconstruct(
        client_id="cliente-task12",
        signal_id="sinal-identidade",
        model_id="demo_identity_3",
        signal=signal,
        max_iterations=10,
        tolerance=1e-8,
        poll_interval=0.01,
        max_polls=100,
    )

    assert response["status"] == "completed"

    result = response["result"]
    metadata = response["metadata"]

    np.testing.assert_allclose(
        result["vector"],
        signal,
        rtol=1e-10,
        atol=1e-10,
    )

    assert result["shape"] == [1, 3]
    assert metadata["implementation"] == "python"
    assert metadata["algorithm"] == "cgnr"
    assert metadata["client_id"] == "cliente-task12"
    assert metadata["signal_id"] == "sinal-identidade"
    assert metadata["model_id"] == "demo_identity_3"
    assert metadata["converged"] is True
    assert metadata["iterations"] >= 1
    assert metadata["residual_norm"] < 1e-8
    assert metadata["execution_time_ms"] >= 0
    assert metadata["parameters"] == {
        "max_iterations": 10,
        "tolerance": 1e-8,
    }


def test_submit_status_and_result(client):
    request_id = client.submit_signal(
        "cliente-02",
        "sinal-02",
        "demo_identity_3",
        [1.0, 2.0, 3.0],
    )

    assert isinstance(request_id, str)
    assert request_id

    deadline = time.monotonic() + 5

    while True:
        status = client.get_status(request_id)

        assert status["request_id"] == request_id
        assert status["status"] in {
            "queued",
            "running",
            "completed",
            "failed",
        }

        if status["status"] == "completed":
            break

        assert status["status"] != "failed"

        if time.monotonic() >= deadline:
            pytest.fail("Reconstrução não terminou em 5 segundos.")

        time.sleep(0.01)

    response = client.get_result(request_id)

    assert response["request_id"] == request_id

    np.testing.assert_allclose(
        response["result"]["vector"],
        [1.0, 2.0, 3.0],
        atol=1e-10,
    )


def test_multiple_requests(client):
    request_ids = []

    for index in range(5):
        request_id = client.submit_signal(
            client_id="cliente-multiplo",
            signal_id=f"sinal-{index}",
            model_id="demo_identity_3",
            signal=[float(index), 2.0, 3.0],
        )

        request_ids.append(request_id)

    assert len(set(request_ids)) == 5

    for index, request_id in enumerate(request_ids):
        deadline = time.monotonic() + 5

        while True:
            status = client.get_status(request_id)

            if status["status"] == "completed":
                break

            assert status["status"] != "failed"

            if time.monotonic() >= deadline:
                pytest.fail(
                    f"Reconstrução {index} não terminou."
                )

            time.sleep(0.01)

        result = client.get_result(request_id)

        np.testing.assert_allclose(
            result["result"]["vector"],
            [float(index), 2.0, 3.0],
            atol=1e-10,
        )

        assert result["metadata"]["signal_id"] == (
            f"sinal-{index}"
        )


def test_unknown_model(client):
    with pytest.raises(
        CommunicationError,
        match="404",
    ):
        client.get_model("modelo-inexistente")


def test_unknown_reconstruction(client):
    with pytest.raises(
        CommunicationError,
        match="404",
    ):
        client.get_status("id-inexistente")


def test_invalid_signal_dimension(server_url):
    response = requests.post(
        f"{server_url}/reconstructions",
        json={
            "client_id": "cliente",
            "signal_id": "sinal-invalido",
            "model_id": "demo_identity_3",
            "algorithm": "cgnr",
            "signal": [1.0, 2.0],
            "parameters": {
                "max_iterations": 10,
                "tolerance": 1e-8,
            },
        },
        timeout=5,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == (
        "INVALID_SIGNAL_DIMENSION"
    )


def test_invalid_algorithm(server_url):
    response = requests.post(
        f"{server_url}/reconstructions",
        json={
            "client_id": "cliente",
            "signal_id": "sinal-invalido",
            "model_id": "demo_identity_3",
            "algorithm": "outro",
            "signal": [1.0, 2.0, 3.0],
            "parameters": {
                "max_iterations": 10,
                "tolerance": 1e-8,
            },
        },
        timeout=5,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == (
        "INVALID_ALGORITHM"
    )


def test_missing_fields(server_url):
    response = requests.post(
        f"{server_url}/reconstructions",
        json={"model_id": "demo_identity_3"},
        timeout=5,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == (
        "MISSING_FIELDS"
    )


def test_invalid_json(server_url):
    response = requests.post(
        f"{server_url}/reconstructions",
        data="{json quebrado",
        headers={"Content-Type": "application/json"},
        timeout=5,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == (
        "INVALID_JSON"
    )


def test_unsupported_content_type(server_url):
    response = requests.post(
        f"{server_url}/reconstructions",
        data="texto",
        headers={"Content-Type": "text/plain"},
        timeout=5,
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == (
        "UNSUPPORTED_MEDIA_TYPE"
    )


def test_missing_result(server_url):
    response = requests.get(
        f"{server_url}/reconstructions/id-inexistente/result",
        timeout=5,
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == (
        "REQUEST_NOT_FOUND"
    )

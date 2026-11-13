"""Integração real do cliente da TASK-09 com o servidor C++ da TASK-13.

Executar após compilar: uv run python -m pytest tests/integration/test_cpp_server.py -v
"""

import os
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest
import requests

from client.reconstruction_client import CommunicationError, ReconstructionClient
from server.python.cgnr import cgnr


ROOT = Path(__file__).resolve().parents[2]
EXECUTABLE = Path(os.getenv("CPP_SERVER_BIN", str(ROOT / "build" / "reconstruction_server")))
CATALOG = ROOT / "models" / "catalog.json"


@pytest.fixture(scope="module")
def server_url():
    assert EXECUTABLE.exists(), f"Compile o servidor primeiro: {EXECUTABLE}"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [str(EXECUTABLE), "--host", "127.0.0.1", "--port", str(port),
         "--catalog", str(CATALOG)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(f"Servidor encerrou: {process.stderr.read().decode()}")
            try:
                if requests.get(url + "/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.05)
        else:
            raise AssertionError("Servidor não iniciou dentro do prazo")
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stderr.close()


def test_health_and_models(server_url):
    client = ReconstructionClient(server_url)
    assert client.health() == {"status": "ok"}
    models = client.list_models()["models"]
    assert len(models) == 1
    model = client.get_model("demo_identity_3")
    assert model["rows"] == model["columns"] == 3
    assert model["image_shape"] == [1, 3]
    assert model["data_type"] == "float64"


def test_reconstruction_matches_python(server_url):
    client = ReconstructionClient(server_url)
    signal = [1.25, -2.5, 3.75]
    response = client.reconstruct(
        "cliente-01", "sinal-01", "demo_identity_3", signal,
        poll_interval=0.01, max_polls=100,
    )
    expected = cgnr(np.eye(3), np.array(signal))
    assert response["status"] == "completed"
    assert response["result"]["shape"] == [1, 3]
    np.testing.assert_allclose(response["result"]["vector"], expected["solution"], rtol=1e-10, atol=1e-10)
    metadata = response["metadata"]
    assert metadata["client_id"] == "cliente-01"
    assert metadata["signal_id"] == "sinal-01"
    assert metadata["implementation"] == "cpp"
    assert metadata["algorithm"] == "cgnr"
    assert metadata["iterations"] == expected["iterations"]
    assert metadata["converged"] is True
    assert metadata["stop_reason"] == "tolerance_reached"
    assert metadata["execution_time_ms"] >= 0
    assert metadata["parameters"] == {"max_iterations": 10, "tolerance": 1e-8}
    for key in ("created_at", "started_at", "finished_at"):
        assert isinstance(metadata[key], str) and metadata[key].endswith("Z")
    assert response["request_id"]


def test_three_clients_can_submit_same_model(server_url):
    def reconstruct(index):
        return ReconstructionClient(server_url).reconstruct(
            f"client-{index}", f"signal-{index}", "demo_identity_3",
            [float(index), 1.0, -1.0], poll_interval=0.01, max_polls=100,
        )

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(reconstruct, range(3)))
    assert len({job["request_id"] for job in results}) == 3
    assert all(job["metadata"]["implementation"] == "cpp" for job in results)


@pytest.mark.parametrize("payload,status,code", [
    ({}, 422, "MISSING_FIELDS"),
    ({"client_id": "", "signal_id": "s", "model_id": "demo_identity_3"}, 422, "MISSING_FIELDS"),
    ({"client_id": "a", "signal_id": "b", "model_id": "unknown", "algorithm": "cgnr", "signal": [1, 2, 3], "parameters": {"max_iterations": 10, "tolerance": 1e-8}}, 404, "MODEL_NOT_FOUND"),
    ({"client_id": "a", "signal_id": "b", "model_id": "demo_identity_3", "algorithm": "cgne", "signal": [1, 2, 3], "parameters": {"max_iterations": 10, "tolerance": 1e-8}}, 400, "INVALID_ALGORITHM"),
    ({"client_id": "a", "signal_id": "b", "model_id": "demo_identity_3", "algorithm": "cgnr", "signal": [1, 2], "parameters": {"max_iterations": 10, "tolerance": 1e-8}}, 400, "INVALID_SIGNAL_DIMENSION"),
    ({"client_id": "a", "signal_id": "b", "model_id": "demo_identity_3", "algorithm": "cgnr", "signal": [1, True, 3], "parameters": {"max_iterations": 10, "tolerance": 1e-8}}, 400, "INVALID_SIGNAL_DIMENSION"),
    ({"client_id": "a", "signal_id": "b", "model_id": "demo_identity_3", "algorithm": "cgnr", "signal": [1, 2, 3], "parameters": {"max_iterations": 11, "tolerance": 1e-8}}, 400, "INVALID_PARAMETERS"),
    ({"client_id": "a", "signal_id": "b", "model_id": "demo_identity_3", "algorithm": "cgnr", "signal": [1, 2, 3], "parameters": {"max_iterations": True, "tolerance": 1e-8}}, 400, "INVALID_PARAMETERS"),
    ({"client_id": "a", "signal_id": "b", "model_id": "demo_identity_3", "algorithm": "cgnr", "signal": [1, 2, 3], "parameters": {"max_iterations": 10, "tolerance": 0}}, 400, "INVALID_PARAMETERS"),
])
def test_invalid_requests(server_url, payload, status, code):
    response = requests.post(server_url + "/reconstructions", json=payload, timeout=3)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_invalid_json_and_missing_resource(server_url):
    malformed = requests.post(
        server_url + "/reconstructions", data="{", headers={"Content-Type": "application/json"}, timeout=3
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "INVALID_JSON"
    unsupported = requests.post(server_url + "/reconstructions", data="hello", timeout=3)
    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert requests.get(server_url + "/models/unknown", timeout=3).status_code == 404
    assert requests.get(server_url + "/reconstructions/unknown", timeout=3).status_code == 404
    with pytest.raises(CommunicationError, match="404"):
        ReconstructionClient(server_url).get_result("unknown")

"""Testes HTTP ponta a ponta com um servidor de teste (não CGNR real)."""

import threading
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
import requests

from client.reconstruction_client import CommunicationError, ReconstructionClient
from scripts.mock_reconstruction_server import Handler


@pytest.fixture(scope="module")
def server_url():
    with Handler.lock:
        Handler.jobs = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_health(server_url):
    assert ReconstructionClient(server_url).health()["status"] == "ok"


def test_model_catalog(server_url):
    client = ReconstructionClient(server_url)
    assert client.list_models()["models"][0]["model_id"] == "mock_3"
    assert client.get_model("mock_3")["rows"] == 3


def test_send_receive_and_ids(server_url):
    client = ReconstructionClient(server_url)
    output = client.reconstruct(
        "cliente-01", "sinal-02", "mock_3", np.array([1., 2., -3.]), poll_interval=0,
    )
    assert output["metadata"]["client_id"] == "cliente-01"
    assert output["metadata"]["signal_id"] == "sinal-02"
    assert output["metadata"]["model_id"] == "mock_3"
    assert output["metadata"]["implementation"] == "mock"
    assert output["metadata"]["parameters"] == {"max_iterations": 10, "tolerance": 1e-8}
    assert output["result"] == {"vector": [1., 2., -3.], "shape": [1, 3]}
    assert output["request_id"]


def test_separate_requests(server_url):
    client = ReconstructionClient(server_url)
    first = client.submit_signal("a", "1", "mock_3", [1, 0, 0])
    second = client.submit_signal("a", "2", "mock_3", [2, 0, 0])
    assert first != second
    assert client.get_result(first)["metadata"]["signal_id"] == "1"
    assert client.get_result(second)["metadata"]["signal_id"] == "2"


@pytest.mark.parametrize("signal", [[], [float("nan")], [float("inf")], ["a"], [[1, 2]]])
def test_invalid_signals(server_url, signal):
    with pytest.raises(ValueError):
        ReconstructionClient(server_url).submit_signal("a", "s", "mock_3", signal)


@pytest.mark.parametrize("params", [
    {"max_iterations": 11}, {"max_iterations": 0}, {"max_iterations": True},
    {"tolerance": 0}, {"tolerance": float("nan")},
])
def test_invalid_parameters(server_url, params):
    with pytest.raises(ValueError):
        ReconstructionClient(server_url).submit_signal("a", "s", "mock_3", [1, 2, 3], **params)


def test_missing_request(server_url):
    with pytest.raises(CommunicationError, match="404"):
        ReconstructionClient(server_url).get_result("nao-existe")


def test_unknown_model(server_url):
    with pytest.raises(CommunicationError, match="404"):
        ReconstructionClient(server_url).submit_signal("a", "s", "inexistente", [1, 2, 3])


def test_signal_dimension(server_url):
    with pytest.raises(CommunicationError, match="400"):
        ReconstructionClient(server_url).submit_signal("a", "s", "mock_3", [1, 2])


def test_connection_error():
    class BrokenSession:
        def request(self, *args, **kwargs):
            raise requests.ConnectionError("Conexão recusada")

    with pytest.raises(CommunicationError, match="Falha na comunicação"):
        ReconstructionClient("http://127.0.0.1:1", session=BrokenSession()).health()


def test_timeout_error():
    class BrokenSession:
        def request(self, *args, **kwargs):
            raise requests.Timeout("tempo esgotado")

    with pytest.raises(CommunicationError, match="Tempo limite"):
        ReconstructionClient("http://127.0.0.1:1", session=BrokenSession()).health()


def test_unexpected_http_status():
    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"request_id": "req", "status": "queued"}

    class FakeSession:
        def request(self, *args, **kwargs):
            return FakeResponse()

    with pytest.raises(CommunicationError, match="Status HTTP inesperado"):
        ReconstructionClient("http://127.0.0.1:1", session=FakeSession()).submit_signal(
            "a", "s", "mock_3", [1, 2, 3]
        )


def test_invalid_result_contract():
    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"request_id": "req", "status": "completed", "reconstruction": [1, 2, 3]}

    class FakeSession:
        def request(self, *args, **kwargs):
            return FakeResponse()

    with pytest.raises(CommunicationError, match="contrato JSON"):
        ReconstructionClient("http://127.0.0.1:1", session=FakeSession()).get_result("req")

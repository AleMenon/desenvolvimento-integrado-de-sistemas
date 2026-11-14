"""Três clientes concorrentes utilizando HTTP real e servidores mock."""

from contextlib import contextmanager
from threading import Thread

import numpy as np

from client.concurrent_experiment import run_concurrent_experiment
from client.reconstruction_client import ReconstructionClient
from client.signal_preparation import create_plan
from scripts.mock_reconstruction_server import (
    Handler,
    ThreadingHTTPServer,
)


@contextmanager
def mock_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_three_clients_send_90_http_requests(tmp_path):
    files = []

    for index in range(3):
        path = tmp_path / f"signal-{index}.csv"
        np.savetxt(
            path,
            [float(index + 1), 2.0, 3.0],
            delimiter=",",
        )
        files.append(path)

    plans = {
        f"cliente-{index:02d}": create_plan(
            {"mock_3": files},
            seed=100 + index,
            count=15,
            target_rms=2.0,
        )
        for index in range(1, 4)
    }

    with mock_server() as python_url, mock_server() as cpp_url:

        def factory(_client_id):
            return (
                ReconstructionClient(python_url),
                ReconstructionClient(cpp_url),
            )

        report = run_concurrent_experiment(
            plans,
            factory,
            seed=42,
            min_interval=0.001,
            max_interval=0.003,
        )

        assert report["client_count"] == 3
        assert report["total_signals"] == 45
        assert report["total_http_submissions"] == 90

        python_client = ReconstructionClient(python_url)
        cpp_client = ReconstructionClient(cpp_url)

        all_signal_ids = set()

        for client_id, result in report["clients"].items():
            assert result["status"] == "completed"
            assert result["signal_count"] == 15

            for record in result["submissions"]:
                signal_id = record["signal_id"]

                assert signal_id.startswith(f"{client_id}:")
                assert signal_id not in all_signal_ids

                all_signal_ids.add(signal_id)

                python_result = python_client.get_result(
                    record["python_request_id"]
                )

                cpp_result = cpp_client.get_result(
                    record["cpp_request_id"]
                )

                assert (
                    python_result["metadata"]["client_id"]
                    == client_id
                )

                assert (
                    cpp_result["metadata"]["client_id"]
                    == client_id
                )

                assert (
                    python_result["metadata"]["signal_id"]
                    == signal_id
                )

                assert (
                    cpp_result["metadata"]["signal_id"]
                    == signal_id
                )

                np.testing.assert_array_equal(
                    python_result["result"]["vector"],
                    cpp_result["result"]["vector"],
                )

        assert len(all_signal_ids) == 45

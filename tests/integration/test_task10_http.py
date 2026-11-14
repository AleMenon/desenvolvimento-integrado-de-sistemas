"""integração http da task-10 com o cliente real da task-09."""

from contextlib import contextmanager
from threading import Thread

import numpy as np
import pytest

from client.experiment_runner import submit_plan_to_servers
from client.reconstruction_client import ReconstructionClient
from client.signal_preparation import create_plan, save_plan, load_plan
from scripts.mock_reconstruction_server import Handler, ThreadingHTTPServer


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


def test_same_plan_over_two_http_servers(tmp_path):
    first = tmp_path / "signal-a.csv"
    second = tmp_path / "signal-b.csv"

    np.savetxt(first, [1.0, 2.0, 3.0], delimiter=",")
    np.savetxt(second, [3.0, 2.0, 1.0], delimiter=",")

    plan = create_plan(
        {"mock_3": [first, second]},
        seed=42,
        count=15,
        target_rms=2.0,
    )

    plan_path = tmp_path / "plan.json"
    save_plan(plan, plan_path)
    plan = load_plan(plan_path)

    with mock_server() as python_url, mock_server() as cpp_url:
        python_client = ReconstructionClient(python_url)
        cpp_client = ReconstructionClient(cpp_url)

        submissions = submit_plan_to_servers(
            plan,
            python_client,
            cpp_client,
            client_id="cliente-task10",
        )

        assert len(submissions) == 15

        for record in submissions:
            python_result = python_client.get_result(
                record["python_request_id"]
            )
            cpp_result = cpp_client.get_result(
                record["cpp_request_id"]
            )

            np.testing.assert_array_equal(
                python_result["result"]["vector"],
                cpp_result["result"]["vector"],
            )

            vector = np.asarray(python_result["result"]["vector"])
            assert 1.6 - 1e-10 <= np.sqrt(np.mean(vector ** 2)) <= 2.4 + 1e-10

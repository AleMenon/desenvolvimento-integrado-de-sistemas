import numpy as np
import pytest

from client.experiment_runner import submit_plan_to_servers
from client.signal_preparation import create_plan


class FakeClient:
    def __init__(self, rows=3):
        self.rows = rows
        self.requests = []

    def get_model(self, model_id):
        return {
            "model_id": model_id,
            "rows": self.rows,
            "columns": 3,
            "image_shape": [1, 3],
            "version": "1.0",
        }

    def submit_signal(self, client_id, signal_id, model_id, signal, **kwargs):
        self.requests.append({
            "client_id": client_id,
            "signal_id": signal_id,
            "model_id": model_id,
            "signal": list(signal),
            "parameters": kwargs,
        })
        return f"request-{len(self.requests)}"


def make_plan(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"

    np.savetxt(first, [1, 2, 3], delimiter=",")
    np.savetxt(second, [4, 5, 6], delimiter=",")

    return create_plan(
        {"demo": [first, second]},
        seed=42,
        count=15,
    )


def test_same_sequence_sent_to_both_servers(tmp_path):
    plan = make_plan(tmp_path)
    python_client = FakeClient()
    cpp_client = FakeClient()

    submissions = submit_plan_to_servers(
        plan, python_client, cpp_client
    )

    assert len(submissions) == 15
    assert len(python_client.requests) == 15
    assert python_client.requests == cpp_client.requests

    assert all(
        record["python_request_id"]
        for record in submissions
    )


def test_mismatched_model_dimensions_rejected(tmp_path):
    plan = make_plan(tmp_path)
    python_client = FakeClient(rows=3)
    cpp_client = FakeClient(rows=4)

    with pytest.raises(ValueError, match="incompatíveis"):
        submit_plan_to_servers(plan, python_client, cpp_client)

    assert not python_client.requests
    assert not cpp_client.requests


def test_wrong_signal_dimension_rejected_before_submission(tmp_path):
    plan = make_plan(tmp_path)
    python_client = FakeClient(rows=4)
    cpp_client = FakeClient(rows=4)

    with pytest.raises(ValueError, match="incompatível"):
        submit_plan_to_servers(plan, python_client, cpp_client)

    assert not python_client.requests
    assert not cpp_client.requests


def test_partial_failure_preserves_accepted_requests(tmp_path):
    from client.experiment_runner import PartialSubmissionError

    class FailingClient(FakeClient):
        def submit_signal(self, *args, **kwargs):
            if len(self.requests) == 2:
                raise ConnectionError("servidor indisponível")
            return super().submit_signal(*args, **kwargs)

    plan = make_plan(tmp_path)
    python_client = FakeClient()
    cpp_client = FailingClient()

    with pytest.raises(PartialSubmissionError) as captured:
        submit_plan_to_servers(plan, python_client, cpp_client)

    history = captured.value.submissions

    assert len(history) == 3

    assert history[0]["python_request_id"] is not None
    assert history[0]["cpp_request_id"] is not None

    assert history[1]["python_request_id"] is not None
    assert history[1]["cpp_request_id"] is not None

    assert history[2]["python_request_id"] is not None
    assert history[2]["cpp_request_id"] is None

    assert len(python_client.requests) == 3
    assert len(cpp_client.requests) == 2

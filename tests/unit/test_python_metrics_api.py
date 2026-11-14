from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.python.metrics_api import create_metrics_router
from server.python.performance_metrics import PerformanceMetrics


def test_fastapi_metrics_contract():
    registry = PerformanceMetrics("python")
    app = FastAPI()
    app.include_router(create_metrics_router(registry))
    http = TestClient(app)

    first = http.get("/metrics")
    assert first.status_code == 200
    assert first.json()["implementation"] == "python"
    registry.accepted("req-9", "cli", "sig", "mod")
    registry.started("req-9")
    registry.finished("req-9", success=True, iterations=1,
                      converged=True, stop_reason="tolerance_reached",
                      execution_time_ms=3.14)
    metrics = http.get("/metrics").json()
    assert metrics["completed_count"] == 1
    rows = http.get("/metrics/reconstructions").json()["reconstructions"]
    assert rows[0]["execution_time_ms"] == 3.14
    assert rows[0]["client_id"] == "cli"

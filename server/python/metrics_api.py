"""FastAPI adapter for TASK-16, to be mounted by the Python server (TASK-12)."""

from fastapi import APIRouter

from server.python.performance_metrics import PerformanceMetrics


def create_metrics_router(registry: PerformanceMetrics) -> APIRouter:
    router = APIRouter()

    @router.get("/metrics")
    def metrics_summary() -> dict:
        return registry.snapshot()

    @router.get("/metrics/reconstructions")
    def metrics_reconstructions() -> dict:
        return registry.reconstructions()

    return router

"""Servidor HTTP/JSON de reconstrução de imagens — TASK-12."""

import json
import math
import os
import queue
import threading
import time
import uuid
from contextlib import asynccontextmanager

from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from server.python.cgnr import cgnr
from server.python.model_catalog import ModelCatalog


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = ROOT / "models" / "catalog.json"

MAX_BODY_BYTES = 2_000_000
MAX_ITERATIONS = 10
QUEUE_CAPACITY = 64


def utc_now():
    """Retorna o horário UTC em formato ISO 8601."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def error_response(status, code, message):
    """Padroniza as respostas de erro HTTP."""
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


class ReconstructionService:
    """Gerencia reconstruções e executa CGNR em um worker dedicado."""

    def __init__(self, catalog_path, queue_capacity=QUEUE_CAPACITY):
        self.catalog = ModelCatalog(catalog_path)
        self.jobs = {}
        self.lock = threading.Lock()

        self.pending = queue.Queue(maxsize=queue_capacity)
        self.stopping = threading.Event()

        self.worker = threading.Thread(
            target=self._worker_loop,
            name="python-cgnr-worker",
            daemon=True,
        )
        self.worker.start()

    def get_job(self, request_id):
        with self.lock:
            job = self.jobs.get(request_id)

            if job is None:
                return None

            return dict(job)

    def submit(self, payload):
        """Valida e registra uma reconstrução.

        Retorna (resposta_json, status_http).
        """
        if not isinstance(payload, dict):
            return (
                {
                    "error": {
                        "code": "INVALID_BODY",
                        "message": "O corpo deve ser um objeto JSON.",
                    }
                },
                422,
            )

        required = (
            "client_id",
            "signal_id",
            "model_id",
            "algorithm",
            "signal",
            "parameters",
        )

        if any(field not in payload for field in required):
            return (
                {
                    "error": {
                        "code": "MISSING_FIELDS",
                        "message": "Campos obrigatórios ausentes.",
                    }
                },
                422,
            )

        for field in ("client_id", "signal_id", "model_id"):
            value = payload[field]

            if not isinstance(value, str) or not value.strip():
                return (
                    {
                        "error": {
                            "code": "INVALID_IDENTIFIER",
                            "message": f"Identificador inválido: {field}.",
                        }
                    },
                    400,
                )

        model_id = payload["model_id"]
        model = self.catalog.get_model(model_id)

        if model is None:
            return (
                {
                    "error": {
                        "code": "MODEL_NOT_FOUND",
                        "message": "Modelo não encontrado.",
                    }
                },
                404,
            )

        if payload["algorithm"] != "cgnr":
            return (
                {
                    "error": {
                        "code": "INVALID_ALGORITHM",
                        "message": "Algoritmo não suportado.",
                    }
                },
                400,
            )

        parameters = payload["parameters"]

        if not isinstance(parameters, dict):
            return (
                {
                    "error": {
                        "code": "INVALID_PARAMETERS",
                        "message": "parameters deve ser um objeto.",
                    }
                },
                422,
            )

        iterations = parameters.get("max_iterations")
        tolerance = parameters.get("tolerance")

        if (
            type(iterations) is not int
            or not 1 <= iterations <= MAX_ITERATIONS
            or type(tolerance) not in (int, float)
            or not math.isfinite(tolerance)
            or tolerance <= 0
        ):
            return (
                {
                    "error": {
                        "code": "INVALID_PARAMETERS",
                        "message": "Parâmetros numéricos inválidos.",
                    }
                },
                400,
            )

        signal = payload["signal"]
        expected_rows = model["metadata"]["rows"]

        if (
            not isinstance(signal, list)
            or len(signal) != expected_rows
            or any(
                type(value) not in (int, float)
                or not math.isfinite(value)
                for value in signal
            )
        ):
            return (
                {
                    "error": {
                        "code": "INVALID_SIGNAL_DIMENSION",
                        "message": "Dimensão ou valores do sinal inválidos.",
                    }
                },
                400,
            )

        request_id = str(uuid.uuid4())

        job = {
            "request_id": request_id,
            "client_id": payload["client_id"],
            "signal_id": payload["signal_id"],
            "model_id": model_id,
            "algorithm": "cgnr",
            "status": "queued",
            "created_at": utc_now(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }

        task = {
            "request_id": request_id,
            "model": model,
            "signal": np.asarray(signal, dtype=np.float64),
            "max_iterations": iterations,
            "tolerance": float(tolerance),
            "parameters": {
                "max_iterations": iterations,
                "tolerance": float(tolerance),
            },
        }

        # O registro e a entrada na fila são protegidos pelo mesmo lock.
        with self.lock:
            if self.stopping.is_set():
                return (
                    {
                        "error": {
                            "code": "SERVER_SHUTTING_DOWN",
                            "message": "Servidor em encerramento.",
                        }
                    },
                    503,
                )

            try:
                self.pending.put_nowait(task)
            except queue.Full:
                return (
                    {
                        "error": {
                            "code": "QUEUE_FULL",
                            "message": "Fila temporariamente cheia.",
                        }
                    },
                    503,
                )

            self.jobs[request_id] = job

        return (
            {
                "request_id": request_id,
                "status": "queued",
                "status_url": f"/reconstructions/{request_id}",
            },
            202,
        )

    def _worker_loop(self):
        """Processa uma reconstrução de cada vez."""
        while not self.stopping.is_set() or not self.pending.empty():
            try:
                task = self.pending.get(timeout=0.1)
            except queue.Empty:
                continue

            request_id = task["request_id"]

            with self.lock:
                job = self.jobs[request_id]
                job["status"] = "running"
                job["started_at"] = utc_now()

            start = time.perf_counter()

            try:
                result = cgnr(
                    task["model"]["matrix"],
                    task["signal"],
                    max_iterations=task["max_iterations"],
                    tolerance=task["tolerance"],
                )

                duration_ms = (
                    time.perf_counter() - start
                ) * 1000.0

                solution = np.asarray(
                    result["solution"],
                    dtype=np.float64,
                )

                if not np.all(np.isfinite(solution)):
                    raise ValueError(
                        "O CGNR produziu uma solução não finita."
                    )

                residual_norm = float(result["residual_norm"])

                if not math.isfinite(residual_norm):
                    raise ValueError(
                        "O CGNR produziu um resíduo inválido."
                    )

                normal_residual_norm = float(
                    result["normal_residual_norm"]
                )

                if not math.isfinite(normal_residual_norm):
                    raise ValueError(
                        "O CGNR produziu um resíduo normal inválido."
                    )

                metadata = task["model"]["metadata"]
                shape = metadata["image_shape"]

                if solution.size != shape[0] * shape[1]:
                    raise ValueError(
                        "Dimensão da reconstrução incompatível."
                    )

                converged = bool(result["converged"])
                stop_reason = (
                    "tolerance_reached"
                    if converged
                    else "max_iterations"
                )

                finished_at = utc_now()

                response = {
                    "request_id": request_id,
                    "status": "completed",
                    "result": {
                        "vector": solution.tolist(),
                        "shape": list(shape),
                    },
                    "metadata": {
                        "client_id": job["client_id"],
                        "signal_id": job["signal_id"],
                        "model_id": job["model_id"],
                        "model_version": metadata["version"],
                        "model_checksum": metadata[
                            "checksum_sha256"
                        ],
                        "algorithm": "cgnr",
                        "implementation": "python",
                        "iterations": int(result["iterations"]),
                        "converged": converged,
                        "stop_reason": stop_reason,
                        "residual_norm": residual_norm,
                        "normal_residual_norm": normal_residual_norm,
                        "execution_time_ms": duration_ms,
                        "parameters": task["parameters"],
                        "created_at": job["created_at"],
                        "started_at": job["started_at"],
                        "finished_at": finished_at,
                    },
                }

                with self.lock:
                    job["result"] = response
                    job["status"] = "completed"
                    job["finished_at"] = finished_at

            except Exception:
                with self.lock:
                    job["status"] = "failed"
                    job["finished_at"] = utc_now()
                    job["error"] = {
                        "code": "RECONSTRUCTION_FAILED",
                        "message": "Erro ao executar a reconstrução.",
                    }

            finally:
                self.pending.task_done()

    def shutdown(self):
        """Solicita o encerramento do worker."""
        with self.lock:
            self.stopping.set()

        self.worker.join(timeout=10)


def create_app(catalog_path=DEFAULT_CATALOG):
    """Cria a aplicação FastAPI com um catálogo configurável."""
    service = None

    @asynccontextmanager
    async def lifespan(_app):
        nonlocal service

        service = ReconstructionService(catalog_path)
        _app.state.reconstruction_service = service

        try:
            yield
        finally:
            service.shutdown()
            service = None
            _app.state.reconstruction_service = None

    app = FastAPI(
        title="Servidor Python de Reconstrução",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/models")
    def list_models():
        return {
            "models": service.catalog.list_models(),
        }

    @app.get("/models/{model_id}")
    def get_model(model_id: str):
        model = service.catalog.get_model(model_id)

        if model is None:
            return error_response(
                404,
                "MODEL_NOT_FOUND",
                "Modelo não encontrado.",
            )

        return model["metadata"]

    @app.post("/reconstructions")
    async def submit_reconstruction(request: Request):
        content_type = request.headers.get(
            "content-type", ""
        ).lower()

        if not content_type.startswith("application/json"):
            return error_response(
                415,
                "UNSUPPORTED_MEDIA_TYPE",
                "Content-Type deve ser application/json.",
            )

        content_length = request.headers.get("content-length")

        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                return error_response(
                    400,
                    "INVALID_CONTENT_LENGTH",
                    "Content-Length inválido.",
                )

            if declared_length > MAX_BODY_BYTES:
                return error_response(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    "Requisição acima do limite permitido.",
                )

        # Leitura limitada, inclusive quando Content-Length não é informado.
        data = bytearray()

        async for chunk in request.stream():
            data.extend(chunk)

            if len(data) > MAX_BODY_BYTES:
                return error_response(
                    413,
                    "PAYLOAD_TOO_LARGE",
                    "Requisição acima do limite permitido.",
                )

        try:
            payload = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            return error_response(
                422,
                "INVALID_JSON",
                "JSON inválido.",
            )

        response, status = service.submit(payload)

        return JSONResponse(
            status_code=status,
            content=response,
        )

    @app.get("/reconstructions/{request_id}")
    def get_reconstruction_status(request_id: str):
        job = service.get_job(request_id)

        if job is None:
            return error_response(
                404,
                "REQUEST_NOT_FOUND",
                "Requisição não encontrada.",
            )

        return {
            key: value
            for key, value in job.items()
            if key not in ("result",)
        }

    @app.get("/reconstructions/{request_id}/result")
    def get_reconstruction_result(request_id: str):
        job = service.get_job(request_id)

        if job is None:
            return error_response(
                404,
                "REQUEST_NOT_FOUND",
                "Requisição não encontrada.",
            )

        if job["status"] == "failed":
            return error_response(
                409,
                "RECONSTRUCTION_FAILED",
                "A reconstrução falhou.",
            )

        if job["status"] != "completed":
            return error_response(
                409,
                "RESULT_NOT_READY",
                "Resultado ainda não disponível.",
            )

        return job["result"]

    return app


app = create_app(
    os.environ.get("RECONSTRUCTION_CATALOG", str(DEFAULT_CATALOG))
)

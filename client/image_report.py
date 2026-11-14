"""Relatório de imagens reconstruídas no cliente — TASK-14."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def collect_reconstruction(client, request_id, *, max_polls=100,
                           poll_interval=0.05, sleep_fn=time.sleep):
    """Recupera o resultado ou registra a falha de uma requisição."""

    if type(max_polls) is not int or max_polls < 1:
        raise ValueError("max_polls deve ser positivo")

    if poll_interval < 0:
        raise ValueError("poll_interval não pode ser negativo")

    for attempt in range(max_polls):
        status = client.get_status(request_id)
        state = status["status"]

        if state == "completed":
            result = client.get_result(request_id)
            metadata = result["metadata"]
            image = result["result"]

            required = (
                "client_id", "signal_id", "algorithm",
                "started_at", "finished_at", "iterations",
            )

            missing = [
                field for field in required
                if field not in metadata
            ]

            if missing:
                raise ValueError(
                    f"Metadados ausentes: {', '.join(missing)}"
                )

            return {
                "request_id": request_id,
                "status": "completed",
                "image": {
                    "vector": image["vector"],
                    "shape": image["shape"],
                },
                "metadata": metadata,
            }

        if state == "failed":
            return {
                "request_id": request_id,
                "status": "failed",
                "image": None,
                "metadata": {
                    "client_id": status.get("client_id"),
                    "signal_id": status.get("signal_id"),
                    "algorithm": status.get("algorithm"),
                    "started_at": status.get("started_at"),
                    "finished_at": status.get("finished_at"),
                },
                "error": status.get("error"),
            }

        if state not in ("queued", "running"):
            raise ValueError(
                f"Estado inesperado para {request_id}: {state}"
            )

        if attempt + 1 < max_polls:
            sleep_fn(poll_interval)

    return {
        "request_id": request_id,
        "status": "pending",
        "image": None,
        "metadata": {
            "client_id": status.get("client_id"),
            "signal_id": status.get("signal_id"),
            "algorithm": status.get("algorithm"),
            "started_at": status.get("started_at"),
            "finished_at": status.get("finished_at"),
        },
        "error": {
            "code": "POLL_LIMIT_REACHED",
            "message": "Resultado ainda não disponível.",
        },
    }


def generate_image_report(experiment, client_factory, *,
                          experiment_id=None, max_polls=100,
                          poll_interval=0.05, sleep_fn=time.sleep):
    """Obtém imagens dos dois servidores, agrupadas por experimento."""

    if not isinstance(experiment, dict):
        raise ValueError("Experimento inválido")

    clients = experiment.get("clients")
    if not isinstance(clients, dict):
        raise ValueError("Clientes do experimento inválidos")

    if experiment_id is None:
        experiment_id = str(uuid4())

    if not isinstance(experiment_id, str) or not experiment_id.strip():
        raise ValueError("experiment_id inválido")

    records = []
    completed = 0
    failed = 0
    pending = 0

    for client_id, client_data in sorted(clients.items()):
        python_client, cpp_client = client_factory(client_id)

        for submission in client_data.get("submissions", []):
            for implementation, client in (
                ("python", python_client),
                ("cpp", cpp_client),
            ):
                request_id = submission.get(
                    f"{implementation}_request_id"
                )

                if request_id is None:
                    continue

                reconstruction = collect_reconstruction(
                    client,
                    request_id,
                    max_polls=max_polls,
                    poll_interval=poll_interval,
                    sleep_fn=sleep_fn,
                )

                metadata = reconstruction["metadata"]

                if metadata.get("client_id") != client_id:
                    raise ValueError(
                        f"Cliente incompatível: {request_id}"
                    )

                if metadata.get("signal_id") != submission["signal_id"]:
                    raise ValueError(
                        f"Sinal incompatível: {request_id}"
                    )

                if reconstruction["status"] == "completed":
                    completed += 1
                elif reconstruction["status"] == "failed":
                    failed += 1
                else:
                    pending += 1

                records.append({
                    "experiment_id": experiment_id,
                    "implementation": implementation,
                    "client_id": client_id,
                    "signal_id": submission["signal_id"],
                    "model_id": submission["model_id"],
                    "position": submission["position"],
                    **reconstruction,
                })

    return {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "generated_at": utc_now(),
        "experiment_status": experiment.get("status"),
        "image_count": completed,
        "failed_count": failed,
        "pending_count": pending,
        "total_records": len(records),
        "reconstructions": records,
    }


def save_image_report(report, path):
    """Persiste todas as imagens e metadados em JSON."""
    if not isinstance(report, dict):
        raise ValueError("Relatório de imagens inválido")

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    destination.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )

    return destination

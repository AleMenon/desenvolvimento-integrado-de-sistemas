"""Execução simultânea e reproduzível de clientes — TASK-11."""

import hashlib
import json
import math
import random
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from client.experiment_runner import (
    PartialSubmissionError,
    submit_plan_to_servers,
)


def utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class ConcurrentExperimentError(RuntimeError):
    """Falha experimental com resultados e erros preservados."""

    def __init__(self, results, errors, report=None):
        super().__init__(
            f"{len(errors)} cliente(s) apresentaram falha"
        )
        self.results = results
        self.errors = errors
        self.report = report


def run_concurrent_experiment(
    plans,
    client_factory,
    *,
    seed=42,
    min_interval=0.0,
    max_interval=0.1,
    max_iterations=10,
    tolerance=1e-8,
    sleep_fn=time.sleep,
):
    """Executa ao menos três clientes simultaneamente.

    plans:
        Dicionário client_id -> plano da TASK-10.

    client_factory:
        Função que recebe client_id e devolve um par
        (python_client, cpp_client).

    Cada cliente utiliza sua própria sequência e envia os mesmos
    sinais e parâmetros aos dois servidores.

    A fábrica deve fornecer instâncias HTTP independentes por cliente.
    """

    if not isinstance(plans, dict) or len(plans) < 3:
        raise ValueError(
            "o experimento exige pelo menos três clientes"
        )

    if type(seed) is not int:
        raise ValueError("seed deve ser um inteiro")

    if (
        type(min_interval) not in (int, float)
        or type(max_interval) not in (int, float)
        or not math.isfinite(min_interval)
        or not math.isfinite(max_interval)
        or min_interval < 0
        or max_interval < min_interval
    ):
        raise ValueError(
            "intervalos devem ser finitos, não negativos e ordenados"
        )

    for client_id, plan in plans.items():
        if not isinstance(client_id, str) or not client_id.strip():
            raise ValueError("client_id inválido")

        if not isinstance(plan, dict):
            raise ValueError(f"plano inválido para {client_id}")

        sequence = plan.get("sequence")

        if not isinstance(sequence, list) or len(sequence) < 15:
            raise ValueError(
                f"o cliente {client_id} precisa de pelo menos 15 sinais"
            )

    client_ids = sorted(plans)

    results = {}
    errors = {}

    def execute_client(client_id):
        plan = plans[client_id]

        # Hash estável: não depende do hash aleatório do Python.
        seed_bytes = hashlib.sha256(
            f"{seed}:{client_id}".encode("utf-8")
        ).digest()

        rng = random.Random(
            int.from_bytes(seed_bytes, "big")
        )

        delays = [
            0.0 if position == 0 else rng.uniform(
                min_interval, max_interval
            )
            for position in range(len(plan["sequence"]))
        ]

        dispatch = {}

        started_at = utc_now()
        started_clock = time.perf_counter()

        python_client, cpp_client = client_factory(client_id)

        def before_submit(entry):
            position = entry["position"]
            delay = delays[position]

            if delay > 0:
                sleep_fn(delay)

            dispatch[position] = {
                "delay_seconds": delay,
                "dispatched_at": utc_now(),
            }

        try:
            submissions = submit_plan_to_servers(
                plan,
                python_client,
                cpp_client,
                client_id=client_id,
                max_iterations=max_iterations,
                tolerance=tolerance,
                before_submit=before_submit,
                signal_id_prefix=f"{client_id}:",
            )

            status = "completed"

        except PartialSubmissionError as exc:
            submissions = exc.submissions
            raise ConcurrentExperimentError(
                {
                    client_id: {
                        "status": "failed",
                        "started_at": started_at,
                        "finished_at": utc_now(),
                        "duration_seconds": (
                            time.perf_counter() - started_clock
                        ),
                        "submissions": submissions,
                        "dispatch": dispatch,
                    }
                },
                {
                    client_id: (
                        f"{type(exc.__cause__).__name__}: {exc.__cause__}"
                        if exc.__cause__ is not None
                        else str(exc)
                    )
                },
            ) from exc

        records = []

        for submission in submissions:
            position = submission["position"]

            records.append({
                **submission,
                **dispatch[position],
            })

        return {
            "client_id": client_id,
            "status": status,
            "started_at": started_at,
            "finished_at": utc_now(),
            "duration_seconds": (
                time.perf_counter() - started_clock
            ),
            "signal_count": len(records),
            "submissions": records,
        }

    with ThreadPoolExecutor(
        max_workers=len(client_ids),
        thread_name_prefix="task11-client",
    ) as executor:
        futures = {
            executor.submit(execute_client, client_id): client_id
            for client_id in client_ids
        }

        for future in as_completed(futures):
            client_id = futures[future]

            try:
                results[client_id] = future.result()

            except ConcurrentExperimentError as exc:
                partial = exc.results[client_id]
                records = []

                for submission in partial["submissions"]:
                    position = submission["position"]

                    records.append({
                        **submission,
                        **partial["dispatch"].get(position, {}),
                    })

                results[client_id] = {
                    "client_id": client_id,
                    "status": "failed",
                    "started_at": partial["started_at"],
                    "finished_at": partial["finished_at"],
                    "duration_seconds": partial["duration_seconds"],
                    "signal_count": len(records),
                    "submissions": records,
                }

                errors[client_id] = exc.errors[client_id]

            except Exception as exc:
                errors[client_id] = (
                    f"{type(exc).__name__}: {exc}"
                )
                results[client_id] = {
                    "client_id": client_id,
                    "status": "failed",
                    "signal_count": 0,
                    "submissions": [],
                }

    ordered_results = {
        client_id: results[client_id]
        for client_id in client_ids
    }

    report = {
        "schema_version": 1,
        "seed": seed,
        "min_interval": min_interval,
        "max_interval": max_interval,
        "client_count": len(client_ids),
        "total_signals": sum(
            result["signal_count"]
            for result in ordered_results.values()
        ),
        "total_http_submissions": sum(
            sum(
                int(record["python_request_id"] is not None)
                + int(record["cpp_request_id"] is not None)
                for record in result["submissions"]
            )
            for result in ordered_results.values()
        ),
        "clients": ordered_results,
        "status": "failed" if errors else "completed",
        "errors": errors,
    }

    if errors:
        raise ConcurrentExperimentError(
            ordered_results,
            errors,
            report=report,
        )

    return report


def save_experiment_log(report, path):
    """Salva resultados completos ou parciais em JSON."""
    if isinstance(report, ConcurrentExperimentError):
        report = report.report

    if not isinstance(report, dict):
        raise ValueError("Relatório experimental inválido.")

    destination = Path(path)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )

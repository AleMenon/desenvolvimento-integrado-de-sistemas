"""TASK-18: repeatable, three-client saturation experiments for Python and C++.

Every combination of implementation and load starts a NEW server process.
The TASK-16 Collector produces the raw CPU, RSS, queue and reconstruction
exports; this module adds submission evidence and an experiment overview.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import random
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from urllib.parse import quote

import psutil
import requests

from monitoring.collect import Collector

CLIENTS = 3
ROOT = Path(__file__).resolve().parents[1]
REQUEST_COLUMNS = (
    "client_id", "signal_id", "attempt", "http_status", "error_code",
    "request_id", "latency_ms", "transport_error",
)
REPORT_COLUMNS = (
    "implementation", "signals_per_client", "attempted", "accepted_http_202",
    "queue_full_http_503", "unexpected_responses", "transport_errors",
    "server_accepted_delta", "server_finished_delta", "server_failed_delta",
    "unfinished_at_deadline", "queue_peak", "queue_peak_sampled",
    "peak_cpu_percent", "mean_cpu_percent", "peak_memory_rss_bytes",
    "rss_growth_bytes", "throughput_images_per_second",
    "mean_reconstruction_time_ms", "workload_duration_ms",
    "workload_complete", "stable", "observations",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Settings:
    levels: tuple[int, ...] = (15, 30, 60)
    workers: int = 1
    queue_capacity: int = 8
    max_inflight: int | None = None
    interval: float = 0.025
    monitor_seconds: float = 2.0
    drain_timeout: float = 10.0
    jitter_ms: float = 0.0
    http_timeout: float = 3.0
    model_id: str = "demo_identity_3"
    catalog: Path = ROOT / "models" / "catalog.json"
    signal: tuple[float, ...] = (1.0, 2.0, 3.0)
    max_iterations: int = 10
    tolerance: float = 1e-8
    seed: int = 18

    def __post_init__(self):
        if not self.levels or any(type(level) is not int or level <= 0 for level in self.levels):
            raise ValueError("levels must be positive integers")
        if len(set(self.levels)) != len(self.levels):
            raise ValueError("levels must not repeat")
        if type(self.workers) is not int or not 1 <= self.workers <= 32:
            raise ValueError("workers must be between 1 and 32")
        if type(self.queue_capacity) is not int or not 1 <= self.queue_capacity <= 100000:
            raise ValueError("queue_capacity must be between 1 and 100000")
        if self.max_inflight is not None and (
            type(self.max_inflight) is not int
            or not 1 <= self.max_inflight <= self.workers + self.queue_capacity
        ):
            raise ValueError("max_inflight must be between 1 and workers + queue_capacity")
        for name in ("interval", "monitor_seconds", "drain_timeout", "http_timeout", "tolerance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(self.jitter_ms) or self.jitter_ms < 0:
            raise ValueError("jitter_ms must be nonnegative")
        if type(self.max_iterations) is not int or not 1 <= self.max_iterations <= 10:
            raise ValueError("max_iterations must be between 1 and 10 (TASK-09)")
        if not self.model_id or not isinstance(self.model_id, str):
            raise ValueError("model_id must be nonempty")
        if not self.signal or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in self.signal):
            raise ValueError("signal must contain finite real numbers")


def _get(url: str, path: str, timeout: float) -> dict:
    response = requests.get(url + path, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON at {path}")
    return data


def _wait_until_ready(url: str, process: subprocess.Popen, timeout: float = 12) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited during startup (exit={process.returncode})")
        try:
            if requests.get(url + "/health", timeout=0.35).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.05)
    raise TimeoutError(f"Server did not become healthy: {url}")


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def launch_server(implementation: str, settings: Settings, directory: Path,
                  *, cpp_bin: Path = ROOT / "build" / "reconstruction_server"):
    """Launch an independent instance for each measurement, avoiding stale counters."""
    port = _port()
    env = os.environ.copy()
    # Keep BLAS thread counts consistent. Uvicorn has only ONE process.
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    total = CLIENTS * max(settings.levels)
    retained = min(100000, max(1024, total + 32))
    if implementation == "python":
        env.update({
            "RECONSTRUCTION_CATALOG": str(settings.catalog.resolve()),
            "RECONSTRUCTION_WORKERS": str(settings.workers),
            "RECONSTRUCTION_QUEUE_CAPACITY": str(settings.queue_capacity),
            "RECONSTRUCTION_MAX_INFLIGHT": str(settings.max_inflight or (settings.workers + settings.queue_capacity)),
            "RECONSTRUCTION_MAX_RESULTS": str(retained),
            "RECONSTRUCTION_RESULT_TTL_SECONDS": "3600",
        })
        argv = [sys.executable, "-m", "uvicorn", "server.python.reconstruction_server:app",
                "--host", "127.0.0.1", "--port", str(port)]
    elif implementation == "cpp":
        binary = Path(cpp_bin).resolve()
        if not binary.is_file():
            raise FileNotFoundError(f"Compile o servidor C++ antes do experimento: {binary}")
        argv = [str(binary), "--host", "127.0.0.1", "--port", str(port),
                "--catalog", str(settings.catalog.resolve()),
                "--queue-capacity", str(settings.queue_capacity),
                "--workers", str(settings.workers),
                "--max-inflight", str(settings.max_inflight or (settings.workers + settings.queue_capacity)),
                "--max-retained-results", str(retained),
                "--result-ttl-seconds", "3600"]
    else:
        raise ValueError(f"Unknown implementation: {implementation}")
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT)
        url = f"http://127.0.0.1:{port}"
        try:
            _wait_until_ready(url, process)
            yield url, process.pid, process
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _submit_client(url: str, settings: Settings, count: int, index: int, barrier: Barrier) -> list[dict]:
    rng = random.Random(settings.seed + index)
    rows = []
    client_id = f"task18-client-{index + 1}"
    with requests.Session() as session:
        barrier.wait(timeout=10)
        for n in range(count):
            signal_id = f"load-{count}-client-{index + 1}-signal-{n + 1}"
            payload = {
                "client_id": client_id,
                "signal_id": signal_id,
                "model_id": settings.model_id,
                "algorithm": "cgnr",
                "signal": list(settings.signal),
                "parameters": {"max_iterations": settings.max_iterations, "tolerance": settings.tolerance},
            }
            start = time.monotonic()
            code = ""
            http_status = ""
            request_id = ""
            transport_error = ""
            try:
                response = session.post(url + "/reconstructions", json=payload,
                                        timeout=settings.http_timeout)
                http_status = response.status_code
                try:
                    data = response.json()
                except ValueError:
                    data = {}
                if response.status_code == 202:
                    request_id = data.get("request_id", "")
                    if not isinstance(request_id, str) or not request_id:
                        code = "INVALID_REQUEST_ID"
                else:
                    code = data.get("error", {}).get("code", "UNKNOWN_HTTP_ERROR")
            except requests.RequestException as exc:
                transport_error = f"{type(exc).__name__}: {exc}"[:250]
            rows.append({
                "client_id": client_id, "signal_id": signal_id, "attempt": n + 1,
                "http_status": http_status, "error_code": code,
                "request_id": request_id,
                "latency_ms": round((time.monotonic() - start) * 1000, 3),
                "transport_error": transport_error,
            })
            if settings.jitter_ms:
                time.sleep(rng.uniform(0, settings.jitter_ms) / 1000.0)
    return rows


def run_scenario(implementation: str, url: str, pid: int, signals_per_client: int,
                 settings: Settings, directory: Path, *, process=None) -> dict:
    """Run 3 synchronized HTTP clients and collect TASK-16 evidence.

    Do NOT interpret 503 QUEUE_FULL as a lost accepted task: it is intended
    backpressure. Stability is checked using lifetime server counters.
    """
    directory.mkdir(parents=True, exist_ok=True)
    model = _get(url, "/models/" + quote(settings.model_id, safe=""), settings.http_timeout)
    if model.get("rows") != len(settings.signal):
        raise ValueError(f"Model expects {model.get('rows')} signal values, got {len(settings.signal)}")
    before = _get(url, "/queue", settings.http_timeout)
    if before.get("implementation") != implementation:
        raise ValueError("Implementation mismatch between runner and server")
    if before.get("queue_size") or before.get("running_count"):
        raise ValueError("The server must be idle before each scenario")
    collector = Collector(url, pid, directory, interval=settings.interval,
                          timeout=settings.http_timeout)
    with ThreadPoolExecutor(max_workers=1) as monitor_pool:
        monitor_future = monitor_pool.submit(collector.run, settings.monitor_seconds)
        deadline = time.monotonic() + min(settings.monitor_seconds, 5.0)
        while (collector.initial is None or not collector.samples) and time.monotonic() < deadline:
            if monitor_future.done():
                monitor_future.result()
            time.sleep(0.002)
        if collector.initial is None or not collector.samples:
            raise RuntimeError("Collector did not start; increase --monitor-seconds")
        barrier = Barrier(CLIENTS + 1)
        with ThreadPoolExecutor(max_workers=CLIENTS) as pool:
            futures = [pool.submit(_submit_client, url, settings, signals_per_client, i, barrier)
                       for i in range(CLIENTS)]
            barrier.wait(timeout=10)
            load_started = time.monotonic()
            rows = [row for future in futures for row in future.result()]
        end_submissions = time.monotonic()
        expected_accepted = sum(row["http_status"] == 202 for row in rows)
        start_finished = before["completed_count"] + before["failed_count"]
        drain_deadline = time.monotonic() + settings.drain_timeout
        drained = False
        last_queue = None
        while time.monotonic() < drain_deadline:
            try:
                last_queue = _get(url, "/queue", settings.http_timeout)
                completed_since_start = last_queue["completed_count"] + last_queue["failed_count"] - start_finished
                if (last_queue["queue_size"] == last_queue["running_count"] == 0
                        and completed_since_start >= expected_accepted):
                    drained = True
                    break
            except requests.RequestException:
                break
            time.sleep(0.01)
        # Even when draining exceeds the observation window, retain the TASK-16
        # incomplete marker instead of reporting a misleading performance result.
        collector_summary = monitor_future.result()

    try:
        after = _get(url, "/queue", settings.http_timeout)
    except requests.RequestException:
        after = last_queue or before
    try:
        healthy = _get(url, "/health", settings.http_timeout).get("status") == "ok"
    except requests.RequestException:
        healthy = False
    alive = process is None or process.poll() is None
    accepted = sum(r["http_status"] == 202 and bool(r["request_id"]) for r in rows)
    queue_full = sum(r["http_status"] == 503 and r["error_code"] == "QUEUE_FULL" for r in rows)
    transport = sum(bool(r["transport_error"]) for r in rows)
    unexpected = len(rows) - accepted - queue_full - transport
    server_accepted = after["accepted_count"] - before["accepted_count"]
    server_finished = after["completed_count"] + after["failed_count"] - start_finished
    server_failed = after["failed_count"] - before["failed_count"]
    ids = [r["request_id"] for r in rows if r["request_id"]]
    ids_unique = len(ids) == len(set(ids))
    stable = bool(alive and healthy and drained and server_accepted == accepted
                  and server_finished == server_accepted and ids_unique
                  and unexpected == 0 and transport == 0)
    samples = collector.samples
    peak_sampled = max((int(r["queue_size"]) for r in samples), default=0)
    # With a new server per scenario, this peak belongs to THIS scenario.
    queue_peak = after.get("queue_peak")
    observations = []
    if queue_full:
        observations.append("Saturação: QUEUE_FULL observado (backpressure intencional)")
    elif queue_peak is not None and queue_peak >= settings.queue_capacity:
        observations.append("Fila atingiu sua capacidade máxima")
    else:
        observations.append("Limite da fila não foi atingido nesta carga")
    if not drained:
        observations.append("Tarefas não drenaram no prazo: ampliar --drain-timeout")
    if not collector_summary["workload_complete"]:
        observations.append("Janela do coletor incompleta: ampliar --monitor-seconds ou retenção")
    if server_failed:
        observations.append(f"{server_failed} reconstruções falharam (inspecionar stop_reason)")
    if transport or unexpected:
        observations.append("Falhas HTTP inesperadas ou de transporte")
    if not ids_unique:
        observations.append("Identificadores duplicados retornados pelo servidor")
    if server_accepted != accepted:
        observations.append("Contadores divergem: possível aceite após timeout HTTP")
    cpu = collector_summary.get("peak_cpu_percent")
    cpu_samples = [s["cpu_percent"] for s in samples if s["cpu_percent"] is not None]
    mean_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else None
    rss_growth = (samples[-1]["memory_rss_bytes"] - samples[0]["memory_rss_bytes"]) if samples else None
    if cpu is not None and cpu >= 85 * settings.workers:
        observations.append("CPU elevada para a quantidade de workers (indício; não diagnóstico definitivo)")

    result = {
        "timestamp_utc": utc_now(),
        "implementation": implementation,
        "signals_per_client": signals_per_client,
        "clients": CLIENTS,
        "attempted": len(rows),
        "accepted_http_202": accepted,
        "queue_full_http_503": queue_full,
        "unexpected_responses": unexpected,
        "transport_errors": transport,
        "server_accepted_delta": server_accepted,
        "server_finished_delta": server_finished,
        "server_failed_delta": server_failed,
        "unfinished_at_deadline": after["queue_size"] + after["running_count"],
        "queue_peak": queue_peak,
        "queue_peak_sampled": peak_sampled,
        "peak_cpu_percent": cpu,
        "mean_cpu_percent": mean_cpu,
        "rss_growth_bytes": rss_growth,
        "peak_memory_rss_bytes": collector_summary.get("peak_memory_rss_bytes"),
        "workload_complete": collector_summary["workload_complete"],
        "stable": stable,
        "submission_elapsed_ms": round((end_submissions - load_started) * 1000, 3),
        "observations": "; ".join(observations),
        "workers": settings.workers,
        "queue_capacity": settings.queue_capacity,
        "admission_limit": settings.max_inflight or (settings.workers + settings.queue_capacity),
        "retention_evicted": after.get("evicted_count"),
        "server_health_ok": healthy,
        "server_process_alive": alive,
        "all_accepted_finished_by_deadline": drained,
        "request_ids_unique": ids_unique,
        "monitoring_window_ms": collector_summary["monitoring_window_ms"],
        "workload_duration_ms": collector_summary["total_execution_time_ms"],
        "mean_reconstruction_time_ms": collector_summary["mean_reconstruction_time_ms"],
        "throughput_images_per_second": collector_summary.get("images_per_second"),
        "mean_queue_sampled": collector_summary["queue_mean_sampled"],
        "completed_during_monitor": collector_summary["completed_count"],
    }
    # Timestamp, PID and environment make the saved result reproducible.
    with (directory / "requests.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REQUEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (directory / "scenario.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return result


def render_report(report: dict) -> str:
    """Render only stored experiment evidence, never current machine measurements.

    This also lets the publish command regenerate the Markdown without re-running
    the workloads (or replacing measured values with the publisher's hardware).
    """
    cfg = report["config"]
    environment = report["environment"]
    results = report["results"]
    errors = report.get("errors") or []
    model_id = cfg["model_id"]
    if model_id == "demo_identity_3":
        model_note = ("Modelo `demo_identity_3`: matriz identidade 3 × 3 usada para "
                      "testar o protocolo e o controle de carga; não representa "
                      "o custo de uma reconstrução experimental real.")
    elif model_id.startswith("task18_dense_"):
        model_note = (f"Modelo `{model_id}`: matriz **sintética densa**, gerada "
                      f"de forma reproduzível (seed `{cfg.get('seed', 'N/D')}`). "
                      "Não é uma matriz experimental real; seu custo depende "
                      "da dimensão, algoritmo e parâmetros escolhidos.")
    else:
        model_note = (f"Modelo `{model_id}` definido pelo catálogo do ensaio. "
                      "O formato, as dimensões e a origem devem ser verificados "
                      "no catálogo antes de generalizar o resultado.")

    lines = [
        "# TASK-18 — Resultados de saturação", "",
        f"Gerado em: `{report.get('generated_at_utc', 'N/D')}`.",
        "Três clientes com largada sincronizada; um servidor novo por cenário.",
        "Rejeição `503/QUEUE_FULL` = **backpressure intencional**; não é perda "
        "de uma tarefa aceita (`202`).", "",
        "## Ambiente medido", "",
        f"- Sistema: `{environment.get('system', 'N/D')}`",
        f"- Python: `{environment.get('python', 'N/D')}`",
        f"- CPUs lógicas: `{environment.get('logical_cpu_count', 'N/D')}`",
        f"- RAM física total (bytes): `{environment.get('total_ram_bytes', 'N/D')}`",
        "", "## Configuração do experimento", "",
        f"- Modelo: `{model_id}`; amostras por sinal: `{cfg.get('signal_size', 'N/D')}`",
        f"- Catálogo utilizado: `{cfg.get('catalog', 'N/D')}`",
        f"- Cargas: `{', '.join(str(n) for n in cfg.get('levels', []))}` sinais por cliente × 3 clientes",
        f"- Workers internos por servidor: `{cfg.get('workers', 'N/D')}`; "
        f"capacidade de espera: `{cfg.get('queue_capacity', 'N/D')}`",
        f"- Monitoramento: `{cfg.get('monitor_seconds', 'N/D')}` s, "
        f"amostragem: `{cfg.get('interval_seconds', 'N/D')}` s, "
        f"drenagem: `{cfg.get('drain_timeout', 'N/D')}` s",
        f"- Intervalo aleatório entre envios: `0–{cfg.get('jitter_ms', 'N/D')}` ms",
        f"- CGNR: máximo de `{cfg.get('max_iterations', 'N/D')}` iterações, "
        f"tolerância `{cfg.get('tolerance', 'N/D')}`",
        "- BLAS: `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1` "
        "(definidos pelo executor para os processos iniciados)",
        "", model_note, "", "## Medições por cenário", "",
    ]
    columns = ("implementation", "signals_per_client", "attempted", "accepted_http_202",
               "queue_full_http_503", "queue_peak", "peak_cpu_percent",
               "peak_memory_rss_bytes", "workload_complete", "stable")
    lines.extend(["| " + " | ".join(columns) + " |",
                  "| " + " | ".join(["---"] * len(columns)) + " |"])
    lines.extend("| " + " | ".join("N/D" if result.get(k) is None else str(result[k])
                                     for k in columns) + " |" for result in results)
    lines += [
        "", "## Interpretação da taxa de aceitação", "",
        "`accepted_http_202` conta **envios HTTP aceitos**, não imagens/s "
        "reconstruídas. O desempenho do CGNR, os workers disponíveis, "
        "a capacidade da fila e o intervalo entre POSTs afetam quantos envios "
        "recebem `202` antes que a fila fique cheia. Comparar somente cargas, "
        "modelos e configurações equivalentes. Sem múltiplas repetições, os "
        "valores não são uma conclusão geral de desempenho entre linguagens.", "",
    ]
    py_by_load = {r["signals_per_client"]: r for r in results if r["implementation"] == "python"}
    cpp_by_load = {r["signals_per_client"]: r for r in results if r["implementation"] == "cpp"}
    if py_by_load.keys() & cpp_by_load.keys():
        lines += ["| Carga total | Python (202/503) | C++ (202/503) |",
                  "| ---: | ---: | ---: |"]
        for level in sorted(py_by_load.keys() & cpp_by_load.keys()):
            py, cpp = py_by_load[level], cpp_by_load[level]
            lines.append(f"| {3*level} | {py['accepted_http_202']} / {py['queue_full_http_503']} "
                         f"| {cpp['accepted_http_202']} / {cpp['queue_full_http_503']} |")
    else:
        lines.append("Não há pares Python/C++ com a mesma carga neste relatório.")
    lines += [
        "", "## Metodologia de CPU e memória", "",
        "O coletor da TASK-16 soma o **tempo de CPU (usuário + sistema) do "
        "processo monitorado e dos processos filhos**; calcula, entre duas "
        "amostras, `CPU% = 100 × Δ(tempo de CPU) / Δ(tempo de parede)`. "
        "Por convenção, **100% equivale ao uso contínuo de um núcleo lógico**. "
        "Por isso, o valor pode ultrapassar 100% quando há processamento "
        "paralelo em múltiplos núcleos: por exemplo, 715% equivalem a "
        "aproximadamente 7,15 núcleos lógicos durante o intervalo observado, "
        "e **não** a 715% da capacidade total da máquina. O número de "
        "workers CGNR não equivale necessariamente ao número de threads "
        "de todo o processo. O pico é uma **amostra temporal**, não a média "
        "sobre toda a carga.", "",
        "A memória é a **soma do RSS** do processo e dos filhos em cada amostra. "
        "Memória compartilhada pode ser contabilizada em mais de um processo; "
        "aumento de RSS isoladamente não comprova vazamento de memória.",
        "", "## Observações e gargalos", "",
    ]
    for r in results:
        lines.append(f"- **{r['implementation']} — {r['signals_per_client']} sinais/cliente:** "
                     f"{r.get('observations') or 'Sem observações automáticas; analisar dados brutos.'}")
    lines += ["", "## Progressão da carga", ""]
    trends = 0
    for implementation in sorted({r["implementation"] for r in results}):
        runs = sorted((r for r in results if r["implementation"] == implementation),
                      key=lambda r: r["signals_per_client"])
        for prev, curr in zip(runs, runs[1:]):
            a, b = prev.get("throughput_images_per_second"), curr.get("throughput_images_per_second")
            if (a is not None and b is not None and a > 0 and
                    curr["signals_per_client"] >= prev["signals_per_client"] * 1.5 and
                    b <= a * 1.1):
                lines.append(f"- {implementation}: vazão estável ou menor entre "
                             f"{prev['signals_per_client']} e {curr['signals_per_client']} sinais/cliente "
                             "(indício; verificar se ambas as janelas são completas).")
                trends += 1
            ra, rb = prev.get("peak_memory_rss_bytes"), curr.get("peak_memory_rss_bytes")
            if ra and rb and rb >= ra * 1.25:
                lines.append(f"- {implementation}: pico RSS aumentou pelo menos 25% "
                             f"entre {prev['signals_per_client']} e {curr['signals_per_client']} sinais/cliente "
                             "(não é evidência suficiente de vazamento).")
                trends += 1
    if not trends:
        lines.append("- Nenhuma tendência adicional foi detectada pelas heurísticas automáticas; "
                     "analisar os dados de fila, CPU, RSS e as repetições dos ensaios.")
    if errors:
        lines += ["", "## Erros durante a campanha", "", *[f"- {e}" for e in errors]]
    lines += [
        "", "## Limitações e evidências", "",
        "- `workload_complete=false`: a janela de coleta não cobre toda a carga; "
        "não comparar os tempos de execução e a vazão como se fossem completos.",
        "- A matriz sintética é um cenário controlado, não um modelo experimental real.",
        "- `queue_peak` é observado pelo servidor; o pico amostrado da TASK-16 "
        "pode perder alterações de fila muito rápidas.",
        "- O pacote de evidências inclui `report.json`, `report.csv` e, "
        "para cada cenário, `scenario.json`, `requests.csv`, `summary.json`, "
        "`samples.csv` e `reconstructions.csv`. Os números são derivados da "
        "execução registrada, não de estimativas manuais.",
        "", "Gargalos e comparação de implementações dependem da carga, "
        "hardware e configuração observados; outros ambientes exigem novas medições.", "",
    ]
    return "\n".join(lines)


def write_report(results: list[dict], directory: Path, settings: Settings,
                 errors: list[str] | None = None) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "report.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REPORT_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)
    report = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "environment": {"system": platform.platform(), "python": sys.version.split()[0],
                        "logical_cpu_count": psutil.cpu_count(logical=True),
                        "total_ram_bytes": psutil.virtual_memory().total},
        "method": "three-client-synchronized-start, fresh-server-per-scenario",
        "errors": errors or [],
        "config": {"levels": settings.levels, "workers": settings.workers,
                   "queue_capacity": settings.queue_capacity,
                   "max_inflight": settings.max_inflight or (settings.workers + settings.queue_capacity),
                   "interval_seconds": settings.interval,
                   "monitor_seconds": settings.monitor_seconds, "drain_timeout": settings.drain_timeout,
                   "jitter_ms": settings.jitter_ms, "model_id": settings.model_id,
                   "catalog": str(settings.catalog.resolve()),
                   "signal_size": len(settings.signal), "max_iterations": settings.max_iterations,
                   "tolerance": settings.tolerance, "seed": settings.seed},
        "results": results,
    }
    (directory / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (directory / "report.md").write_text(render_report(report), encoding="utf-8")


def _parse_signal(path: Path | None) -> tuple[float, ...]:
    if path is None:
        return (1., 2., 3.)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Signal JSON must contain a numeric list")
    return tuple(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="TASK-18: 3-client saturation tests and TASK-16 exports")
    parser.add_argument("--implementations", nargs="+", choices=("python", "cpp"),
                        default=["python", "cpp"])
    parser.add_argument("--levels", nargs="+", type=int, default=[15, 30, 60],
                        help="number of signals PER CLIENT at each level (3 clients)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--queue-capacity", type=int, default=8)
    parser.add_argument("--max-inflight", type=int, default=None)
    parser.add_argument("--sample-interval", type=float, default=0.025)
    parser.add_argument("--monitor-seconds", type=float, default=2.0)
    parser.add_argument("--drain-timeout", type=float, default=10.0)
    parser.add_argument("--jitter-ms", type=float, default=0.0)
    parser.add_argument("--http-timeout", type=float, default=3.0)
    parser.add_argument("--model-id", default="demo_identity_3")
    parser.add_argument("--catalog", type=Path, default=ROOT / "models" / "catalog.json")
    parser.add_argument("--signal-file", type=Path, help="JSON array, length = model rows")
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--tolerance", type=float, default=1e-8)
    parser.add_argument("--seed", type=int, default=18)
    parser.add_argument("--cpp-bin", type=Path, default=ROOT / "build" / "reconstruction_server")
    parser.add_argument("--output", type=Path, default=None,
                        help="empty output directory; default: timestamped results/saturation/run-...")
    args = parser.parse_args()
    settings = Settings(levels=tuple(args.levels), workers=args.workers,
                        queue_capacity=args.queue_capacity, max_inflight=args.max_inflight,
                        interval=args.sample_interval,
                        monitor_seconds=args.monitor_seconds, drain_timeout=args.drain_timeout,
                        jitter_ms=args.jitter_ms, http_timeout=args.http_timeout,
                        model_id=args.model_id, catalog=args.catalog,
                        signal=_parse_signal(args.signal_file),
                        max_iterations=args.max_iterations, tolerance=args.tolerance, seed=args.seed)
    output = (args.output or (ROOT / "results" / "saturation" /
              ("run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")))).resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"Output directory is not empty: {output}. Use a new --output.")
    results = []
    errors = []
    for implementation in args.implementations:
        for volume in settings.levels:
            directory = output / implementation / f"signals-{volume}-per-client"
            try:
                with launch_server(implementation, settings, directory, cpp_bin=args.cpp_bin) as (url, pid, proc):
                    result = run_scenario(implementation, url, pid, volume, settings, directory, process=proc)
                results.append(result)
                print(f"{implementation} {volume}/client: accepted={result['accepted_http_202']} "
                      f"queue_full={result['queue_full_http_503']} stable={result['stable']} "
                      f"complete={result['workload_complete']}", flush=True)
            except Exception as exc:
                message = f"{implementation}, {volume} signals/client: {type(exc).__name__}: {exc}"
                errors.append(message)
                print("ERROR: " + message, file=sys.stderr, flush=True)
    # The combined report is written after optional TASK-17 comparison.
    # TASK-17 comparison is valid only between equivalent volume pairs.
    try:
        from monitoring.statistics import export_comparison
        for level in settings.levels:
            paths = [output / impl / f"signals-{level}-per-client" for impl in ("python", "cpp")]
            if all((p / "summary.json").is_file() for p in paths):
                export_comparison(paths, output / "comparisons" / f"signals-{level}-per-client")
    except (ImportError, ValueError) as exc:
        errors.append(f"Statistics comparison: {exc}")
        print(f"Statistics comparison skipped: {exc}", file=sys.stderr)
    write_report(results, output, settings, errors)
    if errors:
        (output / "errors.json").write_text(json.dumps(errors, indent=2) + "\n", encoding="utf-8")
    print(f"Relatório: {output / 'report.md'}")
    return 1 if errors or any(not r["stable"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())

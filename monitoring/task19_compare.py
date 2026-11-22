"""TASK-19: paired saturation experiments before/after admission tuning.

Fresh server process per profile / implementation / load / repetition.
No numbers are fabricated: measurements are produced by the TASK-18 runner.
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import psutil

from monitoring.saturation import (
    ROOT, Settings, _parse_signal, launch_server, run_scenario, write_report,
)

COLUMNS = (
    "implementation", "signals_per_client", "repeat", "attempted",
    "before_workers", "before_queue_capacity", "before_admission_limit",
    "after_workers", "after_queue_capacity", "after_admission_limit",
    "before_accepted", "after_accepted", "accepted_delta",
    "before_queue_full", "after_queue_full", "rejected_delta",
    "before_rejection_percent", "after_rejection_percent", "rejection_change_pp",
    "before_queue_peak", "after_queue_peak",
    "before_cpu_peak", "after_cpu_peak", "before_rss_peak", "after_rss_peak",
    "before_throughput", "after_throughput",
    "before_stable", "after_stable", "before_complete", "after_complete",
)


def compare_rows(before: dict, after: dict, *, repeat: int) -> dict:
    """Pair only matching implementations, load and three-client request counts."""
    for name in ("implementation", "signals_per_client", "attempted", "clients"):
        if before[name] != after[name]:
            raise ValueError(f"Cannot compare different {name}")
    if before["clients"] != 3 or before["attempted"] <= 0:
        raise ValueError("Expected three clients and a positive number of attempts")
    for sample in (before, after):
        accepted = sample["accepted_http_202"]
        rejected = sample["queue_full_http_503"]
        unexpected = sample["unexpected_responses"]
        transport = sample["transport_errors"]
        if any(type(v) is not int or v < 0 for v in (accepted, rejected, unexpected, transport)):
            raise ValueError("Invalid HTTP counters")
        if accepted + rejected + unexpected + transport != sample["attempted"]:
            raise ValueError("Inconsistent submission counters")
    attempted = before["attempted"]
    before_pct = 100 * before["queue_full_http_503"] / attempted
    after_pct = 100 * after["queue_full_http_503"] / attempted
    return {
        "implementation": before["implementation"],
        "signals_per_client": before["signals_per_client"],
        "repeat": repeat, "attempted": attempted,
        "before_workers": before["workers"],
        "before_queue_capacity": before["queue_capacity"],
        "before_admission_limit": before.get("admission_limit", before["workers"] + before["queue_capacity"]),
        "after_workers": after["workers"],
        "after_queue_capacity": after["queue_capacity"],
        "after_admission_limit": after.get("admission_limit", after["workers"] + after["queue_capacity"]),
        "before_accepted": before["accepted_http_202"],
        "after_accepted": after["accepted_http_202"],
        "accepted_delta": after["accepted_http_202"] - before["accepted_http_202"],
        "before_queue_full": before["queue_full_http_503"],
        "after_queue_full": after["queue_full_http_503"],
        "rejected_delta": after["queue_full_http_503"] - before["queue_full_http_503"],
        "before_rejection_percent": round(before_pct, 3),
        "after_rejection_percent": round(after_pct, 3),
        "rejection_change_pp": round(after_pct - before_pct, 3),
        "before_queue_peak": before["queue_peak"], "after_queue_peak": after["queue_peak"],
        "before_cpu_peak": before["peak_cpu_percent"], "after_cpu_peak": after["peak_cpu_percent"],
        "before_rss_peak": before["peak_memory_rss_bytes"],
        "after_rss_peak": after["peak_memory_rss_bytes"],
        "before_throughput": before.get("throughput_images_per_second") if before["workload_complete"] else None,
        "after_throughput": after.get("throughput_images_per_second") if after["workload_complete"] else None,
        "before_stable": before["stable"], "after_stable": after["stable"],
        "before_complete": before["workload_complete"],
        "after_complete": after["workload_complete"],
    }


def write_comparison(rows: list[dict], output: Path, errors: list[str], *, model_id: str) -> None:
    """Write a measured report; never claim improvement based on 202 count alone."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "comparison.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "schema_version": 1,
        "model_id": model_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"platform": platform.platform(), "logical_cpus": psutil.cpu_count(),
                        "memory_bytes": psutil.virtual_memory().total},
        "method": "same model and signal; matched load, fresh process for each sample",
        "errors": errors,
        "comparisons": rows,
    }
    (output / "comparison.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    lines = [
        "# TASK-19 — Comparação antes/depois do controle de saturação",
        "",
        f"Modelo: `{model_id}`; três clientes simultâneos; servidor novo em cada execução.",
        "",
        "| Versão | Sinais/cliente | Repetição | 202 antes/depois | 503 antes/depois | Variação de rejeição (p.p.) | Fila máxima antes/depois | Estável antes/depois |",
        "| --- | ---: | ---: | --- | --- | ---: | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r['implementation']} | {r['signals_per_client']} | {r['repeat']} | "
            f"{r['before_accepted']}/{r['after_accepted']} | "
            f"{r['before_queue_full']}/{r['after_queue_full']} | "
            f"{r['rejection_change_pp']:+.3f} | "
            f"{r['before_queue_peak']}/{r['after_queue_peak']} | "
            f"{r['before_stable']}/{r['after_stable']} |"
        )
    lines.extend([
        "", "## Interpretação", "",
        "- `202` mede aceitação HTTP, não produtividade do CGNR. Uma fila maior pode elevar "
        "a aceitação sem melhorar o tempo de processamento.",
        "- Rejeições `503/QUEUE_FULL` são backpressure esperado, não perda de tarefas aceitas.",
        "- Os resultados só são comparáveis sob o mesmo hardware, modelo, carga, ritmo "
        "de envio, bibliotecas numéricas e políticas de amostragem.",
        "- Mudar workers, capacidade da fila e limite de admissão simultaneamente "
        "impede atribuir qualquer melhoria a uma única variável.",
        "- CPU% usa 100% por núcleo lógico, incluindo processos filhos (TASK-16); "
        "picos acima de 100% são possíveis.",
        "- Resultados de vazão com `workload_complete=false` devem ser ignorados; "
        "a coluna 202 sozinha não comprova maior throughput.",
        "", "## Evidências", "",
        "Os diretórios `before/` e `after/` contêm `scenario.json`, `requests.csv`, "
        "`summary.json`, `samples.csv` e `reconstructions.csv` por versão/carga/repetição.",
    ])
    if errors:
        lines.extend(["", "## Erros", "", *[f"- {error}" for error in errors]])
    (output / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--implementations", nargs="+", choices=("python", "cpp"), default=["python", "cpp"])
    parser.add_argument("--levels", nargs="+", type=int, default=[15, 30, 60])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--workers-before", type=int, default=1)
    parser.add_argument("--queue-before", type=int, default=2)
    parser.add_argument("--max-inflight-before", type=int, default=3)
    parser.add_argument("--workers-after", type=int, default=2)
    parser.add_argument("--queue-after", type=int, default=8)
    parser.add_argument("--max-inflight-after", type=int, default=6)
    parser.add_argument("--model-id", default="task18_dense_512")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--signal-file", type=Path, required=True)
    parser.add_argument("--monitor-seconds", type=float, default=30.0)
    parser.add_argument("--drain-timeout", type=float, default=90.0)
    parser.add_argument("--sample-interval", type=float, default=0.025)
    parser.add_argument("--jitter-ms", type=float, default=0.0)
    parser.add_argument("--http-timeout", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=18)
    parser.add_argument("--cpp-bin", type=Path, default=ROOT / "build" / "reconstruction_server")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "task19")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"Output directory not empty: {output}")
    signal = _parse_signal(args.signal_file)
    base = Settings(
        levels=tuple(args.levels), catalog=args.catalog, signal=signal,
        model_id=args.model_id, monitor_seconds=args.monitor_seconds,
        drain_timeout=args.drain_timeout, interval=args.sample_interval,
        jitter_ms=args.jitter_ms, http_timeout=args.http_timeout,
        seed=args.seed,
    )
    settings_map = {
        "before": replace(base, workers=args.workers_before, queue_capacity=args.queue_before,
                          max_inflight=args.max_inflight_before),
        "after": replace(base, workers=args.workers_after, queue_capacity=args.queue_after,
                         max_inflight=args.max_inflight_after),
    }
    measurements = {}
    errors = []
    for implementation in args.implementations:
        for level in base.levels:
            for repeat in range(1, args.repeats + 1):
                for profile, settings in settings_map.items():
                    settings = replace(settings, seed=args.seed + repeat - 1)
                    dest = output / profile / implementation / f"signals-{level}-per-client" / f"repeat-{repeat}"
                    try:
                        with launch_server(implementation, settings, dest, cpp_bin=args.cpp_bin) as (url, pid, process):
                            result = run_scenario(implementation, url, pid, level, settings, dest, process=process)
                        result["admission_limit"] = settings.max_inflight
                        measurements[(implementation, level, repeat, profile)] = result
                        print(f"{implementation} {level}/client repeat {repeat} {profile}: "
                              f"202={result['accepted_http_202']} "
                              f"503={result['queue_full_http_503']} stable={result['stable']}", flush=True)
                    except Exception as exc:
                        message = f"{implementation} {level} repeat {repeat} {profile}: {type(exc).__name__}: {exc}"
                        errors.append(message)
                        print(message, flush=True)
    comparisons = []
    for implementation in args.implementations:
        for level in base.levels:
            for repeat in range(1, args.repeats + 1):
                before = measurements.get((implementation, level, repeat, "before"))
                after = measurements.get((implementation, level, repeat, "after"))
                if before is None or after is None:
                    errors.append(f"Missing pair: {implementation} {level} repeat {repeat}")
                else:
                    comparisons.append(compare_rows(before, after, repeat=repeat))
    write_comparison(comparisons, output, errors, model_id=args.model_id)
    print(f"Compare report: {output / 'comparison.md'}")
    return int(bool(errors) or any(not (r["before_stable"] and r["after_stable"]) for r in comparisons))


if __name__ == "__main__":
    raise SystemExit(main())

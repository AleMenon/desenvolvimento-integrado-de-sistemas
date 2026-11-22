"""TASK-21: paired, reproducible Python/C++ HTTP reconstruction benchmarks.

The TASK-18 launcher starts a fresh server for every run. The TASK-16 collector
exports the original metrics, and TASK-17 computes queue time-weighting.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, Event
from urllib.parse import quote

import psutil
import requests

from monitoring.collect import Collector, RECONSTRUCTION_COLUMNS, utc_parse
from monitoring.saturation import ROOT, Settings as SaturationSettings, launch_server
from monitoring.statistics import queue_durations

CLIENT_COUNT = 3
SAMPLE_FIELDS = ('implementation', 'signals_per_client', 'repeat', 'planned', 'accepted',
                 'rejected', 'failed', 'transport_errors', 'unexpected', 'finished',
                 'workload_complete', 'valid', 'total_execution_time_ms',
                 'mean_reconstruction_time_ms', 'cpu_mean_percent', 'cpu_peak_percent',
                 'rss_peak_bytes', 'queue_mean', 'queue_mode', 'queue_peak',
                 'observation_time_ms', 'submission_time_ms', 'plan_sha256')


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class Settings:
    levels: tuple[int, ...] = (15, 30, 60)
    repeats: int = 3
    workers: int = 2
    queue_capacity: int = 256
    interval: float = 0.025
    drain_timeout: float = 120.0
    http_timeout: float = 5.0
    model_id: str = 'task18_dense_512'
    catalog: Path = ROOT / 'models' / 'catalog.json'
    signal: tuple[float, ...] = (1.0, 2.0, 3.0)
    seed: int = 21
    max_iterations: int = 10
    tolerance: float = 1e-8

    def __post_init__(self):
        if not self.levels or any(type(n) is not int or n < 1 for n in self.levels):
            raise ValueError('levels must be positive integers')
        if len(set(self.levels)) != len(self.levels):
            raise ValueError('levels cannot repeat')
        for key, minimum, maximum in (('repeats', 1, 100), ('workers', 1, 32),
                                       ('queue_capacity', 1, 100000), ('seed', 0, 2**32-1),
                                       ('max_iterations', 1, 10)):
            value = getattr(self, key)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f'invalid {key}')
        if self.queue_capacity < CLIENT_COUNT * max(self.levels):
            raise ValueError('queue_capacity must hold all submitted signals; avoid saturation bias')
        for key in ('interval', 'drain_timeout', 'http_timeout', 'tolerance'):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'invalid {key}')
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError('model_id is required')
        if not self.signal or any(type(x) not in (float, int) or not math.isfinite(x) for x in self.signal):
            raise ValueError('signal must contain finite real values')


def make_plan(settings: Settings) -> dict:
    """Freeze a single ordered set of different signals for *all* runs.

    Each level uses the same prefix per client. The plan's self-hash detects
    accidental changes before benchmark execution or later replay.
    """
    rng = random.Random(settings.seed)
    entries = []
    for client in range(CLIENT_COUNT):
        for pos in range(max(settings.levels)):
            # A fixed small perturbation of the common base signal ensures
            # different numerical inputs without changing the model size.
            vec = [float(x + rng.uniform(-0.01, 0.01) * max(abs(x), 1.0))
                   for x in settings.signal]
            entries.append({'client_id': f'task21-client-{client+1}',
                            'signal_id': f'task21-c{client+1}-s{pos+1}',
                            'position': pos + 1, 'signal': vec})
    body = {'schema_version': 1, 'model_id': settings.model_id,
            'clients': CLIENT_COUNT, 'max_signals_per_client': max(settings.levels),
            'seed': settings.seed, 'max_iterations': settings.max_iterations,
            'tolerance': settings.tolerance,
            'base_signal_sha256': _digest(list(settings.signal)), 'entries': entries}
    return {**body, 'sha256': _digest(body)}


def validate_plan(plan: dict, settings: Settings) -> None:
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        raise ValueError('Invalid plan format')
    body = {k: v for k, v in plan.items() if k != 'sha256'}
    if _digest(body) != plan.get('sha256'):
        raise ValueError('Plan SHA256 mismatch')
    if (plan.get('model_id') != settings.model_id or plan.get('clients') != CLIENT_COUNT
            or plan.get('max_signals_per_client') != max(settings.levels)
            or plan.get('max_iterations') != settings.max_iterations
            or plan.get('tolerance') != settings.tolerance
            or plan.get('seed') != settings.seed
            or plan.get('base_signal_sha256') != _digest(list(settings.signal))):
        raise ValueError('Plan does not match benchmark parameters')
    entries = plan.get('entries')
    if not isinstance(entries, list) or len(entries) != CLIENT_COUNT * max(settings.levels):
        raise ValueError('Plan contains incorrect number of signals')
    expected = {(f'task21-client-{c+1}', i) for c in range(CLIENT_COUNT)
                for i in range(1, max(settings.levels) + 1)}
    found = set()
    ids = set()
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError('Malformed plan entry')
        key = (item.get('client_id'), item.get('position'))
        signal_id = item.get('signal_id')
        signal = item.get('signal')
        if key in found or key not in expected or not isinstance(signal_id, str) or signal_id in ids:
            raise ValueError('Repeated or unexpected plan entry')
        if not isinstance(signal, list) or len(signal) != len(settings.signal) or any(
                type(v) not in (float, int) or not math.isfinite(v) for v in signal):
            raise ValueError('Invalid plan signal')
        found.add(key)
        ids.add(signal_id)
    if found != expected:
        raise ValueError('Missing plan entries')


def selected_entries(plan: dict, level: int, client: int) -> list[dict]:
    cid = f'task21-client-{client + 1}'
    return sorted((e for e in plan['entries'] if e['client_id'] == cid and e['position'] <= level),
                  key=lambda e: e['position'])


def _get(url: str, path: str, timeout: float) -> dict:
    response = requests.get(url + path, timeout=timeout)
    response.raise_for_status()
    obj = response.json()
    if not isinstance(obj, dict):
        raise ValueError(f'Invalid response: {path}')
    return obj


def _send_client(url: str, entries: list[dict], settings: Settings, gate: Barrier) -> list[dict]:
    records = []
    with requests.Session() as session:
        gate.wait(timeout=15)
        for item in entries:
            body = {'client_id': item['client_id'], 'signal_id': item['signal_id'],
                    'model_id': settings.model_id, 'signal': item['signal'], 'algorithm': 'cgnr',
                    'parameters': {'max_iterations': settings.max_iterations,
                                   'tolerance': settings.tolerance}}
            before = time.monotonic()
            status = None
            request_id = None
            error_code = None
            exception = None
            try:
                response = session.post(url + '/reconstructions', json=body,
                                        timeout=settings.http_timeout)
                status = response.status_code
                try:
                    payload = response.json()
                except ValueError:
                    payload = {}
                if status == 202:
                    request_id = payload.get('request_id')
                    if not isinstance(request_id, str) or not request_id:
                        request_id = None
                        error_code = 'INVALID_REQUEST_ID'
                else:
                    error_code = (payload.get('error') or {}).get('code', 'HTTP_ERROR')
            except requests.RequestException as exc:
                exception = f'{type(exc).__name__}: {str(exc)[:200]}'
            records.append({'client_id': item['client_id'], 'signal_id': item['signal_id'],
                            'position': item['position'], 'http_status': status,
                            'request_id': request_id, 'error_code': error_code,
                            'transport_error': exception,
                            'http_latency_ms': (time.monotonic() - before) * 1000})
    return records


def _monitor(url: str, pid: int, directory: Path, settings: Settings,
             ready: Event, stop: Event) -> dict:
    """Sample until the observed workload has drained, never for a fixed 30 s.

    Collector.run() uses a fixed window; this wrapper uses the same TASK-16
    exporter with a workload-bound window so short/long cases stay complete.
    """
    collector = Collector(url, pid, directory, interval=settings.interval,
                          timeout=settings.http_timeout)
    collector.initial = collector._get('/metrics')
    start_utc = datetime.now(timezone.utc) - timedelta(seconds=1)
    started = time.monotonic()
    collector._sample(started, started, collector.initial)
    ready.set()
    while not stop.wait(settings.interval):
        now = time.monotonic()
        collector._sample(started, now, collector._get('/metrics'))
    collector.final = collector._get('/metrics')
    ended = time.monotonic()
    collector._sample(started, ended, collector.final)
    end_utc = datetime.now(timezone.utc) + timedelta(seconds=1)
    jobs = collector._get('/metrics/reconstructions')
    if (jobs.get('implementation') != collector.initial.get('implementation')
            or jobs.get('schema_version') != 1):
        raise ValueError('TASK-16 collector implementation changed during run')
    reconstructions = []
    for job in jobs.get('reconstructions', []):
        if job.get('status') not in ('completed', 'failed') or not job.get('finished_at'):
            continue
        stamp = utc_parse(job['finished_at'])
        if start_utc <= stamp <= end_utc:
            reconstructions.append({key: job.get(key) for key in RECONSTRUCTION_COLUMNS})
    return {'summary': collector.export(ended - started, reconstructions),
            'samples': collector.samples}


def _weighted_cpu(samples: list[dict]) -> float | None:
    # CPU% from psutil is the average *over the preceding interval*.
    numerator = denominator = 0.0
    previous = None
    for sample in samples:
        now = float(sample['elapsed_ms'])
        if previous is not None and sample.get('cpu_percent') is not None:
            dt = now - previous
            if dt > 0:
                numerator += float(sample['cpu_percent']) * dt
                denominator += dt
        previous = now
    return numerator / denominator if denominator else None


def run_one(implementation: str, url: str, pid: int, settings: Settings,
            plan: dict, level: int, repeat: int, directory: Path,
            *, process=None) -> dict:
    """Measure exactly the same signal IDs and vectors in both servers."""
    validate_plan(plan, settings)
    directory.mkdir(parents=True, exist_ok=True)
    model = _get(url, '/models/' + quote(settings.model_id, safe=''), settings.http_timeout)
    if model.get('rows') != len(settings.signal):
        raise ValueError('Signal dimensions do not match server model')
    before = _get(url, '/queue', settings.http_timeout)
    if (before.get('implementation') != implementation
            or before.get('queue_size') != 0 or before.get('running_count') != 0):
        raise ValueError('Expected a fresh idle server')
    ready, stop = Event(), Event()
    monitor_result = None
    with ThreadPoolExecutor(max_workers=1) as observer:
        future = observer.submit(_monitor, url, pid, directory, settings, ready, stop)
        if not ready.wait(timeout=min(20.0, settings.http_timeout * 3)):
            if future.done():
                future.result()
            stop.set()
            raise TimeoutError('Monitoring did not start')
        try:
            gate = Barrier(CLIENT_COUNT + 1)
            with ThreadPoolExecutor(max_workers=CLIENT_COUNT) as senders:
                work = [senders.submit(_send_client, url, selected_entries(plan, level, c),
                                       settings, gate) for c in range(CLIENT_COUNT)]
                gate.wait(timeout=15)
                first_submission = time.monotonic()
                requests_rows = [row for item in work for row in item.result()]
                submission_ms = (time.monotonic() - first_submission) * 1000
            accepted = sum(r['http_status'] == 202 and r['request_id'] is not None
                           for r in requests_rows)
            finished_before = before['completed_count'] + before['failed_count']
            deadline = time.monotonic() + settings.drain_timeout
            final = before
            drained = False
            while time.monotonic() < deadline:
                if process is not None and process.poll() is not None:
                    break
                try:
                    final = _get(url, '/queue', settings.http_timeout)
                except requests.RequestException:
                    break
                finished = final['completed_count'] + final['failed_count'] - finished_before
                if (final['queue_size'] == 0 and final['running_count'] == 0
                        and finished >= accepted):
                    drained = True
                    break
                time.sleep(min(settings.interval, 0.05))
        finally:
            stop.set()
            monitor_result = future.result()
    summary, samples = monitor_result['summary'], monitor_result['samples']
    # Ensure exported job IDs and signal IDs match the exact fixed workload;
    # counts alone cannot detect a duplicated or unrelated metrics record.
    with (directory / 'reconstructions.csv').open(newline='', encoding='utf-8') as stream:
        exported_rows = list(csv.DictReader(stream))
    exported = {r['request_id']: (r['client_id'], r['signal_id']) for r in exported_rows}
    expected_ids = {r['request_id']: (r['client_id'], r['signal_id'])
                    for r in requests_rows if r['request_id']}
    job_ids_match = (len(exported) == len(exported_rows) == len(expected_ids)
                     and exported == expected_ids)
    try:
        health = _get(url, '/health', settings.http_timeout).get('status') == 'ok'
    except requests.RequestException:
        health = False
    planned = level * CLIENT_COUNT
    rejected = sum(r['http_status'] == 503 for r in requests_rows)
    transport = sum(bool(r['transport_error']) for r in requests_rows)
    unexpected = planned - accepted - rejected - transport
    completed = final['completed_count'] - before['completed_count']
    failed = final['failed_count'] - before['failed_count']
    ids = [r['request_id'] for r in requests_rows if r['request_id']]
    valid = bool(drained and health and (process is None or process.poll() is None)
                 and accepted == planned and rejected == transport == unexpected == failed == 0
                 and final['accepted_count'] - before['accepted_count'] == planned
                 and completed == planned and len(ids) == len(set(ids))
                 and job_ids_match and summary['workload_complete'] is True)
    durations = queue_durations(samples)
    observed = math.fsum(durations.values())
    queue_mean = (math.fsum(q * ms for q, ms in durations.items()) / observed
                  if observed else None)
    queue_mode = min(durations, key=lambda q: (-durations[q], q)) if observed else None
    result = {'implementation': implementation, 'signals_per_client': level, 'repeat': repeat,
              'planned': planned, 'accepted': accepted, 'rejected': rejected,
              'failed': failed, 'transport_errors': transport, 'unexpected': unexpected,
              'finished': completed, 'workload_complete': summary['workload_complete'],
              'valid': valid,
              'total_execution_time_ms': summary['total_execution_time_ms'] if valid else None,
              'mean_reconstruction_time_ms': summary['mean_reconstruction_time_ms'] if valid else None,
              'cpu_mean_percent': _weighted_cpu(samples),
              'cpu_peak_percent': summary['peak_cpu_percent'],
              'rss_peak_bytes': summary['peak_memory_rss_bytes'],
              'queue_mean': queue_mean, 'queue_mode': queue_mode,
              'queue_peak': final.get('queue_peak'),
              'observation_time_ms': summary['monitoring_window_ms'],
              'submission_time_ms': submission_ms, 'plan_sha256': plan['sha256'],
              'reason': None if valid else 'Not all jobs accepted and finished within observation',
              'clients': CLIENT_COUNT, 'workers': settings.workers,
              'queue_capacity': settings.queue_capacity,
              'exported_ids_match': job_ids_match}
    with (directory / 'requests.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(requests_rows[0]))
        writer.writeheader()
        writer.writerows(requests_rows)
    (directory / 'scenario.json').write_text(json.dumps(result, indent=2,
                                    ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
    return result


def _median(rows: list[dict], field: str) -> float | None:
    values = [r[field] for r in rows if r.get(field) is not None]
    return statistics.median(values) if values else None


def aggregate(results: list[dict], levels: tuple[int, ...], repeats: int) -> list[dict]:
    """A comparative row is valid only when all expected pairs are complete."""
    output = []
    for level in levels:
        by_version = {v: [r for r in results if r['signals_per_client'] == level
                          and r['implementation'] == v] for v in ('python', 'cpp')}
        py, cpp = by_version['python'], by_version['cpp']
        valid_py = {r['repeat'] for r in py if r['valid']}
        valid_cpp = {r['repeat'] for r in cpp if r['valid']}
        expected = set(range(1, repeats + 1))
        paired = expected & valid_py & valid_cpp
        eligible = len(paired) == repeats and len(py) == len(cpp) == repeats
        paired_py = [r for r in py if r['repeat'] in paired]
        paired_cpp = [r for r in cpp if r['repeat'] in paired]
        py_time = _median(paired_py, 'total_execution_time_ms') if eligible else None
        cpp_time = _median(paired_cpp, 'total_execution_time_ms') if eligible else None
        output.append({
            'signals_per_client': level, 'total_signals': CLIENT_COUNT * level,
            'repeats_required': repeats, 'paired_valid': len(paired), 'comparable': eligible,
            'python_median_total_ms': py_time,
            'cpp_median_total_ms': cpp_time,
            'python_median_reconstruction_ms': _median(paired_py, 'mean_reconstruction_time_ms') if eligible else None,
            'cpp_median_reconstruction_ms': _median(paired_cpp, 'mean_reconstruction_time_ms') if eligible else None,
            'python_median_cpu_percent': _median(paired_py, 'cpu_mean_percent') if eligible else None,
            'cpp_median_cpu_percent': _median(paired_cpp, 'cpu_mean_percent') if eligible else None,
            'python_median_rss_mib': (_median(paired_py, 'rss_peak_bytes') / 2**20) if eligible else None,
            'cpp_median_rss_mib': (_median(paired_cpp, 'rss_peak_bytes') / 2**20) if eligible else None,
            'python_median_queue': _median(paired_py, 'queue_mean') if eligible else None,
            'cpp_median_queue': _median(paired_cpp, 'queue_mean') if eligible else None,
            'python_peak_queue_max': max((r['queue_peak'] for r in paired_py if r.get('queue_peak') is not None), default=None) if eligible else None,
            'cpp_peak_queue_max': max((r['queue_peak'] for r in paired_cpp if r.get('queue_peak') is not None), default=None) if eligible else None,
            'speedup_cpp_vs_python': (py_time / cpp_time if py_time is not None and cpp_time is not None and cpp_time > 0 else None),
        })
    return output


def _cell(val):
    if val is None:
        return 'N/D'
    if isinstance(val, float):
        return f'{val:.3f}'
    return str(val)


def render_report(report: dict) -> str:
    c = report['config']
    env = report['environment']
    lines = [
        '# TASK-21 — Benchmarks comparativos Python × C++', '',
        f"Gerado em: `{report['generated_at_utc']}`.",
        f"Plano de sinais SHA-256: `{report['plan_sha256']}`.", '',
        '## Ambiente e protocolo', '',
        f"- SO: `{env['system']}`; Python: `{env['python']}`; CPUs lógicas: `{env['logical_cpu_count']}`; RAM: `{env['total_ram_bytes']}` bytes",
        f"- Modelo: `{c['model_id']}`; dimensão do sinal: `{c['signal_size']}`; seed: `{c['seed']}`",
        f"- Três clientes sincronizados; {c['repeats']} repetições por implementação/carga, com ordem alternada",
        f"- Cargas: {c['levels']} sinais/cliente; workers: {c['workers']}; fila: {c['queue_capacity']}",
        f"- CGNR: {c['max_iterations']} iterações, tolerância {c['tolerance']}; BLAS threads por processo: 1",
        f"- Amostragem: {c['interval']} s; timeout de drenagem: {c['drain_timeout']} s",
        '- Cada execução inicia um servidor novo, e usa **o mesmo conjunto de sinais e a mesma ordem por cliente**.',
        '- São elegíveis à comparação somente execuções com todas as respostas HTTP 202, sem falhas e com exportação completa.',
        '', '## Medianas por carga (somente pares completos)', '',
    ]
    cols = ['total_signals', 'paired_valid', 'comparable', 'python_median_total_ms',
            'cpp_median_total_ms', 'speedup_cpp_vs_python', 'python_median_cpu_percent',
            'cpp_median_cpu_percent', 'python_median_rss_mib', 'cpp_median_rss_mib',
            'python_median_queue', 'cpp_median_queue']
    lines.extend(['| ' + ' | '.join(cols) + ' |', '| ' + ' | '.join(['---'] * len(cols)) + ' |'])
    for row in report['comparison']:
        lines.append('| ' + ' | '.join(_cell(row[k]) for k in cols) + ' |')
    lines += ['', '## Todas as execuções', '']
    rawcols = ['implementation', 'signals_per_client', 'repeat', 'accepted', 'rejected',
               'finished', 'valid', 'total_execution_time_ms', 'cpu_mean_percent',
               'rss_peak_bytes', 'queue_peak']
    lines.extend(['| ' + ' | '.join(rawcols) + ' |', '| ' + ' | '.join(['---'] * len(rawcols)) + ' |'])
    for row in report['runs']:
        lines.append('| ' + ' | '.join(_cell(row.get(k)) for k in rawcols) + ' |')
    lines += ['', '## Interpretação e limitações', '',
              '- Speedup = mediana do tempo total Python / mediana do tempo total C++; >1 favorece C++.',
              '- Tempos refletem a janela de aceitação até última conclusão de cada carga, e não a inicialização do servidor.',
              '- CPU% da TASK-16 soma processo e filhos: 100% corresponde a um núcleo lógico; pode ultrapassar 100%.',
              '- RSS é soma do processo e descendentes (páginas compartilhadas podem ser contadas várias vezes).',
              '- Fila média é ponderada pela duração entre amostras (retenção à esquerda), não pelo número de amostras.',
              '- CPU média é ponderada pelos intervalos observados; picos de duração curta podem escapar à amostragem.',
              '- Resultados não garantem causalidade nem superioridade geral: hardware, bibliotecas, agendamento e concorrência variam.',
              '- `N/D` significa dado ausente ou rodada não comparável, nunca tempo zero.',
              '', '## Evidências', '',
              '- `plan.json` contém os vetores enviados e o hash verificável.',
              '- `runs/<implementação>/level-*/repeat-*/` contém `requests.csv`, `scenario.json`, `summary.json`, `samples.csv`, `reconstructions.csv` e `server.log`.',
              '- `comparison.json` e `comparison.csv` guardam resultados estruturados para a TASK-22.',
              '']
    if report['errors']:
        lines += ['## Erros de execução', ''] + ['- ' + s for s in report['errors']] + ['']
    return '\n'.join(lines)


def write_report(results: list[dict], settings: Settings, output: Path, plan_sha: str,
                 errors: list[str]) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    summary = aggregate(results, settings.levels, settings.repeats)
    report = {'schema_version': 1, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
              'plan_sha256': plan_sha,
              'environment': {'system': platform.platform(), 'python': sys.version.split()[0],
                              'logical_cpu_count': psutil.cpu_count(logical=True),
                              'total_ram_bytes': psutil.virtual_memory().total},
              'config': {'levels': list(settings.levels), 'repeats': settings.repeats,
                         'workers': settings.workers, 'queue_capacity': settings.queue_capacity,
                         'interval': settings.interval, 'drain_timeout': settings.drain_timeout,
                         'http_timeout': settings.http_timeout,
                         'model_id': settings.model_id, 'signal_size': len(settings.signal),
                         'seed': settings.seed, 'max_iterations': settings.max_iterations,
                         'tolerance': settings.tolerance,
                         'catalog': str(settings.catalog.resolve())},
              'runs': results, 'comparison': summary, 'errors': errors}
    (output / 'comparison.json').write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                      allow_nan=False) + '\n', encoding='utf-8')
    with (output / 'comparison.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    with (output / 'runs.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=SAMPLE_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    (output / 'comparison.md').write_text(render_report(report), encoding='utf-8')
    return report


def _read_signal(path: Path) -> tuple[float, ...]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list):
        raise ValueError('Signal file must contain a JSON vector')
    return tuple(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--model-id', required=True)
    parser.add_argument('--signal-file', type=Path, required=True)
    parser.add_argument('--levels', nargs='+', type=int, default=[15, 30, 60])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--queue-capacity', type=int, default=256)
    parser.add_argument('--sample-interval', type=float, default=0.025)
    parser.add_argument('--drain-timeout', type=float, default=120.0)
    parser.add_argument('--http-timeout', type=float, default=5.0)
    parser.add_argument('--seed', type=int, default=21)
    parser.add_argument('--max-iterations', type=int, default=10)
    parser.add_argument('--tolerance', type=float, default=1e-8)
    parser.add_argument('--cpp-bin', type=Path, default=ROOT / 'build' / 'reconstruction_server')
    parser.add_argument('--output', type=Path, default=Path('results/task21/benchmark'))
    parser.add_argument('--reuse-plan', type=Path, help='Replay an existing plan.json after SHA256 validation')
    parser.add_argument('--plan-only', action='store_true', help='Generate a plan without starting servers')
    args = parser.parse_args()
    settings = Settings(levels=tuple(args.levels), repeats=args.repeats, workers=args.workers,
                        queue_capacity=args.queue_capacity, interval=args.sample_interval,
                        drain_timeout=args.drain_timeout, http_timeout=args.http_timeout,
                        model_id=args.model_id, catalog=args.catalog,
                        signal=_read_signal(args.signal_file), seed=args.seed,
                        max_iterations=args.max_iterations, tolerance=args.tolerance)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    if args.reuse_plan:
        plan = json.loads(args.reuse_plan.read_text(encoding='utf-8'))
        validate_plan(plan, settings)
    else:
        plan = make_plan(settings)
    (output / 'plan.json').write_text(json.dumps(plan, indent=2, ensure_ascii=False,
                                                allow_nan=False) + '\n', encoding='utf-8')
    print('Plan SHA256:', plan['sha256'], flush=True)
    if args.plan_only:
        return 0
    if not args.cpp_bin.is_file():
        parser.error(f'C++ server binary not found: {args.cpp_bin} (build using CMake)')
    sat = SaturationSettings(levels=settings.levels, workers=settings.workers,
                             queue_capacity=settings.queue_capacity, interval=settings.interval,
                             monitor_seconds=5.0, drain_timeout=settings.drain_timeout,
                             http_timeout=settings.http_timeout, model_id=settings.model_id,
                             catalog=settings.catalog, signal=settings.signal,
                             max_iterations=settings.max_iterations, tolerance=settings.tolerance,
                             seed=settings.seed)
    results = []
    errors = []
    # Alternates server order between repetitions to reduce warm-up/order bias.
    for level in settings.levels:
        for rep in range(1, settings.repeats + 1):
            order = ('python', 'cpp') if rep % 2 else ('cpp', 'python')
            for implementation in order:
                directory = output / 'runs' / implementation / f'level-{level}' / f'repeat-{rep}'
                try:
                    with launch_server(implementation, sat, directory, cpp_bin=args.cpp_bin) as (url, pid, proc):
                        result = run_one(implementation, url, pid, settings, plan, level, rep,
                                         directory, process=proc)
                    results.append(result)
                    print(f'{implementation} level={level} repeat={rep}: '
                          f"accepted={result['accepted']}/{result['planned']} "
                          f"valid={result['valid']} time_ms={result['total_execution_time_ms']}",
                          flush=True)
                except Exception as exc:
                    msg = f'{implementation} level={level} repeat={rep}: {type(exc).__name__}: {exc}'
                    errors.append(msg)
                    print(msg, file=sys.stderr, flush=True)
                write_report(results, settings, output, plan['sha256'], errors)
    report = write_report(results, settings, output, plan['sha256'], errors)
    print('Report:', output / 'comparison.md')
    return 0 if not errors and all(x['comparable'] for x in report['comparison']) else 1


if __name__ == '__main__':
    raise SystemExit(main())

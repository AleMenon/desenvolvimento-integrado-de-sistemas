"""TASK-17: estatísticas offline dos exports da TASK-16."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path

from monitoring.collect import utc_parse


def number(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{name} deve ser finito e não negativo')
    return value


def count(value, name):
    if isinstance(value, bool):
        raise ValueError(f'{name} deve ser inteiro, não booleano')
    value = number(value, name)
    if not value.is_integer():
        raise ValueError(f'{name} deve ser inteiro')
    return int(value)


def queue_durations(samples):
    """Retenção à esquerda: q[i] vale de t[i] até t[i+1]."""
    durations = defaultdict(float)
    previous = None
    for sample in samples:
        t = number(sample['elapsed_ms'], 'elapsed_ms')
        q = count(sample['queue_size'], 'queue_size')
        if previous is not None:
            pt, pq = previous
            if t <= pt:
                raise ValueError('Amostras devem ter tempos estritamente crescentes')
            durations[pq] += t - pt
        previous = t, q
    return dict(durations)


def read_run(directory):
    directory = Path(directory)
    summary = json.loads((directory / 'summary.json').read_text())
    if summary.get('schema_version') != 1 or summary.get('implementation') not in ('python', 'cpp'):
        raise ValueError('Versão ou implementação desconhecida')
    with (directory / 'samples.csv').open(newline='') as stream:
        durations = queue_durations(list(csv.DictReader(stream)))
    with (directory / 'reconstructions.csv').open(newline='') as stream:
        jobs = list(csv.DictReader(stream))
    ids = [job['request_id'] for job in jobs]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        raise ValueError('Reconstruções duplicadas ou sem request_id')
    if any(j['status'] not in ('completed', 'failed') for j in jobs):
        raise ValueError('Export deve conter apenas tarefas finalizadas')
    completed = count(summary['completed_count'], 'completed_count')
    failed = count(summary['failed_count'], 'failed_count')
    received = count(summary['received_count'], 'received_count')
    times = []
    missing_duration = False
    for job in jobs:
        if job['status'] != 'completed':
            continue
        raw_duration = job['execution_time_ms']
        if raw_duration is None or not str(raw_duration).strip():
            missing_duration = True
        else:
            times.append(number(raw_duration, 'execution_time_ms'))
    records_complete = (not missing_duration and len(times) == completed and
                        sum(j['status'] == 'failed' for j in jobs) == failed)
    complete = (summary.get('workload_complete') is True and records_complete
                and received == completed + failed and received > 0
                and count(summary['inflight_at_start'], 'inflight_at_start') == 0
                and count(summary['unfinished_count_at_end'], 'unfinished_count_at_end') == 0)
    total = None
    dates = []
    for job in jobs:
        created, finished = utc_parse(job['created_at']), utc_parse(job['finished_at'])
        if created.tzinfo is None or finished.tzinfo is None or finished < created:
            raise ValueError('Horários inválidos ou sem fuso')
        dates.append((created, finished))
    if complete:
        total = (max(end for _, end in dates) - min(start for start, _ in dates)).total_seconds() * 1000
    return dict(implementation=summary['implementation'], runs=1,
                completed_count=completed, failed_count=failed,
                workload_complete=complete, total_execution_time_ms=total,
                _duration_sum=math.fsum(times), _times_complete=records_complete,
                _queue_durations=durations, source=str(directory.resolve()))


def consolidate(runs):
    """Agrupa ensaios por versão, sem calcular média de médias."""
    grouped = defaultdict(list)
    for run in runs:
        grouped[run['implementation']].append(run)
    rows = []
    for version, group in sorted(grouped.items()):
        completed = sum(r['completed_count'] for r in group)
        histogram = defaultdict(float)
        for run in group:
            for size, duration in run['_queue_durations'].items():
                histogram[size] += duration
        observed = math.fsum(histogram.values())
        complete = all(r['workload_complete'] for r in group)
        rows.append(dict(
            implementation=version, runs=len(group),
            completed_count=completed,
            failed_count=sum(r['failed_count'] for r in group),
            workload_complete=complete,
            total_execution_time_ms=math.fsum(r['total_execution_time_ms'] for r in group) if complete else None,
            mean_reconstruction_time_ms=(math.fsum(r['_duration_sum'] for r in group) / completed
                if completed and all(r['_times_complete'] for r in group) else None),
            queue_mean=(math.fsum(q*t for q,t in histogram.items()) / observed if observed else None),
            queue_mode=(min(histogram, key=lambda q: (-histogram[q], q)) if observed else None),
            queue_observation_time_ms=observed,
        ))
    return rows


def export_comparison(directories, output):
    paths = [Path(p).resolve() for p in directories]
    if not paths or len(paths) != len(set(paths)):
        raise ValueError('Informe diretórios distintos de ensaios')
    runs = [read_run(p) for p in paths]
    rows = consolidate(runs)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'comparison.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / 'comparison.json').write_text(json.dumps(
        {'schema_version': 1, 'sources': [str(p) for p in paths],
         'queue_method': 'sampled_left_hold_time_weighted', 'versions': rows,
         'runs': [dict(source=r['source'], **consolidate([r])[0]) for r in runs]},
        indent=2, allow_nan=False) + '\n', encoding='utf-8')
    keys = list(rows[0])
    lines = ['| ' + ' | '.join(keys) + ' |', '| ' + ' | '.join(['---']*len(keys)) + ' |']
    lines += ['| ' + ' | '.join('N/D' if row[k] is None else str(row[k]) for k in keys) + ' |' for row in rows]
    (output / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    export_comparison(args.directories, args.output)


if __name__ == '__main__':
    main()

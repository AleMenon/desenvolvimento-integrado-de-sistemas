import csv
import json
import os
import threading
import time

import pytest

from monitoring.collect import Collector
from monitoring.statistics import count, queue_durations, export_comparison, consolidate
from server.python.performance_metrics import PerformanceMetrics


def write_run(path, version='python', times=(10, 30), complete=True):
    path.mkdir()
    summary = dict(schema_version=1, implementation=version, completed_count=len(times),
                   failed_count=1, received_count=len(times)+1, workload_complete=complete,
                   inflight_at_start=0, unfinished_count_at_end=0)
    (path/'summary.json').write_text(json.dumps(summary))
    with (path/'samples.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['elapsed_ms', 'queue_size'])
        writer.writeheader()
        writer.writerows([dict(elapsed_ms=t, queue_size=q) for t,q in [(0,0),(100,2),(400,0)]])
    with (path/'reconstructions.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['request_id','status','created_at','finished_at','execution_time_ms'])
        writer.writeheader()
        for i, duration in enumerate([*times, 999]):
            writer.writerow(dict(request_id=str(i), status='completed' if i<len(times) else 'failed',
                                 created_at='2026-01-01T00:00:00Z', finished_at='2026-01-01T00:00:02Z',
                                 execution_time_ms=duration))
    return path


def test_export_and_weighted_aggregation(tmp_path):
    a = write_run(tmp_path/'a')
    b = write_run(tmp_path/'b', times=(100,))
    c = write_run(tmp_path/'c', version='cpp', times=(5,))
    rows = export_comparison([a,b,c], tmp_path/'out')
    cpp, python = rows
    assert python['completed_count'] == 3
    assert python['failed_count'] == 2
    assert python['mean_reconstruction_time_ms'] == pytest.approx(140/3)
    assert python['total_execution_time_ms'] == 4000
    assert python['queue_mean'] == 1.5
    assert python['queue_mode'] == 2
    assert cpp['mean_reconstruction_time_ms'] == 5
    report = json.loads((tmp_path/'out/comparison.json').read_text())
    assert report['versions'] == rows
    assert len(report['runs']) == 3
    with (tmp_path/'out/comparison.csv').open() as f:
        assert len(list(csv.DictReader(f))) == 2
    assert 'python' in (tmp_path/'out/comparison.md').read_text()


def test_partial_run_does_not_claim_total(tmp_path):
    a = write_run(tmp_path/'a', complete=False)
    row = export_comparison([a], tmp_path/'out')[0]
    assert row['total_execution_time_ms'] is None
    assert not row['workload_complete']
    assert row['completed_count'] == 2
    assert row['mean_reconstruction_time_ms'] == 20


def test_no_completed_images(tmp_path):
    a = write_run(tmp_path/'a', times=())
    row = export_comparison([a], tmp_path/'out')[0]
    assert row['completed_count'] == 0
    assert row['mean_reconstruction_time_ms'] is None
    assert row['total_execution_time_ms'] == 2000  # Uma falha ainda consumiu tempo.


def test_queue_tie_empty_and_single():
    assert queue_durations([]) == {}
    assert queue_durations([dict(elapsed_ms=0,queue_size=0)]) == {}
    hist = queue_durations([dict(elapsed_ms=t,queue_size=q) for t,q in [(0,2),(5,0),(10,7)]])
    run = dict(implementation='cpp', completed_count=0, failed_count=0,
               workload_complete=False, total_execution_time_ms=None,
               _duration_sum=0, _times_complete=True, _queue_durations=hist)
    assert consolidate([run])[0]['queue_mode'] == 0
    run['_queue_durations'] = {}
    assert consolidate([run])[0]['queue_mean'] is None
    assert consolidate([run])[0]['queue_mode'] is None


@pytest.mark.parametrize('samples', [
    [dict(elapsed_ms=0,queue_size=-1)],
    [dict(elapsed_ms=float('nan'),queue_size=0)],
    [dict(elapsed_ms=0,queue_size=1.5)],
    [dict(elapsed_ms=1,queue_size=0),dict(elapsed_ms=0,queue_size=0)],
    [dict(elapsed_ms=1,queue_size=0),dict(elapsed_ms=1,queue_size=0)],
])
def test_invalid_samples(samples):
    with pytest.raises(ValueError): queue_durations(samples)


def test_duplicate_input_and_missing_records(tmp_path):
    a = write_run(tmp_path/'a')
    with pytest.raises(ValueError): export_comparison([a,a], tmp_path/'out')
    summary = json.loads((a/'summary.json').read_text())
    summary['completed_count'] = 3
    (a/'summary.json').write_text(json.dumps(summary))
    row = export_comparison([a], tmp_path/'out')[0]
    assert row['mean_reconstruction_time_ms'] is None
    assert row['total_execution_time_ms'] is None


@pytest.mark.parametrize('value', [True, False])
def test_count_rejects_boolean(value):
    with pytest.raises(ValueError, match='booleano'):
        count(value, 'completed_count')
    with pytest.raises(ValueError, match='booleano'):
        queue_durations([{'elapsed_ms': 0, 'queue_size': value}])


def test_read_run_rejects_boolean_counters_in_summary(tmp_path):
    path = write_run(tmp_path / 'run')
    summary_path = path / 'summary.json'
    summary = json.loads(summary_path.read_text())
    summary['completed_count'] = True
    summary_path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match='booleano'):
        export_comparison([path], tmp_path / 'out')


def test_missing_completed_duration_returns_null_statistics(tmp_path):
    path = write_run(tmp_path / 'run')
    jobs_path = path / 'reconstructions.csv'
    with jobs_path.open(newline='') as f:
        jobs = list(csv.DictReader(f))
    # Exports TASK-16 usam uma string vazia para campos None no CSV.
    jobs[0]['execution_time_ms'] = ''
    with jobs_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(jobs[0]))
        writer.writeheader()
        writer.writerows(jobs)

    row = export_comparison([path], tmp_path / 'out')[0]
    assert row['completed_count'] == 2
    assert row['failed_count'] == 1
    assert row['workload_complete'] is False
    assert row['mean_reconstruction_time_ms'] is None
    assert row['total_execution_time_ms'] is None
    assert row['queue_mean'] == 1.5
    assert row['queue_mode'] == 2
    report = json.loads((tmp_path / 'out' / 'comparison.json').read_text())
    assert report['versions'][0]['mean_reconstruction_time_ms'] is None


def test_missing_failed_duration_remains_acceptable(tmp_path):
    path = write_run(tmp_path / 'run')
    jobs_path = path / 'reconstructions.csv'
    with jobs_path.open(newline='') as f:
        jobs = list(csv.DictReader(f))
    jobs[-1]['execution_time_ms'] = ''
    with jobs_path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(jobs[0]))
        writer.writeheader()
        writer.writerows(jobs)
    row = export_comparison([path], tmp_path / 'out')[0]
    assert row['workload_complete'] is True
    assert row['mean_reconstruction_time_ms'] == 20


def test_task16_collector_export_round_trip(tmp_path):
    """Confere a leitura dos arquivos produzidos por Collector.run()."""
    folders = []
    for implementation in ('python', 'cpp'):
        metrics = PerformanceMetrics(implementation)
        output = tmp_path / implementation
        collector = Collector('http://127.0.0.1:1', os.getpid(), output, interval=0.01)
        collector._get = lambda endpoint, registry=metrics: (
            registry.snapshot() if endpoint == '/metrics' else registry.reconstructions()
        )

        def workload():
            deadline = time.monotonic() + 3
            while (collector.initial is None or not collector.samples) and time.monotonic() < deadline:
                time.sleep(0.001)
            assert collector.initial is not None and collector.samples
            metrics.accepted('req-1', 'client', 'signal', 'model')
            time.sleep(0.02)
            metrics.started('req-1')
            time.sleep(0.02)
            metrics.finished('req-1', success=True, iterations=1,
                             converged=True, stop_reason='tolerance_reached',
                             execution_time_ms=12.5)

        thread = threading.Thread(target=workload)
        thread.start()
        try:
            summary = collector.run(duration=0.25)
        finally:
            thread.join(timeout=5)
        assert not thread.is_alive()
        assert summary['workload_complete'] is True
        assert summary['completed_count'] == 1
        for name in ('summary.json', 'samples.csv', 'reconstructions.csv'):
            assert (output / name).is_file()
        folders.append(output)

    rows = export_comparison(folders, tmp_path / 'comparison')
    assert [row['implementation'] for row in rows] == ['cpp', 'python']
    assert all(row['completed_count'] == 1 for row in rows)
    assert all(row['failed_count'] == 0 for row in rows)
    assert all(row['workload_complete'] is True for row in rows)
    assert all(row['mean_reconstruction_time_ms'] == 12.5 for row in rows)
    assert all(row['total_execution_time_ms'] is not None for row in rows)
    assert all(row['queue_observation_time_ms'] > 0 for row in rows)

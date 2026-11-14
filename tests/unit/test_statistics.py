import csv
import json
import pytest
from monitoring.statistics import queue_durations, export_comparison, consolidate


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

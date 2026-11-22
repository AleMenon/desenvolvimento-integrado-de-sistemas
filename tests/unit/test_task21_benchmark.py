"""TASK-21 reproducible plan, paired analysis and report serialization."""
import copy
import csv
import json

import pytest

from monitoring.benchmark import (Settings, aggregate, make_plan, render_report,
                                  selected_entries, validate_plan, write_report,
                                  _weighted_cpu, _digest)


def settings(**overrides):
    base = dict(levels=(2, 3), repeats=2, queue_capacity=9,
                model_id='demo_identity_3', signal=(1., 2., 3.))
    base.update(overrides)
    return Settings(**base)


def test_fixed_plan_replay_across_versions_levels_and_repetitions():
    config = settings(seed=18)
    plan = make_plan(config)
    assert make_plan(config) == plan
    validate_plan(plan, config)
    assert plan['sha256'] != make_plan(settings(seed=19))['sha256']
    assert len(plan['entries']) == 9
    assert len({e['signal_id'] for e in plan['entries']}) == 9
    assert len({tuple(e['signal']) for e in plan['entries']}) == 9
    assert selected_entries(plan, 2, 0) == selected_entries(plan, 3, 0)[:2]
    assert selected_entries(plan, 3, 2)[-1]['signal_id'] == 'task21-c3-s3'


def test_replay_refuses_tampering_and_incompatible_parameters():
    s = settings()
    plan = make_plan(s)
    tampered = copy.deepcopy(plan)
    tampered['entries'][0]['signal'][0] += 1
    with pytest.raises(ValueError, match='SHA256'):
        validate_plan(tampered, s)
    tampered = copy.deepcopy(plan)
    tampered['entries'][0]['position'] = 2
    tampered['sha256'] = _digest(
        {k:v for k,v in tampered.items() if k != 'sha256'})
    with pytest.raises(ValueError, match='Repeated'):
        validate_plan(tampered, s)
    with pytest.raises(ValueError, match='parameters'):
        validate_plan(plan, settings(signal=(3., 2., 1.)))


@pytest.mark.parametrize('kwargs', [
    {'levels': ()}, {'levels': (2, 2)}, {'levels': (True,)},
    {'repeats': 0}, {'repeats': True}, {'workers': 33},
    {'queue_capacity': 8}, {'queue_capacity': True},
    {'interval': 0}, {'http_timeout': float('nan')},
    {'drain_timeout': float('inf')}, {'signal': (True,)},
    {'seed': -1}, {'max_iterations': 11}, {'tolerance': 0},
    {'model_id': ''},
])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        settings(**kwargs)


def row(version, repeat, level=2, total=100, *, valid=True):
    return dict(implementation=version, signals_per_client=level, repeat=repeat,
                valid=valid, total_execution_time_ms=total if valid else None,
                mean_reconstruction_time_ms=total / 2 if valid else None,
                cpu_mean_percent=50, rss_peak_bytes=2**20, queue_mean=1.25,
                queue_peak=2, accepted=level*3, rejected=0, finished=level*3)


def test_paired_medians_and_speedup():
    results = [row('python', 1, total=160), row('cpp', 1, total=80),
               row('python', 2, total=200), row('cpp', 2, total=100)]
    output = aggregate(results, (2,), 2)[0]
    assert output['comparable'] is True
    assert output['paired_valid'] == 2
    assert output['python_median_total_ms'] == 180
    assert output['cpp_median_total_ms'] == 90
    assert output['speedup_cpp_vs_python'] == 2
    assert output['python_median_rss_mib'] == 1


def test_missing_or_partial_pair_marked_incomparable():
    results = [row('python', 1), row('cpp', 1), row('python', 2),
               row('cpp', 2, valid=False)]
    summary = aggregate(results, (2,), 2)[0]
    assert summary['paired_valid'] == 1
    assert not summary['comparable']
    assert summary['python_median_total_ms'] is None
    assert summary['speedup_cpp_vs_python'] is None


def test_weighted_cpu_uses_elapsed_time_not_simple_mean():
    samples = [{'elapsed_ms': 0, 'cpu_percent': None},
               {'elapsed_ms': 10, 'cpu_percent': 100},
               {'elapsed_ms': 110, 'cpu_percent': 20}]
    assert _weighted_cpu(samples) == pytest.approx(3000 / 110)
    assert _weighted_cpu([samples[0]]) is None


def test_report_exports_csv_json_markdown(tmp_path):
    config = settings(levels=(2,))
    results = [row('python',1), row('cpp',1), row('python',2),row('cpp',2)]
    report = write_report(results, config, tmp_path, 'a'*64, [])
    assert report['comparison'][0]['comparable']
    assert 'TASK-21' in (tmp_path / 'comparison.md').read_text()
    assert '| N/D |' not in render_report(report)
    assert json.loads((tmp_path / 'comparison.json').read_text())['plan_sha256'] == 'a'*64
    assert len(list(csv.DictReader((tmp_path / 'runs.csv').open()))) == 4
    assert len(list(csv.DictReader((tmp_path / 'comparison.csv').open()))) == 1

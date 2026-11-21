"""TASK-18 review #45: evidence publishing and correct interpretation."""
import csv
import json

import pytest

from monitoring.saturation import Settings, write_report
from monitoring.publish_task18_results import EVIDENCE_FILES, publish


def make_run(path, model_id='task18_dense_512'):
    settings = Settings(model_id=model_id, levels=(15, 30, 60))
    results = []
    counts = {'python': [6, 11, 19], 'cpp': [44, 89, 179]}
    for impl in ('python', 'cpp'):
        for level, accepted in zip((15, 30, 60), counts[impl]):
            row = dict(implementation=impl, clients=3, signals_per_client=level,
                       attempted=3*level, accepted_http_202=accepted,
                       queue_full_http_503=3*level-accepted, unexpected_responses=0,
                       transport_errors=0, queue_peak=8,
                       peak_cpu_percent=715.0 if impl == 'python' else 70.,
                       peak_memory_rss_bytes=1000000,
                       workload_complete=False, stable=True,
                       observations='Apenas fixture de teste; não é medição real')
            results.append(row)
            d = path / impl / f'signals-{level}-per-client'
            d.mkdir(parents=True)
            (d / 'scenario.json').write_text(json.dumps(row))
            (d / 'summary.json').write_text(json.dumps({'implementation': impl, 'schema_version': 1}))
            with (d / 'requests.csv').open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=['http_status', 'request_id', 'error_code'])
                writer.writeheader()
                for i in range(accepted):
                    writer.writerow(dict(http_status=202, request_id=f'req-{i}', error_code=''))
                for i in range(3*level-accepted):
                    writer.writerow(dict(http_status=503, request_id='', error_code='QUEUE_FULL'))
            (d / 'samples.csv').write_text('queue_size,elapsed_ms\n0,0\n1,10\n')
            (d / 'reconstructions.csv').write_text('request_id,status\n')
    write_report(results, path, settings)
    return path


def test_dense_model_report_and_cpu_methodology(tmp_path):
    report = (make_run(tmp_path / 'run') / 'report.md').read_text()
    assert 'matriz **sintética densa**' in report
    assert 'matriz identidade 3' not in report
    assert '715%' in report and '7,15 núcleos' in report
    assert 'não imagens/s' in report
    assert '| 45 | 6 / 39 | 44 / 1 |' in report
    assert '## Configuração do experimento' in report


def test_identity_report_is_conditional(tmp_path):
    report = (make_run(tmp_path / 'run', 'demo_identity_3') / 'report.md').read_text()
    assert 'matriz identidade 3 × 3' in report
    assert 'matriz **sintética densa**' not in report


def test_publish_keeps_raw_evidence(tmp_path):
    src = make_run(tmp_path / 'run')
    out = tmp_path / 'published'
    report_path = publish(src, out)
    assert report_path.exists()
    assert 'task18_dense_512' in report_path.read_text()
    assert (out / 'report.json').is_file()
    assert (out / 'manifest.json').is_file()
    assert len(json.loads((out / 'manifest.json').read_text())['files_sha256']) == 33
    for impl in ('cpp', 'python'):
        for n in (15, 30, 60):
            folder = out / 'evidence' / impl / f'signals-{n}-per-client'
            assert all((folder / name).is_file() for name in EVIDENCE_FILES)
    with pytest.raises(FileExistsError):
        publish(src, out)


def test_missing_evidence_is_rejected(tmp_path):
    src = make_run(tmp_path / 'run')
    (src / 'cpp' / 'signals-30-per-client' / 'requests.csv').unlink()
    with pytest.raises(FileNotFoundError, match='Missing raw evidence'):
        publish(src, tmp_path / 'out')


def test_tampered_scenario_is_rejected(tmp_path):
    src = make_run(tmp_path / 'run')
    p = src / 'cpp' / 'signals-15-per-client' / 'scenario.json'
    data = json.loads(p.read_text())
    data['accepted_http_202'] += 1
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Mismatch'):
        publish(src, tmp_path / 'out')


def test_incomplete_campaign_is_rejected(tmp_path):
    src = make_run(tmp_path / 'run')
    p = src / 'report.json'
    data = json.loads(p.read_text())
    data['results'].pop()
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Incomplete or duplicate'):
        publish(src, tmp_path / 'out')

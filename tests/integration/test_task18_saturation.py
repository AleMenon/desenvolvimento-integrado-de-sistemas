"""TASK-18 runner contract tests; real-server runs are documented separately.

This fixture deliberately slows the in-memory worker. It validates backpressure
and the reporting workflow, NOT real Python/C++ reconstruction performance.
"""

import csv
import json
import os
import queue
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from monitoring.saturation import CLIENTS, Settings, run_scenario, write_report
from server.python.performance_metrics import PerformanceMetrics


@contextmanager
def fake_reconstruction_server(*, queue_capacity=64, worker_delay=0.002):
    registry = PerformanceMetrics('python')
    tasks = queue.Queue(maxsize=queue_capacity)
    lock = threading.Lock()
    counters = {'accepted': 0, 'rejected': 0, 'peak': 0, 'completed': 0}
    finished = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health':
                return self.respond(200, {'status': 'ok'})
            if self.path == '/models/demo_identity_3':
                return self.respond(200, {'model_id': 'demo_identity_3', 'rows': 3})
            if self.path == '/metrics':
                return self.respond(200, registry.snapshot())
            if self.path == '/metrics/reconstructions':
                return self.respond(200, registry.reconstructions())
            if self.path == '/queue':
                with lock:
                    data = {'implementation': 'python', 'queue_capacity': queue_capacity,
                            'queue_size': tasks.qsize(), 'running_count': registry.snapshot()['running_count'],
                            'queue_peak': counters['peak'], 'accepted_count': counters['accepted'],
                            'completed_count': counters['completed'], 'failed_count': 0,
                            'rejected_count': counters['rejected'], 'evicted_count': 0}
                return self.respond(200, data)
            self.respond(404, {'error': {'code': 'NOT_FOUND'}})

        def do_POST(self):
            if self.path != '/reconstructions':
                return self.respond(404, {'error': {'code': 'NOT_FOUND'}})
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:
                request_id = f'req-{counters["accepted"] + 1}'
                if tasks.full():
                    counters['rejected'] += 1
                    return self.respond(503, {'error': {'code': 'QUEUE_FULL'}})
                registry.accepted(request_id, body['client_id'], body['signal_id'], body['model_id'])
                tasks.put_nowait(request_id)
                counters['accepted'] += 1
                counters['peak'] = max(counters['peak'], tasks.qsize())
            self.respond(202, {'request_id': request_id, 'status': 'queued'})

        def log_message(self, *args):
            pass

    def work():
        while not finished.is_set() or not tasks.empty():
            try:
                request_id = tasks.get(timeout=0.05)
            except queue.Empty:
                continue
            with lock:
                registry.started(request_id)
            time.sleep(worker_delay)
            with lock:
                registry.finished(request_id, success=True, iterations=1,
                                  converged=True, stop_reason='tolerance_reached',
                                  execution_time_ms=worker_delay * 1000)
                counters['completed'] += 1
            tasks.task_done()

    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    web_thread = threading.Thread(target=http.serve_forever, daemon=True)
    worker_thread = threading.Thread(target=work, daemon=True)
    web_thread.start()
    worker_thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}'
    finally:
        finished.set()
        tasks.join()
        worker_thread.join(timeout=5)
        http.shutdown()
        http.server_close()
        web_thread.join(timeout=5)


def test_three_clients_export_all_task16_files_without_loss(tmp_path):
    settings = Settings(levels=(5,), queue_capacity=64, monitor_seconds=0.65,
                        drain_timeout=3, interval=0.025)
    with fake_reconstruction_server(queue_capacity=64) as url:
        result = run_scenario('python', url, os.getpid(), 5, settings, tmp_path)
    assert result['attempted'] == CLIENTS * 5
    assert result['accepted_http_202'] == 15
    assert result['server_finished_delta'] == 15
    assert result['queue_full_http_503'] == 0
    assert result['stable'] is True
    assert result['workload_complete'] is True
    for name in ('summary.json', 'samples.csv', 'reconstructions.csv', 'requests.csv', 'scenario.json'):
        assert (tmp_path / name).is_file()
    with (tmp_path / 'requests.csv').open() as f:
        attempts = list(csv.DictReader(f))
    assert len({r['client_id'] for r in attempts}) == 3
    assert len({r['signal_id'] for r in attempts}) == 15
    assert len({r['request_id'] for r in attempts}) == 15
    summary = json.loads((tmp_path / 'summary.json').read_text())
    assert summary['implementation'] == 'python'
    assert summary['completed_count'] == 15
    assert summary['peak_memory_rss_bytes'] > 0
    write_report([result], tmp_path / 'overview', settings)
    assert (tmp_path / 'overview' / 'report.md').is_file()
    assert len(list(csv.DictReader((tmp_path / 'overview' / 'report.csv').open()))) == 1


def test_three_clients_generate_queue_full_without_losing_accepted(tmp_path):
    settings = Settings(levels=(5,), queue_capacity=1, monitor_seconds=1.1,
                        drain_timeout=3, interval=0.02)
    with fake_reconstruction_server(queue_capacity=1, worker_delay=0.12) as url:
        result = run_scenario('python', url, os.getpid(), 5, settings, tmp_path)
    assert result['attempted'] == 15
    assert result['queue_full_http_503'] > 0
    assert result['queue_peak'] == 1
    assert result['server_accepted_delta'] == result['accepted_http_202']
    assert result['server_finished_delta'] == result['accepted_http_202']
    assert result['stable'] is True
    assert 'Saturação' in result['observations']


@pytest.mark.parametrize('kwargs', [
    {'levels': (0,)}, {'levels': (5,5)}, {'workers': 0},
    {'workers': 33}, {'queue_capacity': 0}, {'interval': 0},
    {'monitor_seconds': float('inf')}, {'jitter_ms': -1},
    {'signal': (True, 2.0, 3.0)}, {'max_iterations': 11},
])
def test_invalid_experiment_configuration(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_dense_fixture_is_reproducible(tmp_path):
    import numpy as np
    from monitoring.generate_task18_fixture import generate

    first, signal_path = generate(8, tmp_path / 'first', seed=18)
    second, other_signal = generate(8, tmp_path / 'second', seed=18)
    assert json.loads(signal_path.read_text()) == json.loads(other_signal.read_text())
    models = json.loads(first.read_text())['models']
    assert models[0]['image_shape'] == [1, 8]
    matrix = np.loadtxt(first.parent / models[0]['file'], delimiter=',')
    assert matrix.shape == (8, 8)
    assert np.linalg.cond(matrix) < 5
    assert (second.parent / models[0]['file']).read_bytes() == (first.parent / models[0]['file']).read_bytes()


def test_real_servers_with_three_clients(tmp_path):
    """Real Python server: 3 clients x 15 signals, no accepted tasks lost."""
    from pathlib import Path
    from monitoring.saturation import ROOT, launch_server
    if not (ROOT / 'server' / 'python' / 'reconstruction_server.py').is_file():
        pytest.skip('real Python server not available in this isolated checkout')
    settings = Settings(levels=(15,), workers=2, queue_capacity=64,
                        monitor_seconds=2.0, drain_timeout=15, interval=0.03)
    with launch_server('python', settings, tmp_path) as (url, pid, process):
        result = run_scenario('python', url, pid, 15, settings, tmp_path, process=process)
    assert result['attempted'] == 45
    assert result['server_accepted_delta'] == 45
    assert result['server_finished_delta'] == 45
    assert result['queue_full_http_503'] == 0
    assert result['workload_complete'] is True
    assert result['stable'] is True


def test_real_cpp_server_with_three_clients(tmp_path):
    """Optional real C++ server test (requires native CMake build)."""
    from monitoring.saturation import ROOT, launch_server
    if not (ROOT / 'build' / 'reconstruction_server').is_file():
        pytest.skip('compile C++ reconstruction_server first')
    settings = Settings(levels=(15,), workers=2, queue_capacity=64,
                        monitor_seconds=2.0, drain_timeout=15, interval=0.03)
    with launch_server('cpp', settings, tmp_path) as (url, pid, process):
        result = run_scenario('cpp', url, pid, 15, settings, tmp_path, process=process)
    assert result['attempted'] == 45
    assert result['server_accepted_delta'] == 45
    assert result['server_finished_delta'] == 45
    assert result['queue_full_http_503'] == 0
    assert result['workload_complete'] is True
    assert result['stable'] is True

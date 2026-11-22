"""TASK-21 real Collector HTTP protocol exercised against an in-process fake.

Not a benchmark of real CGNR. Tests only the client/collector/report contract.
"""
import json
import os
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from monitoring.benchmark import Settings, make_plan, run_one
from server.python.performance_metrics import PerformanceMetrics


@contextmanager
def fake_metrics_server(*, reject_after=None):
    registry = PerformanceMetrics('python')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                payload = {'status': 'ok'}
            elif self.path == '/queue':
                m = registry.snapshot()
                payload = {'implementation': 'python', 'queue_size': m['queue_size'],
                           'running_count': m['running_count'],
                           'accepted_count': m['received_count'],
                           'completed_count': m['completed_count'],
                           'failed_count': m['failed_count'], 'queue_peak': 3}
            elif self.path == '/models/demo_identity_3':
                payload = {'rows': 3}
            elif self.path == '/metrics':
                payload = registry.snapshot()
            elif self.path == '/metrics/reconstructions':
                payload = registry.reconstructions()
            else:
                self.send_error(404)
                return
            self._send(200, payload)

        def do_POST(self):
            if self.path != '/reconstructions':
                self.send_error(404)
                return
            n = int(self.headers['Content-Length'])
            request = json.loads(self.rfile.read(n))
            unique = request['signal_id']
            if reject_after is not None and registry.snapshot()['received_count'] >= reject_after:
                self._send(503, {'error': {'code': 'QUEUE_FULL'}})
                return
            registry.accepted(unique, request['client_id'], request['signal_id'], request['model_id'])
            registry.started(unique)
            time.sleep(0.001)
            registry.finished(unique, success=True, execution_time_ms=1.0)
            self._send(202, {'request_id': unique, 'status': 'queued'})

        def _send(self, status, value):
            raw = json.dumps(value).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{http.server_port}'
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=3)


def test_three_clients_fixed_inputs_and_task16_exports(tmp_path):
    settings = Settings(levels=(3,), repeats=1, workers=1, queue_capacity=9,
                        interval=0.01, drain_timeout=3, http_timeout=3,
                        model_id='demo_identity_3', signal=(1., 2., 3.))
    plan = make_plan(settings)
    with fake_metrics_server() as url:
        output = run_one('python', url, os.getpid(), settings, plan, 3, 1, tmp_path)
    assert output['accepted'] == output['finished'] == 9
    assert output['rejected'] == output['failed'] == output['unexpected'] == 0
    assert output['valid'] is True
    assert output['workload_complete'] is True
    assert output['total_execution_time_ms'] is not None
    assert output['queue_mean'] is not None
    for filename in ('summary.json', 'samples.csv', 'reconstructions.csv',
                     'requests.csv', 'scenario.json'):
        assert (tmp_path / filename).is_file(), filename
    import csv
    with (tmp_path / 'requests.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 9
    assert {r['client_id'] for r in rows} == {f'task21-client-{n}' for n in range(1, 4)}
    assert {r['signal_id'] for r in rows} == {x['signal_id'] for x in plan['entries']}


def test_rejections_are_not_misreported_as_benchmark_timings(tmp_path):
    settings = Settings(levels=(2,), repeats=1, workers=1, queue_capacity=6,
                        interval=0.01, drain_timeout=3, http_timeout=3,
                        model_id='demo_identity_3', signal=(1., 2., 3.))
    with fake_metrics_server(reject_after=2) as url:
        result = run_one('python', url, os.getpid(), settings, make_plan(settings),
                         2, 1, tmp_path)
    assert result['accepted'] == result['finished'] == 2
    assert result['rejected'] == 4
    assert result['valid'] is False
    assert result['total_execution_time_ms'] is None

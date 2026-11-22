"""Optional TASK-21 smoke on actual Python/C++ servers (build C++ first)."""
import os

import pytest

from monitoring.benchmark import Settings, make_plan, run_one
from monitoring.saturation import ROOT, Settings as SaturationSettings, launch_server


@pytest.mark.parametrize('implementation', ['python', 'cpp'])
def test_real_server_completes_fixed_benchmark(tmp_path, implementation):
    if implementation == 'python' and not (ROOT / 'server/python/reconstruction_server.py').is_file():
        pytest.skip('full project checkout required')
    if implementation == 'cpp' and not (ROOT / 'build/reconstruction_server').is_file():
        pytest.skip('C++ binary missing: build with CMake before testing')
    bench = Settings(levels=(2,), repeats=1, workers=1, queue_capacity=6,
                     interval=0.02, drain_timeout=12, http_timeout=4,
                     model_id='demo_identity_3', catalog=ROOT / 'models/catalog.json',
                     signal=(1., 2., 3.))
    sat = SaturationSettings(levels=bench.levels, workers=bench.workers,
                             queue_capacity=bench.queue_capacity,
                             interval=bench.interval, monitor_seconds=5,
                             drain_timeout=bench.drain_timeout,
                             http_timeout=bench.http_timeout,
                             model_id=bench.model_id, catalog=bench.catalog,
                             signal=bench.signal)
    with launch_server(implementation, sat, tmp_path) as (url, pid, proc):
        result = run_one(implementation, url, pid, bench, make_plan(bench),
                         2, 1, tmp_path, process=proc)
    assert result['valid']
    assert result['accepted'] == 6
    assert result['finished'] == 6
    assert result['workload_complete']
    assert result['exported_ids_match']

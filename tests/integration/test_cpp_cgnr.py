"""Compara implementações reais com entradas e parâmetros idênticos."""
import os
from pathlib import Path
import subprocess
import numpy as np
import pytest
from server.python.cgnr import cgnr

ROOT = Path(__file__).resolve().parents[2]


def cases():
    yield np.eye(3), np.array([2., 4., 6.])
    yield np.diag([2., 3., 4.]), np.array([2., 6., 12.])
    yield np.array([[1., 0.], [0., 1.], [1., 1.]]), np.array([2., 3., 5.])
    yield np.ones((3, 1)), np.array([1., 2., 3.])
    yield np.eye(3), np.zeros(3)
    yield np.zeros((3, 2)), np.ones(3)
    yield np.array([[1., 1.], [2., 2.]]), np.array([2., 4.])
    yield np.array([[1., 0., 0.], [0., 1., 0.]]), np.array([2., 3.])
    yield np.diag(np.arange(1., 21.)), np.ones(20)
    rng = np.random.default_rng(42)
    yield rng.normal(size=(25, 15)), rng.normal(size=25)
    yield 1e-20 * np.eye(3), 1e-20 * np.array([1., 2., 3.])


@pytest.mark.parametrize('h,g', list(cases()))
@pytest.mark.parametrize('limit', [1, 10])
def test_cpp_python_cgnr(h, g, limit):
    runner = Path(os.environ.get('CGNR_RUNNER', ROOT / 'build/cgnr_runner'))
    assert runner.is_file(), 'Compile cgnr_runner com CMake antes de executar pytest.'
    tolerance = 1e-8
    payload = f'{h.shape[0]} {h.shape[1]} {tolerance} {limit}\n'
    payload += ' '.join(format(v, '.17g') for v in h.flat) + '\n'
    payload += ' '.join(format(v, '.17g') for v in g) + '\n'
    process = subprocess.run([str(runner)], input=payload, text=True,
                             capture_output=True, check=True, timeout=30)
    metadata, solution, history = process.stdout.splitlines()
    iterations, converged, residual, normal = map(float, metadata.split())
    expected = cgnr(h, g, tolerance=tolerance, max_iterations=limit)
    assert iterations == expected['iterations']
    assert 0 <= iterations <= limit <= 10
    assert bool(converged) == expected['converged']
    for actual, reference in [
        (np.array(solution.split(), dtype=float), expected['solution']),
        (np.array(history.split(), dtype=float), expected['residual_history']),
        (float(residual), expected['residual_norm']),
        (float(normal), expected['normal_residual_norm']),
    ]:
        assert np.shape(actual) == np.shape(reference)
        assert np.all(np.isfinite(actual))
        np.testing.assert_allclose(actual, reference, rtol=1e-8, atol=1e-10,
                                   equal_nan=False)

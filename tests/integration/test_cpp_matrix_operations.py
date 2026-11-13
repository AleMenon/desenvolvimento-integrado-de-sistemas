"""Compara a biblioteca C++ com a implementação real da TASK-04."""
import io
import os
from pathlib import Path
import subprocess
import zipfile

import numpy as np
import pytest

from server.python import matrix_operations as python_ops

ROOT = Path(__file__).resolve().parents[2]
RTOL = ATOL = 1e-12


@pytest.fixture(scope="module")
def runner():
    path = Path(os.environ.get(
        "MATRIX_OPERATIONS_RUNNER", ROOT / "build" / "matrix_operations_runner"
    )).resolve()
    if not path.is_file():
        pytest.fail("Compile matrix_operations_runner com CMake antes dos testes.")
    return path


def serialize(value):
    array = np.asarray(value, dtype=np.float64)
    if array.ndim == 1:
        array = array[:, None]
    return (f"{array.shape[0]} {array.shape[1]}\n"
            + " ".join(format(x, ".17g") for x in array.flat) + "\n")


def cpp(runner, operation, m, other):
    payload = operation + "\n" + serialize(m)
    payload += f"{other:.17g}\n" if operation == "scalar" else serialize(other)
    return subprocess.run(
        [str(runner)], input=payload, text=True, capture_output=True, timeout=30,
    )


def python(operation, m, other):
    if operation == "scalar":
        return python_ops.multiply_scalar_matrix(other, m)
    if operation == "matrices":
        return python_ops.multiply_matrices(m, other)
    if operation == "matrix_vector":
        return python_ops.multiply_matrix_vector(m, other)
    return python_ops.multiply_vector_matrix(other, m)


def compare(runner, operation, m, other):
    expected = python(operation, m, other)
    process = cpp(runner, operation, m, other)
    assert process.returncode == 0, process.stderr
    header, values = process.stdout.split("\n", 1)
    shape = tuple(map(int, header.split()))
    actual = np.array(values.split(), dtype=np.float64).reshape(shape)
    if expected.ndim == 1:
        assert shape[1] == 1
        actual = actual[:, 0]
    assert actual.shape == expected.shape
    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL, equal_nan=False)
    return actual


# Mesmas entradas dos testes unitários da TASK-04.
@pytest.mark.parametrize("operation,m,other", [
    ("matrices", [[1, 2], [3, 4]], [[5, 6], [7, 8]]),
    ("matrices", [[1, 2, 3], [4, 5, 6]], [[1, 2], [3, 4], [5, 6]]),
    ("scalar", [[1, 2], [3, 4]], 3),
    ("scalar", [[1, 2], [3, 4]], -2),
    ("scalar", [[1, 2], [3, 4]], 0),
    ("matrix_vector", [[1, 2], [3, 4]], [5, 6]),
    ("matrix_vector", [[1, 2, 3], [4, 5, 6]], [1, 2, 3]),
    ("vector_matrix", [[1, 2, 3], [4, 5, 6]], [0.25, -2]),
    ("matrices", [[0.1]], [[-0.3]]),
    ("matrices", [[1, -1]], [[1], [1]]),
])
def test_same_inputs(runner, operation, m, other):
    compare(runner, operation, m, other)


@pytest.mark.parametrize("shape", [(1, 7, 3), (7, 1, 4), (32, 64, 17)])
def test_rectangular_random(runner, shape):
    rng = np.random.default_rng(42)
    rows, inner, cols = shape
    m = rng.normal(size=(rows, inner))
    compare(runner, "matrices", m, rng.normal(size=(inner, cols)))
    compare(runner, "scalar", m, -0.125)
    compare(runner, "matrix_vector", m, rng.normal(size=inner))
    compare(runner, "vector_matrix", m, rng.normal(size=rows))


@pytest.mark.parametrize("operation,m,other", [
    ("matrices", np.ones((2, 3)), np.ones((2, 2))),
    ("matrix_vector", np.ones((2, 3)), np.ones(2)),
    ("vector_matrix", np.ones((2, 4)), np.ones(3)),
    ("matrices", np.empty((0, 2)), np.ones((2, 2))),
    ("matrices", np.ones((2, 2)), np.empty((2, 0))),
    ("scalar", np.empty((2, 0)), 2),
    ("matrix_vector", np.ones((2, 2)), np.empty(0)),
    ("vector_matrix", np.ones((2, 2)), np.empty(0)),
    *[(op, [[value]], [1]) for op in ("matrix_vector", "vector_matrix")
      for value in (np.nan, np.inf, -np.inf)],
    *[(op, [[1]], [value]) for op in ("matrix_vector", "vector_matrix")
      for value in (np.nan, np.inf, -np.inf)],
    *[("scalar", [[1]], value) for value in (np.nan, np.inf, -np.inf)],
    ("scalar", [[np.nan]], 2),
    ("matrices", [[np.nan]], [[1]]),
    ("matrices", [[1]], [[np.inf]]),
])
def test_same_rejections(runner, operation, m, other):
    with pytest.raises(ValueError):
        python(operation, m, other)
    process = cpp(runner, operation, m, other)
    assert process.returncode == 2, process.stderr
    assert process.stderr.strip()


def test_professor_data(runner):
    with zipfile.ZipFile(ROOT / "tests/fixtures/Dados.zip") as archive:
        data = {name: np.loadtxt(io.BytesIO(archive.read(name)), delimiter=";")
                for name in ("M.csv", "N.csv", "a.csv", "MN.csv", "aM.csv")}
    m, n, a = data["M.csv"], data["N.csv"], data["a.csv"]
    result = compare(runner, "matrices", m, n)
    np.testing.assert_array_equal(result, data["MN.csv"])
    result = compare(runner, "vector_matrix", m, a)
    # O arquivo oficial aM tem arredondamento: somente esta comparação usa 0.005.
    np.testing.assert_allclose(result, data["aM.csv"], rtol=0, atol=0.005)
    compare(runner, "matrix_vector", m, a)
    compare(runner, "scalar", m, -2.5)

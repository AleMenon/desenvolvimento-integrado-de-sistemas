import numpy as np


def test_numpy_matrix_vector_product():
    matrix = np.array([
        [1.0, 2.0],
        [3.0, 4.0],
    ], dtype=np.float64)

    vector = np.array([1.0, 1.0], dtype=np.float64)

    result = matrix @ vector

    expected = np.array([3.0, 7.0])

    np.testing.assert_allclose(result, expected)


def test_numpy_float64():
    vector = np.array([1.0, 2.0], dtype=np.float64)

    assert vector.dtype == np.float64
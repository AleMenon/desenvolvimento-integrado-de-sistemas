"""Testes unitários das operações matriciais — TASK-04."""

import numpy as np
import pytest

from server.python.matrix_operations import (
    multiply_matrices,
    multiply_scalar_matrix,
    multiply_matrix_vector,
)


# ============================================================
# 1. multiplicação matriz-matriz
# ============================================================


def test_multiply_matrices():
    """Verifica a multiplicação de duas matrizes 2x2."""

    m = [[1, 2], [3, 4]]
    n = [[5, 6], [7, 8]]

    expected = [[19, 22], [43, 50]]

    result = multiply_matrices(m, n)

    np.testing.assert_allclose(result, expected)


def test_multiply_rectangular_matrices():
    """Verifica a multiplicação de matrizes retangulares."""

    m = [[1, 2, 3], [4, 5, 6]]
    n = [[1, 2], [3, 4], [5, 6]]

    expected = [[22, 28], [49, 64]]

    result = multiply_matrices(m, n)

    np.testing.assert_allclose(result, expected)


def test_multiply_matrices_invalid_dimensions():
    """Verifica a rejeição de matrizes incompatíveis."""

    m = np.ones((2, 3))
    n = np.ones((2, 2))

    with pytest.raises(ValueError, match="Dimensões incompatíveis"):
        multiply_matrices(m, n)


# ============================================================
# 2. multiplicação escalar-matriz
# ============================================================


def test_multiply_scalar_matrix():
    """Verifica a multiplicação por um escalar positivo."""

    a = 3
    m = [[1, 2], [3, 4]]

    expected = [[3, 6], [9, 12]]

    result = multiply_scalar_matrix(a, m)

    np.testing.assert_allclose(result, expected)


def test_multiply_scalar_matrix_negative():
    """Verifica a multiplicação por um escalar negativo."""

    a = -2
    m = [[1, 2], [3, 4]]

    expected = [[-2, -4], [-6, -8]]

    result = multiply_scalar_matrix(a, m)

    np.testing.assert_allclose(result, expected)


def test_multiply_scalar_matrix_zero():
    """Verifica a multiplicação por zero."""

    m = [[1, 2], [3, 4]]

    result = multiply_scalar_matrix(0, m)

    np.testing.assert_allclose(result, np.zeros((2, 2)))


# ============================================================
# 3. multiplicação matriz-vetor
# ============================================================


def test_multiply_matrix_vector():
    """Verifica a multiplicação de matriz por vetor."""

    m = [[1, 2], [3, 4]]
    a = [5, 6]

    expected = [17, 39]

    result = multiply_matrix_vector(m, a)

    np.testing.assert_allclose(result, expected)


def test_multiply_rectangular_matrix_vector():
    """Verifica matriz retangular multiplicada por vetor."""

    m = [[1, 2, 3], [4, 5, 6]]
    a = [1, 2, 3]

    expected = [14, 32]

    result = multiply_matrix_vector(m, a)

    np.testing.assert_allclose(result, expected)


def test_multiply_matrix_vector_invalid_dimensions():
    """Verifica dimensões incompatíveis entre matriz e vetor."""

    m = np.ones((2, 3))
    a = np.ones(2)

    with pytest.raises(ValueError, match="Dimensões incompatíveis"):
        multiply_matrix_vector(m, a)


# ============================================================
# 4. validação de entradas
# ============================================================


def test_invalid_matrix_dimension():
    """Rejeita um vetor quando uma matriz é esperada."""

    m = [1, 2, 3]
    n = [[1, 2], [3, 4]]

    with pytest.raises(ValueError):
        multiply_matrices(m, n)


def test_empty_matrix():
    """Rejeita matrizes vazias."""

    m = []
    n = [[1, 2], [3, 4]]

    with pytest.raises(ValueError):
        multiply_matrices(m, n)


def test_nan_values():
    """Rejeita matrizes que contêm NaN."""

    m = [[1, np.nan], [3, 4]]
    n = [[1, 2], [3, 4]]

    with pytest.raises(ValueError, match="NaN ou infinitos"):
        multiply_matrices(m, n)


def test_infinite_values():
    """Rejeita matrizes com valores infinitos."""

    m = [[1, np.inf], [3, 4]]
    n = [[1, 2], [3, 4]]

    with pytest.raises(ValueError, match="NaN ou infinitos"):
        multiply_matrices(m, n)


def test_infinite_scalar():
    """Rejeita escalares infinitos."""

    m = [[1, 2], [3, 4]]

    with pytest.raises(ValueError, match="finito"):
        multiply_scalar_matrix(np.inf, m)


def test_invalid_scalar_type():
    """Rejeita escalares não numéricos."""

    m = [[1, 2], [3, 4]]

    with pytest.raises(TypeError):
        multiply_scalar_matrix("abc", m)


# ============================================================
# 5. precisão e integridade dos dados
# ============================================================


def test_float64_precision():
    """Verifica se o resultado utiliza float64."""

    m = [[1, 2], [3, 4]]
    a = [5, 6]

    result = multiply_matrix_vector(m, a)

    assert result.dtype == np.float64


def test_input_matrix_not_modified():
    """Verifica que a matriz original não é modificada."""

    m = np.array([[1, 2], [3, 4]], dtype=np.float64)

    original = m.copy()

    multiply_scalar_matrix(3, m)

    np.testing.assert_array_equal(m, original)


def test_matrix_product_shape():
    """Verifica as dimensões da matriz resultante."""

    m = np.ones((2, 3))
    n = np.ones((3, 4))

    result = multiply_matrices(m, n)

    assert result.shape == (2, 4)


def test_matrix_vector_product_shape():
    """Verifica as dimensões do vetor resultante."""

    m = np.ones((3, 5))
    a = np.ones(5)

    result = multiply_matrix_vector(m, a)

    assert result.shape == (3,)

# ============================================================
# 6. validação com dados disponibilizados pelo professor
# ============================================================

import io
import zipfile
from pathlib import Path

from server.python.matrix_operations import multiply_vector_matrix


DADOS_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "Dados.zip"
)


def load_professor_data(filename):
    """Carrega um CSV diretamente do arquivo Dados.zip."""

    with zipfile.ZipFile(DADOS_PATH) as archive:
        content = archive.read(filename)

    return np.loadtxt(
        io.BytesIO(content),
        delimiter=";",
        dtype=np.float64,
    )


def test_professor_matrix_multiplication():
    """Valida MN com o resultado oficial do professor."""

    m = load_professor_data("M.csv")
    n = load_professor_data("N.csv")
    expected = load_professor_data("MN.csv")

    result = multiply_matrices(m, n)

    np.testing.assert_array_equal(result, expected)


def test_professor_vector_matrix_multiplication():
    """Valida aM com o resultado oficial arredondado."""

    a = load_professor_data("a.csv")
    m = load_professor_data("M.csv")
    expected = load_professor_data("aM.csv")

    result = multiply_vector_matrix(a, m)

    np.testing.assert_allclose(
        result,
        expected,
        rtol=0,
        atol=0.005,
    )


def test_professor_matrix_vector_multiplication():
    """Valida Ma usando os dados oficiais de M e a."""

    m = load_professor_data("M.csv")
    a = load_professor_data("a.csv")

    result = multiply_matrix_vector(m, a)

    expected = np.array([
        sum(m[i, j] * a[j] for j in range(m.shape[1]))
        for i in range(m.shape[0])
    ])

    np.testing.assert_allclose(
        result,
        expected,
        rtol=1e-12,
        atol=1e-12,
    )


def test_vector_matrix_invalid_dimensions():
    """Verifica dimensões incompatíveis em aM."""

    a = np.ones(3)
    m = np.ones((2, 4))

    with pytest.raises(ValueError, match="Dimensões incompatíveis"):
        multiply_vector_matrix(a, m)
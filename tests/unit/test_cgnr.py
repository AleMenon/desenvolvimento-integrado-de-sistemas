"""Testes unitários do algoritmo CGNR — TASK-06."""

import numpy as np
import pytest

from server.python.cgnr import cgnr


def test_cgnr_identity_matrix():
    """Resolve um sistema com matriz identidade."""

    h = np.eye(3)
    g = np.array([2.0, 4.0, 6.0])

    result = cgnr(h, g)

    np.testing.assert_allclose(
        result["solution"],
        g,
        atol=1e-10,
    )

    assert result["converged"]


def test_cgnr_diagonal_matrix():
    """Resolve um sistema diagonal."""

    h = np.diag([2.0, 3.0, 4.0])
    expected = np.array([1.0, 2.0, 3.0])

    g = h @ expected

    result = cgnr(h, g, tolerance=1e-12)

    np.testing.assert_allclose(
        result["solution"],
        expected,
        rtol=1e-9,
        atol=1e-9,
    )

    assert result["converged"]


def test_cgnr_rectangular_system():
    """Resolve um sistema retangular consistente."""

    h = np.array([
        [1.0, 0.0],
        [0.0, 1.0],
        [1.0, 1.0],
    ])

    expected = np.array([2.0, 3.0])
    g = h @ expected

    result = cgnr(h, g, tolerance=1e-12)

    np.testing.assert_allclose(
        result["solution"],
        expected,
        atol=1e-10,
    )

    assert result["converged"]


def test_cgnr_least_squares():
    """Resolve um problema de mínimos quadrados."""

    h = np.array([
        [1.0],
        [1.0],
        [1.0],
    ])

    g = np.array([1.0, 2.0, 3.0])

    result = cgnr(h, g)

    np.testing.assert_allclose(
        result["solution"],
        [2.0],
        atol=1e-10,
    )

    assert result["converged"]


def test_cgnr_zero_measurements():
    """Verifica o caso de medições nulas."""

    h = np.eye(3)
    g = np.zeros(3)

    result = cgnr(h, g)

    np.testing.assert_array_equal(
        result["solution"],
        np.zeros(3),
    )

    assert result["converged"]
    assert result["iterations"] == 0


def test_cgnr_initial_guess():
    """Verifica uma estimativa inicial fornecida."""

    h = np.eye(2)
    g = np.array([3.0, 5.0])
    x0 = np.array([3.0, 5.0])

    result = cgnr(h, g, x0=x0)

    np.testing.assert_allclose(
        result["solution"],
        x0,
    )

    assert result["iterations"] == 0
    assert result["converged"]


def test_cgnr_does_not_modify_initial_guess():
    """Verifica que x0 não é modificado."""

    h = np.eye(2)
    g = np.array([4.0, 6.0])
    x0 = np.array([1.0, 1.0])
    original = x0.copy()

    cgnr(h, g, x0=x0)

    np.testing.assert_array_equal(x0, original)


def test_cgnr_invalid_dimensions():
    """Rejeita dimensões incompatíveis."""

    h = np.ones((3, 2))
    g = np.ones(2)

    with pytest.raises(ValueError, match="Dimensões incompatíveis"):
        cgnr(h, g)


def test_cgnr_invalid_tolerance():
    """Rejeita uma tolerância inválida."""

    with pytest.raises(ValueError):
        cgnr(np.eye(2), np.ones(2), tolerance=-1)


def test_cgnr_invalid_iterations():
    """Rejeita limite de iterações inválido."""

    with pytest.raises(ValueError):
        cgnr(np.eye(2), np.ones(2), max_iterations=0)


def test_cgnr_nan_values():
    """Rejeita valores NaN na matriz."""

    h = np.array([
        [1.0, np.nan],
        [0.0, 1.0],
    ])

    g = np.ones(2)

    with pytest.raises(ValueError):
        cgnr(h, g)


def test_cgnr_result_structure():
    """Verifica os dados retornados pelo algoritmo."""

    h = np.eye(2)
    g = np.array([1.0, 2.0])

    result = cgnr(h, g)

    assert "solution" in result
    assert "iterations" in result
    assert "converged" in result
    assert "residual_norm" in result
    assert "normal_residual_norm" in result
    assert "residual_history" in result

    assert result["solution"].dtype == np.float64
    assert len(result["residual_history"]) == result["iterations"] + 1


def test_cgnr_residual():
    """Verifica que o resíduo final é pequeno."""

    h = np.eye(3)
    g = np.array([1.0, 2.0, 3.0])

    result = cgnr(h, g)

    assert result["residual_norm"] < 1e-10


def test_cgnr_iteration_limit():
    """Verifica o respeito ao limite de iterações."""

    h = np.diag([1.0, 2.0, 4.0])
    g = np.ones(3)

    result = cgnr(
        h,
        g,
        tolerance=1e-14,
        max_iterations=1,
    )

    assert result["iterations"] <= 1


def test_cgnr_rank_deficient_system():
    """Verifica um sistema com colunas dependentes."""

    h = np.array([
        [1.0, 1.0],
        [2.0, 2.0],
    ])

    g = np.array([2.0, 4.0])

    result = cgnr(h, g)

    np.testing.assert_allclose(
        h @ result["solution"],
        g,
        atol=1e-10,
    )

    assert result["converged"]

"""Operações matriciais básicas para reconstrução de imagens.

TASK-04 — Implementar operações matriciais básicas em Python.

Operações exigidas:
    - MN = M × N: multiplicação matriz-matriz
    - aM = a × M: multiplicação vetor-matriz
    - Ma = M × a: multiplicação matriz-vetor

Operação adicional:
    - Multiplicação escalar-matriz (multiply_scalar_matrix)

Todas as operações utilizam NumPy e precisão float64.
"""

import numpy as np


def _validate_array(data, name, ndim):
    """Valida e converte uma matriz ou vetor para float64."""

    try:
        array = np.asarray(data)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{name} deve conter dados numéricos válidos."
        ) from exc

    # Verifica o número de dimensões
    if array.ndim != ndim:
        raise ValueError(
            f"{name} deve possuir {ndim} dimensão(ões), "
            f"mas possui {array.ndim}."
        )

    # Impede matrizes e vetores vazios
    if array.size == 0 or any(size == 0 for size in array.shape):
        raise ValueError(
            f"{name} não pode ser vazio."
        )

    # Aceita apenas números reais
    if array.dtype.kind not in "iuf":
        raise TypeError(
            f"{name} deve conter apenas números reais."
        )

    # Converte para precisão dupla
    try:
        array = array.astype(np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{name} não pode ser convertido para float64."
        ) from exc

    # Impede NaN e infinito
    if not np.all(np.isfinite(array)):
        raise ValueError(
            f"{name} contém valores NaN ou infinitos."
        )

    return array


def _validate_scalar(value):
    """Valida um escalar numérico real e finito."""

    try:
        array = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(
            "O escalar deve ser um número real."
        ) from exc

    if array.ndim != 0 or array.dtype.kind not in "iuf":
        raise TypeError(
            "O escalar deve ser um número real."
        )

    try:
        scalar = float(array)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "O escalar não pode ser convertido para float64."
        ) from exc

    if not np.isfinite(scalar):
        raise ValueError(
            "O escalar deve ser finito."
        )

    return scalar


def multiply_matrices(m, n):
    """Calcula o produto matricial M × N.

    Parâmetros:
        m: matriz de dimensões (a, b)
        n: matriz de dimensões (b, c)

    Retorna:
        Matriz de dimensões (a, c), em float64.

    Raises:
        ValueError: se as dimensões forem incompatíveis.
    """

    m = _validate_array(m, "M", ndim=2)
    n = _validate_array(n, "N", ndim=2)

    if m.shape[1] != n.shape[0]:
        raise ValueError(
            "Dimensões incompatíveis para multiplicação: "
            f"M possui formato {m.shape} e "
            f"N possui formato {n.shape}."
        )

    return m @ n


def multiply_scalar_matrix(a, m):
    """Calcula o produto de um escalar por uma matriz: a × M.

    Parâmetros:
        a: escalar numérico real
        m: matriz bidimensional

    Retorna:
        Matriz resultante em float64.
    """

    a = _validate_scalar(a)
    m = _validate_array(m, "M", ndim=2)

    return a * m


def multiply_matrix_vector(m, a):
    """Calcula o produto de uma matriz por um vetor: M × a.

    Parâmetros:
        m: matriz de dimensões (linhas, colunas)
        a: vetor com comprimento igual ao número de colunas

    Retorna:
        Vetor com comprimento igual ao número de linhas,
        utilizando precisão float64.

    Raises:
        ValueError: se as dimensões forem incompatíveis.
    """

    m = _validate_array(m, "M", ndim=2)
    a = _validate_array(a, "a", ndim=1)

    if m.shape[1] != a.shape[0]:
        raise ValueError(
            "Dimensões incompatíveis para multiplicação: "
            f"M possui formato {m.shape} e "
            f"o vetor possui tamanho {a.shape[0]}."
        )

    return m @ a


def multiply_vector_matrix(a, m):
    """Calcula o produto de um vetor-linha por uma matriz: a × M.

    Parâmetros:
        a: vetor com comprimento igual ao número de linhas de M
        m: matriz bidimensional

    Retorna:
        Vetor com comprimento igual ao número de colunas de M,
        utilizando precisão float64.

    Raises:
        ValueError: se as dimensões forem incompatíveis.
    """

    a = _validate_array(a, "a", ndim=1)
    m = _validate_array(m, "M", ndim=2)

    if a.shape[0] != m.shape[0]:
        raise ValueError(
            "Dimensões incompatíveis para multiplicação: "
            f"o vetor possui tamanho {a.shape[0]} e "
            f"M possui formato {m.shape}."
        )

    return a @ m
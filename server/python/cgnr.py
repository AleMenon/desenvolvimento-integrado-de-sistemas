"""Algoritmo CGNR para resolução aproximada de sistemas lineares.

TASK-06 — Implementar algoritmo CGNR em Python.

Resolve o problema de mínimos quadrados:

    min ||H @ x - g||²

Utiliza NumPy e precisão float64.
Não forma explicitamente a matriz H.T @ H.
"""

import numpy as np


def cgnr(h, g, x0=None, tolerance=1e-8, max_iterations=None):
    """Resolve Hx ≈ g utilizando CGNR.

    Parâmetros:
        h: matriz do sistema, com dimensões (m, n).
        g: vetor de medições, com m elementos.
        x0: estimativa inicial com n elementos (opcional).
        tolerance: tolerância relativa para o resíduo normal.
        max_iterations: número máximo de iterações.

    Retorna:
        Dicionário contendo:
            solution: vetor solução.
            iterations: número de iterações executadas.
            converged: indica se o critério de parada foi atingido.
            residual_norm: norma de ||g - Hx||.
            normal_residual_norm: norma de ||H.T @ (g - Hx)||.
            residual_history: histórico da norma do resíduo.
    """

    # Validação da matriz H
    try:
        h = np.asarray(h, dtype=np.float64)
        g = np.asarray(g, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "H e g devem conter valores numéricos válidos."
        ) from exc

    if h.ndim != 2:
        raise ValueError("H deve ser uma matriz bidimensional.")

    if g.ndim != 1:
        raise ValueError("g deve ser um vetor unidimensional.")

    m, n = h.shape

    if m == 0 or n == 0:
        raise ValueError("H não pode ser vazia.")

    if g.shape[0] != m:
        raise ValueError(
            "Dimensões incompatíveis: "
            f"H possui {m} linhas e g possui {g.shape[0]} elementos."
        )

    if not np.all(np.isfinite(h)) or not np.all(np.isfinite(g)):
        raise ValueError("H e g devem conter apenas valores finitos.")

    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("A tolerância deve ser positiva e finita.")

    if max_iterations is None:
        max_iterations = max(1, 2 * n)

    if (
        isinstance(max_iterations, (bool, np.bool_))
        or not isinstance(max_iterations, (int, np.integer))
        or max_iterations <= 0
    ):
        raise ValueError(
            "O número máximo de iterações deve ser inteiro e positivo."
        )

    # Estimativa inicial
    if x0 is None:
        x = np.zeros(n, dtype=np.float64)
    else:
        try:
            x = np.asarray(x0, dtype=np.float64).copy()
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "x0 deve conter valores numéricos válidos."
            ) from exc

        if x.ndim != 1 or x.shape[0] != n:
            raise ValueError(
                f"x0 deve ser um vetor com {n} elementos."
            )

        if not np.all(np.isfinite(x)):
            raise ValueError("x0 deve conter apenas valores finitos.")

    # Resíduo inicial: r = g - Hx
    r = g - h @ x

    # Resíduo normal: z = H.T @ r
    z = h.T @ r

    # Direção de busca inicial
    p = z.copy()

    gamma = float(z @ z)

    # Critério relativo baseado no resíduo normal inicial
    initial_normal_norm = np.sqrt(gamma)
    threshold = tolerance * initial_normal_norm

    residual_history = [float(np.linalg.norm(r))]

    if initial_normal_norm == 0.0:
        return {
            "solution": x,
            "iterations": 0,
            "converged": True,
            "residual_norm": float(np.linalg.norm(r)),
            "normal_residual_norm": 0.0,
            "residual_history": residual_history,
        }

    converged = False
    iterations = 0

    for iteration in range(1, max_iterations + 1):
        # Produto matriz-vetor: q = H @ p
        q = h @ p

        denominator = float(q @ q)

        # Evita divisão por zero ou valores inválidos
        if denominator <= 0 or not np.isfinite(denominator):
            break

        # Comprimento do passo
        alpha = gamma / denominator

        # Atualização da solução e do resíduo
        x = x + alpha * p
        r = r - alpha * q

        # Novo resíduo normal
        z_new = h.T @ r

        gamma_new = float(z_new @ z_new)

        iterations = iteration
        residual_history.append(float(np.linalg.norm(r)))

        if not np.isfinite(gamma_new):
            break

        # Critério de parada
        if np.sqrt(gamma_new) <= threshold:
            converged = True
            break

        # Atualização da direção conjugada
        beta = gamma_new / gamma
        p = z_new + beta * p

        gamma = gamma_new

    # Recalcula os resíduos usando a solução final
    final_r = g - h @ x
    final_z = h.T @ final_r

    final_normal_norm = float(np.linalg.norm(final_z))

    if final_normal_norm <= threshold:
        converged = True

    return {
        "solution": x,
        "iterations": iterations,
        "converged": converged,
        "residual_norm": float(np.linalg.norm(final_r)),
        "normal_residual_norm": final_normal_norm,
        "residual_history": residual_history,
    }

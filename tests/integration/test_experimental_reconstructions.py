"""TASK-08 — Validação opcional de resultados experimentais Python × C++.

Os testes analisam resultados previamente gerados. Eles não executam
novamente o CGNR nem dependem dos arquivos grandes de matriz.
"""

import json
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "build" / "results"

EXPERIMENTS = [
    ("g-30x30-1", 30, 27904),
    ("g-30x30-2", 30, 27904),
    ("G-1", 60, 50816),
    ("G-2", 60, 50816),
]


@pytest.mark.parametrize(
    "signal_name,side,expected_rows",
    EXPERIMENTS,
)
def test_experimental_python_cpp_equivalence(
    signal_name, side, expected_rows
):
    python_dir = RESULTS / signal_name
    cpp_dir = RESULTS / "cpp" / signal_name

    required_files = [
        python_dir / "experiment.json",
        python_dir / f"reconstruction_{side}x{side}.csv",
        cpp_dir / "metrics.json",
        cpp_dir / "solution.csv",
    ]

    missing = [path for path in required_files if not path.is_file()]

    if missing:
        pytest.skip(
            "Resultados experimentais ausentes: "
            + ", ".join(str(path) for path in missing)
        )

    python_metrics = json.loads(
        (python_dir / "experiment.json").read_text(encoding="utf-8")
    )
    cpp_metrics = json.loads(
        (cpp_dir / "metrics.json").read_text(encoding="utf-8")
    )

    python_image = np.loadtxt(
        python_dir / f"reconstruction_{side}x{side}.csv",
        delimiter=",",
        dtype=np.float64,
    )
    cpp_solution = np.loadtxt(
        cpp_dir / "solution.csv",
        delimiter=",",
        dtype=np.float64,
    ).reshape(-1)

    # Dimensões do modelo.
    assert python_metrics["matrix_shape"] == [
        expected_rows, side * side
    ]
    assert python_metrics["image_shape"] == [side, side]
    assert cpp_metrics["rows"] == expected_rows
    assert cpp_metrics["columns"] == side * side

    assert python_image.shape == (side, side)
    assert cpp_solution.shape == (side * side,)

    assert np.isfinite(python_image).all()
    assert np.isfinite(cpp_solution).all()

    # Parâmetros e resultados.
    assert python_metrics["max_iterations"] == 10
    assert python_metrics["tolerance"] == pytest.approx(1e-8)

    assert 0 <= python_metrics["iterations"] <= 10
    assert 0 <= cpp_metrics["iterations"] <= 10

    assert python_metrics["iterations"] == cpp_metrics["iterations"]
    assert python_metrics["converged"] == cpp_metrics["converged"]

    # Equivalência numérica.
    python_solution = python_image.reshape(-1)

    absolute_difference = np.linalg.norm(
        python_solution - cpp_solution
    )
    reference_norm = np.linalg.norm(python_solution)

    relative_difference = absolute_difference / max(
        reference_norm, np.finfo(float).tiny
    )

    assert relative_difference < 1e-9

    # Resíduos finais.
    np.testing.assert_allclose(
        cpp_metrics["residual_norm"],
        python_metrics["residual_norm"],
        rtol=1e-8,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        cpp_metrics["normal_residual_norm"],
        python_metrics["normal_residual_norm"],
        rtol=1e-8,
        atol=1e-12,
    )

    # Histórico de resíduos C++.
    history = np.asarray(
        cpp_metrics["residual_history"], dtype=np.float64
    )

    assert len(history) == cpp_metrics["iterations"] + 1
    assert np.isfinite(history).all()

    np.testing.assert_allclose(
        history[-1],
        cpp_metrics["residual_norm"],
        rtol=1e-8,
        atol=1e-12,
    )

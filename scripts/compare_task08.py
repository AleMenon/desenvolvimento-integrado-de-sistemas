"""Compara soluções experimentais Python e C++ da TASK-08."""
import argparse
import json
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-dir", type=Path, required=True)
    parser.add_argument("--cpp-dir", type=Path, required=True)
    args = parser.parse_args()
    pmeta = json.loads((args.python_dir / "experiment.json").read_text())
    cmeta = json.loads((args.cpp_dir / "metrics.json").read_text())

    height, width = pmeta["image_shape"]
    image_file = f"reconstruction_{height}x{width}.csv"

    p = np.loadtxt(args.python_dir / image_file, delimiter=",").ravel()
    c = np.loadtxt(args.cpp_dir / "solution.csv", delimiter=",").ravel()

    if p.size != height * width:
        raise ValueError("A imagem Python não corresponde ao image_shape")

    if c.size != cmeta["columns"]:
        raise ValueError("A solução C++ não corresponde ao número de colunas")
    if p.shape != c.shape:
        raise ValueError(f"Dimensões distintas: {p.shape} vs. {c.shape}")
    if not (np.isfinite(p).all() and np.isfinite(c).all()):
        raise ValueError("Solução contém NaN ou infinito")
    difference = p - c
    absolute = float(np.linalg.norm(difference))
    relative = absolute / max(float(np.linalg.norm(p)), np.finfo(float).tiny)
    max_diff = float(np.max(np.abs(difference)))
    print(f"Elementos: {p.size}")
    print(f"Iterações (Python / C++): {pmeta['iterations']} / {cmeta['iterations']}")
    print(f"Convergiu (Python / C++): {pmeta['converged']} / {cmeta['converged']}")
    print(f"Norma L2 da diferença: {absolute:.12e}")
    print(f"Diferença relativa L2: {relative:.12e}")
    print(f"Maior diferença absoluta: {max_diff:.12e}")
    print(f"Tempo Python: {pmeta['elapsed_seconds']:.4f}s | C++: {cmeta['elapsed_seconds']:.4f}s")
    for label in ("residual_norm", "normal_residual_norm"):
        print(f"{label} Python: {pmeta[label]:.12e} | C++: {cmeta[label]:.12e}")
    result = {"elements": p.size, "l2_difference": absolute, "relative_l2_difference": relative,
              "max_absolute_difference": max_diff,
              "iterations_match": pmeta["iterations"] == cmeta["iterations"],
              "convergence_match": pmeta["converged"] == cmeta["converged"]}
    (args.cpp_dir / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()

"""Exporta matriz NumPy e sinais para leitura nativa pelo Eigen (TASK-08).

Formato H: dois uint64 little-endian (linhas, colunas), seguidos de
float64 little-endian em ordem de COLUNAS (Eigen::MatrixXd).
Formato g: um uint64 little-endian (tamanho) seguido de float64 little-endian.
"""
import argparse
from pathlib import Path
import struct

import numpy as np


def export_matrix(source: Path, target: Path) -> None:
    matrix = np.load(source, mmap_mode="r", allow_pickle=False)
    if matrix.ndim != 2 or matrix.dtype != np.dtype("float64"):
        raise ValueError("H deve ser matriz 2D float64")
    if not matrix.shape[0] or not matrix.shape[1]:
        raise ValueError("Matriz vazia")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as output:
        output.write(struct.pack("<QQ", *matrix.shape))
        # Evita criar outra matriz de ~192 MiB (ou >1 GiB no caso 60x60).
        for col in range(matrix.shape[1]):
            values = np.asarray(matrix[:, col], dtype="<f8")
            if not np.isfinite(values).all():
                raise ValueError(f"H contém valor não finito na coluna {col}")
            output.write(values.tobytes(order="C"))
    print(f"Matriz: {matrix.shape} -> {target} ({target.stat().st_size:,} bytes)")


def export_signal(source: Path, target: Path) -> None:
    values = np.loadtxt(source, delimiter=",", dtype=np.float64)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all():
        raise ValueError("Sinal deve ser vetor 1D não vazio e finito")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as output:
        output.write(struct.pack("<Q", values.size))
        output.write(np.asarray(values, dtype="<f8").tobytes())
    print(f"Sinal: {values.size} valores -> {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-npy", type=Path)
    parser.add_argument("--signal-csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (args.matrix_npy or args.signal_csv) or (args.matrix_npy and args.signal_csv):
        parser.error("informe apenas --matrix-npy OU --signal-csv")
    if args.matrix_npy:
        export_matrix(args.matrix_npy, args.output)
    else:
        export_signal(args.signal_csv, args.output)


if __name__ == "__main__":
    main()

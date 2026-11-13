"""Experimento de reconstrução 30x30 usando CGNR.

Exemplo:
    uv run python scripts/run_cgnr_experiment.py \
        --matrix-zip build/data/H-2.csv.zip \
        --measurements build/data/g-30x30-1.csv
"""

import argparse
import json
import time
import zipfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from server.python.cgnr import cgnr


def load_matrix_from_zip(zip_path, cache_path, expected_rows):
    """Converte o CSV comprimido para uma matriz NumPy em disco."""

    with zipfile.ZipFile(zip_path) as archive:
        filenames = [
            name for name in archive.namelist()
            if name.lower().endswith(".csv")
            and not name.startswith("__MACOSX/")
        ]

        if len(filenames) != 1:
            raise ValueError(
                "O ZIP deve conter exatamente um arquivo CSV de dados."
            )

        csv_name = filenames[0]

        if cache_path.exists() and (
            cache_path.stat().st_mtime >= zip_path.stat().st_mtime
        ):
            cached = np.load(cache_path, mmap_mode="r")

            if (
                cached.ndim == 2
                and cached.shape[0] == expected_rows
                and cached.dtype == np.float64
            ):
                print("Utilizando matriz previamente convertida.")
                return cached

        print("Convertendo CSV para matriz NumPy...")

        with archive.open(csv_name) as source:
            first_line = source.readline().decode("utf-8").strip()
            first_row = np.fromstring(first_line, sep=",")

            columns = first_row.size

            if columns == 0:
                raise ValueError("A primeira linha da matriz está vazia.")

            cache_path.parent.mkdir(parents=True, exist_ok=True)

            matrix = np.lib.format.open_memmap(
                cache_path,
                mode="w+",
                dtype=np.float64,
                shape=(expected_rows, columns),
            )

            matrix[0] = first_row
            row_count = 1

            for line in source:
                if row_count >= expected_rows:
                    raise ValueError(
                        "A matriz possui mais linhas que o vetor g."
                    )

                values = np.fromstring(
                    line.decode("utf-8"),
                    sep=",",
                )

                if values.size != columns:
                    raise ValueError(
                        f"Linha {row_count + 1}: "
                        f"esperadas {columns} colunas, "
                        f"encontradas {values.size}."
                    )

                matrix[row_count] = values
                row_count += 1

            if row_count != expected_rows:
                raise ValueError(
                    f"A matriz possui {row_count} linhas, "
                    f"mas g possui {expected_rows} elementos."
                )

            matrix.flush()
            del matrix

    print("Conversão concluída.")

    return np.load(cache_path, mmap_mode="r")


def main():
    parser = argparse.ArgumentParser(
        description="Reconstrução de imagem usando CGNR."
    )

    parser.add_argument(
        "--matrix-zip",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--measurements",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-6,
    )

    args = parser.parse_args()

    # Cada sinal recebe seu próprio diretório de resultados.
    output_dir = Path("build/results") / args.measurements.stem

    # O cache acompanha o nome da matriz utilizada.
    matrix_name = args.matrix_zip.name
    if matrix_name.endswith(".csv.zip"):
        matrix_name = matrix_name[:-8]

    cache_path = Path("build/data") / f"{matrix_name}.npy"

    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.matrix_zip.is_file():
        raise FileNotFoundError(args.matrix_zip)

    if not args.measurements.is_file():
        raise FileNotFoundError(args.measurements)

    g = np.loadtxt(
        args.measurements,
        delimiter=",",
        dtype=np.float64,
    )

    if g.ndim != 1:
        raise ValueError("O arquivo g deve conter um vetor.")

    print(f"Vetor de medições: {g.shape[0]} elementos")

    h = load_matrix_from_zip(
        args.matrix_zip,
        cache_path,
        expected_rows=g.size,
    )

    rows, columns = h.shape

    print(f"Dimensões de H: {rows} x {columns}")

    side = int(np.sqrt(columns))

    if side * side != columns:
        raise ValueError(
            "O número de colunas não forma uma imagem quadrada."
        )

    print(f"Imagem de saída: {side} x {side}")
    print("Executando CGNR...")

    start = time.perf_counter()

    result = cgnr(
        h,
        g,
        tolerance=args.tolerance,
        max_iterations=args.max_iterations,
    )

    elapsed = time.perf_counter() - start

    x = result["solution"]
    image = x.reshape((side, side))

    # Calcula o resíduo relativo ao vetor de medições.
    relative_residual = (
        result["residual_norm"] / np.linalg.norm(g)
        if np.linalg.norm(g) > 0
        else 0.0
    )

    # Salva os valores da solução.
    np.savetxt(
        output_dir / f"reconstruction_{side}x{side}.csv",
        image,
        delimiter=",",
        fmt="%.12e",
    )

    # Salva uma visualização da reconstrução.
    plt.figure(figsize=(6, 6))
    plt.imshow(image, cmap="gray")
    plt.colorbar(label="Intensidade reconstruída")
    plt.title("Reconstrução CGNR — 30x30")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(
        output_dir / f"reconstruction_{side}x{side}.png",
        dpi=160,
    )
    plt.close()

    # Salva o histórico de convergência.
    np.savetxt(
        output_dir / "residual_history.csv",
        np.asarray(result["residual_history"]),
        delimiter=",",
        header="residual_norm",
        comments="",
    )

    metadata = {
        "matrix": str(args.matrix_zip),
        "measurements": str(args.measurements),
        "matrix_shape": [rows, columns],
        "image_shape": [side, side],
        "python_numpy_version": np.__version__,
        "tolerance": args.tolerance,
        "max_iterations": args.max_iterations,
        "iterations": result["iterations"],
        "converged": bool(result["converged"]),
        "residual_norm": result["residual_norm"],
        "normal_residual_norm": result["normal_residual_norm"],
        "relative_residual": float(relative_residual),
        "elapsed_seconds": elapsed,
    }

    with open(
        output_dir / "experiment.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(metadata, file, indent=2)

    print()
    print("===== RESULTADOS =====")
    print(f"Iterações: {result['iterations']}")
    print(f"Convergiu: {result['converged']}")
    print(f"Norma do resíduo: {result['residual_norm']:.6e}")
    print(f"Resíduo relativo: {relative_residual:.6e}")
    print(
        "Norma do resíduo normal: "
        f"{result['normal_residual_norm']:.6e}"
    )
    print(f"Tempo de execução: {elapsed:.2f} s")
    print(f"Resultado salvo em: {output_dir.resolve()}")

    if not result["converged"]:
        print(
            "AVISO: o critério de convergência não foi "
            "atingido no limite de iterações."
        )


if __name__ == "__main__":
    main()

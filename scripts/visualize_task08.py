"""Comparação visual das reconstruções Python e C++ — TASK-08."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np


def visualize(signal_name: str) -> None:
    root = Path("build/results")
    python_dir = root / signal_name
    cpp_dir = root / "cpp" / signal_name

    metadata = json.loads(
        (python_dir / "experiment.json").read_text(encoding="utf-8")
    )

    height, width = metadata["image_shape"]

    python_file = (
        python_dir / f"reconstruction_{height}x{width}.csv"
    )
    cpp_file = cpp_dir / "solution.csv"

    python_image = np.loadtxt(
        python_file,
        delimiter=",",
        dtype=np.float64,
    )

    cpp_vector = np.loadtxt(
        cpp_file,
        delimiter=",",
        dtype=np.float64,
    ).reshape(-1)

    if python_image.shape != (height, width):
        raise ValueError(
            f"Dimensões inesperadas em Python: {python_image.shape}"
        )

    if cpp_vector.size != height * width:
        raise ValueError(
            f"Esperados {height * width} valores em C++, "
            f"encontrados {cpp_vector.size}"
        )

    cpp_image = cpp_vector.reshape(height, width)

    if not (
        np.isfinite(python_image).all()
        and np.isfinite(cpp_image).all()
    ):
        raise ValueError("As imagens contêm valores não finitos.")

    difference = np.abs(python_image - cpp_image)

    vmin = min(python_image.min(), cpp_image.min())
    vmax = max(python_image.max(), cpp_image.max())

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    image_plot = axes[0].imshow(
        python_image,
        cmap="gray",
        vmin=vmin,
        vmax=vmax,
    )
    axes[0].set_title("CGNR Python")

    axes[1].imshow(
        cpp_image,
        cmap="gray",
        vmin=vmin,
        vmax=vmax,
    )
    axes[1].set_title("CGNR C++")

    difference_plot = axes[2].imshow(
        difference,
        cmap="magma",
        vmin=0,
    )
    axes[2].set_title("Diferença absoluta")

    for axis in axes:
        axis.axis("off")

    fig.colorbar(image_plot, ax=axes[:2], shrink=0.8)
    fig.colorbar(difference_plot, ax=axes[2], shrink=0.8)

    fig.suptitle(
        f"TASK-08 — {signal_name} — {height} × {width}"
    )

    output_dir = root / "comparisons"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = (
        output_dir / f"{signal_name}_comparison.png"
    )

    fig.savefig(
        output_file,
        dpi=160,
        bbox_inches="tight",
    )

    plt.close(fig)

    print(f"Comparação salva em: {output_file}")
    print(
        f"Maior diferença absoluta: "
        f"{difference.max():.12e}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal", required=True)
    args = parser.parse_args()

    visualize(args.signal)

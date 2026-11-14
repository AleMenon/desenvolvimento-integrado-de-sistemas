"""TASK-22: gráficos comparativos a partir dos exports da TASK-16."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from monitoring.statistics import (
    consolidate,
    count,
    number,
    read_run,
)


COLORS = {
    "python": "#3778bf",
    "cpp": "#e18b35",
}

LABELS = {
    "python": "Python",
    "cpp": "C++",
}

CHARTS = {
    "cpu": "cpu_comparison.png",
    "memory": "memory_comparison.png",
    "total": "total_execution_time.png",
    "mean": "mean_reconstruction_time.png",
    "images": "image_counts.png",
}


def optional_number(value, name):
    """Converte número opcional; vazio significa amostra indisponível."""
    if value is None or str(value).strip() == "":
        return None
    return number(value, name)


def load_samples(directory):
    """Lê amostras da TASK-16 e valida seus campos numéricos."""
    path = Path(directory) / "samples.csv"

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    samples = []
    previous = None

    for row in rows:
        elapsed = number(row["elapsed_ms"], "elapsed_ms")

        if previous is not None and elapsed <= previous:
            raise ValueError("elapsed_ms deve ser estritamente crescente")

        previous = elapsed

        cpu = optional_number(row["cpu_percent"], "cpu_percent")
        rss = optional_number(
            row["memory_rss_bytes"],
            "memory_rss_bytes",
        )

        if rss is not None and not rss.is_integer():
            raise ValueError("memory_rss_bytes deve ser inteiro")

        samples.append({
            "elapsed_ms": elapsed,
            "cpu_percent": cpu,
            "memory_rss_bytes": int(rss) if rss is not None else None,
        })

    return samples


def load_experiments(directories):
    """Lê e valida ensaios reais ou fixtures no formato da TASK-16."""
    paths = [Path(directory).resolve() for directory in directories]

    if not paths or len(set(paths)) != len(paths):
        raise ValueError("Informe diretórios distintos de ensaios")

    experiments = []

    for path in paths:
        stats = read_run(path)
        samples = load_samples(path)

        experiments.append({
            "source": str(path),
            "implementation": stats["implementation"],
            "statistics": stats,
            "samples": samples,
        })

    implementations = {
        run["implementation"] for run in experiments
    }

    if implementations != {"python", "cpp"}:
        raise ValueError(
            "A comparação exige ensaios Python e C++"
        )

    return experiments


def save_figure(fig, path):
    fig.savefig(
        path,
        dpi=180,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)


def plot_resources(experiments, output, metric, ylabel, title, divisor=1):
    """Mostra amostras de cada ensaio sem inventar pontos intermediários."""
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.set_title(title, fontsize=14, weight="bold")

    counters = defaultdict(int)
    plotted = False

    for run in sorted(
        experiments,
        key=lambda item: (
            item["implementation"],
            item["source"],
        ),
    ):
        implementation = run["implementation"]
        counters[implementation] += 1

        points = [
            (
                sample["elapsed_ms"] / 1000,
                sample[metric] / divisor,
            )
            for sample in run["samples"]
            if sample[metric] is not None
        ]

        if not points:
            continue

        x, y = zip(*points)

        label = (
            f"{LABELS[implementation]} "
            f"— ensaio {counters[implementation]}"
        )

        ax.plot(
            x,
            y,
            marker="o",
            markersize=2.5,
            linewidth=1.6,
            alpha=0.85,
            color=COLORS[implementation],
            label=label,
        )
        plotted = True

    ax.set_xlabel("Tempo desde o início da coleta (s)")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.2)

    if plotted:
        ax.legend(loc="best", fontsize=9)
    else:
        ax.text(
            0.5, 0.5,
            "N/D — não há amostras válidas",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )

    fig.tight_layout()
    save_figure(fig, output)


def plot_time(rows, output, field, title):
    """Apresenta N/D explicitamente para estatísticas indisponíveis."""
    fig, ax = plt.subplots(figsize=(8, 5))

    labels = [LABELS[row["implementation"]] for row in rows]
    values = [row[field] for row in rows]
    positions = np.arange(len(rows))

    for index, (row, value) in enumerate(zip(rows, values)):
        color = COLORS[row["implementation"]]

        if value is None:
            ax.text(
                index, 0.08,
                "N/D",
                ha="center",
                va="bottom",
                fontsize=12,
                weight="bold",
                transform=ax.get_xaxis_transform(),
            )
        else:
            ax.bar(index, value, color=color, width=0.5)
            ax.annotate(
                f"{value:.2f}",
                (index, value),
                xytext=(0, 5),
                textcoords="offset points",
                ha="center",
                fontsize=10,
            )

    ax.set_xticks(positions, labels)
    ax.set_xlim(-0.6, len(rows) - 0.4)
    ax.set_ylim(
        0,
        max((v for v in values if v is not None), default=0) * 1.2
        or 1,
    )
    ax.set_ylabel("Tempo (ms)")
    ax.set_title(title, fontsize=14, weight="bold")
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)

    fig.tight_layout()
    save_figure(fig, output)


def plot_images(rows, output):
    """Compara imagens concluídas e falhas sem misturar os contadores."""
    fig, ax = plt.subplots(figsize=(8, 5))

    positions = np.arange(len(rows))
    completed = [row["completed_count"] for row in rows]
    failed = [row["failed_count"] for row in rows]

    width = 0.34

    ax.bar(
        positions - width / 2,
        completed,
        width,
        label="Concluídas",
        color="#368c74",
    )
    ax.bar(
        positions + width / 2,
        failed,
        width,
        label="Falhas",
        color="#cf735d",
    )

    for index in range(len(rows)):
        for offset, value in (
            (-width / 2, completed[index]),
            (width / 2, failed[index]),
        ):
            ax.annotate(
                str(value),
                (index + offset, value),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center",
            )

    ax.set_xticks(
        positions,
        [LABELS[row["implementation"]] for row in rows],
    )
    ax.set_ylabel("Quantidade de imagens")
    ax.set_title(
        "Reconstruções concluídas e falhas",
        fontsize=14,
        weight="bold",
    )
    ax.set_ylim(
        0,
        max([*completed, *failed, 1]) * 1.2 + 1,
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.2)
    ax.set_axisbelow(True)

    fig.tight_layout()
    save_figure(fig, output)


def generate_plots(directories, output):
    """Gera os cinco gráficos e um manifesto de rastreabilidade."""
    experiments = load_experiments(directories)

    rows = consolidate([
        experiment["statistics"]
        for experiment in experiments
    ])

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    plot_resources(
        experiments,
        output / CHARTS["cpu"],
        "cpu_percent",
        "CPU utilizada pelo processo (%)",
        "Consumo de CPU durante os ensaios",
    )

    plot_resources(
        experiments,
        output / CHARTS["memory"],
        "memory_rss_bytes",
        "Memória RSS (MiB)",
        "Consumo de memória durante os ensaios",
        divisor=1024 ** 2,
    )

    plot_time(
        rows,
        output / CHARTS["total"],
        "total_execution_time_ms",
        "Tempo total dos ensaios",
    )

    plot_time(
        rows,
        output / CHARTS["mean"],
        "mean_reconstruction_time_ms",
        "Tempo médio por reconstrução concluída",
    )

    plot_images(
        rows,
        output / CHARTS["images"],
    )

    manifest = {
        "schema_version": 1,
        "task": "TASK-22",
        "sources": [
            experiment["source"]
            for experiment in experiments
        ],
        "versions": rows,
        "charts": CHARTS,
        "notes": [
            "CPU e memória representam amostras por ensaio.",
            "CPU percentual pode exceder 100% em múltiplos núcleos.",
            "Memória RSS usa MiB (2^20 bytes).",
            "Tempos indisponíveis aparecem como N/D, não zero.",
            "Tempos estatísticos seguem a metodologia da TASK-17.",
            "Comparações exigem cargas e ambientes equivalentes.",
        ],
    }

    (output / "plots_manifest.json").write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )

    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "directories",
        nargs="+",
        type=Path,
        help="Diretórios de ensaios exportados pela TASK-16",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Diretório de saída dos gráficos",
    )

    args = parser.parse_args()
    manifest = generate_plots(args.directories, args.output)

    print("Gráficos gerados:")
    for filename in manifest["charts"].values():
        print(f"  {args.output / filename}")

    print(f"  {args.output / 'plots_manifest.json'}")


if __name__ == "__main__":
    main()

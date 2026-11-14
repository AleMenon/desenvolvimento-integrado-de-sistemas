"""Generate one reproducible dense CGNR test model for TASK-18 experiments.

The model is synthetic, NOT an experimental reconstruction matrix.
Both servers consume the same CSV catalog and the exact same JSON signal.
"""

import argparse
import json
from pathlib import Path

import numpy as np


def generate(size: int, output: Path, seed: int = 18) -> tuple[Path, Path]:
    if type(size) is not int or not 3 <= size <= 2048:
        raise ValueError("size must be an integer from 3 through 2048")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    output = Path(output)
    models = output / "models"
    models.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    # Well-conditioned yet nontrivial dense matrix; ten CGNR iterations are
    # enough to exercise matrix/vector products without risking singularity.
    matrix = rng.normal(0, 0.4 / np.sqrt(size), (size, size))
    matrix += np.eye(size) * 2.0
    solution = rng.normal(size=size)
    model_id = f"task18_dense_{size}"
    file_name = f"{model_id}.csv"
    np.savetxt(models / file_name, matrix, delimiter=",", fmt="%.17g")
    signal = (matrix @ solution).tolist()
    (output / "signal.json").write_text(json.dumps(signal) + "\n", encoding="utf-8")
    catalog = {"models": [{"model_id": model_id, "file": file_name,
                            "image_shape": [1, size], "version": f"task18-seed-{seed}"}]}
    catalog_path = models / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    return catalog_path, output / "signal.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--seed", type=int, default=18)
    parser.add_argument("--output", type=Path, default=Path("results/task18-fixture"))
    args = parser.parse_args()
    catalog, signal = generate(args.size, args.output, args.seed)
    print(f"Catalog: {catalog}\nSignal: {signal}\nModel ID: task18_dense_{args.size}")


if __name__ == "__main__":
    main()

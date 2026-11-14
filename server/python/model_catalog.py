"""Carregamento e validação de modelos matriciais — TASK-12."""

import hashlib
import json
from pathlib import Path

import numpy as np


class ModelCatalog:
    """Catálogo de matrizes disponíveis para reconstrução."""

    def __init__(self, catalog_path):
        self.catalog_path = Path(catalog_path).resolve()
        self.models = {}

        if not self.catalog_path.is_file():
            raise FileNotFoundError(
                f"Catálogo não encontrado: {self.catalog_path}"
            )

        with self.catalog_path.open("r", encoding="utf-8") as source:
            catalog = json.load(source)

        if not isinstance(catalog, dict):
            raise ValueError("O catálogo deve ser um objeto JSON.")

        entries = catalog.get("models")

        if not isinstance(entries, list) or not entries:
            raise ValueError(
                "O catálogo deve conter uma lista não vazia de modelos."
            )

        for entry in entries:
            self._load_model(entry)

    def _load_model(self, entry):
        if not isinstance(entry, dict):
            raise ValueError("Entrada de modelo inválida.")

        model_id = entry.get("model_id")
        filename = entry.get("file")
        image_shape = entry.get("image_shape")
        version = entry.get("version")

        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id inválido.")

        if model_id in self.models:
            raise ValueError(f"Modelo duplicado: {model_id}")

        if not isinstance(filename, str) or not filename.strip():
            raise ValueError(f"Arquivo inválido para o modelo {model_id}.")

        if (
            not isinstance(image_shape, list)
            or len(image_shape) != 2
            or any(type(value) is not int or value <= 0 for value in image_shape)
        ):
            raise ValueError(f"image_shape inválido para {model_id}.")

        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"Versão inválida para {model_id}.")

        matrix_path = (self.catalog_path.parent / filename).resolve()

        if not matrix_path.is_file():
            raise FileNotFoundError(
                f"Matriz não encontrada para {model_id}: {matrix_path}"
            )

        matrix = np.loadtxt(
            matrix_path,
            delimiter=",",
            dtype=np.float64,
            ndmin=2,
        )

        if matrix.ndim != 2 or matrix.size == 0:
            raise ValueError(f"Matriz inválida para {model_id}.")

        if not np.all(np.isfinite(matrix)):
            raise ValueError(
                f"Matriz contém valores não finitos: {model_id}."
            )

        rows, columns = matrix.shape

        if image_shape[0] * image_shape[1] != columns:
            raise ValueError(
                f"Dimensões da imagem incompatíveis com a matriz {model_id}."
            )

        digest = hashlib.sha256()

        with matrix_path.open("rb") as source:
            for block in iter(
                lambda: source.read(1024 * 1024),
                b"",
            ):
                digest.update(block)

        metadata = {
            "model_id": model_id,
            "rows": rows,
            "columns": columns,
            "image_shape": image_shape,
            "data_type": "float64",
            "version": version,
            "checksum_sha256": digest.hexdigest(),
        }

        self.models[model_id] = {
            "matrix": matrix,
            "metadata": metadata,
        }

    def list_models(self):
        """Retorna os metadados de todos os modelos."""
        return [
            item["metadata"].copy()
            for item in self.models.values()
        ]

    def get_model(self, model_id):
        """Retorna o modelo ou None quando não existir."""
        return self.models.get(model_id)

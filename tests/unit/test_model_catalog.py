"""Testes do catálogo de modelos da TASK-12."""

import json

import numpy as np
import pytest

from server.python.model_catalog import ModelCatalog


def create_catalog(tmp_path, matrix, image_shape):
    matrix_path = tmp_path / "matrix.csv"

    np.savetxt(
        matrix_path,
        matrix,
        delimiter=",",
    )

    catalog_path = tmp_path / "catalog.json"

    catalog_path.write_text(
        json.dumps({
            "models": [
                {
                    "model_id": "test_model",
                    "file": "matrix.csv",
                    "image_shape": image_shape,
                    "version": "1.0",
                }
            ]
        }),
        encoding="utf-8",
    )

    return catalog_path


def test_load_demo_catalog():
    catalog = ModelCatalog("models/catalog.json")

    model = catalog.get_model("demo_identity_3")

    assert model is not None
    assert model["metadata"]["rows"] == 3
    assert model["metadata"]["columns"] == 3
    assert model["metadata"]["image_shape"] == [1, 3]

    np.testing.assert_array_equal(
        model["matrix"],
        np.eye(3),
    )


def test_list_models():
    catalog = ModelCatalog("models/catalog.json")

    models = catalog.list_models()

    assert len(models) == 1
    assert models[0]["model_id"] == "demo_identity_3"


def test_unknown_model():
    catalog = ModelCatalog("models/catalog.json")

    assert catalog.get_model("inexistente") is None


def test_invalid_image_shape(tmp_path):
    path = create_catalog(
        tmp_path,
        np.eye(3),
        [2, 2],
    )

    with pytest.raises(ValueError, match="incompatíveis"):
        ModelCatalog(path)


def test_nonfinite_matrix(tmp_path):
    path = create_catalog(
        tmp_path,
        [[1.0, 0.0], [float("nan"), 1.0]],
        [1, 2],
    )

    with pytest.raises(ValueError, match="não finitos"):
        ModelCatalog(path)


def test_missing_catalog(tmp_path):
    with pytest.raises(FileNotFoundError):
        ModelCatalog(tmp_path / "missing.json")


def test_duplicate_model_id(tmp_path):
    path = create_catalog(
        tmp_path,
        np.eye(2),
        [1, 2],
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    data["models"].append(data["models"][0])

    path.write_text(
        json.dumps(data),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicado"):
        ModelCatalog(path)

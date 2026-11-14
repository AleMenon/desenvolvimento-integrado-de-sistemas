"""Preparação reproduzível de sinais experimentais — task-10."""

import hashlib
import json
import math
from pathlib import Path

import numpy as np


def load_signal(path, expected_size=None):
    """Carrega um sinal csv e valida seus valores."""
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"sinal não encontrado: {path}")

    signal = np.loadtxt(path, delimiter=",", dtype=np.float64)

    if signal.ndim != 1 or signal.size == 0:
        raise ValueError("o sinal deve ser um vetor não vazio")

    if expected_size is not None and signal.size != expected_size:
        raise ValueError(
            f"dimensão inválida: esperado {expected_size}, "
            f"recebido {signal.size}"
        )

    if not np.all(np.isfinite(signal)):
        raise ValueError("o sinal contém valores não finitos")

    return signal


def calculate_gain(signal, target_rms=1.0):
    """Calcula o ganho para atingir uma amplitude rms configurável."""
    signal = np.asarray(signal, dtype=np.float64)

    if signal.ndim != 1 or signal.size == 0:
        raise ValueError("o sinal deve ser um vetor não vazio")

    if not np.all(np.isfinite(signal)):
        raise ValueError("o sinal contém valores não finitos")

    if not math.isfinite(target_rms) or target_rms <= 0:
        raise ValueError("target_rms deve ser positivo e finito")

    rms = float(np.linalg.norm(signal / np.sqrt(signal.size)))

    if rms == 0:
        raise ValueError("não é possível normalizar um sinal nulo")

    gain = float(target_rms / rms)

    if not math.isfinite(gain):
        raise ValueError("ganho calculado não é finito")

    return gain


def apply_gain(signal, gain):
    """Aplica um fator de ganho a um sinal."""
    if not math.isfinite(gain) or gain <= 0:
        raise ValueError("ganho deve ser positivo e finito")

    values = np.asarray(signal, dtype=np.float64)

    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise ValueError("sinal inválido")

    result = values * gain

    if not np.all(np.isfinite(result)):
        raise ValueError("o ganho produziu valores não finitos")

    return result


def file_sha256(path):
    digest = hashlib.sha256()

    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def create_plan(
    models,
    *,
    seed,
    count=15,
    target_rms=1.0,
    gain_variation=(0.8, 1.2),
):
    """Seleciona modelo e sequência reproduzíveis.

    models: dicionário model_id -> lista de caminhos csv.
    a sequência admite repetição dos sinais disponíveis.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed deve ser inteiro")

    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError("count deve ser inteiro positivo")

    if not models:
        raise ValueError("nenhum modelo disponível")

    if (
        type(target_rms) not in (int, float)
        or not math.isfinite(target_rms)
        or target_rms <= 0
    ):
        raise ValueError("target_rms deve ser positivo e finito")

    if (
        not isinstance(gain_variation, (tuple, list))
        or len(gain_variation) != 2
        or any(
            type(value) not in (int, float)
            or not math.isfinite(value)
            for value in gain_variation
        )
        or gain_variation[0] <= 0
        or gain_variation[1] < gain_variation[0]
    ):
        raise ValueError(
            "gain_variation deve conter limites positivos e ordenados"
        )

    rng = np.random.default_rng(seed)
    model_ids = sorted(models)
    model_id = model_ids[int(rng.integers(len(model_ids)))]
    paths = sorted(str(Path(p).resolve()) for p in models[model_id])

    if not paths:
        raise ValueError("o modelo selecionado não possui sinais")

    sequence = []
    for position in range(count):
        path = paths[int(rng.integers(len(paths)))]
        signal = load_signal(path)

        # Um novo RMS-alvo é sorteado para cada transmissão.
        # O mesmo rng garante reprodução a partir da semente.
        variation = float(
            rng.uniform(gain_variation[0], gain_variation[1])
        )
        entry_target_rms = float(target_rms * variation)
        gain = calculate_gain(signal, entry_target_rms)

        sequence.append({
            "position": position,
            "model_id": model_id,
            "signal_id": Path(path).stem,
            "source": path,
            "sha256": file_sha256(path),
            "gain": gain,
        })

    return {
        "schema_version": 1,
        "seed": seed,
        "target_rms": target_rms,
        "gain_variation": list(gain_variation),
        "sequence": sequence,
    }


def save_plan(plan, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def prepare_entry(entry):
    """Recarrega o arquivo, confere sua identidade e aplica o ganho."""
    path = Path(entry["source"])

    if file_sha256(path) != entry["sha256"]:
        raise ValueError(f"o arquivo do sinal foi alterado: {path}")

    signal = load_signal(path)
    return apply_gain(signal, entry["gain"])


def load_plan(path):
    """Carrega um plano salvo e valida sua estrutura básica."""
    with Path(path).open("r", encoding="utf-8") as source:
        plan = json.load(source)

    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("versão ou formato de plano inválido")

    if type(plan.get("seed")) is not int:
        raise ValueError("seed inválida no plano")

    target_rms = plan.get("target_rms")
    if (type(target_rms) not in (int, float)
            or not math.isfinite(target_rms) or target_rms <= 0):
        raise ValueError("target_rms inválido no plano")

    sequence = plan.get("sequence")
    if not isinstance(sequence, list) or not sequence:
        raise ValueError("sequência inválida no plano")

    for position, entry in enumerate(sequence):
        if not isinstance(entry, dict):
            raise ValueError("entrada inválida no plano")

        for field in ("model_id", "signal_id", "source", "sha256"):
            if not isinstance(entry.get(field), str) or not entry[field]:
                raise ValueError(f"campo inválido no plano: {field}")

        if type(entry.get("position")) is not int or entry["position"] != position:
            raise ValueError("posição inválida no plano")

        gain = entry.get("gain")
        if type(gain) not in (int, float) or not math.isfinite(gain) or gain <= 0:
            raise ValueError("ganho inválido no plano")

    return plan

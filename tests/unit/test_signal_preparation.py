import numpy as np
import pytest

from client.signal_preparation import (
    apply_gain,
    calculate_gain,
    create_plan,
    load_signal,
    prepare_entry,
    save_plan,
)


def test_load_signal(tmp_path):
    path = tmp_path / "g.csv"
    np.savetxt(path, [1.0, 2.0, 3.0], delimiter=",")

    np.testing.assert_array_equal(load_signal(path, 3), [1, 2, 3])

    with pytest.raises(ValueError, match="dimensão"):
        load_signal(path, 4)


def test_gain_reaches_target_rms():
    signal = np.array([1.0, 2.0, 3.0])

    gain = calculate_gain(signal, target_rms=2.0)
    amplified = apply_gain(signal, gain)

    assert np.sqrt(np.mean(amplified ** 2)) == pytest.approx(2.0)


def test_zero_signal_rejected():
    with pytest.raises(ValueError, match="nulo"):
        calculate_gain(np.zeros(3))


def test_plan_is_reproducible(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"

    np.savetxt(first, [1, 2, 3], delimiter=",")
    np.savetxt(second, [4, 5, 6], delimiter=",")

    models = {"demo": [first, second]}

    plan_a = create_plan(models, seed=42, count=15)
    plan_b = create_plan(models, seed=42, count=15)

    assert plan_a == plan_b
    assert len(plan_a["sequence"]) == 15

    save_plan(plan_a, tmp_path / "plan.json")
    assert (tmp_path / "plan.json").is_file()

    for entry in plan_a["sequence"]:
        prepared = prepare_entry(entry)
        assert prepared.shape == (3,)
        assert 0.8 - 1e-10 <= np.sqrt(np.mean(prepared ** 2)) <= 1.2 + 1e-10


def test_modified_signal_is_rejected(tmp_path):
    path = tmp_path / "signal.csv"
    np.savetxt(path, [1, 2, 3], delimiter=",")

    plan = create_plan({"demo": [path]}, seed=7, count=1)

    np.savetxt(path, [9, 8, 7], delimiter=",")

    with pytest.raises(ValueError, match="alterado"):
        prepare_entry(plan["sequence"][0])


def test_saved_plan_can_be_loaded_and_replayed(tmp_path):
    from client.signal_preparation import load_plan

    path = tmp_path / "signal.csv"
    np.savetxt(path, [1.0, 2.0, 3.0], delimiter=",")

    original = create_plan(
        {"demo": [path]},
        seed=42,
        count=15,
        target_rms=2.0,
    )

    destination = tmp_path / "experiment.json"
    save_plan(original, destination)

    restored = load_plan(destination)

    assert restored == original

    for entry in restored["sequence"]:
        prepared = prepare_entry(entry)
        assert 1.6 - 1e-10 <= np.sqrt(np.mean(prepared ** 2)) <= 2.4 + 1e-10


def test_invalid_saved_plan_is_rejected(tmp_path):
    from client.signal_preparation import load_plan

    path = tmp_path / "invalid.json"
    path.write_text('{"schema_version": 999}', encoding="utf-8")

    with pytest.raises(ValueError, match="versão"):
        load_plan(path)


def test_gain_varies_between_repeated_transmissions(tmp_path):
    path = tmp_path / "repeated.csv"
    np.savetxt(path, [1.0, 2.0, 3.0], delimiter=",")

    models = {"demo": [path]}

    first = create_plan(
        models,
        seed=42,
        count=15,
        target_rms=2.0,
    )

    repeated = create_plan(
        models,
        seed=42,
        count=15,
        target_rms=2.0,
    )

    different_seed = create_plan(
        models,
        seed=43,
        count=15,
        target_rms=2.0,
    )

    first_gains = [
        entry["gain"]
        for entry in first["sequence"]
    ]

    repeated_gains = [
        entry["gain"]
        for entry in repeated["sequence"]
    ]

    different_gains = [
        entry["gain"]
        for entry in different_seed["sequence"]
    ]

    assert len(set(first_gains)) == 15
    assert first_gains == repeated_gains
    assert first_gains != different_gains

    for entry in first["sequence"]:
        prepared = prepare_entry(entry)
        rms = float(np.sqrt(np.mean(prepared ** 2)))
        assert 1.6 - 1e-10 <= rms <= 2.4 + 1e-10


def test_gain_variation_can_be_configured(tmp_path):
    path = tmp_path / "signal.csv"
    np.savetxt(path, [1.0, 2.0, 3.0], delimiter=",")

    plan = create_plan(
        {"demo": [path]},
        seed=10,
        count=5,
        target_rms=2.0,
        gain_variation=(0.5, 1.5),
    )

    assert plan["gain_variation"] == [0.5, 1.5]

    for entry in plan["sequence"]:
        prepared = prepare_entry(entry)
        rms = float(np.sqrt(np.mean(prepared ** 2)))
        assert 1.0 - 1e-10 <= rms <= 3.0 + 1e-10


def test_invalid_gain_variation_is_rejected(tmp_path):
    path = tmp_path / "signal.csv"
    np.savetxt(path, [1.0, 2.0, 3.0], delimiter=",")

    for invalid in (
        (0.0, 1.0),
        (1.2, 0.8),
        (float("nan"), 1.0),
        (0.8,),
    ):
        with pytest.raises(ValueError, match="gain_variation"):
            create_plan(
                {"demo": [path]},
                seed=42,
                gain_variation=invalid,
            )

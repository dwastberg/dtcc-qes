"""Guard the study against false acceptance of inaccurate or masked results."""
import copy
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "vertical_grid_study", Path(__file__).parents[1] / "tools/run_vertical_grid_study.py")
study = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(study)


def stable_run():
    return {"hmax": 12, "checkpoints": [
        {"iterations": n, "max_divergence": 1e-5, "rms_divergence": 1e-6,
         "velocity": [[5., 0., 0.], None, [1., 0., 0.]]}
        for n in (1000, 2000, 4000)]}


def test_stability_is_required_at_both_successive_comparisons():
    run = stable_run()
    assert study.evaluate(run)["accepted"]
    run["checkpoints"][0]["velocity"][0] = [0., 5., 0.]
    # Speeds agree exactly, but velocity vectors do not.
    result = study.evaluate(run)
    assert not result["accepted"]
    assert not result["changes"][0]["pass"]
    assert result["changes"][1]["pass"]


@pytest.mark.parametrize("checkpoint", [0, 1, 2])
@pytest.mark.parametrize("field,value", [("max_divergence", .001), ("rms_divergence", .001)])
def test_any_residual_checkpoint_can_reject_a_stable_plane(checkpoint, field, value):
    run = stable_run()
    run["checkpoints"][checkpoint][field] = value
    assert not study.evaluate(run)["accepted"]


def test_changing_validity_does_not_hide_a_stability_failure():
    run = stable_run()
    run["checkpoints"][0]["velocity"][2] = None
    result = study.evaluate(run)
    assert not result["accepted"]
    assert result["changes"][0]["mask_changes"] == 1


def test_empty_common_plane_is_not_an_accuracy_pass():
    run = stable_run()
    run["checkpoints"][1]["velocity"] = [None] * 3
    with pytest.raises(ValueError, match="No common-fluid"):
        study.evaluate(run)


def test_comparison_uses_vector_magnitude_after_component_sampling():
    a, b = stable_run(), copy.deepcopy(stable_run())
    b["checkpoints"][-1]["velocity"][0] = [3., 4., 0.]
    stats = study.compare(a, b, study.plane(a["checkpoints"][-1])[1])
    assert stats["max_abs_delta_K"] == 0  # Both vectors have magnitude 5.
    assert stats["vector_max_delta_over_Uref"] > .8


def test_failed_accuracy_withholds_error_and_runtime_comparisons():
    good = stable_run() | {"geometry": "isolated", "direction": 270, "grid": "2", "repeat": 0,
        "layers": 32, "cells": 51200, "z_faces": list(range(0, 65, 2)), "roof_errors": [0],
        "peak_rss_bytes": 1000000, "prep_seconds": .1}
    for c in good["checkpoints"]:
        c.update(solve_seconds=1, sampling_seconds=.001, top_band_max_divergence=.01)
    bad = copy.deepcopy(good)
    bad["grid"] = "0.5"
    bad["checkpoints"][0]["max_divergence"] = .001
    result = study.summarize({"metadata": {}, "runs": [good, bad]})
    pair, = result["comparisons"]
    assert not pair["matched_accuracy"]
    assert "final_solve_time_ratio" not in pair
    assert "p95_abs_delta_K" not in pair

"""Independent checks of the C2 collocation and acceptance decisions."""

from fixtures.support import load_tool
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

_tools = Path(__file__).parents[1]/"tools"
controls = load_tool("auto_grid_controls", _tools/"run_auto_grid_controls.py")


from fixtures.auto_grid_controls import document, native_run, worker

def test_horizontal_collocation_preserves_affine_components():
    axis = np.array([1.5, 2.5, 3.5, 4.5])
    yy, xx = np.meshgrid(axis, axis, indexing="ij")
    values = np.stack([2+3*xx-yy, xx+yy, -2*xx], axis=-1)
    points = np.array([2., 3., 4.])
    actual = controls.collocate(values.reshape(-1, 3), axis, axis, points)
    yy, xx = np.meshgrid(points, points, indexing="ij")
    expected = np.stack([2+3*xx-yy, xx+yy, -2*xx], axis=-1)
    np.testing.assert_array_equal(np.array(actual).reshape(3, 3, 3), expected)


def test_collocation_interpolates_components_before_speed():
    values = [[5., 0., 0.], [-5., 0., 0.]]*2
    actual = controls.collocate(values, [0, 2], [0, 2], [1])
    np.testing.assert_array_equal(actual, [[0, 0, 0]])


@pytest.mark.parametrize("corner", range(4))
def test_each_positive_weight_solid_corner_invalidates_sample(corner):
    values = [[5., 0., 0.]]*4
    values[corner] = None
    assert controls.collocate(values, [0, 2], [0, 2], [1]) == [None]


def test_exact_centre_ignores_zero_weight_solid_neighbours():
    values = [[5., 0., 0.], None, None, None]
    assert controls.collocate(values, [0, 2], [0, 2], [0]) == [[5., 0., 0.]]


@pytest.mark.parametrize("points", [[-1], [3]])
def test_collocation_cannot_extrapolate(points):
    with pytest.raises(ValueError, match="extrapolate"):
        controls.collocate([[5., 0., 0.]]*4, [0, 2], [0, 2], points)


def test_tall_control_preserves_effective_lower_faces():
    from dtcc_qes.vertical_grid import effective_faces
    layers = np.r_[np.full(7, 3/7), np.full(61, 1.)]
    extended = controls.extend_layers(layers, 144)
    np.testing.assert_array_equal(extended[:len(layers)], layers)
    np.testing.assert_array_equal(effective_faces(extended)[:len(layers)+1], effective_faces(layers))
    assert extended.sum() == pytest.approx(144)
    assert np.all(extended[len(layers):] >= layers[-1])


def test_instability_at_second_height_rejects_the_whole_run():
    run = native_run()
    assert controls.assess(run)["accepted"]
    run["checkpoints"][0]["planes"][1]["velocity"][0] = [0., 5., 0.]
    stats = controls.assess(run)
    assert not stats["accepted"]
    assert stats["heights"]["1.5"]["accepted"]
    assert not stats["heights"]["1.75"]["accepted"]


def test_failed_solve_withholds_boundary_error_claims():
    a, b = native_run(), native_run("tall")
    b["checkpoints"][0]["max_divergence"] = 1
    summary = controls.summarize(document([a, b]))
    assert not summary["early_controls_within_budget"]
    for c in summary["comparisons"]:
        assert not c["matched_accuracy"]
        assert "p95_abs_delta_K" not in c and "peak_relative_difference" not in c


def test_passing_incomplete_matrix_cannot_open_the_early_gate():
    summary = controls.summarize(document([native_run(), native_run("tall")]))
    assert all(c["within_control_budget"] for c in summary["comparisons"])
    assert not summary["complete"] and not summary["early_controls_within_budget"]


def test_peak_failure_cannot_be_hidden_by_a_small_percentile():
    a, b, c = native_run(), native_run("tall"), native_run("xy1")
    for checkpoint in b["checkpoints"]:
        for plane in checkpoint["planes"]:
            plane["velocity"][0] = [6., 0., 0.]
    summary = controls.summarize(document([a, b, c]))
    assert summary["complete"]
    assert not summary["early_controls_within_budget"]
    failed = [c for c in summary["comparisons"] if c["control"] == "tall"]
    assert all(c["p95_abs_delta_K"] == 0 and not c["within_control_budget"] for c in failed)


def test_fixed_critical_failure_rejects_even_with_unchanged_global_peak():
    a, b, c = native_run(), native_run("tall"), native_run("xy1")
    for checkpoint in c["checkpoints"]:
        for plane in checkpoint["planes"]:
            plane["velocity"][0] = [4.5, 0., 0.]
    summary = controls.summarize(document([a, b, c]))
    failed = [item for item in summary["comparisons"] if item["control"] == "xy1"]
    assert all(item["p95_abs_delta_K"] == 0 and item["peak_relative_difference"] == 0 for item in failed)
    assert all(item["critical_max_relative_difference"] > .1 and not item["within_control_budget"] for item in failed)
    assert not summary["early_controls_within_budget"]


def test_public_plans_use_real_generator_and_preserve_operands():
    from dtcc_qes.vertical_grid import effective_faces
    base, tall, xy = controls.plans("tower", ["auto"])
    assert base["provenance"]["mode"] == "auto"
    assert base["provenance"]["policy_status"] == "prototype_unvalidated"
    assert base["provenance"]["pedestrian_sampling"]["third_centre"] <= 1.5
    np.testing.assert_array_equal(xy["layers_input"], base["layers_input"])
    assert xy["resolution"] == 1
    np.testing.assert_array_equal(effective_faces(tall["layers_input"])[:len(base["expected_faces"])],
                                  base["expected_faces"])


@pytest.mark.parametrize("bad", ["missing", "duplicate", "one_checkpoint", "wrong_sweeps", "negative_residual"])
def test_invalid_certification_data_cannot_pass(bad):
    run = native_run()
    if bad == "missing":
        run["checkpoints"][0]["planes"].pop()
    elif bad == "duplicate":
        run["checkpoints"][0]["planes"][1]["height"] = 1.5
    elif bad == "one_checkpoint":
        run["checkpoints"] = run["checkpoints"][:1]
    elif bad == "wrong_sweeps":
        run["checkpoints"][1]["iterations"] += 1
    else:
        run["checkpoints"][0]["max_divergence"] = -1
    with pytest.raises(ValueError):
        controls.assess(run)


def test_duplicate_repeat_ids_do_not_complete_the_matrix():
    runs = [native_run(c) for c in ("base", "tall", "xy1")]
    doc = document(runs+[copy.deepcopy(r) for r in runs])
    doc["metadata"]["repeats"] = 2
    summary = controls.summarize(doc)
    assert not summary["complete"] and not summary["early_controls_within_budget"]


def test_configurable_worker_preserves_legacy_fields_exactly(worker):
    legacy = json.loads(subprocess.run([str(worker), "isolated", "2", "270", "1"],
        capture_output=True, text=True, check=True).stdout)
    values = [2, 32, 1, 1, *([2]*32), 1.5, 32, 32, 12, 16, 12]
    custom = json.loads(subprocess.run([str(worker), "isolated", "--layers", "270", "1"],
        input=" ".join(map(str, values)), capture_output=True, text=True, check=True).stdout)
    for key in ("z_faces", "roof_errors", "sample_x", "sample_y", "cells", "layers"):
        assert legacy[key] == custom[key]
    for a, b in zip(legacy["checkpoints"], custom["checkpoints"]):
        for key in ("iterations", "velocity", "planes", "max_divergence", "rms_divergence", "assessed_cells"):
            assert a[key] == b[key]


@pytest.mark.parametrize("text", ["", ".5 2 1 1", "2 10001 1 1", "2 2 1 1 -1 .5",
    "2 2 1 1 .5 .5 1.5 32 32 -12 16 12", "2 2 1 1 .5 .5 1.5 32 32 12 16 12 extra"])
def test_configurable_worker_rejects_malformed_inputs(worker, text):
    process = subprocess.run([str(worker), "isolated", "--layers", "270", "1"],
                             input=text, capture_output=True, text=True)
    assert process.returncode != 0 and not process.stdout and process.stderr

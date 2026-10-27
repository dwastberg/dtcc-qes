"""C2b acceptance, sparse support and initialization controls."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from test_auto_grid_controls import native_run

_tools = Path(__file__).parents[1]/"tools"
_spec = importlib.util.spec_from_file_location("horizontal_sensitivity", _tools/"run_horizontal_sensitivity.py")
study = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(_tools))
try:
    _spec.loader.exec_module(study)
finally:
    sys.path.pop(0)

_continuation_spec = importlib.util.spec_from_file_location("horizontal_continuation", _tools/"continue_horizontal_sensitivity.py")
continuation = importlib.util.module_from_spec(_continuation_spec)
sys.path.insert(0, str(_tools))
try:
    _continuation_spec.loader.exec_module(continuation)
finally:
    sys.path.pop(0)


def refs():
    return {(family, direction, resolution): native_run()
            for family in study.FAMILIES for direction in study.DIRECTIONS for resolution in (2, 1)}


def doc_and_refs():
    reference = refs()
    runs = []
    for task in study.tasks():
        run = native_run()
        run["task"] = task
        run["profile_planes"] = copy.deepcopy(run["checkpoints"][0]["planes"])
        run["initial_planes"] = copy.deepcopy(run["profile_planes"])
        if task["kind"] == "probe":
            run["checkpoints"] = []
        runs.append(run)
    return dict(metadata={"frozen_critical_indices": study.frozen_locations(reference)}, runs=runs), reference


def test_initial_only_probes_are_never_counted_as_certified_wind_fields():
    doc, reference = doc_and_refs()
    result = study.summarize(doc, reference)
    assert result["complete"] and result["initial_only_probes"] == 8
    assert result["accepted_final_runs"] == 10
    assert all(not row["certified_solution"] for row in result["initialization"])
    assert result["horizontal_scope_pass"]


def test_any_failed_fine_solve_withholds_its_comparison_and_scope():
    doc, reference = doc_and_refs()
    fine = next(r for r in doc["runs"] if r["task"]["kind"] == "fine")
    fine["checkpoints"][0]["max_divergence"] = 1
    result = study.summarize(doc, reference)
    assert result["complete"] and not result["horizontal_scope_pass"]
    rows = [r for r in result["comparisons"] if r["comparison"] == "1_to_0.5"
            and r["family"] == fine["task"]["family"] and r["direction"] == fine["task"]["direction"]]
    assert len(rows) == 4 and all(not row["matched_accuracy"] for row in rows)
    assert all("p95_abs_delta_K" not in row for row in rows)


def test_frozen_critical_point_cannot_be_replaced_by_a_new_peak_set():
    a, b = native_run(), native_run()
    # A known critical location is deliberately outside the new top ten.
    index = 900
    for p in b["checkpoints"][-1]["planes"]:
        p["velocity"][index] = [4., 0., 0.]
    row = study.comparison(a, b, 1.5, [index])
    assert row["peak_relative_difference"] == 0 and row["p95_abs_delta_K"] == 0
    assert row["frozen_critical_max_relative_difference"] == pytest.approx(.25)
    assert not row["within_budget"]


def test_invalid_frozen_point_cannot_silently_disappear_from_budget():
    a, b = native_run(), native_run()
    for p in b["checkpoints"][-1]["planes"]:
        p["velocity"][0] = None
    row = study.comparison(a, b, 1.5, [0])
    assert row["invalid_frozen_critical_points"] == 1
    assert row["solid_fluid_transitions"] == 1 and not row["within_budget"]


def test_low_speed_critical_locations_use_the_declared_absolute_K_bound():
    a, b = native_run(), native_run()
    for p in a["checkpoints"][-1]["planes"]:
        p["velocity"][0] = [.2, 0., 0.]  # K=0.04
    for p in b["checkpoints"][-1]["planes"]:
        p["velocity"][0] = [.25, 0., 0.]  # 20% relative difference, 0.01 absolute K
    row = study.comparison(a, b, 1.5, [0])
    assert row["within_budget"] and row["frozen_critical_max_relative_difference"] is None
    assert row["frozen_critical_low_speed_max_abs_delta_K"] == pytest.approx(.01)
    for p in b["checkpoints"][-1]["planes"]:
        p["velocity"][0] = [.495, 0., 0.]  # Still K<0.1, but absolute change exceeds 0.05
    assert not study.comparison(a, b, 1.5, [0])["within_budget"]


def test_fixed_away_region_is_geometric_and_does_not_change_full_result():
    points = study.POINTS
    index = int(np.where(points == 21)[0][0])*len(points)+int(np.where(points == 27)[0][0])
    assert study.wall_distance()[index] == 1
    a, b = native_run(), native_run()
    for p in b["checkpoints"][-1]["planes"]:
        p["velocity"][index] = [3., 0., 0.]
    assert not study.comparison(a, b, 1.5, [index])["within_budget"]
    away = study.comparison(a, b, 1.5, [0], "away4m")
    assert away["within_budget"] and away["max_abs_delta_K"] == 0
    assert away["common_fluid_points"] < len(points)**2


def test_incomplete_or_duplicate_task_matrix_cannot_pass_scope():
    doc, reference = doc_and_refs()
    doc["runs"].pop()
    assert not study.summarize(doc, reference)["horizontal_scope_pass"]
    doc["runs"].append(copy.deepcopy(doc["runs"][0]))
    assert not study.summarize(doc, reference)["complete"]


@pytest.fixture
def worker():
    executable = Path(os.environ.get("DTCC_QES_STUDY_EXECUTABLE", "build/extension/vertical_grid_study"))
    if not executable.exists():
        pytest.skip("Build vertical_grid_study for worker integration")
    return executable.resolve()


def configuration():
    return dict(layers_input=[.5]*128)


def execute(worker, task, n):
    process = subprocess.run([str(worker), "tower", "--horizontal", "270", str(n)],
        input=study.input_text(configuration(), task), capture_output=True, text=True, check=True)
    assert not process.stderr
    return json.loads(process.stdout)


def test_horizontal_mode_preserves_legacy_solve_and_both_height_samples(worker):
    task = dict(kind="fine", resolution=1)
    horizontal = execute(worker, task, 1)
    rects = study.rectangles("tower")
    data = [1, 128, 2, 4, *([.5]*128), *study.HEIGHTS, *sum(rects, [])]
    legacy = json.loads(subprocess.run([str(worker), "tower", "--layers", "270", "1"],
        input=" ".join(map(str, data)), capture_output=True, text=True, check=True).stdout)
    for height in study.HEIGHTS:
        a, b = study.height_run(horizontal, height), study.height_run(legacy, height)
        for ca, cb in zip(a["checkpoints"], b["checkpoints"]):
            assert ca["velocity"] == cb["velocity"]
            assert ca["max_divergence"] == cb["max_divergence"]
    assert len(horizontal["sample_x"]) == 76 < len(legacy["sample_x"])


def test_initial_only_half_metre_worker_retains_support_flags_and_neutral_profile(worker):
    run = execute(worker, dict(kind="probe", resolution=.5), 0)
    assert run["checkpoints"] == []
    assert len(run["sample_x"]) == len(run["sample_y"]) == 76
    for height in study.HEIGHTS:
        p = study.audit_point(run, height, [27, 21], "profile")
        assert p["valid"] and len(p["corners"]) == 4
        assert sum(c["weight"] for c in p["corners"]) == 1
        assert all(len(c["flags"]) == 2 and c["flags"][0] not in (0, 2) for c in p["corners"])
        v = np.array([c["velocity"] for c in p["corners"]])
        np.testing.assert_array_equal(v, np.tile(v[0], (4, 1)))


def test_expanded_domain_outputs_world_coordinates_and_preserves_native_z(worker):
    run = execute(worker, dict(kind="lateral", resolution=2), 0)
    assert run["horizontal_bounds"] == [-40, -40, 120, 120]
    assert run["sample_x"] == study.POINTS.tolist() and run["sample_y"] == study.POINTS.tolist()
    assert run["z_faces"] == np.arange(0, 64.5, .5).tolist()


def test_disabled_parameterizations_are_recorded_and_profile_is_preserved(worker):
    run = execute(worker, dict(kind="ablation", resolution=2, disabled=31), 0)
    assert run["disabled_mask"] == 31
    for height in study.HEIGHTS:
        profile = study.audit_point(run, height, [27, 21], "profile")
        initial = study.audit_point(run, height, [27, 21], "initial")
        assert profile["K"] == initial["K"]


@pytest.mark.parametrize("text", ["", ".3 0 0 80 80 128 2 4 0", "1 0 0 80.5 80 128 2 4 0",
    "1 0 0 80 80 128 2 4 32", ".25 0 0 320 320 128 2 4 0 "+" .5"*128])
def test_horizontal_worker_rejects_bad_headers_or_excessive_cell_budget(worker, text):
    proc = subprocess.run([str(worker), "tower", "--horizontal", "270", "0"],
                          input=text, capture_output=True, text=True)
    assert proc.returncode != 0 and not proc.stdout and proc.stderr


def test_horizontal_worker_cell_budget_is_checked_before_flow_allocation(worker):
    text = study.input_text(configuration(), dict(kind="lateral", resolution=.25))
    proc = subprocess.run([str(worker), "tower", "--horizontal", "270", "0"],
                          input=text, capture_output=True, text=True)
    assert proc.returncode != 0 and not proc.stdout
    assert "cell limit" in proc.stderr


@pytest.mark.parametrize("changed", ["source", "worker", "reference", "continuation"])
def test_continuation_rejects_changed_acquisition_inputs(tmp_path, changed):
    paths = {name: tmp_path/name for name in ("source", "worker", "reference", "continuation")}
    for path in paths.values():
        path.write_text("original")
    metadata = dict(source_sha256={str(paths["source"]): study.digest(paths["source"])},
        executable=str(paths["worker"]), executable_sha256=study.digest(paths["worker"]),
        reference=str(paths["reference"]), reference_sha256=study.digest(paths["reference"]),
        continuations=[dict(source=str(paths["continuation"]), sha256=study.digest(paths["continuation"]))])
    continuation.validate({"metadata": metadata})
    paths[changed].write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        continuation.validate({"metadata": metadata})


@pytest.mark.parametrize("failed,expected", [([], 1000), ([1000], 2000), ([1000, 2000], 4000)])
def test_continuation_resumes_after_completed_failed_budgets(failed, expected):
    task = dict(id="example", kind="fine")
    doc = dict(metadata=dict(initial_n=1000, max_n=4000), attempts=[
        dict(task=task, checkpoints=[dict(iterations=n)]) for n in failed])
    assert continuation.next_budget(doc, task) == expected
    assert continuation.next_budget(doc, dict(id="probe", kind="probe")) == 0

"""The precision-reference gate must protect subsequent grid comparisons."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest
from test_auto_grid_controls import native_run

_tools = Path(__file__).parents[1]/"tools"
_spec = importlib.util.spec_from_file_location("precision_verification", _tools/"run_precision_verification.py")
study = importlib.util.module_from_spec(_spec)
sys.path.insert(0, str(_tools))
try:
    _spec.loader.exec_module(study)
finally:
    sys.path.pop(0)


def precision_document():
    runs = []
    for task in study.tasks("precision"):
        run = native_run()
        run.update(task=task, start="zero", precision=task["precision"], solver_workspace_bytes=100)
        runs.append(run)
    return dict(metadata=dict(phase="precision"), runs=runs)


def test_precision_prerequisite_requires_all_cases_and_full_tighter_checkpoints():
    doc = precision_document()
    study.require_precision_reference(doc)
    assert study.summarize(doc)["tighter_accepted"] == len(doc["runs"])
    # A tight final residual cannot conceal failing earlier checkpoints.
    for run in doc["runs"]:
        run["checkpoints"][0]["max_divergence"] = 1e-4
    assert all(study.gate(r)["accepted"] for r in doc["runs"])
    assert not any(study.gate(r)["ten_times_tighter_accepted"] for r in doc["runs"])
    with pytest.raises(ValueError, match="tighter"):
        study.require_precision_reference(doc)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "warm", "float32", "residual", "second_height"])
def test_precision_references_cannot_be_accepted_by_label_alone(mutation):
    doc = precision_document()
    run = doc["runs"][0]
    if mutation == "missing":
        doc["runs"].pop()
    elif mutation == "duplicate":
        doc["runs"][-1] = copy.deepcopy(run)
    elif mutation == "warm":
        run["start"] = "warm"
    elif mutation == "float32":
        run["precision"] = "float32"
    elif mutation == "residual":
        run["checkpoints"][0]["max_divergence"] = 1
    else:
        run["checkpoints"][0]["planes"][1]["velocity"][0] = [0, 5, 0]
    with pytest.raises(ValueError):
        study.require_precision_reference(doc)


def test_verification_preserves_world_grid_phase_and_production_flags():
    configs = {f: dict(layers_input=[.5]*128) for f in study.FAMILIES}
    jobs = study.tasks("verification")
    assert {t["extent"] for t in jobs} == {160, 240}
    assert len(jobs) == 8
    for task in jobs:
        tokens = list(map(float, study.input_text(task, configs).split()))
        resolution, x0, y0, lx, ly, nz, nh, nb, disabled = tokens[:9]
        assert resolution == 1 and x0 == y0 == (80-task["extent"])/2
        assert x0 % 2 == 0 and y0 % 2 == 0 and lx == ly == task["extent"]
        assert disabled == 0 and nz == 128 and nh == 2 and nb == 4
        assert tokens[9:137] == [.5]*128
        assert tokens[137:139] == [1.5, 1.75]

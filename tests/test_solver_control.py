"""Bounded public/native continuation, snapshots, failures and serialization."""
from dataclasses import asdict, replace
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from dtcc_qes import wind, _qes
from test_condition_state import configuration, prepare
from fixtures.cases import ONE_BUILDING
from city_cases import city_case
from test_datasets import fetched, source_city


def settings(**changes):
    return wind.SolverControl(10, wind.MonitorSpec((0, 100, 0, 80),
        receptors=(wind.Receptor("street", 25, 21, 1.5),), history_limit=4), checkpoint_interval=1, **changes)


@pytest.mark.parametrize("precision", ["float32", "float64"])
@pytest.mark.parametrize("stretched", [False, True])
def test_controlled_completed_work_matches_legacy_and_owns_history(precision, stretched):
    config = configuration(stretched)
    runner = prepare(config)
    c, opts = _qes.WindCondition(), _qes.SolverOptions()
    c.direction = 33; opts.precision = precision; opts.max_iterations = 8
    expected = runner.solve(c, opts)
    actual = runner.solve(c, opts, control=settings(residual_interval=2)._native((0, 0, 0), None))
    np.testing.assert_array_equal(actual["velocity"], expected["velocity"])
    np.testing.assert_array_equal(actual["cell_flags"], expected["cell_flags"])
    assert actual["diagnostics"] == expected["diagnostics"]
    record = actual["control"]
    assert record["termination_reason"] == "iteration_limit" and record["accuracy_status"] == "not_assessed"
    assert record["iterations"] == 8 and len(record["checkpoint_history"]) == 4
    assert record["history_truncated"] and record["checkpoint_count"] == 9
    assert [h["iteration"] for h in record["checkpoint_history"]] == [5, 6, 7, 8]
    assert record["checkpoint_history"][-1]["residual_trend"]["iteration"] == 8
    del runner
    assert actual["velocity"].flags.owndata
    json.dumps(record, allow_nan=False)


def test_zero_work_budget_error_and_same_runner_retry():
    runner = prepare(configuration())
    c, opts = _qes.WindCondition(), _qes.SolverOptions(); opts.max_iterations = 3
    with pytest.raises(wind.BudgetExhaustedError) as caught:
        runner.solve(c, opts, control=replace(settings(), max_solve_seconds=1e-12)._native((0, 0, 0), None))
    record = caught.value.record
    assert record["iterations"] == 0 and record["termination_reason"] == "time_limit"
    assert record["accuracy_status"] == "not_assessed" and record["phase"] == "mutex_wait"
    assert record["timings"]["mutex_wait_seconds"] > 0
    json.dumps(record, allow_nan=False)
    assert runner.solve(c, opts)["diagnostics"]["iterations"] == 3


def test_public_world_frame_warning_and_initial_history(caplog):
    city, condition, grid, _ = city_case(ONE_BUILDING, (1e9, -2e9, 100))
    b = grid["bounds"]
    monitor = wind.MonitorSpec((b[0], b[3], b[1], b[4]), frame="world")
    r = wind.run(city, **condition, **grid, max_iterations=2,
                 solver_control=wind.SolverControl(10, monitor, checkpoint_interval=1))
    assert tuple(r.control["monitor"]["origin"]) == (1e9, -2e9, 100)
    assert r.control["execution"]["precision"] == "float32"
    assert r.control["checkpoint_history"][0]["initial"]
    assert not r.control["checkpoint_history"][0]["heights"][0]["short_change"]["available"]
    assert "termination: iteration_limit" in caplog.text
    json.dumps(r.metadata, allow_nan=False)
    with pytest.raises(wind.ConvergenceError) as caught:
        wind.run(city, **condition, **grid, max_iterations=1, raise_on_nonconvergence=True,
                 solver_control=wind.SolverControl(10, monitor))
    assert caught.value.control["termination_reason"] == "iteration_limit"


@pytest.mark.parametrize("change", [dict(mode="adaptive"), dict(max_solve_seconds=0),
    dict(max_solve_seconds=float("nan")), dict(checkpoint_interval=0), dict(residual_interval=-1),
    dict(checkpoint_interval=True)])
def test_invalid_settings_rejected(change):
    with pytest.raises((ValueError, TypeError)):
        replace(settings(), **change)


def test_monitor_inputs_are_immutable_snapshots_and_roundtrip():
    roi, heights = [0, 100, 0, 80], [1.5, 1.75]
    monitor = wind.MonitorSpec(roi, heights)
    roi[1] = 0; heights.append(6)
    assert monitor.region == (0, 100, 0, 80) and monitor.heights == (1.5, 1.75)
    c = wind.SolverControl(5, monitor)
    assert wind.SolverControl.from_dict(json.loads(json.dumps(asdict(c)))) == c


def test_native_invalid_config_and_monitor_budget_raise_then_retry():
    runner = prepare(configuration()); c, opts = _qes.WindCondition(), _qes.SolverOptions(); opts.max_iterations = 2
    value = settings()._native((0, 0, 0), None)
    value["monitor"]["memory_limit_bytes"] = 1
    with pytest.raises(ValueError, match="memory"):
        runner.solve(c, opts, control=value)
    value = settings()._native((0, 0, 0), None); value["mode"] = "adaptive"
    with pytest.raises(ValueError, match="bounded"):
        runner.solve(c, opts, control=value)
    assert runner.solve(c, opts)["diagnostics"]["iterations"] == 2


def test_dataset_control_identity_and_health(fetched, source_city):
    from dtcc_core import datasets
    from dtcc_qes.datasets import QESWindArgs
    from test_datasets import request
    c = wind.SolverControl(10, wind.MonitorSpec((0, 42, 0, 36)), checkpoint_interval=1)
    args = QESWindArgs(**request(max_iterations=2, solver_control=asdict(c)))
    assert args.wind_options()["solver_control"] == c
    result = datasets.qes_wind(**request(max_iterations=2, solver_control=asdict(c)))
    assert result.dataset_context.health["solver_control"]["accuracy_status"] == "not_assessed"
    assert not result.dataset_context.health["execution_deterministic"]
    dumped = result.dataset_context.model_dump(mode="json")
    assert "max_solve_seconds" in json.dumps(dumped, allow_nan=False)


def test_real_deadlines_and_parallel_calls_do_not_deadlock():
    script = r'''
from concurrent.futures import ThreadPoolExecutor
from dtcc_core.model import City
from dtcc_qes import wind
def run(i):
    control=wind.SolverControl(1e-12 if i==0 else 5,wind.MonitorSpec((0,24,0,20)))
    try:
        r=wind.run(City(),5,270,bounds=(0,0,0,24,20,12),solver_control=control)
        assert r.control['accuracy_status']=='not_assessed'
        return r.diagnostics.iterations
    except wind.BudgetExhaustedError as e:
        assert e.record['iterations']==0
        return 0
with ThreadPoolExecutor(2) as pool:
    result=list(pool.map(run,range(4)))
assert result==[0,1,1,1],result
'''
    subprocess.run([sys.executable, "-c", script], check=True, timeout=20, capture_output=True,
                   env=os.environ | {"OMP_NUM_THREADS":"2", "OMP_DYNAMIC":"FALSE"})

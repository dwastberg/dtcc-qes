"""Lifecycle observations use the supported runner, without a research adapter."""
import gc
import threading
import weakref

import numpy as np
import pytest

from dtcc_qes import _qes, wind
from fixtures.cases import ONE_BUILDING
from fixtures.condition_state import configuration, prepare
from runner_cases import inputs, prepared


def ownership():
    return {k: (v["objects"], v["bytes"]) for k, v in _qes._resource_usage().items()
            if isinstance(v, dict)}


def test_workspace_replacement_releases_before_allocation_and_balances_ownership():
    gc.collect()
    baseline = ownership()
    runner = prepare(configuration(stretched=True))
    condition, options = _qes.WindCondition(), _qes.SolverOptions()
    options.max_iterations = 20
    _qes._reset_resource_peaks()
    for index in range(18):
        options.precision = "float64" if index % 4 == 0 else "float32"
        options.tolerance = 1e-4 if index % 3 == 0 else 1e-5
        result = runner.solve(condition, options)
        usage = _qes._resource_usage()["solver_workspace"]
        assert usage["objects"] == usage["peak_objects"] == baseline["solver_workspace"][0] + 1
        assert usage["bytes"] > baseline["solver_workspace"][1]
        assert runner._progress["phase"] == "completed"
        del result
    del runner
    gc.collect()
    assert ownership() == baseline


def test_failed_preparation_preserves_geometry_and_balances_partial_ownership():
    gc.collect()
    baseline = ownership()
    runner, condition, options = prepared(ONE_BUILDING)
    expected = runner.solve(condition, options)
    live = ownership()
    grid, model, _, _, arrays = inputs(ONE_BUILDING)
    arrays["heights"][:] = -1
    operation = runner._progress["operation_id"]
    with pytest.raises(ValueError): runner.prepare(grid, model, **arrays)
    assert runner._progress["operation_id"] == operation + 1
    assert runner._progress["phase"] == "failed" and runner._progress["finished"]
    assert ownership() == live
    np.testing.assert_array_equal(runner.solve(condition, options)["velocity"], expected["velocity"])
    del runner
    gc.collect()
    assert ownership() == baseline


def test_numerical_failure_discards_workspace_and_allows_identical_retry():
    gc.collect()
    runner = prepare(configuration(rooftop_flag=0, upwind_cavity_flag=0,
        street_canyon_flag=0, sidewall_flag=0, wake_flag=0))
    condition, options = _qes.WindCondition(), _qes.SolverOptions()
    expected = runner.solve(condition, options)
    live = ownership()
    condition.speed = 4e37
    with pytest.raises(RuntimeError, match="Non-finite Lagrange multiplier change"):
        runner.solve(condition, options)
    assert runner._progress["phase"] == "failed" and runner._progress["finished"]
    assert ownership()["solver_workspace"][0] == live["solver_workspace"][0] - 1
    condition.speed = 5
    np.testing.assert_array_equal(runner.solve(condition, options)["velocity"], expected["velocity"])


def test_progress_during_supported_control_reports_completed_sweeps_and_checkpoints():
    config = configuration(stretched=True)
    runner = prepare(config)
    condition, options = _qes.WindCondition(), _qes.SolverOptions()
    options.max_iterations = 3000
    options.tolerance = 1.2e-7
    control = wind.Solver(max_solve_seconds=30, monitor=wind.MonitorSpec((0, 100, 0, 80), history_limit=4),
                          checkpoint_interval=20)._native((0, 0, 0), None)
    results, failures = [], []
    def solve():
        try: results.append(runner.solve(condition, options, control=control))
        except BaseException as error: failures.append(error)
    thread = threading.Thread(target=solve)
    thread.start()
    snapshots = []
    while thread.is_alive():
        snapshots.append(runner._progress)
        thread.join(.001)
    assert not failures
    assert any(not s["finished"] and s["completed_sweeps"] > 0 for s in snapshots)
    assert any(not s["finished"] and s["last_checkpoint"] > 0 for s in snapshots)
    final = runner._progress
    assert final["finished"] and final["phase"] == "completed"
    assert final["completed_sweeps"] == results[0]["diagnostics"]["iterations"]
    assert final["last_checkpoint"] == results[0]["control"]["checkpoint_history"][-1]["iteration"]
    assert final["last_completed_stage"] == "projection"
    fresh = prepare(config).solve(condition, options, control=control)
    np.testing.assert_array_equal(results[0]["velocity"], fresh["velocity"])
    np.testing.assert_array_equal(results[0]["cell_flags"], fresh["cell_flags"])


def test_failed_binding_transfer_is_terminal_and_runner_remains_reusable(monkeypatch):
    from dtcc_qes import _logging
    runner, condition, options = prepared(ONE_BUILDING)
    expected = runner.solve(condition, options)["velocity"]
    original = _logging._log_solve
    def fail(result): raise ValueError("Injected output-transfer failure")
    monkeypatch.setattr(_logging, "_log_solve", fail)
    with pytest.raises(ValueError, match="output-transfer failure"): runner.solve(condition, options)
    assert runner._progress["phase"] == "failed" and runner._progress["finished"]
    monkeypatch.setattr(_logging, "_log_solve", original)
    np.testing.assert_array_equal(runner.solve(condition, options)["velocity"], expected)
    assert runner._progress["phase"] == "completed"


def test_result_arrays_release_independently_of_prepared_native_domain():
    gc.collect()
    grid, model, condition, options, arrays = inputs(ONE_BUILDING)
    runner = _qes.WindRunner()
    turbulence = _qes.TurbulenceSettings(); turbulence.enabled = True
    runner.prepare(grid, model, **arrays, turbulence=turbulence)
    result = runner.solve(condition, options)
    references = [weakref.ref(value) for value in result.values() if isinstance(value, np.ndarray)]
    references += [weakref.ref(value) for value in result["turbulence"].values() if isinstance(value, np.ndarray)]
    assert references and all(reference() is not None for reference in references)
    live = ownership()
    del result
    gc.collect()
    assert all(reference() is None for reference in references)
    assert ownership() == live
    assert runner.solve(condition, options)["velocity"].size > 0

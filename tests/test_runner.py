"""Step 4 exercises the private array boundary, without the city adapter."""

import gc
import logging
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from dtcc_core.common import get_python_logger
from dtcc_qes import _qes

from fixtures.cases import CASES, FLAT, ONE_BUILDING, reference_path
from runner_cases import inputs, prepared


def assert_reference_velocity(actual, expected):
    # The references use Apple Clang 17 on arm64. Keep exact comparisons on
    # that host family. Other compiler/libm combinations may round float32
    # profiles and SOR updates differently: 1e-5 relative, 2e-5 m/s absolute.
    # Coordinate and classification comparisons remain exact on every host.
    if sys.platform == "darwin" and platform.machine() == "arm64":
        np.testing.assert_array_equal(actual, expected)
    else:
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=2e-5)


@pytest.fixture(autouse=True)
def quiet_logger():
    logger = get_python_logger("dtcc-qes")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    logger.handlers = [logging.NullHandler()]
    logger.propagate = True
    logger.setLevel(logging.DEBUG)
    yield logger
    logger.handlers, logger.level, logger.propagate = handlers, level, propagate


@pytest.mark.parametrize("case", CASES.values(), ids=CASES)
def test_bound_runner_matches_reference(case):
    runner, condition, solver = prepared(case)
    result = runner.solve(condition, solver)
    with np.load(reference_path(case)) as reference:
        for name in ("x", "y", "z"):
            np.testing.assert_array_equal(result[name], reference[name])
        for component, name in enumerate(("u", "v", "w")):
            assert_reference_velocity(result["velocity"][..., component], reference[name])
        np.testing.assert_array_equal(result["cell_flags"], reference["icell"])
    g = case.grid
    assert result["velocity"].shape == (g.nz, g.ny, g.nx, 3)
    assert result["cell_flags"].shape == (g.nz, g.ny, g.nx)
    for name in ("x", "y", "z", "velocity", "cell_flags"):
        array = result[name]
        assert array.flags.c_contiguous and array.flags.owndata
        assert array.dtype == (np.int32 if name == "cell_flags" else np.float32)
    diagnostics = result["diagnostics"]
    assert diagnostics["converged"]
    assert diagnostics["max_lagrange_multiplier_change"] <= diagnostics["tolerance"]
    assert result["building_count"] == len(case.buildings)


def test_results_survive_runner_and_do_not_alias_later_solves():
    runner, condition, solver = prepared(ONE_BUILDING)
    first = runner.solve(condition, solver)
    snapshot = {key: value.copy() for key, value in first.items() if isinstance(value, np.ndarray)}
    condition.direction = 90
    second = runner.solve(condition, solver)
    assert not np.array_equal(first["velocity"], second["velocity"])
    condition.direction = ONE_BUILDING.wind.direction
    third = runner.solve(condition, solver)
    np.testing.assert_array_equal(first["velocity"], third["velocity"])
    del runner
    gc.collect()
    for key, expected in snapshot.items():
        np.testing.assert_array_equal(first[key], expected)
        assert not np.shares_memory(first[key], third[key])


def test_preparation_snapshots_input_arrays_and_settings():
    grid, model, condition, solver, arrays = inputs(ONE_BUILDING)
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays)
    arrays["vertices"][:] = np.nan
    arrays["heights"][:] = -1
    model.roughness_length = 20
    grid.nx = 3
    result = runner.solve(condition, solver)
    with np.load(reference_path(ONE_BUILDING)) as reference:
        assert_reference_velocity(result["velocity"][..., 0], reference["u"])


def test_logs_use_dtcc_logger_after_native_work(caplog):
    with caplog.at_level(logging.DEBUG, logger="dtcc-qes"):
        runner, condition, solver = prepared(ONE_BUILDING)
        runner.solve(condition, solver)
    records = [r for r in caplog.records if r.name == "dtcc-qes"]
    assert any(r.levelno == logging.DEBUG and "QES" in r.message for r in records)
    summaries = [r for r in records if r.levelno == logging.INFO]
    assert len(summaries) == 1
    assert "40 x 30 x 20, 1 buildings" in summaries[0].message
    assert "converged=True" in summaries[0].message
    assert not any(r.levelno >= logging.ERROR for r in records)


def test_warning_forwarding_and_native_failure_is_not_logged_twice(caplog):
    from dtcc_qes._logging import _forward_native_messages

    with caplog.at_level(logging.DEBUG, logger="dtcc-qes"):
        _forward_native_messages([(logging.WARNING, "buffered warning\n")])
        with pytest.raises(RuntimeError, match="Prepare"):
            _qes.WindRunner().solve(_qes.WindCondition())
    assert [(r.levelno, r.message) for r in caplog.records] == [(logging.WARNING, "buffered warning")]


def test_nonconvergence_and_tolerance_change():
    runner, condition, solver = prepared(ONE_BUILDING)
    solver.max_iterations = 1
    diagnostics = runner.solve(condition, solver)["diagnostics"]
    assert not diagnostics["converged"] and diagnostics["iterations"] == 1
    assert diagnostics["max_lagrange_multiplier_change"] > diagnostics["tolerance"]
    solver.max_iterations = 500
    solver.tolerance = 1e-4
    assert runner.solve(condition, solver)["diagnostics"]["converged"]


@pytest.mark.parametrize("field, value", [
    ("offsets", np.array([], dtype=np.int64)),
    ("offsets", np.array([1, 5], dtype=np.int64)),
    ("offsets", np.array([0, 6], dtype=np.int64)),
    ("offsets", np.array([0, -1], dtype=np.int64)),
    ("offsets", np.array([0, 2**63 - 1], dtype=np.int64)),
    ("heights", np.array([], dtype=np.float64)),
    ("base_heights", np.array([], dtype=np.float64)),
    ("ids", np.array([], dtype=np.int64)),
    ("ids", np.array([-1], dtype=np.int64)),
    ("ids", np.array([2**40], dtype=np.int64)),
    ("heights", np.array([np.nan], dtype=np.float64)),
    ("heights", np.array([40], dtype=np.float64)),
    ("base_heights", np.array([1], dtype=np.float64)),
])
def test_malformed_lengths_and_values_preserve_prepared_state(field, value):
    runner, condition, solver = prepared(FLAT)
    grid, model, _, _, arrays = inputs(ONE_BUILDING)
    arrays[field] = value
    with pytest.raises(ValueError):
        runner.prepare(grid, model, **arrays)
    assert runner.solve(condition, solver)["building_count"] == 0


@pytest.mark.parametrize("mutation", ["nan", "outside", "unclosed", "winding", "float_collapse"])
def test_native_polygon_guards(mutation):
    grid, model, _, _, arrays = inputs(ONE_BUILDING)
    vertices = arrays["vertices"]
    if mutation == "nan":
        vertices[1, 0] = np.nan
    elif mutation == "outside":
        vertices[1, 0] = -1
    elif mutation == "unclosed":
        vertices[-1] = (31, 25)
    elif mutation == "winding":
        arrays["vertices"] = vertices[::-1].copy()
    else:
        vertices[1] = vertices[0] + 1e-10
    with pytest.raises(ValueError):
        _qes.WindRunner().prepare(grid, model, **arrays)


@pytest.mark.parametrize("field, value", [
    ("vertices", np.zeros((5, 2), dtype=np.float32)),
    ("vertices", np.zeros((5, 3), dtype=np.float64)),
    ("vertices", np.zeros((5, 4), dtype=np.float64)[:, ::2]),
    ("offsets", np.array([0, 5], dtype=np.int32)),
    ("heights", [8.0]),
    ("heights", np.ones((1, 1), dtype=np.float64)),
])
def test_binding_rejects_incompatible_numpy_buffers(field, value):
    grid, model, _, _, arrays = inputs(ONE_BUILDING)
    arrays[field] = value
    with pytest.raises(TypeError):
        _qes.WindRunner().prepare(grid, model, **arrays)


@pytest.mark.parametrize("field, value", [("nx", 0), ("nx", 10001), ("cell_size", np.inf),
                                          ("cell_size", 1e-100), ("max_cells", 10)])
def test_grid_validation_before_allocation(field, value):
    grid, model, _, _, arrays = inputs(FLAT)
    setattr(grid, field, value)
    with pytest.raises(ValueError):
        _qes.WindRunner().prepare(grid, model, **arrays)


@pytest.mark.parametrize("field, value", [("speed", -1), ("speed", 1e300), ("direction", np.nan),
                                          ("direction", 360), ("reference_height", 0)])
def test_invalid_wind_recovers(field, value):
    runner, condition, solver = prepared(FLAT)
    original = getattr(condition, field)
    setattr(condition, field, value)
    with pytest.raises(ValueError):
        runner.solve(condition, solver)
    setattr(condition, field, original)
    assert runner.solve(condition, solver)["diagnostics"]["converged"]


def test_invalid_solver_recovers():
    runner, condition, solver = prepared(FLAT)
    solver.tolerance = 1e-12
    with pytest.raises(ValueError, match="epsilon"):
        runner.solve(condition, solver)
    solver.tolerance = 1e-5
    solver.max_iterations = 0
    with pytest.raises(ValueError, match="iterations"):
        runner.solve(condition, solver)
    solver.max_iterations = 500
    assert runner.solve(condition, solver)["diagnostics"]["converged"]


@pytest.mark.parametrize("field, value", [("roughness_length", 0), ("roughness_length", np.nan),
                                          ("sensor_x", -1), ("sensor_y", 1e300),
                                          ("wall_roughness", -1), ("wake_flag", 99)])
def test_model_validation(field, value):
    grid, model, _, _, arrays = inputs(FLAT)
    setattr(model, field, value)
    with pytest.raises(ValueError):
        _qes.WindRunner().prepare(grid, model, **arrays)


def test_readonly_inputs_are_accepted():
    grid, model, condition, solver, arrays = inputs(ONE_BUILDING)
    for array in arrays.values():
        array.setflags(write=False)
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays)
    assert runner.solve(condition, solver)["diagnostics"]["converged"]


def test_concurrent_calls_complete_without_gil_deadlock():
    script = f"""
import sys, logging, threading
from concurrent.futures import ThreadPoolExecutor
import numpy as np
sys.path.insert(0, {str(Path(__file__).parent)!r})
from dtcc_core.common import get_python_logger
from fixtures.cases import ONE_BUILDING
from runner_cases import prepared
logger = get_python_logger('dtcc-qes')
logger.handlers = [logging.NullHandler()]
runner, condition, solver = prepared(ONE_BUILDING)
start, progressed = threading.Event(), threading.Event()
def heartbeat():
    start.wait()
    progressed.set()
thread = threading.Thread(target=heartbeat)
thread.start()
sys.setswitchinterval(1000)
start.set()
expected = runner.solve(condition, solver)['velocity']
assert progressed.is_set(), 'Native solve did not release the GIL'
thread.join()
sys.setswitchinterval(0.005)
def solve(index):
    if index % 2:
        local, wind, options = prepared(ONE_BUILDING)
    else:
        local, wind, options = runner, condition, solver
    return local.solve(wind, options)['velocity']
with ThreadPoolExecutor(max_workers=4) as pool:
    for result in pool.map(solve, range(12)):
        np.testing.assert_array_equal(result, expected)
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stdout == completed.stderr == b""

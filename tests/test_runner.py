"""Step 4 exercises the private array boundary, without the city adapter."""

import gc
import logging
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from dtcc_core.common import get_python_logger
from dtcc_qes import _qes

from fixtures.cases import CASES, FLAT, ONE_BUILDING, reference_path
from runner_cases import inputs, prepared
from reference_checks import assert_reference_velocity


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
    assert result["turbulence"] is None


def turbulence_settings(method=0, enabled=True):
    settings = _qes.TurbulenceSettings()
    settings.enabled = enabled
    settings.mixing_length_method = method
    return settings


@pytest.mark.parametrize("setting", [None, False])
def test_turbulence_disabled(setting):
    grid, model, condition, solver, arrays = inputs(FLAT)
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays,
                   turbulence=None if setting is None else turbulence_settings(enabled=False))
    assert runner.solve(condition, solver)["turbulence"] is None


@pytest.mark.parametrize("method", [0, 1])
@pytest.mark.parametrize("precision", ["float32", "float64"])
def test_turbulence_arrays_masks_metadata_and_ownership(method, precision):
    grid, model, condition, solver, arrays = inputs(ONE_BUILDING)
    runner = _qes.WindRunner()
    solver.precision = precision
    settings = turbulence_settings(method)
    runner.prepare(grid, model, **arrays, turbulence=settings)
    settings.enabled = False
    settings.mixing_length_method = 4
    first = runner.solve(condition, solver)
    turb = first["turbulence"]
    float_arrays = ("stress", "tke", "co_eps", "mixing_length")
    arrays_names = (*float_arrays, "state", "stress_valid")
    scalars = ("friction_velocity", "reference_speed", "reference_height", "roughness_length",
               "displacement_height", "upper_bound", "computed_cells", "capped_cells",
               "invalid_stress_cells", "rotation_fallback_columns")
    assert set(turb) == set((*arrays_names, *scalars))
    shape = (grid.nz, grid.ny, grid.nx)
    for name in arrays_names:
        array = turb[name]
        assert array.shape == ((*shape, 6) if name == "stress" else shape)
        assert array.dtype == (np.float32 if name in float_arrays else np.uint8)
        assert array.flags.c_contiguous and array.flags.owndata
    computed = turb["state"] > 0
    assert computed.sum() == turb["computed_cells"]
    assert not computed[-1].any() and not computed[:, (0, -1), :].any()
    assert not computed[:, :, (0, -1)].any()
    assert not computed[np.isin(first["cell_flags"], (0, 2))].any()
    assert turb["computed_cells"] > 10000
    assert np.all(np.isin(turb["state"], (0, 1, 2)))
    assert (turb["state"] == 2).sum() == turb["capped_cells"]
    bound = (np.float32(turb["upper_bound"]) * np.float32(turb["friction_velocity"]))
    bound *= np.float32(turb["friction_velocity"])
    capped = computed & ((turb["tke"] >= bound) | (np.abs(turb["stress"]).max(axis=-1) >= bound))
    np.testing.assert_array_equal(turb["state"] == 2, capped)
    assert not turb["stress_valid"][~computed].any()
    for name in float_arrays:
        assert np.isnan(turb[name][~computed]).all()
        assert np.isfinite(turb[name][computed]).all()
    # Independent covariance check on the extracted, stored float32 values.
    raw = turb["stress"][computed].astype(np.float64)
    tensor = raw[:, (0, 1, 2, 1, 3, 4, 2, 4, 5)].reshape(-1, 3, 3)
    eigenvalues = np.linalg.eigvalsh(tensor)
    valid = eigenvalues[:, 0] >= -32 * np.finfo(np.float32).eps * np.abs(eigenvalues).max(axis=1)
    np.testing.assert_array_equal(turb["stress_valid"][computed], valid)
    assert (~valid).sum() == turb["invalid_stress_cells"]
    assert turb["reference_height"] == 24
    assert turb["roughness_length"] == pytest.approx(0.8)
    assert turb["displacement_height"] == pytest.approx(5.6)
    assert turb["upper_bound"] == 20
    assert turb["friction_velocity"] > 0
    snapshot = {name: turb[name].copy() for name in arrays_names}
    condition.direction = 0
    second = runner.solve(condition, solver)
    assert not np.array_equal(turb["stress"], second["turbulence"]["stress"], equal_nan=True)
    condition.direction = 270
    third = runner.solve(condition, solver)["turbulence"]
    del runner
    gc.collect()
    for name in arrays_names:
        np.testing.assert_array_equal(turb[name], snapshot[name])
        np.testing.assert_array_equal(third[name], snapshot[name])
        assert not np.shares_memory(turb[name], third[name])


def test_enabling_turbulence_preserves_wind_results():
    runner, condition, solver = prepared(ONE_BUILDING)
    original = runner.solve(condition, solver)
    grid, model, _, _, arrays = inputs(ONE_BUILDING)
    runner.prepare(grid, model, **arrays, turbulence=turbulence_settings())
    enabled = runner.solve(condition, solver)
    np.testing.assert_array_equal(enabled["velocity"], original["velocity"])
    np.testing.assert_array_equal(enabled["cell_flags"], original["cell_flags"])
    assert enabled["diagnostics"] == original["diagnostics"]
    runner.prepare(grid, model, **arrays)
    assert runner.solve(condition, solver)["turbulence"] is None


@pytest.mark.parametrize("method", [-1, 2, 3, 4, 5])
def test_unsupported_turbulence_method_preserves_preparation(method):
    runner, condition, solver = prepared(FLAT)
    grid, model, _, _, arrays = inputs(ONE_BUILDING)
    arrays["heights"][:] = np.nan  # Method validation must precede native geometry setup.
    with pytest.raises(ValueError, match="mixing-length method"):
        runner.prepare(grid, model, **arrays, turbulence=turbulence_settings(method))
    recovered = runner.solve(condition, solver)
    assert recovered["turbulence"] is None and recovered["building_count"] == 0


def test_turbulence_margin_failure_preserves_preparation():
    runner, condition, solver = prepared(FLAT)
    grid, model, _, _, arrays = inputs(ONE_BUILDING)
    grid.nz = 13
    with pytest.raises(ValueError, match=r"domain top.*24.*margin.*30"):
        runner.prepare(grid, model, **arrays, turbulence=turbulence_settings())
    assert runner.solve(condition, solver)["turbulence"] is None
    grid.nz = 15
    runner.prepare(grid, model, **arrays, turbulence=turbulence_settings())
    assert runner.solve(condition, solver)["turbulence"]["reference_height"] == 24


@pytest.mark.parametrize("case,nz,roughness,sufficient_nz", [
    (FLAT, 6, 0.05, 8),      # Below the 15 m rotation reference.
    (FLAT, 20, 0.5, 28),     # zRef=50 m lies above the domain.
    (ONE_BUILDING, 10, 0.1, 15),  # Building zRef=24 m lies above the domain.
    (ONE_BUILDING, 12, 0.1, 15),  # zRef is exactly the top face.
])
@pytest.mark.parametrize("method", [0, 1])
def test_turbulence_preflight_reports_sufficient_top(case, nz, roughness, sufficient_nz, method, caplog):
    grid, model, _, _, arrays = inputs(case)
    grid.nz, model.roughness_length = nz, roughness
    runner = _qes.WindRunner()
    settings = turbulence_settings(method)
    with caplog.at_level(logging.DEBUG, logger="dtcc-qes"):
        with pytest.raises(ValueError, match=rf"zRef .*margin.*sufficient top of {2*sufficient_nz} m"):
            runner.prepare(grid, model, **arrays, turbulence=settings)
    assert not any("Initialization of turbulence model" in record.message for record in caplog.records)
    assert grid.nz == nz
    grid.nz = sufficient_nz
    runner.prepare(grid, model, **arrays, turbulence=settings)


def test_turbulence_margin_does_not_suggest_collapsed_cell_centres():
    grid, model, _, _, arrays = inputs(FLAT)
    grid.nz = 2
    layers = np.array([16777211, 1], dtype=np.float64)
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays, dz_layers=layers)
    with pytest.raises(ValueError, match="float32 cell-centre progress limit"):
        runner.prepare(grid, model, **arrays, dz_layers=layers, turbulence=turbulence_settings())
    # The proposed first tail layer would pass the face check but fail the
    # native domain's independent centre-coordinate validation.
    grid.nz = 3
    with pytest.raises(ValueError, match="coordinates must remain finite and strictly increasing"):
        runner.prepare(grid, model, **arrays, dz_layers=np.append(layers, 1))


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
    assert "max_divergence=" in summaries[0].message
    assert not any(r.levelno >= logging.ERROR for r in records)


def test_conservative_divergence_diagnostics_are_separate_from_convergence():
    runner, condition, solver = prepared(ONE_BUILDING)
    solver.max_iterations = 1
    early = runner.solve(condition, solver)["diagnostics"]
    solver.max_iterations = 500
    final = runner.solve(condition, solver)["diagnostics"]
    assert final["max_divergence"] < 1e-5
    assert final["rms_divergence"] < 1e-6
    assert early["max_divergence"] > final["max_divergence"] * 100
    assert final["divergence_cell_count"] > 1000
    assert final["top_band_cell_count"] > 0
    assert final["top_band_max_divergence"] > 1e-3


def test_empty_assessed_regions_return_unavailable_metrics():
    grid, model, condition, solver, arrays = inputs(FLAT)
    grid.nx = grid.ny = 3
    grid.nz = 2
    model.sensor_x = model.sensor_y = 1
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays)
    diagnostics = runner.solve(condition, solver)["diagnostics"]
    assert diagnostics["divergence_cell_count"] == 0
    assert diagnostics["max_divergence"] is None
    assert diagnostics["rms_divergence"] is None
    assert diagnostics["top_band_cell_count"] == 1
    assert diagnostics["top_band_max_divergence"] == 0


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

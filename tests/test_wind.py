from dataclasses import FrozenInstanceError
import json
import logging
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from dtcc_core.model import Bounds
from dtcc_qes import wind

from city_cases import city_case
from fixtures.cases import CASES, FLAT, ONE_BUILDING, reference_path
from reference_checks import assert_reference_velocity

pytestmark = pytest.mark.usefixtures("dtcc_logger")


@pytest.mark.parametrize("case", CASES.values(), ids=CASES)
@pytest.mark.parametrize("translation", [(0, 0, 0), (1e9, -2e9, 100)])
def test_public_api_matches_references(case, translation):
    city, condition, grid, solver = city_case(case, translation)
    before = [building.lod0.vertices.copy() for building in city.buildings]
    result = wind.run(city, condition, grid=grid, solver=solver)
    with np.load(reference_path(case)) as reference:
        for name in ("x", "y", "z"):
            np.testing.assert_array_equal(getattr(result, name), reference[name])
        for i, name in enumerate(("u", "v", "w")):
            assert_reference_velocity(result.velocity[..., i], reference[name])
        np.testing.assert_array_equal(result.cell_flags, reference["icell"])
    assert result.origin == translation
    assert result.diagnostics.converged
    assert result.metadata["domain"]["effective_bounds"] == grid.bounds
    assert result.metadata["versions"]["qes"]["revision"]
    assert result.metadata["versions"]["dtcc_core"]["version"]
    assert result.metadata["model"]["sensor"] == (case.wind.sensor_x, case.wind.sensor_y)
    assert result.velocity.flags.owndata and result.velocity.dtype == np.float32
    for old, building in zip(before, city.buildings):
        np.testing.assert_array_equal(building.lod0.vertices, old)
    json.dumps(result.metadata, allow_nan=False)


def test_automatic_bounds_are_translation_invariant():
    outputs = []
    for translation in ((0, 0, 0), (1e9, -2e9, 100)):
        city, condition, _, solver = city_case(ONE_BUILDING, translation)
        outputs.append(wind.run(city, condition, solver=solver))
    np.testing.assert_array_equal(outputs[0].velocity, outputs[1].velocity)
    np.testing.assert_array_equal(outputs[0].cell_flags, outputs[1].cell_flags)
    np.testing.assert_array_equal(np.asarray(outputs[1].origin) - outputs[0].origin, (1e9, -2e9, 100))
    assert outputs[0].metadata["domain"]["effective_horizontal_padding"] == 20


def test_empty_city_requires_bounds():
    city, condition, _, _ = city_case(FLAT)
    with pytest.raises(ValueError, match="empty city.*explicit"):
        wind.run(city, condition)


def test_limits_checked_before_native_allocation(monkeypatch):
    from dtcc_qes import _qes

    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Native allocation occurred"))
    city, condition, _, _ = city_case(FLAT)
    with pytest.raises(ValueError, match="max_cells"):
        wind.run(city, condition, grid=wind.GridSpec(bounds=(0, 0, 0, 80, 60, 40), max_cells=100))
    with pytest.raises(ValueError, match="10000"):
        wind.run(city, condition, grid=wind.GridSpec(bounds=(0, 0, 0, 1e6, 60, 40)))


def test_nonconvergence_default_and_opt_out(caplog):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    with pytest.raises(wind.ConvergenceError, match="maximum Lagrange multiplier change") as caught:
        wind.run(city, condition, grid=grid, solver=wind.SolverOptions(max_iterations=1))
    assert not caught.value.diagnostics.converged
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    caplog.clear()
    result = wind.run(city, condition, grid=grid,
                      solver=wind.SolverOptions(max_iterations=1, raise_on_nonconvergence=False))
    assert not result.diagnostics.converged and result.diagnostics.iterations == 1
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1 and "did not converge" in warnings[0].message


def test_retained_convergence_exception_does_not_retain_native_domain(monkeypatch):
    from dtcc_qes import _qes

    original = _qes.WindRunner
    active = []

    class TrackedRunner:
        def __init__(self):
            self.native = original()
            active.append(True)

        def prepare(self, *args, **kwargs):
            self.native.prepare(*args, **kwargs)

        def solve(self, *args, **kwargs):
            return self.native.solve(*args, **kwargs)

        def __del__(self):
            active.pop()

    monkeypatch.setattr(_qes, "WindRunner", TrackedRunner)
    city, condition, grid, _ = city_case(ONE_BUILDING)
    with pytest.raises(wind.ConvergenceError) as retained:
        wind.run(city, condition, grid=grid, solver=wind.SolverOptions(max_iterations=1))
    assert retained.value.diagnostics.iterations == 1
    assert not active


def test_bounds_expand_upper_edges_and_preserve_lower_origin():
    city, condition, _, _ = city_case(FLAT)
    grid = wind.GridSpec(bounds=Bounds(xmin=10, ymin=20, zmin=30, xmax=17, ymax=29, zmax=35))
    result = wind.run(city, condition, grid=grid)
    assert result.origin == (10, 20, 30)
    assert result.velocity.shape == (3, 5, 4, 3)
    assert result.metadata["domain"]["effective_bounds"] == (10, 20, 30, 18, 30, 36)


@pytest.mark.parametrize("options", [
    lambda: wind.WindCondition(-1, 270), lambda: wind.WindCondition(1, 360),
    lambda: wind.WindCondition(1, float("nan")), lambda: wind.WindCondition(True, 270),
    lambda: wind.WindCondition(1, 270, roughness_length=0),
    lambda: wind.WindCondition(1, 270, reference_height=1e-20),
    lambda: wind.WindCondition(1, 270, reference_height=1e38, roughness_length=1e-38),
    lambda: wind.WindCondition(10**1000, 270),
    lambda: wind.WindCondition(1e300, 270),
    lambda: wind.GridSpec(resolution=0), lambda: wind.GridSpec(resolution=1e-100),
    lambda: wind.GridSpec(horizontal_padding=-1), lambda: wind.GridSpec(vertical_clearance=-1),
    lambda: wind.GridSpec(max_cells=True), lambda: wind.GridSpec(bounds=(0, 0, 0, 1, 2)),
    lambda: wind.GridSpec(bounds=(0, 0, 0, 0, 2, 3)),
    lambda: wind.SolverOptions(tolerance=1e-12), lambda: wind.SolverOptions(max_iterations=0),
    lambda: wind.SolverOptions(raise_on_nonconvergence="false"),
    lambda: wind.FlatTerrain(float("inf")),
])
def test_options_reject_invalid_values(options):
    with pytest.raises(ValueError):
        options()


def test_options_are_frozen_and_bounds_are_snapshotted():
    bounds = Bounds(xmin=0, ymin=0, zmin=0, xmax=10, ymax=10, zmax=10)
    grid = wind.GridSpec(bounds=bounds)
    bounds.xmax = 99
    assert grid.bounds[3] == 10
    with pytest.raises(FrozenInstanceError):
        grid.resolution = 3


def test_public_success_failures_and_shutdown_are_silent_with_logging_disabled():
    script = f"""
import sys, logging
sys.path.insert(0, {str(Path(__file__).parent)!r})
from dtcc_core.common import get_python_logger
from dtcc_qes import wind
from fixtures.cases import ONE_BUILDING
from city_cases import city_case
logger = get_python_logger('dtcc-qes')
logger.handlers = [logging.NullHandler()]
city, condition, grid, solver = city_case(ONE_BUILDING)
for repeat in range(3):
    assert wind.run(city, condition, grid=grid).diagnostics.converged
    city.buildings[0].measured_height = 0
    try:
        wind.run(city, condition, grid=grid)
    except ValueError as error:
        assert "Building '0'" in str(error)
    else:
        raise AssertionError('Missing height validation')
    city.buildings[0].measured_height = 8
    try:
        wind.run(city, condition, grid=grid, solver=wind.SolverOptions(max_iterations=1))
    except wind.ConvergenceError:
        pass
    else:
        raise AssertionError('Missing convergence error')
assert wind.run(city, condition, grid=grid).diagnostics.converged
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stdout == completed.stderr == b""

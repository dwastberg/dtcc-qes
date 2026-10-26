import json
import logging
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from dtcc_core.model import Bounds
from dtcc_qes import _qes, wind

from city_cases import city_case
from fixtures.cases import CASES, FLAT, ONE_BUILDING, reference_path
from reference_checks import assert_reference_velocity

pytestmark = pytest.mark.usefixtures("dtcc_logger")


@pytest.mark.parametrize("case", CASES.values(), ids=CASES)
@pytest.mark.parametrize("translation", [(0, 0, 0), (1e9, -2e9, 100)])
def test_public_api_matches_references(case, translation):
    city, condition, grid, solver = city_case(case, translation)
    before = [building.lod0.vertices.copy() for building in city.buildings]
    result = wind.run(city, **condition, **grid, **solver)
    with np.load(reference_path(case)) as reference:
        for name in ("x", "y", "z"):
            np.testing.assert_array_equal(getattr(result, name), reference[name])
        for i, name in enumerate(("u", "v", "w")):
            assert_reference_velocity(result.velocity[..., i], reference[name])
        np.testing.assert_array_equal(result.cell_flags, reference["icell"])
    assert result.origin == translation
    assert result.diagnostics.converged
    assert result.metadata["domain"]["effective_bounds"] == grid["bounds"]
    assert result.metadata["versions"]["qes"]["revision"]
    assert result.metadata["versions"]["native_build"]["openmp_enabled"] is _qes.openmp_enabled
    assert result.metadata["model"]["backend"] == _qes.cpu_backend
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
        outputs.append(wind.run(city, **condition, **solver))
    np.testing.assert_array_equal(outputs[0].velocity, outputs[1].velocity)
    np.testing.assert_array_equal(outputs[0].cell_flags, outputs[1].cell_flags)
    np.testing.assert_array_equal(np.asarray(outputs[1].origin) - outputs[0].origin, (1e9, -2e9, 100))
    assert outputs[0].metadata["domain"]["effective_horizontal_padding"] == 20


def test_empty_city_requires_bounds():
    city, condition, _, _ = city_case(FLAT)
    with pytest.raises(ValueError, match="empty city.*explicit"):
        wind.run(city, **condition)


def test_limits_checked_before_native_allocation(monkeypatch):
    from dtcc_qes import _qes

    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Native allocation occurred"))
    city, condition, _, _ = city_case(FLAT)
    with pytest.raises(ValueError, match="max_cells"):
        wind.run(city, **condition, bounds=(0, 0, 0, 80, 60, 40), max_cells=100)
    with pytest.raises(ValueError, match="10000"):
        wind.run(city, **condition, bounds=(0, 0, 0, 1e6, 60, 40))


def test_nonconvergence_warns_by_default(caplog):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    result = wind.run(city, **condition, **grid,
                      max_iterations=1)
    assert not result.diagnostics.converged and result.diagnostics.iterations == 1
    assert result.velocity.shape == result.cell_flags.shape + (3,)
    assert np.isfinite(result.velocity).all()
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1 and "did not converge" in warnings[0].message
    assert "after 1 iterations" in warnings[0].message
    assert "maximum Lagrange multiplier change" in warnings[0].message
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_nonconvergence_can_explicitly_raise():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    with pytest.raises(wind.ConvergenceError, match="maximum Lagrange multiplier change") as caught:
        wind.run(city, **condition, **grid,
                 max_iterations=1, raise_on_nonconvergence=True)
    assert not caught.value.diagnostics.converged


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
        wind.run(city, **condition, **grid,
                 max_iterations=1, raise_on_nonconvergence=True)
    assert retained.value.diagnostics.iterations == 1
    assert not active


def test_bounds_expand_upper_edges_and_preserve_lower_origin():
    city, condition, _, _ = city_case(FLAT)
    grid = dict(bounds=Bounds(xmin=10, ymin=20, zmin=30, xmax=17, ymax=29, zmax=35))
    result = wind.run(city, **condition, **grid)
    assert result.origin == (10, 20, 30)
    assert result.velocity.shape == (3, 5, 4, 3)
    assert result.metadata["domain"]["effective_bounds"] == (10, 20, 30, 18, 30, 36)


@pytest.mark.parametrize("options", [
    dict(speed=-1), dict(direction=360),
    dict(direction=float("nan")), dict(speed=True),
    dict(roughness_length=0), dict(reference_height=1e-20),
    dict(reference_height=1e38, roughness_length=1e-38),
    dict(speed=10**1000), dict(speed=1e300),
    dict(resolution=0), dict(resolution=1e-100),
    dict(horizontal_padding=-1), dict(vertical_clearance=-1),
    dict(max_cells=True), dict(bounds=(0, 0, 0, 1, 2)),
    dict(bounds=(0, 0, 0, 0, 2, 3)),
    dict(tolerance=1e-12), dict(max_iterations=0),
    dict(raise_on_nonconvergence="false"), dict(terrain=float("inf")),
])
def test_options_reject_invalid_values_before_native_allocation(options, monkeypatch):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Native allocation occurred"))
    city, condition, grid, _ = city_case(ONE_BUILDING)
    with pytest.raises(ValueError):
        wind.run(city, **(condition | grid | options))


def test_bounds_are_snapshotted_without_mutating_the_input():
    city, condition, _, _ = city_case(FLAT)
    bounds = Bounds(xmin=0, ymin=0, zmin=0, xmax=10, ymax=10, zmax=10)
    result = wind.run(city, **condition, bounds=bounds)
    assert bounds.xmax == 10
    bounds.xmax = 99
    assert result.metadata["domain"]["requested_bounds"] == (0, 0, 0, 10, 10, 10)


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
    assert wind.run(city, **condition, **grid).diagnostics.converged
    city.buildings[0].measured_height = 0
    try:
        wind.run(city, **condition, **grid)
    except ValueError as error:
        assert "Building '0'" in str(error)
    else:
        raise AssertionError('Missing height validation')
    city.buildings[0].measured_height = 8
    result = wind.run(city, **condition, **grid, max_iterations=1)
    assert not result.diagnostics.converged
assert wind.run(city, **condition, **grid).diagnostics.converged
"""
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=60)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stdout == completed.stderr == b""

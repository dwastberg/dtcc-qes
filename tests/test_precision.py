"""The opt-in arithmetic contract, public provenance and zero-start lifecycle."""
import numpy as np
import pytest

from dtcc_qes import _qes, wind
from city_cases import city_case
from fixtures.cases import FLAT, ONE_BUILDING
from runner_cases import prepared

pytestmark = pytest.mark.usefixtures("dtcc_logger")


@pytest.mark.parametrize("precision", [None, True, 64, "double", "FLOAT64", [], np.float64])
def test_precision_is_explicit_and_validated_before_native_preparation(precision, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid precision reached preparation")
    monkeypatch.setattr(wind, "_prepare_city", forbidden)
    with pytest.raises(ValueError, match="solver_precision"):
        wind.run(None, 5, 270, solver_precision=precision)


def test_native_runner_switches_modes_without_retaining_a_previous_solution():
    runner, condition, options = prepared(ONE_BUILDING)
    default = runner.solve(condition, options)
    assert default["diagnostics"]["precision"] == "float32"
    options.precision = "float64"
    options.tolerance = 1e-10
    options.max_iterations = 2000
    precise = runner.solve(condition, options)
    diagnostics = precise["diagnostics"]
    assert diagnostics["precision"] == "float64" and diagnostics["tolerance"] == 1e-10
    assert diagnostics["converged"] and diagnostics["max_divergence"] < 1e-6
    assert precise["velocity"].dtype == np.float32
    condition.direction = 315
    runner.solve(condition, options)
    condition.direction = ONE_BUILDING.wind.direction
    repeated = runner.solve(condition, options)
    np.testing.assert_array_equal(repeated["velocity"], precise["velocity"])
    assert repeated["diagnostics"] == diagnostics
    options.precision = "float32"
    options.tolerance = ONE_BUILDING.solver.tolerance
    options.max_iterations = ONE_BUILDING.solver.max_iterations
    restored = runner.solve(condition, options)
    np.testing.assert_array_equal(default["velocity"], restored["velocity"])
    assert restored["diagnostics"] == default["diagnostics"]


@pytest.mark.parametrize("precision,tolerance", [("float64", 1e-20), ("float64", np.inf),
    ("float64", np.nan), ("float32", 1e-10), ("invalid", 1e-5)])
def test_native_validation_also_enforces_precision_tolerance(precision, tolerance):
    runner, condition, options = prepared(FLAT)
    options.precision = precision
    options.tolerance = tolerance
    with pytest.raises(ValueError):
        runner.solve(condition, options)
    options.precision = "float64"
    options.tolerance = 1e-12
    assert runner.solve(condition, options)["diagnostics"]["converged"]


@pytest.mark.parametrize("spec", [None, wind.VerticalGrid.from_faces(np.arange(0, 40.5, .5)),
                                  wind.VerticalGrid.auto(pedestrian_height=1.5)])
def test_public_precision_preserves_geometry_sampling_and_reports_actual_arithmetic(spec):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    default = wind.run(city, **condition, **grid, vertical_grid=spec, max_iterations=2000)
    precise = wind.run(city, **condition, **grid, vertical_grid=spec, solver_precision="float64",
                       tolerance=1e-10, max_iterations=2000)
    assert precise.diagnostics.precision == precise.metadata["solver"]["precision"] == "float64"
    assert default.diagnostics.precision == default.metadata["solver"]["precision"] == "float32"
    assert precise.diagnostics.tolerance == 1e-10
    assert precise.metadata["domain"] == default.metadata["domain"]
    assert precise.diagnostics.converged
    assert precise.velocity.dtype == np.float32
    for name in ("x", "y", "z", "z_faces", "cell_flags"):
        np.testing.assert_array_equal(getattr(precise, name), getattr(default, name))
    for height in (1.5, 1.75):
        sample = precise.sample(height, method="linear")
        assert sample.sampled_height == height and sample.valid.any()
        assert sample.velocity.dtype == np.float64
        assert np.isfinite(sample.velocity[sample.valid]).all()


def test_large_precision_tolerance_still_measures_at_least_one_update():
    runner, condition, options = prepared(ONE_BUILDING)
    options.precision = "float64"
    options.tolerance = 1e100
    diagnostics = runner.solve(condition, options)["diagnostics"]
    assert diagnostics["iterations"] == 1 and diagnostics["converged"]
    assert diagnostics["max_lagrange_multiplier_change"] > 0

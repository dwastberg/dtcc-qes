"""``Parameterizations.angle_fade``: the sidewall and upwind-cavity zones fade with angle instead of switching at 10 degrees."""
import numpy as np
import pytest
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import _qes, wind
from fixtures.geometry import tower_city
from fixtures.specs import pedestrian_solver

pytestmark = pytest.mark.usefixtures("dtcc_logger")
BOUNDS = (0, 0, 0, 200, 200, 60)


def building():
    """One 20 x 30 x 20 m building with walls along the axes (the direction sweep of FABEL_WAKE_INVESTIGATION.md, 4.6)."""
    city = City()
    b = Building(id="b")
    b.measured_height = 20.0
    b.add_geometry(Surface(vertices=np.array([[90., 85, 0], [90, 115, 0], [110, 115, 0], [110, 85, 0]])), GeometryType.LOD0)
    city.add_building(b)
    return city


def solve(direction, fade=None, solver=wind.Solver(max_iterations=400), **changes):
    options = {} if fade is None else dict(parameterizations=wind.Parameterizations(angle_fade=fade, **changes))
    return wind.run(building(), speed=5.0, direction=float(direction), resolution=2.0, bounds=BOUNDS,
                    solver=solver, **options)


def plane(result):
    sample = result.sample(2.0, "linear")
    return np.where(sample.valid, np.linalg.norm(sample.velocity, axis=-1) / result.reference_speed, np.nan)


def test_default_is_off_and_native():
    assert wind.Parameterizations().angle_fade == 0.0
    assert _qes.ModelSettings().angle_fade == 0.0
    assert wind.Parameterizations.from_dict(wind.Parameterizations(angle_fade=2.5).to_dict()).angle_fade == 2.5


@pytest.mark.parametrize("value", [-0.1, 10.5, float("nan"), "2.5", True])
def test_invalid_half_widths_are_rejected(value):
    with pytest.raises(ValueError, match="angle_fade"):
        wind.Parameterizations(angle_fade=value)


def test_zero_keeps_the_switch_bit_for_bit():
    np.testing.assert_array_equal(solve(279).velocity, solve(279, 0.0).velocity)


def test_a_wall_aligned_with_the_wind_is_unchanged():
    np.testing.assert_array_equal(solve(270, 0.0).velocity, solve(270, 2.5).velocity)


@pytest.mark.parametrize("direction,changed", [(264, False), (279, True), (281, True), (284, False)])
def test_the_weight_acts_only_inside_the_ramp(direction, changed):
    # the switch is at 10 degrees from alignment; a 2.5 degree half-width fades from 7.5 to 12.5 degrees
    difference = np.nanmax(np.abs(solve(direction, 0.0).velocity - solve(direction, 2.5).velocity))
    assert (difference > 0.05) if changed else (difference == 0)


def test_the_direction_step_at_the_switch_is_removed():
    # the gate of validation/ACCURACY_RESULTS.md, section 1: wake code 3 and the sweep's solver settings
    sweep = wind.Solver(tolerance=1e-6, max_iterations=3000, stop="multiplier_change")
    steps = {}
    for fade in (0.0, 2.5):
        planes = np.array([plane(solve(direction, fade, sweep, wake=3)) for direction in (278, 279, 280, 281, 282)])
        steps[fade] = np.sqrt(np.nanmean(np.diff(planes, axis=0) ** 2, axis=(1, 2)))
    assert steps[0.0].max() > 0.025  # the switch, between 279 and 280 degrees
    assert steps[2.5].max() < 0.016


def test_cell_flags_keep_the_switch():
    # later zones and the turbulence model read the flags; the fade must not move them
    np.testing.assert_array_equal(solve(281, 0.0).cell_flags, solve(281, 2.5).cell_flags)


def test_it_works_with_the_spreading_wake_and_is_recorded():
    result = solve(279, 2.5, wake=3)
    model = result.metadata["model"]
    assert model["angle_fade"] == 2.5 and model["parameterizations"]["angle_fade"] == 2.5
    assert np.nanmax(np.abs(result.velocity - solve(279, 0.0, wake=3).velocity)) > 0.05


def test_a_fade_is_outside_pedestrian_policy():
    options = dict(speed=5, direction=270, bounds=(0, 0, 0, 160, 160, 64), solver=pedestrian_solver())
    preview = wind.preview_grid(tower_city(), **options, parameterizations=wind.Parameterizations(angle_fade=2.5))
    assert "unqualified_model_settings" in preview.eligibility["exclusions"]

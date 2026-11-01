"""Physical assertions independent of the executable regression arrays."""

import copy
import numpy as np
import pytest
from dtcc_qes import wind
from dtcc_core.model import Bounds

from fixtures.cities import city_case
from fixtures.cases import FLAT, ONE_BUILDING

pytestmark = pytest.mark.usefixtures("dtcc_logger")


@pytest.mark.parametrize("direction, unit", [(0, (0, -1, 0)), (90, (-1, 0, 0)),
                                             (180, (0, 1, 0)), (270, (1, 0, 0))])
@pytest.mark.parametrize("roughness", [0.1, 0.5])
def test_flat_neutral_profile_and_meteorological_cardinal_directions(direction, unit, roughness):
    city, _, grid, _ = city_case(FLAT)
    condition = dict(profile=wind.LogProfile(5, direction, roughness_length=roughness))
    result = wind.run(city, **condition, **grid)
    expected_speed = 5 * np.log((result.z.astype(float) + roughness) / roughness)
    expected_speed /= np.log((10 + roughness) / roughness)
    expected = np.broadcast_to(expected_speed[:, None, None, None] * np.asarray(unit), result.velocity.shape)
    np.testing.assert_allclose(result.velocity, expected, rtol=2e-6, atol=2e-6)
    assert np.isfinite(result.velocity).all()
    assert not result.solid_mask.any()
    assert np.all(result.x > 0) and np.all(result.y > 0) and np.all(result.z > 0)


def test_building_occupancy_and_zero_solid_velocity():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    # This diagnostic threshold was qualified at the historical explicit
    # tolerance; default selection has its own pedestrian-error study.
    result = wind.run(city, **condition, **grid,solver=wind.Solver(tolerance=1e-5,max_iterations=500))
    z, y, x = np.meshgrid(result.z, result.y, result.x, indexing="ij")
    expected = (x >= 30) & (x < 40) & (y >= 25) & (y < 35) & (z < 8)
    np.testing.assert_array_equal(result.solid_mask, expected)
    assert np.count_nonzero(expected) == 100
    np.testing.assert_array_equal(result.velocity[expected], 0)
    assert np.isfinite(result.velocity).all()
    assert result.diagnostics.max_divergence < 1e-5
    assert result.diagnostics.rms_divergence < 1e-6
    assert result.diagnostics.top_band_max_divergence > 1e-3
    assert result.diagnostics.divergence_cell_count > 1000
    assert result.metadata["divergence_diagnostic"]["highest_physical_layer"] == "unassessed"


def test_diagnostic_construction_remains_backwards_compatible():
    diagnostics = wind.SolveDiagnostics(1, 0, 1e-5, True)
    assert diagnostics.max_divergence is None
    assert diagnostics.rms_divergence is None
    assert diagnostics.divergence_cell_count is None


def test_calm_wind_and_concave_simple_footprint():
    city, _, grid, _ = city_case(ONE_BUILDING)
    city.buildings[0].lod0.vertices = np.array([
        [30, 25, 0], [30, 35, 0], [35, 35, 0], [35, 30, 0], [40, 30, 0], [40, 25, 0],
    ], dtype=float)
    calm = wind.run(city, speed=0, direction=270, **grid)
    np.testing.assert_array_equal(calm.velocity, 0)
    result = wind.run(city, speed=5, direction=270, **grid)
    assert result.diagnostics.converged and np.isfinite(result.velocity).all()
    assert result.solid_mask.any()


def test_repeated_public_calls_preserve_all_city_state_and_own_results():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    building = city.buildings[0]
    city._bounds = Bounds(xmin=0, ymin=0, zmin=0, xmax=80, ymax=60, zmax=40)
    building.attributes["source"] = {"values": [1, 2]}
    before = copy.deepcopy(city)
    first = wind.run(city, **condition, **grid)
    second = wind.run(city, profile=wind.LogProfile(condition["profile"].speed,90,reference_height=condition["profile"].reference_height,roughness_length=condition["profile"].roughness_length), **grid)
    third = wind.run(city, **condition, **grid)
    np.testing.assert_array_equal(first.velocity, third.velocity)
    assert not np.array_equal(first.velocity, second.velocity)
    assert not np.shares_memory(first.velocity, third.velocity)
    assert building.attributes == before.buildings[0].attributes
    assert vars(city._bounds) == vars(before._bounds)
    np.testing.assert_array_equal(building.lod0.vertices, before.buildings[0].lod0.vertices)
    for current, old in ((city, before), (building, before.buildings[0]), (building.lod0, before.buildings[0].lod0)):
        np.testing.assert_array_equal(current.transform.affine, old.transform.affine)


def test_explicit_upper_bound_is_never_rounded_inward():
    city, condition, _, _ = city_case(FLAT)
    xmax = 80 + 1e-11
    result = wind.run(city, **condition, bounds=(0, 0, 0, xmax, 60, 40))
    assert result.metadata["domain"]["effective_bounds"][3] >= xmax
    assert len(result.x) == 41


def test_impossible_padding_fails_without_numpy_overflow():
    city, condition, _, _ = city_case(ONE_BUILDING)
    with pytest.raises(ValueError, match="padding.*10000"):
        wind.run(city, **condition, horizontal_padding=1e308)


def test_permissive_tolerance_still_measures_a_solve():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    result = wind.run(city, **condition, **grid, solver=wind.Solver(tolerance=2))
    assert result.diagnostics.iterations > 0
    assert np.isfinite(result.diagnostics.max_lagrange_multiplier_change)

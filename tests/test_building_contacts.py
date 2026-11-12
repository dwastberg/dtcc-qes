"""Public canonical-solid and native ring/exposure integration."""

from copy import deepcopy
import json

import numpy as np
import pytest
from shapely import contains_xy
from shapely.geometry import Polygon, box
from shapely.affinity import rotate
from dtcc_core.model import GeometryType, MultiSurface
from dtcc_qes import wind
from fixtures.footprints import building, city, surface

pytestmark = pytest.mark.usefixtures("dtcc_logger")
OPTIONS = dict(bounds=(-20, -20, 0, 60, 40, 40), resolution=1, solver=wind.Solver(max_iterations=12))


def run(value, *, expose=True, **options):
    return wind.run(value, footprints=wind.Footprints(min_detail=0.01, exposed_faces=expose), **OPTIONS | options, speed=5, direction=270)


def same(a, b):
    np.testing.assert_array_equal(a.cell_flags, b.cell_flags)
    np.testing.assert_array_equal(a.velocity, b.velocity)


def test_split_and_single_canonical_solids_are_exact():
    split = run(city(building("a", box(0, 0, 10, 10), 10), building("b", box(10, 0, 20, 10), 9.9)))
    single = run(city(building("block", box(0, 0, 20, 10), 10)))
    same(split, single)
    assert split.metadata["footprints"]["counts"]["solids"] == 1
    assert all(s["solids"] == [0] for s in split.metadata["buildings"])
    assert split.metadata["model"]["exposed_faces"]
    json.dumps(split.metadata, allow_nan=False)


def test_overlap_and_partition_are_exact_and_permutation_independent():
    low = building("low", box(0, 0, 20, 10), 6)
    high = building("high", box(10, 0, 20, 10), 12)
    overlap = run(city(low, high))
    partition = run(city(building("low", box(0, 0, 10, 10), 6), deepcopy(high)))
    reversed_ = run(city(deepcopy(high), deepcopy(low)))
    same(overlap, partition)
    same(overlap, reversed_)


@pytest.mark.parametrize("expose", [False, True])
def test_courtyard_and_tower_masks_follow_even_odd_rings(expose):
    value = city(building("podium", box(0, 0, 20, 20), 6), building("tower", box(5, 5, 15, 15), 12))
    result = run(value, expose=expose)
    x, y = np.meshgrid(result.x + result.origin[0], result.y + result.origin[1])
    podium = contains_xy(box(0, 0, 20, 20), x, y)
    tower = contains_xy(box(5, 5, 15, 15), x, y)
    for k, z in enumerate(result.z):
        expected = (podium & (z <= 6)) | (tower & (z <= 12))
        np.testing.assert_array_equal(result.solid_mask[k], expected)
    assert np.isfinite(result.velocity).all()
    # An actual empty courtyard, rather than a hole occupied by a tower.
    hole = Polygon(box(0, 0, 20, 20).exterior.coords, [box(5, 5, 15, 15).exterior.coords])
    courtyard = run(city(building("courtyard", hole, 6)), expose=expose)
    expected = contains_xy(hole, x, y)
    np.testing.assert_array_equal(courtyard.solid_mask[2], expected)


def test_multipart_holes_and_oblique_contacts_are_supported():
    hole = Polygon(box(0, 0, 10, 10).exterior.coords, [box(2, 2, 8, 8).exterior.coords])
    a = building("multipart", hole, 8)
    a.add_geometry(MultiSurface(surfaces=[surface(hole), surface(box(20, 0, 30, 10))]), GeometryType.LOD0)
    result = run(city(a))
    assert result.metadata["footprints"]["counts"]["solids"] == 2
    first = rotate(box(0, 0, 10, 10), 25, origin=(0, 0))
    second = rotate(box(10, 0, 20, 10), 25, origin=(0, 0))
    rotated = run(city(building("a", first, 6), building("b", second, 12)))
    assert np.isfinite(rotated.velocity).all()


@pytest.mark.parametrize(
    "grid", [None, wind.VerticalGrid.from_faces(np.arange(0, 41, 0.5)), wind.VerticalGrid.auto()]
)
def test_preview_and_solve_share_final_solids_and_turbulence_reference(grid):
    value = city(building("a", box(0, 0, 10, 10), 10), building("b", box(10, 0, 20, 10), 9.9))
    options = dict(resolution=1, vertical_grid=grid, turbulence=wind.Turbulence(), footprints=wind.Footprints(min_detail=0.01))
    preview = wind.preview_grid(value, speed=5, direction=270, **options)
    result = wind.run(value, **options, solver=wind.Solver(max_iterations=3), speed=5, direction=270)
    assert preview.domain == result.metadata["domain"]
    assert preview.shape == result.solid_mask.shape
    heights = np.sort(np.array([s["native_height"] for s in result.metadata["solids"]], dtype=np.float32))
    mean = np.float32(np.cumsum(heights, dtype=np.float32)[-1] / len(heights))
    assert result.turbulence.reference_height == float(np.float32(3 * float(mean)))


def test_isolated_reference_exposure_switch_preserves_bits():
    from fixtures.cities import city_case
    from fixtures.cases import ONE_BUILDING

    value, condition, grid, solver = city_case(ONE_BUILDING)
    strict = wind.run(value, **condition, **grid, **solver)
    for expose in [False, True]:
        result = wind.run(
            value,
            **condition,
            **grid,
            **solver,
            footprints=wind.Footprints(min_detail=0.01, exposed_faces=expose),
        )
        same(strict, result)


def test_exposure_changes_stepped_contact_but_preserves_mask():
    value = city(building("a", box(0, 0, 10, 10), 6), building("b", box(10, 0, 20, 10), 12))
    on, off = run(value), run(value, expose=False)
    np.testing.assert_array_equal(on.solid_mask, off.solid_mask)
    assert np.any(on.cell_flags != off.cell_flags)
    assert np.max(np.abs(on.velocity - off.velocity)) > 0


@pytest.mark.parametrize("value", [True, {}, "resolve"])
def test_invalid_public_footprint_settings_are_rejected(value):
    with pytest.raises(TypeError, match="Footprints or None"):
        wind.preview_grid(city(), bounds=(-20, -20, 0, 60, 40, 40), footprints=value)


def test_strict_near_contacts_are_recorded_without_cleaning(caplog):
    value = city(building("a", box(0, 0, 10, 10), 6), building("b", box(10.3, 0, 20.3, 10), 6))
    result = wind.run(value, **OPTIONS | {"solver": wind.Solver(max_iterations=2)}, speed=5, direction=270)
    (pair,) = result.metadata["near_contacts"]
    assert pair["source_ids"] == ["a", "b"]
    assert pair["distance"] == pytest.approx(0.3)
    assert len([r for r in caplog.records if "building pairs are closer" in r.message]) == 1
    assert "footprints" not in result.metadata


def test_empty_resolved_city_and_corner_contact():
    empty = run(city())
    assert empty.metadata["footprints"]["counts"]["solids"] == 0
    assert np.isfinite(empty.velocity).all()
    corner = run(city(building("a", box(0, 0, 10, 10), 6), building("b", box(10, 10, 20, 20), 12)))
    assert np.isfinite(corner.velocity).all()


def test_exposed_faces_fit_the_cavity_to_a_separated_neighbour():
    """Two 80 m slabs 15 m apart, wind across, canyon model off (WAKE_UPDATE_V2.md, section 3.5).

    The upstream cavity closes at the downstream wall with exposed faces as with
    strict footprints. With the sidewall model off the fields are identical; with
    it on, only its separate exposure rule (initial flags) differs.
    """
    value = city(building("up", box(60, 60, 70, 140), 20), building("down", box(85, 60, 95, 140), 20))
    options = dict(bounds=(0, 0, 0, 280, 200, 60), resolution=2.5, solver=wind.Solver(stop="multiplier_change", max_iterations=300),
                   speed=5, direction=270)
    isolated = wind.Parameterizations(street_canyon=0, sidewall=0)
    strict = wind.run(value, parameterizations=isolated, **options)
    exposed = wind.run(value, parameterizations=isolated, footprints=wind.Footprints(min_detail=0.1), **options)
    same(strict, exposed)
    assert not np.any(exposed.cell_flags[:, 25:55, 28:34] == 5)  # no far wake in the gap, inside the end strips
    gap = np.array([[77.5, 100.0, 15.0]])  # 0.75 H, mid-gap
    speeds = []
    for footprints in (wind.Footprints(min_detail=0.1, exposed_faces=False), wind.Footprints(min_detail=0.1)):
        result = wind.run(value, parameterizations=wind.Parameterizations(street_canyon=0), footprints=footprints, **options)
        speeds.append(result.sample_points(gap, "linear", frame="global").velocity[0, 0] / 5)
    assert abs(speeds[1] - speeds[0]) < 0.02  # before the fix: about 0.26

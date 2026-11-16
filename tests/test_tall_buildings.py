"""``Parameterizations.tall_buildings``: root-sum-of-squares shelter and the tall-building zone (docs/tall-buildings.md)."""
import numpy as np
import pytest
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import _qes, wind
from fixtures.geometry import tower_city
from fixtures.specs import pedestrian_solver

pytestmark = pytest.mark.usefixtures("dtcc_logger")
OFF, ON = wind.Parameterizations(wake=3), wind.Parameterizations(wake=3, tall_buildings=1)


def city(blocks):
    """Buildings from (x0, y0, x1, y1, height) boxes."""
    out = City()
    for n, (x0, y0, x1, y1, height) in enumerate(blocks):
        b = Building(id=f"b{n}")
        b.measured_height = float(height)
        b.add_geometry(Surface(vertices=np.array([[x0, y0, 0.], [x0, y1, 0], [x1, y1, 0], [x1, y0, 0]])), GeometryType.LOD0)
        out.add_building(b)
    return out


def array(centre_height=10.0, rows=range(-2, 3)):
    """5 x 5 blocks of 10 m on a 20 m pitch around (100, 100); walls on the faces of a 2 m grid."""
    return city([(100 + 20 * i - 5, 100 + 20 * j - 5, 100 + 20 * i + 5, 100 + 20 * j + 5,
                  centre_height if i == j == 0 else 10.0) for i in rows for j in range(-2, 3)])


def solve(model, parameterizations, direction=270.0, **options):
    # odd bounds put the cell faces on the walls, which keeps the layout mirror-symmetric
    options.setdefault("solver", wind.Solver(max_iterations=400))
    return wind.run(model, speed=5.0, direction=direction, resolution=2.0, bounds=(-1, -1, 0, 201, 201, None),
                    parameterizations=parameterizations, **options)


def scalar(result, height=2.0):
    sample = result.sample(height, "nearest")
    return np.where(sample.valid, sample.scalar_speed, np.nan)


def test_default_is_off_and_needs_the_spreading_wake():
    assert wind.Parameterizations().tall_buildings == 0 and _qes.ModelSettings().tall_buildings_flag == 0
    assert wind.Parameterizations.from_dict(ON.to_dict()) == ON
    for changes in (dict(tall_buildings=1), dict(tall_buildings=1, wake=2), dict(tall_buildings=2, wake=3),
                    dict(tall_buildings=True, wake=3)):
        with pytest.raises(ValueError, match="tall_buildings"):
            wind.Parameterizations(**changes)


def test_off_is_the_released_spreading_wake():
    model = array(60.0)
    np.testing.assert_array_equal(solve(model, OFF).velocity, solve(model, wind.Parameterizations(wake=3, tall_buildings=0)).velocity)


def test_an_isolated_building_is_unchanged():
    tower = city([(90, 90, 110, 110, 60)])
    off, on = solve(tower, OFF), solve(tower, ON)
    np.testing.assert_array_equal(off.velocity, on.velocity)
    np.testing.assert_array_equal(off.wake.tke, on.wake.tke)


def test_an_equal_height_array_gets_the_shelter_rule_but_no_zone():
    off, on = solve(array(), OFF), solve(array(), ON)
    assert np.nanmax(np.abs(off.wake.deficit - on.wake.deficit)) > 0.05  # overlapping wakes add up
    np.testing.assert_array_equal(off.wake.tke, on.wake.tke)  # no zone: no added turbulence
    assert float(on.wake.deficit.max()) <= 1.0
    assert (on.wake.deficit >= off.wake.deficit - 1e-6).all()


def test_the_deficit_does_not_fall_with_added_upwind_rows():
    behind = np.array([[151.0, 101.0, 2.0], [161.0, 101.0, 2.0], [181.0, 101.0, 2.0]])
    values = [solve(array(rows=range(2 - n, 3)), ON).sample_points(behind, "nearest", frame="global").wake_deficit
              for n in (0, 2, 4)]
    assert (values[1] >= values[0] - 1e-6).all() and (values[2] >= values[1] - 1e-6).all()
    assert values[2][0] > values[0][0] + 0.02


def test_a_tower_among_low_blocks_speeds_up_the_ground_around_it():
    off, on = solve(array(60.0), OFF, 225.0), solve(array(60.0), ON, 225.0)
    sample = off.sample(2.0, "nearest")
    x, y = np.meshgrid(sample.x + off.origin[0], sample.y + off.origin[1])
    distance = np.maximum(np.maximum(np.abs(x - 100) - 5, np.abs(y - 100) - 5), 0)  # to the tower's footprint
    near, far = (distance > 0) & (distance < 15), distance > 60
    change = scalar(on) - scalar(off)  # m/s, at an inflow of 5 m/s at 10 m
    assert np.nanmean(change[near]) > 0.2 and np.nanmax(change[near]) > 1.0
    assert np.nanmean(np.abs(change[far])) < 0.25
    assert np.nanmax(np.abs(on.wake.tke - off.wake.tke)) > 0.1  # the turbulent share of the zone


def test_the_zone_keeps_the_mirror_symmetry_and_the_mass_balance():
    off, on = solve(array(60.0), OFF), solve(array(60.0), ON)
    mirror = lambda result: np.nanmax(np.abs(scalar(result) - scalar(result)[::-1]))  # noqa: E731
    assert mirror(on) < 1.5 * mirror(off)  # the released layout carries about 2e-3 m/s at this iteration count
    assert on.diagnostics.max_divergence < 2 * off.diagnostics.max_divergence


def test_both_precisions_carry_the_turbulent_share():
    single = solve(array(60.0), ON)
    double = solve(array(60.0), ON, solver=wind.Solver(max_iterations=400, precision="float64"))
    assert np.nanmax(np.abs(scalar(single) - scalar(double))) < 0.05


def test_it_is_recorded_and_outside_pedestrian_policy():
    model = solve(array(60.0), ON).metadata["model"]
    assert model["tall_buildings_flag"] == 1 and model["parameterizations"]["tall_buildings"] == 1
    options = dict(speed=5, direction=270, bounds=(0, 0, 0, 160, 160, 64), solver=pedestrian_solver())
    preview = wind.preview_grid(tower_city(), **options, parameterizations=ON)
    assert "unqualified_model_settings" in preview.eligibility["exclusions"]

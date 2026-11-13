"""Spreading far wake, wake code 3 (WAKE_UPDATE_V2.md, sections 3.3, 3.4 and 5)."""
import json
import math

import numpy as np
import pytest
from shapely.geometry import Polygon, box
from dtcc_qes import _qes, wind
from dtcc_qes.profiles import friction_velocity
from fixtures.footprints import building, city
from fixtures.specs import pedestrian_solver

pytestmark = pytest.mark.usefixtures("dtcc_logger")
SPREADING = wind.Parameterizations(wake=3)
# One 20 x 30 x 20 m building on a 2 m grid: the investigation's wake-edge and direction setup.
SINGLE = dict(resolution=2.0, bounds=(0, 0, 0, 200, 200, 60), solver=wind.Solver(stop="multiplier_change", max_iterations=400))


def single():
    return city(building("b", box(90, 85, 110, 115), 20.0))


def pair():
    return city(building("a", box(20, 20, 32, 50), 18), building("b", box(60, 30, 70, 42), 9))


def run(value=None, **options):
    options = dict(dict(speed=5, direction=270, bounds=(0, 0, 0, 150, 80, 50), parameterizations=SPREADING,
                        solver=wind.Solver(stop="multiplier_change", max_iterations=100)), **options)
    return wind.run(pair() if value is None else value, **options)


def test_flag_range_accepts_three_and_the_bridge_rejects_four():
    assert SPREADING.wake == 3 and wind.Parameterizations.from_dict(SPREADING.to_dict()) == SPREADING
    with pytest.raises(ValueError, match=r"wake must be an integer in \[0, 3\]"):
        wind.Parameterizations(wake=4)
    model = _qes.ModelSettings()
    model.wake_flag = 4
    grid = _qes.GridConfig()
    empty = dict(vertices=np.empty((0, 2)), offsets=np.zeros(1, np.int64), heights=np.empty(0),
                 base_heights=np.empty(0), ids=np.empty(0, np.int64))
    with pytest.raises(ValueError, match="wake flag"):
        _qes.WindRunner().prepare(grid, model, **empty)


def test_fields_exist_for_code_three_only():
    result = run()
    shape = result.velocity.shape[:3]
    assert result.wake.deficit.shape == result.wake.tke.shape == shape
    assert result.wake.deficit.dtype == result.wake.tke.dtype == np.float32
    assert np.isfinite(result.wake.deficit).all() and np.isfinite(result.wake.tke).all()
    assert 0 <= result.wake.deficit.min() and result.wake.deficit.max() <= 1 and result.wake.deficit.max() > 0.5
    assert result.wake.tke.min() >= 0 and result.wake.tke.max() > 0
    assert not np.any(result.cell_flags == 5)  # no far-wake flag
    wake = result.metadata["wake"]
    assert wake["constants"] == dict(spread=0.2, edge_offset=0.22, edge_length=0.9, turbulence=0.08,
                                     reach_cut=0.05, taper_start=0.1, skip=1e-4, layer_cut=6.0)
    assert result.metadata["model"]["wake_flag"] == 3
    json.dumps(result.metadata, allow_nan=False)
    names = [field.name for field in result.to_dtcc().fields]
    assert "wake_deficit" in names and "wake_tke" in names
    legacy = run(parameterizations=wind.Parameterizations())
    assert legacy.wake is None and "wake" not in legacy.metadata
    assert "wake_deficit" not in [field.name for field in legacy.to_dtcc().fields]
    with pytest.raises(ValueError, match="no wake fields"):
        legacy.scalar_speed()
    with pytest.raises(ValueError, match="inflow_tke requires wake fields"):
        legacy.sample(2.0, inflow_tke=1.0)


def test_scalar_speed_bounds_and_inflow_turbulence():
    result = run()
    fluid = ~result.solid_mask
    speed, scalar = result.speed, result.scalar_speed()
    assert np.all(scalar[fluid] >= speed[fluid])
    assert np.isnan(scalar[result.solid_mask]).all()
    still = fluid & (result.wake.deficit == 0) & (result.wake.tke == 0)
    assert still.any()
    np.testing.assert_allclose(result.scalar_speed(inflow_tke=0.0)[still], speed[still], rtol=1e-14)
    # The default inflow k is 5.5 u*², u* exact for the default log profile.
    ustar = 0.4 * 5 / math.log1p(10 / 0.1)
    inflow = result.metadata["wake"]["inflow_tke"]
    assert inflow["source"] == "profile fit" and inflow["fit_window"] == [1.0, float(result.z_faces[-1])]
    assert inflow["friction_velocity"] == pytest.approx(ustar, rel=1e-9)
    assert inflow["value"] == pytest.approx(5.5 * ustar ** 2, rel=1e-9)
    np.testing.assert_allclose(scalar[still], np.sqrt(speed[still] ** 2 + 2 * inflow["value"]), rtol=1e-12)
    # Overrides: a number, a callable and a table in log height, with the deficit and the wake turbulence.
    u = result.velocity.astype(np.float64)
    D, kw = result.wake.deficit.astype(np.float64), result.wake.tke.astype(np.float64)
    z = np.asarray(result.z, np.float64)[:, None, None]
    for inflow_tke, k in ((0.7, 0.7), (lambda h: 0.1 * h, 0.1 * z),
                          (([1.0, 100.0], [0.0, 2.0]), np.interp(np.log(z), np.log([1.0, 100.0]), [0.0, 2.0]))):
        expected = np.sqrt((u ** 2).sum(-1) + 2 * (k * (1 - D) ** 2 + kw))
        np.testing.assert_allclose(result.scalar_speed(inflow_tke=inflow_tke)[fluid], expected[fluid], rtol=1e-12)
    for bad in (-1.0, ([1.0], [1.0, 2.0]), "k", lambda h: np.nan):
        with pytest.raises(ValueError):
            result.scalar_speed(inflow_tke=bad)


def test_samples_carry_the_wake_fields():
    result = run()
    plane = result.sample(float(result.z[1]), "nearest")
    expected = result.scalar_speed()[1]
    valid = plane.valid
    np.testing.assert_allclose(plane.scalar_speed[valid], expected[valid], rtol=1e-12)
    np.testing.assert_array_equal(plane.wake_deficit[valid], result.wake.deficit[1][valid])
    assert np.isnan(plane.scalar_speed[~valid]).all()
    linear = result.sample(2.0, "linear", inflow_tke=0.0)
    assert np.all(linear.scalar_speed[linear.valid] >= linear.speed[linear.valid] - 1e-12)
    points = np.array([[50.0, 35.0, 2.0], [100.0, 35.0, 2.0], [26.0, 35.0, 2.0]])  # the last inside building a
    sample = result.sample_points(points, "linear", frame="global")
    assert np.isfinite(sample.scalar_speed[:2]).all() and np.isnan(sample.scalar_speed[2])
    assert sample.wake_deficit[0] > 0.5 and sample.wake_tke[0] > 0
    local = result.sample_points(points - np.asarray(result.origin), "linear")
    np.testing.assert_array_equal(local.scalar_speed[:2], sample.scalar_speed[:2])
    assert result.sample_points(points, "linear", frame="global", inflow_tke=0.0).scalar_speed[0] <= sample.scalar_speed[0]


def test_friction_velocity_rules():
    for z0 in (0.03, 0.1, 0.5):
        fit = friction_velocity(wind.LogProfile(5, 270, roughness_length=z0), 60.0)
        assert fit["friction_velocity"] == pytest.approx(0.4 * 5 / math.log1p(10 / z0), rel=1e-9)
        assert fit["source"] == "profile fit" and fit["window"] == (1.0, 60.0)
    uniform = friction_velocity(wind.UniformProfile(5, 270, roughness_length=0.05), 60.0)
    assert uniform == dict(friction_velocity=pytest.approx(0.4 * 5 / math.log1p(10 / 0.05)),
                           source="declared roughness", window=None, roughness_length=pytest.approx(0.05))
    assert friction_velocity(wind.LogProfile(0, 270), 60.0)["friction_velocity"] == 0
    with pytest.raises(ValueError):
        friction_velocity(wind.LogProfile(5, 270), 0.5)
    result = run(profile=wind.UniformProfile(5, 270), speed=None, direction=None)
    assert result.metadata["wake"]["inflow_tke"]["source"] == "declared roughness"


def test_wake_edge_has_no_step():
    """K along a lateral line 41 and 61 m behind the lee face (2 m): code 2 steps by 0.20 and 0.16."""
    steps = {}
    for code in (2, 3):
        result = wind.run(single(), speed=5, direction=270, **SINGLE, parameterizations=wind.Parameterizations(wake=code))
        plane = result.sample(2.0, "linear")
        K = np.where(plane.valid, plane.speed / result.reference_speed, np.nan)
        x, y = np.asarray(plane.x) + result.origin[0], np.asarray(plane.y) + result.origin[1]
        lateral = (y > 100) & (y < 132)
        steps[code] = [np.nanmax(np.abs(np.diff(K[lateral, np.abs(x - (110 + d)).argmin()]))) for d in (41, 61)]
    assert min(steps[2]) > 0.15
    assert max(steps[3]) < 0.05


def test_direction_sweep_has_no_jump_at_the_far_wake_probe():
    """K at (160, 100, 2) for 225-315 degrees in 1 degree steps: code 2 jumps by 0.057."""
    K = []
    for direction in np.arange(225.0, 315.5, 1.0):
        result = wind.run(single(), speed=5, direction=float(direction), **SINGLE, parameterizations=SPREADING)
        K.append(result.sample_points(np.array([[160.0, 100.0, 2.0]]), "linear", frame="global").speed[0] / 5)
    assert np.max(np.abs(np.diff(K))) < 0.02


@pytest.mark.parametrize("shape", ["l_shape", "courtyard"])
def test_concave_and_holed_footprints(shape):
    outline = (Polygon([(20, 20), (20, 50), (32, 50), (32, 32), (50, 32), (50, 20)]) if shape == "l_shape" else
               Polygon(box(20, 20, 50, 50).exterior.coords, [box(30, 30, 40, 40).exterior.coords]))
    for direction in (270.0, 225.0, 90.0):
        result = run(city(building("x", outline, 15)), direction=direction, bounds=(0, 0, 0, 120, 100, 40),
                     footprints=wind.Footprints(min_detail=0.01))
        assert np.isfinite(result.velocity).all() and np.isfinite(result.wake.deficit).all()
        assert 0 <= result.wake.deficit.min() and result.wake.deficit.max() <= 1
        if shape == "courtyard":  # no deficit from its own building inside the courtyard
            x, y = np.meshgrid(np.asarray(result.x) + result.origin[0], np.asarray(result.y) + result.origin[1])
            inside = (x > 31) & (x < 39) & (y > 31) & (y < 39)
            assert np.all(result.wake.deficit[:, inside] == 0)


@pytest.mark.parametrize("profile", [wind.PowerLawProfile(5, 250, reference_height=10, exponent=0.2),
                                     wind.MeasuredProfile([2, 10, 60], [3.5, 5, 6.5], direction=250,
                                                          reference_height=10, below="log"),
                                     wind.UniformProfile(5, 250)])
def test_combines_with_profiles_grids_turbulence_and_exposed_faces(profile):
    faces = np.r_[np.arange(0, 10, 1.0), np.arange(10, 65, 3.0)]
    result = wind.run(pair(), profile, bounds=(0, 0, 0, 150, 80, None), resolution=2.0,
                      vertical_grid=wind.VerticalGrid.from_faces(faces), turbulence=wind.Turbulence(),
                      footprints=wind.Footprints(min_detail=0.01), parameterizations=SPREADING,
                      solver=wind.Solver(stop="multiplier_change", max_iterations=100))
    assert result.metadata["model"]["exposed_faces"] and result.turbulence is not None
    assert result.wake.deficit.shape == result.velocity.shape[:3] and result.wake.deficit.max() > 0.5
    scalar = result.scalar_speed()
    assert np.isfinite(scalar[~result.solid_mask]).all()
    json.dumps(result.metadata, allow_nan=False)


def test_spreading_wake_is_outside_pedestrian_policy():
    options = dict(speed=5, direction=270, bounds=(0, 0, 0, 150, 80, 50), solver=pedestrian_solver())
    assert "unqualified_model_settings" not in wind.preview_grid(pair(), **options).eligibility["exclusions"]
    preview = wind.preview_grid(pair(), **options, parameterizations=SPREADING)
    assert "unqualified_model_settings" in preview.eligibility["exclusions"]

"""Automatic prototype constraints and geometry/solver integration."""
from dataclasses import FrozenInstanceError
import json

import numpy as np
import pytest
from dtcc_core.model import City
from dtcc_qes import _qes, wind
from dtcc_qes._auto_grid import generate_auto_layers
from dtcc_qes.vertical_grid import effective_faces

from city_cases import city_case
from fixtures.cases import ONE_BUILDING

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def generate(spec=None, *, resolution=2, top=40, heights=()):
    spec = wind.VerticalGrid.auto() if spec is None else spec
    return generate_auto_layers(spec._automatic, resolution=float(np.float32(resolution)),
                                top=top, heights=heights)


def check_constraints(layers, record, *, heights, top):
    faces = effective_faces(layers)
    native = layers.astype(np.float32).astype(float)
    settings = record["effective_settings"]
    r, hmin, growth = (settings[name] for name in ("resolution", "minimum_thickness", "growth_rate"))
    tolerance = record["constraint_relative_tolerance"]
    assert faces[0] == 0 and np.all(np.diff(faces) > 0)
    assert np.all(native >= hmin*(1-tolerance))
    assert np.all(native[1:] >= native[:-1]*(1-tolerance))
    assert np.all(native[1:] <= native[:-1]*growth*(1+tolerance))
    count = settings["fine_layer_count"]
    np.testing.assert_array_equal(native[:count], native[0])
    assert native[0] <= settings["maximum_fine_thickness"]*(1+tolerance)
    for h, lower in zip(native, faces[:-1]):
        active = [float(np.float32(value)) for value in heights if float(lower) < 1.5*float(np.float32(value))]
        cap = min(r, max(hmin, min(active)/10)) if active else settings["upper_layer_cap"]
        assert h <= cap*(1+tolerance)
    centres = np.float32(0.5)*(faces[:-1]+faces[1:])
    assert centres[2] <= settings["pedestrian_height"] <= centres[-1]
    fit = record["endpoint_fit"]
    assert abs(fit["planned_top"]-top) < 1e-10
    assert abs(float(faces[-1])-top) <= fit["accumulation_tolerance"]
    json.dumps(record, allow_nan=False)


@pytest.mark.parametrize("resolution,count,h", [(2,7,3/7), (4,6,0.5), (4.5,5,0.6), (0.1,30,0.1)])
def test_fine_band_policy_examples(resolution, count, h):
    layers, record = generate(resolution=resolution)
    settings = record["effective_settings"]
    assert settings["fine_layer_count"] == count
    np.testing.assert_allclose(layers[:count], h, rtol=2e-8, atol=0)
    check_constraints(layers, record, heights=(), top=40)


@pytest.mark.parametrize("resolution", [0.1, 0.3, 1, 2, 4.5])
@pytest.mark.parametrize("heights", [(), (0.4,), (2.9,), (8,24), (0.4,8,30)])
@pytest.mark.parametrize("growth", [1.10, 1.15, 1.20])
def test_generated_grids_satisfy_constraints_across_caps_and_decimal_endpoints(resolution, heights, growth):
    top = max(12.345, max(heights, default=0)+20)+0.123
    layers, record = generate(wind.VerticalGrid.auto(growth_rate=growth),
                              resolution=resolution, top=top, heights=heights)
    check_constraints(layers, record, heights=heights, top=top)


def test_empty_feasible_count_interval_extends_fine_band_upward():
    layers, record = generate(resolution=2.24, heights=[2.9])
    settings = record["effective_settings"]
    assert settings["fine_layer_count"] == 11 and settings["fine_band_extended"]
    assert settings["planned_fine_region_height"] == pytest.approx(3.08, abs=2e-8)
    np.testing.assert_allclose(layers[:11], 0.28, rtol=1e-8)
    check_constraints(layers, record, heights=[2.9], top=40)
    with pytest.raises(ValueError, match="fine band does not fit"):
        generate(resolution=2.24, heights=[2.9], top=3.04)


def test_endpoint_redistributes_tail_and_preserves_fine_band():
    spec = wind.VerticalGrid.auto(first_layer_thickness=0.5)
    layers, record = generate(spec, top=4.1)
    np.testing.assert_array_equal(layers[:6], 0.5)
    np.testing.assert_allclose(layers[6:], [0.55,0.55], rtol=0, atol=1e-15)
    assert record["endpoint_fit"]["tail_start_index"] == 6
    check_constraints(layers, record, heights=(), top=4.1)


@pytest.mark.parametrize("top", [3.0000001, 3.4, 3.6])
def test_infeasible_terminal_count_rejects_instead_of_appending_a_sliver(top):
    with pytest.raises(ValueError, match="preserving the fine band"):
        generate(wind.VerticalGrid.auto(first_layer_thickness=0.5), top=top)


def test_domain_can_end_at_fine_band_if_pedestrian_height_is_bracketed():
    layers, record = generate(top=3)
    assert len(layers) == record["effective_settings"]["fine_layer_count"] == 7
    check_constraints(layers, record, heights=(), top=3)
    with pytest.raises(ValueError, match="bracket pedestrian_height"):
        generate(wind.VerticalGrid.auto(fine_region_height=1.5), top=1.5)


def test_short_building_only_limits_its_own_region_and_is_not_discarded():
    layers, record = generate(heights=[0.4,30], top=80)
    faces = effective_faces(layers)
    assert layers[0] == 0.25
    assert np.max(layers[faces[:-1] >= 45]) > 3
    check_constraints(layers, record, heights=[0.4,30], top=80)


def test_effective_face_below_roof_buffer_does_not_release_cap_early():
    layers, record = generate(resolution=0.1, heights=[2])
    count = record["effective_settings"]["fine_layer_count"]
    faces = effective_faces(layers)
    assert record["effective_settings"]["planned_fine_region_height"] >= 3
    assert faces[count] < 3  # Accumulation places this face below 1.5 * H.
    assert layers[count] <= float(np.float32(0.1))
    assert layers[count+1] > layers[count]
    check_constraints(layers, record, heights=[2], top=40)


def test_building_order_and_duplicate_heights_do_not_change_grid():
    first, _ = generate(heights=[0.4,8,8,30], top=80)
    second, _ = generate(heights=[30,8,0.4,8], top=80)
    np.testing.assert_array_equal(first,second)


def test_equal_native_override_values_survive_horizontal_spacing_narrowing():
    top = 80*float(np.float32(0.7))
    layers, record = generate(wind.VerticalGrid.auto(pedestrian_height=10,
        min_layer_thickness=0.7, upper_layer_cap=0.7), resolution=0.7, top=top)
    check_constraints(layers, record, heights=(), top=top)
    with pytest.raises(ValueError, match="upper_layer_cap"):
        generate(wind.VerticalGrid.auto(upper_layer_cap=2*(1-9e-7)))


def test_bounded_settings_do_not_silently_coarsen_to_meet_cell_budget(monkeypatch):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    spec = wind.VerticalGrid.auto()
    before = wind.preview_grid(city, **condition, **grid, vertical_grid=spec)
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native fields"))
    with pytest.raises(ValueError, match="max_cells"):
        wind.preview_grid(city, **condition, **grid, vertical_grid=spec, max_cells=before.cell_count-1)
    after = wind.preview_grid(city, **condition, **grid, vertical_grid=spec, max_cells=before.cell_count)
    np.testing.assert_array_equal(after.solver_dz,before.solver_dz)


def test_automatic_grid_still_enforces_native_face_index_limit(monkeypatch):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native fields"))
    with pytest.raises(ValueError, match="native index limit"):
        wind.preview_grid(City(), bounds=(0,0,0,20000,20000,40),
            max_cells=10_000_000_000, vertical_grid=wind.VerticalGrid.auto())


@pytest.mark.parametrize("count", range(5,12))
def test_count_tie_favors_fewer_layers(count):
    target = (3/count+3/(count+1))/2
    layers, record = generate(wind.VerticalGrid.auto(first_layer_thickness=target))
    assert record["effective_settings"]["fine_layer_count"] == count
    assert layers[0] == 3/count


@pytest.mark.parametrize("options", [
    {"pedestrian_height": 0}, {"pedestrian_height": True}, {"pedestrian_height": None},
    {"growth_rate": 1}, {"growth_rate": 1.21}, {"growth_rate": np.nan}, {"growth_rate": None},
    {"min_layer_thickness": 0}, {"min_layer_thickness": "0.2"},
    {"max_aspect_ratio": 0.9}, {"max_aspect_ratio": None},
    {"first_layer_thickness": -1}, {"fine_region_height": 1},
    {"upper_layer_cap": np.inf}, {"upper_layer_cap": 10**1000},
])
def test_invalid_settings_rejected_at_specification_creation(options):
    with pytest.raises(ValueError):
        wind.VerticalGrid.auto(**options)


@pytest.mark.parametrize("spec,resolution,message", [
    (wind.VerticalGrid.auto(), 5, "minimum thickness conflicts"),
    (wind.VerticalGrid.auto(min_layer_thickness=0.3), 0.1, "lower the explicit min_layer_thickness"),
    (wind.VerticalGrid.auto(upper_layer_cap=1), 2, "upper_layer_cap"),
    (wind.VerticalGrid.auto(fine_region_height=10000), 0.1, "10000"),
    (wind.VerticalGrid.auto(first_layer_thickness=1e-9, min_layer_thickness=1e-9,
                           max_aspect_ratio=1e12), 2, "10000"),
])
def test_incompatible_effective_settings_fail_before_flow_allocation(spec, resolution, message, monkeypatch):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native fields"))
    with pytest.raises(ValueError, match=message):
        wind.preview_grid(City(), resolution=resolution,
            bounds=(0,0,0,10*resolution,10*resolution,40), vertical_grid=spec)


def test_uniform_spacing_that_would_exceed_native_layer_count_fails():
    with pytest.raises(ValueError, match="10000"):
        generate(wind.VerticalGrid.auto(growth_rate=1.000001), resolution=0.1, top=10000)


def test_specification_and_returned_settings_are_independent_immutable_snapshots():
    spec = wind.VerticalGrid.auto(growth_rate=np.float32(1.15))
    assert spec.mode == "auto" and spec.faces is None
    with pytest.raises(FrozenInstanceError):
        spec._automatic.growth_rate = 1.2
    with pytest.raises(ValueError, match="depend on geometry"):
        _ = spec.layers
    first = spec.to_metadata()
    first["requested_settings"]["growth_rate"] = 1.2
    assert spec.to_metadata()["requested_settings"]["growth_rate"] == float(np.float32(1.15))
    assert first["policy_status"] == "prototype_unvalidated"


@pytest.mark.parametrize("resolution", [0.1,2,4.5])
def test_preview_and_native_flat_profile_agree_for_automatic_grid(resolution):
    spec = wind.VerticalGrid.auto()
    options = dict(resolution=resolution, bounds=(0,0,0,8*resolution,8*resolution,12.345), vertical_grid=spec)
    preview = wind.preview_grid(City(), speed=5, direction=270, **options)
    result = wind.run(City(), speed=5, direction=270, **options)
    np.testing.assert_array_equal(preview.z_faces, result.z_faces)
    np.testing.assert_array_equal(preview.z, result.z)
    assert preview.domain == result.metadata["domain"]
    assert result.metadata["domain"]["vertical_grid"]["mode"] == "auto"
    assert "automatic vertical layers" in result.metadata["simplifications"][-1]
    # Other horizontal spacings already produce tiny nonzero native residuals
    # on the equivalent explicit grid. Use the predeclared empty-city scales,
    # not an exact-zero assumption that happens to hold for the 2 m case.
    assert result.diagnostics.max_divergence*(10/5) <= 1e-3
    assert result.diagnostics.rms_divergence*(10/5) <= 1e-4
    explicit = wind.run(City(), speed=5, direction=270,
        **(options | {"vertical_grid": wind.VerticalGrid.from_faces(
            preview.domain["vertical_grid"]["planned_faces"])}))
    np.testing.assert_array_equal(result.velocity,explicit.velocity)
    assert result.diagnostics == explicit.diagnostics
    expected = 5*np.log1p(result.z.astype(float)/0.1)/np.log(101)
    np.testing.assert_allclose(result.velocity[...,0], np.broadcast_to(expected[:,None,None], result.velocity.shape[:-1]),
                               rtol=2e-6, atol=2e-6)
    assert result.sample(1.5, method="linear").valid.all()
    record = preview.domain["vertical_grid"]
    profile = record["pedestrian_sampling"]
    assert profile["bracketing_centres"][0] <= 1.5 <= profile["bracketing_centres"][1]
    assert abs(profile["flat_profile_bias_K"]) < 0.01
    assert record["endpoint_fit"]["requested_top"] == 12.345
    assert result.z_faces[-1] < 14  # No legacy expansion to the next 2 m cell.
    json.dumps(result.metadata, allow_nan=False)


def test_translated_building_occupancy_and_roofs_use_effective_faces():
    outputs = []
    for offset in [(0,0,0), (1e9,-2e9,100)]:
        city, condition, grid, _ = city_case(ONE_BUILDING, offset)
        city.buildings[0].measured_height = 7.9
        preview = wind.preview_grid(city, **condition, **grid, vertical_grid=wind.VerticalGrid.auto())
        result = wind.run(city, **condition, **grid, vertical_grid=wind.VerticalGrid.auto())
        assert preview.domain == result.metadata["domain"]
        outputs.append(result)
    a, b = outputs
    np.testing.assert_array_equal(a.z_faces,b.z_faces)
    np.testing.assert_array_equal(a.velocity,b.velocity)
    z, y, x = np.meshgrid(a.z,a.y,a.x,indexing="ij")
    np.testing.assert_array_equal(a.solid_mask,(x>=30)&(x<40)&(y>=25)&(y<35)&(z<=np.float32(7.9)))
    roof, = a.metadata["domain"]["vertical_grid"]["roof_representation"]
    assert roof["represented_height"] == a.z_faces[np.searchsorted(a.z,np.float32(7.9),side="right")]
    assert not np.any(a.z_faces == np.float32(7.9))


def test_automatic_bounds_and_limits_preserve_legacy_rules(monkeypatch):
    spec = wind.VerticalGrid.auto()
    city, _, _, _ = city_case(ONE_BUILDING)
    preview = wind.preview_grid(city, vertical_clearance=35, vertical_grid=spec, profile=wind.LogProfile(1, 0, reference_height=50))
    fit = preview.domain["vertical_grid"]["endpoint_fit"]
    assert fit["requested_top"] == 50
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native fields"))
    with pytest.raises(ValueError, match="max_cells"):
        wind.run(city, speed=5, direction=270, vertical_grid=spec, max_cells=100)
    with pytest.raises(ValueError, match="empty city requires explicit"):
        wind.preview_grid(City(), vertical_grid=spec)


def test_preview_is_independent_of_wind_direction_and_serializes_requested_effective_settings(monkeypatch):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Preview allocated flow fields"))
    city, _, grid, _ = city_case(ONE_BUILDING)
    options = dict(**grid, vertical_grid=wind.VerticalGrid.auto())
    a, b = wind.preview_grid(city, **options), wind.preview_grid(city, **options)
    np.testing.assert_array_equal(a.z_faces,b.z_faces)
    assert a.domain == b.domain
    metadata = a.domain["vertical_grid"]
    assert metadata["requested_settings"]["upper_layer_cap"] is None
    assert metadata["effective_settings"]["upper_layer_cap"] == 8
    assert metadata["mode"] == "auto" and metadata["policy_status"] == "prototype_unvalidated"
    json.dumps(metadata, allow_nan=False)

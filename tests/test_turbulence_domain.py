"""Turbulence domain growth, prefix preservation and native margin equivalence."""

import json
import numpy as np
import pytest
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import _qes, wind
from dtcc_qes import _city
from dtcc_qes.vertical_grid import effective_faces

from fixtures.cases import FLAT, ONE_BUILDING
from runner_cases import inputs

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def blocks(heights=(15, 15, 15, 15), *, base=0, width=12):
    city = City()
    for i, height in enumerate(heights):
        x, y = 22 + (i % 2)*20, 22 + (i // 2)*20
        building = Building(id=str(i))
        building.measured_height = float(height)
        building.add_geometry(Surface(vertices=np.array([
            [x,y,base], [x,y+width,base], [x+width,y+width,base], [x+width,y,base],
        ], dtype=float)), GeometryType.LOD0)
        city.add_building(building)
    return city


def assert_margin(preview, reference):
    assert preview.z_faces.dtype == np.float32
    assert len(preview.z_faces) >= 4
    assert preview.z_faces[-4] >= reference and preview.z_faces[-1] >= 15
    record = preview.domain["turbulence"]
    assert record["reference_height"] == reference
    assert record["effective_top"] == float(preview.z_faces[-1])
    assert record["required_top"] <= record["effective_top"]
    json.dumps(preview.domain, allow_nan=False)


def test_uniform_midrise_city_raises_automatic_top():
    city = blocks()
    baseline = wind.preview_grid(city)
    actual = wind.preview_grid(city, turbulence=True)
    assert_margin(actual, 45)
    record = actual.domain["turbulence"]
    assert record["raised"] and record["default_top"] == float(baseline.z_faces[-1])
    assert record["added_layers"] == actual.shape[0] - baseline.shape[0]
    assert record["required_top"] == record["effective_top"] == 52
    assert actual.domain["effective_bounds"][-1] == 52


def test_tall_tower_keeps_default_top():
    city = blocks((7.9, 7.9, 7.9, 23.7))
    baseline = wind.preview_grid(city)
    actual = wind.preview_grid(city, turbulence=True)
    np.testing.assert_array_equal(actual.z_faces, baseline.z_faces)
    assert not actual.domain["turbulence"]["raised"]
    assert actual.domain["turbulence"]["added_layers"] == 0


def test_explicit_bounds_too_low_raise():
    with pytest.raises(ValueError, match=r"zRef 24.*margin.*sufficient top of 30 m"):
        wind.preview_grid(blocks((8,)), bounds=(0,0,0,80,80,26), turbulence=True)


@pytest.mark.parametrize("faces,top", [(np.arange(0,30,2), 30),
    (np.r_[np.arange(0,22,2), 23,27,32], 42)])
def test_explicit_z_faces_too_low_raise(faces, top):
    spec = wind.VerticalGrid.from_faces(faces)
    with pytest.raises(ValueError, match=rf"zRef 24.*margin.*sufficient top of {top} m"):
        wind.preview_grid(blocks((8,)), vertical_grid=spec, turbulence=True)


@pytest.mark.parametrize("bounds", [None, (0,0,0,80,80,40)])
def test_automatic_vertical_grid_satisfies_margin(bounds):
    city = blocks()
    options = dict(vertical_grid=wind.VerticalGrid.auto(), bounds=bounds)
    if bounds is not None:
        with pytest.raises(ValueError, match=r"zRef 45.*margin"):
            wind.preview_grid(city, **options, turbulence=True)
        return
    actual = wind.preview_grid(city, **options, turbulence=True)
    assert_margin(actual, 45)
    assert actual.domain["turbulence"]["extension_policy"] == "constant_last_thickness"


@pytest.mark.parametrize("height,resolution", [(20,2), (15,1), (15,0.5)])
@pytest.mark.parametrize("spec", [None, wind.VerticalGrid.auto()])
def test_automatic_midrise_retry_regression(height, resolution, spec):
    actual = wind.preview_grid(blocks((height,)*4), resolution=resolution,
                               vertical_grid=spec, turbulence=True)
    assert_margin(actual, 3*height)


@pytest.mark.parametrize("spec", [None, wind.VerticalGrid.auto(),
    wind.VerticalGrid.auto(first_layer_thickness=0.3, growth_rate=1.10)])
def test_automatic_extension_preserves_lower_layers(spec):
    city = blocks((20,)*4)
    options = dict(vertical_grid=spec)
    baseline = wind.preview_grid(city, **options)
    actual = wind.preview_grid(city, **options, turbulence=True)
    count = baseline.shape[0]
    np.testing.assert_array_equal(actual.solver_dz[:count], baseline.solver_dz)
    np.testing.assert_array_equal(actual.z_faces[:count+1], baseline.z_faces)
    np.testing.assert_array_equal(actual.z[:count], baseline.z)
    np.testing.assert_array_equal(actual.solver_dz[count:], baseline.solver_dz[-1])
    record = actual.domain["turbulence"]
    assert record["lower_layers_preserved"] and record["added_layers"] > 1
    if spec is not None:
        vertical = actual.domain["vertical_grid"]
        np.testing.assert_array_equal(vertical["solver_layer_thicknesses"], actual.solver_dz.astype(float))
        planned = np.diff(vertical["planned_faces"])
        np.testing.assert_array_equal(planned.astype(np.float32), actual.solver_dz)
        tolerance = vertical["constraint_relative_tolerance"]
        settings = vertical["effective_settings"]
        assert np.all(actual.growth_ratios >= 1-tolerance)
        assert np.all(actual.growth_ratios <= settings["growth_rate"]*(1+tolerance))
        assert actual.solver_dz.min() >= settings["minimum_thickness"]*(1-tolerance)
        assert actual.solver_dz.max() <= settings["upper_layer_cap"]*(1+tolerance)
        assert vertical["pedestrian_sampling"] == baseline.domain["vertical_grid"]["pedestrian_sampling"]
        assert vertical["roof_representation"] == baseline.domain["vertical_grid"]["roof_representation"]


@pytest.mark.parametrize("spec", [None, wind.VerticalGrid.auto()])
def test_automatic_growth_respects_cell_limit_before_flow_allocation(monkeypatch, spec):
    city = blocks()
    options = dict(vertical_grid=spec)
    baseline = wind.preview_grid(city, **options)
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native flow fields"))
    with pytest.raises(ValueError, match=r"zRef 45.*max_cells limit"):
        wind.preview_grid(city, **options, max_cells=baseline.cell_count, turbulence=True)


def test_automatic_growth_respects_layer_limit(monkeypatch):
    city = City()
    building = Building(id="tiny")
    building.measured_height = 15
    building.add_geometry(Surface(vertices=np.array([
        [0,0,0], [0,.012,0], [.012,.012,0], [.012,0,0],
    ])), GeometryType.LOD0)
    city.add_building(building)
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native flow fields"))
    with pytest.raises(ValueError, match=r"zRef 45.*10000-layer limit"):
        wind.preview_grid(city, resolution=.004, horizontal_padding=.012,
                          max_cells=20_000_000, turbulence=True)


def test_automatic_growth_respects_native_index_limit(monkeypatch):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native flow fields"))
    with pytest.raises(ValueError, match=r"zRef 45.*native index limit"):
        wind.preview_grid(blocks(), horizontal_padding=9000, max_cells=2**63-1, turbulence=True)


@pytest.mark.parametrize("layers", [np.full(3,5.), np.full(8,2.),
    np.array([1,1,1,1,2,3,4,5,6.]), np.full(2,8.)])
@pytest.mark.parametrize("offset", [-1,0,1])
def test_python_and_native_reference_margin_agree(layers, offset):
    grid, model, _, _, arrays = inputs(FLAT)
    grid.nz = len(layers)
    faces = effective_faces(layers)
    boundary = faces[-4] if len(layers) > 3 else np.float32(1)
    roughness = np.float32(float(boundary)/100)
    roughness = np.nextafter(roughness, np.float32(-np.inf if offset < 0 else np.inf)) if offset else roughness
    model.roughness_length = float(roughness)
    reference = np.float32(100 * float(roughness))
    expected = len(layers) >= 3 and faces[-4] >= reference and faces[-1] >= 15
    settings = _qes.TurbulenceSettings()
    settings.enabled = True
    if expected:
        _city.check_turbulence_faces(faces, reference)
        _qes.WindRunner().prepare(grid, model, **arrays, dz_layers=layers, turbulence=settings)
    else:
        with pytest.raises(ValueError, match="zRef"):
            _city.check_turbulence_faces(faces, reference)
        with pytest.raises(ValueError, match="zRef"):
            _qes.WindRunner().prepare(grid, model, **arrays, dz_layers=layers, turbulence=settings)


def test_face_check_rejects_collapsed_centres_in_extension():
    with pytest.raises(ValueError, match="cell-centre progress limit"):
        _city.check_turbulence_faces(effective_faces([16777211,1]), 10)


def test_no_buildings_uses_roughness():
    with pytest.raises(ValueError, match=r"zRef 50.*sufficient top of 56 m"):
        wind.preview_grid(City(), bounds=(0,0,0,80,80,40), roughness_length=.5, turbulence=True)


@pytest.mark.parametrize("spec", [None, wind.VerticalGrid.auto(), wind.VerticalGrid.from_faces(np.arange(0,82,2))])
def test_turbulence_false_domain_unchanged(spec):
    city = blocks()
    options = dict(vertical_grid=spec)
    baseline = wind.preview_grid(city, **options)
    actual = wind.preview_grid(city, **options, turbulence=False)
    for name in ("x", "y", "z", "z_faces", "solver_dz"):
        np.testing.assert_array_equal(getattr(actual,name), getattr(baseline,name))
    assert actual.domain == baseline.domain and "turbulence" not in actual.domain


def test_reference_height_matches_native_float32_sorted_accumulation():
    heights = [23.7, 7.9, 11.1234567, .001234, 7.9]
    total = np.float32(0)
    for height in sorted(np.float32(heights)):
        total = np.float32(total+height)
    expected = float(np.float32(3*float(np.float32(total/np.float32(len(heights))))))
    assert _city.turbulence_reference_height(heights,.1) == expected
    assert _city.turbulence_reference_height(heights[::-1],.1) == expected
    assert _city.turbulence_reference_height([], .5) == 50
    assert _city.default_domain_top([15]*4,10,20,2,turbulence_reference=45) == 51


def test_preview_turbulence_rejects_non_boolean_values():
    for value in (None, 1, "height", {}, np.bool_(True)):
        with pytest.raises(ValueError, match="turbulence must be a bool"):
            wind.preview_grid(blocks(), turbulence=value)


def test_translated_ground_keeps_reference_local_and_global_top_correct():
    actual = wind.preview_grid(blocks(base=100), turbulence=True)
    assert_margin(actual,45)
    assert actual.origin[2] == 100
    assert actual.domain["effective_bounds"][-1] == 100+float(actual.z_faces[-1])


@pytest.mark.parametrize("spec", [None, wind.VerticalGrid.auto()])
@pytest.mark.parametrize("method", [0,1])
def test_prepared_domain_and_preview_are_accepted_by_native_runner(spec, method):
    city = blocks((8,))
    options = dict(resolution=.7, vertical_grid=spec)
    preview = wind.preview_grid(city, **options, turbulence=True)
    condition = wind._validate_condition(5,270,10,.1)
    grid = wind._validate_grid(.7,None,20,20,20_000_000,vertical_grid=spec)
    _, prepared = wind._prepare_city(city,condition,grid,None,"measured",turbulence=True)
    assert prepared.domain == preview.domain
    settings = _qes.TurbulenceSettings()
    settings.enabled, settings.mixing_length_method = True, method
    runner = _qes.WindRunner()
    runner.prepare(prepared.grid,prepared.model,**prepared.arrays,dz_layers=prepared.dz_layers,
                   turbulence=settings)
    # Calm solves converge immediately and still exercise native extraction.
    calm = _qes.WindCondition()
    calm.speed = 0
    result = runner.solve(calm,_qes.SolverOptions())
    for name in ("x","y","z","z_faces"):
        np.testing.assert_array_equal(result[name],getattr(preview,name))
    assert result["turbulence"]["reference_height"] == preview.domain["turbulence"]["reference_height"]


def test_mixed_native_building_heights_match_preflight_reference():
    heights = (23.7,7.9,11.1234567,.001234,7.9)
    city = blocks(heights)
    condition = wind._validate_condition(5,270,10,.1)
    grid = wind._validate_grid(2,None,20,20,20_000_000)
    _, prepared = wind._prepare_city(city,condition,grid,None,"measured",turbulence=True)
    settings = _qes.TurbulenceSettings()
    settings.enabled = True
    runner = _qes.WindRunner()
    runner.prepare(prepared.grid,prepared.model,**prepared.arrays,turbulence=settings)
    calm = _qes.WindCondition()
    calm.speed = 0
    actual = runner.solve(calm,_qes.SolverOptions())
    assert actual["turbulence"]["reference_height"] == prepared.domain["turbulence"]["reference_height"]


def test_regeneration_records_changed_prefix_and_preserves_fine_band():
    from dtcc_qes._auto_grid import generate_auto_layers
    city = blocks()
    spec = wind.VerticalGrid.auto(fine_region_height=40)
    with pytest.raises(ValueError, match="fine band does not fit"):
        wind.preview_grid(city,vertical_grid=spec)
    actual = wind.preview_grid(city,vertical_grid=spec,turbulence=True)
    assert_margin(actual,45)
    record = actual.domain["turbulence"]
    assert record["raised"] and not record["lower_layers_preserved"]
    assert record["extension_policy"] == "regenerated_then_constant_last_thickness"
    assert record["regeneration"]["requested_top"] == record["default_top"] == 35
    layers, metadata = generate_auto_layers(spec._automatic,resolution=2,top=71,heights=[15]*4)
    count = metadata["effective_settings"]["fine_layer_count"]
    np.testing.assert_array_equal(actual.solver_dz[:count],layers[:count].astype(np.float32))
    with pytest.raises(ValueError, match="fine band does not fit"):
        wind.preview_grid(city,bounds=(0,0,0,80,80,35),vertical_grid=spec,turbulence=True)


def test_regeneration_retries_an_infeasible_initial_turbulence_endpoint():
    # The wind-only 35 m top cannot fit this band. The initial 51 m turbulence
    # target leaves a 0.1 m sliver, below its valid 0.428 m final thickness.
    preview = wind.preview_grid(blocks(),vertical_grid=wind.VerticalGrid.auto(fine_region_height=50.9),
                                turbulence=True)
    assert_margin(preview,45)
    record = preview.domain["turbulence"]["regeneration"]
    assert record["attempts"] == 2 and record["generated_top"] > 51


@pytest.mark.parametrize("spec", [None, wind.VerticalGrid.auto(),
    wind.VerticalGrid.from_faces(np.r_[np.arange(0,22,2),23,27,32,37,42])])
def test_safe_explicit_domain_is_checked_without_growth(spec):
    options = dict(vertical_grid=spec)
    if spec is None or spec.mode == "auto":
        options["bounds"] = (0,0,0,80,80,60)
    city = blocks((8,))
    before = wind.preview_grid(city,**options)
    after = wind.preview_grid(city,**options,turbulence=True)
    np.testing.assert_array_equal(after.z_faces,before.z_faces)
    np.testing.assert_array_equal(after.solver_dz,before.solver_dz)
    assert after.domain["turbulence"]["extension_policy"] == "check_only"
    assert after.domain["turbulence"]["added_layers"] == 0
    assert not after.domain["turbulence"]["raised"]


def test_extension_uses_native_operand_instead_of_rounded_face_difference():
    # At the end of an accumulated decimal grid, face separation is no longer
    # the solver's 0.3 m operand. Preview's suggested tail must use that operand.
    from dtcc_qes._turbulence_domain import extend_turbulence_faces
    layers = np.full(100,.3)
    before = effective_faces(layers)
    after = extend_turbulence_faces(before,45,np.float32(.3))
    assert before[-1]-before[-2] != np.float32(.3)
    expected = effective_faces(np.full(len(after)-1,.3))
    np.testing.assert_array_equal(after,expected)


def test_regeneration_control_has_archived_sources_and_converged_runs():
    import hashlib
    from pathlib import Path
    study = Path(__file__).resolve().parents[1]/"docs/data/turbulence-domain"
    record = json.loads((study/"control.json").read_text())
    assert record["passed"] and record["fine_band_operands_identical"]
    assert record["preserved_control_prefix_identical"]
    for name,digest in record["source_sha256"].items():
        assert hashlib.sha256((study/"sources"/name).read_bytes()).hexdigest() == digest
    assert all(run["converged"] for run in record["runs"].values())
    for comparison in record["comparisons"]:
        assert comparison["fluid_points"] > 1000
        assert comparison["p95_abs_delta_K"] <= record["targets"]["p95_abs_delta_K"]
        assert comparison["peak_relative_difference"] <= record["targets"]["peak_relative_difference"]

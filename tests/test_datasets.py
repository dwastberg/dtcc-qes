from copy import deepcopy
import json
import subprocess
import sys

import numpy as np
import pytest
from dtcc_core import builder, datasets
from dtcc_core.model import Bounds, Building, City, FieldSlice, GeometryType, Raster, Surface, Transform, VolumeGrid

from dtcc_qes import wind
from dtcc_qes.datasets import QESWindArgs, _field_slice
from dtcc_qes._dataset_city import prepare_city, _source_city


pytestmark = pytest.mark.usefixtures("dtcc_logger")


def building(name, x=10.0, y=10.0, width=6.0, height=6.0, holes=False):
    obj = Building(id=name)
    obj.estimated_height = height
    vertices = np.array([[x, y, 0], [x + width, y, 0],
                         [x + width, y + width, 0], [x, y + width, 0]], dtype=float)
    interior = [np.array([[x+1, y+1, 0], [x+2, y+1, 0],
                          [x+2, y+2, 0], [x+1, y+2, 0]], dtype=float)] if holes else []
    obj.add_geometry(Surface(vertices=vertices, holes=interior), GeometryType.LOD0)
    return obj


@pytest.fixture
def source_city():
    city = City(transform=Transform(srs="EPSG:3006"))
    city.add_building(building("a"))
    return city


@pytest.fixture
def fetched(monkeypatch, source_city):
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return source_city

    monkeypatch.setattr(datasets, "city", fetch)
    return calls


def request(**kwargs):
    return dict(bounds=[0, 0, 30, 24], horizontal_padding=6.0, vertical_clearance=6.0, **kwargs)


def realization(obj):
    return obj.provenance.processing_steps[-1]


def test_package_import_registers_dataset_once():
    subprocess.run([sys.executable, "-c", """
from dtcc_core import datasets
assert 'qes_wind' not in datasets.list()
import dtcc_qes
first = datasets.qes_wind
import dtcc_qes.datasets
assert datasets.get_dataset('qes_wind') is first
import importlib
importlib.reload(dtcc_qes)
assert datasets.get_dataset('qes_wind') is first
assert list(datasets.list()).count('qes_wind') == 1
"""], check=True, capture_output=True, text=True)


def test_discovery_has_native_products_and_no_formats():
    meta = datasets.qes_wind.describe()
    assert meta["data_category"] == "simulation"
    assert meta["supported_formats"] == []
    assert [p["python_return_type"] for p in meta["products"]] == [
        "dtcc_core.model.VolumeGrid", "dtcc_core.model.FieldSlice"]
    json.dumps(datasets.qes_wind.show_options(), allow_nan=False)


def test_field_matches_direct_solver_and_keeps_source(source_city, fetched):
    before = deepcopy(source_city)
    args = QESWindArgs(**request())
    _, bounds, _ = prepare_city(source_city, args)
    expected = wind.run(_source_city(source_city, []), footprints=wind.Footprints(
                        min_detail=args.min_building_detail, fallback="tallest"),
                        **args.wind_options(), bounds=bounds,
                        terrain=bounds[2], height_policy="allow_estimated").to_dtcc()
    actual = datasets.qes_wind(**request())
    assert type(actual) is VolumeGrid
    assert len(fetched) == 1
    assert fetched[0] == dict(bounds=[0, 0, 30, 24], source="LM", smallest_building_size=15.0,
                             lod="lod1", strict_live=False)
    for left, right in zip(actual.fields, expected.fields):
        assert left.association == "cell"
        np.testing.assert_array_equal(left.values, right.values)
    np.testing.assert_array_equal(actual.transform.affine, expected.transform.affine)
    assert actual.transform.srs == "EPSG:3006"
    assert actual.dataset_context.identity.name == "qes_wind"
    assert realization(actual)["diagnostics"]["converged"]
    np.testing.assert_array_equal(source_city.buildings[0].lod0.vertices, before.buildings[0].lod0.vertices)
    assert source_city.buildings[0].attributes == before.buildings[0].attributes
    assert source_city.dataset_context is None
    json.dumps(actual.dataset_context.model_dump(mode="json"), allow_nan=False)


def test_cleaning_preserves_cell_heights_and_records_courtyards(source_city, monkeypatch):
    source_city.add_building(building("b", x=16.2, height=12.0, holes=True))
    clean = builder.clean_footprints
    seen = []

    def tracked(*args, **kwargs):
        result = clean(*args, **kwargs)
        seen.append(result)
        return result

    monkeypatch.setattr(builder, "clean_footprints", tracked)
    prepared, bounds, metadata = prepare_city(source_city, QESWindArgs(**request()))
    assert len(seen) == 1
    assert sorted(c.height for c in prepared.cells) == [6, 12]
    assert {s.source_id for s in prepared.sources} == {"a", "b"}
    assert metadata["schema_version"] == 2
    assert metadata["footprint_cleaning"]["merged_count"] == 1
    assert metadata["footprint_cleaning"]["remove_holes"] is True
    assert metadata["filled_courtyards"] == [{"source_id": "b", "hole_count": 1, "filled_area": 1.0}]
    assert len(source_city.buildings[1].lod0.holes) == 1


def coded_result():
    z, y, x = np.indices((2, 4, 3))
    codes = (100*z + 10*y + x).astype(np.float32)
    velocity = np.stack([codes, codes+1000, codes+2000], axis=-1)
    return wind.WindResult(velocity, np.arange(3)+0.5, np.arange(4)+0.5, np.arange(2)+0.5,
                           codes.astype(np.int32)+3, (300000, 6400000, 50), "EPSG:3006", 1.0,
                           wind.SolveDiagnostics(1, 0, 1e-5, True),
                           {"domain": {"effective_bounds": (300000,6400000,50,300003,6400004,52)}})


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize("position", [0.0, 0.5, 1.0])
def test_slice_sampling_on_unequal_axes(axis, position):
    result = coded_result()
    velocity = result.velocity
    args = QESWindArgs(**request(product="slice", slice_axis=axis, slice_position=position, slice_resolution=5))
    obj = _field_slice(result, args)
    assert type(obj) is FieldSlice
    assert obj.points.shape == (25, 3)
    assert tuple(getattr(obj.domain_bounds, name) for name in
                 ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")) == result.metadata["domain"]["effective_bounds"]
    assert obj.metadata_payload["dataset"] == "qes_wind"
    local = obj.points - np.asarray(result.origin)
    indices = [np.abs(local[:, i, None] - a).argmin(axis=1) for i, a in enumerate((result.x,result.y,result.z))]
    expected = velocity[indices[2],indices[1],indices[0]]
    np.testing.assert_array_equal(obj.field("velocity").values, expected)
    np.testing.assert_array_equal(obj.field("cell_flags").values, expected[:,0]+3)
    assert obj.field("valid").values.all()
    np.testing.assert_allclose(obj.field("speed").values, np.linalg.norm(expected.astype(float), axis=1))
    np.testing.assert_allclose(obj.field("speedup").values, obj.field("speed").values / args.wind_speed)
    assert obj.metadata_payload["speedup_reference"] == {"speed": 5.0, "height": 10.0}
    assert all(f.association == "sample" for f in obj.fields)
    assert not np.shares_memory(obj.field("velocity").values, result.velocity)
    normal = "xyz".index(axis)
    assert len(np.unique(obj.points[:, normal])) == 1
    assert obj.metadata_payload["slice_coordinate"] == obj.points[0, normal]


def test_slice_speedup_is_nan_for_calm_inflow():
    obj = _field_slice(coded_result(), QESWindArgs(**request(product="slice", wind_speed=0.0, slice_resolution=3)))
    assert np.isfinite(obj.field("speed").values).all()
    assert np.isnan(obj.field("speedup").values).all()


def test_dataset_slice_solves_once_and_context_is_per_request(fetched, monkeypatch):
    run = wind._solve_prepared
    calls = []

    def tracked(*args, **kwargs):
        calls.append(1)
        return run(*args, **kwargs)

    monkeypatch.setattr(wind, "_solve_prepared", tracked)
    first = datasets.qes_wind(**request(product="slice", slice_resolution=8))
    saved = first.dataset_context.model_dump(mode="json")
    second = datasets.qes_wind(**request(wind_speed=2.0))
    assert len(calls) == len(fetched) == 2
    assert type(first) is FieldSlice and type(second) is VolumeGrid
    assert first.dataset_context.model_dump(mode="json") == saved
    assert first.dataset_context.metadata.python_return_type == "dtcc_core.model.FieldSlice"
    assert first.field("pressure") is None


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize("height, expected", [(0.0, 1.0), (2.0, 1.0), (3.2, 3.0), (20.0, 19.0)])
def test_slice_height_uses_metres_above_ground_and_overrides_axis(fetched, axis, height, expected):
    obj = datasets.qes_wind(**(request(product="slice", slice_height=height,
                                       slice_axis=axis, slice_position=1.0, slice_resolution=4) |
                              {"bounds": [0, 0, 100, 30, 24, 120]}))
    assert type(obj) is FieldSlice
    assert obj.slice_axis == "z"
    assert obj.axes == (0, 1)
    np.testing.assert_allclose(obj.points[:, 2], 100 + expected)
    assert obj.metadata_payload["slice_height"] == expected
    assert obj.metadata_payload["requested_slice_height"] == height
    assert obj.metadata_payload["slice_coordinate"] == 100 + expected
    assert obj.slice_position == (expected - 1.0) / 18.0
    assert obj.dataset_context.request.parameters["slice_axis"] == "z"
    assert obj.dataset_context.request.parameters["slice_height"] == height


def test_slice_height_above_domain_is_rejected(fetched):
    with pytest.raises(ValueError, match="slice_height must be within the simulation domain"):
        datasets.qes_wind(**(request(product="slice", slice_height=21.0) |
                              {"bounds": [0, 0, 100, 30, 24, 120]}))


@pytest.mark.parametrize("kwargs", [
    {"wind_direction": 360.0}, {"wind_speed": float("nan")}, {"resolution": 0.0},
    {"bounds": [0, 0, float("inf"), 20]}, {"tolerance": 1e-12},
    {"slice_resolution": 1}, {"max_cells": True}, {"min_building_detail": 0.0},
    {"format": "png"}, {"product": "streamlines"},
    {"slice_height": -1.0}, {"slice_height": float("nan")}, {"slice_height": float("inf")},
])
def test_bad_arguments_fail_before_fetch(fetched, kwargs):
    with pytest.raises(ValueError):
        datasets.qes_wind(**(request() | kwargs))
    assert not fetched


def test_bounds_enclose_query_and_buildings_with_padding(source_city):
    source_city.add_building(building("outside", x=40, y=30))
    city, bounds, prep = prepare_city(source_city, QESWindArgs(**request()))
    assert bounds[:3] == (-6, -6, 0)
    assert bounds[3:5] == (52, 42)
    assert prep["horizontal_padding"] == 6


def test_3d_bounds_define_ground_and_top(fetched):
    bounds = Bounds(xmin=0, ymin=0, zmin=100, xmax=30, ymax=24, zmax=120)
    obj = datasets.qes_wind(**(request() | {"bounds": bounds}))
    assert realization(obj)["simulation"]["domain"]["effective_bounds"][2::3] == (100, 120)
    assert realization(obj)["simulation"]["terrain"]["flattening_requested"]


def test_resource_and_roof_limits(fetched, monkeypatch):
    from dtcc_qes import _qes
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Allocated native runner"))
    with pytest.raises(ValueError, match="max_cells"):
        datasets.qes_wind(**request(max_cells=10))
    with pytest.raises(ValueError, match="roof needs clearance"):
        datasets.qes_wind(**(request() | {"bounds": [0, 0, 0, 30, 24, 4]}))


def test_nonconvergence_is_not_hidden(fetched, caplog):
    result = datasets.qes_wind(**request(max_iterations=1))
    assert not result.dataset_context.health["converged"]
    assert result.dataset_context.health["max_divergence"] == realization(result)["diagnostics"]["max_divergence"]
    assert result.dataset_context.warnings
    assert "did not converge" in caplog.text


def test_nonconvergence_can_explicitly_raise(fetched):
    with pytest.raises(wind.ConvergenceError):
        datasets.qes_wind(**request(max_iterations=1, raise_on_nonconvergence=True))


def test_upstream_failure_propagates(monkeypatch):
    def fail(**kwargs):
        raise ConnectionError("provider unavailable")
    monkeypatch.setattr(datasets, "city", fail)
    with pytest.raises(ConnectionError, match="provider unavailable"):
        datasets.qes_wind(**request())


def test_invalid_height_fails_before_cleaning(source_city, monkeypatch):
    source_city.buildings[0].measured_height = -1
    monkeypatch.setattr(builder, "clean_footprints", lambda *a, **k: pytest.fail("Cleaned invalid input"))
    with pytest.raises(ValueError, match="height must be positive"):
        prepare_city(source_city, QESWindArgs(**request()))


def test_terrain_ground_ignores_nodata(source_city):
    source_city.add_terrain(Raster(data=np.array([[-9999., 11.], [10., np.nan]]), nodata=-9999.))
    _, bounds, _ = prepare_city(source_city, QESWindArgs(**request()))
    assert bounds[2] == 10


def test_upstream_context_is_retained_and_partial_city_rejected(source_city, fetched):
    from dtcc_core.datasets.city import CityDataset, CityArgs
    source_city.dataset_context = CityDataset().create_context(CityArgs(bounds=[0, 0, 30, 24]))
    before = source_city.dataset_context.model_dump(mode="json")
    result = datasets.qes_wind(**request(source="OSM", strict_live=True))
    assert fetched[0]["source"] == "OSM" and fetched[0]["strict_live"] is True
    assert result.provenance.derived_from[-1] == before
    assert source_city.dataset_context.model_dump(mode="json") == before
    source_city.dataset_context.health = {"partial_result": True}
    with pytest.raises(ValueError, match="partial result"):
        datasets.qes_wind(**request())


def test_empty_city_with_explicit_elevation(fetched, source_city):
    source_city.remove_buildings()
    result = datasets.qes_wind(**(request() | {"bounds": [0, 0, 10, 30, 24, 30]}))
    assert type(result) is VolumeGrid
    assert realization(result)["preparation"]["footprints"]["counts"]["sources"] == 0
    with pytest.raises(ValueError, match="empty city without terrain"):
        datasets.qes_wind(**request())


def test_cleaning_failure_propagates(source_city, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("Core footprint cleaning failed")
    monkeypatch.setattr(builder, "clean_footprints", fail)
    with pytest.raises(ValueError, match="Core footprint cleaning failed"):
        prepare_city(source_city, QESWindArgs(**request()))


def test_residual_overlap_is_rejected(source_city, monkeypatch):
    source_city.add_building(building("overlap", x=12))
    def unresolved(city, **kwargs):
        city.attributes["footprint_cleaning"] = {}
        return city
    monkeypatch.setattr(builder, "clean_footprints", unresolved)
    with pytest.raises(ValueError, match="footprints share area"):
        prepare_city(source_city, QESWindArgs(**request()))


def test_projected_coordinates_and_translations(source_city):
    source_city.transform.set_translation(300000, 6400000, 20)
    args = QESWindArgs(**(request() | {"bounds": [300000, 6400000, 300030, 6400024]}))
    prepared, bounds, _ = prepare_city(source_city, args)
    assert bounds[:3] == (299994, 6399994, 20)
    np.testing.assert_allclose(
        np.asarray(prepared.sources[0].polygon.exterior.coords).min(axis=0) + prepared.anchor,
        [300010, 6400010])
    assert prepared.sources[0].base_range == (20, 20)
    assert prepared.crs == "EPSG:3006"
    source_city.transform.srs = "EPSG:4326"
    with pytest.raises(ValueError, match="planar"):
        prepare_city(source_city, args)

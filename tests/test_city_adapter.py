import copy

import numpy as np
import pytest
from dtcc_core.model import BuildingPart, City, CityObject, GeometryType, MultiSurface, Terrain
from dtcc_qes import wind
from dtcc_qes._city import extract_city
from dtcc_qes._config import prepare_config

from city_cases import city_case
from fixtures.cases import ONE_BUILDING

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def test_city_maps_to_exact_native_fixture():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    geometry = extract_city(city, "measured")
    prepared = prepare_config(geometry, condition, grid, None)
    source = ONE_BUILDING.buildings[0]
    np.testing.assert_array_equal(prepared.arrays["vertices"], (*source.vertices, source.vertices[0]))
    np.testing.assert_array_equal(prepared.arrays["offsets"], (0, 5))
    assert prepared.grid.nx == 40 and prepared.grid.ny == 30 and prepared.grid.nz == 20
    assert prepared.arrays["heights"].tolist() == [8]
    assert geometry.source_ids == ("0",)


def test_estimates_require_explicit_policy_and_do_not_replace_bad_measurements():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    building = city.buildings[0]
    building.measured_height = None
    building.estimated_height = 8
    with pytest.raises(ValueError, match="Building '0'.*measured_height"):
        wind.run(city, condition, grid=grid)
    result = wind.run(city, condition, grid=grid, height_policy="allow_estimated")
    assert result.metadata["buildings"][0]["height_source"] == "estimated_height"
    building.measured_height = -1
    with pytest.raises(ValueError, match="Building '0'.*measured_height"):
        wind.run(city, condition, grid=grid, height_policy="allow_estimated")


@pytest.mark.parametrize("height", [None, 0, -1, np.nan, np.inf, "8", True])
def test_missing_or_invalid_height_identifies_building(height):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    city.buildings[0].measured_height = height
    with pytest.raises(ValueError, match="Building '0'"):
        wind.run(city, condition, grid=grid)


@pytest.mark.parametrize("mutation", ["missing", "multipart", "holes", "bowtie", "line", "nonfinite", "parts", "ambiguous"])
def test_invalid_footprints_identify_building(mutation):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    building = city.buildings[0]
    surface = building.lod0
    if mutation == "missing":
        building.geometry.clear()
    elif mutation == "multipart":
        building.add_geometry(MultiSurface(surfaces=[surface]), GeometryType.LOD0)
    elif mutation == "holes":
        surface.holes = [np.array([[31, 26, 0], [32, 26, 0], [31, 27, 0]])]
    elif mutation == "bowtie":
        surface.vertices = surface.vertices[[0, 2, 1, 3]]
    elif mutation == "line":
        surface.vertices[:, 1] = 25
    elif mutation == "nonfinite":
        surface.vertices[1, 0] = np.inf
    elif mutation == "parts":
        building.add_child(BuildingPart())
    else:
        building.add_geometry(copy.deepcopy(surface), id="second-footprint", lod="0")
    with pytest.raises(ValueError, match="Building '0'"):
        wind.run(city, condition, grid=grid)


def test_ring_cleanup_and_winding_do_not_mutate_source():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    surface = city.buildings[0].lod0
    surface.vertices = surface.vertices[[0, 0, 3, 2, 1, 0]].copy()
    original = surface.vertices.copy()
    result = wind.run(city, condition, grid=grid)
    np.testing.assert_array_equal(surface.vertices, original)
    assert result.metadata["buildings"][0]["redundant_vertices_removed"] == 1
    geometry = extract_city(city, "measured")
    expected = np.array((*ONE_BUILDING.buildings[0].vertices, ONE_BUILDING.buildings[0].vertices[0]))
    np.testing.assert_array_equal(geometry.rings[0], expected)


@pytest.mark.parametrize("shift", [0, 5, 10])
def test_overlapping_and_touching_buildings_rejected(shift):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    second = copy.deepcopy(city.buildings[0])
    second.id = "other"
    second.lod0.vertices[:, 0] += shift
    city.add_building(second)
    with pytest.raises(ValueError, match="'0'.*'other'.*overlapping or touching"):
        wind.run(city, condition, grid=grid)


def test_two_disjoint_buildings_keep_source_mapping():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    second = copy.deepcopy(city.buildings[0])
    second.id = "source-b"
    second.lod0.vertices[:, 0] += 20
    city.add_building(second)
    result = wind.run(city, condition, grid=grid)
    assert [(b["native_id"], b["source_id"]) for b in result.metadata["buildings"]] == [(0, "0"), (1, "source-b")]


@pytest.mark.parametrize("srs", ["EPSG:4326", "EPSG:2263", "invalid-crs"])
def test_geographic_nonmetre_and_invalid_crs_rejected(srs):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    city.transform.srs = srs
    with pytest.raises(ValueError, match="CRS"):
        wind.run(city, condition, grid=grid)


def test_shared_crs_inheritance_and_conflict():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    city.transform.srs = "EPSG:3006"
    result = wind.run(city, condition, grid=grid)
    assert result.crs == "EPSG:3006"
    city.buildings[0].lod0.transform.srs = "EPSG:3857"
    with pytest.raises(ValueError, match="Building '0'.*CRS"):
        wind.run(city, condition, grid=grid)


@pytest.mark.parametrize("target", ["city", "building", "surface", "all"])
def test_absolute_translations_applied_once(target):
    city, condition, _, solver = city_case(ONE_BUILDING)
    transforms = dict(city=city.transform, building=city.buildings[0].transform,
                      surface=city.buildings[0].lod0.transform)
    shift = (1e9, -2e9, 100)
    for name, transform in transforms.items():
        if target in (name, "all"):
            transform.set_translation(*shift)
    grid = wind.GridSpec(bounds=(*shift, shift[0] + 80, shift[1] + 60, shift[2] + 40))
    result = wind.run(city, condition, grid=grid, solver=solver)
    assert result.origin == shift
    assert result.metadata["buildings"][0]["original_base_range"] == (100, 100)


@pytest.mark.parametrize("mutation", ["rotation", "scale", "shear", "projective", "nonfinite", "conflict"])
def test_unsupported_transforms_rejected(mutation):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    affine = city.buildings[0].lod0.transform.affine
    if mutation == "rotation":
        affine[:2, :2] = [[0, -1], [1, 0]]
    elif mutation == "scale":
        affine[0, 0] = 2
    elif mutation == "shear":
        affine[0, 1] = 0.01
    elif mutation == "projective":
        affine[3, 0] = 1
    elif mutation == "nonfinite":
        affine[0, 3] = np.nan
    else:
        city.transform.set_translation(10, 0, 0)
        affine[0, 3] = 20
    with pytest.raises(ValueError, match="Building '0'"):
        wind.run(city, condition, grid=grid)


def test_terrain_requires_explicit_flattening_and_records_it():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    city.add_terrain(Terrain())
    with pytest.raises(ValueError, match="explicitly accept flattening"):
        wind.run(city, condition, grid=grid)
    result = wind.run(city, condition, grid=grid, terrain="flat")
    assert result.metadata["terrain"]["city_terrain_ignored"]
    assert result.metadata["terrain"]["flattening_requested"]


def test_nonplanar_bases_require_explicit_flattening():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    city.buildings[0].lod0.vertices[1, 2] = 2
    with pytest.raises(ValueError, match="Building '0'.*base elevation"):
        wind.run(city, condition, grid=grid)
    result = wind.run(city, condition, grid=grid, terrain=wind.FlatTerrain(elevation=0))
    assert result.metadata["terrain"]["base_elevations_flattened"]
    assert result.metadata["buildings"][0]["original_base_range"] == (0, 2)


def test_flat_plane_and_explicit_bounds_must_agree():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    with pytest.raises(ValueError, match="zmin"):
        wind.run(city, condition, grid=grid, terrain=wind.FlatTerrain(elevation=10))


def test_bounds_guards_identify_affected_building():
    city, condition, _, _ = city_case(ONE_BUILDING)
    for bounds in [(28, 0, 0, 80, 60, 40), (0, 0, 0, 80, 60, 8)]:
        with pytest.raises(ValueError, match="Building '0'.*clearance"):
            wind.run(city, condition, grid=wind.GridSpec(bounds=bounds))


def test_float32_conversion_cannot_join_previously_separate_footprints():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    second = copy.deepcopy(city.buildings[0])
    second.id = "narrow-gap"
    second.lod0.vertices[:, 0] += 10 + 1e-7
    city.add_building(second)
    with pytest.raises(ValueError, match="'0'.*'narrow-gap'.*after float32 conversion"):
        wind.run(city, condition, grid=grid)


def test_float32_collapsed_edge_identifies_source():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    city.buildings[0].lod0.vertices[1] = city.buildings[0].lod0.vertices[0] + (0, 1e-7, 0)
    with pytest.raises(ValueError, match="Building '0'.*float32 precision"):
        wind.run(city, condition, grid=grid)


def test_different_building_bases_require_flattening():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    second = copy.deepcopy(city.buildings[0])
    second.id = "raised"
    second.lod0.vertices += (20, 0, 5)
    city.add_building(second)
    with pytest.raises(ValueError, match="Building 'raised'.*base elevation"):
        wind.run(city, condition, grid=grid)
    result = wind.run(city, condition, grid=grid, terrain="flat")
    assert result.metadata["terrain"]["base_elevations_flattened"]
    assert result.metadata["buildings"][1]["original_base_range"] == (5, 5)


def test_nested_buildings_are_not_silently_omitted():
    source, condition, grid, _ = city_case(ONE_BUILDING)
    container = CityObject()
    container.add_child(source.buildings[0])
    city = City()
    city.add_child(container)
    with pytest.raises(ValueError, match="Building '0'.*nested"):
        wind.run(city, condition, grid=grid)

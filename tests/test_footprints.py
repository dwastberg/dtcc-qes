"""Geometry preparation against the pinned Core cleaning implementation."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from dtcc_core.model import Building, BuildingPart, City, GeometryType, MultiSurface, Surface
from dtcc_qes import wind
from dtcc_qes import _footprints
from dtcc_qes._footprints import prepare_footprints, merge_roof_cells
from dtcc_qes.footprints import Footprints


def surface(polygon, z=0):
    return Surface(vertices=np.c_[polygon.exterior.coords, np.full(len(polygon.exterior.coords), z)],
        holes=[np.c_[h.coords, np.full(len(h.coords), z)] for h in polygon.interiors])


def building(name, polygon, height, z=0):
    value = Building(id=name)
    value.measured_height = height
    value.add_geometry(surface(polygon, z), GeometryType.LOD0)
    return value


def city(*buildings):
    value = City()
    value.add_buildings(list(buildings))
    return value


def prepare(value, **kwargs):
    return prepare_footprints(value, settings=Footprints(min_detail=.01, **kwargs))


@pytest.mark.parametrize("kwargs", [dict(min_detail=0), dict(min_detail=-1),
    dict(min_detail=np.nan), dict(min_detail=True), dict(min_detail="1"),
    dict(exposed_faces=1), dict(fallback="average"), dict(fallback=[])])
def test_settings_reject_invalid_values(kwargs):
    with pytest.raises(ValueError):
        Footprints(**kwargs)


def test_settings_are_frozen():
    with pytest.raises(FrozenInstanceError):
        Footprints().fallback = "tallest"


def test_measured_height_wins_overlap_and_original_elevations_are_preserved():
    tower = building("tower", box(5, 5, 15, 15), 60, z=100)
    tower.estimated_height = 6
    podium = building("podium", box(0, 0, 20, 20), 10, z=200)
    value = city(tower, podium)
    original = tower.lod0.vertices.copy()
    result = prepare(value)
    tall, low = result.cells
    assert (tall.height, tall.source_ids, tall.polygon.area) == (60, ("tower",), 100)
    assert (low.height, low.polygon.area) == (10, 300)
    assert len(low.polygon.interiors) == 1
    assert low.polygon.interiors[0].is_ccw
    assert not low.polygon.exterior.is_ccw
    assert {s.source_id: s.base_range for s in result.sources} == {
        "tower": (100, 100), "podium": (200, 200)}
    np.testing.assert_array_equal(tower.lod0.vertices, original)
    assert tower.estimated_height == 6 and tower.measured_height == 60


def test_disconnected_multisurface_does_not_fill_gap_and_keeps_holes():
    holed = Polygon(box(0, 0, 10, 10).exterior.coords, [box(2, 2, 8, 8).exterior.coords])
    value = building("multipart", holed, 10)
    value.add_geometry(MultiSurface(surfaces=[surface(holed), surface(box(30, 0, 40, 10))]), GeometryType.LOD0)
    result = prepare(city(value))
    assert len(result.sources) == 1 and len(result.cells) == 2
    assert unary_union([c.polygon for c in result.cells]).equals(unary_union([holed, box(30, 0, 40, 10)]))
    assert result.metadata["counts"]["components"] == 2
    assert all(c.source_ids == ("multipart",) for c in result.cells)


def test_multipart_transform_applied_once_and_hole_elevations_preserved():
    holed = Polygon(box(0, 0, 10, 10).exterior.coords, [box(2, 2, 8, 8).exterior.coords])
    part = surface(holed)
    part.holes[0][:, 2] = 1
    value = building("multipart", holed, 10)
    geometry = MultiSurface(surfaces=[part])
    geometry.transform.set_translation(1e9, -2e9, 100)
    value.add_geometry(geometry, GeometryType.LOD0)
    result = prepare(city(value))
    assert result.anchor == (1e9, -2e9)
    assert result.sources[0].base_range == (100, 101)
    assert result.cells[0].polygon.equals(holed)


def test_multipart_component_order_and_small_areas_are_preserved():
    value = building("multipart", box(0, 0, 10, 10), 10)
    value.add_geometry(MultiSurface(surfaces=[surface(box(0, 0, 10, 10)),
        surface(box(20, 0, 20.08, .08))]), GeometryType.LOD0)
    original = prepare(city(value))
    value.lod0.surfaces.reverse()
    reordered = prepare(city(value))
    assert original.cells == reordered.cells
    assert original.metadata["buildings"] == reordered.metadata["buildings"]
    assert len(original.cells) == 2
    assert sum(c.polygon.area for c in original.cells) == pytest.approx(100.0064)


def test_conflicting_component_transforms_are_rejected():
    value = building("multipart", box(0, 0, 10, 10), 10)
    geometry = MultiSurface(surfaces=[value.lod0])
    geometry.transform.set_translation(10, 0, 0)
    value.transform.set_translation(20, 0, 0)
    value.add_geometry(geometry, GeometryType.LOD0)
    with pytest.raises(ValueError, match="multipart.*conflicting absolute translations"):
        prepare(city(value))


def test_invalid_hole_is_rejected_before_cleaning():
    value = building("bad-hole", box(0, 0, 10, 10), 10)
    value.lod0.holes = [surface(box(20, 20, 25, 25)).vertices]
    with pytest.raises(ValueError, match="bad-hole.*invalid footprint"):
        prepare(city(value))


def test_parts_remain_rejected():
    value = building("parts", box(0, 0, 10, 10), 10)
    value.add_child(BuildingPart())
    with pytest.raises(ValueError, match="parts are unsupported"):
        prepare(city(value))


def test_estimates_require_opt_in():
    value = building("estimate", box(0, 0, 10, 10), None)
    value.estimated_height = 8
    with pytest.raises(ValueError, match="missing measured_height"):
        prepare(city(value))
    result = prepare_footprints(city(value), "allow_estimated")
    assert result.cells[0].height == 8
    assert result.sources[0].height_source == "estimated_height"


def test_source_permutation_and_ring_rotation_produce_same_cells():
    a = building("a", box(0, 0, 20, 20), 10)
    b = building("b", box(5, 5, 15, 15), 20)
    first = prepare(city(a, b))
    a, b = deepcopy(a), deepcopy(b)
    for value in (a, b):
        coords = value.lod0.vertices[:-1]
        value.lod0.vertices = np.roll(coords[::-1], 2, axis=0)
    second = prepare(city(b, a))
    assert first.cells == second.cells
    assert first.metadata["buildings"] == second.metadata["buildings"]


def test_equal_represented_roofs_merge_after_grid_is_known():
    result = prepare(city(building("a", box(0, 0, 10, 10), 10),
                          building("b", box(10, 0, 20, 10), 9.9)))
    assert len(result.cells) == 2
    solids = merge_roof_cells(result, np.arange(0, 21))
    assert len(solids) == 1
    assert solids[0].polygon.equals(box(0, 0, 20, 10))
    assert solids[0].height == solids[0].represented_roof == 10
    assert solids[0].source_ids == ("a", "b")
    finer = merge_roof_cells(result, np.arange(0, 21, .1))
    assert len(finer) == 2


def test_subcell_gap_is_not_silently_merged_by_roof_grouping():
    result = prepare(city(building("a", box(0, 0, 10, 10), 10),
                          building("b", box(10.3, 0, 20.3, 10), 10)))
    assert len(merge_roof_cells(result, np.arange(0, 21))) == 2


def test_fully_covered_source_is_accounted_for():
    result = prepare(city(building("tower", box(0, 0, 20, 20), 20),
                          building("covered", box(5, 5, 15, 15), 10)))
    rows = {row["source_id"]: row for row in result.metadata["buildings"]}
    assert rows["covered"]["status"] == "covered"
    assert rows["covered"]["cells"] == []
    assert rows["tower"]["status"] == "solid"


@pytest.mark.parametrize("heights", [(10, 11), (10, 12), (10, 13)])
def test_tallest_fallback_overrides_upstream_average(monkeypatch, heights):
    def clean(flat, **kwargs):
        block = Building(id="fallback")
        block.attributes["footprint_walls"] = {"outcome": "fallback", "detail": "forced wall failure"}
        result = city(block)
        result.attributes["footprint_cleaning"] = {"excluded": []}
        result.attributes["test_source_ids"] = tuple(b.id for b in flat.buildings)
        return result

    def cells(cleaned):
        return [SimpleNamespace(polygon=box(0, 0, 20, 10), height=sum(heights)/2,
            source_ids=cleaned.attributes["test_source_ids"], part_id=None, building_id="fallback")]

    monkeypatch.setattr(_footprints.builder, "clean_footprints", clean)
    monkeypatch.setattr(_footprints.builder, "building_cells", cells)
    value = city(building("a", box(0, 0, 10, 10), heights[0]),
                 building("b", box(10, 0, 20, 10), heights[1]))
    with pytest.raises(ValueError, match="fallback.*a.*b.*forced wall failure"):
        prepare(value)
    result = prepare(value, fallback="tallest")
    assert result.cells[0].height == max(heights)
    assert result.metadata["fallbacks"][0]["added_volume"] == 100 * abs(heights[1] - heights[0])


@pytest.mark.parametrize("faces", [[0, 1], [1, 2, 3], [0, 1, 1], [0, 1, np.nan], [0, 1, 2]])
def test_invalid_or_insufficient_grid_rejected(faces):
    result = prepare(city(building("a", box(0, 0, 10, 10), 10)))
    with pytest.raises(ValueError):
        merge_roof_cells(result, faces)


def test_empty_city_prepares_without_solids():
    result = prepare(city())
    assert result.sources == result.cells == ()
    assert merge_roof_cells(result, [0, 1, 2]) == ()


def test_strict_wind_path_still_rejects_contact():
    value = city(building("a", box(10, 10, 20, 20), 10),
                 building("b", box(20, 10, 30, 20), 10))
    with pytest.raises(ValueError, match="overlapping or touching"):
        wind.preview_grid(value)


# Finalization receives the physical grid after planning, including any extra
# layers required for turbulence. It does not allocate native flow storage.
def finalize(prepared, **kwargs):
    from dtcc_qes._footprints import finalize_footprints
    defaults = dict(effective_faces=np.arange(0, 41), origin=(-20, -20, 0),
                    shape=(40, 60, 80), resolution=1)
    return finalize_footprints(prepared, **(defaults | kwargs))


def test_split_and_single_block_have_identical_canonical_native_arrays():
    split = finalize(prepare(city(building("a", box(0, 0, 10, 10), 10),
                                  building("b", box(10, 0, 20, 10), 10))))
    single = finalize(prepare(city(building("block", box(0, 0, 20, 10), 10))))
    for name in single.arrays:
        np.testing.assert_array_equal(split.arrays[name], single.arrays[name])
    assert split.metadata["counts"]["merges"] == 1
    assert split.metadata["counts"]["solids"] == 1
    assert all(row["solids"] == [0] for row in split.metadata["buildings"])


def test_t_junction_vertices_are_shared_across_unequal_height_cells():
    value = prepare(city(building("left", box(0, 0, 10, 20), 6),
        building("right-lower", box(10, 0, 20, 10), 10),
        building("right-upper", box(10, 10, 20, 20), 12)))
    result = finalize(value)
    assert len(result.solids) == 3
    for solid in result.solids:
        assert (10., 10.) in list(solid.polygon.exterior.coords)
    assert all(solid.polygon.is_valid for solid in result.solids)


def test_redundant_vertices_hole_order_and_winding_are_canonical():
    from dtcc_qes._footprints import canonical_polygon
    outer = [(0, 0), (0, 0), (5, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
    holes = [list(box(1, 1, 3, 3).exterior.coords), list(box(6, 6, 9, 9).exterior.coords)]
    first = canonical_polygon(Polygon(outer, holes))
    second = canonical_polygon(Polygon(list(reversed(outer)), [list(reversed(h)) for h in holes[::-1]]))
    assert first.wkb == second.wkb
    assert len(first.exterior.coords) == 5


def test_canonical_native_arrays_ignore_component_and_source_order():
    a = building("a", box(0, 0, 10, 10), 10)
    a.add_geometry(MultiSurface(surfaces=[surface(box(0, 0, 10, 10)),
        surface(box(30, 0, 40, 10))]), GeometryType.LOD0)
    b = building("b", box(10, 0, 20, 10), 10)
    first = finalize(prepare(city(a, b)))
    a.lod0.surfaces.reverse()
    for part in a.lod0.surfaces:
        part.vertices = np.roll(part.vertices[:-1][::-1], 1, axis=0)
    second = finalize(prepare(city(b, a)))
    for name in first.arrays:
        np.testing.assert_array_equal(first.arrays[name], second.arrays[name])
    assert first.metadata["buildings"] == second.metadata["buildings"]


def test_holes_are_preserved_in_native_ring_arrays():
    value = prepare(city(building("podium", box(0, 0, 20, 20), 10),
                          building("tower", box(5, 5, 15, 15), 20)))
    assert sum(c.polygon.area for c in value.cells) == 400
    result = finalize(value)
    assert len(result.arrays["ring_offsets"]) == 4
    assert len(result.solids) == 2
    assert sum(c.polygon.area for c in result.solids) == 400
    # A hole removed by a legitimate same-roof union needs no native ring support.
    same_roof = prepare(city(building("podium", box(0, 0, 20, 20), 10),
                            building("tower", box(5, 5, 15, 15), 10)))
    assert len(finalize(same_roof).solids) == 1


def test_nonuniform_effective_faces_and_centre_tie_match_native_roof_rule():
    value = prepare(city(building("a", box(0, 0, 10, 10), 10),
                          building("b", box(10, 0, 20, 10), 9.9)))
    # Centre at 10: exact ties are occupied; 9.9 is below the centre.
    faces = np.array([0., 4., 8., 12., 20.])
    result = finalize(value, effective_faces=faces, shape=(4, 60, 80))
    assert sorted(s.represented_roof for s in result.solids) == [8, 12]
    assert result.metadata["grid"]["effective_faces"] == faces.tolist()
    # Extending the final grid does not alter lower roof grouping.
    extended = finalize(value, effective_faces=[*faces, 30, 40], shape=(6, 60, 80))
    np.testing.assert_array_equal(result.arrays["vertices"], extended.arrays["vertices"])
    np.testing.assert_array_equal(result.arrays["heights"], extended.arrays["heights"])


def test_finalization_checks_original_bases_even_for_covered_sources():
    value = prepare(city(building("tower", box(0, 0, 20, 20), 20),
                          building("covered", box(5, 5, 15, 15), 10, z=5)))
    with pytest.raises(ValueError, match="covered.*incompatible base elevation"):
        finalize(value)
    assert len(finalize(value, terrain="flat").solids) == 1
    assert len(finalize(value, terrain=0).solids) == 1
    with pytest.raises(ValueError, match="origin z"):
        finalize(value, terrain=5)


def test_finalization_requires_explicit_terrain_flattening():
    from dtcc_core.model import Terrain
    value = city(building("a", box(0, 0, 10, 10), 10))
    value.add_terrain(Terrain())
    prepared = prepare(value)
    with pytest.raises(ValueError, match="City has terrain"):
        finalize(prepared)
    assert len(finalize(prepared, terrain="flat").solids) == 1


def test_finalization_preserves_global_anchor_with_large_translation():
    value = city(building("a", box(0, 0, 10, 10), 10))
    plain = finalize(prepare(value))
    value.transform.set_translation(1e9, -2e9, 100)
    translated = finalize(prepare(value), origin=(1e9-20, -2e9-20, 100))
    for name in plain.arrays:
        np.testing.assert_array_equal(plain.arrays[name], translated.arrays[name])


@pytest.mark.parametrize("kwargs, message", [
    (dict(origin=(-1, -20, 0)), "two cells of clearance"),
    (dict(origin=(np.nan, 0, 0)), "origin must be finite"),
    (dict(shape=(40, 2, 80)), "shape must contain"),
    (dict(shape=(39, 60, 80)), "physical z dimension"),
    (dict(max_cells=10), "max_cells"),
    (dict(resolution=0), "resolution must be positive"),
    (dict(resolution=1e-30), "solver coefficients"),
    (dict(resolution=1e30), "solver coefficients"),
])
def test_finalization_rejects_invalid_domain(kwargs, message):
    value = prepare(city(building("a", box(0, 0, 10, 10), 10)))
    with pytest.raises(ValueError, match=message):
        finalize(value, **kwargs)


def test_float32_collapsed_edge_is_rejected_after_cleaning():
    from dataclasses import replace
    value = prepare(city(building("a", box(0, 0, 10, 10), 10)))
    # A valid sliver whose edge disappears when converted to native coordinates.
    polygon = Polygon([(0, 0), (0, 10), (1e-8, 10-1e-8), (10, 0)])
    value = replace(value, cells=(replace(value.cells[0], polygon=polygon),))
    with pytest.raises(ValueError, match="float32 precision"):
        finalize(value)


def test_float32_gap_closure_is_allowed_without_shared_area():
    from dataclasses import replace
    value = prepare(city(building("a", box(0, 0, 10, 10), 10),
                          building("b", box(11, 0, 20, 10), 20)))
    cells = tuple(replace(c, polygon=box(10+1e-7, 0, 20, 10)) if c.height == 20 else c
                  for c in value.cells)
    result = finalize(replace(value, cells=cells))
    assert len(result.solids) == 2


def test_native_bridge_accepts_finalized_arrays():
    from dtcc_qes import _qes
    value = finalize(prepare(city(building("a", box(0, 0, 10, 10), 10),
                                 building("b", box(10, 0, 20, 10), 9.9))))
    grid = _qes.GridConfig()
    grid.nx, grid.ny, grid.nz, grid.cell_size = 80, 60, 40, 1
    runner = _qes.WindRunner()
    runner.prepare(grid, _qes.ModelSettings(), **value.arrays)
    condition, options = _qes.WindCondition(), _qes.SolverOptions()
    options.max_iterations = 1
    result = runner.solve(condition, options)
    assert result["building_count"] == 1
    assert np.isfinite(result["velocity"]).all()


def test_cleaning_failure_names_original_sources_and_keeps_diagnostics(monkeypatch):
    from dtcc_core.builder.cleaning.footprints import UnresolvedFootprintCleaningError
    def fail(*args, **kwargs):
        raise UnresolvedFootprintCleaningError({"unresolved_groups": [
            {"group": 0, "source_indices": [0, 1], "reason": "work_limit", "attempts": 7}]})
    monkeypatch.setattr(_footprints.builder, "clean_footprints", fail)
    value = city(building("source-a", box(0, 0, 10, 10), 10),
                 building("source-b", box(10, 0, 20, 10), 20))
    with pytest.raises(ValueError, match="source-a.*source-b") as caught:
        prepare(value)
    assert "work_limit" in str(caught.value) and "attempts" in str(caught.value)
    assert isinstance(caught.value.__cause__, UnresolvedFootprintCleaningError)


def test_partial_exclusion_covered_and_excluded_sources_are_all_accounted_for(monkeypatch):
    def clean(flat, **kwargs):
        result = city(deepcopy(flat.buildings[0]))
        result.attributes["footprint_cleaning"] = {"excluded": [
            {"ids": [flat.buildings[1].id], "reason": "no_protected_core"},
            {"ids": [flat.buildings[3].id], "reason": "no_protected_core"}]}
        return result
    monkeypatch.setattr(_footprints.builder, "clean_footprints", clean)
    a = building("a", box(0, 0, 10, 10), 10)
    a.add_geometry(MultiSurface(surfaces=[a.lod0, surface(box(20, 0, 20.005, .005))]), GeometryType.LOD0)
    value = prepare(city(a, building("b", box(2, 2, 5, 5), 5),
                         building("c", box(30, 0, 30.005, .005), 10)))
    rows = {r["source_id"]: r for r in value.metadata["buildings"]}
    assert rows["a"]["status"] == "solid"
    assert sorted(rows["a"]["components"].values()) == ["excluded", "solid"]
    assert rows["b"]["status"] == "covered"
    assert rows["c"]["status"] == "excluded"
    assert rows["c"]["reason"] == "no_protected_core"
    final = finalize(value)
    assert final.metadata["buildings"][0]["solids"] == [0]
    assert final.metadata["buildings"][1]["solids"] == []
    assert final.metadata["counts"]["covered"] == final.metadata["counts"]["excluded"] == 1
    import json
    json.dumps(final.metadata, allow_nan=False)
    final.metadata["buildings"][0]["components"].clear()
    assert value.metadata["buildings"][0]["components"]


def test_fallback_volume_counts_overlaps_once_and_blocks_once(monkeypatch):
    def clean(flat, **kwargs):
        block = Building(id="fallback")
        block.attributes["footprint_walls"] = {"outcome": "fallback", "detail": {"reason": "forced"}}
        result = city(block)
        result.attributes["footprint_cleaning"] = {"excluded": []}
        result.attributes["components"] = tuple(b.id for b in flat.buildings)
        return result
    def cells(cleaned):
        return [SimpleNamespace(polygon=p, height=15., source_ids=cleaned.attributes["components"],
            part_id=None, building_id="fallback") for p in [box(0, 0, 10, 10), box(10, 0, 20, 10)]]
    monkeypatch.setattr(_footprints.builder, "clean_footprints", clean)
    monkeypatch.setattr(_footprints.builder, "building_cells", cells)
    value = prepare(city(building("low", box(0, 0, 20, 10), 10),
                         building("tall", box(10, 0, 20, 10), 20)), fallback="tallest")
    assert value.metadata["counts"]["fallbacks"] == 1
    record, = value.metadata["fallbacks"]
    assert record["reference_volume_within_output"] == 3000
    assert record["output_volume"] == 4000
    assert record["added_volume"] == 1000


def test_multipart_ambiguous_geometry_names_original_building():
    value = building("ambiguous-source", box(0, 0, 10, 10), 10)
    value.add_geometry(surface(box(20, 0, 30, 10)), id="other", lod="0")
    with pytest.raises(ValueError, match="ambiguous-source.*Ambiguous geometry"):
        prepare(city(value))


def test_original_coordinate_system_is_preserved_and_conflicts_rejected():
    value = city(building("a", box(0, 0, 10, 10), 10))
    value.transform.srs = "EPSG:3006"
    assert prepare(value).crs == "EPSG:3006"
    value.buildings[0].lod0.transform.srs = "EPSG:3857"
    with pytest.raises(ValueError, match="a.*CRS differs"):
        prepare(value)


@pytest.mark.parametrize("grid", [None, wind.VerticalGrid.from_faces(np.arange(0, 51, .5)),
                                   wind.VerticalGrid.auto()])
def test_finalization_uses_effective_grid_from_existing_planner(grid):
    envelope = city(building("envelope", box(0, 0, 20, 10), 10))
    preview = wind.preview_grid(envelope, resolution=1, vertical_clearance=20,
                                vertical_grid=grid, turbulence=True)
    prepared = prepare(city(building("a", box(0, 0, 10, 10), 10),
                            building("b", box(10, 0, 20, 10), 9.9)))
    result = finalize(prepared, effective_faces=preview.z_faces, shape=preview.shape,
                      origin=preview.origin, resolution=preview.resolution)
    assert result.metadata["grid"]["shape"] == list(preview.shape)
    assert result.metadata["grid"]["effective_faces"] == preview.z_faces.astype(float).tolist()
    assert result.solids


def test_float32_narrowing_must_not_introduce_shared_area():
    from dataclasses import replace
    a = Polygon([(3, 3), (3, 7), (5.004, 7), (5, 3)])
    b = Polygon([(5.00100001, 4), (5.00300001, 6), (8, 6), (8, 4)])
    assert a.intersection(b).area == 0
    value = prepare(city(building("a", box(0, 0, 10, 10), 10),
                          building("b", box(11, 0, 20, 10), 20)))
    cells = tuple(replace(c, polygon=a if c.height == 10 else b)
                  for c in value.cells)
    with pytest.raises(ValueError, match="share area"):
        finalize(replace(value, cells=cells), origin=(0, 0, 0))


def test_empty_city_finalizes_to_empty_native_arrays():
    result = finalize(prepare(city()))
    assert result.solids == ()
    assert result.arrays["vertices"].shape == (0, 2)
    assert result.arrays["offsets"].tolist() == [0]
    assert result.metadata["counts"]["solids"] == 0
    assert result.arrays["vertices"].dtype == np.float64

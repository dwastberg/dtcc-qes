"""Dataset-specific policies on the shared canonical-solid preparation path."""

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
from shapely import contains_xy
from shapely.geometry import Polygon, box

from dtcc_core import builder, datasets
from dtcc_core.model import GeometryType, MultiSurface
from dtcc_qes import _city, wind
from dtcc_qes._dataset_city import prepare_city
from dtcc_qes.datasets import QESWindArgs
import test_datasets as dataset_fixtures
from test_datasets import request, realization
from test_footprints import building, surface

# Reuse the fetched-city fixtures without registering the other module's tests.
source_city = dataset_fixtures.source_city
fetched = dataset_fixtures.fetched

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def test_dataset_cleans_once_during_auto_grid_stabilization(source_city, fetched, monkeypatch):
    source_city.replace_buildings(
        [
            building("a", box(10, 10, 16, 16), 10),
            building("b", box(16, 10, 22, 16), 9.9),
        ]
    )
    clean, plan, solve = (
        builder.clean_footprints,
        _city.prepare_domain,
        wind._solve_prepared,
    )
    calls = dict(clean=0, plan=0, solve=0)

    def tracked_clean(*args, **kwargs):
        calls["clean"] += 1
        assert kwargs["remove_holes"] is True and kwargs["strict"] is False
        return clean(*args, **kwargs)

    def tracked_plan(*args, **kwargs):
        calls["plan"] += 1
        return plan(*args, **kwargs)

    def tracked_solve(*args, **kwargs):
        calls["solve"] += 1
        return solve(*args, **kwargs)

    monkeypatch.setattr(builder, "clean_footprints", tracked_clean)
    monkeypatch.setattr(_city, "prepare_domain", tracked_plan)
    monkeypatch.setattr(wind, "_solve_prepared", tracked_solve)
    obj = datasets.qes_wind(
        **request(product="slice", vertical_grid="auto", slice_resolution=4, max_iterations=2)
    )
    assert calls["clean"] == calls["solve"] == 1
    assert calls["plan"] >= 2
    assert realization(obj)["preparation"]["footprints"]["counts"]["solids"] == 1


def test_tower_partition_hole_and_height_policy_survive_dataset_filling(source_city, fetched, monkeypatch):
    podium = building(
        "podium",
        Polygon(box(10, 10, 30, 30).exterior.coords, [box(14, 14, 26, 26).exterior.coords]),
        6,
        z=100,
    )
    tower = building("tower", box(14, 14, 26, 26), 12, z=10)
    covered = building("covered", box(18, 18, 20, 20), 2, z=500)
    podium.estimated_height = 60
    tower.estimated_height = 3
    source_city.replace_buildings([podium, tower, covered])
    before = deepcopy(source_city)
    solve = wind._solve_prepared
    retained = []

    def tracked(*args, **kwargs):
        result = solve(*args, **kwargs)
        retained.append(result)
        return result

    monkeypatch.setattr(wind, "_solve_prepared", tracked)
    obj = datasets.qes_wind(**request(max_iterations=3))
    (result,) = retained
    records = {r["source_id"]: r for r in result.metadata["buildings"]}
    assert records["covered"]["status"] == "covered"
    assert records["podium"]["height"] == 6 and records["tower"]["height"] == 12
    assert records["podium"]["height_source"] == "measured_height"
    assert records["podium"]["original_base_range"] == (100, 100)
    assert result.origin[2] == 10
    assert sorted((r["height"], r["area"]) for r in result.metadata["solids"]) == [
        (6, 256),
        (12, 144),
    ]
    x, y = np.meshgrid(result.x + result.origin[0], result.y + result.origin[1])
    outer, inner = (
        contains_xy(box(10, 10, 30, 30), x, y),
        contains_xy(box(14, 14, 26, 26), x, y),
    )
    expected = (outer[None] & (result.z[:, None, None] <= 6)) | (
        inner[None] & (result.z[:, None, None] <= 12)
    )
    np.testing.assert_array_equal(result.solid_mask, expected)
    prep = realization(obj)["preparation"]
    assert prep["schema_version"] == 2 and prep["pipeline"] == "canonical-cells-v1"
    assert prep["source_courtyard_filled_area"] == 144
    assert prep["dtcc_core"]["revision"] == "80a4bbae2760e891e2a0be4175d67bf3340a8e67"
    assert "blocks" not in prep and "block_height_policy" not in prep
    direct_city = deepcopy(source_city)
    for value in direct_city.buildings:
        value.lod0.holes = []
    args = QESWindArgs(**request(max_iterations=3))
    direct = wind.run(
        direct_city,
        **args.wind_options(),
        bounds=prep["bounds"],
        terrain=result.origin[2],
        height_policy="allow_estimated",
        footprints=wind.Footprints(min_detail=args.min_building_detail, fallback="tallest"),
    )
    np.testing.assert_array_equal(result.velocity, direct.velocity)
    np.testing.assert_array_equal(result.cell_flags, direct.cell_flags)
    assert len(source_city.buildings[0].lod0.holes) == len(before.buildings[0].lod0.holes) == 1
    np.testing.assert_array_equal(podium.lod0.vertices, before.buildings[0].lod0.vertices)


def test_courtyard_formed_by_a_ring_of_sources_is_filled(source_city, fetched):
    polygons = [
        box(10, 10, 14, 30),
        box(26, 10, 30, 30),
        box(14, 10, 26, 14),
        box(14, 26, 26, 30),
    ]
    source_city.replace_buildings([building(str(i), p, 6) for i, p in enumerate(polygons)])
    obj = datasets.qes_wind(**request(max_iterations=2))
    prep = realization(obj)["preparation"]
    assert prep["source_courtyard_filled_area"] == 0
    assert prep["courtyard_policy"]["input_union_void_area"] == 144
    assert prep["courtyard_policy"]["cleaned_occupied_area"] == pytest.approx(400)
    assert prep["footprints"]["counts"]["solids"] == 1
    assert prep["footprints"]["solids"][0]["area"] == pytest.approx(400)
    assert prep["courtyard_policy"]["conditioned_region_filled_area"] is None


def test_disconnected_multipart_source_keeps_components(source_city, fetched):
    value = building("multipart", box(10, 10, 16, 16), 6)
    value.add_geometry(
        MultiSurface(surfaces=[value.lod0, surface(box(24, 10, 30, 16))]),
        GeometryType.LOD0,
    )
    source_city.replace_buildings([value])
    obj = datasets.qes_wind(**request(max_iterations=2))
    meta = realization(obj)["preparation"]["footprints"]
    assert (
        meta["counts"]["sources"] == 1 and meta["counts"]["components"] == 2 and meta["counts"]["solids"] == 2
    )
    assert meta["buildings"][0]["solids"] == [0, 1]
    assert sum(row["area"] for row in meta["solids"]) == 72


def test_cleaned_extents_determine_padding_when_detail_exceeds_spacing(source_city, monkeypatch):
    source_city.replace_buildings([building("a", box(10, 10, 16, 16), 6)])
    clean = builder.clean_footprints

    def shifted(flat, **kwargs):
        # A controlled valid single-source displacement within delta/2.
        flat.buildings[0].lod0.vertices[:, 0] -= 0.4
        return clean(flat, **kwargs)

    monkeypatch.setattr(builder, "clean_footprints", shifted)
    args = QESWindArgs(
        **(
            request(resolution=0.1, min_building_detail=1.0, max_cells=10_000_000)
            | {"bounds": [10.0, 10.0, 16.0, 16.0], "horizontal_padding": 0.0}
        )
    )
    prepared, bounds, provenance = prepare_city(source_city, args)
    assert provenance["horizontal_padding"] == pytest.approx(0.3)
    assert bounds[0] == pytest.approx(9.3)
    assert bounds[3] == pytest.approx(16.3)  # Query rectangle remains enclosed too.
    from dtcc_qes._footprints import plan_footprint_domain

    geometry, domain = plan_footprint_domain(
        prepared,
        reference_height=args.reference_height,
        roughness_length=args.roughness_length,
        **wind._validate_grid(args.resolution, bounds, 0, args.vertical_clearance, args.max_cells),
        terrain=bounds[2],
    )
    assert domain.footprints.metadata["counts"]["solids"] == 1


def test_tallest_fallback_is_reported_in_health_warning_and_volume(source_city, fetched, monkeypatch):
    source_city.replace_buildings(
        [building("a", box(10, 10, 16, 16), 6), building("b", box(16, 10, 22, 16), 12)]
    )

    def forced(flat, **kwargs):
        from dtcc_core.model import Building, City

        block = Building(id="fallback")
        block.attributes["footprint_walls"] = {
            "outcome": "fallback",
            "detail": {"reason": "forced"},
        }
        result = City()
        result.add_building(block)
        result.attributes["footprint_cleaning"] = {"excluded": []}
        result.attributes["component_ids"] = tuple(b.id for b in flat.buildings)
        return result

    def cells(cleaned):
        return [
            SimpleNamespace(
                polygon=box(0, 0, 12, 6),
                height=9.0,
                building_id="fallback",
                part_id=None,
                source_ids=cleaned.attributes["component_ids"],
            )
        ]

    monkeypatch.setattr(builder, "clean_footprints", forced)
    monkeypatch.setattr(builder, "building_cells", cells)
    obj = datasets.qes_wind(**request(max_iterations=2))
    assert obj.dataset_context.health["footprint_fallbacks"] == 1
    assert any("tallest-height" in message for message in obj.dataset_context.warnings)
    meta = realization(obj)["preparation"]["footprints"]
    (record,) = meta["fallbacks"]
    assert record["height"] == 12 and record["added_volume"] == 216
    assert meta["settings"] == dict(min_detail=0.5, exposed_faces=True, fallback="tallest")


def test_unresolved_cleaning_still_raises_under_tallest_policy(source_city, fetched, monkeypatch):
    from dtcc_core.builder.cleaning.footprints import UnresolvedFootprintCleaningError

    def fail(*args, **kwargs):
        raise UnresolvedFootprintCleaningError(
            {"unresolved_groups": [dict(group=0, source_indices=[0], reason="work_limit")]}
        )

    monkeypatch.setattr(builder, "clean_footprints", fail)
    with pytest.raises(ValueError, match="work_limit.*source_ids.*a"):
        datasets.qes_wind(**request())


def test_invalid_source_holes_are_not_silently_filled(source_city):
    source_city.buildings[0].lod0.holes = [surface(box(40, 40, 45, 45)).vertices]
    with pytest.raises(ValueError, match="a.*invalid footprint"):
        prepare_city(source_city, QESWindArgs(**request()))


def test_partial_exclusions_and_covered_sources_reach_dataset_health(source_city, fetched, monkeypatch):
    a = building("a", box(10, 10, 16, 16), 6)
    a.add_geometry(
        MultiSurface(surfaces=[a.lod0, surface(box(20, 10, 20.05, 10.05))]),
        GeometryType.LOD0,
    )
    source_city.replace_buildings(
        [
            a,
            building("b", box(11, 11, 13, 13), 3),
            building("c", box(24, 10, 24.05, 10.05), 6),
        ]
    )

    def selected(flat, **kwargs):
        from dtcc_core.model import City

        result = City()
        result.add_building(deepcopy(flat.buildings[0]))
        result.attributes["footprint_cleaning"] = {
            "excluded": [
                {"ids": [flat.buildings[1].id], "reason": "no_protected_core"},
                {"ids": [flat.buildings[3].id], "reason": "no_protected_core"},
            ]
        }
        return result

    monkeypatch.setattr(builder, "clean_footprints", selected)
    obj = datasets.qes_wind(**request(max_iterations=2))
    assert obj.dataset_context.health["excluded_sources"] == 1
    assert obj.dataset_context.health["excluded_components"] == 2
    records = {r["source_id"]: r for r in realization(obj)["preparation"]["footprints"]["buildings"]}
    assert records["a"]["status"] == "solid" and records["a"]["excluded_components"]
    assert records["b"]["status"] == "covered"
    assert records["c"]["status"] == "excluded"


def test_source_hole_elevations_survive_filling_and_define_ground(source_city):
    value = building(
        "a",
        Polygon(box(10, 10, 20, 20).exterior.coords, [box(12, 12, 14, 14).exterior.coords]),
        6,
        z=10,
    )
    value.lod0.holes[0][:, 2] = 1
    source_city.replace_buildings([value])
    prepared, bounds, provenance = prepare_city(source_city, QESWindArgs(**request()))
    assert bounds[2] == 1
    assert prepared.sources[0].base_range == (1, 10)
    assert prepared.sources[0].polygon.area == 100
    assert provenance["source_courtyard_filled_area"] == 4
    assert value.lod0.holes[0][0, 2] == 1


@pytest.mark.parametrize("location", ["building", "container", "part", "deep"])
def test_dataset_rejects_nested_buildings_before_cleaning(source_city, monkeypatch, location):
    from dtcc_core.model import BuildingPart, CityObject

    if location == "building":
        source_city.buildings[0].add_child(building("nested", box(12, 12, 14, 14), 3))
    else:
        child = BuildingPart(id="nested") if location == "part" else CityObject()
        if location in ("container", "deep"):
            child.add_child(building("nested", box(12, 12, 14, 14), 3))
        if location == "deep":
            source_city.buildings[0].add_child(child)
        else:
            source_city.add_child(child)
    monkeypatch.setattr(
        builder, "clean_footprints", lambda *a, **k: pytest.fail("Cleaned unsupported children")
    )
    with pytest.raises(ValueError, match="unsupported"):
        prepare_city(source_city, QESWindArgs(**request()))


@pytest.mark.parametrize("grid", ["uniform", "auto"])
def test_stepped_dataset_combines_profiles_controls_and_final_grid(source_city, fetched, grid):
    from dataclasses import asdict
    from dtcc_qes.datasets import _field_slice

    source_city.replace_buildings(
        [
            building("podium", box(10, 10, 30, 30), 6),
            building("tower", box(14, 14, 26, 26), 12),
        ]
    )
    profile = wind.UniformProfile(5, 270, reference_height=30)
    control = wind.SolverControl(10, wind.MonitorSpec((0, 40, 0, 40)), checkpoint_interval=1)
    args = QESWindArgs(
        **request(
            product="slice",
            slice_resolution=4,
            vertical_grid=grid,
            profile=profile.to_dict(),
            solver_control=asdict(control),
            max_iterations=3,
        )
    )
    actual = datasets.qes_wind(**args.model_dump())
    prep = realization(actual)["preparation"]
    direct = wind.run(
        source_city,
        **args.wind_options(),
        bounds=prep["bounds"],
        terrain=0,
        footprints=wind.Footprints(min_detail=args.min_building_detail, fallback="tallest"),
    )
    preview = wind.preview_grid(
        source_city,
        profile=profile,
        resolution=args.resolution,
        max_cells=args.max_cells,
        bounds=prep["bounds"],
        terrain=0,
        vertical_grid=args.vertical_grid_spec(),
        footprints=wind.Footprints(min_detail=args.min_building_detail, fallback="tallest"),
    )
    assert preview.domain == direct.metadata["domain"]
    assert prep["bounds"][5] >= 30
    assert prep["footprints"]["counts"]["solids"] == 2
    assert realization(actual)["simulation"]["profile"] == direct.metadata["profile"]
    assert actual.dataset_context.health["solver_control"]["iterations"] == 3
    expected = _field_slice(direct, args)
    for name in ("velocity", "speed", "speedup", "cell_flags", "valid"):
        np.testing.assert_array_equal(actual.field(name).values, expected.field(name).values)

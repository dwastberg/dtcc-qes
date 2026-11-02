"""Checks on the AIJ Case D and E City models.

    uv run --group validate pytest validation/tests -q
"""

import numpy as np
import pytest
import shapely
from dtcc_core.io import load_city
from dtcc_qes import wind
from shapely.geometry import Point

from aij import case_d, case_e, cityutil, prisms, tables


@pytest.fixture(scope="module")
def d():
    return case_d.build_case_d()


@pytest.fixture(scope="module", params=["before", "after"])
def e(request):
    return case_e.build_case_e(request.param)


@pytest.fixture(scope="module", params=["before", "after"])
def e_qes(request):
    return request.param, case_e.build_case_e(request.param), case_e.build_case_e_qes(request.param)


def by_id(city):
    return {id_: (polygon, height) for id_, polygon, height in cityutil.footprints(city)}


def test_points():
    points_d, points_e = tables.load_points_d(), tables.load_points_e()
    assert list(points_d.ids) == list(range(1, 79))
    assert list(points_e.ids) == list(range(1, 81))
    np.testing.assert_allclose(points_d.xyz[0], [-137.5 * 0.4, 62.5 * 0.4, 2.0])
    np.testing.assert_allclose(points_e.xyz[0], [-27.0, 112.0, 2.0])


def test_case_d(d):
    buildings = by_id(d.city)
    assert len(buildings) == 83
    tower, height = buildings.pop("D-tower")
    assert height == 100.0 and tower.bounds == (-12.5, -12.5, 12.5, 12.5)
    assert all(h == 10.0 and abs(p.area - 1600.0) < 1e-9 for p, h in buildings.values())
    summary = cityutil.summary(d.city)
    assert summary["touching_pairs"] == summary["overlapping_pairs"] == 0
    assert summary["volume"] == pytest.approx(82 * 16000 + 62500) == d.report["face_volume"]
    assert d.city.attributes["measurement_height"] == 2.0
    assert cityutil.qes_check(d.city)["ok"]


@pytest.mark.parametrize("build, load_points", [
    (lambda: case_d.build_case_d(), tables.load_points_d),
    (lambda: case_e.build_case_e("after"), tables.load_points_e),
    (lambda: case_e.build_case_e_qes("after"), tables.load_points_e),
])
def test_points_outside_buildings(build, load_points):
    union = shapely.union_all([p for _, p, _ in cityutil.footprints(build().city)])
    assert not any(union.contains(Point(x, y)) for x, y, _ in load_points().xyz)


def test_case_e_exact(e):
    state, report, city = e.report["state"], e.report, e.city
    buildings = by_id(city)
    assert len(buildings) == (533 if state == "before" else 536)
    assert report["overlay"]["parts_out"] == report["parts"] and report["overlay"]["dropped"] == 0
    new = {k: h for k, (_, h) in buildings.items() if k.startswith("E-new")}
    assert new == ({} if state == "before" else {"E-new-tower": 60.0, "E-new-low-1": 18.0, "E-new-low-2": 18.0})
    summary = cityutil.summary(city)
    # Parts are disjoint (exact overlay, no snapping) and cover the DXF base faces exactly.
    assert summary["overlapping_pairs"] == 0 and summary["touching_pairs"] > 0
    assert summary["max_overlap_area"] < 1e-9
    assert summary["footprint_area"] == pytest.approx(report["base_union_area"], abs=1e-2)
    # Raw top faces minus the overlap removed by the overlay give the City volume.
    expected = report["face_volume"] - report["overlay"]["removed_volume"]
    assert summary["volume"] == pytest.approx(expected, rel=1e-4)
    assert summary["holes"] == 0


def test_case_e_elevated(e):
    elevated = cityutil.elevated_footprints(e.city)
    kinds = [o.attributes["kind"] for o in cityutil.city_objects(e.city)]
    assert {k: kinds.count(k) for k in set(kinds)} == {"arcade": 21, "canopy": 8, "pilotis": 3}
    ranges = {(o.attributes["kind"], o.attributes["zmin"], o.attributes["zmax"])
              for o in cityutil.city_objects(e.city)}
    assert ranges == {("arcade", 2.4, 2.9), ("canopy", 3.0, 3.5), ("pilotis", 4.0, 4.5), ("pilotis", 4.0, 6.0)}
    union = shapely.union_all([p for _, p, _ in cityutil.footprints(e.city)])
    # Elevated objects stand over open ground, not on buildings.
    assert sum(union.intersection(p).area for _, p, *_ in elevated) < 0.02 * sum(p.area for _, p, *_ in elevated)


def test_case_e_before_after_share_existing():
    before = by_id(case_e.build_case_e("before").city)
    after = by_id(case_e.build_case_e("after").city)
    assert set(after) - set(before) == {"E-new-tower", "E-new-low-1", "E-new-low-2"}
    assert all(before[k][0].equals(after[k][0]) and before[k][1] == after[k][1] for k in before)


def test_case_e_exact_is_rejected_by_strict_qes(e):
    check = cityutil.qes_check(e.city)
    assert not check["ok"] and "touching footprints are unsupported" in check["error"]


@pytest.mark.parametrize("min_detail", [0.1, 0.5])
def test_case_e_exact_is_accepted_with_footprints(e, min_detail):
    # fallback="error" (the default) raises on any wall fallback, so ok means none occurred.
    check = cityutil.qes_check(e.city, footprints=wind.Footprints(min_detail=min_detail))
    assert check["ok"], check.get("error")
    counts = check["counts"]
    assert check["fallbacks"] == [] and counts["fallbacks"] == 0
    assert counts["sources"] == len(e.city.buildings) and counts["covered"] == counts["excluded"] == 0
    assert check["cleaned_area"] == pytest.approx(cityutil.summary(e.city)["footprint_area"], rel=2e-3)


def test_case_e_small_detail_cleans():
    # DTCC_REQUESTS.md R6 acceptance: δ = 0.01 failed with dtcc-core 80a4bba and passes from
    # dev/qes-updates 66c81a2 (2026-11-01), with no fallback and no lost source.
    city = case_e.build_case_e("after").city
    check = cityutil.qes_check(city, footprints=wind.Footprints(min_detail=0.01))
    assert check["ok"], check.get("error")
    assert check["fallbacks"] == [] and check["counts"]["fallbacks"] == 0
    assert check["counts"]["sources"] == len(city.buildings)


def test_case_e_qes_ready(e_qes):
    state, exact, merged = e_qes
    report = merged.report["merge"]
    summary = cityutil.summary(merged.city)
    assert summary["touching_pairs"] == summary["overlapping_pairs"] == 0
    assert summary["holes"] == 0
    assert summary["volume"] == pytest.approx(cityutil.summary(exact.city)["volume"] + report["added_volume"])
    covered = [i for m in report["merges"] for i in m["members"]]
    kept = [b.id for b in merged.city.buildings if "merged_parts" not in b.attributes]
    assert sorted(covered + kept) == sorted(b.id for b in exact.city.buildings)
    assert len(cityutil.city_objects(merged.city)) == 32
    assert cityutil.qes_check(merged.city)["ok"]


def test_markers_are_at_measurement_points():
    markers = case_e.load().markers
    points = tables.load_points_e().xyz
    gaps = np.linalg.norm(markers[:, None, :2] - points[None, :, :2], axis=2).min(axis=1)
    assert len(markers) == 80 and np.all(markers[:, 2] == 2.0)
    assert np.median(gaps) < 3.0


@pytest.mark.parametrize("build", [lambda: case_d.build_case_d(), lambda: case_e.build_case_e("after")])
def test_round_trip(tmp_path, build):
    city = build().city
    path = tmp_path / "city.dtcc"
    city.save(path)
    loaded = load_city(path)
    assert loaded.attributes == city.attributes
    original, restored = by_id(city), by_id(loaded)
    assert original.keys() == restored.keys()
    for key, (polygon, height) in original.items():
        assert restored[key][1] == height and restored[key][0].equals(polygon)
    assert ([o.attributes for o in cityutil.city_objects(loaded)]
            == [o.attributes for o in cityutil.city_objects(city)])


def test_sloped_faces_are_rejected():
    with pytest.raises(ValueError, match="neither horizontal nor vertical"):
        prisms.solid([np.array([[0, 0, 0], [1, 0, 0], [1, 1, 1.0]]), np.array([[0, 0, 0], [1, 1, 0], [0, 1, 0.0]])])


def test_buildings_follow_the_dtcc_core_convention(d):
    tower = next(b for b in d.city.buildings if b.id == "D-tower")
    assert tower.lod0.vertices[:, 2].tolist() == [100.0] * len(tower.lod0.vertices)  # LOD0 at the roof
    assert tower.attributes["ground_height"] == 0.0 and tower.measured_height == 100.0
    assert tower.attributes["prism_decomposition"]["version"] == 1  # derived by footprints_from_lod1
    report = d.city.attributes["footprints_from_lod1"]
    assert report["converted"] == report["attempted"] == 83 and not report["failures"]


def test_qes_city_moves_lod0_to_the_ground(e):
    moved = cityutil.qes_city(e.city)
    for original, building in zip(e.city.buildings, moved.buildings):
        assert set(building.lod0.vertices[:, 2]) == {0.0}
        assert original.lod0.vertices[0, 2] == original.measured_height  # the source is unchanged
    assert cityutil.footprints(moved) == cityutil.footprints(e.city)
    assert len(cityutil.city_objects(moved)) == len(cityutil.city_objects(e.city))


def test_dtcc_qes_still_reads_lod0_as_the_base(d):
    # DTCC_REQUESTS.md R3: when this fails, dtcc-qes reads the dtcc-core convention and
    # cityutil.qes_city can be removed.
    with pytest.raises(ValueError, match="incompatible base elevation"):
        wind.preview_grid(d.city, resolution=4.0)


def test_footprints_from_lod1_agrees_with_the_validation_decomposition():
    """dtcc-core's decomposition of the Case E solids equals aij.prisms wherever it succeeds.

    It rejects the 27 stepped solids and 6 others as nonmanifold: 22 have T-junctions
    (non-conforming faces) and 11 have walls drawn from the ground inside the footprint
    (DTCC_REQUESTS.md R5). When this count drops, Case E can move to footprints_from_lod1.
    """
    from dtcc_core.builder import footprints_from_lod1
    from dtcc_core.model import City

    geometry = case_e.load()
    solids = geometry.existing + geometry.new + [solid for _, solid in geometry.elevated]
    source = City()
    for i, solid in enumerate(solids):
        source.add_building(cityutil.lod1_building(f"s{i:03d}", solid.faces))
    derived = footprints_from_lod1(source, on_error="warn")
    report = derived.attributes["footprints_from_lod1"]
    failed = {f["input_id"] for f in report["failures"]}
    assert len(failed) == 33 and {f["reason"] for f in report["failures"]} == {"nonmanifold"}
    stepped = {f"s{i:03d}" for i, solid in enumerate(solids) if len(solid.levels) > 1}
    assert stepped <= failed and len(stepped) == 27
    pieces = {}
    for building in derived.buildings:
        record = building.attributes.get("prism_decomposition")
        if record is not None:  # failed sources come back as LOD1-only copies
            polygon = shapely.Polygon(building.lod0.vertices[:, :2], [h[:, :2] for h in building.lod0.holes])
            pieces.setdefault(record["input_id"], []).append(
                (polygon, building.measured_height, building.attributes["ground_height"]))
    assert len(pieces) == len(solids) - 33
    for i, solid in enumerate(solids):
        if f"s{i:03d}" in failed:
            continue
        (polygon, height, ground), = pieces[f"s{i:03d}"]  # single-level solids give one piece
        (roof, level), = solid.levels.items()
        assert ground == pytest.approx(solid.zmin, abs=1e-9) and height == pytest.approx(roof - solid.zmin, abs=1e-9)
        assert polygon.symmetric_difference(level).area < 1e-6

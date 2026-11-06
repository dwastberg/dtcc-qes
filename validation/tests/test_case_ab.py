"""Cases A and B: readers, geometry, grids, run specs, comparisons and one small solve (AIJ_AB_VALIDATION.md)."""

import json

import numpy as np
import pytest

from aij import CASE_A_XLS, CASE_B_XLS, campaigns, case_ab, compare, cityutil, grids, runner, sampling, tables
from aij.conventions import AB_DIRECTION, flow_vector
from aij.runspec import AB_DOMAIN, RunSpec


pytestmark = pytest.mark.skipif(
    not (CASE_A_XLS.is_file() and CASE_B_XLS.is_file()),
    reason="External AIJ A/B spreadsheets required; set DTCC_QES_AIJ_DATA",
)


@pytest.fixture(scope="module", params=["A", "B"])
def case(request):
    return request.param


def test_results_layout():
    a, b = tables.load_results_ab("A"), tables.load_results_ab("B")
    assert {s: int((a.section == s).sum()) for s in ("vertical", "z=0.125b", "z=1.25b")} == \
        {"vertical": 66, "z=0.125b": 60, "z=1.25b": 60}
    assert {s: int((b.section == s).sum()) for s in ("vertical", "z=12.5mm")} == {"vertical": 109, "z=12.5mm": 115}
    for data in (a, b):
        assert len(set(data.ids.tolist())) == len(data.ids)
        np.testing.assert_allclose(data.k, 0.5 * data.variance.sum(axis=1), rtol=1e-12)
        assert np.all(data.xyz[data.section != "vertical", 1] <= 0)  # horizontal sections: the y <= 0 half
        assert np.all(data.xyz[data.section == "vertical", 1] == 0)
    # The z = 1.25b sheet's z column says 0.125; the reader puts it at 1.25 b = 20 m.
    assert np.all(a.xyz[a.section == "z=1.25b", 2] == 20.0) and np.all(a.xyz[a.section == "z=0.125b", 2] == 2.0)
    assert np.all(b.xyz[b.section == "z=12.5mm", 2] == 2.0)
    np.testing.assert_allclose(a.xyz[0], [-12.0, 0.0, 2.0])  # x/b = -0.75, z/b = 0.125 at b = 16 m
    np.testing.assert_allclose(b.xyz[0], [-12.0, 0.0, 56.0])  # (-75, 0, 350) mm at 1:160


def test_inflow():
    a, b = tables.load_inflow_ab("A"), tables.load_inflow_ab("B")
    assert a.reference == dict(height=32.0, speed=4.491) and b.reference == dict(height=32.0, speed=5.133)
    assert (a.heights[0], a.heights[-1]) == (1.0, 120.0) and (b.heights[0], b.heights[-1]) == (0.8, 160.0)
    assert np.all(np.diff(a.speeds) > 0) and np.all(np.diff(b.speeds) > 0)


def test_direction_is_toward_plus_x():
    np.testing.assert_allclose(flow_vector(AB_DIRECTION), [1.0, 0.0], atol=1e-12)
    # The data agree: reverse flow near the ground behind both buildings.
    for c in ("A", "B"):
        data = tables.load_results_ab(c)
        wake = (data.section == "vertical") & (data.xyz[:, 0] > case_ab.size(c)[0] / 2) & (data.xyz[:, 2] <= 2.0)
        assert (data.velocity[wake, 0] < 0).any() and data.velocity[data.xyz[:, 2] > 50, 0].min() > 0


def test_city(case):
    built = case_ab.build_case_ab(case)
    rows = cityutil.footprints(built.city)
    assert len(rows) == 1
    _, polygon, height = rows[0]
    depth, width, h = case_ab.size(case)
    assert height == h == 32.0 and polygon.bounds == (-depth / 2, -width / 2, depth / 2, width / 2)
    assert built.city.attributes["scale"] == pytest.approx(200.0 if case == "A" else 160.0)
    points = tables.load_points_ab(case)
    distance = case_ab.surface_distance(points.xyz, case)
    assert distance.min() == pytest.approx(2.0 if case == "A" else 1.6)
    # The plan distance agrees beside the building, where the 3D one has no vertical part.
    low = points.xyz[:, 2] < h
    np.testing.assert_allclose(distance[low], sampling.wall_distance(points.xyz[low, :2], [polygon]))
    assert set(case_ab.regions(points.xyz, case)) == set(case_ab.REGIONS)


@pytest.mark.parametrize("layer", [4.0, 2.0, 1.0, 0.5])
def test_faces_put_the_building_on_the_grid(case, layer):
    faces = grids.vertical_faces(layer, 160.0, 64.0, centre=grids.layer_centre(case, layer), max_dz=4 * layer)
    assert faces[0] == 0.0 and np.any(np.isclose(faces, 32.0)) and faces[-1] >= 160.0
    assert np.allclose(np.diff(faces[faces <= 64.0]), layer)
    polygon = cityutil.footprints(case_ab.build_case_ab(case).city)[0][1]
    xmin, ymin, _, xmax, ymax, _ = grids.horizontal_bounds(case, [polygon], AB_DOMAIN["padding"],
                                                           AB_DOMAIN["downstream"])
    for edge in polygon.bounds[::2]:
        assert ((edge - xmin) / layer) % 1 == 0
    for edge in polygon.bounds[1::2]:
        assert ((edge - ymin) / layer) % 1 == 0
    assert xmax - polygon.bounds[2] == AB_DOMAIN["downstream"] and polygon.bounds[0] - xmin == AB_DOMAIN["padding"]


def test_runspec():
    a, b = campaigns.ab_baseline()
    # Keys of stored runs must not change when campaigns move or grow.
    assert (a.key, b.key) == ("f536f3697b5ceedb", "619891fb6b410b83")
    assert a.name == "A-0deg-r1-measured-float32-it6000"
    assert RunSpec.from_dict(json.loads(json.dumps(a.to_dict()))) == a
    assert campaigns.case_d(0.0, resolution=2.0, turbulence=False).key == "3af75ea91b3dfde2"
    assert "downstream" not in campaigns.case_d(0.0).to_dict()
    assert campaigns.case_ab("A", padding=160.0, downstream=480.0).name.endswith("pad160-down480")
    with pytest.raises(ValueError, match="downstream"):
        RunSpec("A", "0 deg.", 270.0)
    with pytest.raises(ValueError, match="downstream"):
        campaigns.case_d(0.0, downstream=100.0)
    for name in ("ab_smoke", "ab_convergence", "ab_baseline", "ab_grid", "ab_sensitivity"):
        specs = campaigns.campaign(name)
        assert {s.case for s in specs} == {"A", "B"} and len({s.key for s in specs}) == len(specs)


def test_reattachment():
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    assert compare.reattachment(x, [-1.0, -1.0, -0.5, 0.5, 1.0]) == pytest.approx(2.5)
    assert compare.reattachment(x, [1.0, -1.0, 1.0, 1.0, 1.0]) == pytest.approx(1.5)
    assert compare.reattachment(x, np.ones(5)) is None and compare.reattachment(x, -np.ones(5)) is None


def test_sign_scores():
    scores = compare.sign_scores([-0.2, 0.3, -0.1, 0.0], [-0.3, 0.4, 0.2, 0.01])
    assert scores["count"] == 3 and scores["reverse"] == 1 and scores["reverse_recall"] == 1.0
    assert scores["false_reverse"] == 0.5 and scores["agreement"] == pytest.approx(2 / 3)


def test_measured_features():
    # Wake reattachment at 2 m from the tabulated stations, near the published 1.42 b and 7.6 b.
    for c, published in (("A", 1.42), ("B", 7.6)):
        measured = compare.ab_reattachment({}, c)["2"]["measured"] / case_ab.b(c)
        assert abs(measured - published) < 0.3
    a, b = compare.ab_repeatability("A"), compare.ab_repeatability("B")
    assert (a["pairs"], b["pairs"]) == (5, 7) and a["U"]["max_abs_difference"] < 0.01


def test_lateral_sign():
    """Case B: the tabulated V runs into the side wall; the comparisons use the negated value."""
    data = tables.load_results_ab("B")
    beside = (data.section == "z=12.5mm") & (data.xyz[:, 0] == -4.0) & (data.xyz[:, 1] == -17.6)
    assert data.velocity[beside, 1] > 0 and compare.ab_velocity("B")[beside, 1] < 0
    np.testing.assert_array_equal(compare.ab_velocity("A"), tables.load_results_ab("A").velocity)


def test_null_model(case):
    null = compare.null_model(case)
    data = tables.load_results_ab(case)
    at_h = np.isclose(data.xyz[:, 2], 32.0)
    np.testing.assert_allclose(null["K"][at_h], 1.0, rtol=1e-9)
    assert np.all(null["W"] == 0) and np.all(np.diff(null["K"][np.argsort(data.xyz[:, 2])]) >= -1e-12)


@pytest.fixture(scope="module")
def solved():
    spec = campaigns.case_ab("B", resolution=4.0, max_iterations=200, tolerance=1.2e-7)
    return spec, *runner.run(spec)


def test_record(solved):
    spec, record, arrays = solved
    probes = record["probes"]
    assert len(probes["K"]) == 224 and np.isfinite(probes["K"]).all()
    assert set(probes["method"]) <= {sampling.LINEAR, sampling.NEAREST_FLUID}
    assert record["provenance"]["xls_sha256"] == cityutil.sha256(tables.ab_source("B")[0])
    assert set(record["centreline"]) == {"0.8", "2"}
    assert {"plane_2_velocity", "centre_velocity", "centre_k"} <= set(arrays)
    assert arrays["centre_velocity"].shape == (len(arrays["centre_z"]), len(arrays["centre_x"]), 3)
    comparisons = compare.isolated({("B", "-", "0 deg."): record}, "B")
    assert [c.quantity for c in comparisons] == list(compare.AB_QUANTITIES)
    assert comparisons[0].scores()["count"] == 224 and comparisons[-1].options == dict(w=0.0)


def test_solid_cells_match_the_building(solved):
    """The roof and walls lie on grid faces: the solid cells are exactly the building's volume."""
    from dtcc_qes import wind
    spec = solved[0]
    args = runner.inputs(spec)
    result = wind.run(args["city"], args["profile"], **{**args["run"], "turbulence": None,
                                                       "solver": wind.Solver(max_iterations=1)})
    solid = (result.cell_flags == 0) | (result.cell_flags == 2)
    depth, width, height = case_ab.size("B")
    assert solid.sum() * spec.resolution ** 2 * spec.probe_layer == depth * width * height

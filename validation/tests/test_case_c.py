"""Case C workbook interpretation and shared-runner integration."""
import numpy as np
import pytest

from aij import CASE_C_XLS, campaigns, case_c, cityutil, grids, inflow, runner, tables
from aij.conventions import C_ANGLES, C_STATES, c_direction, flow_vector
from aij.runspec import RunSpec

pytestmark = pytest.mark.skipif(not CASE_C_XLS.is_file(), reason="External AIJ C workbook required")


def test_workbook():
    data = tables.load_results_c("2H")
    assert data.values.shape == (120, 3)
    assert np.isfinite(data.values).all()
    assert len(set(data.ids)) == 120
    np.testing.assert_allclose(data.xyz[0], [-30, -25, 2])
    np.testing.assert_allclose(data.values[0], [1.0830552580525286, 1.0140908550861247, .854839741723679])
    assert data.instrument == "thermistor" and data.quantity == "scalar_speed_ratio"
    profile = tables.load_inflow_c()
    assert len(profile.heights) == 16 and np.isnan(profile.k).all()
    assert profile.reference == dict(height=2.0, speed=2.434)
    np.testing.assert_allclose(profile.heights[[0, -1]], [1, 120])
    assert inflow.reference_speed(inflow.measured_profile(profile, 270)) == pytest.approx(2.434)


def test_direction_evidence():
    np.testing.assert_allclose(flow_vector(c_direction(45)), [2**-.5, -2**-.5], atol=1e-12)
    # Infer the sign from measured 45-degree reflection symmetry, independently of QES.
    for state in C_STATES:
        data = tables.load_results_c(state)
        lookup = {tuple(xy): i for i, xy in enumerate(data.xyz[:, :2])}
        errors = []
        for sign in (1, -1):
            order = [lookup[tuple(sign * xy[::-1])] for xy in data.xyz[:, :2]]
            errors.append(np.mean(abs(data.values[:, 2] - data.values[order, 2])))
        assert errors[1] < errors[0] / 4


@pytest.mark.parametrize("state,count,volume", [("0H", 8, 64000), ("1H", 9, 72000), ("2H", 9, 80000)])
def test_geometry(state, count, volume):
    built = case_c.build_case_c(state)
    rows = cityutil.footprints(built.city)
    assert len(rows) == count and built.report["volume"] == volume
    assert built.city.attributes["scale"] == 100
    points = tables.load_points_c()
    from shapely.geometry import Point
    assert all(not p.covers(Point(*xy)) for _, p, _ in rows for xy in points.xyz[:, :2])
    assert min(p.distance(Point(*xy)) for _, p, _ in rows for xy in points.xyz[:, :2]) == pytest.approx(5)


def test_campaigns_and_inputs():
    for name, count in (("c_smoke", 9), ("c_baseline", 9), ("c_grid", 18), ("c_fine", 9),
                        ("c_convergence", 36), ("c_sensitivity", 81)):
        specs = campaigns.campaign(name)
        assert len(specs) == count and len({s.key for s in specs}) == count
        assert all(RunSpec.from_dict(s.to_dict()) == s for s in specs)
    for state in C_STATES:
        args = runner.inputs(campaigns.case_c(45, state))
        assert args['reference_speed'] == pytest.approx(2.434)
        assert args['run']['bounds'] == (-170, -170, 0, 170, 170, None)
    for r in (4, 2, 1, .5):
        faces = grids.vertical_faces(r, 200, 80, centre=grids.layer_centre('C', r), max_dz=4*r)
        assert 20 in faces and 40 in faces
    with pytest.raises(ValueError):
        campaigns.case_c(state='before')
    with pytest.raises(ValueError):
        campaigns.case_c(angle=90)


def test_small_solve_and_comparison():
    from aij.report_c import comparison
    spec = campaigns.case_c(22.5, '2H', resolution=4, max_iterations=20, turbulence=False)
    record, arrays = runner.run(spec)
    assert record['provenance']['xls_sha256'] == cityutil.sha256(CASE_C_XLS)
    np.testing.assert_allclose(record["probes"]["sampled"], tables.load_points_c().xyz)
    assert record['profile']['reference_speed'] == pytest.approx(2.434)
    row = comparison(record)
    assert row['scores']['mean_vector_speed']['count'] == 120
    assert arrays['velocity'].shape[-1] == 3
    # ID joins survive storage reordering, and coordinate mismatches are rejected.
    for key in ('ids', 'xyz', 'K'):
        record['probes'][key] = record['probes'][key][::-1]
    np.testing.assert_allclose(comparison(record)['simulated']['mean_vector_speed'],
                               row['simulated']['mean_vector_speed'])
    record['probes']['xyz'] = record['probes']['xyz'].copy()
    record['probes']['xyz'][0, 0] += 1
    with pytest.raises(ValueError, match='coordinates'):
        comparison(record)

"""Wind-direction conventions and the model-independent checks of them (plan F8)."""

import numpy as np
import pytest
from dtcc_qes.profiles import LogProfile

from aij import case_e, cityutil, conventions, metrics, tables


def test_case_d_mapping():
    assert [conventions.d_direction(a) for a in conventions.D_ANGLES] == [270.0, 247.5, 225.0]
    np.testing.assert_allclose(conventions.flow_vector(270.0), [1.0, 0.0], atol=1e-15)  # 0° flows toward +x
    flow = conventions.flow_vector(225.0)
    assert flow[0] > 0 and flow[1] > 0  # 45° turns toward +y


def test_case_e_mapping():
    assert conventions.e_direction("N") == 0.0
    assert conventions.e_direction("E") == 90.0
    assert conventions.e_direction("NNW") == 337.5
    np.testing.assert_allclose(conventions.flow_vector(0.0), [0.0, -1.0], atol=1e-15)  # wind from +y


@pytest.mark.parametrize("direction", [0.0, 67.5, 225.0, 270.0])
def test_flow_vector_matches_dtcc_qes(direction):
    u, v = LogProfile(1.0, direction).evaluate(np.array([10.0]))[0]
    np.testing.assert_allclose(conventions.flow_vector(direction), [u, v], atol=1e-12)


def test_case_d_reverse_flow_upstream_of_tower():
    """At 0° the near-ground flow 22.5 m in front of the tower runs back upstream (U < 0).

    In a wake under the opposite flow it would run toward the tower (U > 0).
    """
    exp_s = tables.load_exp_s()
    upstream = np.isin(exp_s.ids, (8, 9))
    assert np.all(exp_s.xyz[upstream, 0] < -12.5)  # west of the tower face
    assert np.all(exp_s.velocity[upstream, 0] < -1.5)
    # They are the two strongest reverse flows of the 33 points, as in a standing vortex.
    m = exp_s.measured
    assert sorted(exp_s.ids[m][np.argsort(exp_s.velocity[m, 0])[:2]]) == [8, 9]


def test_case_d_45_degrees_follows_the_diagonal():
    exp_t = tables.load_exp_t()
    xy = exp_t.xyz[:, :2]
    along = conventions.mirror_symmetry(exp_t.values, xy, "y=x")
    across = conventions.mirror_symmetry(exp_t.values, xy, "y=-x")
    assert along[2] < 0.7 * across[2]
    assert conventions.mirror_symmetry(exp_t.values, xy, "x-axis")[0] == 0.0  # 0° copies


def test_case_e_mapping_check():
    """Of the eight rotations and senses of the 16 labels, the meteorological mapping
    gives by far the strongest sheltering signal in the "before" data."""
    before = tables.load_results_e("before")
    footprints = cityutil.footprints(case_e.build_case_e("before").city)
    polygons, heights = [p for _, p, _ in footprints], np.array([h for _, _, h in footprints])
    results = conventions.mapping_check(before.values, before.xyz[:, :2], polygons, heights)
    best = min(results, key=lambda r: r["median_rho"])
    assert (best["sense"], best["offset"]) == ("clockwise", 0.0)
    assert best["median_rho"] < -0.4 and best["negative_directions"] == 16
    others = sorted(r["median_rho"] for r in results if r is not best)
    assert others[0] > -0.2


def test_ranks_average_ties():
    np.testing.assert_allclose(metrics.ranks([3.0, 1.0, 3.0, 2.0]), [2.5, 0.0, 2.5, 1.0])
    assert metrics.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert metrics.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert metrics.spearman([1, 2, np.nan, 4, 5], [1, 2, 3, np.nan, 5]) == pytest.approx(1.0)

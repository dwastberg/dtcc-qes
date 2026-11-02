"""Readers of the AIJ inflow and result tables (AIJ_VALIDATION_PLAN.md, F9-F10).

    uv run --group validate pytest validation/tests -q
"""

import numpy as np
import pytest

from aij import conventions, tables

EXP_S_IDS = [1, 3, 5, 6, 7, 8, 9, 15, 16, 17, 18, 19, 25, 31, 35, 39, 45, 46, 47, 48, 49,
             55, 56, 57, 58, 59, 65, 66, 67, 68, 69, 75, 77]
EXP_T_MISSING = [26, 27, 28, 29, 32, 33, 36, 37, 40, 41, 42, 43]


@pytest.fixture(scope="module")
def exp_s():
    return tables.load_exp_s()


@pytest.fixture(scope="module")
def exp_t():
    return tables.load_exp_t()


@pytest.fixture(scope="module", params=conventions.E_STATES)
def e(request):
    return tables.load_results_e(request.param)


def test_inflow_d():
    inflow = tables.load_inflow_d()
    np.testing.assert_allclose(inflow.heights, np.array([5, 10, 20, 30, 50, 100, 200, 300, 400, 600, 800, 1000, 1200]) * 0.4)
    assert inflow.speeds[5] == pytest.approx(0.8 * tables.U_H)  # z = 100 mm: U/U_H = 0.8 exactly
    assert inflow.reference == dict(height=100.0, speed=6.65)
    assert np.all(np.diff(inflow.speeds) > 0) and np.all(inflow.k > 0)


def test_inflow_e():
    inflow = tables.load_inflow_e()
    assert inflow.heights[0] == pytest.approx(1.25) and inflow.heights[-1] == pytest.approx(250.0)
    assert inflow.speeds[-1] == pytest.approx(tables.U_R)  # U/U_R = 1 at Z_R
    assert inflow.k[0] == pytest.approx(0.008 * tables.U_R ** 2)
    assert inflow.reference == dict(height=15.9, speed=None)


def test_exp_s_identities(exp_s):
    assert exp_s.ids[exp_s.measured].tolist() == EXP_S_IDS
    assert np.all(exp_s.xyz[exp_s.measured, 1] > 0)  # a half-domain survey
    m = exp_s.measured
    np.testing.assert_allclose(exp_s.speed_ratio[m], np.linalg.norm(exp_s.velocity[m], axis=1) / tables.U_H, rtol=1e-12)
    np.testing.assert_allclose(exp_s.k[m], 0.5 * exp_s.variance[m].sum(axis=1), rtol=1e-12)
    assert np.isnan(exp_s.velocity[~m]).all() and np.isnan(exp_s.speed_ratio[~m]).all()
    assert exp_s.direction == 270.0


def test_exp_s_coordinates_match_points(exp_s):
    import xlrd
    sheet = xlrd.open_workbook(tables.CASE_D_XLS).sheet_by_name("Results (Exp_S)")
    for i, r in enumerate(range(3, 81)):
        if exp_s.measured[i]:
            assert np.allclose(np.array(sheet.row_values(r)[1:4]) * 0.4, exp_s.xyz[i])


def test_exp_t(exp_t):
    import xlrd
    assert exp_t.values.shape == (78, 3)
    assert exp_t.ids[np.isnan(exp_t.values).all(axis=1)].tolist() == EXP_T_MISSING
    assert np.isnan(exp_t.values).sum() == 3 * len(EXP_T_MISSING)
    np.testing.assert_allclose(exp_t.directions, [270.0, 247.5, 225.0])
    # The ratio columns equal the m/s columns divided by U_H.
    sheet = xlrd.open_workbook(tables.CASE_D_XLS).sheet_by_name("Results (Exp_T)")
    speeds = tables._values(sheet, range(5, 83), range(4, 7))
    np.testing.assert_allclose(exp_t.values, speeds / tables.U_H, rtol=1e-12)


def test_exp_t_mirrored_copies(exp_t):
    """At 0° every y < 0 value equals its mirror point (x, -y): 33 copies, none at 22.5° or 45°."""
    assert exp_t.mirrored[:, 0].sum() == 33 and not exp_t.mirrored[:, 1:].any()
    xy = exp_t.xyz[:, :2]
    for i in np.flatnonzero(exp_t.mirrored[:, 0]):
        j = np.flatnonzero(np.all(np.isclose(xy, xy[i] * [1, -1]), axis=1))[0]
        assert exp_t.values[i, 0] == exp_t.values[j, 0]


def test_results_e(e):
    assert e.values.shape == (80, 16) and np.isfinite(e.values).all()
    assert e.labels == conventions.E_LABELS
    np.testing.assert_allclose(e.directions, 22.5 * np.arange(16))
    np.testing.assert_array_equal(e.ids, np.arange(1, 81))
    np.testing.assert_allclose(e.xyz, tables.load_points_e().xyz)
    steps = e.values / tables.E_QUANTUM
    np.testing.assert_allclose(steps, np.round(steps), atol=1e-9)  # quantised measurement resolution
    assert 0.09 < e.values.min() and e.values.max() < 1.4


def test_results_e_states_differ_near_new_buildings():
    before, after = tables.load_results_e("before"), tables.load_results_e("after")
    assert before.values.max() == pytest.approx(0.7135, abs=1e-4)
    assert after.values.max() == pytest.approx(1.3676, abs=1e-4)
    assert (after.values != before.values).any(axis=1).sum() > 60


def test_bad_state():
    with pytest.raises(ValueError):
        tables.load_results_e("during")

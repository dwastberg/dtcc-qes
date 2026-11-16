"""The spreading far wake in the AIJ harness (WAKE_UPDATE_V2.md, step W3)."""

import numpy as np
import pytest

from aij import CASE_A_XLS, CASE_B_XLS, campaigns, compare, runner
from aij.conventions import AB_LABEL

import run_wake_validation


def test_wake3_campaigns():
    specs = campaigns.campaign("wake3")
    baseline = campaigns.campaign("baseline")
    assert len(specs) == len(baseline) == 35
    assert all(dict(s.parameterizations) == {"wake": 3} for s in specs)
    assert [s.key for s in specs] != [s.key for s in baseline]
    ab = campaigns.campaign("ab_wake3")
    assert sorted((s.case, s.resolution) for s in ab) == [("A", 1.0), ("A", 2.0), ("B", 1.0), ("B", 2.0)]
    assert all(dict(s.parameterizations) == {"wake": 3} for s in ab)


def _probes(record, name):
    return np.array([np.nan if v is None else v for v in record["probes"][name]], dtype=np.float64)


# Cases A and B need the external AIJ spreadsheets, as in test_case_ab.py.
needs_ab = pytest.mark.skipif(not (CASE_A_XLS.is_file() and CASE_B_XLS.is_file()),
                              reason="External AIJ A/B spreadsheets required; set DTCC_QES_AIJ_DATA")


@pytest.fixture(scope="module")
def solved():
    spec = campaigns.case_ab("B", resolution=4.0, max_iterations=200, tolerance=1.2e-7,
                             parameterizations=campaigns.WAKE3)
    return spec, *runner.run(spec)


@needs_ab
def test_record_has_the_wake_scalar_speeds(solved):
    spec, record, _ = solved
    K, D, kw = (_probes(record, n) for n in ("K", "wake_deficit", "wake_tke"))
    table, rule = _probes(record, "K_scalar_wake"), _probes(record, "K_scalar_wake_rule")
    finite = np.isfinite(K)
    assert finite.all() and np.all((D >= 0) & (D <= 1)) and np.all(kw >= 0) and D.max() > 0.3
    assert np.all(table >= K) and np.all(rule >= K)
    uref = record["profile"]["reference_speed"]
    k_in = _probes(record, "k_inflow_table")
    np.testing.assert_allclose(table, np.sqrt(K ** 2 + 2 * (k_in * (1 - D) ** 2 + kw) / uref ** 2), rtol=1e-12)
    assert record["provenance"]["model"]["wake_flag"] == 3


@needs_ab
def test_ab_scalar_comparison(solved):
    spec, record, _ = solved
    records = {("B", "-", AB_LABEL): record}
    comparison = compare.ab_scalar(records, "B")
    heights = np.array(record["probes"]["xyz"])[:, 2]
    assert comparison.quantity == "K_scalar_wake" and comparison.simulated.shape == (len(heights), 1)
    assert np.isnan(comparison.measured[heights > compare.AB_SCALAR_HEIGHT]).all()
    assert np.isfinite(comparison.scores()["hit_rate"])
    everything = compare.ab_scalar(records, "B", "K_scalar_wake_rule", max_height=None)
    assert np.isfinite(everything.measured).sum() > np.isfinite(comparison.measured).sum()
    assert compare.ab_scalar(records, "B", "missing") is None and compare.ab_scalar({}, "A") is None


def test_wake_validation_matrices_and_empty_gate_table(monkeypatch, tmp_path):
    specs = run_wake_validation.matrices()
    assert len(specs["baseline", 3]) == len(specs["baseline", 2]) == 35 + 4
    assert all(dict(s.parameterizations).get("wake") == 3 for s in specs["baseline", 3] + specs["models", 3])
    assert all(s.monitor and not s.turbulence for s in specs["convergence", 2])
    monkeypatch.setattr(run_wake_validation, "RUNS", tmp_path)
    rows = run_wake_validation.gate_table({3: {}, 2: {}})
    assert len(rows) == len(run_wake_validation.GATES) and all(r["passed"] is None for r in rows)


def test_registered_m2_strict_threshold_and_missing_inputs():
    from aij.wake_comfort import m2
    result = m2([.5, .6, .7, np.nan, .8], [.2, .2, .2, .9, np.nan], .6)
    np.testing.assert_allclose(result, [.2, .2, .7, np.nan, np.nan], equal_nan=True)


def test_registered_climates_and_public_assessment():
    from aij.wake_comfort import climate, assess
    directions = np.arange(16) * 22.5
    for dominant in (None, 5):
        speeds, angles = climate(directions, 7., dominant)
        assert len(speeds) == len(angles) == 150000
        counts = np.array([np.sum(angles == d) for d in directions])
        assert sorted(set(counts)) == ([9375] if dominant is None else [7000, 45000])
        field = np.full((80, 16), .8)
        result = assess(field, directions, 7., dominant)
        for threshold in (5., 15.):
            np.testing.assert_allclose(result.exceedance[threshold], np.exp(-(threshold / (7 * .8))**2), atol=16/150000)
        assert result.metadata['hours'] == 150000
        assert result.warnings  # registered 2 m height differs from NEN's 1.75 m


def test_cost_and_paired_maximum_bootstrap():
    from aij.wake_comfort import cost, worst_rotation, evaluate
    np.testing.assert_array_equal(cost(np.array([0, 4, 2]), np.array([2, 2, 2])), [6, 2, 0])
    d = np.full((16, 80), -2.)
    d[7] = 1.
    assert worst_rotation(d) == dict(T=1., interval_95=[1., 1.])
    # Missing observations must not become favourable classes (-1).
    x = np.ones((80, 16)); x[0, 0] = np.nan
    with pytest.raises(ValueError, match='complete finite'):
        evaluate(x, {'wake 2 vector': np.ones_like(x)}, np.arange(16)*22.5)


def test_gaussian_mean_limits_bounds_and_quadrature():
    from aij.wake_comfort import gaussian_mean_speed
    v = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [2., 3., 1.]])
    k = np.array([1., .2, .2, 0.])
    mean = gaussian_mean_speed(v, k)
    assert np.all(mean >= np.linalg.norm(v, axis=1) - 1e-12)
    assert np.all(mean <= np.sqrt(np.sum(v*v, axis=1)+2*k) + 1e-12)
    assert mean[1] == mean[2]
    np.testing.assert_allclose(mean, gaussian_mean_speed(v, k, order=256), atol=1e-10)
    assert np.isnan(gaussian_mean_speed(np.array([[np.nan, 0, 0]]), np.array([1.]))[0])


def test_cavity_overlap_joins_probe_id_and_direction():
    from types import SimpleNamespace
    from check_wake_cavity_overlap import overlap
    measured = SimpleNamespace(ids=np.array([3, 8]), labels=['N', 'E'], values=np.array([[1., 2.], [3., 4.]]))
    masks = dict(probe_ids=[3, 8], frozen_full_spurious_pairs=[dict(probe_id=8, label='E'), dict(probe_id=3, label='N')])
    assert overlap(masks, measured)['overlap_pairs'] == [(8, 'E')]
    masks['probe_ids'] = [8, 3]
    with pytest.raises(ValueError, match='probe order'):
        overlap(masks, measured)


def test_accuracy_option_campaigns():
    """The opt-in settings of 0.1.0b6 on the wake=3 matrices; each variant has its own run keys."""
    wake3 = campaigns.campaign("wake3")
    for name, settings in (("angle_fade", {"wake": 3, "angle_fade": 2.5}),
                           ("tall_buildings", {"wake": 3, "tall_buildings": 1}),
                           ("accuracy_options", {"wake": 3, "angle_fade": 2.5, "tall_buildings": 1})):
        specs = campaigns.campaign(name)
        assert len(specs) == len(wake3) == 35
        assert all(dict(s.parameterizations) == settings for s in specs)
        assert not {s.key for s in specs} & {s.key for s in wake3}
    ab = campaigns.campaign("ab_accuracy_options")
    assert sorted((s.case, s.resolution) for s in ab) == [("A", 1.0), ("A", 2.0), ("B", 1.0), ("B", 2.0)]
    c = campaigns.campaign("c_accuracy_options")
    assert len(c) == 9 and all(dict(s.parameterizations) == campaigns.ACCURACY_OPTIONS for s in c)
    assert campaigns.ACCURACY_OPTIONS == {"wake": 3, "angle_fade": 2.5, "tall_buildings": 1}

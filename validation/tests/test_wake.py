"""The spreading far wake in the AIJ harness (WAKE_UPDATE_V2.md, step W3)."""

import numpy as np
import pytest

from aij import campaigns, compare, runner
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


@pytest.fixture(scope="module")
def solved():
    spec = campaigns.case_ab("B", resolution=4.0, max_iterations=200, tolerance=1.2e-7,
                             parameterizations=campaigns.WAKE3)
    return spec, *runner.run(spec)


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

"""Phase 3: agreement metrics and the pairing of runs with measurements.

Synthetic records stand in for runs, so these checks do not need stored campaign output.
"""

import numpy as np
import pytest

from aij import campaigns, compare, metrics, tables


def test_scores_of_a_perfect_model():
    m = np.array([0.1, 0.3, 0.5, 0.9])
    s = metrics.scores(m, m)
    assert (s["hit_rate"], s["fac2"], s["fb"], s["nmse"], s["bias"]) == (1.0, 1.0, 0.0, 0.0, 0.0)
    assert s["r"] == pytest.approx(1.0) and s["spearman"] == pytest.approx(1.0)


def test_scores_of_a_biased_model():
    m = np.array([0.1, 0.3, 0.5, 0.9, np.nan])
    s = metrics.scores(1.3 * m, m, w=0.0)
    assert s["count"] == 4 and s["hit_rate"] == 0.0 and s["fac2"] == 1.0
    assert s["fb"] == pytest.approx(-0.3 / 1.15)  # (m - 1.3 m) / (0.5 (m + 1.3 m)); negative = overprediction
    assert s["bias"] == pytest.approx(0.3 * np.mean([0.1, 0.3, 0.5, 0.9]))
    sweep = list(metrics.scores(1.3 * m, m)["hit_rate_sweep"].values())
    assert sweep == sorted(sweep)  # a larger absolute tolerance never lowers the hit rate


def test_hit_rate_rule():
    # |s - m| <= 0.25 |m| hits; |s - m| <= W hits for small m.
    assert metrics.hit_rate([1.25, 1.26], [1.0, 1.0], w=0.0) == 0.5
    assert metrics.hit_rate([0.14], [0.1], w=0.05) == 1.0 and metrics.hit_rate([0.16], [0.1], w=0.05) == 0.0


def test_change_scores():
    before = np.array([[0.2, 0.3], [0.4, 0.5], [0.1, 0.2]] * 4)
    after = before + np.array([[0.1, -0.1], [0.0, 0.2], [-0.2, 0.05]] * 4)
    s = metrics.change_scores(before, after, before, after, top=3)
    assert s["sign_agreement"] == 1.0 and s["top_overlap"] == 1.0 and s["r"] == pytest.approx(1.0)
    flipped = metrics.change_scores(after, before, before, after, top=3)
    assert flipped["sign_agreement"] == 0.0


def test_angle_error():
    np.testing.assert_allclose(metrics.angle_error([[1, 0], [1, 0], [0, 1]], [[0, 1], [-1, 0], [0, 1]]), [90, 180, 0])


def _records(case, state, labels, ids, values, extra=None):
    out = {}
    for d, label in enumerate(labels):
        probes = dict(ids=ids.tolist(), K=values[:, d].tolist(), K_scalar=values[:, d].tolist(),
                      wall_distance=np.full(len(ids), 3.0).tolist())
        out[(case, state, label)] = dict(key=f"{case}{state}{d}", probes=probes, **(extra or {}))
    return out


def test_case_d_pairing():
    exp_t = tables.load_exp_t()
    values = np.where(np.isfinite(exp_t.values), exp_t.values, 0.3)
    records = _records("D", "-", exp_t.labels, exp_t.ids, values)
    comparisons = {c.name: c for c in compare.case_d(records)}
    thermistor = comparisons["D-thermistor-K"]
    assert thermistor.scores()["hit_rate"] == 1.0 and thermistor.scores()["count"] == 198
    assert thermistor.scores(thermistor.strata["mirror"] == "measured")["count"] == 198 - 33
    split = comparisons["D-split_fibre"]
    assert split.scores()["count"] == 33  # only the split-fibre points are paired


def test_case_e_pairing():
    records = {}
    for state in ("before", "after"):
        m = tables.load_results_e(state)
        records.update(_records("E", state, m.labels, m.ids, m.values))
    comparisons = compare.case_e_comparisons(records)
    assert [c.name for c in comparisons] == ["E-before-thermistor-K", "E-before-thermistor-K_scalar",
                                             "E-after-thermistor-K", "E-after-thermistor-K_scalar"]
    assert all(c.scores()["hit_rate"] == 1.0 and c.scores()["count"] == 1280 for c in comparisons)
    slab = comparisons[0].strata["slab"]
    assert set(np.unique(slab)) == {"open", "slab-adjacent"}


def test_span_stratum():
    m = tables.load_results_e("after")
    records = _records("E", "after", m.labels, m.ids, m.values)
    assert "span" not in compare.case_e_comparisons(records, ("K",))[0].strata  # no neighbourhood stored
    for record in records.values():
        k = np.array(record["probes"]["K"])
        record["probes"].update(K_min=(k - 0.01).tolist(), K_max=(k + 0.1).tolist())
    span = compare.case_e_comparisons(records, ("K",))[0].strata["span"]
    assert span.shape == m.values.shape and set(np.unique(span)) == {"span 0.05-0.15"}


def test_instrument_ceiling_matches_phase_1():
    ceiling = compare.instrument_ceiling()
    assert ceiling["vector"]["hit_rate"] == pytest.approx(0.52, abs=0.01)
    assert ceiling["scalar"]["hit_rate"] == pytest.approx(0.91, abs=0.01)


def test_inflow_ratio():
    # 2 m is the lowest Case D table point; Case E interpolates between 1.25 and 2.5 m.
    assert compare.inflow_ratio("D") == pytest.approx(3.833055975794251 / 6.667139535345842, rel=1e-9)
    assert compare.inflow_ratio("E") == pytest.approx(0.750, abs=0.002)


def test_baseline_has_every_measured_direction():
    specs = campaigns.baseline(2.0)
    assert sorted({(s.case, s.state) for s in specs}) == [("D", "-"), ("E", "after"), ("E", "before")]

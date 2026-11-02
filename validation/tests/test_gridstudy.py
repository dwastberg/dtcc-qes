"""Phase 4: refinement budgets, sub-cell gaps and self-convergence, on synthetic records."""

import numpy as np
import pytest
from shapely.geometry import box

from aij import campaigns, gridstudy, numerics


def _record(k, wall=10.0, method="linear"):
    return dict(probes=dict(K=list(k), wall_distance=[wall] * len(k), method=[method] * len(k)))


def test_changes_and_budget():
    coarse = {("E", "after", "N"): _record([0.50, 0.30, 0.05, 0.20])}
    fine = {("E", "after", "N"): _record([0.52, 0.30, 0.09, 0.20])}
    entry = gridstudy.changes(coarse, fine)["E-after"]
    assert entry["count"] == 4 and entry["max"] == pytest.approx(0.04)
    # 0.50 -> 0.52 changes by 3.8 % (inside 5 %); 0.05 -> 0.09 is below K = 0.1, with |ΔK| = 0.04 < 0.05.
    assert entry["changed_fraction"] == 0.0 and entry["within_p95_budget"]
    fine[("E", "after", "N")]["probes"]["K"][0] = 0.56
    assert gridstudy.changes(coarse, fine)["E-after"]["changed_fraction"] == 0.25


def test_changes_skip_runs_missing_at_one_resolution():
    coarse = {("D", "-", "0 deg."): _record([0.3]), ("D", "-", "45 deg."): _record([0.4])}
    fine = {("D", "-", "0 deg."): _record([0.3])}
    assert gridstudy.changes(coarse, fine)["D"]["runs"] == 1


def test_changes_by_span():
    coarse = {("E", "after", "N"): _record([0.50, 0.30, 0.20])}
    coarse[("E", "after", "N")]["probes"].update(K_min=[0.49, 0.10, 0.18], K_max=[0.51, 0.40, 0.30])
    fine = {("E", "after", "N"): _record([0.50, 0.10, 0.25])}
    by_span = gridstudy.changes(coarse, fine)["E-after"]["by_span"]
    # spans 0.02, 0.30 and 0.12 on the coarser grid
    assert {c: b["count"] for c, b in by_span.items()} == {"span <0.05": 1, "span 0.05-0.15": 1, "span >0.15": 1}
    assert by_span["span >0.15"]["max"] == pytest.approx(0.20) and by_span["span <0.05"]["max"] == 0.0


def test_trend():
    key = ("E", "after", "N")
    coarse, middle = {key: _record([0.30, 0.30, 0.30])}, {key: _record([0.40, 0.20, 0.31])}
    # probe 0 keeps converging (+0.10 then +0.03), probe 1 reverses (-0.10 then +0.10), probe 2 is below the threshold
    fine = {key: _record([0.43, 0.30, 0.32])}
    out = gridstudy.trend(coarse, middle, fine)
    assert out["count"] == 2 and out["same_direction"] == 0.5
    assert out["median_ratio"] == pytest.approx(0.65)
    assert gridstudy.trend(coarse, middle, {})["count"] == 0


def test_subcell_gaps():
    polygons = [box(0, 0, 10, 10), box(10.5, 0, 20, 10), box(21.5, 0, 30, 10), box(30, 0, 40, 10)]
    # gaps 0.5 m and 1.5 m; the last pair touches and is not a gap
    assert gridstudy.subcell_gaps(polygons, (4.0, 1.0, 0.5)) == {"4": 2, "1": 1, "0.5": 0}


def test_fallbacks():
    records = {("E", "after", "N"): _record([0.1, 0.2], method="nearest_fluid"), ("D", "-", "0 deg."): _record([0.3])}
    assert gridstudy.fallbacks(records) == {"E": 2, "D": 0}


def test_self_convergence():
    iterations = list(range(0, 2001, 100))
    k = [[0.5 + 0.3 * np.exp(-i / 200), 0.2] for i in iterations]
    record = dict(name="x", grid=dict(cells=1), wall_seconds=1.0, peak_rss_bytes=2 ** 30,
                  history=dict(iterations=iterations, K=k))
    out = numerics.self_convergence(record)
    # 0.3 exp(-i/200) <= 0.005 from i = 900 (p95 over two probes is close to the max)
    assert out["required_iterations"] == 900 and out["within_1e4_from"] == 1600


def test_fine_subset():
    specs = campaigns.fine_subset(0.5)
    assert len(specs) == 9 and all(not s.turbulence and s.max_iterations == 16000 for s in specs)
    assert {(s.case, s.state) for s in specs} == {("D", "-"), ("E", "before"), ("E", "after")}
    assert gridstudy.subset_keys() == {(s.case, s.state, s.label) for s in specs}

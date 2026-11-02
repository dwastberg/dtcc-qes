"""Phase 4: how the probe values and the agreement scores change with grid resolution.

Refinement pairs use the repo's pairwise budgets (docs/joint-grid-verification.md,
tools/run_horizontal_sensitivity.py): p95 |ΔK| < 0.05, and a probe "changes" when
|ΔK| exceeds 5 % of K, or 0.05 where K < 0.1. No Richardson extrapolation
(docs/finest-reference.md).
"""

import json
from pathlib import Path

import numpy as np
import shapely
from shapely.strtree import STRtree

from . import campaigns, compare, metrics

P95_BUDGET = 0.05
RELATIVE_BUDGET = 0.05
LOW_SPEED = 0.1  # below this K the budget is absolute
LOW_SPEED_BUDGET = 0.05
WALL_CLASSES = ("wall <2 m", "wall 2-5 m", "wall >5 m")


def load(runs: Path, specs) -> dict:
    """Run records keyed by (case, state, label); missing runs are left out."""
    return compare.load_records(runs, specs)


def _values(record, quantity="K"):
    return np.array([np.nan if v is None else v for v in record["probes"][quantity]], dtype=np.float64)


def _k(record):
    return _values(record)


def _span_class(record):
    """Span class of each probe on this grid (compare.SPAN_BINS); None without a stored neighbourhood."""
    if "K_max" not in record["probes"]:
        return np.full(len(record["probes"]["K"]), None, dtype=object)
    return compare.span_classes(_values(record, "K_max") - _values(record, "K_min"))


def _wall_class(record):
    wall = np.array(record["probes"]["wall_distance"], dtype=np.float64)
    return np.where(wall < 2.0, WALL_CLASSES[0], np.where(wall < 5.0, WALL_CLASSES[1], WALL_CLASSES[2]))


def changes(coarse, fine) -> dict:
    """Probe changes K(fine) - K(coarse) over every run present at both resolutions, per case and state.

    Strata: wall distance, and the span class on the coarser grid (what one run can see in advance).
    """
    out = {}
    for key in sorted(set(coarse) & set(fine)):
        case, state, _ = key
        out.setdefault((case, state), []).append((_k(coarse[key]), _k(fine[key]), _wall_class(fine[key]),
                                                  _span_class(coarse[key])))
    summary = {}
    for (case, state), rows in out.items():
        before = np.concatenate([r[0] for r in rows])
        after = np.concatenate([r[1] for r in rows])
        walls = np.concatenate([r[2] for r in rows])
        spans = np.concatenate([r[3] for r in rows])
        entry = dict(runs=len(rows), **_budget(before, after))
        entry["by_wall"] = {w: _budget(before[walls == w], after[walls == w]) for w in WALL_CLASSES if (walls == w).any()}
        entry["by_span"] = {c: _budget(before[spans == c], after[spans == c])
                            for c in compare.SPAN_CLASSES if (spans == c).any()}
        summary[f"{case}-{state}" if case == "E" else case] = entry
    return summary


def _budget(coarse, fine) -> dict:
    keep = np.isfinite(coarse) & np.isfinite(fine)
    coarse, fine = coarse[keep], fine[keep]
    if not coarse.size:
        return dict(count=0)
    diff = np.abs(fine - coarse)
    changed = np.where(fine < LOW_SPEED, diff > LOW_SPEED_BUDGET, diff > RELATIVE_BUDGET * np.abs(fine))
    return dict(count=int(coarse.size), p95=float(np.percentile(diff, 95)), max=float(diff.max()),
                mean=float(diff.mean()), changed_fraction=float(changed.mean()),
                within_p95_budget=bool(np.percentile(diff, 95) < P95_BUDGET),
                mean_shift=float(np.mean(fine - coarse)))


SCORE_KEYS = ("count", "hit_rate", "fac2", "fb", "r", "spearman", "bias")


def scores(records: dict, quantities=("K",)) -> dict:
    """Pooled agreement scores per comparison (with a span breakdown), and the Case E change scores."""
    out = {}
    comparisons = compare.case_d(records, quantities) + compare.case_e_comparisons(records, quantities)
    by_name = {c.name: c for c in comparisons}
    for c in comparisons:
        s = c.scores()
        if s.get("count", 0) >= 3:
            out[c.name] = {k: s[k] for k in SCORE_KEYS}
            if "span" in c.strata:
                by_span = {cls: c.scores(c.strata["span"] == cls) for cls in compare.SPAN_CLASSES}
                out[c.name]["by_span"] = {cls: {k: s[k] for k in SCORE_KEYS if k in s} for cls, s in by_span.items()}
    before, after = by_name.get("E-before-thermistor-K"), by_name.get("E-after-thermistor-K")
    if before is not None and after is not None:
        out["E-change"] = metrics.change_scores(before.simulated, after.simulated, before.measured, after.measured)
    return out


def trend(coarse, middle, fine, threshold=0.02) -> dict:
    """Do the probes that still change on the last refinement keep the direction of the one before?

    Over probe values with |K(fine) - K(middle)| > ``threshold``: the fraction whose change has the
    sign of K(middle) - K(coarse), and the median ratio of the two changes. Asymptotic convergence
    would give a fraction near 1 and a ratio well below 1.
    """
    keys = sorted(set(coarse) & set(middle) & set(fine))
    if not keys:
        return dict(count=0)
    a, b, c = (np.concatenate([_k(records[key]) for key in keys]) for records in (coarse, middle, fine))
    first, last = b - a, c - b
    keep = np.isfinite(first) & np.isfinite(last) & (np.abs(last) > threshold)
    if not keep.any():
        return dict(count=0, threshold=threshold)
    return dict(count=int(keep.sum()), threshold=threshold,
                same_direction=float(np.mean(np.sign(first[keep]) == np.sign(last[keep]))),
                median_ratio=float(np.median(np.abs(last[keep]) / np.maximum(np.abs(first[keep]), 1e-12))))


def fallbacks(records: dict) -> dict:
    """Probes sampled at the nearest fluid centre instead of linearly, per case."""
    out = {}
    for (case, _, _), record in records.items():
        out[case] = out.get(case, 0) + sum(m != "linear" for m in record["probes"]["method"])
    return out


def subcell_gaps(polygons, resolutions) -> dict:
    """Pairs of separate footprints closer than one cell (but not touching), per resolution."""
    tree = STRtree(polygons)
    largest = max(resolutions)
    distances = []
    for i, polygon in enumerate(polygons):
        for j in tree.query(polygon, predicate="dwithin", distance=largest):
            if j > i:
                distances.append(shapely.distance(polygon, polygons[j]))
    distances = np.array(distances)
    return {f"{r:g}": int(np.sum((distances > 1e-6) & (distances < r))) for r in resolutions}


def subset_keys() -> set:
    return {(s.case, s.state, s.label) for s in campaigns.fine_subset(campaigns.FINE_RESOLUTION)}


def to_json(value):
    return json.loads(json.dumps(value, default=float))

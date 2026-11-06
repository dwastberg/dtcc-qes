"""Agreement metrics between simulated and measured values (AIJ_VALIDATION_PLAN.md, Metrics).

Every function takes paired arrays of any shape and uses only the pairs where
both values are finite; ``count`` reports how many that was.

- Hit rate (VDI 3783-9 / COST 732): a pair hits when |s - m| <= D·|m| or |s - m| <= W.
- FAC2: the fraction with 0.5 <= s/m <= 2.
- FB = (mean m - mean s) / (0.5 (mean m + mean s)): positive when the model underpredicts.
- NMSE = mean((m - s)^2) / (mean m · mean s).
"""

import numpy as np

D = 0.25  # relative tolerance of the hit rate
W = 0.05  # absolute tolerance in K; provisional (VDI 3783-9's own value to be confirmed)
W_SWEEP = (0.0, 0.02, 0.05, 0.08)
REFERENCE_HIT_RATE = 0.66  # the VDI 3783-9 / COST 732 acceptance line, drawn as a reference only


def _pairs(simulated, measured):
    s, m = np.asarray(simulated, dtype=np.float64).ravel(), np.asarray(measured, dtype=np.float64).ravel()
    keep = np.isfinite(s) & np.isfinite(m)
    return s[keep], m[keep]


def ranks(values) -> np.ndarray:
    """Ranks from 0, ties sharing their average rank (the measured values are quantised)."""
    values = np.asarray(values, dtype=np.float64)
    order = np.argsort(values, kind="mergesort")
    positions = np.empty(len(values))
    positions[order] = np.arange(len(values))
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    return (np.bincount(inverse, weights=positions) / counts)[inverse]


def spearman(a, b) -> float:
    """Spearman rank correlation over the pairs where both values are finite."""
    a, b = _pairs(a, b)
    if a.size < 3:
        return float("nan")
    return float(np.corrcoef(ranks(a), ranks(b))[0, 1])


def pearson(a, b) -> float:
    a, b = _pairs(a, b)
    if a.size < 3:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def hit_rate(simulated, measured, d: float = D, w: float = W) -> float:
    s, m = _pairs(simulated, measured)
    if not s.size:
        return float("nan")
    error = np.abs(s - m)
    return float(np.mean((error <= d * np.abs(m)) | (error <= w)))


def scores(simulated, measured, *, d: float = D, w: float = W) -> dict:
    """The standard set of agreement scores for one comparison."""
    s, m = _pairs(simulated, measured)
    out = dict(count=int(s.size))
    if s.size < 3:
        return out
    positive = m > 0
    out.update(
        hit_rate=hit_rate(s, m, d, w),
        hit_rate_sweep={f"{value:g}": hit_rate(s, m, d, value) for value in W_SWEEP},
        fac2=float(np.mean((s[positive] / m[positive] >= 0.5) & (s[positive] / m[positive] <= 2.0))),
        fb=float((m.mean() - s.mean()) / (0.5 * (m.mean() + s.mean()))),
        nmse=float(np.mean((m - s) ** 2) / (m.mean() * s.mean())),
        r=pearson(s, m), spearman=spearman(s, m),
        bias=float(np.mean(s - m)), mae=float(np.mean(np.abs(s - m))),
        rmse=float(np.sqrt(np.mean((s - m) ** 2))),
        mean_simulated=float(s.mean()), mean_measured=float(m.mean()))
    return out


def change_scores(sim_before, sim_after, exp_before, exp_after, *, threshold: float = 0.04,
                  top: int = 10) -> dict:
    """Agreement on the change K_after - K_before, arrays shaped (point, direction).

    ``sign_agreement`` uses the pairs whose measured change exceeds ``threshold``
    (two measurement steps in Case E). ``top_overlap`` is the mean fraction of
    the ``top`` windiest measured points per direction that are also among the
    ``top`` windiest simulated points, in the "after" state.
    """
    d_sim = np.asarray(sim_after, dtype=np.float64) - np.asarray(sim_before, dtype=np.float64)
    d_exp = np.asarray(exp_after, dtype=np.float64) - np.asarray(exp_before, dtype=np.float64)
    s, m = _pairs(d_sim, d_exp)
    clear = np.abs(m) > threshold
    overlaps = []
    for k in range(d_exp.shape[1]):
        sim, exp = np.asarray(sim_after, dtype=np.float64)[:, k], np.asarray(exp_after, dtype=np.float64)[:, k]
        keep = np.isfinite(sim) & np.isfinite(exp)
        if keep.sum() >= top:
            index = np.flatnonzero(keep)
            best_sim = set(index[np.argsort(-sim[keep], kind="mergesort")[:top]])
            best_exp = set(index[np.argsort(-exp[keep], kind="mergesort")[:top]])
            overlaps.append(len(best_sim & best_exp) / top)
    return dict(count=int(s.size), r=pearson(s, m), spearman=spearman(s, m), mae=float(np.mean(np.abs(s - m))),
                bias=float(np.mean(s - m)), clear_changes=int(clear.sum()),
                sign_agreement=float(np.mean(np.sign(s[clear]) == np.sign(m[clear]))) if clear.any() else None,
                top_overlap=float(np.mean(overlaps)) if overlaps else None)


def angle_error(simulated_uv, measured_uv) -> np.ndarray:
    """Angle in degrees, in [0, 180], between horizontal vectors (n, 2); NaN where either is invalid."""
    s, m = np.asarray(simulated_uv, dtype=np.float64), np.asarray(measured_uv, dtype=np.float64)
    a = np.degrees(np.arctan2(s[:, 1], s[:, 0]) - np.arctan2(m[:, 1], m[:, 0]))
    return np.abs((a + 180.0) % 360.0 - 180.0)



def paired_scores(before, after, measured, options=None):
    a, b, m = [np.asarray(v, dtype=float) for v in (before, after, measured)]
    if a.shape != b.shape or a.shape != m.shape:
        raise ValueError("Paired scores require identical observation shapes")
    baseline = np.isfinite(a) & np.isfinite(m)
    candidate = np.isfinite(b) & np.isfinite(m)
    common = baseline & candidate
    old, new = [scores(v[common], m[common], **(options or {})) for v in (a,b)]
    return dict(baseline_count=int(baseline.sum()), candidate_count=int(candidate.sum()), common_count=int(common.sum()),
        lost=int(np.sum(baseline & ~candidate)), gained=int(np.sum(candidate & ~baseline)),
        baseline=old, candidate=new,
        mae_change_percent=None if old.get("mae", 0.) == 0 else 100*(new["mae"]/old["mae"]-1))

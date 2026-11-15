"""Frozen scoring protocol of ACCURACY_IMPROVEMENT_PLAN.md (I0).

Scores: q (hit rate, D = 0.25, W = 0.05), FAC2, R (Pearson), rho (Spearman), FB, bias, MAE, and the
contrast statistics r = SD(sim)/SD(meas), r², b = R/r (slope of measured on simulated).
Intervals: 95 % percentile bootstrap over spatial probe groups and, where there are at least
``MIN_DIRECTIONS`` of them, direction groups. Seed and replicate count are frozen here.
Candidate and parent are compared through paired differences on the same resamples.
"""
import numpy as np

import common
from aij import metrics

REPLICATES = 2000
MIN_DIRECTIONS = 5  # fewer directions are not resampled; the interval then covers probe sampling only
MIN_GROUPS = 10  # fewer probe groups: inference is marked inconclusive
METRICS = ("q", "fac2", "R", "rho", "FB", "bias", "MAE", "r", "b")
LOWER_IS_BETTER = ("MAE",)


def stats(s, m, w=metrics.W, rank=True):
    """Scores of finite pairs; ``s`` and ``m`` are any equal shape."""
    s, m = np.asarray(s, float).ravel(), np.asarray(m, float).ravel()
    keep = np.isfinite(s) & np.isfinite(m)
    s, m = s[keep], m[keep]
    out = dict(n=int(s.size))
    if s.size < 3:
        return {**out, **{name: np.nan for name in METRICS}, "hits": 0}
    error = np.abs(s - m)
    hit = (error <= metrics.D * np.abs(m)) | (error <= w)
    positive = m > 0
    ratio = s[positive] / m[positive]
    sd_s, sd_m = s.std(), m.std()
    R = float(np.corrcoef(s, m)[0, 1]) if sd_s > 0 and sd_m > 0 else np.nan
    r = sd_s / sd_m if sd_m > 0 else np.nan
    out.update(q=float(hit.mean()), hits=int(hit.sum()), fac2=float(np.mean((ratio >= 0.5) & (ratio <= 2))),
               R=R, rho=metrics.spearman(s, m) if rank else np.nan,
               FB=float((m.mean() - s.mean()) / (0.5 * (m.mean() + s.mean()))), bias=float(np.mean(s - m)),
               MAE=float(error.mean()), r=float(r), b=float(R / r) if r and r > 0 else np.nan)
    return out


def resamples(groups, n_directions, replicates=REPLICATES, seed=common.SEED):
    """Yield (row index, column index) arrays: probe groups and direction groups drawn with replacement."""
    rng = np.random.default_rng(seed)
    groups = np.asarray(groups)
    labels = np.unique(groups)
    members = [np.flatnonzero(groups == g) for g in labels]
    for _ in range(replicates):
        rows = np.concatenate([members[i] for i in rng.integers(0, len(labels), len(labels))])
        cols = (rng.integers(0, n_directions, n_directions) if n_directions >= MIN_DIRECTIONS
                else np.arange(n_directions))
        yield rows, cols


def interval(function, groups, n_directions, **options):
    """Point value and 95 % interval of ``function(rows, cols) -> dict`` under the frozen resampling."""
    n = len(np.asarray(groups))
    point = function(np.arange(n), np.arange(n_directions))
    draws = {name: [] for name in point}
    for rows, cols in resamples(groups, n_directions, **options):
        for name, value in function(rows, cols).items():
            draws[name].append(value)
    out = {}
    for name, value in point.items():
        sample = np.asarray(draws[name], float)
        finite = sample[np.isfinite(sample)]
        low, high = (np.percentile(finite, [2.5, 97.5]) if finite.size > 0.9 * sample.size else (np.nan, np.nan))
        out[name] = (float(value), float(low), float(high))
    return out


def conclusive(groups):
    return len(np.unique(groups)) >= MIN_GROUPS


def scored(sim, measured, groups, mask=None, rank=False, **options):
    """Scores with intervals of one simulated array against the measurements."""
    if mask is not None:
        sim = np.where(mask, sim, np.nan)

    def function(rows, cols):
        result = stats(sim[np.ix_(rows, cols)], measured[np.ix_(rows, cols)], rank=rank)
        return {name: result[name] for name in METRICS if name != "rho" or rank}
    return interval(function, groups, sim.shape[1], **options)


def paired(candidate, parent, measured, groups, mask=None, **options):
    """Candidate minus parent, per metric, on the same resampled groups and the common finite mask."""
    common_mask = np.isfinite(candidate) & np.isfinite(parent) & np.isfinite(measured)
    if mask is not None:
        common_mask &= mask
    c, p = np.where(common_mask, candidate, np.nan), np.where(common_mask, parent, np.nan)

    def function(rows, cols):
        index = np.ix_(rows, cols)
        a, b = stats(c[index], measured[index], rank=False), stats(p[index], measured[index], rank=False)
        out = {name: a[name] - b[name] for name in METRICS if name != "rho"}
        out["abs_log_r"] = abs(np.log(a["r"])) - abs(np.log(b["r"])) if a["r"] > 0 and b["r"] > 0 else np.nan
        out["abs_bias"] = abs(a["bias"]) - abs(b["bias"])
        return out
    result = interval(function, groups, candidate.shape[1], **options)
    a, b = stats(c, measured), stats(p, measured)
    result["hits"] = (a["hits"] - b["hits"], a["n"])
    return result


def hit_transitions(candidate, parent, measured):
    """(gained, lost) hit counts on the common finite mask."""
    ok = np.isfinite(candidate) & np.isfinite(parent) & np.isfinite(measured)
    hit = lambda s: (np.abs(s - measured) <= metrics.D * np.abs(measured)) | (np.abs(s - measured) <= metrics.W)  # noqa: E731
    a, b = hit(candidate) & ok, hit(parent) & ok
    return int((a & ~b).sum()), int((b & ~a).sum())


# Reference rows -------------------------------------------------------------------------------------------

def linear_map(sim, measured, fit_sim=None, fit_measured=None):
    """a + b·K, fitted on (fit_sim, fit_measured); in-sample when those are omitted."""
    fs, fm = (sim, measured) if fit_sim is None else (fit_sim, fit_measured)
    fs, fm = np.asarray(fs, float).ravel(), np.asarray(fm, float).ravel()
    keep = np.isfinite(fs) & np.isfinite(fm)
    slope, intercept = np.polyfit(fs[keep], fm[keep], 1)
    return intercept + slope * sim, (float(intercept), float(slope))


def shrinkage(parent, candidate, measured, match_mean=False):
    """Matched-variance shrinkage of the parent: K̄ + s (K - K̄), with the candidate's variance.

    Mean and variances are taken over the pairs where parent, candidate and measurement are all finite.
    ``match_mean`` also moves the mean to the candidate's, so that a candidate cannot beat the comparator
    through a change of level alone.
    """
    ok = np.isfinite(parent) & np.isfinite(candidate) & np.isfinite(measured)
    mean = parent[ok].mean()
    s = candidate[ok].std() / parent[ok].std()
    return (candidate[ok].mean() if match_mean else mean) + s * (parent - mean), float(s)


def shrink_to(parent, measured, factor):
    ok = np.isfinite(parent) & np.isfinite(measured)
    mean = parent[ok].mean()
    return mean + factor * (parent - mean)


# Vector scores --------------------------------------------------------------------------------------------

def vector_stats(sim_velocity, measured_velocity):
    """Signed-component MAE and vector RMSE, both normalised by U_ref (inputs are already normalised).

    Components that were not measured (all NaN) are left out; a point enters the vector RMSE with the
    components measured there.
    """
    s, m = np.asarray(sim_velocity, float), np.asarray(measured_velocity, float)
    out = {}
    for i, name in enumerate("UVW"):
        ok = np.isfinite(s[..., i]) & np.isfinite(m[..., i])
        out[f"MAE_{name}"] = float(np.abs(s[..., i] - m[..., i])[ok].mean()) if ok.sum() >= 3 else np.nan
    square = np.where(np.isfinite(m) & np.isfinite(s), (s - m) ** 2, np.nan)
    any_ = np.isfinite(square).any(axis=-1)
    out["vector_RMSE"] = float(np.sqrt(np.nansum(square[any_], axis=-1).mean())) if any_.sum() >= 3 else np.nan
    return out


def sign_errors(sim_u, measured_u, clear=0.05):
    """Counts of streamwise sign errors where the measured |U|/U_ref exceeds ``clear``."""
    s, m = np.asarray(sim_u, float).ravel(), np.asarray(measured_u, float).ravel()
    ok = np.isfinite(s) & np.isfinite(m) & (np.abs(m) > clear)
    wrong = ok & (np.sign(s) != np.sign(m))
    reverse = ok & (m < 0)
    return dict(n=int(ok.sum()), wrong=int(wrong.sum()), measured_reverse=int(reverse.sum()),
                reverse_found=int((reverse & (s < 0)).sum()))


def fmt(value, digits=3):
    """'x [lo, hi]' of an (value, low, high) triple."""
    v, low, high = value
    if not np.isfinite(v):
        return "n/a"
    if not np.isfinite(low):
        return f"{v:.{digits}f}"
    return f"{v:.{digits}f} [{low:.{digits}f}, {high:.{digits}f}]"

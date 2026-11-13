"""Registered C1 climate and M2 assessment; no fitting and no native solves."""
from functools import lru_cache

import numpy as np
from dtcc_qes import comfort

SEED = 20261113
RESAMPLES = 4000
MODELS = (("wake 2 vector", 2, "K"), ("wake 2 + inflow k", 2, "K_scalar_inflow"),
          ("wake 3 vector", 3, "K"), ("wake 3 scalar", 3, "K_scalar_wake_rule"))


def m2(vector, scalar, approach):
    """Registered strict speed-up rule, with either missing input propagating."""
    vector, scalar = np.broadcast_arrays(np.asarray(vector, float), np.asarray(scalar, float))
    return np.where(np.isnan(vector) | np.isnan(scalar), np.nan,
                    np.where(vector > approach, np.maximum(vector, scalar), scalar))


def climate(directions, scale, dominant=None):
    counts = np.full(16, 9375 if dominant is None else 7000)
    if dominant is not None:
        counts[dominant] = 45000
    speeds = np.concatenate([scale * np.sqrt(-np.log1p(-(np.arange(n) + .5) / n)) for n in counts])
    return speeds, np.repeat(directions, counts)


def assess(fields, directions, scale, dominant=None):
    speeds, hours = climate(directions, scale, dominant)
    return comfort.assess(speeds, hours, fields.T, directions, 1., height=2.)


def levels(measured, directions):
    """Smallest 0.05 m/s scales reaching median classes B, C, D on discrete hours."""
    result = []
    for target in (1, 2, 3):
        lo, hi = 1, 800
        if np.median(assess(measured, directions, hi * .05).comfort) < target:
            raise ValueError("Climate level not bracketed")
        while lo < hi:
            mid = (lo + hi) // 2
            if np.median(assess(measured, directions, mid * .05).comfort) >= target:
                hi = mid
            else:
                lo = mid + 1
        result.append(round(lo * .05, 2))
    return result


def cost(predicted, measured):
    delta = predicted.astype(float) - measured
    return np.maximum(delta, 0) + 3 * np.maximum(-delta, 0)


def rank_correlation(a, b):
    # Average ranks for ties, including zero empirical exceedance; log is monotone.
    def ranks(x):
        _, inverse, counts = np.unique(x, return_inverse=True, return_counts=True)
        return (np.cumsum(counts) - (counts + 1) / 2)[inverse]
    a, b = ranks(a), ranks(b)
    if np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def worst_rotation(differences):
    """Bootstrap paired probes, recomputing the maximum over rotations each time."""
    indices = np.random.default_rng(SEED).integers(0, differences.shape[1], (RESAMPLES, differences.shape[1]))
    samples = differences[:, indices].mean(axis=2).max(axis=0)
    return dict(T=float(differences.mean(axis=1).max()),
                interval_95=np.quantile(samples, [.025, .975]).tolist())


def evaluate(measured, models, directions):
    measured = np.asarray(measured, float)
    if measured.shape != (80, 16) or len(np.unique(directions)) != 16:
        raise ValueError("C1 requires 80 aligned probes and 16 directions")
    if any(np.shape(x) != measured.shape or not np.isfinite(x).all() or np.any(x < 0)
           for x in [measured, *models.values()]):
        raise ValueError("C1 requires complete finite nonnegative fields; missing data cannot pass")
    out = []
    for scale in levels(measured, directions):
        assessments = {name: [assess(field, directions, scale, dominant) for dominant in [None, *range(16)]]
                       for name, field in {"measured": measured, **models}.items()}
        target = assessments["measured"]
        costs = {name: np.array([cost(p.comfort, t.comfort) for p, t in zip(rows, target)])
                 for name, rows in assessments.items()}
        baseline = costs["wake 2 vector"]
        rows = {}
        for name in models:
            p, t = assessments[name][0], target[0]
            difference = costs[name] - baseline
            delta = p.comfort.astype(float) - t.comfort
            rows[name] = dict(exact=float(np.mean(delta == 0)), optimistic=float(np.mean(delta < 0)),
                conservative=float(np.mean(delta > 0)), mean_absolute_class_error=float(np.mean(abs(delta))),
                spearman=rank_correlation(p.exceedance[5.], t.exceedance[5.]),
                missed_danger=int(np.sum((t.safety > 0) & (p.safety == 0))),
                false_danger=int(np.sum((t.safety == 0) & (p.safety > 0))),
                danger_probes=int(np.sum(t.safety > 0)),
                mean_cost=costs[name].mean(axis=1).tolist(),
                cost_difference=difference.mean(axis=1).tolist(),
                worst_rotation=worst_rotation(difference[1:]),
                comfort_classes=p.comfort.tolist(), safety_classes=p.safety.tolist())
        ref = rows["wake 2 vector"]
        for row in rows.values():
            row["comfort_gates"] = dict(cost=row["worst_rotation"]["interval_95"][1] < 0,
                safety=row["missed_danger"] <= ref["missed_danger"], exact=row["exact"] > ref["exact"])
        out.append(dict(scale=scale, models=rows, measured_comfort=target[0].comfort.tolist(),
                        measured_safety=target[0].safety.tolist(), warnings=list(target[0].warnings)))
    return out


def report(records):
    from . import compare, runner, tables
    output = dict(seed=SEED, resamples=RESAMPLES, hours=150000, a_opt=3,
                  status="complete", states={})
    for state in ("before", "after"):
        measurement = tables.load_results_e(state)
        models, keys = {}, {}
        for label in measurement.labels:
            pair = [records[w].get(("E", state, label, 2.)) for w in (2, 3)]
            if any(r is None for r in pair):
                raise ValueError(f"C1 missing paired run: {state} {label}")
            left, right = pair
            specs = [{k: v for k, v in r["spec"].items() if k != "parameterizations"} for r in pair]
            if specs[0] != specs[1] or left["profile"] != right["profile"]:
                raise ValueError("M2 requires identical run settings apart from wake")
            for name in ("xyz", "sampled"):
                if not np.allclose(np.asarray(left["probes"][name], float),
                                   np.asarray(right["probes"][name], float), equal_nan=True):
                    raise ValueError("M2 requires the same sampled points")
            if left["probes"]["method"] != right["probes"]["method"]:
                raise ValueError("M2 requires the same sampling method")
        for name, wake, quantity in MODELS:
            recs = {(c, s, l): r for (c, s, l, res), r in records[wake].items() if res == 2.}
            models[name], keys[name] = compare._matrix(recs, "E", state, measurement.labels, quantity, measurement.ids)
        recs = {(c, s, l): r for (c, s, l, res), r in records[3].items() if res == 2.}
        models["wake 3 Gaussian mean"], keys["wake 3 Gaussian mean"] = compare._matrix(
            recs, "E", state, measurement.labels, "K_gaussian_mean", measurement.ids)
        table = runner._tables("E")[0]
        heights = measurement.xyz[:, 2]
        # Same log-height interpolation as the declared validation inflow profile.
        record = next((r for (c, s, l, res), r in records[2].items() if c == "E" and s == state and res == 2.), None)
        if record is None:
            raise ValueError(f"C1 missing Case E {state} records")
        approach = np.interp(np.log(heights), np.log(table.heights), table.speeds) / record["profile"]["reference_speed"]
        models["M2"] = m2(models["wake 2 vector"], models["wake 3 scalar"], approach[:, None])
        output["states"][state] = dict(probe_ids=measurement.ids.tolist(), directions=measurement.directions.tolist(),
            run_keys=keys, source_identities={r["key"]: r["native"] for wake in (2, 3)
                for (c, st, label, res), r in records[wake].items() if c == "E" and st == state and res == 2.},
            approach=approach.tolist(), levels=evaluate(measurement.values, models, measurement.directions))
    return output


@lru_cache(maxsize=4)
def _quadrature(order):
    nodes, weights = np.polynomial.legendre.leggauss(order)
    return (nodes+1)/2, weights/2


def gaussian_mean_speed(velocity, tke, order=128):
    """E|U| for diagonal Gaussian fluctuations in the horizontal mean-flow frame.

    Standard deviations have ratios 2.4:1.9:1.25; their squared sum is 2k.
    Laplace-transform quadrature reduces the expectation to one dimension.
    NaN support propagates. This is a sensitivity estimate, not a criterion.
    """
    velocity, tke = np.asarray(velocity, float), np.asarray(tke, float)
    if velocity.shape != (*tke.shape, 3) or np.any(tke < 0):
        raise ValueError("Expected (..., 3) velocities and nonnegative matching TKE")
    mean = np.stack([np.hypot(velocity[..., 0], velocity[..., 1]), np.zeros_like(tke), velocity[..., 2]], axis=-1)
    rms = np.sqrt(np.sum(mean**2, axis=-1) + 2*tke)
    scale = np.where(rms > 0, rms, 1.)
    mu2 = (mean / scale[..., None])**2
    ratios = np.array([2.4, 1.9, 1.25])**2
    variance = (2*tke / scale**2)[..., None] * ratios / ratios.sum()
    nodes, weights = _quadrature(order)
    result = np.zeros_like(tke)
    for x, w in zip(nodes, weights):
        t = (x/(1-x))**2
        denominator = 1+2*t*variance
        log_laplace = -.5*np.log(denominator).sum(axis=-1) - (t*mu2/denominator).sum(axis=-1)
        result += w*(-np.expm1(log_laplace))/(np.sqrt(np.pi)*x*x)
    return np.where(tke == 0, np.linalg.norm(velocity, axis=-1), result*scale)

"""Tower scoring contract (ACCURACY_IMPROVEMENT_PLAN.md, I0) for Case E, and its Case C counterpart (I4).

Distance is the horizontal distance to the after-state tower footprint (Case E) or to the central
block footprint (Case C), used for every state. States are matched by probe id and direction on a
common finite mask of the measurements and of every simulated array passed in. Each probe's value
is its equal-weight mean over the common directions; a bin value is the equal-weight mean over probes.
"""
import numpy as np
import shapely

import score
from aij import cityutil, conventions, runner

E_BINS = ((0, 15), (15, 30), (0, 30), (30, 60), (60, 120), (120, np.inf), (60, np.inf))
C_BINS = ((0, 15), (15, 30), (30, np.inf))  # m from the central 20 m block; the array edge is 40 m away


def e_tower():
    before = cityutil.footprints(runner.city("E", "before"))
    after = cityutil.footprints(runner.city("E", "after"))
    union = shapely.unary_union([p for _, p, _ in before])
    new = [(p, h) for _, p, h in after if p.difference(union.buffer(0.5)).area > 0.5 * p.area]
    return max(new, key=lambda item: item[1])


def c_centre():
    return shapely.box(-10, -10, 10, 10)


def distance(xy, polygon):
    return np.array([shapely.Point(*p).distance(polygon) for p in xy])


def sectors(xy, centre, directions):
    """(point, direction) labels: upwind if a < -c, downwind if a > c, beside otherwise (disjoint)."""
    flow = conventions.flow_vector(directions)
    rel = np.asarray(xy)[:, None, :] - np.asarray(centre)[None, None, :]
    along = (rel * flow[None]).sum(-1)
    cross = np.abs(rel[..., 0] * flow[None, :, 1] - rel[..., 1] * flow[None, :, 0])
    return np.where(along < -cross, "upwind", np.where(along > cross, "downwind", "beside"))


def _probe_mean(values, mask):
    with np.errstate(invalid="ignore"):
        return np.where(mask, values, 0).sum(1) / mask.sum(1)


def table(dist, measured, simulated, bins, mask=None, replicates=score.REPLICATES):
    """Per bin: probes, pairs, and the means of state a, state b and the paired change b - a.

    ``measured`` and ``simulated`` are (a, b) pairs of (point, direction) arrays. Intervals: frozen
    bootstrap over probes and (with enough of them) directions; the rows are the probes of the bin.
    """
    common = np.isfinite(measured[0]) & np.isfinite(measured[1]) & np.isfinite(simulated[0]) & np.isfinite(simulated[1])
    if mask is not None:
        common &= mask
    rows_out = []
    for low, high in bins:
        inside = np.flatnonzero((dist >= low) & (dist < high) & common.any(1))
        if not len(inside):
            rows_out.append(dict(bin=(low, high), probes=0))
            continue
        arrays = [a[inside] for a in (*measured, *simulated)]
        ok = common[inside]

        def function(rows, cols):
            index = np.ix_(rows, cols)
            m = ok[index]
            keep = m.any(1)
            ma, mb, sa, sb = (np.nanmean(_probe_mean(a[index], m)[keep]) for a in arrays)
            return dict(measured_a=ma, measured_b=mb, sim_a=sa, sim_b=sb, error_a=sa - ma, error_b=sb - mb,
                        measured_change=mb - ma, sim_change=sb - sa, change_error=(sb - sa) - (mb - ma))
        result = score.interval(function, np.arange(len(inside)), ok.shape[1], replicates=replicates)
        rows_out.append(dict(bin=(low, high), probes=len(inside), pairs=int(ok.sum()),
                             conclusive=len(inside) >= score.MIN_GROUPS, **result))
    return rows_out


def render(rows, a="before", b="after"):
    lines = [f"| Distance [m] | Probes (pairs) | Measured {a} → {b} | Simulated {a} → {b} | Error {a} | Error {b} | "
             f"Measured Δ | Simulated Δ | Δ error |", "|---|---|---|---|---|---|---|---|---|"]
    for row in rows:
        low, high = row["bin"]
        label = f"{low:g}–{high:g}" if np.isfinite(high) else f"≥{low:g}"
        if not row["probes"]:
            lines.append(f"| {label} | 0 | | | | | | | |")
            continue
        g = lambda name: row[name][0]  # noqa: E731
        note = "" if row["conclusive"] else " †"
        lines.append(f"| {label} | {row['probes']} ({row['pairs']}){note} | {g('measured_a'):.3f} → {g('measured_b'):.3f} | "
                     f"{g('sim_a'):.3f} → {g('sim_b'):.3f} | {score.fmt(row['error_a'])} | {score.fmt(row['error_b'])} | "
                     f"{g('measured_change'):+.3f} | {g('sim_change'):+.3f} | {score.fmt(row['change_error'])} |")
    return "\n".join(lines)

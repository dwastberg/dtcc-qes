"""Phase 5: what one change does to the probes and the scores, and the tuning objective.

A variant is compared with the base on the runs both have, so a Case E-only
variant is scored against the Case E base. The tuning objective is fixed in
AIJ_VALIDATION_PLAN.md (Phase 5, part B): the pooled hit rate q of K on Case E
"before", ties within ``TIE`` broken by Spearman ρ.
"""

import copy
from dataclasses import replace
from pathlib import Path

import numpy as np

from . import compare, gridstudy, metrics

COMPARISONS = ("E-before-thermistor-K", "E-after-thermistor-K", "D-split_fibre", "D-thermistor-K")
TIE = 0.01  # hit-rate differences below this are ties, and the least a tuning step must gain


def common(base: dict, variant: dict) -> tuple[dict, dict]:
    keys = set(base) & set(variant)
    return {k: base[k] for k in keys}, {k: variant[k] for k in keys}


def effect(base: dict, variant: dict) -> dict:
    """Probe changes (per case and state) and the scores of both, on the runs both have."""
    base, variant = common(base, variant)
    out = dict(runs=len(base), changes=gridstudy.changes(base, variant),
               base=gridstudy.scores(base, ("K", "K_scalar")), variant=gridstudy.scores(variant, ("K", "K_scalar")))
    extras = [compare.split_fibre_extras(r) for r in (base, variant)]
    if all(e and "k" in e for e in extras):
        out["split_fibre_k"] = {name: {key: e["k"]["scores"][key] for key in ("fac2", "fb", "r", "mean_simulated")}
                                for name, e in zip(("base", "variant"), extras)}
    return out


def nearest(records: dict, runs: Path) -> dict:
    """Copies of ``records`` with K taken at the nearest cell centre of the stored 2 m plane."""
    out = {}
    for key, record in records.items():
        with np.load(Path(runs) / record["spec"]["case"] / f"{record['key']}.npz") as plane:
            x, y, velocity, valid = plane["x"], plane["y"], plane["velocity"], plane["valid"]
            uref = float(plane["reference_speed"])
        if velocity.shape[:2] != (len(y), len(x)):
            raise ValueError("Unexpected plane layout")
        xyz = np.asarray(record["probes"]["xyz"], dtype=np.float64)
        ix = np.abs(x[None, :] - xyz[:, :1]).argmin(axis=1)
        iy = np.abs(y[None, :] - xyz[:, 1:2]).argmin(axis=1)
        k = np.linalg.norm(velocity[iy, ix].astype(np.float64), axis=1) / uref
        copied = copy.deepcopy(record)
        copied["probes"]["K"] = np.where(valid[iy, ix], k, np.nan).tolist()
        out[key] = copied
    return out


def neighbourhood_best(comparison: compare.Comparison, records: dict) -> compare.Comparison:
    """``comparison`` with each simulated K moved to the value closest to the measurement within
    max(1 m, dx) of the probe: the score a positional tolerance of one neighbourhood would allow."""
    low, _ = compare._matrix(records, comparison.case, comparison.state, comparison.labels, "K_min", comparison.ids)
    high, _ = compare._matrix(records, comparison.case, comparison.state, comparison.labels, "K_max", comparison.ids)
    return replace(comparison, simulated=np.clip(comparison.measured, low, high))


def objective(records: dict) -> dict:
    """The tuning objective on the Case E "before" runs in ``records``."""
    training = {k: v for k, v in records.items() if k[:2] == ("E", "before")}
    comparison = next(c for c in compare.case_e_comparisons(training, ("K",)) if c.state == "before")
    scores = comparison.scores()
    return dict(q=scores["hit_rate"], rho=scores["spearman"], fb=scores["fb"], r=scores["r"],
                count=scores["count"], directions=int(np.isfinite(comparison.simulated).any(axis=0).sum()))


def choose(rows: list[dict]) -> dict:
    """The best candidate: highest q, and among those within ``TIE`` of it the highest ρ."""
    best_q = max(row["objective"]["q"] for row in rows)
    tied = [row for row in rows if row["objective"]["q"] >= best_q - TIE]
    return max(tied, key=lambda row: (row["objective"]["rho"], row["objective"]["q"]))


def accepted(current: dict, best: dict) -> bool:
    return best["objective"]["q"] >= current["q"] + TIE


def summary(scores: dict) -> dict:
    """The headline scores of the Phase 5 comparisons, from ``gridstudy.scores``."""
    out = {name: {k: scores[name][k] for k in ("count", "hit_rate", "fac2", "fb", "r", "spearman")}
           for name in COMPARISONS if name in scores}
    if "E-change" in scores:
        out["E-change"] = {k: scores["E-change"][k] for k in ("r", "spearman", "sign_agreement", "top_overlap", "bias")}
    return out


def scores_of(comparisons) -> dict:
    return {c.name: metrics.scores(c.simulated, c.measured) for c in comparisons}


UPSTREAM_DISTANCE = 25.0  # m: cells this far from every building and upwind of all of them are "approach flow"


def upstream_turbulence(records: dict, runs: Path, polygons, inflow_table, min_distance=UPSTREAM_DISTANCE) -> dict:
    """QES-Turb k at 2 m in the undisturbed approach flow against the inflow table (R11 diagnostic).

    Cells qualify when they are at least ``min_distance`` from every footprint and upwind of
    every footprint vertex. k is normalised by each run's reference speed, as the table is by
    the approach flow at the reference height.
    """
    import shapely
    from .conventions import flow_vector
    from .inflow import measured_profile, reference_speed
    union = shapely.union_all(polygons)
    vertices = np.vstack([np.asarray(p.exterior.coords) for p in polygons])
    values = []
    for record in records.values():
        with np.load(Path(runs) / record["spec"]["case"] / f"{record['key']}.npz") as plane:
            if "k" not in plane.files:
                continue
            x, y, k, valid = plane["x"], plane["y"], plane["k"], plane["valid"]
            uref = float(plane["reference_speed"])
        gx, gy = np.meshgrid(x, y)
        towards = flow_vector(record["spec"]["direction"])
        along = gx * towards[0] + gy * towards[1]
        upwind = along < (vertices @ towards).min()
        far = shapely.distance(shapely.points(np.c_[gx.ravel(), gy.ravel()]), union).reshape(gx.shape) >= min_distance
        pick = upwind & far & valid & np.isfinite(k)
        values.append(k[pick] / uref ** 2)
    values = np.concatenate(values) if values else np.array([])
    approach = measured_profile(inflow_table, 0.0)
    table = float(np.interp(2.0, inflow_table.heights, inflow_table.k)) / reference_speed(approach) ** 2
    if not values.size:
        return dict(cells=0, table=table)
    return dict(cells=int(values.size), median=float(np.median(values)), p10=float(np.percentile(values, 10)),
                p90=float(np.percentile(values, 90)), table=table, ratio=float(np.median(values) / table))

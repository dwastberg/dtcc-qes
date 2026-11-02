"""Pair simulated probe values with the AIJ measurements (AIJ_VALIDATION_PLAN.md, Phase 3).

A Comparison holds simulated and measured values shaped (point, direction) on
the same probe ids and direction order, plus the per-point strata. Simulated
K values are the run records' speed ratios (each normalised by its own inflow
at the reference height); ``K_scalar`` adds the QES-Turb k: √(|U|² + 2k)/U_ref.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely

from . import case_e, cityutil, metrics, tables
from .runspec import RunSpec

WALL_BINS = (2.0, 5.0)  # m: near (< 2), mid, far (> 5)
K_BINS = (0.2, 0.6)
SLAB_DISTANCE = 5.0  # m: a Case E probe this close to an elevated slab (in plan) is "slab-adjacent"
# K range within max(1 m, dx) of the probe. A large span marks a sharp local feature, where
# probes change most under grid refinement (AIJ_VALIDATION.md, Phase 4).
SPAN_BINS = (0.05, 0.15)
SPAN_CLASSES = ("span <0.05", "span 0.05-0.15", "span >0.15")


@dataclass
class Comparison:
    name: str  # e.g. "E-after-thermistor"
    case: str
    state: str
    instrument: str  # "split_fibre" or "thermistor"
    quantity: str  # simulated quantity: "K" (mean vector) or "K_scalar"
    labels: tuple
    directions: np.ndarray
    ids: np.ndarray
    simulated: np.ndarray  # (point, direction)
    measured: np.ndarray  # (point, direction)
    strata: dict = field(default_factory=dict)  # name -> (point, direction) array of labels
    records: list = field(default_factory=list)  # run keys, in direction order

    def scores(self, mask=None, **options) -> dict:
        s, m = self.simulated, self.measured
        if mask is not None:
            s, m = np.where(mask, s, np.nan), np.where(mask, m, np.nan)
        return metrics.scores(s, m, **options)


def load_records(runs: Path, specs) -> dict:
    """Run records for ``specs`` keyed by (case, state, label); missing runs are left out."""
    out = {}
    for spec in specs:
        path = Path(runs) / spec.case / f"{spec.key}.json"
        if path.exists():
            out[(spec.case, spec.state, spec.label)] = json.loads(path.read_text())
    return out


def _matrix(records, case, state, labels, quantity, ids):
    columns, keys = [], []
    for label in labels:
        record = records.get((case, state, label))
        if record is None:
            columns.append(np.full(len(ids), np.nan))
            keys.append(None)
            continue
        probes = record["probes"]
        if list(probes["ids"]) != list(ids):
            raise ValueError(f"Probe ids of run {record['key']} differ from the measurements")
        columns.append(np.array([np.nan if v is None else v for v in probes[quantity]], dtype=np.float64))
        keys.append(record["key"])
    return np.column_stack(columns), keys


def _bins(values, edges, names):
    out = np.full(np.shape(values), names[-1], dtype=object)
    for edge, name in reversed(list(zip(edges, names))):
        out[np.asarray(values) < edge] = name
    return out


def span_classes(span):
    span = np.asarray(span, dtype=np.float64)
    return np.where(np.isfinite(span), _bins(np.nan_to_num(span), SPAN_BINS, SPAN_CLASSES), None)


def _span(records, case, state, labels, ids) -> dict:
    """The span stratum (point, direction), or nothing when the records carry no neighbourhood."""
    present = [r for k, r in records.items() if k[:2] == (case, state)]
    if not present or not all("K_max" in r["probes"] for r in present):
        return {}
    high, _ = _matrix(records, case, state, labels, "K_max", ids)
    low, _ = _matrix(records, case, state, labels, "K_min", ids)
    return dict(span=span_classes(high - low))


def _strata(measured, wall, extra=None) -> dict:
    shape = measured.shape
    wall_class = _bins(wall, WALL_BINS, ("wall <2 m", "wall 2-5 m", "wall >5 m"))
    strata = dict(wall=np.broadcast_to(wall_class[:, None], shape),
                  speed=np.where(np.isfinite(measured), _bins(np.nan_to_num(measured), K_BINS,
                                                              ("K <0.2", "K 0.2-0.6", "K >0.6")), None))
    if extra:
        strata.update(extra)
    return strata


def slab_distance(points_xy, city) -> np.ndarray:
    """Plan distance from each point to the nearest elevated slab (Case E arcades, canopies, pilotis)."""
    polygons = [polygon for _, polygon, _, _ in cityutil.elevated_footprints(city)]
    return shapely.distance(shapely.points(np.asarray(points_xy)), shapely.union_all(polygons))


def case_d(records: dict, quantities=("K", "K_scalar")) -> list[Comparison]:
    """Split fibre (0°, vector speed and k) and thermistor (3 directions, scalar speed)."""
    exp_s, exp_t = tables.load_exp_s(), tables.load_exp_t()
    out = []
    any_record = next((r for k, r in records.items() if k[0] == "D"), None)
    if any_record is None:
        return out
    wall = np.array(any_record["probes"]["wall_distance"], dtype=np.float64)
    sim, keys = _matrix(records, "D", "-", exp_t.labels[:1], "K", exp_s.ids)
    out.append(Comparison("D-split_fibre", "D", "-", "split_fibre", "K", exp_t.labels[:1], exp_t.directions[:1],
                          exp_s.ids, sim, exp_s.speed_ratio[:, None],
                          _strata(exp_s.speed_ratio[:, None], wall, _span(records, "D", "-", exp_t.labels[:1], exp_s.ids)),
                          keys))
    mirrored = np.where(exp_t.mirrored, "mirrored copy", "measured")
    span = _span(records, "D", "-", exp_t.labels, exp_t.ids)
    for quantity in quantities:
        sim, keys = _matrix(records, "D", "-", exp_t.labels, quantity, exp_t.ids)
        out.append(Comparison(f"D-thermistor-{quantity}", "D", "-", "thermistor", quantity, exp_t.labels,
                              exp_t.directions, exp_t.ids, sim, exp_t.values,
                              _strata(exp_t.values, wall, dict(mirror=mirrored, **span)), keys))
    return out


def case_e_comparisons(records: dict, quantities=("K", "K_scalar")) -> list[Comparison]:
    out = []
    for state in ("before", "after"):
        measurements = tables.load_results_e(state)
        any_record = next((r for k, r in records.items() if k[:2] == ("E", state)), None)
        if any_record is None:
            continue
        wall = np.array(any_record["probes"]["wall_distance"], dtype=np.float64)
        slab = slab_distance(measurements.xyz[:, :2], case_e.build_case_e(state).city)
        slab_class = np.where(slab < SLAB_DISTANCE, "slab-adjacent", "open")
        extra = dict(slab=np.broadcast_to(slab_class[:, None], measurements.values.shape),
                     **_span(records, "E", state, measurements.labels, measurements.ids))
        for quantity in quantities:
            sim, keys = _matrix(records, "E", state, measurements.labels, quantity, measurements.ids)
            out.append(Comparison(f"E-{state}-thermistor-{quantity}", "E", state, "thermistor", quantity,
                                  measurements.labels, measurements.directions, measurements.ids, sim,
                                  measurements.values, _strata(measurements.values, wall, extra), keys))
    return out


def instrument_ceiling() -> dict:
    """How well the split-fibre probe's own values match the thermistor at Case D 0°.

    The mean vector speed is what an exact mean-flow model would give; its scores
    against the thermistor bound what any K_vec comparison with thermistor data
    can reach. √(|U|² + 2k) is the measured counterpart of K_scalar.
    """
    exp_s, exp_t = tables.load_exp_s(), tables.load_exp_t()
    m = exp_s.measured
    thermistor = exp_t.values[m, 0]
    vector = exp_s.speed_ratio[m]
    scalar = np.sqrt(vector ** 2 + 2 * exp_s.k[m] / tables.U_H ** 2)
    return dict(vector=metrics.scores(vector, thermistor), scalar=metrics.scores(scalar, thermistor))


def split_fibre_extras(records: dict) -> dict | None:
    """Case D 0°: flow-direction error and k against the split-fibre probe at its 33 points."""
    record = records.get(("D", "-", "0 deg."))
    if record is None:
        return None
    exp_s = tables.load_exp_s()
    m = exp_s.measured
    probes = record["probes"]
    velocity = np.array(probes["velocity"], dtype=np.float64)
    angle = metrics.angle_error(velocity[m, :2], exp_s.velocity[m, :2])
    out = dict(angle_error=dict(median=float(np.nanmedian(angle)), p90=float(np.nanpercentile(angle, 90)),
                                within_30=float(np.nanmean(angle <= 30)), values=angle.tolist()))
    if "k" in probes:
        uref = record["profile"]["reference_speed"]
        k_sim = np.array([np.nan if v is None else v for v in probes["k"]], dtype=np.float64)[m] / uref ** 2
        k_exp = exp_s.k[m] / tables.U_H ** 2
        # No absolute tolerance: k/U² is about 0.02, so W = 0.05 would accept everything.
        out["k"] = dict(scores=metrics.scores(k_sim, k_exp, w=0.0), simulated=k_sim.tolist(), measured=k_exp.tolist())
    return out


def inflow_ratio(case: str) -> float:
    """Approach-flow speed at the probe height over its speed at the reference height (baseline profile).

    A probe that no building parameterisation reaches keeps this K in dtcc-qes,
    because the profile initialises the whole domain.
    """
    from .grids import PROBE_HEIGHT
    from .inflow import measured_profile, reference_speed
    data = tables.load_inflow_d() if case == "D" else tables.load_inflow_e()
    profile = measured_profile(data, 0.0)
    return reference_speed(profile, PROBE_HEIGHT) / reference_speed(profile)


def background_fraction(values, ratio: float, tolerance: float = 0.03) -> float:
    """Fraction of finite values within ``tolerance`` of the approach-flow ratio."""
    values = np.asarray(values, dtype=np.float64).ravel()
    values = values[np.isfinite(values)]
    return float(np.mean(np.abs(values - ratio) <= tolerance)) if values.size else float("nan")


def baseline_specs(resolution: float = 2.0) -> list[RunSpec]:
    from .campaigns import baseline
    return baseline(resolution)

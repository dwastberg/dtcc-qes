"""Pair simulated probe values with the AIJ measurements (AIJ_VALIDATION_PLAN.md, Phase 3).

A Comparison holds simulated and measured values shaped (point, direction) on
the same probe ids and direction order, plus the per-point strata. Simulated
K values are the run records' speed ratios (each normalised by its own inflow
at the reference height); ``K_scalar`` adds the QES-Turb k: √(|U|² + 2k)/U_ref.

Cases A and B (``isolated``) compare the mean vector itself: its magnitude, its
streamwise and vertical components and k, all normalised by U_H (AIJ_AB_VALIDATION.md).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import shapely

from . import case_ab, case_e, cityutil, metrics, tables
from .conventions import AB_LABEL
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
    options: dict = field(default_factory=dict)  # metrics.scores options of this quantity (k: w = 0)

    def scores(self, mask=None, **options) -> dict:
        s, m = self.simulated, self.measured
        if mask is not None:
            s, m = np.where(mask, s, np.nan), np.where(mask, m, np.nan)
        return metrics.scores(s, m, **{**self.options, **options})


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


# Cases A and B ------------------------------------------------------------------------------------------

AB_QUANTITIES = ("K", "U", "W", "k")  # |(U, V, W)|/U_H, U/U_H, W/U_H and k/U_H²
# Published values, in b: wake reattachment X_F behind the leeward face near the ground (experiment and
# model ranges) and Case A's roof reattachment X_R from the windward edge. Tominaga et al. 2004 (JAABE 3,
# Tables 1-2), Mochida et al. 2002, Shirasawa et al. 2003; AIJ_AB_VALIDATION.md, F6.
LITERATURE = {
    "A": dict(wake_experiment=1.42, roof_experiment=0.52, wake_standard_k_epsilon=(1.66, 2.70),
              wake_revised_k_epsilon=(2.70, 3.34), wake_les=(1.02, 2.10)),
    "B": dict(wake_experiment=7.6, wake_standard_k_epsilon=(9.2, 11.6), wake_revised_k_epsilon=(9.2, 13.6),
              wake_les=(7.6, 7.6)),
}
QUANTITY_LABELS = {"K": "|U|/U_H", "U": "U/U_H", "W": "W/U_H", "k": "k/U_H²"}
CLEAR_SIGN = 0.05  # |U|/U_H above which the sign of the streamwise component counts
# The Case B sheet's V is positive toward -y: as tabulated, the flow 1.6 m outside the side face runs into
# the wall at 0.7 U_H, and V correlates with the simulated V at -0.81 (Case A: +0.89). This is an
# inference (AIJ_AB_VALIDATION.md, F5); ``tables`` keeps the sheet values, the comparisons negate them.
LATERAL_SIGN = {"A": 1.0, "B": -1.0}
FLOW_CLASSES = ("reverse", "near zero", "forward")


def _float(values) -> np.ndarray:
    """A record's numbers, possibly nested, as float64: the None that JSON stores for NaN becomes NaN again."""
    return np.array(values, dtype=np.float64)


def _ab_fields(velocity, k) -> dict:
    """The compared quantities from velocity (n, 3) and k (n,), both already normalised."""
    return dict(K=np.linalg.norm(velocity, axis=1), U=velocity[:, 0], W=velocity[:, 2], k=k)


def ab_velocity(case: str) -> np.ndarray:
    """The measured mean velocity (n, 3) in m/s, with V in the +y convention (``LATERAL_SIGN``)."""
    return tables.load_results_ab(case).velocity * np.array([1.0, LATERAL_SIGN[case], 1.0])


def ab_measured(case: str) -> dict:
    """The AIJ values of the compared quantities, normalised by the tabulated U_H."""
    data = tables.load_results_ab(case)
    uh = data.reference["speed"]
    return _ab_fields(ab_velocity(case) / uh, data.k / uh ** 2)


def ab_simulated(record: dict) -> dict:
    """A run record's values of the compared quantities, normalised by its own inflow at H."""
    uref = record["profile"]["reference_speed"]
    probes = record["probes"]
    velocity = _float(probes["velocity"]) / uref
    k = _float(probes["k"]) / uref ** 2 if "k" in probes else np.full(len(velocity), np.nan)
    return _ab_fields(velocity, k)


def null_model(case: str) -> dict:
    """The undisturbed approach flow at every probe (no building): the reference any model should beat.

    Its K and U are the inflow profile at the probe height over U_H, W is zero, and
    k is the tabulated inflow k, interpolated in log height.
    """
    from .inflow import measured_profile, reference_speed
    data = tables.load_results_ab(case)
    table = tables.load_inflow_ab(case)
    profile = measured_profile(table, 270.0)
    speed = np.array([reference_speed(profile, z) for z in data.xyz[:, 2]]) / reference_speed(profile)
    k = np.interp(np.log(data.xyz[:, 2]), np.log(table.heights), table.k) / table.reference["speed"] ** 2
    velocity = np.column_stack([speed, np.zeros_like(speed), np.zeros_like(speed)])
    return _ab_fields(velocity, k)


def flow_classes(u) -> np.ndarray:
    u = np.asarray(u, dtype=np.float64)
    return np.where(u < -CLEAR_SIGN, FLOW_CLASSES[0], np.where(u > CLEAR_SIGN, FLOW_CLASSES[2], FLOW_CLASSES[1]))


def ab_strata(case: str) -> dict:
    """Per-point strata of Case A or B: section, region, measured flow sense and 3D wall distance."""
    data = tables.load_results_ab(case)
    wall = case_ab.surface_distance(data.xyz, case)
    return dict(section=data.section.astype(object), region=case_ab.regions(data.xyz, case).astype(object),
                flow=flow_classes(ab_measured(case)["U"]).astype(object),
                wall=_bins(wall, WALL_BINS, ("wall <2 m", "wall 2-5 m", "wall >5 m")))


def isolated(records: dict, case: str, simulated: dict | None = None, name: str | None = None) -> list[Comparison]:
    """One Comparison per quantity (``AB_QUANTITIES``) over every measured point of Case A or B.

    ``simulated`` replaces the run record's values (e.g. ``null_model(case)``).
    """
    record = records.get((case, "-", AB_LABEL))
    if record is None and simulated is None:
        return []
    data = tables.load_results_ab(case)
    if record is not None and list(record["probes"]["ids"]) != list(data.ids):
        raise ValueError(f"Probe ids of run {record['key']} differ from the measurements")
    values = ab_simulated(record) if simulated is None else simulated
    measured = ab_measured(case)
    strata = {key: classes[:, None] for key, classes in ab_strata(case).items()}
    out = []
    for quantity in AB_QUANTITIES:
        out.append(Comparison(f"{name or case}-{quantity}", case, "-", tables.AB_INSTRUMENT[case], quantity,
                              (AB_LABEL,), np.array([data.direction]), data.ids, values[quantity][:, None],
                              measured[quantity][:, None], strata, [None if record is None else record["key"]],
                              dict(w=0.0) if quantity == "k" else {}))
    return out


def sign_scores(simulated_u, measured_u, mask=None) -> dict:
    """Agreement on the sense of the streamwise component where the measured |U|/U_H > ``CLEAR_SIGN``.

    ``reverse_recall``: measured reverse-flow points that are simulated as reverse flow;
    ``false_reverse``: measured forward-flow points simulated as reverse flow.
    """
    s, m = np.asarray(simulated_u, dtype=np.float64).ravel(), np.asarray(measured_u, dtype=np.float64).ravel()
    keep = np.isfinite(s) & np.isfinite(m) & (np.abs(m) > CLEAR_SIGN)
    if mask is not None:
        keep &= np.asarray(mask, dtype=bool).ravel()
    s, m = s[keep], m[keep]
    reverse, forward = m < 0, m > 0
    return dict(count=int(keep.sum()), reverse=int(reverse.sum()),
                agreement=float(np.mean(np.sign(s) == np.sign(m))) if keep.any() else None,
                reverse_recall=float(np.mean(s[reverse] < 0)) if reverse.any() else None,
                false_reverse=float(np.mean(s[forward] < 0)) if forward.any() else None)


def reattachment(x, u) -> float | None:
    """The last downstream zero crossing of u from reverse to forward flow, interpolated linearly.

    None when u is never negative, or never recovers.
    """
    x, u = np.asarray(x, dtype=np.float64), np.asarray(u, dtype=np.float64)
    keep = np.isfinite(u)
    x, u = x[keep], u[keep]
    negative = np.flatnonzero(u < 0)
    if not len(negative) or negative[-1] == len(u) - 1:
        return None
    i = negative[-1]
    return float(x[i] + (x[i + 1] - x[i]) * (-u[i]) / (u[i + 1] - u[i]))


def ab_reattachment(records: dict, case: str) -> dict:
    """Wake reattachment on the centreline at each stored height: measured (from the vertical
    section) and simulated, as distance behind the building in metres and in H.

    The measured value interpolates between two stations; ``bracket`` gives them.
    """
    data = tables.load_results_ab(case)
    measured = ab_measured(case)["U"]
    depth, _, height = case_ab.size(case)
    record = records.get((case, "-", AB_LABEL))
    out = {}
    for z in (record or {}).get("centreline", {}) or {f"{h:g}": None for h in _centreline_heights(case)}:
        pick = (data.section == "vertical") & np.isclose(data.xyz[:, 2], float(z)) & (data.xyz[:, 0] > depth / 2)
        order = np.argsort(data.xyz[pick, 0])
        x, u = data.xyz[pick, 0][order], measured[pick][order]
        crossing = reattachment(x, u)
        negative = np.flatnonzero(u < 0)
        bracket = (x[negative[-1]], x[negative[-1] + 1]) if len(negative) and negative[-1] < len(x) - 1 else None
        entry = dict(measured=None if crossing is None else crossing - depth / 2,
                     bracket=None if bracket is None else [b_ - depth / 2 for b_ in bracket])
        if record is not None:
            line = record["centreline"][z]
            simulated = reattachment(line["x"], _float(line["u"]))
            entry["simulated"] = None if simulated is None else simulated - depth / 2
        entry.update({f"{key}_H": None if entry.get(key) is None else entry[key] / height
                      for key in ("measured", "simulated")})
        out[z] = entry
    return out


def _centreline_heights(case):
    from .runner import CENTRELINE_HEIGHTS
    return CENTRELINE_HEIGHTS[case]


def ab_angle_error(records: dict, case: str) -> dict | None:
    """Horizontal flow-direction error at the horizontal-section points with a clear horizontal flow."""
    record = records.get((case, "-", AB_LABEL))
    if record is None:
        return None
    data = tables.load_results_ab(case)
    uh = data.reference["speed"]
    simulated, measured = _float(record["probes"]["velocity"]), ab_velocity(case)
    clear = (data.section != "vertical") & (np.hypot(measured[:, 0], measured[:, 1]) / uh > CLEAR_SIGN)
    angle = metrics.angle_error(simulated[clear, :2], measured[clear, :2])
    return dict(count=int(np.isfinite(angle).sum()), median=float(np.nanmedian(angle)),
                p90=float(np.nanpercentile(angle, 90)), within_30=float(np.nanmean(angle <= 30)))


def ab_repeatability(case: str) -> dict:
    """Points measured twice (the same position in two sections): one measurement scored against the other.

    This bounds what any model can reach on these instruments, like the Case D instrument ceiling.
    """
    data = tables.load_results_ab(case)
    measured = ab_measured(case)
    key = {}
    pairs = []
    for i, position in enumerate(np.round(data.xyz, 6)):
        j = key.setdefault(tuple(position), i)
        if j != i:
            pairs.append((j, i))
    first, second = (np.array(index) for index in zip(*pairs)) if pairs else (np.array([], int),) * 2
    out = dict(pairs=len(pairs), ids=[[int(data.ids[a]), int(data.ids[b])] for a, b in pairs])
    for quantity in AB_QUANTITIES:
        a, b = measured[quantity][first], measured[quantity][second]
        out[quantity] = dict(max_abs_difference=float(np.max(np.abs(a - b))) if pairs else None,
                             mean_abs_difference=float(np.mean(np.abs(a - b))) if pairs else None,
                             hit_rate=metrics.hit_rate(a, b, w=0.0 if quantity == "k" else metrics.W))
    return out

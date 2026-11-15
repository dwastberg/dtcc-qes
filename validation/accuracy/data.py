"""Matched simulated and measured values per case, state and parent (ACCURACY_IMPROVEMENT_PLAN.md, I0, A3).

A ``Data`` holds arrays shaped (point, direction). Simulated quantities:

- ``K``: mean-vector magnitude / U_ref.
- ``K_scalar``: √(|U|² + 2k)/U_ref with the QES-Turb k (the ``wake=2`` scalar proxy).
- ``K_scalar_wake_rule``: the same with k = k_in (1 - D)² + k_w and k_in = 5.5 u*² (``wake=3``, primary).
- ``K_scalar_wake``: k_in from the measured inflow table (``wake=3``, labelled sensitivity; NaN without a table).
- ``<scalar>_mean``: the mean speed of an isotropic Gaussian vector with the same |U| and k (report only).
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.special import erf

import common
from aij import cityutil, compare, runner, tables

PRIMARY = {2: "K_scalar", 3: "K_scalar_wake_rule"}  # scalar gate quantity of each parent (A3)


def mean_speed(m, k):
    """Mean speed of an isotropic Gaussian vector with mean magnitude ``m`` and variance 2k/3 per component."""
    m, k = np.asarray(m, float), np.asarray(k, float)
    sigma = np.sqrt(np.maximum(2 * k / 3, 0))
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = m / (sigma * np.sqrt(2))
        full = sigma * np.sqrt(2 / np.pi) * np.exp(-ratio ** 2) + (m + sigma ** 2 / m) * erf(ratio)
    out = np.where(sigma == 0, m, np.where(m < 1e-9 * np.maximum(sigma, 1e-30), 2 * sigma * np.sqrt(2 / np.pi), full))
    return np.where(np.isfinite(m) & np.isfinite(k), out, np.nan)


@dataclass
class Data:
    name: str
    case: str
    state: str | None
    wake: int
    resolution: float
    ids: np.ndarray
    xyz: np.ndarray
    directions: np.ndarray
    labels: tuple
    measured: np.ndarray  # thermistor scalar speed ratio (C, D, E); split-fibre |U|/U_H (A, B)
    sim: dict  # quantity -> (point, direction)
    velocity: np.ndarray  # (point, direction, 3) / U_ref
    extras: dict = field(default_factory=dict)  # wall distance, deficit, k, groups, vector measurements, keys
    polygons: list = field(default_factory=list)
    heights: np.ndarray | None = None

    @property
    def primary(self):
        return PRIMARY[self.wake]


def _column(probes, name, n):
    if name not in probes:
        return np.full(n, np.nan)
    return np.array([np.nan if v is None else v for v in probes[name]], dtype=np.float64)


def load(case, state=None, wake=2, resolution=None, getter=common.get):
    """The matched data of one case and parent; ``getter`` maps a RunSpec to (record, arrays)."""
    resolution = common.GRID[case] if resolution is None else resolution
    specs = common.specs(case, wake, resolution, state)
    stored = [getter(spec) for spec in specs]
    records = [s[0] for s in stored]
    probes = [r["probes"] for r in records]
    n = len(probes[0]["ids"])
    uref = np.array([r["profile"]["reference_speed"] for r in records])
    stack = lambda name: np.column_stack([_column(p, name, n) for p in probes])  # noqa: E731
    speed, k = stack("speed"), stack("k")
    sim = dict(K=stack("K"), K_scalar=stack("K_scalar"))
    sim["K_scalar_mean"] = mean_speed(speed, k) / uref
    if wake == 3:
        for name in ("K_scalar_wake_rule", "K_scalar_wake"):
            sim[name] = stack(name)
            k_total = ((sim[name] * uref) ** 2 - speed ** 2) / 2
            sim[name + "_mean"] = mean_speed(speed, k_total) / uref
    velocity = np.stack([np.array(p["velocity"], dtype=np.float64) for p in probes], axis=1) / uref[None, :, None]
    extras = dict(wall=np.array(probes[0]["wall_distance"], dtype=np.float64), k=k / uref ** 2, uref=uref,
                  keys=[r["key"] for r in records], native=records[0]["native"]["sha256"],
                  deficit=stack("wake_deficit"), wake_tke=stack("wake_tke") / uref ** 2,
                  method=np.column_stack([np.asarray(p["method"], dtype=str) for p in probes]))
    ids = np.asarray(probes[0]["ids"])
    xyz = np.asarray(probes[0]["xyz"], dtype=np.float64)
    rows = cityutil.footprints(runner.city(case, state or "-"))
    polygons, heights = [p for _, p, _ in rows], np.array([h for _, _, h in rows])
    if case in ("A", "B"):
        table = tables.load_results_ab(case)
        measured_fields = compare.ab_measured(case)
        uh = table.reference["speed"]
        extras.update(measured_velocity=(compare.ab_velocity(case) / uh)[:, None, :], section=table.section,
                      measured_k=measured_fields["k"][:, None],
                      # spatial groups: 16 m blocks (H/2) within a section
                      groups=_groups(np.column_stack([np.floor(table.xyz / 16.0), _codes(table.section)])))
        measured, labels, directions = measured_fields["K"][:, None], ("0 deg.",), np.array([table.direction])
        assert list(ids) == list(table.ids)
    else:
        table = (tables.load_exp_t() if case == "D" else tables.load_results_e(state) if case == "E"
                 else tables.load_results_c(state))
        assert list(ids) == list(table.ids)
        measured, labels, directions = table.values, table.labels, table.directions
        extras["groups"] = np.arange(n)
        if case == "D":
            split = tables.load_exp_s()
            extras.update(measured_velocity=np.where(split.measured[:, None], split.velocity, np.nan)[:, None, :]
                          / tables.U_H, measured_k=(split.k / tables.U_H ** 2)[:, None],
                          split_measured=split.measured, mirrored=table.mirrored,
                          # a mirrored copy at 0 degrees shares the group of the point it repeats
                          groups=_groups(np.column_stack([np.round(xyz[:, 0], 3), np.round(np.abs(xyz[:, 1]), 3)])))
    name = f"{case}{'-' + state if state else ''}-w{wake}-r{resolution:g}"
    return Data(name, case, state, wake, resolution, ids, xyz, np.asarray(directions, float), tuple(labels),
                np.asarray(measured, float), sim, velocity, extras, polygons, heights)


def _codes(values):
    return np.unique(np.asarray(values), return_inverse=True)[1]


def _groups(keys):
    return np.unique(np.asarray(keys, float), axis=0, return_inverse=True)[1].ravel()


def null_K(data):
    """The null model: the approach-flow profile at the probe height over the reference speed, at every probe."""
    if data.case in ("A", "B"):
        return compare.null_model(data.case)["K"][:, None]
    if data.case == "C":
        return np.ones_like(data.measured)
    return np.full_like(data.measured, compare.inflow_ratio(data.case))

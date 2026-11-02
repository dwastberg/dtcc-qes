"""Phase 2 analysis: cost of the smoke runs and iterative convergence at the probes.

The convergence campaign pairs, per case, direction and resolution:
- a bounded float32 run that records the probe speeds every checkpoint (its
  iterates are those of a legacy solve: monitoring leaves the field unchanged);
- a float64 run of the same length, the reference end point.

Comparisons use only probes that are sampled linearly in both runs: the native
receptor history has no nearest-fluid fallback.
"""

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from .campaigns import campaign
from .runspec import RunSpec

P95_TARGET = 0.005  # |ΔK| at the 95th percentile: a quarter of the Case E measurement step
MAX_TARGET = 0.02  # |ΔK| at the worst probe: one Case E measurement step


def records(output: Path, name: str) -> list[tuple[RunSpec, dict]]:
    out = []
    for spec in campaign(name):
        path = Path(output) / spec.case / f"{spec.key}.json"
        if path.exists():
            out.append((spec, json.loads(path.read_text())))
    return out


def _array(values):
    return np.array([np.nan if v is None else v for v in values], dtype=np.float64)


def _changes(a, b) -> dict:
    diff = np.abs(a - b)
    diff = diff[np.isfinite(diff)]
    if not diff.size:
        return dict(count=0, p95=None, max=None)
    return dict(count=int(diff.size), p95=float(np.percentile(diff, 95)), max=float(diff.max()))


def smoke_table(rows) -> list[dict]:
    table = []
    for spec, record in rows:
        native = record["timings"]["native"]
        table.append(dict(
            name=record["name"], cells=record["grid"]["cells"], iterations=record["diagnostics"]["iterations"],
            converged=record["diagnostics"]["converged"], wall=record["wall_seconds"],
            preparation=record["timings"]["city_preparation_seconds"], sweeps=native["sweeps_seconds"],
            postprocessing=native["postprocessing_seconds"], rss_gib=record["peak_rss_bytes"] / 2 ** 30,
            fallback=sum(m != "linear" for m in record["probes"]["method"]),
            turbulence=spec.turbulence, resolution=spec.resolution, case=spec.case))
    return table


def convergence(rows) -> list[dict]:
    """One row per (case, direction, resolution) with the iteration needed to meet the targets."""
    groups = defaultdict(dict)
    for spec, record in rows:
        base = (spec.case, spec.label, spec.resolution)
        kind = "history" if spec.monitor else ("float64" if spec.precision == "float64" else "legacy")
        groups[base][kind] = record
    out = []
    for (case, label, resolution), runs in sorted(groups.items()):
        if "history" not in runs or "float64" not in runs:
            continue
        history, reference = runs["history"], runs["float64"]
        iterations = np.array(history["history"]["iterations"])
        k_history = np.array([_array(row) for row in history["history"]["K"]])
        linear = (np.array(history["probes"]["method"]) == "linear") & (np.array(reference["probes"]["method"]) == "linear")
        k_ref = np.where(linear, _array(reference["probes"]["K"]), np.nan)
        k_end = np.where(linear, _array(history["probes"]["K"]), np.nan)
        steps = [_changes(k, k_ref) for k in k_history]
        p95 = np.array([s["p95"] if s["p95"] is not None else np.inf for s in steps])
        worst = np.array([s["max"] if s["max"] is not None else np.inf for s in steps])
        within = (p95 <= P95_TARGET) & (worst <= MAX_TARGET)
        # The first checkpoint after which every later checkpoint stays within the targets.
        stays = np.flatnonzero(within & np.flip(np.cumprod(np.flip(within)).astype(bool)))
        row = dict(case=case, label=label, resolution=resolution, probes=int(linear.sum()),
                   iterations=iterations.tolist(), p95=p95.tolist(), max=worst.tolist(),
                   required_iterations=int(iterations[stays[0]]) if len(stays) else None,
                   float32_vs_float64=_changes(k_end, k_ref),
                   history_vs_record=_changes(k_history[-1], k_end),
                   self_change_last_1000=_changes(k_history[-1], k_history[np.searchsorted(iterations, iterations[-1] - 1000)]),
                   divergence=dict(float32=history["diagnostics"]["max_divergence"],
                                   float64=reference["diagnostics"]["max_divergence"],
                                   float32_rms=history["diagnostics"]["rms_divergence"],
                                   float64_rms=reference["diagnostics"]["rms_divergence"]),
                   lagrange_change_float32=history["diagnostics"]["max_lagrange_multiplier_change"],
                   wall=dict(float32=history["wall_seconds"], float64=reference["wall_seconds"]))
        for target in (1000, 2000, 4000, 8000):
            if target <= iterations[-1]:
                i = int(np.searchsorted(iterations, target))
                row[f"at_{target}"] = dict(p95=float(p95[i]), max=float(worst[i]))
        if "legacy" in runs:
            legacy = runs["legacy"]
            n = legacy["diagnostics"]["iterations"]
            i = int(np.searchsorted(iterations, n))
            same = (np.array(legacy["probes"]["method"]) == "linear") & linear
            row["legacy_vs_history"] = dict(iterations=n, checkpoint=int(iterations[min(i, len(iterations) - 1)]),
                                            **_changes(np.where(same, _array(legacy["probes"]["K"]), np.nan),
                                                       k_history[min(i, len(iterations) - 1)]))
        out.append(row)
    return out


def self_convergence(record: dict) -> dict:
    """Probe-history convergence against the run's own last checkpoint (no float64 partner).

    Phase 2 showed the float32 end point equals float64 within 3e-5 at the probes,
    so the last checkpoint of a long float32 run is an adequate reference.
    """
    history = record["history"]
    iterations = np.array(history["iterations"])
    k = np.array([_array(row) for row in history["K"]])
    steps = [_changes(row, k[-1]) for row in k]
    p95 = np.array([s["p95"] if s["p95"] is not None else np.inf for s in steps])
    worst = np.array([s["max"] if s["max"] is not None else np.inf for s in steps])
    within = (p95 <= P95_TARGET) & (worst <= MAX_TARGET)
    stays = np.flatnonzero(within & np.flip(np.cumprod(np.flip(within)).astype(bool)))
    near_floor = np.flatnonzero((worst <= 1e-4) & np.flip(np.cumprod(np.flip(worst <= 1e-4)).astype(bool)))
    out = dict(name=record["name"], cells=record["grid"]["cells"], wall=record["wall_seconds"],
               peak_rss_gib=record["peak_rss_bytes"] / 2 ** 30, iterations=iterations.tolist(),
               p95=p95.tolist(), max=worst.tolist(),
               required_iterations=int(iterations[stays[0]]) if len(stays) else None,
               within_1e4_from=int(iterations[near_floor[0]]) if len(near_floor) else None)
    for target in (6000, 12000, 24000):
        if target <= iterations[-1]:
            i = int(np.searchsorted(iterations, target))
            out[f"at_{target}"] = dict(p95=float(p95[i]), max=float(worst[i]))
    return out

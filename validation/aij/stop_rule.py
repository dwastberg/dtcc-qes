"""Study E1 of SOLVER_STOP_RULE.md: SOR relaxation and the velocity-estimate stop rule.

Every study run is a float32 fixed-work solve (``stop="fixed"``) with the probe
history and the native estimate history, so one run gives the whole trajectory:
the stop sweep of any tolerance is replayed offline with the native rule
(``replay``), and its probe error is read from the history at that sweep.
References are float64 fixed-work solves at ω = 1.90; their own estimate
history shows how far they are converged. The full-field subset compares whole
velocity fields at the native stop of each tolerance with an in-process float64
reference, for the bound the estimate claims (the largest face error anywhere).
"""

import json
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

import numpy as np

from .conventions import D_ANGLES
from .numerics import MAX_TARGET, P95_TARGET

OMEGAS = (1.78, 1.85, 1.90, 1.93, 1.95, 1.97)
BUDGETS = {2.0: 4000, 1.0: 12000, 0.5: 32000}  # float32 sweeps per study run
REFERENCE_RELAXATION = 1.90
REFERENCE_BUDGETS = {2.0: 8000, 1.0: 16000, 0.5: 40000}  # float64 sweeps per reference
E_LABELS = ("N", "E", "S", "W")  # Case E "after", as in the convergence campaign
TOLERANCES = (3e-3, 1e-3, 3e-4, 1e-4, 3e-5)
G2_P95, G2_MAX = P95_TARGET / 2, MAX_TARGET / 2  # gate G2: half of the F02 probe targets
FULL_FIELD_OMEGAS = (1.78, 1.90)  # the subset is Case D 0° and Case E "after" W (run_stop_rule_study.py)


def bases(resolutions=(2.0, 1.0, 0.5)):
    """Base specs: Cases D and E at 2 m and 1 m, Case D at 0° at 0.5 m; turbulence off."""
    from .campaigns import FINE_MAX_CELLS, case_d, case_e
    out = []
    for resolution in resolutions:
        if resolution == 0.5:
            out.append(case_d(0.0, resolution=0.5, turbulence=False, max_cells=FINE_MAX_CELLS))
            continue
        out += [case_d(a, resolution=resolution, turbulence=False) for a in D_ANGLES]
        out += [case_e(label, resolution=resolution, turbulence=False) for label in E_LABELS]
    return out


def study_run(base, omega):
    return replace(base, stop="fixed", relaxation=omega, monitor=True, max_iterations=BUDGETS[base.resolution])


def reference_run(base):
    return replace(base, stop="fixed", relaxation=REFERENCE_RELAXATION, precision="float64",
                   max_iterations=REFERENCE_BUDGETS[base.resolution])


def campaign(resolutions=(2.0, 1.0, 0.5)):
    specs = []
    for base in bases(resolutions):
        specs.append(reference_run(base))
        specs += [study_run(base, omega) for omega in OMEGAS]
    return specs


def replay(estimate, tolerance, required=2, minimum=3):
    """(sweep, reason) at which the native velocity rule stops, from a recorded history; (None, None) if never.

    Mirrors SolverState::check_estimate: a check passes when its estimate is at
    most the tolerance (unavailable estimates are None and fail), the floor
    passes when the change is at most the rounding floor, and either needs
    ``required`` consecutive passes from the ``minimum``-th check on.
    """
    passes = floor_passes = 0
    for n, (iteration, value, change, floor) in enumerate(
            zip(estimate["iterations"], estimate["estimate"], estimate["change"], estimate["floor"]), 1):
        passes = passes + 1 if value is not None and value <= tolerance else 0
        floor_passes = floor_passes + 1 if change is not None and floor is not None and change <= floor else 0
        if n >= minimum:
            if passes >= required:
                return iteration, "velocity_estimate"
            if floor_passes >= required:
                return iteration, "precision_floor"
    return None, None


def _values(values):
    return np.array([np.nan if v is None else v for v in values], dtype=np.float64)


def _errors(history, reference, run):
    """Per-checkpoint (iterations, p95, max) of |K - K_ref| over probes linear in both runs."""
    linear = (np.array(run["probes"]["method"]) == "linear") & (np.array(reference["probes"]["method"]) == "linear")
    k_ref = np.where(linear, _values(reference["probes"]["K"]), np.nan)
    iterations = np.array(history["iterations"])
    p95, worst = [], []
    for row in history["K"]:
        d = np.abs(_values(row) - k_ref)
        d = d[np.isfinite(d)]
        p95.append(float(np.percentile(d, 95)) if d.size else np.inf)
        worst.append(float(d.max()) if d.size else np.inf)
    return iterations, np.array(p95), np.array(worst), int(linear.sum())


def _first_staying(iterations, ok):
    stays = np.flatnonzero(ok & np.flip(np.cumprod(np.flip(ok)).astype(bool)))
    return int(iterations[stays[0]]) if len(stays) else None


def analyse_run(run, reference):
    """Metrics M1-M5 of one study run against its float64 reference."""
    iterations, p95, worst, probes = _errors(run["history"], reference, run)
    at = {int(i): n for n, i in enumerate(iterations)}
    estimate = run["stop_estimate"]
    out = dict(probes=probes,
               target_sweeps=_first_staying(iterations, (p95 <= P95_TARGET) & (worst <= MAX_TARGET)),
               g2_sweeps=_first_staying(iterations, (p95 <= G2_P95) & (worst <= G2_MAX)),
               final=dict(p95=float(p95[-1]), max=float(worst[-1])))
    stops = {}
    for tolerance in TOLERANCES:
        sweep, reason = replay(estimate, tolerance)
        if sweep is None:
            stops[f"{tolerance:g}"] = dict(sweep=None, reason=None)
            continue
        n = at[sweep]
        e = estimate["estimate"][estimate["iterations"].index(sweep)]
        stops[f"{tolerance:g}"] = dict(sweep=sweep, reason=reason, estimate=e, p95=float(p95[n]), max=float(worst[n]),
                                       g2=bool(p95[n] <= G2_P95 and worst[n] <= G2_MAX),
                                       max_over_estimate=None if not e else float(worst[n] / e))
    out["stops"] = stops
    # M2: the probe error never exceeds the estimate where one is available (it bounds every face).
    ratios = [worst[at[i]] / e for i, e in zip(estimate["iterations"], estimate["estimate"])
              if e and np.isfinite(worst[at[i]]) and worst[at[i]] > 1e-6]
    out["max_probe_error_over_estimate"] = float(max(ratios)) if ratios else None
    # M4: the float32 floor, from the last tenth of the checks.
    change, floor = _values(estimate["change"]), _values(estimate["floor"])
    tail = slice(int(0.9 * len(change)), None)
    out["tail"] = dict(change=float(np.nanmedian(change[tail])), floor=float(np.nanmedian(floor[tail])),
                       change_over_floor_max=float(np.nanmax(change[tail] / floor[tail])))
    out["floor_sweep"] = next((i for i, c, f in zip(estimate["iterations"], change, floor) if c <= f), None)
    return out


def load(output, specs):
    rows = {}
    for spec in specs:
        path = Path(output) / spec.case / f"{spec.key}.json"
        if path.exists():
            rows[spec.key] = json.loads(path.read_text())
    return rows


def analyse(output, resolutions=(2.0, 1.0, 0.5)):
    """Per base and ω: the run metrics, the reference's own convergence and the converged-value spread (M5)."""
    records = load(output, campaign(resolutions))
    out = []
    for base in bases(resolutions):
        reference = records.get(reference_run(base).key)
        if reference is None:
            continue
        ref_estimate = reference["stop_estimate"]
        row = dict(case=base.case, label=base.label, resolution=base.resolution,
                   cells=reference["grid"]["cells"], reference=dict(
                       final_change=ref_estimate["change"][-1], final_estimate=ref_estimate["estimate"][-1],
                       sweeps=reference["diagnostics"]["iterations"]), runs={})
        for omega in OMEGAS:
            run = records.get(study_run(base, omega).key)
            if run is None:
                continue
            metrics = analyse_run(run, reference)
            metrics["sweep_seconds"] = run["timings"]["native"]["sweeps_seconds"] / run["diagnostics"]["iterations"]
            row["runs"][f"{omega:g}"] = metrics
        out.append(row)
    return out


def full_field(spec, reference_budget, budget, tolerances=TOLERANCES, omegas=FULL_FIELD_OMEGAS, log=print):
    """Largest whole-volume and pedestrian-band |u - u_ref| / U_ref at each native velocity stop."""
    from dtcc_qes import wind
    from . import runner
    args = runner.inputs(spec)
    uref = args["reference_speed"]
    kwargs = dict(args["run"])
    model = wind.prepare(args["city"], args["profile"], **kwargs)
    try:
        reference = model.run(args["profile"], solver=wind.Solver(
            precision="float64", stop="fixed", relaxation=REFERENCE_RELAXATION, max_iterations=reference_budget))
        fluid = ~reference.solid_mask
        band = np.asarray(reference.z) <= 10.0
        u_ref = reference.velocity.astype(np.float64)
        rows = []
        for omega in omegas:
            for tolerance in tolerances:
                result = model.run(args["profile"], solver=wind.Solver(
                    stop="velocity", velocity_tolerance=tolerance, relaxation=omega, max_iterations=budget))
                error = np.abs(result.velocity.astype(np.float64) - u_ref).max(axis=-1) / uref
                error = np.where(fluid, error, 0.0)
                estimate = result.solver["stop_estimate"]
                row = dict(omega=omega, tolerance=tolerance, sweeps=result.diagnostics.iterations,
                           termination=estimate["termination"], estimate=estimate["estimate"][-1],
                           volume=float(error.max()), band=float(error[band].max()))
                row["volume_over_estimate"] = row["volume"] / row["estimate"] if row["estimate"] else None
                log(f"  {spec.name} omega {omega:g} tol {tolerance:g}: {row['sweeps']} sweeps "
                    f"({row['termination']}), estimate {row['estimate']}, volume {row['volume']:.2e}, "
                    f"band {row['band']:.2e}")
                rows.append(row)
        return dict(name=spec.name, case=spec.case, label=spec.label, resolution=spec.resolution,
                    reference_estimate=reference.solver["stop_estimate"]["estimate"][-1], rows=rows)
    finally:
        model.close()

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
HIGH_OMEGAS = (1.98, 1.99)  # 1 m only: where the 1 m optimum lies (P4, recommendation R2)
BUDGETS = {2.0: 4000, 1.0: 12000}  # float32 sweeps per study run (0.5 m was dropped: 142 M cells)
REFERENCE_RELAXATION = 1.90
REFERENCE_BUDGETS = {2.0: 8000, 1.0: 16000}  # float64 sweeps per reference
E_LABELS = ("N", "E", "S", "W")  # Case E "after", as in the convergence campaign
TOLERANCES = (3e-3, 1e-3, 3e-4, 1e-4, 3e-5)
G2_P95, G2_MAX = P95_TARGET / 2, MAX_TARGET / 2  # gate G2: half of the F02 probe targets
FULL_FIELD_OMEGAS = (1.78, 1.90)  # the subset is Case D 0° and Case E "after" W (run_stop_rule_study.py)


def bases(resolutions=(2.0, 1.0)):
    """Base specs: Cases D and E at 2 m and 1 m; turbulence off."""
    from .campaigns import case_d, case_e
    out = []
    for resolution in resolutions:
        out += [case_d(a, resolution=resolution, turbulence=False) for a in D_ANGLES]
        out += [case_e(label, resolution=resolution, turbulence=False) for label in E_LABELS]
    return out


def study_run(base, omega):
    return replace(base, stop="fixed", relaxation=omega, monitor=True, max_iterations=BUDGETS[base.resolution])


def reference_run(base):
    return replace(base, stop="fixed", relaxation=REFERENCE_RELAXATION, precision="float64",
                   max_iterations=REFERENCE_BUDGETS[base.resolution])


CANDIDATE = dict(relaxation="grid", stop="velocity", velocity_tolerance=1e-3, max_iterations=20000)  # D6-D9


def candidate_run(base):
    """The stage 2 default candidate: grid relaxation, velocity rule at 1e-3, cap 20,000 (D4, D6-D9)."""
    return replace(base, **CANDIDATE)


def analyse_candidates(output, resolutions=(2.0, 1.0)):
    """Native stops of the candidate against the float64 references: sweeps, reason, ω, probe errors."""
    rows = []
    for base in bases(resolutions):
        records = load(output, [reference_run(base), candidate_run(base)])
        reference, run = records.get(reference_run(base).key), records.get(candidate_run(base).key)
        if reference is None or run is None:
            continue
        linear = (np.array(run["probes"]["method"]) == "linear") & (np.array(reference["probes"]["method"]) == "linear")
        d = np.abs(_values(run["probes"]["K"]) - _values(reference["probes"]["K"]))[linear]
        estimate = run["stop_estimate"]
        rows.append(dict(case=base.case, label=base.label, resolution=base.resolution, cells=run["grid"]["cells"],
                         short_side=min(run["grid"]["shape"][1:]), sweeps=run["diagnostics"]["iterations"],
                         termination=estimate["termination"], estimate=estimate["estimate"][-1],
                         converged=run["diagnostics"]["converged"], p95=float(np.percentile(d, 95)),
                         max=float(d.max()), g2=bool(np.percentile(d, 95) <= G2_P95 and d.max() <= G2_MAX),
                         sweep_seconds=run["timings"]["native"]["sweeps_seconds"]))
    return rows


def campaign(resolutions=(2.0, 1.0), omegas=OMEGAS):
    specs = []
    for base in bases(resolutions):
        specs.append(reference_run(base))
        specs += [study_run(base, omega) for omega in omegas]
    return specs


def replay(estimate, tolerance, *, floor_factor=None, first_counted_check=None, required=2):
    """(sweep, reason) at which the native velocity rule stops, from a recorded history; (None, None) if never.

    Mirrors SolverState::check_estimate: a check passes when its estimate is at
    most the tolerance (unavailable estimates are None and fail), the floor
    passes when the change is at most the rounding floor, and either stops after
    ``required`` consecutive passes. Passes count from ``first_counted_check``
    (records made before it was reported: from the first, with no stop before
    the third). ``floor_factor`` replays another factor by rescaling the
    recorded floor; both default to the rule the record was made with.
    """
    recorded_first = estimate.get("first_counted_check")
    first = first_counted_check or recorded_first or 1
    minimum = 3 if first_counted_check is None and recorded_first is None else first
    scale = 1.0 if floor_factor is None else floor_factor / estimate.get("floor_factor", 4)
    passes = floor_passes = 0
    best, stale, near = float("inf"), 0, 0
    window = estimate.get("stagnation_checks", 0)
    factor = estimate.get("stagnation_floor_factor", 2)
    for n, (iteration, value, change, floor) in enumerate(
            zip(estimate["iterations"], estimate["estimate"], estimate["change"], estimate["floor"]), 1):
        counted = n >= first
        passes = passes + 1 if counted and value is not None and value <= tolerance else 0
        floor_passes = (floor_passes + 1 if counted and change is not None and floor is not None
                        and change <= scale * floor else 0)
        if change is not None and floor is not None:
            if change < best:
                best, stale = change, 0
            else:
                stale += 1
            near = near + 1 if counted and change <= factor * scale * floor else 0
        else:
            near = 0
        if n >= minimum:
            if passes >= required:
                return iteration, "velocity_estimate"
            if floor_passes >= required:
                return iteration, "precision_floor"
            if window and stale >= window and near >= window:
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


def analyse(output, resolutions=(2.0, 1.0)):
    """Per base and ω: the run metrics, the reference's own convergence and the converged-value spread (M5)."""
    records = load(output, campaign(resolutions, OMEGAS + HIGH_OMEGAS))
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
        for omega in OMEGAS + HIGH_OMEGAS:
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


# Gate G6 (stage 2): the AIJ 2 m baseline of Cases A, B, D and E with the new default
# Solver() against the fixed-work records. Fixed before the runs: every pooled score
# below differs by at most G6_LIMIT.
G6_SCORES = ("hit_rate", "fac2", "r", "spearman", "fb")
G6_LIMIT = 0.01


def g6_fixed():
    from .campaigns import ab_baseline, baseline
    return baseline(2.0) + ab_baseline(2.0)


def g6_campaign():
    fixed = g6_fixed()
    return fixed + [candidate_run(spec) for spec in fixed]


def _comparisons(records):
    from . import compare
    out = {c.name: c for c in compare.case_d(records) + compare.case_e_comparisons(records)}
    for case in ("A", "B"):
        out.update({c.name: c for c in compare.isolated(records, case)})
    return out


def analyse_g6(output):
    """Pooled scores of the fixed-work and default runs, their differences, and the gate."""
    from . import compare
    fixed = compare.load_records(output, g6_fixed())
    default = compare.load_records(output, [candidate_run(spec) for spec in g6_fixed()])
    before, after = _comparisons(fixed), _comparisons(default)
    rows, worst = [], 0.0
    for name in sorted(before):
        a, b = before[name].scores(), after[name].scores()
        delta = {k: (b[k] - a[k]) for k in G6_SCORES if a.get(k) is not None and b.get(k) is not None}
        worst = max([worst] + [abs(v) for v in delta.values()])
        rows.append(dict(name=name, count=a.get("count"), fixed={k: a.get(k) for k in G6_SCORES},
                         default={k: b.get(k) for k in G6_SCORES}, delta=delta))
    sweeps = sorted(r["diagnostics"]["iterations"] for r in default.values())
    stops = sorted({r["stop_estimate"]["termination"] for r in default.values()})
    return dict(runs=dict(fixed=len(fixed), default=len(default)), sweeps=dict(min=sweeps[0], max=sweeps[-1],
                median=sweeps[len(sweeps) // 2]) if sweeps else None, terminations=stops,
                limit=G6_LIMIT, worst=worst, passed=bool(rows) and worst <= G6_LIMIT
                and len(fixed) == len(default) == len(g6_fixed()), comparisons=rows)

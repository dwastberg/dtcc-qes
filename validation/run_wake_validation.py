"""Validate the spreading far wake (wake code 3) and print its gate table (WAKE_UPDATE_V2.md, section 6).

    uv run --group validate python validation/run_wake_validation.py [--jobs N] [--grid]

Runs, with turbulence on and the fixed-work solver, each with wake 3 and with the
default wake 2 as the reference:
- the baseline matrix: Cases D and E at 2 m (35 runs), Cases A and B at 2 m and 1 m;
- Cases A and B at 1 m with the rooftop vortex and with the high-rise model;
- probe-history runs (8000 iterations, no turbulence) of A, B, D 0° and E N after
  at 2 m, for the iterations to the probe tolerance;
- ``--grid``: Cases A and B at 4 m and 0.5 m.

Runs go through ``run_validation.execute`` into validation/output/runs and are
reused when current. ``--jobs 1`` (the default) keeps the wall times usable as
cost evidence. Prints the gate table and the ungated reports, and writes them to
validation/output/wake/summary.json.

The scalar speeds compared: ``K_scalar_wake`` is √(|U|² + 2k)/U_ref with
k = k_in (1 - D)² + k_w and the tunnel inflow k (``K_scalar_wake_rule``: 5.5 u*²);
``K_scalar`` adds the QES-Turb k; ``K_scalar_inflow`` adds only the tunnel inflow k
(the wake 2 reference of the investigation).
"""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

import run_validation
from aij import campaigns, compare, metrics, numerics, runner
from aij.campaigns import WAKE3
from aij.conventions import AB_LABEL

VALIDATION = Path(__file__).resolve().parent
RUNS = VALIDATION / "output" / "runs"
OUTPUT = VALIDATION / "output" / "wake"
WAKES = (3, 2)
# Section 6: (case, row, resolution, quantity, score, comparator, threshold). The prototype's values less 0.03.
GATES = (
    ("A", "|U|/U_H", 2.0, "K", "hit_rate", ">=", 0.71), ("A", "|U|/U_H", 1.0, "K", "hit_rate", ">=", 0.67),
    ("A", "|U|/U_H", 2.0, "K", "r", ">=", 0.90), ("A", "|U|/U_H", 1.0, "K", "r", ">=", 0.88),
    ("B", "|U|/U_H", 2.0, "K", "hit_rate", ">=", 0.64), ("B", "|U|/U_H", 1.0, "K", "hit_rate", ">=", 0.62),
    ("B", "|U|/U_H", 2.0, "K", "r", ">=", 0.91), ("B", "|U|/U_H", 1.0, "K", "r", ">=", 0.90),
    ("A", "scalar speed, 2 m probes", 2.0, "K_scalar_wake", "hit_rate", ">=", 0.83),
    ("B", "scalar speed, 2 m probes", 2.0, "K_scalar_wake", "hit_rate", ">=", 0.86),
    ("D", "split fibre, mean vector", 2.0, "K", "mae", "<=", 0.15),
    ("D", "thermistor, scalar", 2.0, "K_scalar_wake", "hit_rate", ">=", 0.38),
    ("D", "thermistor, scalar", 2.0, "K_scalar_wake", "r", ">=", 0.52),
    ("E before", "thermistor, scalar", 2.0, "K_scalar_wake", "hit_rate", ">=", 0.27),
    ("E before", "thermistor, scalar", 2.0, "K_scalar_wake", "r", ">=", 0.52),
    ("E after", "thermistor, scalar", 2.0, "K_scalar_wake", "hit_rate", ">=", 0.43),
    ("E after", "thermistor, scalar", 2.0, "K_scalar_wake", "r", ">=", 0.52),
    ("E change", "scalar", 2.0, "K_scalar_wake", "r", ">=", 0.45),
)
# The wake 2 reference column compares like with like where wake 2 has no wake fields.
REFERENCE_QUANTITY = {"K_scalar_wake": "K_scalar_inflow"}
SCORE_NAMES = {"hit_rate": "q", "r": "R", "mae": "MAE"}
CONVERGENCE_ITERATIONS = 8000


def _wake(wake):
    return dict(parameterizations=WAKE3) if wake == 3 else {}


def matrices(grid=False) -> dict:
    """Run specs per (purpose, wake)."""
    out = {}
    for wake in WAKES:
        out["baseline", wake] = (campaigns.baseline(2.0, **_wake(wake)) + campaigns.ab_baseline(2.0, **_wake(wake))
                                 + campaigns.ab_baseline(1.0, **_wake(wake)))
        models = []
        for change in (dict(rooftop=2), dict(high_rise=1)):
            parameterizations = {**(WAKE3 if wake == 3 else {}), **change}
            models += campaigns.ab_baseline(campaigns.AB_RESOLUTION, parameterizations=parameterizations)
        out["models", wake] = models
        bases = [campaigns.case_ab(case, resolution=2.0, turbulence=False, **_wake(wake)) for case in campaigns.AB_CASES]
        bases += [campaigns.case_d(0.0, resolution=2.0, turbulence=False, **_wake(wake)),
                  campaigns.case_e("N", "after", resolution=2.0, turbulence=False, **_wake(wake))]
        out["convergence", wake] = [replace(b, tolerance=1.2e-7, max_iterations=CONVERGENCE_ITERATIONS, monitor=True)
                                    for b in bases]
        if grid:
            out["grid", wake] = campaigns.ab_baseline(4.0, **_wake(wake)) + campaigns.ab_baseline(0.5, **_wake(wake))
    return out


def load(specs) -> dict:
    """Records keyed by (case, state, label, resolution), with K_scalar_inflow added."""
    out = {}
    for spec in specs:
        record = runner.load(RUNS / spec.case, spec.key)
        if record is None:
            continue
        probes = record["probes"]
        table = runner._tables(spec.case)[0]
        uref = record["profile"]["reference_speed"]
        heights = np.array(probes["xyz"], dtype=np.float64)[:, 2]
        k_in = np.interp(np.log(heights), np.log(table.heights), table.k)
        K = np.array([np.nan if v is None else v for v in probes["K"]], dtype=np.float64)
        probes["K_scalar_inflow"] = np.sqrt(K ** 2 + 2 * k_in / uref ** 2).tolist()
        out[spec.case, spec.state, spec.label, spec.resolution] = record
    return out


def _at(records, resolution):
    return {(c, s, l): r for (c, s, l, res), r in records.items() if res == resolution}


def _comparison(records, case, quantity, resolution):
    """The comparison of one gate row (None when its runs or quantity are missing)."""
    recs = _at(records, resolution)
    if case in ("A", "B"):
        if quantity == "K":
            return next((c for c in compare.isolated(recs, case) if c.quantity == "K"), None)
        return compare.ab_scalar(recs, case, quantity)
    if not any(quantity in r["probes"] for r in recs.values()):
        return None
    if case == "D":
        name = "D-split_fibre" if quantity == "K" else f"D-thermistor-{quantity}"
        return next((c for c in compare.case_d(recs, (quantity,)) if c.name == name), None)
    state = case.split()[1]
    return next((c for c in compare.case_e_comparisons(recs, (quantity,)) if c.state == state), None)


def change(records, quantity) -> dict | None:
    recs = _at(records, 2.0)
    if not any(quantity in r["probes"] for r in recs.values()):
        return None
    by_state = {c.state: c for c in compare.case_e_comparisons(recs, (quantity,))}
    if set(by_state) != {"before", "after"}:
        return None
    b, a = by_state["before"], by_state["after"]
    return metrics.change_scores(b.simulated, a.simulated, b.measured, a.measured)


def score(records, case, quantity, resolution, name):
    if case == "E change":
        scores = change(records, quantity)
        return None if scores is None else scores[name]
    comparison = _comparison(records, case, quantity, resolution)
    return None if comparison is None else comparison.scores()[name]


def gate_table(records) -> list[dict]:
    rows = []
    for case, row, resolution, quantity, name, comparator, threshold in GATES:
        value = score(records[3], case, quantity, resolution, name)
        reference = score(records[2], case, REFERENCE_QUANTITY.get(quantity, quantity), resolution, name)
        passed = None if value is None else (value >= threshold if comparator == ">=" else value <= threshold)
        rows.append(dict(case=case, quantity=row, resolution=resolution, score=SCORE_NAMES[name],
                         gate=f"{comparator} {threshold:g}", wake3=value, wake2=reference, passed=passed))
    return rows


def reports(records, models, convergence) -> dict:
    out = {}
    # Case E change: sign agreement and top-10 overlap, beside wake 2 with the inflow k.
    out["E change"] = {label: change(records[wake], quantity) for label, wake, quantity in (
        ("wake 3, table inflow k", 3, "K_scalar_wake"), ("wake 3, 5.5 u*²", 3, "K_scalar_wake_rule"),
        ("wake 3, QES-Turb k", 3, "K_scalar"), ("wake 2, inflow k", 2, "K_scalar_inflow"),
        ("wake 2, QES-Turb k", 2, "K_scalar"))}
    # Every scalar comparison with each inflow k (the table and the rule, section 3.4) and QES-Turb's k.
    scalars = {}
    for wake, quantities in ((3, ("K_scalar_wake", "K_scalar_wake_rule", "K_scalar", "K")),
                             (2, ("K_scalar_inflow", "K_scalar", "K"))):
        for quantity in quantities:
            for case in ("A", "B", "D", "E before", "E after"):
                comparison = _comparison(records[wake], case, quantity, 2.0)
                if comparison is not None:
                    s = comparison.scores()
                    scalars[f"wake {wake} {case} {quantity}"] = {k: s[k] for k in ("hit_rate", "r", "fb", "mae")}
    out["scalar speeds at 2 m"] = scalars
    # Cases A and B at 1 m with the cavity variants.
    variants = {}
    for wake in WAKES:
        for spec in models[wake]:
            record = runner.load(RUNS / spec.case, spec.key)
            if record is None:
                continue
            recs = {(spec.case, "-", AB_LABEL): record}
            c = {x.quantity: x.scores() for x in compare.isolated(recs, spec.case)}
            reattachment = {z: e.get("simulated_H") for z, e in compare.ab_reattachment(recs, spec.case).items()}
            variants[f"wake {wake} {spec.case} {dict(spec.parameterizations)}"] = dict(
                q=c["K"]["hit_rate"], R=c["K"]["r"], reattachment_H=reattachment)
    out["A, B cavity variants (1 m)"] = variants
    # QES-Turb k on the new field.
    turb = {}
    for wake in WAKES:
        for case in ("A", "B"):
            recs = _at(records[wake], 2.0)
            k = next((x for x in compare.isolated(recs, case) if x.quantity == "k"), None)
            if k is not None:
                s = k.scores()
                turb[f"wake {wake} {case} k/U_H² (2 m grid)"] = {n: s[n] for n in ("hit_rate", "r", "fb")}
        extras = compare.split_fibre_extras(_at(records[wake], 2.0))
        if extras and "k" in extras:
            turb[f"wake {wake} D 0° k/U²"] = {n: extras["k"]["scores"][n] for n in ("hit_rate", "r", "fb")}
    out["QES-Turb k"] = turb
    # Iterations to the probe tolerance (numerics.self_convergence), wake 3 against wake 2.
    iterations = {}
    for wake in WAKES:
        for spec in convergence[wake]:
            record = runner.load(RUNS / spec.case, spec.key)
            if record is not None and "history" in record:
                s = numerics.self_convergence(record)
                iterations[f"wake {wake} {spec.case} {spec.state} {spec.label}"] = s["required_iterations"]
    out["iterations to the probe tolerance"] = iterations
    # Cost: native initialization (the parameterizations) and wall time per Case E run.
    cost = {}
    for wake in WAKES:
        e = [r for (c, s, l, res), r in records[wake].items() if c == "E" and res == 2.0]
        if e:
            cost[f"wake {wake}"] = dict(
                initialization_seconds=float(np.mean([r["timings"]["native"]["initialization_seconds"] for r in e])),
                wall_seconds=float(np.mean([r["wall_seconds"] for r in e])), runs=len(e))
    out["Case E cost per direction (2 m)"] = cost
    return out


def grid_study(grid) -> dict:
    out = {}
    for wake in WAKES:
        for spec in grid.get(wake, []):
            record = runner.load(RUNS / spec.case, spec.key)
            if record is None:
                continue
            c = {x.quantity: x.scores() for x in compare.isolated({(spec.case, "-", AB_LABEL): record}, spec.case)}
            out[f"wake {wake} {spec.case} {spec.resolution:g} m"] = dict(q=c["K"]["hit_rate"], R=c["K"]["r"])
    return out


def _fmt(value):
    return "–" if value is None else (f"{value:.3f}" if isinstance(value, float) else str(value))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--grid", action="store_true", help="also Cases A and B at 4 m and 0.5 m")
    parser.add_argument("--no-run", action="store_true", help="summarise the stored runs only")
    args = parser.parse_args(argv)
    specs = matrices(args.grid)
    if not args.no_run:
        everything = [s for group in specs.values() for s in group]
        failed = run_validation.execute(everything, RUNS, jobs=args.jobs)
        if failed:
            print(f"{len(failed)} runs failed", file=sys.stderr)
    records = {wake: load(specs["baseline", wake]) for wake in WAKES}
    rows = gate_table(records)
    print("| Case | Quantity | Grid | Score | Gate | wake 3 | wake 2 | Pass |\n|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['case']} | {r['quantity']} | {r['resolution']:g} m | {r['score']} | {r['gate']} | "
              f"{_fmt(r['wake3'])} | {_fmt(r['wake2'])} | {'yes' if r['passed'] else ('–' if r['passed'] is None else 'NO')} |")
    extra = reports(records, {w: specs["models", w] for w in WAKES}, {w: specs["convergence", w] for w in WAKES})
    if args.grid:
        extra["A, B grid study"] = grid_study({w: specs["grid", w] for w in WAKES})
    print(json.dumps(extra, indent=1, default=float))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "summary.json").write_text(json.dumps(dict(gates=rows, reports=extra), indent=1, default=float))
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

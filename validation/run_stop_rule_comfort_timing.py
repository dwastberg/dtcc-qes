"""Step P7 of SOLVER_STOP_RULE.md: the user-facing gain of the default switch.

A 16-direction Case E ("after", 2 m, measured inflow, turbulence on) comfort
series on one PreparedWindModel, with the former default
``Solver(stop="multiplier_change")`` ("before") and the stage 2 default
``Solver()`` ("after"). Each series runs in a fresh process; three repetitions
of each alternate in order. The OpenMP team is the machine default unless
OMP_NUM_THREADS is set.

    uv run --group validate python validation/run_stop_rule_comfort_timing.py

Writes validation/output/stop_rule/comfort-timing.json and prints the summary.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output" / "stop_rule"
ORDER = ("before", "after", "after", "before", "before", "after")


def series(kind: str) -> dict:
    """One fresh-process series: prepare once, then all 16 directions."""
    from dtcc_qes import _qes, wind
    from aij import campaigns, runner, sampling
    from aij.conventions import E_LABELS
    solver = wind.Solver(stop="multiplier_change") if kind == "before" else wind.Solver()
    specs = [campaigns.case_e(label, resolution=2.0) for label in E_LABELS]
    first = runner.inputs(specs[0])
    run = first["run"]
    started = time.perf_counter()
    model = wind.prepare(first["city"], first["profile"], resolution=run["resolution"], bounds=run["bounds"],
                         vertical_grid=run["vertical_grid"], turbulence=run["turbulence"],
                         footprints=run["footprints"], vertical_clearance=run["vertical_clearance"],
                         max_cells=run["max_cells"], parameterizations=run["parameterizations"], solver=solver)
    prepare_seconds = time.perf_counter() - started
    directions = []
    with model:
        for spec in specs:
            args = runner.inputs(spec)
            t = time.perf_counter()
            result = model.run(args["profile"])
            wall = time.perf_counter() - t
            k = sampling.probe_sample(result, args["probes"].xyz)["speed"] / args["reference_speed"]
            estimate = result.solver.get("stop_estimate")
            native = result.metadata["timings"]["native"]
            directions.append(dict(
                label=spec.label, sweeps=result.diagnostics.iterations,
                termination=result.qualification["solver"]["termination_reason"],
                converged=bool(result.diagnostics.converged), relaxation=result.solver.get("relaxation"),
                estimate=None if estimate is None else estimate["estimate"][-1],
                wall_seconds=wall, sweeps_seconds=native.get("sweeps_seconds"),
                K=[None if not np.isfinite(v) else float(v) for v in k]))
        timings = model.preparation_timings
    return dict(kind=kind, solver=solver.to_dict(), threads=os.environ.get("OMP_NUM_THREADS"),
                identity=_qes.solver_policy_revision, supported=bool(_qes.solver_policy_build_supported),
                cells=int(np.prod(result.velocity.shape[:3])), prepare_seconds=prepare_seconds,
                preparation_timings=timings, directions=directions,
                directions_seconds=sum(d["wall_seconds"] for d in directions),
                total_seconds=prepare_seconds + sum(d["wall_seconds"] for d in directions))


def _values(values):
    return np.array([np.nan if v is None else v for v in values], dtype=np.float64)


def summarise(runs: list[dict]) -> dict:
    by = {kind: [r for r in runs if r["kind"] == kind] for kind in ("before", "after")}
    out = {}
    for kind, rows in by.items():
        totals = [r["total_seconds"] for r in rows]
        directions = [r["directions_seconds"] for r in rows]
        first = rows[0]["directions"]
        out[kind] = dict(repetitions=len(rows), total_seconds=dict(median=float(np.median(totals)),
                         min=min(totals), max=max(totals)),
                         directions_seconds=dict(median=float(np.median(directions)), min=min(directions),
                                                 max=max(directions)),
                         prepare_seconds=float(np.median([r["prepare_seconds"] for r in rows])),
                         per_direction_seconds=float(np.median(directions)) / len(first),
                         sweeps=dict(total=sum(d["sweeps"] for d in first), min=min(d["sweeps"] for d in first),
                                     max=max(d["sweeps"] for d in first)),
                         terminations=sorted({d["termination"] for d in first}),
                         deterministic=all([d["sweeps"] for d in r["directions"]] == [d["sweeps"] for d in first]
                                           for r in rows))
    # K agreement between the series, per direction (first repetition of each).
    before, after = by["before"][0]["directions"], by["after"][0]["directions"]
    deltas = []
    for b, a in zip(before, after):
        d = np.abs(_values(a["K"]) - _values(b["K"]))
        d = d[np.isfinite(d)]
        deltas.append(dict(label=b["label"], p95=float(np.percentile(d, 95)), max=float(d.max())))
    out["K_difference"] = dict(p95_max=max(d["p95"] for d in deltas), max=max(d["max"] for d in deltas),
                               directions=deltas)
    out["speedup"] = dict(total=out["before"]["total_seconds"]["median"] / out["after"]["total_seconds"]["median"],
                          directions=out["before"]["directions_seconds"]["median"]
                          / out["after"]["directions_seconds"]["median"],
                          sweeps=out["before"]["sweeps"]["total"] / out["after"]["sweeps"]["total"])
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--series", choices=("before", "after"), help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.series:
        args.output.write_text(json.dumps(series(args.series)) + "\n")
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    runs = []
    for n, kind in enumerate(ORDER):
        path = OUTPUT / f".comfort-{n}-{kind}.json"
        subprocess.run([sys.executable, "-W", "ignore", __file__, "--series", kind, "--output", str(path)],
                       check=True, cwd=HERE)
        run = json.loads(path.read_text())
        path.unlink()
        runs.append(run)
        print(f"[{n + 1}/{len(ORDER)}] {kind}: {run['total_seconds']:.1f} s total "
              f"(prepare {run['prepare_seconds']:.1f} s), sweeps "
              f"{sum(d['sweeps'] for d in run['directions'])}", flush=True)
    summary = summarise(runs)
    (OUTPUT / "comfort-timing.json").write_text(json.dumps(dict(summary=summary, runs=runs), indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "K_difference"}, indent=1))
    print(f"K difference: p95 up to {summary['K_difference']['p95_max']:.1e}, max {summary['K_difference']['max']:.1e}")


if __name__ == "__main__":
    main()

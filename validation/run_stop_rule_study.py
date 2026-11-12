"""Study E1 of SOLVER_STOP_RULE.md: relaxation and the velocity-estimate stop rule.

    uv run --group validate python validation/run_stop_rule_study.py --resolutions 2 --jobs 2
    uv run --group validate python validation/run_stop_rule_study.py --resolutions 1 --jobs 3

Stages (default: all): ``matrix`` runs the float32 study runs and the float64
references through the AIJ harness (records in validation/output/runs);
``fullfield`` compares whole fields at native velocity stops for the subset
(Case D 0° and Case E "after" W at 2 m and 1 m); ``analyse`` writes
validation/output/stop_rule/summary-<resolutions>.json and prints the tables.
"""

import argparse
import json
import time
from pathlib import Path

from aij import stop_rule
from run_validation import OUTPUT, execute

SUMMARY = Path(__file__).resolve().parent / "output" / "stop_rule"


def _tag(resolutions):
    return "-".join(f"r{r:g}" for r in resolutions)


def matrix(resolutions, jobs, output):
    specs = stop_rule.campaign(resolutions)
    failed = execute(specs, output, jobs=jobs, log=lambda line: print(line, flush=True))
    if failed:
        raise SystemExit(f"{len(failed)} study runs failed")


def fullfield(resolutions, omegas=stop_rule.FULL_FIELD_OMEGAS):
    SUMMARY.mkdir(parents=True, exist_ok=True)
    suffix = "" if tuple(omegas) == stop_rule.FULL_FIELD_OMEGAS else "-w" + "-".join(f"{w:g}" for w in omegas)
    from aij.campaigns import case_d, case_e
    for resolution in [r for r in resolutions if r in (2.0, 1.0)]:
        subset = [case_d(0.0, resolution=resolution, turbulence=False),
                  case_e("W", resolution=resolution, turbulence=False)]
        rows = [stop_rule.full_field(base, stop_rule.REFERENCE_BUDGETS[resolution], stop_rule.BUDGETS[resolution],
                                     omegas=omegas, log=lambda line: print(line, flush=True))
                for base in subset]
        path = SUMMARY / f"fullfield-r{resolution:g}{suffix}.json"
        path.write_text(json.dumps(rows, indent=1) + "\n")
        print(f"wrote {path}", flush=True)


def _fmt(value, spec=".1e"):
    return "-" if value is None else format(value, spec)


def analyse(resolutions, output):
    rows = stop_rule.analyse(output, resolutions)
    SUMMARY.mkdir(parents=True, exist_ok=True)
    path = SUMMARY / f"summary-{_tag(resolutions)}.json"
    path.write_text(json.dumps(rows, indent=1) + "\n")
    shown = ("3e-03", "1e-03", "3e-04")
    print(f"wrote {path}")
    print("case label res omega | target g2 | " + " | ".join(f"tol {t}: stop max g2" for t in shown)
          + " | probe/e floor-sweep tail c/floor | ref c")
    for row in rows:
        for omega, m in row["runs"].items():
            stops = " | ".join(
                f"{_fmt(m['stops'][f'{float(t):g}']['sweep'], 'd')} {_fmt(m['stops'][f'{float(t):g}'].get('max'))} "
                f"{'ok' if m['stops'][f'{float(t):g}'].get('g2') else 'NO'}" for t in shown)
            print(f"{row['case']} {row['label']:>8} {row['resolution']:g} {omega:>5} | "
                  f"{_fmt(m['target_sweeps'], 'd')} {_fmt(m['g2_sweeps'], 'd')} | {stops} | "
                  f"{_fmt(m['max_probe_error_over_estimate'], '.2f')} {_fmt(m['floor_sweep'], 'd')} "
                  f"{m['tail']['change_over_floor_max']:.2f} | {row['reference']['final_change']:.1e}")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--resolutions", type=float, nargs="+", default=[2.0, 1.0])
    parser.add_argument("--stage", choices=("all", "matrix", "fullfield", "analyse"), default="all")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--fullfield-omegas", type=float, nargs="+", default=list(stop_rule.FULL_FIELD_OMEGAS))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    resolutions = tuple(args.resolutions)
    started = time.perf_counter()
    if args.stage in ("all", "matrix"):
        matrix(resolutions, args.jobs, args.output)
    if args.stage in ("all", "fullfield"):
        fullfield(resolutions, tuple(args.fullfield_omegas))
    if args.stage in ("all", "analyse"):
        analyse(resolutions, args.output)
    print(f"done in {time.perf_counter() - started:.0f} s", flush=True)


if __name__ == "__main__":
    main()

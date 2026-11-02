"""Tune dtcc-qes to the AIJ data (AIJ_VALIDATION_PLAN.md, Phase 5, part B).

    uv run --group validate python validation/tune_validation.py --jobs 6

Greedy coordinate descent from the base settings over the building
parameterizations and the in-canopy inflow (``campaigns.tuning_candidates``).
Each step solves every single change on the training runs (Case E "before") and
keeps the best one if it raises the hit rate by at least ``sensitivity.TIE``.
The search log goes to validation/output/tuning/search.json. The tuned and the
base settings are then run on the full matrix at 2 m and 1 m; the test sets
(Case E "after", the change scores, Case D) are scored by report_validation.py.
"""

import argparse
import json
import time
from pathlib import Path

from aij import campaigns, compare, sensitivity
from run_validation import OUTPUT, execute

SEARCH = Path(__file__).resolve().parent / "output" / "tuning" / "search.json"
MAX_STEPS = 8


def _evaluate(config, runs):
    specs = campaigns.tuned(config, select={campaigns.TRAINING})
    return sensitivity.objective(compare.load_records(runs, specs))


def _json_config(config):
    return {k: list(v) if k == "canopy" else v for k, v in config.items()}


def config_from_json(payload):
    return {k: tuple(v) if k == "canopy" else v for k, v in payload.items()}


def search(runs: Path, jobs: int, log=print) -> dict:
    config = {}
    execute(campaigns.tuned(config, select={campaigns.TRAINING}), runs, jobs=jobs, log=log)
    current = _evaluate(config, runs)
    steps = []
    for step in range(1, MAX_STEPS + 1):
        candidates = campaigns.tuning_candidates(config)
        specs = [s for _, c in candidates for s in campaigns.tuned(c, select={campaigns.TRAINING})]
        failed = execute(specs, runs, jobs=jobs, log=log)
        if failed:
            raise RuntimeError(f"{len(failed)} tuning runs failed")
        rows = [dict(label=label, config=_json_config(c), objective=_evaluate(c, runs)) for label, c in candidates]
        best = sensitivity.choose(rows)
        keep = sensitivity.accepted(current, best)
        steps.append(dict(step=step, start=_json_config(config), start_objective=current, candidates=rows,
                          best=best["label"], accepted=keep))
        log(f"step {step}: q {current['q']:.3f} -> best {best['label']} q {best['objective']['q']:.3f} "
            f"rho {best['objective']['rho']:.3f} ({'kept' if keep else 'stop'})")
        if not keep:
            break
        config, current = config_from_json(best["config"]), best["objective"]
    return dict(objective="hit rate q of K on Case E 'before' (D = 0.25, W = 0.05); ties within "
                          f"{sensitivity.TIE} by Spearman rho", tie=sensitivity.TIE,
                steps=steps, final=_json_config(config), final_objective=current)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--confirm-jobs", type=int, default=4, help="jobs for the 1 m confirmation runs")
    args = parser.parse_args(argv)
    log = lambda line: print(line, flush=True)  # noqa: E731
    started = time.perf_counter()
    result = search(args.output, args.jobs, log)
    SEARCH.parent.mkdir(parents=True, exist_ok=True)
    SEARCH.write_text(json.dumps(result, indent=1) + "\n")
    tuned = config_from_json(result["final"])
    log(f"tuned: {result['final']}; running the full matrix at 2 m and 1 m")
    failed = execute(campaigns.tuned(tuned, 2.0), args.output, jobs=args.jobs, log=log)
    failed += execute(campaigns.tuned(tuned, 1.0) + campaigns.baseline(1.0), args.output,
                      jobs=args.confirm_jobs, log=log)
    log(f"{len(failed)} failed; {time.perf_counter() - started:.0f} s")


if __name__ == "__main__":
    main()

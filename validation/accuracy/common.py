"""Run matrix and run cache of ACCURACY_IMPROVEMENT_PLAN.md (I0). A research tool, kept as it was used.

The released options have ordinary run specifications and campaigns (`aij.campaigns`: `angle_fade`,
`tall_buildings`, `accuracy_options`); use those for validation. This cache stores a variant (`ACC_TAG`,
`ACC_PARAMS`) in its own directory under the key of its parent specification, so that the scripts of
the accuracy study can pair a variant with its parent by key.

Every run uses the ordinary ``wind.Solver()`` (velocity stop rule, grid relaxation,
at most 20,000 sweeps), turbulence on, float32. Records go to
``validation/output/accuracy/runs/<case>/<key>.{json,npz}`` and are reused only when
the run fingerprint (validation run modules, dtcc_qes sources and the loaded native
extension) is unchanged. The plane arrays add the wake code 3 fields at 2 m.
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "validation"))
import numpy as np  # noqa: E402
from aij import campaigns, runner  # noqa: E402
from aij.conventions import C_ANGLES, C_STATES, D_ANGLES, E_LABELS, E_STATES  # noqa: E402

OUT = REPO / "validation" / "output" / "accuracy"
# Experiment builds (branch exp/accuracy-prototypes) keep their own run cache: ACC_TAG names the variant,
# and the QES_EXP_* switches that define it are recorded beside the runs.
TAG = os.environ.get("ACC_TAG", "")
RUNS = OUT / (f"runs-{TAG}" if TAG else "runs")
if TAG:
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / "variant.json").write_text(json.dumps({k: v for k, v in sorted(os.environ.items()) if k.startswith("QES_EXP_")}))
SOLVER = dict(stop="velocity", relaxation="grid", max_iterations=20000)
SEED = 20261115
# Working grid of each case, and the second grid used for robustness.
GRID = {"A": 1.0, "B": 1.0, "C": 1.0, "D": 2.0, "E": 2.0}
SECOND_GRID = {"A": 2.0, "B": 2.0, "C": 2.0, "D": 1.0, "E": 1.0}


def specs(case, wake=2, resolution=None, state=None, **options):
    """Run specifications of one case (and state), in the direction order of its measurements."""
    resolution = GRID[case] if resolution is None else resolution
    options = dict(SOLVER, resolution=resolution, **options)
    if wake == 3:
        options["parameterizations"] = {"wake": 3, **dict(options.get("parameterizations", {}))}
    if case in ("A", "B"):
        return [campaigns.case_ab(case, **options)]
    if case == "C":
        return [campaigns.case_c(a, state, **options) for a in C_ANGLES]
    if case == "D":
        return [campaigns.case_d(a, **options) for a in D_ANGLES]
    return [campaigns.case_e(label, state, **options) for label in E_LABELS]


DATASETS = (("A", None), ("B", None), ("C", "0H"), ("C", "1H"), ("C", "2H"), ("D", None),
            ("E", "before"), ("E", "after"))


def all_specs(wakes=(2, 3), second_grid=False, cases=None, states=None):
    out = []
    for case, state in DATASETS:
        if cases and case not in cases:
            continue
        if states and state is not None and state not in states:
            continue
        for wake in wakes:
            out += specs(case, wake, SECOND_GRID[case] if second_grid else None, state)
    return out


def load(spec):
    """(record, arrays) of a current stored run, or None."""
    path = RUNS / spec.case / f"{spec.key}.json"
    if not path.exists():
        return None
    record = runner.read_record(json.loads(path.read_text()))
    if record["fingerprint"] != runner.fingerprint():
        return None
    return record, np.load(RUNS / spec.case / f"{spec.key}.npz")


def stored(tag):
    """A getter for ``data.load``: the stored runs of an experiment variant (no fingerprint check; other build)."""
    directory = OUT / (f"runs-{tag}" if tag else "runs")

    def get_(spec):
        record = runner.read_record(json.loads((directory / spec.case / f"{spec.key}.json").read_text()))
        return record, np.load(directory / spec.case / f"{spec.key}.npz")
    return get_


# ACC_PARAMS: Parameterizations fields of a variant, as JSON (e.g. {"angle_fade": 2.5}). The run is stored in
# the variant's own directory (ACC_TAG) under the key of the plain specification, so that a variant and its
# parent are matched by key; the record carries the variant's settings.
PARAMS = json.loads(os.environ.get("ACC_PARAMS", "{}"))


def execute(spec, mutate=None):
    """Solve ``spec`` and store it; the wake code 3 plane fields are added to the arrays."""
    from dataclasses import replace
    from dtcc_qes import wind
    key = spec.key
    if PARAMS:
        if not TAG:
            raise SystemExit("ACC_PARAMS needs ACC_TAG: a variant must not overwrite the parent's runs")
        spec = replace(spec, parameterizations={**dict(spec.parameterizations), **PARAMS})
    held, original = {}, wind.run

    def capture(*args, **kwargs):
        held["result"] = original(*args, **kwargs)
        return held["result"]
    wind.run = capture
    try:
        record, arrays = runner.run(spec)
    finally:
        wind.run = original
    result = held["result"]
    if result.wake is not None:
        plane = result.sample(2.0, "nearest")
        arrays.update(wake_deficit=plane.wake_deficit.astype(np.float32), wake_tke=plane.wake_tke.astype(np.float32),
                      wake_inflow_tke=np.float64(result.metadata["wake"]["inflow_tke"]["value"]))
    if PARAMS:
        record.update(key=key, variant=PARAMS)
    runner.write(record, arrays, RUNS / spec.case)
    return record


FLAG_NAMES = {1: "open", 3: "upwind cavity", 4: "near-wake cavity", 5: "far wake", 6: "street canyon", 9: "sidewall",
              10: "rooftop"}


def flags(spec):
    """Cell flags of the 2 m layer after the parameterizations (cached); from a run cut short at 25 sweeps."""
    from dataclasses import replace
    from dtcc_qes import wind
    path = OUT / "flags" / f"{spec.key}.npy"
    if path.exists():
        return np.load(path)
    args = runner.inputs(replace(spec, max_iterations=25, turbulence=False))
    result = wind.run(args["city"], args["profile"], **args["run"])
    layer = int(np.abs(np.asarray(result.z, dtype=np.float64) - 2.0).argmin())
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.asarray(result.cell_flags[layer], dtype=np.int8))
    return np.load(path)


def get(spec):
    stored = load(spec)
    if stored is None:
        execute(spec)
        stored = load(spec)
    return stored


def _work(payload):
    from aij.runspec import RunSpec
    spec = RunSpec.from_dict(payload)
    if load(spec) is None:
        record = execute(spec)
        return spec.name, record["wall_seconds"], record["diagnostics"].get("iterations")
    return spec.name, 0.0, None


def run_many(specs_, jobs=4):
    """Run the missing specs, one fresh process per run."""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    todo = [s for s in {s.key: s for s in specs_}.values() if load(s) is None]
    print(f"{len(todo)} of {len(specs_)} runs missing", flush=True)
    env = dict(os.environ)
    env.setdefault("OMP_NUM_THREADS", str(max(1, (os.cpu_count() or 4) // jobs)))

    def one(spec):
        done = subprocess.run([sys.executable, __file__, "--one", json.dumps(spec.to_dict())], env=env,
                              capture_output=True, text=True)
        tail = done.stdout.strip().splitlines()[-1:] if done.returncode == 0 else [done.stderr[-2000:]]
        print(f"  {spec.name}: {'ok' if done.returncode == 0 else 'FAILED'} {tail[0] if tail else ''}", flush=True)
        return done.returncode
    with ThreadPoolExecutor(jobs) as pool:
        failed = sum(code != 0 for code in pool.map(one, todo))
    if failed:
        raise SystemExit(f"{failed} runs failed")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=None)
    parser.add_argument("--second-grid", action="store_true")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--wakes", default="23")
    parser.add_argument("--states", default=None, help="comma-separated states, e.g. before or 0H,1H")
    parser.add_argument("--one", default=None, help="internal: run one RunSpec given as JSON")
    args = parser.parse_args()
    if args.one:
        print(*_work(json.loads(args.one)))
        raise SystemExit(0)
    run_many(all_specs(tuple(int(w) for w in args.wakes), second_grid=args.second_grid, cases=args.cases,
                       states=args.states.split(",") if args.states else None), args.jobs)

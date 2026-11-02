"""Run AIJ validation campaigns through dtcc-qes (AIJ_VALIDATION_PLAN.md, Phase 2 onwards).

    uv run --group validate python validation/run_validation.py --campaign smoke
    uv run --group validate python validation/run_validation.py --campaign convergence --case E

Each run executes in its own process (for an honest peak memory) and writes
validation/output/runs/<case>/<key>.{json,npz}. A run whose record exists with
the same code fingerprint is skipped unless --force is given. ``--jobs N`` runs
N processes at once, each with OMP_NUM_THREADS = cores // N unless it is set.
Results do not depend on the thread count (checked bit for bit in Phase 5), but
wall times of parallel runs are not cost evidence.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from aij import runner
from aij.campaigns import campaign
from aij.runspec import RunSpec

OUTPUT = Path(__file__).resolve().parent / "output" / "runs"


def _directory(output: Path, spec: RunSpec) -> Path:
    return output / spec.case


def _summary(record: dict) -> str:
    diagnostics, probes = record["diagnostics"], record["probes"]
    k = [v for v in probes["K"] if v is not None]
    fallback = sum(m != "linear" for m in probes["method"])
    return (f"{record['name']}: {record['grid']['cells'] / 1e6:.1f} M cells, {diagnostics['iterations']} it, "
            f"max div {diagnostics['max_divergence']:.1e}, {record['wall_seconds']:.1f} s "
            f"(prep {record['timings']['city_preparation_seconds']:.1f} s), "
            f"{record['peak_rss_bytes'] / 2 ** 30:.2f} GiB, K median {sorted(k)[len(k) // 2]:.3f}, "
            f"{fallback} fallback probes")


def worker(spec_path: Path, output: Path) -> None:
    spec = RunSpec.from_dict(json.loads(spec_path.read_text()))
    record, arrays = runner.run(spec)
    runner.write(record, arrays, _directory(output, spec))


def _solve(spec: RunSpec, output: Path, env: dict) -> int:
    directory = _directory(output, spec)
    directory.mkdir(parents=True, exist_ok=True)
    spec_path = directory / f".{spec.key}.spec.json"
    spec_path.write_text(json.dumps(spec.to_dict()))
    try:
        done = subprocess.run([sys.executable, __file__, "--worker", str(spec_path), "--output", str(output)],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        return done.returncode, "\n".join(done.stderr.strip().splitlines()[-5:])
    finally:
        spec_path.unlink(missing_ok=True)


def execute(specs, output: Path = OUTPUT, *, force=False, jobs=1, in_process=False, log=print) -> list[RunSpec]:
    """Run every spec whose record is missing or stale; return the specs that failed."""
    fingerprint = runner.fingerprint()
    pending = []
    for spec in specs:
        existing = runner.load(_directory(output, spec), spec.key)
        if existing and existing["fingerprint"] == fingerprint and not force:
            continue
        pending.append(spec)
    log(f"{len(specs) - len(pending)} of {len(specs)} runs are current; running {len(pending)} with {jobs} job(s)")
    env = dict(os.environ)
    if jobs > 1:
        env.setdefault("OMP_NUM_THREADS", str(max(1, (os.cpu_count() or 1) // jobs)))
    failed = []
    if in_process:
        for spec in pending:
            record, arrays = runner.run(spec)
            runner.write(record, arrays, _directory(output, spec))
            log(f"{spec.key} {_summary(record)}")
        return failed
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(_solve, spec, output, env): spec for spec in pending}
        for n, future in enumerate(as_completed(futures), 1):
            spec = futures[future]
            tag = f"[{n}/{len(pending)}] {spec.key}"
            code, error = future.result()
            if code:
                failed.append(spec)
                log(f"{tag} FAILED {spec.name} (exit {code}):\n{error}")
            else:
                log(f"{tag} {_summary(runner.load(_directory(output, spec), spec.key))}")
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--campaign", default="smoke")
    parser.add_argument("--case", choices=("D", "E"), help="run only this case")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--force", action="store_true", help="rerun even when a matching record exists")
    parser.add_argument("--in-process", action="store_true", help="run in this process (no peak-memory isolation)")
    parser.add_argument("--list", action="store_true", help="list the runs and exit")
    parser.add_argument("--jobs", type=int, default=1, help="runs at once (default 1)")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return worker(args.worker, args.output)

    specs = [s for s in campaign(args.campaign) if args.case in (None, s.case)]
    if args.list:
        fingerprint = runner.fingerprint()
        for n, spec in enumerate(specs, 1):
            existing = runner.load(_directory(args.output, spec), spec.key)
            done = existing and existing["fingerprint"] == fingerprint
            print(f"[{n}/{len(specs)}] {spec.key} {spec.name}{' (done)' if done else ''}")
        return
    started = time.perf_counter()
    failed = execute(specs, args.output, force=args.force, jobs=args.jobs, in_process=args.in_process,
                     log=lambda line: print(line, flush=True))
    print(f"{len(failed)} failed; {time.perf_counter() - started:.0f} s", flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

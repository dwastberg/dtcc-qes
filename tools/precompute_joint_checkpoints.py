"""Compute expensive future zero-start checkpoints without changing a manifest.

Supplemental scheduling is recorded separately. Publishing uses an exclusive
hard link: a supplemental process never overwrites an existing primary cache.
If both schedules execute a budget, both executions remain archived and costed.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import argparse
import os

from run_joint_grid_verification import (atomic_json, digest, fingerprint,
    load_references, obtain_checkpoint, read, resource_estimate, tasks)


def publish(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except FileExistsError:
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Existing primary study directory")
    parser.add_argument("--backend", choices=("serial", "openmp"), required=True)
    parser.add_argument("--sweeps", type=int, required=True)
    parser.add_argument("--tasks", nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or not 1 <= args.sweeps <= 100000:
        parser.error("Require 1..4 workers and 1..100000 sweeps")
    manifest_path = args.output/"manifest.json"
    manifest = read(manifest_path)
    metadata = manifest["metadata"]
    for path, expected in metadata["source_sha256"].items():
        if digest(path) != expected:
            raise ValueError("Primary sources changed")
    executable = Path(metadata["executable"])
    if digest(executable) != metadata["executable_sha256"]:
        raise ValueError("Primary executable changed")
    _, configs, _, hashes = load_references(args.backend)
    if hashes != metadata["references_sha256"] or configs != manifest["configurations"]:
        raise ValueError("Primary references changed")
    chosen = [t for t in tasks() if t["id"] in args.tasks]
    if {t["id"] for t in chosen} != set(args.tasks):
        parser.error("Unknown task ID")
    plan_path = args.output/"supplemental.json"
    plan = dict(primary_manifest_sha256=digest(manifest_path), study_identity=fingerprint(metadata),
        source=str(Path(__file__)), source_sha256=digest(__file__), workers=args.workers,
        sweeps=args.sweeps, tasks=chosen, backend=metadata["backend"],
        primary_workers=metadata["workers"], maximum_combined_workers=metadata["workers"]+args.workers,
        estimated_additional_process_bytes=args.workers*max(resource_estimate(t, configs)["estimated_process_bytes"] for t in chosen),
        policy="independent zero starts; never overwrite primary cache; retain duplicate work and charge its cost")
    if plan_path.exists():
        if read(plan_path)["plan"] != plan:
            parser.error("Supplemental plan changed")
    else:
        atomic_json(plan_path, dict(utc=datetime.now(timezone.utc).isoformat(), plan=plan))
    def execute(task):
        run, origin = obtain_checkpoint(task, configs, executable, metadata["backend"], args.sweeps,
            metadata["allocation_ceiling"], args.output/"supplemental", fingerprint(metadata))
        source = Path(origin["path"])
        target = args.output/source.relative_to(args.output/"supplemental")
        linked = publish(source, target)
        atomic_json(args.output/"supplemental"/"results"/(task["id"]+".json"),
            dict(origin=origin, published_exclusively=linked, target=str(target),
                 run_sha256=fingerprint(run), finished_utc=datetime.now(timezone.utc).isoformat()))
        print(task["id"], args.sweeps, "archived; exclusively published", linked, flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(execute, task) for task in chosen]):
            future.result()


if __name__ == "__main__":
    main()

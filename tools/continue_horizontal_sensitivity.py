"""Continue a C2b archive with bounded concurrent native workers; no timing claims."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import subprocess
from threading import Lock

import numpy as np

from run_horizontal_sensitivity import assess, digest, input_text, references, tasks, write


def validate(doc):
    metadata = doc["metadata"]
    for path, expected in metadata["source_sha256"].items():
        if digest(path) != expected:
            raise ValueError(f"Acquisition source changed: {path}")
    if digest(metadata["executable"]) != metadata["executable_sha256"]:
        raise ValueError("Worker changed")
    if digest(metadata["reference"]) != metadata["reference_sha256"]:
        raise ValueError("Reference archive changed")
    for continuation in metadata.get("continuations", []):
        if digest(continuation["source"]) != continuation["sha256"]:
            raise ValueError("Continuation source changed")


def next_budget(doc, task):
    failed = [r["checkpoints"][0]["iterations"] for r in doc["attempts"] if r["task"]["id"] == task["id"]]
    return 0 if task["kind"] == "probe" else min(doc["metadata"]["max_n"],
        max(doc["metadata"]["initial_n"], 2*max(failed, default=0)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2, 3), default=2)
    args = parser.parse_args()
    doc = json.loads(gzip.decompress((args.output/"raw.json.gz").read_bytes()))
    validate(doc)
    metadata = doc["metadata"]
    refs, _ = references(Path(metadata["reference"]))
    done = {r["task"]["id"] for r in doc["runs"]}
    remaining = [t for t in tasks() if t["id"] not in done]
    if not remaining:
        print("Matrix already complete")
        return
    source = str(Path(__file__).resolve())
    metadata.setdefault("continuations", []).append(dict(utc=datetime.now(timezone.utc).isoformat(),
        source=source, sha256=digest(source), jobs=args.jobs, remaining_tasks=[t["id"] for t in remaining],
        timing_scope="concurrent numerical diagnosis; no performance comparison"))
    lock = Lock()
    write(doc, args.output, refs)

    def run_task(task):
        n = next_budget(doc, task)
        while True:
            print(task["id"], "N=", n, flush=True)
            proc = subprocess.run([metadata["executable"], "tower", "--horizontal", str(task["direction"]), str(n)],
                input=input_text(doc["configurations"][task["family"]], task), text=True, capture_output=True,
                check=True, timeout=1800)
            if proc.stderr:
                raise RuntimeError(proc.stderr)
            run = json.loads(proc.stdout) | {"task": task}
            if run["backend"] != metadata["reference_backend"]:
                raise ValueError("Worker/reference backend mismatch")
            np.testing.assert_array_equal(np.array(run["z_faces"], dtype=np.float32),
                                           doc["configurations"][task["family"]]["expected_faces"])
            accepted = n > 0 and assess(run)["accepted"]
            final = n == 0 or accepted or n >= metadata["max_n"]
            with lock:
                doc["runs" if final else "attempts"].append(run)
                write(doc, args.output, refs)
            if final:
                print(task["id"], "INITIAL ONLY" if n == 0 else "PASS" if accepted else "FAIL; comparison withheld", flush=True)
                return
            n = min(2*n, metadata["max_n"])

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(run_task, remaining))
    print("C2b continuation complete", flush=True)


if __name__ == "__main__":
    main()

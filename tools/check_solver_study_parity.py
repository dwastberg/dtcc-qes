"""Compare bounded study diagnostics, including the last per-cell update.

Timing, resource accounting and backend identity are deliberately reported
separately from numerical comparisons. Historical archives are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

IGNORED = {"backend", "threads", "peak_rss_bytes", "solver_workspace_bytes"}


def numerics(value):
    if isinstance(value,dict):
        return {k:numerics(v) for k,v in value.items() if k not in IGNORED and not k.endswith("_seconds")}
    if isinstance(value,list):
        return [numerics(v) for v in value]
    return value


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("baseline-serial","baseline-openmp","candidate-serial","candidate-openmp"):
        ap.add_argument("--"+name,type=Path,required=True)
    ap.add_argument("--ordering-migration",action="store_true")
    ap.add_argument("--output",type=Path,required=True)
    args = ap.parse_args()
    binaries = {name:getattr(args,name.replace("-","_")) for name in
                ("baseline-serial","baseline-openmp","candidate-serial","candidate-openmp")}
    rows, comparisons = [], []
    start = time.monotonic()
    results = {}
    for spacing in ("2","stretched"):
        for precision in ("float32","float64"):
            for name,binary in binaries.items():
                modes = ("default","lexicographic") if args.ordering_migration and name.startswith("candidate") else ("default",)
                for mode in modes:
                    command = [str(binary.resolve()),"tower",spacing,"33","2",
                               "--diagnose" if precision == "float32" else "--float64"]
                    if mode == "lexicographic": command.append("--lexicographic")
                    remaining = 180-(time.monotonic()-start)
                    if remaining <= 0: raise TimeoutError("Study comparison matrix exceeded 180 s")
                    env = os.environ.copy()
                    env.pop("DTCC_QES_STUDY_ORDER",None)
                    proc = subprocess.run(command,check=True,text=True,capture_output=True,
                                          env=env,timeout=min(30,remaining))
                    result = json.loads(proc.stdout)
                    results[spacing,precision,name,mode] = numerics(result)
                    canonical = json.dumps(numerics(result),sort_keys=True,allow_nan=False).encode()
                    rows.append(dict(command=command,spacing=spacing,precision=precision,mode=mode,
                        backend=result["backend"],numerical_sha256=hashlib.sha256(canonical).hexdigest(),
                        solver_workspace_bytes=result["solver_workspace_bytes"],
                        checkpoints=[r["iterations"] for r in result["checkpoints"]]))
            for backend in ("serial","openmp"):
                baseline = "baseline-openmp" if args.ordering_migration else "baseline-"+backend
                a = results[spacing,precision,baseline,"default"]
                b = results[spacing,precision,"candidate-"+backend,"default"]
                comparisons.append(dict(spacing=spacing,precision=precision,backend=backend,
                    ordering="default",passed=a==b))
                if args.ordering_migration:
                    comparisons.append(dict(spacing=spacing,precision=precision,backend=backend,ordering="lexicographic",
                        passed=results[spacing,precision,"baseline-serial","default"] ==
                               results[spacing,precision,"candidate-"+backend,"lexicographic"]))
    report = dict(passed=all(c["passed"] for c in comparisons),per_worker_seconds=30,matrix_seconds=180,
        elapsed_seconds=time.monotonic()-start,ordering_migration=args.ordering_migration,
        executable_sha256={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in binaries.items()},
        ignored_resource_fields=sorted(IGNORED),ignored_timing_suffix="_seconds",runs=rows,comparisons=comparisons)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(passed=report["passed"],comparisons=len(comparisons),runs=len(rows))))
    if not report["passed"]: raise SystemExit("Study numerical outputs differ")


if __name__ == "__main__":
    main()

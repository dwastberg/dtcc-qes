"""Bounded S3 monitoring overhead on fixed work, with frozen S2/S3 sources.

Native workers run sequentially: 30 s each, 180 s for the declared matrix.
Builds are separately bounded. This measures cost, never solution accuracy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time

import profile_solver_baseline as common
from profile_solver_s2 import source_files

ROOT = Path(__file__).resolve().parents[1]


def audit(output):
    manifest = json.loads((output / "manifest.json").read_text())
    for name, sha in manifest["files"].items():
        if common.digest((output / name).read_bytes()) != sha:
            raise ValueError(f"Changed S3 profile evidence: {name}")
    summary = json.loads((output / "summary.json").read_text())
    if not summary["completed"] or not summary["parity_passed"]:
        raise ValueError("Incomplete S3 profile or numerical fingerprint mismatch")
    return dict(passed=True, files=len(manifest["files"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-archive", type=Path)
    parser.add_argument("--candidate-archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "build/solver-control-s3-profile")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.audit:
        print(json.dumps(audit(output))); return
    if not args.baseline_archive or not args.candidate_archive:
        parser.error("both source archives are required")
    output.mkdir(parents=True, exist_ok=False)
    work = args.work_dir.resolve()
    executables, sources = {}, {}
    for label, archive_path in (("s2", args.baseline_archive), ("s3", args.candidate_archive)):
        tree = work / label
        tree.mkdir(parents=True, exist_ok=False)
        with tarfile.open(archive_path) as archive:
            archive.extractall(tree, filter="data")
        if label == "s2":
            shutil.copyfile(ROOT / "tools/solver_monitor_probe.cpp", tree / "tools/solver_monitor_probe.cpp")
            with (tree / "CMakeLists.txt").open("a") as cmake:
                cmake.write('\nadd_executable(solver_monitor_probe tools/solver_monitor_probe.cpp $<TARGET_OBJECTS:qesbridge>)\n'
                    'target_link_libraries(solver_monitor_probe PRIVATE dtcc_qes_internal)\n'
                    'target_compile_definitions(solver_monitor_probe PRIVATE DTCC_QES_MONITOR_BASELINE)\n')
        files = source_files(tree)
        sources[label] = common.archive_files(output / f"{label}-probe-sources.tar.gz", files, tree)
        build = work / f"{label}-build"
        subprocess.run(["cmake", "-S", str(tree), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                        f"-DPython_EXECUTABLE={sys.executable}", "-DDTCC_QES_OPENMP=ON", "-DDTCC_QES_BUILD_TESTS=ON"],
                       capture_output=True, text=True, check=True, timeout=120)
        result = subprocess.run(["cmake", "--build", str(build), "--target", "solver_monitor_probe", "-j12"],
                                capture_output=True, text=True, timeout=180)
        (output / f"{label}-build.log").write_text(result.stdout + result.stderr)
        result.check_returncode()
        executables[label] = build / "solver_monitor_probe"
    layers = json.loads((ROOT / "docs/data/solver-control-s2/baseline-corrected/runs/00-openmp-plain-float32-1t.json").read_text())["grid"]["solver_layer_thicknesses"]
    choices = [("s2", "disabled")] + [("s3", mode) for mode in
               ("disabled", "planes", "trend-checkpoint", "trend-continuous")]
    matrix = [(precision, team, repeat, label, mode)
              for team, repeat in [(1, 0), (2, 0), (4, 0), (8, 0), (4, 1), (4, 2)]
              for precision in ("float32", "float64") for label, mode in choices]
    common.write_json(output / "protocol.json", dict(
        utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(), cpu_count=os.cpu_count(),
        baseline_source_id="sha256:" + common.digest(args.baseline_archive.read_bytes()),
        candidate_source_id="sha256:" + common.digest(args.candidate_archive.read_bytes()), sources=sources,
        matrix=matrix, per_worker_seconds=30, total_matrix_seconds=180,
        geometry="S0 tower: four 12 m squares at (22,22),(42,22),(22,42),(42,42), heights 7.9/7.9/7.9/23.7 m; 160 m square, 0.5 m xy",
        solver_layer_thicknesses=layers, iterations=40, checkpoint_cadence=10,
        monitor="ROI [0,80)x[0,80); heights 1.5/1.75 m; all five mandatory receptors at both heights; short/long spans 1/2; 8 summaries; no optional global mass scan; low-flow threshold unset",
        modes={"disabled":"No monitor; same blocks of ten whole sweeps in both revisions",
               "planes":"Compiled monitor and slab/regional-flux checkpoints",
               "trend-checkpoint":"Planes plus residual collection on each checkpoint's final sweep",
               "trend-continuous":"Planes plus residual collection on every sweep"},
        timing="steady_clock phase brackets only; actual OpenMP team established before timer; process setup, input parsing and output fingerprinting excluded; full centered finalization included; native timings exclude Python/NumPy",
        memory="Process high-water RSS includes preparation; monitor bytes cover owned buffer capacities and remain constant across checkpoints",
        parity="FNV1a64 field fingerprints and exact final norm/mass across modes and revisions; full 429-case bitwise parity is a separate gate",
        limitations="Short matched-work local measurements, no convergence/reference trajectory, no accuracy or universal timing claim"))
    rows, start = [], time.monotonic()
    stdin = " ".join(map(str, layers))
    for i, (precision, team, repeat, label, mode) in enumerate(matrix):
        remaining = 180 - (time.monotonic() - start)
        row = dict(precision=precision, requested_threads=team, repeat=repeat, revision=label, mode=mode)
        if remaining <= 0:
            row["status"] = "skipped_total_budget"
        else:
            try:
                result = subprocess.run([str(executables[label]), precision, mode], input=stdin, text=True,
                    capture_output=True, timeout=min(30, remaining),
                    env=os.environ | {"OMP_NUM_THREADS":str(team), "OMP_DYNAMIC":"FALSE"})
                if result.returncode:
                    row.update(status="failed", stderr=result.stderr[-6000:])
                else:
                    row.update(json.loads(result.stdout), status="completed")
                    if row["team"] != team or row["iterations"] != 40 or row["shape"] != [92,320,320]:
                        row["status"] = "unexpected_team_grid_or_work"
            except subprocess.TimeoutExpired:
                row.update(status="timeout", limit_seconds=min(30, remaining))
        name = f"runs/{i:02d}-{label}-{mode}-{precision}-{team}t-{repeat}.json"
        common.write_json(output / name, row)
        rows.append(row)
        print(f"{i+1}/{len(matrix)} {label}/{mode}/{precision}/{team}t: {row['status']}", flush=True)
    keys = ("fingerprints_fnv1a64", "iterations", "max_change", "mass")
    parity = all(len(selected := [r for r in rows if r["precision"] == p and r["status"] == "completed"])
                 == len(matrix)//2 and all(all(r[k] == selected[0][k] for k in keys) for r in selected)
                 for p in ("float32", "float64"))
    common.write_json(output / "summary.json", dict(completed=all(r["status"] == "completed" for r in rows),
        parity_passed=parity, elapsed_seconds=time.monotonic()-start, runs=rows))
    common.write_json(output / "manifest.json", dict(files={p.relative_to(output).as_posix():common.digest(p.read_bytes())
        for p in output.rglob("*") if p.is_file()}))
    print(json.dumps(audit(output)))


if __name__ == "__main__":
    main()

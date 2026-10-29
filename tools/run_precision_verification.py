"""Opt-in float64 from-zero validation, then fixed-region lateral/x-y checks.

Immutable older archives remain failed or passing under their original arithmetic.
Each checkpoint is a fresh zero start using the production precision solver.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import platform
import subprocess

import numpy as np

from run_auto_grid_controls import HEIGHTS, POINTS, assess
from run_horizontal_sensitivity import (FAMILIES, DIRECTIONS, digest, references,
    frozen_locations, comparison, values, array, audit_point)
from run_auto_grid_controls import rectangles


def tasks(phase):
    if phase == "precision":
        jobs = [dict(id=f"base/{f}/{w}/{r}", family=f, direction=w, resolution=r,
                     extent=80, precision="float64")
                for f in FAMILIES for w in DIRECTIONS for r in (2, 1, .5)]
        jobs += [dict(id=f"legacy/{z}/{w}", family=f"legacy-{z}", direction=w,
                      resolution=2, extent=80, precision="float64")
                 for z in (.5, .25) for w in DIRECTIONS]
        jobs += [dict(id=f"float32/{f}/270/2", family=f, direction=270,
                      resolution=2, extent=80, precision="float32") for f in FAMILIES]
        return jobs
    if phase == "verification":
        return [dict(id=f"lateral/{e}/{f}/{w}/1", family=f, direction=w,
                     resolution=1, extent=e, precision="float64")
                for e in (160, 240) for f in FAMILIES for w in DIRECTIONS]
    raise ValueError("Unknown phase")


def input_text(task, configs):
    legacy = task["family"].startswith("legacy-")
    dz = float(task["family"].split("-")[1]) if legacy else None
    layers = [dz]*int(64/dz) if legacy else configs[task["family"]]["layers_input"]
    rects = rectangles("tower")
    if legacy:
        rects = [[x, y, w, length, 24 if h > 20 else 8] for x, y, w, length, h in rects]
    extent = task["extent"]
    origin = (80-extent)/2
    data = [task["resolution"], origin, origin, extent, extent,
            len(layers), len(HEIGHTS), len(rects), 0, *layers, *HEIGHTS,
            *[v for rect in rects for v in rect]]
    return " ".join(format(v, ".17g") for v in data)+"\n"


def gate(run):
    result = assess(run)
    result["ten_times_tighter_accepted"] = result["accepted"] and all(
        r["ten_times_tighter_pass"] for h in result["heights"].values() for r in h["residuals"])
    return result


def require_precision_reference(doc):
    expected = {t["id"] for t in tasks("precision")}
    actual = {r["task"]["id"] for r in doc["runs"]}
    if expected != actual or len(actual) != len(doc["runs"]):
        raise ValueError("Precision matrix incomplete")
    doubles = [r for r in doc["runs"] if r["task"]["precision"] == "float64"]
    if not all(gate(r)["accepted"] and r["start"] == "zero" and r["precision"] == "float64" for r in doubles):
        raise ValueError("Float64 from-zero references failed common gate")
    if not any(gate(r)["ten_times_tighter_accepted"] for r in doubles):
        raise ValueError("Require a successfully ten-times tighter subset")


def summarize(doc, precision_doc=None):
    runs = doc["runs"]
    checks = [dict(task=r["task"], **gate(r), peak_rss_bytes=r["peak_rss_bytes"],
                   solver_workspace_bytes=r["solver_workspace_bytes"],
                   total_solve_seconds=sum(c["solve_seconds"] for c in r["checkpoints"]),
                   final_solve_seconds=r["checkpoints"][-1]["solve_seconds"],
                   top_band_max_divergence=r["checkpoints"][-1]["top_band_max_divergence"])
              for r in runs]
    result = dict(metadata=doc["metadata"], complete=len(runs) == len(tasks(doc["metadata"]["phase"])),
                  runs=checks, accepted=sum(c["accepted"] for c in checks),
                  tighter_accepted=sum(c["ten_times_tighter_accepted"] for c in checks), comparisons=[])
    if precision_doc is None:
        return result
    available = {r["task"]["id"]: r for r in precision_doc["runs"]+runs}
    frozen = doc["metadata"]["frozen_critical_indices"]
    initialization = []
    for family in FAMILIES:
        for wind in DIRECTIONS:
            pairs = [(f"base/{family}/{wind}/2", f"base/{family}/{wind}/1", "xy_2_to_1"),
                     (f"base/{family}/{wind}/1", f"base/{family}/{wind}/0.5", "xy_1_to_0.5"),
                     (f"base/{family}/{wind}/1", f"lateral/160/{family}/{wind}/1", "extent_80_to_160"),
                     (f"lateral/160/{family}/{wind}/1", f"lateral/240/{family}/{wind}/1", "extent_160_to_240")]
            for aid, bid, label in pairs:
                if aid not in available or bid not in available:
                    continue
                a, b = available[aid], available[bid]
                accepted = gate(a)["accepted"] and gate(b)["accepted"]
                for height in HEIGHTS:
                    for region in ("all", "away4m"):
                        row = dict(comparison=label, family=family, direction=wind, height=height,
                                   region=region, matched_accuracy=accepted)
                        if accepted:
                            row.update(comparison(a, b, height, frozen[f"{family}/{wind}/{height}/{region}"], region))
                        else:
                            row["withheld_reason"] = "Failed common residual/stability gate"
                        result["comparisons"].append(row)
                    for stage in ("profile", "initial"):
                        av, bv = array(values(a, height, stage)), array(values(b, height, stage))
                        am, bm = np.isfinite(av).all(axis=1), np.isfinite(bv).all(axis=1)
                        keep = am & bm
                        delta = np.abs(np.linalg.norm(av[keep], axis=1)-np.linalg.norm(bv[keep], axis=1))/5
                        initialization.append(dict(comparison=label, family=family, direction=wind,
                            height=height, stage=stage, solid_fluid_transitions=int((am != bm).sum()),
                            max_component_difference=float(np.max(np.abs(av[keep]-bv[keep]))),
                            p95_abs_delta_K=float(np.percentile(delta, 95)), max_abs_delta_K=float(delta.max()),
                            certified_solution=False))
    result["initialization"] = initialization
    result["point_audits"] = [dict(task=key, **audit_point(run, height, point, stage))
        for key, run in available.items() if run["task"]["precision"] == "float64"
            and not run["task"]["family"].startswith("legacy-")
        for height in HEIGHTS for point in ([27, 21], [21, 23], [51, 35])
        for stage in ("profile", "initial", "final")]
    result["joint_scope_established"] = False
    result["scope_note"] = "Horizontal refinement is at 80 m extent; lateral refinement is at 1 m spacing. No joint adequate-extent fine-grid claim."
    return result


def write(doc, output, precision_doc):
    output.mkdir(parents=True, exist_ok=True)
    for name, contents in (("raw.json.gz", gzip.compress(json.dumps(doc, allow_nan=False).encode(), mtime=0)),
                           ("summary.json", (json.dumps(summarize(doc, precision_doc), indent=2, allow_nan=False)+"\n").encode())):
        temporary = output/(name+".tmp")
        temporary.write_bytes(contents)
        temporary.replace(output/name)


def execute(task, configs, executable, initial_n, max_n):
    attempts = []
    n = initial_n
    # A predeclared subset must pass the full gate at ten-times tighter residual
    # bounds at all checkpoints, rather than cherry-picking a final residual.
    tight = task["precision"] == "float64" and task["extent"] == 80 and task["direction"] == 270
    while True:
        print(task["id"], "N=", n, "tight subset" if tight else "", flush=True)
        cmd = [str(executable), "tower", "--horizontal", str(task["direction"]), str(n)]
        if task["precision"] == "float64":
            cmd.append("--float64")
        proc = subprocess.run(cmd, input=input_text(task, configs), text=True,
                              capture_output=True, check=True, timeout=7200)
        if proc.stderr:
            raise RuntimeError(proc.stderr)
        run = json.loads(proc.stdout)
        run["task"] = task
        if run["start"] != "zero" or run["precision"] != task["precision"] or run["disabled_mask"]:
            raise ValueError("Worker precision/start/model mismatch")
        if not task["family"].startswith("legacy-"):
            np.testing.assert_array_equal(np.asarray(run["z_faces"], np.float32), configs[task["family"]]["expected_faces"])
        check = gate(run)
        if (check["ten_times_tighter_accepted"] if tight else check["accepted"]) or n >= max_n:
            print(task["id"], "PASS" if check["accepted"] else "FAIL", "tight=", check["ten_times_tighter_accepted"], flush=True)
            return run, attempts
        attempts.append(run)
        n = min(n*2, max_n)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("precision", "verification"), required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--precision-reference", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--max-n", type=int, default=8000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.n <= args.max_n <= 25000 or not 1 <= args.workers <= 4:
        parser.error("Require 1 <= n <= max-n <= 25000 and 1..4 workers")
    refs, configs = references(args.reference)
    precision_doc = None
    if args.phase == "verification":
        if args.precision_reference is None:
            parser.error("Verification requires --precision-reference")
        precision_doc = json.loads(gzip.decompress(args.precision_reference.read_bytes()))
        require_precision_reference(precision_doc)
    executable = args.executable.resolve()
    sources = (Path(__file__), Path("tools/vertical_grid_study.cpp"), Path("src/qes_core/dtcc/precision_solver.cpp"),
               Path("src/qes_core/dtcc/precision_solver.h"), Path("src/qes_core/dtcc/divergence.cpp"), Path("src/qes_core/dtcc/qes_inputs.cpp"),
               Path("tools/run_horizontal_sensitivity.py"), Path("tools/run_auto_grid_controls.py"),
               Path("tools/run_vertical_grid_study.py"))
    metadata = dict(utc=datetime.now(timezone.utc).isoformat(), phase=args.phase, platform=platform.platform(),
        python=platform.python_version(), numpy=np.__version__, executable=str(executable),
        executable_sha256=digest(executable), source_sha256={str(p): digest(p) for p in sources},
        reference=str(args.reference), reference_sha256=digest(args.reference),
        precision_reference_sha256=digest(args.precision_reference) if args.precision_reference else None,
        qes_revision=Path("src/dtcc_qes/_qes_revision.txt").read_text().strip(),
        backend=next(iter(refs.values()))["backend"], workers=args.workers,
        initial_n=args.n, max_n=args.max_n, fixed_region_m=[3, 3, 77, 77],
        points=POINTS.tolist(), heights=list(HEIGHTS), Uref=5, world_sensor=[5, 5],
        frozen_critical_indices=frozen_locations(refs), away_region_distance_m=4,
        tight_subset="all float64 80 m tower cases at 270 degrees; all three checkpoint residuals",
        cost_scope="one diagnostic repetition; concurrent workers; no timing-ratio or preset claims",
        output_storage="float32 faces, geometry and coefficients; precision controls multiplier/RHS/correction arithmetic",
        targets=dict(max_scaled_residual=1e-3, rms_scaled_residual=1e-4, max_vector_change_over_Uref=1e-3,
                     p95_vector_change_over_Uref=5e-4, p95_abs_delta_K=.05, peak_relative=.05, critical_relative=.05))
    doc = dict(metadata=metadata, configurations=configs, runs=[], attempts=[])
    path = args.output/"raw.json.gz"
    if args.resume or args.summarize:
        doc = json.loads(gzip.decompress(path.read_bytes()))
        for key in metadata:
            if key != "utc" and doc["metadata"].get(key) != metadata[key]:
                parser.error(f"Changed configuration/source: {key}")
    elif path.exists():
        parser.error("Output exists; choose --resume or a new directory")
    if args.summarize:
        write(doc, args.output, precision_doc)
        return
    existing = {r["task"]["id"] for r in doc["runs"]}
    remaining = [t for t in tasks(args.phase) if t["id"] not in existing]
    # Freeze the region, critical locations, sources and input matrix on disk
    # before any newly measured field is available.
    write(doc, args.output, precision_doc)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, task, configs, executable, args.n, args.max_n) for task in remaining]
        for future in as_completed(futures):
            run, attempts = future.result()
            if run["backend"] != metadata["backend"]:
                raise ValueError("Backend/reference mismatch")
            doc["runs"].append(run)
            doc["runs"].sort(key=lambda r: r["task"]["id"])
            doc["attempts"].extend(attempts)
            write(doc, args.output, precision_doc)
    print(args.phase, "complete", flush=True)


if __name__ == "__main__":
    main()

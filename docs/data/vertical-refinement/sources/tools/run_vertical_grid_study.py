"""Run isolated native workers and assess the declared vertical-grid gate.

Run from the checkout, using the serial Release study target. Raw samples are
kept in a gzip JSON artifact so every mask, percentile and decision is auditable.
The summary contains timing comparisons only when both solves pass accuracy.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import platform
import random
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

GRIDS = ("2", "1", "0.5", "0.25", "stretched")
GEOMETRIES = ("isolated", "passage", "array", "tower")
TARGETS = {"max_residual": 1e-3, "rms_residual": 1e-4,
           "max_vector_change": 1e-3, "p95_vector_change": 5e-4}


def plane(checkpoint):
    values = np.array([v if v is not None else [np.nan] * 3
                       for v in checkpoint["velocity"]], dtype=float)
    return values, np.isfinite(values).all(axis=1)


def evaluate(run):
    checkpoints = run["checkpoints"]
    planes = [plane(c) for c in checkpoints]
    result = {"residuals": [], "changes": []}
    for c in checkpoints:
        scale = run["hmax"] / 5
        maximum = c["max_divergence"] * scale
        rms = c["rms_divergence"] * scale
        result["residuals"].append({
            "iterations": c["iterations"], "max_scaled": maximum, "rms_scaled": rms,
            "pass": maximum <= TARGETS["max_residual"] and rms <= TARGETS["rms_residual"],
            "ten_times_tighter_pass": maximum <= TARGETS["max_residual"] / 10
                                      and rms <= TARGETS["rms_residual"] / 10})
    for (a, amask), (b, bmask) in zip(planes, planes[1:]):
        mask = amask & bmask
        if not mask.any():
            raise ValueError("No common-fluid samples")
        delta = np.linalg.norm(b[mask] - a[mask], axis=1) / 5
        maximum, p95 = float(delta.max()), float(np.percentile(delta, 95))
        changes = int(np.count_nonzero(amask != bmask))
        result["changes"].append({"max": maximum, "p95": p95, "mask_changes": changes,
                                  "pass": maximum <= TARGETS["max_vector_change"]
                                          and p95 <= TARGETS["p95_vector_change"] and changes == 0})
    result["accepted"] = all(c["pass"] for c in result["residuals"] + result["changes"])
    passing = [c["iterations"] for c in result["residuals"] if c["pass"]]
    result["first_residual_passing_checkpoint"] = min(passing) if passing else None
    result["demonstration_sweeps"] = sum(c["iterations"] for c in checkpoints)
    result["valid_points"] = int(planes[-1][1].sum())
    return result


def timing(runs, field):
    values = [r[field] if field in r else r["checkpoints"][-1][field] for r in runs]
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def compare(a, b, mask):
    av, _ = plane(a["checkpoints"][-1])
    bv, _ = plane(b["checkpoints"][-1])
    av, bv = av[mask], bv[mask]
    ak, bk = np.linalg.norm(av, axis=1) / 5, np.linalg.norm(bv, axis=1) / 5
    delta = np.abs(ak - bk)
    indices = np.flatnonzero(mask)

    def location(local):
        index = int(indices[local])
        return [3 + 2 * (index % 38), 3 + 2 * (index // 38), 1.5]

    return {"p95_abs_delta_K": float(np.percentile(delta, 95)),
            "max_abs_delta_K": float(delta.max()),
            "peak_K": [float(ak.max()), float(bk.max())],
            "peak_relative_difference": float(abs(ak.max() - bk.max()) / bk.max()) if bk.max() else None,
            "peak_locations": [location(int(ak.argmax())), location(int(bk.argmax()))],
            "max_error_location": location(int(delta.argmax())),
            "low_speed_points_in_reference": int(np.count_nonzero(bk < .1)),
            "low_speed_max_abs_delta_K": float(delta[bk < .1].max()) if np.any(bk < .1) else None,
            "vector_max_delta_over_Uref": float((np.linalg.norm(av - bv, axis=1) / 5).max())}


def summarize(document):
    runs = document["runs"]
    summary = {"metadata": document["metadata"], "accuracy_targets": TARGETS,
               "runs": [], "groups": [], "comparisons": [], "flat_profile_sampling": {}}
    summary["analysis_software"] = {"python": platform.python_version(), "numpy": np.__version__}
    for run in runs:
        if run["grid"] in summary["flat_profile_sampling"]:
            continue
        faces = np.asarray(run["z_faces"], dtype=np.float32)
        centres = np.float32(.5) * (faces[:-1] + faces[1:])
        profile = np.log((centres.astype(float) + .1) / .1) / np.log(10.1 / .1)
        sampled_k = float(np.interp(1.5, centres, profile))
        exact_k = float(np.log(16) / np.log(101))
        summary["flat_profile_sampling"][run["grid"]] = {
            "sampled_K": sampled_k, "exact_K": exact_k,
            "bias_K": sampled_k - exact_k}
    for run in runs:
        summary["runs"].append({k: run[k] for k in ("geometry", "grid", "direction", "repeat")}
                               | evaluate(run))
    for case, direction in sorted({(r["geometry"], r["direction"]) for r in runs}):
        families = {g: [r for r in runs if (r["geometry"], r["direction"], r["grid"])
                       == (case, direction, g)] for g in GRIDS}
        families = {g: rs for g, rs in families.items() if rs}
        reference_planes = [plane(rs[0]["checkpoints"][-1]) for rs in families.values()]
        common = np.logical_and.reduce([m for _, m in reference_planes])
        union = np.logical_or.reduce([m for _, m in reference_planes])
        for grid, group in families.items():
            evaluations = [evaluate(r) for r in group]
            summary["groups"].append({"geometry": case, "direction": direction, "grid": grid,
                "accepted_all_repeats": all(e["accepted"] for e in evaluations),
                "layers": group[0]["layers"], "cells": group[0]["cells"],
                "aspect_ratio_max": float(2 / np.diff(group[0]["z_faces"]).min()),
                "roof_errors": group[0]["roof_errors"],
                "peak_rss_bytes": timing(group, "peak_rss_bytes"),
                "prep_seconds": timing(group, "prep_seconds"),
                "final_solve_seconds": timing(group, "solve_seconds"),
                "sampling_seconds": timing(group, "sampling_seconds"),
                "demonstration_solve_seconds": statistics.median(
                    sum(c["solve_seconds"] for c in r["checkpoints"]) for r in group),
                "representative_repeat": group[0]["repeat"],
                "scaled_residuals": evaluations[0]["residuals"],
                "changes": evaluations[0]["changes"],
                "n": group[0]["checkpoints"][0]["iterations"],
                "top_band_max_divergence": group[0]["checkpoints"][-1]["top_band_max_divergence"],
                "common_fluid_points": int(common.sum()),
                "solid_fluid_transitions_across_grids": int(np.count_nonzero(union != common))})
        for ga, gb in (("2", "0.5"), ("0.5", "0.25"), ("stretched", "0.5"),
                       ("stretched", "0.25")):
            if ga not in families or gb not in families:
                continue
            aa, bb = families[ga], families[gb]
            accepted = all(evaluate(r)["accepted"] for r in aa + bb)
            item = {"geometry": case, "direction": direction, "grids": [ga, gb],
                    "matched_accuracy": accepted, "common_fluid_points": int(common.sum())}
            if accepted:
                item |= compare(aa[0], bb[0], common)
                item["final_solve_time_ratio"] = (timing(aa, "solve_seconds")["median"]
                                                   / timing(bb, "solve_seconds")["median"])
            else:
                item["withheld_reason"] = "At least one grid failed common solve accuracy"
            summary["comparisons"].append(item)
    summary["accepted_runs"] = sum(r["accepted"] for r in summary["runs"])
    summary["total_runs"] = len(runs)
    return summary


def write(document, output):
    output.mkdir(parents=True, exist_ok=True)
    # mtime=0 makes compression reproducible; timings inside remain measurements.
    raw = output / "raw.json.gz.tmp"
    raw.write_bytes(gzip.compress(json.dumps(document).encode(), mtime=0))
    raw.replace(output / "raw.json.gz")
    summary = output / "summary.json.tmp"
    summary.write_text(json.dumps(summarize(document), indent=2) + "\n")
    summary.replace(output / "summary.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=Path("build/extension/vertical_grid_study"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--max-n", type=int, default=8000,
                        help="Double N after a failed accuracy check, up to this ceiling")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--geometries", nargs="+", choices=GEOMETRIES, default=GEOMETRIES)
    parser.add_argument("--grids", nargs="+", choices=GRIDS, default=GRIDS)
    parser.add_argument("--directions", nargs="+", type=float, default=[270, 315])
    parser.add_argument("--summarize", action="store_true", help="Reassess stored raw samples without running workers")
    args = parser.parse_args()
    if args.summarize:
        write(json.loads(gzip.decompress((args.output / "raw.json.gz").read_bytes())), args.output)
        return
    if not 1 <= args.n <= args.max_n <= 100000 or args.repeats < 1:
        parser.error("Require 1 <= n <= max-n <= 100000 and a positive repeat count")
    executable = args.executable.resolve()
    metadata = {"utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
                "machine": platform.machine(), "executable": str(args.executable),
                "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "qes_revision": Path("src/dtcc_qes/_qes_revision.txt").read_text().strip(),
                "initial_n": args.n, "max_n": args.max_n, "repeats": args.repeats,
                "bounds": [0, 0, 0, 80, 80, 64],
                "resolution": 2, "sampling_height": 1.5, "speed_observable": "magnitude of mean velocity",
                "Uref": 5, "reference_height": 10, "roughness_length": .1,
                "model_flags": {"rooftop": 1, "upwind_cavity": 2, "street_canyon": 1,
                                "street_intersection": 0, "wake": 2, "high_rise": 0, "sidewall": 1},
                "checkpoint_restart": "zero lambda, original parametrized initial velocity",
                "timing_scope": "native prepare includes profile, parametrizations, solver allocation; solve includes reset; sampling excludes residual diagnostic and JSON",
                "random_seed": 20261026}
    document = {"metadata": metadata, "runs": []}
    tasks = list(itertools.product(args.geometries, args.grids, args.directions, range(args.repeats)))
    random.Random(metadata["random_seed"]).shuffle(tasks)
    budgets = {}
    document["attempts"] = []
    for i, (case, grid, direction, repeat) in enumerate(tasks):
        key = (case, grid, direction)
        n = budgets.get(key, args.n)
        while True:
            print(f"{i+1}/{len(tasks)} {case} {grid} {direction:g} repeat {repeat}: N={n}", flush=True)
            process = subprocess.run([str(executable), case, grid, str(direction), str(n)],
                                     check=True, capture_output=True, text=True, timeout=600)
            run = json.loads(process.stdout)
            if process.stderr:
                raise RuntimeError(process.stderr)
            run["repeat"] = repeat
            if evaluate(run)["accepted"] or n >= args.max_n or key in budgets:
                budgets[key] = n
                break
            document["attempts"].append(run)
            write(document, args.output)
            n = min(n * 2, args.max_n)
        run["repeat"] = repeat
        document["runs"].append(run)
        write(document, args.output)
        status = "pass" if evaluate(run)["accepted"] else "FAIL accuracy"
        print(f"{i+1}/{len(tasks)} {case} {grid} {direction:g} repeat {repeat}: {status}", flush=True)


if __name__ == "__main__":
    main()

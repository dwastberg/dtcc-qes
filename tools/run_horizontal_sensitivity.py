"""C2b: fixed-z horizontal refinement, lateral bounds and initialization controls.

The C2a archives are immutable references. No production settings are selected.
Initial-only probes never count as accepted wind solutions or accuracy references.
"""
from __future__ import annotations

import os
import argparse
import gzip
import hashlib
import json
import math
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from run_auto_grid_controls import HEIGHTS, POINTS, assess, collocate, compare, height_run, rectangles

FAMILIES = ("auto", "uniform-0.5")
DIRECTIONS = (270, 315)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def references(path):
    doc = json.loads(gzip.decompress(path.read_bytes()))
    runs = {(r["family"], r["direction"], r["resolution"]): r for r in doc["runs"]
            if r["geometry"] == "tower" and r["control"] in ("base", "xy1") and r["repeat"] == 0}
    if len(runs) != 8 or not all(assess(r)["accepted"] for r in runs.values()):
        raise ValueError("Require all eight accepted C2a tower references")
    expected_flags = dict(rooftop=1, upwind_cavity=2, street_canyon=1, street_intersection=0,
                          wake=2, high_rise=0, sidewall=1)
    if (doc["metadata"]["model_flags"] != expected_flags or doc["metadata"]["Uref"] != 5
            or doc["metadata"]["qes_revision"] != Path("src/dtcc_qes/_qes_revision.txt").read_text().strip()):
        raise ValueError("Reference model/revision mismatch")
    configs = {p["family"]: p for p in doc["configurations"]["tower"] if p["control"] == "base"}
    return runs, configs


def wall_distance():
    yy, xx = np.meshgrid(POINTS, POINTS, indexing="ij")
    distances = []
    for x, y, w, length, _ in rectangles("tower"):
        dx = np.maximum(np.maximum(x-xx, xx-x-w), 0)
        dy = np.maximum(np.maximum(y-yy, yy-y-length), 0)
        distances.append(np.hypot(dx, dy))
    return np.min(distances, axis=0).ravel()


def values(run, height, stage="final"):
    if stage == "final":
        return height_run(run, height)["checkpoints"][-1]["velocity"]
    plane, = [p for p in run[stage+"_planes"] if p["height"] == height]
    return collocate(plane["velocity"], run["sample_x"], run["sample_y"])


def array(plane):
    return np.array([v if v is not None else [np.nan]*3 for v in plane], dtype=float)


def frozen_locations(refs):
    result = {}
    distance = wall_distance()
    for family in FAMILIES:
        for direction in DIRECTIONS:
            for height in HEIGHTS:
                v = array(values(refs[family, direction, 2], height))
                k = np.linalg.norm(v, axis=1)/5
                for region, keep in (("all", distance >= 0), ("away4m", distance >= 4)):
                    ids = np.flatnonzero(np.isfinite(k) & keep)
                    order = ids[np.argsort(-k[ids], kind="stable")[:10]]
                    result[f"{family}/{direction}/{height}/{region}"] = order.tolist()
    return result


def comparison(a, b, height, ids, region="all"):
    av, bv = array(values(a, height)), array(values(b, height))
    am, bm = np.isfinite(av).all(axis=1), np.isfinite(bv).all(axis=1)
    keep = wall_distance() >= (4 if region == "away4m" else 0)
    mask = am & bm & keep
    stats = dict(common_fluid_points=int(mask.sum()), solid_fluid_transitions=int(((am != bm) & keep).sum()),
                 region=region, height=height)
    if not mask.any():
        raise ValueError("No common-fluid comparison points")
    # Retain all original metrics, including a separate pair-local peak set.
    aa = a | {"checkpoints": [{"velocity": values(a, height)}]}
    bb = b | {"checkpoints": [{"velocity": values(b, height)}]}
    stats.update(compare(aa, bb, mask))
    stats["pair_local_critical_max_relative_difference"] = stats.pop("critical_max_relative_difference")
    frozen = np.asarray(ids, dtype=int)
    valid = mask[frozen]
    ak, bk = np.linalg.norm(av[frozen], axis=1)/5, np.linalg.norm(bv[frozen], axis=1)/5
    changes = np.abs(ak-bk)
    appreciable = bk >= .1
    relative = changes[appreciable & valid]/bk[appreciable & valid]
    low = changes[~appreciable & valid]
    stats.update(frozen_critical_indices=ids, invalid_frozen_critical_points=int((~valid).sum()),
        frozen_critical_K=[[float(x), float(y)] if ok else None for x, y, ok in zip(ak, bk, valid)],
        frozen_critical_max_relative_difference=float(relative.max()) if relative.size else None,
        frozen_critical_low_speed_max_abs_delta_K=float(low.max()) if low.size else None)
    stats["within_budget"] = bool(stats["p95_abs_delta_K"] < .05
        and (stats["peak_relative_difference"] is None or stats["peak_relative_difference"] < .05)
        and valid.all() and (not relative.size or relative.max() < .05)
        and (not low.size or low.max() < .05))
    return stats


def input_text(config, task):
    bounds = (-40, -40, 120, 120) if task["kind"] == "lateral" else (0, 0, 80, 80)
    x0, y0, x1, y1 = bounds
    rects = rectangles("tower")
    data = [task["resolution"], x0, y0, x1-x0, y1-y0, len(config["layers_input"]), len(HEIGHTS),
            len(rects), task.get("disabled", 0), *config["layers_input"], *HEIGHTS,
            *[v for rect in rects for v in rect]]
    return " ".join(format(v, ".17g") for v in data)+"\n"


def tasks():
    result = []
    for family in FAMILIES:
        for direction in DIRECTIONS:
            for resolution in (2, 1):
                result.append(dict(id=f"probe/{family}/{direction}/{resolution}", kind="probe",
                                   family=family, direction=direction, resolution=resolution))
            result.append(dict(id=f"fine/{family}/{direction}/0.5", kind="fine",
                               family=family, direction=direction, resolution=.5))
    for direction in DIRECTIONS:
        result.append(dict(id=f"lateral/uniform-0.5/{direction}/1", kind="lateral",
                           family="uniform-0.5", direction=direction, resolution=1))
    for disabled in (16, 31):
        for resolution in (2, 1):
            result.append(dict(id=f"ablation/{disabled}/{resolution}", kind="ablation",
                family="uniform-0.5", direction=270, resolution=resolution, disabled=disabled))
    return result


def audit_point(run, height, point, stage):
    x, y = map(np.asarray, (run["sample_x"], run["sample_y"]))
    plane = (run["checkpoints"][-1]["planes"] if stage == "final" else run[stage+"_planes"])
    p, = [p for p in plane if p["height"] == height]

    def brackets(axis, value):
        hi = int(np.searchsorted(axis, value))
        if hi == len(axis) or (hi == 0 and axis[hi] != value):
            raise ValueError("Audit point outside support")
        if axis[hi] == value:
            return [(hi, 1.)]
        weight = (value-axis[hi-1])/(axis[hi]-axis[hi-1])
        return [(hi-1, 1-weight), (hi, weight)]

    corners, v = [], np.zeros(3)
    valid = True
    for j, wy in brackets(y, point[1]):
        for i, wx in brackets(x, point[0]):
            index = j*len(x)+i
            velocity = p["velocity"][index]
            flags = p.get("flags", [])[index] if "flags" in p else None
            valid &= velocity is not None
            if velocity is not None:
                v += wx*wy*np.asarray(velocity)
            corners.append(dict(x=float(x[i]), y=float(y[j]), weight=float(wx*wy), flags=flags, velocity=velocity))
    return dict(point=point, stage=stage, height=height, valid=bool(valid),
                K=float(np.linalg.norm(v)/5) if valid else None, corners=corners)


def summarize(doc, refs):
    frozen = doc["metadata"]["frozen_critical_indices"]
    solved = {r["task"]["id"]: r for r in doc["runs"] if r["task"]["kind"] != "probe"}
    probes = {r["task"]["id"]: r for r in doc["runs"] if r["task"]["kind"] == "probe"}
    comparisons = []

    def add(a, b, label, family, direction):
        accepted = assess(a)["accepted"] and assess(b)["accepted"]
        for height in HEIGHTS:
            for region in ("all", "away4m"):
                row = dict(comparison=label, family=family, direction=direction, height=height,
                           region=region, matched_accuracy=accepted)
                if accepted:
                    ids = frozen[f"{family}/{direction}/{height}/{region}"]
                    row.update(comparison(a, b, height, ids, region))
                else:
                    row["withheld_reason"] = "Failed common residual/stability gate"
                comparisons.append(row)

    initial = []
    for family in FAMILIES:
        for direction in DIRECTIONS:
            add(refs[family, direction, 2], refs[family, direction, 1], "2_to_1", family, direction)
            fine = solved.get(f"fine/{family}/{direction}/0.5")
            if fine is not None:
                add(refs[family, direction, 1], fine, "1_to_0.5", family, direction)
            pairs = [(probes.get(f"probe/{family}/{direction}/2"), probes.get(f"probe/{family}/{direction}/1"), "2_to_1")]
            pairs.append((probes.get(f"probe/{family}/{direction}/1"), fine, "1_to_0.5"))
            for a, b, label in pairs:
                if a is None or b is None:
                    continue
                for height in HEIGHTS:
                    for stage in ("profile", "initial"):
                        aa = a | {"checkpoints": [{"planes": a[stage+"_planes"]}]}
                        bb = b | {"checkpoints": [{"planes": b[stage+"_planes"]}]}
                        # These are initialization diagnostics, never solve passes.
                        av = array(values(aa, height)); bv = array(values(bb, height))
                        mask = np.isfinite(av).all(axis=1) & np.isfinite(bv).all(axis=1)
                        delta = np.abs(np.linalg.norm(av[mask], axis=1)-np.linalg.norm(bv[mask], axis=1))/5
                        initial.append(dict(family=family, direction=direction, height=height, stage=stage,
                            comparison=label, p95_abs_delta_K=float(np.percentile(delta, 95)),
                            max_abs_delta_K=float(delta.max()), certified_solution=False))
    for direction in DIRECTIONS:
        lateral = solved.get(f"lateral/uniform-0.5/{direction}/1")
        if lateral is not None:
            add(refs["uniform-0.5", direction, 1], lateral, "lateral_80_to_160", "uniform-0.5", direction)
    for disabled in (16, 31):
        a, b = (solved.get(f"ablation/{disabled}/{r}") for r in (2, 1))
        if a is not None and b is not None:
            add(a, b, f"ablation_{disabled}_2_to_1", "uniform-0.5", 270)
    audits = []
    for r in doc["runs"]:
        for height in HEIGHTS:
            for point in ((27, 21), (51, 35)):
                for stage in ("profile", "initial", *(() if r["task"]["kind"] == "probe" else ("final",))):
                    audits.append(dict(task=r["task"]["id"], **audit_point(r, height, list(point), stage)))
    checks = [dict(task=r["task"]["id"], **assess(r)) for r in solved.values()]
    complete = {r["task"]["id"] for r in doc["runs"]} == {t["id"] for t in tasks()} and len(doc["runs"]) == len(tasks())
    refinement = [c for c in comparisons if c["comparison"] == "1_to_0.5" and c["region"] == "all"]
    return dict(metadata=doc["metadata"], complete=complete, runs=checks,
        initial_only_probes=len(probes), accepted_final_runs=sum(c["accepted"] for c in checks),
        comparisons=comparisons, initialization=initial, point_audits=audits,
        horizontal_scope_pass=complete and len(refinement) == 8 and all(c.get("within_budget", False) for c in refinement),
        decision="Assess full and fixed-region findings before C2c; no automatic preset selected")


def write(doc, output, refs):
    output.mkdir(parents=True, exist_ok=True)
    for name, value in (("raw.json.gz", gzip.compress(json.dumps(doc, allow_nan=False).encode(), mtime=0)),
                        ("summary.json", (json.dumps(summarize(doc, refs), indent=2, allow_nan=False)+"\n").encode())):
        temp = output/(name+".tmp")
        temp.write_bytes(value); temp.replace(output/name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=Path("build/extension/vertical_grid_study"))
    parser.add_argument("--reference", type=Path, default=Path("docs/data/auto-grid-controls/serial/raw.json.gz"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--max-n", type=int, default=4000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    refs, configs = references(args.reference)
    if args.summarize:
        doc = json.loads(gzip.decompress((args.output/"raw.json.gz").read_bytes()))
        if digest(args.reference) != doc["metadata"]["reference_sha256"]:
            parser.error("Reference archive changed")
        write(doc, args.output, refs)
        return
    if not 1 <= args.n <= args.max_n <= 25000:
        parser.error("Require 1 <= n <= max-n <= 25000")
    executable = args.executable.resolve()
    metadata = dict(utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
        python=platform.python_version(), numpy=np.__version__, executable=str(executable),
        executable_sha256=digest(executable), reference=str(args.reference), reference_sha256=digest(args.reference),
        source_sha256={str(p): digest(p) for p in (Path(__file__), Path("tools/run_auto_grid_controls.py"),
            Path("tools/run_vertical_grid_study.py"), Path("tools/vertical_grid_study.cpp"),
            Path("src/qes_core/dtcc/divergence.cpp"), Path("src/qes_core/dtcc/model_inputs.cpp"),
            *[p for p in sorted(Path("src/qes_core").rglob("*")) if p.suffix in (".cpp", ".h", ".txt")])},
        initial_n=args.n, max_n=args.max_n, qes_revision=Path("src/dtcc_qes/_qes_revision.txt").read_text().strip(),
        frozen_critical_indices=frozen_locations(refs), heights=list(HEIGHTS), comparison_points=POINTS.tolist(),
        away_region_distance_m=4, error_targets=dict(p95_abs_delta_K=.05, peak_relative=.05,
            frozen_critical_relative=.05, frozen_critical_low_speed_abs_delta_K=.05),
        disabled_bitmask=dict(rooftop=1, upwind=2, canyon=4, wake=8, sidewall=16),
        reference_backend=next(iter(refs.values()))["backend"],
        scope="tower, winds 270/315, fixed z from C2a; one diagnostic repetition; no timing claims")
    doc = dict(metadata=metadata, configurations=configs, runs=[], attempts=[])
    if args.resume:
        doc = json.loads(gzip.decompress((args.output/"raw.json.gz").read_bytes()))
        for key, value in metadata.items():
            if key != "utc" and doc["metadata"].get(key) != value:
                parser.error(f"Cannot resume changed configuration/source: {key}")
    elif (args.output/"raw.json.gz").exists():
        parser.error("Output exists; choose a new directory or --resume")
    for task in tasks():
        if any(r["task"]["id"] == task["id"] for r in doc["runs"]):
            continue
        n = 0 if task["kind"] == "probe" else args.n
        while True:
            print(task["id"], "N=", n, flush=True)
            proc = subprocess.run([str(executable), "tower", "--horizontal", str(task["direction"]), str(n)],
                env=os.environ | {"DTCC_QES_STUDY_ORDER": "legacy"}, input=input_text(configs[task["family"]], task), text=True, capture_output=True, check=True, timeout=1800)
            if proc.stderr:
                raise RuntimeError(proc.stderr)
            run = json.loads(proc.stdout)
            run["task"] = task
            if run["backend"] != metadata["reference_backend"]:
                raise ValueError("Worker/reference backend mismatch")
            np.testing.assert_array_equal(np.array(run["z_faces"], dtype=np.float32), configs[task["family"]]["expected_faces"])
            accepted = n > 0 and assess(run)["accepted"]
            if n == 0 or accepted or n >= args.max_n:
                doc["runs"].append(run)
                break
            doc["attempts"].append(run)
            write(doc, args.output, refs)
            n = min(2*n, args.max_n)
        write(doc, args.output, refs)
        print("INITIAL ONLY" if n == 0 else "PASS solve gate" if accepted else "FAIL; comparison withheld", flush=True)
    print("C2b matrix complete; inspect full and fixed-region assessments", flush=True)


if __name__ == "__main__":
    main()

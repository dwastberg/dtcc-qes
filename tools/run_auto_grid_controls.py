"""C2 early boundary/horizontal controls using actual Python-generated layers.

No preset is selected here. Run native workers sequentially; archive every
checkpoint and failed budget, including native planes before collocation.
"""
from __future__ import annotations

import os
import argparse
import copy
import gzip
import hashlib
import itertools
import json
import math
import platform
import random
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from run_vertical_grid_study import evaluate, timing

HEIGHTS = (1.5, 1.75)
POINTS = np.arange(3., 79., 2.)
CONTROL_TARGETS = {"p95_abs_delta_K": .05, "peak_relative_difference": .05}
GEOMETRIES = ("isolated", "passage", "array", "tower")


def rectangles(name):
    if name == "isolated":
        return [[32, 32, 12, 16, 12.3]]
    if name == "passage":
        return [[24, 24, 12, 32, 12.3], [44, 24, 12, 32, 12.3]]
    if name in ("array", "tower"):
        return [[x, y, 12, 12, 23.7 if name == "tower" and x == y == 42 else 7.9]
                for y in (22, 42) for x in (22, 42)]
    raise ValueError("Unknown geometry")


def make_city(rects):
    from dtcc_core.model import Building, City, GeometryType, Surface
    city = City()
    for i, (x, y, w, length, height) in enumerate(rects):
        b = Building(id=str(i))
        b.measured_height = height
        b.add_geometry(Surface(vertices=np.array([
            [x, y, 0.], [x, y+length, 0.], [x+w, y+length, 0.], [x+w, y, 0.],
        ])), GeometryType.LOD0)
        city.add_building(b)
    return city


def extend_layers(layers, top):
    """Preserve every lower solver operand; append a constant upper tail.

    A study control, not a second automatic generator. The new tail is at least
    as thick as the old last layer and obeys its 1.15 growth bound.
    """
    layers = np.asarray(layers, dtype=float)
    remaining = top-float(layers.sum())
    count = math.floor(remaining/layers[-1])
    if count < 1 or remaining/count > layers[-1]*1.15:
        raise ValueError("Cannot extend control without changing lower faces")
    return np.r_[layers, np.full(count, remaining/count)]


def plans(name, families):
    from dtcc_qes import wind
    from dtcc_qes.vertical_grid import effective_faces
    city = make_city(rectangles(name))
    result = []
    for family in families:
        start = time.perf_counter()
        if family == "auto":
            spec = wind.VerticalGrid.auto(pedestrian_height=min(HEIGHTS))
            preview = wind.preview_grid(city, resolution=2, bounds=(0, 0, 0, 80, 80, 64),
                                        vertical_grid=spec)
            record = preview.domain["vertical_grid"]
            layers = np.diff(record["planned_faces"])
            # Subtraction must preserve the actual native solver operands.
            np.testing.assert_array_equal(layers.astype(np.float32), preview.solver_dz.astype(np.float32))
        elif family == "uniform-0.5":
            layers = np.full(128, .5)
            preview = wind.preview_grid(city, resolution=2, bounds=(0, 0, 0, 80, 80, 64),
                                        vertical_grid=wind.VerticalGrid.from_faces(np.r_[0., np.cumsum(layers)]))
            record = preview.domain["vertical_grid"]
        else:
            raise ValueError("Unknown grid family")
        seconds = time.perf_counter()-start
        for control in ("base", "tall", "xy1"):
            actual = extend_layers(layers, 144) if control == "tall" else layers.copy()
            faces = effective_faces(actual)
            np.testing.assert_array_equal(faces[:len(preview.z_faces)], preview.z_faces)
            result.append(dict(family=family, control=control, resolution=1 if control == "xy1" else 2,
                requested_top=144 if control == "tall" else 64, layers_input=actual.tolist(),
                expected_faces=faces.tolist(), python_preview_seconds=seconds,
                planning_scope="policy timed again per worker; public preview measured separately once per family/geometry",
                provenance=copy.deepcopy(record),
                control_policy="append constant tail, preserve lower faces" if control == "tall" else
                               "preserve all vertical solver operands"))
    return result


def worker_input(plan, rects):
    values = [plan["resolution"], len(plan["layers_input"]), len(HEIGHTS), len(rects),
              *plan["layers_input"], *HEIGHTS, *itertools.chain.from_iterable(rects)]
    return " ".join(format(v, ".17g") for v in values)+"\n"


def collocate(velocity, x, y, points=POINTS):
    """Bilinear component sampling; every positive-weight corner must be fluid.

    Exact native centres use just that centre. No extrapolation or flag
    interpolation. Output order is y-major, x-minor, as in the original study.
    """
    x, y, points = (np.asarray(a, dtype=float) for a in (x, y, points))
    if any(a.ndim != 1 or len(a) < 1 or not np.isfinite(a).all()
           or np.any(np.diff(a) <= 0) for a in (x, y, points)):
        raise ValueError("Invalid sampling axes")
    v = np.array([a if a is not None else [np.nan]*3 for a in velocity], dtype=float)
    v = v.reshape(len(y), len(x), 3)

    def brackets(axis):
        if points[0] < axis[0] or points[-1] > axis[-1]:
            raise ValueError("Horizontal sampling would extrapolate")
        hi = np.searchsorted(axis, points)
        exact = axis[hi] == points
        lo = np.where(exact, hi, hi-1)
        weight = np.zeros(len(points))
        np.divide(points-axis[lo], axis[hi]-axis[lo], out=weight, where=~exact)
        return ((lo, 1-weight), (hi, weight))

    result = np.zeros((len(points), len(points), 3))
    valid = np.ones(result.shape[:2], dtype=bool)
    for j, wy in brackets(y):
        for i, wx in brackets(x):
            weight = wy[:, None]*wx[None, :]
            values = v[j[:, None], i[None, :]]
            contributes = weight > 0
            valid &= ~contributes | np.isfinite(values).all(axis=-1)
            result += weight[..., None]*np.where(contributes[..., None], values, 0)
    return [value.tolist() if ok else None for value, ok in zip(result.reshape(-1, 3), valid.ravel())]


def height_run(run, height):
    checkpoints = []
    for c in run["checkpoints"]:
        p, = [p for p in c["planes"] if p["height"] == height]
        checkpoints.append(c | {"velocity": collocate(p["velocity"], run["sample_x"], run["sample_y"])})
    return run | {"checkpoints": checkpoints}


def assess(run):
    checkpoints = run["checkpoints"]
    if (len(checkpoints) != 3 or checkpoints[0]["iterations"] < 1
            or [c["iterations"] for c in checkpoints] != [checkpoints[0]["iterations"]*m for m in (1, 2, 4)]):
        raise ValueError("Require exactly three increasing fixed-sweep checkpoints N,2N,4N")
    for c in checkpoints:
        if sorted(p["height"] for p in c["planes"]) != list(HEIGHTS):
            raise ValueError("Missing or duplicate sampling heights")
        for key in ("max_divergence", "rms_divergence"):
            if not math.isfinite(c[key]) or c[key] < 0:
                raise ValueError("Invalid residual diagnostic")
    heights = {str(h): evaluate(height_run(run, h)) for h in HEIGHTS}
    return {"accepted": all(h["accepted"] for h in heights.values()), "heights": heights}


def compare(a, b, mask):
    """a is the candidate/base; b is the finer/taller comparison."""
    av = np.array([v if v is not None else [np.nan]*3 for v in a["checkpoints"][-1]["velocity"]])[mask]
    bv = np.array([v if v is not None else [np.nan]*3 for v in b["checkpoints"][-1]["velocity"]])[mask]
    if not len(av):
        raise ValueError("No common-fluid samples")
    ak, bk = np.linalg.norm(av, axis=1)/5, np.linalg.norm(bv, axis=1)/5
    delta = np.abs(ak-bk)
    indices = np.flatnonzero(mask)

    def location(local):
        j, i = divmod(int(indices[local]), len(POINTS))
        return [float(POINTS[i]), float(POINTS[j])]

    # Fixed critical locations: the ten fastest base points, frozen before
    # inspecting the control. Also retain both peaks and high-speed area.
    critical = np.argsort(-ak, kind="stable")[:10]
    critical_deltas = delta[critical]
    appreciable = bk >= .1
    return dict(p95_abs_delta_K=float(np.percentile(delta, 95)), max_abs_delta_K=float(delta.max()),
        vector_max_delta_over_Uref=float(np.linalg.norm(av-bv, axis=1).max()/5),
        peak_K=[float(ak.max()), float(bk.max())],
        peak_relative_difference=float(abs(ak.max()-bk.max())/bk.max()) if bk.max() >= .1 else None,
        peak_locations=[location(int(ak.argmax())), location(int(bk.argmax()))],
        max_error_location=location(int(delta.argmax())),
        critical_locations=[location(int(i)) for i in critical],
        critical_max_abs_delta_K=float(critical_deltas.max()),
        critical_max_relative_difference=float((critical_deltas/bk[critical]).max())
            if np.all(bk[critical] >= .1) else None,
        high_speed_points_K_ge_1=[int((ak >= 1).sum()), int((bk >= 1).sum())],
        high_speed_region_changes=int(np.count_nonzero((ak >= 1) != (bk >= 1))),
        low_speed_points_in_reference=int((~appreciable).sum()),
        low_speed_max_abs_delta_K=float(delta[~appreciable].max()) if (~appreciable).any() else None)


def summarize(document):
    groups = []
    runs = document["runs"]
    for key in sorted({(r["geometry"], r["direction"], r["family"], r["control"]) for r in runs}):
        group = [r for r in runs if (r["geometry"], r["direction"], r["family"], r["control"]) == key]
        r = group[0]
        checks = [assess(g) for g in group]
        groups.append(dict(geometry=key[0], direction=key[1], family=key[2], control=key[3],
            accepted=all(c["accepted"] for c in checks), repeats=len(group),
            repeat_ids=[g["repeat"] for g in group],
            layers=r["layers"], cells=r["cells"], resolution=r["resolution"], roof_errors=r["roof_errors"],
            backend=r["backend"], threads=r["threads"],
            peak_rss_bytes=timing(group, "peak_rss_bytes"),
            planning_seconds=timing(group, "planning_seconds"), prep_seconds=timing(group, "prep_seconds"),
            final_solve_seconds=timing(group, "solve_seconds"),
            sampling_seconds=timing(group, "sampling_seconds"),
            certification_sweeps=sum(c["iterations"] for c in r["checkpoints"]),
            certification_checkpoint=r["checkpoints"][-1]["iterations"], assessments=checks,
            top_band_max_divergence=r["checkpoints"][-1]["top_band_max_divergence"]))
    comparisons = []
    for base in [g for g in groups if g["control"] == "base"]:
        for control in ("tall", "xy1"):
            other = next((g for g in groups if (g["geometry"], g["direction"], g["family"], g["control"])
                          == (base["geometry"], base["direction"], base["family"], control)), None)
            if other is None:
                continue
            def representative(g):
                return next(r for r in runs if (r["geometry"], r["direction"], r["family"], r["control"])
                            == (g["geometry"], g["direction"], g["family"], g["control"]))
            for height in HEIGHTS:
                a, b = height_run(representative(base), height), height_run(representative(other), height)
                am = np.array([v is not None for v in a["checkpoints"][-1]["velocity"]])
                bm = np.array([v is not None for v in b["checkpoints"][-1]["velocity"]])
                item = dict(geometry=base["geometry"], direction=base["direction"], family=base["family"],
                    control=control, height=height, matched_accuracy=base["accepted"] and other["accepted"],
                    common_fluid_points=int((am & bm).sum()), solid_fluid_transitions=int((am != bm).sum()))
                if item["matched_accuracy"]:
                    item.update(compare(a, b, am & bm))
                    peak = item["peak_relative_difference"]
                    critical = item["critical_max_relative_difference"]
                    item["within_control_budget"] = bool(item["p95_abs_delta_K"] < .05
                        and (peak is None or peak < .05)
                        and (critical is None or critical < .05))
                else:
                    item["withheld_reason"] = "At least one solve failed residual/stability certification"
                comparisons.append(item)
    complete = all(sorted(g["repeat_ids"]) == list(range(document["metadata"]["repeats"])) for g in groups)
    expected = len(document["metadata"]["geometries"])*len(document["metadata"]["directions"])*len(document["metadata"]["families"])*3
    complete = complete and len(groups) == expected
    passed = complete and bool(comparisons) and all(c.get("within_control_budget", False) for c in comparisons)
    return dict(metadata=document["metadata"], control_targets=CONTROL_TARGETS,
        complete=complete, groups=groups, comparisons=comparisons,
        accepted_runs=sum(assess(r)["accepted"] for r in runs), total_runs=len(runs),
        early_controls_within_budget=passed,
        decision="Early controls permit further C2 work; no preset selected" if passed else
                 "Do not select a preset; resolve or narrow boundary/horizontal scope first")


def write(document, output):
    output.mkdir(parents=True, exist_ok=True)
    for name, content in (("raw.json.gz", gzip.compress(json.dumps(document, allow_nan=False).encode(), mtime=0)),
                          ("summary.json", (json.dumps(summarize(document), indent=2, allow_nan=False)+"\n").encode())):
        temp = output/(name+".tmp")
        temp.write_bytes(content)
        temp.replace(output/name)


def timed_policy(plan, rects):
    """Measure the real generator independently of city/native preparation."""
    if plan["family"] != "auto":
        return 0., 0.
    from dtcc_qes import wind
    from dtcc_qes._auto_grid import generate_auto_layers
    settings = wind.VerticalGrid.auto(**plan["provenance"]["requested_settings"])._automatic
    start = time.perf_counter()
    layers, _ = generate_auto_layers(settings, resolution=2., top=64., heights=[r[-1] for r in rects])
    policy_seconds = time.perf_counter()-start
    start = time.perf_counter()
    if plan["control"] == "tall":
        layers = extend_layers(layers, 144.)
    extension_seconds = time.perf_counter()-start
    np.testing.assert_array_equal(layers.astype(np.float32), np.asarray(plan["layers_input"], dtype=np.float32))
    return policy_seconds, extension_seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=Path("build/extension/vertical_grid_study"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n", type=int, default=1000)
    parser.add_argument("--max-n", type=int, default=8000)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--geometries", nargs="+", choices=GEOMETRIES, default=["passage", "tower"])
    parser.add_argument("--families", nargs="+", choices=["auto", "uniform-0.5"], default=["auto", "uniform-0.5"])
    parser.add_argument("--directions", nargs="+", type=float, default=[270, 315])
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.summarize:
        write(json.loads(gzip.decompress((args.output/"raw.json.gz").read_bytes())), args.output)
        return
    if not 1 <= args.n <= args.max_n <= 25000 or args.repeats < 1:
        parser.error("Require 1 <= n <= max-n <= 25000 and repeats >= 1")
    if any(not math.isfinite(d) or not 0 <= d < 360 for d in args.directions):
        parser.error("Directions must be finite in [0,360)")
    executable = args.executable.resolve()
    metadata = dict(utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
        machine=platform.machine(), python=platform.python_version(), numpy=np.__version__,
        executable=str(executable), executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path("tools/vertical_grid_study.cpp"), Path("src/dtcc_qes/_auto_grid.py"),
            Path("src/dtcc_qes/_city.py"), Path("src/dtcc_qes/vertical_grid.py"))},
        qes_revision=Path("src/dtcc_qes/_qes_revision.txt").read_text().strip(),
        initial_n=args.n, max_n=args.max_n, repeats=args.repeats, geometries=args.geometries,
        families=args.families, directions=args.directions, sampling_heights=list(HEIGHTS),
        comparison_points=POINTS.tolist(), bounds=[0, 0, 0, 80, 80, 64], tall_top=144,
        Uref=5, reference_height=10, roughness_length=.1,
        control_targets=CONTROL_TARGETS, critical_rule="ten fastest base common-fluid points; relative change <5% where K>=0.1",
        horizontal_sampling="bilinear components; all positive-weight corners finite/fluid; no extrapolation",
        observable="magnitude of mean velocity", random_seed=20261026,
        timing_scope="isolated sequential workers; fixed sweeps; not optimized time-to-accuracy or release performance",
        model_flags=dict(rooftop=1, upwind_cavity=2, street_canyon=1, street_intersection=0, wake=2, high_rise=0, sidewall=1))
    document = dict(metadata=metadata, runs=[], attempts=[], configurations={})
    if args.resume:
        document = json.loads(gzip.decompress((args.output/"raw.json.gz").read_bytes()))
        for key, value in metadata.items():
            if key != "utc" and document["metadata"].get(key) != value:
                parser.error(f"Cannot resume: metadata changed: {key}")
    elif (args.output/"raw.json.gz").exists():
        parser.error("Output already exists; use --resume or choose a fresh directory")
    for name in args.geometries:
        if name not in document["configurations"]:
            document["configurations"][name] = plans(name, args.families)
    tasks = [(name, plan, direction, repeat) for name in args.geometries
             for plan in document["configurations"][name] for direction in args.directions
             for repeat in range(args.repeats)]
    random.Random(metadata["random_seed"]).shuffle(tasks)
    budgets = {(r["geometry"], r["family"], r["control"], r["direction"]): r["checkpoints"][0]["iterations"]
               for r in document["runs"]}
    for index, (name, plan, direction, repeat) in enumerate(tasks):
        key = (name, plan["family"], plan["control"], direction)
        if any((r["geometry"], r["family"], r["control"], r["direction"], r["repeat"]) == (*key, repeat)
               for r in document["runs"]):
            continue
        n = budgets.get(key, args.n)
        while True:
            print(f"{index+1}/{len(tasks)} {key} repeat={repeat} N={n}", flush=True)
            policy_seconds, extension_seconds = timed_policy(plan, rectangles(name))
            proc = subprocess.run([str(executable), name, "--layers", str(direction), str(n)],
                                  env=os.environ | {"DTCC_QES_STUDY_ORDER": "legacy"}, input=worker_input(plan, rectangles(name)), capture_output=True,
                                  text=True, check=True, timeout=1200)
            if proc.stderr:
                raise RuntimeError(proc.stderr)
            run = json.loads(proc.stdout)
            np.testing.assert_array_equal(np.asarray(run["z_faces"], dtype=np.float32),
                                          np.asarray(plan["expected_faces"], dtype=np.float32))
            run.update(family=plan["family"], control=plan["control"], repeat=repeat,
                       planning_seconds=policy_seconds, extension_seconds=extension_seconds,
                       python_preview_seconds=plan["python_preview_seconds"])
            passed = assess(run)["accepted"]
            if passed or n >= args.max_n or key in budgets:
                budgets[key] = n
                document["runs"].append(run)
                break
            document["attempts"].append(run)
            write(document, args.output)
            n = min(2*n, args.max_n)
        write(document, args.output)
        print("PASS solve gate" if passed else "FAIL solve gate; comparisons withheld", flush=True)
    print(summarize(document)["decision"], flush=True)


if __name__ == "__main__":
    main()

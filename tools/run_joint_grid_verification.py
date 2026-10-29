"""Joint 160/240 m extent and 1/0.5 m spacing verification, never preset tuning.

Each native checkpoint independently starts from zero. Checkpoints are saved
atomically and reused only with identical inputs, sources, executable and budget.
Historical precision/lateral archives and their frozen critical sets are retained.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess

import numpy as np

from run_auto_grid_controls import HEIGHTS, POINTS
from run_horizontal_sensitivity import (FAMILIES, DIRECTIONS, array, audit_point,
    comparison, digest, frozen_locations, references, values)
from run_precision_verification import gate, input_text, tasks as previous_tasks

EXTRA_POINTS = [[27, 21], [21, 23], [51, 35]]
BASELINE = Path("docs/data/joint-grid-verification/baseline-sources")
BACKENDS = {"serial": "serial_lexicographic", "openmp": "openmp_red_black"}


def tasks():
    return [dict(id=f"joint/{e}/{f}/{w}/0.5", family=f, direction=w,
                 resolution=.5, extent=e, precision="float64")
            for e in (160, 240) for f in FAMILIES for w in DIRECTIONS]


def atomic_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = (json.dumps(document, allow_nan=False, sort_keys=True)+"\n").encode()
    if path.suffix == ".gz":
        contents = gzip.compress(contents, mtime=0)
    temporary = path.with_name(path.name+".tmp")
    temporary.write_bytes(contents)
    temporary.replace(path)


def read(path):
    path = Path(path)
    data = path.read_bytes()
    return json.loads(gzip.decompress(data) if path.suffix == ".gz" else data)


def fingerprint(document):
    return hashlib.sha256(json.dumps(document, sort_keys=True, allow_nan=False).encode()).hexdigest()


def require_reference_matrix(doc, phase, backend):
    expected = {t["id"]: t for t in previous_tasks(phase)}
    runs = doc["runs"]
    if (doc["metadata"]["phase"] != phase or len(runs) != len(expected)
            or {r["task"]["id"] for r in runs} != set(expected)):
        raise ValueError("Missing or duplicate reference cases")
    for run in runs:
        task = run["task"]
        if (task != expected[task["id"]] or run["backend"] != backend
                or run["start"] != "zero" or run["precision"] != task["precision"]
                or run.get("disabled_mask") != 0 or not gate(run)["accepted"]):
            raise ValueError("Reference task, backend, precision, model or solve mismatch")
        if (phase == "precision" and task["precision"] == "float64"
                and task["direction"] == 270 and not gate(run)["ten_times_tighter_accepted"]):
            raise ValueError("Every predeclared tighter reference must pass all checkpoints")


def load_references(backend):
    paths = {name: Path("docs/data")/folder/backend/"raw.json.gz" for name, folder in (
        ("precision", "precision-remedy"), ("verification", "lateral-horizontal-verification"))}
    docs = {name: read(path) for name, path in paths.items()}
    for name, doc in docs.items():
        require_reference_matrix(doc, name, BACKENDS[backend])
        metadata = doc["metadata"]
        for source, sha in metadata["source_sha256"].items():
            path = BASELINE/source if source == "tools/vertical_grid_study.cpp" else Path(source)
            if digest(path) != sha:
                raise ValueError(f"Changed reference source: {source}")
        legacy_binary = Path("build/joint-grid-verification/bin")/f"legacy-{backend}"
        if digest(legacy_binary) != metadata["executable_sha256"]:
            raise ValueError("Historical binary fingerprint mismatch")
        if digest(metadata["reference"]) != metadata["reference_sha256"]:
            raise ValueError("Historical C2a reference fingerprint mismatch")
    precision, lateral = docs["precision"], docs["verification"]
    if lateral["metadata"]["precision_reference_sha256"] != digest(paths["precision"]):
        raise ValueError("Lateral/precision reference provenance mismatch")
    refs, configs = references(Path(precision["metadata"]["reference"]))
    frozen = frozen_locations(refs)
    for doc in docs.values():
        if (doc["metadata"]["frozen_critical_indices"] != frozen
                or doc["metadata"]["points"] != POINTS.tolist()
                or doc["metadata"]["heights"] != list(HEIGHTS)
                or doc["metadata"]["world_sensor"] != [5, 5]
                or doc["metadata"]["Uref"] != 5
                or doc["metadata"]["qes_revision"] != Path("src/dtcc_qes/_qes_revision.txt").read_text().strip()):
            raise ValueError("Reference physical scope mismatch")
    return docs, configs, frozen, {str(p): digest(p) for p in paths.values()}


def resource_estimate(task, configs):
    nx = int(task["extent"]/task["resolution"])
    nz = len(configs[task["family"]]["layers_input"])
    # Domain uses nx+1 horizontal faces, nz+2 vertical faces, one lower
    # ghost-cell layer. WINDSGeneralData allocates 15 floats, four ints and a
    # double per native centre; PrecisionSolver adds two doubles. Also include
    # six float face arrays and the main terrain/roughness horizontal arrays.
    centres = nx*nx*(nz+1)
    faces = (nx+1)**2*(nz+2)
    arrays = 100*centres+24*faces+24*nx*nx
    return dict(physical_cells=nx*nx*nz, native_cell_centres=centres,
                native_faces=faces, solver_workspace_bytes=16*centres,
                estimated_array_bytes=arrays,
                estimated_process_bytes=int(arrays*1.25+64*1024**2),
                estimate_scope="array-based estimate plus 25% and 64 MiB overhead; not a peak-RSS guarantee")


def validate_checkpoint(run, task, configs, backend, sweeps):
    if (run["backend"] != backend or run["start"] != "zero"
            or run["precision"] != "float64" or run.get("disabled_mask") != 0
            or run["direction"] != task["direction"] or run["resolution"] != task["resolution"]
            or len(run["checkpoints"]) != 1 or run["checkpoints"][0]["iterations"] != sweeps):
        raise ValueError("Checkpoint execution scope mismatch")
    np.testing.assert_array_equal(np.asarray(run["z_faces"], np.float32),
                                  configs[task["family"]]["expected_faces"])
    origin = (80-task["extent"])/2
    if run["horizontal_bounds"] != [origin, origin, origin+task["extent"], origin+task["extent"]]:
        raise ValueError("Checkpoint world bounds mismatch")
    resource = resource_estimate(task, configs)
    if (run["cells"] != resource["physical_cells"]
            or run["solver_workspace_bytes"] != resource["solver_workspace_bytes"]):
        raise ValueError("Checkpoint allocation mismatch")
    # Reusing the one checkpoint three times is only a schema/residual check;
    # acceptance is always evaluated later on three DISTINCT sweep budgets.
    c = run["checkpoints"][0]
    gate(run | {"checkpoints": [c | {"iterations": sweeps*m} for m in (1, 2, 4)]})
    for stage in ("profile", "initial", "final"):
        for height in HEIGHTS:
            for point in EXTRA_POINTS:
                audit_point(run, height, point, stage)


def checkpoint_path(output, task, sweeps):
    return output/"checkpoints"/task["id"]/f"{sweeps:06d}.json.gz"


def obtain_checkpoint(task, configs, executable, backend, sweeps, ceiling, output, identity):
    path = checkpoint_path(output, task, sweeps)
    request = dict(study_identity=identity, task=task, sweeps=sweeps,
                   input_sha256=hashlib.sha256(input_text(task, configs).encode()).hexdigest())
    if path.exists():
        saved = read(path)
        if saved["request"] != request or saved["run_sha256"] != fingerprint(saved["run"]):
            raise ValueError(f"Cached checkpoint identity/content mismatch: {path}")
        run = saved["run"]
    else:
        print(task["id"], "zero-start sweeps", sweeps, flush=True)
        command = [str(executable), "tower", "--horizontal", str(task["direction"]), str(sweeps),
                   "--float64", "--checkpoint", "--max-cells", str(ceiling)]
        proc = subprocess.run(command, input=input_text(task, configs), text=True,
                              capture_output=True, check=True, timeout=86400)
        if proc.stderr:
            raise ValueError(proc.stderr)
        run = json.loads(proc.stdout)
        validate_checkpoint(run, task, configs, backend, sweeps)
        atomic_json(path, dict(request=request, run=run, run_sha256=fingerprint(run)))
    validate_checkpoint(run, task, configs, backend, sweeps)
    return run, dict(path=str(path), sha256=digest(path))


def assemble(task, documents, origins):
    return documents[-1] | dict(task=task,
        checkpoints=[d["checkpoints"][0] for d in documents], checkpoint_origins=origins,
        peak_rss_bytes=max(d["peak_rss_bytes"] for d in documents),
        checkpoint_preparation_seconds=[d["prep_seconds"] for d in documents])


def execute(task, configs, executable, backend, initial_n, max_n, ceiling, output, identity):
    n, attempts = initial_n, []
    while True:
        documents, origins = [], []
        for sweeps in (n, 2*n, 4*n):
            doc, origin = obtain_checkpoint(task, configs, executable, backend, sweeps,
                                            ceiling, output, identity)
            documents.append(doc)
            origins.append(origin)
        run = assemble(task, documents, origins)
        check = gate(run)
        record = dict(run=run, attempts=attempts, accepted=check["accepted"], study_identity=identity)
        if check["accepted"] or n >= max_n:
            atomic_json(output/"cases"/(task["id"]+".json.gz"), record)
            print(task["id"], "PASS" if check["accepted"] else "FAIL", "N", n, flush=True)
            return record
        attempts.append(run)
        atomic_json(output/"cases"/(task["id"]+".json.gz"),
                    record | dict(attempts=attempts, run=None, accepted=False))
        n = min(2*n, max_n)


def local_checks(a, b, height):
    rows = []
    for point in EXTRA_POINTS:
        pa, pb = [audit_point(run, height, point, "final") for run in (a, b)]
        valid = pa["valid"] and pb["valid"]
        delta = abs(pa["K"]-pb["K"]) if valid else None
        relative = delta/pb["K"] if valid and pb["K"] >= .1 else None
        rows.append(dict(point=point, valid=valid, K=[pa["K"], pb["K"]],
                         abs_delta_K=delta, relative_difference=relative,
                         within_budget=bool(valid and (relative < .05 if relative is not None else delta < .05))))
    return rows


def summarize(doc, reference_docs):
    runs = doc["runs"]
    expected = {t["id"] for t in tasks()}
    actual = {r["task"]["id"] for r in runs}
    if len(actual) != len(runs) or not actual <= expected:
        raise ValueError("Unexpected or duplicate joint cases")
    result = dict(metadata=doc["metadata"], complete=actual == expected,
                  runs=[dict(task=r["task"], **gate(r), cells=r["cells"],
                      peak_rss_bytes=r["peak_rss_bytes"], solver_workspace_bytes=r["solver_workspace_bytes"],
                      certification_solve_seconds=sum(c["solve_seconds"] for c in r["checkpoints"]),
                      final_solve_seconds=r["checkpoints"][-1]["solve_seconds"],
                      final_sweeps=r["checkpoints"][-1]["iterations"],
                      top_band_max_divergence=r["checkpoints"][-1]["top_band_max_divergence"])
                      for r in runs], comparisons=[], initialization=[], point_audits=[])
    available = {r["task"]["id"]: r for r in reference_docs["verification"]["runs"]+runs}
    frozen = doc["metadata"]["frozen_critical_indices"]
    for family in FAMILIES:
        for wind in DIRECTIONS:
            pairs = [(f"lateral/{e}/{family}/{wind}/1", f"joint/{e}/{family}/{wind}/0.5", f"xy_1_to_0.5_at_{e}")
                     for e in (160, 240)]
            pairs += [(f"joint/160/{family}/{wind}/0.5", f"joint/240/{family}/{wind}/0.5", "extent_160_to_240_at_0.5"),
                      (f"lateral/160/{family}/{wind}/1", f"lateral/240/{family}/{wind}/1", "extent_160_to_240_at_1")]
            for aid, bid, label in pairs:
                if aid not in available or bid not in available:
                    continue
                a, b = available[aid], available[bid]
                accepted = gate(a)["accepted"] and gate(b)["accepted"]
                for height in HEIGHTS:
                    for region in ("all", "away4m"):
                        row = dict(comparison=label, family=family, direction=wind,
                                   height=height, region=region, matched_accuracy=accepted)
                        if accepted:
                            row.update(comparison(a, b, height, frozen[f"{family}/{wind}/{height}/{region}"], region))
                            row["additional_fixed_checks"] = local_checks(a, b, height)
                            row["local_checks_within_budget"] = all(c["within_budget"] for c in row["additional_fixed_checks"])
                            row["combined_within_budget"] = bool(row["within_budget"]
                                and row["solid_fluid_transitions"] == 0 and row["local_checks_within_budget"])
                        else:
                            row["withheld_reason"] = "Failed common residual/stability gate"
                        result["comparisons"].append(row)
                    for stage in ("profile", "initial"):
                        av, bv = [array(values(r, height, stage)) for r in (a, b)]
                        am, bm = np.isfinite(av).all(axis=1), np.isfinite(bv).all(axis=1)
                        mask = am & bm
                        result["initialization"].append(dict(comparison=label, family=family, direction=wind,
                            height=height, stage=stage, solid_fluid_transitions=int((am != bm).sum()),
                            max_component_difference=float(np.max(np.abs(av[mask]-bv[mask]))),
                            max_abs_delta_K=float(np.max(np.abs(np.linalg.norm(av[mask], axis=1)-np.linalg.norm(bv[mask], axis=1))/5))))
    result["point_audits"] = [dict(task=key, **audit_point(run, height, point, stage))
        for key, run in available.items() for height in HEIGHTS for point in EXTRA_POINTS
        for stage in ("profile", "initial", "final")]
    full = [r for r in result["comparisons"] if r["region"] == "all"]
    result["joint_scope_established"] = bool(result["complete"] and len(full) == 32
        and all(r.get("combined_within_budget", False) for r in full))
    result["scope_note"] = ("Joint numerical budgets pass on these fixtures only; no empirical validation or preset selected."
        if result["joint_scope_established"] else
        "Joint full-region scope not established; retain failed comparisons and local checks. C2c remains gated.")
    return result


def collect(output, metadata):
    runs, attempts = [], []
    for task in tasks():
        path = output/"cases"/(task["id"]+".json.gz")
        if not path.exists():
            continue
        record = read(path)
        if record["study_identity"] != fingerprint(metadata):
            raise ValueError("Case identity mismatch")
        if record["run"] is not None:
            runs.append(record["run"])
        attempts.extend(record["attempts"])
    return dict(metadata=metadata, runs=runs, attempts=attempts)


def write_summary(output, metadata, references):
    doc = collect(output, metadata)
    atomic_json(output/"raw.json.gz", doc)
    atomic_json(output/"summary.json", summarize(doc, references))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=BACKENDS, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n", type=int, default=2000)
    parser.add_argument("--max-n", type=int, default=16000)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--cell-target", type=int, default=20000000)
    parser.add_argument("--allocation-ceiling", type=int, default=40000000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--summarize", action="store_true")
    parser.add_argument("--only", nargs="*", help="Task IDs for a pilot; complete matrix is always frozen")
    args = parser.parse_args()
    if not 1 <= args.n <= args.max_n <= 25000 or not 1 <= args.workers <= 4:
        parser.error("Require 1 <= n <= max-n <= 25000 and 1..4 workers")
    if args.cell_target < 1 or args.allocation_ceiling < 1:
        parser.error("Resource counts must be positive")
    refs, configs, frozen, archive_hashes = load_references(args.backend)
    estimates = {t["id"]: resource_estimate(t, configs) for t in tasks()}
    if max(e["physical_cells"] for e in estimates.values()) > args.allocation_ceiling:
        parser.error("Configured allocation ceiling is below a declared case; raise it for the available hardware")
    chosen = tasks() if args.only is None else [t for t in tasks() if t["id"] in args.only]
    if args.only is not None and {t["id"] for t in chosen} != set(args.only):
        parser.error("Unknown pilot task ID")
    executable = args.executable.resolve()
    sources = [Path(__file__), Path("tools/vertical_grid_study.cpp"), Path("tools/vertical_grid_diagnostics.cpp"),
        Path("tools/vertical_grid_diagnostics.h"), Path("tools/run_precision_verification.py"),
        Path("tools/run_horizontal_sensitivity.py"), Path("tools/run_auto_grid_controls.py"),
        Path("tools/run_vertical_grid_study.py"), Path("CMakeLists.txt")]
    sources += sorted(Path("src/cpp").glob("*.cpp"))+sorted(Path("src/qes_core/dtcc").rglob("*.cpp"))+sorted(Path("src/qes_core/dtcc").rglob("*.h"))
    metadata = dict(phase="joint", backend=BACKENDS[args.backend], executable=str(executable),
        executable_sha256=digest(executable), source_sha256={str(p): digest(p) for p in sources},
        references_sha256=archive_hashes, baseline_worker_sha256=digest(BASELINE/"tools/vertical_grid_study.cpp"),
        qes_revision=Path("src/dtcc_qes/_qes_revision.txt").read_text().strip(),
        platform=platform.platform(), python=platform.python_version(), numpy=np.__version__,
        hardware_memory_bytes=os.sysconf("SC_PHYS_PAGES")*os.sysconf("SC_PAGE_SIZE"),
        workers=args.workers, initial_n=args.n, max_n=args.max_n, task_matrix=tasks(),
        cell_target=args.cell_target, allocation_ceiling=args.allocation_ceiling, resources=estimates,
        estimated_concurrent_process_bytes=args.workers*max(e["estimated_process_bytes"] for e in estimates.values()),
        resource_policy="soft target; allocation ceiling configurable; 29.49M case retained",
        frozen_critical_indices=frozen, additional_fixed_points=EXTRA_POINTS,
        points=POINTS.tolist(), heights=list(HEIGHTS), Uref=5, world_sensor=[5, 5],
        targets=dict(p95_abs_delta_K=.05, peak_relative=.05, critical_relative=.05,
                     low_speed_abs_delta_K=.05, low_speed_threshold_K=.1,
                     max_scaled_residual=1e-3, rms_scaled_residual=1e-4,
                     max_vector_change_over_Uref=1e-3, p95_vector_change_over_Uref=5e-4),
        sampling="bilinear centred components then linear vertical components; identical world points and grid phase",
        cost_scope="one diagnostic repetition; concurrent workers; certification and actual unique-checkpoint work separate")
    manifest = args.output/"manifest.json"
    if args.resume or args.summarize:
        if read(manifest)["metadata"] != metadata:
            parser.error("Changed source, binary, input, reference or resource configuration")
    elif manifest.exists():
        parser.error("Output exists; use --resume or a new directory")
    else:
        atomic_json(manifest, dict(utc=datetime.now(timezone.utc).isoformat(), metadata=metadata,
                                  configurations=configs))
    write_summary(args.output, metadata, refs)
    if args.summarize:
        return
    existing = {r["task"]["id"] for r in collect(args.output, metadata)["runs"]}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(execute, t, configs, executable, BACKENDS[args.backend],
            args.n, args.max_n, args.allocation_ceiling, args.output, fingerprint(metadata))
            for t in chosen if t["id"] not in existing]
        for future in as_completed(futures):
            future.result()
            write_summary(args.output, metadata, refs)
    print("Selected tasks complete; inspect summary for matrix completeness and scope", flush=True)


if __name__ == "__main__":
    main()

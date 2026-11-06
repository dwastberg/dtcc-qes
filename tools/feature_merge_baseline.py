"""Freeze feature intersections before changing the public Python API.

Run captures in separate processes with OMP_NUM_THREADS fixed. Archives belong
under build/feature-merge-baseline, never in the frozen historical evidence.
The old/new adapters execute the same declared work. Timing observations are
validated and retained separately from the deterministic comparison.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tarfile
import time
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def deterministic(value, timings, path=""):
    """Remove only documented timers; validate each removed observation."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            name = path + "/" + key
            if key == "elapsed_seconds" or (key.endswith("_seconds") and
                    ("/timings/" in name or path.endswith("/timings"))):
                if item is not None and (isinstance(item, bool) or not isinstance(item, (float, int)) or not math.isfinite(item) or item < 0):
                    raise ValueError(f"Invalid timing at {name}: {item}")
                timings[name] = item
            else:
                result[key] = deterministic(item, timings, name)
        return result
    if isinstance(value, (tuple, list)):
        return [deterministic(v, timings, path + f"/{i}") for i, v in enumerate(value)]
    return value


def cases():
    # Deliberately finite pairwise/high-risk set rather than a Cartesian product.
    rows = [dict(id="scalar", profile="scalar", grid="uniform", mode="legacy", precision="float32", turbulence=None)]
    for kind in ("log", "uniform", "power", "turning", "jet", "calm"):
        rows.append(dict(rows[0], id=kind, profile=kind))
        rows.append(dict(rows[0], id=kind+"-bounded-height", profile=kind,
                         mode="bounded", turbulence="height"))
        rows.append(dict(rows[0], id=kind+"-explicit-double-wall", profile=kind,
                         grid="explicit", precision="float64", turbulence="wall_distance"))
    rows += [dict(rows[0], id="auto", grid="auto"),
             dict(rows[0], id="empty", geometry="empty"),
             dict(rows[0], id="empty-turbulence", geometry="empty", turbulence="height", precision="float64"),
             dict(rows[0], id="canonical-footprints", geometry="contacts", mode="bounded", turbulence="height"),
             dict(rows[0], id="turbulence-extended", grid="auto", turbulence="height"),
             dict(rows[0], id="adaptive", mode="adaptive"),
             dict(rows[0], id="adaptive-profile", mode="adaptive", profile="uniform"),
             dict(rows[0], id="adaptive-turbulence", mode="adaptive", turbulence="height"),
             dict(rows[0], id="adaptive-double", mode="adaptive", precision="float64")]
    return rows


def profile(wind, kind):
    if kind == "scalar":
        return None
    if kind in ("log", "calm"):
        return wind.LogProfile(0 if kind == "calm" else 5, 270)
    if kind == "uniform":
        return wind.UniformProfile(5, 270)
    if kind == "power":
        return wind.PowerLawProfile(5, 270, reference_height=10, exponent=.2)
    heights = [1, 5, 10, 30, 100]
    if kind == "turning":
        return wind.MeasuredProfile(heights, [2, 4, 5, 6, 7],
                                    directions=[350, 10, 30, 40, 50], reference_height=10, below="log")
    return wind.MeasuredProfile(heights, [2, 6, 5, 3, 2], direction=270, reference_height=10, below="log")


def execute(wind, city, row, api):
    p = profile(wind, row["profile"])
    adaptive = row["mode"] == "adaptive"
    options = dict(resolution=2., bounds=(0, 0, 0, 160, 160, 64) if adaptive else (0, 0, 0, 80, 80, 64))
    if row["grid"] == "explicit":
        options["vertical_grid"] = wind.VerticalGrid.from_faces([0, 1, 2, 3, 5, 8, 12, 18, 26, 40, 48, 56, 64, 72])
        options["bounds"] = (0, 0, 0, 80, 80, 72)
    elif row["grid"] == "auto":
        options.pop("bounds")
        options["vertical_grid"] = wind.VerticalGrid.auto()
    monitor = wind.MonitorSpec((0, 80, 0, 80), history_limit=8,
        receptors=tuple(wind.Receptor(f"h{h}", 27, 21, h) for h in (1.5, 1.75)))
    turbulence = None if row["turbulence"] is None else wind.Turbulence(row["turbulence"])
    if row.get("geometry") == "contacts":
        options["footprints"] = wind.Footprints(min_detail=.01)
    # A generous budget makes bounded captures iteration-capped, never timed work.
    if api == "old":
        options.update(max_iterations=600 if adaptive else 30, solver_precision=row["precision"])
        if row["mode"] != "legacy":
            options["solver_control"] = wind.SolverControl(60., monitor, mode=row["mode"])
        if turbulence is not None:
            options["turbulence"] = turbulence
    else:
        settings = dict(tolerance=1e-5,max_iterations=600 if adaptive else 30, precision=row["precision"])
        if row["mode"] != "legacy":
            settings.update(max_solve_seconds=60., monitor=monitor)
        if adaptive:
            settings["policy"] = "pedestrian-v1"
        options["solver"] = wind.Solver(**settings)
        if turbulence is not None:
            options["turbulence"] = turbulence
    if p is None:
        result = wind.run(city, speed=5, direction=270, **options)
    else:
        result = wind.run(city, profile=p, **options)
    record = result.control if api == "old" else result.solver["record"]
    if record is not None and record["termination_reason"] == "time_limit":
        raise ValueError(f"Budget interrupted fixed work for {row['id']}")
    return result


def capture(api, output, select):
    from dtcc_qes import wind, _qes
    from compare_native_builds import make_city
    if os.environ.get("OMP_NUM_THREADS") not in ("1", "2", "4"):
        raise ValueError("Fix OMP_NUM_THREADS to 1, 2 or 4 before capturing")
    output.mkdir(parents=True, exist_ok=False)
    sources = [p for folder in ("src", "tools") for p in (ROOT/folder).rglob("*")
               if p.is_file() and p.suffix in (".py", ".cpp", ".h", ".txt") and "__pycache__" not in p.parts]
    with tarfile.open(output/"sources.tar.gz", "w:gz") as archive:
        for p in sorted(sources):
            archive.add(p, arcname=p.relative_to(ROOT), recursive=False)
    manifest = dict(schema_version=1, api=api,
        source_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        source_index={str(p.relative_to(ROOT)): digest(p) for p in sorted(sources)},
        lock_sha256=digest(ROOT/"uv.lock"), extension=str(Path(_qes.__file__).resolve()),
        extension_sha256=digest(_qes.__file__), policy_revision=_qes.solver_policy_revision,
        backend=_qes.cpu_backend, omp_num_threads=os.environ["OMP_NUM_THREADS"],
        compiler=[_qes.compiler_id, _qes.compiler_version, _qes.build_type, _qes.fp_contract],
        cases={}, timings={})
    towers = make_city([(22,22,12,12,7.9), (42,22,12,12,7.9),
                        (22,42,12,12,7.9), (42,42,12,12,23.7)])
    small = make_city([(30,30,10,10,15)])
    contacts = make_city([(20,20,12,12,8), (32,20,12,12,16)])
    for row in cases():
        if select != "all" and (row["mode"] == "adaptive") != (select == "adaptive"):
            continue
        print(row["id"], flush=True)
        city = towers if row["mode"] == "adaptive" else small
        if row.get("geometry") == "empty":
            city = make_city([])
        elif row.get("geometry") == "contacts":
            city = contacts
        result = execute(wind, city, row, api)
        arrays = {n:getattr(result,n) for n in ("velocity", "cell_flags", "x", "y", "z", "z_faces", "solid_mask")}
        if result.turbulence is not None:
            arrays.update({"turbulence/"+n:getattr(result.turbulence,n) for n in
                           ("stress", "tke", "co_eps", "mixing_length", "computed", "capped", "stress_valid")})
        sample = result.sample(1.5, method="linear")
        arrays.update({"sample/"+n:getattr(sample,n) for n in ("velocity", "valid", "x", "y")})
        np.savez_compressed(output/(row["id"]+".npz"), **arrays)
        timings = {}
        manifest["cases"][row["id"]] = dict(request=row, diagnostics=asdict(result.diagnostics),
            metadata=deterministic(result.metadata, timings))
        manifest["timings"][row["id"]] = timings
        write(output/"manifest.json", manifest)
    # Dataset build() bypasses external fetch/cache while exercising the real pipeline.
    from dtcc_qes.datasets import QESWindArgs, QESWindDataset
    from dtcc_core import datasets
    for kind in (() if select == "adaptive" else ("field", "linear", "auto")):
        args = dict(bounds=[0,0,60,60], horizontal_padding=6., vertical_clearance=6.)
        if api == "new":
            args["solver"] = wind.Solver(tolerance=1e-4,max_iterations=1000).to_dict()
        if kind != "field":
            args.update(product="slice", slice_sampling="linear", slice_height=1.5, slice_resolution=12)
        if kind == "auto":
            args["vertical_grid"] = "auto"
        request = QESWindArgs(**args)
        with patch.object(datasets, "city", return_value=small):
            obj = QESWindDataset().build(request)
        arrays = {f.name:np.array(f.values, copy=True) for f in obj.fields}
        arrays["coordinates"] = np.asarray(obj.coordinates() if kind == "field" else obj.points)
        name = "dataset-"+kind
        np.savez_compressed(output/(name+".npz"), **arrays)
        step = obj.provenance.processing_steps[-1]
        timings = {}
        manifest["cases"][name] = deterministic(dict(request=request.model_dump(mode="json"),
            diagnostics=step["diagnostics"], metadata=step["simulation"]), timings)
        manifest["timings"][name] = timings
    write(output/"manifest.json", manifest)


def measure_costs(api, output):
    """Five public-call measurements after one warm-up, with frozen work."""
    from dtcc_qes import wind, _qes
    from compare_native_builds import make_city
    city = make_city([(30,30,10,10,15)])
    row = cases()[0]
    combined = dict(row, id="cost-combined", profile="turning", mode="bounded", turbulence="height")
    report = dict(repetitions=5, warmups=1, backend=_qes.cpu_backend,
        policy_revision=_qes.solver_policy_revision, omp_num_threads=os.environ["OMP_NUM_THREADS"],
        clock="time.perf_counter; durations include the entire named public operation",
        review_rule="Investigate median regression exceeding both 10 percent and 0.01 seconds; report all observations and range",
        default_study=dict(reference_precision="float64", initial_reference_tolerance=1e-7,
            stability_tolerance=1e-8, stability_p95_K=1e-5, stability_max_K=1e-4,
            candidate_p95_K=5e-4, candidate_max_K=1e-3,
            selection="Fastest median public call among candidates passing both error limits on both cities; require reference convergence and tightening stability"),
        measurements={})
    for name, settings in (("wind-only", row), ("combined", combined), ("export", combined)):
        result = execute(wind, city, settings, api)
        work = dict(request=settings, shape=list(result.cell_flags.shape),
                    iterations=result.diagnostics.iterations, diagnostics=asdict(result.diagnostics))
        times = []
        for i in range(6):
            start = time.perf_counter()
            if name == "export":
                obj = result.to_dtcc(include_speedup=True)
                work["outputs"] = [f.name for f in obj.fields]
                del obj
            else:
                measured = execute(wind, city, settings, api)
                if measured.diagnostics.iterations != work["iterations"]:
                    raise ValueError("Cost measurement changed completed work")
                del measured
            elapsed = time.perf_counter()-start
            if i:
                times.append(elapsed)
        report["measurements"][name] = dict(work=work, seconds=times,
            median_seconds=float(np.median(times)), minimum_seconds=min(times), maximum_seconds=max(times))
    write(output, report)


def phase3_metadata(row):
    """Upgrade only declared diagnostic additions from frozen physical facts.

    Existing candidate fields are kept, so corrupt diagnostics still fail the
    comparison. Historical Log K values are retained and compared verbatim.
    Unit tests independently check the new profile interpolation formulas.
    """
    metadata = row.get("metadata", {})
    domain, profile = metadata.get("domain", {}), metadata.get("profile")
    vertical = domain.get("vertical_grid", {})
    if not profile or "effective_faces" not in vertical:
        return
    from dtcc_qes.profiles import profile_from_dict, _pedestrian_sampling
    from dtcc_qes.wind import _timing_report
    faces = np.asarray(vertical["effective_faces"], dtype=np.float32)
    centres = (np.float32(.5)*(faces[:-1]+faces[1:])).astype(float)
    request = row.get("request", {})
    spacing = domain["resolution"]
    clearance = max(request.get("vertical_clearance", 20.), spacing)
    roofs = vertical.get("roof_representation", [])
    roof = max((r["requested_height"] for r in roofs), default=0.)
    bounds = domain["requested_bounds"]
    fixed = bounds is not None and bounds[-1] is not None
    top = bounds[-1]-bounds[2] if fixed else max(roof+clearance,profile["reference"]["height"],2*spacing)
    growth = domain.get("turbulence")
    regeneration = growth.get("regeneration") if growth else None
    added = growth["added_layers"] if growth else 0
    before = float(faces[-added-1])
    domain.setdefault("top_requirements",dict(height_datum="metres above flat ground",
        fixed_top=bool(fixed or vertical["mode"]=="explicit"),
        requested_top=vertical["requested_faces"][-1] if vertical["mode"]=="explicit" else top,
        effective_top=float(faces[-1]),
        roof_clearance=dict(minimum_top=roof+clearance,clearance=clearance,applied=not fixed),
        profile_reference=dict(minimum_top=profile["reference"]["height"],applied=not fixed),
        minimum_cells=dict(count=2,minimum_top=None if fixed and vertical["mode"]!="uniform" else 2*spacing,applied=True),
        auto_grid_endpoint_fit=None if vertical["mode"]!="auto" else dict(
            target_top=regeneration["generated_top"] if regeneration else top,
            effective_top_before_turbulence=before,
            endpoint_fit=vertical.get("base_endpoint_fit",vertical["endpoint_fit"]),regeneration=regeneration),
        turbulence_reference=None if growth is None else dict(reference_height=growth["reference_height"],
            required_layers_above=2,minimum_margin_face=growth["reference_height"],effective_margin_face=float(faces[-4])),
        turbulence_rotation_15m=None if growth is None else dict(minimum_top=15.)))
    if vertical["mode"]=="auto" and "inflow" not in vertical["pedestrian_sampling"]:
        diagnostic = vertical["pedestrian_sampling"]
        updated = _pedestrian_sampling(profile_from_dict(profile["requested"]),centres,diagnostic["height"],profile)
        # Non-log diagnostics previously described the wrong (logarithmic)
        # law. Only these named scalar facts are permitted to change.
        replacements = {"flat_profile_exact_K","flat_profile_interpolated_K","flat_profile_bias_K",
                        "reference_height","roughness_length"} if profile["kind"]!="log" else set()
        for key,value in updated.items():
            if key not in diagnostic or key in replacements:
                diagnostic[key]=value
    if "timings" not in metadata:
        metadata["timings"] = deterministic(_timing_report(metadata["solver"]["record"]),{},"/timings")


def comparison_cases(cases):
    """Apply declared profile/solver schema moves; preserve numerical evidence."""
    result = deepcopy(cases)
    # Legacy calls did not store an environment. Recover the sweep-order
    # declaration from a controlled sibling using the same frozen native build.
    orders = {row.get("metadata", {}).get("solver_control", {}).get("execution", {}).get("sweep_order")
              for row in result.values()}
    orders.discard(None)
    if len(orders) > 1:
        raise ValueError("Archive contains conflicting sweep-order declarations")
    for row in result.values():
        metadata = row.get("metadata", {})
        roughness = metadata.get("condition", {}).get("roughness_length", .1)
        records = [metadata.get("profile"), metadata.get("domain", {}).get("profile")]
        for record in records:
            if not isinstance(record, dict) or record.get("schema_version") != 1:
                continue
            if record.get("type") not in ("log", "uniform", "power_law", "measured"):
                continue
            record["schema_version"] = 2
            requested = record.get("requested", {})
            if requested.get("schema_version") == 1:
                requested["schema_version"] = 2
                requested.setdefault("roughness_length", roughness)
        for record in records:
            if not isinstance(record, dict):
                continue
            if "type" in record and "kind" not in record:
                record["kind"] = record.pop("type")
            if "turbulence_caveat" in record and "caveats" not in record:
                record["caveats"] = [record.pop("turbulence_caveat")]
            record.setdefault("caveats", [])
        turbulence = metadata.get("turbulence")
        if isinstance(turbulence, dict):
            if "profile_caveat" in turbulence and "caveats" not in turbulence:
                turbulence["caveats"] = [turbulence.pop("profile_caveat")]
            turbulence.setdefault("caveats", [])
        old_solver = metadata.get("solver")
        if isinstance(old_solver, dict) and "spec" not in old_solver:
            spec = dict(schema_version=1, tolerance=old_solver["tolerance"],
                max_iterations=old_solver["max_iterations"], precision=old_solver["precision"],
                max_solve_seconds=None, monitor=None, policy=None,
                checkpoint_interval=25, residual_interval=0,
                raise_on_failure=old_solver.get("raise_on_unaccepted", old_solver["raise_on_nonconvergence"]))
            unknown = set(old_solver) - {"tolerance", "max_iterations", "precision", "raise_on_nonconvergence", "raise_on_unaccepted"}
            if unknown:
                raise ValueError(f"Undeclared legacy solver fields: {unknown}")
            record = metadata.pop("solver_control", None)
            if record is not None:
                environment = record.pop("execution")
                spec.update(record["requested"])
                monitor = deepcopy(record["monitor"])
                for name in ("origin", "crs", "reference_speed"):
                    monitor.pop(name)
                # The frozen capture protocol requests windows 1/2 and no
                # global mass; pedestrian-v1 overrides these natively to 1/4
                # and True. Preserve that requested/effective distinction.
                if record["mode"] == "adaptive":
                    monitor.update(long_window=2, global_mass=False)
                spec["monitor"] = monitor
            else:
                if not orders:
                    raise ValueError("Legacy environment requires a controlled sibling")
                environment = dict(precision=spec["precision"], backend=metadata["model"]["backend"],
                    sweep_order=next(iter(orders)), native_build=deepcopy(metadata["versions"]["native_build"]),
                    source_revision=metadata["versions"]["qes"]["revision"], shape=metadata["domain"]["shape"])
            metadata["solver"] = dict(spec=spec, record=record, environment=environment)
            request = row.get("request", {})
            if "solver_control" in request:
                for key in ("tolerance", "max_iterations", "solver_precision", "raise_on_nonconvergence", "raise_on_unaccepted", "solver_control"):
                    request.pop(key)
                request["solver"] = deepcopy(spec)
        request = row.get("request", {})
        if "wind_speed" in request or "wind_direction" in request:
            request["speed"] = request.pop("wind_speed")
            request["direction"] = request.pop("wind_direction")
            height, roughness = request.pop("reference_height"), request.pop("roughness_length")
            if (height, roughness) != (10., .1):
                request["profile"] = dict(schema_version=2, kind="log", speed=request.pop("speed"),
                    direction=request.pop("direction"), reference_height=height,
                    roughness_length=roughness, metadata={})
        profile = metadata.get("profile")
        if isinstance(profile, dict) and "reference" in profile and "requested" in profile:
            reference, requested = profile["reference"], profile["requested"]
            expected = dict(speed=reference["speed"],
                direction=requested["direction"] if profile["kind"] == "log" else reference["direction"] or 0.,
                reference_height=reference["height"], roughness_length=requested["roughness_length"])
            effective = {key:float(np.float32(value)) for key,value in expected.items()}
            if profile["kind"] != "log":
                effective.update(speed=reference["speed"],direction=reference["direction"])
            for key,value in (("condition",expected),("effective_condition",effective)):
                if key in metadata:
                    if metadata[key] != value:
                        raise ValueError(f"Undeclared {key} change disagrees with the profile record")
                    metadata.pop(key)
            boundary_layer = metadata.get("model", {}).get("boundary_layer")
            if boundary_layer is not None:
                for record in records:
                    if isinstance(record,dict):
                        record.setdefault("boundary_layer",boundary_layer)
            if "domain" in metadata:
                metadata["domain"].setdefault("profile",deepcopy(profile))
        phase3_metadata(row)
        if "bounds" in request and "id" not in request:
            old_dataset_schema = "turbulence_numerics_version" not in request
            request.setdefault("turbulence",None)
            request.setdefault("turbulence_numerics_version",None)
            domain=metadata.get("domain",{})
            # Four-coordinate dataset requests now defer top planning. The
            # frozen field/face comparison still checks the resulting grid.
            if old_dataset_schema and len(request["bounds"]) == 4 and domain.get("requested_bounds",[None]*6)[-1] is not None:
                domain["requested_bounds"][-1]=None
                requirements=domain["top_requirements"]
                requirements["fixed_top"]=False
                requirements["roof_clearance"]["applied"]=True
                requirements["profile_reference"]["applied"]=True
                requirements["minimum_cells"]["minimum_top"]=2*domain["resolution"]
    return result


def native_consolidation_cases(case_rows,identity,*,baseline=False):
    """Explicit Phase 9 additions, with native decisions left untouched."""
    from dtcc_qes import wind,_qes
    from compare_native_builds import make_city
    if _qes.solver_policy_revision!=identity:
        raise ValueError("Comparison must import the declared candidate native build")
    result=deepcopy(case_rows)
    for row in result.values():
        metadata=row.get("metadata",{})
        solver=metadata.get("solver")
        if solver is None:
            continue
        record=solver["record"]
        for build in (metadata["versions"]["native_build"],solver["environment"]["native_build"]):
            if type(build["solver_policy_build_supported"]) is not bool:
                raise ValueError("Invalid build qualification provenance")
            if not baseline and build["solver_policy_build_supported"]!=_qes.solver_policy_build_supported:
                raise ValueError("Candidate qualification provenance disagrees with the imported native build")
            build["solver_policy_build_supported"]="declared qualification transition"
        if record is None and metadata["timings"]["native"] is None:
            if not baseline:
                raise ValueError("Candidate legacy native timings are missing")
            metadata["timings"]["native"]={}
        if record is not None and "exclusions" not in record:
            if not baseline:
                raise ValueError("Candidate native exclusions are missing")
            if solver["spec"]["policy"] is None:
                record["exclusions"]=[]
            else:
                request=row["request"]
                if not _qes.solver_policy_build_supported:
                    raise ValueError("Adaptive compatibility requires the isolated qualified candidate")
                if request.get("id") not in {r["id"] for r in cases() if r["mode"]=="adaptive"}:
                    raise ValueError("Undeclared adaptive baseline protocol")
                city=make_city([(22,22,12,12,7.9),(42,22,12,12,7.9),
                                (22,42,12,12,7.9),(42,42,12,12,23.7)])
                inflow=profile(wind,request["profile"]) or wind.LogProfile(5,270)
                spec=wind.Solver.from_dict(solver["spec"])
                preview=wind.preview_grid(city,inflow,bounds=(0,0,0,160,160,64),solver=spec,
                    turbulence=None if request["turbulence"] is None else wind.Turbulence(request["turbulence"]))
                record["exclusions"]=preview.eligibility["exclusions"]
    return result


def monitor_storage_cases(case_rows, delta):
    """Apply a declared sizeof(Monitor) change, preserving every other field.

    The caller must supply an independently measured layout delta and an exact
    native identity pair. This is storage accounting, never a numerical tolerance.
    """
    if type(delta) is not int:
        raise ValueError("Monitor storage delta must be an integer")
    result = deepcopy(case_rows)
    for row in result.values():
        record = (row.get("metadata", {}).get("solver") or {}).get("record")
        if record is None:
            continue
        value = record.get("monitor_bytes")
        if type(value) is not int or value <= 0 or value + delta <= 0:
            raise ValueError("Invalid monitor storage accounting")
        record["monitor_bytes"] = value + delta
    return result


def compare(baseline, candidate, identity_pair=None, *, select="all", native_consolidation=False,
            monitor_storage_delta=0):
    if monitor_storage_delta and (identity_pair is None or not native_consolidation):
        raise ValueError("Monitor storage migration requires native consolidation and an exact identity pair")
    a, b = [json.loads((p/"manifest.json").read_text()) for p in (baseline,candidate)]
    differences = []
    for key in ("lock_sha256", "backend", "omp_num_threads", "compiler"):
        if a[key] != b[key]:
            differences.append(key)
    if identity_pair is None:
        for key in ("policy_revision", "extension_sha256"):
            if a[key] != b[key]:
                differences.append(key)
    elif (a["policy_revision"], b["policy_revision"]) != tuple(identity_pair):
        differences.append("unexpected native identity pair")
    ca, cb = comparison_cases(a["cases"]), comparison_cases(b["cases"])
    if select!="all":
        def selected(row):
            adaptive=(row.get("metadata",{}).get("solver",{}).get("spec",{}).get("policy") is not None)
            return adaptive==(select=="adaptive")
        ca,cb=({k:v for k,v in mapping.items() if selected(v)} for mapping in (ca,cb))
    if native_consolidation:
        if identity_pair is None:
            raise ValueError("Native consolidation requires an explicit identity pair")
        for mapping,expected in ((ca,identity_pair[0]),(cb,identity_pair[1])):
            for row in mapping.values():
                record=row.get("metadata",{}).get("solver",{}).get("record")
                if record is not None and record["policy"]:
                    if record["policy_revision"]!=expected:
                        raise ValueError("Unexpected native record identity")
                    record["policy_revision"]="declared native identity"
        ca=native_consolidation_cases(ca,identity_pair[1],baseline=True)
        cb=native_consolidation_cases(cb,identity_pair[1])
    if monitor_storage_delta:
        ca = monitor_storage_cases(ca, monitor_storage_delta)
    if ca != cb:
        differences += ["metadata/"+k for k in sorted(ca.keys() | cb.keys())
                        if ca.get(k) != cb.get(k)]
    for name in sorted(ca.keys() & cb.keys()):
        with np.load(baseline/(name+".npz"), allow_pickle=False) as x, np.load(candidate/(name+".npz"), allow_pickle=False) as y:
            if set(x.files) != set(y.files):
                differences.append(name+"/array keys")
            for key in sorted(set(x.files) & set(y.files)):
                if x[key].dtype != y[key].dtype or x[key].shape != y[key].shape or x[key].tobytes() != y[key].tobytes():
                    differences.append(name+"/"+key)
    print(json.dumps(dict(passed=not differences, differences=differences), indent=2))
    return not differences


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", choices=("old", "new"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", nargs=2, type=Path)
    parser.add_argument("--identity-pair", nargs=2)
    parser.add_argument("--native-consolidation",action="store_true",help="Declared Phase 9 clocks, exclusions and qualification provenance additions")
    parser.add_argument("--monitor-storage-delta", type=int, default=0,
                        help="Independently measured change in sizeof(Monitor); requires native consolidation and identity pair")
    parser.add_argument("--costs", type=Path, help="write focused baseline costs and predeclared default-study limits")
    parser.add_argument("--select", choices=("all", "adaptive", "non-adaptive"), default="all")
    args = parser.parse_args()
    if args.compare:
        raise SystemExit(0 if compare(*args.compare,args.identity_pair,select=args.select,
            native_consolidation=args.native_consolidation,
            monitor_storage_delta=args.monitor_storage_delta) else 1)
    if args.costs:
        if args.api is None:
            parser.error("--costs requires --api")
        measure_costs(args.api, args.costs)
        raise SystemExit(0)
    if args.api is None or args.output is None:
        parser.error("capture requires --api and --output")
    capture(args.api, args.output, args.select)

"""Archive and profile S0, with timing hooks confined to an isolated build.

Workers run sequentially, each with a 30 s subprocess deadline, under a 180 s
matrix cap. Builds and parity checks are separately bounded. No reference solve
or automatic acceptance is performed. Run from the repository root.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import resource
import shutil
import subprocess
import sys
import tarfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "bbfd20005e0bd7d7e648438a1bc8d5a9a4358a71"
LEGACY = "3f18072"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, timeout=120, **kwargs)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Instrumentation anchor must occur once: {old[:90]!r}")
    return text.replace(old, new, 1)


def inventory(header, prefix, expression=""):
    # Only actual, flat numeric vectors; ignore comments and nested containers.
    header = re.sub(r"/\*.*?\*/|//[^\n]*", "", header, flags=re.S)
    names = []
    for declaration in re.findall(r"std::vector<(?:float|double|int)>\s+([^;]+);", header):
        if re.fullmatch(r"\s*\w+(?:\s*,\s*\w+)*\s*", declaration):
            names.extend(n.strip() for n in declaration.split(","))
    return "\n".join(f'  solver_profile::array("{prefix}.{n}", {expression}{n});' for n in names)


def instrument(tree):
    """Insert clocks and array accounting, preserving numerical statements verbatim."""
    def edit(path, replacements):
        p = tree / path
        s = p.read_text()
        for old, new in replacements:
            s = replace_once(s, old, new)
        p.write_text(s)

    edit("src/qes_core/dtcc/wind_runner.cpp", [
        ("  auto prepared = std::make_unique<Impl>", '  solver_profile::mark("model_inputs");\n  auto prepared = std::make_unique<Impl>'),
        ("  impl_.swap(prepared);", '  impl_.swap(prepared);\n  solver_profile::mark("idle");\n  solver_profile::resident("prepared");'),
        ("  state.inputs.set_condition(condition);", '  solver_profile::mark("initialization");\n  state.inputs.set_condition(condition);'),
        ("  PrecisionDiagnostics diagnostics;", '  solver_profile::mark("solver_allocation");\n  PrecisionDiagnostics diagnostics;'),
        ("  if (state.turbulence) state.turbulence->run();", '  solver_profile::mark("turbulence_run");\n  if (state.turbulence) state.turbulence->run();\n  solver_profile::mark("output_extraction");'),
        ("  result.divergence = divergence_stats(data);", '  solver_profile::mark("divergence");\n  result.divergence = divergence_stats(data);\n  solver_profile::mark("output_extraction");'),
        ("  return result;", '  solver_profile::resident("native_output");\n  solver_profile::mark("idle");\n  return result;'),
    ])
    wind_inventory = inventory((tree/"src/qes_core/winds/WINDSGeneralData.h").read_text(), "wind")
    edit("src/qes_core/winds/WINDSGeneralData.cpp", [
        ("  // /////////////////////////\n  // Allocate memory", '  solver_profile::mark("wind_allocation");\n  // /////////////////////////\n  // Allocate memory'),
        ("  z0 = 0.1;", '  solver_profile::mark("geometry");\n  z0 = 0.1;'),
        ("  wall->defineWalls(this);", '  solver_profile::mark("operator_setup");\n  wall->defineWalls(this);'),
        ("    icellflag_initial[id] = icellflag[id];\n  }", "    icellflag_initial[id] = icellflag[id];\n  }\n" + wind_inventory + '\n  solver_profile::mark("idle");'),
    ])
    turb_inventory = inventory((tree/"src/qes_core/winds/TURBGeneralData.h").read_text(), "turbulence")
    edit("src/qes_core/winds/TURBGeneralData.cpp", [
        ("  m_WGD = WGD;\n\n  const int method", '  solver_profile::mark("turbulence_setup");\n  m_WGD = WGD;\n\n  const int method'),
        ("\n}\n\n\n\nTURBGeneralData::TURBGeneralData(WINDSGeneralData *WGD)", "\n" + turb_inventory + '\n  solver_profile::mark("idle");\n}\n\n\n\nTURBGeneralData::TURBGeneralData(WINDSGeneralData *WGD)'),
    ])
    edit("src/qes_core/winds/Solver.cpp", [
        ("  R.resize(domain.numCellCentered(), 0.0);", '  R.resize(domain.numCellCentered(), 0.0);\n  solver_profile::array("solver.lambda", lambda);\n  solver_profile::array("solver.lambda_old", lambda_old);\n  solver_profile::array("solver.rhs", R);'),
    ])
    for name in ("Solver_CPU.cpp", "Solver_CPU_RB.cpp"):
        p = tree / "src/qes_core/winds" / name
        s = p.read_text()
        s = replace_once(s, "  validateSolve(WGD, itermax);", '  solver_profile::mark("validation");\n  validateSolve(WGD, itermax);\n  solver_profile::mark("rhs");')
        s = replace_once(s, "  int iter = 0;", '  solver_profile::mark("sweeps");\n  int iter = 0;')
        s = replace_once(s, "    iter += 1;", '    solver_profile::sweep_mark("idle");\n    iter += 1;')
        rb = name == "Solver_CPU_RB.cpp"
        # Pass clocks run on the existing master, without adding barriers.
        def clock(label):
            return ('\n#pragma omp master\n' if rb else '\n') + '    { solver_profile::sweep_mark("' + label + '"); }\n'
        if rb:
            s = replace_once(s, "    {\n#pragma omp for", "    {" + clock("lambda_copy") + "#pragma omp for")
            for marker, label in (("      // Red nodes pass", "red"), ("      // Black nodes pass", "black"),
                                  ("      // Mirror boundary condition", "ground_mirror"), ("      // Error calculation", "change")):
                s = replace_once(s, marker, clock(label) + marker)
            s = replace_once(s, "  const auto solid =", '  solver_profile::mark("face_copy");\n  const auto solid =')
            s = replace_once(s, "    // Update the velocity field using Euler equations", '\n#pragma omp master\n    { solver_profile::mark("face_correction"); }\n    // Update the velocity field using Euler equations')
            s = replace_once(s, "#pragma omp for\n    // Each face", '#pragma omp master\n    { solver_profile::mark("solid_mask"); }\n#pragma omp for\n    // Each face')
        else:
            s = replace_once(s, "    // Save previous iteration values", clock("lambda_copy") + "    // Save previous iteration values")
            s = replace_once(s, "    // main SOR formulation loop", clock("lexicographic") + "    // main SOR formulation loop")
            s = replace_once(s, "    // Mirror boundary condition", clock("ground_mirror") + "    // Mirror boundary condition")
            s = replace_once(s, "    max_error = 0.0;", clock("change") + "    max_error = 0.0;")
            s = replace_once(s, "  for (auto k = 0u; k < WGD->u.size();", '  solver_profile::mark("face_copy");\n  for (auto k = 0u; k < WGD->u.size();')
            marker = "  for (int k = 1; k < domain.nz() - 2; ++k) {"
            at = s.index(marker, s.index('solver_profile::mark("face_copy")'))
            s = s[:at] + '  solver_profile::mark("face_correction");\n' + s[at:]
            marker = "  for (int k = 1; k < domain.nz() - 1; ++k) {"
            at = s.index(marker, at)
            s = s[:at] + '  solver_profile::mark("solid_mask");\n' + s[at:]
        s = replace_once(s, "  auto finish =", '  solver_profile::mark("idle");\n  auto finish =')
        p.write_text(s)
    edit("src/qes_core/dtcc/precision_solver.cpp", [
        ("  rhs_.resize(domain.numCellCentered());", '  rhs_.resize(domain.numCellCentered());\n  solver_profile::array("solver.lambda", lambda_);\n  solver_profile::array("solver.rhs", rhs_);'),
        ("  if (!data || iterations < 1)", '  solver_profile::mark("validation");\n  if (!data || iterations < 1)'),
        ("  std::fill(lambda_.begin()", '  solver_profile::mark("rhs");\n  std::fill(lambda_.begin()'),
        ("  int iter = 0;", '  solver_profile::mark("sweeps");\n  int iter = 0;'),
        ("      for (int colour =", '#ifdef _OPENMP\n#pragma omp master\n#endif\n      { solver_profile::sweep_mark("update_and_change"); }\n      for (int colour ='),
        ("    ++iter;", '    solver_profile::sweep_mark("idle");\n    ++iter;'),
        ("  a.u = a.u0;", '  solver_profile::mark("face_copy");\n  a.u = a.u0;'),
        ("  for (int k = 1; k < d.nz()-2; ++k)\n    for (int j = 1;", '  solver_profile::mark("face_correction");\n  for (int k = 1; k < d.nz()-2; ++k)\n    for (int j = 1;'),
        ("  for (int k = 1; k < d.nz()-1; ++k)", '  solver_profile::mark("solid_mask");\n  for (int k = 1; k < d.nz()-1; ++k)'),
        ("  return {iter,", '  solver_profile::mark("idle");\n  return {iter,'),
    ])
    edit("src/cpp/bindings.cpp", [
        ("nb::dict python_result(const WindData &data)\n{", 'nb::dict python_result(const WindData &data)\n{\n  solver_profile::mark("numpy_transfer");'),
        ("  return result;\n}\n}", '  solver_profile::mark("idle");\n  solver_profile::resident("numpy_output");\n  return result;\n}\n}'),
        ("  m.def(\"_core_grid_shape\"", '''  m.def("_s0_reset", &solver_profile::reset);
  m.def("_s0_profile", [] {
    nb::dict result, seconds, passes, bytes, capacities, rss;
    for (const auto &v : solver_profile::seconds) seconds[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::passes) passes[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::bytes) bytes[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::capacity_bytes) capacities[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::rss) rss[v.first.c_str()] = v.second;
    result["seconds"] = seconds; result["sweep_pass_seconds"] = passes;
    result["array_bytes"] = bytes; result["array_capacity_bytes"] = capacities;
    result["peak_rss_bytes_at_phase"] = rss;
    result["actual_threads"] = solver_profile::actual_threads;
    return result;
  });
  m.def("_core_grid_shape"'''),
    ])
    with (tree/"CMakeLists.txt").open("a") as f:
        f.write('\ntarget_compile_options(qesbuild INTERFACE -include "${CMAKE_CURRENT_SOURCE_DIR}/tools/solver_profile_hooks.h")\n'
                'target_compile_options(_qes PRIVATE -include "${CMAKE_CURRENT_SOURCE_DIR}/tools/solver_profile_hooks.h")\n')


def source_files(root):
    return sorted([p for directory in ("src", "tools") for p in (root/directory).rglob("*")
                   if p.is_file() and p.suffix in (".h", ".cpp", ".py", ".txt") and "__pycache__" not in p.parts]
                  + [root/"CMakeLists.txt", root/"pyproject.toml"])


def archive_files(path, files, root):
    hashes = {}
    with tarfile.open(path, "w:gz") as out:
        for p in files:
            name = p.relative_to(root).as_posix()
            hashes[name] = digest(p.read_bytes())
            out.add(p, arcname=name, recursive=False)
    return dict(sha256=digest(path.read_bytes()), files=hashes)


def archive_legacy(output):
    archived = {}
    for directory in ("build/openmp-benchmark/20261028T194857Z", "build/accuracy-budget-float32"):
        for p in sorted((ROOT/directory).iterdir()):
            if not p.is_file():
                continue  # No binary or staged-package archives.
            data = p.read_bytes()
            dest = output/"legacy"/p.relative_to(ROOT)
            dest = dest.with_name(dest.name + ".gz")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(gzip.compress(data, mtime=0))
            archived[dest.relative_to(output).as_posix()] = dict(original=p.relative_to(ROOT).as_posix(),
                original_sha256=digest(data), sha256=digest(dest.read_bytes()))
    # The old API sources and reference identity are retained separately from S0.
    legacy = command(["git", "archive", LEGACY, "src", "CMakeLists.txt"]).stdout
    (output/"legacy"/"root-sources.tar.gz").write_bytes(gzip.compress(legacy, mtime=0))
    subrevision = command(["git", "rev-parse", f"{LEGACY}:QES-Public"]).stdout.decode().strip()
    qes = command(["git", "-C", "QES-Public", "archive", subrevision, "src"]).stdout
    (output/"legacy"/"qes-sources.tar.gz").write_bytes(gzip.compress(qes, mtime=0))
    # Check the recorded old-API hashes against the archived commit, rather than live files.
    old = json.loads((ROOT/"docs/data/finest-reference/runtime-review.json").read_text())
    matches = {}
    with tarfile.open(fileobj=io.BytesIO(legacy)) as tar:
        for name, sha in old["source_sha256"].items():
            if name.startswith("src/"):
                matches[name] = digest(tar.extractfile(name).read()) == sha
    if not all(matches.values()):
        raise ValueError(f"Legacy source identity mismatch: {matches}")
    for name in ("tools/benchmark_fast_wind.py", "tools/benchmark_openmp.py"):
        p = ROOT/name
        shutil.copyfile(p, output/"legacy"/p.name)
    protocol = json.loads((ROOT/"build/openmp-benchmark/20261028T194857Z/protocol.json").read_text())
    if digest((output/"legacy/benchmark_openmp.py").read_bytes()) != protocol["tool_sha256"]:
        raise ValueError("Historical benchmark tool changed")
    if digest((output/"legacy/benchmark_fast_wind.py").read_bytes()) != old["source_sha256"]["tools/benchmark_fast_wind.py"]:
        raise ValueError("Historical API tool changed")
    for name in ("docs/data/finest-reference/runtime-review.json", "docs/data/generated-grid-pilot/raw.json.gz"):
        archived[name] = dict(external_repository_evidence=True, sha256=digest((ROOT/name).read_bytes()))
    return dict(records=archived, root_revision=command(["git", "rev-parse", LEGACY]).stdout.decode().strip(),
                qes_revision=subrevision, verified_old_api_sources=matches,
                snapshots={p.name: digest(p.read_bytes()) for p in (output/"legacy").glob("*.tar.gz")})


def load_harness():
    spec = importlib.util.spec_from_file_location("s0_harness", ROOT/"tools/compare_native_builds.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(args):
    from dtcc_qes import _qes, wind
    from run_auto_grid_controls import make_city, rectangles
    if not Path(_qes.__file__).resolve().is_relative_to(args.package.resolve()):
        raise RuntimeError("Profile imported the wrong extension")
    import logging
    from dtcc_core.common import get_python_logger
    get_python_logger("dtcc-qes").handlers = [logging.NullHandler()]
    # Warm the runtime/team on a small unrelated case; exclude it from all counters.
    wind.run(make_city([]), 5, 270, bounds=(0, 0, 0, 20, 20, 20), resolution=2, max_iterations=2)
    if args.instrumented:
        _qes._s0_reset()
    timing = {}
    original_prepare = wind._prepare_city
    def prepare(*a, **kw):
        start = time.perf_counter()
        result = original_prepare(*a, **kw)
        timing["python_geometry_and_grid"] = time.perf_counter()-start
        return result
    wind._prepare_city = prepare
    native_runner = _qes.WindRunner
    class Runner:
        def __init__(self): self.native = native_runner()
        def prepare(self, *a, **kw):
            start = time.perf_counter()
            result = self.native.prepare(*a, **kw)
            timing["native_prepare_including_boundary"] = time.perf_counter()-start
            return result
        def solve(self, *a, **kw):
            start = time.perf_counter()
            result = self.native.solve(*a, **kw)
            timing["native_solve_including_output_transfer"] = time.perf_counter()-start
            return result
    _qes.WindRunner = Runner
    city = make_city(rectangles("tower"))
    start = time.perf_counter()
    result = wind.run(city, 5, 270, resolution=.5, bounds=(-40, -40, 0, 120, 120, 64),
        vertical_grid=wind.VerticalGrid.auto(), max_cells=40000000,
        solver_precision=args.precision, max_iterations=args.iterations, turbulence=args.turbulence)
    timing["api_seconds"] = time.perf_counter()-start
    from dataclasses import asdict
    arrays = {name: digest(getattr(result, name).tobytes()) for name in ("velocity", "cell_flags", "x", "y", "z", "z_faces")}
    if result.turbulence:
        arrays.update({"turbulence."+k: digest(v.tobytes()) for k,v in vars(result.turbulence).items() if isinstance(v,np.ndarray)})
    row = dict(status="completed", precision=args.precision, iterations=args.iterations, turbulence=args.turbulence,
        instrumented=args.instrumented, requested_threads=int(os.environ["OMP_NUM_THREADS"]),
        timing=timing, output_sha256=arrays, diagnostics=asdict(result.diagnostics),
        shape=list(result.velocity.shape[:3]), grid=result.metadata["domain"]["vertical_grid"],
        build=result.metadata["versions"]["native_build"], extension_sha256=digest(Path(_qes.__file__).read_bytes()),
        peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=="darwin" else 1024),
        numpy_output_bytes=sum(getattr(result,n).nbytes for n in ("velocity","cell_flags","x","y","z","z_faces")))
    if args.instrumented:
        row["profile"] = _qes._s0_profile()
        if row["profile"]["actual_threads"] != row["requested_threads"]:
            raise RuntimeError("Actual team differs from the requested team")
    write_json(args.output, row)


def audit(output):
    manifest = json.loads((output/"manifest.json").read_text())
    for name, sha in manifest["files"].items():
        if digest((output/name).read_bytes()) != sha:
            raise ValueError(f"Changed archived file: {name}")
    for name, snapshot in manifest["sources"].items():
        with tarfile.open(output/name) as tar:
            for member, sha in snapshot["files"].items():
                if digest(tar.extractfile(member).read()) != sha:
                    raise ValueError(f"Changed source: {name}/{member}")
    for name, record in manifest["legacy"]["records"].items():
        if record.get("external_repository_evidence"):
            if digest((ROOT/name).read_bytes()) != record["sha256"]:
                raise ValueError(f"Changed historical reference: {name}")
        elif digest(gzip.decompress((output/name).read_bytes())) != record["original_sha256"]:
            raise ValueError(f"Changed legacy record: {name}")
    if (output/"summary.json").exists():
        summary = json.loads((output/"summary.json").read_text())
        if not summary["completed"] or not summary["parity_passed"]:
            raise ValueError("Incomplete profile or failed instrumentation parity")
        protocol = json.loads((output/"protocol.json").read_text())
        if len(summary["runs"]) != len(protocol["matrix"]):
            raise ValueError("Profile matrix coverage changed")
        for row in summary["runs"]:
            if row["status"] != "completed" or (row.get("instrumented") and
                    row["profile"]["actual_threads"] != row["requested_threads"]):
                raise ValueError("Incomplete worker or unexpected OpenMP team")
    return dict(passed=True, files=len(manifest["files"]), source_snapshots=len(manifest["sources"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("docs/data/solver-control-s0"))
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--precision", choices=("float32","float64"))
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--turbulence", action="store_true")
    parser.add_argument("--instrumented", action="store_true")
    parser.add_argument("--machine", help="CPU identity from a separately permitted hardware query")
    parser.add_argument("--work-dir", type=Path, default=ROOT/"build/solver-control-s0")
    parser.add_argument("--plain-package", type=Path, help="optional already staged S0 plain package; otherwise build the frozen snapshot")
    parser.add_argument("--source-archive", type=Path, default=ROOT/"docs/data/solver-control-s0/sources.tar.gz",
                        help="frozen S0 sources; later solver layouts are not S0 profiling inputs")
    parser.add_argument("--parity-report", type=Path, default=ROOT/"build/solver-control-s0/parity.json")
    args = parser.parse_args()
    if args.worker: return worker(args)
    if args.audit:
        print(json.dumps(audit(args.output)))
        return
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    harness = load_harness()
    work = args.work_dir.resolve()
    tree = work/"profile-tree"
    tree.mkdir(parents=True, exist_ok=False)
    with tarfile.open(args.source_archive) as archive:
        archive.extractall(tree,filter="data")
    sources = {"sources.tar.gz": archive_files(output/"sources.tar.gz", source_files(tree), tree)}
    baseline_tree, _ = harness.export_tree(BASELINE, work)
    sources["baseline-sources.tar.gz"] = archive_files(output/"baseline-sources.tar.gz", source_files(baseline_tree), baseline_tree)
    parity = json.loads(args.parity_report.read_text())
    if not parity["passed"] or parity["baseline_revision"] != BASELINE:
        raise ValueError("Missing or failed S0 revision parity")
    (output/"parity.json.gz").write_bytes(gzip.compress(args.parity_report.read_bytes(), mtime=0))
    legacy = archive_legacy(output)
    if args.plain_package:
        plain = args.plain_package.resolve()
    else:
        plain_module = harness.build(tree,work/"plain-build","openmp")
        plain = work/"plain-package"
        harness.stage_package(tree,plain_module,plain)
    instrument(tree)
    sources["instrumented-sources.tar.gz"] = archive_files(output/"instrumented-sources.tar.gz", source_files(tree), tree)
    module = harness.build(tree, work/"profile-build", "openmp")
    harness.stage_package(tree, module, work/"profile-package")
    # Plain and instrumented packages both use the frozen S0 layout.
    matrix = [(kind, precision, 4, 500, False) for kind in ("plain","profile")
              for precision in ("float32","float64") for repeat in range(2)]
    matrix += [("profile", precision, threads, 200, False) for precision in ("float32","float64") for threads in (1,2,8)]
    matrix += [("profile", precision, 4, 100, True) for precision in ("float32","float64")]
    protocol = dict(utc=datetime.now(timezone.utc).isoformat(), baseline_revision=BASELINE,
        source_revision=command(["git","rev-parse","HEAD"]).stdout.decode().strip(),
        dirty_paths=command(["git","status","--short"]).stdout.decode().splitlines(),
        platform=platform.platform(), machine=args.machine or platform.processor(),
        cpu_count=os.cpu_count(), matrix=matrix, per_worker_seconds=30, total_matrix_seconds=180,
        exclusions="API excludes imports, runtime warmup, City creation and sampling. Matrix cap excludes builds. RSS is process high-water, not attributed live RSS.",
        instrumentation="Snapshot only; master-thread clocks use existing OpenMP barriers; pass times include barrier/scheduling costs. Output/diagnostic parity required against plain build.",
        bandwidth="Logical load/store estimate per updated cell: float32 76 B; float64 96 B. Effective GB/s is not a hardware DRAM counter or proof of a bandwidth bottleneck.",
        automatic_grid_scope="Experimental; no new accuracy, grid or comfort qualification.")
    write_json(output/"protocol.json", protocol)
    rows = []
    start = time.monotonic()
    for index, (kind, precision, threads, iterations, turbulence) in enumerate(matrix):
        remaining = 180-(time.monotonic()-start)
        name = f"runs/{index:02d}-{kind}-{precision}-{threads}t.json"
        if remaining <= 0:
            rows.append(dict(record=name, status="skipped_total_budget")); continue
        package = work/"profile-package" if kind=="profile" else plain
        cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", "--package", str(package),
               "--precision", precision, "--iterations", str(iterations), "--output", str(output/name)]
        if kind=="profile": cmd.append("--instrumented")
        if turbulence: cmd.append("--turbulence")
        try:
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=min(30,remaining),
                cwd=ROOT, env=os.environ|dict(PYTHONPATH=str(package),OMP_NUM_THREADS=str(threads),OMP_DYNAMIC="FALSE"))
            row = json.loads((output/name).read_text()) if run.returncode==0 else dict(status="failed", stderr=run.stderr[-6000:])
        except subprocess.TimeoutExpired:
            row = dict(status="timeout", limit_seconds=min(30,remaining))
        row["record"] = name
        write_json(output/name,row)
        rows.append(row)
        print(f"{index}: {kind}/{precision}/{threads}t turbulence={turbulence}: {row['status']}",flush=True)
    paired = []
    for precision in ("float32","float64"):
        selected = [r for r in rows if r.get("status")=="completed" and r["precision"]==precision and r["iterations"]==500 and not r["turbulence"]]
        identical = len(selected)==4 and all(r["output_sha256"]==selected[0]["output_sha256"] and r["diagnostics"]==selected[0]["diagnostics"] for r in selected)
        paired.append(dict(precision=precision, instrumented_parity=identical))
    write_json(output/"summary.json",dict(runs=rows, paired=paired, elapsed_seconds=time.monotonic()-start,
        completed=all(r["status"]=="completed" for r in rows), parity_passed=all(p["instrumented_parity"] for p in paired)))
    files = {p.relative_to(output).as_posix():digest(p.read_bytes()) for p in output.rglob("*") if p.is_file()}
    write_json(output/"manifest.json",dict(baseline_revision=BASELINE,sources=sources,legacy=legacy,files=files))
    print(json.dumps(audit(output)))
    if not all(r["status"]=="completed" for r in rows) or not all(p["instrumented_parity"] for p in paired):
        raise SystemExit("S0 profiling incomplete or instrumentation changed outputs; inspect the archived failures")


if __name__ == "__main__":
    main()

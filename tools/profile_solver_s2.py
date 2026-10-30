"""Bounded phase profiling of S1a/S2 snapshots; production has no timing hooks.

Each stage archives its complete sources, plain/instrumented output identities,
declared protocol and bounded outcomes. S0's replay and evidence stay separate.
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

import profile_solver_baseline as legacy

ROOT = Path(__file__).resolve().parents[1]


def source_files(root):
    files = [p for directory in ("src", "tools", "tests") for p in (root/directory).rglob("*")
             if p.is_file() and p.suffix in (".h", ".cpp", ".py", ".txt")
             and "__pycache__" not in p.parts]
    return sorted(files + [root/n for n in ("CMakeLists.txt", "pyproject.toml", "uv.lock", "README.md", "LICENSE", "NOTICE")])


def instrument(tree):
    if 'm.def("_s0_profile"' in (tree/"src/cpp/bindings.cpp").read_text():
        raise ValueError("Snapshot is already instrumented")
    def edit(name, changes):
        p = tree/name
        s = p.read_text()
        for old, new in changes:
            s = legacy.replace_once(s, old, new)
        p.write_text(s)

    inventory = legacy.inventory((tree/"src/qes_core/winds/WINDSGeneralData.h").read_text(), "wind", "prepared->data->")
    operator_bytes = ('prepared->poisson->storage_bytes()' if 'storage_bytes()' in
                      (tree/"src/qes_core/solver/solver.h").read_text() else '0')
    edit("src/qes_core/dtcc/wind_runner.cpp", [
        ("  auto prepared = std::make_unique<Impl>", '''#ifdef _OPENMP
#pragma omp parallel
  {
#pragma omp single
    solver_profile::actual_threads = omp_get_num_threads();
  }
#endif
  solver_profile::mark("prepare");
  auto prepared = std::make_unique<Impl>'''),
        ("  impl_.swap(prepared);", inventory + f'\n  solver_profile::bytes["operator.owned"] = {operator_bytes};\n'
         '  solver_profile::resident("prepared");\n  solver_profile::mark("idle");\n  impl_.swap(prepared);'),
        ("  state.inputs.set_condition(condition);", '  solver_profile::mark("initialization");\n  state.inputs.set_condition(condition);'),
        ("  solver::SolveDiagnostics diagnostics;", '  solver_profile::mark("workspace_allocation");\n  solver::SolveDiagnostics diagnostics;'),
        ("      workspace.begin(", '      solver_profile::bytes["solver.workspace"] = workspace.workspace_bytes();\n'
         '      solver_profile::mark("begin_validation_zero_rhs");\n      workspace.begin('),
        ("      workspace.advance(options.max_iterations);", '      solver_profile::mark("sweeps");\n'
         '      workspace.advance(options.max_iterations);\n  solver_profile::mark("finalization");'),
        ("      state.phase = Impl::Phase::Finalized;", '      solver_profile::mark("solver_other");\n      state.phase = Impl::Phase::Finalized;'),
        ("  if (state.turbulence) state.turbulence->run();", '  solver_profile::mark("turbulence");\n'
         '  if (state.turbulence) state.turbulence->run();\n  solver_profile::mark("output_extraction");'),
        ("  return result;", '  solver_profile::resident("native_output");\n  solver_profile::mark("idle");\n  return result;'),
    ])
    # Export the same isolated hook schema as S0 so its worker can be reused.
    hook = '''  m.def("_s0_reset", [] {
    solver_profile::reset();
#ifdef _OPENMP
#pragma omp parallel
    {
#pragma omp single
      solver_profile::actual_threads = omp_get_num_threads();
    }
#endif
  });
  m.def("_s0_profile", [] {
    nb::dict result, seconds, bytes, capacities, rss;
    for (const auto &v : solver_profile::seconds) seconds[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::bytes) bytes[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::capacity_bytes) capacities[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::rss) rss[v.first.c_str()] = v.second;
    result["seconds"] = seconds; result["array_bytes"] = bytes;
    result["array_capacity_bytes"] = capacities; result["peak_rss_bytes_at_phase"] = rss;
    result["actual_threads"] = solver_profile::actual_threads;
    return result;
  });
  m.def("_core_grid_shape"'''
    edit("src/cpp/bindings.cpp", [
        ("nb::dict python_result(const WindData &data)\n{", 'nb::dict python_result(const WindData &data)\n{\n  solver_profile::mark("numpy_transfer");'),
        ("  return result;\n}\n}", '  solver_profile::mark("idle");\n  solver_profile::resident("numpy_output");\n  return result;\n}\n}'),
        ('  m.def("_core_grid_shape"', hook),
    ])
    shutil.copyfile(ROOT/"tools/solver_profile_hooks.h", tree/"tools/solver_profile_hooks.h")
    with (tree/"CMakeLists.txt").open("a") as f:
        f.write('\ntarget_compile_options(qesbuild INTERFACE -include "${CMAKE_CURRENT_SOURCE_DIR}/tools/solver_profile_hooks.h")\n'
                'target_compile_options(_qes PRIVATE -include "${CMAKE_CURRENT_SOURCE_DIR}/tools/solver_profile_hooks.h")\n')


def audit(output):
    manifest = json.loads((output/"manifest.json").read_text())
    for name, sha in manifest["files"].items():
        if legacy.digest((output/name).read_bytes()) != sha:
            raise ValueError(f"Changed S2 evidence: {name}")
    for name, snapshot in manifest["sources"].items():
        with tarfile.open(output/name) as archive:
            for member, sha in snapshot["files"].items():
                if legacy.digest(archive.extractfile(member).read()) != sha:
                    raise ValueError(f"Changed S2 source: {member}")
    summary = json.loads((output/"summary.json").read_text())
    if not summary["completed"] or not summary["parity_passed"]:
        raise ValueError("Incomplete S2 profile or instrumentation parity")
    return {"passed": True, "files": len(manifest["files"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--source-archive", type=Path)
    ap.add_argument("--stage", default="candidate")
    ap.add_argument("--iterations", type=int, default=80)
    ap.add_argument("--audit", action="store_true")
    args = ap.parse_args()
    output = args.output.resolve()
    if args.audit:
        print(json.dumps(audit(output))); return
    if not 1 <= args.iterations <= 500:
        ap.error("iterations must be between 1 and 500")
    output.mkdir(parents=True, exist_ok=False)
    work = ROOT/"build/solver-control-s2"/args.stage
    plain = work/"plain-tree"
    plain.mkdir(parents=True, exist_ok=False)
    if args.source_archive:
        with tarfile.open(args.source_archive) as archive:
            archive.extractall(plain, filter="data")
        # The original snapshot predates this profiler; record the exact tool too.
        shutil.copyfile(Path(__file__), plain/"tools/profile_solver_s2.py")
    else:
        for p in source_files(ROOT):
            dest = plain/p.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
    sources = {"sources.tar.gz": legacy.archive_files(output/"sources.tar.gz", source_files(plain), plain)}
    profiled = work/"profile-tree"
    shutil.copytree(plain, profiled)
    instrument(profiled)
    sources["instrumented-sources.tar.gz"] = legacy.archive_files(output/"instrumented-sources.tar.gz", source_files(profiled), profiled)
    harness = legacy.load_harness()
    packages = {}
    for backend in ("openmp", "serial"):
        for kind, tree in (("plain", plain), ("profile", profiled)):
            module = harness.build(tree, work/f"{kind}-{backend}-build", backend)
            package = work/f"{kind}-{backend}-package"
            harness.stage_package(tree, module, package)
            packages[kind, backend] = package
    matrix = [(backend, precision, threads, kind, 0, False)
              for backend in ("openmp", "serial") for precision in ("float32", "float64")
              for threads in ((1,2,4,8) if backend == "openmp" else (1,)) for kind in ("plain", "profile")]
    matrix += [("openmp", p, 4, kind, 1, False) for p in ("float32", "float64") for kind in ("plain", "profile")]
    matrix += [("openmp", p, 4, kind, 0, True) for p in ("float32", "float64") for kind in ("plain", "profile")]
    protocol = dict(stage=args.stage, utc=datetime.now(timezone.utc).isoformat(),
        input_archive_sha256=legacy.digest(args.source_archive.read_bytes()) if args.source_archive else None,
        platform=platform.platform(), cpu_count=os.cpu_count(), iterations=args.iterations,
        matrix=matrix, per_worker_seconds=30, total_matrix_seconds=180,
        geometry="S0 tower; 0.5 m xy; automatic 92 layers; Uref=5 m/s, direction=270; worker checks shape and completed sweeps",
        warmup="Small flat 2-sweep solve; imports, City creation, warmup and hashing excluded from API timer",
        instrumentation="Isolated snapshot only. Phase clocks bracket native calls; no clocks in cell loops. Plain/profile numerical parity required.",
        memory="Vector sizes/capacities at prepare, operator-owned and workspace bytes; RSS is process high-water including transient setup and output copies.",
        bandwidth="No DRAM counters. Logical byte models are reported separately from measured phase time; no bandwidth bottleneck claim.")
    legacy.write_json(output/"protocol.json", protocol)
    rows = []
    start = time.monotonic()
    for index, (backend, precision, threads, kind, repeat, turbulence) in enumerate(matrix):
        remaining = 180-(time.monotonic()-start)
        name = f"runs/{index:02d}-{backend}-{kind}-{precision}-{threads}t.json"
        package = packages[kind, backend]
        cmd = [sys.executable, str(ROOT/"tools/profile_solver_baseline.py"), "--worker", "--package", str(package),
               "--precision", precision, "--iterations", str(args.iterations), "--output", str(output/name)]
        if kind == "profile": cmd.append("--instrumented")
        if turbulence: cmd.append("--turbulence")
        if remaining <= 0:
            row = dict(status="skipped_total_budget")
        else:
            try:
                result = subprocess.run(cmd, text=True, capture_output=True, timeout=min(30,remaining), cwd=ROOT,
                    env=os.environ|dict(PYTHONPATH=str(package), OMP_NUM_THREADS=str(threads), OMP_DYNAMIC="FALSE"))
                row = json.loads((output/name).read_text()) if result.returncode == 0 else dict(status="failed", stderr=result.stderr[-6000:])
                if row.get("status") == "completed" and (row["shape"] != [92,320,320] or
                        row["diagnostics"]["iterations"] != args.iterations):
                    row["status"] = "unexpected_grid_or_work"
            except subprocess.TimeoutExpired:
                row = dict(status="timeout", limit_seconds=min(30,remaining))
        row.update(record=name, backend=backend, repeat=repeat)
        legacy.write_json(output/name, row)
        rows.append(row)
        print(f"{args.stage} {index}/{len(matrix)} {backend}/{precision}/{threads}t/{kind}: {row['status']}", flush=True)
    paired = []
    for backend, precision, threads, _, repeat, turbulence in matrix[::2]:
        selected = [r for r in rows if r.get("status") == "completed" and
                    (r["backend"],r["precision"],r["requested_threads"],r["repeat"],r["turbulence"]) ==
                    (backend,precision,threads,repeat,turbulence)]
        paired.append(dict(backend=backend, precision=precision, threads=threads, repeat=repeat, turbulence=turbulence,
            passed=len(selected)==2 and selected[0]["output_sha256"]==selected[1]["output_sha256"]
            and selected[0]["diagnostics"]==selected[1]["diagnostics"]))
    summary = dict(runs=rows, paired=paired, elapsed_seconds=time.monotonic()-start,
                   completed=all(r["status"]=="completed" for r in rows), parity_passed=all(p["passed"] for p in paired))
    legacy.write_json(output/"summary.json", summary)
    files = {p.relative_to(output).as_posix():legacy.digest(p.read_bytes()) for p in output.rglob("*") if p.is_file()}
    legacy.write_json(output/"manifest.json", dict(sources=sources, files=files))
    print(json.dumps(audit(output)))


if __name__ == "__main__":
    main()

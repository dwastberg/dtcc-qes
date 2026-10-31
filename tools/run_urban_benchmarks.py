"""Build, run and summarize a complete urban wind benchmark campaign.

Example: .venv/bin/python tools/run_urban_benchmarks.py --tier pilot
Only validated native builds are reused; every invocation measures fresh workers.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import fcntl
import importlib.metadata
import inspect
import io
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import sysconfig
import time
from types import SimpleNamespace
import uuid

import benchmark_urban_wind as benchmark
import compare_native_builds as native
from profile_solver_baseline import archive_files
from profile_solver_s2 import source_files

ROOT = Path(__file__).resolve().parents[1]
BASELINES = {"overall": "s1a", "controls": "s3"}


def stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def file_identity(path):
    path = Path(path)
    return dict(path=str(path.resolve()), sha256=benchmark.digest(path))


def tool_identity(command):
    parts = shlex.split(command)
    executable = shutil.which(parts[0]) if parts else None
    if executable is None:
        raise RuntimeError(f"Required build tool not found: {command}")
    result = subprocess.run([executable, *parts[1:], "--version"], check=True,
                            capture_output=True, text=True, timeout=30)
    return dict(command=parts, executable=file_identity(executable), version=result.stdout + result.stderr)


def build_context():
    """Fingerprint build inputs, independently of the benchmark tier and results."""
    nanobind = importlib.metadata.distribution("nanobind")
    binding_files = {}
    for name in nanobind.files or ():
        path = Path(nanobind.locate_file(name))
        if path.is_file() and path.suffix in (".h", ".hpp", ".cpp", ".cmake", ".py"):
            binding_files[str(name)] = benchmark.digest(path)
    include = Path(sysconfig.get_path("include"))
    environment = {k: v for k, v in os.environ.items() if
                   k.startswith(("CMAKE_", "OpenMP_", "DTCC_QES_")) or k in {
                       "PATH", "CC", "CXX", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
                       "CPATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH", "LD_LIBRARY_PATH",
                       "DYLD_LIBRARY_PATH", "SDKROOT", "MACOSX_DEPLOYMENT_TARGET", "DEVELOPER_DIR",
                       "ARCHFLAGS", "MAKEFLAGS", "AR", "LD", "RANLIB"}}
    tools = dict(cmake=tool_identity("cmake"), cxx=tool_identity(os.environ.get("CXX", "c++")))
    if sys.platform == "darwin":
        tools["sdk"] = {name: subprocess.run(["xcrun", f"--show-sdk-{name}"],
            check=True, capture_output=True, text=True, timeout=30).stdout.strip() for name in ("path", "version")}
        sdk = Path(tools["sdk"]["path"])
        tools["sdk"]["settings"] = {name: file_identity(sdk / name) for name in
            ("SDKSettings.json", "SDKSettings.plist") if (sdk / name).is_file()}
    configuration_files = {name: file_identity(value) for name, value in environment.items()
                           if name.startswith("CMAKE_") and Path(value).is_absolute() and Path(value).is_file()}
    return dict(schema="urban-build-cache-v1", platform=platform.platform(), machine=platform.machine(),
        python=dict(executable=str(Path(sys.executable).absolute()), version=sys.version,
                    soabi=sysconfig.get_config_var("SOABI"), binary=file_identity(sys.executable),
                    headers={str(p.relative_to(include)): benchmark.digest(p) for p in sorted(include.rglob("*.h"))}),
        nanobind=dict(version=nanobind.version, files=binding_files), tools=tools, environment=environment,
        configuration_files=configuration_files,
        builder_files={p.name: benchmark.digest(p) for p in (
            Path(__file__), Path(native.__file__), ROOT / "tools/profile_solver_baseline.py",
            ROOT / "tools/profile_solver_s2.py")},
        instrumentation=inspect.getsource(benchmark.instrument_team_probe),
        staging=inspect.getsource(benchmark.package_index), build_type="Release")


def dependency_files(build_dir):
    """Include the selected compiler, build tools and OpenMP headers/runtime."""
    paths = set()
    for line in (build_dir / "CMakeCache.txt").read_text().splitlines():
        if line.startswith(("//", "#")) or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.split(":", 1)[0]
        if name in {"CMAKE_CXX_COMPILER", "CMAKE_MAKE_PROGRAM", "CMAKE_LINKER", "CMAKE_AR", "CMAKE_RANLIB"} or name.startswith("OpenMP_"):
            for item in value.split(";"):
                path = Path(item)
                if path.is_absolute() and path.is_file():
                    paths.add(path)
                elif path.is_absolute() and path.is_dir():
                    paths.update(path.glob("omp*.h"))
    return {str(p): file_identity(p) for p in sorted(paths)}


def verify_package(package, backend):
    """Check import isolation, dynamic linkage and the actual OpenMP team."""
    code = '''import sys
from pathlib import Path
import dtcc_qes
from dtcc_qes import wind, _qes
root = Path(sys.argv[1]).resolve()
if any(not Path(m.__file__).resolve().is_relative_to(root) for m in (dtcc_qes, wind, _qes)):
    raise RuntimeError("Imported a package outside the build cache")
expected = sys.argv[2] == "openmp"
if bool(_qes.openmp_enabled) != expected:
    raise RuntimeError("Cached backend differs from requested backend")
if _qes._urban_benchmark_actual_threads() != (2 if expected else 1):
    raise RuntimeError("Unexpected OpenMP team in cached extension")
'''
    result = subprocess.run([sys.executable, "-c", code, str(package), backend], cwd=package,
        env=os.environ | dict(PYTHONPATH=str(package), OMP_NUM_THREADS="2", OMP_DYNAMIC="FALSE"),
        capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Cached package import/probe failed: " + result.stderr[-2000:])


def cached_build(archive, backend, cache, context, *, rebuild=False, label="solver"):
    source_id = "sha256:" + benchmark.digest(archive)
    identity = dict(source_id=source_id, backend=backend, context=context)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    entry = cache / "builds" / key
    current = entry / "current.json"
    reason = "no matching source/toolchain cache"
    if current.exists() and not rebuild:
        try:
            record = json.loads(current.read_text())
            if record["identity"] != identity:
                raise ValueError("cache identity changed")
            value = record["build"]
            if benchmark.package_index(Path(value["package"])) != value["files"]:
                raise ValueError("cached package files changed or are missing")
            if benchmark.digest(value["instrumented_archive"]) != value["instrumented_sources"]["sha256"]:
                raise ValueError("instrumented source archive changed or is missing")
            if any(file_identity(p) != expected for p, expected in record["dependencies"].items()):
                raise ValueError("compiler, build tool or OpenMP dependency changed")
            verify_package(Path(value["package"]), backend)
            print(f"Reusing {label}: {source_id[7:19]} ({backend}, verified)", flush=True)
            return value, dict(key=key, reused=True, reason="source, toolchain, package and import checks passed")
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError, subprocess.SubprocessError) as error:
            reason = str(error)
    if rebuild:
        reason = "--rebuild requested"
    print(f"Building {label}: {source_id[7:19]} ({reason})", flush=True)
    generation = entry / stamp()
    generation.mkdir(parents=True)
    log_path = generation / "build.log"
    try:
        with log_path.open("w") as log, redirect_stdout(log), redirect_stderr(log):
            print(f"Archive: {archive}\nSource: {source_id}\nBackend: {backend}\nCache key: {key}", flush=True)
            tree, _, exported_id = native.export_archive(archive, generation / "work")
            if exported_id != source_id:
                raise ValueError("Source archive changed during preparation")
            benchmark.instrument_team_probe(tree)
            instrumented_archive = generation / "probe-sources.tar.gz"
            instrumented = archive_files(instrumented_archive, source_files(tree), tree)
            build_dir = generation / "native"
            module = native.build(tree, build_dir, backend)
            package = generation / "package"
            native.stage_package(tree, module, package)
            verify_package(package, backend)
            value = dict(package=str(package), source_id=source_id,
                         instrumented_sources=instrumented, instrumented_archive=str(instrumented_archive),
                         files=benchmark.package_index(package))
            dependencies = dependency_files(build_dir)
            print(f"Build and import checks passed. CMake configuration: {build_dir / 'CMakeCache.txt'}", flush=True)
        benchmark.write(current, dict(identity=identity, build=value, dependencies=dependencies))
    except Exception as error:
        raise RuntimeError(f"Build of {label} failed; see {log_path}: {error}") from error
    print(f"Built {label}; log: {log_path}", flush=True)
    return value, dict(key=key, reused=False, reason=reason)


@contextmanager
def campaign_lock(cache):
    """Avoid simultaneous builds or timing campaigns using the same cache."""
    cache.mkdir(parents=True, exist_ok=True)
    with (cache / "campaign.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another benchmark is using {cache}; wait for it to finish") from error
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def campaign(args):
    output = (args.output or ROOT / "build/urban-benchmarks" / stamp()).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cache = args.cache_dir.resolve()
    baseline = (args.baseline_archive or ROOT / f"docs/data/solver-control-s5/{BASELINES[args.comparison]}-matched-mask-sources.tar.gz").resolve()
    candidate = args.candidate_archive.resolve()
    state = dict(schema="urban-campaign-v1", status="running", tier=args.tier, backend=args.backend,
                 iterations=args.iterations, max_solve_seconds=args.solve_seconds,
                 started_utc=datetime.now(timezone.utc).isoformat(), output=str(output),
                 command=sys.argv, runner_sha256=benchmark.digest(__file__), shards=[])
    started = time.monotonic()
    benchmark.write(output / "campaign.json", state)
    print(f"Campaign: {output}", flush=True)
    try:
        with campaign_lock(cache):
            context = build_context()
            values = {}; decisions = {}
            for label, archive in (("baseline", baseline), ("candidate", candidate)):
                values[label], decisions[label] = cached_build(archive, args.backend, cache, context,
                                                              rebuild=args.rebuild, label=label)
            build_manifest = output / "builds.json"
            benchmark.write(build_manifest, dict(backend=args.backend, builds=values))
            state["build_cache"] = decisions
            benchmark.write(output / "campaign.json", state)

            fixtures = output / "fixtures"
            command = [sys.executable, str(Path(benchmark.__file__).resolve()), "fixtures",
                       "--tier", args.tier, "--output", str(fixtures), "--solve-seconds", str(args.solve_seconds)]
            if args.iterations is not None:
                command.extend(["--iterations", str(args.iterations)])
            for path in args.city_case:
                command.extend(["--city-case", str(path.resolve())])
            print(f"Preparing fresh {args.tier} fixtures...", flush=True)
            with (output / "fixtures.log").open("w") as log:
                subprocess.run(command, check=True, cwd=ROOT,
                    env=os.environ | dict(PYTHONPATH=values["candidate"]["package"]),
                    stdout=log, stderr=subprocess.STDOUT, timeout=180)
            protocol = benchmark.check_inputs(fixtures)
            state["expected_rows"] = len(protocol["rows"])
            print(f"Running {len(protocol['rows'])} workers in {protocol['shards']} sequential shards "
                  f"(up to {protocol['shards'] * protocol['total_shard_seconds'] / 60:g} minutes, excluding preparation).", flush=True)
            runs = []
            for shard in range(protocol["shards"]):
                folder = output / f"run-{shard:02d}"
                print(f"Shard {shard + 1}/{protocol['shards']}...", flush=True)
                with (output / f"run-{shard:02d}.log").open("w") as log, redirect_stdout(log):
                    benchmark.run(SimpleNamespace(fixtures=fixtures, builds=build_manifest, shard=shard, output=folder))
                runs.append(folder)
                summary = json.loads((folder / "summary.json").read_text())
                n = sum(r["status"] == "completed" for r in summary["results"])
                state["shards"].append(dict(shard=shard, completed=n, workers=len(summary["results"]), output=str(folder)))
                benchmark.write(output / "campaign.json", state)
                print(f"  {n}/{len(summary['results'])} completed in {summary['elapsed_seconds']:.2f} s", flush=True)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                benchmark.aggregate(SimpleNamespace(runs=runs, output=output / "results.json"))
            report = buffer.getvalue()
            (output / "results.txt").write_text(report)
            print(report, end="", flush=True)
            state["status"] = "completed" if all(s["completed"] == s["workers"] for s in state["shards"]) else "incomplete"
            state["elapsed_seconds"] = time.monotonic() - started
            benchmark.write(output / "campaign.json", state)
            print(f"Campaign {state['status']} in {state['elapsed_seconds']:.2f} s. Report: {output / 'results.txt'}", flush=True)
            return 0 if state["status"] == "completed" else 1
    except BaseException as error:
        state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                     error=str(error), elapsed_seconds=time.monotonic() - started)
        benchmark.write(output / "campaign.json", state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("smoke", "pilot", "core", "scale"), default="pilot")
    parser.add_argument("--iterations", type=benchmark.positive_iterations, help="Override the tier iteration cap")
    parser.add_argument("--solve-seconds", type=benchmark.positive_seconds, default=5.,
                        help="Monitored solve budget (default: 5 seconds)")
    parser.add_argument("--comparison", choices=tuple(BASELINES), default="overall",
                        help="overall: S1a to current; controls: S3 to current; baselines share the current mask correction")
    parser.add_argument("--baseline-archive", type=Path, help="Override the comparison baseline")
    parser.add_argument("--candidate-archive", type=Path, default=ROOT / "docs/data/solver-control-s9/sources.tar.gz",
                        help="Frozen S9 release sources; older archives can be selected explicitly")
    parser.add_argument("--backend", choices=("openmp", "serial"), default="openmp")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "build/urban-benchmark-cache")
    parser.add_argument("--output", type=Path, help="Fresh campaign directory; default: timestamp under build/urban-benchmarks")
    parser.add_argument("--city-case", type=Path, action="append", default=[])
    parser.add_argument("--rebuild", action="store_true", help="Build fresh cache generations even if reuse checks pass")
    args = parser.parse_args()
    try:
        return campaign(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

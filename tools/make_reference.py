#!/usr/bin/env python3
"""Generate QES-Winds reference results for the dtcc-qes test fixtures.

For every case in ``tests/fixtures/cases.py`` this tool

1. writes a QES XML input file using polygon (``QUICBuilding``) buildings in
   local coordinates,
2. runs the standalone ``qesWinds`` executable with the serial CPU solver,
3. reads its NetCDF visualization and workspace output, and
4. stores velocities, cell flags, coordinates and the solver summary as a
   compressed NumPy archive (``<case>.npz``) plus a JSON metadata file
   (``<case>.json``) recording the QES revision, compiler, flags and platform.

By default the *unmodified* QES sources at ``QES_REFERENCE_REV`` are exported
from the ``QES-Public`` submodule with ``git archive`` and built in
``build/qes-reference``. ``--qes-source`` builds another QES tree instead, for
example the patched submodule, which must reproduce the stored references.

This tool needs a QES build with GDAL, NetCDF (C and C++) and Boost, and the
``reference`` dependency group (``netCDF4``). None of these are dependencies
of the dtcc-qes library.

Usage::

    uv run --group reference tools/make_reference.py            # regenerate
    uv run --group reference tools/make_reference.py --check    # compare only

Turbulence references require an explicit baseline. ``upstream`` uses only
safety-qualified pristine cases; ``audited`` exports the exact revision in
``_qes_revision.txt``. ``--method 0|1`` filters the named method-specific cases.
Source contents are verified against Git blobs, and existing executables need
a matching build attestation. Wind tolerances never relax turbulence fields::

    uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline upstream
    uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline audited
    uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline audited --check
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
QES_SUBMODULE = ROOT / "QES-Public"
# QES 2.3.1, the unmodified upstream revision the references are taken from.
QES_REFERENCE_REV = "dced7ec571487be7538eca17bfc25bb3262fb6d0"

sys.path.insert(0, str(ROOT / "tests"))
from fixtures import cases as fixtures  # noqa: E402
from fixtures.turbulence_cases import CASES as TURBULENCE_CASES  # noqa: E402

# Arrays compared by --check (all of them except purely descriptive ones).
COMPARED_ARRAYS = (
    "x", "y", "z", "u", "v", "w", "icell",
    "x_face", "y_face", "z_face", "u_face", "v_face", "w_face", "icellflag_full", "dz_array",
)
TURBULENCE_ARRAYS = ("stress", "tke", "co_eps", "mixing_length", "computed", "iturbflag")
STRESS_COMPONENTS = ("txx", "txy", "txz", "tyy", "tyz", "tzz")


# --------------------------------------------------------------------------
# Building QES
# --------------------------------------------------------------------------

def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, text=True, **kwargs)


def export_pristine_qes(rev: str, dest: Path) -> Path:
    """Export the QES submodule at ``rev`` into ``dest`` (replacing it)."""
    full_rev = run(["git", "-C", str(QES_SUBMODULE), "rev-parse", rev],
                   capture_output=True).stdout.strip()
    stamp = dest / ".qes-revision"
    if stamp.exists() and stamp.read_text().strip() == full_rev:
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    archive = subprocess.Popen(
        ["git", "-C", str(QES_SUBMODULE), "archive", full_rev], stdout=subprocess.PIPE
    )
    run(["tar", "-x", "-C", str(dest)], stdin=archive.stdout)
    if archive.wait() != 0:
        raise RuntimeError(f"git archive of QES revision {rev} failed")
    stamp.write_text(full_rev + "\n")
    return dest


def netcdf_cxx_hints() -> list[str]:
    """Locate the NetCDF C++ library without machine-specific paths.

    QES's FindNetCDF.cmake (at the reference revision) only searches for a
    library named ``netcdf_c++4``; Homebrew and several Linux distributions
    install it as ``netcdf-cxx4``. Ask ``ncxx4-config`` or ``pkg-config`` where
    the library is and pass it to CMake explicitly.
    """
    prefix = None
    for cmd in (["ncxx4-config", "--prefix"], ["pkg-config", "--variable=prefix", "netcdf-cxx4"]):
        if shutil.which(cmd[0]):
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                prefix = Path(res.stdout.strip())
                break
    if prefix is None:
        return []
    libdir = None
    for cand in ("lib", "lib64", f"lib/{platform.machine()}-linux-gnu"):
        if (prefix / cand).is_dir():
            for name in ("libnetcdf-cxx4", "libnetcdf_c++4"):
                for ext in (".dylib", ".so", ".a"):
                    if (prefix / cand / f"{name}{ext}").exists():
                        libdir = prefix / cand / f"{name}{ext}"
                        break
                if libdir:
                    break
        if libdir:
            break
    if libdir is None:
        return []
    return [
        f"-DNETCDF_LIBRARIES_CXX={libdir}",
        f"-DNETCDF_INCLUDES_CXX={prefix / 'include'}",
    ]


def build_qes(source: Path, build: Path, jobs: int, *, turbulence: bool = False) -> Path:
    configure = [
        "cmake", "-S", str(source), "-B", str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        "-DENABLE_OPENMP=OFF",
        "-DCMAKE_CUDA_COMPILER=NOTFOUND",
        "-DCMAKE_DISABLE_FIND_PACKAGE_CUDAToolkit=ON",
        "-DQES_ENABLE_CUDA=OFF", "-DQES_BUILD_PLUME=OFF",
        "-DQES_BUILD_FIRE=OFF", "-DQES_BUILD_EXAMPLES=OFF",
        *netcdf_cxx_hints(),
    ]
    if turbulence:
        configure += ["-DQES_ENABLE_IO=ON", "-DQES_BUILD_EXECUTABLES=ON",
                      "-DQES_ENABLE_OPTIX=OFF", "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
                      "-DCMAKE_CXX_STANDARD=17"]
    run(configure, capture_output=True)
    run(["cmake", "--build", str(build), "--target", "qesWinds", "-j", str(jobs)],
        capture_output=True)
    exe = build / "qesWinds" / "qesWinds"
    if not exe.exists():
        raise RuntimeError(f"qesWinds executable not found at {exe}")
    return exe


def cmake_cache(build: Path) -> dict[str, str]:
    values = {}
    for line in (build / "CMakeCache.txt").read_text().splitlines():
        m = re.match(r"^([A-Za-z0-9_]+):[A-Z]+=(.*)$", line)
        if m:
            values[m.group(1)] = m.group(2)
    return values


def toolchain_info(build: Path) -> dict[str, str]:
    cache = cmake_cache(build)
    compiler = cache.get("CMAKE_CXX_COMPILER", "")
    version = ""
    try:
        version = run([compiler, "--version"], capture_output=True).stdout.splitlines()[0]
    except Exception:  # noqa: BLE001 - informational only
        pass
    build_type = cache.get("CMAKE_BUILD_TYPE", "")
    return {
        "compiler": compiler,
        "compiler_version": version,
        "build_type": build_type,
        "cxx_flags": " ".join(
            f for f in (cache.get("CMAKE_CXX_FLAGS", ""),
                        cache.get(f"CMAKE_CXX_FLAGS_{build_type.upper()}", "")) if f
        ),
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def qes_revision(source: Path) -> dict[str, object]:
    stamp = source / ".qes-revision"
    if stamp.exists():
        return {"revision": stamp.read_text().strip(), "modified": False}
    rev = run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True).stdout.strip()
    dirty = bool(run(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
                     capture_output=True).stdout.strip())
    return {"revision": rev, "modified": dirty}


def audited_revision() -> str:
    return (ROOT / "src/dtcc_qes/_qes_revision.txt").read_text().strip()


def verified_source(source: Path, revision: str) -> dict:
    """Verify source bytes against the pinned Git tree, not just a stamp."""
    exported = not (source / ".git").exists()
    identity = qes_revision(source) if exported else {
        "revision": run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True).stdout.strip(),
        "modified": bool(run(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all"],
                             capture_output=True).stdout.strip()),
    }
    if identity["revision"] != revision or identity["modified"]:
        raise ValueError(f"Reference source must be clean at {revision}, got {identity}")
    entries = {}
    listing = subprocess.check_output(["git", "-C", str(QES_SUBMODULE), "ls-tree", "-rz", revision])
    for record in listing.split(b"\0"):
        if not record:
            continue
        description, filename = record.split(b"\t", 1)
        mode, kind, oid = description.decode().split()
        if kind != "blob":
            continue
        name = filename.decode()
        path = source / name
        if not path.exists() and not path.is_symlink():
            raise ValueError(f"Pinned reference source is missing {name}")
        if (mode == "120000") != path.is_symlink():
            raise ValueError(f"Pinned reference source changed file type: {name}")
        if not path.is_symlink() and bool(path.stat().st_mode & 0o111) != (mode == "100755"):
            raise ValueError(f"Pinned reference source changed file mode: {name}")
        contents = os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes()
        actual = hashlib.sha1(f"blob {len(contents)}\0".encode() + contents).hexdigest()
        if actual != oid:
            raise ValueError(f"Pinned reference source was modified: {name}")
        entries[name] = {"mode": mode, "git_blob": oid}
    if exported:
        extra = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file() or p.is_symlink()}
        extra -= entries.keys() | {".qes-revision"}
        if extra:
            raise ValueError(f"Exported reference source has untracked files: {sorted(extra)}")
    tree = run(["git", "-C", str(QES_SUBMODULE), "rev-parse", f"{revision}^{{tree}}"],
               capture_output=True).stdout.strip()
    return {"revision": revision, "modified": False, "tree": tree,
            "verified_files": len(entries),
            "source_manifest_sha256": hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()}


def turbulence_build_info(build: Path) -> dict:
    info = toolchain_info(build)
    info["compiler_command_version"] = info["compiler_version"]
    compiler_file = next((build / "CMakeFiles").glob("*/CMakeCXXCompiler.cmake"))
    compiler_text = compiler_file.read_text()
    for key in ("ID", "VERSION"):
        value = re.search(rf'set\(CMAKE_CXX_COMPILER_{key} "([^"]+)"\)', compiler_text)
        info[f"compiler_{key.lower()}"] = value.group(1) if value else "unknown"
    cache = cmake_cache(build)
    options = {key: cache.get(key) for key in (
        "ENABLE_OPENMP", "QES_ENABLE_IO", "QES_ENABLE_CUDA", "QES_ENABLE_OPTIX",
        "QES_BUILD_EXECUTABLES", "CMAKE_POSITION_INDEPENDENT_CODE", "CMAKE_CXX_STANDARD")}
    return {"toolchain": info, "build_options": options}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def attest_build(exe: Path, build: Path, source: Path, revision: str, *, existing: bool) -> dict:
    evidence = {"qes": verified_source(source, revision), **turbulence_build_info(build),
                "executable_sha256": file_sha256(exe)}
    stamp = build / "turbulence-reference-build.json"
    if existing:
        if not stamp.exists() or json.loads(stamp.read_text()) != evidence:
            raise ValueError("Existing turbulence executable has no matching verified build attestation; rebuild it")
    else:
        stamp.write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def select_turbulence_cases(names: list[str], baseline: str, method: int | None) -> list:
    selected = [TURBULENCE_CASES[name] for name in names] if names else list(TURBULENCE_CASES.values())
    if names and any(spec.upstream_exclusion for spec in selected) and baseline == "upstream":
        raise ValueError("Unsafe or unqualified upstream case requested; use the audited baseline")
    selected = [spec for spec in selected if baseline != "upstream" or not spec.upstream_exclusion]
    if method is not None:
        if names and any(spec.method != method for spec in selected):
            raise ValueError("Named cases have a different mixing method; select a matching method-specific case")
        selected = [spec for spec in selected if spec.method == method]
    if not selected:
        raise ValueError("No reference cases selected")
    return selected


def case_definition(spec) -> dict:
    return json.loads(json.dumps({"case": asdict(spec.case), "mixing_length_method": spec.method,
                                  "dz_layers": spec.dz_layers}))


# --------------------------------------------------------------------------
# QES XML
# --------------------------------------------------------------------------

def write_xml(case: fixtures.Case, path: Path, *, turbulence: bool = False,
              method: int = 0, dz_layers: tuple = ()) -> None:
    g, w, p, s = case.grid, case.wind, case.parameterizations, case.solver
    buildings = []
    for b in case.buildings:
        verts = "\n".join(
            f"      <xVertex>{x!r}</xVertex>\n      <yVertex>{y!r}</yVertex>" for x, y in b.vertices
        )
        buildings.append(
            "    <QUICBuilding>\n"
            f"      <height>{b.height!r}</height>\n"
            f"      <baseHeight>{b.base_height!r}</baseHeight>\n"
            f"{verts}\n"
            "    </QUICBuilding>"
        )
    building_xml = "\n".join(buildings)
    layers_xml = "<verticalStretching>0</verticalStretching>"
    if dz_layers:
        layers_xml = "<verticalStretching>1</verticalStretching>\n    " + "\n    ".join(
            f"<dz_value>{h!r}</dz_value>" for h in dz_layers)
    vertical_spacing = min(dz_layers) if dz_layers else g.cell_size
    turbulence_xml = f"  <turbParams><method>{method}</method></turbParams>\n" if turbulence else ""
    xml = f"""<QESWindsParameters>
  <simulationParameters>
    <halo_x>{case.halo_x!r}</halo_x>
    <halo_y>{case.halo_y!r}</halo_y>
    <domain>{g.nx} {g.ny} {g.nz}</domain>
    <cellSize>{g.cell_size!r} {g.cell_size!r} {vertical_spacing!r}</cellSize>
    {layers_xml}
    <totalTimeIncrements>1</totalTimeIncrements>
    <logLawFlag>{case.log_law_flag}</logLawFlag>
    <maxIterations>{s.max_iterations}</maxIterations>
    <tolerance>{s.tolerance!r}</tolerance>
    <meshTypeFlag>{case.mesh_type_flag}</meshTypeFlag>
    <domainRotation>0</domainRotation>
    <UTMx>0</UTMx>
    <UTMy>0</UTMy>
    <UTMZone>1</UTMZone>
    <UTMZoneLetter>17</UTMZoneLetter>
    <readCoefficientsFlag>0</readCoefficientsFlag>
  </simulationParameters>
  <metParams>
    <z0_domain_flag>0</z0_domain_flag>
    <sensor>
      <site_coord_flag>1</site_coord_flag>
      <site_xcoord>{w.sensor_x!r}</site_xcoord>
      <site_ycoord>{w.sensor_y!r}</site_ycoord>
      <timeSeries>
        <timeStamp>{w.timestamp}</timeStamp>
        <boundaryLayerFlag>1</boundaryLayerFlag>
        <siteZ0>{w.roughness_length!r}</siteZ0>
        <reciprocal>0.0</reciprocal>
        <height>{w.reference_height!r}</height>
        <speed>{w.speed!r}</speed>
        <direction>{w.direction!r}</direction>
      </timeSeries>
    </sensor>
  </metParams>
  <buildingsParams>
    <wallRoughness>{p.wall_roughness!r}</wallRoughness>
    <rooftopFlag>{p.rooftop_flag}</rooftopFlag>
    <upwindCavityFlag>{p.upwind_cavity_flag}</upwindCavityFlag>
    <streetCanyonFlag>{p.street_canyon_flag}</streetCanyonFlag>
    <streetIntersectionFlag>{p.street_intersection_flag}</streetIntersectionFlag>
    <wakeFlag>{p.wake_flag}</wakeFlag>
    <highRiseFlag>{p.high_rise_flag}</highRiseFlag>
    <sidewallFlag>{p.sidewall_flag}</sidewallFlag>
{building_xml}
  </buildingsParams>
{turbulence_xml}  <fileOptions>
    <outputFlag>1</outputFlag>
    <outputFields>all</outputFields>
  </fileOptions>
</QESWindsParameters>
"""
    path.write_text(xml)


# --------------------------------------------------------------------------
# Running a case
# --------------------------------------------------------------------------

_SUMMARY = re.compile(r"Residual after (\d+) itertations: ([-+0-9.eEinfa]+)")


def run_case(exe: Path, case: fixtures.Case, workdir: Path, *, turbulence: bool = False,
             method: int = 0, dz_layers: tuple = ()) -> tuple[dict[str, np.ndarray], dict]:
    from netCDF4 import Dataset  # reference dependency group only

    xml = workdir / f"{case.name}.xml"
    write_xml(case, xml, turbulence=turbulence, method=method, dz_layers=dz_layers)
    base = workdir / case.name
    # -s 1: serial CPU solver; -w: workspace (staggered) output.
    proc = subprocess.run(
        [str(exe), "-q", str(xml), "-o", str(base), "-w", "-s", "1", *(["-t"] if turbulence else [])],
        capture_output=True, text=True, cwd=workdir,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"qesWinds failed for {case.name}:\n{proc.stdout}\n{proc.stderr}")
    m = _SUMMARY.findall(proc.stdout)
    if len(m) != 1:
        raise RuntimeError(f"could not parse solver summary for {case.name}:\n{proc.stdout}")
    iterations, max_change = int(m[0][0]), float(m[0][1])

    arrays: dict[str, np.ndarray] = {}
    with Dataset(f"{base}_windsOut.nc") as nc:
        nc.set_auto_mask(False)
        for name in ("x", "y", "z"):
            arrays[name] = np.asarray(nc.variables[name][:])
        for name in ("u", "v", "w"):
            arrays[name] = np.asarray(nc.variables[name][0])  # (nz, ny, nx)
        arrays["icell"] = np.asarray(nc.variables["icell"][0])
    with Dataset(f"{base}_windsWk.nc") as nc:
        nc.set_auto_mask(False)
        for name in ("x_face", "y_face", "z_face"):
            arrays[name] = np.asarray(nc.variables[name][:])
        for name in ("u", "v", "w"):
            arrays[f"{name}_face"] = np.asarray(nc.variables[name][0])
        arrays["icellflag_full"] = np.asarray(nc.variables["icellflag"][0])
        arrays["dz_array"] = np.asarray(nc.variables["dz_array"][:])

    g = case.grid
    expected = (g.nz, g.ny, g.nx)
    for name in ("u", "v", "w", "icell"):
        if arrays[name].shape != expected:
            raise RuntimeError(f"{case.name}: {name} has shape {arrays[name].shape}, expected {expected}")
        if name != "icell" and not np.all(np.isfinite(arrays[name])):
            raise RuntimeError(f"{case.name}: non-finite values in {name}")

    summary = {
        "iterations": iterations,
        "max_lagrange_multiplier_change": max_change,
        "tolerance": case.solver.tolerance,
        "max_iterations": case.solver.max_iterations,
        "converged": iterations < case.solver.max_iterations,
    }
    if turbulence:
        if not summary["converged"]:
            raise RuntimeError(f"Unconverged turbulence reference: {case.name}")
        with Dataset(f"{base}_turbOut.nc") as nc:
            nc.set_auto_mask(False)
            for axis in ("x", "y"):
                np.testing.assert_array_equal(nc.variables[axis][:], arrays[axis])
            np.testing.assert_array_equal(nc.variables["z"][1:], arrays["z"])
            arrays["stress"] = np.stack([np.asarray(nc.variables[name][0,1:]) for name in STRESS_COMPONENTS], axis=-1)
            for output, name in (("tke", "tke"), ("co_eps", "CoEps"), ("mixing_length", "L"), ("iturbflag", "iturbflag")):
                arrays[output] = np.asarray(nc.variables[name][0,1:])
        computed = np.zeros(expected, dtype=np.uint8)
        computed[:-1,1:-1,1:-1] = ~np.isin(arrays["icell"][:-1,1:-1,1:-1], (0,2))
        arrays["computed"] = computed
        for name in ("stress", "tke", "co_eps", "mixing_length"):
            expected_shape = (*expected,6) if name == "stress" else expected
            if arrays[name].shape != expected_shape:
                raise RuntimeError(f"Unexpected turbulence field shape for {name}")
            if arrays[name].dtype != np.float32 or not np.isfinite(arrays[name]).all():
                raise RuntimeError(f"Reference {name} must contain finite stored float32 values")
            if np.any(arrays[name][computed == 0] != 0):
                raise RuntimeError(f"Standalone {name} is nonzero outside the computed interior")
    return arrays, summary


def compare(name: str, new: dict[str, np.ndarray], ref_path: Path, rtol: float, atol: float,
            *, turbulence: bool = False) -> list[str]:
    problems = []
    with np.load(ref_path) as ref:
        for key in (*COMPARED_ARRAYS, *(TURBULENCE_ARRAYS if turbulence else ())):
            a, b = new[key], ref[key]
            if a.shape != b.shape or a.dtype != b.dtype:
                problems.append(f"{name}.{key}: shape/dtype {a.shape}/{a.dtype} != {b.shape}/{b.dtype}")
            elif key not in {"u", "v", "w", "u_face", "v_face", "w_face"} or (rtol == 0 and atol == 0):
                if not np.array_equal(a, b):
                    diff = np.max(np.abs(a.astype(np.float64) - b.astype(np.float64)))
                    problems.append(f"{name}.{key}: differs (max abs diff {diff:.3g})")
            elif not np.allclose(a, b, rtol=rtol, atol=atol):
                diff = np.max(np.abs(a.astype(np.float64) - b.astype(np.float64)))
                problems.append(f"{name}.{key}: outside tolerance (max abs diff {diff:.3g})")
    return problems


def compare_turbulence_metadata(metadata: dict, provenance: dict, spec, archive: Path) -> list[str]:
    """Check the interpretation of stored arrays as well as their build identity."""
    expected = {key: provenance[key] for key in ("baseline", "qes", "build_options", "toolchain", "schema_version")}
    expected.update(case=spec.case.name, case_definition=case_definition(spec),
                    stress_components=list(STRESS_COMPONENTS), archive_sha256=file_sha256(archive),
                    upstream_exclusions={name: item.upstream_exclusion for name, item in TURBULENCE_CASES.items()
                                         if item.upstream_exclusion})
    return [f"{spec.case.name}: {key} metadata differs from the verified current case/build"
            for key, value in expected.items() if metadata.get(key) != value]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qes-source", type=Path, help="QES tree to build instead of the pristine reference revision")
    ap.add_argument("--qes-rev", help="QES revision to export (wind default: pristine QES_REFERENCE_REV)")
    ap.add_argument("--turbulence", action="store_true", help="generate standalone turbulence as well as wind")
    ap.add_argument("--baseline", choices=("upstream", "audited"), help="required for turbulence references")
    ap.add_argument("--method", type=int, choices=(0,1), help="select method-specific turbulence cases")
    ap.add_argument("--build-dir", type=Path, default=None, help="CMake build directory")
    ap.add_argument("--exe", type=Path, help="use an existing qesWinds executable (skips building)")
    ap.add_argument("--output", type=Path, help="where to write references (default follows baseline)")
    ap.add_argument("--reference-dir", type=Path,
                    help="reference directory for --check (default: committed fixtures)")
    ap.add_argument("--check", action="store_true", help="compare with stored references instead of writing")
    ap.add_argument("--rtol", type=float, default=0.0, help="--check relative tolerance (default exact)")
    ap.add_argument("--atol", type=float, default=0.0, help="--check absolute tolerance (default exact)")
    ap.add_argument("--keep", action="store_true", help="keep the XML/NetCDF working directory")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("cases", nargs="*", help="case names (default: all)")
    args = ap.parse_args(argv)

    if args.turbulence and not args.baseline:
        ap.error("--turbulence requires explicit --baseline upstream|audited")
    if not args.turbulence and (args.baseline or args.method is not None):
        ap.error("--baseline and --method require --turbulence")
    revision = args.qes_rev or QES_REFERENCE_REV
    if args.turbulence:
        revision = QES_REFERENCE_REV if args.baseline == "upstream" else audited_revision()
        if args.qes_rev and args.qes_rev != revision:
            ap.error(f"The {args.baseline} turbulence baseline is pinned to {revision}")
        try:
            specs = select_turbulence_cases(args.cases, args.baseline, args.method)
        except (KeyError, ValueError) as error:
            ap.error(str(error))
        selected = [spec.case for spec in specs]
        default_directory = fixtures.REFERENCE_DIR / "turbulence" / args.baseline
    else:
        selected = [fixtures.CASES[n] for n in args.cases] if args.cases else list(fixtures.CASES.values())
        specs = [None] * len(selected)
        default_directory = fixtures.REFERENCE_DIR
    output = args.output or default_directory
    reference_directory = args.reference_dir or default_directory

    if args.exe:
        exe = args.exe.resolve()
        build = exe.parents[1]
        source = Path(cmake_cache(build).get("CMAKE_HOME_DIRECTORY", str(QES_SUBMODULE)))
    else:
        if args.qes_source:
            source = args.qes_source.resolve()
            build = args.build_dir or ROOT / "build" / "qes-check"
        elif args.turbulence:
            root = ROOT / "build" / "qes-turbulence-reference" / args.baseline / revision
            source = export_pristine_qes(revision, root / "source")
            build = args.build_dir or root / "build"
        else:
            source = export_pristine_qes(revision, ROOT / "build" / "qes-reference-src")
            build = args.build_dir or ROOT / "build" / "qes-reference"
        build = build.resolve()
        if args.turbulence:
            verified_source(source, revision)
        print(f"building qesWinds from {source} in {build}", file=sys.stderr)
        exe = build_qes(source, build, args.jobs, turbulence=args.turbulence)

    provenance = {
        "qes": qes_revision(source),
        "toolchain": toolchain_info(build),
        "solver": "serial CPU (qesWinds -s 1)",
        "generator": "tools/make_reference.py",
    }
    if args.turbulence:
        provenance.update(attest_build(exe, build, source, revision, existing=bool(args.exe)))
        provenance["baseline"] = args.baseline
        provenance["schema_version"] = 1

    workdir = Path(tempfile.mkdtemp(prefix="qes-ref-"))
    problems: list[str] = []
    try:
        for case, spec in zip(selected, specs):
            arrays, summary = run_case(exe, case, workdir, turbulence=args.turbulence,
                                       method=spec.method if spec else 0, dz_layers=spec.dz_layers if spec else ())
            print(f"{case.name}: {summary['iterations']} iterations, "
                  f"max Lagrange multiplier change {summary['max_lagrange_multiplier_change']:.3g}",
                  file=sys.stderr)
            if args.check:
                reference = reference_directory / f"{case.name}.npz"
                problems += compare(case.name, arrays, reference, args.rtol, args.atol, turbulence=args.turbulence)
                with open(reference.with_suffix(".json")) as f:
                    metadata = json.load(f)
                stored = metadata["solver_summary"]
                if args.turbulence:
                    problems += compare_turbulence_metadata(metadata, provenance, spec, reference)
                if stored != summary and args.rtol == 0 and args.atol == 0:
                    problems.append(f"{case.name}: solver summary {summary} != stored {stored}")
                continue
            output.mkdir(parents=True, exist_ok=True)
            archive = output / f"{case.name}.npz"
            np.savez_compressed(archive, **arrays)
            meta = {"case": case.name, "solver_summary": summary, **provenance}
            if args.turbulence:
                meta["case_definition"] = case_definition(spec)
                meta["archive_sha256"] = file_sha256(archive)
                meta["stress_components"] = STRESS_COMPONENTS
                meta["upstream_exclusions"] = {name: item.upstream_exclusion for name, item in TURBULENCE_CASES.items()
                                               if item.upstream_exclusion}
            (output / f"{case.name}.json").write_text(json.dumps(meta, indent=2) + "\n")
    finally:
        if args.keep:
            print(f"working files kept in {workdir}", file=sys.stderr)
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    if problems:
        print("reference check FAILED:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    if args.check:
        print("reference check passed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

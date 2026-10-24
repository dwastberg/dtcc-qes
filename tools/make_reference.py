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
"""

from __future__ import annotations

import argparse
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
QES_REFERENCE_REV = "dced7ec5"

sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import cases as fixtures  # noqa: E402

# Arrays compared by --check (all of them except purely descriptive ones).
COMPARED_ARRAYS = (
    "x", "y", "z", "u", "v", "w", "icell",
    "x_face", "y_face", "z_face", "u_face", "v_face", "w_face", "icellflag_full",
)


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


def build_qes(source: Path, build: Path, jobs: int) -> Path:
    configure = [
        "cmake", "-S", str(source), "-B", str(build),
        "-DCMAKE_BUILD_TYPE=Release",
        "-DENABLE_OPENMP=OFF",
        *netcdf_cxx_hints(),
    ]
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


# --------------------------------------------------------------------------
# QES XML
# --------------------------------------------------------------------------

def write_xml(case: fixtures.Case, path: Path) -> None:
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
    xml = f"""<QESWindsParameters>
  <simulationParameters>
    <halo_x>{case.halo_x!r}</halo_x>
    <halo_y>{case.halo_y!r}</halo_y>
    <domain>{g.nx} {g.ny} {g.nz}</domain>
    <cellSize>{g.cell_size!r} {g.cell_size!r} {g.cell_size!r}</cellSize>
    <verticalStretching>0</verticalStretching>
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
  <fileOptions>
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


def run_case(exe: Path, case: fixtures.Case, workdir: Path) -> tuple[dict[str, np.ndarray], dict]:
    from netCDF4 import Dataset  # reference dependency group only

    xml = workdir / f"{case.name}.xml"
    write_xml(case, xml)
    base = workdir / case.name
    # -s 1: serial CPU solver; -w: workspace (staggered) output.
    proc = subprocess.run(
        [str(exe), "-q", str(xml), "-o", str(base), "-w", "-s", "1"],
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
    return arrays, summary


def compare(name: str, new: dict[str, np.ndarray], ref_path: Path, rtol: float, atol: float) -> list[str]:
    problems = []
    with np.load(ref_path) as ref:
        for key in COMPARED_ARRAYS:
            a, b = new[key], ref[key]
            if a.shape != b.shape or a.dtype != b.dtype:
                problems.append(f"{name}.{key}: shape/dtype {a.shape}/{a.dtype} != {b.shape}/{b.dtype}")
            elif rtol == 0 and atol == 0:
                if not np.array_equal(a, b):
                    diff = np.max(np.abs(a.astype(np.float64) - b.astype(np.float64)))
                    problems.append(f"{name}.{key}: differs (max abs diff {diff:.3g})")
            elif not np.allclose(a, b, rtol=rtol, atol=atol):
                diff = np.max(np.abs(a.astype(np.float64) - b.astype(np.float64)))
                problems.append(f"{name}.{key}: outside tolerance (max abs diff {diff:.3g})")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--qes-source", type=Path, help="QES tree to build instead of the pristine reference revision")
    ap.add_argument("--qes-rev", default=QES_REFERENCE_REV, help="QES revision to export (default: %(default)s)")
    ap.add_argument("--build-dir", type=Path, default=None, help="CMake build directory")
    ap.add_argument("--exe", type=Path, help="use an existing qesWinds executable (skips building)")
    ap.add_argument("--output", type=Path, default=fixtures.REFERENCE_DIR, help="where to write references")
    ap.add_argument("--check", action="store_true", help="compare with stored references instead of writing")
    ap.add_argument("--rtol", type=float, default=0.0, help="--check relative tolerance (default exact)")
    ap.add_argument("--atol", type=float, default=0.0, help="--check absolute tolerance (default exact)")
    ap.add_argument("--keep", action="store_true", help="keep the XML/NetCDF working directory")
    ap.add_argument("-j", "--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("cases", nargs="*", help="case names (default: all)")
    args = ap.parse_args(argv)

    selected = [fixtures.CASES[n] for n in args.cases] if args.cases else list(fixtures.CASES.values())

    if args.exe:
        exe = args.exe.resolve()
        build = exe.parents[1]
        source = Path(cmake_cache(build).get("CMAKE_HOME_DIRECTORY", str(QES_SUBMODULE)))
    else:
        if args.qes_source:
            source = args.qes_source.resolve()
            build = args.build_dir or ROOT / "build" / "qes-check"
        else:
            source = export_pristine_qes(args.qes_rev, ROOT / "build" / "qes-reference-src")
            build = args.build_dir or ROOT / "build" / "qes-reference"
        print(f"building qesWinds from {source} in {build}", file=sys.stderr)
        exe = build_qes(source, build, args.jobs)

    provenance = {
        "qes": qes_revision(source),
        "toolchain": toolchain_info(build),
        "solver": "serial CPU (qesWinds -s 1)",
        "generator": "tools/make_reference.py",
    }

    workdir = Path(tempfile.mkdtemp(prefix="qes-ref-"))
    problems: list[str] = []
    try:
        for case in selected:
            arrays, summary = run_case(exe, case, workdir)
            print(f"{case.name}: {summary['iterations']} iterations, "
                  f"max Lagrange multiplier change {summary['max_lagrange_multiplier_change']:.3g}",
                  file=sys.stderr)
            if args.check:
                problems += compare(case.name, arrays, fixtures.reference_path(case), args.rtol, args.atol)
                with open(fixtures.reference_path(case).with_suffix(".json")) as f:
                    stored = json.load(f)["solver_summary"]
                if stored != summary and args.rtol == 0 and args.atol == 0:
                    problems.append(f"{case.name}: solver summary {summary} != stored {stored}")
                continue
            args.output.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(args.output / f"{case.name}.npz", **arrays)
            meta = {"case": case.name, "solver_summary": summary, **provenance}
            (args.output / f"{case.name}.json").write_text(json.dumps(meta, indent=2) + "\n")
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

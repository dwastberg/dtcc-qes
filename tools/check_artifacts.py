"""Verify the licenses and corresponding build sources in release artifacts."""

import argparse
from email.parser import BytesParser
from pathlib import Path
import tarfile
import zipfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_metadata(data):
    metadata = BytesParser().parsebytes(data)
    require(metadata.get("License-Expression") == "GPL-3.0-only", "Missing GPL-3.0-only metadata")
    requirements = metadata.get_all("Requires-Dist", [])
    require(any(item.startswith("dtcc-core") for item in requirements), "Missing DTCC runtime dependency")
    require(any(item.startswith("numpy") for item in requirements), "Missing NumPy runtime dependency")
    require(not any(item.startswith("nanobind") for item in requirements), "nanobind must be build-only")


def check_wheel(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        check_metadata(archive.read(metadata))
        prefix = metadata.rsplit("/", 1)[0] + "/licenses/"
        for name in ("LICENSE", "NOTICE", "QES-Public/LICENSE"):
            require(prefix + name in names, f"Wheel omits {name}")
        require(b"GNU GENERAL PUBLIC LICENSE" in archive.read(prefix + "LICENSE"), "Wrong root license")
        require(b"QES-Winds" in archive.read(prefix + "NOTICE"), "Missing QES attribution")
        require(any(name.startswith("dtcc_qes/_qes.") and name.endswith((".so", ".pyd")) for name in names),
                "Wheel omits native extension")
        for name in ("wind.py", "result.py", "_city.py", "vertical_grid.py", "_auto_grid.py", "comfort.py", "_qes_revision.txt"):
            require("dtcc_qes/" + name in names, f"Wheel omits {name}")
        require(len(archive.read("dtcc_qes/_qes_revision.txt").strip()) == 40, "Missing source revision")


def check_sdist(path):
    with tarfile.open(path) as archive:
        members = {name.split("/", 1)[1]: name for name in archive.getnames() if "/" in name}
        for name in (
            "LICENSE", "NOTICE", "README.md", "pyproject.toml", "uv.lock", "CMakeLists.txt",
            "QES-Public/LICENSE", "QES-Public/CMakeLists.txt", "QES-Public/src/winds/Solver_CPU.cpp",
            "QES-Public/src/winds/Solver_CPU_RB.cpp", "QES-Public/src/winds/Solver_CPU_RB.h",
            "QES-Public/src/winds/CMakeLists.txt", "QES-Public/src/util/CMakeLists.txt",
            "QES-Public/src/qes/Domain.cpp", "QES-Public/cmake/Modules/FindNetCDF.cmake",
            "src/cpp/bindings.cpp", "src/cpp/wind_runner.cpp", "src/cpp/qes_inputs.cpp",
            "src/cpp/divergence.cpp", "src/cpp/divergence.h",
            "src/cpp/stress_validity.h", "tests/native/check_turbulence.cpp",
            "src/cpp/turbulence.h", "src/cpp/turbulence.cpp",
            "tools/check_stress_validity.py",
            "docs/turbulence-reference-differences.md",
            "tests/test_turbulence_reference.py", "tests/fixtures/turbulence_cases.py",
            "src/cpp/precision_solver.cpp", "src/cpp/precision_solver.h", "tests/native/check_precision.cpp",
            "tests/test_precision.py", "tests/test_precision_verification.py", "tools/run_precision_verification.py",
            "tools/audit_precision_verification.py", "tools/plot_precision_verification.py",
            "docs/data/precision-remedy/audit.json", "docs/data/precision-remedy/verification.png",
            "docs/precision-and-horizontal-verification.md",
            "tools/run_joint_grid_verification.py", "tools/audit_joint_grid_verification.py",
            "tools/precompute_joint_checkpoints.py",
            "tools/plot_joint_grid_verification.py", "tests/test_joint_grid_verification.py",
            "docs/joint-grid-verification.md", "docs/data/joint-grid-verification/audit.json",
            "docs/data/joint-grid-verification/execution-environment.json",
            "docs/data/joint-grid-verification/verification.png", "docs/data/joint-grid-verification/figure.json",
            "docs/data/joint-grid-verification/baseline-sources/tools/vertical_grid_study.cpp",
            "docs/data/joint-grid-verification/serial/manifest.json",
            "docs/data/joint-grid-verification/serial/raw.json.gz",
            "docs/data/joint-grid-verification/serial/summary.json",
            "docs/data/joint-grid-verification/openmp/manifest.json",
            "docs/data/joint-grid-verification/openmp/raw.json.gz",
            "docs/data/joint-grid-verification/openmp/summary.json",
            "docs/data/precision-remedy/serial/raw.json.gz", "docs/data/precision-remedy/serial/summary.json",
            "docs/data/precision-remedy/openmp/raw.json.gz", "docs/data/precision-remedy/openmp/summary.json",
            "docs/data/lateral-horizontal-verification/serial/raw.json.gz",
            "docs/data/lateral-horizontal-verification/serial/summary.json",
            "docs/data/lateral-horizontal-verification/openmp/raw.json.gz",
            "docs/data/lateral-horizontal-verification/openmp/summary.json",
            "src/dtcc_qes/vertical_grid.py", "tests/test_vertical_grid.py", "tests/native/check_vertical_grid.cpp",
            "src/dtcc_qes/wind.py", "src/dtcc_qes/_qes_revision.txt", "tests/fixtures/reference/flat.npz",
            "tests/fixtures/reference/one_building.npz", "tests/native/check_physics.cpp",
            "tests/native/check_openmp.cpp", "demo/simple_wind_demo.py", "demo/medium_city.py",
            "tools/check_native_symbols.py", "tools/make_reference.py", "tools/check_artifacts.py",
            "examples/single_building.py", "docs/validation.md", "docs/upstream-license-report.md",
            "docs/milestone1-audit.md", "docs/stagea-validation.md",
            "docs/stageb1-validation.md", "tests/test_sampling.py", "tests/test_grid_preview.py",
            "examples/vertical_grid.py",
            "src/dtcc_qes/_auto_grid.py", "tests/test_auto_grid.py",
            "examples/automatic_vertical_grid.py", "docs/stagec1-validation.md",
            "tools/run_auto_grid_controls.py", "tests/test_auto_grid_controls.py",
            "tools/plot_auto_grid_controls.py", "docs/data/auto-grid-controls/horizontal-sensitivity.png",
            "docs/stagec2-controls.md",
            "docs/data/auto-grid-controls/serial/raw.json.gz",
            "docs/data/auto-grid-controls/serial/summary.json",
            "docs/data/auto-grid-controls/openmp/raw.json.gz",
            "docs/data/auto-grid-controls/openmp/summary.json",
            "tools/run_horizontal_sensitivity.py", "tests/test_horizontal_sensitivity.py",
            "tools/continue_horizontal_sensitivity.py",
            "tools/plot_horizontal_sensitivity.py", "docs/data/horizontal-sensitivity/initialization.png",
            "docs/stagec2b-horizontal-sensitivity.md",
            "docs/data/horizontal-sensitivity/serial/raw.json.gz",
            "docs/data/horizontal-sensitivity/serial/summary.json",
            "docs/data/horizontal-sensitivity/openmp/raw.json.gz",
            "docs/data/horizontal-sensitivity/openmp/summary.json",
            "DYNAMIC_VERTICAL_GRID.md", "docs/vertical-grid-gate.md",
            "docs/data/vertical-grid-gate/raw.json.gz", "docs/data/vertical-grid-gate/summary.json",
            "tools/vertical_grid_study.cpp", "tools/run_vertical_grid_study.py",
            "tools/vertical_grid_diagnostics.cpp", "tools/vertical_grid_diagnostics.h",
            "tools/run_vertical_grid_diagnosis.py", "docs/vertical-grid-diagnosis.md",
            "docs/data/vertical-grid-diagnosis/raw.json.gz",
            "docs/data/vertical-grid-diagnosis/summary.json",
            "tests/test_vertical_grid_study.py",
            "src/dtcc_qes/comfort.py", "tests/test_comfort.py", "examples/wind_comfort.py",
            "docs/wind-comfort.md",
        ):
            require(name in members, f"Source distribution omits {name}")
        shared = ("flat", "flat_oblique", "one_building", "building_oblique", "building_wall")
        for baseline, cases in {
            "upstream": shared,
            "audited": (*shared, "building_thin_wall", "building_nonuniform", "building_nonuniform_wall"),
        }.items():
            for case in cases:
                for suffix in ("npz", "json"):
                    name = f"tests/fixtures/reference/turbulence/{baseline}/{case}.{suffix}"
                    require(name in members, f"Source distribution omits {name}")
        require(not any(name.startswith((".idea/", "build/")) for name in members), "Private build/IDE files in sdist")
        check_metadata(archive.extractfile(members["PKG-INFO"]).read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Artifact paths or directories")
    args = parser.parse_args()
    artifacts = []
    for path in args.paths:
        artifacts.extend(sorted(path.glob("*.whl")) + sorted(path.glob("*.tar.gz")) if path.is_dir() else [path])
    require(bool(artifacts), "No artifacts found")
    for path in artifacts:
        (check_wheel if path.suffix == ".whl" else check_sdist)(path)
        print(f"Artifact check passed: {path.name}")


if __name__ == "__main__":
    main()

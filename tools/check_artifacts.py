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
        for name in ("wind.py", "result.py", "_city.py", "_qes_revision.txt"):
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
            "src/dtcc_qes/wind.py", "src/dtcc_qes/_qes_revision.txt", "tests/fixtures/reference/flat.npz",
            "tests/fixtures/reference/one_building.npz", "tests/native/check_physics.cpp",
            "tests/native/check_openmp.cpp", "demo/simple_wind_demo.py", "demo/medium_city.py",
            "tools/check_native_symbols.py", "tools/make_reference.py", "tools/check_artifacts.py",
            "examples/single_building.py", "docs/validation.md", "docs/upstream-license-report.md",
            "docs/milestone1-audit.md",
        ):
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

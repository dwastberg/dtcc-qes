"""Exercise fresh CMake defaults and intentional serial opt-outs."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    shutil.which("cmake") is None or importlib.util.find_spec("nanobind") is None,
    reason="CMake configuration checks require the native build tools",
)


@pytest.mark.parametrize("mode", [None, "ON", "AUTO", "OFF"])
def test_missing_openmp_requires_explicit_opt_out(tmp_path, mode):
    command = ["cmake", "-S", str(ROOT), "-B", str(tmp_path),
               f"-DPython_EXECUTABLE={Path(sys.executable).absolute()}",
               "-DCMAKE_DISABLE_FIND_PACKAGE_OpenMP=ON"]
    if mode is not None:
        command.append(f"-DDTCC_QES_OPENMP={mode}")
    result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    cache = (tmp_path / "CMakeCache.txt").read_text()
    assert f"DTCC_QES_OPENMP:STRING={mode or 'ON'}" in cache
    if mode in (None, "ON"):
        assert result.returncode != 0
        assert "OpenMP is required by default" in output
        assert "DTCC_QES_OPENMP=OFF" in output
    else:
        assert result.returncode == 0, output
        assert "OpenMP CPU solver: OFF" in output
        if mode == "AUTO":
            assert "explicit AUTO mode selects the serial CPU solver" in output


@pytest.mark.parametrize("mode", ["on", "off"])
def test_contraction_probe_preserves_explicit_compiler_mode(tmp_path, mode):
    import json
    result = subprocess.run(["cmake", "-S", str(ROOT), "-B", str(tmp_path),
        f"-DPython_EXECUTABLE={Path(sys.executable).absolute()}", "-DDTCC_QES_OPENMP=OFF",
        "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        f"-DCMAKE_CXX_FLAGS=-ffp-contract={mode}"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"floating-point contraction: {mode}" in result.stdout
    commands = json.loads((tmp_path/"compile_commands.json").read_text())
    kernels = [c["command"] for c in commands if c["file"].endswith(("cpu_float32.cpp", "cpu_float64.cpp", "/solver/solver.cpp"))]
    assert len(kernels) == 3
    for command in kernels:
        assert command.rsplit("-ffp-contract=", 1)[1].split()[0] == mode

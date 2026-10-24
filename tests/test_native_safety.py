"""Descriptor-level checks include the native executable's shutdown."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NATIVE = Path(os.environ.get("DTCC_QES_NATIVE_TEST", ROOT / "build/extension/check_safety"))


@pytest.mark.parametrize("mode", ["success", "failures", "nonconvergence", "messages"])
def test_native_process_survives_silently(mode):
    if not NATIVE.is_file():
        pytest.skip("Build with DTCC_QES_BUILD_TESTS=ON to run native safety checks")
    result = subprocess.run([str(NATIVE), mode], capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == b""
    assert result.stderr == b""


def test_private_extension_failure_survives_silently():
    script = """
from dtcc_qes import _qes
for shape in [(0, 3, 2), (10000, 10000, 10000)]:
    try:
        _qes._core_grid_shape(*shape)
    except ValueError:
        pass
    else:
        raise AssertionError('Native validation did not reject the input')
assert _qes._core_grid_shape(4, 3, 2) == [4, 3, 2]
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == result.stderr == b""


def test_runner_native_process_survives_silently():
    runner = Path(os.environ.get("DTCC_QES_RUNNER_TEST", NATIVE.with_name("check_runner")))
    if not runner.is_file():
        pytest.skip("Build with DTCC_QES_BUILD_TESTS=ON to run native runner checks")
    result = subprocess.run([str(runner)], capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout == result.stderr == b""

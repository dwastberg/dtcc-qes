"""Unit checks for the native build parity harness (the builds themselves are not run)."""

import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compare_native_builds", ROOT / "tools/compare_native_builds.py")
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def save(path, **values):
    np.savez(path, _module=np.array(str(path)), **values)
    return path


def test_identical_results_ignore_module_path(tmp_path):
    a = save(tmp_path / "a.npz", v=np.arange(4, dtype=np.float32))
    b = save(tmp_path / "b.npz", v=np.arange(4, dtype=np.float32))
    assert harness.compare_results(a, b) == ([], 1)


def test_bit_dtype_shape_and_key_differences_are_reported(tmp_path):
    v = np.array([0.0, 1.0], dtype=np.float32)
    a = save(tmp_path / "a.npz", bits=v, dtype=v, shape=v, only_a=v)
    b = save(tmp_path / "b.npz", bits=np.array([-0.0, 1.0], dtype=np.float32), dtype=v.astype(np.float64),
             shape=v.reshape(2, 1), only_b=v)
    problems, _ = harness.compare_results(a, b)
    assert problems == ["only in one result: only_a", "only in one result: only_b",
                        "differs: bits", "differs: dtype", "differs: shape"]


def test_store_flattens_nested_results():
    out = {}
    harness.store(out, "case", dict(velocity=np.zeros(3), diagnostics=dict(iterations=5), turbulence=None))
    assert set(out) == {"case/velocity", "case/scalars", "case/diagnostics/scalars"}
    assert str(out["case/diagnostics/scalars"]) == '{"iterations": 5}'

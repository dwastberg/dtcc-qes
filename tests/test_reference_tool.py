import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reference_tool", ROOT / "tools/make_reference.py")
reference_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference_tool)


@pytest.mark.parametrize("field", ["x", "dz_array", "icell", "u"])
def test_cross_platform_tolerance_only_relaxes_velocity(field):
    path = ROOT / "tests/fixtures/reference/flat.npz"
    with np.load(path) as stored:
        arrays = {name: stored[name].copy() for name in reference_tool.COMPARED_ARRAYS}
    if field == "icell":
        arrays[field].flat[0] += 1
        tolerance = 2
    else:
        arrays[field].flat[0] += 1e-5
        tolerance = 2e-5
    problems = reference_tool.compare("flat", arrays, path, 0, tolerance)
    assert bool(problems) is (field != "u")

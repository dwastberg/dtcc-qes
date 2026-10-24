from pathlib import Path
import runpy

import numpy as np
import pytest

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def test_self_contained_example():
    example = Path(__file__).resolve().parents[1] / "examples/single_building.py"
    result, grid = runpy.run_path(str(example))["main"]()
    assert result.diagnostics.converged
    assert result.velocity.shape == (20, 30, 40, 3)
    assert np.isfinite(result.velocity).all()
    assert grid.num_cells == 24000 and len(grid.fields) == 3

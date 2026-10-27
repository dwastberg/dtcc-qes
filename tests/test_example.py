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


def test_vertical_grid_preview_and_sampling_example():
    example = Path(__file__).resolve().parents[1] / "examples/vertical_grid.py"
    outputs = runpy.run_path(str(example))["main"]()
    for entry in outputs.values():
        preview, result, sample = (entry[name] for name in ("preview", "result", "pedestrian"))
        assert preview.shape == result.cell_flags.shape
        np.testing.assert_array_equal(preview.z, result.z)
        assert sample.requested_height == sample.sampled_height == 1.5
        assert sample.velocity.shape == (30,40,3)
        assert sample.valid.sum() == 1175
    assert outputs["stretched"]["preview"].cell_count < outputs["uniform"]["preview"].cell_count


def test_automatic_vertical_grid_example():
    example = Path(__file__).resolve().parents[1] / "examples/automatic_vertical_grid.py"
    preview, result, sample = runpy.run_path(str(example))["main"]()
    np.testing.assert_array_equal(preview.z_faces,result.z_faces)
    assert preview.shape == result.cell_flags.shape
    assert preview.domain["vertical_grid"]["policy_status"] == "prototype_unvalidated"
    assert sample.sampled_height == 1.5 and sample.valid.sum() == 1175


def test_wind_comfort_example():
    example = Path(__file__).resolve().parents[1] / "examples/wind_comfort.py"
    nen, london = runpy.run_path(str(example))["main"]()
    for result in (nen, london):
        assert result.comfort.shape == result.safety.shape == (30, 40)
        assert (result.comfort == -1).sum() == 25  # the 10 m x 10 m building at 2 m spacing
        assert len(np.unique(result.comfort[result.comfort >= 0])) > 1
        assert result.metadata["hours"] == 8760 and result.metadata["field_height"] == 1.5
    assert set(london.seasonal) == {"winter", "spring", "summer", "autumn"}
    assert any("Mean speeds only" in warning for warning in london.warnings)
    assert any("1.75 m" in warning for warning in nen.warnings)

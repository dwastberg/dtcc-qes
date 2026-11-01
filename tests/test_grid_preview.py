"""Preview uses the solve preparation path without allocating flow arrays."""
import json
import math
import tracemalloc

import numpy as np
import pytest

from dtcc_core.model import City
from dtcc_qes import _qes, wind
from fixtures.cities import city_case
from fixtures.cases import ONE_BUILDING

pytestmark = pytest.mark.usefixtures("dtcc_logger")


@pytest.mark.parametrize("resolution,faces", [
    (2, None), (0.3, None), (2, [0,0.5,2,2.5,5,8,12]),
    (0.3, np.linspace(0,12,121)),
])
def test_preview_matches_native_effective_coordinates_and_metadata(resolution, faces):
    options = dict(resolution=resolution, bounds=(0,0,0,9,11,12))
    if faces is not None:
        options["vertical_grid"] = wind.VerticalGrid.from_faces(faces)
    preview = wind.preview_grid(City(), speed=5, direction=270, **options)
    result = wind.run(City(), speed=5, direction=270, **options)
    for name in ("x", "y", "z", "z_faces", "dz"):
        np.testing.assert_array_equal(getattr(preview,name), getattr(result,name))
    assert preview.shape == result.cell_flags.shape
    assert preview.cell_count == result.cell_flags.size
    assert preview.domain == result.metadata["domain"]
    assert preview.terrain == result.metadata["terrain"]
    assert preview.origin == result.origin and preview.resolution == result.resolution
    record = preview.domain["vertical_grid"]
    assert float(preview.growth_ratios.max()) == record["max_growth_ratio"]
    assert float(preview.thin_cell_aspect_ratios.max()) == record["max_thin_cell_aspect_ratio"]
    assert float(preview.tall_cell_aspect_ratios.max()) == record["max_tall_cell_aspect_ratio"]
    json.dumps(preview.domain, allow_nan=False)


def test_translated_city_and_roof_diagnostics_match_solve_without_mutation():
    city, condition, grid, _ = city_case(ONE_BUILDING, (1e9,-2e9,100))
    city.transform.srs = "EPSG:3006"
    vertices = city.buildings[0].lod0.vertices.copy()
    spec = wind.VerticalGrid.from_faces(np.r_[np.arange(0,10,0.5), np.arange(10,42,2)])
    preview = wind.preview_grid(city, **condition, **grid, vertical_grid=spec)
    result = wind.run(city, **condition, **grid, vertical_grid=spec)
    assert preview.domain == result.metadata["domain"]
    assert preview.origin == (1e9,-2e9,100) and preview.crs == "EPSG:3006"
    roof, = preview.domain["vertical_grid"]["roof_representation"]
    assert roof["source_id"] == "0" and roof["represented_height"] == 8
    np.testing.assert_array_equal(vertices, city.buildings[0].lod0.vertices)
    preview.z_faces[:] = -1
    preview.domain["vertical_grid"]["requested_faces"][1] = -1
    assert result.z_faces[0] == 0 and spec.faces[1] == 0.5


def test_automatic_bounds_share_clearance_and_origin_with_solve():
    city, condition, _, _ = city_case(ONE_BUILDING)
    profile = wind.LogProfile(5,270,reference_height=50)
    preview = wind.preview_grid(city, profile, vertical_clearance=35)
    result = wind.run(city, vertical_clearance=35, profile=profile)
    assert preview.domain == result.metadata["domain"]
    np.testing.assert_array_equal(preview.z_faces,result.z_faces)


def test_large_preview_allocates_only_axes_and_geometry(monkeypatch):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Preview allocated native flow fields"))
    tracemalloc.start()
    try:
        preview = wind.preview_grid(City(), resolution=2, bounds=(0,0,0,20000,20000,4),
                                    max_cells=200_000_000)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert preview.shape == (2,10000,10000) and preview.cell_count == 200_000_000
    assert peak < 3_000_000


def test_rounding_across_coefficient_limit_is_rejected_by_both_paths(monkeypatch):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Unexpected flow allocation"))
    # Valid in float64, but rounding r to float32 makes 1/(r*r) overflow.
    resolution = math.sqrt(1/float(np.finfo(np.float32).max))
    options = dict(resolution=resolution, bounds=(0,0,0,4*resolution,4*resolution,2*resolution))
    for operation in (lambda: wind.preview_grid(City(), speed=5, direction=270, **options),
                      lambda: wind.run(City(), speed=5, direction=270, **options)):
        with pytest.raises(ValueError, match="float32 solver coefficients"):
            operation()


@pytest.mark.parametrize("options,message", [
    ({"max_cells": 100}, "max_cells"),
    ({"bounds": (0,0,0,20002,10,10)}, "10000"),
    ({"resolution": 0}, "resolution"),
    ({"terrain": np.inf}, "terrain"),
    ({"vertical_grid": [0,1,40]}, "vertical_grid"),
    ({"vertical_grid": wind.VerticalGrid.from_faces([0,1,39])}, "top must match"),
])
def test_preview_and_run_reject_same_options_before_flow_allocation(monkeypatch, options, message):
    monkeypatch.setattr(_qes, "WindRunner", lambda: pytest.fail("Unexpected flow allocation"))
    city, condition, grid, _ = city_case(ONE_BUILDING)
    with pytest.raises(ValueError, match=message):
        wind.preview_grid(city, **(grid | options))
    with pytest.raises(ValueError, match=message):
        wind.run(city, **(condition | grid | options))

from dataclasses import replace

import numpy as np
import pytest
from dtcc_qes import wind

from city_cases import city_case
from fixtures.cases import ONE_BUILDING

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def test_volume_grid_preserves_frame_units_and_independent_fields():
    city, condition, grid, _ = city_case(ONE_BUILDING, (1e9, -2e9, 100))
    city.transform.srs = "EPSG:3006"
    result = wind.run(city, condition, grid=grid)
    converted = result.to_dtcc()
    assert (converted.width, converted.height, converted.depth) == (40, 30, 20)
    assert (converted.xstep, converted.ystep, converted.zstep) == (2, 2, 2)
    assert converted.transform.srs == "EPSG:3006"
    np.testing.assert_array_equal(converted.transform.offset, result.origin)
    fields = {field.name: field for field in converted.fields}
    assert set(fields) == {"velocity", "speed", "cell_flags"}
    for name, field in fields.items():
        assert field.association == "cell"
        assert field.values.shape == ((converted.num_cells, 3) if name == "velocity" else (converted.num_cells,))
        assert field.unit == ("1" if name == "cell_flags" else "m/s")
    expected_speed = np.hypot.reduce(fields["velocity"].values.astype(np.float64), axis=1)
    np.testing.assert_allclose(fields["speed"].values, expected_speed, rtol=1e-14, atol=1e-14)
    assert not np.shares_memory(fields["velocity"].values, result.velocity)
    assert not np.shares_memory(fields["cell_flags"].values, result.cell_flags)
    assert np.any(result.solid_mask)
    np.testing.assert_array_equal(result.solid_mask, result.cell_flags == 0)


def test_cell_order_uses_y_x_z_fastest_on_unequal_axes():
    # Encode axis indices into distinguishable values rather than relying on
    # a symmetric physical field to expose a transposition error.
    nz, ny, nx = 2, 4, 3
    z, y, x = np.indices((nz, ny, nx))
    values = (100 * z + 10 * y + x).astype(np.float32)
    velocity = np.stack((values, values + 1000, values + 2000), axis=-1)
    result = wind.WindResult(velocity, np.arange(nx) + 0.5, np.arange(ny) + 0.5,
                             np.arange(nz) + 0.5, values.astype(np.int32), (10, 20, 30), None, 1,
                             wind.SolveDiagnostics(1, 0, 1e-5, True), {})
    converted = result.to_dtcc()
    fields = {field.name: field.values for field in converted.fields}
    centres = np.array(np.meshgrid(result.x, result.y, result.z)).reshape(3, -1).T
    expected = np.array([100 * int(z) + 10 * int(y) + int(x) for x, y, z in centres])
    np.testing.assert_array_equal(fields["velocity"][:, 0], expected)
    np.testing.assert_array_equal(fields["cell_flags"], expected)
    np.testing.assert_array_equal(fields["velocity"][:, 1], expected + 1000)
    for index, (x, y, z) in enumerate(centres):
        corner_index = (int(y) * (nx + 1) + int(x)) * (nz + 1) + int(z)
        np.testing.assert_array_equal(converted.coordinates()[corner_index] + 0.5, (x, y, z))


def test_solid_mask_excludes_air_parameterizations():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    result = wind.run(city, condition, grid=grid)
    flags = np.array([[[0, 1, 2, 3, 4, 5, 7, 8]]], dtype=np.int32)
    result = replace(result, cell_flags=flags)
    np.testing.assert_array_equal(result.solid_mask, [[[True, False, True, False, False, False, False, False]]])

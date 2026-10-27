from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from dtcc_qes import _qes, wind
from dtcc_qes.vertical_grid import effective_faces
from city_cases import city_case
from fixtures.cases import FLAT, ONE_BUILDING
from runner_cases import inputs

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def stretched_faces():
    return np.r_[np.arange(0, 10, 0.5), np.arange(10, 20), np.arange(20, 42, 2)]


def test_specification_owns_immutable_requested_coordinates():
    faces = stretched_faces()
    spec = wind.VerticalGrid.from_faces(faces)
    saved = spec.faces
    faces[:] = -1
    assert spec.faces == saved
    with pytest.raises(FrozenInstanceError):
        spec.faces = (0, 1, 2)
    layers = spec.layers
    layers[:] = 99
    assert spec.layers[0] == 0.5


@pytest.mark.parametrize("faces", [[], [0, 1], [1, 2, 3], [0, 0, 1], [0, 2, 1],
    [0, 1, np.nan], [0, 1, np.inf], [[0, 1, 2]], [False, True, True], ["0", "1", "2"],
    [0, 1e-50, 1], [0, 1e8, 1e8 + 1], [0, 1e30, 2e30], list(range(10002))])
def test_invalid_face_sequences_rejected(faces):
    with pytest.raises(ValueError):
        wind.VerticalGrid.from_faces(faces)


def test_explicit_equal_layers_match_uniform_solver_bitwise():
    city, condition, grid, _ = city_case(ONE_BUILDING)
    legacy = wind.run(city, **condition, **grid)
    explicit = wind.run(city, **condition, **grid,
                        vertical_grid=wind.VerticalGrid.from_faces(np.arange(0, 42, 2)))
    for name in ("x", "y", "z", "z_faces", "velocity", "cell_flags"):
        np.testing.assert_array_equal(getattr(explicit, name), getattr(legacy, name))
    assert explicit.diagnostics == legacy.diagnostics
    assert explicit.vertical_uniform
    assert explicit.to_dtcc().zstep == 2


@pytest.mark.parametrize("resolution", [1.0, 2.0])
@pytest.mark.parametrize("direction,component,sign", [(0, 1, -1), (90, 0, -1), (180, 1, 1), (270, 0, 1)])
def test_flat_log_profile_uses_effective_centres(resolution, direction, component, sign):
    city, condition, grid, _ = city_case(FLAT)
    faces = stretched_faces()
    result = wind.run(city, speed=5, direction=direction, resolution=resolution,
                      bounds=grid["bounds"], vertical_grid=wind.VerticalGrid.from_faces(faces))
    expected_faces = effective_faces(np.diff(faces))
    np.testing.assert_array_equal(result.z_faces, expected_faces)
    np.testing.assert_array_equal(result.z, np.float32(0.5) * (expected_faces[:-1] + expected_faces[1:]))
    speed = 5 * np.log((result.z.astype(float) + 0.1) / 0.1) / np.log(10.1 / 0.1)
    np.testing.assert_allclose(result.velocity[..., component],
                               np.broadcast_to(sign * speed[:, None, None], result.velocity.shape[:-1]),
                               rtol=2e-6, atol=2e-6)
    assert result.diagnostics.max_divergence == 0
    assert not result.vertical_uniform
    with pytest.raises(ValueError, match="Nonuniform"):
        result.to_dtcc()
    assert result.metadata["domain"]["local_bounds"][-1] == float(expected_faces[-1])


@pytest.mark.parametrize("height", [7.99, 8.0, 8.25, 8.5])
def test_building_occupancy_uses_layer_centres(height):
    city, condition, grid, _ = city_case(ONE_BUILDING)
    city.buildings[0].measured_height = height
    result = wind.run(city, **condition, **grid, max_iterations=2000,
                      vertical_grid=wind.VerticalGrid.from_faces(stretched_faces()))
    z, y, x = np.meshgrid(result.z, result.y, result.x, indexing="ij")
    expected = (x >= 30) & (x < 40) & (y >= 25) & (y < 35) & (z <= np.float32(height))
    np.testing.assert_array_equal(result.solid_mask, expected)
    np.testing.assert_array_equal(result.velocity[expected], 0)
    assert np.isfinite(result.velocity).all()
    assert result.diagnostics.max_divergence < 3e-4
    roof = result.metadata["domain"]["vertical_grid"]["roof_representation"][0]
    assert roof["represented_height"] == result.z_faces[np.searchsorted(result.z, np.float32(height), side="right")]


def test_uniform_anisotropic_grid_exports_true_z_extent():
    city, condition, grid, _ = city_case(FLAT)
    result = wind.run(city, **condition, **grid,
                      vertical_grid=wind.VerticalGrid.from_faces(np.arange(0, 40.5, 0.5)))
    assert result.vertical_uniform
    converted = result.to_dtcc()
    assert (converted.xstep, converted.ystep, converted.zstep) == (2, 2, 0.5)
    assert converted.bounds.zmax == result.z_faces[-1] == 40


def test_decimal_uniform_layers_preserve_actual_faces_and_uniformity():
    city, condition, grid, _ = city_case(FLAT)
    requested = np.linspace(0, 40, 401)
    result = wind.run(city, **condition, **grid, vertical_grid=wind.VerticalGrid.from_faces(requested))
    np.testing.assert_array_equal(result.z_faces, effective_faces(np.diff(requested)))
    assert result.vertical_uniform
    assert result.metadata["domain"]["effective_bounds"][-1] == float(result.z_faces[-1])
    assert result.to_dtcc().bounds.zmax == float(result.z_faces[-1])


def test_nonmonotonic_layer_thicknesses_are_valid_explicit_input():
    city, condition, grid, _ = city_case(FLAT)
    spec = wind.VerticalGrid.from_faces([0, 0.5, 2, 2.5, 10, 20, 40])
    result = wind.run(city, **condition, **grid, vertical_grid=spec)
    assert not result.vertical_uniform
    assert result.diagnostics.max_divergence == 0


def test_explicit_top_is_checked_before_coordinate_rounding():
    city, condition, grid, _ = city_case(FLAT)
    for top in (39.0, 41.0):
        with pytest.raises(ValueError, match="top must match"):
            wind.run(city, **condition, **grid,
                     vertical_grid=wind.VerticalGrid.from_faces([0, 1, top]))
    with pytest.raises(ValueError, match="vertical_grid"):
        wind.run(city, **condition, **grid, vertical_grid=[0, 1, 40])


def test_automatic_bounds_accept_explicit_top_only_with_clearance():
    city, condition, _, _ = city_case(ONE_BUILDING)
    with pytest.raises(ValueError, match="required clearance"):
        wind.run(city, **condition, vertical_grid=wind.VerticalGrid.from_faces([0, 1, 20]))
    result = wind.run(city, **condition, vertical_grid=wind.VerticalGrid.from_faces(stretched_faces()))
    assert result.metadata["domain"]["effective_bounds"][-1] == 40


def test_translated_explicit_coordinates_and_allocation_limit():
    first_city, condition, grid, _ = city_case(ONE_BUILDING)
    city, moved_condition, moved_grid, _ = city_case(ONE_BUILDING, (1e9, -2e9, 100))
    spec = wind.VerticalGrid.from_faces(stretched_faces())
    first = wind.run(first_city, **condition, **grid, vertical_grid=spec)
    second = wind.run(city, **moved_condition, **moved_grid, vertical_grid=spec)
    np.testing.assert_array_equal(first.velocity, second.velocity)
    np.testing.assert_array_equal(first.z_faces, second.z_faces)
    assert second.origin[2] == 100
    with pytest.raises(ValueError, match="max_cells"):
        wind.run(first_city, **condition, **grid, vertical_grid=spec, max_cells=30000)


def test_native_layers_are_snapshotted_and_owned():
    grid, model, condition, solver, arrays = inputs(ONE_BUILDING)
    layers = np.ascontiguousarray(np.diff(stretched_faces()), dtype=np.float64)
    grid.nz = len(layers)
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays, dz_layers=layers)
    layers[:] = np.nan
    first = runner.solve(condition, solver)
    saved = first["z_faces"].copy()
    first["z_faces"][:] = -1
    second = runner.solve(condition, solver)
    del runner
    np.testing.assert_array_equal(second["z_faces"], saved)
    assert second["z_faces"].flags.owndata
    assert second["z_faces"].dtype == np.float32


@pytest.mark.parametrize("layers", [np.array([1, 2], dtype=float), np.full(20, np.nan),
    np.full(20, -1.0), np.full(20, 1e-100), np.r_[1e8, np.ones(19)], np.full(20, 1e30)])
def test_native_bad_layers_preserve_prepared_state(layers):
    grid, model, condition, solver, arrays = inputs(FLAT)
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays)
    baseline = runner.solve(condition, solver)
    with pytest.raises(ValueError):
        runner.prepare(grid, model, **arrays, dz_layers=layers)
    np.testing.assert_array_equal(runner.solve(condition, solver)["velocity"], baseline["velocity"])


@pytest.mark.parametrize("layers", [np.ones(20, dtype=np.float32), [1.0] * 20, np.ones((20, 1))])
def test_native_layers_require_contiguous_float64_vector(layers):
    grid, model, _, _, arrays = inputs(FLAT)
    with pytest.raises(TypeError):
        _qes.WindRunner().prepare(grid, model, **arrays, dz_layers=layers)


def test_none_and_empty_native_layers_keep_uniform_path():
    grid, model, condition, solver, arrays = inputs(FLAT)
    runner = _qes.WindRunner()
    snapshots = []
    for layers in (None, np.array([], dtype=np.float64), np.full(grid.nz, grid.cell_size)):
        runner.prepare(grid, model, **arrays, dz_layers=layers)
        snapshots.append(runner.solve(condition, solver))
    for result in snapshots[1:]:
        np.testing.assert_array_equal(result["velocity"], snapshots[0]["velocity"])
        np.testing.assert_array_equal(result["z_faces"], snapshots[0]["z_faces"])

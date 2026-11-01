"""Probe interpolation, coordinates and contributor masks on manufactured fields."""

from dataclasses import replace
import tracemalloc

import numpy as np
import pytest

from dtcc_qes import wind
from fixtures.sampling import manufactured


def with_stress(result):
    shape = result.cell_flags.shape
    stress = np.empty((*shape, 6), dtype=np.float32)
    stress[:] = [4, 0, 0, 2, 0, 1]
    return replace(result, turbulence=wind.TurbulenceFields(
        stress=stress, tke=np.ones(shape), co_eps=np.ones(shape), mixing_length=np.ones(shape),
        computed=np.ones(shape, dtype=bool), capped=np.zeros(shape, dtype=bool),
        stress_valid=np.ones(shape, dtype=bool), friction_velocity=1, reference_speed=5,
        reference_height=10, roughness_length=.1, displacement_height=0))


def test_trilinear_nonuniform_grid_reproduces_multiaffine_components_in_probe_order():
    result = manufactured()

    def field(x, y, z):
        return np.stack((x*y*z + 2*x - z, x*z - 3*y, 2*y*z - x*y), axis=-1)

    z, y, x = np.meshgrid(result.z, result.y, result.x, indexing="ij")
    result.velocity[:] = field(x, y, z)
    points = np.array([[3.2, 2.1, 3.5], [.6, .7, .4], [1.25, 1.75, 1.5]])
    sample = result.sample_points(points, "linear")
    assert isinstance(sample, wind.WindPointSample)
    np.testing.assert_allclose(sample.velocity, field(*points.T), rtol=2e-15, atol=2e-15)
    np.testing.assert_allclose(sample.speed, np.linalg.norm(field(*points.T), axis=-1))
    np.testing.assert_array_equal(sample.points, points)
    np.testing.assert_array_equal(sample.sampled_points, points)
    assert sample.valid.all() and sample.valid.dtype == bool
    assert sample.velocity.dtype == sample.points.dtype == np.float64
    assert sample.method == "linear" and sample.frame == "local"
    assert sample.origin == result.origin and sample.crs == result.crs


def test_nearest_ties_and_physical_faces():
    result = manufactured()
    points = [[0, 0, 0], [4, 3, 7.25], [1, 2, 1.3125]]
    sample = result.sample_points(points)
    np.testing.assert_array_equal(sample.velocity,
                                 result.velocity[[0, 4, 1], [0, 2, 1], [0, 3, 0]])
    np.testing.assert_array_equal(sample.sampled_points,
                                 [[.5, .5, .25], [3.5, 2.5, 5.75], [.5, 1.5, .875]])
    assert sample.valid.all() and sample.method == "nearest"


@pytest.mark.parametrize("method", ["nearest", "linear"])
def test_global_probes_use_all_three_origin_components(method):
    result = manufactured()
    points = np.array([[.5, 1.5, .875], [3, 2, 3], [1.5, .5, 1.75]])
    global_points = points + np.asarray(result.origin, dtype=np.float64)
    local = result.sample_points(points, method)
    sample = result.sample_points(global_points, method, frame="global")
    np.testing.assert_array_equal(sample.velocity, local.velocity)
    np.testing.assert_array_equal(sample.points, global_points)
    np.testing.assert_array_equal(sample.sampled_points, local.sampled_points + result.origin)
    assert sample.frame == "global" and sample.origin == result.origin


@pytest.mark.parametrize("method", ["nearest", "linear"])
def test_outside_physical_domain_masks_individual_rows(method):
    points = np.array([[1.5, 1.5, 1.75], [-.01, 1, 1], [4.01, 1, 1],
                       [1, -.01, 1], [1, 3.01, 1], [1, 1, -.01], [1, 1, 7.26]])
    sample = with_stress(manufactured()).sample_points(points, method)
    np.testing.assert_array_equal(sample.valid, [True, False, False, False, False, False, False])
    assert np.isnan(sample.velocity[1:]).all() and np.isnan(sample.speed[1:]).all()
    assert np.isnan(sample.sampled_points[1:]).all() and np.isnan(sample.stress[1:]).all()
    assert not sample.stress_valid[1:].any()


@pytest.mark.parametrize("dim", range(3))
def test_linear_does_not_extrapolate_beyond_centres(dim):
    result = manufactured()
    points = np.tile([1.5, 1.5, 1.75], (2, 1))
    axis = (result.x, result.y, result.z)[dim]
    points[:, dim] = [np.nextafter(float(axis[0]), -np.inf),
                      np.nextafter(float(axis[-1]), np.inf)]
    sample = result.sample_points(points, "linear")
    assert not sample.valid.any() and np.isnan(sample.sampled_points).all()
    assert result.sample_points(points).valid.all()


@pytest.mark.parametrize("method", ["nearest", "linear"])
def test_points_at_native_xy_centres_match_existing_plane_sampler(method):
    result = with_stress(manufactured())
    result.velocity[2, 1, 2] = np.inf
    result.cell_flags[1, 0, 0] = 0
    result.turbulence.computed[1, 2, 3] = False
    x, y = np.meshgrid(result.x, result.y)
    points = np.column_stack((x.ravel(), y.ravel(), np.full(x.size, 1.5)))
    probes = result.sample_points(points, method)
    plane = result.sample(1.5, method)
    for name in ("velocity", "valid", "stress", "stress_valid", "streamwise_std", "turbulence_intensity"):
        expected = getattr(plane, name)
        actual = getattr(probes, name).reshape(expected.shape)
        np.testing.assert_allclose(actual, expected, rtol=2e-15, equal_nan=True)


@pytest.mark.parametrize("corner", list(np.ndindex(2, 2, 2)))
@pytest.mark.parametrize("bad", [0, 2, np.nan, np.inf])
def test_every_trilinear_contributor_must_be_fluid_and_finite(corner, bad):
    result = manufactured()
    if np.isfinite(bad):
        result.cell_flags[corner] = bad
    else:
        result.velocity[corner] = bad
    sample = result.sample_points([[1, 1, .5], [3, 2, 3]], "linear")
    np.testing.assert_array_equal(sample.valid, [False, True])
    assert np.isnan(sample.velocity[0]).all()
    assert np.isfinite(sample.sampled_points[0]).all()


@pytest.mark.parametrize("dim", range(3))
def test_exact_coordinate_ignores_neighbour_but_float64_nearby_point_includes_it(dim):
    result = manufactured()
    point = np.array([1.5, 1.5, 1.75])
    bad_index = [2, 1, 1]  # z, y, x indices of the exact point
    bad_index[2 - dim] += 1
    result.cell_flags[tuple(bad_index)] = 2
    result.velocity[tuple(bad_index)] = np.nan
    assert result.sample_points([point], "linear").valid[0]
    point[dim] = np.nextafter(point[dim], np.inf)
    assert not result.sample_points([point], "linear").valid[0]


def test_interpolate_vectors_before_speed():
    result = manufactured()
    result.velocity[:, :, 0] = [5, 0, 0]
    result.velocity[:, :, 1] = [-5, 0, 0]
    sample = result.sample_points([[1, 1, 1.5]], "linear")
    np.testing.assert_array_equal(sample.speed, 0)


def test_stress_preserves_invalid_contributors_and_rechecks_edits():
    result = with_stress(manufactured())
    result.velocity[:] = [1, 0, 0]
    result.turbulence.stress[:, :, 0] = [1, 2, 0, 1, 0, 1]
    result.turbulence.stress[:, :, 1] = [3, -2, 0, 3, 0, 3]
    # A stale public source mask must not conceal an indefinite tensor.
    result.turbulence.stress_valid[:] = True
    sample = result.sample_points([[1, 1, 1.5], [2.5, 1, 1.5]], "linear")
    np.testing.assert_array_equal(sample.stress[0], [2, 0, 0, 2, 0, 2])
    np.testing.assert_array_equal(sample.stress_valid, [False, True])
    assert np.isnan(sample.streamwise_std[0]) and sample.streamwise_std[1] == 2
    sample.stress_valid[:] = True
    sample.stress[:] = [4, 0, 0, 2, 0, 1]
    assert np.isnan(sample.streamwise_std[0]) and sample.streamwise_std[1] == 2
    sample.stress[1] = [1, 2, 0, 1, 0, 1]
    assert np.isnan(sample.streamwise_std).all()


def test_uncomputed_stress_and_undefined_direction():
    result = with_stress(manufactured())
    result.turbulence.computed[0, 0, 0] = False
    result.velocity[:] = 0
    sample = result.sample_points([[1, 1, .5], [3, 2, 3]], "linear")
    assert sample.valid.all() and np.isnan(sample.stress[0]).all()
    np.testing.assert_array_equal(sample.stress_valid, [False, True])
    assert np.isnan(sample.streamwise_std).all() and np.isnan(sample.turbulence_intensity).all()


@pytest.mark.parametrize("method", ["nearest", "linear"])
def test_empty_probes_and_singleton_axes(method):
    result = with_stress(manufactured())
    empty = result.sample_points(np.empty((0, 3)), method)
    assert empty.velocity.shape == empty.points.shape == empty.sampled_points.shape == (0, 3)
    assert empty.valid.shape == empty.streamwise_std.shape == (0,)
    assert empty.stress.shape == (0, 6)
    result = replace(result, velocity=result.velocity[:1, :1, :1], x=result.x[:1], y=result.y[:1],
                     z=result.z[:1], cell_flags=result.cell_flags[:1, :1, :1],
                     z_faces=result.z_faces[:2], turbulence=None)
    assert result.sample_points([[.5, .5, .25]], method).valid.all()
    assert result.sample_points([[0, 0, 0]], method).valid[0] == (method == "nearest")


def test_legacy_result_without_faces():
    result = replace(manufactured(), z=np.arange(5, dtype=np.float32) + .5, z_faces=None)
    sample = result.sample_points([[1, 1, 5], [1, 1, 5.01]])
    np.testing.assert_array_equal(sample.valid, [True, False])


@pytest.mark.usefixtures("dtcc_logger")
def test_native_decimal_spacing_uses_physical_faces_and_global_elevation():
    from dtcc_core.model import City

    result = wind.run(City(), speed=5, direction=270, resolution=.3,
                      bounds=(1e9, -2e9, 100, 1e9 + 1.5, -2e9 + 1.5, 132),
                      solver=wind.Solver(max_iterations=1))
    top = float(result.z_faces[-1])
    xmax, ymax = np.asarray(result.metadata["domain"]["local_bounds"])[3:5]
    points = np.array([[0, 0, 0], [xmax, ymax, top]])
    sample = result.sample_points(points)
    assert sample.valid.all()
    np.testing.assert_array_equal(sample.velocity,
                                 result.velocity[[0, -1], [0, -1], [0, -1]])
    centre = np.array([[float(result.x[1]), float(result.y[1]), float(result.z[1])]])
    # Exact represented global centres must use only their own cell.
    global_points = centre + result.origin
    global_sample = result.sample_points(global_points, "linear", frame="global")
    assert global_sample.valid.all()
    np.testing.assert_array_equal(global_sample.velocity, result.velocity[1, 1, 1][None])
    np.testing.assert_array_equal(global_sample.sampled_points, global_points)


@pytest.mark.parametrize("change, message", [
    ({"velocity": np.zeros((1, 1, 1, 3))}, "Velocity"),
    ({"cell_flags": np.ones((1, 1, 1))}, "cell flags"),
    ({"resolution": 0}, "resolution"),
    ({"resolution": np.nan}, "resolution"),
    ({"z_faces": np.arange(5)}, "z_faces"),
    ({"z_faces": np.array([0, 1, 1, 2, 3, 4])}, "z_faces"),
    ({"z_faces": np.array([1, 2, 3, 4, 5, 6])}, "z_faces"),
])
def test_malformed_result_rejected(change, message):
    with pytest.raises(ValueError, match=message):
        replace(manufactured(), **change).sample_points([[1, 1, 1]])


def test_malformed_turbulence_rejected():
    result = with_stress(manufactured())
    result = replace(result, turbulence=replace(result.turbulence, computed=np.ones((1, 1, 1))))
    with pytest.raises(ValueError, match="Turbulence"):
        result.sample_points([[1, 1, 1]])


@pytest.mark.parametrize("points", [None, [], [1, 2, 3], [[1, 2]], [[[1, 2, 3]]],
    [[True, False, True]], [["1", "2", "3"]], [[1+1j, 2, 3]], [[1, None, 3]],
    [[1, 2, np.nan]], [[1, np.inf, 3]], [[10**1000, 2, 3]], [[1, 2, 3], [1]]])
def test_malformed_points_rejected(points):
    with pytest.raises(ValueError, match="points"):
        manufactured().sample_points(points)


@pytest.mark.parametrize("method", ["cubic", None, [], np.array(["linear"])])
def test_bad_method(method):
    with pytest.raises(ValueError, match="method"):
        manufactured().sample_points([[1, 1, 1]], method)


@pytest.mark.parametrize("frame", ["world", None, [], np.array(["local"])])
def test_bad_frame(frame):
    with pytest.raises(ValueError, match="frame"):
        manufactured().sample_points([[1, 1, 1]], frame=frame)


@pytest.mark.parametrize("axis", ["x", "y", "z"])
@pytest.mark.parametrize("values", [[], [1, 1], [2, 1], [0, np.nan]])
def test_malformed_axes_rejected(axis, values):
    result = replace(manufactured(), **{axis: np.asarray(values)})
    with pytest.raises(ValueError, match=axis):
        result.sample_points([[1, 1, 1]])


def test_owned_arrays_and_no_turbulence():
    result = with_stress(manufactured())
    points = np.array([[1., 1., 1.]])
    sample = result.sample_points(points, "linear")
    for array in (sample.points, sample.sampled_points, sample.velocity, sample.valid,
                  sample.stress, sample.stress_valid):
        assert array.flags.owndata
        for original in (points, result.velocity, result.cell_flags, result.turbulence.stress):
            assert not np.shares_memory(array, original)
    sample.points[:] = -1
    np.testing.assert_array_equal(points, [[1, 1, 1]])
    plain = manufactured().sample_points(points)
    assert plain.stress is None and plain.stress_valid is None
    with pytest.raises(ValueError, match="turbulence"):
        _ = plain.streamwise_std


def test_probe_sampling_memory_does_not_scale_with_volume():
    result = manufactured()
    shape = (9000, 64, 64)
    result = replace(result, x=np.arange(64) + .5, y=np.arange(64) + .5,
        z=np.arange(9000, dtype=np.float32) + .5, z_faces=np.arange(9001, dtype=np.float32),
        velocity=np.broadcast_to(np.ones(3, dtype=np.float32), (*shape, 3)),
        cell_flags=np.broadcast_to(np.int32(1), shape))
    tracemalloc.start()
    try:
        sample = result.sample_points([[1, 1, 1], [30, 40, 8000]], "linear")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert sample.valid.all() and peak < 3_000_000


def decimal_grid():
    result = manufactured()
    # Keep the same float32 spacing and centre construction as the native grid.
    spacing = np.float32(.3)
    return replace(result, resolution=spacing,
                   x=(np.arange(len(result.x), dtype=np.float32) + np.float32(.5))*spacing,
                   y=(np.arange(len(result.y), dtype=np.float32) + np.float32(.5))*spacing)


@pytest.mark.parametrize("frame", ["local", "global"])
def test_decimal_physical_faces_are_inclusive_but_adjacent_float64_positions_are_outside(frame):
    result = decimal_grid()
    lo = np.zeros(3)
    hi = np.array([len(result.x)*float(result.resolution), len(result.y)*float(result.resolution),
                   float(result.z_faces[-1])])
    if frame == "global":
        lo += result.origin
        hi += result.origin
    faces = []
    outside = []
    for dim in range(3):
        for boundary, direction in ((lo, -np.inf), (hi, np.inf)):
            point = (lo + hi)/2
            point[dim] = boundary[dim]
            faces.append(point.copy())
            point[dim] = np.nextafter(point[dim], direction)
            outside.append(point)
    sample = result.sample_points(faces + outside, frame=frame)
    np.testing.assert_array_equal(sample.valid, [True]*6 + [False]*6)
    assert np.isnan(sample.velocity[6:]).all() and np.isnan(sample.sampled_points[6:]).all()


@pytest.mark.parametrize("dim", range(3))
@pytest.mark.parametrize("index", [0, -1])
def test_global_linear_endpoint_centres_ignore_neighbours_without_snapping_nearby_requests(dim, index):
    result = decimal_grid()
    axis = (result.x, result.y, result.z)[dim]
    point = np.array([float(result.x[1]), float(result.y[1]), float(result.z[1])])
    point[dim] = float(axis[index])
    cell = [1, 1, 1]
    cell[2 - dim] = index
    selected = result.velocity[tuple(cell)].copy()
    # All neighbouring cells must be irrelevant to an exact endpoint centre.
    result.cell_flags[:] = 2
    result.cell_flags[tuple(cell)] = 1
    global_point = point + result.origin
    inward = global_point.copy()
    inward[dim] = np.nextafter(inward[dim], np.inf if index == 0 else -np.inf)
    outward = global_point.copy()
    outward[dim] = np.nextafter(outward[dim], -np.inf if index == 0 else np.inf)
    sample = result.sample_points([global_point, inward, outward], "linear", frame="global")
    np.testing.assert_array_equal(sample.valid, [True, False, False])
    np.testing.assert_array_equal(sample.velocity[0], selected)
    np.testing.assert_array_equal(sample.sampled_points[0], global_point)
    assert np.isfinite(sample.sampled_points[1]).all()  # Inside centres, but a solid contributes.
    assert np.isnan(sample.sampled_points[2]).all()  # Outside centre range.


def test_global_off_centre_interpolation_uses_represented_global_axes():
    result = decimal_grid()
    gx = result.x.astype(np.float64) + result.origin[0]
    # A one-dimensional field gives an independent expected linear interpolant.
    result.velocity[:] = 0
    result.velocity[..., 0] = np.arange(len(result.x))
    point = np.array([[gx[1] + (gx[2] - gx[1])*.25,
                       float(result.y[1]) + result.origin[1],
                       float(result.z[1]) + result.origin[2]]])
    sample = result.sample_points(point, "linear", frame="global")
    expected = np.interp(point[0, 0], gx, np.arange(len(gx)))
    assert sample.valid.all()
    np.testing.assert_allclose(sample.velocity[0], [expected, 0, 0], rtol=2e-15)


@pytest.mark.parametrize("origin", [(0, 0), (0, 0, 0, 0), (np.nan, 0, 0), (0, np.inf, 0),
                                    ("bad", 0, 0), (10**1000, 0, 0)])
def test_global_sampling_rejects_malformed_origin(origin):
    with pytest.raises(ValueError, match="origin"):
        replace(manufactured(), origin=origin).sample_points([[1, 1, 1]], frame="global")


def test_global_sampling_rejects_origin_that_collapses_adjacent_centres():
    result = replace(manufactured(), origin=(1e20, 0, 0))
    with pytest.raises(ValueError, match="global coordinate precision"):
        result.sample_points([[1e20, 1, 1]], frame="global")


@pytest.mark.parametrize("resolution", [True, None, "1", np.inf, 10**1000])
def test_invalid_resolution_has_clear_error(resolution):
    with pytest.raises(ValueError, match="resolution"):
        replace(manufactured(), resolution=resolution).sample_points([[1, 1, 1]])


@pytest.mark.parametrize("method", ["nearest", "linear"])
@pytest.mark.parametrize("frame", ["local", "global"])
def test_finite_extreme_outside_probes_do_not_raise_or_warn(method, frame):
    result = manufactured()
    far = np.finfo(np.float64).max
    points = np.array([[far, 1, 1], [-far, 1, 1], [1, far, 1], [1, -far, 1],
                       [1, 1, far], [1, 1, -far]])
    with np.errstate(all="raise"):
        if frame == "global":
            points += result.origin
        sample = result.sample_points(points, method, frame=frame)
    assert not sample.valid.any() and np.isnan(sample.velocity).all()


@pytest.mark.parametrize("method", ["nearest", "linear"])
@pytest.mark.parametrize("flag", [1, 3, 4, 5, 7, 8, 9])
def test_air_parameterization_flags_remain_valid(method, flag):
    result = manufactured()
    result.cell_flags[:] = flag
    assert result.sample_points([[1, 1, 1]], method).valid.all()


@pytest.mark.parametrize("corner", list(np.ndindex(2, 2, 2)))
@pytest.mark.parametrize("problem", ["uncomputed", "indefinite", "nonfinite"])
def test_every_stress_contributor_preserves_coverage_and_tensor_validity(corner, problem):
    result = with_stress(manufactured())
    if problem == "uncomputed":
        result.turbulence.computed[corner] = False
    elif problem == "indefinite":
        # Its small weight conceals the negative eigenvalue in the interpolant.
        result.turbulence.stress[corner] = [-1, 0, 0, 2, 0, 1]
    else:
        result.turbulence.stress[corner] = np.nan
    sample = result.sample_points([[1, 1, .5], [3, 2, 3]], "linear")
    assert sample.valid.all()  # Velocity validity is independent of turbulence.
    np.testing.assert_array_equal(sample.stress_valid, [False, True])
    assert np.isnan(sample.streamwise_std[0]) and np.isfinite(sample.streamwise_std[1])
    if problem == "indefinite":
        assert sample.stress[0, 0] > 0
        assert np.isfinite(sample.stress[0]).all()
    else:
        assert np.isnan(sample.stress[0]).all()


def test_trilinear_stress_components_are_interpolated_before_projection():
    result = with_stress(manufactured())
    z, y, x = np.meshgrid(result.z, result.y, result.x, indexing="ij")

    def tensor(x, y, z):
        return np.stack((4+x*y*z, .125*x, .125*y, 2+y*z, .125*z, 1+x*z), axis=-1)

    result.turbulence.stress[:] = tensor(x, y, z)
    points = np.array([[1, 1, .5], [3, 2, 3]])
    sample = result.sample_points(points, "linear")
    expected = tensor(*points.T)
    np.testing.assert_allclose(sample.stress, expected, rtol=2e-15)
    n = sample.velocity / sample.speed[:, None]
    matrix = expected[:, (0, 1, 2, 1, 3, 4, 2, 4, 5)].reshape(-1, 3, 3)
    std = np.sqrt(np.einsum("ni,nij,nj->n", n, matrix, n))
    assert sample.stress_valid.all()
    np.testing.assert_allclose(sample.streamwise_std, std, rtol=2e-15)
    np.testing.assert_allclose(sample.turbulence_intensity, std/sample.speed, rtol=2e-15)


@pytest.mark.parametrize("problem", ["solid", "nonfinite"])
def test_stress_coverage_is_independent_of_mean_velocity_validity(problem):
    result = with_stress(manufactured())
    if problem == "solid":
        result.cell_flags[0, 0, 0] = 0
    else:
        result.velocity[0, 0, 0] = np.inf
    sample = result.sample_points([[1, 1, .5]], "linear")
    assert not sample.valid.any() and sample.stress_valid.all()
    np.testing.assert_array_equal(sample.stress[0], [4, 0, 0, 2, 0, 1])
    assert np.isnan(sample.streamwise_std).all() and np.isnan(sample.turbulence_intensity).all()


@pytest.mark.parametrize("scale", [1e-200, 1e200])
def test_speed_and_streamwise_projection_at_extreme_finite_velocity_scales(scale):
    result = with_stress(manufactured())
    result = replace(result, velocity=np.full_like(result.velocity, scale, dtype=np.float64))
    sample = result.sample_points([[1, 1, 1]], "linear")
    assert sample.valid.all()
    np.testing.assert_allclose(sample.speed, np.sqrt(3)*scale, rtol=2e-15, atol=0)
    np.testing.assert_allclose(sample.streamwise_std, np.sqrt(7/3), rtol=2e-15)
    np.testing.assert_allclose(sample.turbulence_intensity, np.sqrt(7)/3/scale, rtol=2e-15, atol=0)


@pytest.mark.parametrize("method", ["nearest", "linear"])
def test_duplicate_and_noncontiguous_probes_preserve_order_and_owned_storage(method):
    result = manufactured()
    backing = np.array([[3, 2, 3], [0, 0, 0], [1, 1, 1], [0, 0, 0], [3, 2, 3], [0, 0, 0.]])
    points = backing[::2]
    assert not points.flags.c_contiguous
    sample = result.sample_points(points, method)
    for i, point in enumerate(points):
        np.testing.assert_array_equal(sample.velocity[i], result.sample_points([point], method).velocity[0])
    np.testing.assert_array_equal(sample.velocity[0], sample.velocity[2])
    before = sample.points.copy()
    backing[:] = -1
    np.testing.assert_array_equal(sample.points, before)

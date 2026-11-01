"""Height sampling checks independent of the urban flow parameterizations."""
from dataclasses import replace
import gzip
import json
from pathlib import Path
import os
import subprocess
import tracemalloc

import numpy as np
import pytest

from dtcc_qes import _qes, wind


def manufactured():
    faces = np.array([0, 0.5, 1.25, 2.25, 4.25, 7.25], dtype=np.float32)
    centres = np.float32(0.5) * (faces[:-1] + faces[1:])
    x, y = np.arange(4, dtype=np.float32) + 0.5, np.arange(3, dtype=np.float32) + 0.5
    z, yy, xx = np.meshgrid(centres, y, x, indexing="ij")
    velocity = np.stack((1 + 2*z + 0.25*xx, -2 + 0.5*z - 0.5*yy, 3 - 0.75*z), axis=-1)
    return wind.WindResult(velocity, x, y, centres, np.ones(z.shape, dtype=np.int32),
                           (1e9, -2e9, 100), "EPSG:3006", 1,
                           wind.SolveDiagnostics(1, 0, 1e-5, True), {}, z_faces=faces)


def test_affine_vector_on_nonuniform_layers_preserves_axes_height_and_frame():
    result = manufactured()
    sample = result.sample(1.5, method="linear")
    yy, xx = np.meshgrid(result.y, result.x, indexing="ij")
    expected = np.stack((4 + 0.25*xx, -1.25 - 0.5*yy, np.full(xx.shape, 1.875)), axis=-1)
    np.testing.assert_allclose(sample.velocity, expected, rtol=0, atol=1e-15)
    np.testing.assert_allclose(sample.speed, np.linalg.norm(expected, axis=-1))
    np.testing.assert_array_equal(sample.x, result.x)
    np.testing.assert_array_equal(sample.y, result.y)
    assert sample.velocity.shape == (3, 4, 3)
    assert sample.velocity.dtype == np.float64 and sample.valid.all()
    assert sample.requested_height == sample.sampled_height == 1.5
    assert sample.method == "linear" and sample.origin == result.origin and sample.crs == result.crs


def test_interpolate_components_before_magnitude():
    result = manufactured()
    result.velocity[1] = [5, 0, 0]
    result.velocity[2] = [-5, 0, 0]
    sample = result.sample(float(result.z[1] + result.z[2])/2, method="linear")
    np.testing.assert_array_equal(sample.velocity, 0)
    np.testing.assert_array_equal(sample.speed, 0)


@pytest.mark.parametrize("flag", [0, 2])
@pytest.mark.parametrize("layer", [1, 2])
def test_either_contributing_solid_invalidates_only_its_sample(flag, layer):
    result = manufactured()
    result.cell_flags[layer, 0, 1] = flag
    result.cell_flags[1, 2, 3] = 9  # An air parameterization remains valid.
    sample = result.sample(1.5, method="linear")
    assert not sample.valid[0, 1] and sample.valid.sum() == 11
    assert np.isnan(sample.velocity[0, 1]).all() and np.isnan(sample.speed[0, 1])
    assert sample.valid[2, 3]


@pytest.mark.parametrize("layer", [0, 2, 4])
@pytest.mark.parametrize("scalar", [float, np.float32])
def test_exact_centre_uses_only_that_layer_including_endpoints(layer, scalar):
    result = manufactured()
    result.cell_flags[:] = 2
    result.cell_flags[layer] = 1
    for other in set(range(len(result.z))) - {layer}:
        result.velocity[other] = np.nan
    sample = result.sample(scalar(result.z[layer]), method="linear")
    assert sample.valid.all()
    np.testing.assert_array_equal(sample.velocity, result.velocity[layer])


def test_nearby_float64_height_is_not_rounded_to_a_centre():
    result = manufactured()
    result.cell_flags[3] = 0
    height = np.nextafter(float(result.z[2]), np.inf)
    assert np.float32(height) == result.z[2]  # A float32 comparison would snap.
    sample = result.sample(height, method="linear")
    assert not sample.valid.any() and np.isnan(sample.velocity).all()
    assert sample.requested_height == sample.sampled_height == height
    below_first = np.nextafter(float(result.z[0]), 0)
    assert result.sample(below_first, method="linear").sampled_height is None


def test_decimal_python_float_and_effective_float32_centre_remain_distinct():
    result = manufactured()
    result.z[2] = np.float32(1.7)
    result.cell_flags[1] = 2
    assert float(result.z[2]) > 1.7
    assert not result.sample(1.7, method="linear").valid.any()
    assert result.sample(np.float32(1.7), method="linear").valid.all()


def test_nearest_default_clips_endpoints_and_breaks_ties_toward_lower_index():
    result = manufactured()
    for height, layer in [(0, 0), (7.25, 4), (1.3125, 1)]:
        sample = result.sample(height)
        assert sample.method == "nearest" and sample.sampled_height == float(result.z[layer])
        assert sample.requested_height == height
        np.testing.assert_array_equal(sample.velocity, result.velocity[layer])
    result.cell_flags[2] = 0
    assert result.sample(1.3125).valid.all()  # Unselected solid is irrelevant.
    assert not result.sample(float(result.z[2])).valid.any()


@pytest.mark.parametrize("height", [0, 7.25])
def test_linear_inside_domain_but_outside_centres_is_invalid(height):
    sample = manufactured().sample(height, method="linear")
    assert sample.sampled_height is None and sample.requested_height == height
    assert not sample.valid.any() and np.isnan(sample.velocity).all() and np.isnan(sample.speed).all()


@pytest.mark.parametrize("height", [-1, 8, np.nan, np.inf, True, np.bool_(False), "1.5", None,
                                    [1.5], np.array([1.5]), 1+1j, 10**1000])
def test_bad_heights_are_rejected(height):
    with pytest.raises(ValueError, match="height"):
        manufactured().sample(height, method="linear")


@pytest.mark.parametrize("method", ["cubic", "Linear", None, [], np.array(["linear"])])
def test_bad_methods_are_rejected(method):
    with pytest.raises(ValueError, match="method"):
        manufactured().sample(1.5, method=method)


def test_nonfinite_contributor_is_invalid_and_samples_own_their_storage():
    result = manufactured()
    result.velocity[2, 1, 2, 0] = np.inf
    sample = result.sample(1.5, method="linear")
    assert not sample.valid[1, 2] and np.isnan(sample.velocity[1, 2]).all()
    before = result.velocity.copy()
    sample.velocity[:] = 0
    sample.x[:] = -1
    sample.y[:] = -1
    sample.valid[:] = False
    np.testing.assert_array_equal(result.velocity, before)
    assert (result.x > 0).all() and (result.y > 0).all()
    assert (result.cell_flags == 1).all()


def test_legacy_result_without_faces_derives_physical_top():
    result = manufactured()
    result = replace(result, z=np.arange(5, dtype=np.float32) + 0.5, z_faces=None)
    assert result.sample(5).sampled_height == 4.5
    assert result.sample(5, method="linear").sampled_height is None
    with pytest.raises(ValueError, match="physical domain"):
        result.sample(5.1)


def test_sampling_memory_scales_with_planes_not_volume():
    result = manufactured()
    # A virtual volume would require hundreds of MB if copied or fully masked.
    nz, ny, nx = 9000, 64, 64
    result = replace(result,
        x=np.arange(nx), y=np.arange(ny), z=np.arange(nz, dtype=np.float32)+0.5,
        z_faces=np.arange(nz+1, dtype=np.float32),
        velocity=np.broadcast_to(np.ones((ny,nx,3), dtype=np.float32), (nz,ny,nx,3)),
        cell_flags=np.broadcast_to(np.ones((ny,nx), dtype=np.int32), (nz,ny,nx)))
    tracemalloc.start()
    try:
        sample = result.sample(1, method="linear")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert sample.valid.all() and sample.velocity.shape == (ny,nx,3)
    assert peak < 3_000_000


@pytest.mark.usefixtures("dtcc_logger")
@pytest.mark.parametrize("spacing", ["0.5", "stretched"])
def test_public_sampler_matches_current_native_study(spacing):
    from dtcc_core.model import Building, City, GeometryType, Surface

    archive = Path(__file__).parents[1] / "docs/data/vertical-grid-gate/raw.json.gz"
    runs = json.loads(gzip.decompress(archive.read_bytes()))["runs"]
    reference = next(r for r in runs if r["geometry"] == "tower" and r["direction"] == 270
                     and r["grid"] == spacing)
    root = Path(__file__).parents[1]
    executable = Path(os.environ.get("DTCC_QES_STUDY_EXECUTABLE",
        root/"build"/("openmp" if _qes.openmp_enabled else "serial")/"vertical_grid_study"))
    if not executable.exists():
        pytest.skip("Build the native vertical_grid_study target for sampler parity")
    # Sampling parity needs the same finite iterate, not a converged reference.
    # Compare the current red/black trajectory in both builds; retain archived
    # grid operands without claiming its old lexicographic field is unchanged.
    current = json.loads(subprocess.check_output([str(executable),"tower",spacing,"270","8"],
        env=os.environ | {"DTCC_QES_STUDY_ORDER": "red_black"}, text=True, timeout=30))
    assert current["backend"] == ("openmp_red_black" if _qes.openmp_enabled else "serial_red_black")
    np.testing.assert_array_equal(current["z_faces"],reference["z_faces"])
    checkpoint = current["checkpoints"][0]
    city = City()
    for y in (22, 42):
        for x in (22, 42):
            b = Building(id=f"{x}-{y}")
            b.measured_height = 24 if x == y == 42 else 8
            b.add_geometry(Surface(vertices=np.array([[x,y,0], [x,y+12,0],
                [x+12,y+12,0], [x+12,y,0]], dtype=float)), GeometryType.LOD0)
            city.add_building(b)
    result = wind.run(city, speed=5, direction=270, resolution=2, bounds=(0,0,0,80,80,64), vertical_grid=wind.VerticalGrid.from_faces(reference["z_faces"]), solver=wind.Solver(tolerance=float(np.finfo(np.float32).eps), max_iterations=checkpoint["iterations"]))
    assert result.diagnostics.iterations == checkpoint["iterations"]
    sample = result.sample(1.5, method="linear")
    expected = np.array([v if v is not None else [np.nan]*3 for v in checkpoint["velocity"]])
    np.testing.assert_array_equal(sample.valid[1:-1,1:-1].ravel(), np.isfinite(expected).all(axis=1))
    np.testing.assert_allclose(sample.velocity[1:-1,1:-1].reshape(-1,3), expected,
                               rtol=0, atol=6e-10, equal_nan=True)

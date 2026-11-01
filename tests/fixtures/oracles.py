"""Independent covariance and archive oracles; no production stress helpers."""

from collections.abc import Mapping
import numpy as np
from reference_checks import assert_reference_velocity


def covariance(direction, mixing_length, gradient):
    n = np.asarray(direction, dtype=float)
    n = n / np.linalg.norm(n)
    m, ez = np.array([-n[1], n[0], 0]), np.array([0, 0, 1])
    length, gradient = float(mixing_length), float(gradient)
    tensor = (2.5 * length * gradient) ** 2 * np.outer(n, n) + (
        2 * length * gradient
    ) ** 2 * np.outer(m, m)
    tensor += (1.3 * length * gradient) ** 2 * np.outer(ez, ez)
    tensor -= length**2 * gradient**2 * (np.outer(n, ez) + np.outer(ez, n))
    return tensor[(0, 0, 0, 1, 1, 2), (0, 1, 2, 1, 2, 2)]


def stress_validity(stress):
    raw = np.asarray(stress, dtype=np.float64)
    matrix = raw[..., (0, 1, 2, 1, 3, 4, 2, 4, 5)].reshape(*raw.shape[:-1], 3, 3)
    finite = np.isfinite(matrix).all(axis=(-2, -1))
    eigenvalues = np.linalg.eigvalsh(np.where(finite[..., None, None], matrix, 0))
    return finite & (
        eigenvalues[..., 0]
        >= -32 * np.finfo(np.float32).eps * np.abs(eigenvalues).max(axis=-1)
    )


def assert_wind_archive(result, reference):
    def get(name):
        return result[name] if isinstance(result, Mapping) else getattr(result, name)

    for axis in ("x", "y", "z"):
        np.testing.assert_array_equal(get(axis), reference[axis])
    for i, name in enumerate(("u", "v", "w")):
        assert_reference_velocity(get("velocity")[..., i], reference[name])
    np.testing.assert_array_equal(get("cell_flags"), reference["icell"])


def assert_turbulence_archive(fields, reference, computed):
    def get(name):
        return fields[name] if isinstance(fields, Mapping) else getattr(fields, name)

    np.testing.assert_array_equal(computed, reference["computed"])
    for name in ("stress", "tke", "co_eps", "mixing_length"):
        np.testing.assert_array_equal(get(name)[computed], reference[name][computed])
        assert np.isnan(get(name)[~computed]).all()
        assert np.all(reference[name][~computed] == 0)

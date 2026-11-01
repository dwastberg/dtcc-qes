"""A prepared geometry must reproduce a fresh condition, including after failure."""

import numpy as np


import pytest


from dtcc_qes import _qes


def configuration(stretched=False, **flags):
    grid = _qes.GridConfig()
    grid.nx, grid.ny, grid.nz, grid.cell_size = 50, 40, 20, 2
    model = _qes.ModelSettings()
    model.sensor_x = model.sensor_y = 5
    model.rooftop_flag = 2
    for name, value in flags.items():
        setattr(model, name, value)
    blocks = [(14, 12, 10, 16, 10), (32, 12, 8, 8, 6), (32, 26, 12, 8, 14)]
    vertices, offsets = [], [0]
    for x, y, w, d, _ in blocks:
        vertices += [(x, y), (x, y + d), (x + w, y + d), (x + w, y), (x, y)]
        offsets.append(len(vertices))
    arrays = dict(
        vertices=np.asarray(vertices, np.float64),
        offsets=np.asarray(offsets, np.int64),
        heights=np.asarray([b[4] for b in blocks], np.float64),
        base_heights=np.zeros(3),
        ids=np.arange(3, dtype=np.int64),
    )
    if stretched:
        arrays["dz_layers"] = np.r_[np.ones(8), np.full(12, 3.0)]
    return grid, model, arrays


def prepare(config, method=None):
    grid, model, arrays = config
    runner = _qes.WindRunner()
    settings = _qes.TurbulenceSettings()
    settings.enabled = method is not None
    settings.mixing_length_method = method or 0
    runner.prepare(grid, model, **arrays, turbulence=settings)
    return runner


def solve(runner, direction, precision="float32", speed=5.0, iterations=12):
    condition = _qes.WindCondition()
    condition.speed, condition.direction, condition.reference_height = (
        speed,
        direction,
        10,
    )
    options = _qes.SolverOptions()
    options.precision, options.max_iterations = precision, iterations
    return runner.solve(condition, options)


def assert_same(actual, expected):
    assert actual.keys() == expected.keys()
    for key, value in expected.items():
        other = actual[key]
        if key == "timings":
            assert other.keys() == value.keys()
            assert all(type(t) is float and np.isfinite(t) and t >= 0 for t in other.values())
            assert all(type(t) is float and np.isfinite(t) and t >= 0 for t in value.values())
            continue
        if isinstance(value, np.ndarray):
            assert other.dtype == value.dtype and other.shape == value.shape, key
            assert other.tobytes() == value.tobytes(), key
        elif isinstance(value, dict):
            assert_same(other, value)
        else:
            assert other == value, key

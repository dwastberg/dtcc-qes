"""Build the private native contract from the canonical reference cases."""

import numpy as np

from dtcc_qes import _qes


def inputs(case):
    grid = _qes.GridConfig()
    for name in ("nx", "ny", "nz", "cell_size"):
        setattr(grid, name, getattr(case.grid, name))
    model = _qes.ModelSettings()
    for name in ("roughness_length", "sensor_x", "sensor_y"):
        setattr(model, name, getattr(case.wind, name))
    for name in case.parameterizations.__dataclass_fields__:
        setattr(model, name, getattr(case.parameterizations, name))
    condition = _qes.WindCondition()
    for name in ("speed", "direction", "reference_height"):
        setattr(condition, name, getattr(case.wind, name))
    solver = _qes.SolverOptions()
    solver.tolerance = case.solver.tolerance
    solver.max_iterations = case.solver.max_iterations
    vertices, offsets = [], [0]
    for building in case.buildings:
        vertices.extend((*building.vertices, building.vertices[0]))
        offsets.append(len(vertices))
    arrays = dict(
        vertices=np.asarray(vertices, dtype=np.float64).reshape(-1, 2),
        offsets=np.asarray(offsets, dtype=np.int64),
        heights=np.asarray([b.height for b in case.buildings], dtype=np.float64),
        base_heights=np.asarray([b.base_height for b in case.buildings], dtype=np.float64),
        ids=np.asarray([b.id for b in case.buildings], dtype=np.int64),
    )
    return grid, model, condition, solver, arrays


def prepared(case):
    grid, model, condition, solver, arrays = inputs(case)
    runner = _qes.WindRunner()
    runner.prepare(grid, model, **arrays)
    return runner, condition, solver

"""Synthetic DTCC cities built from the canonical numerical fixtures."""

import numpy as np
from dtcc_core.model import Building, City, GeometryType, Surface

from dtcc_qes import wind


def city_case(case, translation=(0.0, 0.0, 0.0)):
    city = City()
    for source in case.buildings:
        building = Building(id=str(source.id))
        building.measured_height = source.height
        vertices = np.c_[np.asarray(source.vertices), np.full(len(source.vertices), source.base_height)]
        vertices += np.asarray(translation)
        building.add_geometry(Surface(vertices=vertices), GeometryType.LOD0)
        city.add_building(building)
    condition = wind.WindCondition(case.wind.speed, case.wind.direction,
                                   case.wind.reference_height, case.wind.roughness_length)
    extent = case.extent
    bounds = (*translation, *(translation[i] + extent[i] for i in range(3)))
    grid = wind.GridSpec(resolution=case.grid.cell_size, bounds=bounds)
    solver = wind.SolverOptions(case.solver.tolerance, case.solver.max_iterations)
    return city, condition, grid, solver

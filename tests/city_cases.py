"""Synthetic DTCC cities built from the canonical numerical fixtures."""

import numpy as np
from dtcc_core.model import Building, City, GeometryType, Surface


def city_case(case, translation=(0.0, 0.0, 0.0)):
    city = City()
    for source in case.buildings:
        building = Building(id=str(source.id))
        building.measured_height = source.height
        vertices = np.c_[np.asarray(source.vertices), np.full(len(source.vertices), source.base_height)]
        vertices += np.asarray(translation)
        building.add_geometry(Surface(vertices=vertices), GeometryType.LOD0)
        city.add_building(building)
    condition = dict(speed=case.wind.speed, direction=case.wind.direction,
                     reference_height=case.wind.reference_height, roughness_length=case.wind.roughness_length)
    extent = case.extent
    bounds = (*translation, *(translation[i] + extent[i] for i in range(3)))
    grid = dict(resolution=case.grid.cell_size, bounds=bounds)
    solver = dict(tolerance=case.solver.tolerance, max_iterations=case.solver.max_iterations)
    return city, condition, grid, solver

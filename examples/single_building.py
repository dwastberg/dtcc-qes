"""Self-contained steady wind example: no files are read or written by QES."""

import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind


def main():
    city = City()
    building = Building(id="example-building")
    building.measured_height = 8.0
    building.add_geometry(Surface(vertices=np.array([
        [30.0, 25.0, 0.0], [30.0, 35.0, 0.0],
        [40.0, 35.0, 0.0], [40.0, 25.0, 0.0],
    ])), GeometryType.LOD0)
    city.add_building(building)
    result = wind.run(city, wind.WindCondition(speed=5.0, direction=270.0),
                      grid=wind.GridSpec(resolution=2.0, bounds=(0, 0, 0, 80, 60, 40)))
    volume_grid = result.to_dtcc()
    get_python_logger("dtcc-qes").info(
        "Example produced %d georeferenced cells; velocity shape=%s; origin=%s",
        volume_grid.num_cells, result.velocity.shape, result.origin,
    )
    return result, volume_grid


if __name__ == "__main__":
    main()

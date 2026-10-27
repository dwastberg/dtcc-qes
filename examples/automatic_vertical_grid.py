"""Preview and solve with the provisional automatic-grid policy."""
import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind


def main():
    city = City()
    building = Building(id="example-building")
    building.measured_height = 8
    building.add_geometry(Surface(vertices=np.array([
        [30., 25., 0.], [30., 35., 0.], [40., 35., 0.], [40., 25., 0.],
    ])), GeometryType.LOD0)
    city.add_building(building)
    # These are prototype settings, not a validated comfort-analysis preset.
    specification = wind.VerticalGrid.auto(pedestrian_height=1.5, growth_rate=1.15)
    options = dict(resolution=2, bounds=(0, 0, 0, 80, 60, 40), vertical_grid=specification)
    preview = wind.preview_grid(city, **options)
    record = preview.domain["vertical_grid"]
    logger = get_python_logger("dtcc-qes")
    logger.info("Automatic prototype: shape=%s, cells=%d, layer thickness=%g..%g m",
                preview.shape, preview.cell_count, preview.solver_dz.min(), preview.solver_dz.max())
    logger.info("Policy status=%s; endpoint=%s", record["policy_status"], record["endpoint_fit"])
    result = wind.run(city, speed=5, direction=270, max_iterations=4000, **options)
    pedestrian = result.sample(1.5, method="linear")
    logger.info("At %.2f m: valid points=%d, maximum interior divergence=%s s^-1",
                pedestrian.sampled_height, int(pedestrian.valid.sum()), result.diagnostics.max_divergence)
    return preview, result, pedestrian


if __name__ == "__main__":
    main()

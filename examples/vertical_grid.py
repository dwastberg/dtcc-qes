"""Preview and compare explicit uniform/stretched grids at pedestrian height."""
import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind


def main():
    city = City()
    building = Building(id="example-building")
    building.measured_height = 8
    building.add_geometry(Surface(vertices=np.array([
        [30.,25.,0.], [30.,35.,0.], [40.,35.,0.], [40.,25.,0.],
    ])), GeometryType.LOD0)
    city.add_building(building)
    specifications = {
        "uniform": wind.VerticalGrid.from_faces(np.arange(0,40.5,0.5)),
        "stretched": wind.VerticalGrid.from_faces(
            np.r_[np.arange(0,4,0.5), np.arange(4,20), np.arange(20,42,2)]),
    }
    logger = get_python_logger("dtcc-qes")
    outputs = {}
    for name, spec in specifications.items():
        options = dict(resolution=2, bounds=(0,0,0,80,60,40), vertical_grid=spec)
        preview = wind.preview_grid(city, **options)
        logger.info("%s grid: shape=%s, cells=%d", name, preview.shape, preview.cell_count)
        result = wind.run(city, speed=5, direction=270, **options, solver=wind.Solver(max_iterations=4000))
        pedestrian = result.sample(1.5, method="linear")
        logger.info("%s: sampled at %.2f m, valid points=%d, max interior divergence=%s s^-1",
                    name, pedestrian.sampled_height, int(pedestrian.valid.sum()),
                    result.diagnostics.max_divergence)
        outputs[name] = dict(preview=preview, result=result, pedestrian=pedestrian)
    a, b = (outputs[name]["pedestrian"] for name in ("uniform", "stretched"))
    common = a.valid & b.valid
    logger.info("Pedestrian P95 |delta K| = %.6f on %d common fluid points",
                np.percentile(np.abs(a.speed[common]-b.speed[common])/5,95), int(common.sum()))
    preview = outputs["stretched"]["preview"]
    logger.info("Stretched layers (local centre height, effective thickness), metres:\n%s",
                np.column_stack((preview.z, preview.dz)))
    return outputs


if __name__ == "__main__":
    main()

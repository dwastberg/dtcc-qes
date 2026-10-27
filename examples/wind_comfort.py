"""Pedestrian wind comfort around one building from one QES solve per direction.

``dtcc_qes.comfort`` needs only pedestrian-level speeds per direction and an
hourly climate; QES is one source of the speeds. Speed-ups do not depend on
the inflow speed, so each direction is solved once at REFERENCE_SPEED. The
climate is synthetic (seeded Weibull speeds at the 10 m reference, prevailing
south-westerlies) so the example reads no files.
"""

import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import comfort, wind

REFERENCE_SPEED = 5.0
PEDESTRIAN_HEIGHT = 1.5
# Explicit layers give a cell centre at 1.5 m with 2 m cells above.
FACES = np.r_[0.0, 0.5, 1.0, 2.0, np.arange(4.0, 42.0, 2.0)]


def example_city():
    city = City()
    building = Building(id="example-building")
    building.measured_height = 8.0
    building.add_geometry(Surface(vertices=np.array([
        [30.0, 25.0, 0.0], [30.0, 35.0, 0.0],
        [40.0, 35.0, 0.0], [40.0, 25.0, 0.0],
    ])), GeometryType.LOD0)
    city.add_building(building)
    return city


def pedestrian_speeds(city, directions):
    """(D, ny, nx) speed at the 1.5 m layer, NaN inside buildings."""
    fields = []
    for direction in directions:
        result = wind.run(city, speed=REFERENCE_SPEED, direction=float(direction), resolution=2.0,
                          bounds=(0, 0, 0, 80, 60, 40), vertical_grid=wind.VerticalGrid.from_faces(FACES))
        layer = int(np.argmin(np.abs(result.z - PEDESTRIAN_HEIGHT)))
        speed = np.linalg.norm(result.velocity[layer].astype(np.float64), axis=-1)
        speed[result.solid_mask[layer]] = np.nan
        fields.append(speed)
    return np.stack(fields), float(result.z[layer])


def synthetic_climate(years=1, seed=1):
    hours = 8760 * years
    rng = np.random.default_rng(seed)
    times = np.datetime64("2023-01-01T00") + np.arange(hours).astype("timedelta64[h]")
    speeds = np.round(rng.weibull(2.0, hours) * 4.5, 1)
    directions = np.mod(rng.normal(225.0, 60.0, hours), 360.0)
    return speeds, directions, times


def main(directions=np.arange(0.0, 360.0, 30.0)):
    fields, height = pedestrian_speeds(example_city(), directions)
    speeds, wind_directions, times = synthetic_climate()
    nen = comfort.assess(speeds, wind_directions, fields, directions, REFERENCE_SPEED,
                         comfort.NEN8100, height=height)
    london = comfort.assess(speeds, wind_directions, fields, directions, REFERENCE_SPEED,
                            comfort.CITY_OF_LONDON, times=times, height=height)
    logger = get_python_logger("dtcc-qes")
    for result in (nen, london):
        labels = result.criterion.comfort.labels
        counts = {labels[i]: int((result.comfort == i).sum()) for i in range(len(labels))}
        logger.info("%s comfort cells at %g m: %s", result.criterion.name, height, counts)
        for warning in result.warnings:
            logger.info("%s: %s", result.criterion.name, warning)
    return nen, london


if __name__ == "__main__":
    main()

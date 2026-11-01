"""Pedestrian wind comfort around one building from one QES solve per direction.

``dtcc_qes.comfort`` needs only pedestrian-level speeds per direction and an
hourly climate; QES is one source of the speeds. Speed-ups do not depend on
the inflow speed, so each direction is solved once at REFERENCE_SPEED. The
climate is synthetic (seeded Weibull speeds at the 10 m reference, prevailing
south-westerlies) so the example reads no files.

London GEM uses QES-Turb standard deviations with peak factor 3.0, a
user-selected screening assumption with no QES calibration. Mean and gust
averaging times are unspecified. The algebraic gust estimates are not validated
for pedestrian gusts or planning compliance.
"""

import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import comfort, wind

REFERENCE_SPEED = 5.0
PEDESTRIAN_HEIGHT = 1.5
# User-selected screening factors; the guideline supplies only the 1.85 conversion.
PEAK_FACTOR = 3.0
GUST_RATIO = 1.85
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


def directional_results(city, directions):
    """One bounded solve per rotated profile; turbulence remains screening."""
    profile = wind.LogProfile(REFERENCE_SPEED, 270)
    solver = wind.Solver(max_solve_seconds=10, monitor=wind.MonitorSpec((0,80,0,60)),
                         raise_on_failure=True)
    return [wind.run(city, profile.with_direction(float(direction)), resolution=2.,
        bounds=(0,0,0,80,60,40), vertical_grid=wind.VerticalGrid.from_faces(FACES),
        turbulence=wind.Turbulence(), solver=solver) for direction in directions]


def synthetic_climate(years=1, seed=1):
    hours = 8760 * years
    rng = np.random.default_rng(seed)
    times = np.datetime64("2023-01-01T00") + np.arange(hours).astype("timedelta64[h]")
    speeds = np.round(rng.weibull(2.0, hours) * 4.5, 1)
    directions = np.mod(rng.normal(225.0, 60.0, hours), 360.0)
    return speeds, directions, times


def main(directions=np.arange(0.0, 360.0, 30.0)):
    results = directional_results(example_city(), directions)
    speeds, wind_directions, times = synthetic_climate()
    nen = comfort.assess_results(results, speeds, wind_directions, comfort.NEN8100,
                                 height=PEDESTRIAN_HEIGHT)
    london = comfort.assess_results(results, speeds, wind_directions, comfort.CITY_OF_LONDON,
        times=times, height=PEDESTRIAN_HEIGHT, peak_factor=PEAK_FACTOR, gust_ratio=GUST_RATIO)
    height = PEDESTRIAN_HEIGHT
    logger = get_python_logger("dtcc-qes")
    for result in (nen, london):
        labels = result.criterion.comfort.labels
        counts = {labels[i]: int((result.comfort == i).sum()) for i in range(len(labels))}
        logger.info("%s comfort cells at %g m: %s", result.criterion.name, height, counts)
        logger.info("%s unassessed cells: %d", result.criterion.name, int((result.comfort < 0).sum()))
        for warning in result.warnings:
            logger.info("%s: %s", result.criterion.name, warning)
    return nen, london


if __name__ == "__main__":
    main()

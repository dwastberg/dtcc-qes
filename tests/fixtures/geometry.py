"""Shared qualified 2×2 tower city and measured-height block layouts."""

from dtcc_core.model import Transform
from fixtures.turbulence_domain import blocks


def tower_city():
    city = blocks((7.9, 7.9, 7.9, 23.7))
    city.transform = Transform(srs="EPSG:3006")
    for building in city.buildings:
        building.estimated_height = building.measured_height
    return city

"""Case C: a 3x3 cube array with three centre heights (AIJ_C_VALIDATION.md)."""
from typing import NamedTuple

from dtcc_core.model import City
from shapely.geometry import box

from . import CASE_C_XLS
from .cityutil import make_building, new_city, sha256
from .conventions import C_STATES
from .tables import C_SCALE

BLOCK = 20.0
PITCH = 40.0


class Built(NamedTuple):
    city: City
    report: dict


def build_case_c(state: str = "1H") -> Built:
    if state not in C_STATES:
        raise ValueError(f"Case C state must be one of {C_STATES}")
    city = new_city(case="AIJ-C", state=state, scale=C_SCALE, units="m",
                    frame="workbook coordinates; origin at array centre; 0 degrees flows toward +x",
                    measurement_height=2.0, source_xls=CASE_C_XLS.name,
                    source_xls_sha256=sha256(CASE_C_XLS))
    volume = 0.0
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            height = C_STATES.index(state) * BLOCK if i == j == 0 else BLOCK
            if not height:
                continue
            x, y = i * PITCH, j * PITCH
            footprint = box(x - BLOCK / 2, y - BLOCK / 2, x + BLOCK / 2, y + BLOCK / 2)
            city.add_building(make_building(f"C-{i}-{j}", footprint, height))
            volume += footprint.area * height
    return Built(city, dict(state=state, block=BLOCK, pitch=PITCH, volume=volume,
                            buildings=len(city.buildings)))

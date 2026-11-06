"""AIJ Cases A and B: one building in a turbulent boundary layer, at full scale.

- Case A ("1:1:2"): a square prism b x b x 2b (Meng & Hibi 1998).
- Case B ("4:4:1"): a slab b deep, 4b wide and 4b tall, its wide face normal to
  the wind.

Neither case comes with a drawing. The geometry follows from the schematic
figures and the point layouts of the spreadsheets (AIJ_AB_VALIDATION.md, F2).
Full scale puts the near-ground section at the 2 m pedestrian height
(``tables.A_B``, ``tables.B_B``), so both buildings are 32 m tall, with the
origin at the building centre on the ground and the flow along +x.
"""

from typing import NamedTuple

import numpy as np
from dtcc_core.model import City
from shapely.geometry import box

from .cityutil import make_building, new_city, sha256
from .tables import A_B, A_MODEL_B_MM, AB_HEIGHT_B, B_B, B_MODEL_B_MM, ab_source

PLAN_B = {"A": (1.0, 1.0), "B": (1.0, 4.0)}  # depth (x, along the wind) and width (y), in b
REGIONS = ("upwind", "roof", "side", "wake")


class Built(NamedTuple):
    city: City
    report: dict


def b(case: str) -> float:
    """Full-scale b in metres."""
    return A_B if case == "A" else B_B


def size(case: str) -> tuple[float, float, float]:
    """Depth (x), width (y) and height of the building in metres."""
    depth, width = PLAN_B[case]
    return depth * b(case), width * b(case), AB_HEIGHT_B[case] * b(case)


def build_case_ab(case: str) -> Built:
    path, _, _ = ab_source(case)
    depth, width, height = size(case)
    model_b = A_MODEL_B_MM if case == "A" else B_MODEL_B_MM
    city = new_city(
        case=f"AIJ-{case}", scale=b(case) / model_b * 1000.0, units="m",
        frame="AIJ measurement frame scaled to full size; origin at the building centre on the ground; flow along +x",
        building_height=height, reference_height_uh=height, measurement_height=2.0,
        source_xls=path.name, source_xls_sha256=sha256(path))
    footprint = box(-depth / 2, -width / 2, depth / 2, width / 2)
    city.add_building(make_building(f"{case}-building", footprint, height, role="building"))
    report = dict(depth=depth, width=width, height=height, b=b(case), volume=footprint.area * height)
    return Built(city, report)


def regions(xyz, case: str) -> np.ndarray:
    """Where each point lies relative to the building: upwind, roof (above it), side or wake."""
    depth, width, _ = size(case)
    x, y = np.asarray(xyz, dtype=np.float64)[:, 0], np.asarray(xyz, dtype=np.float64)[:, 1]
    beside = np.abs(y) > width / 2
    return np.where(x < -depth / 2, "upwind", np.where(x > depth / 2, "wake", np.where(beside, "side", "roof")))


def surface_distance(xyz, case: str) -> np.ndarray:
    """3D distance from each point to the building (the ground excluded); 0 on or inside it."""
    depth, width, height = size(case)
    xyz = np.asarray(xyz, dtype=np.float64)
    half = np.array([depth / 2, width / 2])
    gap_xy = np.maximum(np.abs(xyz[:, :2]) - half, 0.0)
    gap_z = np.maximum(xyz[:, 2] - height, 0.0)
    return np.sqrt((gap_xy ** 2).sum(axis=1) + gap_z ** 2)

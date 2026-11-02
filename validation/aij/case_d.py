"""AIJ Case D: a 1:1:4 high-rise in a regular array of city blocks (model scale 1:400).

The DXF holds 83 axis-aligned boxes in model-scale millimetres: 82 blocks of
100x100x25 mm and a 62.5x62.5x250 mm tower at the origin. At full scale these
are 40x40x10 m blocks and a 25x25x100 m tower; streets are 20 m and 30 m wide.

The boxes are decomposed into footprint Buildings by dtcc-core's
``builder.footprints_from_lod1``; 48 of them are drawn twice, so faces are
de-duplicated first.
"""

from typing import NamedTuple

from dtcc_core.builder import footprints_from_lod1
from dtcc_core.model import City

from . import CASE_D_DXF, CASE_D_XLS, dxf, prisms
from .cityutil import footprints, lod1_building, new_city, sha256

SCALE = 400.0
DXF_UNITS_MM = 4
BLOCK_HEIGHT_MM = 25.0
TOWER_HEIGHT_MM = 250.0


class Built(NamedTuple):
    city: City
    report: dict


def build_case_d(scale=SCALE, path=CASE_D_DXF) -> Built:
    doc = dxf.read(path)
    if doc.units != DXF_UNITS_MM:
        raise ValueError(f"Case D DXF units are {doc.units}, expected millimetres ({DXF_UNITS_MM})")
    factor = scale / 1000.0
    faces = prisms.unique([face * factor for face in dxf.faces(doc.modelspace())])
    solids = prisms.components(faces)
    source = City()
    for i, solid_faces in enumerate(solids):
        source.add_building(lod1_building(f"solid-{i:03d}", solid_faces))
    derived = footprints_from_lod1(source)  # raises on any solid it cannot decompose

    blocks, towers = [], []
    for building, (_, polygon, height) in zip(derived.buildings, footprints(derived)):
        if building.attributes["ground_height"] != 0.0 or "#" in building.id:
            raise ValueError("Case D solids must be single-level prisms on the ground")
        if abs(polygon.area - polygon.envelope.area) > 1e-9 * polygon.area:
            raise ValueError("Case D footprints must be axis-aligned rectangles")
        if abs(height / factor - BLOCK_HEIGHT_MM) < 1e-6:
            blocks.append((building, polygon))
        elif abs(height / factor - TOWER_HEIGHT_MM) < 1e-6:
            towers.append((building, polygon))
        else:
            raise ValueError(f"Unexpected Case D height {height / factor} mm")
    if len(blocks) != 82 or len(towers) != 1:
        raise ValueError(f"Expected 82 blocks and 1 tower, found {len(blocks)} and {len(towers)}")

    tower, _ = towers[0]
    columns = sorted({round(p.bounds[0], 3) for _, p in blocks})
    rows = sorted({round(p.bounds[1], 3) for _, p in blocks})
    city = new_city(
        case="AIJ-D", scale=scale, units="m",
        frame="AIJ measurement frame scaled to full size; origin at the tower centre",
        building_height=tower.measured_height, reference_height_uh=tower.measured_height,
        measurement_height=5.0 * factor,
        source_dxf=path.name, source_dxf_sha256=sha256(path), source_xls_sha256=sha256(CASE_D_XLS),
        footprints_from_lod1=derived.attributes["footprints_from_lod1"],
    )
    tower.id = "D-tower"
    tower.attributes["role"] = "tower"
    city.add_building(tower)
    for building, polygon in sorted(blocks, key=lambda bp: (bp[1].bounds[1], bp[1].bounds[0])):
        row, column = rows.index(round(polygon.bounds[1], 3)), columns.index(round(polygon.bounds[0], 3))
        building.id = f"D-block-r{row:02d}-c{column:02d}"
        building.attributes.update(role="block", row=row, column=column)
        city.add_building(building)
    # Independent volume check from the raw top faces (validation decomposition).
    report = dict(solids=len(solids), blocks=len(blocks), towers=len(towers),
                  face_volume=float(sum(prisms.solid(f).face_volume for f in solids)))
    return Built(city, report)

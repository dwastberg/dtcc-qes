"""AIJ Case E: a low-rise district of Niigata City, before and after a high-rise
complex is built (model scale 1:250; the DXF is already in full-scale metres).

The DXF nests its blocks inside each other, so resolving INSERTs recursively
duplicates the city (including a copy lifted by 2.4 m). Each block's own faces
are therefore taken exactly once, placed by the INSERT listed in ``BLOCKS``.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import NamedTuple

import numpy as np
import shapely
from dtcc_core.model import City

from . import CASE_E_DXF, CASE_E_XLS, dxf, prisms
from .cityutil import make_building, make_elevated, merge_touching, new_city, sha256

EXISTING = "市街地地図 (3D)"  # city map: the existing buildings
NEW = "高層建築・集合住宅 (3D)"  # high-rise / apartment complex: "after construction"
ARCADE = "アーケイド (3D)"  # shopping-arcade roofs over sidewalks
CANOPY = "屋根 (3D)"  # roof canopies over open ground
PILOTIS = "ピロティ- (3D)"  # building volumes raised on pilotis
MARKERS = "NW4 (3D)"  # 4 m spheres at the measurement points; not geometry
SITE = "敷地 (3D)"  # 500x500x0.1 m ground plate; not geometry

# block -> (role, number of own 3DFACE entities, parent block whose INSERT places it)
BLOCKS = {
    EXISTING: ("existing", 4953, None),
    NEW: ("new", 18, None),
    ARCADE: ("arcade", 167, None),
    CANOPY: ("canopy", 62, None),
    PILOTIS: ("pilotis", 18, None),
    MARKERS: ("marker", 5760, NEW),
    SITE: ("site", 6, NEW),
}
ELEVATED = (ARCADE, CANOPY, PILOTIS)
MODEL_OFFSET = (26.5, -35.5)
DXF_UNITS_M = 6
SCALE = 250.0
NEW_IDS = ("E-new-tower", "E-new-low-1", "E-new-low-2")


class Built(NamedTuple):
    city: City
    report: dict


@dataclass
class Geometry:
    existing: list  # Solid, ordered by footprint centroid (y, x)
    new: list  # Solid: tower first, then the low blocks by x
    elevated: list  # (kind, Solid), ordered by kind then centroid
    markers: np.ndarray  # (n, 3) sphere centres
    site_bounds: tuple
    offsets: dict  # block -> placement translation


def _order(solid):
    centroid = solid.centroid
    return round(centroid.y, 1), round(centroid.x, 1)


@lru_cache(maxsize=2)
def load(path=CASE_E_DXF) -> Geometry:
    doc = dxf.read(path)
    if doc.units != DXF_UNITS_M:
        raise ValueError(f"Case E DXF units are {doc.units}, expected metres ({DXF_UNITS_M})")
    model_space = doc.modelspace()
    placements, offsets = {}, {}
    for name, (role, count, parent) in BLOCKS.items():
        block = doc.blocks.get(name)
        if block is None:
            raise ValueError(f"Case E DXF lacks block {name!r} ({role})")
        found = len(block.query("3DFACE"))
        if found != count:
            raise ValueError(f"Block {name!r} ({role}) has {found} 3DFACEs, expected {count}")
        if parent is None:
            matrix = dxf.insert_matrix(model_space, name)
        else:
            matrix = dxf.chain(dxf.insert_matrix(doc.blocks.get(parent), name),
                               dxf.insert_matrix(model_space, parent))
        offset = tuple(float(v) for v in matrix.transform((0, 0, 0)))
        if not np.allclose(offset[:2], MODEL_OFFSET):
            raise ValueError(f"Block {name!r} is placed at {offset[:2]}, expected {MODEL_OFFSET}")
        placements[name], offsets[name] = matrix, offset

    def solids(name):
        return prisms.solids(dxf.block_faces(doc, name, placements[name]))

    existing = sorted(solids(EXISTING), key=_order)
    new = sorted(solids(NEW), key=lambda s: (-s.zmax, s.centroid.x))
    for solid in existing + new:
        if solid.zmin != 0.0:
            raise ValueError(f"Ground building near {solid.centroid} starts at z = {solid.zmin}")
    elevated = []
    for name in ELEVATED:
        for solid in sorted(solids(name), key=_order):
            if solid.zmin <= 0.0 or len(solid.levels) != 1:
                raise ValueError(f"Elevated {name!r} solid near {solid.centroid} is not a raised slab")
            elevated.append((BLOCKS[name][0], solid))
    marker_faces = dxf.block_faces(doc, MARKERS, placements[MARKERS])
    markers = np.array([0.5 * (np.min(np.vstack(g), 0) + np.max(np.vstack(g), 0))
                        for g in prisms.components(marker_faces)])
    site = np.vstack(dxf.block_faces(doc, SITE, placements[SITE]))
    site_bounds = tuple(float(v) for v in (*site.min(0), *site.max(0)))
    return Geometry(existing, new, elevated, markers[np.lexsort(markers[:, :2].T[::-1])], site_bounds, offsets)


def build_case_e(state="after", path=CASE_E_DXF) -> Built:
    """The exact City: one Building per roof-level part; parts may touch, never overlap."""
    if state not in ("before", "after"):
        raise ValueError("state must be 'before' or 'after'")
    geometry = load(path)
    parts = []
    for i, solid in enumerate(geometry.existing):
        parts += prisms.solid_parts(solid, (0, i), source="existing", component=i, dxf_block=EXISTING)
    if state == "after":
        for i, solid in enumerate(geometry.new):
            parts += prisms.solid_parts(solid, (1, i), source="new", dxf_block=NEW)
    disjoint, overlay = prisms.overlay(parts)

    city = new_city(
        case="AIJ-E", state=state, scale=SCALE, units="m",
        frame="AIJ measurement frame (origin at the centre of the reproduced area); "
              f"DXF model-space offset {MODEL_OFFSET} applied",
        measurement_height=2.0, boundary_layer_height=250.0, normalisation_height=15.9,
        source_dxf=path.name, source_dxf_sha256=sha256(path), source_xls_sha256=sha256(CASE_E_XLS),
    )
    counters = {}
    for part in disjoint:
        group, index = part.key[:2]
        k = counters.get((group, index), 0)
        counters[(group, index)] = k + 1
        if group == 0:
            id_ = f"E-{index:03d}-{k}"
        elif k == 0:
            id_ = NEW_IDS[index]
        else:
            raise ValueError(f"New building {NEW_IDS[index]} split into several parts")
        city.add_building(make_building(id_, part.polygon, part.height, **part.attributes))
    counts = {}
    elevated = []
    for kind, solid in geometry.elevated:
        counts[kind] = counts.get(kind, 0) + 1
        elevated.append(make_elevated(f"E-{kind}-{counts[kind]:02d}", prisms.clean(solid.footprint),
                                      solid.zmin, solid.zmax, kind, dxf_block=_block_of(kind)))
    city.add_children(elevated)

    solids = geometry.existing + (geometry.new if state == "after" else [])
    report = dict(
        state=state, solids=len(solids), stepped_solids=sum(len(s.levels) > 1 for s in solids),
        parts=len(parts), overlay=overlay, face_volume=float(sum(s.face_volume for s in solids)),
        base_union_area=float(shapely.union_all([s.footprint for s in solids]).area),
        elevated=counts, offsets={BLOCKS[k][0]: v for k, v in geometry.offsets.items()},
        site_bounds=geometry.site_bounds, markers=len(geometry.markers),
    )
    return Built(city, report)


def build_case_e_qes(state="after", path=CASE_E_DXF) -> Built:
    """The QES-ready City: touching clusters merged at max height (see DTCC_REQUESTS.md R1)."""
    exact = build_case_e(state, path)
    city, report = merge_touching(exact.city, prefix="E")
    return Built(city, dict(state=state, merge=report))


def _block_of(kind):
    return next(name for name, (role, *_) in BLOCKS.items() if role == kind)

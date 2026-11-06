"""dtcc-core City construction shared by the AIJ cases.

Buildings follow the dtcc-core convention of ``builder.building_from_footprint``:
LOD0 at the absolute roof, ``ground_height`` = 0, ``measured_height`` and a
recorded LOD1 prism. dtcc-qes still reads LOD0 z as the building base
(DTCC_REQUESTS.md R3), so every City goes through ``qes_city`` before it reaches
dtcc-qes. Elevated obstacles are generic CityObjects, which dtcc-qes ignores (R2).
"""

import copy
import hashlib

import numpy as np
import shapely
from dtcc_core.builder import building_from_footprint
from dtcc_core.builder.geometry_builders.surface import extrude_surface
from dtcc_core.model import Building, City, GeometryType, MultiSurface, Surface
from dtcc_core.model.object.city import CityObject
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from .prisms import GRID, clean, intersecting_pairs

GROUND_Z = 0.0
OVERLAP_AREA = 1e-6  # m2; smaller overlaps are floating-point noise of exact overlay, counted as touching


def sha256(path) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def new_city(**attributes) -> City:
    city = City()
    city.attributes.update(attributes)
    return city


def make_building(id, polygon: Polygon, height: float, **attributes) -> Building:
    """A Building on the flat ground in the dtcc-core convention (LOD0 at the roof)."""
    return building_from_footprint(polygon, height, ground_height=GROUND_Z, id=id, attributes=attributes)


def lod1_building(id, faces) -> Building:
    """A Building whose LOD1 is the given planar faces, for ``builder.footprints_from_lod1``."""
    building = Building(id=id)
    building.add_geometry(MultiSurface(surfaces=[Surface(vertices=np.asarray(f, dtype=np.float64)) for f in faces]),
                          GeometryType.LOD1)
    return building


def qes_city(city: City) -> City:
    """A copy of ``city`` in the dtcc-qes input contract: each LOD0 moved to its ``ground_height``.

    dtcc-core puts LOD0 at the absolute roof; dtcc-qes reads LOD0 z as the base
    and rejects roofs at different heights (DTCC_REQUESTS.md R3). Heights,
    footprints and CityObjects are unchanged. Remove once dtcc-qes reads the
    dtcc-core convention.
    """
    out = copy.deepcopy(city)
    for building in out.buildings:
        building.lod0.set_z(float(building.attributes["ground_height"]))
    return out


def make_elevated(id, polygon: Polygon, zmin: float, zmax: float, kind: str, **attributes) -> CityObject:
    obj = CityObject(id=id)
    obj.attributes.update(kind=kind, zmin=float(zmin), zmax=float(zmax), **attributes)
    top = Surface().from_polygon(polygon, float(zmax))
    obj.add_geometry(extrude_surface(top, float(zmin)), GeometryType.LOD1)
    return obj


def fill_slabs(city: City) -> City:
    """A copy of ``city`` with every elevated slab filled down to the ground, as a Building to its zmax.

    The opposite extreme to ignoring the slabs (R2). Filled slabs overlap the buildings they
    adjoin, so the City needs ``wind.Footprints``, whose cleaning keeps the taller roof.
    """
    out = copy.deepcopy(city)
    for id_, polygon, zmin, zmax in elevated_footprints(city):
        out.add_building(make_building(f"{id_}-filled", polygon, zmax, role="filled slab", slab_zmin=zmin))
    out.children.pop(CityObject, None)
    return out


def city_objects(city) -> list[CityObject]:
    return list(city.children.get(CityObject, []))


def footprints(city) -> list[tuple[str, Polygon, float]]:
    """(id, LOD0 polygon, measured height) for every Building."""
    out = []
    for building in city.buildings:
        surface = building.lod0
        holes = [h[:, :2] for h in surface.holes]
        out.append((building.id, Polygon(surface.vertices[:, :2], holes), float(building.measured_height)))
    return out


def elevated_footprints(city) -> list[tuple[str, Polygon, float, float]]:
    """(id, footprint, zmin, zmax) for every elevated CityObject, from its LOD1 top face."""
    out = []
    for obj in city_objects(city):
        zmax = obj.attributes["zmax"]
        top = next(s for s in obj.lod1.surfaces if np.allclose(s.vertices[:, 2], zmax))
        out.append((obj.id, Polygon(top.vertices[:, :2]), obj.attributes["zmin"], zmax))
    return out


FUSE_DISTANCE = 1e-3  # metres; footprints closer than this count as touching


def merge_touching(city: City, prefix: str):
    """Merge every cluster of touching or overlapping footprints into one Building.

    Footprints within FUSE_DISTANCE count as touching, so hairline gaps in the
    drawing do not split a building. The merged footprint is the union on the
    GRID, closed by FUSE_DISTANCE with mitred joins and with holes filled; the
    height is the cluster maximum. Returns (new City, report).
    """
    records = footprints(city)
    polys = [p for _, p, _ in records]
    tree = STRtree(polys)
    parent = list(range(len(polys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, polygon in enumerate(polys):
        for j in tree.query(polygon, predicate="dwithin", distance=FUSE_DISTANCE):
            a, b = find(i), find(int(j))
            if a != b:
                parent[b] = a
    clusters = {}
    for i in range(len(polys)):
        clusters.setdefault(find(i), []).append(i)

    merged = new_city(**city.attributes)
    merged.attributes["qes_ready"] = "touching footprints merged at max height"
    report = dict(clusters_merged=0, buildings_in=len(records), buildings_out=0,
                  corner_fusions=0, filled_hole_area=0.0, added_volume=0.0, merges=[])
    count = 0
    for members in sorted(clusters.values(), key=lambda m: records[m[0]][0]):
        if len(members) == 1:
            id_, polygon, height = records[members[0]]
            source = next(b for b in city.buildings if b.id == id_)
            merged.add_building(make_building(id_, polygon, height, **_extra(source)))
            continue
        count += 1
        union = shapely.union_all([polys[i] for i in members], grid_size=GRID)
        if union.geom_type != "Polygon":
            union = union.buffer(FUSE_DISTANCE, join_style="mitre").buffer(-FUSE_DISTANCE, join_style="mitre")
            report["corner_fusions"] += 1
        if union.geom_type != "Polygon":
            raise ValueError(f"Cannot fuse cluster {[records[i][0] for i in members]} into one polygon")
        filled = _snapped(Polygon(union.exterior))
        height = max(records[i][2] for i in members)
        member_volume = sum(polys[i].area * records[i][2] for i in members)
        hole_area = filled.area - union.area
        id_ = f"{prefix}-m{count:03d}"
        ids = [records[i][0] for i in members]
        merged.add_building(make_building(id_, filled, height, merged_parts=",".join(ids)))
        report["filled_hole_area"] += hole_area
        report["added_volume"] += filled.area * height - member_volume
        report["merges"].append(dict(id=id_, members=ids, heights=[records[i][2] for i in members],
                                     height=height, added_volume=filled.area * height - member_volume))
    report["clusters_merged"] = count
    report["buildings_out"] = len(merged.buildings)
    merged.add_children([copy.deepcopy(obj) for obj in city_objects(city)])
    return merged, report


def _snapped(polygon: Polygon) -> Polygon:
    """Snap a merged envelope to GRID and drop near-collinear vertices.

    The mitred closing leaves vertices a fraction of a millimetre apart, which
    collapse in dtcc-qes's float32 check. Merged envelopes are approximations
    that touch nothing, so snapping them is safe; exact parts are never snapped.
    """
    polygon = shapely.set_precision(polygon, GRID)
    return clean(polygon.simplify(GRID, preserve_topology=True))


def _extra(building):
    skip = {"measured_height", "ground_height"}
    return {k: v for k, v in building.attributes.items() if k not in skip}


def qes_check(city: City, resolution=2.0, footprints=None) -> dict:
    """Run dtcc-qes geometry and grid preparation without solving.

    ``footprints`` is passed to dtcc-qes: None for the strict contract, or a
    ``wind.Footprints`` for contact-aware cleaning, whose counts, fallbacks and
    cleaned area are then reported.
    """
    from dtcc_qes import wind
    try:
        preview = wind.preview_grid(qes_city(city), resolution=resolution, footprints=footprints)
    except ValueError as error:
        return dict(ok=False, error=str(error))
    check = dict(ok=True, resolution=float(preview.resolution), shape=list(preview.shape),
                 cells=int(preview.cell_count), origin=[float(v) for v in preview.origin])
    if footprints is None:
        check["near_contacts"] = len(preview.domain.get("near_contacts", []))
    else:
        record = preview.domain["footprints"]
        check.update(min_detail=footprints.min_detail, counts=record["counts"], fallbacks=record["fallbacks"],
                     cleaned_area=float(sum(solid["area"] for solid in record["solids"])))
    return check


def summary(city: City) -> dict:
    records = footprints(city)
    heights = np.array([h for _, _, h in records])
    union = shapely.union_all([p for _, p, _ in records], grid_size=GRID)
    pairs = intersecting_pairs([p for _, p, _ in records])
    objects = city_objects(city)
    return dict(
        buildings=len(records),
        footprint_area=float(sum(p.area for _, p, _ in records)),
        footprint_union_area=float(union.area),
        volume=float(sum(p.area * h for _, p, h in records)),
        height_min=float(heights.min()), height_max=float(heights.max()),
        holes=int(sum(len(p.interiors) for _, p, _ in records)),
        touching_pairs=sum(1 for *_, a in pairs if a <= OVERLAP_AREA),
        overlapping_pairs=sum(1 for *_, a in pairs if a > OVERLAP_AREA),
        max_overlap_area=max((a for *_, a in pairs), default=0.0),
        city_objects=len(objects),
        city_object_kinds={k: sum(1 for o in objects if o.attributes.get("kind") == k)
                           for k in sorted({o.attributes.get("kind") for o in objects})},
    )

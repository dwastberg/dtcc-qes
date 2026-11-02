"""Turn 3DFACE soups into vertical-walled solids and non-overlapping 2.5D parts.

Every AIJ obstacle is a set of prisms: horizontal faces and vertical walls
only. A connected set of faces is one solid. Its horizontal faces above the
base, grouped by height, give the roof levels; each level is a footprint part
extruded from the base to that height. ``overlay`` then resolves overlaps
between parts (from stepped solids or neighbouring solids) by keeping the
highest roof.

Coordinates are never snapped. The faces share exact DXF vertices, so exact
boolean operations keep shared edges identical. Snapping pieces independently
made neighbours overlap by up to 2e-4 m2, which broke dtcc-core's wall
construction downstream (DTCC_CORE_PLAN.md, section 3.2).
"""

import collections
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree

GRID = 1e-4  # metres; tolerance of the roof/base coverage check (per metre of perimeter)
HEIGHT_DECIMALS = 4
VERTICAL_TOLERANCE = 1e-6


def components(faces, decimals=4) -> list[list[np.ndarray]]:
    """Group faces that share vertices (rounded to ``decimals``)."""
    parent = {}

    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    keys = []
    for face in faces:
        face_keys = [tuple(np.round(p, decimals)) for p in face]
        keys.append(face_keys)
        for key in face_keys:
            parent.setdefault(key, key)
        root = find(face_keys[0])
        for key in face_keys[1:]:
            other = find(key)
            if other != root:
                parent[other] = root
    groups = collections.defaultdict(list)
    for face, face_keys in zip(faces, keys):
        groups[find(face_keys[0])].append(face)
    return list(groups.values())


def _xy_polygon(face):
    polygon = Polygon(face[:, :2])
    if not polygon.is_valid:
        polygon = shapely.make_valid(polygon)
    return polygon


def _normal(face):
    # Newell's method; robust for quads that are not exactly planar.
    shifted = np.roll(face, -1, axis=0)
    return np.array([
        np.sum((face[:, 1] - shifted[:, 1]) * (face[:, 2] + shifted[:, 2])),
        np.sum((face[:, 2] - shifted[:, 2]) * (face[:, 0] + shifted[:, 0])),
        np.sum((face[:, 0] - shifted[:, 0]) * (face[:, 1] + shifted[:, 1])),
    ])


def polygons(geometry) -> list[Polygon]:
    """Explode a (Multi)Polygon or collection into non-empty polygons."""
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [g for part in getattr(geometry, "geoms", []) for g in polygons(part)]


def clean(polygon: Polygon) -> Polygon:
    """Orient counter-clockwise, keeping the coordinates exactly."""
    return orient(polygon, sign=1.0)


@dataclass
class Solid:
    faces: list
    zmin: float
    zmax: float
    footprint: object  # union of the base faces
    levels: dict  # roof height -> union of the top faces at that height
    face_volume: float  # sum of top-face area x (z - zmin), from the raw faces

    @property
    def centroid(self):
        return self.footprint.centroid


def solid(faces) -> Solid:
    """Analyse one connected face set; raises unless it is a vertical-walled 2.5D solid."""
    zmin = min(float(f[:, 2].min()) for f in faces)
    zmax = max(float(f[:, 2].max()) for f in faces)
    base, tops = [], collections.defaultdict(list)
    for face in faces:
        if np.ptp(face[:, 2]) < VERTICAL_TOLERANCE:
            z = round(float(face[0, 2]), HEIGHT_DECIMALS)
            (base if abs(z - zmin) < VERTICAL_TOLERANCE else tops[z]).append(_xy_polygon(face))
            continue
        normal = _normal(face)
        if abs(normal[2]) > VERTICAL_TOLERANCE * np.linalg.norm(normal):
            raise ValueError(f"Face at {face[0]} is neither horizontal nor vertical")
    if not base or not tops:
        raise ValueError(f"Solid near {faces[0][0]} has no base or no roof")
    # Exact unions: the faces share DXF vertices, so snapping here would only
    # open hairline gaps where one level's vertex sits on another's edge.
    footprint = shapely.union_all(base)
    levels = {z: shapely.union_all(ps) for z, ps in sorted(tops.items())}
    covered = shapely.union_all(list(levels.values()))
    if abs(covered.area - footprint.area) > footprint.length * GRID:
        raise ValueError(f"Solid near {faces[0][0]}: roofs do not cover the base exactly (overhang?)")
    face_volume = sum(p.area * (z - zmin) for z, ps in tops.items() for p in ps)
    return Solid(faces, zmin, zmax, footprint, levels, face_volume)


def unique(faces, decimals=4) -> list[np.ndarray]:
    """Drop faces that repeat another face's vertex set (the AIJ drawings repeat some)."""
    seen, out = set(), []
    for face in faces:
        key = tuple(sorted(tuple(np.round(p, decimals)) for p in face))
        if key not in seen:
            seen.add(key)
            out.append(face)
    return out


def solids(faces) -> list[Solid]:
    return [solid(group) for group in components(unique(faces))]


@dataclass
class Part:
    key: tuple  # stable ordering key, e.g. (component, level)
    height: float
    polygon: Polygon
    attributes: dict = field(default_factory=dict)

    @property
    def volume(self):
        return self.polygon.area * self.height


def solid_parts(solid_: Solid, key, **attributes) -> list[Part]:
    """One part per roof level (and per polygon within a level)."""
    out = []
    for level, (z, geometry) in enumerate(solid_.levels.items()):
        for polygon in polygons(geometry):
            out.append(Part((*key, level), z - solid_.zmin, polygon, dict(attributes, roof_level=level)))
    return out


def overlay(parts: list[Part], min_area=0.01):
    """Make parts disjoint, keeping the higher roof where they overlap.

    Parts are ranked by height (then key). Each part loses the area covered by
    higher-ranked parts, using exact (unsnapped) overlay. Pieces smaller than
    ``min_area`` are dropped and reported. Returns (disjoint parts, report).
    """
    ranked = sorted(parts, key=lambda p: (-p.height, p.key))
    originals = [p.polygon for p in ranked]
    tree = STRtree(originals)
    out, dropped, trimmed, holes = [], [], 0, 0
    for rank, part in enumerate(ranked):
        higher = [j for j in tree.query(part.polygon, predicate="intersects") if j < rank]
        geometry = part.polygon
        if higher:
            cover = shapely.union_all([originals[j] for j in higher])
            geometry = shapely.difference(geometry, cover)
            if abs(geometry.area - part.polygon.area) > 1e-9:
                trimmed += 1
        pieces = [clean(p) for p in polygons(geometry)]
        pieces = [p for p in pieces if not p.is_empty]
        for piece in pieces:
            if piece.area < min_area:
                dropped.append((part.key, piece.area))
                continue
            holes += len(piece.interiors)
            out.append(Part(part.key, part.height, piece, dict(part.attributes)))
    out.sort(key=lambda p: (p.key, p.polygon.centroid.y, p.polygon.centroid.x))
    report = dict(
        parts_in=len(parts), parts_out=len(out), trimmed=trimmed,
        dropped=len(dropped), dropped_area=float(sum(a for _, a in dropped)),
        holes=holes,
        removed_area=float(sum(p.polygon.area for p in parts) - sum(p.polygon.area for p in out)),
        removed_volume=float(sum(p.volume for p in parts) - sum(p.volume for p in out)),
    )
    return out, report


def intersecting_pairs(polygons_):
    """Index pairs (i, j), i < j, of polygons that touch or overlap, with overlap area."""
    tree = STRtree(polygons_)
    pairs = []
    for i, polygon in enumerate(polygons_):
        for j in tree.query(polygon, predicate="intersects"):
            if j > i:
                pairs.append((i, int(j), float(polygon.intersection(polygons_[j]).area)))
    return pairs

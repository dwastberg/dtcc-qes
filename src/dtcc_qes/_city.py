"""Read canonical DTCC geometry without mutating or simplifying the city."""

from dataclasses import dataclass
import math
from numbers import Real

import numpy as np
from pyproj import CRS
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree
from shapely.validation import explain_validity

from dtcc_core.model import Building, BuildingPart, City, Surface, Terrain


def number(value, name, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    try:
        value = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _frame(transform, label):
    affine = np.asarray(transform.affine)
    if (affine.shape != (4, 4) or affine.dtype.kind not in "iuf"
            or not np.isfinite(affine).all() or not np.array_equal(affine[3], [0, 0, 0, 1])
            or not np.array_equal(affine[:3, :3], np.eye(3))):
        raise ValueError(f"{label}: only identity and translation-only transforms are supported")
    crs = None
    if transform.srs:
        try:
            crs = CRS.from_user_input(transform.srs)
        except Exception as error:
            raise ValueError(f"{label}: invalid CRS {transform.srs!r}") from error
        if (not (crs.is_projected or crs.is_engineering) or len(crs.axis_info) < 2
                or any(axis.unit_conversion_factor != 1 for axis in crs.axis_info)):
            raise ValueError(f"{label}: CRS must be planar and measured in metres")
    return affine[:3, 3].astype(np.float64, copy=True), crs


def _resolve_frame(frames, label):
    # DTCC documents transforms as local-to-global, not parent-relative.
    # Identity inherits the enclosing frame; repeated absolute translations
    # are applied once. Conflicting declarations need an explicit conversion.
    offsets = [offset for offset, _ in frames if np.any(offset)]
    if offsets and any(not np.array_equal(offset, offsets[0]) for offset in offsets[1:]):
        raise ValueError(f"{label}: conflicting absolute translations on city, building and surface")
    systems = [crs for _, crs in frames if crs is not None]
    if systems and any(not crs.equals(systems[0]) for crs in systems[1:]):
        raise ValueError(f"{label}: CRS differs from the enclosing coordinate frame")
    return offsets[0] if offsets else np.zeros(3), systems[0] if systems else None


@dataclass(frozen=True)
class CityGeometry:
    rings: tuple[np.ndarray, ...]
    heights: tuple[float, ...]
    base_ranges: tuple[tuple[float, float], ...]
    source_ids: tuple[str, ...]
    height_sources: tuple[str, ...]
    crs: str | None
    has_terrain: bool
    removed_vertices: tuple[int, ...]
    ignored_objects: dict[str, int]


def reject_intersections(polygons, source_ids, *, context=""):
    tree = STRtree(polygons)
    for i, polygon in enumerate(polygons):
        for j in tree.query(polygon, predicate="intersects"):
            if j > i:
                raise ValueError(f"Buildings {source_ids[i]!r} and {source_ids[j]!r}: "
                                 f"overlapping or touching footprints are unsupported{context}")


def extract_city(city, height_policy):
    if not isinstance(city, City):
        raise TypeError("city must be a dtcc_core.model.City")
    if height_policy not in ("measured", "allow_estimated"):
        raise ValueError("height_policy must be 'measured' or 'allow_estimated'")
    city_frame = _frame(city.transform, "City")
    children = [child for group in city.children.values() for child in group]
    parts = [child for child in children if isinstance(child, BuildingPart)]
    if parts:
        raise ValueError(f"BuildingPart {parts[0].id!r} is unsupported; supply complete LOD0 buildings")
    buildings = [child for child in children if isinstance(child, Building)]
    pending = [child for child in children if not isinstance(child, (Building, BuildingPart))]
    seen = set()
    while pending:
        parent = pending.pop()
        if id(parent) in seen:
            continue
        seen.add(id(parent))
        for group in parent.children.values():
            for child in group:
                if isinstance(child, (Building, BuildingPart)):
                    raise ValueError(f"Building {child.id!r}: nested buildings/parts are unsupported; attach complete buildings directly to the City")
                pending.append(child)
    rings, heights, ranges, ids, sources, systems, removed = [], [], [], [], [], [], []
    seen_ids = set()
    for building in buildings:
        label = f"Building {building.id!r}"
        if not isinstance(building.id, str) or not building.id or building.id in seen_ids:
            raise ValueError(f"{label}: source IDs must be unique nonempty strings")
        seen_ids.add(building.id)
        if any(isinstance(child, (Building, BuildingPart))
               for group in building.children.values() for child in group):
            raise ValueError(f"{label}: building parts are unsupported; supply one complete LOD0 footprint")
        try:
            surface = building.get_geometry(lod="0")
        except ValueError as error:
            raise ValueError(f"{label}: {error}") from error
        if not isinstance(surface, Surface):
            raise ValueError(f"{label}: requires a single LOD0 Surface; missing or multipart geometry is unsupported")
        if len(surface.holes):
            raise ValueError(f"{label}: footprint holes are unsupported")
        offset, crs = _resolve_frame([
            city_frame, _frame(building.transform, label), _frame(surface.transform, label),
        ], label)
        vertices = np.asarray(surface.vertices)
        if (vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 3
                or vertices.dtype.kind not in "iuf" or not np.isfinite(vertices).all()):
            raise ValueError(f"{label}: LOD0 vertices must be a finite (N, 3) array")
        vertices = vertices.astype(np.float64, copy=True) + offset
        if not np.isfinite(vertices).all():
            raise ValueError(f"{label}: translated coordinates are not finite")
        ranges.append((float(vertices[:, 2].min()), float(vertices[:, 2].max())))
        xy = vertices[:, :2]
        # Remove only exact, consecutive duplicates, including redundant closure.
        xy = xy[np.r_[True, np.any(xy[1:] != xy[:-1], axis=1)]]
        while len(xy) > 1 and np.array_equal(xy[-1], xy[0]):
            xy = xy[:-1]
        if len(xy) < 3:
            raise ValueError(f"{label}: footprint needs at least three distinct vertices")
        anchor = xy[0].copy()
        if float(np.max(np.abs(xy - anchor))) > 10000 * math.sqrt(float(np.finfo(np.float32).max)):
            raise ValueError(f"{label}: footprint extent exceeds the native grid range")
        polygon = Polygon(xy - anchor)
        if polygon.is_empty or not polygon.is_valid or not math.isfinite(polygon.area) or polygon.area <= 0:
            raise ValueError(f"{label}: invalid footprint ({explain_validity(polygon)})")
        ring = np.asarray(orient(polygon, sign=-1).exterior.coords) + anchor
        source = "measured_height"
        height = building.measured_height
        if height is None and height_policy == "allow_estimated":
            height, source = building.estimated_height, "estimated_height"
        if height is None:
            raise ValueError(f"{label}: missing {source}; set a height or explicitly allow estimated heights")
        height = number(height, f"{label} {source}", positive=True)
        if height > float(np.finfo(np.float32).max) or np.float32(height) <= 0:
            raise ValueError(f"{label}: height must be positive and representable in float32")
        rings.append(ring)
        heights.append(height)
        ids.append(building.id)
        sources.append(source)
        systems.append(crs)
        removed.append(len(vertices) - len(xy) - int(np.array_equal(vertices[0, :2], vertices[-1, :2])))
    declared = [crs for crs in systems if crs is not None]
    if declared and any(crs is None or not crs.equals(declared[0]) for crs in systems):
        raise ValueError("Buildings must share one CRS; declare it on the city to inherit it")
    system = declared[0] if declared else city_frame[1]
    if rings:
        anchor = np.min(np.concatenate(rings), axis=0)
        polygons = [Polygon(ring - anchor) for ring in rings]
        reject_intersections(polygons, ids)
    ignored = {}
    for child in children:
        if not isinstance(child, Building):
            name = type(child).__name__
            ignored[name] = ignored.get(name, 0) + 1
    return CityGeometry(tuple(rings), tuple(heights), tuple(ranges), tuple(ids), tuple(sources),
                        system.to_string() if system else None,
                        any(isinstance(child, Terrain) for child in children), tuple(removed), ignored)

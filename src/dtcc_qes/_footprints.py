"""Prepare height-preserving footprint cells without invoking the wind solver."""

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from numbers import Integral

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely.validation import explain_validity

from dtcc_core import builder
from dtcc_core.builder.cleaning.footprints import UnresolvedFootprintCleaningError
from dtcc_core.model import Building, City, GeometryType, MultiSurface, Surface, Transform

from ._city import extract_city, number, _frame, _resolve_frame
from .footprints import Footprints


def _ring_key(coords, protected=()):
    points = []
    for point in coords:
        value = tuple(0.0 if v == 0 else float(v) for v in point[:2])
        if not points or value != points[-1]:
            points.append(value)
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    changed = True
    while changed and len(points) > 3:
        changed = False
        for i, b in enumerate(points):
            if b in protected:
                continue
            a, c = points[i-1], points[(i+1) % len(points)]
            if ((b[0]-a[0])*(c[1]-b[1]) == (b[1]-a[1])*(c[0]-b[0])
                    and min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
                    and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])):
                points.pop(i)
                changed = True
                break
    # Winding is already fixed. Resolve cyclic shifts without changing edges.
    start = min(range(len(points)), key=lambda i: points[i])
    return tuple(points[start:] + points[:start])


def canonical_polygon(polygon, *, protected=()):
    """Fix winding and traversal, removing exact redundant vertices only."""
    polygon = orient(polygon, sign=-1)
    outer = _ring_key(polygon.exterior.coords, protected)
    holes = sorted(_ring_key(ring.coords, protected) for ring in polygon.interiors)
    return Polygon(outer, holes)


def _polygon_key(polygon):
    return (tuple(polygon.exterior.coords),
            tuple(tuple(ring.coords) for ring in polygon.interiors))


@dataclass(frozen=True)
class FootprintSource:
    source_id: str
    component_ids: tuple[str, ...]
    polygon: object
    height: float
    height_source: str
    base_range: tuple[float, float]


@dataclass(frozen=True)
class FootprintSolid:
    polygon: Polygon
    height: float
    source_ids: tuple[str, ...]
    building_ids: tuple[str, ...]
    part_ids: tuple[str, ...]
    represented_roof: float | None = None


@dataclass(frozen=True)
class PreparedFootprints:
    sources: tuple[FootprintSource, ...]
    cells: tuple[FootprintSolid, ...]
    anchor: tuple[float, float]
    crs: str | None
    has_terrain: bool
    ignored_objects: dict
    metadata: dict


@dataclass(frozen=True)
class FinalizedFootprints:
    """Canonical solids, native arrays and source accounting on a final grid."""

    solids: tuple[FootprintSolid, ...]
    arrays: dict
    metadata: dict


def _components(city):
    """Expand MultiSurfaces before Core can flatten them to a convex hull.

    A proxy retains nonbuilding objects and children so the existing city
    validator continues to reject unsupported parts and nested buildings.
    All component transforms are resolved before copying into world space.
    """
    if not isinstance(city, City):
        raise TypeError("city must be a dtcc_core.model.City")
    ids = [building.id for building in city.buildings]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ValueError("Building source IDs must be unique nonempty strings")
    proxy = deepcopy(city)
    proxy.remove_buildings()
    proxy.transform = Transform(srs=city.transform.srs)
    mappings, holes = {}, {}
    city_frame = _frame(city.transform, "City")
    for source_index, building in enumerate(sorted(city.buildings, key=lambda b: b.id)):
        label = f"Building {building.id!r}"
        try:
            geometry = building.get_geometry(lod="0")
        except ValueError as error:
            raise ValueError(f"{label}: {error}") from error
        surfaces = geometry.surfaces if isinstance(geometry, MultiSurface) else [geometry]
        if not surfaces:
            raise ValueError(f"{label}: empty MultiSurface footprint")
        resolved = []
        for surface in surfaces:
            if not isinstance(surface, Surface):
                raise ValueError(f"{label}: requires LOD0 Surface geometry")
            frames = [city_frame, _frame(building.transform, label)]
            if isinstance(geometry, MultiSurface):
                frames.append(_frame(geometry.transform, label))
            offset, crs = _resolve_frame([*frames, _frame(surface.transform, label)], label)
            rings = []
            for ring in [surface.vertices, *surface.holes]:
                values = np.asarray(ring)
                if (values.ndim != 2 or values.shape[1] != 3 or len(values) < 3
                        or values.dtype.kind not in "iuf" or not np.isfinite(values).all()):
                    raise ValueError(f"{label}: footprint rings must be finite (N, 3) arrays")
                translated = values.astype(np.float64) + offset
                if not np.isfinite(translated).all():
                    raise ValueError(f"{label}: translated coordinates are not finite")
                rings.append(translated)
            local_anchor = rings[0][0, :2]
            polygon = Polygon(rings[0][:, :2] - local_anchor,
                              [h[:, :2] - local_anchor for h in rings[1:]])
            if (not polygon.is_valid or polygon.is_empty or not np.isfinite(polygon.area)
                    or polygon.area <= 0):
                raise ValueError(f"{label}: invalid footprint ({explain_validity(polygon)})")
            # A world-space key gives each component a stable identity even
            # when the caller changes its position in the MultiSurface list.
            key = _polygon_key(canonical_polygon(Polygon(rings[0][:, :2],
                [h[:, :2] for h in rings[1:]])))
            resolved.append((key, rings, crs))
        for component_index, (_, rings, crs) in enumerate(sorted(resolved, key=lambda row: row[0])):
            component_id = f"qes-component-{source_index}-{component_index}"
            copy = deepcopy(building)
            copy.id = component_id
            copy.transform = Transform()
            copy.geometry.clear()
            copy.add_geometry(Surface(vertices=rings[0],
                transform=Transform(srs=crs.to_string() if crs else "")), GeometryType.LOD0)
            proxy.add_building(copy)
            mappings[component_id] = building.id
            holes[component_id] = rings[1:]
    return proxy, mappings, holes


def _validate_partition(cells):
    polygons = [cell.polygon for cell in cells]
    tree = STRtree(polygons)
    for i, polygon in enumerate(polygons):
        if (polygon.is_empty or not polygon.is_valid or not np.isfinite(polygon.area)
                or polygon.area <= 0):
            raise ValueError(f"Invalid cleaned footprint: {explain_validity(polygon)}")
        for j in tree.query(polygon, predicate="intersects"):
            if j > i and polygon.intersection(polygons[j]).area > 0:
                raise ValueError(f"Cleaned footprints share area: {cells[i].source_ids}, {cells[j].source_ids}")


def _sorted_cells(cells):
    return tuple(sorted(cells, key=lambda c: (-c.height, c.polygon.centroid.x,
        c.polygon.centroid.y, _polygon_key(c.polygon))))


def _node_cells(cells):
    """Keep identical junction vertices on both sides of shared boundaries."""
    if not cells:
        return ()
    polygons = [c.polygon for c in cells]
    polygon_tree = STRtree(polygons)
    vertices = sorted({tuple(p) for polygon in polygons
        for ring in [polygon.exterior, *polygon.interiors] for p in ring.coords[:-1]})
    points = [Point(v) for v in vertices]
    point_tree = STRtree(points)
    result = []
    for index, cell in enumerate(cells):
        rings, protected = [], set()
        for ring in [cell.polygon.exterior, *cell.polygon.interiors]:
            noded = []
            coords = list(ring.coords)
            for a, b in zip(coords[:-1], coords[1:]):
                edge = LineString([a, b])
                candidates = point_tree.query(edge, predicate="intersects")
                ordered = sorted((vertices[i] for i in candidates),
                    key=lambda v: (v[0]-a[0])*(b[0]-a[0]) + (v[1]-a[1])*(b[1]-a[1]))
                for vertex in ordered[:-1]:
                    noded.append(vertex)
                    if any(other != index for other in
                           polygon_tree.query(Point(vertex), predicate="touches")):
                        protected.add(vertex)
            rings.append(noded)
        polygon = canonical_polygon(Polygon(rings[0], rings[1:]), protected=protected)
        result.append(replace(cell, polygon=polygon))
    return _sorted_cells(result)


def prepare_footprints(city, height_policy="measured", *, settings=None, remove_holes=False):
    """Clean flat component copies and preserve the original source accounting.

    Coordinates are float64 relative to ``anchor``. Base elevations remain in
    the source records for the domain's subsequent flat-ground validation.
    """
    if type(remove_holes) is not bool:
        raise ValueError("remove_holes must be a bool")
    settings = Footprints() if settings is None else settings
    if not isinstance(settings, Footprints):
        raise TypeError("settings must be Footprints")
    proxy, mappings, holes = _components(city)
    try:
        geometry = extract_city(proxy, height_policy, _allow_contacts=True)
    except ValueError as error:
        message = str(error)
        for component_id, source_id in mappings.items():
            message = message.replace(repr(component_id), repr(source_id))
        raise ValueError(message) from error
    anchor = np.min(np.concatenate(geometry.rings), axis=0) if geometry.rings else np.zeros(2)
    flat = City()
    components, sources = {}, {}
    for component_id, ring, height, height_source, base_range in zip(
            geometry.source_ids, geometry.rings, geometry.heights,
            geometry.height_sources, geometry.base_ranges):
        source_id = mappings[component_id]
        polygon = Polygon(ring - anchor, [h[:, :2] - anchor for h in holes[component_id]])
        if not polygon.is_valid or polygon.is_empty or polygon.area <= 0:
            raise ValueError(f"Building {source_id!r}: invalid footprint ({explain_validity(polygon)})")
        polygon = canonical_polygon(polygon)
        if holes[component_id]:
            z = np.concatenate([h[:, 2] for h in holes[component_id]])
            base_range = (min(base_range[0], float(z.min())), max(base_range[1], float(z.max())))
        # Preserve all original elevations before filling the cleaning copy.
        if remove_holes:
            polygon = Polygon(polygon.exterior)
        components[component_id] = (polygon, height)
        sources.setdefault(source_id, []).append((component_id, polygon, height, height_source, base_range))
        building = Building(id=component_id)
        building.estimated_height = height
        building.measured_height = None
        building.add_geometry(Surface(
            vertices=np.c_[polygon.exterior.coords, np.zeros(len(polygon.exterior.coords))],
            holes=[np.c_[h.coords, np.zeros(len(h.coords))] for h in polygon.interiors]), GeometryType.LOD0)
        flat.add_building(building)
    # Core has no lossy MultiSurface conversion to perform: every source is a Surface.
    try:
        cleaned = builder.clean_footprints(flat, min_building_detail=settings.min_detail,
            min_area=0.0, lod=GeometryType.LOD0, strict=False, remove_holes=remove_holes)
    except UnresolvedFootprintCleaningError as error:
        groups = deepcopy(error.diagnostics.get("unresolved_groups", []))
        identifiers = list(components)
        for group in groups:
            indices = group.get("source_indices", range(len(identifiers)))
            group["source_ids"] = sorted({mappings[identifiers[i]] for i in indices})
        raise ValueError(f"Unresolved footprint cleaning: {groups!r}") from error
    record = deepcopy(cleaned.attributes["footprint_cleaning"])
    blocks = {block.id: block for block in cleaned.buildings}
    fallbacks, cells, retained_components = {}, [], set()
    for cell in builder.building_cells(cleaned):
        if not cell.source_ids or any(value not in mappings for value in cell.source_ids):
            raise ValueError(f"Cleaned cell has unknown source attribution: {cell.source_ids}")
        retained_components.update(cell.source_ids)
        source_ids = tuple(sorted({mappings[value] for value in cell.source_ids}))
        height = cell.height
        wall_record = blocks[cell.building_id].attributes.get("footprint_walls", {})
        if wall_record.get("outcome") == "fallback":
            reason = wall_record.get("detail", "single-cell fallback")
            if settings.fallback == "error":
                raise ValueError(f"Footprint fallback for block {cell.building_id!r}, sources {source_ids}: {reason}")
            height = max(components[value][1] for value in cell.source_ids)
            # Integrate the original upper envelope within this output cell;
            # overlap volume is counted once, and newly occupied area starts at zero.
            occupied = Polygon()
            original_volume = 0.0
            for value in sorted(cell.source_ids, key=lambda v: -components[v][1]):
                polygon, h = components[value]
                original_volume += polygon.intersection(cell.polygon).difference(occupied).area * h
                occupied = occupied.union(polygon)
            fallback = fallbacks.setdefault(cell.building_id, dict(
                building_id=cell.building_id, source_ids=source_ids,
                reason=reason, height=height, upstream_height=cell.height,
                reference_volume_within_output=0., output_volume=0., added_volume=0.))
            fallback["reference_volume_within_output"] += original_volume
            fallback["output_volume"] += cell.polygon.area * height
            fallback["added_volume"] = fallback["output_volume"] - fallback["reference_volume_within_output"]
        if height is None or not np.isfinite(height) or height <= 0:
            raise ValueError(f"Invalid cleaned height for sources {source_ids}")
        cells.append(FootprintSolid(canonical_polygon(cell.polygon), float(height), source_ids,
            (cell.building_id,), () if cell.part_id is None else (cell.part_id,)))
    _validate_partition(cells)
    cells = _node_cells(cells)
    source_records = tuple(FootprintSource(source_id, tuple(r[0] for r in rows),
        unary_union([r[1] for r in rows]), rows[0][2], rows[0][3],
        (min(r[4][0] for r in rows), max(r[4][1] for r in rows)))
        for source_id, rows in sorted(sources.items()))
    excluded = {value: row["reason"] for row in record.get("excluded", []) for value in row["ids"]}
    accounting = []
    for source in source_records:
        indices = [i for i, cell in enumerate(cells) if source.source_id in cell.source_ids]
        reasons = sorted({excluded[c] for c in source.component_ids if c in excluded})
        status = "solid" if indices else "excluded" if all(c in excluded for c in source.component_ids) else "covered"
        accounting.append(dict(source_id=source.source_id, height=source.height,
            height_source=source.height_source, original_base_range=source.base_range,
            cells=indices, status=status,
            components={c: "solid" if c in retained_components else "excluded" if c in excluded
                        else "covered" for c in source.component_ids},
            excluded_components={c: excluded[c] for c in source.component_ids if c in excluded},
            reason=None if indices else "; ".join(reasons) or "covered by taller or equal-height sources"))
    metadata = dict(settings=asdict(settings), remove_holes=remove_holes, cleaning=record,
        component_sources=mappings, buildings=accounting,
        fallbacks=[fallbacks[key] for key in sorted(fallbacks)],
        counts=dict(sources=len(source_records), components=len(components), cells=len(cells),
            covered=sum(r["status"] == "covered" for r in accounting),
            excluded=sum(r["status"] == "excluded" for r in accounting), fallbacks=len(fallbacks)))
    if remove_holes:
        original_union = unary_union([polygon for polygon, _ in components.values()])
        pieces = [original_union] if isinstance(original_union, Polygon) else list(original_union.geoms)
        filled_union = unary_union([Polygon(p.exterior) for p in pieces if not p.is_empty])
        input_area = float(original_union.area)
        output_area = float(sum(c.polygon.area for c in cells))
        metadata["courtyards"] = dict(
            policy="fill_sources_and_cleaned_regions_preserve_partition_holes",
            input_geometry="source_holes_filled",
            input_occupied_area=input_area, input_union_void_area=float(filled_union.difference(original_union).area),
            cleaned_occupied_area=output_area, net_occupied_area_change=output_area-input_area,
            conditioned_region_filled_area=None,
            area_note="Core does not separately report final region filling area; net area change also includes conditioning and exclusions")
    return PreparedFootprints(source_records, cells, tuple(map(float, anchor)), geometry.crs,
        geometry.has_terrain, geometry.ignored_objects, metadata)


def merge_roof_cells(prepared, effective_faces):
    """Union cells in each cleaned block with the same float32 roof index.

    Faces must be the final effective grid faces, including any turbulence
    extension. This does not claim equivalence for arbitrary equal solid masks.
    """
    with np.errstate(over="ignore", invalid="ignore"):
        faces = np.asarray(effective_faces, dtype=np.float32)
    if (faces.ndim != 1 or len(faces) < 3 or not np.isfinite(faces).all()
            or faces[0] != 0 or np.any(np.diff(faces) <= 0)):
        raise ValueError("effective_faces must be finite, increasing faces starting at zero")
    with np.errstate(over="ignore", invalid="ignore"):
        centres = np.float32(0.5) * (faces[:-1] + faces[1:])
    if not np.isfinite(centres).all() or np.any(np.diff(centres) <= 0):
        raise ValueError("effective_faces produce collapsed or nonfinite float32 centres")
    groups = {}
    for cell in prepared.cells:
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            height = np.float32(cell.height)
        if not np.isfinite(height) or height <= 0:
            raise ValueError(f"Sources {cell.source_ids}: height must be positive finite float32")
        if height >= centres[-1]:
            raise ValueError(f"Sources {cell.source_ids}: roof needs clearance below the top cell centre")
        roof = int(np.searchsorted(centres, height, side="right"))
        groups.setdefault((cell.building_ids, roof), []).append(cell)
    solids = []
    for (_, roof), cells in groups.items():
        union = unary_union([c.polygon for c in cells])
        polygons = [union] if isinstance(union, Polygon) else list(union.geoms)
        for polygon in polygons:
            contributors = [c for c in cells if polygon.intersection(c.polygon).area > 0]
            solids.append(FootprintSolid(canonical_polygon(polygon),
                max(c.height for c in contributors),
                tuple(sorted({s for c in contributors for s in c.source_ids})),
                tuple(sorted({s for c in contributors for s in c.building_ids})),
                tuple(sorted({s for c in contributors for s in c.part_ids})), float(faces[roof])))
    _validate_partition(solids)
    return _node_cells(solids)


def finalize_footprints(prepared, *, effective_faces, origin, resolution, shape,
                        terrain=None, max_cells=20_000_000):
    """Build arrays on an already planned physical grid without allocating flow.

    ``origin`` is global (x, y, ground); ``shape`` is physical (nz, ny, nx).
    Use final effective faces, including any turbulence extension. Every ring
    is closed explicitly; building and ring offsets share the vertex array.
    """
    spacing = number(resolution, "resolution", positive=True)
    if spacing > np.finfo(np.float32).max or np.float32(spacing) <= 0:
        raise ValueError("resolution must be representable in float32")
    spacing = float(np.float32(spacing))
    with np.errstate(over="ignore", under="ignore", divide="ignore", invalid="ignore"):
        squared = np.float32(spacing) * np.float32(spacing)
        coefficient = np.float32(1) / squared
    if not np.isfinite(squared) or squared <= 0 or not np.isfinite(coefficient) or coefficient <= 0:
        raise ValueError("resolution cannot form finite positive float32 solver coefficients")
    if (len(shape) != 3 or any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Integral)
            or not 2 <= v <= 10000 for v in shape) or shape[1] < 3 or shape[2] < 3):
        raise ValueError("shape must contain physical integer (nz, ny, nx) grid dimensions")
    nz, ny, nx = map(int, shape)
    if (isinstance(max_cells, (bool, np.bool_)) or not isinstance(max_cells, Integral)
            or max_cells < 1 or nx*ny*nz > max_cells
            or (nx+1)*(ny+1)*(nz+2) > np.iinfo(np.int32).max):
        raise ValueError("Grid exceeds max_cells or the native index limit")
    origin = np.asarray(origin, dtype=np.float64)
    if origin.shape != (3,) or not np.isfinite(origin).all():
        raise ValueError("origin must be finite global (x, y, ground) coordinates")
    faces = np.asarray(effective_faces)
    if faces.ndim != 1 or len(faces) != nz+1:
        raise ValueError("effective_faces must match the physical z dimension")
    if prepared.has_terrain and terrain is None:
        raise ValueError("City has terrain; explicitly request terrain='flat' or a ground elevation")
    if terrain is None:
        for source in prepared.sources:
            lo, hi = source.base_range
            if hi-lo > 1e-6 or abs(lo-origin[2]) > 1e-6:
                raise ValueError(f"Building {source.source_id!r}: incompatible base elevation; explicitly request terrain='flat'")
    elif not (isinstance(terrain, str) and terrain == "flat"):
        ground = number(terrain, "terrain elevation")
        if abs(ground-origin[2]) > 1e-6:
            raise ValueError("Grid origin z must equal the flat ground elevation")
    solids = merge_roof_cells(prepared, effective_faces)
    polygons, rings, offsets, ring_offsets = [], [], [0], [0]
    rows = []
    for index, solid in enumerate(solids):
        local_rings = [np.asarray(r.coords) + (np.asarray(prepared.anchor)-origin[:2])
                       for r in [solid.polygon.exterior, *solid.polygon.interiors]]
        upper = np.asarray([nx, ny])*spacing - 2*spacing
        narrowed_rings = []
        for local in local_rings:
            if not np.isfinite(local).all() or np.any(local < 2*spacing) or np.any(local >= upper):
                raise ValueError(f"Sources {solid.source_ids}: footprint needs two cells of clearance")
            narrowed = local.astype(np.float32).astype(np.float64)
            if np.any(narrowed < 2*spacing) or np.any(narrowed >= upper):
                raise ValueError(f"Sources {solid.source_ids}: footprint needs two cells of clearance after float32 conversion")
            if np.any(np.all(narrowed[1:] == narrowed[:-1], axis=1)):
                raise ValueError(f"Sources {solid.source_ids}: footprint loses valid edges or area at float32 precision")
            narrowed_rings.append(narrowed)
            rings.append(local)
            ring_offsets.append(ring_offsets[-1]+len(local))
        polygon = Polygon(narrowed_rings[0], narrowed_rings[1:])
        if (not polygon.is_valid or polygon.area <= 0 or polygon.exterior.is_ccw
                or any(not r.is_ccw for r in polygon.interiors)):
            raise ValueError(f"Sources {solid.source_ids}: footprint loses valid edges or area at float32 precision")
        polygons.append(replace(solid, polygon=polygon))
        offsets.append(ring_offsets[-1])
        rows.append(dict(native_id=index, source_ids=list(solid.source_ids),
            building_ids=list(solid.building_ids), part_ids=list(solid.part_ids),
            height=solid.height, native_height=float(np.float32(solid.height)),
            area=solid.polygon.area, native_area=polygon.area,
            represented_roof=solid.represented_roof, roof_error=solid.represented_roof-solid.height))
    _validate_partition(polygons)
    arrays = dict(vertices=np.ascontiguousarray(np.concatenate(rings) if rings else np.empty((0, 2))),
        offsets=np.asarray(offsets, dtype=np.int64), heights=np.asarray([c.height for c in solids], dtype=np.float64),
        base_heights=np.zeros(len(solids), dtype=np.float64), ids=np.arange(len(solids), dtype=np.int64),
        ring_offsets=np.asarray(ring_offsets,dtype=np.int64))
    metadata = deepcopy(prepared.metadata)
    metadata["solids"] = rows
    metadata["counts"].update(solids=len(solids), merges=len(prepared.cells)-len(solids))
    metadata["grid"] = dict(origin=origin.tolist(), shape=[nz, ny, nx], resolution=spacing,
        effective_faces=np.asarray(effective_faces, dtype=np.float32).astype(float).tolist())
    for source in metadata["buildings"]:
        source["solids"] = [i for i, c in enumerate(solids) if source["source_id"] in c.source_ids]
    return FinalizedFootprints(solids, arrays, metadata)


def prepare_footprint_domain(city, height_policy, settings, **options):
    """Plan and finalize the same solids, including turbulence's mean height.

    Automatic layers can depend on the roof heights that are merged on those
    layers. Iterate until geometry and heights used by the planner agree with
    the final solids; fail explicitly if that dependency cannot stabilize.
    """
    prepared = prepare_footprints(city, height_policy, settings=settings)
    return plan_footprint_domain(prepared, **options)


def plan_footprint_domain(prepared, **options):
    """Plan a cleaned collection to stability without repeating cleaning."""
    from ._city import CityGeometry, prepare_domain
    if not isinstance(prepared, PreparedFootprints):
        raise TypeError("prepared must be PreparedFootprints")
    solids = prepared.cells
    signatures = set()
    for _ in range(16):
        signature = tuple((c.height,c.polygon.wkb) for c in solids)
        if signature in signatures:
            raise ValueError("Footprint/grid planning did not stabilize; use explicit vertical faces")
        signatures.add(signature)
        geometry = CityGeometry(
            tuple(np.asarray(c.polygon.exterior.coords)+prepared.anchor for c in solids),
            tuple(c.height for c in solids),
            tuple((0.,0.) for c in solids), tuple(str(i) for i in range(len(solids))),
            tuple("canonical" for c in solids), prepared.crs, prepared.has_terrain,
            tuple(0 for c in solids), prepared.ignored_objects)
        domain = prepare_domain(geometry, _footprints=prepared, **options)
        final = domain.footprints
        if signature == tuple((c.height,c.polygon.wkb) for c in final.solids):
            return geometry, domain
        solids = final.solids
    raise ValueError("Footprint/grid planning exceeded 16 passes; use explicit vertical faces")

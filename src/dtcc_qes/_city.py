"""Read canonical DTCC geometry without mutating or simplifying the city."""

from dataclasses import dataclass
import math
from numbers import Real

import numpy as np
from pyproj import CRS
from shapely.geometry import Point, Polygon
from shapely.geometry.polygon import orient
from shapely.strtree import STRtree
from shapely.validation import explain_validity

from dtcc_core.model import Building, BuildingPart, City, Surface, Terrain

from . import _qes
from .vertical_grid import effective_faces
from ._turbulence_domain import (check_turbulence_faces, extend_turbulence_faces,
                                turbulence_reference_height, turbulence_top)


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


def near_contacts(city, resolution):
    """Report strict-mode pairs separated by less than one horizontal cell."""
    if not city.rings:
        return ()
    anchor = np.min(np.concatenate(city.rings), axis=0)
    polygons = [Polygon(ring - anchor) for ring in city.rings]
    tree = STRtree(polygons)
    rows = []
    for i, polygon in enumerate(polygons):
        for j in tree.query(polygon.buffer(resolution).envelope):
            if j <= i:
                continue
            distance = polygon.distance(polygons[j])
            if distance < resolution:
                rows.append(dict(source_ids=[city.source_ids[i], city.source_ids[j]], distance=distance))
    return tuple(rows)


def _validate_city_objects(city):
    """Validate source identities and reject buildings hidden in object trees."""
    if not isinstance(city, City):
        raise TypeError("city must be a dtcc_core.model.City")
    children = [child for group in city.children.values() for child in group]
    parts = [child for child in children if isinstance(child, BuildingPart)]
    if parts:
        raise ValueError(f"BuildingPart {parts[0].id!r} is unsupported; supply complete LOD0 buildings")
    buildings = [child for child in children if isinstance(child, Building)]
    pending = [child for child in children if not isinstance(child, (Building, BuildingPart))]
    seen_ids = set()
    for building in buildings:
        label = f"Building {building.id!r}"
        if not isinstance(building.id, str) or not building.id or building.id in seen_ids:
            raise ValueError(f"{label}: source IDs must be unique nonempty strings")
        seen_ids.add(building.id)
        descendants = [child for group in building.children.values() for child in group]
        if any(isinstance(child, (Building, BuildingPart)) for child in descendants):
            raise ValueError(f"{label}: building parts are unsupported; supply one complete LOD0 footprint")
        pending.extend(descendants)
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
    return children, buildings


def extract_city(city, height_policy, *, _allow_contacts=False):
    if not isinstance(city, City):
        raise TypeError("city must be a dtcc_core.model.City")
    if height_policy not in ("measured", "allow_estimated"):
        raise ValueError("height_policy must be 'measured' or 'allow_estimated'")
    city_frame = _frame(city.transform, "City")
    children, buildings = _validate_city_objects(city)
    rings, heights, ranges, ids, sources, systems, removed = [], [], [], [], [], [], []
    for building in buildings:
        label = f"Building {building.id!r}"
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
    if rings and not _allow_contacts:
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


@dataclass(frozen=True)
class PreparedDomain:
    grid: object
    model: object
    arrays: dict
    origin: tuple[float, float, float]
    resolution: float
    domain: dict
    terrain: dict
    dz_layers: np.ndarray | None = None
    footprints: object | None = None
    near_contacts: tuple = ()


def default_domain_top(heights, reference_height, vertical_clearance, spacing, *, turbulence_reference=None):
    """Local minimum domain top, shared by the city and dataset adapters."""
    top = max(max(heights, default=0.0) + max(vertical_clearance, spacing),
              reference_height, 2 * spacing)
    return top if turbulence_reference is None else max(top, turbulence_top(turbulence_reference, spacing))


def prepare_domain(city: CityGeometry, *, reference_height, roughness_length, resolution,
                   bounds, horizontal_padding, vertical_clearance, max_cells, terrain, vertical_grid=None,
                   turbulence=False, _footprints=None):
    if not isinstance(turbulence, bool):
        raise ValueError("turbulence must be a bool")
    z_ref = turbulence_reference_height(city.heights, roughness_length) if turbulence else None
    if city.has_terrain and terrain is None:
        raise ValueError("City has terrain; pass terrain='flat' or a ground elevation to explicitly accept flattening")
    if not city.rings and bounds is None:
        raise ValueError("An empty city requires explicit grid bounds")
    base_ranges = city.base_ranges if _footprints is None else tuple(s.base_range for s in _footprints.sources)
    base_ids = city.source_ids if _footprints is None else tuple(s.source_id for s in _footprints.sources)
    base = min((lo for lo, _ in base_ranges), default=bounds[2] if bounds else 0.0)
    if terrain is None:
        for source_id, (lo, hi) in zip(base_ids, base_ranges):
            if hi - lo > 1e-6 or abs(lo - base) > 1e-6:
                raise ValueError(f"Building {source_id!r}: incompatible base elevation; explicitly request terrain='flat' to flatten")
    elif terrain != "flat":
        base = terrain
    elif bounds:
        base = bounds[2]
    if bounds and abs(bounds[2] - base) > 1e-6:
        raise ValueError("Grid zmin must equal the flat ground elevation")
    spacing = float(np.float32(resolution))
    fixed_top = bounds is not None and bounds[5] is not None
    if bounds:
        origin = (bounds[0], bounds[1], base)
        extents = (bounds[3] - origin[0], bounds[4] - origin[1],
                   bounds[5] - base if fixed_top else
                   default_domain_top(city.heights, reference_height, vertical_clearance, spacing))
        padding = None
    else:
        xy = np.concatenate(city.rings)
        padding = max(horizontal_padding, 3 * spacing)
        if padding > 5000 * spacing:
            raise ValueError("Horizontal padding exceeds the native 10000-cell dimension limit")
        lower, upper = xy.min(axis=0) - padding, xy.max(axis=0) + padding
        origin = (float(lower[0]), float(lower[1]), base)
        extents = (float(upper[0] - lower[0]), float(upper[1] - lower[1]),
                   default_domain_top(city.heights, reference_height, vertical_clearance, spacing))
    automatic_metadata = None
    regeneration = None
    if vertical_grid is not None and vertical_grid.mode == "auto":
        from ._auto_grid import AutomaticGridFitError, generate_auto_layers
        settings = vertical_grid._automatic
        try:
            layers, automatic_metadata = generate_auto_layers(settings,
                resolution=spacing, top=extents[2], heights=city.heights)
        except AutomaticGridFitError as error:
            # A valid wind-only prefix is always retained. Only endpoint-fit
            # failures can be recovered by selecting a higher initial top.
            if not turbulence or fixed_top:
                raise
            target = max(default_domain_top(city.heights, reference_height, vertical_clearance,
                spacing, turbulence_reference=z_ref), error.minimum_top)
            for attempt in range(1,10001):
                try:
                    layers, automatic_metadata = generate_auto_layers(settings,
                        resolution=spacing, top=target, heights=city.heights)
                    break
                except AutomaticGridFitError as retry:
                    # The generator supplies the next feasible endpoint for
                    # its fine band/count. Each retry must make progress.
                    if retry.minimum_top <= target:
                        raise ValueError("Turbulence regeneration cannot make endpoint progress") from retry
                    target = retry.minimum_top
            else:
                raise ValueError("Turbulence regeneration exceeds the 10000-attempt limit")
            regeneration = dict(reason=str(error), requested_top=extents[2],
                                generated_top=target, generated_layers=len(layers), attempts=attempt)
    else:
        layers = None if vertical_grid is None else vertical_grid.layers
    if layers is not None and automatic_metadata is None:
        requested_top = vertical_grid.faces[-1]
        if fixed_top:
            # Compare the requested physical endpoints before float32 narrowing.
            # Permit only float64 subtraction error in translated global bounds.
            tolerance = 4 * max(abs(np.spacing(origin[2])), abs(np.spacing(bounds[5])),
                                abs(np.spacing(requested_top)))
            if abs(requested_top - extents[2]) > tolerance:
                raise ValueError("Explicit z_faces top must match bounds height above flat ground")
        elif requested_top < extents[2]:
            raise ValueError("Explicit z_faces top must cover the required clearance and reference height")
    counts = []
    for axis, extent in zip("xyz", extents):
        if axis == "z" and layers is not None:
            counts.append(len(layers))
            continue
        ratio = extent / spacing
        if not math.isfinite(ratio) or ratio > 10000:
            raise ValueError(f"Grid {axis} dimension exceeds the native 10000-cell limit")
        counts.append(math.ceil(ratio))
    nx, ny, nz = counts
    if nx < 3 or ny < 3 or nz < 2:
        raise ValueError("Grid needs at least three cells in x/y and two in z")
    if nx * ny * nz > max_cells or (nx + 1) * (ny + 1) * (nz + 2) > np.iinfo(np.int32).max:
        raise ValueError("Grid exceeds max_cells or the native index limit; increase resolution or reduce bounds")
    effective = tuple(count * spacing for count in counts)
    # Match QES's accumulated float32 vertical coordinates for the roof check.
    if layers is None:
        faces = np.r_[np.float32(0), np.cumsum(np.full(nz, spacing, dtype=np.float32), dtype=np.float32)]
        vertical_metadata = dict(mode="uniform", uniform=True)
    else:
        faces = effective_faces(layers)
        effective = (*effective[:2], float(faces[-1]))
        vertical_metadata = vertical_grid.to_metadata()
        if automatic_metadata is not None:
            vertical_metadata.update(automatic_metadata)
    wind_only_top = float(faces[-1])
    turbulence_metadata = None
    if turbulence:
        default_top = extents[2] if regeneration is not None else float(faces[-1])
        original_count = nz
        thickness = spacing if layers is None else layers[-1]
        explicit = fixed_top or (vertical_grid is not None and vertical_grid.mode == "explicit")
        if explicit:
            check_turbulence_faces(faces, z_ref, last_thickness=thickness, nx=nx, ny=ny, max_cells=max_cells)
        else:
            faces = extend_turbulence_faces(faces, z_ref, thickness, nx=nx, ny=ny, max_cells=max_cells)
            nz = len(faces)-1
            if layers is not None and nz != original_count:
                layers = np.r_[layers, np.full(nz-original_count, layers[-1], dtype=np.float64)]
                # Constant thickness inherits the final layer's valid minimum,
                # aspect, growth and cap constraints: all upper caps are
                # nondecreasing. Revalidate native arithmetic on the final grid.
                faces = effective_faces(layers)
                planned = np.r_[0., np.cumsum(layers)]
                unit_roundoff = float(np.finfo(np.float32).eps)/2
                gamma = (nz+1)*unit_roundoff/(1-(nz+1)*unit_roundoff)
                vertical_metadata.update(planned_faces=planned.tolist(),
                    solver_layer_thicknesses=layers.astype(np.float32).astype(float).tolist(),
                    base_endpoint_fit=vertical_metadata["endpoint_fit"],
                    endpoint_fit=dict(method="prefix-preserving constant tail", tail_start_index=original_count,
                        requested_top=float(planned[-1]), planned_top=float(planned[-1]),
                        effective_top=float(faces[-1]), coordinate_error=float(faces[-1])-float(planned[-1]),
                        accumulation_tolerance=gamma*float(planned[-1])))
        counts = [nx,ny,nz]
        effective = (*effective[:2], float(faces[-1]))
        turbulence_metadata = dict(reference_height=z_ref, required_top=float(faces[-1]),
            default_top=default_top, effective_top=float(faces[-1]),
            raised=bool(nz > original_count or regeneration is not None), added_layers=nz-original_count,
            lower_layers_preserved=regeneration is None,
            extension_policy="check_only" if explicit else "constant_last_thickness")
        if regeneration is not None:
            turbulence_metadata.update(extension_policy="regenerated_then_constant_last_thickness",
                                       regeneration=regeneration)
    vertical_metadata.update(effective_faces=faces.tolist(),
        min_thickness=float(np.diff(faces).min()), max_thickness=float(np.diff(faces).max()))
    solver_layers = np.full(nz, spacing, dtype=np.float32) if layers is None else layers.astype(np.float32)
    vertical_metadata.update(max_growth_ratio=float(np.max(solver_layers[1:] / solver_layers[:-1])),
        max_thin_cell_aspect_ratio=float(spacing / solver_layers.min()),
        max_tall_cell_aspect_ratio=float(solver_layers.max() / spacing))
    centres_z = np.float32(0.5) * (faces[:-1] + faces[1:])
    top_requirements = dict(height_datum="metres above flat ground", fixed_top=bool(
            fixed_top or vertical_grid is not None and vertical_grid.mode == "explicit"),
        requested_top=vertical_grid.faces[-1] if vertical_grid is not None and
            vertical_grid.mode == "explicit" else extents[2], effective_top=float(faces[-1]),
        roof_clearance=dict(minimum_top=max(city.heights,default=0.) + max(vertical_clearance,spacing),
                            clearance=max(vertical_clearance,spacing), applied=not fixed_top),
        profile_reference=dict(minimum_top=reference_height, applied=not fixed_top),
        minimum_cells=dict(count=2, minimum_top=None if fixed_top and layers is not None else 2*spacing,
                           applied=True),
        auto_grid_endpoint_fit=None if automatic_metadata is None else dict(
            target_top=regeneration["generated_top"] if regeneration is not None else extents[2],
            effective_top_before_turbulence=wind_only_top,
            endpoint_fit=vertical_metadata.get("base_endpoint_fit",vertical_metadata["endpoint_fit"]),
            regeneration=regeneration),
        turbulence_reference=None if not turbulence else dict(reference_height=z_ref,
            required_layers_above=2, minimum_margin_face=z_ref, effective_margin_face=float(faces[-4])),
        turbulence_rotation_15m=None if not turbulence else dict(minimum_top=15.))
    vertical_metadata["roof_representation"] = [
        dict(source_id=source_id, requested_height=height,
             represented_height=float(faces[np.searchsorted(centres_z, np.float32(height), side="right")]),
             error=float(faces[np.searchsorted(centres_z, np.float32(height), side="right")]) - height)
        for source_id, height in zip(city.source_ids, city.heights)
    ]
    final_footprints = None
    if _footprints is not None:
        from ._footprints import finalize_footprints
        final_footprints = finalize_footprints(_footprints, effective_faces=faces,
            origin=origin, resolution=spacing, shape=(nz,ny,nx), terrain=terrain, max_cells=max_cells)
        local_rings = [np.asarray(c.polygon.exterior.coords)+np.asarray(_footprints.anchor)-origin[:2]
                       for c in final_footprints.solids]
        vertical_metadata["roof_representation"] = [dict(native_id=r["native_id"],
            source_ids=r["source_ids"], requested_height=r["height"],
            represented_height=r["represented_roof"], error=r["roof_error"])
            for r in final_footprints.metadata["solids"]]
    else:
        top_centre = float(np.float32(0.5) * (faces[-2] + faces[-1]))
        local_rings, narrowed_polygons, offsets = [], [], [0]
        for source_id, ring, height in zip(city.source_ids, city.rings, city.heights):
            local = ring - np.asarray(origin[:2], dtype=np.float64)
            if (not np.isfinite(local).all() or np.any(local < 2 * spacing)
                    or np.any(local >= np.asarray(effective[:2]) - 2 * spacing)):
                raise ValueError(f"Building {source_id!r}: footprint needs two cells of clearance inside the effective bounds")
            narrowed = local.astype(np.float32).astype(np.float64)
            if (np.any(narrowed < 2 * spacing)
                    or np.any(narrowed >= np.asarray(effective[:2]) - 2 * spacing)):
                raise ValueError(f"Building {source_id!r}: footprint needs two cells of clearance inside the effective bounds")
            if np.float32(height) >= top_centre:
                raise ValueError(f"Building {source_id!r}: roof needs clearance below the top physical cell centre")
            polygon = Polygon(narrowed)
            if (np.any(np.all(narrowed[1:] == narrowed[:-1], axis=1))
                    or not polygon.is_valid or polygon.area <= 0 or polygon.exterior.is_ccw):
                raise ValueError(f"Building {source_id!r}: footprint loses valid edges or area at float32 precision")
            local_rings.append(local)
            narrowed_polygons.append(polygon)
            offsets.append(offsets[-1] + len(local))
        reject_intersections(narrowed_polygons, city.source_ids, context=" after float32 conversion")
    native_grid = _qes.GridConfig()
    native_grid.nx, native_grid.ny, native_grid.nz = counts
    native_grid.cell_size, native_grid.max_cells = spacing, max_cells
    model = _qes.ModelSettings()
    model.roughness_length = roughness_length
    model.sensor_x = (min(5, nx - 1) + 0.5) * spacing
    model.sensor_y = (min(15, ny - 1) + 0.5) * spacing
    if any(Polygon(ring).covers(Point(model.sensor_x, model.sensor_y)) for ring in local_rings):
        model.sensor_x = model.sensor_y = 0.5 * spacing
    if final_footprints is not None:
        arrays = final_footprints.arrays
        model.exposed_faces = _footprints.metadata["settings"]["exposed_faces"]
    else:
        arrays = dict(vertices=np.ascontiguousarray(np.concatenate(local_rings) if local_rings else np.empty((0, 2)), dtype=np.float64),
                      offsets=np.asarray(offsets, dtype=np.int64), heights=np.asarray(city.heights, dtype=np.float64),
                      base_heights=np.zeros(len(city.rings), dtype=np.float64), ids=np.arange(len(city.rings), dtype=np.int64))
    return PreparedDomain(native_grid, model, arrays, origin, spacing,
                          dict(requested_bounds=bounds, local_bounds=(0.0, 0.0, 0.0, *effective),
                               effective_bounds=(*origin, *(origin[i] + effective[i] for i in range(3))),
                               shape=(nz, ny, nx), requested_resolution=resolution, resolution=spacing,
                               top_requirements=top_requirements,
                               vertical_grid=vertical_metadata,
                               **({"turbulence": turbulence_metadata} if turbulence else {}),
                               **({"footprints": final_footprints.metadata} if final_footprints is not None else {}),
                               effective_horizontal_padding=padding, max_cells=max_cells),
                          dict(model="flat", elevation=base, flattening_requested=terrain is not None,
                               city_terrain_ignored=city.has_terrain, base_elevation_tolerance=1e-6,
                               base_elevations_flattened=any(abs(lo - base) > 1e-6 or abs(hi - base) > 1e-6
                                                            for lo, hi in base_ranges)), layers, final_footprints)

"""Adapt Core's cleaned city blocks to the QES flat-ground input contract."""

from copy import deepcopy

import numpy as np
from pyproj import CRS
from shapely.geometry import Polygon

from dtcc_core import builder
from dtcc_core.model import Building, City, GeometryType, MultiSurface, Surface, Transform

from ._city import _frame, _resolve_frame, default_domain_top, extract_city, number


def _fill_courtyards(surface, source_id, record):
    if surface.holes:
        record.append({"source_id": source_id, "hole_count": len(surface.holes),
                       "filled_area": sum(float(Polygon(hole[:, :2]).area) for hole in surface.holes)})
        surface.holes = []


def _source_city(source, filled):
    """Copy source footprints into the provider's global EPSG:3006 frame."""
    if not isinstance(source, City):
        raise TypeError("The city dataset must return a dtcc_core.model.City")
    prepared = City(transform=Transform(srs="EPSG:3006"))
    city_frame = _frame(source.transform, "City")
    for building in source.buildings:
        if building.building_parts:
            raise ValueError(f"Source building {building.id!r} has unsupported building parts")
        geometry = building.get_geometry(lod="0")
        surfaces = geometry.surfaces if isinstance(geometry, MultiSurface) else [geometry]
        copied = []
        for surface in surfaces:
            if not isinstance(surface, Surface):
                raise ValueError(f"Source building {building.id!r} has no LOD0 footprint")
            frames = [city_frame, _frame(building.transform, building.id)]
            if isinstance(geometry, MultiSurface):
                frames.append(_frame(geometry.transform, building.id))
            offset, crs = _resolve_frame([*frames, _frame(surface.transform, building.id)], building.id)
            if crs is not None and not crs.equals(CRS.from_epsg(3006)):
                raise ValueError("Fetched city geometry must use EPSG:3006")
            copy = Surface(vertices=np.asarray(surface.vertices, dtype=float).copy() + offset,
                           holes=[np.asarray(hole, dtype=float).copy() + offset for hole in surface.holes])
            _fill_courtyards(copy, building.id, filled)
            copied.append(copy)
        height = building.measured_height if building.measured_height is not None else building.estimated_height
        number(height, f"Building {building.id!r} height", positive=True)
        copy = Building(id=building.id, attributes=deepcopy(building.attributes))
        copy.add_geometry(copied[0] if len(copied) == 1 else MultiSurface(surfaces=copied), GeometryType.LOD0)
        prepared.add_building(copy)
    return prepared


def _ground_elevation(source, prepared):
    terrain = source.terrain
    raster = terrain.raster if terrain is not None else None
    if raster is not None:
        values = np.asarray(raster.data)
        valid = np.isfinite(values) & (values != raster.nodata)
        if not np.any(valid):
            raise ValueError("City terrain has no valid elevations")
        offset, _ = _resolve_frame([_frame(source.transform, "City"),
                                   _frame(terrain.transform, "Terrain")], "Terrain")
        return float(values[valid].min()) + float(offset[2])
    if prepared.buildings:
        return min(float(b.lod0.bounds.zmin) for b in prepared.buildings)
    raise ValueError("An empty city without terrain needs 3D bounds to define ground elevation")


def prepare_city(source, args):
    filled = []
    prepared = _source_city(source, filled)
    ground = float(args.bounds[2]) if len(args.bounds) == 6 else _ground_elevation(source, prepared)
    cleaned = builder.clean_footprints(prepared, min_building_detail=args.min_building_detail,
                                       min_area=0.0, lod=GeometryType.LOD0, strict=True, remove_holes=True)
    city = City(transform=Transform(srs="EPSG:3006"))
    blocks = []
    for block in cleaned.buildings:
        surface = block.get_geometry(lod="0")
        if not isinstance(surface, Surface):
            raise ValueError(f"Core cleaning did not produce one Surface for block {block.id!r}")
        surface = deepcopy(surface)
        _fill_courtyards(surface, block.id, filled)
        # Core owns block heights and merging. QES consumes the block envelope;
        # its parts and source geometry remain represented in provenance.
        building = Building(id=block.id, attributes=deepcopy(block.attributes))
        building.add_geometry(surface, GeometryType.LOD0)
        city.add_building(building)
        blocks.append({"id": block.id, "source_ids": block.attributes.get("merged_from", [block.id]),
                       "measured_height": block.measured_height, "estimated_height": block.estimated_height})
    geometry = extract_city(city, "allow_estimated")
    xy_bounds = np.asarray(args.bounds)[[0, 1, 2, 3] if len(args.bounds) == 4 else [0, 1, 3, 4]]
    lower, upper = xy_bounds[:2].copy(), xy_bounds[2:].copy()
    if geometry.rings:
        xy = np.concatenate(geometry.rings)
        lower, upper = np.minimum(lower, xy.min(axis=0)), np.maximum(upper, xy.max(axis=0))
    spacing = float(np.float32(args.resolution))
    padding = max(args.horizontal_padding, 3 * spacing)
    lower, upper = lower - padding, upper + padding
    top = (float(args.bounds[5]) if len(args.bounds) == 6 else ground + default_domain_top(
        geometry.heights, args.reference_condition()["height"], args.vertical_clearance, spacing))
    bounds = (float(lower[0]), float(lower[1]), ground, float(upper[0]), float(upper[1]), top)
    return city, bounds, {
        "crs": "EPSG:3006", "ground_elevation": ground,
        "source_terrain_flattened": source.has_terrain(),
        "horizontal_padding": padding, "bounds": list(bounds),
        "footprint_cleaning": deepcopy(cleaned.attributes["footprint_cleaning"]),
        "filled_courtyards": filled, "blocks": blocks,
        "block_height_policy": "dtcc-core cleaned block heights; measured then estimated",
    }

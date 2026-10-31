"""Prepare fetched sources, ground and bounds for the canonical-solid pipeline."""

from copy import deepcopy

import numpy as np
from pyproj import CRS
from shapely.geometry import Polygon

from dtcc_core.model import (
    Building,
    City,
    GeometryType,
    MultiSurface,
    Surface,
    Transform,
)

from ._city import _frame, _resolve_frame, _validate_city_objects, default_domain_top
from ._footprints import prepare_footprints, _resolved_surfaces
from .footprints import Footprints


def _record_courtyards(surface, source_id, record):
    if surface.holes:
        record.append(
            {
                "source_id": source_id,
                "hole_count": len(surface.holes),
                "filled_area": sum(float(Polygon(hole[:, :2]).area) for hole in surface.holes),
            }
        )


def _source_city(source, filled):
    """Copy source footprints into the provider's global EPSG:3006 frame."""
    _validate_city_objects(source)
    prepared = City(transform=Transform(srs="EPSG:3006"))
    city_frame = _frame(source.transform, "City")
    for building in source.buildings:
        copied = []
        for rings, crs in _resolved_surfaces(building, city_frame):
            if crs is not None and not crs.equals(CRS.from_epsg(3006)):
                raise ValueError("Fetched city geometry must use EPSG:3006")
            copy = Surface(vertices=rings[0], holes=rings[1:])
            _record_courtyards(copy, building.id, filled)
            copied.append(copy)
        copy = Building(id=building.id, attributes=deepcopy(building.attributes))
        copy.add_geometry(
            copied[0] if len(copied) == 1 else MultiSurface(surfaces=copied),
            GeometryType.LOD0,
        )
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
        offset, _ = _resolve_frame(
            [_frame(source.transform, "City"), _frame(terrain.transform, "Terrain")],
            "Terrain",
        )
        return float(values[valid].min()) + float(offset[2])
    if prepared.buildings:
        return min(
            float(np.asarray(ring)[:, 2].min())
            for building in prepared.buildings
            for surface in (
                building.lod0.surfaces if isinstance(building.lod0, MultiSurface) else [building.lod0]
            )
            for ring in [surface.vertices, *surface.holes]
        )
    raise ValueError("An empty city without terrain needs 3D bounds to define ground elevation")


def prepare_city(source, args):
    filled = []
    prepared = _source_city(source, filled)
    ground = float(args.bounds[2]) if len(args.bounds) == 6 else _ground_elevation(source, prepared)
    settings = Footprints(min_detail=args.min_building_detail, exposed_faces=True, fallback="tallest")
    footprints = prepare_footprints(prepared, "allow_estimated", settings=settings, remove_holes=True)
    xy_bounds = np.asarray(args.bounds)[[0, 1, 2, 3] if len(args.bounds) == 4 else [0, 1, 3, 4]]
    lower, upper = xy_bounds[:2].copy(), xy_bounds[2:].copy()
    if footprints.cells:
        xy = (
            np.concatenate([np.asarray(c.polygon.exterior.coords) for c in footprints.cells])
            + footprints.anchor
        )
        lower, upper = (
            np.minimum(lower, xy.min(axis=0)),
            np.maximum(upper, xy.max(axis=0)),
        )
    spacing = float(np.float32(args.resolution))
    padding = max(args.horizontal_padding, 3 * spacing)
    lower, upper = lower - padding, upper + padding
    top = (
        float(args.bounds[5])
        if len(args.bounds) == 6
        else ground
        + default_domain_top(
            [c.height for c in footprints.cells],
            args.reference_condition()["height"],
            args.vertical_clearance,
            spacing,
        )
    )
    bounds = (
        float(lower[0]),
        float(lower[1]),
        ground,
        float(upper[0]),
        float(upper[1]),
        top,
    )
    return (
        footprints,
        bounds,
        {
            "schema_version": 2,
            "pipeline": "canonical-cells-v1",
            "crs": "EPSG:3006",
            "ground_elevation": ground,
            "source_terrain_flattened": source.has_terrain(),
            "horizontal_padding": padding,
            "bounds": list(bounds),
            "footprint_cleaning": deepcopy(footprints.metadata["cleaning"]),
            "footprint_settings": deepcopy(footprints.metadata["settings"]),
            "courtyard_policy": deepcopy(footprints.metadata["courtyards"]),
            "filled_courtyards": filled,
            "source_courtyard_filled_area": sum(row["filled_area"] for row in filled),
            "height_policy": "allow_estimated",
        },
    )

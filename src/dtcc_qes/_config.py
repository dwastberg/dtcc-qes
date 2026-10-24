"""Public option validation and conversion to the private numerical contract."""

from dataclasses import dataclass
import math
from numbers import Integral

import numpy as np
from dtcc_core.model import Bounds
from shapely.geometry import Point, Polygon

from . import _qes
from ._city import CityGeometry, number, reject_intersections


@dataclass(frozen=True)
class WindCondition:
    """Neutral log-law wind: speed in m/s, meteorological direction in degrees.

    Direction is clockwise from north and denotes where wind comes from.
    Heights and roughness are metres above the flat ground plane.
    """
    speed: float
    direction: float
    reference_height: float = 10.0
    roughness_length: float = 0.1

    def __post_init__(self):
        for name in ("speed", "direction", "reference_height", "roughness_length"):
            value = number(getattr(self, name), name, positive=name in ("reference_height", "roughness_length"))
            if abs(value) > float(np.finfo(np.float32).max):
                raise ValueError(f"{name} must be representable in float32")
            object.__setattr__(self, name, value)
        if self.speed < 0 or not 0 <= self.direction < 360:
            raise ValueError("speed must be nonnegative and direction must be in [0, 360)")
        height, roughness = float(np.float32(self.reference_height)), float(np.float32(self.roughness_length))
        if roughness <= 0 or height <= 0 or height + roughness > float(np.finfo(np.float32).max):
            raise ValueError("Reference height and roughness must form a finite float32 profile")
        ratio = float(np.float32(height + roughness)) / roughness
        if not 1 < ratio <= float(np.finfo(np.float32).max) or np.float32(ratio) <= 1:
            raise ValueError("Reference height and roughness must form a finite float32 log profile")


@dataclass(frozen=True)
class GridSpec:
    """Uniform cells in metres, with bounds in the input's global frame.

    Bounds are DTCC Bounds or (xmin, ymin, zmin, xmax, ymax, zmax). Lower
    bounds define the local origin; upper bounds expand to whole cells.
    Automatic bounds use at least three cells of horizontal padding.
    """
    resolution: float = 2.0
    bounds: tuple[float, float, float, float, float, float] | Bounds | None = None
    horizontal_padding: float = 20.0
    vertical_clearance: float = 20.0
    max_cells: int = 20000000

    def __post_init__(self):
        for name in ("resolution", "horizontal_padding", "vertical_clearance"):
            value = number(getattr(self, name), name, positive=name == "resolution")
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")
            object.__setattr__(self, name, value)
        if (isinstance(self.max_cells, (bool, np.bool_)) or not isinstance(self.max_cells, Integral)
                or not 1 <= self.max_cells <= np.iinfo(np.int64).max):
            raise ValueError("max_cells must be a positive int64 integer")
        object.__setattr__(self, "max_cells", int(self.max_cells))
        # Match the native coefficient check without overflowing float casts.
        limit = float(np.finfo(np.float32).max)
        if not math.sqrt(1 / limit) <= self.resolution <= math.sqrt(limit):
            raise ValueError("resolution cannot form finite float32 solver coefficients")
        if self.bounds is not None:
            values = self.bounds
            if isinstance(values, Bounds):
                values = (values.xmin, values.ymin, values.zmin, values.xmax, values.ymax, values.zmax)
            try:
                values = tuple(number(value, "bounds") for value in values)
            except TypeError as error:
                raise ValueError("bounds must contain six finite coordinates") from error
            if len(values) != 6 or any(values[i + 3] <= values[i] for i in range(3)):
                raise ValueError("bounds must be (xmin, ymin, zmin, xmax, ymax, zmax) with positive extents")
            object.__setattr__(self, "bounds", values)


@dataclass(frozen=True)
class SolverOptions:
    """CPU convergence control; the metric is multiplier change."""
    tolerance: float = 1e-5
    max_iterations: int = 500
    raise_on_nonconvergence: bool = True

    def __post_init__(self):
        tolerance = number(self.tolerance, "tolerance", positive=True)
        if not float(np.finfo(np.float32).eps) <= tolerance <= float(np.finfo(np.float32).max):
            raise ValueError("tolerance must be at least float32 epsilon and finite in float32")
        if (isinstance(self.max_iterations, (bool, np.bool_)) or not isinstance(self.max_iterations, Integral)
                or not 1 <= self.max_iterations <= np.iinfo(np.int32).max):
            raise ValueError("max_iterations must be a positive int32 integer")
        if not isinstance(self.raise_on_nonconvergence, bool):
            raise ValueError("raise_on_nonconvergence must be a bool")
        object.__setattr__(self, "tolerance", tolerance)
        object.__setattr__(self, "max_iterations", int(self.max_iterations))


@dataclass(frozen=True)
class FlatTerrain:
    """Explicitly flatten terrain and building bases to this global elevation."""
    elevation: float = 0.0

    def __post_init__(self):
        object.__setattr__(self, "elevation", number(self.elevation, "elevation"))


@dataclass(frozen=True)
class PreparedConfig:
    grid: object
    model: object
    arrays: dict
    origin: tuple[float, float, float]
    resolution: float
    domain: dict
    terrain: dict


def prepare_config(city: CityGeometry, condition: WindCondition, grid: GridSpec, terrain):
    if terrain is not None and not isinstance(terrain, FlatTerrain) and not (isinstance(terrain, str) and terrain == "flat"):
        raise ValueError("terrain must be None, 'flat', or FlatTerrain(elevation=...)")
    if city.has_terrain and terrain is None:
        raise ValueError("City has terrain; pass terrain='flat' or FlatTerrain(...) to explicitly accept flattening")
    if not city.rings and grid.bounds is None:
        raise ValueError("An empty city requires explicit grid bounds")
    bounds = grid.bounds
    base = min((lo for lo, _ in city.base_ranges), default=bounds[2] if bounds else 0.0)
    if terrain is None:
        for source_id, (lo, hi) in zip(city.source_ids, city.base_ranges):
            if hi - lo > 1e-6 or abs(lo - base) > 1e-6:
                raise ValueError(f"Building {source_id!r}: incompatible base elevation; explicitly request terrain='flat' to flatten")
    elif isinstance(terrain, FlatTerrain):
        base = terrain.elevation
    elif bounds:
        base = bounds[2]
    if bounds and abs(bounds[2] - base) > 1e-6:
        raise ValueError("Grid zmin must equal the flat ground elevation")
    spacing = float(np.float32(grid.resolution))
    if bounds:
        origin = (bounds[0], bounds[1], base)
        extents = tuple(bounds[i + 3] - origin[i] for i in range(3))
        padding = None
    else:
        xy = np.concatenate(city.rings)
        padding = max(grid.horizontal_padding, 3 * spacing)
        if padding > 5000 * spacing:
            raise ValueError("Horizontal padding exceeds the native 10000-cell dimension limit")
        lower, upper = xy.min(axis=0) - padding, xy.max(axis=0) + padding
        origin = (float(lower[0]), float(lower[1]), base)
        extents = (float(upper[0] - lower[0]), float(upper[1] - lower[1]),
                   max(max(city.heights) + max(grid.vertical_clearance, spacing), condition.reference_height, 2 * spacing))
    counts = []
    for axis, extent in zip("xyz", extents):
        ratio = extent / spacing
        if not math.isfinite(ratio) or ratio > 10000:
            raise ValueError(f"Grid {axis} dimension exceeds the native 10000-cell limit")
        counts.append(math.ceil(ratio))
    nx, ny, nz = counts
    if nx < 3 or ny < 3 or nz < 2:
        raise ValueError("Grid needs at least three cells in x/y and two in z")
    if nx * ny * nz > grid.max_cells or (nx + 1) * (ny + 1) * (nz + 2) > np.iinfo(np.int32).max:
        raise ValueError("Grid exceeds max_cells or the native index limit; increase resolution or reduce bounds")
    effective = tuple(count * spacing for count in counts)
    # Match QES's accumulated float32 vertical coordinates for the roof check.
    faces = np.r_[np.float32(0), np.cumsum(np.full(nz, spacing, dtype=np.float32), dtype=np.float32)]
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
    native_grid.cell_size, native_grid.max_cells = spacing, grid.max_cells
    model = _qes.ModelSettings()
    model.roughness_length = condition.roughness_length
    model.sensor_x = (min(5, nx - 1) + 0.5) * spacing
    model.sensor_y = (min(15, ny - 1) + 0.5) * spacing
    if any(Polygon(ring).covers(Point(model.sensor_x, model.sensor_y)) for ring in local_rings):
        model.sensor_x = model.sensor_y = 0.5 * spacing
    arrays = dict(vertices=np.ascontiguousarray(np.concatenate(local_rings) if local_rings else np.empty((0, 2)), dtype=np.float64),
                  offsets=np.asarray(offsets, dtype=np.int64), heights=np.asarray(city.heights, dtype=np.float64),
                  base_heights=np.zeros(len(city.rings), dtype=np.float64), ids=np.arange(len(city.rings), dtype=np.int64))
    return PreparedConfig(native_grid, model, arrays, origin, spacing,
                          dict(requested_bounds=bounds, local_bounds=(0.0, 0.0, 0.0, *effective),
                               effective_bounds=(*origin, *(origin[i] + effective[i] for i in range(3))),
                               shape=(nz, ny, nx), requested_resolution=grid.resolution, resolution=spacing,
                               effective_horizontal_padding=padding, max_cells=grid.max_cells),
                          dict(model="flat", elevation=base, flattening_requested=terrain is not None,
                               city_terrain_ignored=city.has_terrain, base_elevation_tolerance=1e-6,
                               base_elevations_flattened=any(abs(lo - base) > 1e-6 or abs(hi - base) > 1e-6
                                                            for lo, hi in city.base_ranges)))

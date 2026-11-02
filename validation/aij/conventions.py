"""Wind-direction conventions of the AIJ tables, mapped to dtcc-qes.

dtcc-qes uses the meteorological convention: the direction the wind blows
*from*, in degrees clockwise from north, with x = east and y = north, so the
flow vector is (-sin φ, -cos φ). See AIJ_VALIDATION_PLAN.md, F8.

- Case D: an arrow glyph next to Fig. 2 of the XLS shows 0° flowing toward +x,
  with 22.5° and 45° turning counter-clockwise toward +y. Hence φ = 270 - θ.
- Case E: the "N" arrow next to the XLS map points to +y, and the result columns
  run clockwise from N. Hence φ = 22.5° · i, reading "N" as the direction the
  wind comes from.

The checks below test these readings against the measurements alone, without
the model (results in AIJ_VALIDATION.md).
"""

import numpy as np
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from .metrics import spearman

D_ANGLES = (0.0, 22.5, 45.0)  # the AIJ flow angles of Case D, as labelled in the XLS
D_LABELS = ("0 deg.", "22.5 deg.", "45 deg.")
E_LABELS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")
E_STATES = ("before", "after")
REFLECTIONS = {"y=x": (lambda x, y: (y, x)), "y=-x": (lambda x, y: (-y, -x)),
               "x-axis": (lambda x, y: (x, -y)), "y-axis": (lambda x, y: (-x, y))}


def d_direction(angle: float) -> float:
    """Meteorological direction of a Case D flow angle (0° flows toward +x)."""
    return (270.0 - float(angle)) % 360.0


def e_direction(label: str) -> float:
    """Meteorological direction of a Case E label (N = wind from +y)."""
    return 22.5 * E_LABELS.index(label)


def flow_vector(direction) -> np.ndarray:
    """Unit vector(s) the wind blows toward, for meteorological direction(s)."""
    angle = np.deg2rad(np.asarray(direction, dtype=np.float64))
    return np.stack((-np.sin(angle), -np.cos(angle)), axis=-1)


def upwind_blockage(points_xy, directions, polygons, heights, length=60.0) -> np.ndarray:
    """(point, direction): the largest height / distance of a building on the upwind ray.

    The ray runs ``length`` metres from the point toward where the wind comes
    from. Distances below 1 m count as 1 m. Zero means no building on the ray.
    """
    tree = STRtree(polygons)
    out = np.zeros((len(points_xy), len(directions)))
    for d, direction in enumerate(directions):
        upwind = -flow_vector(direction)
        for i, (x, y) in enumerate(points_xy):
            ray = LineString([(x, y), (x + length * upwind[0], y + length * upwind[1])])
            for j in tree.query(ray, predicate="intersects"):
                distance = Point(x, y).distance(polygons[j].intersection(ray))
                out[i, d] = max(out[i, d], heights[j] / max(distance, 1.0))
    return out


def mapping_check(values, points_xy, polygons, heights, length=60.0) -> list[dict]:
    """Rank correlation of measured speed with upwind blockage, for every rotation and sense
    of the 16 Case E labels.

    Mapping (sense, offset) puts label i at (offset + sense · 22.5 · i) mod 360;
    (+1, 0) is ``e_direction``, and (+1, 180) is the "blows toward" reading.
    Sheltered points are slower, so the true mapping gives the most negative
    correlation in every direction. Use the "before" state: the new 60 m tower
    raises speeds around it and confounds the blockage measure.
    """
    index = np.arange(np.shape(values)[1])
    out = []
    for sense in (1, -1):
        for offset in (0.0, 90.0, 180.0, 270.0):
            directions = (offset + sense * 22.5 * index) % 360.0
            blockage = upwind_blockage(points_xy, directions, polygons, heights, length)
            rho = np.array([spearman(blockage[:, d], values[:, d]) for d in index])
            out.append(dict(sense="clockwise" if sense > 0 else "counter-clockwise", offset=offset,
                            median_rho=float(np.median(rho)), negative_directions=int((rho < 0).sum()),
                            rho=rho.tolist()))
    return out


def mirror_symmetry(values, points_xy, reflection: str) -> np.ndarray:
    """Per direction, the mean |difference| between points related by a reflection about the origin.

    Case D is symmetric about the tower: at 45° the flow runs along a diagonal,
    so the field should be most symmetric about that diagonal.
    """
    reflect = REFLECTIONS[reflection]
    key = {(round(x, 4), round(y, 4)): i for i, (x, y) in enumerate(points_xy)}
    out = []
    for d in range(np.shape(values)[1]):
        diffs = []
        for i, (x, y) in enumerate(points_xy):
            j = key.get(tuple(round(v, 4) for v in reflect(x, y)))
            if j is not None and j != i and np.isfinite(values[i, d]) and np.isfinite(values[j, d]):
                diffs.append(abs(values[i, d] - values[j, d]))
        out.append(np.mean(diffs) if diffs else np.nan)
    return np.asarray(out)

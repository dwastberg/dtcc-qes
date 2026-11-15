"""Geometric features of probe-direction pairs: upwind fetch, nearest upwind building, zone flags."""
import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point

import common
from aij import conventions, grids


def domain(d):
    xmin, ymin, _, xmax, ymax, _ = grids.horizontal_bounds(d.case, d.polygons, 120.0 if d.case == "C" else 20.0)
    return xmin, ymin, xmax, ymax


def upwind(d, length=1000.0):
    """Per (point, direction): distance to the upwind domain edge, buildings crossed upwind, their path length,
    distance to the nearest upwind building and its height (NaN / 0 when there is none)."""
    xmin, ymin, xmax, ymax = domain(d)
    tree = STRtree(d.polygons)
    n, m = len(d.ids), len(d.directions)
    out = dict(edge=np.zeros((n, m)), crossed=np.zeros((n, m)), path=np.zeros((n, m)),
               nearest=np.full((n, m), np.nan), nearest_height=np.full((n, m), np.nan), tallest=np.zeros((n, m)))
    for j, direction in enumerate(d.directions):
        ux, uy = -conventions.flow_vector(direction)
        for i, (x, y) in enumerate(d.xyz[:, :2]):
            ts = []
            if ux:
                ts += [(xmin - x) / ux, (xmax - x) / ux]
            if uy:
                ts += [(ymin - y) / uy, (ymax - y) / uy]
            edge = min([t for t in ts if t > 0] + [length])
            out["edge"][i, j] = edge
            ray = LineString([(x, y), (x + edge * ux, y + edge * uy)])
            point = Point(x, y)
            best = np.inf
            for k in tree.query(ray, predicate="intersects"):
                piece = d.polygons[k].intersection(ray)
                out["crossed"][i, j] += 1
                out["path"][i, j] += piece.length
                out["tallest"][i, j] = max(out["tallest"][i, j], d.heights[k])
                distance = point.distance(piece)
                if distance < best:
                    best = distance
                    out["nearest"][i, j], out["nearest_height"][i, j] = distance, d.heights[k]
    return out


def blockage(d, length=60.0):
    return conventions.upwind_blockage(d.xyz[:, :2], d.directions, d.polygons, d.heights, length)


def zones(d, deficit_threshold=0.05):
    """Zone name of each (point, direction): the flag of the nearest 2 m cell; with wake code 3, open cells whose
    deficit exceeds the threshold are named 'spreading wake'."""
    specs = common.specs(d.case, d.wake, d.resolution, d.state)
    out = np.empty((len(d.ids), len(specs)), dtype=object)
    for j, spec in enumerate(specs):
        flag = common.flags(spec)
        _, arrays = common.load(spec)
        x, y = arrays["x"], arrays["y"]
        ix = np.clip(np.rint((d.xyz[:, 0] - x[0]) / (x[1] - x[0])).astype(int), 0, len(x) - 1)
        iy = np.clip(np.rint((d.xyz[:, 1] - y[0]) / (y[1] - y[0])).astype(int), 0, len(y) - 1)
        codes = flag[iy, ix]
        names = np.array([common.FLAG_NAMES.get(int(c), "solid/other") for c in codes], dtype=object)
        if d.wake == 3:
            deficit = d.extras["deficit"][:, j]
            names[(codes == 1) & (deficit > deficit_threshold)] = "spreading wake"
        out[:, j] = names
    return out

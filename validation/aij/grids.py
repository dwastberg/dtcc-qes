"""Computational domains for the AIJ runs (AIJ_VALIDATION_PLAN.md, Grids).

Horizontal bounds are fixed per case and shared by every direction and both
Case E states, so "before" and "after" differ only by the new buildings. The
vertical faces put a cell centre exactly at the probe height (2 m), so the
probe layer needs no vertical interpolation: uniform fine layers up to about
1.2 H_max, then geometric growth to the top.
"""

import math

import numpy as np

PROBE_HEIGHT = 2.0  # m
CASE_E_BOUNDS = (-246.0, -250.0, 254.0, 250.0)  # the DXF site plate: the reproduced area plus a margin
FINE_FACTOR = 1.2  # uniform layers up to this multiple of the tallest roof
GROWTH = 1.15  # thickness ratio of successive layers above the fine region


def horizontal_bounds(case: str, polygons, padding: float = 20.0) -> tuple:
    """(xmin, ymin, 0, xmax, ymax, None) in the AIJ frame; the top follows the vertical faces.

    Case D: the footprint box plus ``padding``. Case E: the site plate, which
    leaves 42-50 m between the outermost building and the domain edge.
    """
    if case == "E":
        xmin, ymin, xmax, ymax = CASE_E_BOUNDS
    else:
        boxes = np.array([p.bounds for p in polygons])
        xmin, ymin = boxes[:, :2].min(axis=0) - padding
        xmax, ymax = boxes[:, 2:].max(axis=0) + padding
    return (float(xmin), float(ymin), 0.0, float(xmax), float(ymax), None)


def vertical_faces(dz: float, top: float, fine_top: float, *, centre: float = PROBE_HEIGHT,
                   growth: float | None = GROWTH, max_dz: float | None = None) -> np.ndarray:
    """Faces from 0 with a layer of thickness ``dz`` centred at ``centre``.

    Below that layer, one thinner layer takes up the remainder; above it, layers
    of ``dz`` continue to at least ``fine_top``, then grow by ``growth`` per layer
    (capped at ``max_dz``) until the last face reaches ``top``. ``growth=None``
    keeps ``dz`` all the way up (the uniform control).
    """
    bottom = centre - dz / 2
    if bottom < 0:
        raise ValueError(f"A {dz:g} m layer cannot be centred at {centre:g} m above the ground")
    faces = [0.0]
    count = math.floor(bottom / dz + 1e-9)
    remainder = bottom - count * dz
    if remainder > 1e-9:
        faces.append(remainder)
    faces.extend(remainder + dz * np.arange(1, count + 1) if remainder > 1e-9 else dz * np.arange(1, count + 1))
    faces.append(bottom + dz)  # the probe layer
    thickness = dz
    while faces[-1] < top - 1e-9:
        if growth is not None and faces[-1] >= fine_top - 1e-9:
            thickness *= growth
            if max_dz is not None:
                thickness = min(thickness, max_dz)
        faces.append(faces[-1] + thickness)
    faces = np.round(np.asarray(faces, dtype=np.float64), 9)
    if np.any(np.diff(faces) <= 0):
        raise ValueError("Vertical faces must increase")
    return faces


def required_top(heights, clearance: float = 20.0, reference_height: float = 0.0) -> float:
    """dtcc-qes's top rule for automatic grids: H_max + clearance, and at least the reference height."""
    return max(float(np.max(heights)) + clearance, reference_height)

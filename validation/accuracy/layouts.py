"""I2: synthetic layouts (ACCURACY_IMPROVEMENT_PLAN.md). Invariance and physical checks only; no measured targets.

- ``isolated``: a 10 m cube, or a 1:1:3 tower (20 × 20 × 60 m).
- ``array``: 5 × 5 blocks of 10 m height at plan-area density 0.25 (10 m blocks, 20 m pitch) or 0.44
  (10 m blocks, 15 m pitch), optionally with the central block replaced by a 60 m tower of the same footprint.
- ``tandem``: two 10 m cubes in line along x, with a gap of 1, 2 or 4 H.

Runs use a log profile (default 5 m/s at 10 m, z0 = 0.1 m), 2 m cells and ``wind.Solver()``; the 2 m plane is
returned with K = speed / the profile speed at 2 m... see ``run``.
"""
import numpy as np
from shapely.affinity import rotate
from shapely.geometry import box

from common import REPO  # noqa: F401  (puts validation/ on the path)
from aij import cityutil

H = 10.0
PITCH = {0.25: 20.0, 0.44: 15.0}


def _city(blocks, name):
    city = cityutil.new_city(case=f"synthetic-{name}")
    for i, (polygon, height) in enumerate(blocks):
        city.add_building(cityutil.make_building(f"S-{i}", polygon, height))
    return cityutil.qes_city(city)


def isolated(kind="cube", rotation=0.0):
    polygon, height = (box(-5, -5, 5, 5), H) if kind == "cube" else (box(-10, -10, 10, 10), 60.0)
    return _city([(rotate(polygon, rotation, origin=(0, 0)), height)], f"{kind}-{rotation:g}")


def array(density=0.25, tower=False, missing_centre=False):
    pitch = PITCH[density]
    blocks = []
    for i in range(-2, 3):
        for j in range(-2, 3):
            centre = i == j == 0
            if centre and missing_centre:
                continue
            blocks.append((box(i * pitch - 5, j * pitch - 5, i * pitch + 5, j * pitch + 5), 60.0 if centre and tower else H))
    return _city(blocks, f"array-{density:g}-{'tower' if tower else 'flat'}")


def tandem(gap_h=2.0):
    gap = gap_h * H
    # shifted by 1 m in x so that every wall shares the cube's odd offset on a 2 m grid
    return _city([(box(-9 - gap / 2, -5, 1 - gap / 2, 5), H), (box(1 + gap / 2, -5, 11 + gap / 2, 5), H)], f"tandem-{gap_h:g}H")


def run(city, direction=270.0, wake=3, resolution=2.0, padding=80.0, clearance=40.0, speed=5.0, **parameterizations):
    """Solve a layout; returns the WindResult. Symmetric padding, so that mirrored directions see mirrored domains."""
    from dtcc_qes import wind
    rows = cityutil.footprints(city)
    xs = np.concatenate([np.asarray(p.exterior.coords)[:, 0] for _, p, _ in rows])
    ys = np.concatenate([np.asarray(p.exterior.coords)[:, 1] for _, p, _ in rows])
    # Cell faces must fall on every wall, or the rasterised layout loses its mirror symmetry.
    remainder = np.unique(np.round(np.mod(np.concatenate([xs, ys]), resolution), 6))
    if len(remainder) != 1:
        raise ValueError(f"walls do not share one offset on a {resolution:g} m grid; use a finer resolution")
    half = max(np.abs(xs).max(), np.abs(ys).max()) + padding
    half = np.ceil(half / resolution) * resolution + remainder[0]
    return wind.run(city, speed=speed, direction=direction, resolution=resolution,
                    bounds=(-half, -half, 0.0, half, half, None), vertical_clearance=clearance,
                    turbulence=wind.Turbulence(),
                    parameterizations=wind.Parameterizations(wake=wake, **parameterizations))


def plane_K(result, height=2.0):
    """(x, y, K, valid) at ``height``: mean-vector speed over the inflow speed at the same height (far upwind value)."""
    plane = result.sample(height, "nearest")
    speed = np.linalg.norm(plane.velocity, axis=-1)
    x = plane.x.astype(float) + result.origin[0]
    y = plane.y.astype(float) + result.origin[1]
    return x, y, speed, plane.valid


if __name__ == "__main__":
    # Smoke check of every layout: it runs, converges, and a mirrored direction gives the mirrored field.
    for name, city in (("cube", isolated()), ("tower", isolated("tower")), ("array 0.25", array(0.25)),
                       ("array 0.44 + tower", array(0.44, True)), ("tandem 2H", tandem(2.0))):
        for wake in (2, 3):
            a = run(city, 270.0, wake, resolution=1.0 if "0.44" in name else 2.0)
            x, y, k, ok = plane_K(a)
            mirror = np.nanmax(np.abs(np.where(ok & ok[::-1], k - k[::-1], np.nan)))
            print(f"{name:20s} wake={wake} cells={a.velocity.shape[:3]} converged={a.diagnostics.converged} "
                  f"max speed {np.nanmax(np.where(ok, k, np.nan)):.2f} m/s, y-mirror max |Δspeed| {mirror:.2e} m/s")

"""The Fabel 1° direction sweep (FABEL_WAKE_INVESTIGATION.md, 4.6) on the public API, for M's continuity bar.

One 20 × 30 × 20 m building, 2 m grid, 225°–315° in 1° steps. Reports the per-degree steps of K at five
probes and the per-degree RMS change of the 2 m plane, for a given parameterization set and optional
field transform. Results are cached per variant name.
"""
import json
import os
import logging
import sys

import numpy as np
from dtcc_core.model import Building, City, GeometryType, Surface

import common

PROBES = {"front": (84, 100), "corner": (87, 82), "side": (100, 80), "wake": (125, 100), "far wake": (160, 100)}
DIRECTIONS = np.arange(225.0, 315.5, 1.0)


RESOLUTION = float(os.environ.get("ACC_SWEEP_RES", "2"))
ROTATION = float(os.environ.get("ACC_SWEEP_ROTATION", "0"))  # degrees; the building turned about its centre


def city():
    out = City()
    b = Building(id="b")
    b.measured_height = 20.0
    corners = np.array([[90., 85, 0], [90, 115, 0], [110, 115, 0], [110, 85, 0]])
    if ROTATION:
        c, sn = np.cos(np.deg2rad(ROTATION)), np.sin(np.deg2rad(ROTATION))
        xy = corners[:, :2] - 100.0
        corners[:, :2] = np.column_stack([c * xy[:, 0] - sn * xy[:, 1], sn * xy[:, 0] + c * xy[:, 1]]) + 100.0
    b.add_geometry(Surface(vertices=corners), GeometryType.LOD0)
    out.add_building(b)
    return out


def sweep(name, wake=3, transform=None, sigma=0.0, **parameterizations):
    """Steps of K per degree. ``transform(result) -> result`` is reserved for prototypes; None for a parent."""
    from dtcc_qes import wind
    name = name + (f"-rot{ROTATION:g}" if ROTATION else "") + (f"-r{RESOLUTION:g}" if RESOLUTION != 2 else "")
    path = common.OUT / ("sweep-" + common.TAG if common.TAG else "sweep") / f"{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    logging.disable(logging.WARNING)
    points = np.array([(x, y, 2.0) for x, y in PROBES.values()], float)
    K, planes = [], []
    for direction in DIRECTIONS:
        r = wind.run(city(), speed=5.0, direction=float(direction), resolution=RESOLUTION, bounds=(0, 0, 0, 200, 200, 60),
                     solver=wind.Solver(tolerance=1e-6, max_iterations=3000, stop="multiplier_change"),
                     parameterizations=wind.Parameterizations(wake=wake, **parameterizations))
        if transform is not None:
            r = transform(r)
        s = r.sample_points(points, "linear", frame="global")
        K.append(np.linalg.norm(s.velocity, axis=1) / r.reference_speed)
        p = r.sample(2.0, "linear")
        speed = np.where(p.valid, np.linalg.norm(p.velocity, axis=-1) / r.reference_speed, np.nan)
        if sigma:  # post-hoc screen: fluid-restricted Gaussian of the solved speed
            import planes as plane_tools
            speed = plane_tools.smooth(speed, p.valid, sigma / 2.0)
            x, y = np.asarray(p.x, float) + r.origin[0], np.asarray(p.y, float) + r.origin[1]
            K[-1] = plane_tools.sample(speed, x, y, points[:, :2])
        planes.append(speed)
    K, planes = np.array(K), np.array(planes)
    step = np.abs(np.diff(K, axis=0))
    change = np.sqrt(np.nanmean(np.diff(planes, axis=0) ** 2, axis=(1, 2)))
    cell = np.abs(np.diff(planes, axis=0))
    out = dict(name=name, probe_steps={n: step[:, i].tolist() for i, n in enumerate(PROBES)},
               plane_rms=change.tolist(), plane_max_cell_step=np.nanmax(cell, axis=(1, 2)).tolist(),
               plane_p999_cell_step=float(np.nanpercentile(cell, 99.9)), plane_p99_cell_step=float(np.nanpercentile(cell, 99)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out))
    return out


def summary(result):
    lines = []
    rms = np.array(result["plane_rms"])
    i = int(rms.argmax())
    lines.append(f"| {result['name']} | plane RMS ΔK per degree | {np.median(rms):.4f} | {np.percentile(rms, 95):.4f} | "
                 f"{rms.max():.4f} ({rms.max() / np.median(rms):.1f}× median) | {DIRECTIONS[i]:.0f}→{DIRECTIONS[i] + 1:.0f} |")
    cell = np.array(result["plane_max_cell_step"])
    i = int(cell.argmax())
    lines.append(f"| {result['name']} | largest single-cell ΔK per degree | {np.median(cell):.3f} | {np.percentile(cell, 95):.3f} | "
                 f"{cell.max():.3f} | {DIRECTIONS[i]:.0f}→{DIRECTIONS[i] + 1:.0f} |")
    for probe, steps in result["probe_steps"].items():
        steps = np.array(steps)
        i = int(steps.argmax())
        lines.append(f"| {result['name']} | probe {probe} | {np.median(steps):.4f} | {np.percentile(steps, 95):.4f} | "
                     f"{steps.max():.3f} | {DIRECTIONS[i]:.0f}→{DIRECTIONS[i] + 1:.0f} |")
    return lines


if __name__ == "__main__":
    print("| Variant | Quantity | Median | 95th percentile | Maximum | At |\n|---|---|---|---|---|---|")
    for wake in ((3,) if common.TAG else (2, 3)):
        print("\n".join(summary(sweep(f"parent-wake{wake}", wake))))
    if "--fade" in sys.argv:  # Parameterizations.angle_fade, on the build in use
        fade = float(sys.argv[sys.argv.index("--fade") + 1])
        print("\n".join(summary(sweep(f"angle-fade-{fade:g}", 3, angle_fade=fade))))
    if "--attribution" in sys.argv:
        for name, options in (("wake3, sidewall off", dict(sidewall=0)), ("wake3, upwind cavity off", dict(upwind_cavity=0)),
                              ("wake3, rooftop off", dict(rooftop=0)),
                              ("wake3, sidewall and upwind cavity off", dict(sidewall=0, upwind_cavity=0)),
                              ("wake3, post-hoc 4 m smoothing", dict(sigma=4.0)), ("wake3, post-hoc 8 m smoothing", dict(sigma=8.0))):
            print("\n".join(summary(sweep(name, 3, **options))[:2]))

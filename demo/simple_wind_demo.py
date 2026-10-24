"""Simulate and plot wind around three rectangular buildings on flat ground.

Run from the repository root after installation:
    uv run --frozen python demo/simple_wind_demo.py

Save a figure without opening a window:
    uv run --frozen python demo/simple_wind_demo.py --save wind.png --no-show
"""

import argparse
from pathlib import Path
from time import perf_counter

import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind

# Each rectangle is (x, y, width, depth, height), in metres.
BUILDINGS = (
    (28.0, 24.0, 12.0, 18.0, 10.0),
    (54.0, 50.0, 18.0, 12.0, 14.0),
    (80.0, 24.0, 14.0, 20.0, 8.0),
)
SLICE_HEIGHT = 3.0


def make_city() -> City:
    """Create three LOD0 footprints with measured extrusion heights."""
    city = City()
    for index, (x, y, width, depth, height) in enumerate(BUILDINGS, start=1):
        building = Building(id=f"building-{index}")
        building.measured_height = height
        footprint = Surface(vertices=np.array([
            [x, y, 0.0],
            [x, y + depth, 0.0],
            [x + width, y + depth, 0.0],
            [x + width, y, 0.0],
        ]))
        building.add_geometry(footprint, GeometryType.LOD0)
        city.add_building(building)
    return city


def plot_wind(result: wind.WindResult):
    """Plot horizontal speed and projected streamlines, masking solid cells."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    x = result.x + result.origin[0]
    y = result.y + result.origin[1]
    z = result.z + result.origin[2]
    level = int(np.argmin(np.abs(z - SLICE_HEIGHT)))
    solid = result.solid_mask[level]
    u = np.ma.array(result.velocity[level, :, :, 0], mask=solid)
    v = np.ma.array(result.velocity[level, :, :, 1], mask=solid)
    speed = np.hypot(u, v)

    fig, ax = plt.subplots(figsize=(11, 8), layout="constrained")
    field = ax.pcolormesh(x, y, speed, shading="nearest", cmap="viridis", vmin=0)
    fig.colorbar(field, ax=ax, label="Horizontal wind speed (m/s)", shrink=0.85)
    ax.streamplot(x, y, u, v, color="white", density=1.6,
                  linewidth=0.75, arrowsize=1.0)

    for index, (bx, by, width, depth, height) in enumerate(BUILDINGS, start=1):
        ax.add_patch(Rectangle((bx, by), width, depth, facecolor="#263238",
                               edgecolor="white", linewidth=1.3, zorder=3))
        ax.text(bx + width / 2, by + depth / 2, f"B{index}\n{height:g} m",
                color="white", ha="center", va="center", fontsize=10, zorder=4)

    ax.annotate("Wind from west", xy=(42, 77), xytext=(5, 77), color="white",
                fontsize=10, va="center",
                bbox={"facecolor": "#263238", "edgecolor": "none", "alpha": 0.75},
                arrowprops={"arrowstyle": "->", "color": "white", "lw": 1.5})
    ax.set(title=("Wind around three rectangular buildings\n"
                  f"Slice at z = {z[level]:g} m; inflow 5 m/s at 10 m height"),
           xlabel="x (m)", ylabel="y (m)", aspect="equal")
    half_cell = result.resolution / 2
    ax.set_xlim(x[0] - half_cell, x[-1] + half_cell)
    ax.set_ylim(y[0] - half_cell, y[-1] + half_cell)
    return fig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--save", type=Path, metavar="PATH", help="save the plot to an image")
    parser.add_argument("--no-show", action="store_true", help="run without opening a plot window")
    args = parser.parse_args(argv)

    if args.no_show:
        import matplotlib
        matplotlib.use("Agg")

    import matplotlib.pyplot as plt

    start_time = perf_counter()
    result = wind.run(
        make_city(),
        wind.WindCondition(speed=5.0, direction=270.0),
        grid=wind.GridSpec(resolution=0.5, bounds=(0, 0, 0, 120, 90, 40)),
        # Avoid demanding multiplier changes below this domain's float32 precision.
        solver=wind.SolverOptions(tolerance=1e-4, max_iterations=2000),
    )
    get_python_logger("dtcc-qes").info("Wind simulation took %.2f seconds", perf_counter() - start_time)
    fig = plot_wind(result)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.save, dpi=180)
        get_python_logger("dtcc-qes").info("Saved wind demo to %s", args.save.resolve())
    if not args.no_show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()

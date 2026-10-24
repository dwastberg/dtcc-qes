"""Simulate wind through a medium city with 20 buildings in six street blocks.

Run from the repository root after installation:
    uv run --frozen python demo/medium_city.py

Save the wind map without opening a window:
    uv run --frozen python demo/medium_city.py --save build/medium-city.png --no-show
"""

import argparse
from pathlib import Path
from time import perf_counter

import numpy as np
from dtcc_core.common import get_python_logger
from dtcc_core.model import Building, City, GeometryType, Surface
from dtcc_qes import wind


# Each rectangle is (x, y, width, depth, height), in metres. Short residential
# blocks surround taller offices near the central avenue. All gaps stay open.
BUILDINGS = (
    # Southwest block: four apartment buildings.
    (42.0, 30.0, 24.0, 12.0, 10.0),
    (72.0, 30.0, 28.0, 14.0, 16.0),
    (42.0, 50.0, 20.0, 12.0, 12.0),
    (70.0, 50.0, 30.0, 12.0, 18.0),
    # Southeast block: a long building and two smaller neighbors.
    (132.0, 30.0, 24.0, 30.0, 22.0),
    (164.0, 30.0, 26.0, 12.0, 14.0),
    (164.0, 50.0, 26.0, 12.0, 12.0),
    # Central west block: mixed mid-rise buildings and service lanes.
    (42.0, 84.0, 20.0, 30.0, 18.0),
    (70.0, 84.0, 30.0, 12.0, 24.0),
    (72.0, 104.0, 28.0, 12.0, 30.0),
    # Central east block: the city's tallest office faces the avenue.
    (132.0, 84.0, 22.0, 12.0, 30.0),
    (164.0, 84.0, 26.0, 12.0, 20.0),
    (132.0, 104.0, 22.0, 12.0, 42.0),
    (164.0, 104.0, 26.0, 12.0, 28.0),
    # Northwest block: lower residential buildings.
    (42.0, 138.0, 24.0, 30.0, 14.0),
    (74.0, 138.0, 26.0, 12.0, 18.0),
    (74.0, 158.0, 26.0, 12.0, 12.0),
    # Northeast block: a mid-rise slab and two low-rise buildings.
    (132.0, 138.0, 22.0, 30.0, 24.0),
    (164.0, 138.0, 26.0, 12.0, 16.0),
    (164.0, 158.0, 26.0, 12.0, 10.0),
)

DOMAIN = (0.0, 0.0, 0.0, 240.0, 200.0, 80.0)
SLICE_HEIGHT = 3.0


def make_city() -> City:
    """Create 20 LOD0 extrusions arranged in six street blocks."""
    city = City()
    for index, (x, y, width, depth, height) in enumerate(BUILDINGS, start=1):
        building = Building(id=f"medium-city-{index:02d}")
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
    """Plot horizontal speed and streamlines around the buildings at street level."""
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
    fig.colorbar(field, ax=ax, label="Horizontal wind speed (m/s)", shrink=0.75)
    ax.streamplot(x, y, u, v, color="white", density=1.5,
                  linewidth=0.65, arrowsize=0.8)

    for bx, by, width, depth, height in BUILDINGS:
        ax.add_patch(Rectangle((bx, by), width, depth, facecolor="#263238",
                               edgecolor="white", linewidth=0.9, zorder=3))
        ax.text(bx + width / 2, by + depth / 2, f"{height:g} m",
                color="white", ha="center", va="center", fontsize=7, zorder=4)

    ax.annotate("Wind from west", xy=(78, 190), xytext=(8, 190), color="white",
                fontsize=9, va="center",
                bbox={"facecolor": "#263238", "edgecolor": "none", "alpha": 0.8},
                arrowprops={"arrowstyle": "->", "color": "white", "lw": 1.5})
    half_cell = result.resolution / 2
    ax.set(xlim=(x[0] - half_cell, x[-1] + half_cell),
           ylim=(y[0] - half_cell, y[-1] + half_cell), aspect="equal",
           title=f"Street-level wind · slice at z = {z[level]:g} m",
           xlabel="x (m)", ylabel="y (m)")
    fig.suptitle(f"Medium city · {len(BUILDINGS)} buildings · inflow 5 m/s at 10 m height",
                 fontsize=16)
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

    start = perf_counter()
    result = wind.run(
        make_city(),
        wind.WindCondition(speed=5.0, direction=270.0),
        # This 0.5 m domain has 30,720,000 cells, above the default cell limit.
        grid=wind.GridSpec(resolution=0.5, bounds=DOMAIN, max_cells=40_000_000),
        solver=wind.SolverOptions(tolerance=1e-4, max_iterations=20000),
    )
    logger = get_python_logger("dtcc-qes")
    logger.info("Medium city wind simulation took %.2f seconds", perf_counter() - start)
    fig = plot_wind(result)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(args.save, dpi=180)
        logger.info("Saved medium city demo to %s", args.save.resolve())
    if not args.no_show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()

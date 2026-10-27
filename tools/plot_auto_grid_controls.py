"""Plot the archived C2 tower horizontal-sensitivity control (optional matplotlib)."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from run_auto_grid_controls import POINTS, assess, height_run, rectangles


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = json.loads(gzip.decompress(args.input.read_bytes()))
    runs = [r for r in document["runs"] if r["geometry"] == "tower" and r["direction"] == 270
            and r["family"] == "uniform-0.5" and r["repeat"] == 0]
    base, = [r for r in runs if r["control"] == "base"]
    fine, = [r for r in runs if r["control"] == "xy1"]
    if not all(assess(r)["accepted"] for r in (base, fine)):
        raise ValueError("Plot requires accepted solves")
    fields = []
    for r in (base, fine):
        plane = height_run(r, 1.75)["checkpoints"][-1]["velocity"]
        v = np.array([value if value is not None else [np.nan]*3 for value in plane])
        fields.append(np.linalg.norm(v, axis=1).reshape(len(POINTS), len(POINTS))/5)
    common = np.isfinite(fields[0]) & np.isfinite(fields[1])
    base_k = np.where(common, fields[0], np.nan)
    delta = np.where(common, np.abs(fields[0]-fields[1]), np.nan)
    j, i = np.unravel_index(np.nanargmax(delta), delta.shape)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5), layout="constrained")
    for ax, field, title, label, cmap in zip(axes, (base_k, delta),
            ("Base: 2 m horizontal cells", "Difference from 1 m horizontal cells"),
            ("K = speed / 5 m/s", "Absolute change in K"), ("viridis", "magma")):
        mesh = ax.pcolormesh(POINTS, POINTS, field, shading="nearest", cmap=cmap, vmin=0)
        for x, y, width, length, _ in rectangles("tower"):
            ax.add_patch(Rectangle((x, y), width, length, facecolor="0.75", edgecolor="0.35"))
        ax.set(xlim=(2, 78), ylim=(2, 78), xlabel="x (m)", ylabel="y (m)", title=title, aspect="equal")
        fig.colorbar(mesh, ax=ax, label=label, shrink=.8)
    axes[1].plot(POINTS[i], POINTS[j], "o", markerfacecolor="none", markeredgecolor="cyan", markersize=8)
    fig.suptitle("Tower, wind from 270°, height 1.75 m; uniform 0.5 m vertical layers")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    print(f"Maximum change: {delta[j, i]:.6f} K at ({POINTS[i]:g}, {POINTS[j]:g}) m")


if __name__ == "__main__":
    main()

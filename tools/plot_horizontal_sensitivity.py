"""Plot initialization and certified corrected speeds at the C2b audit point."""
import argparse
import gzip
import json
from pathlib import Path

import numpy as np

from run_horizontal_sensitivity import references, values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="C2b raw.json.gz")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    doc = json.loads(gzip.decompress(args.input.read_bytes()))
    summary = json.loads((args.input.parent/"summary.json").read_text())
    refs, _ = references(Path(doc["metadata"]["reference"]))
    accepted = {row["task"]: row["accepted"] for row in summary["runs"]}

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 4), layout="constrained", sharey=True)
    point, height = [27, 21], 1.75
    for ax, family in zip(axes, ("auto", "uniform-0.5")):
        for stage, label, color in (("profile", "Approach profile", "0.4"),
                                     ("initial", "After models and wall zeroing", "tab:orange"),
                                     ("final", "Corrected, accepted solve", "tab:blue")):
            speeds = []
            for resolution in (2, 1, .5):
                if stage == "final" and resolution in (2, 1):
                    v = values(refs[family, 270, resolution], height)[9*38+12]
                    speeds.append(float(np.linalg.norm(v)/5))
                else:
                    kind = "fine" if resolution == .5 else "probe"
                    task = f"{kind}/{family}/270/{resolution:g}"
                    row = next(a for a in summary["point_audits"] if a["task"] == task
                               and a["height"] == height and a["point"] == point and a["stage"] == stage)
                    speeds.append(row["K"] if stage != "final" or accepted[task] else np.nan)
            ax.plot(range(3), speeds, "o-", label=label, color=color)
        if not accepted[f"fine/{family}/270/0.5"]:
            ax.annotate("Corrected 0.5 m value omitted:\nresidual gate failed", (1.02, .97),
                        xycoords="axes fraction", ha="right", va="top", fontsize=8)
        ax.set(xticks=range(3), xticklabels=["2 m", "1 m", "0.5 m"], xlabel="Uniform x/y cell size",
               title="Automatic z layers" if family == "auto" else "Uniform 0.5 m z layers", ylim=(0, .8))
        ax.grid(alpha=.2)
    axes[0].set_ylabel("K = magnitude of mean velocity / 5 m/s")
    axes[0].legend(loc="lower left", fontsize=8)
    backend = "OpenMP red-black" if doc["metadata"]["reference_backend"] == "openmp_red_black" else "Serial"
    fig.suptitle(f"{backend}: tower, wind from 270°, point (27, 21, 1.75) m")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()

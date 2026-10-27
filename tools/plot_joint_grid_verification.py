"""Plot the joint comparisons, keeping near-wall failures visible."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from run_joint_grid_verification import atomic_json, digest, read


def main():
    root = Path("docs/data/joint-grid-verification")
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    fig.subplots_adjust(left=.065, right=.99, bottom=.15, top=.85, hspace=.44, wspace=.25)
    labels = ("xy_1_to_0.5_at_160", "xy_1_to_0.5_at_240", "extent_160_to_240_at_0.5")
    titles = ("Horizontal refinement at 160 m", "Horizontal refinement at 240 m", "Lateral expansion at 0.5 m")
    for line, backend in enumerate(("serial", "openmp")):
        summary = read(root/backend/"summary.json")
        if not summary["complete"] or not all(r["accepted"] for r in summary["runs"]):
            raise ValueError("Plot requires complete matrices and accepted solves")
        for column, (label, title) in enumerate(zip(labels, titles)):
            ax = axes[line, column]
            rows = [r for r in summary["comparisons"] if r["region"] == "all" and r["comparison"] == label]
            for i, row in enumerate(rows):
                x = np.array([i-.2, i, i+.2])
                valid = all(c["valid"] for c in row["additional_fixed_checks"])
                local = max(c["relative_difference"] if c["relative_difference"] is not None
                            else c["abs_delta_K"] for c in row["additional_fixed_checks"]) if valid else np.nan
                metrics = [row["p95_abs_delta_K"], row["frozen_critical_max_relative_difference"], local]
                for xx, value, colour, marker in zip(x, metrics, ("#3278a8", "#d18b19", "#b73d57"), ("o", "s", "^")):
                    ax.scatter(xx, value, color=colour, marker=marker, s=32)
                if not valid:
                    ax.scatter(i+.2, .055, color="#b73d57", marker="x", s=40)
                    ax.annotate("invalid", (i+.2, .055), fontsize=6, rotation=90)
            ax.axhline(.05, color="black", linestyle="--", linewidth=1)
            ax.set_xticks(range(len(rows)), [f"{'A' if r['family']=='auto' else 'U'} {r['direction']}°\n{r['height']} m" for r in rows], fontsize=7)
            ax.set_ylim(bottom=0)
            ax.grid(axis="y", alpha=.2)
            ax.set_title(title)
            ax.set_ylabel(f"{backend}: ΔK or relative change")
    handles = [plt.Line2D([], [], linestyle="none", marker=m, color=c, label=l)
               for m, c, l in (("o", "#3278a8", "P95 absolute ΔK"),
                   ("s", "#d18b19", "Frozen critical max relative change"),
                   ("^", "#b73d57", "Additional fixed-point max change*"))]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .945), ncol=3, frameon=False, fontsize=9)
    fig.suptitle("Joint extent / horizontal verification — independent accepted float64 solves", y=.985, fontsize=14)
    fig.text(.065, .055, "A = frozen automatic z layers; U = uniform z=0.5 m. Tick labels show family, direction and sample height.", fontsize=9)
    fig.text(.065, .025, "*Relative change for reference K ≥ 0.1; absolute ΔK otherwise. Dashed line = 0.05. Full-region samples; no preset selected.", fontsize=9)
    fig.savefig(root/"verification.png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    atomic_json(root/"figure.json", dict(source_sha256=digest(__file__),
        summaries_sha256={b: digest(root/b/"summary.json") for b in ("serial", "openmp")},
        figure_sha256=digest(root/"verification.png")))


if __name__ == "__main__":
    main()

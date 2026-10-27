"""Reproduce the precision and fixed-region comparison figure from summaries."""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def main():
    root = Path("docs/data")
    fig, axes = plt.subplots(2, 3, figsize=(14, 7.5), constrained_layout=True)
    labels = ["auto 270", "auto 315", "uniform 270", "uniform 315"]
    pairs = [(family, wind) for family in ("auto", "uniform-0.5") for wind in (270, 315)]
    for row, backend in enumerate(("serial", "openmp")):
        precision = json.loads((root/"precision-remedy"/backend/"summary.json").read_text())
        old = json.loads((root/"horizontal-sensitivity"/backend/"summary.json").read_text())
        verification = json.loads((root/"lateral-horizontal-verification"/backend/"summary.json").read_text())
        if not precision["complete"] or not verification["complete"]:
            raise ValueError("Require complete matrices")
        before, after = [], []
        for family, wind in pairs:
            a, = [r for r in old["runs"] if r["task"] == f"fine/{family}/{wind}/0.5"]
            b, = [r for r in precision["runs"] if r["task"]["id"] == f"base/{family}/{wind}/0.5"]
            if not b["accepted"]:
                raise ValueError("Cannot plot failed finer references as accepted")
            before.append(a["heights"]["1.5"]["residuals"][-1]["max_scaled"])
            after.append(b["heights"]["1.5"]["residuals"][-1]["max_scaled"])
        x = np.arange(4)
        ax = axes[row, 0]
        ax.bar(x-.18, before, .36, label="float32, C2b (failed)", color="#bf5543")
        ax.bar(x+.18, after, .36, label="float64, from zero", color="#327a9c")
        ax.axhline(1e-3, color="black", linestyle="--", label="max residual limit")
        ax.set_yscale("log"); ax.set_ylabel(f"{backend}\nmax divergence × Hmax/Uref")
        ax.set_xticks(x, labels, rotation=20); ax.set_title("0.5 m x/y: final residual")
        if row == 0: ax.legend(fontsize=8)
        for col, prefix, metrics in ((1, "xy_", ("frozen_critical_max_relative_difference",)),
                                      (2, "extent_", ("p95_abs_delta_K",))):
            ax = axes[row, col]
            for label, style in (("2_to_1", "o-"), ("1_to_0.5", "s-")) if col == 1 else (("80_to_160", "o-"), ("160_to_240", "s-")):
                vals = []
                for family, wind in pairs:
                    rs = [r for r in verification["comparisons"] if r["comparison"] == prefix+label
                          and r["family"] == family and r["direction"] == wind and r["region"] == "all"]
                    if len(rs) != 2 or not all(r["matched_accuracy"] for r in rs):
                        raise ValueError("Only compare accepted solutions")
                    vals.append(max(r[metrics[0]] or 0 for r in rs))
                ax.plot(x, vals, style, label=label.replace("_to_", " → "))
            ax.axhline(.05, color="black", linestyle="--", label="comparison budget")
            ax.set_xticks(x, labels, rotation=20)
            ax.set_ylabel("max over 1.5 / 1.75 m")
            ax.set_title("Fixed-critical relative K change" if col == 1 else "Lateral P95 |ΔK|")
            if row == 0: ax.legend(fontsize=8)
    fig.suptitle("Accepted float64 references enable grid checks; pointwise and joint-scope limits remain")
    fig.savefig(root/"precision-remedy"/"verification.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()

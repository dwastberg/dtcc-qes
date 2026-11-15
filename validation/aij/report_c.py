"""Case C scalar-speed comparisons using the common run records and metrics."""
import json

import numpy as np

from . import campaigns, metrics, runner, tables


def comparison(record: dict) -> dict:
    spec = runner.RunSpec.from_dict(record["spec"])
    data = tables.load_results_c(spec.state)
    column = data.labels.index(spec.label)
    probes = record["probes"]
    # Join by ID rather than assuming a stored run retained the workbook row order.
    ids = list(probes["ids"])
    if len(set(ids)) != len(ids) or set(ids) != set(data.ids):
        raise ValueError("Case C run probe IDs do not match the workbook")
    order = [ids.index(int(i)) for i in data.ids]
    if not np.allclose(np.asarray(probes["xyz"])[order], data.xyz):
        raise ValueError("Case C run probe coordinates do not match the workbook")
    measured = data.values[:, column]
    quantities = {"mean_vector_speed": np.asarray(probes["K"], dtype=float)[order]}
    if "K_scalar" in probes:
        quantities["rms_speed_proxy"] = np.asarray(probes["K_scalar"], dtype=float)[order]
    with np.errstate(invalid="ignore", divide="ignore"):
        null = metrics.scores(np.ones_like(measured), measured)
    return dict(key=spec.key, state=spec.state, label=spec.label, resolution=spec.resolution,
                reference=data.reference, measured_quantity=data.quantity, instrument=data.instrument,
                total=len(measured), scores={name: metrics.scores(values, measured)
                                            for name, values in quantities.items()},
                no_building=null, ids=data.ids, measured=measured, simulated=quantities,
                provenance=record["provenance"],
                caveat="Thermistor mean scalar speed differs from mean-vector magnitude; "
                       "sqrt(|U|^2+2k) is an RMS proxy, not measured mean scalar speed.")


def report(runs, output, resolution=1.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=True)
    rows, missing, stale = [], [], []
    fig, axes = plt.subplots(3, 3, figsize=(11, 10), sharex=True, sharey=True)
    lines = ["# Case C validation", "", f"Grid: {resolution:g} m. K = speed / U_in(2 m).",
             "Measured: thermistor mean scalar speed. Simulated: mean-vector magnitude; RMS proxy reported separately.",
             "Missing/invalid probe pairs are excluded from scores; n / 120 shows coverage.", "",
             "| State | Direction | n / 120 | q | FAC2 | R | FB | No-building q |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for ax, spec in zip(axes.flat, campaigns.c_baseline(resolution)):
        ax.set_title(f"{spec.state}, {spec.label}")
        ax.plot([0, 2], [0, 2], color="black", linewidth=.7)
        record = runner.load(runs / "C", spec.key)
        if record is None:
            missing.append(spec.key)
            ax.text(.1, .9, "missing", transform=ax.transAxes)
            continue
        if record["fingerprint"] != runner.fingerprint():
            stale.append(spec.key)
            ax.text(.1, .9, "stale — rerun", transform=ax.transAxes)
            continue
        row = comparison(record)
        rows.append(row)
        values = row["simulated"]["mean_vector_speed"]
        ax.scatter(row["measured"], values, s=9)
        score = row["scores"]["mean_vector_speed"]
        lines.append(f"| {spec.state} | {spec.label} | {score['count']} | "
                     + " | ".join(f"{score.get(k, float('nan')):.3f}" for k in ("hit_rate", "fac2", "r", "fb"))
                     + f" | {row['no_building']['hit_rate']:.3f} |")
    fig.supxlabel("Measured scalar speed / U_in(2 m)")
    fig.supylabel("Simulated mean-vector speed / U_in(2 m)")
    fig.tight_layout()
    fig.savefig(output / "c_scatter.png", dpi=150)
    plt.close(fig)
    lines += ["", f"Missing runs: {len(missing)}. Stale runs: {len(stale)}."]
    payload = dict(resolution=resolution, comparisons=rows, missing=missing, stale=stale)
    (output / "case_c.json").write_text(json.dumps(runner._clean(payload), indent=2, allow_nan=False) + "\n")
    (output / "headline_c.md").write_text("\n".join(lines) + "\n")
    print(f"Case C: {len(rows)}/9 current runs, {len(missing)} missing, {len(stale)} stale; {output / 'headline_c.md'}")
    return payload

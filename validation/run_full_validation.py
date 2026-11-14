"""Run the AIJ validation of Cases A, B, D and E at 2 m and 1 m, summarise it and plot where it fails.

    uv run --group validate python validation/run_full_validation.py [--fast]

Runs the baseline campaigns of every case (``campaigns.ab_baseline`` and
``campaigns.baseline``) at both grid spacings through ``run_validation.execute``,
one run at a time with the default thread team, so that the wall times are cost
evidence. A run stored with the current code fingerprint is reused (identical by
construction) and counted as reused in the timing table.

Prints the timing, the headline scores at both spacings, the main flow features
and the weakest kinds of location, and writes the same text (summary.txt) and two
or three figures per case to validation/output/full/: error maps at the finest
spacing, and hit rate and bias per kind of location at both spacings.

``--fast`` runs 13 of the 2 m runs (``FAST_E_LABELS``) and writes to
validation/output/fast/. Its scores track changes of the full set, but differ
from the full set's own scores, so compare a fast run with an earlier fast run.
"""

import argparse
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.colors import TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import run_validation
from archive_results import archive_results
from aij import campaigns, case_ab, case_d, case_e, cityutil, compare, metrics, report, runner, tables
from aij.conventions import AB_LABEL, D_LABELS
from aij.report import BUILDING, DIVERGING, GRID, INK, INK_SECONDARY, MISSING, SERIES, SURFACE

import matplotlib.pyplot as plt  # after aij.report, which selects the Agg backend

VALIDATION = Path(__file__).resolve().parent
RUNS = VALIDATION / "output" / "runs"
OUTPUT = VALIDATION / "output" / "full"
FAST_OUTPUT = VALIDATION / "output" / "fast"
RESOLUTIONS = (2.0, 1.0)  # m, coarse to fine; the maps use the finest
# --fast: Cases A, B and D at 2 m, and Case E at the four diagonal directions in both states. Over the 32
# stored 2 m perturbations of Case E (the sensitivity and tuning-screen variants), these four tracked the
# score changes of all 16 directions best of the subsets tried: RMS error 0.011, and every full-set change
# above 0.03 moved them by more than 0.015 the same way. Their own scores differ from the full set's by up to 0.06.
FAST_RESOLUTIONS = (2.0,)
FAST_E_LABELS = ("NE", "SE", "SW", "NW")
CASES = ("A", "B", "D", "E")
CASE_NAMES = {"A": "A (1:1:2 tower)", "B": "B (4:4:1 slab)", "D": "D (high-rise and blocks)", "E": "E (Niigata)"}
D_EXTENT = (-72.0, -55.0, 82.0, 55.0)  # the probe areas, as in report_validation.py
E_EXTENT = (-150.0, -112.0, 142.0, 130.0)
WALL = ("wall <2 m", "wall 2-5 m", "wall >5 m")
SPEED = ("K <0.2", "K 0.2-0.6", "K >0.6")  # classes of the measured K
# The comparisons pooled per kind of location, and the strata that define the locations. Every
# measured Case D thermistor probe lies 5 m or more from a wall, so Case D is split by wind direction.
POOLED = {"A": ("A-K",), "B": ("B-K",), "D": ("D-thermistor-K",),
          "E": ("E-before-thermistor-K", "E-after-thermistor-K")}
STRATA = {"A": (("region", case_ab.REGIONS),), "B": (("region", case_ab.REGIONS),),
          "D": (("direction", D_LABELS), ("speed", SPEED)),
          "E": (("wall", WALL), ("speed", SPEED), ("slab", ("slab-adjacent", "open")))}
STRATUM_TITLES = dict(region="position relative to the building", wall="distance to the nearest wall",
                      speed="measured speed", slab="elevated slabs (arcades, canopies, pilotis)",
                      direction="wind direction")
MIN_STRATUM = 10  # points a location class needs to be named among the weakest


def specs(resolution: float, fast: bool = False) -> list:
    every = campaigns.ab_baseline(resolution) + campaigns.baseline(resolution)
    return [spec for spec in every if not fast or spec.case != "E" or spec.label in FAST_E_LABELS]


def run_all(plan: dict, fingerprint: str) -> tuple[set, list]:
    """Run every spec of ``plan`` ({resolution: specs}) without a current record, one at a time.

    Returns (keys solved now, failed specs).
    """
    every = [spec for resolution_specs in plan.values() for spec in resolution_specs]
    stale = set()
    for spec in every:
        record = runner.load(RUNS / spec.case, spec.key)
        if record is None or record["fingerprint"] != fingerprint:
            stale.add(spec.key)
    failed = run_validation.execute(every, RUNS, jobs=1, log=lambda line: print(line, flush=True))
    return stale - {spec.key for spec in failed}, failed


def load(resolution_specs: list, fingerprint: str) -> dict:
    """The current records of the specs, keyed (case, state, label); stale and failed runs are left out."""
    records = compare.load_records(RUNS, resolution_specs)
    return {key: record for key, record in records.items() if record["fingerprint"] == fingerprint}


def comparisons(records: dict) -> dict:
    """{case: [Comparison]}: A and B per quantity, D split fibre and thermistor, E per state and quantity."""
    out = {case: compare.isolated(records, case) for case in ("A", "B")}
    out["D"] = compare.case_d(records)
    out["E"] = compare.case_e_comparisons(records)
    return out


def label(comparison) -> str:
    if comparison.case in ("A", "B"):
        return compare.QUANTITY_LABELS[comparison.quantity]
    where = comparison.state if comparison.case == "E" else comparison.instrument.replace("_", " ")
    return f"{where} {'√(|U|²+2k)' if comparison.quantity == 'K_scalar' else '|U|'}"


def _classes(comparison, stratum: str) -> np.ndarray:
    """The class of every (point, direction) value; the "direction" stratum is the direction label."""
    if stratum == "direction":
        return np.broadcast_to(np.array(comparison.labels, dtype=object), comparison.simulated.shape)
    return comparison.strata[stratum]


def _class_name(stratum: str, cls: str) -> str:
    return f"wind {cls}" if stratum == "direction" else cls


def stratum_scores(pool: list, stratum: str, classes) -> dict:
    """Scores of the pooled comparisons per class of ``stratum``."""
    measured = np.concatenate([c.measured.ravel() for c in pool])
    return {cls: metrics.scores(np.concatenate([np.where(_classes(c, stratum) == cls, c.simulated, np.nan).ravel()
                                                for c in pool]), measured)
            for cls in classes}


def _directions(comparison) -> int:
    """Directions with at least one simulated value."""
    return int(np.isfinite(comparison.simulated).any(axis=0).sum())


def location_scores(comps: dict) -> dict:
    """{case: {resolution: {stratum: {class: scores}}}} over the ``POOLED`` comparisons."""
    out = {}
    for case in CASES:
        out[case] = {}
        for resolution, by_case in comps.items():
            pool = [c for c in by_case[case] if c.name in POOLED[case]]
            if pool:
                out[case][resolution] = {stratum: stratum_scores(pool, stratum, classes)
                                         for stratum, classes in STRATA[case]}
    return out


# Console summary ----------------------------------------------------------------------------------------

def _number(value, digits=2, sign=False) -> str:
    if value is None or not np.isfinite(value):
        return "-"
    return f"{value:{'+' if sign else ''}.{digits}f}"


def _each(values: dict, fmt=_number) -> str:
    """'a (2 m), b (1 m)' over the resolutions present."""
    return ", ".join(f"{fmt(v)} ({r:g} m)" for r, v in values.items()) or "no runs"


def timing_table(by_resolution: dict, fresh: set) -> list[str]:
    lines = ["Timing (one run at a time; wall: the whole wind.run call, solver: the native solve)",
             f"{'case':<6}{'grid':>5}{'runs':>6}{'new':>5}{'M cells':>9}{'iterations':>12}{'wall':>10}"
             f"{'per run':>9}{'max':>8}{'solver':>9}{'peak RSS':>10}  threads"]
    for resolution, by_key in by_resolution.items():
        for case in CASES:
            records = [record for (c, _, _), record in by_key.items() if c == case]
            if not records:
                lines.append(f"{case:<6}{resolution:>3g} m  no current runs")
                continue
            wall = np.array([record["wall_seconds"] for record in records])
            solve = sum(record["timings"].get("native", {}).get("solve_seconds", np.nan) for record in records)
            iterations = "/".join(str(i) for i in sorted({record["diagnostics"]["iterations"] for record in records}))
            threads = "/".join(sorted({record["provenance"]["omp_num_threads"] or "default" for record in records}))
            lines.append(f"{case:<6}{resolution:>3g} m{len(records):>6}{sum(r['key'] in fresh for r in records):>5}"
                         f"{np.mean([r['grid']['cells'] for r in records]) / 1e6:>9.1f}{iterations:>12}"
                         f"{wall.sum():>9.0f}s{wall.mean():>8.1f}s{wall.max():>7.1f}s{solve:>8.0f}s"
                         f"{max(r['peak_rss_bytes'] for r in records) / 2 ** 30:>6.2f} GiB  {threads}")
    total = sum(record["wall_seconds"] for records in by_resolution.values() for record in records.values())
    lines.append(f"{'all':<6}{'':>5}{sum(map(len, by_resolution.values())):>6}{len(fresh):>5}{'':>21}{total:>9.0f}s")
    return lines


def score_table(comps: dict) -> list[str]:
    resolutions = list(comps)
    rows = {}
    for case in CASES:
        for resolution in resolutions:
            for comparison in comps[resolution][case]:
                rows.setdefault((case, label(comparison)), {})[resolution] = comparison.scores()
        if case in ("A", "B"):
            null = compare.isolated({}, case, compare.null_model(case), name=f"{case}-null")[0].scores()
            rows[(case, "no building |U|/U_H")] = {resolution: null for resolution in resolutions}
    columns = (("hit_rate", "q", False), ("fac2", "FAC2", False), ("r", "R", False), ("fb", "FB", True))
    block = 7 * len(resolutions) + 2
    lines = ["Agreement with the measurements (q: |s - m| <= 0.25 |m| or <= 0.05, VDI 3783-9 reference 0.66; "
             "FB > 0: dtcc-qes too slow on average)",
             f"{'':<31}{'':>5}" + "".join(f"{title:^{block}}" for _, title, _ in columns),
             f"{'case':<6}{'comparison':<25}{'n':>5}"
             + "".join("  " + "".join(f"{r:>5g} m" for r in resolutions) for _ in columns)]
    for (case, name), by_r in rows.items():
        count = next((s["count"] for r in reversed(resolutions) if (s := by_r.get(r))), 0)
        cells = "".join("  " + "".join(f"{_number(by_r.get(r, {}).get(key), sign=sign):>7}" for r in resolutions)
                        for key, _, sign in columns)
        lines.append(f"{case:<6}{name:<25}{count:>5}{cells}")
    lines.append("(the no-building reference is the undisturbed inflow at each probe; it does not depend on the grid)")
    return lines


def feature_lines(by_resolution: dict, comps: dict) -> list[str]:
    lines = ["Flow features"]
    for case in ("A", "B"):
        b = case_ab.b(case)
        in_b = lambda v: "none" if v is None else f"{v / b:.2f}"
        reattachment, sign, recall = {}, {}, {}
        for resolution, records in by_resolution.items():
            record = records.get((case, "-", AB_LABEL))
            if record is None:
                continue
            reattachment[resolution] = compare.ab_reattachment(records, case)["2"].get("simulated")
            scores = compare.sign_scores(compare.ab_simulated(record)["U"], compare.ab_measured(case)["U"])
            sign[resolution], recall[resolution] = scores["agreement"], scores["reverse_recall"]
        measured = compare.ab_reattachment({}, case)["2"]["measured"]
        lines.append(f"{case}  wake reattachment X_F/b at z = 2 m: measured {in_b(measured)} (published "
                     f"{compare.LITERATURE[case]['wake_experiment']:.2f}), dtcc-qes {_each(reattachment, in_b)}")
        lines.append(f"   streamwise-flow sign agreement {_each(sign)}; measured reverse flow reproduced {_each(recall)}")
    angle, within = {}, {}
    for resolution, records in by_resolution.items():
        extras = compare.split_fibre_extras(records)
        if extras:
            angle[resolution], within[resolution] = extras["angle_error"]["median"], extras["angle_error"]["within_30"]
    lines.append(f"D  split-fibre flow direction at 0°: median error {_each(angle, lambda v: f'{v:.0f}°')}; "
                 f"within 30° {_each(within)}")
    for case in ("D", "E"):
        ratio = compare.inflow_ratio(case)
        for name in POOLED[case]:
            simulated, measured = {}, None
            for resolution, by_case in comps.items():
                for c in by_case[case]:
                    if c.name == name:
                        simulated[resolution] = compare.background_fraction(c.simulated, ratio)
                        measured = compare.background_fraction(c.measured, ratio)
            where = name.split("-")[1]
            lines.append(f"{case}  {where}: share of K within 0.03 of the undisturbed inflow ({ratio:.2f}): "
                         f"measured {_number(measured)}, dtcc-qes {_each(simulated)}")
    change, mean_simulated, mean_measured, directions = {}, {}, None, 0
    for resolution, by_case in comps.items():
        by_name = {c.name: c for c in by_case["E"]}
        before, after = by_name.get("E-before-thermistor-K"), by_name.get("E-after-thermistor-K")
        if before is None or after is None:
            continue
        change[resolution] = metrics.change_scores(before.simulated, after.simulated, before.measured, after.measured)
        mean_simulated[resolution] = np.nanmean(after.simulated - before.simulated)
        # The measured mean over the directions simulated, so that it compares with the simulated one.
        mean_measured = np.nanmean(np.where(np.isfinite(after.simulated - before.simulated),
                                            after.measured - before.measured, np.nan))
        directions = _directions(after)
    signed = lambda v: _number(v, 3, sign=True)
    lines.append(f"E  new buildings, ΔK = K_after - K_before over {directions} directions: mean measured "
                 f"{signed(mean_measured)}, dtcc-qes {_each(mean_simulated, signed)}")
    lines.append(f"   ΔK correlation R {_each({r: s['r'] for r, s in change.items()})}; sign agreement where "
                 f"|ΔK| > 0.04 {_each({r: s['sign_agreement'] for r, s in change.items()})}; "
                 f"top-10 windiest overlap {_each({r: s['top_overlap'] for r, s in change.items()})}")
    return lines


def weakest_lines(locations: dict, resolution: float) -> list[str]:
    lines = [f"Weakest kinds of location at {resolution:g} m (lowest hit rate, classes with >= {MIN_STRATUM} values)"]
    for case in CASES:
        table = locations[case].get(resolution)
        if not table:
            continue
        classes = [(_class_name(stratum, cls), s) for stratum, strata in table.items() for cls, s in strata.items()
                   if s.get("count", 0) >= MIN_STRATUM and "hit_rate" in s]
        classes.sort(key=lambda item: item[1]["hit_rate"])
        quantity = "|U|/U_H" if case in ("A", "B") else "thermistor |U|"
        lines.append(f"{case}  ({quantity}) " + "; ".join(
            f"{cls}: q {s['hit_rate']:.2f}, bias {s['bias']:+.2f} (n {s['count']})" for cls, s in classes[:3]))
    return lines


def header(fingerprint: str, fast: bool) -> list[str]:
    from dtcc_qes import _qes
    git = runner.git_state()
    mode = f"fast (Case E at {', '.join(FAST_E_LABELS)} only)" if fast else "full"
    return [f"AIJ {mode} validation, {time.strftime('%Y-%m-%d %H:%M')}: dtcc-qes {git['revision'][:7]}"
            f"{'+dirty' if git['dirty'] else ''}, solver policy {_qes.solver_policy_revision[:8]}, "
            f"code fingerprint {fingerprint[:12]}"]


# Figures --------------------------------------------------------------------------------------------------

def _figure(nrows, ncols, size):
    return plt.subplots(nrows, ncols, figsize=size, squeeze=False, facecolor=SURFACE, layout="constrained")


def _norm(*values) -> TwoSlopeNorm:
    """A symmetric diverging norm over the finite values, its limit rounded up to 0.05."""
    finite = np.concatenate([np.ravel(v)[np.isfinite(np.ravel(v))] for v in values])
    limit = max(0.05, np.ceil(np.abs(finite).max() / 0.05) * 0.05) if finite.size else 0.05
    return TwoSlopeNorm(0.0, -limit, limit)


def _colourbar(fig, mappable, axes, text):
    bar = fig.colorbar(mappable, ax=list(np.ravel(axes)), orientation="horizontal", shrink=0.5, aspect=40)
    bar.set_label(text, color=INK_SECONDARY, fontsize=9)
    bar.ax.tick_params(colors=INK_SECONDARY, labelsize=8)
    bar.outline.set_visible(False)


def _points(ax, xy, values, norm, size=36):
    """Points coloured by ``values`` on the diverging ramp; missing values as hollow grey rings."""
    ok = np.isfinite(values)
    ax.scatter(*xy[~ok].T, s=size, facecolors="none", edgecolors=MISSING, linewidths=0.8, zorder=3)
    return ax.scatter(*xy[ok].T, c=values[ok], cmap=DIVERGING, norm=norm, s=size, edgecolors=SURFACE,
                      linewidths=0.8, zorder=3)


def _title(ax, text):
    ax.set_title(text, fontsize=10, color=INK)


def _reverse_rings(ax, xy, measured_u):
    reverse = measured_u < -compare.CLEAR_SIGN
    ax.scatter(*xy[reverse].T, s=120, facecolors="none", edgecolors=INK, linewidths=1.1, zorder=2)


def _zero_contour(ax, x, y, u):
    """The simulated U = 0 line (the edge of the recirculation); solids count as forward flow."""
    if np.nanmin(u) < 0:
        ax.contour(x, y, np.nan_to_num(u, nan=1.0), levels=[0.0], colors=INK, linewidths=1.2, zorder=2)


def _recirculation_legend(ax, loc):
    handles = [Line2D([], [], color=INK, lw=1.2, label="dtcc-qes U = 0 (edge of its recirculation)"),
               Line2D([], [], ls="", marker="o", ms=10, mfc="none", mec=INK, label="measured reverse flow")]
    ax.legend(handles=handles, fontsize=8, frameon=False, loc=loc)


def plot_ab_section(case, record, arrays, resolution, path) -> Path:
    """Case A or B: the streamwise-velocity error on the measured vertical section (y = 0)."""
    data = tables.load_results_ab(case)
    vertical = data.section == "vertical"
    xz = data.xyz[vertical][:, [0, 2]]
    measured = compare.ab_measured(case)["U"][vertical]
    error = compare.ab_simulated(record)["U"][vertical] - measured
    b, (depth, _, height) = case_ab.b(case), case_ab.size(case)
    left, right, top = xz[:, 0].min() - b, xz[:, 0].max() + b, 1.15 * xz[:, 1].max()
    fig, axes = _figure(1, 1, (11.0, 11.0 * top / (right - left) + 1.6))
    ax = axes[0, 0]
    x, z = arrays["centre_x"], arrays["centre_z"]
    keep = (x >= left) & (x <= right)
    u = np.where(arrays["centre_valid"], arrays["centre_velocity"][..., 0], np.nan)
    _zero_contour(ax, x[keep] / b, z / b, u[:, keep])
    ax.add_patch(Rectangle((-depth / 2 / b, 0), depth / b, height / b, color=BUILDING, lw=0))
    _reverse_rings(ax, xz / b, measured)
    points = _points(ax, xz / b, error, _norm(error), size=46)
    reattachment = compare.ab_reattachment({(case, "-", AB_LABEL): record}, case)
    for key, marker in (("measured", "^"), ("simulated", "v")):
        for z_, entry in reattachment.items():
            if entry.get(key) is not None:
                ax.plot((depth / 2 + entry[key]) / b, float(z_) / b, marker, ms=9, color=INK, mfc=SURFACE, zorder=4)
    _recirculation_legend(ax, "upper right")
    ax.set(xlim=(left / b, right / b), ylim=(0, top / b), xlabel="x/b (flow toward +x)", ylabel="z/b")
    ax.set_aspect("equal")
    ax.grid(color=GRID, lw=0.6)
    report._style(ax)
    _title(ax, f"Case {CASE_NAMES[case]} at {resolution:g} m: streamwise velocity on the centre plane; "
               f"wake reattachment ▲ measured, ▼ dtcc-qes")
    _colourbar(fig, points, axes, "dtcc-qes - measured U/U_H (red: too fast downstream, blue: too slow or reversed)")
    report._save(fig, path)
    return path


def plot_ab_planes(case, record, arrays, resolution, path) -> Path:
    """Case A or B: the speed error at each measured horizontal section, with the simulated recirculation."""
    data = tables.load_results_ab(case)
    sections = sorted(set(data.section) - {"vertical"}, key=lambda s: data.xyz[data.section == s, 2][0])
    measured, simulated = compare.ab_measured(case), compare.ab_simulated(record)
    error = simulated["K"] - measured["K"]
    horizontal = data.section != "vertical"
    norm = _norm(error[horizontal])
    b, (depth, width, _) = case_ab.b(case), case_ab.size(case)
    xy = data.xyz[horizontal, :2]
    extent = (xy[:, 0].min() - b, xy[:, 1].min() - 0.5 * b, xy[:, 0].max() + b, 0.5 * b)
    panel = 11.0 * (extent[3] - extent[1]) / (extent[2] - extent[0])
    fig, axes = _figure(len(sections), 1, (11.0, panel * len(sections) + 1.6))
    for ax, section in zip(axes[:, 0], sections):
        pick = data.section == section
        height = float(data.xyz[pick, 2][0])
        if f"plane_{height:g}_velocity" in arrays:
            u = np.where(arrays[f"plane_{height:g}_valid"], arrays[f"plane_{height:g}_velocity"][..., 0], np.nan)
            _zero_contour(ax, arrays["x"] / b, arrays["y"] / b, u)
        ax.add_patch(Rectangle((-depth / 2 / b, -width / 2 / b), depth / b, width / b, color=BUILDING, lw=0))
        _reverse_rings(ax, data.xyz[pick, :2] / b, measured["U"][pick])
        points = _points(ax, data.xyz[pick, :2] / b, error[pick], norm, size=46)
        ax.set(xlim=(extent[0] / b, extent[2] / b), ylim=(extent[1] / b, extent[3] / b), xlabel="x/b", ylabel="y/b")
        ax.set_aspect("equal")
        ax.grid(color=GRID, lw=0.6)
        report._style(ax)
        _title(ax, f"section {section} (z = {height:g} m)")
    _recirculation_legend(axes[0, 0], "lower right")
    fig.suptitle(f"Case {CASE_NAMES[case]} at {resolution:g} m: speed error at the horizontal sections "
                 f"(measured on y ≤ 0)", color=INK, fontsize=11)
    _colourbar(fig, points, axes, "dtcc-qes - measured |U|/U_H (red: overprediction)")
    report._save(fig, path)
    return path


def plot_d_maps(thermistor, resolution, path) -> Path:
    """Case D: the thermistor speed error per direction."""
    polygons = [p for _, p, _ in cityutil.footprints(case_d.build_case_d().city)]
    titles = [f"{label_} (φ = {deg:g}°)" for label_, deg in zip(thermistor.labels, thermistor.directions)]
    report.plot_maps(tables.load_points_d().xyz[:, :2], thermistor.simulated - thermistor.measured,
                     thermistor.directions, titles, polygons, path, extent=D_EXTENT, ncols=3, diverging=True,
                     mask=tables.load_exp_t().mirrored, label="dtcc-qes |U|/U_ref - measured thermistor K",
                     suptitle=f"Case D at {resolution:g} m: speed error (red: overprediction; "
                              f"dashed rings: values mirrored from y > 0)")
    return path


def plot_d_vectors(record, resolution, path) -> Path:
    """Case D at 0°: measured and simulated mean wind at the split-fibre probes; rings where they disagree by > 30°."""
    exp_s = tables.load_exp_s()
    m = exp_s.measured
    xy = exp_s.xyz[m, :2]
    measured = exp_s.velocity[m, :2] / tables.U_H
    simulated = np.array(record["probes"]["velocity"], dtype=np.float64)[m, :2] / record["profile"]["reference_speed"]
    angle = metrics.angle_error(simulated, measured)
    distance = np.hypot(*(xy[:, None, :] - xy[None, :, :]).transpose(2, 0, 1))
    spacing = np.median(np.where(distance > 0, distance, np.inf).min(axis=1))
    extent = (*(xy.min(axis=0) - 2 * spacing), *(xy.max(axis=0) + 2 * spacing))
    fig, axes = _figure(1, 1, (9.0, 9.0 * (extent[3] - extent[1]) / (extent[2] - extent[0]) + 0.8))
    ax = axes[0, 0]
    report._map_axes(ax, [p for _, p, _ in cityutil.footprints(case_d.build_case_d().city)], extent)
    off = angle > 30
    ax.scatter(*xy[off].T, s=320, facecolors="none", edgecolors=SERIES[1], linewidths=1.6, zorder=2,
               label=f"direction off by more than 30° ({off.sum()} of {np.isfinite(angle).sum()})")
    arrow = dict(angles="xy", scale_units="xy", scale=1.0 / (0.9 * spacing), width=0.004, zorder=3)
    ax.quiver(*xy.T, *measured.T, color=INK, label="measured (split fibre)", **arrow)
    ax.quiver(*xy.T, *simulated.T, color=SERIES[0], label="dtcc-qes", **arrow)
    report._arrow(ax, exp_s.direction, extent)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    _title(ax, f"Case D at {resolution:g} m, 0°: mean wind at 2 m (arrow length: speed / U_H; "
               f"median direction error {np.nanmedian(angle):.0f}°)")
    report._save(fig, path)
    return path


def _e_map(ax, xy, values, norm, state):
    rows = cityutil.footprints(case_e.build_case_e(state).city)
    report._map_axes(ax, [p for id_, p, _ in rows if id_ not in case_e.NEW_IDS], E_EXTENT)
    new = [np.asarray(p.exterior.coords)[:, :2] for id_, p, _ in rows if id_ in case_e.NEW_IDS]
    ax.add_collection(PolyCollection(new, facecolor=BUILDING, edgecolor=INK, linewidths=1.0, zorder=1))
    return _points(ax, xy, values, norm)


def plot_e_error(before, after, resolution, path) -> Path:
    """Case E: the mean speed error over the simulated directions at each probe, before and after construction."""
    xy = tables.load_points_e().xyz[:, :2]
    errors = [np.nanmean(c.simulated - c.measured, axis=1) for c in (before, after)]
    norm = _norm(*errors)
    size = 7.0 * (E_EXTENT[3] - E_EXTENT[1]) / (E_EXTENT[2] - E_EXTENT[0])
    fig, axes = _figure(1, 2, (14.0, size + 1.4))
    for ax, comparison, error in zip(axes[0], (before, after), errors):
        points = _e_map(ax, xy, error, norm, comparison.state)
        bias = np.nanmean(comparison.simulated - comparison.measured)
        _title(ax, f"{comparison.state} construction (mean error {bias:+.3f})")
    fig.suptitle(f"Case E at {resolution:g} m: speed error averaged over {_directions(after)} directions "
                 f"(outlined: the new buildings)", color=INK, fontsize=11)
    _colourbar(fig, points, axes, "dtcc-qes |U|/U_ref - measured thermistor K (red: overprediction)")
    report._save(fig, path)
    return path


def plot_e_change(before, after, resolution, path) -> Path:
    """Case E: the measured and simulated effect of the new buildings, averaged over the simulated directions."""
    xy = tables.load_points_e().xyz[:, :2]
    simulated = after.simulated - before.simulated
    changes = {"measured": np.nanmean(np.where(np.isfinite(simulated), after.measured - before.measured, np.nan), axis=1),
               "dtcc-qes": np.nanmean(simulated, axis=1)}
    norm = _norm(*changes.values())
    size = 7.0 * (E_EXTENT[3] - E_EXTENT[1]) / (E_EXTENT[2] - E_EXTENT[0])
    fig, axes = _figure(1, 2, (14.0, size + 1.4))
    for ax, (name, change) in zip(axes[0], changes.items()):
        points = _e_map(ax, xy, change, norm, "after")
        _title(ax, f"{name} (mean ΔK {np.nanmean(change):+.3f})")
    fig.suptitle(f"Case E at {resolution:g} m: effect of the new buildings, ΔK = K_after - K_before averaged over "
                 f"{_directions(after)} directions", color=INK, fontsize=11)
    _colourbar(fig, points, axes, "ΔK (red: windier after construction)")
    report._save(fig, path)
    return path


def plot_locations(case, table, quantity, path) -> Path:
    """Hit rate and mean bias per kind of location, one bar per grid spacing."""
    slots = [(stratum, cls) for stratum, classes in STRATA[case] for cls in classes]
    positions, groups, p = [], [], 0.0
    for stratum, classes in STRATA[case]:
        positions += [p + i for i in range(len(classes))]
        groups.append((stratum, p + (len(classes) - 1) / 2))
        p += len(classes) + 0.6
    positions = np.array(positions)
    resolutions = sorted(table, reverse=True)
    width = 0.8 / len(resolutions)
    fig, axes = _figure(2, 1, (max(6.0, 1.2 * len(slots) + 2.0), 6.6))
    for i, resolution in enumerate(resolutions):
        scores = [table[resolution][stratum][cls] for stratum, cls in slots]
        offset = (i - (len(resolutions) - 1) / 2) * width
        for ax, key in zip(axes[:, 0], ("hit_rate", "bias")):
            values = [s.get(key, np.nan) for s in scores]
            ax.bar(positions + offset, values, width - 0.04, color=SERIES[i], label=f"{resolution:g} m", zorder=2)
    finest = table[resolutions[-1]]
    names = [f"{cls}\nn = {finest[stratum][cls]['count']}" for stratum, cls in slots]
    axes[0, 0].axhline(metrics.REFERENCE_HIT_RATE, color=INK_SECONDARY, lw=1, ls=":")
    axes[0, 0].annotate(f"reference {metrics.REFERENCE_HIT_RATE:.2f}", (positions[-1] + 0.5, metrics.REFERENCE_HIT_RATE),
                        xytext=(0, 3), textcoords="offset points", ha="right", fontsize=8, color=INK_SECONDARY)
    axes[0, 0].set(ylim=(0, 1), ylabel="hit rate q")
    axes[0, 0].set_xticks(positions, [])
    axes[1, 0].axhline(0, color=INK_SECONDARY, lw=1)
    axes[1, 0].set(ylabel="mean bias (dtcc-qes - measured)")
    axes[1, 0].set_xticks(positions, names, fontsize=8)
    for stratum, centre in groups:
        axes[1, 0].annotate(STRATUM_TITLES[stratum], (centre, 0), xycoords=axes[1, 0].get_xaxis_transform(),
                            xytext=(0, -32), textcoords="offset points", ha="center", va="top", fontsize=9,
                            color=INK, annotation_clip=False)
    for ax in axes[:, 0]:
        ax.set_xlim(positions[0] - 0.6, positions[-1] + 0.6)
        ax.grid(color=GRID, lw=0.6, axis="y", zorder=0)
        report._style(ax)
    axes[0, 0].legend(fontsize=8, frameon=False, loc="upper left", ncol=len(resolutions))
    fig.suptitle(f"Case {CASE_NAMES[case]}: agreement by kind of location ({quantity})", color=INK, fontsize=11)
    report._save(fig, path)
    return path


def plot_all(by_resolution: dict, comps: dict, locations: dict, output: Path) -> list[Path]:
    """The figures of every case: maps at the finest resolution, locations at every resolution."""
    resolution = min(by_resolution)
    records, out = by_resolution[resolution], []
    for case in ("A", "B"):
        record = records.get((case, "-", AB_LABEL))
        if record is not None:
            with np.load(RUNS / case / f"{record['key']}.npz") as data:
                arrays = {name: data[name] for name in data.files}
            out.append(plot_ab_section(case, record, arrays, resolution, output / f"{case}_1_centre_plane.png"))
            out.append(plot_ab_planes(case, record, arrays, resolution, output / f"{case}_2_sections.png"))
    by_name = {c.name: c for case in ("D", "E") for c in comps[resolution][case]}
    if "D-thermistor-K" in by_name:
        out.append(plot_d_maps(by_name["D-thermistor-K"], resolution, output / "D_1_error_maps.png"))
    if ("D", "-", "0 deg.") in records:
        out.append(plot_d_vectors(records[("D", "-", "0 deg.")], resolution, output / "D_2_split_fibre.png"))
    before, after = by_name.get("E-before-thermistor-K"), by_name.get("E-after-thermistor-K")
    if before is not None and after is not None:
        out.append(plot_e_error(before, after, resolution, output / "E_1_error_maps.png"))
        out.append(plot_e_change(before, after, resolution, output / "E_2_new_buildings.png"))
    quantities = {"A": "|U|/U_H", "B": "|U|/U_H", "D": "thermistor K, 3 directions",
                  "E": f"thermistor K, both states and {_directions(after) if after else 0} directions"}
    for case in CASES:
        if locations[case]:
            out.append(plot_locations(case, locations[case], quantities[case], output / f"{case}_3_locations.png"))
    return sorted(out)


def main(argv=None):
    global RUNS
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive", metavar="LABEL", help="save an immutable checksummed result snapshot")
    parser.add_argument("--output-root", type=Path, default=VALIDATION / "output",
                        help="independent run cache and summaries (for concurrent baseline validation)")
    parser.add_argument("--fast", action="store_true",
                        help=f"only the 13 runs at 2 m with Case E at {', '.join(FAST_E_LABELS)}; "
                             f"figures and summary in {FAST_OUTPUT}")
    args = parser.parse_args(argv)
    RUNS = args.output_root / "runs"
    output = args.output_root / ("fast" if args.fast else "full")
    revision = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=VALIDATION, text=True).strip()
    resolutions = FAST_RESOLUTIONS if args.fast else RESOLUTIONS
    plan = {resolution: specs(resolution, args.fast) for resolution in resolutions}
    started = time.perf_counter()
    fingerprint = runner.fingerprint()
    fresh, failed = run_all(plan, fingerprint)
    solved = time.perf_counter() - started
    # Location classes without points and probes without valid values give NaN scores; that is intended.
    warnings.simplefilter("ignore", RuntimeWarning)
    by_resolution = {resolution: load(resolution_specs, fingerprint) for resolution, resolution_specs in plan.items()}
    comps = {resolution: comparisons(records) for resolution, records in by_resolution.items()}
    locations = location_scores(comps)
    output.mkdir(parents=True, exist_ok=True)
    figures = plot_all(by_resolution, comps, locations, output)
    lines = header(fingerprint, args.fast)
    for block in (timing_table(by_resolution, fresh), score_table(comps), feature_lines(by_resolution, comps),
                  weakest_lines(locations, min(by_resolution)),
                  [f"Figures in {output}:"] + [f"  {path.name}" for path in figures]):
        lines += [""] + block
    lines += ["", f"{len(fresh)} runs solved now in {solved:.0f} s, {len(failed)} failed"
                  + (f" ({', '.join(spec.name for spec in failed)})" if failed else "")
                  + f"; {time.perf_counter() - started:.0f} s in total"]
    text = "\n".join(lines)
    print("\n" + text)
    (output / "summary.txt").write_text(text + "\n")
    if failed:
        sys.exit(1)
    if args.archive:
        records = [(case, record["key"]) for by_key in by_resolution.values()
                   for (case, _, _), record in by_key.items()]
        print("Archived:", archive_results(args.output_root, args.archive, revision,
                                          output, figures, records, fingerprint))


if __name__ == "__main__":
    main()

"""Figures for the AIJ validation (static PNG, light surface).

Colour follows the job: speed ratios use one blue ramp (light = slow), signed
changes a blue-red diverging ramp with a grey midpoint, and series the first
categorical slots in fixed order.
"""

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm  # noqa: E402

from .conventions import flow_vector  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"
BUILDING = "#d9d8d3"
MISSING = "#9a9994"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")  # categorical slots 1-3
SEQUENTIAL = LinearSegmentedColormap.from_list(
    "blue", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIVERGING = LinearSegmentedColormap.from_list(
    "blue_red", ["#184f95", "#3987e5", "#9ec5f4", "#f0efec", "#f4a3a2", "#e34948", "#a32727"])


def _style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MISSING)
    ax.tick_params(colors=INK_SECONDARY, labelsize=8)
    ax.xaxis.label.set_color(INK_SECONDARY)
    ax.yaxis.label.set_color(INK_SECONDARY)


def _figure(nrows, ncols, size):
    fig, axes = plt.subplots(nrows, ncols, figsize=size, squeeze=False, facecolor=SURFACE)
    return fig, axes


def _save(fig, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, facecolor=SURFACE, bbox_inches="tight", metadata={"Software": None})
    plt.close(fig)


def plot_inflow(inflows, profiles, path):
    """Approach-flow speed and k against height; one column per case.

    ``profiles[i]`` maps a label to a dtcc-qes profile drawn as a curve.
    """
    fig, axes = _figure(2, len(inflows), (4.2 * len(inflows), 7.5))
    for col, (inflow, curves) in enumerate(zip(inflows, profiles)):
        top = inflow.heights.max() * 1.05
        z = np.geomspace(0.25, top, 400)
        ax = axes[0, col]
        for (label, profile), colour in zip(curves.items(), SERIES):
            speed = np.hypot(*profile.evaluate(z).T)
            ax.plot(speed, z, color=colour, lw=2, label=label)
        ax.plot(inflow.speeds, inflow.heights, "o", ms=6, mfc=INK, mec=SURFACE, mew=1, label="AIJ table")
        ax.axhline(inflow.reference["height"], color=INK_SECONDARY, lw=1, ls=":")
        ax.annotate(f"reference {inflow.reference['height']:g} m", (ax.get_xlim()[0], inflow.reference["height"]),
                    xytext=(4, 3), textcoords="offset points", fontsize=8, color=INK_SECONDARY)
        ax.set_yscale("log")
        ax.set(ylabel="height above ground [m, full scale]", xlabel="mean speed [m/s, wind tunnel]",
               title=f"Case {inflow.case} inflow")
        ax.title.set_color(INK)
        ax.grid(color=GRID, lw=0.6)
        ax.legend(fontsize=8, frameon=False)
        _style(ax)
        ax = axes[1, col]
        ax.plot(inflow.k, inflow.heights, "o-", ms=6, color=SERIES[0], mfc=INK, mec=SURFACE, lw=2)
        ax.set_yscale("log")
        ax.set(ylabel="height above ground [m, full scale]", xlabel="k [m²/s², wind tunnel]")
        ax.grid(color=GRID, lw=0.6)
        _style(ax)
    fig.tight_layout()
    _save(fig, path)


def _map_axes(ax, polygons, extent):
    ax.add_collection(PolyCollection([np.asarray(p.exterior.coords)[:, :2] for p in polygons],
                                     facecolor=BUILDING, edgecolor="none", zorder=1))
    ax.set_xlim(extent[0], extent[2])
    ax.set_ylim(extent[1], extent[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.set_facecolor(SURFACE)


def _arrow(ax, direction, extent):
    flow = flow_vector(direction)
    width, height = extent[2] - extent[0], extent[3] - extent[1]
    centre = np.array([extent[0] + 0.12 * width, extent[3] - 0.12 * height])
    length = 0.16 * min(width, height)
    ax.annotate("", centre + 0.5 * length * flow, centre - 0.5 * length * flow,
                arrowprops=dict(arrowstyle="-|>", color=INK_SECONDARY, lw=1.5), zorder=4)


def plot_maps(xy, values, directions, titles, polygons, path, *, suptitle, label,
              diverging=False, extent=None, ncols=4, mask=None):
    """One map per direction: buildings in grey, probes coloured by ``values[:, d]``.

    Missing values are hollow rings; ``mask[:, d]`` marks points drawn with a
    dashed ring (for example values copied by symmetry).
    """
    xy = np.asarray(xy)
    if extent is None:
        pad = 0.08 * np.ptp(xy, axis=0).max()
        extent = (*(xy.min(axis=0) - pad), *(xy.max(axis=0) + pad))
    finite = values[np.isfinite(values)]
    if diverging:
        limit = np.abs(finite).max()
        norm, cmap = TwoSlopeNorm(0.0, -limit, limit), DIVERGING
    else:
        norm, cmap = plt.Normalize(0.0, finite.max()), SEQUENTIAL
    nrows = int(np.ceil(len(directions) / ncols))
    width = 3.4 if ncols > 1 else 4.6
    height = width * (extent[3] - extent[1]) / (extent[2] - extent[0])
    fig, axes = _figure(nrows, ncols, (width * ncols, height * nrows + 1.2))
    for d, ax in enumerate(axes.ravel()):
        if d >= len(directions):
            ax.set_visible(False)
            continue
        _map_axes(ax, polygons, extent)
        ok = np.isfinite(values[:, d])
        scatter = ax.scatter(*xy[ok].T, c=values[ok, d], cmap=cmap, norm=norm, s=30,
                             edgecolors=SURFACE, linewidths=0.8, zorder=3)
        ax.scatter(*xy[~ok].T, s=30, facecolors="none", edgecolors=MISSING, linewidths=0.8, zorder=3)
        if mask is not None and mask[:, d].any():
            ax.scatter(*xy[mask[:, d]].T, s=70, facecolors="none", edgecolors=INK_SECONDARY,
                       linewidths=0.6, linestyles="--", zorder=2)
        _arrow(ax, directions[d], extent)
        ax.set_title(titles[d], fontsize=9, color=INK)
    fig.suptitle(suptitle, color=INK, fontsize=11)
    bottom = 0.9 / (height * nrows + 1.2)
    fig.tight_layout(rect=(0, bottom, 1, 1 - 0.45 / (height * nrows + 1.2)))
    bar = fig.colorbar(scatter, cax=fig.add_axes((0.3, 0.45 * bottom, 0.4, 0.18 * bottom)), orientation="horizontal")
    bar.set_label(label, color=INK_SECONDARY, fontsize=9)
    bar.ax.tick_params(colors=INK_SECONDARY, labelsize=8)
    bar.outline.set_visible(False)
    _save(fig, path)


def plot_scalar_estimates(thermistor, estimates, path, *, title):
    """Estimates of the mean scalar speed against the thermistor measurement at the same points.

    ``estimates`` maps a label to values at the points; the dashed lines are 1:1 and ±25 %.
    """
    fig, axes = _figure(1, 1, (4.8, 4.6))
    ax = axes[0, 0]
    top = 1.05 * np.nanmax([thermistor, *estimates.values()])
    line = np.array([0, top])
    ax.plot(line, line, color=INK_SECONDARY, lw=1, ls="--")
    for factor in (0.75, 1.25):
        ax.plot(line, factor * line, color=MISSING, lw=0.8, ls=":")
    ax.annotate("1:1", (0.92 * top, 0.92 * top), xytext=(4, -10), textcoords="offset points",
                fontsize=8, color=INK_SECONDARY)
    for (label, values), colour in zip(estimates.items(), SERIES):
        ax.plot(thermistor, values, "o", ms=6, color=colour, mec=SURFACE, mew=1, label=label)
    ax.set(xlim=(0, top), ylim=(0, top), xlabel="thermistor mean scalar speed / U_H",
           ylabel="estimate from the split fibre / U_H", title=title)
    ax.title.set_color(INK)
    ax.set_aspect("equal")
    ax.grid(color=GRID, lw=0.6)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    _style(ax)
    fig.tight_layout()
    _save(fig, path)


def plot_convergence(rows, path):
    """|K(iteration) - K(float64 end point)| at the probes: p95 (solid) and maximum (dashed)."""
    cases = sorted({r["case"] for r in rows})
    resolutions = sorted({r["resolution"] for r in rows}, reverse=True)
    fig, axes = _figure(len(cases), len(resolutions), (4.6 * len(resolutions), 3.6 * len(cases)))
    for i, case in enumerate(cases):
        for j, resolution in enumerate(resolutions):
            ax = axes[i, j]
            selected = [r for r in rows if r["case"] == case and r["resolution"] == resolution]
            for row, colour in zip(selected, SERIES + ("#eda100",)):
                ax.plot(row["iterations"], row["p95"], color=colour, lw=2, label=row["label"])
                ax.plot(row["iterations"], row["max"], color=colour, lw=1.2, ls="--")
            for target, text in ((0.005, "p95 target"), (0.02, "max target")):
                ax.axhline(target, color=INK_SECONDARY, lw=0.8, ls=":")
                ax.annotate(text, (0, target), xytext=(4, 2),
                            textcoords="offset points", fontsize=7, color=INK_SECONDARY)
            ax.set_yscale("log")
            ax.set(xlabel="iteration", ylabel="|ΔK| at the probes", title=f"Case {case}, {resolution:g} m")
            ax.title.set_color(INK)
            ax.grid(color=GRID, lw=0.6)
            ax.legend(fontsize=8, frameon=False, title="solid p95, dashed max", title_fontsize=7)
            _style(ax)
    fig.tight_layout()
    _save(fig, path)


STRATUM_ORDER = {"wall": ("wall <2 m", "wall 2-5 m", "wall >5 m")}


def _agreement_axes(ax, top):
    line = np.array([0, top])
    ax.plot(line, line, color=INK_SECONDARY, lw=1, ls="--")
    for factor in (0.75, 1.25):
        ax.plot(line, factor * line, color=MISSING, lw=0.8, ls=":")
    ax.set(xlim=(0, top), ylim=(0, top))
    ax.set_aspect("equal")
    ax.grid(color=GRID, lw=0.6)


def _score_text(scores):
    return (f"n = {scores['count']}\nq = {scores['hit_rate']:.2f}  FAC2 = {scores['fac2']:.2f}\n"
            f"R = {scores['r']:.2f}  ρ = {scores['spearman']:.2f}\nbias = {scores['bias']:+.3f}")


def plot_scatter(comparisons, path, *, stratum="wall", ncols=2, suptitle=""):
    """Simulated against measured K, one panel per comparison, coloured by a stratum."""
    nrows = int(np.ceil(len(comparisons) / ncols))
    fig, axes = _figure(nrows, ncols, (4.4 * ncols, 4.4 * nrows))
    top = 1.05 * max(np.nanmax([np.nanmax(c.simulated), np.nanmax(c.measured)]) for c in comparisons)
    for ax, comparison in zip(axes.ravel(), comparisons):
        _agreement_axes(ax, top)
        classes = comparison.strata[stratum]
        for name, colour in zip(STRATUM_ORDER[stratum], SERIES):
            pick = classes == name
            ax.plot(comparison.measured[pick], comparison.simulated[pick], "o", ms=4, color=colour,
                    mec=SURFACE, mew=0.6, alpha=0.85, label=name)
        ax.text(0.03, 0.97, _score_text(comparison.scores()), transform=ax.transAxes, va="top", fontsize=8,
                color=INK_SECONDARY, family="monospace")
        quantity = "√(|U|²+2k)/U_ref" if comparison.quantity == "K_scalar" else "|U|/U_ref"
        ax.set(xlabel=f"measured ({comparison.instrument.replace('_', ' ')})", ylabel=f"dtcc-qes {quantity}",
               title=comparison.name)
        ax.title.set_color(INK)
        ax.legend(fontsize=7, frameon=False, loc="lower right")
        _style(ax)
    for ax in axes.ravel()[len(comparisons):]:
        ax.set_visible(False)
    if suptitle:
        fig.suptitle(suptitle, color=INK, fontsize=11)
    fig.tight_layout()
    _save(fig, path)


def plot_hit_rate_by_direction(series, labels, path, *, reference=0.66, ceiling=None, title=""):
    """Hit rate per direction; ``series`` maps a label to one value per direction."""
    fig, axes = _figure(1, 1, (8.0, 3.6))
    ax = axes[0, 0]
    x = np.arange(len(labels))
    for (name, values), colour in zip(series.items(), SERIES + ("#eda100",)):
        ax.plot(x, values, "o-", color=colour, lw=2, ms=5, mec=SURFACE, label=name)
    ax.axhline(reference, color=INK_SECONDARY, lw=1, ls=":")
    ax.annotate(f"reference {reference:.2f}", (x[-1], reference), xytext=(-70, 3), textcoords="offset points",
                fontsize=8, color=INK_SECONDARY)
    if ceiling is not None:
        ax.axhline(ceiling, color=MISSING, lw=1, ls="--")
        ax.annotate(f"instrument ceiling for |U| (Case D) {ceiling:.2f}", (0, ceiling), xytext=(2, 3),
                    textcoords="offset points", fontsize=8, color=INK_SECONDARY)
    ax.set_xticks(x, labels)
    ax.set(ylim=(0, 1), ylabel="hit rate q (D = 0.25, W = 0.05)", title=title)
    ax.title.set_color(INK)
    ax.grid(color=GRID, lw=0.6)
    ax.legend(fontsize=8, frameon=False, ncol=2, loc="lower left")
    _style(ax)
    fig.tight_layout()
    _save(fig, path)


def plot_change(simulated, measured, path, *, title, scores=None):
    """Simulated against measured change after - before (Case E), all points and directions."""
    fig, axes = _figure(1, 1, (4.6, 4.4))
    ax = axes[0, 0]
    limit = 1.05 * np.nanmax(np.abs([simulated, measured]))
    ax.axhline(0, color=GRID, lw=1)
    ax.axvline(0, color=GRID, lw=1)
    ax.plot([-limit, limit], [-limit, limit], color=INK_SECONDARY, lw=1, ls="--")
    ax.plot(measured.ravel(), simulated.ravel(), "o", ms=3.5, color=SERIES[0], mec=SURFACE, mew=0.5, alpha=0.7)
    if scores:
        ax.text(0.03, 0.97, f"n = {scores['count']}\nR = {scores['r']:.2f}  ρ = {scores['spearman']:.2f}\n"
                f"sign agreement = {scores['sign_agreement']:.2f}\ntop-10 overlap = {scores['top_overlap']:.2f}",
                transform=ax.transAxes, va="top", fontsize=8, color=INK_SECONDARY, family="monospace")
    ax.set(xlim=(-limit, limit), ylim=(-limit, limit), xlabel="measured ΔK (after - before)",
           ylabel="dtcc-qes ΔK", title=title)
    ax.title.set_color(INK)
    ax.set_aspect("equal")
    ax.grid(color=GRID, lw=0.6)
    _style(ax)
    fig.tight_layout()
    _save(fig, path)


def plot_split_fibre(extras, path):
    """Case D 0° at the 33 split-fibre points: k/U_H² and the flow-direction error."""
    fig, axes = _figure(1, 2, (9.0, 4.2))
    ax = axes[0, 0]
    k_sim, k_exp = np.array(extras["k"]["simulated"]), np.array(extras["k"]["measured"])
    top = 1.05 * np.nanmax([k_sim, k_exp])
    _agreement_axes(ax, top)
    ax.plot(k_exp, k_sim, "o", ms=6, color=SERIES[0], mec=SURFACE, mew=1)
    ax.set(xlabel="split fibre k / U_H²", ylabel="dtcc-qes (QES-Turb) k / U_ref²", title="Turbulence energy")
    ax.title.set_color(INK)
    _style(ax)
    ax = axes[0, 1]
    angle = np.array(extras["angle_error"]["values"])
    ax.hist(angle[np.isfinite(angle)], bins=np.arange(0, 181, 15), color=SERIES[0], edgecolor=SURFACE)
    ax.set(xlabel="angle between simulated and measured mean vector [°]", ylabel="points",
           title="Flow direction at 2 m")
    ax.title.set_color(INK)
    ax.grid(color=GRID, lw=0.6, axis="y")
    _style(ax)
    fig.tight_layout()
    _save(fig, path)


def plot_distributions(comparisons, ratios, path, *, ncols=3, suptitle=""):
    """Histograms of measured and simulated K; the dotted line is the approach flow at 2 m."""
    nrows = int(np.ceil(len(comparisons) / ncols))
    fig, axes = _figure(nrows, ncols, (4.0 * ncols, 3.0 * nrows))
    bins = np.linspace(0, 1.4, 36)
    for ax, comparison in zip(axes.ravel(), comparisons):
        measured = comparison.measured[np.isfinite(comparison.measured)]
        simulated = comparison.simulated[np.isfinite(comparison.simulated)]
        ax.hist(measured, bins=bins, color=SERIES[0], alpha=0.8, label="measured", edgecolor=SURFACE)
        ax.hist(simulated, bins=bins, histtype="step", color=SERIES[1], lw=2, label="dtcc-qes")
        ratio = ratios[comparison.case]
        ax.axvline(ratio, color=INK_SECONDARY, lw=1, ls=":")
        ax.set(xlabel="K", ylabel="count", title=comparison.name)
        ax.title.set_color(INK)
        ax.grid(color=GRID, lw=0.6, axis="y")
        ax.legend(fontsize=7, frameon=False, loc="upper right")
        _style(ax)
    for ax in axes.ravel()[len(comparisons):]:
        ax.set_visible(False)
    if suptitle:
        fig.suptitle(suptitle, color=INK, fontsize=11)
    fig.tight_layout()
    _save(fig, path)


def plot_scores_by_resolution(tables, path, *, title=""):
    """Agreement scores against grid spacing; ``tables`` maps a resolution to {comparison: scores}."""
    resolutions = sorted(tables, reverse=True)
    names = [n for n in ("D-split_fibre", "D-thermistor-K", "E-before-thermistor-K", "E-after-thermistor-K")
             if any(n in tables[r] for r in resolutions)]
    fig, axes = _figure(1, 4, (16.0, 3.6))
    for ax, (key, label) in zip(axes.ravel(), (("hit_rate", "hit rate q"), ("fb", "FB (> 0: underprediction)"),
                                               ("r", "Pearson R"), ("spearman", "Spearman ρ"))):
        for name, colour in zip(names, SERIES + ("#eda100",)):
            values = [tables[r].get(name, {}).get(key, np.nan) for r in resolutions]
            ax.plot(resolutions, values, "o-", color=colour, lw=2, ms=5, mec=SURFACE, label=name.replace("-thermistor-K", " thermistor").replace("_", " "))
        if key == "fb":
            ax.axhline(0, color=INK_SECONDARY, lw=0.8, ls=":")
        ax.set_xscale("log", base=2)
        ax.set_xticks(resolutions, [f"{r:g}" for r in resolutions])
        ax.invert_xaxis()
        ax.set(xlabel="grid spacing [m]", ylabel=label)
        ax.grid(color=GRID, lw=0.6)
        _style(ax)
    axes[0, 0].legend(fontsize=7, frameon=False)
    if title:
        fig.suptitle(title, color=INK, fontsize=11)
    fig.tight_layout()
    _save(fig, path)


def plot_refinement(rows, path, *, title=""):
    """K at the finer grid against K at the coarser one: one row per case, one panel per refinement.

    ``rows`` maps a case label to {pair label: (coarse K, fine K, wall classes)}.
    """
    ncols = max(len(pairs) for pairs in rows.values())
    fig, axes = _figure(len(rows), ncols, (3.6 * ncols, 3.7 * len(rows)))
    for i, (case, pairs) in enumerate(rows.items()):
        for j in range(ncols):
            ax = axes[i, j]
            if j >= len(pairs):
                ax.set_visible(False)
                continue
            label, (coarse, fine, walls) = list(pairs.items())[j]
            top = 1.05 * np.nanmax([coarse, fine])
            _agreement_axes(ax, top)
            for name, colour in zip(STRATUM_ORDER["wall"], SERIES):
                pick = walls == name
                ax.plot(coarse[pick], fine[pick], "o", ms=3, color=colour, mec=SURFACE, mew=0.4, alpha=0.8, label=name)
            ax.set(xlabel="K, coarser grid", ylabel="K, finer grid", title=f"{case}: {label}")
            ax.title.set_color(INK)
            _style(ax)
            if j == 0:
                ax.legend(fontsize=7, frameon=False, loc="lower right")
    if title:
        fig.suptitle(title, color=INK, fontsize=11)
    fig.tight_layout()
    _save(fig, path)


EFFECT_SERIES = (("E-before-thermistor-K", "E before"), ("E-after-thermistor-K", "E after"),
                 ("D-split_fibre", "D split fibre"), ("D-thermistor-K", "D thermistor"))


def plot_effects(effects, path, *, title="", band=0.03):
    """Score change against the base per variant: one row per variant, one panel per score.

    ``effects`` maps a variant to {comparison: {"hit_rate": Δ, "fb": Δ, "r": Δ}}. The grey band is
    the Phase 4 grid-error resolution of the scores.
    """
    names = list(effects)
    y = np.arange(len(names))[::-1]
    fig, axes = _figure(1, 3, (14.0, 0.34 * len(names) + 1.6))
    for ax, (key, label) in zip(axes.ravel(), (("hit_rate", "Δ hit rate q"), ("fb", "Δ FB (> 0: lower speeds)"),
                                               ("r", "Δ Pearson R"))):
        ax.axvspan(-band, band, color=GRID, lw=0)
        ax.axvline(0, color=INK_SECONDARY, lw=0.8)
        for (comparison, short), colour in zip(EFFECT_SERIES, SERIES + ("#eda100",)):
            values = [effects[n].get(comparison, {}).get(key, np.nan) for n in names]
            ax.plot(values, y, "o", ms=6, color=colour, mec=SURFACE, mew=0.8, label=short)
        ax.set_yticks(y, names if ax is axes[0, 0] else [""] * len(names))
        ax.set(xlabel=label, ylim=(-0.7, len(names) - 0.3))
        ax.grid(color=GRID, lw=0.6, axis="x")
        _style(ax)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    if title:
        fig.suptitle(title, color=INK, fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.97 - 0.25 / fig.get_size_inches()[1]))
    fig.legend(handles, labels, loc="upper center", ncol=len(labels), frameon=False, fontsize=8,
               bbox_to_anchor=(0.5, 1 - 0.45 / fig.get_size_inches()[1]))
    _save(fig, path)


def plot_search(steps, path, *, reference=0.66):
    """The tuning search: every candidate's training hit rate per step, the kept one highlighted."""
    fig, axes = _figure(1, 1, (8.0, 3.8))
    ax = axes[0, 0]
    for step in steps:
        x = step["step"]
        q = [c["objective"]["q"] for c in step["candidates"]]
        ax.plot(np.full(len(q), x) + np.linspace(-0.12, 0.12, len(q)), q, "o", ms=4, color=MISSING, mec=SURFACE, mew=0.4)
        ax.plot([x - 0.3, x + 0.3], [step["start_objective"]["q"]] * 2, color=INK_SECONDARY, lw=1.5)
        best = next(c for c in step["candidates"] if c["label"] == step["best"])
        ax.plot(x, best["objective"]["q"], "o", ms=8, color=SERIES[0] if step["accepted"] else SERIES[1], mec=SURFACE)
        ax.annotate(step["best"] + ("" if step["accepted"] else " (not kept)"), (x, best["objective"]["q"]),
                    xytext=(8, 4 if step["accepted"] else -12), textcoords="offset points", fontsize=7,
                    color=INK_SECONDARY)
    ax.axhline(reference, color=INK_SECONDARY, lw=1, ls=":")
    ax.annotate(f"VDI reference {reference:.2f}", (steps[0]["step"] - 0.4, reference), xytext=(0, 3),
                textcoords="offset points", fontsize=7, color=INK_SECONDARY)
    ax.set_xticks([s["step"] for s in steps])
    ax.set(xlabel="search step", ylabel="hit rate q, Case E before (training)", ylim=(0, max(0.7, ax.get_ylim()[1])),
           title="Tuning search: candidates (grey), start (line), best (blue: kept)")
    ax.title.set_color(INK)
    ax.grid(color=GRID, lw=0.6, axis="y")
    _style(ax)
    fig.tight_layout()
    _save(fig, path)

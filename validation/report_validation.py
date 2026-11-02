"""Reports of the AIJ validation runs (AIJ_VALIDATION_PLAN.md, Phase 2 onwards).

    uv run --group validate python validation/report_validation.py

Reads validation/output/runs and writes validation/output/report/:
- numerics.json, convergence.png (Phase 2);
- comparisons.json, headline.md and the comparison figures (Phase 3);
- grid.json and the grid-study figures (Phase 4);
- sensitivity.json, tuning.json and their figures (Phase 5).
"""

import argparse
import json
from pathlib import Path

import numpy as np

from dataclasses import replace

from aij import (campaigns, case_d, case_e, cityutil, compare, gridstudy, metrics, numerics, report, sensitivity,
                 tables)

VALIDATION = Path(__file__).resolve().parent
RUNS = VALIDATION / "output" / "runs"
OUTPUT = VALIDATION / "output" / "report"


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def numerics_report(runs, output):
    smoke = numerics.smoke_table(numerics.records(runs, "smoke"))
    convergence = numerics.convergence(numerics.records(runs, "convergence"))
    (output / "numerics.json").write_text(json.dumps(dict(smoke=smoke, convergence=convergence), indent=1) + "\n")
    if convergence:
        report.plot_convergence(convergence, output / "convergence.png")


def _comparison_summary(comparison):
    out = dict(name=comparison.name, case=comparison.case, state=comparison.state,
               instrument=comparison.instrument, quantity=comparison.quantity,
               pooled=comparison.scores(),
               by_direction={label: metrics.scores(comparison.simulated[:, d], comparison.measured[:, d])
                             for d, label in enumerate(comparison.labels)},
               strata={name: {str(cls): comparison.scores(classes == cls)
                              for cls in sorted({c for c in np.ravel(classes) if c is not None})}
                       for name, classes in comparison.strata.items()})
    if "mirror" in comparison.strata:
        out["independent"] = comparison.scores(comparison.strata["mirror"] == "measured")
    return out


def _provenance(records):
    record = next(iter(records.values()))
    return dict(dtcc_qes=record["provenance"]["versions"]["dtcc_qes"], git=record["provenance"]["git"],
                solver_policy_revision=record["provenance"].get("solver_policy_revision"),
                model=record["provenance"].get("model"),
                fingerprints=sorted({r["fingerprint"] for r in records.values()}))


def _headline(provenance, rows):
    revision = provenance["git"]["revision"][:7] + ("+dirty" if provenance["git"]["dirty"] else "")
    policy = (provenance["solver_policy_revision"] or "")[:8]
    lines = ["| dtcc-qes | policy | Comparison | Model | n | q | FAC2 | R | ρ | FB |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, quantity, scores in rows:
        lines.append(f"| `{revision}` | `{policy}` | {name} | {quantity} | {scores['count']} | {scores['hit_rate']:.2f} | "
                     f"{scores['fac2']:.2f} | {scores['r']:.2f} | {scores['spearman']:.2f} | {scores['fb']:+.2f} |")
    return "\n".join(lines) + "\n"


def comparison_report(runs, output, resolution=2.0):
    records = compare.load_records(runs, campaigns.baseline(resolution))
    if not records:
        return None
    d = compare.case_d(records)
    e = compare.case_e_comparisons(records)
    comparisons = d + e
    summary = dict(resolution=resolution, runs=len(records), provenance=_provenance(records),
                   comparisons=[_comparison_summary(c) for c in comparisons],
                   instrument_ceiling=compare.instrument_ceiling(),
                   split_fibre=compare.split_fibre_extras(records))
    by_name = {c.name: c for c in comparisons}
    changes = {}
    for quantity in ("K", "K_scalar"):
        before, after = by_name.get(f"E-before-thermistor-{quantity}"), by_name.get(f"E-after-thermistor-{quantity}")
        if before is not None and after is not None:
            changes[quantity] = metrics.change_scores(before.simulated, after.simulated, before.measured, after.measured)
    summary["change"] = changes
    ratios = {case: compare.inflow_ratio(case) for case in ("D", "E")}
    summary["approach_flow"] = dict(
        ratio_at_probe_height=ratios,
        background_fraction={c.name: dict(simulated=compare.background_fraction(c.simulated, ratios[c.case]),
                                           measured=compare.background_fraction(c.measured, ratios[c.case]))
                             for c in comparisons})
    (output / "comparisons.json").write_text(json.dumps(_clean(summary), indent=1) + "\n")

    # Figures
    tag = f"{resolution:g} m"
    report.plot_distributions(comparisons, ratios, output / "distributions.png", ncols=3,
                              suptitle=f"Distributions of K at {tag} (dotted: the approach flow at 2 m)")
    if d:
        report.plot_scatter(d, output / "case_d_scatter.png", ncols=3, suptitle=f"Case D at {tag}")
    if e:
        report.plot_scatter(e, output / "case_e_scatter.png", ncols=2, suptitle=f"Case E at {tag}")
        series = {f"{c.state}, {'√(|U|²+2k)' if c.quantity == 'K_scalar' else '|U|'}":
                  [metrics.hit_rate(c.simulated[:, k], c.measured[:, k]) for k in range(len(c.labels))] for c in e}
        report.plot_hit_rate_by_direction(series, e[0].labels, output / "case_e_hit_rate.png",
                                          ceiling=summary["instrument_ceiling"]["vector"]["hit_rate"],
                                          title=f"Case E at {tag}: hit rate per direction")
        if "K" in changes:
            before, after = by_name["E-before-thermistor-K"], by_name["E-after-thermistor-K"]
            report.plot_change(after.simulated - before.simulated, after.measured - before.measured,
                               output / "case_e_change.png", title=f"Case E at {tag}: effect of the new buildings",
                               scores=changes["K"])
        after = by_name.get("E-after-thermistor-K_scalar")
        if after is not None:
            polygons = [p for _, p, _ in cityutil.footprints(case_e.build_case_e("after").city)]
            report.plot_maps(case_e_xy(after), after.simulated - after.measured, after.directions,
                             [f"{label} (φ = {deg:g}°)" for label, deg in zip(after.labels, after.directions)],
                             polygons, output / "case_e_after_error.png", extent=(-150.0, -112.0, 142.0, 130.0),
                             diverging=True, label="dtcc-qes √(|U|²+2k)/U_ref - measured",
                             suptitle=f"Case E after, {tag}: simulated - measured (red: overprediction)")
    thermistor = by_name.get("D-thermistor-K_scalar")
    if thermistor is not None:
        polygons = [p for _, p, _ in cityutil.footprints(case_d.build_case_d().city)]
        report.plot_maps(case_e_xy(thermistor), thermistor.simulated - thermistor.measured, thermistor.directions,
                         [f"{label} (φ = {deg:g}°)" for label, deg in zip(thermistor.labels, thermistor.directions)],
                         polygons, output / "case_d_error.png", extent=(-72.0, -55.0, 82.0, 55.0), ncols=3,
                         diverging=True, label="dtcc-qes √(|U|²+2k)/U_ref - measured",
                         suptitle=f"Case D, {tag}: simulated - measured thermistor (red: overprediction)")
    if summary["split_fibre"] and "k" in summary["split_fibre"]:
        report.plot_split_fibre(summary["split_fibre"], output / "case_d_split_fibre.png")

    rows = []
    for comparison in comparisons:
        scores = comparison.scores()
        if scores.get("count", 0) >= 3:
            rows.append((comparison.name.rsplit("-K", 1)[0], "√(\\|U\\|²+2k)" if comparison.quantity == "K_scalar" else "\\|U\\|",
                         scores))
    (output / "headline.md").write_text(_headline(summary["provenance"], rows))
    return summary


def _refinement_data(coarse, fine):
    """(coarse K, fine K, wall classes) over the runs present at both resolutions."""
    keys = sorted(set(coarse) & set(fine))
    k = lambda r: np.array([np.nan if v is None else v for v in r["probes"]["K"]], dtype=np.float64)
    walls = lambda r: np.array(r["probes"]["wall_distance"], dtype=np.float64)
    wall_class = lambda w: np.where(w < 2, "wall <2 m", np.where(w < 5, "wall 2-5 m", "wall >5 m"))
    return (np.concatenate([k(coarse[key]) for key in keys]), np.concatenate([k(fine[key]) for key in keys]),
            np.concatenate([wall_class(walls(fine[key])) for key in keys]))


def grid_report(runs, output):
    by_resolution = {r: gridstudy.load(runs, campaigns.baseline(r)) for r in campaigns.GRID_RESOLUTIONS}
    by_resolution = {r: records for r, records in by_resolution.items() if records}
    fine = gridstudy.load(runs, campaigns.fine_subset(campaigns.FINE_RESOLUTION))
    if len(by_resolution) < 2:
        return None
    subset = gridstudy.subset_keys()
    resolutions = sorted(by_resolution, reverse=True)
    pairs = list(zip(resolutions[:-1], resolutions[1:]))
    summary = dict(resolutions=resolutions, fine_runs=len(fine),
                   changes={f"{a:g}->{b:g}": gridstudy.changes(by_resolution[a], by_resolution[b]) for a, b in pairs},
                   scores={f"{r:g}": gridstudy.scores(records) for r, records in by_resolution.items()},
                   fallbacks={f"{r:g}": gridstudy.fallbacks(records) for r, records in by_resolution.items()})
    subset_scores = {r: gridstudy.scores({k: v for k, v in records.items() if k in subset})
                     for r, records in by_resolution.items()}
    if fine:
        finest = min(by_resolution)
        summary["changes"][f"{finest:g}->{campaigns.FINE_RESOLUTION:g}"] = gridstudy.changes(
            {k: v for k, v in by_resolution[finest].items() if k in subset}, fine)
        subset_scores[campaigns.FINE_RESOLUTION] = gridstudy.scores(fine)
        summary["fallbacks"][f"{campaigns.FINE_RESOLUTION:g}"] = gridstudy.fallbacks(fine)
    summary["subset_scores"] = {f"{r:g}": table for r, table in subset_scores.items()}
    # Direction of the last two refinements: full matrix over the three coarsest, subset over the three finest.
    levels = [(resolutions[:3], by_resolution, None)]
    if fine and len(resolutions) >= 2:
        levels.append((resolutions[-2:] + [campaigns.FINE_RESOLUTION], {**by_resolution, campaigns.FINE_RESOLUTION: fine},
                       subset))
    summary["trend"] = {}
    for chain, records, keep in levels:
        if len(chain) < 3:
            continue
        for case in ("D", "E"):
            pick = [{k: v for k, v in records[r].items() if k[0] == case and (keep is None or k in keep)} for r in chain]
            summary["trend"][f"{case} {'->'.join(f'{r:g}' for r in chain)}"] = gridstudy.trend(*pick)
    all_resolutions = sorted(set(by_resolution) | ({campaigns.FINE_RESOLUTION} if fine else set()), reverse=True)
    summary["subcell_gaps"] = {
        "D": gridstudy.subcell_gaps([p for _, p, _ in cityutil.footprints(case_d.build_case_d().city)], all_resolutions),
        "E-after": gridstudy.subcell_gaps([p for _, p, _ in cityutil.footprints(case_e.build_case_e("after").city)],
                                          all_resolutions)}
    check = numerics.records(runs, "fine_check")
    if check:
        summary["fine_check"] = numerics.self_convergence(check[0][1])
    (output / "grid.json").write_text(json.dumps(_clean(gridstudy.to_json(summary)), indent=1) + "\n")

    report.plot_scores_by_resolution({r: summary["scores"][f"{r:g}"] for r in by_resolution},
                                     output / "grid_scores.png", title="Agreement against grid spacing (all runs)")
    if fine:
        report.plot_scores_by_resolution(subset_scores, output / "grid_scores_subset.png",
                                         title="Agreement against grid spacing (0.5 m subset: D 0°, E SW/SSW/E/WSW)")
    rows = {}
    for case, label in (("D", "Case D"), ("E", "Case E")):
        rows[label] = {}
        for a, b in pairs:
            coarse = {k: v for k, v in by_resolution[a].items() if k[0] == case}
            finer = {k: v for k, v in by_resolution[b].items() if k[0] == case}
            rows[label][f"{a:g} → {b:g} m"] = _refinement_data(coarse, finer)
        if fine:
            finest = min(by_resolution)
            coarse = {k: v for k, v in by_resolution[finest].items() if k[0] == case and k in subset}
            finer = {k: v for k, v in fine.items() if k[0] == case}
            if finer:
                rows[label][f"{finest:g} → {campaigns.FINE_RESOLUTION:g} m (subset)"] = _refinement_data(coarse, finer)
    report.plot_refinement(rows, output / "grid_refinement.png", title="Probe K under grid refinement")
    return summary


def _deltas(effect) -> dict:
    """Variant minus base for the Phase 5 comparisons: {comparison: {score: Δ}}."""
    out = {}
    for name in sensitivity.COMPARISONS:
        base, variant = effect["base"].get(name), effect["variant"].get(name)
        if base and variant:
            out[name] = {k: variant[k] - base[k] for k in ("hit_rate", "fac2", "fb", "r", "spearman")}
    base, variant = effect["base"].get("E-change"), effect["variant"].get("E-change")
    if base and variant:
        out["E-change"] = {k: variant[k] - base[k] for k in ("r", "spearman", "sign_agreement", "top_overlap")}
    return out


def _effect_row(effect) -> dict:
    return dict(runs=effect["runs"], deltas=_deltas(effect), base=sensitivity.summary(effect["base"]),
                variant=sensitivity.summary(effect["variant"]),
                probe_change={case: {k: entry[k] for k in ("p95", "max", "changed_fraction", "mean_shift")}
                              for case, entry in effect["changes"].items()},
                **({"split_fibre_k": effect["split_fibre_k"]} if "split_fibre_k" in effect else {}))


def sensitivity_report(runs, output):
    """Phase 5, part A, and the first tuning step on the full matrix: one change from the base each."""
    base = compare.load_records(runs, campaigns.baseline(2.0))
    if not base:
        return None
    variants, upstream_sets = {}, {"base": base}
    for name, specs in campaigns.sensitivity_variants():
        records = compare.load_records(runs, specs)
        if len(records) == len(specs):
            variants[name] = _effect_row(sensitivity.effect(base, records))
            if name == "ground z0 0.05 m":
                upstream_sets[name] = records
    variants["nearest-cell sampling"] = _effect_row(sensitivity.effect(base, sensitivity.nearest(base, runs)))
    comparisons = compare.case_d(base, ("K",)) + compare.case_e_comparisons(base, ("K",))
    neighbourhood = {c.name: {k: s[k] for k in ("count", "hit_rate", "fac2", "fb", "r", "spearman")}
                     for c in comparisons if c.instrument and (s := sensitivity.neighbourhood_best(c, base).scores())}
    screen = {}
    for label, config in campaigns.tuning_candidates({}):
        specs = campaigns.tuned(config)
        records = compare.load_records(runs, specs)
        if len(records) == len(specs):
            screen[label] = _effect_row(sensitivity.effect(base, records))
    sources = (("D", "-", case_d.build_case_d().city, tables.load_inflow_d()),
               ("E", "before", case_e.build_case_e("before").city, tables.load_inflow_e()))
    upstream = {label: {case: sensitivity.upstream_turbulence(
                            {k: v for k, v in records.items() if k[:2] == (case, state)}, runs,
                            [p for _, p, _ in cityutil.footprints(city)], table)
                        for case, state, city, table in sources}
                for label, records in upstream_sets.items()}
    summary = dict(base=sensitivity.summary(gridstudy.scores(base, ("K", "K_scalar"))), variants=variants,
                   neighbourhood_best=neighbourhood, screen=screen, upstream_turbulence=upstream)
    (output / "sensitivity.json").write_text(json.dumps(_clean(summary), indent=1) + "\n")
    if variants:
        report.plot_effects({n: v["deltas"] for n, v in variants.items()}, output / "sensitivity.png",
                            title="Phase 5 sensitivity at 2 m: score change from the base (grey: ±0.03, the grid-error band)")
    if screen:
        report.plot_effects({n: v["deltas"] for n, v in screen.items()}, output / "tuning_screen.png",
                            title="Single tuning changes at 2 m: score change from the base (grey: ±0.03)")
    return summary


def tuning_report(runs, output):
    """Phase 5, part B: the search log, and the tuned against the base settings on training and test sets."""
    path = VALIDATION / "output" / "tuning" / "search.json"
    if not path.exists():
        return None
    search = json.loads(path.read_text())
    config = {k: tuple(v) if k == "canopy" else v for k, v in search["final"].items()}
    out = dict(objective=search["objective"], final=search["final"], final_objective=search["final_objective"],
               steps=[{k: step[k] for k in ("step", "start", "start_objective", "best", "accepted")}
                      for step in search["steps"]], resolutions={})
    report.plot_search(search["steps"], output / "tuning_search.png")
    for resolution in (2.0, 1.0):
        base = compare.load_records(runs, campaigns.baseline(resolution))
        tuned = compare.load_records(runs, campaigns.tuned(config, resolution))
        if len(base) < 35 or len(tuned) < 35:
            continue
        effect = sensitivity.effect(base, tuned)
        row = _effect_row(effect)
        row["neighbourhood_best"] = {}
        for which, records in (("base", base), ("tuned", tuned)):
            comparisons = compare.case_d(records, ("K",)) + compare.case_e_comparisons(records, ("K",))
            row["neighbourhood_best"][which] = {c.name: sensitivity.neighbourhood_best(c, records).scores()["hit_rate"]
                                                for c in comparisons}
            row.setdefault("background_fraction", {})[which] = {
                c.name: compare.background_fraction(c.simulated, compare.inflow_ratio(c.case)) for c in comparisons}
        out["resolutions"][f"{resolution:g}"] = row
        if resolution != 2.0:
            continue
        pick = lambda records, label: [replace(c, name=f"{label}: {c.name.replace('-thermistor-K', '').replace('_', ' ')}")
                                       for c in compare.case_e_comparisons(records, ("K",)) + compare.case_d(records, ("K",))
                                       if c.name in ("E-before-thermistor-K", "E-after-thermistor-K", "D-split_fibre")]
        report.plot_scatter(pick(base, "base") + pick(tuned, "tuned"), output / "tuning_scatter.png", ncols=3,
                            suptitle="Base (top) and tuned (bottom) settings at 2 m; E before is the training set")
        tuned_comparisons = compare.case_d(tuned, ("K",)) + compare.case_e_comparisons(tuned, ("K",))
        report.plot_distributions(tuned_comparisons, {c: compare.inflow_ratio(c) for c in ("D", "E")},
                                  output / "tuning_distributions.png", ncols=3,
                                  suptitle="Distributions of K with the tuned settings at 2 m (dotted: the approach flow at 2 m)")
        by_name = {c.name: c for c in tuned_comparisons}
        before, after = by_name["E-before-thermistor-K"], by_name["E-after-thermistor-K"]
        report.plot_change(after.simulated - before.simulated, after.measured - before.measured,
                           output / "tuning_change.png", title="Tuned settings at 2 m: effect of the new buildings",
                           scores=metrics.change_scores(before.simulated, after.simulated, before.measured, after.measured))
    (output / "tuning.json").write_text(json.dumps(_clean(out), indent=1) + "\n")
    return out


def case_e_xy(comparison):
    """Probe x, y for a comparison, from the measurement tables."""
    from aij import tables
    points = tables.load_points_d() if comparison.case == "D" else tables.load_points_e()
    return points.xyz[:, :2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=Path, default=RUNS)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--resolution", type=float, default=2.0, help="baseline resolution to compare [m]")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    numerics_report(args.runs, args.output)
    summary = comparison_report(args.runs, args.output, args.resolution)
    grid = grid_report(args.runs, args.output)
    phase5 = sensitivity_report(args.runs, args.output)
    tuning = tuning_report(args.runs, args.output)
    if phase5:
        for group in ("variants", "screen"):
            for name, row in phase5[group].items():
                deltas = row["deltas"]
                print(f"{group} {name}: " + ", ".join(
                    f"{c.replace('-thermistor-K', '')} dq {d['hit_rate']:+.2f} dFB {d['fb']:+.2f} dR {d['r']:+.2f}"
                    for c, d in deltas.items() if c != "E-change")
                      + (f", change R {deltas['E-change']['r']:+.2f}" if "E-change" in deltas else ""))
    if tuning:
        print(f"tuning: {tuning['final']} objective {tuning['final_objective']}")
        for resolution, row in tuning["resolutions"].items():
            for name in row["variant"]:
                b, t = row["base"][name], row["variant"][name]
                print(f"  {resolution} m {name}: " + ", ".join(f"{k} {b[k]:.2f}->{t[k]:.2f}" for k in t if k != "count"))
    if grid:
        for pair, cases in grid["changes"].items():
            for case, entry in cases.items():
                print(f"grid {pair} {case}: p95 |dK| {entry['p95']:.3f}, max {entry['max']:.3f}, "
                      f"changed {entry['changed_fraction']:.2f}, mean shift {entry['mean_shift']:+.3f}")
                for name, strata in (("wall", entry["by_wall"]), ("span", entry["by_span"])):
                    print("    by " + name + ": " + ", ".join(f"{c} p95 {b['p95']:.3f} changed {b['changed_fraction']:.2f}"
                                                         f" (n {b['count']})" for c, b in strata.items() if b["count"]))
        for chain, t in grid["trend"].items():
            if t["count"]:
                print(f"trend {chain}: {t['count']} values change > {t['threshold']} last; "
                      f"same direction {t['same_direction']:.2f}, median ratio {t['median_ratio']:.2f}")
        for r, table in grid["scores"].items():
            print(f"scores {r} m: " + ", ".join(f"{n} q {s['hit_rate']:.2f} FB {s['fb']:+.2f} R {s['r']:.2f}"
                                               for n, s in table.items() if "hit_rate" in s))
        if "fine_check" in grid:
            check = grid["fine_check"]
            print(f"0.5 m check: required {check['required_iterations']}, within 1e-4 from {check['within_1e4_from']}, "
                  f"{ {k: v for k, v in check.items() if k.startswith('at_')} }")
    if summary:
        print((args.output / "headline.md").read_text())
        ceiling = summary["instrument_ceiling"]
        print(f"instrument ceiling (Case D 0°, 33 points): |U| q = {ceiling['vector']['hit_rate']:.2f}, "
              f"√(|U|²+2k) q = {ceiling['scalar']['hit_rate']:.2f}")
        print(f"approach flow at 2 m: {summary['approach_flow']['ratio_at_probe_height']}")
        for name, fractions in summary["approach_flow"]["background_fraction"].items():
            print(f"  {name}: within 0.03 of it: simulated {fractions['simulated']:.2f}, measured {fractions['measured']:.2f}")
        for quantity, scores in summary["change"].items():
            print(f"Case E change ({quantity}): {scores}")
        if summary["split_fibre"]:
            extras = summary["split_fibre"]
            print(f"Case D split fibre: angle error median {extras['angle_error']['median']:.0f}°, "
                  f"within 30° {extras['angle_error']['within_30']:.2f}; k {extras.get('k', {}).get('scores')}")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

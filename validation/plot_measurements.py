"""Phase 1 of the AIJ validation: the measured data, inflow fits and direction checks.

    uv run --group validate python validation/plot_measurements.py

Writes validation/output/measurements/{measurements.json, *.png}. No dtcc-qes
solve is involved. See AIJ_VALIDATION_PLAN.md (Phase 1) and AIJ_VALIDATION.md.
"""

import argparse
import json
from pathlib import Path

import numpy as np

from aij import case_d, case_e, cityutil, conventions, inflow, metrics, report, tables

OUTPUT = Path(__file__).resolve().parent / "output" / "measurements"


def _stats(values):
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    return dict(count=int(values.size), min=float(values.min()), median=float(np.median(values)),
                mean=float(values.mean()), max=float(values.max()))


def _polygons(city):
    return [p for _, p, _ in cityutil.footprints(city)], np.array([h for _, _, h in cityutil.footprints(city)])


def _inflow_summary(data):
    tail = inflow.fit_log(data.heights, data.speeds, count=inflow.TAIL_POINTS)
    power = inflow.fit_power_law(data.heights, data.speeds, data.reference["height"], inflow.FIT_HEIGHT[data.case])
    log = inflow.fit_log(data.heights, data.speeds, inflow.FIT_HEIGHT[data.case])
    reference = {kind: inflow.reference_speed(inflow.profile(data, kind, 270.0)) for kind in inflow.KINDS}
    reference["measured_linear"] = inflow.reference_speed(inflow.measured_profile(data, 270.0, interpolation="linear"))
    return dict(heights=data.heights.tolist(), speeds=data.speeds.tolist(), reference=data.reference,
                tail=tail._asdict(), power_law=power._asdict(), log=log._asdict(),
                reference_speed=reference)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args(argv)
    out = args.output
    summary = {}

    # Inflow
    flows = [tables.load_inflow_d(), tables.load_inflow_e()]
    curves = [{"measured (baseline)": inflow.measured_profile(f, 270.0),
               "power-law fit": inflow.power_law_profile(f, 270.0),
               "log-law fit": inflow.log_profile(f, 270.0)} for f in flows]
    report.plot_inflow(flows, curves, out / "inflow.png")
    summary["inflow"] = {f.case: _inflow_summary(f) for f in flows}

    # Case D
    city_d = case_d.build_case_d().city
    polygons_d, _ = _polygons(city_d)
    exp_s, exp_t = tables.load_exp_s(), tables.load_exp_t()
    xy_d = exp_t.xyz[:, :2]
    extent_d = (-72.0, -55.0, 82.0, 55.0)
    report.plot_maps(xy_d, exp_t.values, exp_t.directions,
                     [f"{label} (φ = {d:g}°)" for label, d in zip(exp_t.labels, exp_t.directions)],
                     polygons_d, out / "case_d_thermistor.png", ncols=3, extent=extent_d, mask=exp_t.mirrored,
                     suptitle="Case D, thermistor: scalar speed / U_H at 2 m (dashed ring: copied by symmetry)",
                     label="Vs / U_H")
    report.plot_maps(xy_d, exp_s.speed_ratio[:, None], [exp_s.direction], ["0 deg. (φ = 270°)"],
                     polygons_d, out / "case_d_split_fibre.png", ncols=1, extent=extent_d,
                     suptitle="Case D, split fibre: |mean vector| / U_H at 2 m", label="|U| / U_H")
    measured = exp_s.measured
    thermistor = exp_t.values[measured, 0]
    estimates = {"|mean vector|": exp_s.speed_ratio[measured],
                 "√(|mean vector|² + 2k)": np.sqrt(exp_s.speed_ratio[measured] ** 2
                                                   + 2 * exp_s.k[measured] / tables.U_H ** 2)}
    report.plot_scalar_estimates(thermistor, estimates, out / "case_d_scalar_estimates.png",
                                 title="Case D, 0°: the 33 split-fibre points")
    upstream = np.isin(exp_s.ids, (8, 9))
    summary["case_d"] = dict(
        split_fibre=dict(measured=int(measured.sum()), ids=exp_s.ids[measured].tolist(),
                         speed_ratio=_stats(exp_s.speed_ratio), k_ratio=_stats(exp_s.k / tables.U_H ** 2)),
        thermistor={label: _stats(exp_t.values[:, d]) for d, label in enumerate(exp_t.labels)}
        | dict(missing=exp_t.ids[np.isnan(exp_t.values).all(axis=1)].tolist(),
               mirrored_at_0=int(exp_t.mirrored[:, 0].sum())),
        scalar_estimates_at_0={label: dict(ratio_to_thermistor=_stats(values / thermistor),
                                           within_25_percent=float(np.mean(np.abs(values / thermistor - 1) <= 0.25)),
                                           spearman=metrics.spearman(values, thermistor))
                               for label, values in estimates.items()},
        direction_checks=dict(
            reverse_flow_upstream_of_tower={int(i): float(u) for i, u in
                                            zip(exp_s.ids[upstream], exp_s.velocity[upstream, 0])},
            mirror_symmetry={name: conventions.mirror_symmetry(exp_t.values, xy_d, name).tolist()
                             for name in conventions.REFLECTIONS}))

    # Case E
    before, after = tables.load_results_e("before"), tables.load_results_e("after")
    city_before, city_after = case_e.build_case_e("before").city, case_e.build_case_e("after").city
    polygons_after, _ = _polygons(city_after)
    xy_e = after.xyz[:, :2]
    extent_e = (-150.0, -112.0, 142.0, 130.0)
    titles = [f"{label} (φ = {d:g}°)" for label, d in zip(after.labels, after.directions)]
    for measurements, city in ((before, city_before), (after, city_after)):
        report.plot_maps(xy_e, measurements.values, measurements.directions, titles, _polygons(city)[0],
                         out / f"case_e_{measurements.state}.png", extent=extent_e,
                         suptitle=f"Case E {measurements.state} construction: speed at 2 m / inflow at 15.9 m",
                         label="K")
    delta = after.values - before.values
    report.plot_maps(xy_e, delta, after.directions, titles, polygons_after, out / "case_e_change.png",
                     extent=extent_e, diverging=True, label="K after - K before",
                     suptitle="Case E: measured change from the new buildings (after - before)")
    quantum = tables.E_QUANTUM
    polygons_before, heights_before = _polygons(city_before)
    summary["case_e"] = dict(
        before=_stats(before.values), after=_stats(after.values), change=_stats(delta),
        quantum=quantum,
        largest_quantisation_residual=float(np.abs(np.r_[before.values.ravel(), after.values.ravel()] / quantum
                                                   - np.round(np.r_[before.values.ravel(),
                                                                    after.values.ravel()] / quantum)).max()),
        mapping_check=conventions.mapping_check(before.values, xy_e, polygons_before, heights_before))

    out.mkdir(parents=True, exist_ok=True)
    (out / "measurements.json").write_text(json.dumps(summary, indent=2) + "\n")
    best = min(summary["case_e"]["mapping_check"], key=lambda r: r["median_rho"])
    print(f"Case E mapping check: best {best['sense']} offset {best['offset']:g}, "
          f"median rho {best['median_rho']:.3f}")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()

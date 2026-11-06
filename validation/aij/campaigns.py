"""Campaign matrices of the AIJ validation (AIJ_VALIDATION_PLAN.md, Phases 2-5; AIJ_AB_VALIDATION.md).

Kept apart from ``runspec`` so that adding a campaign does not change the code
fingerprint of stored runs: every setting that changes a result is a RunSpec
field, and so part of the run key.
"""

from dataclasses import replace
from itertools import product

from dtcc_qes import wind

from .conventions import AB_DIRECTION, AB_LABEL, D_ANGLES, D_LABELS, E_LABELS, E_STATES, d_direction, e_direction
from .runspec import AB_DOMAIN, RunSpec

# Fixed solver work per resolution (Phase 2). The tolerance lies below the float32
# multiplier-change stall, so every run does exactly this many iterations. At 2 m and
# 1 m the probe speeds are then within about 1e-4 of the float64 end point (AIJ_VALIDATION.md).
# 0.5 m was set by the Phase 4 check (campaign "fine_check"): the probes stay within 1e-4
# of the 32,000-iteration end point from 13,200 iterations on.
ITERATIONS = {8.0: 1000, 4.0: 1000, 2.0: 2000, 1.0: 6000, 0.5: 16000}
FIXED_WORK_TOLERANCE = 1.2e-7

CONVERGENCE_ITERATIONS = {2.0: 8000, 1.0: 16000}
CONVERGENCE_E_LABELS = ("N", "E", "S", "W")

# Phase 4. The 0.5 m subset: Case D at 0°, and the four Case E directions whose measured
# K changes most between the states (mean |after - before|: SW 0.22, SSW 0.18, E 0.18,
# WSW 0.17), in both states. Turbulence is off there: it doubles memory (Phase 2), and it
# leaves the mean wind unchanged. Without it, 100-142 M cells took 6.8-9.9 GiB (Phase 4).
GRID_RESOLUTIONS = (4.0, 2.0, 1.0)
FINE_RESOLUTION = 0.5
FINE_E_LABELS = ("SW", "SSW", "E", "WSW")
FINE_MAX_CELLS = 200_000_000
FINE_CHECK_ITERATIONS = 32000

# Cases A and B (AIJ_AB_VALIDATION.md). The baseline spacing is 1 m: b/16 in Case A and b/8
# through the Case B slab. The grid study adds 4, 2 and 0.5 m; the domains are small enough
# to keep turbulence on at 0.5 m (about 55 M cells).
AB_CASES = ("A", "B")
AB_RESOLUTION = 1.0
AB_GRID = (4.0, 2.0, 1.0, 0.5)


def case_d(angle: float, **options) -> RunSpec:
    return RunSpec("D", D_LABELS[D_ANGLES.index(angle)], d_direction(angle), **options)


def case_e(label: str, state: str = "after", **options) -> RunSpec:
    options.setdefault("min_detail", 0.1)
    return RunSpec("E", label, e_direction(label), state=state, **options)


def case_ab(case: str, **options) -> RunSpec:
    """Case A or B at its single direction, with the A/B domain unless overridden."""
    for name, value in AB_DOMAIN.items():
        options.setdefault(name, value)
    return RunSpec(case, AB_LABEL, AB_DIRECTION, **options)


def fixed_work(spec: RunSpec) -> RunSpec:
    """``spec`` with the Phase 2 solver work for its resolution."""
    return replace(spec, tolerance=FIXED_WORK_TOLERANCE, max_iterations=ITERATIONS[spec.resolution])


def baseline(resolution: float = 2.0, **options) -> list[RunSpec]:
    """Every measured direction and state of both cases, with the baseline settings."""
    specs = [case_d(a, resolution=resolution, **options) for a in D_ANGLES]
    specs += [case_e(label, state, resolution=resolution, **options) for state in E_STATES for label in E_LABELS]
    return [fixed_work(s) for s in specs]


def ab_baseline(resolution: float = AB_RESOLUTION, **options) -> list[RunSpec]:
    """Cases A and B with the baseline settings; above 20 M cells (0.5 m) with a raised cell cap."""
    if resolution < AB_RESOLUTION:
        options.setdefault("max_cells", FINE_MAX_CELLS)
    return [fixed_work(case_ab(case, resolution=resolution, **options)) for case in AB_CASES]


def campaign(name: str) -> list[RunSpec]:
    """The run matrix of a named campaign."""
    if name.startswith("ab_"):
        return ab_campaign(name)
    if name == "smoke":
        specs = []
        for resolution in (8.0, 4.0, 2.0):
            specs += [case_d(0.0, resolution=resolution), case_e("N", resolution=resolution)]
        # The cost of turbulence, which leaves the mean wind unchanged.
        specs += [case_d(0.0, resolution=2.0, turbulence=False), case_e("N", resolution=2.0, turbulence=False)]
        return specs
    if name == "convergence":
        specs = []
        for resolution, iterations in CONVERGENCE_ITERATIONS.items():
            bases = [case_d(a, resolution=resolution) for a in D_ANGLES]
            bases += [case_e(label, resolution=resolution) for label in CONVERGENCE_E_LABELS]
            for base in bases:
                # Probe histories in float32 (identical iterates to a legacy solve), and a float64 end point.
                specs.append(replace(base, tolerance=1.2e-7, max_iterations=iterations, monitor=True,
                                     turbulence=False))
                specs.append(replace(base, precision="float64", tolerance=1e-12, max_iterations=iterations,
                                     turbulence=False))
            # One legacy default run per resolution and case: checks that the history equals a legacy solve.
            specs += [replace(bases[0], turbulence=False), replace(bases[3], turbulence=False)]
        return specs
    if name == "baseline":
        return baseline(2.0)
    if name == "grid":
        return baseline(4.0) + baseline(1.0)
    if name == "fine_check":
        # Probe histories at 0.5 m, to confirm ITERATIONS[0.5] before the subset runs.
        spec = case_e(FINE_E_LABELS[0], resolution=FINE_RESOLUTION, turbulence=False, max_cells=FINE_MAX_CELLS)
        return [replace(spec, tolerance=FIXED_WORK_TOLERANCE, max_iterations=FINE_CHECK_ITERATIONS, monitor=True,
                        checkpoint_interval=100)]
    if name == "fine":
        return fine_subset(FINE_RESOLUTION)
    if name == "sensitivity":
        return [spec for _, specs in sensitivity_variants() for spec in specs]
    if name == "tuning_screen":
        return [spec for _, config in tuning_candidates({}) for spec in tuned(config)]
    raise ValueError(f"Unknown campaign {name!r}")


# Phase 5, part A: one change from the base settings per variant (AIJ_VALIDATION_PLAN.md).
# A value given as {case: value} differs between the cases; "cases" limits a variant to one case.
SENSITIVITY = (
    ("power-law inflow", dict(inflow="power_law"), "DE"),
    ("log-law inflow", dict(inflow="log"), "DE"),
    ("linear profile interpolation", dict(interpolation="linear"), "DE"),
    ("Footprints δ = 0.5 m", dict(min_detail=0.5), "E"),
    ("Footprints δ = 0.01 m", dict(min_detail=0.01), "E"),
    ("QES-ready City", dict(city="qes_ready"), "E"),
    ("slabs filled to the ground", dict(city="slabs_filled"), "E"),
    ("padding 100 m", dict(padding=100.0), "D"),
    ("top clearance H_max", dict(clearance={"D": 100.0, "E": 60.0}), "DE"),
    ("uniform vertical grid", dict(vertical="uniform"), "DE"),
    ("ground z0 0.05 m", dict(ground_roughness=0.05), "DE"),
)


def _resolve(changes: dict, case: str) -> dict:
    return {k: v[case] if isinstance(v, dict) and k != "parameterizations" else v for k, v in changes.items()}


def sensitivity_variants(resolution: float = 2.0) -> list[tuple[str, list[RunSpec]]]:
    return [(name, [replace(spec, **_resolve(changes, spec.case)) for spec in baseline(resolution) if spec.case in cases])
            for name, changes, cases in SENSITIVITY]


# Phase 5, part B: tuning. The canopy inflow scales with the area-weighted mean building height
# (Case E: the "before" state); tests check these against the Cities.
CANOPY_HEIGHT = {"D": 10.43, "E": 6.03}
CANOPY_A = (0.03, 0.1, 0.3)  # z0_u / H
CANOPY_B = (3.0, 6.0, 10.0)  # z_b / H
FLAG_CODES = dict(rooftop=(0, 1, 2), upwind_cavity=(0, 1, 2, 3), street_canyon=(0, 1), wake=(1, 2),
                  high_rise=(0, 1), sidewall=(0, 1))
WALL_ROUGHNESS = (1e-4, 1e-3, 1e-2, 1e-1)
TRAINING = ("E", "before")


def canopy(case: str, a: float, b: float) -> dict:
    """RunSpec changes for the canopy inflow with z0_u = a·H and z_b = b·H of ``case``."""
    height = CANOPY_HEIGHT[case]
    return dict(inflow="canopy", canopy_roughness=round(a * height, 4), blending_height=round(b * height, 4))


def tuned(config: dict, resolution: float = 2.0, select=None) -> list[RunSpec]:
    """The baseline runs with a tuning configuration: {"parameterizations": {...}, "canopy": (a, b)}.

    ``select`` keeps only runs with (case, state) in it. The empty configuration is the baseline.
    """
    specs = []
    for spec in baseline(resolution):
        if select is not None and (spec.case, spec.state) not in select:
            continue
        changes = dict(parameterizations=config.get("parameterizations", {}))
        if config.get("canopy"):
            changes.update(canopy(spec.case, *config["canopy"]))
        specs.append(replace(spec, **changes))
    return specs


def tuning_candidates(config: dict) -> list[tuple[str, dict]]:
    """Every single change from ``config`` that the Phase 5 search tries, as (label, configuration)."""
    flags = dict(config.get("parameterizations", {}))
    current = wind.Parameterizations(**flags)
    options = [(f"{name}={code}", {**flags, name: code})
               for name, codes in FLAG_CODES.items() for code in codes if code != getattr(current, name)]
    if current.wake:
        options.append(("wake off (with rooftop, street canyon, sidewall)",
                        {**flags, "wake": 0, "rooftop": 0, "street_canyon": 0, "sidewall": 0}))
    options += [(f"wall_roughness={z0:g}", {**flags, "wall_roughness": z0})
                for z0 in WALL_ROUGHNESS if z0 != current.wall_roughness]
    out = []
    for label, values in options:
        try:
            wind.Parameterizations(**values)
        except ValueError:
            continue  # e.g. a rooftop model while the wake is off
        out.append((label, {**config, "parameterizations": values}))
    for a, b in product(CANOPY_A, CANOPY_B):
        if config.get("canopy") != (a, b):
            out.append((f"canopy a={a:g} b={b:g}", {**config, "canopy": (a, b)}))
    if config.get("canopy"):
        out.append(("no canopy", {k: v for k, v in config.items() if k != "canopy"}))
    return out


def fine_subset(resolution: float) -> list[RunSpec]:
    """The Phase 4 subset at ``resolution``; at 0.5 m without turbulence and with a raised cell cap."""
    fine = resolution == FINE_RESOLUTION
    options = dict(turbulence=False, max_cells=FINE_MAX_CELLS) if fine else {}
    specs = [case_d(0.0, resolution=resolution, **options)]
    specs += [case_e(label, state, resolution=resolution, **options)
              for state in E_STATES for label in FINE_E_LABELS]
    return [fixed_work(s) for s in specs]


def physics_foundation(experiment: str, resolutions=(2.0,1.0)) -> list[RunSpec]:
    """Finite E0 matrices, using precisely the existing AIJ adapters/defaults."""
    specs = []
    for resolution in resolutions:
        if experiment=="E0e":
            specs.extend(baseline(resolution))
        elif experiment=="E0a":
            specs.extend(fixed_work(case_e(label,state,resolution=resolution))
                         for state in ("after","before") for label in E_LABELS)
        elif experiment in ("E0c","E0f"):
            specs.extend(fixed_work(case_d(angle,resolution=resolution,turbulence=False)) for angle in D_ANGLES)
            specs.extend(fixed_work(case_e(label,resolution=resolution,turbulence=False)) for label in ("N","E","S","W"))
        elif experiment=="E0d":
            specs.extend(fixed_work(case_e(label,resolution=resolution,turbulence=False)) for label in ("N","E","SW","W"))
        else:
            raise ValueError(experiment)
    return specs


# Cases A and B, one change from the baseline per variant. The building parameterizations come first:
# isolated buildings are the flows the Röckle-type models were built for.
AB_SENSITIVITY = (
    ("rooftop vortex", dict(parameterizations=dict(rooftop=2))),
    ("rooftop off", dict(parameterizations=dict(rooftop=0))),
    ("upwind cavity Röckle", dict(parameterizations=dict(upwind_cavity=1))),
    ("upwind cavity HMVP", dict(parameterizations=dict(upwind_cavity=3))),
    ("upwind cavity off", dict(parameterizations=dict(upwind_cavity=0))),
    ("wake Röckle", dict(parameterizations=dict(wake=1))),
    ("sidewall off", dict(parameterizations=dict(sidewall=0))),
    ("high-rise model", dict(parameterizations=dict(high_rise=1))),
    ("wall z0 0.01 m", dict(parameterizations=dict(wall_roughness=0.01))),
    ("power-law inflow", dict(inflow="power_law")),
    ("log-law inflow", dict(inflow="log")),
    ("linear profile interpolation", dict(interpolation="linear")),
    ("domain 5 H / 15 H", dict(padding=160.0, downstream=480.0, max_cells=FINE_MAX_CELLS)),
    # QES-Turb needs the top above its 3 H reference height plus two layers, so 4 H is the lowest top.
    ("top at 4 H", dict(clearance=96.0)),
    ("top at 8 H", dict(clearance=224.0)),
    ("uniform vertical grid", dict(vertical="uniform")),
    # The floor roughness of the AIJ CFD specifications at full scale: 1.8e-4 m x 200 (Mochida et al. 2002)
    # and 9.6e-5 m x 160 (Shirasawa et al. 2003); the fitted tails are about 100 times smoother.
    ("ground z0 of the AIJ CFD specs", dict(ground_roughness={"A": 0.036, "B": 0.0154})),
)


def ab_sensitivity_variants(resolution: float = AB_RESOLUTION) -> list[tuple[str, list[RunSpec]]]:
    return [(name, [replace(spec, **_resolve(changes, spec.case)) for spec in ab_baseline(resolution)])
            for name, changes in AB_SENSITIVITY]


def ab_campaign(name: str) -> list[RunSpec]:
    """The run matrices of Cases A and B; the names mirror the Case D/E campaigns."""
    if name == "ab_smoke":
        specs = [case_ab(case, resolution=r) for r in (4.0, 2.0, 1.0) for case in AB_CASES]
        return specs + [case_ab(case, resolution=1.0, turbulence=False) for case in AB_CASES]
    if name == "ab_convergence":
        specs = []
        for resolution, iterations in CONVERGENCE_ITERATIONS.items():
            for case in AB_CASES:
                base = case_ab(case, resolution=resolution, turbulence=False)
                specs += [replace(base, tolerance=1.2e-7, max_iterations=iterations, monitor=True),
                          replace(base, precision="float64", tolerance=1e-12, max_iterations=iterations), base]
        return specs
    if name == "ab_baseline":
        return ab_baseline()
    if name == "ab_grid":
        return [spec for r in AB_GRID if r != AB_RESOLUTION for spec in ab_baseline(r)]
    if name == "ab_sensitivity":
        return [spec for _, specs in ab_sensitivity_variants() for spec in specs]
    raise ValueError(f"Unknown campaign {name!r}")

"""Campaign matrices of the AIJ validation (AIJ_VALIDATION_PLAN.md, Phases 2-5).

Kept apart from ``runspec`` so that adding a campaign does not change the code
fingerprint of stored runs: every setting that changes a result is a RunSpec
field, and so part of the run key.
"""

from dataclasses import replace
from itertools import product

from dtcc_qes import wind

from .conventions import D_ANGLES, D_LABELS, E_LABELS, E_STATES, d_direction, e_direction
from .runspec import RunSpec

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


def case_d(angle: float, **options) -> RunSpec:
    return RunSpec("D", D_LABELS[D_ANGLES.index(angle)], d_direction(angle), **options)


def case_e(label: str, state: str = "after", **options) -> RunSpec:
    options.setdefault("min_detail", 0.1)
    return RunSpec("E", label, e_direction(label), state=state, **options)


def fixed_work(spec: RunSpec) -> RunSpec:
    """``spec`` with the Phase 2 solver work for its resolution."""
    return replace(spec, tolerance=FIXED_WORK_TOLERANCE, max_iterations=ITERATIONS[spec.resolution])


def baseline(resolution: float = 2.0, **options) -> list[RunSpec]:
    """Every measured direction and state of both cases, with the baseline settings."""
    specs = [case_d(a, resolution=resolution, **options) for a in D_ANGLES]
    specs += [case_e(label, state, resolution=resolution, **options) for state in E_STATES for label in E_LABELS]
    return [fixed_work(s) for s in specs]


def campaign(name: str) -> list[RunSpec]:
    """The run matrix of a named campaign."""
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

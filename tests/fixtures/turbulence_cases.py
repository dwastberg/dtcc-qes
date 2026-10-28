"""Standalone turbulence cases, shared by generation and bridge comparisons."""

from dataclasses import dataclass, replace

from fixtures.cases import Case, FLAT, ONE_BUILDING


@dataclass(frozen=True)
class TurbulenceCase:
    case: Case
    method: int = 0
    dz_layers: tuple[float, ...] = ()
    upstream_exclusion: str | None = None


def named(case, name, **changes):
    return replace(case, name=name, **changes)


OBLIQUE = replace(FLAT.wind, direction=225.0)
THIN = replace(ONE_BUILDING.grid, nz=80)
LAYER_SOLVER = replace(ONE_BUILDING.solver, max_iterations=20000)
NONUNIFORM = (0.125, 0.375, 0.75, 1.25) * 20
CASES = {
    spec.case.name: spec for spec in (
        TurbulenceCase(FLAT),
        TurbulenceCase(named(FLAT, "flat_oblique", wind=OBLIQUE)),
        TurbulenceCase(ONE_BUILDING),
        TurbulenceCase(named(ONE_BUILDING, "building_oblique", wind=OBLIQUE)),
        TurbulenceCase(named(ONE_BUILDING, "building_wall"), method=1),
        TurbulenceCase(named(ONE_BUILDING, "building_thin_wall", grid=THIN, solver=LAYER_SOLVER), method=1,
                       dz_layers=(0.5,) * 80,
                       upstream_exclusion="Known upstream serial wall-distance coordinate overflow on this grid"),
        TurbulenceCase(named(ONE_BUILDING, "building_nonuniform", grid=THIN, solver=LAYER_SOLVER),
                       dz_layers=NONUNIFORM,
                       upstream_exclusion="Pristine nonuniform turbulence path has not been safety-qualified"),
        TurbulenceCase(named(ONE_BUILDING, "building_nonuniform_wall", grid=THIN, solver=LAYER_SOLVER), method=1,
                       dz_layers=NONUNIFORM,
                       upstream_exclusion="Thin/nonuniform upstream serial wall-distance bounds are unsafe"),
    )
}

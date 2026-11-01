# dtcc-qes

In-memory QES-Winds CPU simulation for DTCC cities, with optional algebraic
turbulence and pedestrian comfort assessment. Wind arrays are float32; the
solver supports float32 and float64 workspaces. GPL-3.0-only.

## Quick start and installation

Python 3.13+, CMake 3.18+ and a C++17 compiler are required. From this checkout:

```sh
uv sync --frozen --group dev
uv run --frozen --no-sync python examples/single_building.py
```

OpenMP is on by default. On macOS install Homebrew `libomp`; custom installations
can set `OpenMP_ROOT`. Set `-Ccmake.define.DTCC_QES_OPENMP=OFF` during `uv sync`
for a serial build. Both builds use red/black ordering. Keep `uv.lock` for
reproduction; the vendored core, licenses and notices ship in the sdist.

```python
from dtcc_core.model import City
from dtcc_qes import wind

city = City()  # Replace with measured-height LOD0 buildings in a planar metre frame.
bounds = (0, 0, 0, 24, 24, 32)
result = wind.run(city, speed=5, direction=270, bounds=bounds)
sample = result.sample(1.75, method="linear")
volume = result.to_dtcc()
```

Bounds use global coordinates; array coordinates are local to `result.origin`.
Empty cities require bounds. Ground must be flat: use `terrain="flat"` to
explicitly flatten terrain, or a numeric elevation. Rotations and scale
transforms are unsupported. Building parts, holes and contacts require
`footprints=wind.Footprints(...)`; canonical cleaning preserves height steps.
See [building contacts](docs/building-contacts.md).

## Inflow profiles

`speed=` and `direction=` construct `LogProfile` with a 10 m reference and
0.1 m roughness. Directions are meteorological FROM, clockwise from north.
All profile families carry their own reference height and ground roughness.

```python
profile = wind.LogProfile(5, 270, roughness_length=.1)
rotated = profile.with_direction(360)  # Rigid rotation; calm references cannot rotate.
measured = wind.MeasuredProfile([1, 10, 100], [2, 5, 7], direction=270,
    reference_height=10, roughness_length=.1, below="log", above="constant")
u, v = wind.evaluate(measured, [1.5, 10, 20])
restored = wind.profile_from_dict(measured.to_dict())  # schema_version=2
```

`UniformProfile` and `PowerLawProfile` are experimental controls/inputs.
Measured profiles interpolate u/v components in log height by default, with
explicit lower/upper tail policies. Coverage includes every final cell centre.
Turning greater than 45° across layers warns: wakes use roof-level direction.
See [profile conventions and caveats](docs/wind-profiles.md).

## Domains and vertical grids

A six-coordinate bounds tuple may end with `None`: the shared planner then
chooses the top and extends it if turbulence needs more clearance. A numeric
zmax is fixed and checked without extension. `domain["top_requirements"]`
attributes roof clearance, inflow reference, cell count and turbulence margins.

```python
preview = wind.preview_grid(city, bounds=(0, 0, 0, 24, 24, None))
assert preview.domain["inflow"] == "unknown"  # No invented calm inflow.
planned = wind.preview_grid(city, profile, bounds=bounds,
                            vertical_grid=wind.VerticalGrid.auto())
```

`VerticalGrid.from_faces(...)` copies explicit physical faces above ground.
`VerticalGrid.auto()` is `prototype_unvalidated`; it is not a comfort preset.
Diagnostics use the selected profile and interpolate components before speed.
Nonuniform grids cannot be represented by uniform DTCC `VolumeGrid`:
use native arrays/`z_faces`, sampled planes, or a dataset slice.

## Turbulence

```python
turbulent = wind.run(city, profile, bounds=bounds,
    turbulence=wind.Turbulence("height"))  # Or "wall_distance".
```

QES-Turb is algebraic screening, unvalidated for pedestrian gusts. Its
building-derived reference, roughness and displacement differ from the inflow
reference. Arbitrary jets/shear may conflict with its log-law conversion.
`computed`, `capped` and covariance `stress_valid` masks are independent.
Uncomputed floats and unusable derived statistics remain NaN; raw invalid
stress tensors are retained. Vertical sampling interpolates the six stress
components before streamwise projection and preserves invalid contributors.
See [model and numerical evidence](QES_TURBULENCE.md).

## Solver

`Solver()` uses tolerance `1e-4`, at most 1,000 iterations and float32 arithmetic.
These shared direct/dataset defaults passed the predeclared two-city
[accuracy/latency study](docs/data/feature-merge/phase5.json). Multiplier-change
convergence is not a mass residual, grid-independence or physical certificate.

```python
monitor = wind.MonitorSpec((0, 24, 0, 24))
bounded = wind.Solver(max_solve_seconds=2, monitor=monitor)
controlled = wind.run(city, profile, bounds=bounds, solver=bounded)
precise = wind.Solver(precision="float64", tolerance=1e-8, max_iterations=8000)
adaptive = wind.Solver(max_solve_seconds=5, policy="pedestrian-v1",
    monitor=wind.MonitorSpec((0, 80, 0, 80), history_limit=8,
        receptors=tuple(wind.Receptor(f"h{h}", 27, 21, h) for h in (1.5, 1.75))))
```

A budget plus monitor selects bounded mode; adding `pedestrian-v1` requests
adaptive assessment. Eligible adaptive runs use method 1.90; other runs use
1.78. Adaptive qualification requires the supported native build, inflow,
precision, grid, geometry, monitor and thread team. `raise_on_failure=True`
raises for legacy/bounded non-convergence or adaptive unaccepted/not-assessed
output; known exclusions raise before native preparation. Zero completed
sweeps raise `BudgetExhaustedError`; completed-work deadlines return a result
unless failure policy raises. See [solver contract](docs/solver-control.md).

## Combining features and qualification

| Combination | Numerical/model scope |
| --- | --- |
| Any profile + legacy/bounded | Assessment `not_requested` |
| Log + eligible adaptive | `accepted` or `unaccepted`; independent of legacy convergence |
| Non-log, float64 or turbulence + adaptive | `not_assessed`, 1.78 fallback; request remains adaptive |
| Turbulence with any solver | Unvalidated algebraic screening |
| Automatic vertical grid | Prototype; no qualified comfort preset |

`result.solver` is the authoritative specification, verbatim native record
(or None for legacy) and environment. `result.qualification` is a fresh derived
view; editing that snapshot does not alter execution evidence. Execution,
legacy convergence, four-state assessment, cell validity and model limitations
stay separate. Mean-wind acceptance does not qualify turbulence or gusts.
For A/B comparisons, freeze the full grid, solver method and completed work:
turbulence may otherwise grow the domain.

## Pedestrian comfort

```python
from dtcc_qes import comfort

runs = [wind.run(city, profile.with_direction(d), bounds=bounds) for d in (0, 90)]
assessment = comfort.assess_results(runs, [3, 5, 7], [0, 90, 0], comfort.NEN8100)
```

`assess_results` checks coordinates, frames, references and actual sampled
heights. It preserves per-direction qualification and caveats under
`metadata["runs"]` for mean-only and GEM criteria. For `CITY_OF_LONDON`, providing
`peak_factor` with turbulent results enables GEM screening; no calibrated peak
factor is assumed. Missing GEM yields one mean-only warning. No weather-station
exposure conversion is implicit: `log_law_transfer` explicitly defaults to a
standard station law and shifted QES target law. See the
[comfort guide and measured class impact](docs/wind-comfort.md).

## DTCC dataset

```python
from dtcc_core import datasets
import dtcc_qes.datasets

plane = datasets.qes_wind(bounds=[0, 0, 24, 24], profile=profile.to_dict(),
    solver=wind.Solver().to_dict(), turbulence=wind.Turbulence().to_dict(),
    product="slice", slice_height=1.75, slice_sampling="linear")
```

Dataset requests fetch/condition a city and fill source courtyards. Four-coordinate
bounds defer top planning. Automatic layers require `product="slice"`.
Turbulent slices export `streamwise_std` (m/s), `turbulence_intensity` (1) and
`stress_valid` (0/1); volumes also retain raw stress and TKE. Requests normalize
profile, solver and turbulence payloads and bind active numerics/policy identities
into cache keys. Time-budgeted runs record `execution_deterministic=False`.
The direct 20M-cell and dataset 200M-cell caps are memory-capacity guards,
not accuracy settings. The [dataset CLI](examples/city_dataset.py) supports
`--profile profile.json` and `--turbulence height|wall_distance`.

## Results and timing scopes

Arrays own their storage. `sample()` returns owned fields; invalid support is
NaN. `speedup` uses the declared profile reference, with NaN for calm inflow.
Exports and datasets store copied qualification snapshots.
`metadata["timings"]` contains `public_call_seconds`, `city_preparation_seconds`
and `native`: public time includes validation, preparation, native execution,
output and cleanup; native totals contain phase timers. Never add parents and
children. Unavailable legacy native phase timings remain None until native
instrumentation is installed. Dataset preparation excludes upstream fetching;
its direct `wind.run` public-call timer is unavailable.

## Validation and qualification reports

The [combined plan](COMBINED_FEATURE_PLAN.md) and
[phase evidence](docs/data/feature-merge/phase7.json) record current gates.
[Profile integration](docs/wind-profiles-verification.md),
[precision/grid studies](docs/precision-and-horizontal-verification.md) and
[solver history](docs/solver-control.md) retain their original scientific scope.
Frozen S4–S9 reports and `docs/data/*` snapshots are historical evidence; replay
pinned campaigns from their archived drivers. They do not redefine the current
API or qualify physical comfort. Native requalification uses the frozen S7
worker compatibility procedure; the frozen S9 release verifier still requires
its original source identity.

## API migration

| Old spelling/behavior | Current spelling/behavior |
| --- | --- |
| `run(city, u, d)` | `run(city, speed=u, direction=d)` or `run(city, LogProfile(u,d))` |
| Run-level `reference_height`, `roughness_length` | Self-contained profile; all families own roughness |
| `tolerance`, `max_iterations`, `solver_precision` kwargs | `solver=Solver(tolerance=..., max_iterations=..., precision=...)` |
| `SolverControl` | `Solver(max_solve_seconds=..., monitor=..., policy=...)` |
| `raise_on_nonconvergence`, `raise_on_unaccepted` | `Solver(raise_on_failure=True)` |
| `turbulence=True/False` | `Turbulence()` / `None`; dataset uses a versioned payload |
| `result.control`, `metadata["solver_control"]` | `result.solver["record"]`; spec/environment are siblings |
| Exception `.control` | `.record` |
| `profile.reference_at(...)` | `profile.reference` at its declared reference height |
| `evaluate(..., roughness_length=...)` | Roughness on profile; `evaluate(profile, heights)` |
| `metadata["condition"]`, `["effective_condition"]` | `metadata["profile"]["reference"]` and native scalar provenance |
| Dataset `wind_speed`, `wind_direction`, solver scalar fields | `speed`, `direction`, versioned `profile`/`solver`/`turbulence` payloads |
| Profile JSON v1 | v2; move roughness onto every profile payload |
| Preview required/placeholder inflow | Omit inflow for grid-only preview; diagnostics explicitly unknown |
| Numeric top from four dataset coordinates | Shared computed top via six-coordinate bounds ending in None |

Terrain sampling, cut cells, vegetation, transient conditions, CUDA and
independent physical comfort/gust qualification remain outside this work.

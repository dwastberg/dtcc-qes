# Vendored QES-Winds core

This directory holds the QES-Winds sources that dtcc-qes compiles. It is a
GPL-3.0 derivative of [QES-Public](https://github.com/UtahEFD/QES-Public)
(University of Utah and University of Minnesota Duluth); see `LICENSE` and the
source headers. Changes made here are ordinary dtcc-qes commits.

## Origin

| | Revision |
| --- | --- |
| Vendored from | `dwastberg/QES-Public`, branch `dtcc-embed`, commit `dce15d7e3b0a2d2cb0a29898f3882d103f66de71` |
| Upstream base | `UtahEFD/QES-Public` v2.3.1, commit `dced7ec571487be7538eca17bfc25bb3262fb6d0` |

The fork commits between the upstream base and the vendored revision are:

1. `47645fa0` Separate the I/O-free QES core and support embedding builds
2. `74817ae4` Introduce silent leveled diagnostics and throwing QES errors
3. `d530b4a3` Own internal wind objects and validate borrowed in-memory inputs
4. `f34034b7` Return solver diagnostics and handle exceptions in standalone drivers
5. `398e9a4e` Measure serial convergence before accepting permissive tolerances
6. `71f8dcb2` Make OpenMP convergence and solid-face updates safe and deterministic
7. `046eb799` Fix vertical divergence scaling in wind solver RHS
8. `e0fb62e9` Support validated explicit vertical grids in embedded winds
9. `514d91cd` Own turbulence helpers and guard reference sampling
10. `2df34fc8` Correct stress rotation and diagnose missing wind directions
11. `57ffb0d9` Fix serial mixing distances with bounded voxel-face updates
12. `dce15d7e` Honor explicit vertical layers in the standalone wind driver

`src/dtcc_qes/_qes_revision.txt` records the vendored revision. It is compiled
into the extension as `_qes.qes_revision`.

## Contents

`qes/`, `util/`, `winds/` and `solver/` hold the QES-derived core; `dtcc/` holds the
dtcc-qes layer that drives it (moved from `src/cpp`), with the QES-free headers
used by the Python bindings in `dtcc/api/`. `LICENSE` is the QES license and
`CMakeLists.txt` builds the `qesutil`, `qeswindscore` and `qesbridge` targets.

### At vendoring (commit `6c2c65c`)

`qes/`, `util/` and `winds/` contained exactly the files that the former
`QES-Public` subproject compiled with `QES_ENABLE_IO`, CUDA and OptiX off: the
`qesutil` and `qeswindscore` sources and every header they include, taken from
compiler dependency files and byte-identical to `src/<path>` at the vendored
revision. Builds from the submodule and from this directory were compared with
AppleClang 17 in Release mode, OpenMP and serial, with and without native tests:
the normalized compile commands matched, and every object file, the `_qes`
extension module and every native test executable were byte-identical. Plume,
Fire, the standalone executables and the I/O, WRF/HRRR, CUDA and OptiX sources
were not vendored.

To see what a file looked like in the fork, compare it with the submodule
(reference-only, see the main README):

```sh
git -C QES-Public show dce15d7e:src/winds/Solver_CPU.cpp | diff - src/qes_core/solver/cpu_float32.cpp
```

## Changes since vendoring

The solver-control release closure is recorded in
[`docs/solver-control-s9.md`](../../docs/solver-control-s9.md). S9 freezes the
S7-qualified native method/source identity without further QES arithmetic,
model or boundary changes. S8a's public reuse API and S8b's comfort sensitivity
are explicitly deferred; neither is a new native feature. The release ledger
preserves the S5c mask correction, restricted grid/reference results and all
remaining numerical/physical limitations separately from release validation.

Each change below kept every output of `tools/compare_native_builds.py`
bitwise identical to the preceding commit, in OpenMP and serial builds, unless
it says otherwise.

- **In-memory inputs.** The model is built from plain structs in
  `winds/WindModelInputs.h` (`BuildingFootprint`, `BuildingParameterizations`,
  `InflowCondition`, `TurbulenceConfig`) instead of the XML parameter classes.
  `WINDSGeneralData` now owns its buildings; `applyWindProfile` takes one
  inflow condition and validates it on every call; the parameterizations,
  turbulence walls and mixing-length methods take the structs. The executed
  single-sensor log profile moved verbatim from `WindProfilerSensorType` and
  `singleSensorInterpolation` into `winds/LogProfile.cpp`.
- **Removed with the XML inputs:** `WINDSInputData`, `SimulationParameters`,
  `MetParams`, `BuildingsParams`, `VegetationParams`, `FileOptions`,
  `HRRRInput`, `TURBParams`, `Sensor`, `TimeSeries`, the wind profilers (Barnes
  interpolation), `RectangularBuilding`, `PolygonQUICBuilding`, the canopy
  (vegetation) classes, which were unreachable, and the no-I/O stubs of the
  file-backed constructors and mixing-length output.
- **Unreachable code removed:** the XML parsing base (`ParseInterface`,
  `ParseVector`, `ParseException`), `QEStime`, `calcTime`, `TimerTool`,
  `GIStool`, `QESout` (use `qes::log` and the `qes::` exceptions), the
  `QES_ENABLE_IO` macro with its branches, the commented-out street
  intersection, and the log-law wall correction (`Wall::wallLogBC`) with the
  wall index lists that only it read. The arrays `terrain_volume_frac`,
  `ti/tj/tk`, `terrain_id` and the write-only `icellflag_footprint` are no
  longer allocated. The core no longer needs Boost.
- **Phase-based CPU solver (S1).** `solver/solver.{h,cpp}` owns per-condition
  workspace and exposes begin, advance, pure slab observation, conservative
  diagnostics and finalization. `cpu_float32.cpp` extracts the expressions and
  boundaries of `Solver_CPU` and `Solver_CPU_RB`, retaining the contributor
  notices above. `cpu_float64.cpp` extracts `dtcc/precision_solver.cpp`, itself
  derived from those QES stencils, retaining the same notices and wider
  arithmetic. An immutable `PoissonOperator` initially borrows existing model
  arrays without a second coefficient volume. Shared conservative flux arithmetic
  lives in `solver/mass_diagnostics.h`. The old `Solver*`, factory and precision
  solver files, including obsolete GPU hooks, were replaced. Fixed work is an
  explicit stop rule rather than a negative-tolerance subclass. No relaxation,
  ordering, allocation optimization or per-condition building-state correction
  is included; the S0 baseline is the numerical oracle.
- **Condition-state correction (S1a).** Building initialization now clears
  `PolyBuilding::rooftop_flag` before each condition's parameterizations, so
  an ineligible wind direction cannot inherit the preceding rooftop-vortex
  decision. Wake-free settings reject enabled rooftop, street-canyon or
  sidewall models, which require wake-derived dimensions. Validation occurs
  before native geometry allocation and at direct core entry points. Upwind
  cavity remains independent. These deliberate changes are archived separately
  from S0/S1; the solver arithmetic and ordering are unchanged.
- **Kept for their own decisions:** cut cells (`CutCell`, `CutBuilding` and the
  arrays they share with `Wall`), `StreetCanyonModified`, OptiX mixing lengths
  (`LocalMixingOptix` with the util mesh classes). The new solver phase contract
  replaces the old `HAS_CUDA` factory hooks for a separate device-backend task.
- **Traffic and storage (S2).** Float32 measures its rounded update change in
  the update pass, with no old-iterate array. The operator owns either exact
  per-cell face masks and per-layer float tables or a checked explicit fallback;
  precision-specific relaxation factors retain the original sums/division.
  Production transfers and releases geometry's setup coefficients; mass and
  study diagnostics use the same operator. Cut-cell fields and mixing lengths
  allocate on use. Default CPU ordering is red/black in serial and OpenMP;
  explicit lexicographic order remains available internally. Historical study
  drivers request their archived order through `DTCC_QES_STUDY_ORDER=legacy`.
  S2 evidence records the intended serial trajectory change separately from
  bitwise-preserving traffic/storage changes. NumPy outputs retain their owned
  allocation/copy contract.
- **Read-only monitoring (S3).** A compiled internal monitor reconstructs only
  the union of requested vertical supports, rounds/collocates like finalization,
  and interpolates requested heights and receptors in double precision. Fixed
  rings retain samples, window summaries, validity transitions and moving peaks.
  Regional six-face flux diagnostics share the solver's rounded reconstruction;
  optional residual accumulation specializes the existing update loops without
  changing their arithmetic. The in-sweep algebraic trend has native RHS units,
  not physical divergence units or an accuracy interpretation. No controller,
  Python controls, stopping policy or tolerance default changes are included.
- **Bounded execution (S4).** The runner optionally checks a monotonic deadline
  around initialization, RHS, every whole sweep and monitor capture. Native
  entry includes mutex wait; necessary finalization/turbulence and NumPy output
  are timed separately. Zero completed work raises BudgetExhausted with its
  control record. Bounded records retain the legacy convergence boolean and
  always report accuracy not assessed. Input snapshots, buffered logging,
  precision/default stopping semantics and owned output arrays are retained.
- **Horizontal background profiles.** New analytic/tabulated profiles are
  evaluated in Python in float64. The QES-free `WindCondition` owns one u/v
  value per physical layer and reference scalars. `ModelInputs` atomically
  validates/narrows a complete table. `LayerProfile.cpp` copies it to exactly
  the physical staggered bands written by `LogProfile.cpp`; cleared lower
  ghost and upper-face bands stay zero. The table velocity limit considers
  interior maxima. Legacy log expressions and native scalar construction are
  unchanged. Turning follows each building's existing roof-level rotation;
  QES-Turb remains enabled with an explicit morphometric log-conversion caveat.
  Measured-tail roughness comes from preparation-time model roughness. See
  `docs/wind-profiles.md` and `docs/wind-profiles-verification.md`.
  Integration with S7 preserves exact log-policy outputs over all 24 frozen
  release workers before updating the qualified source identity. Layer-table
  inflow remains outside that policy's numerical acceptance scope.

- **Geometry/condition consistency (S5c).** Both canyon routines now preserve
  prepared solid/ground flags 0/2 instead of relabeling them as condition-fluid.
  The existing wall operator and solid-owned velocity faces therefore retain
  the same geometry mask. This intentional numerical correction is frozen
  separately from S5b's pure completed-iterate diagnostics; source-matched
  benchmark baselines receive the same correction. Kernels, tolerance,
  relaxation and prescribed top/lateral boundary conventions are unchanged.
  See `docs/solver-control-s5.md` and its separate before/after evidence.

- **Scoped numerical acceptance (S7).** `dtcc/pedestrian_policy.*` and the
  versioned plain API policy types add a native pedestrian predictor and
  current-iterate global/regional safeguards. Qualified opt-in calls use the
  existing `1.90f` internal relaxation option with `FixedSweeps`; legacy and
  bounded calls retain `1.78f` and their original stopping rule. No QES kernel,
  stencil, mask, correction or boundary expression changes. Source/arithmetic
  identity gates qualification and dataset cache provenance. The S7 report
  records the finite calibration/held-out scope, failed draft, domain exclusion
  and exact default comparison; this is not physical/turbulence validation.

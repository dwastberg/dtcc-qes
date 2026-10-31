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

`qes/`, `util/` and `winds/` hold the QES-derived core; `dtcc/` holds the
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
git -C QES-Public show dce15d7e:src/winds/Solver_CPU.cpp | diff - src/qes_core/winds/Solver_CPU.cpp
```

## Changes since vendoring

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
- **Kept for their own decisions:** cut cells (`CutCell`, `CutBuilding` and the
  arrays they share with `Wall`), `StreetCanyonModified`, OptiX mixing lengths
  (`LocalMixingOptix` with the util mesh classes) and the `HAS_CUDA` hooks.

- **Canonical footprints, explicit rings and exposed faces.** `BuildingArrays`
  accepts optional global ring offsets aligned with building vertex offsets.
  The bridge validates closure, winding, simple rings, hole containment and
  nonintersecting/non-nested holes after float32 conversion. Legacy callers
  omit ring offsets and retain their single-ring contract. `BuildingFootprint`
  carries the validated local offsets into `PolyBuilding`.
  `Building` provides ring-local edge traversal and a shared even-odd point
  test used by both rasterization and exposure. All face loops in
  `UpwindCavity`, `PolygonWake`, `StreetCanyon`, `StreetCanyonModified`,
  `Sidewall` and `Rooftop`, including downstream face searches, skip ring
  jumps. The centroid uses the outer ring; wake dimensions use net polygon
  area. Courtyard faces participate in parameterizations, with one common
  wake scale calculated from outer-ring faces. Explicit/canonical ring inputs
  use exact ring ends instead of the legacy 0.1 m closure heuristic.
  Canonical parameterization faces remove exact collinear vertices while
  retaining the original noded vertices for mask membership. This geometry
  is the same with exposure enabled or disabled.
- **Exposure rule (opt-in).** `ModelSettings.exposed_faces` defaults to false.
  For a candidate seed, project onto the source face segment and trace its
  outward normal through grid cells with a deterministic DDA. Skip cells
  whose centres lie in the source's original even-odd footprint. The first
  outside centre must be fluid in `icellflag_initial`. Own solid ahead of the
  seed face blocks the ray, preventing traversal through an opposite courtyard
  wall or concave branch when a gap has no fluid centre. Mutable flow flags and
  input building ownership are not used for this decision. Upwind cavity and
  wake apply this test to their staggered velocity samples; sidewall also
  checks the originating upwind corner and restores eligibility per level.
  Wake and canyon marches skip source-footprint cells before fluid and stop
  at a solid neighbor. Downstream canyon searches require a found face in
  exposure mode. Rooftop support is limited to its own footprint for holes
  and exposure mode, preserving existing upwind-cavity flags in exposure mode.
  The legacy single-ring, exposure-off path retains its closure heuristic.
  Nonfinite wake-length guards and canyon/sidewall bounds checks also protect
  that path; canonical reference fixtures retain their numerical results.
  This is a numerical geometry/exposure correction, not experimental
  validation of empirical parameterizations at height steps. OptiX is not
  enabled by this CPU integration.

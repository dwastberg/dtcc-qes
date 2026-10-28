# Turbulence numerical changes and reference provenance

Task 1A, 2026-10-27. QES repair:
`2df34fc85c6e859d7c8f3bd4aad3975daa7d81d9`, based on Task 1 revision
`514d91cdc1bfc220a17af102df2b267cdc0c2c9e`.

This records the numerical exceptions and Task 3's separately identified
pristine/audited standalone reference fixtures. Exact wind-only references
remain unchanged. Implementation
checks below do not establish physical accuracy for pedestrian gusts.

## Corrected stress rotation

Let `n = (c, s, 0)` be the horizontal flow direction sampled in a column,
`m = (-s, c, 0)` its crosswind direction, and `Q = [n m ez]` the matrix whose
columns are those vectors in Cartesian coordinates. The transforms are

```text
tau_wind = Q^T tau_cartesian Q
tau_cartesian = Q tau_wind Q^T
```

The previous implementation applied `Q tau Q^T` on entry and the opposite
transform on return. Scaling the normal components between these transforms
therefore aligned the anisotropy incorrectly for oblique flow.

The repair normalizes the original staggered horizontal velocity pair in
float64 to obtain `(c, s)`. Orthogonal inverses use transposes. The same
QES normal-component scaling, absolute values and subsequent component caps
remain in place. Roundoff differences can occur from replacing float32 angles,
trigonometric evaluation and generic inversion. Do not promise bitwise
unchanged stress for every cardinal-wind building case: its local reference
directions can be oblique too.

An independent oracle constructs the full tensor from streamwise, crosswind
and vertical dyads for the uncapped manufactured flow
`U(z) = (10 + 0.1 z) (cos(theta), sin(theta), 0)` on a 2 m grid. At z = 9 m,
the analytic streamwise standard deviation is 0.9 m/s.

| Cartesian flow heading | Before Task 1A | After Task 1A | Expected |
| --- | ---: | ---: | ---: |
| 0° | 0.900001 | 0.900001 | 0.9 m/s |
| 30° | 0.768960 | 0.900000 | 0.9 m/s |
| 45° | 0.720000 | 0.900000 | 0.9 m/s |
| 90° | 0.900001 | 0.900001 | 0.9 m/s |

The regression also covers reversed headings 180°, 210°, 225° and 270°,
all six tensor components on physical levels 2–19, uncapped conditions, finite
native fields and preservation of the input wind arrays. Tolerances are
rtol 1e-5 and atol 1e-7. These headings are Cartesian flow directions, not
meteorological wind-from inputs.

## Direction sampling and fallback

Usable preferred samples retain QES's original index: the lower bound of
`15 m + terrain` on ghost-inclusive `z_face`. The sampled cell must be physical
and fluid (neither flag 0 nor 2), and its original staggered `(u, v)` pair must
have finite, nonzero horizontal magnitude. No arbitrary low-speed floor is
introduced, and horizontal velocities are not newly averaged onto cell centres.

For an unusable preferred sample:

1. Search physical fluid levels in that column by distance of their effective
   **z cell centre** from `15 m + terrain`. Horizontal velocities live at these
   vertical centres. Prefer the higher centre when distances tie. Search by
   physical distance, including on nonuniform grids.
2. If no usable horizontal velocity exists anywhere in that column, use the
   fixed Cartesian +x axis. This is a deterministic fallback, not an observed
   wind direction. Calm stress remains zero and finite.

Direction is resolved once per computed column per stress calculation.
`getRotationFallbackColumns()` counts distinct columns requiring either
fallback, including wholly calm columns, and resets on every stress calculation
and hence every normal `run()`. It counts only columns visited through
`icellfluid`. The temporary direction cache uses about 16 bytes per horizontal
cell; it is separate from the persistent turbulence cell arrays.

Tests cover building/terrain flags, zero and nonfinite reference velocities,
all-level calm columns, restoration of a valid direction, tie preference,
terrain-relative reference height and nonuniform spacing where the closest
velocity centre is not adjacent to the original reference index. A domain top
exactly at 15 m exercises the face-without-cell-flag boundary under ASan.

These fallback cases are explicit upstream parity exceptions. They must be
reported in future bridge metadata, rather than silently counted as measured
15 m directions.

## Raw stress and validity

`src/cpp/stress_validity.h` is a QES-free numerical helper for future extraction
and derived statistics. It does not alter QES arrays or make tensors realizable.
It interprets stored float32 components in the order
`xx, xy, xz, yy, yz, zz`, evaluates eigenvalues in float64 using normalized,
bounded symmetric Jacobi rotations, and uses

```text
radius = max(abs(eigenvalues))
tolerance = 32 * eps(float32) * radius
valid = finite(tensor) and lambda_min >= -tolerance
```

There is no absolute variance floor. Finite zero tensors are valid with zero
tolerance. Nonfinite tensors and a failure to finish diagonalization are
invalid. The helper allocates no per-cell matrices on the heap.

Projection first requires a valid tensor and a finite, nonzero mean velocity.
An indefinite tensor gives NaN even if the requested projection is positive.
A negative projection rounds to zero only within the tolerance of a valid
tensor. The helper normalizes direction with `hypot` to handle very small and
large finite speeds. No `makeRealizable` call or raw eigenvalue clipping is
introduced. Coverage (`computed`) remains a separate concern for Task 2.

On the reviewed 40×30×20 uniform-grid 8 m building case, at 5 m/s and 270°
meteorological inflow, the corrected model produced 20,116 computed cells,
90 invalid tensors by this policy and 6 negative streamwise projections.
The native check preserves those raw tensors, masks their derived variance,
and verifies the same validity masks and stress ×4 when the frozen solved wind
is scaled ×2. The earlier review's 91 principal-minor failures used a different
diagnostic threshold; these counts are not directly interchangeable and are
not immutable reference values for subsequent model changes.

Tasks 2 and 5 must consume this policy when returning masks and derived fields.
The helper itself does not expose a Python turbulence API.

## Serial wall-distance repair (Task 1B)

2026-10-27, QES revision `57ffb0d94dd2dcad0ea5841d6d35620c0bfb7198`,
following Task 1A. The serial algorithm changes below affect
method 1 only. Method 0 remains the provisional default. Future standalone
method-1 reference fixtures must use this audited implementation; equality
with pristine QES method 1 is not an acceptance criterion.

Before repair, repository-owned regressions reproduced both review findings
on the Task 1A revision (whose serial method was still unchanged):

| Fixture | Before Task 1B | After Task 1B |
| --- | --- | --- |
| 40×30×80, dx = dy = 2 m, dz = 0.5 m, 8 m box at x = 30–40 m, y = 25–35 m | ASan heap-buffer-overflow at `LocalMixingSerial.cpp:385`, reading immediately after the 30-element y-centre array | 83,656 computed fluid cells; finite positive lengths; zero height-bound violations; maximum length/height = 1 |
| Same box and spacing, 60×60×80 | 40 computed lengths exceed height; maximum length/height = 4 | 265,356 computed fluid cells; finite positive lengths; zero height-bound violations; maximum length/height = 1 |

The audit also found unsafe positive-x bounds, shifted negative-x/y targets,
asymmetric transverse ranges, writes into solid cells, unused underside faces,
stale wall lists on reuse and a potentially zero interpolation denominator.
Correcting only the first failing y access would leave those defects.

The repair replaces the separate point-source directional sweeps with one
calculation over exposed **rectangular voxel faces**. Flags 0 and 2 identify
solids. All six face orientations use the same distance calculation; source
neighbours must exist in the actual arrays. Target ranges are half open and
restricted to turbulence's computed interior: indices `1..cx-2`, `1..cy-2`,
`1..cz-2`, where `(cx,cy,cz)` are the cell-centre coordinate-vector lengths.
Domain edges are not newly treated as solid walls. Distances update only fluid
cells and preserve the minimum found so far. All temporary state is local to
the call, so repeated setup cannot retain removed faces.

Each cell starts with `h = max(z - terrain[column], 0)`. Below the transition,
the result is the smaller of this seed and the Euclidean distance to the
exposed voxel faces. Candidate ranges use physical coordinates and the height
seed as an upper bound: a farther face cannot improve the result. The flat
ground is already represented by the seed and its individual faces need no
propagation. Coordinate inputs remain QES float32, with double-precision face
midpoints, distances and updates in QES's existing double mixing-length array.
This removes the former repeated float32 rounding of distance minima.

Let `g` be the minimum terrain elevation and `H` the highest physical solid
voxel's upper face minus `g`. Ground ghost cells do not define H. For H > 0:

```text
alpha(z) = clamp((z - (g + 3 H)) / (0.6 H), 0, 1)
distance = min(h, distance_to_exposed_voxel_faces)
mixing_length_distance = (1 - alpha) distance + alpha h
```

The implementation uses the actual difference between transition endpoints
as the denominator, guards degenerate intervals, and bypasses the calculation
for H = 0. Above `g + 3.6H` it returns the seed without wall propagation.
The final `TURBGeneralData::Lm` still multiplies this distance by QES's von
Kármán constant. On the reviewed 8 m box the transition is 24–28.8 m.

This is a deliberate, explicit model transition. The old code used a maximum
solid **centre**, then an index-based interval of roughly one fifth of the
starting index; its comments said 2H–2.4H despite a 3H search in the code.
That interval changed with layer spacing, could collapse, and seeded absolute
z instead of terrain-relative height above it. The repaired interval uses
physical height, including on nonuniform grids, and blends each local distance
back to its terrain-height seed. Changes to face geometry, propagation extent,
undersides, transition and arithmetic can all change method-1 turbulence
outputs. These are explicit reference-parity exceptions for Task 3.

Seven new native modes qualify this contract:

- `wall_thin` constructs and runs method-1 `TURBGeneralData` on the original
  overflowing grid, verifies that it consumes the repaired lengths and returns
  finite native fields, and checks that the input wind is preserved.
- `wall_upper_bound` isolates the original wider-grid overwrite counterexample.
- `wall_geometry` checks all 14,292 computed fluid cells in each of nine tall
  18 m box layouts on a 20 m domain, including minimum supported boundary
  clearance, swapped x/y axes and all horizontal reflections.
- `wall_nonuniform` checks 83,706 computed fluid cells on 80 physical layers
  repeating 0.125, 0.375, 0.75 and 1.25 m; it includes 8,512 transition cells
  and 34,048 far-field cells.
- `wall_transition` checks 30,476 computed fluid cells, including 1,568 in
  the transition and 19,600 above it, plus explicit 25 m and 29 m samples.
- `wall_underside` checks 7,808 computed fluid cells around a synthetic
  suspended voxel box. This isolates the sixth face direction and does not
  add elevated-polygon support to the public input contract.
- `wall_empty` compares empty two-layer and nonuniform domains with method 0,
  checks floating invalid/divide-by-zero flags, and checks building removal
  using the same mixing object.

The geometry oracle uses distance to one analytic axis-aligned solid box plus
the ground plane, independently of the exposed-face traversal. It derives the
box extent from QES's voxelization and verifies that every building voxel fits
that rectangular solid before applying the oracle. Every computed fluid cell
in those fixtures is compared at rtol 1e-5, atol 1e-7; near-field, transition
and far-field formulas are explicit. Repeated calls are identical, and solid
cells retain their prior values.

Qualification is for flat terrain and stair-step solids. It does not establish
distance to original polygon surfaces, cut-cell accuracy, general terrain
accuracy or physical gust accuracy. The transition band and far field are
intentionally not exact nearest-wall distances. Setup scans the grid and
propagates exposed faces to candidate cells; its cost can grow substantially
with geometry and domain size. Task 9 must measure that cost. No Python,
bridge or dataset turbulence entry point is added here; Task 2 can now expose
method 1 with height still the provisional default.

## Verification

Host/compiler: AppleClang 17.0.0, macOS arm64, OpenMP off. Native builds use
the isolated worktree and its no-I/O header traps. The interpreter used for
CMake and the NumPy check was the existing Python 3.13 environment, read-only.

```sh
cmake --build build/native --parallel 8
cmake --build build/native --target check_native_symbols
ctest --test-dir build/native --output-on-failure
cmake --build build/asan --target check_turbulence --parallel 6
ctest --test-dir build/asan -R native_turbulence --output-on-failure
python tools/check_stress_validity.py --cases 5000 --seed 20261027
```

- Task 1A full Release suite: 24/24 passed; no-I/O symbol audit passed.
- Task 1A Debug ASan/UBSan turbulence suite: 13/13 passed, with no sanitizer reports.
  The unrelated full Debug suite was not repeated for Task 1A; its 19/19 Task 1
  result and existing Debug assertion-symbol audit limitation remain recorded
  in the plan.
- Independent NumPy 2.5.4 check: 5,000 stored float32 tensors, including
  near-threshold eigenvalues, at scales from 1e-30 to 1e30; zero validity
  mismatches. Maximum minimum-eigenvalue error divided by spectral radius was
  `1.0544456312324755e-15` against NumPy's float64 eigensolver. The repository
  tool compiles the current header and emits its SHA-256 with the result.
- Task 1B full Release suite: 31/31 passed; no-I/O symbol audit passed.
- Task 1B complete Debug ASan/UBSan turbulence suite: 20/20 passed, with no
  sanitizer reports. OpenMP remains off; no Python API suite or large-domain
  benchmark was run at this native-core milestone. The unchanged Debug
  assertion-symbol audit limitation above remains separate from these checks.

## Native bridge integration (Task 2, 2026-10-28)

The private runner now accepts `_qes.TurbulenceSettings` through its optional
keyword-only `turbulence` argument. Disabled/default settings keep the solve
wind-only and return `result["turbulence"] = None`. Enabled settings accept
method 0 or the qualified method 1, with background mixing zero, nonlocal
mixing off, wall flags 2/2, default sigma constants and upper bound 20.
Unsupported methods fail before wind geometry setup. This does not yet add
the public `wind.run(..., turbulence=True)` option or derived gust statistics.

`QESInputs` owns the native parameters. The prepared runner owns one turbulence
object alongside the wind data, reuses it after each wind solve, and destroys
it before its wind data and input owners. All native work stays under the
existing process mutex, with the GIL released by the bindings. Configuration
objects and input arrays are copied before releasing the GIL. Preparation
still swaps state only after successful construction and margin checks.

Extraction maps native `(k,j,i)` to physical `(k-1,j,i)`. Coverage is defined
only by `icellfluid`; `iturbflag` is not a coverage mask. Stress components are
`xx,xy,xz,yy,yz,zz`. Float32 fields outside coverage are NaN; state and validity
are zero there. Computed raw tensors, including indefinite and nonfinite
components, remain unchanged. State 1 means computed, state 2 computed and
capped. Capping is `bound > 0` and either `tke >= bound` or any absolute stress
component reaches the bound, with `bound = upper_bound * uStar * uStar` evaluated
in QES's float32 operation order. Thus finite zero tensors in calm wind are
valid, computed and uncapped. Covariance validity uses the Task 1A helper and
is independent of state/capping. Counts include only computed cells.

All six returned arrays own their NumPy storage. Scalar metadata includes the
native reference values, cap, coverage/cap/invalid counts and distinct direction
fallback-column count. Values and masks are copied anew on every solve, and
survive runner destruction.

The bridge requires the lower-bound index of native zRef on ghost-inclusive
faces to be at most `grid.nz - 2`, plus a top reaching 15 m. A failed margin
check reports the sampled index, required two-layer margin and an actual
sufficient top for a constant tail using the last valid thickness. It uses
float32 accumulation, preserves the input prefix and checks layer, cell,
native-index and coordinate-progress limits. It never grows an explicit grid.
The 8 m uniform box needs 30 m (nz=15), while a tested nonuniform 32 m prefix
needs 42 m after appending two 5 m layers. This is the native margin and error
policy that Task 4's automatic-grid logic must match. The follow-up review
below moves this check ahead of turbulence construction so the bridge also
explains unsampleable references and tops below 15 m.

Validation on AppleClang 17/macOS arm64 with OpenMP off:

- Full Release native suite: 39/39 passed; no-I/O symbol audit passed with all
  nine bridge objects included.
- Full Debug ASan/UBSan native suite: 39/39 passed, no sanitizer reports.
  Expanded nonuniform/limit margin checks were also rerun after the final
  diagnostic formatting change in both builds.
- Initial preimplementation Python runner checks: 13 failed, 50 passed.
  All 65 final runner cases pass, including both solver precisions and methods,
  independent NumPy eigenvalue checks, cap checks, owned arrays, snapshots,
  failure recovery and unchanged wind fields.
- Full locked Python suite in a worktree-local Python 3.13.11 environment:
  605 passed, 24 skipped and one pre-existing failure,
  `test_datasets.py::test_explicit_import_registration`. The same mismatch is
  documented in `docs/stage0-validation.md`: the user-committed package import
  registers the dataset, while that test expects explicit-only registration.
  Registration behavior and its existing test were left unchanged.
- A source distribution built from this worktree passed `check_artifacts.py`,
  including the new `turbulence.h` and `turbulence.cpp` sources.

The new native modes independently check flat log-profile shear formulas,
calm fields/fallback diagnostics, 5-to-10 m/s speed scaling, 270°–0°–270°
repeatability, wall-distance bounds and strict shortening beside a building,
margin failures/recovery, method rejection and preservation of synthetic raw
indefinite/nonfinite stress. The speed-scaling check doubles the linear
solver's absolute tolerance with speed to retain the same relative accuracy;
it does not assert identical errors for different absolute stopping criteria.
Existing wind-only reference fixtures were not regenerated.

```sh
uv sync --frozen --python 3.13
uv sync --frozen --reinstall-package dtcc-qes
ctest --test-dir build/native --output-on-failure
ctest --test-dir build/asan --output-on-failure
cmake --build build/native --target check_native_symbols
uv run --frozen python -m pytest -q
```

## Standalone provenance and parity (Task 3, 2026-10-28)

Committed archives and JSON provenance live under
`tests/fixtures/reference/turbulence/{upstream,audited}`. They were generated
by the standalone `qesWinds -s 1 -t`, using XML inputs and its actual NetCDF
turbulence output. The bridge was not used to generate expected arrays.

- Pristine upstream: `dced7ec571487be7538eca17bfc25bb3262fb6d0`, five uniform
  cases whose reference heights and wall-propagation bounds are safe.
- Audited fork: `dce15d7e3b0a2d2cb0a29898f3882d103f66de71`, eight cases,
  including oblique winds, 0.5 m layers and repeating 0.125/0.375/0.75/1.25 m
  layers. Both mixing methods are represented.
- Upstream exclusions are explicit in the shared case definitions and every
  metadata file. The known thin-grid method-1 overflow is never run on pristine
  QES; unqualified nonuniform upstream paths are also withheld. Explicitly
  requesting such a case with `--baseline upstream` fails before building or
  running QES. `--method 0|1` filters immutable method-specific case presets.

The audited driver required a small correction: it constructed a uniform
`qes::Domain` regardless of XML's `verticalStretching` and `dz_value`. It now
passes the explicit physical layer vector to the existing domain constructor,
matching the bridge. With the nonuniform fixture, the old nominal-minimum
spacing would have made a 10 m uniform domain; the intended physical domain
is 50 m with last centre 49.375 m. The new standalone output agrees exactly
with the bridge's effective layers and coordinates. This change is confined
to `qesWindsMain.cpp`; the Task 1A/1B embedded numerical core is unchanged.
The QES commit, parent submodule pointer, `_qes_revision.txt` and rebuilt
extension all identify the same audited revision.

Both standalone builds use AppleClang `17.0.0.17000404`, macOS arm64, Release
`-O3 -DNDEBUG`, C++17, position-independent code, serial CPU, OpenMP off and
CUDA/OptiX off. Standalone I/O is on to read XML/write NetCDF; the bridge's
numerical build keeps I/O off. Complete compiler/build options, source-tree
and source-manifest fingerprints, executable SHA-256, full case definitions,
solver summaries and archive SHA-256 are recorded individually.

The tool requires `--turbulence --baseline upstream|audited`. It verifies all
source files against the pinned Git blobs and modes, checks actual Git HEAD
and cleanliness for worktrees, and rejects modified or extra files in exports
even when `.qes-revision` still names the expected commit. A stamp cannot
override a real Git HEAD. `--exe` additionally requires a matching build
attestation for the source, options, compiler and executable bytes. These
checks prevent a stale, dirty or differently revised build from silently
acquiring authoritative provenance. Regeneration requires the recursive Git
checkout and optional NetCDF/GDAL/Boost build dependencies, as before.

The reader removes the ground ghost layer from `_turbOut.nc`, verifies the
remaining physical coordinates, and retains the stored float32 values in
`xx,xy,xz,yy,yz,zz` order. Coverage comes from the physical fluid interior, not
`iturbflag`. All four reference turbulence fields are required to be finite
and zero outside that interior. The bridge returns NaNs outside coverage;
comparisons use every computed cell and require exact array equality for
stress, TKE, dissipation and mixing length. Wind arrays and geometry are
checked too. The original wind-only fixture archives and assertions remain
unchanged; the wind-only generator `--check` still passes.

### Measured pristine-to-audited differences

The following numbers compare the two committed standalone sets. Counts are
changed float32 stress components (six per computed cell), not invalid-tensor
counts. Stress differences have units m²/s².

| Case | Method | Changed stress components | Maximum absolute stress difference | Other turbulence changes |
| --- | ---: | ---: | ---: | --- |
| flat, wind-from 270° | 0 | 0 | 0 | None |
| flat, wind-from 225° | 0 | 20,216 | 0.559255421 | None |
| one building, wind-from 270° | 0 | 70,940 | 1.99341035 | None |
| one building, wind-from 225° | 0 | 69,028 | 23.3285427 | None |
| one building, wind-from 270° | 1 | 79,507 | 7.65667057 | TKE, dissipation and mixing length |

All wind arrays, coordinates, classifications, coverage and `iturbflag` are
exactly unchanged in these five shared cases. Method-0 TKE, dissipation and
mixing length are also exactly unchanged. Task 1A changes the stress rotation
and its arithmetic, including locally oblique flow in a cardinal-inflow
building case; that explains why cardinal inflow alone does not preserve every
building stress component. The completely flat cardinal case remains exact
for every returned field.

For flat 225° inflow at z=9 m, upstream streamwise sigma is
`0.8714080209 m/s` and audited sigma is `1.0892600544 m/s`: the original is
20% low. An independent covariance oracle built from the returned log-profile
shear and streamwise/crosswind/vertical dyads verifies the audited full tensor
at all computed central-difference levels (rtol 1e-5, atol 1e-7). This analytic
tolerance does not relax the exact standalone-parity comparisons.

For method 1, Task 1B also changes 3,327 mixing lengths (maximum difference
`2.53333330 m`), 3,319 TKE values (maximum `7.28535748 m²/s²`) and 3,327
dissipation values (maximum `21.1174984 m²/s³`). The different TKE count reflects
the cap retaining equality at some cells. These changes follow the documented
face-distance, minimum-preservation and transition repairs; they are not
treated as permissible roundoff in pristine comparisons.

The thin audited case converges in 693 iterations; both nonuniform cases in
610. They use a 20,000-iteration ceiling and must converge. The original
uniform cases keep their 500-iteration ceiling (flat: 1; cardinal building:
162; oblique building: 140). This records solver convergence, not experimental
or pedestrian-gust validation.

### Reproduction and limits

```sh
uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline upstream
uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline audited
uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline audited --check
uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline upstream --check
uv run --frozen --group reference python -m pytest tests/test_turbulence_reference.py tests/test_reference_tool.py -q
ctest --test-dir build/native --output-on-failure
```

Exact bridge/runtime comparisons are scoped to the fixture's recorded compiler
version, platform, Release mode and serial backend. On a different toolchain
they are explicitly skipped, while provenance and stored upstream-difference
checks still run. Generate both baselines under a separate local directory
with `--output`, and set `DTCC_QES_TURBULENCE_REFERENCE_DIR` to that directory
to exercise exact parity for another supported configuration. The tool's
`--check` never weakens turbulence comparisons with `--rtol`/`--atol`; those
options continue to apply only to wind velocities. Same-source parity does
not prove physical correctness. The independent Task 1A rotation/validity and
Task 1B box/plane geometry tests remain required and pass in the full native
Release suite.

Validation results: 46 focused reference/provenance Python checks pass,
including all eight exact bridge comparisons without skips on the recorded
host. All 39 Release native tests and the no-I/O symbol audit pass. Fresh
audited and upstream `--check` runs pass, as does the original wind-only
`--check`; the verified-existing-executable route also passes for all audited
cases. The final full Python run has 647 passes, 24 skips and the unchanged
pre-existing dataset-registration failure documented under Task 2. A rebuilt
source distribution passes the artifact audit, including every NPZ/JSON pair.
Task 3 does not repeat the Task 2 full ASan/UBSan suite: its embedded numerical
code is unchanged, while the new standalone explicit-layer path is exercised
by actual XML/NetCDF runs and exact nonuniform-coordinate/field comparisons.

Public Python API/results, the benchmark gate and physical gust validation
remain outstanding.

## Review before Task 4 (2026-10-28)

The review covered all completed-task changes against the isolated baseline,
including helper ownership, bounds, rotation and covariance validity, serial
face distances, runner reuse/extraction, and standalone reference provenance.
The QES fork remains at `dce15d7e3b0a2d2cb0a29898f3882d103f66de71` and the
existing reference archives are unchanged.

Two bridge guard gaps were reproduced and repaired:

- A top below 15 m or a zRef at/above the top failed inside the turbulence
  constructor before the bridge could give a usable extension suggestion.
  The bridge now checks the native wind geometry first, reproducing QES's
  float32 accumulation in its actual sorted building order. An 8 m building
  with a 20 or 24 m top now reports the sufficient 30 m top; an empty city
  with roughness 0.5 and a 40 m top reports 56 m. Both mixing methods are
  tested, including successful preparation at the suggested top and rejection
  before turbulence initialization. Explicit grids still never grow.
- Float32 faces can keep increasing while neighbouring centres coincide.
  The valid two-layer prefix `[16777211, 1]` demonstrates this: appending
  another 1 m layer fails the native centre-coordinate check. The suggestion
  loop now reports a cell-centre progress limit instead of offering an
  unusable extension. These extreme coordinates are a validation regression,
  not a representative urban grid.

Reference checking now validates the full stored case definition in pytest
and checks schema, component order and upstream exclusions in `--check`.
Regression tests reject changed heights and reordered stress components.
Relative `--build-dir` arguments are resolved before executing QES in its
temporary working directory.

The previously reported registration failure was a stale expectation, not a
turbulence regression. This cleanup preserves the existing automatic import
behavior, aligns the README and docstrings, and checks that repeated imports
and package reload register `qes_wind` only once.

Validation after repair: 663 Python tests passed, 24 skipped, no failures;
all eight audited bridge comparisons ran and passed. All 39 Release native
tests and the no-I/O symbol audit pass. All 28 turbulence tests pass under
Debug ASan/UBSan, including the independent rotation, covariance and wall
geometry checks. Verified existing standalone executables pass all five
upstream and eight audited `--check` cases with the stronger metadata checks.
The relative-build-directory route passes a fresh flat-case build/check. A
source distribution was rebuilt and passed the artifact audit.

No further blocker was found for Task 4. This remains an implementation
checkpoint: public results/sampling, domain growth, performance qualification
and the Task 9 numerical gate are still pending. Physical pedestrian-gust
validation has not been established. This review used the serial backend;
it does not extend the earlier validation to OpenMP or other toolchains.

## Turbulence domain policy (Task 4, 2026-10-28)

`wind.preview_grid(..., turbulence=True)` and the shared city preparation now
include the native turbulence margin. Public `wind.run(turbulence=...)` and
returned turbulence objects remain Task 5 work. The default preview/run paths
retain their prior grids, metadata and wind-only native preparation.

The reference height uses positive float32 building heights, sorted ascending
and accumulated sequentially in float32 before the mean and final 3× scaling.
An empty city uses `float32(100 × float32(roughness_length))`. Mixed-height and
empty native-runner checks verify the same reference values. Effective physical
faces have no ground ghost: acceptance requires at least three layers,
`faces[-4] >= zRef`, and a top of at least 15 m. Exact-face and adjacent-float32
checks agree with the native bridge on uniform, nonuniform and small grids.

A valid wind-only grid is generated first. Automatic bounds then retain every
existing layer operand and face and append the final thickness until the
actual native faces pass. The loop checks each extension against 10,000 layers,
`max_cells`, native staggered index range, and float32 face/centre progress.
The final nonuniform grid is revalidated with `effective_faces`. Repeating the
last valid automatic thickness preserves minimum/aspect/growth constraints;
its building-region and upper caps are nondecreasing with height. Tests verify
these constraints and unchanged fine-band, roof and pedestrian-sampling data.
Decimal tails use the original solver operand, rather than subtracting rounded
faces. Explicit bounds or faces are checked and never extended.

Some examples for four equal-height blocks, with the default clearance:

| Building height | Horizontal/uniform spacing | Grid | Wind-only effective top | Turbulence effective top | Added layers |
| --- | --- | --- | --- | --- | --- |
| 15 m | 2 m | Uniform | 36 m | 52 m | 8 |
| 20 m | 2 m | Uniform | 40 m | 66 m | 13 |
| 15 m | 1 m | Uniform | 35 m | 48 m | 13 |
| 15 m | 0.5 m | Uniform | 35 m | 46.5 m | 23 |
| 15 m | 2 m | Automatic | 35 m | 51.051788 m | 8 |
| 20 m | 2 m | Automatic | 39.999996 m | 66.997849 m | 12 |

The C2 tower array (mean height 11.85 m) retains its default uniform grid.
Explicit 26 m bounds for an 8 m building report a sufficient 30 m top. A
nonuniform 32 m prefix ending in 3/4/5 m layers reports 42 m; its required
extension is not inferred from minimum spacing. An empty city with roughness
0.5 and a 40 m top reports 56 m. These are construction requirements, not
claims about domain-height independence of the solved field.

### Metadata and regeneration

The `domain['turbulence']` record contains:

- `reference_height`: the native float32 morphometric height.
- `default_top`: the effective wind-only prefix top. If that grid cannot be
  generated, this is its original requested top.
- `required_top`: the shortest accepted constant-tail extension of that
  retained prefix. A valid prefix is never shortened. For check-only explicit
  grids it is the supplied effective top.
- `effective_top`: the final actual float32 extent, also used for local/global
  domain bounds. It equals `required_top` under this policy.
- `raised`, `added_layers`, `lower_layers_preserved` and `extension_policy`:
  whether a tail/regeneration was needed, the number of appended tail layers,
  and the construction policy (`check_only`, `constant_last_thickness`, or
  `regenerated_then_constant_last_thickness`).

A recoverable endpoint-fit error can leave no valid wind-only prefix: for
example, a requested 40 m fine band cannot fit a 35 m wind-only domain. Only
that typed fit error permits generation at a higher initial target, chosen
from the turbulence uniform target and the generator's minimum feasible
endpoint. Further fit failures advance to the next feasible endpoint, with
strict progress and a 10,000-attempt bound in addition to the generator's
10,000-layer bound. This covers a 50.9 m fine band whose first 51 m target
leaves an unusable 0.1 m sliver. Invalid settings,
limits and explicit bounds still raise. The regenerated grid receives the
same bounded, repeated effective-face margin check; one larger initial target
is never treated as sufficient by itself.

Regeneration is recorded with `lower_layers_preserved=False` and a separate
`regeneration` record containing the failed-fit reason, original requested
top, generated top, attempt count and initial generated layer count. `added_layers` counts
any constant tail after this generation; it does not invent a layer-count
comparison with an invalid grid. Extended automatic metadata records the
original `base_endpoint_fit` and the final operands/planned/effective extent.

### New lower-grid sensitivity control

[check_turbulence_domain.py](../tools/check_turbulence_domain.py) and its
[recorded measurements](data/turbulence-domain/control.json) exercise that
regeneration case on four 15 m blocks with 2 m horizontal spacing. The base
regenerated grid retains 93 identical fine-band operands through 40 m. The
control compares a taller regenerated grid with a taller grid preserving every
base operand, including a direct comparison of the two taller grids at the
same planned top. Their actual effective extents can differ by float32
accumulation roundoff; the record reports that difference.

All three mean-wind solves converge using float64 solver arithmetic,
tolerance 1e-8, and a 20,000-iteration ceiling. Linear component sampling at
1.5/1.75 m uses 1,152 common fluid points and `K = |sampled velocity| / 5`.
The recorded targets are p95 absolute delta K <= 0.05 and relative peak change
<= 0.05. The largest observed p95 delta K is 0.000218730, and the largest
relative peak change is 0.000156408. Comparing the two taller grids directly
gives p95 delta K <= 0.000002888; their effective tops differ by 0.000030518 m.
Source hashes identify the generator, preparation, extension policy
and control tool. The current-source audit is part of the domain tests.
This focused control does not establish a general automatic preset or replace
Task 9's numerical and performance gates or physical pedestrian-gust validation.

```sh
uv sync --frozen --group reference --reinstall-package dtcc-qes
uv run --frozen --group reference python -m pytest tests/test_turbulence_domain.py -q
uv run --frozen --group reference python tools/check_turbulence_domain.py --output docs/data/turbulence-domain/control.json
uv run --frozen --group reference python -m pytest -q
```

Validation: the initial 40 domain cases failed before implementation. All 52
final domain cases pass; the full suite has 715 passes and the original 24
opt-in skips. The QES fork revision, embedded numerical code and all reference
archives remain unchanged. Task 4 adds Python grid policy and native acceptance
checks; it does not repeat the unchanged native sanitizer suite.
Wheel and source-distribution audits pass, including source hashes for the
recorded control. The wheel was built from the source distribution and passes
source-content, native-revision, turbulence-preview and calm-solve smoke checks.
The local no-isolation build used the system Unix Makefiles generator.

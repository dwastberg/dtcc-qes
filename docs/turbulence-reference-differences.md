# Turbulence numerical changes and reference provenance

Task 1A, 2026-10-27. QES repair:
`2df34fc85c6e859d7c8f3bd4aad3975daa7d81d9`, based on Task 1 revision
`514d91cdc1bfc220a17af102df2b267cdc0c2c9e`.

This records the numerical exceptions that Task 3 must account for when it
generates standalone reference fixtures. Audited-fork parity fixtures have not
yet been generated. Exact wind-only references remain required. Implementation
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
policy that Task 4's automatic-grid logic must match. Earlier native core
safety guards can reject an unsampleable reference or top below 15 m before
the stricter bridge margin check is reached.

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

Standalone audited reference generation (Task 3), public Python API/results,
the benchmark gate and physical gust validation are still outstanding.

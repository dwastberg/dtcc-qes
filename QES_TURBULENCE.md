# QES Turbulence Binding: Investigation and Implementation Plan

> **Execution:** Follow the task order and acceptance gates below, using checkbox (`- [ ]`) tracking. Superpowers execution skills may be used when installed; they are unavailable in the current environment, so this checkout follows the documented implementation and verification steps directly.

**Goal:** `wind.run(city, speed, direction, turbulence=True)` returns the solved
wind and the QES-Turb turbulence fields from one prepare/solve. Turbulence then
flows through sampling, DTCC export, comfort (GEM) and the `qes_wind` dataset.

**Architecture:** The QES no-I/O core already compiles `TURBGeneralData`. The
audited bridge constructs it once per `prepare` next to `WINDSGeneralData`,
calls `run()` after each solve and copies owned float32 arrays out. Python adds
a `Turbulence` spec, a domain-top policy for turbulence's reference heights, a
`TurbulenceFields` result and derived streamwise statistics.

**Tech Stack:** C++17, QES-Public fork (branch `dtcc-embed`), nanobind, NumPy,
dtcc-core, pytest, CTest.

**Status (implementation started 2026-10-27):** work is isolated in the checkout
below. Tasks 1 and 1A are implemented, verified and committed. The serial
wall-distance repair in Task 1B and the later extraction/result work remain
required before exposing the turbulence-derived statistics. Review measurements describe the original core
at the recorded revision, not necessarily the repaired implementation.

**Spec:** the Findings, Decisions and review revisions sections below. The
initial decisions were agreed on 2026-10-27; the subsequent review revisions
and isolated implementation were requested by the user on the same date.
Task checkboxes and the execution record below track implementation progress.

## Isolated execution record

- Worktree: `/private/tmp/dtcc-qes-turbulence`; branch `feat/qes-turbulence`.
- Baseline commit: `de80e11`, a copy of the original checkout's current tracked
  changes and untracked project files on top of `e30d9c2`. This keeps the
  existing grid, precision, comfort and dataset dependencies available and
  provides a separate baseline for reviewing turbulence changes.
- QES is a nested worktree on `dtcc-embed-turbulence`, branched from
  `e0fb62e9fe5fffc8b4aef8f250f75f929ad27c13`. Its files and index are separate
  from the original checkout's `dtcc-embed` worktree. Do not switch the original
  QES checkout or update its submodule pointer while working here.
- The original checkout's files and index are not used as implementation
  destinations. The repositories share Git object storage and branch refs,
  as normal for worktrees. No pushes are performed.
- Native builds use this worktree's `build/native` and `build/asan`, with
  OpenMP off. The existing Python 3.13 interpreter is used read-only for CMake
  and build dependencies; its installed package is not rebuilt or replaced.
  Python API work must create a worktree-local environment before installation.
- Task 1: complete at QES commit `514d91cdc1bfc220a17af102df2b267cdc0c2c9e`.
  All 8 focused native checks and all 19 full native CTest checks pass in both
  Release and Debug with ASan/UBSan; the Release no-I/O symbol audit passes.
  The no-I/O header traps were active in both builds. The integration commit
  updates the submodule pointer and `_qes_revision.txt` together.
- Validation limits: OpenMP was off; this milestone ran native tests, not the
  Python suite. A direct import smoke check loaded the isolated Release
  extension and verified its recorded QES revision. macOS ASan/UBSan checks
  were supplemented by observable derived
  destruction and repeated successful/throwing construction. A portable
  leak-detector run remains appropriate on a platform supporting it.
- Supplementary Debug symbol auditing reports `___assert_rtn` termination
  references. The same failure was reproduced on the unmodified review
  baseline's Debug ASan archives, so this is an existing assertion-symbol
  limitation of that audit configuration. Both CTest suites pass; the required
  Release symbol audit passes. Keep the Release audit strict.
- Task 1A: complete at QES commit `2df34fc85c6e859d7c8f3bd4aad3975daa7d81d9`.
  Corrected tensor transforms, a counted nearest-fluid-centre direction fallback,
  and a QES-free raw-stress validity/projection helper are covered by 24/24 full
  Release native tests and 13/13 Debug ASan/UBSan turbulence tests. The Release
  no-I/O symbol audit passes. A reproducible NumPy comparison on 5,000 tensors
  found zero validity mismatches. See
  [turbulence-reference-differences.md](docs/turbulence-reference-differences.md)
  for the precise policies, numerical exceptions and validation scope.
- Next: Task 1B (serial wall-distance safety and distance qualification).

---

## Findings

### How QES computes turbulence (QES-Turb)

The model lives in `QES-Public/src/winds/TURBGeneralData.{h,cpp}`. Wall models
are in `TURBWallBuilding` and `TURBWallTerrain`; mixing-length classes are
`LocalMixingDefault` and `LocalMixingSerial`. All of these are already compiled
into `qeswindscore` in the no-I/O build (`QES-Public/src/winds/CMakeLists.txt`).
The NetCDF paths are stubbed in `TURBGeneralData_noio.cpp`. The bridge does not
use any of them yet.

**Lifecycle** (`QES-Public/qesWinds/qesWindsMain.cpp`): the object is
constructed once, after `WINDSGeneralData` and before the time loop. `run()` is
called after every wind solve. It is a pure post-processor: it reads the solved
`u, v, w` and never writes them.

**Construction** depends on geometry only, so it can be reused across solves:
- Allocates about 25 float cell arrays plus 2 int arrays, roughly 110 B per cell.
- `icellfluid` holds the fluid cells QES computes. It excludes the first and
  last x and y columns and the top physical layer.
- Builds stair-step wall lists for buildings (flag 0) and terrain (flag 2).
- Mixing length, `Lm = 0.4 × distance`, by `methodLocalMixing`:
  - 0: height above ground.
  - 1: serial wall-distance propagation, with a transition back to height-based
    lengths above the object-influence region (about 3 × the tallest object).
    This is not a hard cap on Lm or a verified exact nearest-wall distance.
    The current implementation has indexing and distance-update defects.
  - 2: not implemented.
  - 3: OptiX ray tracing (GPU); QES's own urban examples use this.
  - 4: read from NetCDF.
- Morphometric reference values. With buildings: mean building height H̄,
  `z0 = 0.1 H̄`, `d = 0.7 H̄`, `zRef = 3 H̄`. Without buildings: `z0` = site
  roughness, `d = 0`, `zRef = 100 z0`.

**`run()`**, once per solve:
1. `uRef` is the plane mean of |U| over the fluid cells in the layer at or
   above zRef. Then `u* = 0.4 uRef / ln((zRef − d)/z0)`.
2. Velocity-gradient tensor G by central differences. Stretched grids use a
   nonuniform-z formula; cells next to walls use one-sided differences
   (`buildingWallFlag = terrainWallFlag = 2`).
3. `νT = Lm² √(2 SijSij)`, `k = (νT / (0.55 Lm))²`, with k capped at `20 u*²`.
   `CoEps = 5.7 (0.55 √k)³ / Lm`, i.e. C0·ε with C0 = 5.7.
4. `τij = ⅔ k δij − 2 νT Sij`, intended to be rotated into each column's wind direction at
   15 m above ground. The normal components become `|1.5 σ² 0.55² τii|` with
   `σ/u* = (2.5, 2.0, 1.3)`; the tensor is then rotated back. The review
   baseline failed the oblique-wind check below; Task 1A corrected the
   transforms and added the documented direction fallback.
5. Every component is clipped to `|τij| ≤ 20 u*²`. Background mixing is added
   if set. Finally `div τ` is computed for QES-Plume.

QES's own NetCDF output (`TURBOutput`) contains G (9 components), L, the 6 τ
components, tke, CoEps, `div τ` and `iturbflag`.

### Inputs: how turbulence differs from wind

| Input | Wind | Turbulence |
| --- | --- | --- |
| Solved `u, v, w` | Produced by the solve | The primary input; there is no separate speed input |
| Speed, direction, reference height | Inflow log profile | Not used directly. uRef is re-sampled from the solved field at zRef; the stress rotation uses the local wind direction 15 m above ground |
| Roughness length | Inflow profile | Used only when there are no buildings (`zRef = 100 z0`) |
| Building geometry | Cell flags, parameterisations | Also sets H̄, which gives zRef, z0 and d |
| `TURBParams` | — | `method` (mixing length), `turbUpperBound = 20`, `backgroundMixing = 0`, wall flags `2/2`, `nonLocalMixing = false`, `σ/u* = (2.5, 2.0, 1.3)` (`sigConst` is never parsed from XML) |
| Vertical grid | Same | Stretched grids switch to the nonuniform derivative branch |
| Domain top | At least the reference height | Must reach above zRef (3 H̄) and 15 m |

**Answer:** turbulence needs no extra wind-speed input. It takes its velocity
scale from the solved field, so one prepare plus one solve can serve both. Two
real differences remain:

- **u\* is morphometric.** It comes from building heights, not from the inflow
  profile's `roughness_length`. It is used only for the `20 u*²` cap, and that
  cap applies in roof shear layers and corner jets, where gusts govern comfort.
  For uniform 15 m blocks, the morphometric u\* is roughly twice the inflow u\*
  (estimate).
- **The domain needs extra height**, above zRef and 15 m, which the wind alone
  does not need.

### Speed scaling

With background mixing at 0, every step is homogeneous in U:
- G and νT scale with U.
- k, τ, u*² and the cap scale with U².
- CoEps scales with U³.
- Rotation angles do not depend on U.

So σ/U_ref does not depend on speed, and the comfort module's
one-solve-per-direction approach extends to gust-equivalent speeds. Keeping
background mixing unexposed preserves this property; Tasks 2, 5 and 7 test it.
Validity tolerances must scale with stress magnitude too; a fixed absolute
variance floor would break this property at low speeds. Numerical solves and
float32 arithmetic still require the stated comparison tolerances.

### Hazards in the QES turbulence code

1. **zRef near the top.** In `frictionVelocity()` (called by the constructor
   and by `run`), a zRef inside the top physical cell reads `icellflag` and `w`
   past the end of the arrays (undefined behaviour). A zRef above the top
   throws. Handled by a fork guard (Task 1) and the dtcc margin (Tasks 2 and 4).
2. **Domain top below 15 m.** `stressTensor()` loops
   `while (z_face[k_ref] < 15)` and runs past `z_face`. Handled by a fork guard.
3. **Unsupported mixing-length methods.** Method 2 and out-of-range values leave
   `localMixing` uninitialised, which is a null dereference. Method 3 needs
   OptiX and method 4 needs NetCDF. Method 0 is the initial supported method;
   method 1 is exposed only after Task 1B passes. The rest are rejected.
4. **Memory leak.** `~TURBGeneralData()` never deletes `wallVec` or
   `localMixing`, so every prepare leaks. The planned ownership fix must also
   add virtual destructors to `LocalMixing` and `TURBWall`: deleting their
   derived helpers through base-class `unique_ptr`s is otherwise undefined
   behaviour. This repair is still to be implemented.
5. **Private reference values.** zRef, uRef, u\*, z0 and d are private. The fork
   adds accessors.
6. **Log-law building walls.** `buildingWallFlag = 1` divides by
   `ln(…/WGD->z0)`, and `z0` is 0 in this configuration. Its left-wall loop also
   iterates the wall-below list. Not exposed.
7. **`div τ` bugs.** The front-wall x-derivative uses `toy`, and the wall-above
   case uses the wrong dz. These affect `div τ` only, which is not returned.
8. **QES `tke` ≠ ½ trace τ.** The σ scaling is applied after k, so in pure shear
   ½ trace τ ≈ 1.8 k. Both are exposed; σ is derived only from valid τ.
9. **Ground-cell gradient.** Ground-adjacent cells use a one-sided gradient. On
   the uniform 2 m grid, the first-cell σ is roughly 40 % below the
   surface-layer value 2.5 u\* (estimate; Task 9 measures it).
10. **Serial code.** QES-Turb has no OpenMP. Cost is O(cells) per solve, plus
    the mixing-length setup at prepare.
11. **Method 1 reads outside coordinate arrays.** `LocalMixingSerial::getMinDistWall`
    can propagate to `ny - 1`/`nx - 1` although the cell-centre coordinate
    vectors end at `ny - 2`/`nx - 2`. ASan detects a heap-buffer-overflow on the
    valid thin-layer case below. Audit all propagation loops, not just the
    first failing access (Task 1B).
12. **Method 1 can exceed height-based lengths.** Wall updates overwrite
    previously shorter distances. The measured thin-layer case contains
    lengths four times the method-0 value. The planned upper-bound test is a
    requirement for the repaired method, not a property of the current code.
13. **Stress rotation is direction-dependent in flat shear.** Axis-aligned
    checks pass, while a 45° horizontal rotation reduces streamwise σ by 20 %.
    This was verified on the review baseline and is repaired in Task 1A, with
    full-tensor, oblique-angle and direction-reversal regressions.
14. **Computed stress need not be a valid covariance.** Diagonal absolute
    values and component-wise clipping do not guarantee positive
    semidefiniteness. A computed fluid cell can have `ê·τ·ê < 0`, making the
    proposed square root invalid. QES-Plume applies `VectorMath::makeRealizable`
    before using stress (`src/plume/GLE_Solver.cpp`); the binding cannot assume
    that correction has already occurred in QES-Turb.

### Verified review evidence (2026-10-27)

The review rebuilt the current no-I/O core at QES revision
`e0fb62e9fe5fffc8b4aef8f250f75f929ad27c13`, with OpenMP off, using AppleClang
17.0.0. Native probes used Release and a Debug build with AddressSanitizer and
UBSan. They tested the existing core directly; they are not tests of an
implemented turbulence binding or evidence of physical gust validation.

| Probe | Observed result | Required follow-up |
| --- | --- | --- |
| Type traits for `LocalMixing` and `TURBWall` | Both lack virtual destructors | Complete the ownership fix in Task 1 |
| Method 1; 40×30×80 cells, dx = dy = 2 m, dz = 0.5 m; 8 m building with footprint x = 30–40 m, y = 25–35 m | ASan heap-buffer-overflow in `LocalMixingSerial::getMinDistWall`, reading past the y cell-centre coordinates | Repair and cover all propagation bounds in Task 1B |
| Same building and spacing in a larger 60×60×80 domain; method-1 setup only | Sanitizer run completed; 40 computed cells had `Lm > Lm_height`, maximum ratio 4.00000006 | Preserve the minimum distance across wall updates; test thin layers |
| Flat manufactured flow `U(z) = 10 + 0.1 z` m/s, 2 m grid, sampled at z = 9 m | σ ≈ 0.900001 m/s at 0°/90° flow headings, 0.768960 at 30°, 0.720000 at 45°; expected ≈ 0.900000 at every heading | Correct rotation and add oblique-angle analytic tests |
| Uniform 40×30×20, 2 m grid, same 8 m building; method 0; 5 m/s inflow at 10 m, roughness 0.1 m, meteorological direction 270° | Wind converged at multiplier tolerance 1e-5; 91 of 20,116 computed stress tensors failed principal-minor checks, 7 had negative projected variance; minimum ≈ −10.5076 m²/s² | Define validity separately from computation and preserve invalidity in derived output |
| Existing automatic-grid generator; four 20 m buildings, 2 m resolution, zRef = 60 m | Initial top 66 m failed the margin; the prescribed single retry gave top ≈ 75.91046 m but `faces[-4] ≈ 56.45435 m`, still below zRef | Replace the one-retry heuristic with bounded growth until the effective faces pass |

The diagnostic principal-minor threshold in the probe was 1e-8; it is not the
proposed production validity tolerance. The observed negative variances are
far larger than roundoff. Rotation angles in the manufactured-flow probe are
Cartesian flow headings, not meteorological wind-from directions.

The temporary reproducer is `/private/tmp/dtcc-qes-turbulence-review/probe.cpp`
(modes: default, `stretched`, `length`). It may not persist on another host.
Tasks 1A and 1B must promote these cases into repository-owned regression tests.

The [City of London Wind Microclimate Guidelines (2019)](https://www.cityoflondon.gov.uk/assets/Services-Environment/wind-microclimate-guidelines.pdf)
support dividing gust speed by 1.85 and taking the worse mean/GEM assessment
(wind-tunnel requirements and Annex A). They do not establish the peak factor
for this algebraic turbulence model. Peak-factor and averaging-time assumptions
need their own justification and must survive into the comfort result.

**Memory:** about 110 B per cell inside QES for the runner's lifetime, about
38 B per cell for the bridge copy and another 38 B per cell for NumPy, including
the added stress-validity mask. The base estimate is roughly 3.7–3.8 GB extra
at 20 M cells, before additional Python masks, derived float64 arrays and
validity-check temporaries. Measure peak RSS; do not treat this as a peak bound.
The Task 1A direction cache adds about 16 B per horizontal cell during stress
calculation; it is released after that calculation.

## Decisions and review revisions

1. **Single call:** `wind.run(..., turbulence=False | True | Turbulence(...))`
   returns a `WindResult` whose `turbulence` field is set.
2. **Domain top: option 1 with safeguards.**
   - Raise automatic domain tops so the sampled zRef layer has two physical
     layers above it, and so the top is at least 15 m.
   - Explicit bounds or z_faces that are too low raise a `ValueError` stating
     the required top.
   - Record zRef, uRef, u\* and the raised top in metadata, and report the
     number of cells where the `20 u*²` cap applies.
   - Rationale: the taller-domain controls (`docs/stagec2-controls.md`, top
     raised from 64 m to 144 m) changed pedestrian K by at most 0.0003 **while
     preserving every lower-layer operand**. This is limited evidence for
     those cases; regenerating lower layers requires a new control. Clamping
     zRef instead (option 3) would bias the cap by an estimated +18 % to +75 %
     for 15–35 m blocks and would change QES's reference-height definition.
   - Automatic growth must satisfy the final float32 face check, with cell and
     layer limits enforced on each extension. Explicit bounds never grow.
   - Cost estimates need measuring after the repaired policy. Uniform
     mid-rise cases can need substantially more layers; no general claim of
     only a few percent for `VerticalGrid.auto` is established by this review.
3. **Mixing length:** implement both `"height"` (QES method 0) and
   `"wall_distance"` (QES method 1). Method 1 is unavailable until its safety
   and distance checks in Task 1B pass. `"height"` is the provisional default
   until the user has reviewed the Task 9 benchmark; neither method is yet
   validated for pedestrian gusts.
4. **Scope:** the binding and run API, a comfort GEM helper, `to_dtcc` fields
   and a dataset flag.
5. **Not exposed** (fixed at QES defaults and recorded in metadata): σ/u\*,
   `turbUpperBound`, wall flags, non-local mixing and background mixing.
6. **Initial validity policy: preserve raw stress and mask invalid statistics.**
   `computed` records QES coverage; a separate `stress_valid` mask records
   whether a finite tensor is positive semidefinite within a scale-relative
   roundoff tolerance. Invalid raw tensors remain available for diagnosis.
   Derived σ/TI/GEM must be NaN for invalid stress, even if the particular
   projection happens to be positive. Do not silently clamp materially
   negative variance to zero. A realizability correction is a separate,
   explicitly documented numerical change, not part of the initial policy.
7. **Correctness and upstream parity are separate contracts.** Preserve exact
   wind-only references. For turbulence, retain pristine upstream fixtures as
   provenance, record audited numerical differences, and independently test
   the corrected mathematics. No blanket promise of unchanged turbulence
   numerics remains after the rotation and method-1 repairs.
8. **Validation precedes downstream integration.** Task 9 is a numerical
   acceptance gate after results/sampling and before DTCC export, comfort and
   dataset work. Reproducing QES or timing the methods is insufficient to pass.

## Global Constraints

- With `turbulence=False`, domains, arrays, metadata and native calls stay
  identical to today. Existing reference tests pass unchanged.
- Compare turbulence-on/off velocities only on identical explicit grids.
  Automatic domain growth is a separate behaviour and may change shape and
  solved velocity; it is not covered by a bitwise-equality promise.
- `src/cpp/bindings.cpp` includes no QES headers. QES types appear only in
  bridge sources compiled into `qesbridge`.
- `QES_ENABLE_IO=OFF`: no NetCDF or GDAL includes. The Release
  `check_native_symbols` target and the `noio-headers` trap must pass.
  Record the existing Debug assertion-symbol audit limitation above separately
  from sanitizer test results; it does not relax the Release audit.
- Native work runs under `native_mutex()` with the GIL released through
  `native_call`. QES log output goes through `BufferedLogSink`.
- Input errors are `std::invalid_argument` (which includes `qes::InputError`),
  surface as Python `ValueError`, and are raised before solving where possible.
- Arrays are owned NumPy arrays, float32, laid out `(z, y, x[, c])`, physical
  cells only, matching `WindResult.velocity`.
- Stress component order everywhere: `txx, txy, txz, tyy, tyz, tzz` in m²/s².
  `co_eps` is QES `CoEps` = C0·ε with C0 = 5.7, in m²/s³.
- QES changes in this isolated checkout are commits on `QES-Public` branch
  `dtcc-embed-turbulence`, based on `dtcc-embed`. Update the
  submodule pointer and `src/dtcc_qes/_qes_revision.txt` together. No pushes.
  Work happens on a feature branch, never on `main`.
- Turbulence is screening output. Docs and metadata must say it comes from an
  algebraic mixing-length model that has not been validated for pedestrian gusts.
- Invalid stress is not calm flow. Preserve raw tensors, validity masks and
  invalid-cell counts through sampling/export. Record GEM provenance and the
  screening limitation in `ComfortResult`, even when mean-only warnings go away.
- Rebuild before Python tests: `uv sync --frozen --reinstall-package dtcc-qes`.
  Native tests use the `cmake`/`ctest` commands in README §"Validate and package".

## Review Focus

1. **Calm wind** (`speed=0`): computed stress, tke and co_eps are finite zeros,
   and `capped_cells == 0`. Mixing length remains a geometric quantity. A zero
   stress tensor is valid, but σ/TI are NaN where the mean direction is
   undefined; all uncomputed Python float fields remain NaN. Tested in Tasks
   1A, 2 (`calm` mode) and 5. Near-calm inputs must not introduce infinities.
2. **City without buildings**: `zRef = 100 × roughness_length`, i.e. 50 m at
   z0 = 0.5. Automatic tops rise; explicit bounds raise. Tested in Task 4.
3. **One runner, several directions**: a later solve must not inherit earlier
   stresses. Tested in Task 2 (`repeat` mode).
4. **Explicit or automatic vertical grids**: the nonuniform branch must give
   finite native computed fields that match the nonuniform formula. Derived
   values additionally obey the stress-validity mask. Tested in Task 5.
5. **Cells QES does not compute** (solids, first and last x/y columns, top
   layer): NaN in Python, never a 0 that looks like calm. Tested in Task 5.
6. **Oblique winds:** manufactured flat shear must preserve the analytic
   streamwise σ and rotate the complete uncapped tensor consistently at flow
   headings 0°, 30°, 45° and 90° (Task 1A). Cardinal directions alone are
   insufficient.
7. **Computed but invalid stress:** real one-building results and synthetic
   indefinite tensors must be detected, counted and masked in derived output
   without rewriting raw stress (Tasks 1A, 2, 5 and 9).
8. **Method 1 on thin layers:** reproduce the bounds failure and the 4×
   mixing-length counterexample, then pass ASan/UBSan and distance invariants
   after repair (Task 1B).
9. **Automatic tops:** include 20 m mid-rise buildings at 2 m resolution and
   15 m buildings at 1 m and 0.5 m resolution. One retry is not a valid
   termination rule (Task 4).

## Execution order and acceptance gates

Task identifiers are retained for traceability. Execute:
**1 → 1A → 1B → 2 → 3 → 4 → 5 → 9 → 6 → 7 → 8**.

- Tasks 1, 1A and 1B repair the native core and establish the validity policy.
  Method 0 can be used for development while method 1 remains unavailable;
  unfinished method-1 checks must be reported as such.
- Tasks 2–5 provide extraction, reference provenance, domain policy, results
  and sampling. They must not advertise gust validation.
- Task 9 runs before downstream integration. It records numerical acceptance
  separately from physical validation and from performance measurements.
- Tasks 6–8 start only after the numerical acceptance criteria pass. A failed
  criterion returns work to the relevant repair task; it is not waived by
  matching pristine upstream output.

---

### Task 1: QES fork: ownership, accessors and guards

**Files:**
- Modify: `QES-Public/src/winds/TURBGeneralData.h`, `QES-Public/src/winds/TURBGeneralData.cpp`
- Modify: `QES-Public/src/winds/LocalMixing.h`, `QES-Public/src/winds/TURBWall.h`
- Modify: submodule pointer `QES-Public`, `src/dtcc_qes/_qes_revision.txt`
- Create: `tests/native/check_turbulence.cpp`; register it in `CMakeLists.txt` under `DTCC_QES_BUILD_TESTS`, linked like `check_physics`

**Interfaces:**
- Produces (public on `TURBGeneralData`): `float getReferenceHeight() const`
  (zRef), `getReferenceSpeed()` (uRef), `getFrictionVelocity()` (uStar),
  `getRoughnessLength()` (z0d), `getDisplacementHeight()` (d0d),
  `getUpperBound()` (turbUpperBound).
- Produces: the constructor throws `qes::InputError` before any allocation-heavy
  work when either holds:
  - `methodLocalMixing` is not 0 or 1, and not 3 with `HAS_OPTIX`, and not 4
    with `QES_ENABLE_IO`.
  - `domain.z_face.back() < 15 + terrainH_max`.
- Produces: `frictionVelocity()` throws `qes::InputError` when the
  `std::lower_bound(z_face, zRef)` index exceeds `domain.nz() - 2`. Hoist the
  lookup out of the (i, j) loop.
- Produces: `wallVec` becomes `std::vector<std::unique_ptr<TURBWall>>` and
  `localMixing` becomes `std::unique_ptr<LocalMixing>`. Both base classes gain
  `virtual ~LocalMixing() = default` / `virtual ~TURBWall() = default` before
  ownership is converted. Include exception paths and all constructors in
  the ownership audit.

- [x] **Step 1: Write the failing native tests.** `check_turbulence <mode>`
  builds `QESInputs` and `WINDSGeneralData` for a 40×30 flat 2 m grid, sets a
  local `TURBParams` on `inputs.input.turbParams`, and asserts that
  constructing `TURBGeneralData` throws `std::invalid_argument`:
  - `low_top`: nz = 6 (12 m top), roughness 0.05 (zRef 5 m). Tests the 15 m guard.
  - `ref_in_top_cell`: nz = 10 (20 m top), roughness 0.19 (zRef 19 m). The
    lower_bound index is 11 > 10.
  - `methods`: methods 2, 5 and −1.

  Register `add_test(NAME native_turbulence_${mode} …)`.
  Add ownership coverage using a derived helper with observable destruction,
  repeated construction/destruction and a constructor-failure path. Do not
  assume ASan/UBSan alone proves the absence of leaks on every platform; use
  leak detection where supported and verify destruction explicitly.
- [x] **Step 2: Run** `cmake --build build/native --target check_turbulence && ctest --test-dir build/native -R native_turbulence --output-on-failure`.
  The initial test build failed on the missing accessors, virtual destructors
  and owned-helper interface. After implementation, all eight modes pass:
  low_top, ref_in_top_cell, ref_above_top, reference_boundary, methods,
  ownership, references and lifecycle.
- [x] **Step 3: Implement** the fork changes listed above on the isolated
  `dtcc-embed-turbulence` branch.
- [x] **Step 4: Run** the full `ctest` in Release, then again in a sanitizer
  build (`-DDTCC_QES_ENABLE_SANITIZERS=ON -DCMAKE_BUILD_TYPE=Debug`).
  Result: 19/19 passed in Release (4.39 s) and Debug ASan/UBSan (200.89 s),
  with no sanitizer reports. The Release `check_native_symbols` target passed.
- [x] **Step 5: Commit** in `QES-Public` ("Own turbulence helpers, expose
  reference values and guard reference heights"). Then commit the submodule
  pointer, revision file, test and CMake change in dtcc-qes.
  QES commit: `514d91cd` ("Own turbulence helpers and guard reference sampling");
  parent changes are recorded in the Task 1 integration commit on this branch.

### Task 1A: Correct stress rotation and specify tensor validity

**Files:** Modify `QES-Public/src/winds/TURBGeneralData.{h,cpp}`,
`tests/native/check_turbulence.cpp`, `CMakeLists.txt` and
`tools/check_artifacts.py`. Create `src/cpp/stress_validity.h`,
`tools/check_stress_validity.py` and `docs/turbulence-reference-differences.md`
to establish the shared numerical contract and begin Task 3's provenance
report. Record the fork revision and submodule pointer together.

**Requirements:**
- Derive the Cartesian-to-wind and wind-to-Cartesian transforms explicitly.
  For an orthonormal wind basis Q, use consistent tensor transforms
  `tau_wind = Q^T tau_cartesian Q` and `tau_cartesian = Q tau_wind Q^T`.
  Keep direction conventions distinct from meteorological input angles.
- Verify the entire uncapped tensor against an independent analytic oracle,
  including off-diagonal signs. Test direction reversal as well as oblique
  headings. Component-wise clipping is a separate, basis-dependent operation;
  do not mistake clipped-tensor differences for the rotation test.
- Audit the 15 m direction sample when it lies inside a building or has zero
  horizontal speed. A usable preferred sample keeps QES's original
  `lower_bound(z_face, 15 + terrain)` index and staggered u/v pair. Otherwise
  select the closest physical fluid z centre with finite, nonzero horizontal
  velocity; prefer the higher centre on an equal-distance tie. Use Cartesian
  +x only when the entire column has no usable direction. Do not label that
  fallback a measured wind direction. Expose `getRotationFallbackColumns()`
  and reset its count each run; count distinct affected computed columns, not
  every vertical cell. This is an explicit Task 3 parity exception.
- Adopt the initial raw-plus-mask policy: finite zero tensors are valid;
  materially indefinite tensors are invalid even if one projection is positive.
  Use float64 arithmetic on the stored float32 tensor and a scale-relative
  tolerance, initially `tol = 32 * eps(float32) * max(abs(eigenvalues))`.
  Require `lambda_min >= -tol`. Zero tensors have tol = 0. Test and record
  this tolerance; do not introduce a fixed positive variance floor.
- The projection helper may round a negative projected variance to zero only
  when the tensor passes validity and the variance lies within that roundoff
  tolerance. Otherwise derived values are NaN with invalidity recorded.
  No implicit `makeRealizable` call or raw-tensor eigenvalue clipping is added.

- [x] **Step 1: Reproduce the rotation failure.** Manufacture
  `U(z) = (10 + 0.1 z) (cos(theta), sin(theta), 0)` on the 2 m flat grid.
  At z = 9 m, expected σ = 0.9 m/s for theta = 0°, 30°, 45°, 90° and their
  reversals. Confirm the current 45° result is about 0.72 m/s. Compare the full
  analytic tensor at interior cells (rtol 1e-5, atol 1e-7).
  Recorded failing regression: 0.720000 m/s at 45° against 0.900000 expected.
- [x] **Step 2: Add validity cases.** Include a zero tensor, a positive tensor,
  roundoff-scale negative eigenvalues, a materially indefinite tensor with
  positive projection, and a tensor with negative projection. Include the
  reviewed one-building case and test positive speed rescaling. Invalid
  counts from the pre-fix probe are evidence, not immutable golden counts
  after the rotation fix.
  Implemented in the native `validity`/`building_validity` modes, with
  zero/nonfinite velocity, positive-projection indefinite tensors, tolerance
  clamping and extreme finite direction-normalization cases. The independent
  tool agrees with NumPy on 5,000 tensors at scales 1e-30 to 1e30.
- [x] **Step 3: Correct the rotation and cover the direction fallback.** Leave
  the separately specified validity policy visible at the bridge/Python
  boundaries in Tasks 2 and 5. Record expected upstream differences.
  The QES-free helper defines `stress_validity` and `streamwise_variance` for
  Task 2 to consume; Task 5 must mirror the same stored-float32/float64
  tolerance contract. No implicit raw-tensor correction was introduced.
- [x] **Step 4: Run** native analytic cases in Release and under ASan/UBSan.
  Require correct oblique-angle results and finite native computed fields.
  Result: 24/24 full Release tests, 13/13 sanitizer turbulence tests, and the
  Release no-I/O symbol audit pass. The direction tests include blocked,
  zero/nonfinite, nonuniform, tie, terrain-relative and exact-top cases.
- [x] **Step 5: Commit** the numerical repair and its independent regression
  tests, with updated QES revision provenance.
  QES commit `2df34fc8`; parent changes include the shared helper, reference
  comparison tool, tests, provenance report and synchronized submodule revision.

### Task 1B: Repair and qualify serial wall-distance mixing

**Files:** Modify `QES-Public/src/winds/LocalMixingSerial.cpp` and, if needed,
its header; extend `tests/native/check_turbulence.cpp`. Record the fork
revision and submodule pointer together.

**Requirements:**
- Audit all directional propagation loops against actual coordinate and field
  array lengths, including inclusive upper bounds and `i + 1`/`j + 1` offsets.
  Cover tall buildings, boundary clearance, thin/nonuniform layers and flat
  domains without buildings. A fix for just the first ASan failure is insufficient.
- Preserve the minimum already found when applying each wall contribution.
  On flat ground, require `0 < Lm_wall <= Lm_height` on computed cells within
  float32 tolerance. Test selected distances against an independent box/plane
  geometry oracle; agreement with a copied propagation loop is not an oracle.
- Specify the influence-region transition and guard degenerate interpolation
  intervals. State the method's approximation limits; do not claim exact
  nearest-wall distance throughout the domain without evidence.
- Method 1 remains unavailable through the bridge, Python and dataset entry
  points until the safety and distance requirements pass. Keep method 0 as the
  provisional default; this audit does not select a scientifically validated
  default for gusts.

- [ ] **Step 1: Promote both reviewed thin-layer cases into tests.** The
  40×30×80 case reproduces the ASan failure; the 60×60×80 setup case isolates
  the length invariant without the original boundary access. Include genuinely
  nonuniform z layers and permutations/reflections of wall orientations.
- [ ] **Step 2: Run** under ASan/UBSan before repair to capture the failure.
- [ ] **Step 3: Repair** propagation bounds and distance updates. Document
  numerical differences from pristine QES for Task 3.
- [ ] **Step 4: Run** the complete native turbulence suite in Release and under
  ASan/UBSan. Require no invalid accesses, finite positive computed lengths,
  the height upper bound, and agreement with the selected geometry oracles.
- [ ] **Step 5: Commit** the repair and regressions; enable method 1 only after
  these checks pass. Its larger-domain cost is assessed in Task 9.

### Task 2: Bridge: settings, runner lifecycle, extraction and bindings

**Files:**
- Modify: `src/cpp/wind_config.h`, `src/cpp/qes_inputs.{h,cpp}`, `src/cpp/wind_runner.{h,cpp}`, `src/cpp/bindings.cpp`, `CMakeLists.txt` (add `src/cpp/turbulence.cpp` to `qesbridge`), `tools/check_artifacts.py` (list the new sources)
- Create: `src/cpp/turbulence.h`, `src/cpp/turbulence.cpp` (bridge-only; may include QES)
- Test: `tests/native/check_turbulence.cpp`, `tests/test_runner.py`

**Interfaces:**
- Consumes: Task 1 ownership/accessors/guards, Task 1A rotation and validity
  contract, and the Task 1B qualification before method 1 can be selected.
  Reuse `src/cpp/stress_validity.h` for native validity/projection rather than
  introducing a second native policy. Propagate the direction-fallback count.
- Produces (`wind_config.h`, QES-free):
  ```cpp
  struct TurbulenceSettings { bool enabled = false; int mixing_length_method = 0; }; // 0 height, 1 wall distance
  struct TurbulenceData {
    std::vector<float> stress;                          // nz*ny*nx*6: txx, txy, txz, tyy, tyz, tzz
    std::vector<float> tke, co_eps, mixing_length;      // nz*ny*nx
    std::vector<std::uint8_t> state;                    // 0 not computed, 1 computed, 2 computed and capped
    std::vector<std::uint8_t> stress_valid;             // independent covariance-validity mask
    float friction_velocity = 0, reference_speed = 0, reference_height = 0;
    float roughness_length = 0, displacement_height = 0, upper_bound = 0;
    std::size_t computed_cells = 0, capped_cells = 0, invalid_stress_cells = 0;
    std::size_t rotation_fallback_columns = 0;
  };
  // WindData gains: std::optional<TurbulenceData> turbulence;
  ```
- Produces (`turbulence.h`):
  - `void configure_turbulence(TURBParams &, const TurbulenceSettings &)`:
    rejects unsupported or not-yet-qualified methods with `std::invalid_argument`.
  - `void check_turbulence_margin(const TURBGeneralData &, const GridConfig &)`:
    the lower_bound index of `getReferenceHeight()` on QES's ghost-inclusive `z_face` must be
    `≤ grid.nz - 2`. Otherwise throw, with a message naming zRef and the
    failed layer margin and a sufficient top under the Task 4 extension policy.
  - `TurbulenceData turbulence_fields(const TURBGeneralData &, const GridConfig &)`.
- Produces (runner): `WindRunner::prepare(const GridConfig &, const ModelSettings &, const BuildingArrays &, const TurbulenceSettings &, Messages &)`.
  The existing 4-argument overload delegates with `TurbulenceSettings{}`.
  - `Impl` member order is grid, inputs, data, turbulence
    (`std::unique_ptr<TURBGeneralData>`), solver. Reverse destruction must free
    turbulence before data.
  - When enabled, construct turbulence right after `data`, then run
    `check_turbulence_margin`.
  - In `solve`, call `run()` after the wind solve and fill `result.turbulence`.
- Produces (Python): `_qes.TurbulenceSettings` with `enabled` and
  `mixing_length_method`, and
  `WindRunner.prepare(..., *, dz_layers=None, turbulence=None)`. The `solve()`
  dict gains `"turbulence"`, which is either `None` or a dict with:
  - `stress`: (nz, ny, nx, 6) float32.
  - `tke`, `co_eps`, `mixing_length`: (nz, ny, nx) float32.
  - `state`, `stress_valid`: (nz, ny, nx) uint8.
  - the scalar fields of `TurbulenceData`.
- Extraction rules:
  - Use the same `(k = 1..nz, j, i)` mapping as the velocity loop in `wind_runner.cpp`.
  - "Computed" means membership in `icellfluid`, not `iturbflag`; `iturbflag`
    also marks wall cells in the last column.
  - A cell is "capped" when the bound `getUpperBound() * u* * u*` (float, in
    QES's operation order) is > 0 and either `tke` or any `|τ|` is ≥ the bound.
  - `stress_valid` follows Task 1A and is false outside computed cells.
    `invalid_stress_cells` counts computed cells failing that check, including
    nonfinite tensors. Keep their raw tensor components unchanged. A mask or
    cap count never substitutes for a validity check.

- [ ] **Step 1: Write the failing tests.** Add these `check_turbulence` modes:
  - `flat_analytic`: flat 40×30×20 2 m grid, 270°, method 0. Let `U_k` be the
    returned x-velocity, `G = (U_{k+1} − U_{k−1}) / 4 m` and `Lm = 0.4 z_k`.
    For computed cells with 2 ≤ k ≤ nz−1 (1-based physical), assert
    `txx = (2.5 Lm G)²`, `tyy = (2.0 Lm G)²`, `tzz = (1.3 Lm G)²`,
    `txz = −Lm² G|G|`, `txy = tyz = 0`, `tke = (Lm G / 0.55)²`,
    `co_eps = 5.7 (0.55 √tke)³ / Lm`, and `capped_cells == 0`
    (rtol 1e-5, atol 1e-7).
  - `calm`: speed 0. Computed stress, tke and co_eps are finite zeros;
    `capped_cells == 0`; mixing length equals the nonzero-speed run on the same
    grid. Computed zero tensors pass validity.
  - `scaling`: one building at 5 and 10 m/s. Stress and tke ×4 and co_eps ×8
    (rtol 1e-4); `mixing_length`, `state` and `stress_valid` equal;
    `friction_velocity` ×2.
  - `repeat`: solve 270°, then 0°, then 270°. The third result is bitwise equal
    to the first.
  - `wall_distance`: after Task 1B, one building, method 1, on both the uniform
    and thin-layer grids. Computed native fields are finite;
    `mixing_length ≤ 1.000001 × the method-0 value` on computed cells, and
    strictly smaller in at least one cell next to the building.
  - `margin`: one 8 m building (zRef 24 m). nz = 13 throws
    `std::invalid_argument` with "domain top" in the message; nz = 15 passes.
  - `bridge_methods`: methods 2, 3 and 4 are rejected before QES is called.
  - `invalid_stress`: extraction distinguishes computed/valid/capped states,
    preserves indefinite raw tensors, and reports their count correctly.

  In `tests/test_runner.py`, add tests that `turbulence=None` gives
  `result["turbulence"] is None`, and that keys, dtypes, shapes and
  no-aliasing across solves match the velocity tests.
- [ ] **Step 2: Run** `ctest -R native_turbulence` and
  `uv run --frozen python -m pytest tests/test_runner.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run** the full `ctest` (Release and sanitizer),
  `cmake --build build/native --target check_native_symbols`, and
  `uv run --frozen python -m pytest -q`. Expected: all PASS, and existing tests
  are unchanged.
- [ ] **Step 5: Commit.**

### Task 3: Upstream provenance, audited-fork parity and independent correctness

**Files:**
- Modify: `tools/make_reference.py`. Add a `--turbulence` flag that writes
  `<turbParams><method>0</method></turbParams>`, runs `qesWinds … -t`, and
  reads `<base>_turbOut.nc`: `txx txy txz tyy tyz tzz tke CoEps L`, physical
  layers `[1:]`, dropping QES's ghost layer. Add explicit turbulence baseline
  selection, `--baseline upstream|audited`, and method selection for repaired
  method-1 cases. Existing wind-reference behaviour stays unchanged.
- Create: `tests/fixtures/reference/turbulence/{upstream,audited}/*.{npz,json}`,
  `tests/test_turbulence_reference.py`, `docs/turbulence-reference-differences.md`.

**Interfaces:**
- Consumes: the Task 2 runner and `tests/runner_cases.py` (`inputs`, `prepared`).
- Produces two independently identified reference sets:
  - `upstream`: pristine `QES_REFERENCE_REV`, preserving original behaviour
    on cases that can be run safely. Do not run known memory-unsafe cases to
    generate supposedly authoritative fixtures.
  - `audited`: standalone QES at the exact committed fork revision used by
    the bridge, with the Task 1A/1B repairs. Record revision, method, compiler,
    build options and case definition; fixtures must not silently come from
    a dirty or differently revised tree.
- Exact bridge-to-standalone comparisons use the audited baseline on the
  same grid and build configuration. Upstream-to-audited differences are
  attributed to named fixes, with affected fields and measured changes.
  Keep exact upstream assertions for unaffected fields/cases only.
- Include oblique winds and thin/nonuniform layers in corrected cases.
  Independent analytic and geometry tests from Tasks 1A/1B remain required:
  two paths through the same QES implementation can agree on a bug.

- [ ] **Step 1: Write the failing test.**
  `test_bound_runner_turbulence_matches_audited_reference[case]`: on
  computed cells, `assert_array_equal` holds for stress, tke, co_eps and
  mixing_length. Reference values outside the computed cells are 0.
  Add separate upstream-difference checks and preserve wind-only assertions.
- [ ] **Step 2: Run** it. Expected: FAIL (missing fixture).
- [ ] **Step 3: Generate both reference sets** with
  `uv run --frozen --group reference python tools/make_reference.py --turbulence --baseline upstream`
  and `… --baseline audited`. Record the reviewed differences in the report.
- [ ] **Step 4: Run** the tests and `make_reference.py --turbulence --baseline audited --check`.
  Expected: exact audited-fork parity and passing independent correctness
  tests. Investigate unexplained differences; do not relax tolerances or
  overwrite pristine provenance to conceal a numerical change.
- [ ] **Step 5: Commit.**

### Task 4: Domain-top policy for turbulence

**Files:**
- Modify: `src/dtcc_qes/_city.py`, `src/dtcc_qes/wind.py` (`preview_grid` and `_prepare_city` gain `turbulence`)
- Test: `tests/test_turbulence_domain.py`

**Interfaces:**
- `turbulence_reference_height(heights, roughness_length) -> float`: `3 × mean`,
  accumulated in float32 in ascending-height order, or `100 × float32(roughness_length)`
  when there are no buildings.
- `turbulence_top(z_ref: float, spacing: float) -> float`:
  `max(z_ref + 3 * spacing, 15.0)` is an initial uniform-grid target, not a
  sufficient top for an arbitrary stretched grid. Final acceptance always
  uses the effective float32 faces.
- `default_domain_top(heights, reference_height, vertical_clearance, spacing, *, turbulence_reference=None)`:
  the existing maximum, also taking `turbulence_top(...)` into account when
  `turbulence_reference` is given.
- `check_turbulence_faces(faces, z_ref) -> None`: `faces` are float32 with
  length nz+1 and `faces[0] = 0`. Requires at least three physical layers,
  `faces[-4] >= z_ref` (the sampled
  layer has two layers above it) and `faces[-1] >= 15`. Otherwise raises a
  `ValueError` naming zRef and a sufficient top under the stated extension
  policy. For explicit nonuniform faces, also explain the failed layer margin;
  there is no grid-independent minimum top. This mirrors the bridge's
  `check_turbulence_margin` with its different, ghost-inclusive indexing.
- `prepare_domain(..., turbulence=False)`:
  - Automatic bounds use `turbulence_reference`.
  - For automatic uniform grids, append layers until the effective faces pass.
  - For `VerticalGrid.auto`, preserve a valid wind-only layer prefix where
    available and append a constant-thickness tail using the last valid
    thickness. This preserves lower operands and respects the nondecreasing
    caps/growth constraints of the current generator. Recompute float32 faces
    and recheck the margin after extension; do not stop after one retry.
  - Bound extension by the existing 10,000-layer, max_cells and native-index
    limits, checking float32 coordinate progress and existing vertical-grid
    constraints before allocating the solver. Raise with the binding limit if
    a valid top cannot be reached. Never loop without a bound.
  - If a valid base prefix cannot be retained and regeneration is necessary,
    record that fact, preserve the fine band where feasible, and run a new
    lower-grid sensitivity control. The existing taller-domain study does not
    validate regenerated lower layers.
  - Explicit bounds or z_faces are only checked.
  - Records `domain["turbulence"] = dict(reference_height, required_top,
    default_top, effective_top, raised, added_layers, lower_layers_preserved,
    extension_policy)`. Required-top messages and metadata must describe the
    policy actually used, not the rejected one-retry estimate.

- [ ] **Step 1: Write the failing tests:**
  - `test_uniform_midrise_city_raises_automatic_top`: four 15 m blocks at 2 m.
    `preview_grid(turbulence=True)` gives `faces[-4] >= 45` and `raised=True`;
    `turbulence=False` gives the same top as today.
  - `test_tall_tower_keeps_default_top`: the C2 "tower" array (mean 11.85 m).
    `raised=False` and the faces are identical.
  - `test_explicit_bounds_too_low_raise`: an 8 m building with zmax 26 m raises
    a `ValueError` that mentions 30 m.
  - `test_explicit_z_faces_too_low_raise`.
  - `test_automatic_vertical_grid_satisfies_margin`.
  - `test_automatic_midrise_retry_regression`: four 20 m blocks at 2 m;
    `faces[-4] >= 60` after growth. Also cover 15 m blocks at 1 m and 0.5 m.
  - `test_automatic_extension_preserves_lower_layers`: compare the float32
    operands and faces of the retained prefix with the wind-only preview.
  - `test_automatic_growth_respects_cell_and_layer_limits`.
  - `test_python_and_native_reference_margin_agree`: exact-face and adjacent
    float32 heights on uniform and nonuniform grids, including small nz.
  - `test_no_buildings_uses_roughness`: roughness 0.5 with zmax 40 m raises.
  - `test_turbulence_false_domain_unchanged`.
- [ ] **Step 2: Run** `uv run --frozen python -m pytest tests/test_turbulence_domain.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full pytest suite. Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 5: Python API: `run(turbulence=...)`, results and derived statistics

**Files:**
- Create: `src/dtcc_qes/turbulence.py` (the `Turbulence` spec)
- Modify: `src/dtcc_qes/result.py`, `src/dtcc_qes/wind.py` (signature, docstring, metadata, `__all__`), `README.md` (usage, memory note, limitations; remove turbulence from the deferred list)
- Test: `tests/test_turbulence.py`

**Interfaces:**
- `@dataclass(frozen=True) class Turbulence: mixing_length: Literal["height", "wall_distance"] = "height"`,
  validated in `__post_init__`; maps to QES methods 0 and 1. Method 1 requires
  the Task 1B qualification; all entry points use the same availability rule.
- `wind.run(..., turbulence: bool | Turbulence = False) -> WindResult` and
  `wind.preview_grid(..., turbulence=False)`. `True` means `Turbulence()`;
  anything else raises `ValueError`.
- `@dataclass(frozen=True) class TurbulenceFields` (in `result.py`):
  - `stress`: (z, y, x, 6) float32.
  - `tke`, `co_eps`, `mixing_length`: (z, y, x) float32.
  - `computed`, `capped`, `stress_valid`: (z, y, x) bool.
  - `friction_velocity`, `reference_speed`, `reference_height`,
    `roughness_length`, `displacement_height`: float.
  - Float arrays are NaN wherever `computed` is False. Computed raw stresses
    remain unchanged even when `stress_valid` is False; validity is not a
    reason to overwrite diagnostic evidence.
- `WindResult.turbulence: TurbulenceFields | None = None` (new last field).
- `WindResult.streamwise_std` returns float64 (z, y, x): `sqrt(ê·τ·ê)` with
  `ê = velocity / |velocity|`, NaN where a cell is not computed, stress fails
  the Task 1A validity check, velocity is nonfinite, or speed is 0. Only
  roundoff-sized negative projections of valid tensors may round to zero.
  `WindResult.turbulence_intensity = streamwise_std / speed`. Both raise
  `ValueError` when `turbulence is None`.
- `WindSample.stress: np.ndarray | None = None`: (y, x, 6) float64, using the
  same nearest/linear rule, NaN if any contributing cell is not computed.
  Add `WindSample.stress_valid: np.ndarray | None = None`, (y, x) bool:
  every contributing tensor must be valid and the interpolated tensor must
  pass the same check. Exact-centre samples use only that centre. An invalid
  neighbour must not become valid merely because interpolation hides it.
  `WindSample.streamwise_std` and `.turbulence_intensity` follow the same
  definitions. Use one shared private projection helper in `result.py` and
  cross-check its validity result against native extraction. Because arrays
  are editable, derived properties recheck the current tensors rather than
  trusting a stale validity mask. Metadata counts describe the original solve.
- `metadata["turbulence"]` is absent when turbulence is off. When on, it has:
  - `model`, `mixing_length`, `qes_method`, `numerics_version` and the audited
    fixes/parity exceptions applied.
  - `constants`: `von_karman=0.4`, `c_pope=0.55`,
    `sigma_over_ustar=(2.5, 2.0, 1.3)`, `c0=5.7`, `upper_bound`,
    `building_wall_flag=2`, `terrain_wall_flag=2`, `non_local_mixing=False`,
    `background_mixing=0.0`, `rotation_reference_height=15.0`.
  - `reference`: height, speed, friction_velocity, roughness_length,
    displacement_height, and basis (`"3 × mean building height"` or
    `"100 × roughness_length"`).
  - `cap`: value, computed_cells, capped_cells.
  - `validity`: policy (`"raw_and_mask"`), tolerance definition,
    invalid_stress_cells, zero-speed cells, and rotation-direction fallback
    policy/count. Keep validity independent from the cap diagnostics.
  - `domain_top` (from Task 4), `speed_scaling`, `limitations`.

- [ ] **Step 1: Write the failing tests:**
  - `test_run_returns_wind_and_turbulence_in_one_call`: one building. Velocity
    is bitwise equal to a `turbulence=False` run **on the same sufficiently
    tall explicit grid**; turbulence shapes and dtypes are correct. Automatic
    domain growth is tested separately in Task 4.
  - `test_non_computed_cells_are_nan`: solids, i = 0, i = nx−1, j = 0,
    j = ny−1, and the top layer.
  - `test_calm_wind_turbulence_is_zero`: computed stress/tke/co_eps are zero,
    geometric mixing length is retained, zero tensors are valid, undefined
    σ/TI are NaN, and uncomputed arrays stay NaN. Include near-calm inputs.
  - `test_flat_streamwise_std_matches_surface_layer_relation[270, 240, 225, 0]`:
    `streamwise_std = 2.5 · 0.4 z_k |G|` for 2 ≤ k ≤ nz−1 (rtol 1e-5), where
    G is the gradient of the scalar mean-speed profile. These meteorological
    directions include oblique flow; verify the tensor rotation too.
  - `test_stretched_grid_matches_nonuniform_gradient`: explicit z_faces;
    `streamwise_std = 2.5 · 0.4 z_k |G_k|` with
    `G_k = [h⁻/h⁺ (U_{k+1} − U_k) + h⁺/h⁻ (U_k − U_{k−1})] / (h⁺ + h⁻)`,
    where `h± = |z_{k±1} − z_k|` (rtol 1e-4).
  - `test_speed_scaling`: 5 vs 10 m/s. `streamwise_std` doubles and
    `turbulence_intensity` is equal (rtol 1e-4).
  - `test_sample_includes_stress`: `sample(1.5, "linear")` stress equals a
    manual interpolation.
  - `test_invalid_raw_stress_is_preserved_but_statistics_are_nan`.
  - `test_positive_projection_does_not_hide_indefinite_tensor`.
  - `test_validity_roundoff_tolerance_scales_with_speed`.
  - `test_sample_preserves_invalid_contributor_and_zero_speed_masks`.
  - `test_derived_statistics_recheck_edited_stress`.
  - `test_metadata_records_reference_and_cap`.
  - `test_invalid_turbulence_argument`.
  - `test_wall_distance_mixing_length_not_longer_than_height`.
  - `test_turbulence_false_metadata_unchanged`.
- [ ] **Step 2: Run** `uv run --frozen python -m pytest tests/test_turbulence.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full pytest suite. Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 9: Numerical acceptance, mixing-length benchmark and validation report

**Execution:** run after Task 5 and before Tasks 6–8. The identifier is retained
from the original plan; this is no longer the final implementation task.

**Files:**
- Create: `tools/run_turbulence_benchmark.py` (with `--self-test`), `docs/turbulence-benchmark.md`, `docs/data/turbulence-benchmark/*.json`
- Test: `tests/test_turbulence_benchmark.py`, which runs the self-test on a tiny case (pattern: `tests/test_vertical_grid_study.py`)

**Measurements.** Use the median of 3 repetitions for timings. Each
configuration runs in a fresh subprocess so peak RSS is clean. Record solver
convergence and exclude failed solves from accepted numerical comparisons.

1. **Cost per method.** Time `prepare` and `solve` with and without turbulence,
   using `_qes.WindRunner` directly, and record peak RSS. Cases: the C2
   geometries `isolated`, `passage`, `array` and `tower`
   (`rectangles()` in `tools/run_auto_grid_controls.py`), plus one synthetic
   city of about 1–2 M cells. Include validity-check and Python-derived-array
   cost; distinguish same-grid overhead from extra domain layers.
2. **Differences between qualified methods** at 1.5 m and 1.75 m: P50, P95 and
   maximum change in streamwise σ and TI, capped fractions and invalid-stress
   fractions. Compare a common valid sample set and report excluded counts and
   locations. Where a relative denominator is zero, report absolute change
   and a separate zero-denominator count instead of silently dropping it.
3. **Flat-terrain grid sensitivity.** Compare `streamwise_std / u*_inflow` with
   `2.5 z/(z+z0)`, where `u*_inflow = 0.4 U_ref / ln((z_ref+z0)/z0)`.
   Grids: uniform 2, 1 and 0.5 m, and `VerticalGrid.auto`; heights 1.5 m and
   1.75 m. Separate derivative error from sampling error. Record the actual
   sampled height for nearest sampling; use linear sampling for comparisons
   at the requested height. Include cardinal and oblique winds.
4. **Speed scaling** (5 vs 10 m/s) on every geometry, including validity,
   cap and zero-speed masks. Check σ, stress and co_eps, not only TI or
   comfort classes.
5. **Stress validity.** Record minimum eigenvalues, invalid tensor counts,
   negative projected variance counts and affected pedestrian samples. Test
   diagnostics and masks before/after interpolation. Raw values remain available
   even where derived statistics are masked.
6. **Domain growth.** Run the automatic-top regression cases and verify the
   final face margin, limits and prefix preservation. Compare the resulting
   wind/turbulence at pedestrian samples against a taller domain with the same
   retained lower operands. Report any regenerated lower layers separately.

**Numerical acceptance criteria (required before Tasks 6–8):**
- All ownership, height-guard and method-1 bounds regressions pass in Release
  and under ASan/UBSan. Method 1 also passes the distance-oracle and height
  upper-bound checks on uniform and nonuniform grids.
- Uncapped manufactured shear passes the full-tensor and oblique-angle oracle
  at the Task 1A tolerances. Speed scaling passes the Task 2/5 tolerances.
- Validity masks/counts agree with independent float64 eigenvalue checks on
  the small cases. Every materially invalid tensor is accounted for and no
  invalid tensor produces a finite derived statistic. No unexpected native
  NaN/inf occurs on computed cells of accepted cases. Zero raw indefinite
  tensors is **not** a requirement of the raw-plus-mask policy.
- Automatic growth meets its final effective-face margin or raises a clear
  resource-limit error; the reviewed ordinary mid-rise cases must succeed
  with sufficient cell budget. No explicit domain is silently enlarged.
- Flat-profile refinement is checked against the analytic relation, with the
  finest uniform grid closer than the coarsest at both pedestrian heights.
  Report all errors, mask coverage and building-case sensitivity. Declare any
  quantitative accuracy claim and its error budget before using it as a pass
  criterion; absent such a budget, do not claim grid-independent gust accuracy.
- Audited standalone parity passes and every known upstream difference has a
  numerical explanation. Legacy parity alone cannot satisfy this gate.

This gate establishes implementation correctness and quantified limitations.
It does **not** validate urban gusts against observations or certify a comfort
criterion. The report must distinguish those conclusions explicitly. A
realizability correction, if later proposed to recover masked coverage, needs
separate tests and measurements rather than replacing raw tensors silently.

- [ ] **Step 1: Write the self-test** for statistics, mask accounting and
  rejection of failed solves, and run it. Expected: FAIL.
- [ ] **Step 2: Implement the tool.** Run the self-test. Expected: PASS.
- [ ] **Step 3: Run the full benchmark.** Write the report with commands, host,
  QES revision, build type and per-criterion pass/fail evidence. Do not reduce
  the report to timings and a default-method recommendation.
- [ ] **Step 4: Assess the numerical gate and recommend a default.** Return
  failed checks to their repair task before downstream work. Changing the
  provisional default needs the user's sign-off and a separate commit.
- [ ] **Step 5: Commit** the benchmark, data and report.

### Task 6: DTCC export fields

**Files:** Modify `src/dtcc_qes/result.py` (`to_dtcc`). Test: `tests/test_turbulence.py`.

**Prerequisite:** Task 9 numerical acceptance.

**Interfaces:** when `turbulence` is set, `to_dtcc()` also adds these cell
`Field`s, in the same y, x, z-fastest order as `velocity`. Float fields are NaN
where not computed; the validity field is 0 there:
- `stress`: dim 6, m²/s², raw values and component order in the description.
- `tke`: m²/s².
- `streamwise_std`: m/s.
- `turbulence_intensity`: unit `1`.
- `stress_valid`: unit `1`, encoded as 0/1, false outside computed cells.
  Derived σ/TI also stay NaN for invalid stress or undefined mean direction;
  raw stress is not masked merely because it is indefinite. Include the
  screening and validity policy in the exported field descriptions/provenance.

- [ ] **Step 1: Write the failing tests:**
  - `test_to_dtcc_adds_turbulence_fields`: names, units, and the value at one
    known cell after reordering.
  - `test_to_dtcc_preserves_raw_invalid_stress_and_masks_statistics`.
  - `test_to_dtcc_without_turbulence_unchanged`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full pytest suite. Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 7: Comfort GEM helper

**Files:** Modify `src/dtcc_qes/comfort.py` (`__all__`), `docs/wind-comfort.md`, `examples/wind_comfort.py`. Test: `tests/test_comfort.py`.

**Prerequisite:** Task 9 numerical acceptance. Outputs remain screening results.

**Interfaces:**
- `gust_equivalent_mean(speed, streamwise_std, *, peak_factor: float, gust_ratio: float = 1.85) -> np.ndarray`
  returns `(speed + peak_factor * streamwise_std) / gust_ratio` as float64.
  NaN propagates, including invalid-stress and undefined-direction samples.
  Non-finite or non-positive factors, negative finite speeds/standard
  deviations, infinities and mismatched shapes raise `ValueError`.
- The result is passed as `assess(..., gem_fields=...)`. `assess` already takes
  the worse of the mean and GEM exceedances.
- Add optional `gem_metadata` to `assess`, copied into `ComfortResult.metadata`.
  Reject it when no `gem_fields` are supplied. The QES example must supply
  source/model/numerics version, peak_factor, gust_ratio, mean averaging time,
  gust averaging time, validity policy and the screening limitation. Explicitly
  record unknown averaging times as unspecified; do not invent them.
- When provenance identifies QES-Turb, keep an unvalidated-gust screening
  warning in `ComfortResult.warnings`. Supplying GEM removes only the obsolete
  mean-only warning. Generic externally supplied GEM arrays remain supported;
  missing provenance must not imply validated or guideline-compliant gusts.

- [ ] **Step 1: Document the source and modelling assumptions.** Cite the
  [City of London Wind Microclimate Guidelines (2019)](https://www.cityoflondon.gov.uk/assets/Services-Environment/wind-microclimate-guidelines.pdf)
  for the 1.85 conversion and worse mean/GEM assessment. The review did not
  establish a peak factor or gust averaging time for this algebraic model
  from that source. Keep `peak_factor` required. Justify any example value and
  its averaging assumptions with a separate primary source or clearly label
  them as user-selected screening assumptions in the docstring and metadata.
- [ ] **Step 2: Write the failing tests:**
  - `test_gem_formula_and_nan_propagation`.
  - `test_gem_rejects_bad_factors`.
  - `test_gem_from_runs_scales_with_reference_speed`: GEM fields from
    one-building runs at 5 and 10 m/s give identical `assess(CITY_OF_LONDON, …)`
    classes.
  - `test_gem_fields_remove_only_mean_only_warning`.
  - `test_qes_gem_metadata_and_screening_warning_survive_assess`.
  - `test_invalid_stress_and_undefined_direction_remain_unassessed`:
    NaN GEM in any direction retains the existing invalid-cell classification.
- [ ] **Step 3: Run.** Expected: FAIL.
- [ ] **Step 4: Implement.** Update `docs/wind-comfort.md`: replace "QES
  computes no turbulence…" with how to build `gem_fields` from
  `sample.speed` and `sample.streamwise_std`, and say these are unvalidated
  screening results.
- [ ] **Step 5: Run** the full pytest suite and `examples/wind_comfort.py`. Expected: PASS.
- [ ] **Step 6: Commit.**

### Task 8: Dataset flag

**Files:** Modify `src/dtcc_qes/datasets.py`, `src/dtcc_qes/_dataset_city.py`. Test: `tests/test_datasets.py` (follow its existing offline city fixture pattern).

**Prerequisite:** Task 9 numerical acceptance and Task 6 export behaviour.

**Interfaces:**
- `QESWindArgs` gains `turbulence: bool = False` and
  `mixing_length: Literal["height", "wall_distance"] = "height"`. Setting
  `"wall_distance"` without `turbulence` raises `ValueError`.
  `wind_options()` passes `turbulence=Turbulence(mixing_length)` or `False`.
- `prepare_city`: an automatic top (4-value bounds) passes
  `turbulence_reference` to `default_domain_top`. An explicit zmax is checked
  by `run`.
- `describe()` adds `turbulence_field_names = ["stress", "tke", "streamwise_std", "turbulence_intensity", "stress_valid"]`.
- `_field_slice` adds nearest-cell `tke`, `streamwise_std`,
  `turbulence_intensity` and `stress_valid` when turbulence is present.
- Route automatic dataset tops through the same final face-margin/extension
  checks as `run`, preserving whether the user's zmax was explicit. The initial
  `default_domain_top` estimate alone cannot validate an automatic stretched grid.
- `presentation_limitations` gains the screening caveat, raw-stress validity
  policy and invalid coverage information. Method 1 follows the common
  qualification rule; invalid statistics cannot become zeros in a slice.

- [ ] **Step 1: Write the failing tests:**
  - `test_dataset_turbulence_field_product`.
  - `test_dataset_turbulence_slice_product`.
  - `test_dataset_raises_top_for_turbulence`.
  - `test_wall_distance_requires_turbulence`.
  - `test_dataset_preserves_invalid_turbulence_mask_and_provenance`.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full pytest suite and
  `examples/city_dataset.py … --product slice`. Expected: PASS.
- [ ] **Step 5: Commit.**

---

## Verification (end to end)

1. `cmake -S . -B build/native -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release && cmake --build build/native --parallel 8 && cmake --build build/native --target check_native_symbols && ctest --test-dir build/native --output-on-failure`
2. Configure/build and run CTest with `-DDTCC_QES_ENABLE_SANITIZERS=ON -DCMAKE_BUILD_TYPE=Debug` in `build/asan`. Report the known Debug assertion-symbol audit failure separately; the Release audit in step 1 remains mandatory.
3. `uv sync --frozen --reinstall-package dtcc-qes && DTCC_QES_NATIVE_TEST="$PWD/build/native/check_safety" uv run --frozen python -W error -m pytest -q`
4. `uv run --frozen --group reference python tools/make_reference.py --check` and `… --turbulence --baseline audited --check`; verify pristine upstream provenance and documented numerical differences separately.
5. `uv run --frozen python -m build --wheel --sdist --no-isolation -Ccmake.define.DTCC_QES_BUILD_TESTS=OFF && uv run --frozen python tools/check_artifacts.py dist`
6. Run the Task 9 benchmark and require its numerical acceptance report before downstream integration. Re-run affected cases after any subsequent numerical change.
7. Smoke test: `wind.run(city, 5, 270, turbulence=True)` on `examples/single_building.py`'s city, plus an oblique direction. Check `result.sample(1.5).turbulence_intensity` and `stress_valid`; metadata must record zRef, u\*, cap and invalid-stress counts, numerical fixes and actual domain extension. Verify a QES GEM assessment retains its modelling assumptions and screening warning.

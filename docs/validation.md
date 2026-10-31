# Milestone 1 validation

The [building-contact baseline](building-contacts.md) records reproducible
synthetic comparisons of touching, overlapping and nearly touching footprints.
It measures decomposition artifacts and documents the public opt-in canonical
footprint pipeline. Contact rejection remains active in the default strict mode.
The end-to-end review also covers dataset integration, profiles and solver
controls against the merged main branch.

**Current release scope (2026-10-28):** the numerical review is closed with
explicit limitations and B2 dataset integration supports experimental automatic
slices. Explicit grids and physical-height sampling retain their verified API
contracts. Automatic settings have no qualified comfort preset. The earlier
B2 gating statements below record historical decisions; the restricted closure
and dataset checks described later supersede them for this release.

The later [vertical-grid Stage 0 report](stage0-validation.md) documents the
vertical RHS correction, public conservative-divergence diagnostics, injection
and canyon regression tests, and plan reassessment. The original flat and
one-building references below are retained unchanged; they do not exercise
the vertical-divergence defect.

The [Stage A report](stagea-validation.md) documents explicit vertical layers,
coordinate and occupancy checks, serial/OpenMP agreement and the rooftop bounds
regression. The [sensitivity/cost gate](vertical-grid-gate.md) adds fixed-height
sampling, iteration stability and repeated measurements on four synthetic
geometries. A fine-grid tower solve fails the common residual target. The
[focused diagnosis](vertical-grid-diagnosis.md) traces the interior plateau to
the multiplier solution and tests a study-only precision remedy on both CPU
backends. The [B1 report](stageb1-validation.md) documents horizontal height
sampling and grid preview without flow arrays, including manufactured interpolation,
solid masks, archived study parity and coordinate/allocation checks. Failed
references remain excluded and automatic presets require further validation.
These numerical studies do not establish experimental accuracy.

The [C1 report](stagec1-validation.md) documents the automatic-grid prototype:
fine-band selection, height-dependent caps, constrained endpoint fitting,
float32 revalidation, preview/run integration and infeasible-setting checks.
Its candidate settings remain unvalidated for accuracy/cost; C2 precedes
selection of a supported automatic preset and B2 dataset integration.

The [C2 early-control report](stagec2-controls.md) adds actual generated-layer
workers, preserved-layer taller-domain and finer-x/y controls, and sampling at
both 1.5 and 1.75 m on common physical points. All 96 final serial/OpenMP workers
meet the solve gate but identify a fixed-location horizontal-sensitivity failure that
aggregate P95 and peak metrics miss. Resolve the supported horizontal scope
before broad policy tuning or preset selection; this milestone does not
complete C2's remaining accuracy/cost or experimental studies.

The [C2b report](stagec2b-horizontal-sensitivity.md) investigates the tower with
unchanged z layers, finer x/y spacing, larger lateral bounds and diagnostic
parameterization controls. It identifies sidewall and wall-averaging sensitivity,
fails the lateral-domain comparison budget, and withholds finer-grid comparisons
when maximum residuals fail. The 4 m away-region diagnostic does not establish
a supported preset scope. Secure accepted finer solves and verify lateral extent
and horizontal stabilization before C2c tuning or B2.

The [precision and grid-verification report](precision-and-horizontal-verification.md)
documents the separate opt-in float64 CPU solver. All 32 float64 cases pass the
common residual/stability gate from zero, including the old/new failed tower
references; all 16 declared tighter cases pass, with 25 tighter passes overall.
The default float32 implementation and archived failures remain unchanged.
The report separates accepted-solve evidence from lateral/horizontal comparison
budgets, pointwise near-wall effects and the remaining joint-scope requirement.

The [joint extent/resolution report](joint-grid-verification.md) covers the
160/240 m domains at 1/0.5 m horizontal spacing, both frozen z families and both
pedestrian heights. It documents the configurable study allocation ceiling,
independent checkpoint reuse, mandatory near-wall checks and provenance/cost
audit. Focused Python checks pass 83 tests; serial/OpenMP Release and sanitizer
CTest pass 11/14 checks respectively. Both rebuilt wheels pass isolated smoke
tests. Timing measurements retain the qualification for host sleep/wake
interruptions.
The completed matrices accept all 16 new cases and agree on all 64 comparison
decisions across backends. Finer-grid lateral controls pass; added near-wall
checks fail 13/16 horizontal planes per backend, so preset selection remains gated.

The subsequent [near-wall diagnosis](near-wall-validation.md) completes 40
diagnostic cases and independently checks 189,000 raw component averages.
Both sampling methods retain the near-wall failure; source reconstruction
identifies a sidewall initialization discontinuity at one affected point.
The sampler remains unchanged. A bounded C2c vertical-discretization pilot
can proceed with an explicit horizontal-sensitivity limitation; full comfort
qualification remains pending. The focused suite passes 93 tests, and the
saved-data audit reproduces without solver binaries or a build tree.

The [C2c generated-grid pilot](generated-grid-pilot.md) is complete. It uses
the actual 92-layer policy at x/y=0.5 m, retaining both heights and all fixed
checks. All four CPU cases and six full-region comparisons per backend pass,
including the generated-grid lateral control, with 28.125% fewer cells than
uniform 0.5 m layers. Maximum mandatory local vertical change is 0.902% and
maximum CPU vector difference is 2.39e-8 of Uref. The focused checks total 103
passes, and the complete saved-data audit reproduces without worker binaries.
Repeated host sleep is recorded and disqualifies runtime-ratio claims. Bounded
vertical-refinement/centre-alignment validation follows below; preset selection
and full comfort qualification remain pending.

The [bounded refinement/alignment assessment](vertical-refinement.md) is complete:
three new solves pass, while the 368-layer grid exhausts its certification cap.
Accepted base-to-184 comparisons fail added local checks by 13.2–18.3%, despite
passing aggregate and original near-wall checks. These points are 7 m from walls,
so the diagnostic setback retains the failure. A source reconstruction matches
16 initialized checks and identifies a 0.4-to-1 profile-factor jump at an upwind
ellipse boundary. Initial responses are non-monotonic; centre alignment alone
does not resolve the sensitivity. The alignment control agrees exactly across
CPU backends on the final lattice. Fifteen unique executions and all failures
are audited; 115 focused tests pass. The proposed higher-budget
reference was subsequently [stopped for runtime review](finest-reference.md).
No new accepted finest result exists. Hours-long fixed-sweep escalation conflicts
with fast wind approximations; the next step is bounded production-backend
runtime/accuracy assessment. Grid planning takes milliseconds; two ordinary
500-iteration serial API diagnostics take 26–28 s for 9.42 million cells but
remain nonconverged. These timing diagnostics do not qualify comfort accuracy.

The subsequent [bounded practical-grid comparison](data/practical-vertical-grid/summary.json)
uses the default float32 arithmetic with OpenMP and four requested threads.
At fixed 0.5 m x/y, the automatic 92-layer and uniform 128-layer grids finish
2000-iteration API calls in 20.92 and 27.05 s, respectively. Both pass predeclared
candidate sampled iterative-error checks against accepted same-grid references:
p95 speed error below 0.00763 m/s and all five mandatory relative errors below
0.42% at both heights. Their 1000-iteration cases fail a 2% local check despite
passing percentile checks. All four finish within 30 s worker deadlines.
These observations cover one tower/wind and have one timing repetition per case.

The expanded automatic-versus-uniform spatial checks still fail at two mandatory
locations by 20.9–29.7% (about 0.193–0.202 m/s), including in the accepted
reference fields. All cheap runs remain nonconverged by the legacy tolerance
and fail the old residual bounds. Sampled iterative agreement therefore does
not qualify comfort accuracy or select an automatic preset. The
[frozen protocol](data/practical-vertical-grid/protocol.json) and
[data-only audit](data/practical-vertical-grid/audit.json) retain source and
reference identities, raw samples, all failures, memory and timing scopes.
The numerical-scope review is now closed under the user's restricted release
scope: explicit grids and physical-height sampling are supported as implemented,
and automatic generation stays experimental. Broader geometry/wind/roof studies,
automatic comfort presets and physical/grid-independence qualification are
follow-ups. Existing failed references, spatial checks and stopped attempts
retain their original decisions; no new reference is inferred from closure.

### Dataset integration under the experimental scope

The B2 adapter accepts serializable grid mode, pedestrian target, growth rate,
solver precision and slice sampling options. Uniform fields remain the default.
Automatic grids are opt-in slice products and carry an experimental marker in
discovery, health, warnings and provenance, retaining
`policy_status="prototype_unvalidated"`. Full automatic `VolumeGrid` output,
linear field products and linear x/y slices fail before fetching a city.
An explicit `slice_height` applies the existing z-axis override first.

Linear horizontal slices use `WindResult.sample` to interpolate components at
the requested physical height, followed by nearest x/y display sampling.
Coordinates stay at that height; samples outside the native centre support
remain invalid without extrapolation. Every slice now includes boolean `valid`;
invalid vectors and speeds are NaN. Nearest categorical flags are retained
independently, including when a different interpolation contributor is solid.
Context health includes conservative residuals, precision and sample counts;
request parameters retain every new option for identity and provenance.

Tests cover nonuniform manufactured fields, exact-centre behavior, opposite
components, solid/nonfinite contributors, both centre-range endpoints, global
coordinates, all nearest slice axes, unsupported requests before fetch,
serialized identity, and real dataset/direct-solver parity at 1.5 and 1.75 m.
Float64 dispatch and existing default uniform output are also exercised. The
existing user change registering the dataset on package import is preserved;
the old explicit-import-only test now follows that behavior.

Final release checks on 2026-10-28 pass **713 Python tests, with 2 skipped**, using
the rebuilt installed OpenMP wheel, and **all 14 native CTest checks**. Dataset
tests fetch fixture cities through a mocked provider and execute real native
solves; live city-provider networking was not exercised. The wheel and source
distribution pass artifact checks, including the dataset modules, integration
tests, examples, closure documentation and saved numerical evidence. Default
pytest discovery is restricted to `tests/` so frozen historical test copies
remain audit inputs rather than duplicate executable suites.

The canonical flat and one-building cases live in `tests/fixtures/cases.py`.
Committed NumPy arrays and JSON provenance were produced by pristine QES 2.3.1
at `dced7ec571487be7538eca17bfc25bb3262fb6d0`, Apple Clang 17, arm64, Release
`-O3 -DNDEBUG`. Expected physical dimensions are 40 x 30 x 20 cells at 2 m.
Solver iteration counts are recorded as provenance, not asserted as physical
acceptance criteria.

## Numerical parity and physical checks

- All centre coordinates and classifications are exact comparisons. Serial
  velocities are exact on the recorded compiler family/major version,
  architecture and Release mode; elsewhere, including the OpenMP red-black
  solver, `rtol=1e-5`, `atol=2e-5 m/s` permits float32/libm/SOR ordering and
  rounding differences. Metadata identifies the actual native compiler and backend.
  Cross-platform thresholds require successful CI evidence, not only a local
  assertion policy. The reference jobs also compare pristine and patched
  executables **exactly on the same host** before comparing committed arrays.
- Analytic flat logarithmic profiles are checked at every physical cell for
  all four meteorological cardinal winds and two roughness lengths. Separate
  tests check finite values, zero calm flow, concave simple footprints,
  rectangular solid occupancy and zero velocity in solid cells.
- Native `check_physics` uses the six staggered faces and QES's wall/open-face
  coefficients. Net volumetric flux divided by cell volume has units s^-1.
  It never differentiates cell-centred averages or treats multiplier change
  as divergence. It excludes solid cells and prescribed lateral boundary
  cells. A deliberate perturbation of one face verifies that the check fails
  for a broken field.

For the one-building fixture, initial interior RMS divergence is about
`9.68621e-2 s^-1`. After solving, maximum interior divergence is
`4.02331e-6 s^-1`, RMS `2.42600e-7 s^-1` on the reference host. Bounds are
`max < 1e-5 s^-1`, `RMS < 1e-6 s^-1`, with at least a thousand-fold RMS
reduction. Flat-flow flux is exactly zero. These bounds are independent of the
solver's multiplier-change tolerance.

### Preserved QES top-boundary limitation

QES 2.3.1 corrects vertical face velocities only below a prescribed upper band.
The upper face of the last solved band remains uncorrected. That band has
maximum divergence about `1.52191e-2 s^-1` in both the pristine reference and
the embedding build. The flux test reports it separately and guards against
regression (`< 1.6e-2 s^-1`); it is **not** included in the interior bound above.
The highest physical band and lateral prescribed boundaries are also not
claimed to satisfy an interior Poisson solve. All physical cells remain in the
public output, matching the reference writer. Changing this numerical boundary
condition would change the baseline and is outside this embedding milestone.

```sh
build/native/check_physics --report
```

## OpenMP validation

Fresh builds require OpenMP by default. Configure with
`-DDTCC_QES_BUILD_TESTS=ON` to run the native safety, lifecycle and flux checks
with OpenMP; override a previously cached mode with `-DDTCC_QES_OPENMP=ON`.
On macOS, install `libomp`; standard Homebrew locations are discovered
automatically. Custom locations can use `-DOpenMP_ROOT="$(brew --prefix libomp)"`.
The existing native tests use two threads. Additional `openmp_1_threads`,
`openmp_2_threads` and `openmp_4_threads` tests verify real team creation,
factory selection, exact repeatability of velocities and convergence across
thread counts, and agreement with the serial solver at the tolerances above.
They include a tall building spanning thread slabs and check all faces adjoining
solid cells. Non-finite iteration failures are reported after leaving the
parallel region, so they remain catchable native/Python exceptions.

Explicit serial builds remain supported with `-DDTCC_QES_OPENMP=OFF`. Since S2,
their default order is red/black too. Cross-build bitwise checks now compare the
same trajectory; explicit lexicographic native controls and historical study
ordering remain available. The [S2 report](solver-control-s2.md) records the
deliberate serial change separately from arithmetic-preserving storage changes.
`tests/test_openmp_configuration.py` checks the default requirement and explicit
fallback modes. `AUTO` can be checked without an OpenMP installation by configuring with
`-DDTCC_QES_OPENMP=AUTO -DCMAKE_DISABLE_FIND_PACKAGE_OpenMP=ON`; the same missing
dependency must fail configuration with the default mode or explicit `ON`.

Local default-build verification on macOS arm64 / Apple Clang 17: a fresh
Release configuration and wheel build, with no OpenMP option or package-root
override, discover Homebrew `libomp` and select the OpenMP solver. The installed
wheel reports `openmp_enabled=True` and `cpu_backend="OpenMP CPU"`, and its
extension links `libomp.dylib`. All 14 native checks pass, including actual
1/2/4-thread teams; the focused build, runner, safety, physics, precision,
vertical-grid, preview, automatic-grid, wind and sampling Python checks pass
374 tests with two platform-specific reference skips. The native symbol audit
also passes. This verifies backend selection and correctness checks; it does
not establish a runtime speedup.

## Geometry and result ordering

Public tests compare fixtures after a `(1e9, -2e9, 100)` translation, verify
unchanged vertices/attributes/transforms/caches, independent results, rejected
inputs, explicit flattening and convergence policy. Tests bypass Python
validation with malformed arrays to exercise native exceptions and recovery.

DTCC's current `VolumeGrid.coordinates()` uses NumPy meshgrid `xy` indexing,
so fields use **y, x, z-fastest** ordering. The session's accepted convention is
isolated in `WindResult.to_dtcc()` and documented here; it is not a claim that
upstream DTCC has adopted a new public ordering standard. Unequal axis lengths
and axis-encoded distinguishable values check the mapping against DTCC grid
coordinates. Vector fields are `(N, 3)`, scalar fields `(N,)`, with cell
association, local bounds and a global translation/CRS Transform.

## Native safety

Release builds audit both complete QES core archives and all bridge objects,
excluding nanobind objects. The allowlist is empty. Deliberately failing
GDAL/NetCDF headers are first in the include search path in test builds.
Subprocess tests capture stdout/stderr through native shutdown, including
successful runs, invalid inputs, non-convergence and supported native failures.
DTCC log handlers are disabled or captured, independently of descriptor checks.

Debug ASan/UBSan retains invariant assertions; its assertion hooks intentionally
do not satisfy the Release symbol audit. On macOS:

```sh
cmake -S . -B build/sanitizers -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_ENABLE_SANITIZERS=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build/sanitizers --target check_noio check_safety check_runner check_physics --parallel 8
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir build/sanitizers --output-on-failure
leaks --atExit -- build/native/check_runner
```

Linux CI uses `ASAN_OPTIONS=detect_leaks=1:halt_on_error=1` instead; Apple's
LeakSanitizer is unavailable, so `leaks` supplies the local leak check. Private
test builds retain nanobind shutdown leak warnings. Build a development wheel
with `-Ccmake.define.DTCC_QES_BUILD_TESTS=ON` before running Python tests.

## Distribution checks

`tools/check_artifacts.py` verifies license/notices, corresponding QES core
sources/build files, Python sources, tests and the executable example. CI
rebuilds a wheel from the source distribution, checks a clean import, then
installs the locked runtime dependencies and exercises the API and example.
Source distributions deliberately omit optional standalone driver directories;
reference regeneration requires the recursive Git checkout, while rebuilding
the library wheel from the sdist needs only the documented native requirements.

Actual run results and external verification still pending are recorded in
`MILESTONE1_WIP.md`.

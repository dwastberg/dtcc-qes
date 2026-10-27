# Milestone 1 validation

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
checks fail 13/16 horizontal planes per backend, so C2c remains gated.

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

Configure with `-DDTCC_QES_OPENMP=ON -DDTCC_QES_BUILD_TESTS=ON` to run the
native safety, lifecycle and flux checks with OpenMP. On macOS, provide
`-DOpenMP_ROOT="$(brew --prefix libomp)"` after installing `libomp`.
The existing native tests use two threads. Additional `openmp_1_threads`,
`openmp_2_threads` and `openmp_4_threads` tests verify real team creation,
factory selection, exact repeatability of velocities and convergence across
thread counts, and agreement with the serial solver at the tolerances above.
They include a tall building spanning thread slabs and check all faces adjoining
solid cells. Non-finite iteration failures are reported after leaving the
parallel region, so they remain catchable native/Python exceptions.

CI builds both serial and OpenMP variants on Linux and macOS, including wheels,
the full Python suite, native symbol audits and ASan/UBSan checks. `AUTO` can be
checked without an OpenMP installation by configuring with
`-DDTCC_QES_OPENMP=AUTO -DCMAKE_DISABLE_FIND_PACKAGE_OpenMP=ON`; the same missing
dependency must fail configuration when `DTCC_QES_OPENMP=ON`.

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

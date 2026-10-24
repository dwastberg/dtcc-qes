# Milestone 1 validation

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

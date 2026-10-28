# Vertical-grid Stage 0: solver correctness

Implemented on 2026-10-26. This is the first delivery stage of
`DYNAMIC_VERTICAL_GRID.md`; no public nonuniform-grid API has been added.
The embedded QES fix is local commit `046eb799` on `dtcc-embed`, following
`71f8dcb2`. CUDA expressions were updated consistently but were not built or
executed on this Apple arm64 host. No upstream issue or remote push was made.

The RHS multiplied vertical coefficients by both the cell thickness and the
distance between centres, cancelling the required inverse thickness. Removing
only the thickness factor makes the RHS agree with conservative vertical
divergence and the existing velocity correction. Both CPU backends and the
three CUDA variants have the correction. `Solver_CPU.cpp` and
`Solver_CPU_RB.cpp` explain why the centre-distance factor remains.

The bridge now measures conservative six-face flux divided by physical volume,
with volume-weighted RMS and maximum divergence. It excludes solid and
prescribed lateral cells. For physical layer count `nz`, interior indices are
`1 <= k < nz - 1`; `k == nz - 1` is the separately reported prescribed top
band. The highest physical layer `k == nz` is unassessed. The loop never reads
`dz_array[nz + 1]`. Python reports `None` for a region with no contributing
cells and exposes its count. Metadata and diagnostic docstrings state the
coverage; the multiplier stopping rule is unchanged.

Measurements below use Apple Clang 17, Apple arm64, Release `-O3 -DNDEBUG`,
5 m/s reference wind at 10 m for the canyon, and default building
parameterizations. The native test is `tests/native/check_physics.cpp`.

## Injection reproduction

An obstacle-free 24 × 24 × 16-cell domain has a calm initial field. Inject
`w0=0.1 m/s` at native face `(12, 12, 6)`. Use multiplier tolerance `2e-7`
and a maximum of 20,000 iterations. Each row uses equal x/y/z spacing.
Maximum divergence below excludes the prescribed top band.

| Cell spacing | Original serial RHS | Corrected serial | Corrected OpenMP, 2 threads |
| --- | --- | --- | --- |
| 1 m | 2.8915e-7 s^-1 | 2.89155e-7 s^-1 | 2.72237e-7 s^-1 |
| 2 m | 0.05 s^-1 | 7.01771e-8 s^-1 | 5.70451e-8 s^-1 |
| 4 m | 0.075 s^-1 | 1.27989e-8 s^-1 | 1.46279e-8 s^-1 |

All corrected injection and horizontal-control cases meet the absolute bound
`max < 1e-6 s^-1`. Linking the permanent test against the original serial
`Solver_CPU.cpp` fails with `Solver failed to remove injected divergence`.
These are residuals at the stated stopping tolerance, not universal precision
floors. The top-band residual is separately measured, not hidden in this norm.

## Canyon and iterative accuracy

The domain is 120 × 80 × 50 m at 2 m spacing. Buildings are rectangles
`[30,40] × [20,60]` and `[52,62] × [20,60]`, both 15 m tall. Wind comes from
270 degrees. The input roughness length is 0.1 m. The gap is 12 m.

Each solve restarts lambda from zero with the same initial field. A tolerance
of float32 epsilon prevents early exit on this specific case; the test asserts
that all requested iterations were actually performed. It does not add a new
public stopping rule. Velocity comparisons use all interior fluid samples at
the first cell centre, **1 m above ground**, with components averaged from
their staggered faces. The reported street speed is the mean horizontal speed
inside the gap; it is not a 1.5 m comfort result.

| Backend | Iterations | Interior maximum (s^-1) | Volume-weighted RMS (s^-1) | Multiplier change | Maximum normalized vector change from preceding checkpoint |
| --- | --- | --- | --- | --- | --- |
| Serial | 1,000 | 2.32756e-5 | 1.19079e-6 | 6.10352e-5 | Initial checkpoint |
| Serial | 2,000 | 2.12938e-5 | 1.22696e-6 | 5.34058e-5 | 1.50789e-6 |
| Serial | 4,000 | 1.90735e-5 | 1.21252e-6 | 5.34058e-5 | 1.77137e-6 |
| OpenMP, 2 threads | 1,000 | 1.66893e-5 | 1.21856e-6 | 4.95911e-5 | Initial checkpoint |
| OpenMP, 2 threads | 2,000 | 1.94616e-5 | 1.20590e-6 | 4.57764e-5 | 1.50487e-6 |
| OpenMP, 2 threads | 4,000 | 1.91622e-5 | 1.21466e-6 | 5.34058e-5 | 1.38201e-6 |

Normalize divergence by `Hmax/Uref = 15/5 = 3 s`, and vector changes by
`Uref=5 m/s`. Every checkpoint meets the plan's dimensionless maximum bound
`1e-3` and RMS bound `1e-4`, and also the ten-times tighter residual targets
on this case. Both successive velocity comparisons meet maximum `1e-3` and
95th-percentile `5e-4`; the largest observed 95th-percentile change is
`5.64201e-7`. Both backends give approximately 1.31190 m/s mean horizontal
speed in the gap and pass the cross-backend velocity comparison.

All six checkpoints report `converged=False` because multiplier changes exceed
the tolerance. Residual control plus velocity stability establishes the stated
numerical accuracy independently. This supports retaining the legacy flag's
meaning while exposing separate physical residual diagnostics.

The prescribed top-band maximum is approximately **0.1221 s^-1**, much larger
than the interior residual. Stage 0 does not fix that boundary condition.
Domain-height sensitivity remains required before interpreting this canyon
as physically validated or using it to select automatic layer growth.

## Regression and diagnostic coverage

- Existing flat and one-building reference arrays are compared without
  regenerating them. Serial velocity comparisons remain exact on this reference
  toolchain; OpenMP uses the established cross-backend tolerance.
- An independent manufactured `w(z)=z^2` field with known open face areas and
  test-assembled unequal layers checks maximum, volume-weighted RMS and band
  counts. It does not reuse production coefficient recovery as its oracle.
- Smallest allowed domains, zero assessed fluid cells, nonfinite assessed
  faces, a nonfinite unassessed-top value and deliberate face perturbations
  exercise coverage and bounds handling.
- Serial, OpenMP and ASan/UBSan native suites pass. OpenMP team tests cover
  1, 2 and 4 threads; the canyon comparison uses 2 threads. The native no-I/O
  symbol audit passes.
- The 233 other Python tests pass with each of the serial and OpenMP extensions;
  the known registration mismatch below is explicitly deselected in those runs.
- Wheel and source-distribution artifact checks pass, including the new
  diagnostic sources. A wheel rebuilt from the sdist passes an isolated import,
  a flat-wind solve, diagnostic/count assertions and the recorded revision check.

At the Stage 0 checkpoint, the full Python suite had one unrelated failure:
`test_datasets.py::test_explicit_import_registration` expects importing
`dtcc_qes` not to register `qes_wind`, whereas the existing tracked
`src/dtcc_qes/__init__.py` already imports `dtcc_qes.datasets`. All other
233 tests passed. That package/test contract mismatch predates Stage 0.
The 2026-10-28 turbulence worktree review resolved it by preserving the
user-committed automatic registration and updating the stale test and README.
`test_package_import_registers_dataset_once` now verifies registration on
package import and idempotence across subsequent imports and package reload.

## Reproduce

Use the existing development environment and build dependencies. Commands from
the repository root:

```sh
cmake -S . -B build/extension -DPython_EXECUTABLE=.venv/bin/python -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_OPENMP=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/extension --parallel 8
ctest --test-dir build/extension --output-on-failure
build/extension/check_physics --report
cmake --build build/extension --target check_native_symbols

cmake -S . -B build/openmp -DPython_EXECUTABLE=.venv/bin/python -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_OPENMP=ON -DOpenMP_ROOT=/opt/homebrew/opt/libomp -DCMAKE_BUILD_TYPE=Release
cmake --build build/openmp --parallel 8
ctest --test-dir build/openmp --output-on-failure
OMP_NUM_THREADS=2 OMP_DYNAMIC=FALSE build/openmp/check_physics --report

cmake -S . -B build/sanitizers -DPython_EXECUTABLE=.venv/bin/python -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_OPENMP=OFF -DDTCC_QES_ENABLE_SANITIZERS=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build/sanitizers --target check_physics check_runner check_safety check_noio --parallel 8
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir build/sanitizers --output-on-failure
```

Install the rebuilt extension into the development environment before running
the Python suite; then use `.venv/bin/python -m pytest tests -q`.
To reproduce the passing subset, append
`-k 'not test_explicit_import_registration'`; do not interpret that exclusion as
a passing full suite. For the OpenMP extension, use `OMP_NUM_THREADS=2` and
`OMP_DYNAMIC=FALSE`.

Artifact checks can use system Make without installing the optional Ninja
frontend:

```sh
CMAKE_GENERATOR='Unix Makefiles' CMAKE_BUILD_PARALLEL_LEVEL=8 .venv/bin/python -m build --no-isolation --outdir build/stage0-artifacts -Ccmake.define.DTCC_QES_OPENMP=OFF
.venv/bin/python tools/check_artifacts.py build/stage0-artifacts
```

The sanitizer suite took about 139 seconds on this host, with the canyon
check accounting for about 104 seconds. Do not assign it a 60-second test
timeout without separating or reducing the validated checkpoint workload.

## Consequences for the remaining plan

Proceed next with Stage A's validated explicit-grid construction, retaining the
separate sampling, automatic-grid and cost-study stages. Stage 0 establishes
the uniform-grid RHS fix and diagnostics, not the performance of stretched
solves or an optimal aspect ratio. The old ad hoc cost table remains withdrawn.
Keep the common residual/velocity gate and require top-boundary/domain-height
sensitivity before selecting an automatic preset. The absolute injection
bound and empty-region policy now have executable coverage. No subsequent
delivery stage has been implemented here.

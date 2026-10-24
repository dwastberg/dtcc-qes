# Milestone 1: Work In Progress Report

This document records the current implementation status, findings, and next steps for **Milestone 1: Run a DTCC city through QES-Winds**.

---

## 1. Project Decisions & Scope Alignment

Based on the interactive alignment:
- **Submodule branch**: All QES fork modifications are developed on a local branch named `dtcc-embed` in `QES-Public` (remote: `dwastberg/QES-Public`), leaving `main` clean and tracking upstream.
- **Commit strategy**: One atomic commit per completed step in the outer `dtcc-qes` repository. Existing `.idea/` workspace files remain untouched.
- **DTCC `VolumeGrid` ordering**: `to_dtcc()` will match `VolumeGrid.coordinates()` current meshgrid `'xy'` indexing convention ($y$, then $x$, with $z$ fastest), isolated and documented so it can be updated if the DTCC Core maintainers establish an alternate standard.
- **Current sprint focus**: Steps 1–7 are implemented and locally verified. Remote CI execution and submission of the prepared upstream license report remain external follow-ups.

---

## 2. Step 1: Capture the Reference Baseline (Completed)

### Implementation
- **Case Definitions (`tests/fixtures/cases.py`)**:
  - Defined two canonical test cases using frozen dataclasses:
    1. `FLAT`: $40 \times 30 \times 20$ physical grid cells at $2.0\,\text{m}$ resolution, flat terrain, neutral logarithmic wind profile ($U=5.0\,\text{m/s}$ at $10.0\,\text{m}$, meteorological direction $270^\circ$, $z_0=0.1\,\text{m}$).
    2. `ONE_BUILDING`: The same domain and wind profile, plus a single $10\,\text{m} \times 10\,\text{m} \times 8\,\text{m}$ rectangular building at the center ($x \in [30, 40], y \in [25, 35]$).
  - Fixed simulation parameters: serial CPU solver (`-s 1`), `logLawFlag = 0`, tolerance $10^{-5}$, max iterations $500$.
- **Convergence Verification**:
  - Experiments with the baseline QES solver demonstrated that building height $8.0\,\text{m}$ reaches tolerance $10^{-5}$ in **162 iterations** (residual $9.537 \times 10^{-6}$), providing an ideal non-trivial reference case. The flat case converges in **1 iteration**.
- **Automated Generator & Verifier (`tools/make_reference.py`)**:
  - Automatically exports pristine QES 2.3.1 (commit `dced7ec571487be7538eca17bfc25bb3262fb6d0`) from `QES-Public` via `git archive` to ensure zero contamination from local edits.
  - Dynamically detects the NetCDF C++ library (`libnetcdf-cxx4.dylib` / `libnetcdf_c++4`) using `ncxx4-config` and `pkg-config`, avoiding machine-specific paths in CMake.
  - Generates exact QES XML configurations and executes the standalone `qesWinds` binary.
  - Extracts cell-centered variables ($x, y, z, u, v, w, \text{icell}$) from `_windsOut.nc` and staggered face variables ($x_{\text{face}}, y_{\text{face}}, z_{\text{face}}, u_{\text{face}}, v_{\text{face}}, w_{\text{face}}, \text{icellflag}$) from `_windsWk.nc`.
  - Saves compressed NumPy archives (`flat.npz`, `one_building.npz`) and provenance metadata JSON (`flat.json`, `one_building.json`) recording compiler, flags, machine architecture, and convergence metrics.
  - Includes `--check` mode to verify exact array equality against committed references.
- **Packaging & Environment**:
  - Added `netCDF4` to `dependency-groups.reference` in `pyproject.toml` so library runtime/build dependencies remain clean.
- **Git Commit**:
  - Outer repository: commit `7861309` (*"Capture QES-Winds reference baseline (milestone 1, step 1)"*).

---

## 3. Step 2: Establish the Build and I/O-free QES Core (Completed)

### Package and extension

- Replaced the empty `dtcc-qes/` scaffold with `src/dtcc_qes/` and a private
  nanobind module, `dtcc_qes._qes`.
- Switched to `scikit-build-core`; nanobind is a build requirement only.
  Runtime dependencies remain `dtcc-core` and `numpy`, and Python remains
  `>=3.13`. The DTCC revision in `uv.lock` remains unchanged.
- Added the GPL-3.0-only metadata, root `LICENSE`, QES license and attribution
  `NOTICE`. Wheels contain all three license/notice files. Source distributions
  include the QES sources, CMake modules and recorded QES revision.
- Added top-level CMake for C++17, static QES linkage, position-independent code
  and `NDEBUG`. Bindings include no QES headers; the separate audited
  `qesbridge` object contains the small native build check.
- `_qes.qes_version`, `_qes.qes_revision`, `_qes.io_enabled`, and the private
  `_qes._core_grid_shape()` verify the build. The wind runner and public API
  belong to later steps and have not been implemented.

### QES fork (`dtcc-embed`)

- Added `QES_ENABLE_IO` (default `ON`), explicit CUDA/OptiX opt-ins, and options
  for executables, examples, plume, fire and documentation. The extension forces
  I/O, OpenMP, CUDA and the standalone modules off.
- Replaced global include/link settings and forced cache updates with scoped
  target dependencies. CPack, install rules, examples and upstream tests are
  guarded by `PROJECT_IS_TOP_LEVEL`. Source/build paths are relative to QES.
- Split `qesutil` / `qesutilio` and `qeswindscore` / `qeswindsio`. XML file
  parsing, path resolution, NetCDF/GDAL readers and writers, shapefile handling,
  DEM handling, WRF and HRRR input live in the I/O targets.
- Moved mixed initialization and loading methods to `*_io.cpp` files; the
  corresponding `*_noio.cpp` implementations reject I/O operations with
  `qes::UnsupportedFeature`. Core headers use forward declarations for I/O
  types. Directly constructed file-backed configurations are also rejected.
- Removed unused NetCDF includes from profiler and mixing-length headers.
  `SimulationParameters::DTE_mesh` now defaults to null so the I/O rejection
  check can safely inspect a default-constructed input.
- Kept numeric algorithms unchanged. Adapted the previously uncompiled WRF
  writer's old `ptime` signature to the current `QEStime` base interface.
- The fork now discovers both `netcdf_c++4` and `netcdf-cxx4` without hints.
  Corrected the fork's conflicting CMake/CPack MIT labels to GPL-3.0-only.
  Filing a report in the upstream repository remains outstanding; no external
  issue or message has been posted.

### Verification

Verified locally on macOS arm64 with Apple Clang 17 and Python 3.13:

- Pristine QES regeneration/check: both committed references match exactly.
- Refactored `qesWinds` with I/O enabled: **all arrays, classifications,
  coordinates and solver summaries match the references exactly**, including
  the flat case (1 iteration) and one-building case (162 iterations).
- The default standalone build also succeeds, including `qesWinds`, `qes`,
  `qesPlume`, `qesFire`, their libraries and the existing example.
- Both core archives and the bridge object pass the **file I/O** and **I/O
  library** categories of `tools/check_native_symbols.py`. No allowlist is
  needed. The complete audit remains a step 3 requirement.
- The native `check_noio` test force-links every core object, verifies numeric
  grid construction and checks rejection of file-backed inputs.
- With native tests enabled, CMake inserts deliberately failing GDAL/NetCDF
  headers ahead of system headers. The extension and complete core still build.
  Compiler dependency files confirm that none of those I/O headers or the
  QES file-reader headers enters the 50 core translation units.
- **22 Python tests pass**, covering the extension and Mach-O/ELF audit symbol
  classification. The native CTest passes separately.
- Built a wheel, installed/imported it in a fresh virtual environment without
  runtime dependencies, built an sdist, and rebuilt a wheel from that sdist.
  The installed extension links only libc++ and libSystem on macOS.
- Added `.github/workflows/native-build.yml` to build, audit, test and package
  on a Linux container with Boost headers and no GDAL/NetCDF development
  packages. That remote CI job has not been run from this local session.

Useful commands (with the build tools available in the active environment):

```sh
uv sync --group dev --group reference
uv run --group reference tools/make_reference.py --check
uv run --group reference tools/make_reference.py --qes-source QES-Public --check
uv pip install --python .venv/bin/python scikit-build-core nanobind
cmake -S . -B build/extension -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/extension --parallel 8
cmake --build build/extension --target check_native_symbols
ctest --test-dir build/extension --output-on-failure
uv run --group dev python -m pytest -q tests/test_build.py
uv run --group dev python -m build
```

The explicit build-tool installation supports direct CMake checks. Isolated
wheel builds install those tools automatically from `[build-system].requires`.

QES fork commit: `47645fa0` (on `dtcc-embed`).

## 4. Step 3: Make the Supported QES Path Safe to Embed (Completed)

### Implementation and ownership decisions

- Added `qes::log` with `debug`, `info`, `warning` and `error` levels, a
  replaceable handler and an RAII handler scope. The default handler discards
  messages. Callbacks and message destruction cannot let diagnostic exceptions
  escape. Formatting uses `vsnprintf` into memory and never writes to stdio.
- Converted the CPU sources and their headers to this sink, including the I/O
  sources used by standalone programs. The separate `qesutilio` console handler
  is installed by each standalone entry point. Core progress bars and carriage
  return updates were removed; time-step announcements remain ordinary messages.
- Added `qes::InputError`, `qes::RuntimeError` and `qes::UnsupportedFeature`.
  Replaced CPU-source `exit()` calls with exceptions. `QESout::error()` throws
  without logging the error a second time. Standalone entry points catch errors,
  report them through the console handler and return `EXIT_FAILURE`.
- Added checks for missing/null sensors, empty or inconsistent time series,
  non-finite values, invalid local sensor locations, invalid grid sizes/spacing,
  unavailable solvers and invalid building definitions. The old sensor assertion
  is now an input exception, checked before the first sensor is indexed.
- Default-initialized parsing-dependent input and building state. The supported
  default solver tolerance is now `1e-5`; invalid tolerances below float epsilon
  are rejected. The fixture inputs and numerical operations are unchanged.
- `WINDSGeneralData` uniquely owns its internally created wind profiler, wall,
  canopy and shapefile-created buildings. Its public building list continues to
  borrow caller-supplied buildings. Constructor failure releases the objects
  already allocated.
- `WINDSInputData` and its nested raw-pointer lists remain **borrowed views** for
  in-memory inputs. The native test fixture owns every input with `unique_ptr`;
  the future runner must use the same contract and destroy wind data before its
  inputs. No implicit deletion or ownership transfer of caller geometry was added.
  General ownership repair of the optional XML/WRF/terrain paths is outside the
  supported in-memory path.
- Added a virtual `Solver` destructor and structured `SolveDiagnostics` from
  `solve()`: iterations, maximum Lagrange multiplier change, effective tolerance
  and convergence. Non-convergence is returned explicitly; non-finite numerical
  changes throw. The standalone drivers print the historical reference-tool
  summary from this structure, outside the core.
- Release builds now require the **full** symbol audit. Debug/sanitizer builds
  retain internal assertions. Distributable builds disable nanobind leak warnings;
  development builds with native tests keep them enabled.

### Verification

- Full symbol audit passes for both core archives and the bridge object, with
  no allowlist entries: no termination, console, file I/O or I/O-library symbols.
- **Five native CTests pass**: I/O rejection, repeated successful solves, failure
  unwinding, non-convergence and diagnostic handlers. Success checks include
  20 flat preparations/solves and three building runs, the flat logarithmic
  profile, finite results and preservation of borrowed building ownership.
- **27 Python tests pass**, including subprocess checks of stdout/stderr file
  descriptors for successful runs, supported failures, non-convergence and
  diagnostic buffering. Private extension checks cover both native bridge
  validation and a QES `InputError`, followed by another successful call.
- All five native tests pass under **AddressSanitizer and UndefinedBehaviorSanitizer**
  with internal assertions enabled. macOS `leaks --atExit` reports **0 leaks and
  0 leaked bytes** across repeated runs and failure unwinding.
- The full default standalone build succeeds. Both flat and one-building cases
  reproduce all committed arrays and solver summaries **exactly**. A missing
  XML input reports its error once through the console handler and exits with
  status 1 instead of aborting.
- Built and tested the development wheel, then rebuilt the distributable wheel
  from a fresh source-distribution extraction. Both import and propagate native
  input exceptions silently; the packaged QES revision matches `f34034b7`.
- The Linux job now runs the full audit, descriptor-level tests and a separate
  ASan/UBSan build with LeakSanitizer enabled. Remote CI has not been run here.
  CUDA and OpenMP remain deferred and untested; the active CUDA solver signatures
  were kept compatible with the new diagnostics return type.

Focused QES fork commits on `dtcc-embed`:

1. `74817ae4`: silent leveled diagnostics and throwing errors.
2. `d530b4a3`: internal ownership and validation of borrowed inputs.
3. `f34034b7`: solver diagnostics and standalone exception handling.

Additional verification commands:

```sh
cmake --build build/extension --target check_native_symbols
ctest --test-dir build/extension --output-on-failure
uv run --group dev python -m pytest -q tests/test_build.py tests/test_native_safety.py
cmake -S . -B build/sanitizers -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_ENABLE_SANITIZERS=ON -DCMAKE_BUILD_TYPE=Debug
cmake --build build/sanitizers --target check_safety check_noio --parallel 8
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir build/sanitizers --output-on-failure
leaks --atExit -- build/extension/check_safety all
```

The macOS sanitizer command disables LeakSanitizer, which is unavailable there;
`leaks` supplies the local leak check. Linux CI enables LeakSanitizer instead.
The full symbol audit is intended for the Release build; sanitizer/debug builds
intentionally retain assertion-failure references.

## 5. Step 4: Build the Runner and Bindings (Completed)

### Implementation and private contract

- Added plain `GridConfig`, `ModelSettings`, `WindCondition`, `SolverOptions`
  and numeric building arrays in `src/cpp/wind_config.h`. QES types remain
  hidden behind `WindRunner`'s pimpl and never enter the bindings.
- `qes_inputs.cpp` is the single construction and float64-to-float32 conversion
  point for QES simulation, meteorology, sensor, time-series and building
  objects. The sensor defaults to the fixture's `(11, 31)` location and uses
  the fixed `2020-01-01T00:00:00` timestamp. All input owners outlive wind data;
  the solver is destroyed before wind data. The QES fork did not need changes.
- `_qes.WindRunner.prepare(grid, model, vertices, offsets, heights,
  base_heights, ids)` creates fresh owned geometry. Failed preparation preserves
  the previous prepared state. The array contract is CPU NumPy, C contiguous:
  float64 `(N, 2)` vertices, int64 `(B + 1,)` offsets, float64 `(B,)` heights
  and base heights, and int64 `(B,)` IDs. Rings must be closed and clockwise;
  empty geometry uses `(0, 2)` vertices and offsets `[0]`. Read-only arrays
  are supported. The bindings snapshot arrays and config objects with the GIL.
- Native validation checks lengths, offset bounds/ordering, finite values,
  float32 conversion, IDs, ring closure/winding and collapsed edges, grid/index
  limits, sensor position, roof clearance and footprint domain clearance.
  The private grid defaults to a 2,000,000 physical-cell allocation limit and
  accepts 3–10,000 cells in x/y and 2–10,000 in z. Footprints require two cells
  of horizontal clearance, zero base height and a physical cell centre above
  the roof. Full polygon validity and overlap checks belong to Step 5.
- `solve(condition, options)` resets cell flags, applies the wind profile and
  parameterizations, resets solver state, solves, then extracts physical cells.
  It supports subsequent speed, direction, reference-height and solver-option
  changes. Roughness stays fixed at preparation because QES snapshots it there.
  Serial CPU, neutral log law, scalar spacing, flat stair-step geometry,
  zero halos and `logLawFlag=0` remain the supported configuration.
- One process-wide mutex covers preparation, solving and destruction. The GIL
  is released before waiting on that mutex; the mutex is released before the
  GIL is reacquired. `log_sink.cpp` installs/restores a scoped memory buffer
  during native calls and never calls Python. `_logging.py` forwards QES
  info/debug as DEBUG and warnings as WARNING through
  `dtcc_core.common.get_python_logger("dtcc-qes")`, then emits one INFO solve
  summary. Errors reach Python as exceptions without duplicate error records.
- Results are copied into independently owned NumPy arrays: float32 velocity
  `(nz, ny, nx, 3)`, int32 cell flags `(nz, ny, nx)` and float32 centre axes.
  Face averaging follows the visualization writer; the ground ghost and extra
  staggered top layer are omitted consistently. A diagnostics dictionary
  reports iterations, effective tolerance, maximum Lagrange multiplier change
  and convergence; non-convergence remains explicit for the later public API.
  Native input exceptions map to `ValueError`, runtime exceptions to
  `RuntimeError`, and incompatible array buffers to `TypeError`.

### Verification

Verified locally on macOS arm64, Apple Clang 17, Python 3.13:

- Both hand-built fixture configurations reproduce every public coordinate,
  velocity component and classification array **exactly** through the bindings.
  Results own their NumPy storage and survive runner destruction, later solves
  and mutations of the original input arrays/configuration.
- **78 Python tests pass**, including strict buffer requirements, malformed
  offsets and lengths, native validation/failure recovery, repeated solves,
  changed solver tolerance, non-convergence, DTCC log records and descriptor
  silence. A subprocess checks that native solve releases the GIL, then runs
  12 concurrent calls across shared and separate runners without deadlock.
- **Six native CTests pass**. The new runner test covers 12 construction/solve/
  failure/repreparation cycles, concurrent shared/separate runners, independent
  output vectors, diagnostic levels and restoration of the previous log sink.
- All six native tests pass under **ASan and UBSan**, with assertions enabled.
  macOS `leaks --atExit -- build/extension/check_runner` reports **0 leaks and
  0 leaked bytes**.
- The full native symbol audit passes for both archives and all four bridge
  objects, with no allowlist. Poisoned GDAL/NetCDF headers remain enabled in
  the development build.
- Built a development wheel and sdist, rebuilt a distributable wheel from a
  **fresh extraction**, and reran all 78 Python tests against that wheel. The
  fresh source build also passes the complete symbol audit. A separate minimal
  environment imports it and exercises native build checks silently without
  runtime dependencies.
- Linux CI now also installs runtime dependencies exported from the unchanged
  `uv.lock`, tests the array bindings and includes the runner in sanitizer/leak
  checks. Coordinates/classifications remain exact everywhere. Velocity tests
  use exact comparison on macOS arm64 and `rtol=1e-5`, `atol=2e-5 m/s` elsewhere
  to allow float32/compiler/libm rounding differences. Those cross-platform
  thresholds still need confirmation by remote CI; it has not been run here.

Additional commands:

```sh
cmake --build build/extension --parallel 8
cmake --build build/extension --target check_native_symbols
ctest --test-dir build/extension --output-on-failure
.venv/bin/python -m pytest -q
cmake --build build/sanitizers --target check_runner check_safety check_noio --parallel 8
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir build/sanitizers --output-on-failure
leaks --atExit -- build/extension/check_runner
```

## 6. Step 5: City Adapter and Public API (Completed)

### Public contract and decisions

- Added `from dtcc_qes import wind` and
  `wind.run(city, condition, *, grid=GridSpec(), solver=SolverOptions(),
  terrain=None, height_policy="measured")`. The wind condition is required.
  Importing the private extension still does not load runtime dependencies.
- Public option groups are frozen dataclasses. `WindCondition` uses m/s,
  meteorological degrees in `[0, 360)`, reference height `10 m` and roughness
  `0.1 m`. `GridSpec` defaults to `2 m` resolution, `20 m` horizontal padding,
  `20 m` vertical clearance and 2,000,000 physical cells. `SolverOptions`
  defaults to tolerance `1e-5`, 500 iterations and raising on non-convergence.
- Bounds accept a DTCC `Bounds` or a copied six-tuple
  `(xmin, ymin, zmin, xmax, ymax, zmax)` in the global input frame. Lower
  coordinates define the simulation origin. Upper coordinates expand to whole
  cells at the effective float32 resolution. Without bounds, padding is at
  least three cells and the top includes the tallest roof plus clearance and
  the reference height. Empty cities require explicit bounds. Cell counts,
  native dimension/index limits and geometry clearance are checked before
  constructing the native runner.
- `_city.py` reads canonical LOD0 `Surface` objects directly. DTCC's footprint
  helper can select or merge multipart geometry, so it is deliberately avoided.
  Heights come from `measured_height`; `height_policy="allow_estimated"` permits
  `estimated_height` only when the measurement is absent. Invalid measurements
  never fall back to estimates. Errors identify the source building.
- Footprints are checked with Shapely, exact consecutive duplicate vertices are
  removed, rings are closed and winding is made clockwise. Holes, multipart
  geometry, ambiguous LOD0 representations, building parts, nested buildings,
  and overlapping **or touching** footprints are rejected. Attached buildings
  would need an explicit merging policy and remain unsupported. Source IDs
  must be unique nonempty strings; metadata maps them to sequential native IDs.
- A common float64 origin is subtracted before native narrowing. Geometry is
  checked again at float32 precision for collapsed edges, invalid rings and
  newly intersecting/touching footprints. Original geometry, attributes,
  transforms and cached bounds are not changed.
- Coordinate systems must be a shared projected/engineering CRS in metres or
  an unlabelled synthetic metre frame. A city CRS is inherited by undeclared
  descendants; mixed declarations and geographic/non-metre systems are rejected.
  DTCC documents transforms as absolute local-to-global maps: identity inherits
  an enclosing translation, equal repeated translations apply once, and
  conflicting declarations are rejected. Rotation, shear, scale and projective
  transforms are unsupported. Distinct buildings may declare different local
  origins in the same global CRS.
- Without city terrain, consistent LOD0 base elevations define the ground
  plane (absolute tolerance `1e-6 m`). City terrain or inconsistent/nonplanar
  bases require explicit flattening. `terrain="flat"` uses explicit bounds'
  zmin, or the lowest footprint elevation without bounds;
  `FlatTerrain(elevation=...)` chooses an explicit global elevation. Bounds'
  zmin must agree with that plane. Terrain omission, original base ranges,
  flattening and ignored non-building city objects are recorded in metadata.
- `WindResult` exposes owned float32 velocity `(nz, ny, nx, 3)`, centre axes,
  integer cell flags, origin, CRS, effective resolution, metadata and frozen
  `SolveDiagnostics`. `solid_mask` marks QES classes 0 (building) and 2 (terrain),
  excluding air parameterizations. `ConvergenceError` carries diagnostics;
  opting out returns a non-converged result and emits one warning.
  Native state is released before returning results or raising public errors,
  so a retained convergence traceback does not retain the prepared domain.
- `to_dtcc()` returns a uniform `VolumeGrid` with independent cell-associated
  `velocity`, `speed` and `cell_flags` fields. It transposes arrays to y, x,
  z-fastest order to match current `VolumeGrid.coordinates()` meshgrid `xy`
  indexing. Local bounds and a translation/CRS Transform preserve the frame.
  Speed uses float64 arithmetic to avoid overflow while taking a float32 vector
  magnitude. Metadata records requested/effective conditions and domain, model
  defaults, solver options, simplifications and source IDs, QES revision and
  installed DTCC version/VCS revision (when installation metadata provides one).

### Verification

- **157 Python tests pass with warnings treated as errors**, including the
  existing binding checks and 79 new public API/adapter/result checks.
- Both public fixture runs reproduce all reference centre coordinates,
  classifications and velocity components **exactly** on the reference host.
  The same comparisons pass after translating the city and bounds by
  `(1e9, -2e9, 100)`. Automatic domain derivation also preserves results and
  local coordinates under that translation.
- Tests cover measured/estimated height policy, invalid geometry, multipart
  surfaces, holes, parts, duplicate cleanup, winding, overlaps/touching, loss
  of float32 precision, projected/geographic/non-metre and conflicting CRS,
  translation inheritance, rejected transforms, base elevation consistency,
  explicit flattening, effective bounds and allocation limits. Two disjoint
  buildings preserve their source-ID mapping. A calm building case also
  returns finite zero velocity.
- Result checks verify independent arrays/fields, preserved transforms and
  CRS, units, cell associations and solid-mask semantics. Distinguishable
  values on unequal axes verify the DTCC cell order against grid coordinates.
- A subprocess exercises repeated public success, height-validation failures,
  non-convergence, recovery and shutdown, with empty stdout/stderr when DTCC
  logging is disabled. Non-convergence logging is tested separately.
- All **six native CTests** and the complete native symbol audit still pass.
  No C++ or QES fork changes were needed; the native implementation retains
  the sanitizer/leak coverage recorded in Step 4.
- Built the wheel and sdist, then rebuilt and tested the distributable wheel
  from a fresh sdist extraction. The Linux job now runs the complete Python
  suite with locked runtime dependencies. Remote CI has not been run here;
  cross-platform velocity tolerance confirmation remains outstanding.

## 7. Step 6: Physical Validation and Review of Steps 1–5 (Completed Locally)

The audit confirmed the reference generation, I/O-free target split, native
ownership and exceptions, pimpl/array boundary and public city API against the
plan. It also found and corrected these gaps:

- The serial solver treated its initial error sentinel (`1.0`) as convergence
  when tolerance was at least 1. The focused QES commit `398e9a4e` now evaluates
  at least one iteration before accepting convergence. Native/public tests
  exercise this edge case; the default reference operations and results are
  unchanged. The recorded embedding revision is now
  `398e9a4e776575f59f747a7a738048229a9ad166`.
- Explicit upper bounds could snap slightly inward near an integer cell count.
  Counts now always round upward. Unallocatable horizontal padding is rejected
  before overflowing NumPy extent arithmetic.
- Exact-reference selection now checks the actual compiler ID/major version,
  Release build mode and architecture instead of assuming every macOS arm64
  build uses the reference toolchain. Native build provenance is in metadata.
- Reference tooling pins the full pristine commit, disables CUDA discovery,
  checks spacing/coordinates/classifications exactly even with velocity
  tolerances, and supports comparing pristine and patched outputs from a
  separate directory on the same host.

New physical checks cover analytic neutral logarithmic profiles for all four
cardinal winds and two roughness lengths, calm wind, concave simple footprints,
exact rectangular solid occupancy, zero solid velocities, finite results,
repeated calls and preservation of source attributes/transforms/cached bounds.
The existing array-ownership, unequal-axis ordering, native validation,
subprocess silence, GIL release and concurrency checks remain passing.

`check_physics` computes conservative flux from QES's staggered faces and
wall/open-face coefficients, independently of multiplier-change diagnostics.
For the building reference, interior initial RMS divergence `0.0968621 s^-1`
falls to `2.42600e-7 s^-1`, with maximum `4.02331e-6 s^-1`. The assertions are
maximum `< 1e-5 s^-1`, RMS `< 1e-6 s^-1`, and at least a thousand-fold RMS
reduction. Flat flux is exactly zero. Perturbing one face verifies sensitivity.

This validation also identified a **preserved upstream numerical limitation**:
the last solved vertical band has an uncorrected upper staggered face in QES
2.3.1. Both pristine and embedded outputs have about `0.0152191 s^-1` maximum
divergence there. It is reported and regression-tested separately; neither
that band nor prescribed outer boundaries is represented as passing the
interior flux criterion. All physical cells are returned as the baseline does.
Changing the boundary algorithm is outside this embedding milestone.

Local checks after the audit:

- All seven native CTests pass, including staggered flux and failure recovery.
- All seven pass under ASan/UBSan with assertions enabled; macOS `leaks`
  reports **0 leaks and 0 leaked bytes** for repeated runner lifecycle checks.
- The full symbol audit passes for both archives and all four bridge objects,
  with no allowlist entries. Poisoned I/O headers remain active in test builds.
- Rebuilt pristine and patched standalone executables reproduce the committed
  arrays and summaries **exactly**. A separate freshly generated reference
  directory also confirms exact patched/pristine parity. The complete default
  standalone build still succeeds.
- Python checks pass with warnings treated as errors. Final distribution-suite
  counts, example and clean-environment evidence are recorded in Step 7.

## 8. Step 7: Documentation and Reproducibility (Implemented, Locally Verified)

- Added `README.md` with native requirements, locked installation, API/geometry
  conventions, domain defaults, flattening, result/diagnostic semantics, logging,
  validation, packaging, reference regeneration, licensing and deferred scope.
- `examples/single_building.py` constructs a city with one building, solves it
  and returns a georeferenced VolumeGrid without input datasets or QES file I/O.
  Its end-to-end test is part of the suite.
- Added physical/safety/distribution notes in `docs/validation.md` and a
  plan-to-evidence audit in `docs/milestone1-audit.md`. The legacy top-band
  divergence limitation is stated explicitly, not hidden by convergence status.
- Pinned the existing DTCC commit directly in `pyproject.toml` and `uv.lock`;
  it is still `625a8feaff5d0da11d3f078082072e185ffa60a4`. Added nanobind and
  scikit-build-core to the locked development tools so documented direct CMake
  and no-isolation builds work after the standard development install.
- CPU CI now includes macOS and Linux, with the latter verifying that GDAL and
  NetCDF development headers are absent. Jobs audit/test the core, build a test
  wheel from its sdist, install locked runtime dependencies and exercise all
  tests and the example. Development wheels explicitly retain leak warnings.
  Both platforms run native sanitizers; Linux enables LeakSanitizer and macOS
  runs `leaks`. Separate macOS/Linux jobs regenerate pristine references, require
  exact patched/pristine parity on that host and compare committed fixtures.
- `tools/check_artifacts.py` checks GPL-3.0-only metadata, required license and
  QES notice files, the extension/public Python files and corresponding QES
  sources/build files, fixtures, developer tooling, documentation and example.
  Source builds include those files and exclude IDE/build products.
- Built/checked wheel and sdist, then rebuilt a distributable wheel from a fresh
  extraction. A new virtual environment received all **139 locked runtime
  packages** from cache, that rebuilt wheel and no development-environment site
  packages. **All 177 Python tests pass with warnings treated as errors** there,
  and the standalone example produces 24,000 cells with the expected velocity
  shape. Installed QES/DTCC revisions were checked explicitly. Minimal extension
  import without runtime dependencies remains supported and tested separately.
- Final native checks: **seven CTests pass**, the complete symbol audit passes
  without exceptions, and the macOS module links only libc++ and libSystem.
  The seven sanitizer tests and zero-leak result are recorded under Step 6.
- Added a concrete upstream license-metadata issue draft in
  `docs/upstream-license-report.md`; NOTICE identifies its prepared/unsubmitted
  status. No external issue or message was sent.

## 9. Final Status and External Follow-ups

Milestone implementation steps **1–7 are present**, with the full local
end-to-end path, physical checks, safety checks, documentation and installation
verified on macOS arm64 / Apple Clang 17 / Python 3.13. Review corrections and
acceptance mapping are recorded in the final audit document.

Remote acceptance is **not claimed**: the outer checkout has no Git remote and
GitHub CLI has no authenticated host. The new QES fork commit and existing
embedding history must be published before another checkout can fetch the
submodule. After publishing, run the CPU/reference workflow to confirm Linux
execution, cross-platform numerical tolerances and remote macOS/reference jobs.
The prepared licensing report also awaits explicit upstream submission. These
are the only external follow-ups; they are not represented as successful CI or
upstream communication.

The outer repository retains one implementation commit per completed step.
QES changes are committed separately on `dtcc-embed`; its commits must be
available on the fork before remote CI can check out the submodule. Existing
`.idea/` changes are left untouched.

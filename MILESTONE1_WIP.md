# Milestone 1: Work In Progress Report

This document records the current implementation status, findings, and next steps for **Milestone 1: Run a DTCC city through QES-Winds**.

---

## 1. Project Decisions & Scope Alignment

Based on the interactive alignment:
- **Submodule branch**: All QES fork modifications are developed on a local branch named `dtcc-embed` in `QES-Public` (remote: `dwastberg/QES-Public`), leaving `main` clean and tracking upstream.
- **Commit strategy**: One atomic commit per completed step in the outer `dtcc-qes` repository. Existing `.idea/` workspace files remain untouched.
- **DTCC `VolumeGrid` ordering**: `to_dtcc()` will match `VolumeGrid.coordinates()` current meshgrid `'xy'` indexing convention ($y$, then $x$, with $z$ fastest), isolated and documented so it can be updated if the DTCC Core maintainers establish an alternate standard.
- **Current sprint focus**: Execute Step 1 (Reference baseline) and Step 2 (Build & I/O-free QES core).

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

## 4. Stopping Point

Steps **1 and 2 are complete**. Stop here as requested. Step 3 starts with the
native message sink, removal of process termination, ownership cleanup and
structured solver diagnostics. Native console output and legacy termination
paths still exist in the core at this boundary. No public `wind.run()` API is
available yet.

The outer repository retains one implementation commit per completed step.
QES changes are committed separately on `dtcc-embed`; its commit must be
available on the fork before remote CI can check out the submodule. Existing
`.idea/` changes are left untouched.

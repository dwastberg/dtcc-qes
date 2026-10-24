# Milestone 1: Run a DTCC city through QES-Winds

Implement `dtcc_qes.wind.run(city, ...)` so that a synthetic
`dtcc_core.model.City` containing one building can run a QES wind simulation
through nanobind and return validated, georeferenced results in memory.

The first milestone establishes the complete path from DTCC geometry to the
native solver and back to Python. Its reference result must agree with the
existing QES executable for equivalent inputs.

## Scope

Include:

- The QES serial CPU solver, initially on macOS and Linux.
- One steady wind condition, specified by speed, meteorological direction,
  reference height, and roughness length, using a neutral logarithmic profile.
- A uniform grid with a scalar cell size and explicitly flat terrain.
- Simple, hole-free LOD0 building footprints extruded to specified heights.
- A Python `WindResult` containing NumPy arrays, coordinates, classifications,
  configuration metadata, and convergence information.
- Conversion to a DTCC `VolumeGrid` with cell-associated `Field` objects.
- A flat-domain reference case and a one-building reference case.
- A native core that performs no I/O, prints nothing, and never terminates
  the host process, as defined under [Project constraints](#project-constraints).

Defer terrain rasters and meshes, cut cells, detailed roof geometry, vegetation,
turbulence output, multiple wind conditions, OpenMP, CUDA, and concurrent runs.
The `Domain::getDomainSize()` correction belongs to the next milestone.
Public binary-wheel distribution is a later task; this milestone must support
a reproducible local build and installation.

## Project constraints

These are fixed decisions. Each has a verification that runs in CI.

### License

`dtcc-qes` is licensed GPL-3.0-only. QES-Winds is granted under version 3 of
the GPL only ([LICENSE](QES-Public/LICENSE) and the source headers), and the
extension links QES statically, so the distributed package is a combined work
under that license. DTCC Core is MIT-licensed, which is compatible.

- Declare `license = "GPL-3.0-only"` in `pyproject.toml`, add the GPL-3.0 text
  as `LICENSE`, and list `QES-Public/LICENSE` in `license-files`.
- Ship the corresponding source: the sdist includes the QES sources used by the
  build, and result metadata records the QES and DTCC revisions.
- QES's top-level `CMakeLists.txt` and CPack metadata still say MIT. Treat the
  `LICENSE` file and source headers as authoritative and report the
  inconsistency upstream.

### No direct console output from native code

Native code never writes to stdout, stderr, or a terminal. QES diagnostics are
either discarded or captured and logged through DTCC Core logging.

- Patch QES so that `QESout` becomes a leveled message sink (`debug`, `info`,
  `warning`, `error`) with a replaceable handler. Replace every `std::cout`,
  `std::cerr`, `printf`, and `puts` in the sources the extension compiles with
  calls to that sink. A stream-style wrapper (`qes::log::info() << ...`) keeps
  the change mechanical and reviewable.
- The core library's default handler discards messages. The standalone
  executables install a console handler at startup, which preserves their
  command-line behaviour without putting console code in the core library.
- Remove per-iteration progress output (`printProgress`, carriage-return
  updates) from the core instead of logging it. The solver's final summary
  becomes structured diagnostics.
- During each native call the extension installs a handler that buffers
  messages in memory. The handler must not call into Python, because the GIL
  is released. After the call returns and the GIL is reacquired, Python
  forwards the buffer to the `dtcc-qes` logger obtained from
  `dtcc_core.common.get_python_logger`. Forward through that `logging.Logger`,
  not through the callbacks returned by `init_logging`: their `error` and
  `critical` raise `RuntimeError`.
- Forward QES
- informational messages at `DEBUG` and QES warnings at `WARNING`.
  `dtcc-qes` logs its own concise `INFO` summary of each run: grid, building
  count, iterations, and convergence. Native errors arrive as exceptions, not
  log records, so each is reported once.
- Python code in `dtcc-qes` uses DTCC Core logging and never calls `print`.
- Do not redirect file descriptors or replace `std::cout`'s stream buffer.
  Both are process-wide, either miss `printf` or capture unrelated output, and
  behave poorly under Jupyter.
- nanobind leak warnings stay enabled in development and test builds, where
  the silence test turns any leak report into a failure. Distributable builds
  disable them.

Verification: the [native symbol audit](#native-symbol-audit) finds no
references to console streams or stdio output, and a subprocess test checks
that successful runs, invalid inputs, native failures, and non-convergence
leave the process's stdout and stderr file descriptors empty while DTCC logging
is directed away from the console, and that the expected records reach the
`dtcc-qes` logger.

### No reachable process termination

Native code never ends the host process. `src/winds`, `src/util`, and
`src/qes` contain 75 `exit()` calls and 18 `assert()` calls, and
`QESout::error()` calls `exit()`.

- Add a small exception hierarchy to `qesutil`, for example `qes::InputError`,
  `qes::UnsupportedFeature`, and `qes::RuntimeError`, deriving from the
  matching standard exceptions. `QESout::error()` throws instead of exiting.
- Replace every `exit()` in the sources the extension compiles, not only those
  judged reachable. Zero references can be verified; reachability arguments
  cannot.
- Convert assertions that inputs can trigger, such as the sensor-count
  assertion in `WINDSGeneralData`, into checks that throw. Internal invariant
  assertions, such as the index checks in `Matrix3.h`, are compiled out: the
  extension and the audited libraries build with `NDEBUG`. Debug and sanitizer
  builds keep them as development checks.
- The executables catch exceptions in `main`, report the message through their
  console handler, and return `EXIT_FAILURE`, preserving command-line errors.
- Destructors and other `noexcept` paths must not throw, because an escaping
  exception calls `std::terminate`. When OpenMP is enabled later, exceptions
  must not escape parallel regions for the same reason.
- The extension translates input errors to `ValueError` and other native
  exceptions to `RuntimeError` or a `dtcc_qes` subclass.

Verification: the symbol audit finds no references to process-termination or
assertion-failure functions, and subprocess tests trigger each supported native
failure, including calls to the private extension that bypass Python
validation, and check that the process survives with a Python exception.

### Native code performs no I/O

The C++ side neither reads nor writes files. Python supplies all inputs as
arrays and receives all outputs in memory. The extension therefore builds and
links without GDAL, NetCDF (C or C++), or compiled Boost libraries. Boost
headers remain a header-only build dependency for this milestone: `QEStime`
uses Boost.DateTime, which has been header-only since Boost 1.73, and the
`ParseInterface` base class uses Boost.PropertyTree. Boost.ProgramOptions is
used only by the executables.

I/O is currently entangled with the core:

- Core headers include I/O libraries directly. `DTEHeightField.h` includes
  GDAL headers, and `WINDSGeneralData.h`, `WindProfilerType.h`, `LocalMixing.h`,
  and `HRRRInput.h` include `<netcdf>`. Through `SimulationParameters.h`,
  `fire/Fires.hpp`, and `WINDSGeneralData.h`, nearly every core translation unit
  sees them.
- Input classes perform I/O while parsing. `SimulationParameters` constructs DEM
  and WRF readers, `BuildingsParams` opens shapefiles, `MetParams` and `Sensor`
  read sensor files, and all of them resolve paths through
  `QESFileSystemHandler`.
- `WINDSGeneralData.cpp` mixes the core path with WRF, HRRR, DEM, shapefile,
  coefficient-file, and NetCDF workspace code. `Domain.cpp` has a NetCDF
  constructor.
- The top-level CMake requires GDAL and NetCDF unconditionally and adds their
  include directories globally.

Required changes to the QES fork:

- Add a `QES_ENABLE_IO` option that defaults to `ON`, leaving the standalone
  build unchanged. The extension configures it `OFF` and never calls
  `find_package` for GDAL or NetCDF, so any remaining dependency is a compile
  or link error.
- Split the libraries into I/O-free core targets (`qesutil`, `qeswindscore`)
  and I/O targets (`qesutilio`, `qeswindsio`) that only the executables link.
  Whole I/O files move to the I/O targets: NetCDF input and output,
  `ESRIShapefile`, `GIStool`, `WRFInput`, `HRRRData`, `LocalMixingNetCDF`, the
  `WINDSOutput*` and `TURBOutput` writers, `QESFileSystemHandler`,
  `ArgumentParsing`, and, for this milestone, `DTEHeightField`.
- In mixed files, move I/O code into separate functions or translation units,
  such as `WINDSGeneralData_io.cpp`, and confine `#if QES_ENABLE_IO` to the
  remaining call sites. Without I/O those call sites throw
  `qes::UnsupportedFeature`, so an I/O-dependent configuration fails loudly
  instead of being skipped.
- Core headers forward-declare I/O types instead of including their headers.
  Inline functions that use I/O types move out of line, for example
  `SimulationParameters::~SimulationParameters`, which calls
  `DTEHeightField::closeScanner`.
- Because the NetCDF visualization writer leaves the core, the runner
  implements the cell-centre conversion itself, following
  [WINDSOutputVisualization.cpp](QES-Public/src/winds/WINDSOutputVisualization.cpp).

Moving all of `DTEHeightField` to the I/O target is temporary. The terrain
milestone splits its GDAL reader from the array-based height field and meshing
code, which belong in the core.

Verification: a CI job builds and tests the extension on a Linux image without
GDAL or NetCDF development packages, and the symbol audit finds no references
to GDAL, NetCDF, file streams, or file-opening functions.

### Native symbol audit

`tools/check_native_symbols.py` lists the undefined symbols of the QES core
static libraries and the runner's object files, excluding nanobind's, and fails
on any reference in these categories:

| Category | Symbols |
| --- | --- |
| Process termination | `exit`, `_exit`, `_Exit`, `quick_exit`, `abort`, `__assert_fail`, `__assert_rtn` |
| Console output | `std::cout`, `std::cerr`, `std::clog` and wide variants, `stdout`, `stderr`, `printf`, `vprintf`, `puts`, `putchar`, `fprintf`, `vfprintf`, `fputs`, `fputc`, `fwrite`, `perror` |
| File I/O | `fopen`, `freopen`, `open`, `std::basic_filebuf`, `std::basic_ifstream`, `std::basic_ofstream`, `std::basic_fstream`, `std::filesystem` |
| I/O libraries | `nc_*`, `netCDF::*`, `GDAL*`, `OGR*`, `CPL*`, `boost::program_options` |

The script handles Mach-O and ELF naming, including leading underscores and
`std::__1` versus `std::`. Any exception, such as a standard-library hardening
hook, goes in a reviewed allowlist with its justification. `std::terminate` is
not audited because compilers reference it implicitly for `noexcept` paths.

`bindings.cpp` includes no QES headers. The runner exposes a pimpl interface, so
QES inline code is instantiated only in audited objects.

## Findings and working baseline

The initial analysis used QES 2.3.1 at submodule commit `dced7ec5`. The project
lockfile resolves DTCC Core from `develop` at commit
`625a8feaff5d0da11d3f078082072e185ffa60a4`. Development and CI should use a recorded
DTCC revision so model changes do not silently change the adapter contract.

The existing project is a Python scaffold. It needs an extension build backend,
a top-level CMake configuration, and an importable `dtcc_qes` package. The
distribution name remains `dtcc-qes`. `pyproject.toml` currently lists
`nanobind` as a runtime dependency; it belongs in the build requirements only.

| Integration point | Existing implementation | Intended use |
| --- | --- | --- |
| Simulation lifecycle | [qesWindsMain.cpp](QES-Public/qesWinds/qesWindsMain.cpp) | Follow its initialization, profile, parameterization, and solve sequence. |
| Native libraries | [winds/CMakeLists.txt](QES-Public/src/winds/CMakeLists.txt), [util/CMakeLists.txt](QES-Public/src/util/CMakeLists.txt) | Link the I/O-free `qeswindscore` and `qesutil` targets into the extension. |
| Input objects | [WINDSInputData.h](QES-Public/src/winds/WINDSInputData.h), [SimulationParameters.h](QES-Public/src/winds/SimulationParameters.h), [MetParams.h](QES-Public/src/winds/MetParams.h) | Construct simulation and meteorological inputs directly in C++, in one place. |
| Buildings | [PolyBuilding.cpp](QES-Public/src/winds/PolyBuilding.cpp) | Supply polygon vertices, height, base elevation, and an integer ID. |
| Solver selection | [SolverFactory.cpp](QES-Public/src/winds/SolverFactory.cpp) | Select the serial CPU implementation for reproducible reference runs. |
| Output conversion | [WINDSOutputVisualization.cpp](QES-Public/src/winds/WINDSOutputVisualization.cpp) | Reimplement its staggered-to-cell-centre averaging and ghost-layer removal in the runner. |
| Messages and errors | [QESout.cpp](QES-Public/src/util/QESout.cpp) | Becomes the leveled message sink and the throwing error path. |

A local CPU build and two executable runs succeeded during analysis. Both used
40 × 30 × 20 physical cells with a 2 m cell size and produced finite velocity
arrays of the expected dimensions. The flat case converged in one iteration;
the building case reached a solver tolerance of `1e-5` in 162 iterations.
These observations establish a baseline, not fixed iteration-count assertions.

The installed DTCC package also successfully constructed a `City`, extracted a
LOD0 footprint, and attached an `(N, 3)` velocity `Field` with
`association="cell"` to a `VolumeGrid`.

QES currently searches for a NetCDF C++ library named `netcdf_c++4`, while the
local Homebrew installation provides `libnetcdf-cxx4.dylib`. Supplying the
library path allowed configuration and compilation to succeed. This now affects
only the reference executable build, which should handle the naming difference
without a machine-specific path.

### QES behaviour the integration must handle

| Area | Finding | Consequence |
| --- | --- | --- |
| Input objects | `SimulationParameters`, `MetParams`, `Sensor`, and `TimeSeries` are XML-oriented `ParseInterface` classes. `totalTimeIncrements`, `DTE_mesh`, and `m_domIType` are set only by parsing, and `WINDSInputData` has no destructor. | Build them only in `qes_inputs.cpp`, initialize every member explicitly, and own them in the runner. |
| Input mutation | `WINDSGeneralData` shifts sensor coordinates and building vertices by the halo in place, and adopts the input's building pointers into its own list ([WINDSGeneralData.cpp:804](QES-Public/src/winds/WINDSGeneralData.cpp)). | Build fresh inputs for every preparation, and define one owner for buildings before adding cleanup. |
| Sensors | Construction asserts that at least one sensor exists. A time series without a timestamp falls back to the system clock and prints a warning. | The runner always creates one sensor with a fixed timestamp. |
| Destruction | `Solver` has no virtual destructor. `WINDSGeneralData` has a defaulted destructor while holding dynamically allocated objects. | Fix both on the supported path. |
| Convergence | `tolerance` is a `double` defaulting to `1e-9`, but the solver stores `float tol` ([Solver.h:82](QES-Public/src/winds/Solver.h)) and compares a `float` maximum change against it, so the default cannot be reached and runs exhaust `maxIterations`. `Solver::solve` returns `void` and only prints its result. | Use an explicit default tolerance (`1e-5`, as in the baseline), reject tolerances float cannot resolve, and make `solve` return diagnostics. |
| Log-law correction | With `logLawFlag=1`, the driver modifies the velocities after the solve through `wallLogBC`. | Set `logLawFlag=0` for this milestone and record it in the metadata. |
| Repeated solves | Construction snapshots the building cell flags in `icellflag_initial`, and `resetICellFlag()` restores them before each time step. Domain roughness (`z0_domain_u/v`) is taken from the first sensor at construction, and wind conditions are indexed as sensor time series. | Separate preparation from solving in the runner. Roughness length remains a preparation-time input until QES is changed. |
| Output layout | The visualization writer keeps vertical indices `1` to `nz - 2`, dropping the ground ghost layer and the extra staggered top layer. | Public arrays contain physical cells only. |
| Console and exit | 533 console-output statements, 75 `exit()` calls, and 18 `assert()` calls in `src/winds`, `src/util`, and `src/qes`; `QESout::error()` exits. | See [Project constraints](#project-constraints). |
| Build | The top-level CMake uses `CMAKE_SOURCE_DIR`, sets include directories globally, enables CUDA automatically when a CUDA compiler is found, always adds plume, fire, examples, and executables, runs CPack and install rules unconditionally, and force-sets `CMAKE_BUILD_TYPE` and `CMAKE_VERBOSE_MAKEFILE` in the cache. | Make QES safe to include as a subproject (step 2). |
| Grid spacing | `Domain::getDomainSize()` returns `(dx, dx, dz)` ([Domain.h:104](QES-Public/src/qes/Domain.h)). Canopy, HRRR, turbulence, plume, and fire code use it. | Harmless here because the cell size is scalar; corrected in the next milestone. |

### DTCC Core findings

- `VolumeGrid` does not define a cell order. `coordinates()` builds vertices
  with `np.meshgrid(x, y, z)` and its default `'xy'` indexing, which orders
  them by y, then x, with z fastest: neither C nor Fortran order of
  `(x, y, z)`. Agree the cell-order convention with the DTCC Core maintainers,
  and document it there, before `to_dtcc()` relies on it.
- `init_logging(name)` returns callbacks whose `error` and `critical` raise
  `RuntimeError`. `get_python_logger(name)` returns the underlying
  `logging.Logger`, whose handler prints through Rich.
- Shapely is already a DTCC Core dependency and can validate footprints.

## Proposed public contract

```python
from dtcc_qes import wind

condition = wind.WindCondition(
    speed=5.0,              # m/s at reference_height
    direction=270.0,        # degrees clockwise from north; wind comes from west
    reference_height=10.0,  # metres above ground
    roughness_length=0.1,   # metres
)

result = wind.run(
    city,
    condition,
    grid=wind.GridSpec(resolution=2.0),         # metres in x, y, and z
    solver=wind.SolverOptions(tolerance=1e-5),
    terrain="flat",
)

velocity = result.velocity  # (nz, ny, nx, 3), components (u, v, w)
grid = result.to_dtcc()     # VolumeGrid with cell-associated Fields
```

Options are grouped in small frozen dataclasses, so later milestones add fields
or groups instead of growing a flat keyword list:

| Option group | This milestone | Later growth |
| --- | --- | --- |
| `WindCondition` | Speed, direction, reference height, roughness length | Stability; a sequence of conditions |
| `GridSpec` | Resolution, explicit bounds, horizontal padding, clearance above the tallest building, cell-count limit | Per-axis spacing, vertical stretching |
| `SolverOptions` | Tolerance, iteration limit, `raise_on_nonconvergence=True` | Solver backend |
| `terrain` | `"flat"` or `FlatTerrain(elevation=...)` | DTCC rasters and meshes |

Finalize names and defaults while implementing the configuration model.

The city supplies geometry. Wind conditions must be explicit; they cannot be
inferred from the city. Multiple conditions can later be accepted as
`run(city, [c1, c2, ...])`, implemented by preparing the geometry once.

The `terrain` argument makes the terrain approximation explicit. A city without
terrain implies flat ground. If the city has terrain, the caller must pass
`terrain="flat"` to accept flattening, which is recorded in the metadata;
otherwise `run` raises `ValueError`. Missing or incompatible geometry must
produce an actionable error identifying the affected building.

QES parameterization settings (rooftop, upwind cavity, street canyon, wake,
sidewall, and wall roughness) use QES defaults, travel in the native
configuration, and are recorded in the metadata. Exposing them publicly can
wait.

`WindResult` should provide:

| Member | Contract |
| --- | --- |
| `velocity` | Owned `float32` array with shape `(nz, ny, nx, 3)`, in m/s. |
| `x`, `y`, `z` | One-dimensional physical cell-centre coordinates in the local simulation frame, excluding ghost layers. |
| `cell_flags` | Integer array with shape `(nz, ny, nx)` preserving QES cell classifications. |
| `solid_mask` | Boolean mask derived from geometry classifications, with its meaning documented. |
| `origin`, `crs` | Translation back to the input coordinate frame and its coordinate reference system. |
| `metadata` | Effective domain, input conditions, model settings, QES and DTCC revisions, and geometry simplifications. |
| `diagnostics` | Iteration count, tolerance, convergence status, and the solver's final convergence metric. |

QES's reported convergence metric is the maximum change in the Lagrange
multiplier between iterations. Label it accordingly; it is distinct from a
mass-conservation or Poisson residual measurement. Reaching the iteration limit
raises a convergence error by default. With `raise_on_nonconvergence=False`,
`run` returns the result with `diagnostics.converged` set to `False` and logs a
warning.

`to_dtcc()` should return a uniform `VolumeGrid` with velocity, speed, and cell
classification fields. Vector values have shape `(num_cells, 3)` and
`association="cell"`. Preserve the coordinate transform and CRS, and order
cells according to the convention agreed with DTCC Core.

## Architecture

```text
City + option groups
    -> Python validation and geometry conversion          (_city.py, _config.py)
    -> plain native configuration: grid, model settings,
       local polygon arrays, heights, wind condition      (wind_config.h)
    -> nanobind extension (_qes)                          (bindings.cpp)
    -> owning C++ runner: prepare geometry, then solve    (wind_runner.cpp)
         -> QES inputs built in one place                 (qes_inputs.cpp)
         -> I/O-free QES core libraries
         -> QES messages buffered in memory               (log_sink.cpp)
    -> owned result arrays, diagnostics, and messages
    -> WindResult / DTCC VolumeGrid, dtcc-qes logger
```

Design rules:

- Keep DTCC object traversal in Python. The native boundary accepts only
  numeric arrays and plain configuration structs owned by `dtcc-qes`.
- QES types never appear in the bindings, and only the runner's sources include
  QES headers. New features extend the configuration structs and
  `qes_inputs.cpp` rather than exposing QES classes.
- The runner separates preparation (domain, buildings, cell flags) from solving
  (reset flags, wind profile, parameterizations, solver reset, solve,
  extraction). This milestone prepares and solves once, but the interface
  supports further solves on the same geometry.
- Local coordinates cross the boundary as `float64`. Narrowing to QES's `float`
  happens in one place.
- A process-wide mutex serializes native runs until QES thread safety is
  established. The log sink relies on this.
- XML and NetCDF are used only by the reference tooling, never by the library.

Suggested project layout:

```text
CMakeLists.txt
pyproject.toml
LICENSE
src/dtcc_qes/
    __init__.py
    wind.py                 # run() and the public option groups
    result.py               # WindResult and to_dtcc()
    _city.py                # City traversal, footprint validation, local frame
    _config.py              # domain derivation and native configuration
    _logging.py             # dtcc-qes logger and native message forwarding
src/cpp/
    bindings.cpp            # nanobind module; includes no QES headers
    wind_config.h           # plain structs forming the binding contract
    wind_runner.h           # pimpl interface: prepare and solve
    wind_runner.cpp
    qes_inputs.cpp          # the only place QES input objects are built
    log_sink.h
    log_sink.cpp            # buffers QES messages during a native call
tests/
    fixtures/               # case definitions and reference arrays
    test_city_adapter.py
    test_wind.py
    test_results.py
    test_native_safety.py   # silence, unwinding, repeated runs, in subprocesses
tools/
    make_reference.py       # runs the QES executable to produce references
    check_native_symbols.py # native symbol audit
examples/
    single_building.py
QES-Public/
```

## Implementation sequence

### 1. Capture the reference baseline

Record what the unmodified executable produces before changing QES, so every
later change has a regression check.

- Define the flat and single-building cases once in Python, in
  `tests/fixtures/`: grid, geometry in local coordinates, wind condition,
  sensor location, parameterization settings, solver tolerance, and iteration
  limit.
- `tools/make_reference.py` writes QES XML from those definitions, runs the
  unmodified QES 2.3.1 executable with the serial CPU solver and
  `logLawFlag=0`, reads its NetCDF output, and stores velocities, cell flags,
  coordinates, and the solver summary as compressed NumPy arrays. Use XML
  polygon buildings in local coordinates: the shapefile path subtracts the
  minimum extent, the XML path does not.
- Record the QES revision, compiler, flags, and platform with the references.
  The generator's dependencies, including a Python NetCDF reader and a QES
  build with GDAL and NetCDF, form a separate development group and never
  become runtime or library build dependencies.
- Resolve the NetCDF C++ library naming difference in this reference build.

Completion check: reference arrays for both cases are committed and can be
regenerated with one command.

### 2. Establish the build and the I/O-free QES core

- Replace the scaffold package directory with `src/dtcc_qes`.
- Use scikit-build-core as the build backend and nanobind as a build
  requirement. Declare runtime dependencies (`dtcc-core`, `numpy`) separately
  and remove `nanobind` from them. Add the GPL-3.0-only license metadata and
  license files.
- Retain the current Python baseline initially.
- Make QES safe to include as a subproject: use `CMAKE_CURRENT_SOURCE_DIR`
  paths, target-scoped include directories and links, and no forced cache
  variables, and run CPack and install rules only when `PROJECT_IS_TOP_LEVEL`.
  Add options that skip executables, examples, plume, and fire, and an explicit
  `QES_ENABLE_CUDA` option, off for the extension, in place of automatic
  detection. Keep OpenMP off.
- Implement the [I/O split](#native-code-performs-no-io).
- Build a private `_qes` extension statically linked to the core targets, using
  C++17, position-independent code, and `NDEBUG`.
- Run the file I/O and I/O library categories of the symbol audit now. The
  console and termination categories become mandatory after step 3.

Completion check: the extension imports on a machine without GDAL or NetCDF
development packages, and the standalone executable still builds with
`QES_ENABLE_IO=ON` and reproduces the step 1 references exactly.

### 3. Make the supported QES path safe to embed

- Introduce the leveled message sink and replace console output in the core
  sources, as described under
  [Project constraints](#no-direct-console-output-from-native-code).
- Add the exception hierarchy, replace every `exit()`, convert input-reachable
  assertions, and add exception handling to the executables' `main` functions.
- Audit ownership on the supported path: building aliasing, `WINDSInputData`
  cleanup, a virtual destructor for `Solver`, and `WINDSGeneralData`
  destruction. The runner holds the objects it creates in `std::unique_ptr`;
  change QES ownership only where the runner cannot own an object.
- Initialize members that are otherwise set only by XML parsing.
- Make `Solver::solve` return a diagnostics struct: iteration count, final
  maximum change in the Lagrange multiplier, tolerance, and convergence status.
- Keep each change a focused, independently reviewable commit on the QES fork,
  written so it can be proposed upstream.

Completion check: the full symbol audit passes; the patched executable
reproduces the step 1 references exactly and still reports its messages and
errors through its console handler; and a native test runs the flat case
repeatedly with complete cleanup and unwinds from each supported failure
without terminating.

### 4. Build the runner and bindings

- Define the configuration structs in `wind_config.h`, and build all QES inputs
  from them in `qes_inputs.cpp`, following the driver sequence in
  `qesWindsMain.cpp`. Place the single sensor as the reference fixtures do.
- Bind the pimpl runner's `prepare` and `solve` operations using nanobind's
  NumPy array interface with explicit dtype, shape, device, and contiguity
  requirements. Validate offsets and lengths natively as a second line of
  defence behind the Python validation.
- Release the GIL only during native work, and reacquire it before
  constructing Python results and forwarding buffered messages. Serialize
  native runs.
- Return independently owned arrays whose lifetime exceeds the runner's.
  Prefer straightforward copying for the first implementation.
- Convert face velocities to cell centres following the visualization writer's
  convention, and exclude the ghost layers consistently from velocities and
  classifications.
- Translate native exceptions to Python exceptions.

Completion check: a hand-built configuration equal to each fixture reproduces
the step 1 references through the bound runner, the arrays remain valid after
the runner is destroyed, and native messages arrive as `dtcc-qes` log records.

### 5. Implement the city adapter and public API

- Extract canonical LOD0 footprints and require positive, finite building
  heights. Use measured height by default; permit estimated height only through
  an explicit policy. Report missing heights rather than inventing them.
- Validate simple polygons with Shapely, remove redundant consecutive vertices,
  close rings, and normalize winding to QES's convention. Reject holes,
  multipart geometry, unsupported building parts, and overlapping footprints;
  do not attempt to resolve overlaps.
- Require a shared planar coordinate frame measured in metres. Accept the
  synthetic local frame without a CRS. Support identity and translation-only
  transforms, and reject others explicitly.
- Compute a common local origin in double precision before converting geometry.
  Preserve the origin and the source building-ID mapping.
- Define one flat ground plane and consistent building base elevations. Reject
  incompatible elevations unless the caller explicitly requests flattening.
- Derive a padded domain with clearance above buildings, allow explicit bounds,
  align extents to the grid, and record the effective bounds. Require explicit
  bounds for an empty city used as a flat-domain reference case.
- Enforce the cell-count limit before native allocation. Build independent
  native inputs for every run so the original city and later runs are
  unaffected.
- Implement the option groups, `wind.run`, `WindResult`, and `to_dtcc()` with
  documented coordinates, units, and the agreed cell ordering.

Completion check: the synthetic city maps to the same local geometry and domain
as the fixtures, including after a large translation of its coordinates, and
`wind.run` reproduces the references.

### 6. Validate

- Compare coordinates, cell flags, and velocities with the references. On the
  platform and toolchain that produced them, expect exact agreement: any
  difference indicates an input mismatch and must be explained. Across
  platforms, use documented tight tolerances justified by compiler differences.
- Verify finite values, expected output dimensions, cardinal wind directions,
  building occupancy, and the flat logarithmic profile.
- Check mass conservation using QES's native staggered velocities and discrete
  flux operator. Keep this check separate from the convergence metric.
- Test array ordering on unequal axis lengths and use distinguishable field
  values to catch transposition in DTCC conversion.
- Test translation invariance, unchanged input geometry, invalid inputs,
  non-convergence, result ownership, and repeated calls.
- Run the silence and unwinding tests in subprocesses, and run native tests
  under AddressSanitizer and UndefinedBehaviorSanitizer where supported.

Completion check: numerical parity, geometry mapping, silence, termination,
and lifecycle checks pass without relying on exact solver iteration counts.

### 7. Document and make the milestone reproducible

- Add an executable example that constructs its own one-building `City`.
- Document the native build requirements (a C++17 compiler, CMake, and Boost
  headers; no GDAL or NetCDF), build commands, wind conventions, domain
  defaults, flat-terrain assumptions, supported geometry, result semantics,
  logging behaviour, and how to regenerate the references.
- Add CPU CI for macOS and Linux using recorded QES and DTCC revisions. CI
  builds and tests the extension, including on a Linux image without GDAL or
  NetCDF, runs the symbol audit, and in a separate job rebuilds the reference
  executable and confirms the committed references are current.
- Verify local wheel installation in a clean environment. Include the required
  QES sources in the source distribution, and the GPL-3.0 license files and QES
  notices in all distributed artifacts.

## Acceptance criteria

- [ ] `dtcc-qes` declares GPL-3.0-only, and its sdist and wheel include the
  license files, QES notices, and the QES sources the build uses.
- [ ] A clean build on a machine without GDAL or NetCDF development packages
  installs `dtcc_qes` and its nanobind extension.
- [ ] `wind.run(city, ...)` executes the QES serial CPU solver in process.
- [ ] The flat and one-building cases reproduce the references from the
  unmodified executable: exactly on the reference toolchain, and within
  documented tolerances elsewhere.
- [ ] The one-building case reaches the requested solver tolerance and returns
  finite arrays with the expected physical-cell dimensions.
- [ ] Result coordinates, units, classifications, and convergence metrics are
  explicit; ghost layers are absent from public arrays.
- [ ] `result.to_dtcc()` produces cell-associated fields on a georeferenced
  `VolumeGrid`, ordered by the convention agreed with DTCC Core.
- [ ] Invalid inputs, native failures, and non-convergence produce Python
  exceptions, and the process survives each of them.
- [ ] Native code prints nothing: the descriptor-level silence test passes for
  successful and failing runs, and native messages reach the `dtcc-qes`
  logger.
- [ ] The native symbol audit passes with no termination, console, file I/O,
  GDAL, or NetCDF references outside the reviewed allowlist.
- [ ] Repeated calls preserve the input city, return independently owned arrays,
  and pass lifecycle checks without persistent native leaks or crashes.
- [ ] The self-contained example and CPU CI pass on macOS and Linux.

## Next milestones

Terrain support is the next milestone. QES already has an array-based
`DTEHeightField` constructor, but its ownership, initialization, sampling,
coordinate shifts, and building base-elevation behaviour need validation before
connecting DTCC rasters or meshes. That milestone also:

- splits `DTEHeightField` so its array-based height field and meshing live in
  the I/O-free core, leaving only the GDAL reader in the I/O target;
- corrects `Domain::getDomainSize()`.

Later milestones can add cut cells, turbulence, multiple wind conditions,
GPU acceleration, progress reporting, and public binary wheels:

- Multiple wind conditions map to QES sensor time series. Because domain
  roughness is fixed at construction, conditions with different roughness
  lengths need either separate preparations or a QES change.
- OpenMP and CUDA paths must keep exceptions inside parallel regions and keep
  console output behind the message sink.
- Live progress reporting through DTCC Core needs a callback that is safe to
  call while the GIL is released.
- With the I/O-free core, wheels depend only on the C++ runtime and header-only
  Boost. nanobind's stable ABI support can cover Python 3.12 and later.

## Binding references

- [nanobind packaging](https://nanobind.readthedocs.io/en/latest/packaging.html)
- [nanobind NumPy arrays and ownership](https://nanobind.readthedocs.io/en/latest/ndarray.html)

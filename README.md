# dtcc-qes

Run QES-Winds' CPU solver on a DTCC city and receive georeferenced
NumPy arrays in memory. Milestone 1 supports one steady neutral logarithmic
wind profile, uniform cells, flat ground and simple LOD0 building extrusions.
Python supplies geometry and wind inputs; the native core performs no file I/O.

Version `0.1.0b1` is the initial beta. The Python API may change before a stable
release; supported inputs and solver limitations are documented below.

## Build and install

Requirements are Python 3.13+, a C++17 compiler, CMake 3.18+, Git and Boost
1.73+ headers. OpenMP is detected automatically, with a serial CPU fallback
when unavailable. The library requires no GDAL, NetCDF, compiled Boost or CUDA
libraries. DTCC's Python dependencies include their usual GIS wheels; those
are separate from the native QES build requirements.

On macOS, install native tools with `brew install cmake ninja boost`.
On Debian/Ubuntu use
`sudo apt-get install build-essential cmake ninja-build libboost-dev git`.
Install [uv](https://docs.astral.sh/uv/) and start from a recursive checkout:

```sh
git submodule update --init --recursive
uv sync --frozen --group dev
uv run --frozen python examples/single_building.py
```

The submodule pins an exact commit on the embedding fork's `dtcc-embed` branch.
`pyproject.toml` and
`uv.lock` pin DTCC Core to `625a8feaff5d0da11d3f078082072e185ffa60a4`.
Keep the lockfile when reproducing this milestone; do not update it to track
`develop`. First installation downloads the locked packages and builds the
native extensions. The fork's recorded commit must be available on its remote
before another machine can fetch the submodule.

### OpenMP

Set the CMake option `DTCC_QES_OPENMP` to select the CPU build:

| Value | Behavior |
| --- | --- |
| `OFF` | Serial CPU solver; no OpenMP runtime dependency |
| `ON` | OpenMP red-black CPU solver; configuration fails if OpenMP is unavailable |
| `AUTO` (default) | Use OpenMP when CMake finds it; otherwise build the serial solver |

On macOS, install `libomp` and tell CMake where to find it:

```sh
brew install libomp
export OpenMP_ROOT="$(brew --prefix libomp)"
```

GCC on Debian/Ubuntu supports OpenMP with the compiler installed above. Rebuild
the Python package with OpenMP enabled:

```sh
uv sync --frozen --group dev --reinstall-package dtcc-qes -Ccmake.define.DTCC_QES_OPENMP=ON
OMP_NUM_THREADS=4 uv run --frozen --no-sync python examples/single_building.py
```

For a direct CMake build, pass `-DDTCC_QES_OPENMP=ON`. Standard OpenMP settings
such as `OMP_NUM_THREADS` control the thread team. The GIL is released during
native work; the process-wide QES mutex still serializes separate solves.
OpenMP accelerates the numerical solve within that mutex.

`result.metadata["model"]["backend"]` identifies the solver, and
`result.metadata["versions"]["native_build"]["openmp_enabled"]` records build
support. Red-black iteration ordering can change iteration counts and float32
velocities slightly. Serial builds retain the original reference behavior.
An OpenMP-built wheel requires its OpenMP runtime on the destination system.

## Run a city

```python
from dtcc_qes import wind

condition = wind.WindCondition(
    speed=5.0,
    direction=270.0,
    reference_height=10.0,
    roughness_length=0.1,
)
result = wind.run(city, condition, grid=wind.GridSpec(resolution=2.0))
velocity = result.velocity
volume_grid = result.to_dtcc()
```

The executable [example](examples/single_building.py) constructs its own `City`
and has no input files or external datasets.

For a wind speed map and streamlines around three rectangular buildings, run
the self-contained [demo](demo/simple_wind_demo.py):

```sh
uv run --frozen python demo/simple_wind_demo.py
# Save the figure without opening a window:
uv run --frozen python demo/simple_wind_demo.py --save build/wind-demo.png --no-show
```

The [medium city demo](demo/medium_city.py) places 20 buildings of varied heights
in six blocks with a central avenue and cross streets. It shows a street-level
wind speed map and streamlines:

```sh
uv run --frozen python demo/medium_city.py
# Save the figure without opening a window:
uv run --frozen python demo/medium_city.py --save build/medium-city.png --no-show
```

Wind speed is m/s at the reference height above ground. Direction is
meteorological: degrees clockwise from north indicating where the wind comes
from. North (`0°`) flows toward negative y, east (`90°`) toward negative x,
south (`180°`) toward positive y, and west (`270°`) toward positive x. The
profile is `U(z) = U_ref log((z + z0) / z0) / log((z_ref + z0) / z0)`.

## Geometry, coordinates and flat ground

- Buildings must be direct city children with one canonical LOD0 `Surface`.
  Footprints must be valid simple polygons, without holes, multipart surfaces,
  overlap or touching. Building parts and nested buildings are rejected.
  Consecutive duplicate vertices are removed and rings made clockwise.
- Positive finite `measured_height` values are required. Explicit
  `height_policy="allow_estimated"` permits an `estimated_height` when a
  measurement is absent; an invalid measurement never falls back to an estimate.
- All geometry uses one planar CRS in metres, or a synthetic metre frame with
  no CRS. Geographic and non-metre CRSs are rejected. Identity and absolute
  translation-only DTCC transforms are supported: identity inherits the
  enclosing frame, equal translations apply once, and conflicting declarations
  raise. Rotation, scaling and shear require an explicit conversion beforehand.
- Consistent footprint elevations define one ground plane. A city containing
  terrain requires explicit `terrain="flat"` or `FlatTerrain(elevation=...)`.
  Explicit flattening also permits nonplanar/inconsistent building bases.
  `"flat"` chooses bounds' zmin, or the lowest footprint base without bounds.
  Other city objects, such as trees, are omitted and recorded in metadata.
- A common origin is subtracted in float64 before QES's float32 conversion.
  Rings are checked again after narrowing. Float32 precision can reject very
  thin edges or gaps; the adapter does not repair or merge them.

## Options and domain

Options are frozen dataclasses.

| Group | Defaults |
| --- | --- |
| `WindCondition` | Required speed/direction; reference height 10 m; roughness 0.1 m |
| `GridSpec` | Resolution 2 m; horizontal padding 20 m; vertical clearance 20 m; `max_cells=20_000_000` |
| `SolverOptions` | Tolerance `1e-5`; 500 iterations; `raise_on_nonconvergence=True` |
| `FlatTerrain` | Explicit global ground elevation 0 m |

Automatic domains include all footprints, at least three cells of horizontal
padding, roof clearance and the reference height. Explicit `GridSpec(bounds=...)`
accepts DTCC `Bounds` or `(xmin, ymin, zmin, xmax, ymax, zmax)` in the global
input frame. Lower bounds define the local origin; upper bounds expand to
whole cells at the effective float32 spacing. Empty cities need explicit
bounds. Bounds' zmin must equal the chosen ground plane. Native limits are
3–10,000 cells in x/y and 2–10,000 in z, with two cells around footprints and a
physical cell centre above each roof. Cell counts are checked before allocation.

Default rooftop, cavity, street canyon, wake, sidewall and wall roughness
settings are QES's defaults and are recorded in metadata. Both CPU backends use
stair-step geometry, zero halos and `logLawFlag=0`. Native calls serialize through
a process-wide mutex; OpenMP parallelizes each solve internally. Roughness is
preparation-time state in the private reusable runner.

## Results, diagnostics and logging

`WindResult.velocity` owns float32 data with shape `(nz, ny, nx, 3)` and
components `(u, v, w)` in m/s. `x`, `y`, `z` are local physical cell centres;
add `origin` to recover global coordinates. Ghost layers are removed.
`cell_flags` retains QES classifications; `solid_mask` selects 0 (building)
and 2 (terrain), excluding air parameterizations. Results survive native runner
destruction and subsequent calls. The source city is unchanged.

`to_dtcc()` returns a uniform `VolumeGrid` with independent `velocity`, `speed`
and `cell_flags` fields and `association="cell"`. Vector values are `(N, 3)`;
scalars are `(N,)`. Cell order is **y, then x, with z fastest**, matching the
current DTCC `VolumeGrid.coordinates()` meshgrid `xy` order. Local bounds and
a translation/CRS Transform preserve georeferencing. See
[validation notes](docs/validation.md) for the isolated ordering convention.

Diagnostics report iterations, effective tolerance, convergence and the
**maximum Lagrange multiplier change**, which is not a mass-conservation
residual. Non-convergence raises `wind.ConvergenceError` by default; its
`diagnostics` remain available. `SolverOptions(raise_on_nonconvergence=False)`
returns the result and logs one warning. The legacy top-boundary flux limitation
is documented in the validation notes; convergence does not certify zero
divergence in every returned cell.

Metadata records requested/effective conditions and domain, geometry policies,
source building IDs, simplifications, model/solver options, QES revision,
compiler information and DTCC version/VCS revision. A DTCC wheel without VCS
metadata reports its revision as `None` rather than guessing it.

All package logging uses
`dtcc_core.common.get_python_logger("dtcc-qes")`. QES info/debug messages become
DEBUG records; native warnings become WARNING records. One INFO summary reports
grid, building count, iterations and convergence. Native errors become Python
exceptions without duplicate error logging. The native handler buffers messages
without calling Python while the GIL is released. DTCC's ordinary logger/handler
configuration controls console output; the native core never prints or opens files.

## Validate and package

```sh
cmake -S . -B build/native -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/native --parallel 8
cmake --build build/native --target check_native_symbols
ctest --test-dir build/native --output-on-failure
DTCC_QES_NATIVE_TEST="$PWD/build/native/check_safety" uv run --frozen python -W error -m pytest -q
uv run --frozen python -m build --wheel --sdist --no-isolation -Ccmake.define.DTCC_QES_BUILD_TESTS=OFF
uv run --frozen python tools/check_artifacts.py dist
```

For development/test wheels keep nanobind leak warnings enabled by adding
`-Ccmake.define.DTCC_QES_BUILD_TESTS=ON` to the build command. Distributable
wheels disable those shutdown warnings. Native CTests also run under ASan/UBSan;
the exact commands and descriptor-silence checks are in the validation notes.

CI builds the CPU extension on macOS and in a Linux container without GDAL or
NetCDF development packages, audits every native core/bridge object, checks a
wheel rebuilt from its sdist and runs the example/tests. Separate jobs build
the pristine and patched reference executables. A workflow definition alone
is not a successful CI run: see the milestone report for actual evidence and
any external verification still pending.
The [final audit](docs/milestone1-audit.md) maps all seven steps to evidence and
lists the remaining external checks.

## Regenerate executable references

Only reference tooling needs GDAL, NetCDF C/C++, compiled Boost.ProgramOptions
and Python netCDF4. On macOS: `brew install gdal netcdf netcdf-cxx boost`.
On Debian/Ubuntu install `libgdal-dev libnetcdf-dev libnetcdf-c++4-dev
libboost-program-options-dev pkg-config` in addition to the native build tools.

```sh
uv sync --frozen --group dev --group reference
uv run --frozen --group reference python tools/make_reference.py --check
# Intentionally replace references only when reviewing a changed baseline:
uv run --frozen --group reference python tools/make_reference.py
# Check the embedding fork's standalone executable as well:
uv run --frozen --group reference python tools/make_reference.py --qes-source QES-Public --check
```

The generator exports pristine QES commit
`dced7ec571487be7538eca17bfc25bb3262fb6d0` from Git, uses the canonical fixture
definitions, detects NetCDF C++ naming differences and records provenance.
Exact comparison is the default. Cross-platform velocity checks can pass
`--rtol 1e-5 --atol 2e-5`; coordinates, spacing and classifications stay exact.
`--output` and `--reference-dir` allow pristine and patched executables to be
compared exactly on the same host without overwriting committed fixtures.

## License and deferred work

GPL-3.0-only; see [LICENSE](LICENSE), [QES's license](QES-Public/LICENSE) and
[NOTICE](NOTICE). The sdist contains corresponding QES sources and build files;
both distributions carry the licenses/notices. The upstream metadata discrepancy
has a [prepared report](docs/upstream-license-report.md).

Terrain sampling, cut cells, roof detail, vegetation, turbulence, multiple
conditions, CUDA and public binary wheel distribution remain deferred.
`Domain::getDomainSize()`'s anisotropic-spacing correction belongs to the
terrain milestone; this implementation uses scalar spacing throughout.

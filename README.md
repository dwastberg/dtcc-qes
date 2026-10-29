# dtcc-qes

Run QES-Winds' CPU solver on a DTCC city and receive georeferenced
NumPy arrays in memory. The solver supports one steady neutral logarithmic
wind profile, uniform horizontal spacing, uniform or explicit vertical layers,
flat ground and simple LOD0 building extrusions.
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
Install [uv](https://docs.astral.sh/uv/) and start from a checkout:

```sh
uv sync --frozen --group dev
uv run --frozen python examples/single_building.py
```

The QES-Winds core is vendored in `src/qes_core`; its
[provenance](src/qes_core/PROVENANCE.md) records the fork commit it was taken
from. Building needs no submodule. The `QES-Public` submodule is only used by
the [reference tooling](#regenerate-executable-references).
`pyproject.toml` and
`uv.lock` pin DTCC Core to `625a8feaff5d0da11d3f078082072e185ffa60a4`.
Keep the lockfile when reproducing this milestone; do not update it to track
`develop`. First installation downloads the locked packages and builds the
native extensions.

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

result = wind.run(
    city,
    speed=5.0,
    direction=270.0,
    reference_height=10.0,
    roughness_length=0.1,
    resolution=2.0,
)
velocity = result.velocity
volume_grid = result.to_dtcc()
```

Use `vertical_grid=wind.VerticalGrid.from_faces(z_faces)` to supply vertical
cell-face heights in metres above the flat ground. `resolution` continues to
set both x and y spacing. For example, a scene whose required top is at most
40 m can use:

```python
import numpy as np

z_faces = np.r_[np.arange(0, 10, 0.5), np.arange(10, 20), np.arange(20, 42, 2)]
vertical_grid = wind.VerticalGrid.from_faces(z_faces)
preview = wind.preview_grid(city, resolution=2.0, vertical_grid=vertical_grid)
print(preview.shape, preview.cell_count, preview.z, preview.dz)
result = wind.run(
    city, speed=5.0, direction=270.0, resolution=2.0,
    vertical_grid=vertical_grid,
)
print(result.z_faces, result.z, result.dz)
pedestrian = result.sample(height=1.5, method="linear")
speed = pedestrian.speed     # (y, x), m/s; invalid points are NaN
valid = pedestrian.valid     # (y, x), boolean mask
```

Supply at least two layers, start at zero, and increase faces strictly. With
explicit bounds, the requested final face must match the bounds' height above
ground; with automatic bounds it must cover the required clearance and reference
height. Actual faces use QES's float32 layer accumulation and are recorded in
the result and metadata. Invalid or collapsed layers fail before wind-array
allocation. The specification copies its input and is immutable.

`result.vertical_uniform` identifies equal solver-layer thicknesses. Uniform
anisotropic grids can be converted to `VolumeGrid` with their true z extent;
nonuniform grids retain native arrays and reject direct `to_dtcc()` conversion.

`result.sample()` returns a `wind.WindSample` at native x/y centres. Heights
are metres above flat ground. It defaults to `method="nearest"`, recording the
selected centre in `sampled_height`; ties select the lower centre. Use
`method="linear"` to interpolate velocity components at the requested height
before calculating speed. Every contributing cell must contain finite fluid
velocity; building/terrain flags 0/2 are invalid. Exact centres use only that
cell. Linear sampling outside the centre range returns NaNs and
`sampled_height=None`; heights outside the physical domain raise `ValueError`.
Nearest sampling clips to endpoint centres within the physical domain.

Samples own their arrays and carry `origin` and `crs`. For global coordinates,
widen the local axes before adding large translations:
`global_x = pedestrian.x.astype(np.float64) + pedestrian.origin[0]`.
Global elevation is `pedestrian.sampled_height + pedestrian.origin[2]` when a
sampled height is available.

`wind.preview_grid()` returns a `wind.GridPreview` using the same geometry,
terrain, bounds, clearance and cell-limit preparation as `run`, without
allocating native flow arrays. It returns effective x/y/z axes and z faces,
shape/cell count, layer growth and aspect ratios, and domain/roof diagnostics.
`dz` measures effective face separations; `solver_dz` holds layer thicknesses
before float32 accumulation roundoff. Preview does not estimate solver accuracy
or peak memory. The executable [vertical-grid example](examples/vertical_grid.py)
compares explicit uniform and stretched layers at the same pedestrian height.
See the [B1 validation report](docs/stageb1-validation.md) for contracts and checks.

`wind.preview_grid(city, turbulence=True)` includes the QES turbulence reference
height and its required layer margin. Automatic domains preserve a valid
wind-only grid and append layers at its final thickness. Explicit bounds or
faces raise if their margin is insufficient. `preview.domain["turbulence"]`
records the effective top, added layers and any necessary regeneration.

Optional QES turbulence is returned from the same wind solve:

```python
result = wind.run(city, speed=5.0, direction=270.0, turbulence=True)
sigma = result.streamwise_std       # float64, m/s, shape (z, y, x)
intensity = result.turbulence_intensity  # dimensionless sigma / mean speed
pedestrian = result.sample(1.5, method="linear")
pedestrian_sigma = pedestrian.streamwise_std

wall_model = wind.Turbulence(mixing_length="wall_distance")
preview = wind.preview_grid(city, turbulence=wall_model)
```

`True` selects the provisional `"height"` default (QES method 0).
`"wall_distance"` selects the qualified serial voxel-face method (method 1).
Both use the audited fork's corrected rotation. Automatic bounds can add
layers, which can change the wind field; use identical explicit grids when
comparing turbulence on/off. Explicit bounds and faces must provide the
reference-height margin.

`result.turbulence` is a `wind.TurbulenceFields` with owned float32 `stress`
(`z, y, x, 6`, ordered xx/xy/xz/yy/yz/zz), `tke`, `co_eps` and `mixing_length`.
Stress and TKE are in m²/s², `co_eps` is C0·epsilon with C0=5.7 in m²/s³,
and mixing length is in metres. TKE is computed before stress anisotropy
scaling. Independent boolean `computed`, `capped` and `stress_valid` masks
record coverage, cap equality and covariance validity. Uncomputed float
entries are NaN; invalid computed tensors remain available for diagnosis.
Reference scalars and model constants/counts are recorded in
`result.metadata["turbulence"]`.

Streamwise statistics project the full covariance along the current 3D mean
velocity. They return NaN for uncomputed or materially indefinite stress and
undefined mean directions, and raise if turbulence was not requested.
Properties recheck edited tensors. Height samples interpolate stress components
and preserve invalid-contributor evidence even when interpolation produces a
valid tensor. Validity masks and metadata counts describe their original solve
or sample. This algebraic screening model has not been validated for pedestrian
gusts. The [numerical/performance gate](docs/turbulence-benchmark.md) passes
across 72 configurations, with measured coverage, scaling, grid sensitivity
and costs. DTCC turbulence export and comfort GEM screening are supported.
Dataset integration is deferred until further wind-module work is complete;
the later integration target is a unified wind-comfort dataset. Height remains
the provisional default.

Turbulence adds roughly 110 bytes per native cell and 39 bytes of returned
fields/masks per physical cell. Temporary copies, float64 statistics and extra
domain layers increase peak memory. On the benchmark's 1.28-million-cell
serial case, median peak process RSS is about 399 MiB for wind-only, 637–638 MiB
after native turbulence extraction and 729–786 MiB after Python statistics.
These figures include Python/imports and are not a universal memory budget.

The automatic generator is available as an **unvalidated prototype**, opt-in
through `VerticalGrid.auto(...)`:

```python
specification = wind.VerticalGrid.auto(pedestrian_height=1.5, growth_rate=1.15)
preview = wind.preview_grid(city, resolution=2.0, vertical_grid=specification)
print(preview.domain["vertical_grid"]["effective_settings"])
result = wind.run(city, speed=5.0, direction=270.0, resolution=2.0,
                  vertical_grid=specification)
pedestrian = result.sample(1.5, method="linear")
```

The prototype uses equal fine layers around pedestrian height, building-height
caps and bounded growth, then fits the selected top with a constant-thickness
tail. `resolution` sets x/y spacing. Optional settings include
`min_layer_thickness`, `max_aspect_ratio`, `first_layer_thickness` (a preferred
target), `fine_region_height` and `upper_layer_cap`. Incompatible settings or
cell limits raise before native flow allocation; the generator does not silently
coarsen near-ground layers to meet a budget. Automatic settings have no resolved
`faces`/`layers` until preview or run supplies geometry and bounds.

Metadata records requested/effective settings, generator version,
`policy_status="prototype_unvalidated"`, endpoint rounding and pedestrian
bracketing/profile bias. The planned top fits the requested local height;
effective float32 faces can differ slightly, and their actual extent is retained.
`solver_layer_thicknesses` records the native layer widths, which can differ
from accumulated face separations. These checks establish construction and
coordinate correctness. C2 still needs boundary, resolution, accuracy and cost
studies before any automatic comfort-analysis preset is selected. See the
[C1 report](docs/stagec1-validation.md) and executable
[automatic-grid example](examples/automatic_vertical_grid.py).

The [early C2 controls](docs/stagec2-controls.md) compare both 1.5 and 1.75 m
planes with taller domains and finer horizontal spacing. They identify local
horizontal sensitivity that must be assessed before selecting an automatic
preset; adequate vertical cell placement alone does not establish accuracy.

The [C2b assessment](docs/stagec2b-horizontal-sensitivity.md) traces near-wall
sensitivity through initialization and sampling, finds substantial lateral-domain
effects, and excludes finer horizontal solves that fail residual control.
Accepted finer references and lateral/horizontal verification are prerequisites
to preset selection; diagnostic parameterization-disabled runs are not presets.

The [precision and grid-verification report](docs/precision-and-horizontal-verification.md)
documents the opt-in `solver_precision="float64"` remedy, validated from zero
on serial and OpenMP CPU builds. It restores accepted references for the failed
finer tower solves while retaining float32 geometry and output arrays. Lateral
and horizontal comparisons retain a fixed physical region and critical points;
the automatic policy remains an unvalidated prototype.

The [joint extent/resolution report](docs/joint-grid-verification.md) records
the combined larger-domain/finer-grid controls and additional near-wall checks.
The study uses configurable allocation ceilings, soft cell targets and saved
independent zero-start checkpoints for resumable verification.
All 16 new CPU cases pass the solve gate; near-wall horizontal changes keep
automatic preset selection gated despite passing aggregate comparison budgets.

Dataset options for vertical layers remain later work.
See the [Stage A validation report](docs/stagea-validation.md).
The [sensitivity/cost study](docs/vertical-grid-gate.md) compares explicit grids
at 1.5 m. A fine-grid tower solve fails the common residual target. The
[focused diagnosis](docs/vertical-grid-diagnosis.md) supported the now opt-in
precision remedy. Sampling and explicit-grid preview are available; automatic presets
still require further validation.

The executable [example](examples/single_building.py) constructs its own `City`
and has no input files or external datasets.

### Optional wind dataset

Import `dtcc_qes` to register `qes_wind` with DTCC Core. Importing
`dtcc_qes.datasets` also works. Core does not depend on or import QES.
The dataset implementation stays in this GPL-3.0-only package.

```python
from dtcc_core import datasets
import dtcc_qes

field = datasets.qes_wind(
    bounds=[319720, 6397660, 319820, 6397760],  # EPSG:3006
    wind_speed=5.0,
    wind_direction=270.0,
    resolution=2.0,  # solver cell spacing in metres
)
# field is a dtcc_core.model.VolumeGrid with cell-associated fields:
# velocity, speed, cell_flags
```

The dataset fetches a LOD1 city through `datasets.city` (`source="LM"` by
default, or `"OSM"`), fills footprint courtyards, and calls Core's
`builder.clean_footprints` at `min_building_detail=0.5` metres. Core determines
merged blocks and their heights. Each block becomes a constant-height QES
obstacle; source IDs, cleaning changes, and filled courtyard areas are recorded.
The source city is unchanged. Unsupported geometry remaining after cleaning
raises an error.

Bounds select the city area. The solver expands that area and the building
extent by at least three cells of padding. Four-coordinate bounds derive flat
ground from the terrain raster (or footprint bases if no raster exists) and
the domain top from building heights and clearance. Six-coordinate bounds
`[xmin, ymin, zmin, xmax, ymax, zmax]` specify flat ground and the domain top;
insufficient roof clearance raises an error. `Bounds` objects are also accepted.

Use `product="slice"` to return a native `dtcc_core.model.FieldSlice` with the
same three fields associated with samples. `slice_axis="z"`,
`slice_position=0.5`, and `slice_resolution=128` select a plane and square sample
grid within the solver's cell-centre extent. Sampling uses the nearest cell,
with ties choosing the lower index; metadata records the actual plane coordinate.
Slice points use global coordinates. The field uses local coordinates with its
origin and CRS in its transform. Solid cells retain their values and are
identified by `cell_flags` 0 or 2.

Set `slice_height` to request a horizontal slice in metres above the flat
ground plane. It selects `slice_axis="z"` and takes precedence over
`slice_position`:

```python
slice = datasets.qes_wind(bounds=bounds, product="slice", slice_height=2.0)
```

The height snaps to the nearest solver cell centre. Heights from ground level
through the domain top are accepted; heights above the domain raise an error.
`slice.metadata_payload["slice_height"]` records the sampled height above ground,
and `slice_coordinate` records its global elevation.

`result.dataset_context` contains request parameters, upstream lineage,
preparation details, effective solver bounds, versions, and diagnostics.
Rendering and serialized dataset formats are not part of this API yet.
Use `datasets.qes_wind.info()` for options or run the network-backed
[dataset example](examples/city_dataset.py):

```sh
uv run --frozen python examples/city_dataset.py 319720 6397660 319820 6397760 --product slice
```

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

## Pedestrian wind comfort

`dtcc_qes.comfort` classifies comfort and safety maps from an hourly wind
climate and one pedestrian-level speed field per simulated direction. It
depends only on numpy, so fields can come from QES, other CFD or wind-tunnel
probes. NEN 8100 and the City of London Lawson criteria (2019) are built in;
other tables can be defined as `comfort.Criterion`.

```python
from dtcc_qes import comfort

# speeds, directions: hourly (T,) at the simulations' reference height/roughness
# fields: (D, N, M) mean speed at pedestrian height, NaN in buildings
result = comfort.assess(speeds, directions, fields, field_directions, reference_speed,
                        comfort.CITY_OF_LONDON, times=times, height=1.5)
result.comfort         # int8 indices into comfort.CITY_OF_LONDON.comfort.labels, -1 invalid
result.exceedance[15]  # fraction of hours above 15 m/s
```

Each hour uses the field of the nearest simulated direction, scaled by
`speed / reference_speed`. QES speed-ups do not depend on inflow speed, so one
solve per direction is enough; see [the example](examples/wind_comfort.py).
Optional QES-Turb output can feed `comfort.gust_equivalent_mean` with an explicit
`peak_factor`. Pass those fields and `gem_metadata` to `assess` to retain the
model, averaging assumptions and unvalidated-gust screening warning. Lawson
results remain mean-only unless `gem_fields` are supplied. Treat QES comfort maps as
screening: planning guidelines such as City of London's require RANS or LES
CFD. Method, conventions and sources are in
[docs/wind-comfort.md](docs/wind-comfort.md).

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
  terrain requires explicit `terrain="flat"` or a numeric ground elevation,
  such as `terrain=0.0`.
  Explicit flattening also permits nonplanar/inconsistent building bases.
  `"flat"` chooses bounds' zmin, or the lowest footprint base without bounds.
  Other city objects, such as trees, are omitted and recorded in metadata.
- A common origin is subtracted in float64 before QES's float32 conversion.
  Rings are checked again after narrowing. Float32 precision can reject very
  thin edges or gaps; the adapter does not repair or merge them.

## Options and domain

Options are arguments to `wind.run`; defaults are declared in its signature.

| Group | Defaults |
| --- | --- |
| Wind | Required `speed`/`direction`; `reference_height=10.0`; `roughness_length=0.1` |
| Grid | `resolution=2.0`; `bounds=None`; `horizontal_padding=20.0`; `vertical_clearance=20.0`; `max_cells=20_000_000` |
| Solver | `tolerance=1e-5`; `max_iterations=500`; `raise_on_nonconvergence=False`; `solver_precision="float32"` |
| Terrain | `terrain=None` infers flat ground; `"flat"` explicitly flattens; a number sets the global ground elevation |

Automatic domains include all footprints, at least three cells of horizontal
padding, roof clearance and the reference height. Explicit `bounds=...`
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

With turbulence enabled, the same conversion adds `stress` (`N, 6`,
xx/xy/xz/yy/yz/zz, m²/s²), `tke` (m²/s²), `streamwise_std` (m/s),
`turbulence_intensity` (unit 1) and uint8 `stress_valid` (0/1). These fields
use the same cell order and own their arrays. Uncomputed floats are NaN;
raw invalid computed stress and its TKE remain available while σ/TI are
masked. Validity is rechecked against current tensors at export time;
it is independent of capping and mean direction. Zero or nonfinite mean
direction also masks σ/TI without invalidating a valid covariance.
Descriptions record the model, numerics version, QES revision, validity policy
and unvalidated-gust screening limitation. Nonuniform layers still require
sampling or native arrays rather than direct `VolumeGrid` export.

Diagnostics report iterations, effective tolerance, convergence and the
**maximum Lagrange multiplier change**, which is not a mass-conservation
residual. `diagnostics.max_divergence` and `rms_divergence` report conservative
six-face divergence in s^-1; RMS is weighted by physical cell volume.
`divergence_cell_count` identifies the assessed interior. The prescribed top
band is reported separately as `top_band_max_divergence` and
`top_band_cell_count`; the highest physical layer and prescribed lateral
boundary cells are unassessed. A region with no fluid cells has `None` metrics.
Non-convergence returns the result and logs one warning by default;
its `diagnostics.converged` is `False`. Explicit
`wind.run(..., raise_on_nonconvergence=True)` raises `wind.ConvergenceError`
with `diagnostics` available. The legacy top-boundary flux limitation
is documented in the validation notes; convergence does not certify zero
divergence in every returned cell.

Set `solver_precision="float64"` to use double multiplier storage, right-hand
side construction, SOR updates and face corrections. Geometry, stencil
coefficients and returned velocity arrays remain float32. The default float32
solver and its stopping rule are preserved. Both modes stop on multiplier
change; inspect divergence and iteration stability separately. For example:

```python
result = wind.run(city, speed=5, direction=270, vertical_grid=specification,
                  solver_precision="float64", tolerance=1e-10, max_iterations=8000)
print(result.diagnostics.precision, result.diagnostics.max_divergence)
```

The lower tolerance limit is machine epsilon for the selected solver precision.
`diagnostics.precision` and `metadata["solver"]["precision"]` record the mode.
The double solver uses two float64 cell buffers (16 bytes per native cell,
including ghost cells), replacing three float32 buffers (12 bytes per native
cell); other native arrays are unchanged. This mode reduces arithmetic error;
it does not remove model, grid, sampling or boundary sensitivity.

The embedded solver includes a correction to upstream QES's vertical divergence
scaling. This changes results where building parameterizations create vertical
flow, including street canyons. The original flat and one-building reference
arrays remain unchanged. See the [Stage 0 validation report](docs/stage0-validation.md)
for the reproduction, measured residuals and remaining boundary limitations.

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

## Check native refactors

`tools/compare_native_builds.py` builds the extension from a baseline revision
and from the working tree with identical settings, runs a fixed case matrix
against both (public `wind.run` paths, every parameterization flag combination,
runner reuse across directions and turbulence) and requires bitwise-identical
outputs. `--binaries` also requires byte-identical objects, for pure moves.

```sh
uv run --frozen python tools/compare_native_builds.py --baseline HEAD --backends openmp serial
```

## Regenerate executable references

Only reference tooling needs GDAL, NetCDF C/C++, compiled Boost.ProgramOptions
and Python netCDF4. On macOS: `brew install gdal netcdf netcdf-cxx boost`.
On Debian/Ubuntu install `libgdal-dev libnetcdf-dev libnetcdf-c++4-dev
libboost-program-options-dev pkg-config` in addition to the native build tools.

The generator builds standalone QES executables from the reference-only
`QES-Public` submodule (the embedding fork's `dtcc-embed` branch), so fetch it
first. The fork's recorded commit must be available on its remote.

```sh
git submodule update --init --recursive
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

GPL-3.0-only; see [LICENSE](LICENSE), [QES's license](src/qes_core/LICENSE) and
[NOTICE](NOTICE). The sdist contains the vendored QES sources and build files;
both distributions carry the licenses/notices. The upstream metadata discrepancy
has a [prepared report](docs/upstream-license-report.md).

Terrain sampling, cut cells, roof detail, vegetation, multiple conditions,
CUDA and public binary wheel distribution remain deferred. Turbulence export,
comfort and dataset integration follow the turbulence numerical acceptance gate.
`Domain::getDomainSize()`'s anisotropic-spacing correction belongs to the
terrain milestone; this implementation uses scalar spacing throughout.

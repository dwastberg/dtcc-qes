# Vertical-grid Stage A: explicit layers

Implemented on 2026-10-26 following [Stage 0](stage0-validation.md). The local
QES commit is `e0fb62e9fe5fffc8b4aef8f250f75f929ad27c13` on `dtcc-embed`.
No remote push was made. This delivery provides explicit CPU-grid construction;
the sensitivity/cost gate, new sampling, dataset options and automatic layer
generation remain subsequent stages.

## Public API and coordinate contract

```python
import numpy as np
from dtcc_qes import wind

faces = np.r_[np.arange(0, 10, 0.5), np.arange(10, 20), np.arange(20, 42, 2)]
spec = wind.VerticalGrid.from_faces(faces)
result = wind.run(city, speed=5, direction=270, resolution=2, vertical_grid=spec)
```

This grid ends at 40 m above the flat ground; the city must fit the existing
domain-clearance requirements. `resolution` sets constant x/y spacing. Omit
`vertical_grid` for the existing uniform cubic grid. `VerticalGrid` copies its
input into an immutable tuple and accepts 3–10,001 finite, strictly increasing
faces starting at zero. Non-monotonic thickness sequences are allowed for expert
explicit grids; no automatic growth or aspect-ratio limits are imposed here.

Native `dz_layers` are physical thicknesses in a copied float64 buffer. They
are narrowed to float32, accumulated sequentially, and used to construct actual
face/centre coordinates before the wind arrays are allocated. Core and bridge
validation checks positivity, finite coefficients, representable coordinates,
layer counts, index limits and roof clearance. Declared QES layers must exactly
match the domain; the solver also checks layer and horizontal-spacing identity.
The lower ghost mirrors the first physical thickness. Core `dz()` denotes the
minimum layer thickness. Cut cells and the wall log-law option remain rejected
on the explicit-layer path.

With explicit bounds, requested faces must match the requested physical height
before narrowing, allowing four float64 ULPs for subtraction in translated
global coordinates. Actual float32 endpoints can differ through accumulation;
they are returned rather than clipped or rescaled. Without explicit bounds,
the requested final face must cover the existing automatic minimum top. A shared
helper now defines that minimum for the city and existing dataset adapters.
The existing empty-city requirement for explicit bounds remains.

`WindResult.z_faces` owns physical float32 faces without ghosts, `z` contains
centres, and `dz` returns differences between effective faces. `resolution`
remains horizontal spacing. `vertical_uniform` uses equal solver thicknesses
before coordinate accumulation, so decimal uniform layers are not falsely
classified as stretched because of subtraction roundoff. Metadata records
requested/effective faces, mode, uniformity, extrema, growth/aspect ratios and
represented roof heights/errors. Requested geometry is not changed to align
every roof to a face.

Uniform anisotropic layers export to DTCC `VolumeGrid` with their true z extent.
Nonuniform layers reject that export rather than giving them uniform coordinates.
Use native result arrays at this stage. No new interpolation, slice, resampling
or automatic-grid API has been introduced.

## Verification

`tests/test_vertical_grid.py` checks configuration ownership, invalid input,
float32 collapse/overflow, logarithmic profiles at actual centres, cardinal
directions, translated geometry, allocation limits, metadata, explicit endpoint
matching, decimal grids and non-monotonic thickness sequences. It also verifies
that native buffers and configuration snapshots survive mutation and runner
destruction.

Explicit 2 m layers reproduce the legacy one-building solution **bitwise**,
including faces, centres, velocity, classifications and diagnostics. Existing
flat and one-building reference arrays are retained without regeneration.
Occupancy tests cover heights 7.99, 8.0, 8.25 and 8.5 m around fine-layer faces
and centres. Uniform 0.5 m layers with 2 m x/y spacing export with `(2,2,0.5)`
steps and a 40 m vertical extent.

`tests/native/check_vertical_grid.cpp` tests the core constructor directly,
including malformed layers and mode/declaration mismatches, unsupported wall
correction, solver/domain incompatibility, ghosts and the corrected independent
x/y spacing accessor. A stretched vertical-velocity injection meets the absolute
interior bound `1e-6 s^-1` on serial and OpenMP. OpenMP results are exactly
repeatable across 1, 2 and 4 threads and agree with serial within the stated
native comparison tolerance. The manufactured variable-volume flux oracle from
Stage 0 now uses the actual explicit-grid constructor.

The new canyon test uses the Stage 0 120 × 80 × 50 m domain and two 15 m
buildings, 2 m x/y spacing and default parameterizations. Layers are eight at
0.5 m, twelve at 1 m and seventeen at 2 m, totalling 37 layers and 50 m.
At 2,000 iterations with float32-epsilon multiplier tolerance:

| Backend | Interior maximum (s^-1) | Volume-weighted RMS (s^-1) | Prescribed top-band maximum (s^-1) |
| --- | --- | --- | --- |
| Serial | 8.46378e-5 | 3.02199e-6 | 0.114459 |
| OpenMP, 4 threads | 8.68589e-5 | 2.96522e-6 | 0.114459 |

Both pass the base dimensionless residual bounds with `Hmax/Uref = 3 s`.
This single-checkpoint test does not establish iterative velocity stability,
grid independence, experimental accuracy or relative performance. Those remain
the next gate's work. The large prescribed-top residual is still reported
separately and keeps domain-height sensitivity necessary.

## Parameterization audit finding

The enabled building functions already locate heights through `domain.z` and
`z_face`. Their unused scalar `dz` bindings were removed. A vortex-rooftop shell
search could read `z[k+1]` beyond the vector when a shell extended above the
domain. Its upper bound now checks the coordinate-vector size.

The regression uses a 48 × 48 × 10 m domain, layers
`[0.5,0.5,1,2,2,2,2]`, a `[16,30] × [16,30]` building with heights around
8 m, rooftop flag 2, and wind directions 0, 45, 90 and 270 degrees. Linking
the test against the original loop reproduces an AddressSanitizer
heap-buffer-overflow in `PolyBuilding::rooftop`; the corrected test passes.
This is a bounds correction, not new near-wall physics. It also applies to
uniform-grid cases with insufficient space for that search.

## Build and validation commands

Use the development environment and the build configurations documented in the
Stage 0 report. After building each configuration:

```sh
ctest --test-dir build/extension --output-on-failure
ctest --test-dir build/openmp --output-on-failure
build/extension/check_vertical_grid --report
OMP_NUM_THREADS=2 OMP_DYNAMIC=FALSE build/openmp/check_vertical_grid --report
ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 ctest --test-dir build/sanitizers --output-on-failure
cmake --build build/extension --target check_native_symbols
```

The full serial, OpenMP and ASan/UBSan native suites pass. The final expanded
explicit-grid target is also checked separately with ASan/UBSan. The known
dataset-registration test mismatch documented in Stage 0 remains outside this
feature; both CPU extensions pass 278 Python tests with that one test explicitly
deselected. Install each rebuilt
extension before testing its Python path. No CUDA build or execution was tested.

Packaging is checked by rebuilding a wheel from the source distribution,
checking required source files and licences, and running an isolated explicit
flat-grid solve from the wheel:

```sh
CMAKE_GENERATOR='Unix Makefiles' CMAKE_BUILD_PARALLEL_LEVEL=8 .venv/bin/python -m build --no-isolation --outdir build/stagea-artifacts -Ccmake.define.DTCC_QES_OPENMP=OFF
.venv/bin/python tools/check_artifacts.py build/stagea-artifacts
```

The next stage is the planned sensitivity/cost gate. Preserve identical physical
bounds, use the requested pedestrian height consistently, and compare grids at
matched residual and velocity accuracy. Stage A supplies that study's explicit
grids; it does not yet justify the proposed automatic growth factor or aspect
limit.

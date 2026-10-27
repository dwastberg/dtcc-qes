# Vertical-grid Stage B1 validation

Stage B1 adds `WindResult.sample` and `wind.preview_grid` for existing uniform
and explicit grids. Both use the effective physical coordinates established
in Stage A. This is an output/preparation milestone; automatic generation is
the next C1 prototype, with preset selection still dependent on C2 evidence.
See [the implementation plan](../DYNAMIC_VERTICAL_GRID.md) for the sequence.

## Public sampling contract

```python
from dtcc_qes import wind

result = wind.run(city, speed=5, direction=270, resolution=2,
                  vertical_grid=wind.VerticalGrid.from_faces(z_faces))
pedestrian = result.sample(height=1.5, method="linear")
velocity = pedestrian.velocity  # float64 (y, x, component), m/s
speed = pedestrian.speed        # (y, x), magnitude of mean velocity, m/s
valid = pedestrian.valid        # (y, x), boolean
```

`WindSample` owns its velocity, validity and x/y arrays. It records
`requested_height`, `sampled_height`, `method`, `origin` and `crs`. Sampling
does not mutate the result. Arrays remain editable and `speed` is derived from
the current sampled velocity. Flags are never interpolated or returned as a
continuous quantity.

| Case | Behavior |
| --- | --- |
| Default `method="nearest"` | Select the nearest effective centre; ties choose the lower index. |
| Nearest request between the ground/top face and endpoint centre | Clip to that endpoint centre; record its actual height. |
| Linear request between centres | Interpolate velocity components, then calculate magnitude. |
| Linear request exactly at a centre, including the first/last | Use that cell alone; a zero-weight solid or nonfinite neighbour has no effect. |
| Linear request within the physical domain but outside the centre range | Return all-invalid NaNs and `sampled_height=None`; no extrapolation. |
| Any contributing flag is 0 or 2, or velocity is nonfinite | Mark that point invalid and return a NaN vector/speed. Wake/cavity air flags remain valid. |
| Nonfinite/nonnumeric height, or height outside the physical domain | Raise `ValueError`. |

Heights are metres above flat ground, not global elevations. Requests and
effective centres are compared in float64; a distinct Python float must not
silently round onto a float32 centre. A stored float32 centre passed as a scalar
widens exactly. Legacy results constructed without `z_faces` derive the domain
top using canonical float32 accumulation of `resolution`.

Axes remain local float32 coordinates with no ghosts. Widen before adding a
large origin, for example:

```python
global_x = pedestrian.x.astype("float64") + pedestrian.origin[0]
global_y = pedestrian.y.astype("float64") + pedestrian.origin[1]
global_height = pedestrian.sampled_height + pedestrian.origin[2]
```

Check that `sampled_height` is available before computing global elevation.
Interpolation makes no prediction below the first centre, resolves no missing
geometry, and establishes no physical accuracy by itself.

## Public preview contract

```python
preview = wind.preview_grid(city, resolution=2, vertical_grid=specification)
print(preview.shape, preview.cell_count)
print(preview.z_faces, preview.z, preview.dz)
print(preview.domain["vertical_grid"]["roof_representation"])
```

`GridPreview` contains owned x/y/z axes, z faces, solver layer thicknesses,
origin, CRS, effective resolution, domain metadata and terrain metadata.
Properties expose shape `(nz, ny, nx)`, cell count, effective thicknesses,
adjacent growth ratios and both `resolution / dz` and `dz / resolution` aspect
ratios. Ratios use `solver_dz`, the float32 thickness before accumulation;
`dz` measures separations between accumulated faces. Their small decimal-grid
differences remain visible rather than silently equated.

Preview and `run` share city extraction and domain preparation. This preserves
CRS/translation handling, terrain/height policy, requested and effective bounds,
roof diagnostics, and cell/index limits. Reference height and roughness use the
same validation; reference height constrains automatic bounds. Preview needs
no wind condition or solver settings. It allocates geometry and coordinate
vectors, and small grid/model configuration objects, without constructing a
native wind runner or allocating flow arrays. It is not a prepared simulation
and does not estimate occupancy, numerical accuracy or peak process memory.

A validation edge case was found while comparing the two paths. A resolution
at `sqrt(1 / float32_max)` satisfies the old float64 range check but narrows to
a float32 spacing whose reciprocal square overflows. Preview previously
accepted it, while native preparation rejected it. The shared grid validator
now evaluates the actual narrowed square and reciprocal before geometry/flow
allocation. Ordinary uniform results retain their existing numerical path.

## Validation

`tests/test_sampling.py` verifies:

- An affine three-component field on nonuniform layers, including y/x ordering,
  physical height, units and frame information.
- Opposite equal-speed vectors interpolating to zero velocity, to catch
  interpolation of magnitudes instead of components.
- Both contributing solids, flags 0/2, air parameterization flags, nonfinite
  data, exact-centre endpoint/zero-weight cases, float64 neighbouring requests,
  nearest clipping/ties, invalid requests, ownership and legacy face fallback.
- Public sampling against archived native study planes for the serial tower
  case with uniform 0.5 m and hand-built stretched grids. Matching iteration
  counts, masks and vectors are checked; tolerance allows the archive's decimal
  serialization. These two tests are skipped for the OpenMP extension because
  the archive records serial node ordering.
- Sampling a broadcast virtual volume of 9,000 × 64 × 64 cells with less than
  3 MB of traced allocations, guarding against full-volume masks/copies.

`tests/test_grid_preview.py` compares preview with real solves for uniform and
explicit grids, decimal spacing, non-monotonic layers, translated/CRS frames,
automatic bounds and roof diagnostics. It checks shared option failures and
the coefficient-limit regression before flow allocation. A preview of
200 million cells uses less than 3 MB of traced Python/NumPy allocations with
native runner construction forbidden. These limits guard the allocation shape;
they are not claims about solver peak RSS.

The self-contained [example](../examples/vertical_grid.py) compares uniform
0.5 m layers with a 34-layer stretched grid on the same geometry, wind and
bounds. It previews thickness versus height and samples both at 1.5 m, reporting
P95 normalized speed differences on common fluid points. Cell-count savings
are not presented as measured runtime savings.

The serial Python checks pass 400 tests, with the known independent
`test_explicit_import_registration` mismatch explicitly deselected. Against the
OpenMP extension, 398 pass, two serial-archive comparisons are skipped, and the
same registration test is deselected. The existing reference, city/dataset and
comfort tests are included. There are no native solver or bridge changes in B1;
the preceding native/sanitizer evidence remains in the
[diagnostic report](vertical-grid-diagnosis.md).

To reproduce serial checks:

```sh
.venv/bin/python -m pytest -q -k 'not test_explicit_import_registration'
.venv/bin/python examples/vertical_grid.py
```

For OpenMP validation, load the built `build/openmp/_qes*.so` as
`dtcc_qes._qes` before importing the public package and running pytest; verify
`openmp_enabled=True` and the extension path. Both backends use the same Python
sampling and preview code.

```sh
.venv/bin/python - <<'PY'
import importlib.util
from pathlib import Path
import sys
path = next(Path('build/openmp').glob('_qes*.so')).resolve()
spec = importlib.util.spec_from_file_location('dtcc_qes._qes', path)
module = importlib.util.module_from_spec(spec)
sys.modules['dtcc_qes._qes'] = module
spec.loader.exec_module(module)
import dtcc_qes
dtcc_qes._qes = module
from dtcc_qes import wind
assert module.openmp_enabled and wind._qes is module
print(module.__file__)
import pytest
raise SystemExit(pytest.main(['-q', '-k', 'not test_explicit_import_registration']))
PY
```

Source/wheel license and content checks pass, including the new example, tests
and this report. A serial wheel rebuilt from the source distribution passes an
isolated translated-domain smoke test of both APIs, linear interpolation,
nearest/endpoints, preview metadata, and zero flat-flow divergence. Native
runner construction is forbidden during a second preview. Python modules and
the extension were verified to load from the extracted wheel rather than the
editable checkout.

## Decision and remaining scope

B1 is complete. Proceed to the C1 automatic-grid prototype and preview
extension, retaining provisional policy constants until C2. Dataset vertical
grid options and slice integration remain B2 work; uniform resampling remains
deferred. Direct nonuniform `to_dtcc()` conversion still rejects unsupported
geometry, now pointing to `sample()` and native arrays.

The failed fine-grid references, study-only precision remedy and prescribed
top-band limitation remain as documented. Sampling and preview do not change
those conclusions or select an automatic preset.

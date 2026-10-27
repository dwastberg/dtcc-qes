# Automatic vertical-grid prototype (C1)

C1 implements geometry-based automatic layers and extends preview/run to
resolve them. It establishes construction, feasibility and coordinate
correctness. The candidate settings remain **unvalidated for pedestrian-wind
accuracy and cost**. The next milestone is C2, beginning with domain-height
and horizontal-resolution controls. See [the plan](../DYNAMIC_VERTICAL_GRID.md).

## API and provenance

```python
from dtcc_qes import wind

specification = wind.VerticalGrid.auto(
    pedestrian_height=1.5,
    growth_rate=1.15,
    min_layer_thickness=None,
    max_aspect_ratio=8,
    first_layer_thickness=None,
    fine_region_height=None,
    upper_layer_cap=None,
)
preview = wind.preview_grid(city, resolution=2, vertical_grid=specification)
result = wind.run(city, speed=5, direction=270, resolution=2,
                  vertical_grid=specification)
pedestrian = result.sample(1.5, method="linear")
```

All lengths are metres above flat ground. The specification is immutable;
automatic `faces` is unresolved (`None`) and reading `layers` directs the
caller to preview/run. Generation depends on geometry, the selected domain top
and effective horizontal resolution, not the solved field or wind direction/
speed. Reference height still affects automatic bounds through the existing
domain rules. Uniform mode remains the default and explicit faces retain their
existing path.

`first_layer_thickness` is a preferred fine-layer target. The joint integer
count and constraints determine its actual value. The fine-region override
must reach at least the pedestrian height. Settings must be positive and
finite, growth must be in `(1, 1.20]`, and aspect limit must be at least one.
The resolved base minimum cannot exceed resolution and the upper cap cannot
be below it. Equivalent values affected only by float32 narrowing resolve to
the same native spacing; incompatible overrides are rejected, not relaxed.

The domain's `vertical_grid` record includes:

- `mode="auto"`, `generator_version="auto-v1-prototype"` and
  `policy_status="prototype_unvalidated"`.
- Requested settings, resolved constraints, fine-layer count and requested/
  planned/effective fine-band heights, including target/endpoint adjustments.
- Float64 planned faces, native `solver_layer_thicknesses`, effective float32
  faces and the existing growth/aspect/roof diagnostics. Preview exposes the
  same native thicknesses as `solver_dz` and face separations as `dz`.
- Requested/planned/effective top, coordinate error and its accumulation bound.
- Actual pedestrian brackets, indices, upper weight, third-centre height and
  analytic flat-profile exact/interpolated K and bias. The analytic control uses
  effective reference height/roughness with float64 logarithmic evaluation;
  it is not an estimate of disturbed urban-flow error.

## Fine band and caps

The prototype implements the plan's proposed target, minimum/aspect floor,
fine-region extent, building/roof caps and upper cap. It evaluates building
constraints at native float32 heights, consistent with occupancy. Sorting
height thresholds makes lookup independent of building order without scanning
every building for every layer. All retained positive heights contribute,
including duplicates and shallow structures.

For a fixed requested fine-band height, select the feasible equal-layer count
closest to the target thickness. Ties within float64 arithmetic roundoff favor
fewer layers. If no integer count satisfies the thickness interval, extend the
fine band upward using the minimum thickness and record that adjustment.

With default settings, no tighter building cap and a sufficiently tall domain:

| Resolution | Fine layers | Approximate solver thickness |
| --- | --- | --- |
| 2 m | 7 | 0.428571 m |
| 4 m | 6 | 0.5 m |
| 4.5 m | 5 | 0.6 m |
| 5 m | Rejected | Aspect floor 0.625 m exceeds pedestrian limit 0.6 m. |
| 0.1 m | 30 | 0.1 m; no artificial 0.2 m minimum. |

The empty-interval regression (`r=2.24 m`, building height 2.9 m) selects
11 layers near 0.28 m and a planned fine band near 3.08 m instead of 3 m. The
fine band cannot silently shorten or exceed the domain top.

After fitting, native coefficients and face/centre ordering are checked again.
The actual third centre must be at or below the pedestrian plane, and the plane
must be bracketed by physical centres. Roof occupancy/representation uses
effective coordinates and reports source-relative error, without forcing roofs
onto faces.

## Endpoint fitting choice

A single growth-rate bisection is unnecessary and can encounter jumps when a
cell's lower face passes a roof-buffer threshold. The prototype instead uses:

1. Preserve the selected equal fine layers.
2. Follow maximal allowed growth/caps until reaching the selected top. This
   finds the minimum upper count because the caps are nondecreasing: a smaller
   feasible prefix cannot overtake the maximal prefix.
3. Reject if that count times the fine thickness exceeds the remaining height.
   More cells would only increase this minimum, so no count fits while keeping
   the fine band and nondecreasing thicknesses.
4. Generate that many cells with
   `min(previous * growth, cap(lower_face), remaining_height / remaining_count)`.
   Once the average binds, a constant tail fills the top. Its first layer meets
   growth/cap limits and subsequent caps cannot decrease. Earlier upper layers
   are adjusted when necessary; the tail can be one or several cells.

For example, six 0.5 m fine layers ending at 3 m can reach a 4.1 m top using
two 0.55 m upper layers, preserving both monotonicity and growth. A 3.6 m top
is infeasible for the same fine band and growth 1.15: one upper layer is at
most 0.575 m while two are at least 1 m. The generator raises an actionable
error rather than adding a thin remainder or changing near-ground spacing.

Work is bounded by the native 10,000-layer limit. Total physical-cell and
staggered-face index limits use the generated count before native flow
allocation. A smaller `max_cells` does not trigger automatic coarsening.

## Float32 clarification

The plan fits the selected top in float64. Canonical native accumulation can
shift its effective endpoint; exact equality to an arbitrary float64 top is
not promised. The absolute error bound is `gamma_(n+1) * top`, with
`u = float32_eps / 2` and `gamma_k = k*u / (1-k*u)`, covering layer narrowing
and the sequential sum. Requested and effective extents remain distinct.

Constraint checks use narrowed solver thicknesses with a relative tolerance
of `8 * float32_eps` for operand narrowing, not a tolerance for accepting
materially incompatible user settings. Faces and centres must remain strictly
increasing and coefficients positive/finite. As in B1, accumulated face
separations can differ slightly from solver thicknesses.

Planning respects both planned and effective lower faces; final caps are
checked at effective lower faces. With 0.1 m horizontal spacing and a 2 m
building, the planned fine band reaches 3 m but the native face is near
2.9999993 m. Its next cell must retain the building cap until it actually
crosses `1.5 * H`. The regression checks that rounding cannot release the cap
early.

## Validation and reproduction

`tests/test_auto_grid.py` covers policy examples, the empty count interval,
feasible constant-tail fitting and infeasible slivers, fine-only domains,
pedestrian brackets, building-cap release, order/duplicate independence,
small buildings, target ties, invalid/incompatible settings, frozen snapshots,
layer/cell/index limits and effective metadata serialization. A matrix of 75
constructed cases spans five resolutions, five height sets, three growth rates
and non-integer tops, checking constraints independently from the fitting loop.

Integration tests compare preview/solve coordinates, the analytic flat profile,
translated urban occupancy, roof diagnostics and allocation rejection. The
[executable example](../examples/automatic_vertical_grid.py) previews and solves
one synthetic building and samples at 1.5 m. These tests do not measure the
automatic policy's urban accuracy or time to a common residual criterion.

Native flat-profile checks cover 0.1, 2 and 4.5 m horizontal spacing. On this
host, the 0.1 and 4.5 m cases give small nonzero residuals on both automatic and
equivalent explicit grids, with bitwise-identical velocities and diagnostics
between the two paths. The serial 0.1 m maximum is approximately
`1.155e-5 s^-1`, or `2.31e-5` at the existing empty-city scale `10 m / 5 m/s`;
the maximum analytic u-profile discrepancy is about `6.36e-7 m/s`. These checks
use the unchanged declared residual bounds rather than assuming exact zero.
They are not a new full iteration-stability certification.

```sh
.venv/bin/python -m pytest tests/test_auto_grid.py -q
.venv/bin/python -m pytest -q -k 'not test_explicit_import_registration'
.venv/bin/python examples/automatic_vertical_grid.py
```

Use the [B1 report's OpenMP loading procedure](stageb1-validation.md) to run the
same Python suite against `build/openmp/_qes*.so` and verify its backend/path.
The generator and preview remain Python code shared by both backends.

The final serial suite passes **527 tests**. Against the OpenMP extension,
**525 pass and two serial-archive comparisons are skipped**. The pre-existing
`test_explicit_import_registration` mismatch is explicitly deselected on both.
Native solver/bridge sources are unchanged by C1; this milestone does not
claim a new sanitizer or full residual/performance gate result.

Source/wheel content and license checks pass, including the new generator,
tests, report and example. A serial wheel rebuilt from the source distribution
passes an isolated translated-domain smoke check of automatic preview/run,
coordinate and metadata equality, pedestrian sampling, endpoint bounds and
cell-limit rejection. Native runner construction is forbidden during a second
preview. Package modules and the extension were verified to load from the
extracted wheel rather than the editable checkout.

## Next decision

C1 is complete. Start C2 with domain-height and finer-x/y controls before
broad parameter tuning. Compare actual generated grids against accepted finer
references and the cheapest uniform grid satisfying the same error budget.
Assess centre alignment, roof buffers, upper caps, aspect limits and memory/
runtime before selecting any preset. If a precision remedy is needed, it
requires its separate from-zero and full-gate validation.

The failed fine-grid references, top-boundary limitation and physical-model
limitations remain. B2 dataset integration and optional uniform resampling
remain later milestones.

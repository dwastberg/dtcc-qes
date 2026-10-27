# Turbulence numerical changes and reference provenance

Task 1A, 2026-10-27. QES repair:
`2df34fc85c6e859d7c8f3bd4aad3975daa7d81d9`, based on Task 1 revision
`514d91cdc1bfc220a17af102df2b267cdc0c2c9e`.

This records the numerical exceptions that Task 3 must account for when it
generates standalone reference fixtures. Audited-fork parity fixtures have not
yet been generated. Exact wind-only references remain required. Implementation
checks below do not establish physical accuracy for pedestrian gusts.

## Corrected stress rotation

Let `n = (c, s, 0)` be the horizontal flow direction sampled in a column,
`m = (-s, c, 0)` its crosswind direction, and `Q = [n m ez]` the matrix whose
columns are those vectors in Cartesian coordinates. The transforms are

```text
tau_wind = Q^T tau_cartesian Q
tau_cartesian = Q tau_wind Q^T
```

The previous implementation applied `Q tau Q^T` on entry and the opposite
transform on return. Scaling the normal components between these transforms
therefore aligned the anisotropy incorrectly for oblique flow.

The repair normalizes the original staggered horizontal velocity pair in
float64 to obtain `(c, s)`. Orthogonal inverses use transposes. The same
QES normal-component scaling, absolute values and subsequent component caps
remain in place. Roundoff differences can occur from replacing float32 angles,
trigonometric evaluation and generic inversion. Do not promise bitwise
unchanged stress for every cardinal-wind building case: its local reference
directions can be oblique too.

An independent oracle constructs the full tensor from streamwise, crosswind
and vertical dyads for the uncapped manufactured flow
`U(z) = (10 + 0.1 z) (cos(theta), sin(theta), 0)` on a 2 m grid. At z = 9 m,
the analytic streamwise standard deviation is 0.9 m/s.

| Cartesian flow heading | Before Task 1A | After Task 1A | Expected |
| --- | ---: | ---: | ---: |
| 0° | 0.900001 | 0.900001 | 0.9 m/s |
| 30° | 0.768960 | 0.900000 | 0.9 m/s |
| 45° | 0.720000 | 0.900000 | 0.9 m/s |
| 90° | 0.900001 | 0.900001 | 0.9 m/s |

The regression also covers reversed headings 180°, 210°, 225° and 270°,
all six tensor components on physical levels 2–19, uncapped conditions, finite
native fields and preservation of the input wind arrays. Tolerances are
rtol 1e-5 and atol 1e-7. These headings are Cartesian flow directions, not
meteorological wind-from inputs.

## Direction sampling and fallback

Usable preferred samples retain QES's original index: the lower bound of
`15 m + terrain` on ghost-inclusive `z_face`. The sampled cell must be physical
and fluid (neither flag 0 nor 2), and its original staggered `(u, v)` pair must
have finite, nonzero horizontal magnitude. No arbitrary low-speed floor is
introduced, and horizontal velocities are not newly averaged onto cell centres.

For an unusable preferred sample:

1. Search physical fluid levels in that column by distance of their effective
   **z cell centre** from `15 m + terrain`. Horizontal velocities live at these
   vertical centres. Prefer the higher centre when distances tie. Search by
   physical distance, including on nonuniform grids.
2. If no usable horizontal velocity exists anywhere in that column, use the
   fixed Cartesian +x axis. This is a deterministic fallback, not an observed
   wind direction. Calm stress remains zero and finite.

Direction is resolved once per computed column per stress calculation.
`getRotationFallbackColumns()` counts distinct columns requiring either
fallback, including wholly calm columns, and resets on every stress calculation
and hence every normal `run()`. It counts only columns visited through
`icellfluid`. The temporary direction cache uses about 16 bytes per horizontal
cell; it is separate from the persistent turbulence cell arrays.

Tests cover building/terrain flags, zero and nonfinite reference velocities,
all-level calm columns, restoration of a valid direction, tie preference,
terrain-relative reference height and nonuniform spacing where the closest
velocity centre is not adjacent to the original reference index. A domain top
exactly at 15 m exercises the face-without-cell-flag boundary under ASan.

These fallback cases are explicit upstream parity exceptions. They must be
reported in future bridge metadata, rather than silently counted as measured
15 m directions.

## Raw stress and validity

`src/cpp/stress_validity.h` is a QES-free numerical helper for future extraction
and derived statistics. It does not alter QES arrays or make tensors realizable.
It interprets stored float32 components in the order
`xx, xy, xz, yy, yz, zz`, evaluates eigenvalues in float64 using normalized,
bounded symmetric Jacobi rotations, and uses

```text
radius = max(abs(eigenvalues))
tolerance = 32 * eps(float32) * radius
valid = finite(tensor) and lambda_min >= -tolerance
```

There is no absolute variance floor. Finite zero tensors are valid with zero
tolerance. Nonfinite tensors and a failure to finish diagonalization are
invalid. The helper allocates no per-cell matrices on the heap.

Projection first requires a valid tensor and a finite, nonzero mean velocity.
An indefinite tensor gives NaN even if the requested projection is positive.
A negative projection rounds to zero only within the tolerance of a valid
tensor. The helper normalizes direction with `hypot` to handle very small and
large finite speeds. No `makeRealizable` call or raw eigenvalue clipping is
introduced. Coverage (`computed`) remains a separate concern for Task 2.

On the reviewed 40×30×20 uniform-grid 8 m building case, at 5 m/s and 270°
meteorological inflow, the corrected model produced 20,116 computed cells,
90 invalid tensors by this policy and 6 negative streamwise projections.
The native check preserves those raw tensors, masks their derived variance,
and verifies the same validity masks and stress ×4 when the frozen solved wind
is scaled ×2. The earlier review's 91 principal-minor failures used a different
diagnostic threshold; these counts are not directly interchangeable and are
not immutable reference values for subsequent model changes.

Tasks 2 and 5 must consume this policy when returning masks and derived fields.
The helper itself does not expose a Python turbulence API.

## Verification

Host/compiler: AppleClang 17.0.0, macOS arm64, OpenMP off. Native builds use
the isolated worktree and its no-I/O header traps. The interpreter used for
CMake and the NumPy check was the existing Python 3.13 environment, read-only.

```sh
cmake --build build/native --parallel 8
cmake --build build/native --target check_native_symbols
ctest --test-dir build/native --output-on-failure
cmake --build build/asan --target check_turbulence --parallel 6
ctest --test-dir build/asan -R native_turbulence --output-on-failure
python tools/check_stress_validity.py --cases 5000 --seed 20261027
```

- Full Release suite: 24/24 passed; no-I/O symbol audit passed.
- Debug ASan/UBSan turbulence suite: 13/13 passed, with no sanitizer reports.
  The unrelated full Debug suite was not repeated for Task 1A; its 19/19 Task 1
  result and existing Debug assertion-symbol audit limitation remain recorded
  in the plan.
- Independent NumPy 2.5.4 check: 5,000 stored float32 tensors, including
  near-threshold eigenvalues, at scales from 1e-30 to 1e30; zero validity
  mismatches. Maximum minimum-eigenvalue error divided by spectral radius was
  `1.0544456312324755e-15` against NumPy's float64 eigensolver. The repository
  tool compiles the current header and emits its SHA-256 with the result.

The serial wall-distance repair (Task 1B), standalone audited reference
generation (Task 3), Python bindings/results, benchmark gate and physical gust
validation are still outstanding.

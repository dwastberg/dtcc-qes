# S1a: condition-state corrections

Completed 2026-10-29. Every supported condition now produces the same output
through a reused runner as through a freshly prepared runner. S1a resets the
rooftop-vortex decision and rejects model configurations that require a disabled
wake calculation. Solver expressions, defaults, storage and ordering are unchanged.

## Corrections

`PolygonWake` only sets `PolyBuilding::rooftop_flag` when it finds an eligible
face. Previously, other directions could inherit a preceding condition's flag;
`Rooftop` then selected a different model from a fresh building. The new virtual
`Building::resetConditionState` hook runs for every building before any
parameterization. The polygon override restores the fresh value, zero. This
also applies to retries after initialization or numerical failure. The existing
height order and all parameterization arithmetic remain unchanged.

`BuildingParameterizations::validateWakeDependencies` rejects `wake_flag=0`
when any rooftop, street-canyon or sidewall model is enabled. Those models read
`width_eff` or `Lr` computed by the wake calculation; the old combinations could
silently omit models or reach NaN-to-integer conversion. Validation runs in
`ModelInputs` before native geometry construction, in the direct core
constructor before field allocation, and before core parameterizations (whose
settings can be mutated by internal callers). Failed runner preparation retains
the previous geometry. The rule applies even to an empty geometry so model
validity is independent of the current building list.

Wake-free calculations remain supported with all three dependent models off,
including all four independent upwind-cavity settings. `high_rise_flag` only
affects an active wake calculation and introduces no separate consumer when
wake is off. The public `wind.run` defaults enable wake, so ordinary calls keep
their existing fresh-run results.

## State audit

The audit covers the supported flat-ground, stair-step polygon pipeline and the
two exposed turbulence methods. It found one persistent condition decision
requiring reset, plus the wake dependencies above:

| State | Initialization / ownership |
| --- | --- |
| Footprints, height, bounds, centers, rectangle detection, building order | Prepared geometry; unchanged between conditions. |
| `rooftop_flag` | Was conditionally assigned; now reset before every condition. |
| `u0_h`, `v0_h`, `upwind_dir` | Recomputed from the current field by each consuming model. |
| `xi`, `yi`, `xf1/yf1/xf2/yf2`, `upwind_rel_dir` | Each model overwrites the entries it consumes; unused closing entries do not carry decisions. |
| `polygon_area`, `x1/x2/y1/y2`, `width_eff`, `length_eff`, aspect ratios, `Lr` | Reset/recomputed by wake before dependent models; validated dependency prevents reading unavailable values. |
| `small_dimension`, `long_dimension` | Assigned inside each eligible consuming block before use. |
| Geometry cell flags, condition flags, original and corrected faces | Original flags restored; original faces zeroed and profiled each condition; corrected faces reconstructed from the current originals. |
| RHS, multipliers, previous multipliers, iteration/change/termination | Reset by `begin`; runner discards workspaces on failure and precision changes. |
| Turbulence geometry/mixing lengths | Prepared once; supported local mixing lengths remain geometry-dependent. |
| Turbulence reference speed/friction, derivatives, viscosity, stresses, fallback count | Recomputed per run over the prepared fluid domain; extracted current masks and output ownership remain unchanged. |

Non-local turbulence mixing is not exposed by the supported API and is not
qualified by this audit. The separate StreetCanyon solid-cell relabeling question
and the unused street-intersection setting remain model issues outside S1a.
No new public reuse or continuation API is introduced.

## Verification and exact changes

The regression tests were first run against the preserved S1 module and failed
on reused rooftop-vortex conditions in float32, float64 and stretched geometry.
The archived reproduction also compares every direction with a fresh runner.
After the correction, all 24 new condition-state Python tests pass. They cover
both precisions, uniform/stretched grids, wind-only and both turbulence methods,
direction sequences, precision switches, failed preparation and retry. They
compare array dtype, shape and bytes, every diagnostic and all turbulence fields.

A finite extreme inflow injects overflow into the actual float32 iteration,
which raises `Non-finite Lagrange multiplier change`; subsequent normal solves
in either precision match fresh results. This exercises the runner's real
numerical-failure cleanup without a production fault hook. Separate failures
after rooftop initialization verify that the next condition resets the rooftop
decision. Native lifecycle and safety tests cover the same state transition and
direct-core dependency rejection under ASan/UBSan.

The historical 429-case matrix remains fixed for comparison. Against the
[S1 source snapshot](data/solver-control-s1/manifest.json), exactly these cases
change for serial and OpenMP teams 1, 2, 4 and 8:

| Case under `native/reuse/r2/` | Direction | Precision |
| --- | --- | --- |
| `1` | 45° | float32 |
| `2` | 33° | float32 |
| `3` | 300° | float32 |
| `4` | 33° | float32 |
| `5` | 225° | float32 |
| `6` | 45° | float32 |
| `float64` | 33° | float64 |

For each case the changed records are `velocity`, `cell_flags` and
`diagnostics/scalars`: **21 of 3,872 records**, with **422 of 429 cases unchanged**.
There are no other changed records. The normal strict comparator intentionally
returns failure against S1; its report is archived and its entire difference
list is checked against this exact set. No broad prefix exemption was added.
Input rejection and valid wake-free runs are tested separately because the
historical matrix excluded `wake_flag=0`.

OpenMP teams agree bitwise. Serial/OpenMP still have 888 expected record
differences because their sweep ordering remains different. A second strict
comparison against the corrected source snapshot passes all 429 cases in both
backends and all four OpenMP teams.

| Check | Result |
| --- | --- |
| Release native tests, OpenMP / serial | 43 / 40 passed |
| ASan/UBSan native tests, OpenMP | 43 passed |
| Python suite, OpenMP | 979 passed, 18 skipped |
| Python suite, serial | 997 passed |
| Native symbol audits, all three builds | Passed |
| Wheel and sdist contents; packaged-wheel condition-state tests | Passed |
| Preserved S0/S1 evidence and source hashes | Unchanged |

## Corrected baseline and next step

The corrected baseline is `sources.tar.gz` in the
[S1a evidence manifest](data/solver-control-s1a/manifest.json), identified by:

```text
sha256:6fcdfab1abe30e254721495d2fe453f9e4c7eb89be89421df29eb44663e08d76
```

The workspace already contained the uncommitted S0/S1 work and other study
changes. This is a reproducible source identity, not a claimed git revision.
`compare_native_builds.py` now accepts an immutable source archive as well as a
git revision; archive extraction uses the standard data filter and its cache
is keyed by the complete SHA-256. S2 can use:

```sh
.venv/bin/python tools/compare_native_builds.py \
  --baseline-archive docs/data/solver-control-s1a/sources.tar.gz \
  --thread-counts 1 2 4 8 --backend-pair --report build/s2-parity.json
```

Record the eventual commit as an additional identity when these changes are
committed. Preserve the existing S0/S1 records. Source snapshots and test
reports establish implementation behavior on the recorded compiler/machine,
not physical-model accuracy or a cross-compiler guarantee.

S1a's prerequisites are satisfied. The next implementation is S2: fuse change
measurement, compact the operator with a checked fallback, then reduce unused
allocations and output copies. Keep separate bitwise gates and bounded
timing/memory measurements for each change. The serial ordering change retains
its separate backend-parity gate. No S2 work is included here.

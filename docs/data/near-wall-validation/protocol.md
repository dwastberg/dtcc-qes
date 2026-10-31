# Bounded near-wall sampling validation

## Protocol fixed before new measurements

The target remains point velocity at 1.5 and 1.75 m above flat ground, with
speed defined as the magnitude of the interpolated mean vector. A spatial
average would be a different observable and is not introduced to reduce an
observed error. Existing full-region failures and original thresholds remain.

This diagnosis retains the tower geometry, 64 m top, production flags, frozen
42/128-layer z families, world sensor (5,5), Uref=5 m/s and three fixed points
(27,21), (21,23), (51,35). Initialization probes compare x/y=1, 0.5, 0.25 m at
160 m extent for both families and winds. Sidewall-off and all-empirical-off
initialization controls use the automatic family and 270 degrees. These are
diagnostics, not alternative production settings or accepted fine references.

Record raw staggered face values, incident-cell flags, centred values and their
coordinates at every contributing point. Compare the existing centred sampler
with direct component interpolation on each component's native staggered grid.
Both require finite positive-weight support, no extrapolation, and a fluid
query cell. Direct sampling permits a solid/fluid boundary face (its imposed
normal velocity is part of the discrete field), rejects faces with no incident
fluid cell, and never replaces missing values or renormalizes weights.

Before field comparisons, test affine and curved manufactured fields, exact
support positions, invalid solid support and a wall-normal profile. A direct
sampler is a diagnostic candidate, not a public API change. Its final-field
test re-executes the accepted 160 m / automatic / 270-degree cases at 1 and
0.5 m using their archived final fixed-sweep budgets. Existing full-plane
outputs and residuals must match the accepted archive before new face data is
used. Existing N/2N/4N certification is reused only after that parity check;
these executions do not certify a new grid or an alternate sampler's iterative
stability. Acceptance of an alternate sampler would require its own stability
and spatial validation at every required case.

Decompose the final vector change into initialization change plus change of
the projection correction. Do not add speed magnitudes or infer causality from
a single component. Report both samplers at all three points and both heights,
including adverse changes. A replacement is not justified merely by reducing
one discrepancy. Preserve the 5% relative / 0.05 absolute low-speed diagnostic
budget and report magnitude differences separately from vector differences.

Use at most two probe workers and one solved diagnostic worker at a time.
The largest initial probe has 52,428,800 physical cells (160 m / 0.25 m /
128 layers); a 60-million allocation guard accommodates this deliberate
overrun of the soft target on this 51.5 GB host. No public output volumes are
allocated. Estimate native arrays and record RSS before extrapolating costs.
No 0.25 m full-solve matrix is authorized by this protocol: decide whether a
selected finer reference is scientifically useful from the completed diagnosis.

The historical study files remain immutable. New diagnostics live in separate
tools and archives. Region-specific summaries must exclude the three 1 m
wall-distance checks from the 4 m setback region; full-region checks remain
mandatory. Neither region is promoted to a validated comfort preset.

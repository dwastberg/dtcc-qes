# Surrey roughness-transition geometry benchmark, version 1

> Historical research protocol/results, retained from `54ccb39`. Reproduction
> commands with research-only build paths describe that revision. The portable
> tools and current integration qualification are documented in
> [REFERENCE_INTEGRATION_RESULTS.md](../docs/REFERENCE_INTEGRATION_RESULTS.md).


This is the next stage after the frozen [background-profile benchmark](SURREY_BACKGROUND_RESULTS.md).
The [settings](specifications/surrey_transition_v1.json) freeze ten controls
before measured downstream errors are examined. There is no coefficient fitting
or promotion of a physics model. Preserve the background archive and native
binary so that geometry, rather than a code change, is the principal new factor.

## Reconstruction and uncertainty

The paper's section 3.2 explicitly describes these measurements as Suburban to
Urban adjustment **without the tall-building cluster**. Use a regular array
of 70 mm streamwise × 140 mm lateral × 70 mm high blocks, with 70 mm clear
gaps: streamwise/lateral pitches are 140/210 mm. The array's first upstream
face is x-hat=0. Preserve x-hat=x+735 mm and all original measurement locations.
No gap for the absent tall cluster is introduced into the regular array.

The paper's Figure 2 suggests y=0 is a street centre. The primary reconstruction
therefore has block centres at y=(n+1/2)*210 mm. A second reconstruction puts
block centres at y=n*210 mm. This half-pitch shift is a geometry sensitivity,
not a choice selected for a better measurement fit. The supplied files do not
give an explicit roughness-only CAD layout; exact phase remains unconfirmed.

The 20 mm Suburban roughness has conflicting spacing descriptions between the
paper and readme, and its small-element streamwise thickness is not specified.
Do not invent it. Represent its developed upstream effect by the measured
Suburban U/V profile, normalized by each recorded reference speed, with scalar
ground z0=1.9 mm. Impose this same profile on every case. The -10 station is an
input/reference-drift control for U/V, not independent mean-flow validation;
its measured variances remain prediction targets. Do not prescribe measured k
or enable incoming-energy transport. All downstream U/V/W and variance rows
are held out of model inputs.

Blocks fill the retained numerical patch, leaving at least 70 mm clearance to
its boundaries. The primary domain is x-hat=-840 to 2240 mm, y=±560 mm.
The street phase has four lateral rows and sixteen streamwise rows; the block
phase has five lateral rows. This finite-patch edge difference is disclosed
and assessed with the wider street case, not treated as periodic geometry.
There are no tunnel side walls or spires. The raw geometries and plans must
show every block, domain edge and measurement location.

## Controlled runs

Use 17.5 and 8.75 mm spacing, giving four/eight cells across the 70 mm block
height and clear gap. Both phases' edges and all block heights align to the
nominal grids. Use canonical exposed-face geometry with 0.1 mm cleaning detail.
Verify the actual solid mask and volume against an independent rectangular
union; record effective roof/edge coordinates rather than relying on inputs.

Run empty-domain, street-phase and block-phase cases at both spacings. Four
additional coarse street controls widen the domain/array to y=±980 mm, extend
streamwise bounds to -1120/2800 mm, use the experimental tunnel height of 1.5 m
for a wind-only ceiling-height sensitivity, and disable empirical building
parameterizations to retain solid geometry plus mass correction alone.

Turbulence runs retain the current 16 m graded numerical extension required by
the fixed 15 m rotation reference; fine layers end at 0.84 m. The 1.5 m-height
control has no turbulence calculation and cannot score variance predictions.
It tests mean-flow sensitivity to that extension, not a complete tunnel-wall
reconstruction. Upper means are held at the 750 mm profile endpoint. Native
morphometric turbulence reference/cap parameters change when buildings are
present; report them explicitly as part of the model's geometry response.

Use the default height mixing length, legacy covariance and empirical model
flags, with 1 mm wall roughness retained as an untuned model setting. Use
float64 projection, tolerance 1e-10, at most 24,000 iterations, cooperative
120 s solve budgets and separate 180 s worker deadlines. Record checkpoint
receptor histories, convergence, timing, memory and mass diagnostics. These
budget limits are execution bounds, not numerical acceptance criteria.

## Analysis and execution guards

Use all 101 fixed observation IDs and the background benchmark's normalization,
physical half-trace k, internal-energy distinction and strict contributor
validity. Retain invalid/missing points and incomplete scores. Report station
and developing/developed groups separately. Geometry responses are now
predictions from one common upstream profile, unlike the earlier independently
imposed downstream profiles. Report those two experiment types separately.

Compare grid, phase, lateral extent, streamwise extent, ceiling height and
parameterization responses on identical IDs. Report downstream speed deficit,
W, k, directional fractions, and station variation at 90/120 mm. The paper's
reported <3% mean-speed variation at stations 8–20 is contextual evidence,
not a newly imposed universal physical acceptance threshold. The original
log-fit interval and measurement uncertainty do not justify a global pass/fail
threshold or an inferred IBL-growth exponent from sparse profiles.

Execution guards require exact source/build identities, identical planned
geometry, complete geometric sample support, independently matching solid
mask, solid volume within 1e-4 relative error, projection convergence, finite
computed fields, maximum interior divergence times cell spacing/Uref ≤1e-3,
and last-checkpoint receptor-vector change/Uref ≤1e-3. Strict covariance
validity is separately reported and never repaired to pass an execution guard.
The top solved-band mass diagnostic remains explicit; do not hide a poor
upper-boundary result behind the interior scalar. Failed/unfinished runs stay
in the ledger and are not admitted as qualified experimental improvements.

Archive the protocol, geometry, source/build identities, full run metadata,
positive-weight sampling support, sampled tensors, centreline fields,
per-observation comparisons, paired sensitivity summaries, plots and logs.
This is a bounded reconstruction study; exact laboratory phase/inlet mapping
and pedestrian qualification remain separate requirements.

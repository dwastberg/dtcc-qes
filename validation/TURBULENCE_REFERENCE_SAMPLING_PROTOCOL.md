# Turbulence reference-sampling investigation

> Historical research protocol/results, retained from `54ccb39`. Reproduction
> commands with research-only build paths describe that revision. The portable
> tools and current integration qualification are documented in
> [REFERENCE_INTEGRATION_RESULTS.md](../docs/REFERENCE_INTEGRATION_RESULTS.md).


Freeze this protocol before examining the new manufactured/capture results.
The question is whether the native reference estimator introduces avoidable
grid dependence, and how much it contributes to Surrey energy errors.

The current rule selects the cell above the first face at/above zRef, computes
cell-centred velocity magnitudes, and accumulates their horizontal mean in
float32. Float32 face coordinates and morphology-derived reference heights
can move this selection by an entire cell. Isolate four arms:

| Arm | Vertical sampling | Horizontal accumulation |
| --- | --- | --- |
| legacy | Current face lookup | Native float32 |
| wide_sum | Current face lookup | Float64, final speed narrowed to float32 |
| interpolate | Vector interpolation between centres at declared zRef | Float32 |
| interpolate_wide | Same vector interpolation | Float64, final speed narrowed to float32 |

Take magnitude after interpolating vectors in each column. Only positive-weight
fluid contributors count. Do not interpolate through solids or extrapolate
outside physical centres. Record masks, populations, supports, speeds, friction
velocities and caps. Out-of-range or zero-support prototypes remain explicitly
unsupported; do not invent a production fallback. Keep the declared zRef,
morphometric z0/d and current friction-velocity/logarithm arithmetic fixed.

Use a standalone native diagnostic linked to unchanged production numerical
sources. Its only build integration is an additional test executable. No public
API, default reference estimator, model constants or acceptance policy change.

## Manufactured qualification

Use four grid spacings, 35/17.5/8.75/4.375 mm, and affine, curved, turning-vector
and vertical-velocity profiles. At each grid, perturb a face near 210 mm by
±1 micrometre while keeping the same ground/top and subsequent faces. Capture
the actual native legacy reference and verify a separate reduction reproduces
it exactly. Affine component interpolation should match analytic point values
within 2e-6 m/s; curved errors should decrease with refinement. Turning profiles
test why vector interpolation precedes magnitude. Test float32 horizontal
accumulation at 16,192,11264,45056 columns, complete-support masks, zero support
and below-centre rejection. Record morphology-derived targets for 64/80 equal
70 mm buildings. Do not change that arithmetic in this experiment.

## Surrey fixed-mean isolation

Use the archived empty/street/shifted-block coarse/fine cases: six native mean
reproductions. The earlier archive stores a centreline and probes rather than
complete horizontal reference planes. A bounded new native capture is therefore
necessary. Serialize the exact prepared geometry, profile and grid from the
same Python package; execute the production projection/turbulence routines in
the standalone diagnostic. Preserve each recipe and output.

Admission requires identical projection iteration counts, bitwise-equal native
reference speed/friction/cap metadata and source-axis coordinates against the
archive, probe mean differences ≤2e-6 m/s, source stress replay error ≤16 float32
epsilons after scaling by max(1,abs(stress)), and no baseline contributor-validity
disagreements. All 101 probe IDs and positive-weight source cells remain fixed.
If these fail, retain the evidence and do not claim a controlled cap comparison.

Capture the native reference/bracketing planes and native source gradients,
mixing length, uncapped viscosity/energy, actual rotation factors and stress.
For each mean field, compute all four reference estimates without another wind
solve. Replay the current legacy constitutive/anisotropy/component-cap path
with each new cap. Do not change gradients, mixing length, viscosity, direction,
geometry or covariance model. Validate the baseline replay against executed
native tensors before interpreting the candidate arms. Preserve every raw
tensor and strict source/interpolant validity; never drop invalid points.

Report fixed-population physical half-trace k, component variances, internal
energy and invalid contributors separately. Compare reference/cap changes on
each field and their effects on coarse/fine score differences. These replays
assess the cap channel only; they do not assess a new turbulence transport model
or dissipation/divergence recomputation. Measured mean predictions cannot
improve in a fixed-mean experiment. No coefficient fitting, new AIJ runs or
physical/pedestrian qualification is part of this investigation.

Archive sources, helper build identity, recipes, raw captures, reference planes,
source/probe replay arrays, metrics, plots, test logs and checksums. Preserve
the Surrey background and roughness-transition archives and installed modules.

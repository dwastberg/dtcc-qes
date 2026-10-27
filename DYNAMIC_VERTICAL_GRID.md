# Dynamic vertical grid for pedestrian wind analysis

Status: Stages 0, A, B1 and C1 implemented and validated locally on 2026-10-26.
The sensitivity/cost study identified a failing fine-grid solve. The focused
diagnosis is now complete: study-only double-precision refinement substantially
reduces the interior residual on both CPU backends. B1 sampling and explicit-grid
preview and the C1 automatic-grid prototype are available. C2a's early
domain-height/horizontal controls are complete locally on 2026-10-27; both CPU
matrices identify a fixed-location horizontal-sensitivity failure. C2b is also
complete locally on 2026-10-27: near-wall initialization/averaging and lateral
extent materially affect the comparisons, and its finer horizontal float32
references fail residual control. The opt-in `solver_precision="float64"`
remedy is now implemented and validated from zero on both CPU backends: all
32 float64 cases pass the full gate, with 25 tighter passes including every
predeclared tighter case. Separate lateral/horizontal verification uses those
accepted references. The joint 160/240 m extent and 1/0.5 m x/y assessment is
complete locally on 2026-10-27: all 16 new CPU cases pass the solve gate and
finer-grid lateral comparisons pass, but added near-wall checks fail 13 of the
16 horizontal comparison planes on each backend. The expanded full-region
scope is not qualified. Next, review a bounded near-wall scope/sampling
protocol before C2c policy tuning, automatic preset selection or B2 integration.
Configurable allocation ceilings and atomic zero-start checkpoints support
the assessment; no supported automatic preset follows from its aggregate passes.
Treat cell-count budgets as soft planning targets: preserve the accuracy study
when a useful comparison slightly exceeds a target, subject to available
hardware and the resource guidance below.
Automatic presets remain gated by accepted accuracy/cost comparisons and
boundary/horizontal-resolution checks. Explicit vertical layers are available
through `VerticalGrid.from_faces`; `VerticalGrid.auto(...)` resolves provisional
settings through preview/run. Dataset APIs for vertical grids remain proposed.
The current QES commit is
`e0fb62e9fe5fffc8b4aef8f250f75f929ad27c13` on `dtcc-embed`, following the
Stage 0 correction `046eb799`. The submodule checkout and package revision file
identify the current commit. No remote push or upstream submission has been
made. The initial review used the embedded QES fork
(`QES-Public`, branch `dtcc-embed`, revision `71f8dcb2`), the native bridge,
the Python package and the literature linked below. Initial measurements came
from ad hoc native probes linked against the serial Release build on Apple
arm64; the new gate uses the reproducible study tools and stored raw samples
described in [its report](docs/vertical-grid-gate.md).
A follow-up review corrected the old residual measurement ranges and found
an out-of-bounds read in the cost probes. Stage 0 replaced the injection and
canyon probes with permanent tests and an independent residual oracle.
Unreproduced ad hoc results remain provisional. See the measured results and
commands in [the Stage 0 validation report](docs/stage0-validation.md).

Add an opt-in vertical grid that uses thin cells near pedestrian height,
increases cell thickness gradually through the building region, and permits
larger cells above the roofs. Keep `dx = dy = resolution` constant throughout
the domain. Preserve the existing uniform cubic grid when the new option is
omitted.

The objective is to reduce the cost of resolving pedestrian-height winds
compared with using fine vertical cells throughout the domain. This feature
does not resolve QES's underlying physical-model limitations or establish that
its predictions are sufficiently accurate for a particular comfort criterion.

## Stage 0 outcome and plan reassessment

The first stage corrected both CPU RHS expressions and the three CUDA source
variants, added conservative divergence diagnostics to the bridge and Python,
and retained the legacy multiplier stopping rule. CUDA was not compiled or run
on this host. Serial and OpenMP native tests, ASan/UBSan tests, reference-array
checks and the no-I/O symbol audit pass. The new injection regression fails
when linked against the original serial RHS.
The wheel rebuilt from the source distribution passes an isolated flat-solve
smoke test, and artifact checks include the new diagnostic sources.

The corrected 2 m canyon meets the common residual and velocity-stability gate
at 1,000, 2,000 and 4,000 iterations. At 4,000 iterations, serial maximum/RMS
interior divergence is `1.90735e-5 / 1.21252e-6 s^-1`; OpenMP (two threads)
gives `1.91622e-5 / 1.21466e-6 s^-1`. Successive maximum velocity-vector changes
normalized by the 5 m/s reference speed stay below `1.8e-6`. All checkpoints
still have `converged=False`: the multiplier flag must retain its explicitly
limited meaning. These comparisons sample the first centre at **1 m**, not a
1.5 m comfort plane. The future sampler and validation at the requested height
remain necessary.

The prescribed top-band residual is approximately `0.1221 s^-1` on this canyon.
It is not included in the interior norms and remains unfixed. Retain the planned
domain-height sensitivity before automatic-preset selection. Uniform-grid
success does not establish stretched-solve performance: retain Stage A and the
sensitivity/cost gate, and keep the old cost table withdrawn. The default
aspect-ratio limit of 8 is still provisional.

The full Python run passes 233 tests and fails one existing dataset-registration
expectation: `test_explicit_import_registration` expects a lazy registration
contract, while tracked `dtcc_qes/__init__.py` imports the dataset eagerly.
This is independent of the solver changes; resolve that contract separately.
The Stage 0 sanitizer suite takes about 139 seconds on this host (about 104
seconds for the canyon-inclusive physics test), so future CI timeouts must
accommodate it. These were the findings at the end of Stage 0; the subsequent
Stage A delivery is recorded below.

## Stage A outcome and plan reassessment

`wind.run(..., vertical_grid=wind.VerticalGrid.from_faces(z_faces))` now uses
explicit physical layers with constant x/y spacing from `resolution`. Requested
faces are immutable, native thickness buffers are snapshotted, and actual
float32 faces/centres and layer/roof diagnostics are retained in the result.
Direct uniform-grid export rejects nonuniform layers. Explicit equal-thickness
layers reproduce legacy coordinates, classifications, velocity and diagnostics
bitwise; anisotropic uniform grids export their true z extent.

The core validates coordinates and coefficients before wind allocation,
requires declared layers to match the constructed domain, and rejects
solver/domain spacing mismatches. The bridge's coordinate-only helper reuses
the actual `Domain` constructor instead of duplicating its native accumulation.
Python reproduces the sequential float32 accumulation for preparation and
records any difference between requested and effective coordinates. Requested
explicit bounds are checked before narrowing, allowing only float64 subtraction
roundoff, rather than silently clipping or rescaling a supplied grid.

The parameterization audit found an additional rooftop-vortex shell-search
bounds defect. With small roof clearance, the old search can read past `z`.
The permanent low-clearance test reproduces a heap-buffer-overflow under ASan
when linked to the old loop; the bounded search passes. Unused scalar `dz`
bindings were removed, and `getDomainSize()` now returns the actual y spacing.

A 37-layer canyon at 2 m x/y spacing passes the base residual targets at 2,000
iterations: serial maximum/RMS `8.46378e-5 / 3.02199e-6 s^-1`, OpenMP
`8.68589e-5 / 2.96522e-6 s^-1`. The top-band maximum is still about
`0.114459 s^-1`. This establishes coupled-solver coverage, not iterative
stability or a performance result; the next gate must run matched physical
sampling and iteration sweeps. Automatic growth/aspect defaults remain
provisional. See [the Stage A report](docs/stagea-validation.md) for the API,
regression coverage, commands and remaining limitations. Both CPU extensions
pass 278 Python tests with the known registration mismatch explicitly deselected.

The subsequent sensitivity/cost study and its decision are recorded below.
At the end of Stage A, sampling/preview, automatic generation/validation and
dataset integration remained unimplemented. Subsequent milestones are recorded
below. Keep the known
dataset-registration mismatch separate from the vertical-grid feature.

## Sensitivity/cost gate outcome and plan reassessment

The study tools run four synthetic geometries, two wind directions and five
explicit grids at fixed 2 m horizontal spacing and fixed physical bounds.
Pedestrian comparisons use linear component sampling at 1.5 m and a common
fluid mask. The study forces the requested sweeps without changing the public
stopping rule, checks residuals and two successive velocity-vector changes,
and records separate timings and process RSS. See
[the report and raw-data links](docs/vertical-grid-gate.md) for the complete
matrix, repeat counts, numerical comparisons and performance measurements.
All 80 final workers completed; 76 pass and the four failures are the two
repetitions of each 0.25 m tower wind. The two repetitions agree exactly in
sampled fields, masks and residual diagnostics.

The 52-layer stretched grid passes all eight geometry/wind combinations and
takes about 40% of the uniform 0.5 m solve time
and about half its RSS, but costs approximately 1.6 times the 2 m solve.
These are fixed-budget timings at accepted checkpoints, not optimized
time-to-accuracy measurements.
Its P95 discrepancy from 0.5 m is `0.00157–0.00496` in K, against
`0.02327–0.02570` for 2 m. The 2 m grid already meets the proposed aggregate
speed thresholds in this synthetic suite, so this is not evidence that all
comfort studies need the extra layers. Conversely, in tower/270° the peak
location changes by 20.9 m despite a sub-1% stretched-vs-0.5 m peak-value
difference. The 0.5 m field has nearly tied competing peaks, so global argmax
displacement alone is not a reliable failure criterion. Assess speeds at fixed
critical locations and the extent of high-speed regions as well.

The 0.25 m tower grid (aspect ratio 8) fails the declared maximum residual
target at 8,000, 16,000 and 32,000 sweeps for both tested directions. For 270°,
the normalized maxima are approximately `1.585e-3`, `2.194e-3` and `1.279e-3`,
against a `1e-3` limit, while successive maximum velocity-vector changes are
below `5e-6` of the reference speed. A stable pedestrian field does not make
this an accepted fine-grid reference. The thresholds and diagnostic cell range
are unchanged; failed pairs have no matched-accuracy performance claim.

**Revised decision: narrow the gate to claims that depend on accepted solves.**
The failed 0.25 m tower cases remain excluded as accuracy references. They do
not invalidate the passing explicit-grid results or block independently
verifiable sampling and preview functionality. Start with a bounded diagnosis
of one failing tower case and a passing control (section 5.6), then deliver B1.
Keep automatic-preset selection gated; do not freeze the aspect limit of 8,
growth 1.15, roof buffer or upper cap. The tested hand-built grid has a 0.5 m
minimum, a 2 m maximum and maximum upward growth of 1.125, including a final
decrease in thickness allowed by explicit mode. It does not validate the
proposed nondecreasing automatic policy. Neither its passing aspect ratio of
4 nor the failing tower's ratio of 8 establishes a universal solver limit.

This reassessment supersedes the blanket “stop before Stage B” decision in
the historical study report; the measurements and failed-reference exclusions
remain unchanged. The revised sequence is focused diagnosis → B1 sampling and
explicit preview → C1 automatic prototype → C2 validation and preset selection
→ B2 dataset integration. Optional uniform resampling is deferred.

Sampling alignment also matters: in the neutral flat profile, linear sampling
on 2 m layers has approximately `-0.02506` bias in K at 1.5 m, or -4.17% of
the exact local speed. On 1 m layers the requested height is exactly a centre
and has no analytic interpolation bias, whereas 0.5 m layers have a small
negative bias. Include the existing 1 m runs in the comparison summaries.
Stage C2 must assess centre alignment alongside thickness and
flow sensitivity; finer spacing alone does not imply a better sampled value.
Add building heights that do not align with uniform grid faces. A flat-profile
control identifies sampling bias but cannot be subtracted from disturbed
building flow to establish flow convergence.
This is numerical evidence within QES, not wind-tunnel or comfort validation.
Bring domain-height and selected finer-x/y checks forward into C2 before broad
parameter tuning and preset selection. Experimental and OpenMP performance
studies remain prerequisites to claims about physical accuracy and that backend.

## Focused solver diagnosis outcome

The section 5.6 diagnostic milestone is complete locally on 2026-10-26; see
[the diagnostic report](docs/vertical-grid-diagnosis.md) and its archived raw
data. It compares the tower at 270° with 0.25 m and 0.5 m layers, on serial
lexicographic and two-thread OpenMP red-black solvers. The final control uses
2,000/4,000/8,000 sweeps on both backends; an exploratory OpenMP control at
1,000 sweeps fails the RMS criterion, so serial iteration budgets cannot be
assumed sufficient for the other ordering.

Independent float reconstruction matches the stored corrected faces exactly.
In the assessed interior, double-precision stencil and corrected-flux
predictions agree to roundoff, and solid-face zeroing changes no assessed
flux. The failing serial 0.25 m residual at 32,000 sweeps is approximately
`2.66433e-4 s^-1`, already present in the multiplier solution; RHS rounding and
final face-correction roundoff are much smaller. This finds no operator/flux
inconsistency explaining the plateau on these fixtures; it is not an audit of
every parameterization or boundary configuration.

A study-only refinement widens multiplier storage, RHS construction and SOR
updates, retaining float geometry/coefficients, the same node ordering and
boundary conditions. Starting from each 32,000-sweep float solution, 1,000
additional double sweeps reduce maximum interior divergence, after casting
corrected faces back to float, to approximately `3.55e-6 s^-1` (serial) and
`6.94e-6 s^-1` (red-black). These meet the tighter residual bounds at that
snapshot, with maximum pedestrian vector changes below `1.84e-5 * Uref`.
The prescribed top-band residual remains about `0.281 s^-1`.

**Decision:** precision in the multiplier/update path is a supported remedy
candidate for these cases; vertical line relaxation is not the next remedy
established by this evidence. Proceed to B1. Keep the production solver,
stopping rule and failed-reference exclusions as they are. The warm-start
experiment is not a from-zero precision solver, a full stability gate or a
performance result. Before using a precision remedy to support C2 preset
claims, implement it separately and opt-in, test from zero on both backends,
rerun the complete matched-accuracy gate, and measure memory/runtime costs.
Do not infer a universal aspect limit or precision floor from this diagnosis.

## Stage B1 outcome and plan reassessment

`WindResult.sample(height, method="nearest" | "linear")` now returns a
`WindSample` with owned float64 velocity (y, x, component), derived speed,
validity, local x/y axes, requested/sampled heights, method, origin and CRS.
Nearest is the default, clips to endpoint centres within the domain and breaks
ties toward the lower centre. Linear interpolates components at physical
heights, uses one cell for exact-centre requests, and returns invalid NaNs
outside the centre range. Both contributing cells must be finite fluid;
flags 0/2 are invalid. Heights outside the physical domain raise. Requested
numeric values and stored centres are compared in float64 without narrowing
the request to float32. Sampling allocates horizontal planes and coordinate
vectors, not full-volume masks or velocity copies.

`wind.preview_grid(...)` shares geometry/domain preparation with `run` and
returns `GridPreview` coordinates, shape, cell count, solver/effective layer
thicknesses, growth/aspect ratios, bounds and roof diagnostics. It creates no
native wind runner or flow arrays. Uniform and explicit coordinates match the
native solve, including decimal float32 accumulation and translated frames.
Memory estimates remain omitted. A regression found that narrowing at the
coefficient limit could let preview accept spacing rejected by native
preparation; both paths now check the actual narrowed coefficient arithmetic
before allocation.

Manufactured interpolation, solids/nonfinite masks, exact and nearby heights,
endpoint handling, array ownership, archived native study parity and allocation
checks pass. Serial/OpenMP Python suites and packaging checks are recorded in
[the B1 validation report](docs/stageb1-validation.md). The executable
`examples/vertical_grid.py` compares uniform and stretched grids at 1.5 m and
reports layer thickness versus height. Dataset slice behavior, automatic
generation and resampling are not part of B1.

**Decision:** proceed to C1, the automatic-generator prototype and automatic
preview extension. Keep all proposed policy constants provisional until C2
measures actual generated grids, boundary/horizontal sensitivity and cost at
matched accuracy. The solver diagnosis, failed fine-reference exclusions and
top-boundary limitation remain as documented; B1 makes no new accuracy claim.

## Stage C1 outcome and plan reassessment

`VerticalGrid.auto(...)` now stores immutable, unresolved candidate settings.
Preview and run resolve them from the same prepared geometry, selected top and
effective x/y spacing. Metadata marks the policy `prototype_unvalidated`, with
an automatic generator version, requested/effective settings, planned/effective
faces, native solver thicknesses, endpoint error and pedestrian brackets with
an analytic flat-profile sampling control. The uniform default and explicit
face path remain available without opting into the prototype.

The generator implements the joint fine-band count/thickness rule, upward
extension for an empty feasible-count interval, height-dependent building caps,
nondecreasing thicknesses and bounded growth. It retains all positive buildings;
caps use float32 heights to agree with native occupancy. Settings must provide
a fine region at least as high as the pedestrian plane. Cell/dimension limits
fail before native flow allocation and do not silently coarsen the grid.

Endpoint fitting uses a bounded greedy-count/constant-tail construction. Grow
maximally to find the minimum upper count, then cap each upper thickness by the
remaining height divided by the remaining count. When that average becomes
feasible, the rest of the cells form a constant tail. Nondecreasing caps make
this tail valid, avoiding a thin remainder or a search through discontinuous
roof-cap transitions. An endpoint can be infeasible with the fine band fixed;
for example, 0.5 m fine layers, growth 1.15 and 0.6 m remaining cannot fit one
upper cell (maximum 0.575 m) or two (minimum 1 m). Reject that combination rather
than altering the fine band.

The implementation clarified the plan's endpoint wording: the float64 plan
fits the selected top, while canonical float32 accumulation can shift the
effective endpoint. Record both and bound the error by
`gamma_(n+1) * top`, with `u = float32_eps / 2` and
`gamma_k = k*u / (1-k*u)`. For constraints on solver thicknesses, allow only
`8 * float32_eps` relative narrowing tolerance, and recheck actual coordinate
monotonicity, coefficients, pedestrian bracketing and effective lower-face
caps. Planning also respects the lower of planned/effective faces: a face
rounded below `1.5 * Hi` cannot release its roof cap early. Do not describe
the effective float32 endpoint as exactly equal to an arbitrary requested top.

The construction/feasibility, preview/solve coordinate, analytic-profile,
translated occupancy and example checks are recorded in
[the C1 validation report](docs/stagec1-validation.md). No native solver or
precision remedy is added by C1. Flat flows at other horizontal spacings
show small residuals already present on equivalent explicit grids; integration
checks use the unchanged project bounds and bitwise explicit-path controls,
rather than an exact-zero assumption. **Decision:** proceed to C2's early
domain-height and finer-x/y controls, then actual generated-grid accuracy/cost
comparisons. Policy constants, aspect limits, roof buffers, centre alignment
and supported scope remain provisional; C1 correctness tests do not select a
comfort-analysis preset. Keep failed fine references and the top-band
limitation as documented.

## C2 early-control outcome and plan reassessment

The C2a milestone consumes actual Python-generated layers in the native
fixed-sweep worker, rather than reimplementing the policy in C++. The driver
archives generator settings and planned/effective coordinates, verifies native
faces, measures policy generation separately, and samples both 1.5 and 1.75 m.
The base grid is generated for 1.5 m so both planes satisfy the third-centre
requirement. See [the C2 control report](docs/stagec2-controls.md) for commands,
thresholds, raw samples and validation details.

Use non-aligned passage/tower roofs, two winds, automatic and uniform 0.5 m
families, 64/144 m domain tops and 2/1 m horizontal spacing. Preserve every
lower layer for the taller control and all z layers for horizontal refinement.
Compare identical physical locations, using bilinear component interpolation
on the finer horizontal grid, with explicit common-fluid masks and validity
transitions. The unchanged residual/stability gate applies at both heights.
Fixed critical locations, P95 errors, peak changes and maximum errors are all
reported; global percentiles cannot override a critical-location failure.

All 96 final workers (48 serial and 48 two-thread OpenMP) pass the common solve
gate. Taller-domain changes are small: maximum absolute K changes stay below
0.00030. Finer x/y produces
local changes near 0.30 K, and the uniform-fine tower at 270 degrees changes
speeds at fixed critical locations by about 10.98% (1.5 m) and 11.17% (1.75 m),
above the declared 5% limit. P95 and global-peak metrics alone pass, illustrating
why the fixed-location check is needed. These are numerical comparisons within
QES, not experimental errors. OpenMP reproduces the same failure, and all 24
repetition pairs on each backend reproduce fields/masks/residuals exactly.
No configuration meets the ten-times tighter residual bounds at its final
checkpoint; validating a tighter subset remains required before preset claims.

**Revised sequence within C2:** C2a is complete; investigate the tower's
horizontal sensitivity at fixed locations in C2b before
broad automatic-parameter tuning. Use finer x/y with unchanged vertical layers
and the same physical sample points; inspect interpolation, occupancy and
parameterization transitions near the largest errors. If necessary, increase
lateral domain extent while retaining the comparison region. Hold acceptance
criteria fixed. A 64-to-144 m height check does not establish lateral-boundary
independence, horizontal grid independence or adequacy on other geometries.

Only after that assessment establishes a supported scope should C2 continue
with three vertical refinement levels, centre-alignment/shallow-roof cases,
growth/aspect/buffer/cap sensitivity, tighter-residual controls, accepted finer
references and cost against the cheapest qualifying uniform family. Retain
experimental validation as a separate requirement for physical-accuracy claims.
The early-control milestone does not finish those studies or authorize B2.
Keep `prototype_unvalidated`, the production solver and failed 0.25 m tower
reference exclusions unchanged. Do not select an automatic preset from the
current aggregate-error passes or cell savings.

## C2b outcome and prerequisites before policy tuning

The horizontal-sensitivity assessment is complete; see the
[report, raw samples and initialization plot](docs/stagec2b-horizontal-sensitivity.md).
Both CPU backends reuse the accepted C2a tower references and preserve their
z layers while adding 0.5 m x/y grids, larger lateral bounds and diagnostic
parameterization controls. The new worker archives native interpolation
support, flags, approach profiles, parameterized/wall-zeroed initial fields
and corrected checkpoints. The study includes 36 final tasks (16 initial-only
probes and 20 full solves), plus 26 completed rejected budget trials. Twelve
full controls pass; all eight new finer references fail the unchanged maximum
residual bound. Source/binary/reference fingerprints and serial continuation
provenance are archived. No production model or sampling policy is changed.

At the tower/270-degree maximum-error point, sidewall removal eliminates the
large initial-field discrepancy. A control with all five active empirical
building stages disabled still shows near-wall sensitivity caused by solid-wall
face zeroing and cell-centred averaging. The neutral profile matches exactly
across horizontal grids, and manufactured/legacy sampling checks pass. These
findings do not justify altering the wind profile, height sampler or production
sidewall settings as a shortcut to grid independence.

Expanding lateral bounds from 80 to 160 m produces accepted solves but fails
the comparison budget on both backends: P95 absolute K changes reach about
0.069, and fixed-critical changes reach about 5.56%. Approach and parameterized
initial values match exactly at the inspected support points on both sampling
planes. The small height effect in C2a therefore does not establish lateral
boundary adequacy. The separate region at least 4 m from footprints passes the
2-to-1 m horizontal comparison but fails lateral checks, and its finer-reference
comparisons are withheld. It is not a supported comfort-analysis scope.

The 0.5 m x/y references have final normalized maximum residuals about
`1.024e-3` to `1.514e-3` at 16,000 sweeps, above `1e-3`, even though RMS
residuals and successive pedestrian vector changes meet their bounds. Preserve
these failed-reference exclusions. Stable fields are not accepted references,
and these runs do not prove the cause of the residual limit. The earlier
double-precision warm-start diagnosis supports a remedy candidate, not an
already validated production remedy or a guarantee for this new configuration.

The follow-up precision remedy is now implemented and validated separately,
with its outcome below. The original C2b float32 failures remain archived and
excluded under their original arithmetic. New float64 references do not change
those historical acceptance decisions.

## Opt-in precision remedy outcome

`wind.run(..., solver_precision="float64")` selects the bridge's separate
`PrecisionSolver`. The default remains `"float32"` and uses the existing QES
CPU implementations without changes. Double multiplier/RHS storage, diagonal
and neighbour arithmetic, and face corrections widen their operands before
arithmetic; completed faces, geometry, coefficients and public velocity arrays
remain float32. Serial lexicographic and OpenMP red/black order, the actual
`1.78f` relaxation constant, ground mirror, lateral/top conditions and solid
face zeroing are retained. Both modes still stop on maximum multiplier change;
the opt-in mode permits double-precision tolerances, while legacy float32
validation and narrowing remain unchanged. Diagnostics and solver metadata
record precision explicitly. Precision/tolerance switches rebuild the active
solver, discard the other workspace and restart from zero.

The [implementation and verification report](docs/precision-and-horizontal-verification.md)
and [raw precision matrices](docs/data/precision-remedy/) include 16 float64
cases and two new float32 controls per backend. All 32 float64 cases pass the
full common N/2N/4N residual/vector/mask gate from zero, restoring accepted
references for the eight finer-horizontal and four original 0.25 m vertical
tower failures across both backends. All 16 cases in the predeclared 270-degree
tighter subset pass one-tenth of both residual bounds at all checkpoints;
25 float64 cases in total do so. The four new float32 controls pass the original
common gate; matched archived checkpoints retain exact fields and diagnostics.
The prescribed top-band limitation remains separately reported.

The double workspace is two buffers (16 bytes per native cell including ghosts),
replacing the legacy three float buffers (12 bytes per cell). Raw archives
record actual workspace bytes, per-process peak RSS, preparation, solve,
residual and sampling time, and rejected completed budgets. These concurrent
single diagnostic measurements do not establish speedup ratios or cheapest
qualifying presets. Passing from-zero references supports subsequent grid
comparisons; it does not validate the automatic policy or empirical physics.
See the report for the native/Python, sanitizer, artifact and provenance checks.

## Lateral/horizontal verification and remaining scope

Use accepted float64 references with unchanged z layers, production flags,
world geometry, sensor (5,5), grid phase and fixed pedestrian lattice
x,y = 3,5,...,77 m at both 1.5 and 1.75 m. The fixed critical locations and the
exploratory 4 m footprint setback come from C2b and must not be reselected using
new peaks. Compare x/y=2-to-1-to-0.5 m at 80 m extent, and lateral
80-to-160-to-240 m extents at x/y=1 m, separately for both layer families and
winds. Require accepted solves for every comparison. Preserve initialization,
occupancy, corner support, maximum local errors and failures outside the away
region, including when P95, global peak and fixed-critical budgets pass.

The assessment is locally complete on both CPU backends. All 16 larger-domain
workers pass the common gate. At 80 m extent, all eight 1-to-0.5 m full-region
comparisons pass the declared budget, while the two uniform-z / 270-degree
2-to-1 m planes still fail their fixed-critical checks (up to 11.17%). All eight
80-to-160 m full-region comparisons fail, with P95 delta K up to 0.06916 and
fixed-critical changes up to 5.596%. All eight 160-to-240 m comparisons pass:
P95 delta K is 0.00255–0.00422 and fixed-critical changes stay below 0.431%.
These decisions agree between backends. Initialization/support values are
unchanged at the inspected points; masks do not change across the comparisons.
The full-region 1-to-0.5 m maximum local delta K still reaches 0.1735, so retain
the near-wall limitation even when the declared aggregate/critical budget passes.
Raw data, costs and the comparison figure are linked from the report.

These two refinement axes alone do not establish a jointly adequate lateral
extent and fine horizontal grid. Before C2c tuning or preset selection, close
that remaining scope with a declared common-extent finer-grid comparison and
its lateral control, using accepted solves and the same fixed points. Use
160 m and 240 m square domains at 1 m and 0.5 m horizontal spacing, both frozen
z-layer families, both wind directions and both pedestrian heights. Reuse
accepted 1 m references where provenance permits. Keep this matrix even though
the largest uniform-z case exceeds the previous 20-million-cell target; do not
substitute a smaller domain solely to fit that target. Do not
infer that 160 m, 240 m, 1 m/0.5 m spacing or a 4 m setback is universally
adequate. Include (27,21), (21,23) and (51,35) as additional mandatory fixed
checks in the joint study. Before measurement, freeze a relative delta K below
5% when the finer/larger reference K is at least 0.1, otherwise an absolute
delta K below 0.05; unavailable samples fail the local check. Keep the original
aggregate/critical budget distinct from this expanded local gate, and report
both. Preserve the original
study's frozen critical sets and decisions; a P95 pass does not bound every
point, and an aggregate pass cannot erase the observed local delta K near 0.17.
Include any added precision option in B2 request/cache identity and
provenance. Keep `prototype_unvalidated`; experimental physical validation and
B2 remain gated as already described.

### Cell-count targets and hardware resources

Cell-count budgets, including the study worker's current 20-million-cell
setting, are soft resource targets for planning and comparison selection, not
numerical validity limits. Aim to stay close to the chosen target, but accept
modest overruns when they preserve a useful matched comparison. The user
reports successful tests at 40 million cells; around 100 million may also be
feasible with appropriate hardware. These observations guide resource planning
and do not establish measured memory, runtime or accuracy for every grid or
backend.

The joint study's uniform-z=0.5 m grid has 128 physical layers. At 0.5 m x/y
spacing, the 160 m domain contains 13,107,200 physical cells and the 240 m domain
contains 29,491,200. The latter is an acceptable planned overrun of the earlier
20-million target and is below the reported successful 40-million-cell tests.
Begin with the 160 m fine-grid cases to measure cost, then run the 240 m cases
with a hardware-appropriate worker count. Include both domains in the declared
scope; the smaller pilot alone does not close the lateral control.

Before allocation, estimate memory from the actual physical and ghost-cell
arrays, selected solver precision and concurrent workers. Record the target,
actual counts, memory estimate, measured peak RSS and elapsed work. Adjust
concurrency or use a larger host when needed; do not silently coarsen cells,
shrink the domain, omit buildings or relax accuracy criteria to meet a target.
Cell count alone does not determine practical feasibility or runtime.

Existing `max_cells` checks remain enforced allocation guards. The study
worker now accepts a configurable ceiling; set the guard to accommodate the
declared matrix and available hardware; merely documenting a soft target does
not bypass the existing check. Keep a distinction between the planning target
and the configured allocation ceiling. Integer/index overflow, invalid grid
dimensions and representability checks remain hard correctness constraints.
The study controls do not change public API defaults or bypass its guards.

The joint study uses `tools/run_joint_grid_verification.py`, the worker's
study-only `--checkpoint` and `--max-cells` controls, and
`tools/audit_joint_grid_verification.py`. Its predeclared manifest, independent
checkpoints and case records are under `docs/data/joint-grid-verification/`.
The implementation and reproduction procedure are documented in
[`docs/joint-grid-verification.md`](docs/joint-grid-verification.md). The full
matrix and provenance audit are complete: 73 unique independent checkpoint
executions, 25 rejected budget triples retained, and all 16 final cases accepted.
All 64 comparison decisions agree between CPU backends. Original aggregate
budgets pass, but mandatory near-wall checks fail 13 of 16 horizontal planes
per backend, with changes up to 17.32%; maximum full-lattice absolute delta K
remains about 0.17345. The 0.5 m lateral control passes all eight planes and
fixed checks. The largest cases use 29,491,200 physical cells and about 3.72 GB
peak worker RSS. Host sleep/wake interruptions qualify the diagnostic timings;
deterministic cell-sweep work and separately measured costs are archived.
Retain this negative full-region result and keep C2c gated. Do not automatically
start a new refinement study or tune the automatic policy to hide a failed local
check.

The expanded local gate fails, so the next action is a bounded near-wall
scope/sampling review before C2c. Use the saved profile, initialized field,
native-corner support and final vectors to distinguish representation and
initialization effects from the converged projection. Define the intended
point-velocity or spatial-average observable and its validity contract before
changing sampling. Any alternate sampler first needs manufactured curved-field
and wall/solid-support checks. Preserve current sampling results and budgets
as the baseline.

Then decide whether selected 0.5-to-0.25 m x/y references, at a declared common
extent with their lateral control, are needed to qualify the desired near-wall
scope. Freeze z operands and physical check points again. Estimate memory and
certification work before launching them; a full finer-grid matrix is not an
automatic consequence of this assessment. A narrower supported region needs
its own prospective acceptance contract and evidence; the exploratory 4 m
setback is not a ready-made urban comfort preset. Retain all present failures
and keep empirical parameterization/profile tuning separate from numerical
qualification. Cell targets remain soft throughout this decision.

## Findings from the source review

The review changed the plan in four ways. Items 1 and 2 also affect the
existing uniform grid and must be addressed before stretching is added.

1. **The QES right-hand side omits `1 / dz` in its vertical term.**

   After `Wall::solverCoefficients` (`Wall.cpp:829`), the vertical
   coefficients are `m = m̂ / (dz_k * δ_up)` and `n = n̂ / (dz_k * δ_down)`.
   Here `m̂` and `n̂` are open-face fractions and `δ` is the distance between
   adjacent cell centres. The right-hand side in `Solver_CPU.cpp:68-78` and
   `Solver_CPU_RB.cpp:71-81` multiplies them by `dz_k * δ`. Its vertical term is
   therefore `m̂ * w_top - n̂ * w_bottom`, while the horizontal terms are
   `(ê * u_east - f̂ * u_west) / dx`. The vertical term lacks `1 / dz_k`. After
   the solve, `(1 - dz_k)` times the initial vertical divergence remains, with
   `dz_k` in metres. The defect predates the fork: upstream `CPUSolver.cpp`
   contained the same expression before the solver refactor.

   The SOR operator and the vertical velocity correction (`Solver_CPU.cpp:212`)
   are consistent with the corrected right-hand side. Rebuilding the serial
   injection probe with only that correction gives the following maximum
   interior divergence, excluding the prescribed top band:

   | Uniform cell height | Initial divergence | Current solver | Corrected RHS |
   | --- | --- | --- | --- |
   | 1 m | 0.1 s⁻¹ | 2.8915e-7 s⁻¹ | 2.8915e-7 s⁻¹ |
   | 2 m | 0.05 s⁻¹ | 0.05 s⁻¹ | 7.0177e-8 s⁻¹ |
   | 4 m | 0.025 s⁻¹ | 0.075 s⁻¹ | 1.2799e-8 s⁻¹ |

   Reproduction: a calm, obstacle-free 24 × 24 × 16 physical-cell domain,
   equal x/y/z spacing as listed, a single `w0=0.1 m/s` face at native index
   `(12, 12, 6)`, multiplier tolerance `2e-7`, and at most 20,000 iterations.
   The corresponding `u0` control is removed by both versions. These are
   achieved residuals at that stopping tolerance, not established float32 floors.

   The earlier approximately `1e-5 s⁻¹` corrected injection values included
   `k == nz - 1`, the separately prescribed top band. They must not set an
   interior acceptance threshold. The original canyon pedestrian-speed change
   and stretched-solve probes require reproducible before/after reruns before
   their old numbers are reinstated. Stage 0 now verifies corrected canyon
   residuals and iterative stability with the measurement convention in section
   6.3, using its original geometry and default parameterizations as a permanent
   regression.

   Street canyons (`StreetCanyon.cpp:529-532`), the upwind-cavity MVP branch
   (`UpwindCavity.cpp:287`) and tall-building wakes (`PolygonWake.cpp:478-482`)
   create nonzero `w0`. Realistic multi-building cities are therefore affected
   today. Stretching would make the error vary by layer and amplify it up to
   seven times in 8 m upper layers.

2. **The multiplier-change tolerance cannot certify convergence.**

   QES stops when the maximum change in the Lagrange multiplier falls below
   the tolerance. Stage 0's bounds-checked canyon tests show multiplier changes
   around `4.6e-5` to `6.1e-5` after 1,000–4,000 iterations despite acceptable
   residuals and stable velocities. The old 50,000-iteration observation has
   not been repeated; neither observation is a universal precision floor.
   The verified injection test already shows that the original solver can report
   convergence while retaining large physical divergence.

   The inverse diagonal in a Poisson update has spacing-dependent factors,
   but this does not imply that the multiplier solution universally scales as
   cell size squared under mesh refinement: the RHS, geometry and physical
   field also matter. A fixed multiplier-change tolerance is not a transferable
   bound on mass conservation or velocity error. Neither that flag nor a
   residual plateau alone establishes acceptable convergence; section 10
   requires bounded residuals and stable pedestrian velocities together.

3. **Thin layers require a measured conditioning and cost study.**

   The cost/rate probes iterated through physical `k == nz` and read
   `dz_array[k + 1]` beyond the vector. A bounds-checked rebuild reproduced
   the failure. Withdraw their residual/timing table and the associated
   four-times-cheaper and three-times-more-iterations conclusions until rerun.
   Even fixed-iteration timings would not establish savings at matched accuracy.

   The solver uses point SOR with a fixed relaxation factor of 1.78
   (`Solver.h:93`). Thin layers introduce anisotropy, so conditioning remains a
   reason to investigate an aspect-ratio limit. Its proposed value of 8 and the
   minimum-thickness policy are provisional safeguards, not empirically justified
   limits from the withdrawn probes. Repeat the study with identical physical
   bounds, report stair-step roof differences, and compare time to the same
   accuracy criteria before attributing iteration differences to anisotropy.

4. **Much of the stretched path has supporting source evidence.** Numerical
   confirmation with corrected probes remains required:

   - Coefficient assembly and the vertical velocity correction use adjacent
     layer thicknesses.
   - The inflow profile is evaluated at actual cell centres as
     `ln((z + z0) / z0)`; retain an analytic-profile regression test.
   - Building occupancy, rooftop, upwind-cavity, wake and street-canyon code
     use `domain.z` and `domain.z_face` lookups. The scalar `dz` they unpack
     from `getDomainSize()` is never used.
   - The bridge's centre averaging of `w` is correct, because each centre lies
     midway between its faces.
   - `datasets._nearest` uses `searchsorted` on the actual axes.

## Plan

1. **Use the literature as constraints, then validate the QES-specific choices.**

   The literature supports fine near-ground resolution and gradual stretching,
   but does not establish a universally optimal automatic vertical grid for
   QES. Distinguish published guidance from the provisional defaults proposed
   here.

   | Evidence | Design implication |
   | --- | --- |
   | AIJ guidance places pedestrian evaluation height at the third grid point or higher and recommends approximately ten cells across a building dimension as an initial choice. [Tominaga et al., 2008, sections 4.1–4.3](https://doi.org/10.1016/j.jweia.2008.02.058). | Place several layers below the evaluation height and constrain vertical coarsening through buildings. |
   | COST 732 recommends expansion ratios below 1.3 in regions with large gradients, with some cited recommendations limiting the ratio to 1.2. [Franke et al., 2007, section 5.7](https://www.airshed.co.uk/wp-content/uploads/2018/03/COST-732-Best-Practice-Guideline-May-2007.pdf). | Start with a growth factor of 1.15; compare 1.10 and 1.20 experimentally. |
   | QES experiments show sensitivity to vertical resolution and stair-step geometry, including failures to resolve measurement locations. Building parameterizations were disabled in parts of that study to isolate geometry effects. [Bozorgmehr et al., 2025](https://doi.org/10.1029/2024MS004494). | Validate the actual parameterizations enabled in these bindings; do not assume smaller cells always improve agreement with measurements. |

   AIJ and COST principally address momentum-solving CFD. Their recommendations
   are useful starting constraints, not proof that a QES simulation achieves
   comparable accuracy. QES conserves mass and uses empirical building-flow
   parameterizations. Do not choose the first layer from a RANS wall-function
   `y+` target: that is not the numerical model implemented here. Pedestrian
   results may therefore be less sensitive to vertical resolution than RANS
   guidance suggests; the study and preset-selection criteria in section 10
   assess this without blocking independent sampling and preview work.

   Prefer geometry-based grid generation before the solve. Reuse the same grid
   across wind speeds and directions, making results comparable and avoiding
   repeated grid selection costs. Solution-dependent adaptive refinement and
   local refinement in x/y are outside the first implementation.

2. **Define the public contract before changing the solver.**

   Add a public `VerticalGrid` configuration type in a new
   `src/dtcc_qes/vertical_grid.py` module, re-exported through `wind`. It is an
   immutable specification with automatic and explicit-face constructors. Keep
   generation and validation separate from native allocation.

   Proposed usage:

   ```python
   from dtcc_qes import wind

   result = wind.run(
       city,
       speed=5.0,
       direction=270.0,
       resolution=2.0,  # Uniform dx and dy, in metres.
       vertical_grid=wind.VerticalGrid.auto(
           pedestrian_height=1.5,
           growth_rate=1.15,
       ),
   )
   ped = result.sample(height=1.5, method="linear")
   ```

   Support expert-specified physical faces through
   `VerticalGrid.from_faces(z_faces)`. Faces are heights in metres above the flat
   ground, not global elevations and not cell centres. For example,
   `[0.0, 0.4, 0.8, 1.2, 1.6, 2.0]` describes five physical layers, but a real
   simulation must supply enough layers to cover its required domain. Uniform
   anisotropic grids (for example 0.5 m layers with 2 m horizontal cells) are
   expressed as equally spaced faces; the sensitivity gate uses them.

   Contract:

   - `vertical_grid=None` retains the existing uniform behaviour and numerical
     path. Do not change default outputs merely by adding the feature. The
     Stage 0 solver correction is a separate, documented change.
   - `resolution` sets x/y spacing in all modes. It also sets z spacing only in
     legacy uniform mode.
   - Automatic mode exposes `pedestrian_height`, `growth_rate`,
     `min_layer_thickness`, `max_aspect_ratio`, and optional overrides for
     `first_layer_thickness`, `fine_region_height` and `upper_layer_cap`.
     First-layer thickness is a preferred target, not an equality. Results and
     previews record both requested and effective settings.
   - Explicit mode derives `nz` from the number of faces; do not accept a second
     independent layer count that can contradict the faces.
   - Explicit faces may describe non-monotonic layer thicknesses. Automatic mode
     generates nondecreasing thicknesses. Report extreme growth and aspect
     ratios; arbitrary custom grids are not covered by the automatic preset's
     accuracy claims.
   - Copy input arrays and retain existing ownership, mutex and GIL-release
     behaviour. User mutation must not change an in-progress native solve.

   Provide `wind.preview_grid(...)` for legacy and explicit grids in Stage B1,
   using the same geometry and domain preparation path as `run` but without
   allocating QES flow arrays.
   Return effective faces, centres, layer thicknesses, shape, cell count, growth
   ratios, aspect ratios, domain bounds and roof-representation diagnostics.
   The B1 return type is `GridPreview`: `x`, `y`, `z`, `z_faces`, `solver_dz`,
   `origin`, `crs`, `resolution`, `domain` and `terrain`, with derived `shape`,
   `cell_count`, `dz`, `growth_ratios`, `thin_cell_aspect_ratios` and
   `tall_cell_aspect_ratios`. Ratios use solver thicknesses before coordinate
   accumulation roundoff; `dz` uses effective face separations. Coordinates
   and metadata are owned snapshots; preview is not a prepared solver.
   Memory estimates, if added, must be based on the actual allocated array
   types and labelled as estimates rather than promises of peak process memory.

3. **Implement the automatic policy as a constrained vertical grid.**

   Let `r = resolution`, `zp = pedestrian_height`, and `Hi` denote the positive
   building heights after the existing geometry preparation. The following are
   candidate settings for the C1 prototype, not validated release defaults:

   | Quantity | Proposed starting value | Reason |
   | --- | --- | --- |
   | Evaluation height `zp` | 1.5 m, configurable | A common pedestrian evaluation height; users can request 2 m or another height. |
   | Near-ground target thickness `h0` | `min(0.5 m, zp / 3.5, r)` | Places the evaluation height at approximately the fourth centre or higher in the fine band. |
   | Maximum thin-cell aspect ratio `r / dz` | 8, provisional candidate | The uniform 0.25 m tower grid at r = 2 m fails the common accuracy check; this does not establish that every aspect-8 grid fails. Select the limit using generated-grid evidence. |
   | Base minimum thickness `b` | `min(0.2 m, r)` when `min_layer_thickness=None`; otherwise the explicit value | Avoids a fixed 0.2 m floor contradicting finer horizontal resolutions. |
   | Effective minimum layer thickness `hmin` | `max(b, r / max_aspect_ratio)` | No building or pedestrian rule may force layers thinner than this. |
   | Fine-region height | `2 * zp` | Gives a fine band on both sides of the evaluation level for sampling and local gradients. |
   | Adjacent-layer growth factor | 1.15 | Conservative starting point within the cited stretching guidance. |
   | Building constraint | `max(hmin, Hi / 10)` while below `1.5 * Hi` | Preserves several layers through each building and a buffer above its roof, without letting very short structures drive extreme anisotropy. |
   | Additional building-region cap | `r` | Avoids vertical cells becoming coarser than the horizontal spacing around roofs. |
   | Upper-region cap | `4 * r` | Allows savings aloft without unlimited geometric growth. |

   The 0.5 m cap, fine-region extent, roof buffer, aspect limit, exact growth
   factor and upper-region cap are engineering choices to benchmark. They are
   not a published QES recipe. In particular, the `1.5 * Hi` buffer does not
   claim that all roof effects end at that height.
   Benchmark actual generator outputs, including their effective float32
   coordinates. At `r=2 m`, the proposed seven-layer fine band has thickness
   about 0.428571 m and aspect ratio about 4.67; it differs from the tested
   0.5 m hand-built grid. Do not substitute an aspect limit of 4 without
   re-evaluating feasibility and the resulting fine-band count.

   Treat `h0` as a preferred target, not a hard equality or a hard upper bound.
   The hard pedestrian limit is `zp / 2.5`: for equal fine layers, the third
   centre is at `2.5 * dz`. Select an integer layer count and its thickness
   jointly, instead of rounding a count after choosing a fixed thickness.

   Require finite positive settings, `max_aspect_ratio >= 1`, and an explicit
   base minimum no greater than `r`. The default base minimum follows `r` below
   0.2 m; an incompatible explicit override is rejected with advice to lower
   `min_layer_thickness`. Do not advise merely refining `resolution` in that case.
   Require `upper_layer_cap >= r` so the automatic height-dependent caps remain
   nondecreasing. Report `r / dz` and `dz / r` separately in the preview; the
   thin-cell aspect limit does not constrain tall upper cells.
   Require `fine_region_height >= pedestrian_height` when overridden, then check
   actual third-centre placement and bracketing after generation. Resolve `r`
   and building heights at native float32 precision. A base-minimum/upper-cap
   equality affected only by narrowing may resolve to `r` when both values
   narrow identically; preserve the requested values in metadata.

   Define a cap at each height using buildings still relevant there:

   ```text
   active(z) = {Hi where z < 1.5 * Hi}

   if active(z) is nonempty:
       building_cap(z) = min(r, max(hmin, min(Hi / 10 for Hi in active(z))))
   else:
       building_cap(z) = upper_layer_cap
   ```

   For requested fine-band height `L` (default `2 * zp`), define:

   ```text
   hmax = min(r, zp / 2.5, building_cap(0))
   htarget = clamp(h0, hmin, hmax)
   n_min = ceil(L / hmax)
   n_max = floor(L / hmin)
   ```

   Reject `hmin > hmax` before evaluating the clamp. If the integer interval is
   nonempty, choose `n` in `[n_min, n_max]` minimizing `abs(L / n - htarget)`;
   break ties toward fewer layers. The floor/ceiling candidates around
   `L / htarget`, clipped to the interval, suffice. Use `n` equal layers of
   thickness `L / n`. Record deviations from the preferred target, including
   cases where the effective layer is thicker than 0.5 m.

   If the interval is empty despite `hmin <= hmax`, extend the fine band to
   `L_effective = ceil(L / hmax) * hmin` using that many layers of `hmin`.
   This is the smallest feasible upward endpoint adjustment for equal layers.
   Record the requested and effective fine-band heights; never shorten the band
   or violate `hmin` to hit its requested endpoint. Reject if the extension
   conflicts with the domain top or its boundary requirements. Treat integer
   endpoint comparisons consistently under floating-point rounding, then recheck
   the effective float32 coordinates and constraints.

   With `zp=1.5 m`, default `L=3 m`, and no tighter building constraint:

   | `resolution` | `hmin` | Selected fine band |
   | --- | --- | --- |
   | 2 m | 0.25 m | 7 layers of approximately 0.428571 m |
   | 4 m | 0.5 m | 6 layers of 0.5 m |
   | 4.5 m | 0.5625 m | 5 layers of 0.6 m; documented target adjustment |
   | 5 m | 0.625 m | Rejected: the 0.6 m pedestrian limit cannot be met |
   | 0.1 m | 0.1 m | 30 layers of 0.1 m; no artificial 0.2 m minimum |

   The sensitivity study must separate interpolation bias from changes in
   building flow. For `L = 2 * zp`, an odd equal-layer count puts `zp` at a
   centre; an even count generally puts it at a face. Record the effective
   bracketing centres and the analytic flat-profile sampling error. In Stage C2,
   compare feasible centre-aligned candidates with this target-thickness rule
   before freezing the count-selection policy. Do not force alignment by
   violating `hmin`, the pedestrian limit or float32 coordinate checks, and do
   not treat an exact sampled inflow value as evidence of resolved building
   flow. The current count-selection rule remains a proposal until that test.

   Add an endpoint-extension regression: with `r=2.24 m`, `hmin=0.28 m`,
   `L=3 m` and an active building cap of `0.29 m`, the feasible count interval
   is empty. Use 11 layers of 0.28 m and record a 3.08 m effective fine band.

   A short building therefore constrains layers near its own roof without
   forcing thin layers to the top of the domain. Treat all retained buildings
   consistently; do not silently discard small buildings to meet a cell budget.
   Buildings shorter than `10 * hmin` receive fewer than ten layers; report
   their roof-representation error instead. An empty-city case uses the fine
   band followed by upper-region growth.

   Generator instructions:

   - Validate all settings before generating layers. Automatic growth must be
     greater than one and at most 1.20 for the initial supported preset. A
     constant custom grid remains available through explicit faces.
   - Choose equal fine layers with the joint count/thickness algorithm above.
     Prefer the requested fine-band endpoint, using the documented upward
     extension only when no count satisfies both thickness bounds.
   - Above that band, choose the next thickness no larger than the previous
     thickness times the growth factor and the cap applicable across the cell.
     Evaluate caps conservatively at the lower face; the caps are nondecreasing
     in height because buildings drop out of `active(z)` as `z` rises.
   - Fit the domain top while preserving the fine band. Find the smallest upper
     count whose maximal-growth path reaches the top. If that count times the
     fine thickness exceeds the remaining height, no upper count is feasible.
     Otherwise walk the upper path using
     `h = min(previous * growth, cap(lower_face), remaining_height / remaining_count)`.
     Once the average binds, a constant tail fits the endpoint while respecting
     nondecreasing caps and growth. The adjusted tail can span as many upper
     layers as needed; do not append a thin remainder or change the fine band.
   - Recheck every final thickness, adjacent ratio, aspect ratio and `hmin`
     after endpoint fitting. Reject an infeasible requested combination with
     an actionable message.
   - Work in float64 while planning. Apply the canonical float32 accumulation
     (section 7.1) before reporting the effective grid, and validate it again.
     Bound endpoint drift by `gamma_(n+1) * top` as described in the C1 outcome.
     Check narrowed solver thicknesses with at most `8 * float32_eps` relative
     tolerance; actual faces/centres must remain strictly increasing and all
     coefficients finite/positive. Recheck caps at effective lower faces.
   - Fail before allocation if physical cells exceed the configured allocation
     ceiling, or staggered faces or individual dimensions exceed hard index or
     representation limits. Treat planning cell targets as soft, and configure
     `max_cells` for the accepted hardware/study budget as described above.
     Never silently increase near-ground spacing when `max_cells` is exceeded.

   Do not force every roof onto a vertical face. One shared grid spanning a city
   can otherwise acquire many nearly coincident faces and tiny layers. Instead,
   report each building's stair-step roof height and its error relative to the
   input geometry. QES marks a cell solid when its centre is at or below the
   roof (`PolyBuilding.cpp:174-180`), so the represented roof is the top face of
   the highest such cell and the error lies within half a layer. Test whether
   those errors materially alter pedestrian winds.

4. **Keep domain extent and vertical spacing as separate decisions.**

   Automatic layers fit the domain selected by the existing bounds and
   clearance rules. This feature does not change horizontal padding or enlarge
   existing domains.

   With explicit bounds, require explicit faces to end at the requested local
   top within the documented float32 representation tolerance. Reject genuine
   discrepancies instead of clipping or rescaling a custom grid. Automatic mode
   fits an explicit top in its float64 plan, reporting bounded effective float32
   accumulation error, instead of expanding it to whole cells as the legacy
   path does. Without explicit bounds, an explicit face list may define
   the vertical top if it covers the automatically required clearance and
   reference height; automatic mode uses the computed top. Preserve the
   existing empty-city bounds rule.

   The dataset path always passes explicit bounds, computed in
   `_dataset_city.py:98-104` by duplicating the default-top rule at
   `_city.py:226`. Move that rule into one shared helper so both paths stay
   identical.

   Require enough vertical extent to bracket the requested evaluation height,
   provide the specified fine band, and satisfy native roof and boundary
   requirements. Roof checks must use effective cell coordinates, not `nz * r`.

   The current default 20 m roof clearance is not a general comfort-study
   recommendation. COST 732 gives a starting clearance of `5 * Hmax` above the
   tallest roof and discusses its dependence on boundary conditions. Evaluate
   domain-height sensitivity separately, including a reference domain around
   `6 * Hmax` total height where appropriate. QES's boundary treatment differs
   from typical RANS conditions, so do not adopt that height as an untested QES
   guarantee. [COST 732, section 5.5.1](https://www.airshed.co.uk/wp-content/uploads/2018/03/COST-732-Best-Practice-Guideline-May-2007.pdf).

   Do not confuse a reduction in boundary error from a taller domain with an
   improvement caused by stretching. Hold domain bounds fixed in grid comparisons.

5. **Fix and extend QES-Public.**

   All changes go to the `dtcc-embed` branch as separate commits, in the order
   below. Update the submodule pin and `src/dtcc_qes/_qes_revision.txt` when
   delivering each stage. Preserve the no-I/O build (`check_noio`) and the
   native symbol audit (`tools/check_native_symbols.py`).

   **5.1 Correct the vertical right-hand side (Stage 0).** In
   `Solver_CPU.cpp:75-77` and `Solver_CPU_RB.cpp:78-80`, remove only the
   leading `domain.dz_array[k] *` factor from both vertical terms. Leave the
   literals and operand order unchanged so that cases without vertical
   divergence keep bitwise-identical arithmetic:

   ```cpp
   // Before
   + ((WGD->m[icell_cent] * domain.dz_array[k] * 0.5 * (domain.dz_array[k] + domain.dz_array[k + 1])
         * WGD->w0[domain.faceAdd(icell_face, 0, 0, 1)]
       - WGD->n[icell_cent] * domain.dz_array[k] * 0.5f * (domain.dz_array[k] + domain.dz_array[k - 1])
           * WGD->w0[icell_face]))
   // After
   + ((WGD->m[icell_cent] * 0.5 * (domain.dz_array[k] + domain.dz_array[k + 1])
         * WGD->w0[domain.faceAdd(icell_face, 0, 0, 1)]
       - WGD->n[icell_cent] * 0.5f * (domain.dz_array[k] + domain.dz_array[k - 1])
           * WGD->w0[icell_face]))
   ```

   The three CUDA solvers (`Solver_GPU_*.cu`) contain the same expression. They
   are not built here, but correct them in the same commit so the fix can be
   offered upstream with the injected-`w0` reproduction.

   This correction changes uniform-grid results wherever parameterizations
   create vertical divergence. The `flat` and `one_building` references contain
   no interior vertical divergence and are expected to remain unchanged. Verify
   this; if they change, investigate rather than refreshing them. Do not
   generate reference arrays for affected cases from pristine upstream QES,
   which carries the defect; assert flux bounds instead. Update
   `docs/validation.md` and the release notes.

   **5.2 Add a validated stretched `Domain` constructor (Stage A).** The
   public constructors (`Domain.cpp:10`, `Domain.cpp:45`) always build uniform
   layers. A private helper, `defineVerticalStretching(const std::vector<float>&)`
   (`Domain.cpp:60`), exists but is unused. It also reads `dz_value[k - 1]`
   without checking the vector length, and it silently sets `dz()` to the
   thinnest layer. Add:

   ```cpp
   Domain(int nx, int ny, float dx, float dy, const std::vector<float> &dz_layers);
   bool verticallyUniform() const;
   ```

   - Require `dz_layers.size() == nz` with `nz >= 2`, the existing face-count
     index limit, and finite positive layers.
   - Keep the ghost convention `dz_array[0] = dz_array[1]`. The ground mirror
     condition (`lambda(k=0) = lambda(k=1)`) and the first-cell `n` coefficient
     rely on it.
   - After `defineVerticalGrid()`, require strictly increasing finite float32
     `z_face` and `z`. Throw `qes::InputError` if accumulation collapses a
     layer.
   - Keep `dz()` as the minimum layer thickness (upstream semantics) and
     document it. Its remaining uses are `Solver::B`, which the CPU solvers do
     not read, and `Wall::wallLogBC`, which the compiled core never calls.
   - Separately, fix `getDomainSize()` (`Domain.h`), which returns
     `{dx, dx, dz}` instead of `{dx, dy, dz}`. This is latent while `dx = dy`.

   **5.3 Replace the embedded stretching guard.** `WINDSGeneralData.cpp:77`
   rejects any `verticalStretching != 0`. Reuse the existing
   `SimulationParameters::verticalStretching` and `dz_value` fields as the
   declared contract instead of adding new ones, which keeps the fork close to
   upstream:

   - Allow `verticalStretching == 1` only when `dz_value.size()` equals the
     domain's physical `nz` and `domain.dz_array[1..nz]` equals `dz_value`
     exactly.
   - Reject `verticalStretching == 0` with a nonuniform domain.
   - Keep rejecting cut cells (`meshTypeFlag != 0`) and reject `logLawFlag != 0`
     with stretching; the log-law wall code uses scalar `dz`
     (`Wall.cpp:676-677`).

   The consistency check prevents silent fallback in the embedded no-I/O path.
   The standalone I/O driver's choice of domain constructor is outside this
   binding stage; its legacy handling of XML vertical stretching remains
   unvalidated. Do not claim standalone XML support from this feature.

   **5.4 Compare vertical layers in solver compatibility checks.**
   `Solver::validateSolve` (`Solver.cpp:93`) compares only cell counts. Also
   require equal `dz_array` between the solver's domain copy and the wind
   field's domain.

   **5.5 Finish the parameterization review.** The index review found the
   following; the remaining work is behavioural testing and a search for
   index offsets used as physical distances.

   | Code | Finding | Remaining action |
   | --- | --- | --- |
   | `PolyBuilding.cpp:166-187` occupancy | Uses `z` and `z_face`; solid when centre at or below roof | Roofs near faces and centres, across layer transitions |
   | `Rooftop.cpp`, `UpwindCavity.cpp`, `PolygonWake.cpp`, `StreetCanyon.cpp` | Use `z` and `z_face`; unpacked scalar `dz` unused | Search for `k + 1` and `k_end + 1` offsets that assume a fixed thickness; test zones that straddle thick layers |
   | `Sidewall.cpp`, `StreetIntersection.cpp` | No vertical spacing use | None |
   | `WindProfilerSensorType.cpp` | Profile at `domain.z`; source checked | Permanent analytic-profile test with corrected, bounds-checked harness |
   | `Wall::solverCoefficients` (`Wall.cpp:829`) | Uses adjacent thicknesses; source checked | Independent operator and conservative-flux tests |
   | `Wall::wallLogBC` (`Wall.cpp:354`) | Scalar `dz`; never called in the compiled core | Keep rejected by 5.3 |

   Remove the unused `auto [dx, dy, dz] = getDomainSize()` bindings, or keep
   `-Wunused` clean, so that a future scalar-`dz` use is visible in review.

   **5.6 Focused solver diagnosis, followed by an evidence-based remedy.**
   The diagnostic milestone is complete; its findings and the next B1 decision
   are recorded above and in `docs/vertical-grid-diagnosis.md`. The following
   describes the diagnostic method and the conditions on a remedy. The later
   opt-in precision milestone satisfies those conditions on its tested fixtures;
   retain these diagnostic instructions for any newly failing configuration.
   Start with one failing 0.25 m tower configuration and a passing 0.5 m control
   at identical bounds, geometry and wind. Leave production point SOR, its
   relaxation factor and stopping rule unchanged during diagnosis. Distinguish
   operator/boundary inconsistencies, roundoff and slow convergence before
   selecting a remedy:

   - At failing fine-grid checkpoints, record the locations and magnitudes of
     conservative flux residuals, stencil residuals, multiplier values and
     updates. Re-evaluate the stencil/RHS and face-correction expressions in
     float64 as independent diagnostics. Compare conservative corrected face
     flux with the stencil prediction before and after velocity rounding and
     solid-face zeroing, including cells beside buildings and prescribed
     boundaries. Keep the same physical scales and interior-cell definition.
     The existing divergence helper already evaluates flux arithmetic in
     float64 from stored float fields and coefficients; promoting that helper
     alone cannot recover precision lost in the solve or velocity correction.
   - If velocity is stable but residual maxima fluctuate above the target,
     test a study-only higher-precision multiplier/RHS/update path. Verify the
     corrected face flux as well: promoting only a diagnostic expression or
     storing an already-rounded float in a double cannot repair the field.
     Preserve the legacy production path until an opt-in change is justified.
   - If convergence rate, rather than roundoff, erases the cell savings, test
     opt-in vertical line relaxation: a tridiagonal solve per column inside
     the red-black sweep in `Solver_CPU_RB.cpp`. Line relaxation addresses
     anisotropic conditioning; it does not by itself establish a remedy for
     a precision plateau.
   - Compare remedies with point SOR on the focused fixtures first, including
     serial/OpenMP agreement. Run the complete gate after a supported remedy,
     rather than repeating the full matrix after every diagnostic experiment.
     Retain the common residual and velocity-stability targets. Use a
     successfully tighter-converged subset to assess the error budget; a
     failed ten-times-tighter run is diagnostic evidence, not validation of
     the current thresholds. Do not weaken a target to accept a particular grid.
   - End this diagnostic milestone with residual locations, operator/flux
     comparisons and a documented next decision: fix an identified defect,
     test a precision remedy, investigate conditioning, or retain an explicitly
     limited validated scope while the cause remains unresolved. Then proceed
     to B1 without treating failed fine-grid cases as accepted references.
     A production solver change requires the native regression checks in
     section 11; an automatic preset requires the C2 evidence below.

   **5.7 Leave the stopping rule unchanged.** Changing the multiplier
   criterion would alter legacy outputs. Report the true residual from the
   bridge instead (section 6.3). A residual-based or scaled stopping rule is a
   separate, opt-in follow-up.

6. **Extend the native bridge and bindings (`src/cpp`).**

   **6.1 Configuration types (`wind_config.h`).** Use one source of truth: a
   vector of physical layer thicknesses, where an empty vector selects the
   legacy path.

   ```cpp
   struct GridConfig {
     int nx = 40, ny = 30, nz = 20;
     double cell_size = 2.0;        // x/y spacing; also z spacing when dz_layers is empty
     std::vector<double> dz_layers; // physical layers, bottom to top; empty selects uniform
     std::int64_t max_cells = 2000000;
   };

   struct DivergenceStats {
     double interior_max = 0, interior_rms = 0, top_band_max = 0;
     std::size_t cells = 0, top_band_cells = 0;
   };
   ```

   Add `std::vector<float> z_faces` (physical faces, `nz + 1` values) and
   `DivergenceStats divergence` to `WindData`.

   **6.2 Input preparation (`qes_inputs.cpp`).**

   - When `dz_layers` is nonempty, require `dz_layers.size() == nz`. Narrow each
     layer with the existing `positive()` helper. Reject any layer whose solver
     coefficients `1 / (dz_k * 0.5 * (dz_k + dz_neighbour))` are not finite in
     float32, matching the horizontal check at `qes_inputs.cpp:52-54`.
   - Set `simulation.verticalStretching = 1`, `simulation.dz_value` to the
     narrowed layers, and the z component of `simulation.grid` to the minimum
     layer, matching `Domain::dz()`. Update the comment at line 58.
   - Replace the roof-guard accumulation at lines 104-110, which adds
     `spacing` `nz` times, with accumulation over the narrowed layers.
   - Add `std::vector<float> vertical_faces(const GridConfig &)`, the single
     native float32 face accumulation used by preparation, the runner and the
     native tests.
   - Add `qes::Domain make_domain(const QESInputs &)`. It selects the uniform or
     stretched constructor. `wind_runner.cpp:18`, `check_physics.cpp:79` and
     `check_openmp.cpp:44` construct the domain directly today and must use it.

   **6.3 Divergence residual (new `divergence.h` and `divergence.cpp`).** Move
   the six-face flux calculation from `tests/native/check_physics.cpp` into the
   bridge. Use domain dimensions rather than fixture constants and actual layer
   thicknesses. Report:

   - interior maximum and volume-weighted RMS, in s⁻¹,
     `sqrt(sum(V * divergence**2) / sum(V))`;
   - the prescribed top band separately (QES corrects `w` only below it);
   - interior and top-band fluid-cell counts.

   Define the ranges using `nz = domain.nz() - 2`, the physical layer count:

   | Native physical layer indices | Treatment |
   | --- | --- |
   | `1 <= k < nz - 1` | Solved interior; contributes to interior max/RMS. |
   | `k == nz - 1` | Last solved band with an uncorrected upper `w` face; report separately. |
   | `k == nz` | Highest physical layer, outside this coefficient-based flux diagnostic; mark as unassessed. |

   Run the coefficient-based loop only while `k < nz`. At `k == nz`, accessing
   `dz_array[k + 1]` is out of bounds and the coefficients have not received the
   same scaling. If a future diagnostic covers that top layer, compute it from
   independently defined physical face areas instead of reusing this formula.
   Expose the unassessed-top-layer policy in diagnostic metadata.

   If an assessed region has no fluid cells, keep its count at zero, skip RMS
   division and expose its metrics as `None` in Python, not a false zero-residual
   success. Small domains with no assessed interior cannot pass the benchmark
   acceptance gate. Reject nonfinite face values explicitly. Test the smallest
   allowed grids and both band boundaries with sanitizers/bounds checks.

   Exclude solid cells and the prescribed lateral boundary cells, as now. Add
   the source file to the `qesbridge` object library in `CMakeLists.txt`.

   **6.4 Runner (`wind_runner.cpp`).** Build the domain with `make_domain`.
   After the solve and still under the native mutex, compute
   `DivergenceStats` and copy `domain.z_face[1 .. nz + 1]` into
   `WindData::z_faces`. The existing centre averaging needs no change.

   **6.5 Python bindings (`bindings.cpp`).**

   - Add an optional keyword argument, `dz_layers`, to `WindRunner.prepare`,
     using the existing `Floats` type with `noconvert()` and `.none()`. Copy it
     with `copy_input` while holding the GIL, as for the building arrays; None
     or an empty array selects the legacy path. Do not expose `dz_layers` as a
     `GridConfig` attribute: nanobind returns copies of STL members, so
     in-place list mutation would silently do nothing.
   - Add `z_faces` as a `(nz + 1,)` float32 array to the result dictionary.
     Add `max_divergence`, `rms_divergence` and `top_band_max_divergence` to
     `diagnostics`, with the corresponding interior/top-band counts. Return
     `None` for metrics with zero contributing cells.
   - Native validation must reject a layer count that disagrees with `nz` even
     when callers bypass Python validation.

7. **Update the Python package (`src/dtcc_qes`).**

   **7.1 `vertical_grid.py` (new).**

   - `VerticalGrid` is a frozen dataclass with `auto(...)` and `from_faces(...)`
     constructors.
   - A planning function generates float64 layers from building heights, the
     top, `resolution` and the settings in section 3.
   - `effective_faces(layers)` applies the canonical float32 accumulation:
     `np.r_[0, np.cumsum(layers.astype(np.float32), dtype=np.float32)]`. NumPy's
     float32 `cumsum` adds values in order, matching the native loop; this is
     the pattern already used at `_city.py:240`. A separate native coordinate
     validator is therefore unnecessary, and native preparation re-validates
     anyway.
   - Include a generator version constant and `to_metadata()`, which returns a
     serializable record of requested and effective settings.
   - Re-export `VerticalGrid` from `wind` and add it to `__all__`.

   **7.2 `_city.py`.**

   - Add a `vertical_grid` parameter to `prepare_domain` (line 196). Move the
     default-top rule (line 226) into a shared helper, also used by
     `_dataset_city.py`.
   - Legacy mode remains byte-for-byte unchanged:
     `nz = ceil(top / spacing)` and uniform faces.
   - In stretched mode, take `nz` from the layer count. Take the z extent,
     `local_bounds` and `effective_bounds` from the effective faces. Generalize
     the roof check at lines 240-252 to use those faces.
   - Apply the `max_cells`, index-limit and 10,000-layer checks to the actual
     layer count.
   - Pass the layers to the runner through `PreparedDomain`.
   - Add a `vertical_grid` record to the domain metadata: mode, generator
     version, requested and effective settings, faces, minimum and maximum
     thickness, maximum growth ratio, maximum aspect ratio, and per-building
     roof representation.

   **7.3 `wind.py`.**

   - Add `vertical_grid=None` to `run` and validate its type in
     `_validate_grid`.
   - Pass `dz_layers` to `runner.prepare` and `z_faces` and the residual
     diagnostics to `WindResult`.
   - Add `"stair-step cells with stretched vertical layers"` to
     `simplifications` when applicable.
   - Factor geometry extraction and domain preparation into one internal
     function shared with `preview_grid` (Stage B1). Extend preview to automatic
     grids alongside the C1 generator.

   **7.4 `result.py`.**

   - Add `max_divergence`, `rms_divergence` and `top_band_max_divergence` to
     `SolveDiagnostics`, with default `None` so that existing construction
     keeps working. Its docstring already says the multiplier change is not a
     residual; point readers to the new fields. Include defaulted optional
     contributing-cell counts so unavailable and assessed diagnostics differ.
   - Add `z_faces: np.ndarray | None = None` as the last `WindResult` field, so
     existing positional construction remains valid. When it is `None`, derive
     legacy faces with the canonical float32 accumulation of `resolution`.
   - Add a `dz` property and a `vertical_uniform` property. Retain `z` as
     physical centres and `resolution` as the horizontal spacing.
   - Add `sample(height, method="nearest" | "linear")`, defaulting to nearest.
     `height` is metres above flat ground. This returns a horizontal plane at
     native x/y centres as `WindSample`: owned float64 velocity (y, x, component),
     derived speed (y, x), a validity mask, requested/sampled heights, method,
     origin and CRS. It does not sample an arbitrary x- or y-normal plane.
   - For linear sampling, first test whether the requested height equals an
     effective centre. If so, use that cell alone, including at the first/last
     centre. A solid neighbour with zero weight must not invalidate the sample.
     Otherwise interpolate velocity components between the two strictly
     bracketing centres, then calculate magnitude. Both contributing cells must
     be fluid. Outside the centre range, return invalid samples without
     extrapolation; use NaN values with an explicit validity mask.
   - Do not round an arbitrary height to float32 before locating it. For an
     exact-centre request compare the numeric value and widened effective
     centres in float64. A float32 scalar centre widens exactly, while a nearby
     distinct float64 request uses the normal interpolation rules. Return
     `sampled_height=None` when linear sampling has no contributing centres.
     Widen local axes to float64 before adding large global translations.
   - Nearest sampling retains existing endpoint clipping and lower-index tie
     breaking, records the actual selected centre, and tests only that selected
     cell for validity. Validate finite heights and the physical domain range.
     Never interpolate categorical cell flags.
   - In `to_dtcc()` (line 50), raise for stretched grids with a message
     pointing to `sample()` and slices. For uniform grids whose vertical spacing
     differs from `resolution`, use the true extent `z_faces[-1]` instead of
     `nz * resolution` (line 62).

   **7.5 `_logging.py`.** Include the maximum interior divergence in the
   `_log_solve` message alongside iterations and `converged`.

   **7.6 `datasets.py` and `_dataset_city.py` (Stage B2, after C2).**

   This integration depends on the B1 sampler and the validated automatic
   generator. Do not expose a dataset `"auto"` option before those exist.

   - Add typed, serializable options to `QESWindArgs`:
     `vertical_grid: Literal["uniform", "auto"]`, `pedestrian_height`,
     `growth_rate`, `solver_precision: Literal["float32", "float64"]` and
     `slice_sampling: Literal["nearest", "linear"]`. Include
     them in request/cache identity and provenance, and verify that
     `DatasetBaseArgs` includes new arguments automatically.
   - Update the `resolution` description: horizontal spacing, and also
     vertical spacing in uniform mode.
   - In `validate_solver_options`, reject `product="field"` with
     `vertical_grid="auto"` before the expensive solve, until explicit uniform
     resampling exists.
   - In the first release, `slice_sampling="linear"` is supported only for
     `product="slice"` with effective `slice_axis="z"`. Apply `slice_height`'s
     existing axis override before validation. Reject linear x/y slices before
     fetching the city or solving; nearest x/y slices remain supported. Reject
     linear sampling for a field product rather than silently ignoring it.
   - For a linear horizontal slice, use `result.sample` at the requested height
     (or the existing relative-position-derived height). Populate output points
     at that height, not a snapped centre. Map the native x/y plane to display
     samples with the existing nearest x/y lookup; describe the method as
     vertical linear interpolation with nearest horizontal sampling, not full
     trilinear interpolation.
   - Include a `valid` sample field, propagate it with velocity/speed and preserve
     invalid values. Any `cell_flags` field uses the nearest source cell and is
     documented as categorical provenance, not a replacement for `valid`.
     Record requested and sampled heights and the method in metadata. Future
     linear vertical slices require a separate pointwise sampling contract.
   - Record the residual diagnostics in `context.health` next to `converged`.
   - Use the shared default-top helper in `_dataset_city.py`.
   - Integrate with the existing uncommitted dataset work without overwriting
     unrelated changes.

8. **Handle DTCC output without misrepresenting the grid.**

   The installed DTCC `VolumeGrid` derives coordinates from uniform per-axis
   steps (`xstep`, `ystep`, `zstep`). Existing `WindResult.to_dtcc()` therefore
   cannot represent stretched layers faithfully just by changing its bounds.
   `FieldSlice` is a `PointCloud` with explicit point coordinates.

   First-release policy:

   - Keep uniform `to_dtcc()` behaviour unchanged. Uniform vertical spacing that
     differs from x/y spacing is represented using its true vertical extent.
   - Preserve native stretched coordinates in `WindResult`.
   - Support `FieldSlice` output using its explicit point coordinates.
   - Reject direct stretched-grid conversion to a uniform `VolumeGrid` with a
     message pointing to slices or explicit resampling.
   - Defer uniform resampling to a separate follow-up after B2; it is not a
     prerequisite for sampling, automatic grids or slice integration. If added,
     provide an explicit operation with a requested output spacing, sampling
     method, solid-mask policy and provenance. Check its allocation budget
     independently; resampling can erase the memory savings.

   Uniform resampling is for interchange/display and must not be described as a
   new solve or a conservative flux transfer. A native rectilinear DTCC grid is
   a useful follow-up but is not required to ship the first solver extension.

9. **Verify numerical correctness before tuning the automatic preset.**

   | Test group | Required checks |
   | --- | --- |
   | Right-hand side (Stage 0) | Reproduce the specified uniform injection probe with interior maximum divergence below 1e-6 s⁻¹ after correction; test a stretched grid against a separately declared bound and include `u0` controls. The dz = 2 and 4 m cases must fail against the uncorrected solver. |
   | Multi-building flux (Stage 0) | Two-building street canyon with default flags meets the common residual bounds and velocity-stability checks in section 10. The one-building fixture cannot detect the defect. |
   | Residual diagnostic | Bridge `DivergenceStats` equals an independent calculation; a deliberately perturbed face is detected. Exercise the last interior band, prescribed top band, unassessed top layer and zero-count cases under bounds checking. |
   | Legacy compatibility | `flat` and `one_building` references unchanged after Stage 0; ownership, coordinate ordering and default API behaviour. Explicit equal-thickness layers reproduce the legacy path bitwise. |
   | Grid construction | Exact topology, face/centre relationships, physical/ghost indexing, bounded growth, aspect and `hmin` limits, endpoint fitting, empty cities and translated coordinates. Cover r = 4.5 m, r < 0.2 m, an empty feasible-count interval and incompatible explicit overrides. |
   | Invalid inputs | Nonfinite or duplicate faces, negative thicknesses, wrong lengths, insufficient top clearance, float32 collapse, index limits and cell-budget failures at the Python, bridge and `Domain` entry points; guard mismatches between `dz_value` and the domain. |
   | Analytical profiles | Neutral `ln((z + z0) / z0)` profiles at actual centres for cardinal directions and multiple roughness lengths; calm flow and finite results. |
   | Manufactured flow | Nonzero vertically varying initial velocity; agreement of assembled operators with independent conservative flux calculations. |
   | Buildings | Occupancy and zero solid velocity across layer transitions; short and tall buildings, roofs near faces/centres, parameterization zones straddling thick layers, and repeated solves. |
   | Conservation | Maximum and volume-weighted RMS divergence using staggered faces and actual cell volumes. |
   | Backends | Serial/OpenMP agreement and thread-count repeatability with stretched grids; sanitizer and no-I/O checks. |
   | Results | Face arrays, interpolation, solid masks, sampling provenance and rejection of stretched `to_dtcc()`. Exact first/interior/last centres with a solid zero-weight neighbour, true two-cell solid crossings, out-of-range linear heights, nearest endpoint clipping, linear x/y-slice rejection and the slice-height axis override. |

   Generalize `tests/native/check_physics.cpp` to use the shared bridge
   residual and domain dimensions instead of fixture constants. Add the
   canyon and injected-`w0` cases there. Extend `check_runner.cpp`,
   `check_safety.cpp` and `check_openmp.cpp` for stretched preparation, invalid
   layers and backend agreement.

   On the Python side, add `tests/test_vertical_grid.py` for generator
   properties, and extend `test_city_adapter.py`, `test_runner.py`,
   `test_physics.py`, `test_results.py` and `test_datasets.py`. Use
   manufactured linear fields to verify interpolation independently of the
   wind model, and measure interpolation error on log profiles.

   Continue reporting the known prescribed-top-band limitation separately from
   the solved interior. Do not present multiplier-change convergence as proof
   of mass conservation. Establish numerical acceptance bounds using controlled
   manufactured cases and the error budget, then check whether float32 arithmetic
   can meet them. Do not redefine a measured plateau as an acceptable residual.
   Preserve build commands, source revision, geometry, ranges and complete
   outputs for all regenerated probe results in the validation report.

10. **Gate automatic presets on accuracy and cost; validate sampling separately.**

    **Sensitivity and cost study (completed after Stage A).** Use the existing
    measurements to guide further work. B1 sampling and explicit preview have
    independent correctness criteria; this study gates claims about accuracy
    and cost, not all API development:

    - On the benchmark geometries below, at `r = 2 m` and fixed bounds, run
      explicit uniform layers of 2, 1, 0.5 and 0.25 m and one hand-built
      stretched grid.
    - Use a small study-only sampler with the section 7.4 semantics until the
      public sampler is implemented, then verify parity with B1. Record
      pedestrian `K` changes at common
      sample points, iterations to the common acceptance criteria below, and
      wall-clock time.
    - Record iterations against aspect ratio to inform candidate limits and
      the diagnosis in 5.6; do not infer a universal limit from one geometry.
    - Include the already-run 1 m family in accuracy/cost summaries alongside
      2 m, 0.5 m, 0.25 m and stretched grids. Withhold pairs that depend on a
      failed solve, including the current 0.25 m tower references.
    - Select automatic settings that meet a declared pedestrian-speed error
      budget against an accepted finer reference, and compare cost with the
      cheapest uniform grid meeting the same requirements. Do not require
      coarse grids to be materially wrong: they may be adequate for a case.
      Record the supported scope and decision in `docs/validation.md`.

    Use three kinds of evidence:

    - Analytical/manufactured cases establish numerical correctness.
    - A finer QES solution establishes sensitivity to vertical discretization.
    - Wind-tunnel measurements assess physical-model accuracy.

    Agreement with fine-grid QES is not experimental validation. Refining only z
    is not proof of full three-dimensional grid independence; repeat selected
    cases at a finer uniform x/y `resolution` to expose horizontal limitations.
    Before broad automatic-parameter tuning in C2, run a taller-domain control
    preserving the lower vertical faces and the pedestrian comparison region,
    and a selected finer-x/y control sampled at the same physical locations.
    Document horizontal interpolation when native centres differ. These checks
    must establish whether the top boundary or horizontal resolution materially
    affects the proposed error budget before preset selection.

    Include an isolated building, a narrow passage, an array of blocks and a
    tower among lower buildings. Use multiple wind directions and retain all
    parameterizations enabled by the production bindings. The AIJ collection
    provides suitable experimental geometry, approach flow and measurements;
    Case A and Case D are useful starting points. [AIJ benchmark collection](https://www.aij.or.jp/%20jpn/publish/cfdguide/index_e.htm),
    [Case D dataset](https://zenodo.org/records/15402669).

    Match the experimental geometry, inflow and measurement heights. If fitting
    the available neutral logarithmic profile to measured inflow, document its
    residual error. Compare like quantities: magnitude of mean velocity is not
    generally the same as mean scalar speed. Separate an inflow or observable
    mismatch from grid error, and do not claim gust validation from a steady mean
    wind solver.

    At fixed x/y spacing and fixed bounds, compare:

    | Family | Purpose |
    | --- | --- |
    | Uniform z spacing equal to `resolution` | Existing-cost baseline. |
    | Uniform fine z spacing matching the near-ground layers | Cost and numerical reference for fine vertical resolution. |
    | Feasible centre-aligned fine bands and target-thickness bands | Separate sampling alignment from flow-resolution sensitivity, with analytic flat-profile controls. |
    | Automatic grids with growth 1.10, 1.15 and 1.20 | Growth-rate tradeoff. |
    | Automatic grids with aspect limits 4, 8 and 12 | Iteration cost against near-ground resolution. |
    | At least three systematic vertical refinement levels | Evidence that pedestrian results stabilize as vertical spacing decreases. |
    | Alternative roof buffers and upper caps | Determine whether proposed 1.5H buffers and 4r caps are adequate. |
    | Early larger-domain and finer-x/y controls | Distinguish vertical-grid sensitivity from boundary and horizontal errors before broad tuning. |

    Use actual C1 generator outputs, not only hand-built analogues. Include
    non-aligned roof heights and shallow structures to expose occupancy and
    roof-representation sensitivity. Centre-aligned candidates must still obey
    the near-ground layer-count, thickness, aspect and float32 constraints.
    Infeasible candidate combinations are reported as such, not silently relaxed.
    Extend the study driver/worker to consume Python-generated layers instead
    of duplicating the policy in C++. Archive generator version, settings,
    planned/effective faces and native solver thicknesses with each run. Retain
    the fixed-sweep controls and common criteria, and preserve the original
    study archive. Measure automatic planning separately from native preparation,
    solve and sampling so cell savings do not hide policy-generation costs.

    Compare values at the same physical sampling points, with the same sampling
    method and a documented common-fluid mask. Report points that switch between
    solid and fluid; do not silently remove them from the accuracy statistics.

    Measure pedestrian velocity components and speed, normalized errors, hotspot
    peak values and locations, experimental error, roof-height error, interior
    residual, total cells, peak process memory, iterations to matched accuracy
    and wall-clock time. Measure preparation, solve and export
    separately. Use fixed hardware, backend and thread count, and at least three
    timing repetitions for release performance claims after the algorithm is
    fixed. Report the first checkpoint meeting residual bounds, the checkpoint
    completing velocity-stability certification, and total certification work
    separately. The current approximately 2.5× speedup is a fixed-budget result,
    not an optimized time-to-accuracy claim. The multiplier tolerance can
    stagnate above its default; a stable residual can also be too large.
    Neither behaviour is an acceptance criterion.
    Cell-count reduction is not a runtime claim.

    **Common solve-accuracy gate.** Declare one set of bounds before comparing
    grid families and require both residual control and velocity stability:

    - For nonzero benchmark wind, use `Uscale = Uref` and `Lscale = Hmax`, or
      the reference height for an empty-city case. Hold these physical scales
      fixed across grids. Initial project targets are
      `max_divergence * Lscale / Uscale <= 1e-3` and
      `rms_divergence * Lscale / Uscale <= 1e-4`. Report dimensional values
      alongside them; exclude no additional interior cells to obtain a pass.
    - At fixed common pedestrian sample points, require the maximum change in
      velocity vector divided by `Uscale` to be at most `1e-3`, and its 95th
      percentile at most `5e-4`, over each of two successive iteration-budget
      comparisons, for example `N -> 2N -> 4N`. Require the residual bounds at
      all three checkpoints and document validity-mask changes. These iterative
      error targets are deliberately smaller than the grid-selection targets.
    - Ensure the study actually performs additional iterations: use an internal
      test-only fixed-sweep mode or a verified control that prevents early exit
      at each checkpoint. Do not change the public legacy stopping rule as a
      side effect. Report the work required to demonstrate stability as well as
      the first passing checkpoint.
    - A grid that stagnates above the bounds or still changes pedestrian
      velocities fails the comparison, regardless of its `converged` flag.
      Investigate operators, precision or the line-relaxation contingency. Do
      not loosen a threshold for that grid or compare its runtime with an
      accepted solution as if both reached equal accuracy.
    - Validate the chosen bounds against manufactured cases and a subset that
      successfully meets ten-times tighter residual targets, quantifying its
      effect on pedestrian outputs before freezing them. Do not require every
      exploratory grid to pass the tighter target merely to test B1 or prototype
      C1; failed tighter runs do not validate a preset's error budget. If targets
      need revision, justify it from the error budget and repeat all compared
      grids with the same revised criteria. Calm/injection tests use explicit
      absolute bounds such as section 9's `1e-6 s⁻¹`, not division by zero.

    These are provisional project accuracy criteria, not literature-derived
    guarantees. Record a residual plateau as a diagnostic observation only.
    The prescribed top-band residual remains separately reported, and its effect
    is assessed through domain-height sensitivity rather than hidden in an
    interior norm.

    Initial engineering targets for selecting the preset:

    - Define normalized speed `K = U / Uref` using the same nonzero imposed
      reference speed in all compared runs; report the exact speed observable.
    - Target a 95th-percentile absolute change in `K` below 0.05 between the
      selected and finer grid at the pedestrian sample points.
    - Target hotspot peak-speed changes below 5% where speeds are appreciable;
      use absolute normalized errors in low-speed regions.
    - Inspect maximum errors, fixed critical locations, high-speed regions and
      low-speed regions separately. Record hotspot displacement and competing
      peak magnitudes, but do not use raw global argmax displacement as a lone
      rejection criterion when peaks are nearly tied. Define critical locations
      and regions consistently across grids; percentiles must not hide failures
      at important locations.
    - Report experimental errors separately; numerical convergence does not erase
      model bias. Do not assign a universal experimental accuracy bound without
      the measurements.

    These thresholds are proposed project acceptance targets, not standards or
    established QES accuracy. Use the benchmark results to decide whether to
    tighten them and which settings to release. Choose the least expensive preset
    that satisfies the agreed accuracy constraints across the benchmark suite.
    Keep automatic mode opt-in until its useful range is demonstrated.

    For scale, a preliminary layer-count calculation with 30 m buildings, a domain
    around 180 m high, 0.5 m layers through 4 m, a 2 m cap through 45 m, an 8 m
    upper cap and growth 1.15 produces approximately 54 layers. Uniform 0.5 m
    spacing needs 360 layers at 180 m: about 6.7 times as many cells at fixed x/y
    spacing. This calculation precedes exact endpoint fitting and is not a solver
    benchmark. Iteration cost and wall-clock savings still need the corrected
    matched-accuracy study. Preserve the distinction in performance claims.

11. **Deliver in stages with explicit completion criteria.**

    | Stage | QES-Public | Bridge and Python | Completion criteria |
    | --- | --- | --- | --- |
    | 0: Solver correctness — locally complete | 5.1 RHS correction (CPU and CUDA source); local commit 046eb799; upstream reproduction documented, not submitted | 6.3 residual helper and diagnostics; 7.4–7.5 diagnostic fields; generalized physics tests | Injection and canyon accuracy criteria pass; original RHS fails regression; references unchanged; serial/OpenMP and sanitizer checks pass; report in `docs/stage0-validation.md`; CUDA execution and the separate registration-test mismatch remain disclosed |
    | A: Explicit vertical grids — locally complete | 5.2–5.5 constructor, guard, solver spacing checks, parameterization audit and rooftop bounds fix; commit e0fb62e9 | Layers through the bridge; `VerticalGrid.from_faces`; actual faces, metadata and nonuniform `to_dtcc()` rejection | Uniform parity is bitwise; explicit injection, canyon flux, occupancy, ownership, backend and sanitizer checks pass; report in `docs/stagea-validation.md` |
    | Study: sensitivity and cost — evaluated | Production solver unchanged; study-only fixed sweeps | Native worker, Python driver, raw data and `docs/vertical-grid-gate.md` | Passing explicit grids support further development; failed 0.25 m tower cases excluded as references; historical blanket stop superseded by this plan |
    | Focused solver diagnosis — locally complete | Production solver unchanged; independent operator/flux reconstruction and study-only double refinement | Reproducible serial/red-black residual locations and comparisons; report in `docs/vertical-grid-diagnosis.md` | Precision remedy candidate supported on the focused fixtures; top limitation and failed references retained; later opt-in validation is recorded in its own stage |
    | B1: Sampling and explicit preview — locally complete | — | `WindResult.sample` / `WindSample`, legacy/explicit `preview_grid` / `GridPreview`, coordinate and validity metadata; report in `docs/stageb1-validation.md` | Manufactured interpolation, exact-centre/solid-neighbour, bounds, archived study parity, coordinate and allocation checks pass; no automatic dataset options |
    | C1: Automatic prototype — locally complete | Production solver unchanged | `VerticalGrid.auto`, constrained generator, automatic preview/run and provenance; report in `docs/stagec1-validation.md` | Constraint, endpoint, effective-coordinate, occupancy and feasibility checks pass on both CPU backends; candidate policies remain provisional |
    | C2a: Early domain-height/finer-x/y controls — locally complete | Production solver unchanged | Actual Python-generated layers, both pedestrian planes, preserved lower faces, common physical points and archived fixed-location comparisons; report in `docs/stagec2-controls.md` | All 96 final CPU workers pass the solve gate; fixed critical locations fail horizontal sensitivity on both backends, so no preset is selected |
    | C2b: Horizontal-sensitivity assessment — locally complete | Production solver unchanged | Fixed-z refinement, initial/profile/corner diagnostics, larger lateral bounds and parameterization controls; report in `docs/stagec2b-horizontal-sensitivity.md` | Both backends identify initialization/averaging and lateral sensitivity; all eight new finer references fail residual control, so no supported preset scope is established |
    | Accepted-reference precision remedy — locally complete | Default QES float32 CPU paths unchanged | Separate bridge `PrecisionSolver`, `solver_precision`, from-zero CPU matrices, provenance and measured workspace/RSS/cost; report in `docs/precision-and-horizontal-verification.md` | All 32 float64 cases pass the full gate; all 16 declared tighter cases pass, with 25 tighter passes overall; restored references are explicitly float64 |
    | Lateral/horizontal verification — assessment locally complete | Production flags retained; accepted opt-in float64 references | Fixed points/critical locations, 2-to-1-to-0.5 m x/y at 80 m and 80-to-160-to-240 m extents at 1 m, both z families and winds | Report each axis using accepted solves, retain near-wall maxima and failed 80-to-160/coarse-grid comparisons; joint scope remains a separate prerequisite |
    | Joint extent/finer-x/y assessment — locally complete; full-region scope fails | Same production flags, precision and z operands | Combined 160/240 m extent and 1/0.5 m x/y controls; fixed points plus mandatory near-wall checks; configurable cell ceiling and reusable independent checkpoints; report in `docs/joint-grid-verification.md` | All 16 new CPU cases accepted; all 64 decisions agree across backends; fine-grid lateral checks pass, but 13/16 horizontal planes per backend fail added local checks; 29.49-million-cell cases retained with measured resources |
    | Near-wall scope/sampling review — next | Production physics and existing results retained | Review initialized/corner/final fields and the intended sampling observable; predeclare any alternate-sampler tests, selected finer references or narrower scope and their resource cost | A concrete bounded qualification protocol precedes new measurements; current failures remain recorded; the 4 m diagnostic region is not promoted to a preset |
    | C2c: Remaining automatic validation and preset selection — gated by joint-scope closure | Retain validated precision/provenance on supported CPU backends | Generated-grid refinement, centre alignment, shallow/roof sensitivity, policy and cost studies | Accepted references and lateral/horizontal verification establish scope; compare with cheapest qualifying uniform grid and select settings only from measured evidence |
    | B2: Dataset integration and release documentation | — | Section 7.6 options, cache identity, slice output, provenance, examples and documented presets | B1 and C2 complete; coordinates and validity survive dataset output; unsupported field conversions fail early; integration and packaging checks pass |
    | Deferred: Uniform resampling | — | Separate explicit interchange/display operation, if needed | Sampling, solid-mask, provenance and independent allocation contracts defined; not required for B2 |

    This table defines the execution order: diagnosis → B1 → C1 → C2 → B2.
    Do not turn the diagnostic milestone into an open-ended solver rewrite.
    A remaining numerical failure blocks reference comparisons or preset claims
    that rely on that configuration, not independent API correctness work.
    C2 may establish a narrower supported scope, but must state exclusions and
    cannot select a preset without accepted references for the claimed scope.

    Run the existing serial/OpenMP CI, sanitizer checks, symbol audits and
    wheel/sdist checks after each native change. Include this plan and the
    eventual benchmark report in documentation packaging as needed.

    Update `README.md` and `docs/validation.md` with the public API, coordinate
    semantics, sampling policy, the Stage 0 correction, residual diagnostics,
    numerical evidence and limits of physical validation. Provide one
    executable example comparing uniform and stretched grids on identical
    geometry, wind and domain bounds, with a preview of layer thickness versus
    height and a pedestrian-height comparison.

    Keep flat ground, constant-height extrusions, existing empirical flow
    parameterizations and uniform horizontal spacing as the scope of this
    feature. Cut cells, terrain-following layers, new turbulence/near-wall physics,
    gust prediction and local adaptive refinement require separate validation.

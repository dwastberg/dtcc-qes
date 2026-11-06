# Short experiments to choose wind model development priorities

Date: 2026-11-05. Status: lateral-join investigation complete; bounded experimental-option implementation plan added, execution not started. No tested variant passes all physical gates.

**Start with measured canyon flow and the existing wall-distance turbulence option. Then test roof forcing and wake diffusion separately.** These experiments choose where to invest effort. They do not build a combined model or change production defaults.

This combines [the literature tests](UPDATES_FROM_LIT_STUDY.md) and [the A/B findings](AB_VALIDATION_UPDATE_PLAN.md). It replaces their competing first-batch recommendations with the sequence below. The [governing experiment plan](QES_PHYSICS_MODEL_EXPERIMENTS.md), [development plan](docs/WIND_SIMULATION_IMPROVEMENT_PLAN.md) and existing campaign budgets still apply. SE1, canopy backgrounds, flag tuning and non-unit variational weights remain closed.

**Current outcome:** the lateral package imposes the original side-join reversal losses during initialization; parallel-street U is unchanged until projection. Removing the package recovers all 15 original lost rows and improves reversal recall to **98.99%**, but reduces canyon benefit from **50.56% to 40.96%** and still leaves other-region U **6.13% worse** than legacy. Preserve the useful lateral profile while addressing the join; wholesale removal is not recommended. No tested canyon arm passes every physical gate, and no refinement or promotion follows this investigation. E3v remains specified only. The [results](#experiment-results) and [current priorities](#current-development-priorities) retain all stopping decisions. Production defaults remain unchanged. No memory cap applies.

**Next work:** the [bounded implementation plan](#implementation-plan-bounded-validation-behind-an-experimental-option) defines a private default-off option, one join candidate and a conditional six-answer physical validation sequence. It has not been executed.

## First batch

Complete E0, E1 and T1, then review the results before implementing another mechanism. Cap this batch at **one engineering day, 12 primary solves and 12 numerical controls**. With the limits below, the maximum solver-worker allocation is 48 minutes; data preparation and implementation are charged separately. Stop at the effort limit and identify unfinished work.

| Test | Single question | Cases and comparison | Maximum new primary solves |
| --- | --- | --- | ---: |
| E0 | Can the comparisons be reproduced and scored fairly? | Stored A/B audit and EPA array eligibility | 0 |
| E1 | Does the published modified canyon improve measured array flow? | Two synthetic audit fixtures, then EPA array; legacy versus modified canyon | 6 |
| T1 | Does wall distance improve turbulence without changing mean wind? | A, B and D 0 degrees at 2 m; height versus wall distance | 6 |

E0's array inspection can stop E1 without blocking T1. T1 is scientifically independent of E1; timed workers still run sequentially.

## Common controls and decisions

- Freeze the legacy physical parent, data hashes, geometry, inflow, reference speed, probes, region masks, formulas and coefficients before each comparison. Every selectable candidate starts from that parent. Use private experiment switches, not a wider public flag range. A correctness repair must preserve the parent path; if it changes the parent, freeze and qualify a new baseline before comparing physics.
- Use four native threads, one BLAS thread and one worker at a time. Primary A/B and array answers: **60 s**; D city answers: **20 s**; E city answers: **60 s**. **User update on 2026-11-05: no memory limit applies to these experiments.** Record peak RSS where available, without rejecting a run on memory use. Enforce deadlines in the worker controller. Preserve overruns; do not retry, shrink domains or drop probes to obtain a pass.
- Start A/B at the existing 2 m settings and array geometry at at least eight cells across each cube. Keep the canonical sampler and measured inflow. Confirm a surviving isolated candidate at 1 m later; 0.5 m and full-city refinement are outside this screening batch.
- Prefer converged float64 on small fixtures. Each shortlisted fixed-work arm needs a tighter same-model control, at most one per configuration, capped at **180 s**, with no memory limit. Require maximum normalized probe-vector difference <=min(1e-4, 10% of the claimed normalized RMSE improvement). For turbulence, apply the same criterion to the primary k or stress output normalized by Uref squared. An unresolved numerical difference makes the result **inconclusive**.
- Preserve finite fields, probe coverage, solid impermeability and the existing same-operator interior, top-band and integrated-flux guards from the governing plans. Keep any inherited boundary defect visible. Save preprojection and final samples to detect improvements erased by projection.
- Unless a test specifies another criterion, **pursue** requires >=10% lower primary target RMSE, macro-averaged across configurations, with no configuration or measured region >5% worse. Report all eligible observations and overall errors as well as target strata. A local success establishes a local benefit. Use signed U/W and eligible vector errors; exclude Case B signed V/angle selection until independently resolved. Retain q as secondary; use numerical and paired measurement uncertainty rather than a fixed 0.03 q noise threshold.
- Call an adequately resolved failed hypothesis **stop**, a passed engineering screen **pursue**, and missing data or unresolved numerics **inconclusive**. Improvement must exceed numerical uncertainty; report paired spatial uncertainty and effect sizes without claiming statistical confirmation from two buildings. A/B are development cases; the EPA array is reproduction evidence for the canyon model. Neither replaces unseen confirmation or matching interacting-building references.
- Archive source and binary identities, uncached worker fingerprints and complete settings under `experiments/joint_screen/<test>/<attempt>/`. Give variants an experiment identity including their actual changes: `RunSpec` alone does not distinguish all turbulence settings. Never overwrite canonical validation records. Use the existing environment without an automatic dependency sync or rebuild.

## E0 Establish the targets and eligible references

**Work limit: 30 minutes for the stored audit, 60 minutes for array eligibility. No solves.**

Reproduce the stored A/B baseline scores, roof and wake-region errors, signed reverse-core errors, U=0.5/0.75 Uref crossing heights, shear-layer thickness and reattachment length. Verify stage samples reproduce final samples. Preserve the distinction between the 2 m stage records and 1 m headline results, and between their native identities. Do not select a parent using an eight-character policy prefix alone.

For the EPA BROWN2000 array, freeze geometry, units, component coordinates, normalization, inflow and eligible canyon/approach/recovery observations. Apply any similarity scaling to the complete setup. Components measured at different points remain separate profiles. Record hashes and missing metadata in one eligibility table.

**Decision:** an unresolved array convention closes E1 execution for this batch. A stored-record mismatch stops comparisons using that record. Existing eligible evidence may be reused without repeating its analysis.

## E1 Test canyon mixing first

**Change:** only legacy canyon versus the audited Singh modified canyon. **Budget: four audit solves plus two array solves. Implementation timebox: four hours after eligibility.**

Check the source equations and provenance against the cited model, lateral centering, support edges, fractional-power arguments and degenerate wedges. Check translation and rotation at formula level. Run one aligned and one oblique two-building fixture in both arms, using voxelization-aware tolerances for native fields. If qualification needs a general canyon redesign, stop implementation and record the unresolved scope.

Then run the measured EPA array once per arm. Primary metric: normalized signed profile RMSE over all eligible canyon measurements. Report interior, roof shear layer, lateral edge, approach and recovery separately, plus reverse-flow extent and projection changes.

**Decision:** pursue canyon development only if the common gate passes without losing measured reversal or approach/recovery accuracy. Smoother gradients alone do not pass. Next spend, if earned: the second measured wide-canyon geometry from the literature, two arms and two solves. Its absence leaves transfer unassessed.

## T1 Test mixing length without repairing stresses

**Change:** `mixing_length="height"` versus `"wall_distance"`; all cap, anisotropy, covariance and mean-wind settings remain fixed. **Budget: A/B and D 0 degrees, two arms each, six solves at 2 m.**

Require identical sampled mean-velocity vectors between the two arms, not just identical speed magnitudes. Primary metric: measured `k/Uref^2` RMSE, with k defined as half the stress trace. Freeze the baseline valid-probe IDs; losing any of them fails the coverage guard. Score these same IDs in both arms and report newly recovered probes separately. Report each configuration and region, R, bias, invalid covariance counts, internal TKE, cap fractions and recovered/lost coverage separately. Also show the labelled D scalar-speed proxy, but do not use it to select mean-flow physics.

**Decision:** pursue wall distance if k RMSE passes the common gate, spatial k correlation loses <=0.02 in each case, and covariance validity does not deteriorate. Fewer invalid cells alone is an implementation benefit. If it passes, confirm A/B at 1 m and expand only the turbulence evidence; Case E has no measured k.

## Second batch of mean flow tests

Open at most **two new mean-flow candidates**, E2 and E3, after reviewing the first batch. Each gets at most four primary solves and four bounded numerical controls. Timebox implementation to half a day per candidate; anything larger becomes a separately scoped development task.

Execution amendment for E2 only: its initial four answers exposed an inactive implementation caused by the isolation patch. Preserve those answers and allow exactly one implementation correction with four further matched answers, for **eight E2 primary answers total**. The intended physical model, constants, masks and gates are unchanged. No further automatic implementation repeat is added; this exception does not apply to a physical rejection or resource overrun.

### E2 Isolate roof forcing from wake geometry

**Change:** apply the existing rooftop vortex forcing only, keeping the legacy cavity/wake top, Fackrell length, cavity strength and diffusion unchanged. Compare against the legacy default on A and B at 2 m: **four solves**.

Audit the stale `u0_roof`/`v0_roof` initialization first and check the corrected reference lookup on a manufactured roof column. The default parent must retain parity. The existing `rooftop=2` sensitivity record is not this arm: it also changes wake height and length. Freeze the existing rooftop formula constants; do not simultaneously synchronize shell geometry in `PolygonWake.cpp`.

Primary metric: signed U/W profile RMSE above the roofs. Check wake-top crossings, pedestrian reverse flow, reattachment and projection separately. Require the common gate, no >0.05 H additional crossing-height error in A, and no >3% increase in absolute reattachment-length error relative to observations.

**Decision:** a pass prioritizes roof forcing. If the roof improves but B's elevated wake layer remains wrong, retain that as evidence for a separate support problem. It does not authorize adding a taller wake to this arm.

### E3 Test the published wake diffusion envelope

**Change:** only the Singh wake envelope, with the legacy cavity law, cavity-core initialization and roof forcing retained. Compare A and B at 2 m: **four solves**. These are declared development/transfer geometries, not the original Snyder/Lawson experiment.

Check the printed equations, limiting behavior and core continuity before native integration. Use the complete published transition prescription rather than inventing independent smoothing widths. Primary metric: downstream signed U/W profile RMSE. Separately report roof-transition thickness, lateral width, recovery and reverse-core errors.

**Decision:** require the common gate and no >5% reverse-core RMSE regression in either building. Wider or smoother sheltering without lower measured error stops this branch. If it passes, freeze the model before exposing one eligible third isolated dataset; budget one parent/candidate pair for that configuration.

## Cheap diagnoses before another model

Choose at most **two** of these checks at each review, according to the largest unresolved error or feasibility question. They open specific follow-ups without automatically creating more native candidates. Reuse stored arrays; cap each analysis at **30 minutes**, except external metadata inspections, which get **60 minutes**. Missing required fields make a check inconclusive; generating them needs a separately counted run. Offline stress comparisons retain the fixed baseline valid-probe IDs and report repaired coverage separately.

| Check | Isolated comparison | Decision and next focus |
| --- | --- | --- |
| Wake height | Compare the published Wilson/PRIME reattachment rule and spatial envelope against A/B roof reattachment and wake-top observations, with no solve. | If it cannot preserve A while explaining B, stop that prescription. A blanket H+0.22R wake top and an A/B-fitted trigger are excluded. A qualifying fixed prescription earns a separate support-only arm, not an addition to E2. |
| Cavity strength | Split stored signed U errors by geometry, wake versus horseshoe region, height and measured reverse core, before/after projection. | Opposing A/B errors close uniform amplitude reduction. Design a shape/height law only if a fixed independently supported formula is available; do not fit A's 14 core points. |
| Turbulent viscosity | Recompute stresses on the same stored final wind field with only nuT limited to `min(nuT, cPope*Lm*sqrt(internal_TKE_cap))`; retain all other stress operations. First reproduce the original stress calculation. | >=10% lower measured stress/trace-k error with the common non-regression guards supports a viscosity-limit follow-up. Reconcile internal TKE and stress-trace energy explicitly. Zero mixing length needs an explicit finite limit. |
| Covariance repair | Independently project the original raw tensor onto positive-semidefinite tensors with the same nonnegative trace; do not apply the viscosity arm first. | This keeps trace-k unchanged. Score measured stress components on common masks and report repair magnitude/new coverage separately. Validity alone does not establish better k. A large repair points to closure problems. |
| Background turbulence | Compare measured upstream component variances with existing upstream stresses; add a measured contribution offline only if a missing contribution can be independently defined without double counting. | Require >=10% lower measured turbulence error in D and one second eligible setup, preserved spatial pattern and no >5% scalar-proxy regression. Existing upstream overprediction argues against adding background energy. |
| Other diagnostic models | Match archived URock/QUIC E-after E and SSW inputs and receptors before comparing residuals. | >=10% lower MAE in both directions without >0.02 correlation loss supports a targeted implementation audit. Unmatched inputs cannot rank implementations; after-state data cannot test intervention accuracy. |
| Geometry and sampling | On common archived grid results, predeclare wall distance <4 m, 2 m-grid local K span >0.15, and changed passage connectivity as separate strata. Compute the bound from eliminating all error in their union. | A bound >10% of total MAE plus consistent improvement with refinement supports one oblique-wall/gap feasibility task. Near-wall log reconstruction needs a separately eligible measured wall profile and independent roughness. |
| Inflow | Compare the imposed measured E profile with the source measurements at every supplied height, including vector direction and normalization. | A discrepancy beyond interpolation/measurement uncertainty earns an adapter fix. Otherwise close atmospheric-inflow replacement for this tunnel case. |

Building non-local mixing stays queued until its native path and measured stresses are eligible. Tower/canopy redesign needs one reconstructable isolated/embedded measurement pair with at least three relevant heights; its first diagnostic is two parent solves. Corner-stream forcing stays behind the roof/wake tests because side-speed projection already contributes strongly and B's V sign is unresolved.

The negative-height high-rise case belongs in a separate correctness regression with a declared validity range and fallback. Keep high-rise off in these physics arms. Neither the regression nor clipping a negative height demonstrates improved physics.

## E4 Give one surviving mean flow candidate a city test

Choose at most **one** candidate using measured mechanism gains, numerical resolution, implementation effort and actual modified geometry. A candidate requiring further coefficient choices is not ready. If two independent mechanisms later warrant combination, declare a separate 2x2 test.

Use E and SSW, before and after construction, plus D 0 degrees at 2 m: **five configurations, two arms, ten solves**, with matched legacy parents on the same native build. Numerical controls remain separately bounded. This is a rejection screen on development directions.

Pursue the existing eleven-condition development screen only if intervention MAE improves >=10%, neither E-state speed MAE nor D vector RMSE worsens >5%, each E-state spatial correlation and each change-sign recall loses <=0.02, and all coverage/conservation/numerical guards pass. Keep the original clear-change definition, genuine decreases and covered frozen spurious-decrease IDs. Report subgroup denominators and buildings/regions actually modified; inadequate coverage is unassessed. An inactive module provides no transfer evidence.

Stop expansion on a resolved failure. A mechanism winner may remain useful for its measured geometry even when it fails Case E. This pilot does not authorize a full-35 campaign. Remaining array/independent-transfer, 1 m, application, runtime/memory and final accuracy gates must be specified before expansion, with candidate/revision spending charged to the governing ledger. Native release changes also require [requalification](docs/solver-control-requalification.md).

## Choose the next investment

After each batch, produce one comparison table: test, target error reduction, largest regional regression, numerical uncertainty, covariance/flux failures, active geometry, implementation hours, elapsed time/RSS and **pursue / stop / inconclusive**. Link one-page verdicts and a profile plot; retain all failed attempts.

| Evidence | Next investment |
| --- | --- |
| E1 wins on measured canyon profiles | Canyon geometry qualification and a second measured canyon |
| E2 wins on roofs | Roof forcing and a separately justified roof/wake support rule |
| E3 wins on recovery without damaging reversal | Published wake diffusion and unseen isolated confirmation |
| T1 or one offline stress arm wins | Turbulence accuracy as a separate output capability |
| Comparator or grid diagnosis identifies concentrated headroom | One targeted implementation or geometry feasibility task |
| All eligible mean-flow arms fail | Close this empirical screen; assess momentum feasibility before funding new trajectories |

Momentum feasibility initially means a domain/cell preflight for A/B and a review of existing convergence evidence, with **zero new histories**. Record memory needs without rejecting on memory use. The proposed roughly 1.5-hour trajectories and under-resolved 2 m slab roof do not fit this short screen. Any later experiment must declare its own finite history budget and physical/convergence gates; it does not resume or replenish E5a. Missing reference data or numerical failures leave the architectural choice inconclusive rather than establishing that empirical models have failed physically.

## Experiment results

| Experiment | Status | New primary solves | Numerical controls | Next decision |
| --- | --- | ---: | ---: | --- |
| E0 | Pursue with qualified array eligibility | 0 | 0 | Proceed to E1 implementation audit; T1 remains relevant |
| E1 | Restricted QES adaptation qualifies; complete array arm fails resolved guards | 10 | 2 | Keep public flag closed; roof-component results below redirect work to core/lateral changes |
| Canyon roof components | Both converged roof-only arms fail; conditional refinement omitted | 6 | 0 | Stop roof-only development in this screen; isolate core/lateral changes next |
| Core/lateral with legacy roof | Converged 45.77% target benefit; physical guards fail | 4 | 0 | Separate horizontal correction from W initialization; keep roof protection |
| Horizontal core/lateral, legacy W and roof | Converged 50.56% benefit; interior W improves; two physical gates fail | 4 | 0 | Audit lateral joining and parallel-street response; no refinement or promotion |
| Lateral-join investigation and ablation | All original side reversals recover; bulk accuracy trade-off; other-U still fails | 4 | 0 | Target the join while preserving useful lateral structure; do not remove the whole package |
| T1 | Stop automatic expansion; A correlation failure numerically resolved | 6 | 4 | Retain isolated turbulence benefit; proceed to independent E2 |
| E2 | Pursue isolated roof forcing; numerical controls pass | 8 | 4 | Select for small city rejection screen |
| E3 / E3v | Full historical horizontal prescription unresolved; vertical-only component specified and checked | 0 | 0 | Qualify E3v native edge trace before its isolated A/B pair |
| E4 | Stop city expansion; top-band failure numerically resolved | 10 | 2 | Retain isolated roof benefit; qualify canyon/wake mechanisms next |
| Wake-height diagnosis | Stop the unconditional geometry trigger | 0 | 0 | A's measured rooftop reattachment contradicts this trigger |

### E0 results on 2026 11 05

**Conclusion: the stored A/B evidence is reproducible, and the EPA data support a signed U/W profile experiment.** The [final audit](experiments/joint_screen/E0/attempt-002/report.json) passes all 30 identity, score, section-normalization and stage checks. Native binary SHA-256 is `28dce889…5eeef`; the full binary hash, policy and validation fingerprint are recorded in the audit. No native solves were used.

| Case | Resolution | Speed q | Speed MAE / Uref | Reverse-core U bias / Uref |
| --- | ---: | ---: | ---: | ---: |
| A | 1 m | 0.66129 | 0.124956 | -0.117227 |
| B | 1 m | 0.51339 | 0.186147 | +0.092480 |
| A | 2 m | 0.68280 | 0.113207 | -0.093088 |
| B | 2 m | 0.50446 | 0.181155 | +0.100501 |

Final 2 m stage vectors and sampling methods match canonical validation records exactly. The opposing A/B reverse-core biases persist at both resolutions, so uniform cavity weakening is already unsupported. Region biases, shear crossings, thickness and reattachment are in the audit JSON. The initial analysis in `E0/attempt-001` double-normalized the stored centre-plane velocities; its crossing results are invalid and preserved. Attempt 002 corrects this and checks centre-plane normalization against canonical probes before computing crossings. Neither attempt ran the solver.

The archive hash is `8855bfcb…c3033d`. Its original report resolves 150 mm cubes, 150 mm gaps, seven downwind rows, eleven crosswind columns, x downstream and z upward. Parsing preserves 191 U, 186 V and 521 W profiles and their individual coordinates. After excluding the labelled U calibration traverse and two conflicting traverse headers (`3dpwau.101`, `3dpwav.145`), the inventory retains 2,417 U, 2,377 V and 10,476 W observations. Repeats are retained; component arrays must not be joined by row number. Processed MATLAB tables use opaque objects, so the raw dimensional files are the reproducible source.

The [frozen eligibility and setup](experiments/joint_screen/E0/attempt-002/eligibility.json) includes every source hash, row ID, region, coordinate conversion and prospective grid: full 77-cube geometry scaled by 100, 15 m cubes, 1.875 m cells and 32 uniform vertical layers to 60 m. The primary canyon masks contain 816 U and 3,161 W rows; score components separately before macro-averaging. V remains inventory-only until its signed convention is independently established.

Use the measured upstream `3dpwau.006` profile at x=-225 mm, whose building-height Uref is **2.6214 m/s**. This differs from the paper's fitted logarithmic reference (2.82 m/s) and the upstream QES example (2.83 m/s); those settings cannot be substituted silently. The experiment tests the canyon change under matched measured forcing, rather than reproducing every published model input. Ground roughness is frozen from the paper, wall roughness from the upstream example; all lengths scale together. First-canyon, approach and recovery observations are present.

**Next:** E1 remains relevant, starting with source/formula qualification before any native build or solve. T1 remains relevant independently. Keep the cavity-amplitude idea closed; the existing opposing signed errors already answer its simplest version.

### E1 implementation audit on 2026 11 05

**Conclusion: stop the current generalized implementation before native execution; the measured canyon-physics hypothesis remains unassessed.** The [formula audit](experiments/joint_screen/E1/attempt-001/report.json) reproduces the active expressions and archives the inspected source. Two coefficient checks pass; seven geometry/limiting-case checks fail. No native solve, build, public flag change or model revision was spent.

For a 10 m square face with wind 30 degrees oblique to it, the projected face midpoint is -2.5 m. At three probes symmetric about that midpoint, the current core factors are **0.4984 / 0.7578 / 0.8793**; a centered support gives **0.9249 / 1.0000 / 0.9249**. The source leaves the canyon-center definition and lateral-support aggregation commented out. This is an oblique support defect, not failure of global translation or simultaneous geometry/wind rotation.

The unprotected fractional power also becomes nonfinite outside the core, and the wedge formulas have unresolved zero-width/zero-distance limits. Later overwrites can conceal a transient invalid power; these calculations do not claim that every final native field contains NaNs. The published wedges set W=0, but the native resets are commented out: the audit example writes -0.0375 times incident speed where the wedge requires zero. The [author manuscript](https://www.researchgate.net/publication/225596225) also retains the standard model for oblique flow, whereas the current generalized path lacks that qualification.

**Next:** T1 remains relevant and can run with the unchanged binary. Do not spend E1's six native answers on this unqualified arm. A future canyon implementation must explicitly choose the published aligned-flow restriction with legacy oblique behavior, or implement and qualify complete canyon supports. A clamp on the fractional-power argument alone is insufficient. E2 roof forcing and E3 wake diffusion remain independent hypotheses for the later review.

### T1 primary results on 2026 11 05

The [six-answer comparison](experiments/joint_screen/T1/attempt-002/report.json) uses fixed baseline masks on the unchanged binary. Every full wind field and every canonical wind vector is bitwise identical between mixing-length arms. Finite-field, solid, mass/flux, stage-parity and coverage guards pass. No baseline-valid k probe is lost; wall distance recovers 29 A probes and 16 B probes, reported outside the primary denominator.

| Case | Fixed measured probes | Height k RMSE | Wall-distance k RMSE | RMSE change | Spatial R change |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 145 | 0.231325 | 0.113891 | -50.77% | -0.02389 |
| B | 196 | 0.195719 | 0.098245 | -49.80% | +0.32117 |
| D | 33 | 0.023607 | 0.023607 | 0.00% | 0.00000 |

Errors use `k/Uref^2` with k from half the stress trace. Every A/B region improves in RMSE, but A's pooled R loss exceeds the frozen 0.02 allowance. The macro relative RMSE improvement is 33.52%; it cannot average away that failure. D's sampled stresses and scalar proxy are exactly unchanged even though mixing lengths change in 1,818,012 field cells: this pedestrian dataset does not test the changed elevated turbulence structure.

Invalid stress-cell counts fall from 2,032 to 821 in A, 4,575 to 3,027 in B, and 71,319 to 30,985 in D. The measured workers use four native threads, take 2.22–8.39 s inside the worker (including saved fields), and have no memory cap; actual resource values are retained in each worker record. The first sandboxed supervisor failed on `ps` before any worker event or solve (0.011 s). That infrastructure attempt is preserved; attempt 002 uses a deadline-only controller following the user's removal of memory limits. The interrupted escalation request launched no experiment.

**Next:** run one float64 same-model control for each A/B arm, four answers at most, each <=180 s. These controls resolve the numerical status of the large error reductions and the small A correlation failure. No D control is needed to establish that its two primary predictions are identical; no D improvement is claimed. The controls do not alter coefficients, masks or acceptance thresholds. E2/E3 remain relevant because T1 changes no mean wind.

**Numerical completion:** all [four tighter controls](experiments/joint_screen/T1/numerical-001/report.json) converge and pass the same-operator, coverage and field checks. Maximum probe-vector drift is 7.39e-6 Uref; maximum trace-k drift is 1.04e-5 Uref squared. A's tighter correlation loss is **0.02389089**, so the guard failure is numerically resolved. Keep the decision **stop automatic expansion under the frozen gate**; do not change the threshold to obtain a pass.

The [final verdict](experiments/joint_screen/T1/verdict.json) includes paired uncertainty from 2,000 resamples of XY profile/location clusters. The 95% intervals for relative k RMSE reduction are **29.97–75.68% (A)** and **20.56–74.30% (B)**; D remains exactly zero. This supports a real reduction in isolated-building energy error, while preserving the failed spatial-pattern criterion and the two-geometry scope. See the [fixed-mask comparison plot](experiments/joint_screen/T1/comparison.png).

**First-batch review:** six primary answers and four numerical controls have been used. Canyon physics remains unassessed because its implementation failed qualification. Wall distance has a useful isolated turbulence effect but does not pass the complete screen or address mean-flow errors. The next relevant experiment is **E2 roof forcing only**, from the frozen legacy parent, followed by E3 if it remains justified. Keep any native implementation in an isolated source/build/package so existing research binaries and production defaults remain intact.

### E2 initial implementation check on 2026 11 05

The [first matched four answers](experiments/joint_screen/E2/attempt-002/report.json) preserve the legacy whole fields and all guards, but the purported roof-only arm is also bitwise identical to legacy. **This is an inactive implementation, not a physical rejection.** The isolation patch skipped the `PolygonWake.cpp` block that sets `rooftop_flag`; `Rooftop.cpp` then fell back to the legacy log model. Its reported zero improvement cannot assess vortex forcing.

Correct the private patch to preserve upstream-neighbor/roof eligibility detection and skip only the height/length recalculation inside that block. Add an explicit rooftop-stage activity guard before interpreting scores. The bounded amendment above permits one corrected four-answer comparison, retaining all four inactive answers in the cost ledger. No coefficients, physical rule, observations or numerical thresholds change. A source-staging anchor error and a worker import error occurred before any native answer; both are preserved separately under E2.

### E2 corrected primary comparison on 2026 11 05

The [corrected matched comparison](experiments/joint_screen/E2/attempt-003/report.json) activates roof forcing in both cases. The [private patch](experiments/joint_screen/E2/build-003/roof-only.patch) preserves eligibility detection, reads the current face's incident velocity at every roof layer, and suppresses only the wake-height/length coupling. The isolated Release/OpenMP build passes the native symbol audit; its frozen sources, binary and package identities are archived. The repository's production source and installed native binary are unchanged.

| Case | Roof U/W RMSE legacy | Roof U/W RMSE candidate | Roof error reduction | Overall U/W error reduction | Largest regional regression |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 0.340189 | 0.118445 | 65.18% | 14.31% | Side: +2.31% |
| B | 0.579553 | 0.399342 | 31.09% | 8.20% | Side: +2.17% |

Every legacy full field matches the original T1 wind field exactly. Every sampled stage before rooftop forcing is identical between arms, establishing unchanged initialized cavity/wake behavior. Rooftop-stage activity, final coverage, finite fields, stage sampling, four-thread execution and mass/flux guards pass. A's crossing-height guard passes. At z=2 m, simulated reattachment moves 29.5346→29.6250 m in A and 67.0042→67.0531 m in B; the changes in absolute observation error remain below the frozen 3% allowance.

**Next:** E2 passes the primary engineering screen, with a macro roof error reduction of 48.14%. Run four same-model float64 controls, one per arm/configuration, before selection. E3 remains relevant: roof forcing reduces wake-region error by only about 2.6% in each case and does not itself supply an elevated, growing wake layer. Do not combine E2 with diffusion or wall-distance turbulence during these tests.

**Numerical completion and selection:** all [four E2 controls](experiments/joint_screen/E2/numerical-001/report.json) converge and pass the same-operator/coverage checks; maximum vector drift is **7.79e-6 Uref**. The [final verdict](experiments/joint_screen/E2/verdict.json) is **pursue for isolated roof forcing**. Paired roof-location resampling gives 95% relative error-reduction intervals of 56.67–74.48% in A and 23.89–37.14% in B, based on only four and three roof XY groups. Gains chiefly concern U; roof W RMSE rises 0.66% in A and 2.40% in B. Retain that distinction and the small development sample. See the [component and regional comparison](experiments/joint_screen/E2/comparison.png).

### E3 formula eligibility on 2026 11 05

**Conclusion: diffusion remains relevant, but the full published arm is inconclusive until its horizontal coordinate/joining convention is resolved.** The [formula audit](experiments/joint_screen/E3/eligibility-001/report.json) hashes the original PDF and its equation pages. The inverse form of the vertical coordinate in Eq. 8 was visually checked against the PDF, simplified algebraically, and passes finite, boundary-continuity, monotonicity and ambient-recovery limits.

For the horizontal formula, using the stated centerline coordinate in Eq. 6 and the stated wake-edge reference in Eq. 5 yields a boundary mismatch when the legacy core is retained. At x/H=1, a full-width edge y/W=0.5, Uref_edge=0.5 and ambient U=1, the outside formula gives **0.61060** at a core boundary of **0.5**. An outward distance measured from the wake edge would fix that limit, but it is a different origin convention that the present evidence does not independently settle. No offset, width or joining rule is chosen by looking at A/B gains. No native answer or new physical model was spent.

**Next:** E2 is the only mean-flow candidate that passes its isolated physical and numerical screen, so it is relevant to E4's small city rejection test. Keep E3 queued for an unambiguous coordinate/reference implementation. Do not interpret this prerequisite failure as evidence that wake diffusion is ineffective.

### E4 city primary results on 2026 11 05

**Conclusion: stop city expansion of roof forcing alone.** All [ten matched answers](experiments/joint_screen/E4/attempt-001/report.json) complete within their deadlines, with frozen source identities and original geometry/inflow. Intervention MAE changes **0.176681→0.176437**, an improvement of **0.138%**, versus the required 10%. D vector RMSE changes 0.295355→0.295336. Increase/decrease recall remains 0.67470/0.89655, on 83 measured increases and 29 decreases. The common paired sample contains 160 E pairs and 33 independent D vector probes; 18 of the original 89 spurious-decrease pairs are covered, with stratum MAE 0.529703→0.529410.

| Configuration | Buildings with vortex face writes | Adapted footprints | Maximum probe K change |
| --- | ---: | ---: | ---: |
| D 0 degrees | 13 | 83 | 0.001873 |
| E before E | 1 | 533 | 0.000382 |
| E before SSW | 0 | 533 | 0 |
| E after E | 3 | 536 | 0.009928 |
| E after SSW | 0 | 536 | 0 |

Both SSW fields are bitwise unchanged. These are inactive geometry configurations, not independent evidence of transfer. The isolated-build addition counts actual vortex-writing buildings/faces without changing the tested physical rule. Pre-rooftop canonical stages, final coverage, finite fields, solid impermeability, interior and integrated-flux guards pass in all five configurations. The E-after/E top-band maximum rises **0.037758→0.049284** (dimensionless), failing its parent-relative allowance. The parent's existing top-band defect is retained in the report.

**Next:** run only the E-after/E legacy/candidate numerical pair (two controls, each <=180 s) to resolve the top-band failure. No eleven-condition/full-35 expansion, retuning or model stacking follows. Roof forcing remains useful for its demonstrated isolated geometry, while interacting canyon/wake structure remains the relevant urban research question.

**Numerical completion:** both [E-after/E numerical controls](experiments/joint_screen/E4/numerical-001/report.json) converge and reproduce their own primary predictions within **6.93e-6 Uref** at the probes. The tighter top-band maxima remain **0.0377577→0.0492846**, so the candidate still fails the parent-relative guard. Interior, solid and integrated-flux comparisons pass. This is a resolved integration failure under the frozen city configuration; the inherited parent top-band defect also remains.

The [final city verdict](experiments/joint_screen/E4/verdict.json) retains **stop city expansion**. Two-direction/57-spatial-group paired resampling gives a descriptive 95% interval of **0–0.502%** intervention MAE reduction, far below the 10% screen target. With only two development directions, this interval is not transfer confirmation. See the [city benefit, activation and top-band plot](experiments/joint_screen/E4/comparison.png). No full-matrix, 1 m city or timing campaign follows this result.

### Wake height diagnosis on 2026 11 05

The [zero-solve geometry check](experiments/joint_screen/wake_height/attempt-001/report.json) rejects the proposed unconditional roof-reattachment trigger for these cases. For A, `0.9R=18.14 m` exceeds the 16 m roof, so the rule predicts non-reattachment and a maximum wake height of 1.1386 H. The observed roof reattaches at **8.32 m**, before the trailing edge. B gives `0.9R=28.8 m` on an 8 m roof and a maximum height of 1.22 H, but that agreement cannot repair the contradiction in A. Do not raise both wakes or fit an A/B-specific activation threshold. A separately supported support/reattachment law remains relevant.

## Authorized follow-up: canyon qualification and wake prescription

The user authorized this follow-up on 2026-11-05. Keep the original installed module and all completed attempts intact. No memory cap applies. Use a fresh isolated native build, four threads, one BLAS thread and sequential workers. Reserve E1's unused four synthetic answers and two array answers; at most two additional tighter array controls may follow a numerically unresolved result. Each primary worker has a 60 s deadline, each control 180 s. Do not tune against observations or combine mechanisms.

**Canyon scope frozen before native measurements:** qualify a private repair of the existing QES modified-canyon implementation for flat-ground, equal-height rectangular pairs with matching transverse spans and incident flow normal to their faces. Other geometries and oblique flow explicitly use the unchanged legacy algorithm. Check centered support, positive spacing, finite limits, zero W in wedges, and formula translation/rotation invariance. Retain the existing QES core profile and roof-reference convention; document these as adaptations rather than claiming exact reproduction of every Singh equation. The experimental question is whether this qualified QES adaptation merits further development. Native qualification uses an aligned pair and an oblique pair, each in both arms. Only an active aligned arm with finite fields, matching pre-canyon stages, unchanged oblique fields, preserved coverage and numerical/mass guards earns the array pair. If qualification fails, record the failure and do not spend the array answers.

**Wake prescription:** independently resolve what the primary sources establish and distinguish a boundary-continuous adaptation from a literal published-model reproduction. Freeze coordinates, reference values, degenerate limits and overlap handling before looking at any new measured score. If historical horizontal joining remains underdetermined, select the explicitly permitted vertical-only component experiment as the next physical test; do not silently invent a horizontal origin or corner rule.

### E1 qualification attempt 001

**Result: inactive implementation; no physical conclusion.** All four synthetic workers converged, preserved finite fields and sampling, and used four threads. Oblique fallback was bitwise identical to legacy, but so was the aligned candidate: zero qualified buildings and zero modified writes. The [report](experiments/joint_screen/E1/qualification-001/report.json) therefore stops the array. Inspection identified a preflight integration error: QES represents one closed polygon ring by **two** offsets (begin and end), while the new guard rejected more than one offset. The standalone geometry/kernel tests passed but did not exercise this native representation. The analysis also initially used a wrong stage label (`street_canyon` instead of `canyon`); correcting that label required no reruns. The original worker sources remain archived.

**Decision before more runs:** allow one bounded implementation correction and one additional four-answer qualification set (eight synthetic answers total), changing only the ring-offset guard. This addresses an inactive adapter, not a measured-score failure. No further implementation retry is included. The array pair is still conditional on active qualification and all original guards. Build 001's patch-anchor guard failure occurred before compilation or solves and remains archived; build 002 supplied the inactive four-answer set.

### E1 qualification attempt 002

**Result: the restricted QES adaptation qualifies for its measured array screen.** All checks in the [native report](experiments/joint_screen/E1/qualification-002/report.json) pass. The aligned candidate qualifies one upstream building, falls back for the last building, and records 3,600 W-face writes (including repeated traversal writes). It changes the intended canyon stage, gives exactly zero sampled W inside the top wedge, preserves pre-canyon samples, coverage and solid impermeability, and passes interior/top/flux guards. All four workers converge in float64 at tolerance 1e-12. The oblique candidate writes no modified canyon values and reproduces the complete legacy field bitwise.

The implementation centers its face support, uses the qualified physical pair spacing, avoids evaluating fractional powers outside the core, uses exact wedge support without the old one-cell buffers, and applies the published zero-W wedge requirement. Shared native helper checks cover rigid translation/rotation, malformed and oblique geometry, symmetry, joins and degenerate limits. This qualifies the deliberately restricted QES adaptation, with its retained QES core and roof-reference convention; the public flag remains closed. General oblique canyon modeling and exact Singh reproduction remain separate work.

**Next:** the frozen full-array U/W comparison is relevant and now earns its two answers. Use the existing E0 eligibility without changing masks or inflow. Its four horizontal bounds expand explicitly to `(xmin,ymin,0,xmax,ymax,60)` for the six-coordinate native API; this only supplies the already frozen vertical extent. Preserve all repeated eligible observations. No other mechanism joins this arm.

### E1 full-array primary comparison

**Result: large target improvement, with guard failures requiring numerical qualification before a final decision.** The [primary report](experiments/joint_screen/E1/array-001/report.json) retains all 816 canyon U and 3,161 canyon W observations and all other eligible rows. Normalized canyon RMSE falls from 0.29768 to 0.11482 for U (**61.43%**) and 0.17279 to 0.08911 for W (**48.43%**), a **54.93%** macro reduction. A descriptive paired profile bootstrap gives 50.31–58.95% reduction, conditional on the frozen grid/profiles. The candidate qualifies 66 buildings and uses legacy fallback for the 11 last-row cubes. Finite fields, coverage, pre-canyon parity, stage parity and all mass guards pass.

The complete arm fails the frozen region and reversal guards: interior W RMSE rises **10.86%**, U in the residual `other` stratum rises **12.63%**, and measured-negative canyon U recall falls from **100% to 94.71%** (397 retained reverse observations). Reverse-subset U RMSE nevertheless improves 56.42%; reducing error and preserving reversal are distinct checks. Approach U/W improve and recovery changes are within 5%.

Both fixed-work float32 answers reached their 2,000-iteration cap without meeting tolerance. **Next:** run the reserved legacy/candidate float64 controls (at most 16,000 iterations, tolerance 1e-12, 180 s each). They must establish whether these benefits and guard failures survive numerical convergence; no coefficient, geometry or mask changes are allowed. E3v prescription work remains independently relevant.

### E1 resolved array result

**Conclusion: stop the complete adaptation under the frozen selection rules; pursue component isolation.** Both float64 controls converge, at 2,875 and 2,863 iterations. Maximum primary/control probe-vector differences are **4.18e-6 and 3.63e-6 Uref**, comfortably below 1e-4; same-model mass and coverage comparisons pass. The [final verdict and answer ledger](experiments/joint_screen/E1/qualification-verdict.json) and [converged report](experiments/joint_screen/E1/array-numerical-001/report.json) confirm that the **54.93% canyon benefit and all three guard failures persist**. The numerical pair resolves the result; it does not earn promotion of a candidate that fails physical guards.

| Converged metric | Legacy | Restricted QES canyon | Change |
| --- | ---: | ---: | ---: |
| Canyon U RMSE / Uref | 0.29768 | 0.11482 | -61.43% |
| Canyon W RMSE / Uref | 0.17279 | 0.08911 | -48.43% |
| Interior W RMSE / Uref | 0.10417 | 0.11548 | +10.86%, fails |
| Other-region U RMSE / Uref | 0.11572 | 0.13034 | +12.63%, fails |
| Measured-negative canyon U recall | 100% | 94.71% | -5.29 percentage points, fails |

The [regional comparison figure](experiments/joint_screen/E1/qualification-comparison.png) makes the distinction clear: roof-shear U and W improve **55.05% and 77.26%**, while interior W worsens. The final projected field retains the benefit; it is not just smoother initialization. Across all eligible observations, U RMSE improves 42.26% and W 40.34%. These are matched measured-inflow results on the frozen full array, not exact reproduction of the paper's complete model/setup or unseen transfer evidence.

**Next canyon experiment remains relevant, with a narrower question:** compare a vertical roof-mixing wedge alone against the unchanged legacy canyon, retaining its core amplitude, lateral model and geometry. This separates the strongest regional benefit from the changes associated with interior/reversal loss. Start with formula/native fixture qualification, then at most one frozen array pair and its numerical pair. Do not retune gamma or p, combine roof forcing, or open the public flag. The present coupled arm does not identify which term caused each regression; the proposed ablation must establish that.

### E3v prescription resolution

**Conclusion: select the verified vertical component for the next isolated wake test; retain uncertainty about the complete historical horizontal model.** The [prescription report](experiments/joint_screen/E3/prescription-003/report.json), [machine-readable specification](experiments/joint_screen/E3/prescription-003/specification.json) and [executable formula prototype](experiments/joint_screen/wake_prescription.py) fix the implementation contract before new wake measurements. All **14 formula/limit checks pass**. No E3v native answer has been run, and no wake-accuracy benefit is claimed. The final scope explicitly retains geometrically tall Case B under its unchanged standard-wake parent (`highRiseFlag=0`); the specialized high-rise algorithm is excluded. Earlier immutable prescription drafts remain archived.

For downstream distance x from the trailing wall, unchanged building/wake height H, local outer-wake height h, and target height z>h:

`xi = sqrt((z-h)/h) * sqrt(H/x)`

`weight = exp(-xi^1.5)`

`U(z) = (1-weight)*Uambient(z) + weight*Ulegacy_edge(x,y,h)`

This is the verified vertical law in [Singh et al. 2006, Eqs. 7–8](https://ams.confex.com/ams/pdfpapers/104607.pdf). Evaluate its removable singularity by simplifying the algebra; use log-space evaluation for extreme ratios. The ambient velocity belongs to the **target height**, and the edge velocity is the **one-sided interior trace at the outer legacy wake boundary**. Sampling an already ambient outside voxel would make the candidate inactive. For the supported isolated normal rectangle, the outer boundary follows the unchanged legacy `x=3*dn` support, rather than the recirculation-core boundary. The specification supplies its analytic height and edge attenuation using the actual native cavity length and wake factor.

Apply only above that boundary, preserving core initialization, transverse wind, W, other parameterizations and projection. Exclude the specialized high-rise algorithm, oblique flow, terrain and interacting geometry from E3v; geometrically tall B remains eligible under its standard-wake parent. There is no horizontal tail or two-tail overlap rule. This is a component test, not reproduction of the complete 2006 model.

The historical horizontal ambiguity cannot be resolved by continuity alone. With edge y/W=0.5, edge velocity 0.5 and ambient 1, both a shifted Gaussian and a boundary-normalized centerline Gaussian match the edge, yet at y/W=1 they give **0.61060 and 0.76382**. Both are parameter-free, continuous adaptations; choosing either as the published implementation would be unsupported. No A/B score was used to choose a join.

One additional limit matters: the printed vertical exponent is proportional to `(z-h)^0.75`, so the join is **continuous but generally has an unbounded one-sided velocity gradient**. Preserve that distinction; changing the exponent to make it differentiable would create another hypothesis. Native face sampling and subsequent grid checks must quantify the implication.

**Next:** qualify E3v's native edge trace, unchanged preprojection core and active exterior forcing; then its preregistered four A/B answers remain relevant to the elevated wake-layer deficit. Keep the full horizontal+vertical reproduction deferred until a primary reference establishes its joining and corner conventions. Do not combine E3v with the canyon adaptation, roof-only forcing or wall-distance turbulence.

## Canyon component experiments authorized on 2026-11-05

The user requested the minimal experiments needed to decide how to proceed with canyon roof mixing. Keep the full-array geometry, measured profile, observations and regional/reversal/mass gates frozen. No memory limit applies. Four native threads, one BLAS thread and sequential workers remain required. Production sources and the installed module remain untouched.

**First arm: vertical roof wedge only.** Run the complete legacy canyon pass first, then overwrite only faces inside the existing qualified vertical wedge (`0 < roof_distance <= 0.2*x`, with the roof boundary included). Retain the legacy core everywhere else, legacy lateral flow, cavity/wake geometry, roof forcing and projection. Use the already frozen QES wedge reference and coefficients, including gamma=0.3; do not fit any value to observations. W is zero only inside this wedge. This tests the roof component of the prior adaptation, not a new amplitude or support law.

**Implementation gate:** reuse the archived legacy synthetic fixtures and run an aligned and an oblique candidate. Require activity, finite fields, convergence, coverage/stage parity, unchanged pre-canyon stages, bitwise unchanged deep-core samples before projection, zero top-wedge W and the existing mass guards. Oblique flow must reproduce the archived complete legacy field bitwise. A fresh array legacy answer must also reproduce the archived converged legacy array bitwise before a candidate is scored.

**Minimal physical comparison:** use converged float64 directly (tolerance 1e-12, 16,000-iteration maximum) for the fresh array parent and candidate; 60 s per worker. This avoids repeating the already resolved float32/control comparison. Retain all 816 U and 3,161 W canyon observations plus all other eligible rows, and the 10% macro / 5% regional / 5% reverse-RMSE / 2-percentage-point reversal-recall guards. Report roof and interior changes, initialization versus projection, and paired profile uncertainty.

**One conditional second arm:** if the first arm fails physical guards, keep its U/V roof-wedge forcing identical and preserve legacy W everywhere during initialization. This narrower component comparison isolates the zero-W wedge contribution; it is not presented as the published complete wedge. It earns one aligned qualification answer and one array answer only if the first arm shows a material target benefit or exposes a W/reversal regression. Reuse the verified parent; no further variant, lateral-width tuning or coefficient search is included.

**If an arm passes:** run one parent/candidate array pair at half cell size (0.9375 m, 16 cells per cube side), preserving the complete domain, profile and observations. These two refinement workers have 180 s deadlines and no memory cap; use float64 tolerance 1e-12 and a 32,000-iteration maximum. Require convergence, common guards and the same direction of physical benefit. A timeout or unresolved refinement prevents recommending expansion. Stop after the first surviving arm is checked rather than comparing more variants.

**Budget:** at most eight new native answers: two first-arm qualification answers, two coarse array answers, at most one second-arm qualification and array answer, and two conditional refinement answers. Preserve every attempt. After each stage, record the results here and decide whether the next stage is still relevant. E3v, isolated rooftop forcing and turbulence changes are outside this request.

### Roof-component implementation qualification

**Result: the roof-only overlay qualifies for the array pair.** Both converged synthetic answers pass every check in the [qualification report](experiments/joint_screen/canyon_mixing/qualification-v1/report.json). The aligned candidate changes only the intended roof component, leaves deep-core samples bitwise unchanged before projection, gives zero W inside the top wedge, and passes finite-field, sampling, stage, solid, interior, top and flux checks. It records 440 U, 440 V and 200 W assignments, including repeated traversal writes. The oblique candidate records zero overlay writes and reproduces the archived full legacy field bitwise. No new legacy fixture solves were needed.

The [isolated build](experiments/joint_screen/canyon_mixing/build-002/manifest.json) runs the original legacy canyon routine across all buildings before applying the roof overlay. The overlay contains no interior/lateral assignment or cell-flag assignment. It shares the qualified rectangular support and finite wedge helper. Build 001 stopped before compilation/solves because its audit mistook an equality comparison for an assignment; that attempt is preserved. No production source or installed-module change was made.

**Next:** run the fresh converged array parent, require full-field parity with the archived converged parent, then run the roof-component candidate. The second arm and refinement remain conditional; qualification alone does not establish measured improvement.

### First component: roof wedge U/V plus zero W

**Conclusion: stop this arm at the coarse physical gate.** The [array report](experiments/joint_screen/canyon_mixing/array-v1/report.json) finds only **3.51%** macro canyon improvement and **6.09%** macro roof-shear improvement, below the 10% target. Canyon U worsens **3.51%**, while canyon W improves **10.54%**. Interior W worsens **9.21%** and reverse-canyon U RMSE worsens **7.94%**, failing their 5% guards. Reverse-flow recall remains 100%; here its signed error, rather than lost reversal, fails. Roof-shear U worsens 3.38%, while roof-shear W improves 15.56%.

The fresh converged [parent parity audit](experiments/joint_screen/canyon_mixing/array-v1/legacy-parity.json) matches the archived whole field, geometry and coverage bitwise. Both answers converge in float64; all finite, sampling, stage and mass guards pass. All 1,326 deep-core observations are bitwise unchanged at the canyon initialization stage. Projection changes that initially untouched core and reverses the small initialization-stage U benefit into a final U regression. The descriptive paired-profile interval for macro canyon change is -6.40% to -0.85%; it does not meet the target.

**Decision:** the earlier 54.93% improvement of the coupled arm cannot be attributed to the vertical roof wedge alone. Do not refine or recommend this arm. The one narrower W-preserving arm remains relevant because the first arm exposes both an interior-W regression and a reverse-U regression: keep exactly the same U/V wedge forcing and preserve legacy W. Qualify it on the aligned fixture, then use one array answer with the already verified parent. No coefficients, support widths, masks or acceptance gates change.

### W-preserving component qualification

**Result: qualifies for its one array answer.** The [aligned fixture](experiments/joint_screen/canyon_mixing/qualification-v2/report.json) converges and passes finite-field, coverage, stage, deep-core and all mass guards. It records 440 U and 440 V roof assignments and **zero W assignments**. Every sampled canyon-stage W value is bitwise identical to legacy. The oblique guard and dispatch are shared with the first arm, so an additional oblique solve would repeat an unchanged path and is omitted. The array comparison remains relevant to separating the zero-W rule from horizontal roof forcing.

### Second component: roof U/V with legacy W preserved

**Conclusion: stop this narrower arm and close the roof-only branch for this screen.** The [array report](experiments/joint_screen/canyon_mixing/array-v2/report.json) finds **1.36% worse** macro canyon error and only **0.25%** macro roof-shear improvement. Canyon U worsens **6.39%**, roof-shear U worsens **7.44%**, interior W worsens **13.55%**, and reverse-canyon U RMSE worsens **10.79%**. Canyon W improves only 3.67%. Its descriptive macro-change interval spans -1.71% to +4.40%; there is no adequate target benefit. Reverse-flow recall remains 100%.

The candidate converges and passes all numerical, finite, sampling, deep-core and mass checks. It preserves all sampled canyon-stage W bitwise and records zero W assignments. The worse final interior W therefore arises after horizontal initialization and mass projection, despite preserving W initially. Simply removing the zero-W rule does not cure the regressions and reduces the small benefit seen in the first arm.

**Decision:** neither arm earns finer-grid answers, city expansion or production adoption. Stop after six new native answers rather than spend the two conditional refinement answers. The earlier coupled arm's large benefit depends on the remaining core/lateral/geometry changes or their interaction; roof-region improvement was not evidence that the vertical roof wedge caused it. Reassess the canyon development priority around a separate core/lateral ablation. No core amplitude, lateral-width or coefficient experiment has been run in this follow-up, so it does not select among those remaining terms or establish a deployable replacement.

### Final roof-component comparison and direction

The [isolation audit and answer ledger](experiments/joint_screen/canyon_mixing/verdict.json) passes. Both new arms have **bitwise identical sampled U/V initialization**, including the stage immediately before projection. The narrower arm's sampled W is bitwise identical to legacy at both stages. Its final W regression therefore cannot be blamed on a hidden change to W initialization. All 12,893 eligible U/W rows, the same input geometry/profile, the same parent and the same scoring masks are retained. All six new answers converge at tolerance 1e-12 and pass the applicable numerical/implementation checks.

| Converged change from matched legacy | Earlier coupled arm | Roof U/V + zero W | Roof U/V, legacy W |
| --- | ---: | ---: | ---: |
| Macro canyon RMSE | -54.93% | -3.51% | +1.36% |
| Canyon U RMSE | -61.43% | +3.51% | +6.39% |
| Canyon W RMSE | -48.43% | -10.54% | -3.67% |
| Macro roof-shear RMSE | -66.15% | -6.09% | -0.25% |
| Interior W RMSE | +10.86% | +9.21% | +13.55% |
| Reverse-canyon U RMSE | -56.42% | +7.94% | +10.79% |
| Passes complete physical screen | No | No | No |

The [exported comparison](experiments/joint_screen/canyon_mixing/comparison.png) shows the component and region changes. Its W `reverse canyon` diagnostic is the negative-measured-W subset, not a spatially joined U-reversal mask; only the U subset defines reversal selection.

**Recommendation now:** deprioritize standalone roof-wedge work, do not remove the zero-W rule as a proposed cure, and do not promote the coupled arm. The next minimal canyon experiment would retain legacy roof-wedge initialization and apply only the already qualified core/lateral changes outside that vertical wedge, with all coefficients fixed. This complement would test whether the large coupled benefit survives without changing roof initialization. It needs its own support/unchanged-roof qualification before a single matched array pair, and conditional refinement only if it passes. It has not been implemented or scored here. If it retains the benefit, separate its core-amplitude and lateral-taper terms afterward; do not infer either one's value from the present roof ablations.

This conclusion is conditional on the frozen 1.875 m EPA grid and measured forcing. The finite, converged failures close these two QES component arms under this short screen; they do not establish that every possible roof-mixing law fails. No refinement or unseen transfer result is claimed. The two unearned refinement answers remain unused.

## Core/lateral complement authorized on 2026-11-05

The user explicitly requested the core/lateral-only experiment with legacy roof initialization. Apply the previously qualified modified core and lateral formulas **only outside** the vertical roof wedge, after a complete unchanged legacy canyon pass. Preserve legacy U, V and W inside the vertical wedge, including its boundary. Keep gamma=0.3, p=0.25, the qualified physical canyon spacing and lateral wedge definition fixed; no width or coefficient tuning. The arm still contains these core/lateral/spacing changes together and does not isolate their individual contributions. Oblique or unsupported geometry retains legacy behavior. No production source or installed-module change is included.

**Isolation qualification:** use one aligned and one oblique candidate, reusing the hashed legacy fixtures. Require activity, finite/converged fields, unchanged pre-canyon stages, coverage/stage parity and the existing mass guards. Audit the actual staggered face fields before and after the overlay: changed faces must not enter the protected vertical roof support. Record skipped roof assignments and unique changed-face counts. This face audit is necessary because interpolated roof probes can include adjacent non-roof cells and need not remain bitwise identical even when roof faces are preserved. Oblique complete fields must match the archived parent bitwise.

**Array comparison:** after qualification, run one fresh legacy and one candidate on the frozen 1.875 m full EPA grid, directly in converged float64 (tolerance 1e-12; 16,000 iterations maximum; 60 s worker deadline). Require fresh-parent full-field parity with the archived converged legacy result. Retain every eligible observation, the equal-component macro canyon RMSE target, 10% improvement requirement, 5% regional/reverse-U RMSE limits, 2-percentage-point reversal-recall limit and existing mass/coverage guards. Record initialization and projection separately, including final roof-region errors despite protected roof initialization.

**Conditional refinement:** only if all coarse gates pass, run one matched parent/candidate pair at 0.9375 m with the same complete geometry, physical domain, profile and observations. Use float64 tolerance 1e-12, at most 32,000 iterations, 180 s per worker. Require convergence, common physical guards and a retained benefit. No memory cap applies; record RSS. Four native threads, one BLAS thread and sequential workers remain required.

**Budget:** at most six new answers (two qualification, two coarse array, two conditional refinement). No second candidate or coefficient search is included. Preserve all attempts and update this document after each stage before deciding whether the next is relevant. Failure of a physical gate closes refinement without rejecting the scientific value of a large local benefit.

### Core/lateral implementation qualification

**Result: qualifies for the frozen array pair.** Both converged synthetic answers pass the [qualification report](experiments/joint_screen/canyon_core/qualification-001/report.json). The aligned overlay changes 2,630 unique staggered component-faces, skips 1,080 roof assignments (including traversal repeats), and changes **zero protected roof faces** in the independent whole-field audit. A probe whose stencil lies inside the roof wedge also remains bitwise identical to legacy at the canyon stage. Finite fields, pre-canyon parity, coverage, stage parity, solid, interior, top and integrated-flux guards pass. The oblique answer writes no overlay and matches the complete archived legacy field bitwise.

The [isolated build](experiments/joint_screen/canyon_core/build-001/manifest.json) retains the qualified core/lateral expressions and only excludes the vertical-wedge component blocks. It runs after the complete legacy canyon pass. Native-symbol checks pass; no production source or installed module was modified. **Next:** run the fresh converged array parent, verify archived full-field parity, then run the complement. Refinement remains conditional on every physical gate.

### Core/lateral-only array result

**Conclusion: large benefit retained with legacy roof initialization, but the arm fails physical guards.** The [converged array report](experiments/joint_screen/canyon_core/array-001/report.json) gives **45.77% lower macro canyon U/W RMSE**: U improves **55.33%** and W **36.21%**. The final roof-shear U/W macro error improves **51.02%**, despite preserving the roof initialization. Its paired descriptive profile interval for macro canyon change is -51.19% to -39.86%, conditional on the frozen grid/profiles.

The native audit covers 66 qualified canyon supports, finds 88,176 unique changed component-faces, skips 35,904 roof assignments (including repeated traversals), and detects **zero protected roof changes**. The [fresh-parent audit](experiments/joint_screen/canyon_core/array-001/legacy-parity.json) matches the archived converged legacy whole field, geometry and coverage bitwise. Both answers converge at tolerance 1e-12 (2,875 legacy and 2,864 candidate iterations); all finite, sampling, stage, mass and protected-roof checks pass. Every eligible observation remains included.

Three physical failures remain: **interior W RMSE +17.62%**, **other-region U RMSE +9.42%**, and reverse-flow U recall **100% to 93.45%**, a 6.55-percentage-point loss against the allowed 2 points. Reverse-subset U RMSE improves **55.89%**; preserving its sign/extent and reducing its error remain distinct requirements. Approach U/W improve and recovery changes remain within 5%.

**Decision:** close refinement, city expansion and promotion of this arm. Stop after four new native answers, leaving both conditional refinement answers unused. This test demonstrates that much of the coupled arm's benefit survives without modifying roof initialization, but does not isolate core amplitude, lateral taper or spacing from one another. Nor does it prove that direct W changes caused the final W regression: the fixed mass projection couples the components. Any next canyon comparison should separate the horizontal core/lateral correction from W initialization, keeping the protected roof and fixed coefficients; that next arm has not been run here. No retuning or second candidate is added to this request.

### Core/lateral final audit and direction

The [final verdict and four-answer ledger](experiments/joint_screen/canyon_core/verdict.json) verifies the archived source epochs, matched geometry/profile/IDs, qualified helper hashes, complete converged answers, native roof protection and unchanged installed binary/policy/fingerprint. The [comparison figure](experiments/joint_screen/canyon_core/comparison.png) places this arm beside the coupled and roof-only results.

| Converged change from matched legacy | Coupled arm | Roof wedge only | Core/lateral, legacy roof |
| --- | ---: | ---: | ---: |
| Macro canyon U/W RMSE | -54.93% | -3.51% | -45.77% |
| Canyon U RMSE | -61.43% | +3.51% | -55.33% |
| Canyon W RMSE | -48.43% | -10.54% | -36.21% |
| Macro roof-shear U/W RMSE | -66.15% | -6.09% | -51.02% |
| Interior W RMSE | +10.86% | +9.21% | +17.62% |
| Other-region U RMSE | +12.63% | +1.36% | +9.42% |
| Reverse-canyon U recall | 94.71% | 100% | 93.45% |

The interior-W regression emerges during projection: normalized RMSE immediately before projection improves from **0.12878 to 0.11311** (-12.17%), but afterward worsens from **0.10417 to 0.12253** (+17.62%). This identifies a component-coupling problem in the completed field; it does not establish which individual initialization term should change. The apparent final roof-region benefit is compatible with protected roof initialization, since non-roof forcing and mass projection affect that region. Canonical interpolated roof samples can also include adjacent non-roof cells; the direct face audit is the isolation check.

Verification adds a meaningful positive control for that audit: a compiled test of the exact native audit detects injected U, V and W roof-face changes, detects a signed-zero bit change, and permits a legal deep-core change. **33 targeted tests pass.** No extra physical answers are needed for that audit test.

**Next experiment, if pursued:** horizontal core/lateral correction outside the protected roof wedge, with legacy W initialization everywhere and all current coefficients fixed. It should first prove W/roof preservation before scoring the same array. This would distinguish the effect of changing W from the response to horizontal forcing under projection. If it retains the benefit and passes guards, refine; otherwise reassess consistent vortex initialization before tuning gamma or lateral widths. This follow-up is a concrete next question, not a selected model or a run completed in this request.

## Horizontal core/lateral test authorized on 2026-11-05

The user requested horizontal core/lateral forcing with legacy W and roof initialization. Keep the last complement's U/V expressions, coefficients, support and spacing unchanged outside the protected vertical roof wedge; remove its entire W overlay. Run the complete legacy canyon pass first. This isolates W initialization from the horizontal correction without selecting a new amplitude or width. Unsupported and oblique geometry retains legacy behavior.

**Before scoring:** qualify aligned and oblique candidates against the archived legacy fixtures. Require active horizontal forcing, finite/converged fields, unchanged pre-canyon stages, sampling/stage parity, the existing mass guards and direct native roof-face preservation. Add a whole-field bitwise W audit across the overlay and save the complete W face array immediately before projection. Require that final initial-W array to match the fresh legacy parent bitwise. Compare sampled U/V initialization to the preceding complement to verify the horizontal forcing is unchanged. Interpolated roof samples alone are not the roof isolation proof.

**Physical screen:** one fresh legacy/candidate pair on the frozen full EPA grid at 1.875 m, converged float64 tolerance 1e-12 and at most 16,000 iterations. Require fresh-parent whole-field parity with the archived converged legacy answer, all eligible observations and the unchanged 10% target / 5% region and reverse-U RMSE / 2-percentage-point reversal-recall gates. Retain mass and coverage checks, paired profile uncertainty and before/after-projection diagnostics.

**Budget and scope:** four new answers at most (two qualification and two array), four native threads, one BLAS thread, sequential workers, 60 s each. No memory cap applies; record RSS. No refinement, promotion, city run, coefficient search or second candidate is included in this request. Preserve every attempt and record each stage here before continuing. The preceding arm remains closed.

### Horizontal-only implementation qualification

**Result: qualifies for the frozen array pair.** Both converged synthetic answers pass every check in the [qualification report](experiments/joint_screen/canyon_horizontal/qualification-001/report.json). The aligned arm records 1,780 unique changed horizontal component-faces, zero W assignments, zero W bit changes across the complete overlay field, and zero protected roof-face changes. Its sampled U/V initialization is bitwise identical to the preceding core/lateral complement. Finite fields, pre-canyon parity, canonical sampling/stage parity and all mass guards pass. The oblique answer records no overlay and reproduces the complete archived legacy field bitwise.

The [isolated build](experiments/joint_screen/canyon_horizontal/build-001/manifest.json) removes only the preceding arm's W component block, retains its U/V formulas, and captures the full native W face array after initialization and before projection. A complete fresh-parent W-array comparison remains required in the array pair. **Next:** run the fresh converged parent, verify archived full-field parity, then score this single candidate. No refinement or promotion follows in this request.

### Horizontal core/lateral array result

**Conclusion: preserving W resolves the interior-W regression and retains a large target benefit, but two physical gates still fail.** The [converged report](experiments/joint_screen/canyon_horizontal/array-001/report.json) gives **50.56% lower macro canyon U/W RMSE**: U improves **60.18%** and W **40.93%**. Interior U improves **80.19%**, interior W improves **21.73%**, and reverse-canyon U RMSE improves **77.48%**. Roof-shear macro error improves **47.27%**. The paired descriptive profile interval for macro canyon change is -55.46% to -45.26%, conditional on the frozen grid/profiles.

The fresh legacy whole field, geometry and coverage match the archived parent bitwise. The candidate's **1,646,994 native W faces immediately before projection match the fresh parent's W array bitwise**, including signed zeros. Global overlay W changes and protected roof-face changes are both zero. The sampled U/V values at the canyon stage and immediately before projection match the preceding core/lateral complement bitwise. Native cell flags are also identical to that complement. These checks isolate removal of its W correction while retaining horizontal forcing and the protected roof.

Both answers converge at tolerance 1e-12 (2,875 legacy, 2,863 candidate iterations); finite-field, mass, stage, coverage and isolation checks pass. The remaining failures are **other-region U RMSE +8.92%** and reverse-canyon U recall **100% to 96.22%**, a 3.78-percentage-point loss against the allowed 2. Retain these failures despite the much smaller reverse-subset RMSE.

**Decision:** no refinement or promotion. The preceding arm's interior-W regression is not an unavoidable consequence of its horizontal forcing under projection: removing the W initialization correction reverses that regression under matched inputs. Retain the horizontal-only formulation as the more promising development arm, while diagnosing the remaining other-U and reversal losses before changing support or coefficients. Any residual stratification is descriptive only; it cannot remove observations or change the frozen score. Stop at four new answers, with no additional candidate in this request.

### Horizontal-only final audit and remaining targets

The [final isolation audit and answer ledger](experiments/joint_screen/canyon_horizontal/verdict.json) passes every evidence check, including the complete preprojection W-array comparison, sampled U/V parity with the preceding complement, identical native cell flags, input geometry/profile, complete observation IDs and unchanged installed binary/policy/fingerprint. The [comparison figure](experiments/joint_screen/canyon_horizontal/comparison.png) shows the component effects.

| Converged change from matched legacy | Core U/V/W, legacy roof | Core U/V, legacy W and roof |
| --- | ---: | ---: |
| Macro canyon U/W RMSE | -45.77% | -50.56% |
| Canyon U RMSE | -55.33% | -60.18% |
| Canyon W RMSE | -36.21% | -40.93% |
| Interior U RMSE | -69.59% | -80.19% |
| Interior W RMSE | +17.62% | -21.73% |
| Other-region U RMSE | +9.42% | +8.92% |
| Reverse-canyon U RMSE | -55.89% | -77.48% |
| Reverse-canyon U recall | 93.45% | 96.22% |

The new arm starts with the **same W field as legacy**: interior-W RMSE immediately before projection is 0.12878 in both. After projection it is **0.08153**, compared with legacy 0.10417 and the preceding complement 0.12253. Thus the unchanged horizontal forcing can produce a substantially better W field under the existing mass projection when the extra W initialization correction is removed. This supports dropping that correction from the development arm; it does not establish a generally valid production change.

The [zero-solve residual localization](experiments/joint_screen/canyon_horizontal/residual-localization.json) narrows the next question without changing any frozen mask:

- **15 lost reversal rows at 12 distinct coordinates**, all at z=3 m (z/H=0.2), lie 6 m from their column centerline, or 1.5 m inside the building's side edge. All are at or outside the current lateral core join. Their measured U/Uref ranges from -0.0951 to -0.000236, so the loss cannot be dismissed uniformly as near-zero noise. Repeated rows remain included.
- **225 parallel-street/edge U rows** at z=3, 7.5 and 12 m account for **69.13%** of the additional squared error in the frozen `other` U stratum. Their RMSE rises 12.62%. These rows sit alongside the building streamwise spans, at transverse distances 9, 12 and 15 m from the nearest column center.
- The other 232 over-building-plan rows and 96 rows above the canyon scoring height account for 28.67% and 2.20% of that additional squared error. These diagnostic labels do not create new acceptance strata or remove any measurements.

**Next focus:** audit the lateral taper/wedge join and its response in parallel streets at these exact coordinates. A separately scoped ablation retaining the horizontal core correction while restoring the legacy lateral prescription would distinguish core-strength benefit from lateral-joining error before any coefficient fit. This is a suggested experiment, not a selected model or a completed run. The four-answer diagnostic stops here with no refinement or promotion.

Verification: **34 targeted tests pass**, including a compiled test of the exact new whole-W audit. Injected W changes at core/boundary positions and signed-zero changes are detected; identical W is accepted and shape mismatches are rejected. The preceding roof-face audit positive controls still pass. No additional physical solve was needed for these checks.

## Lateral-join investigation authorized on 2026-11-05

The user requested investigation of lateral-join reversal losses and parallel-street other-region U error. First perform a **zero-solve audit** of the archived horizontal-only and legacy fields: retain every original observation; trace the lost reversals and all 225 parallel-street rows through each native stage; inspect canonical interpolation contributors and fallback status; check the join's coordinate/centering/support formulas and limiting signs. Diagnostic groupings do not change masks or acceptance gates.

**One conditional causal comparison:** if the audit supports a lateral-package origin rather than a data/geometry mismatch or failed sampling, test removal of the lateral package (the lateral core taper and lateral tanh overwrite together), retaining the same gamma=0.3 core amplitude, physical spacing, legacy W and protected roof initialization. This replaces the lateral package with the legacy canyon's transverse-uniform horizontal core profile, not a fitted width, shifted join or new coefficient. It isolates the lateral package as a unit and cannot distinguish its two terms individually.

**Bounded execution:** at most four new float64 native answers: aligned/oblique qualification of this one ablation, then a fresh horizontal-only reference and the ablation on the frozen full EPA grid. Verify the reference whole field against the archived horizontal-only answer; reuse the hashed original legacy fields for the unchanged physical scoring gates. Retain W/roof audits and capture complete preprojection W. Require convergence at tolerance 1e-12, at most 16,000 array iterations, 60 s deadlines, four native threads, one BLAS thread and sequential workers. No memory cap applies. Preserve all attempts; record results after the audit, qualification and physical pair. No additional arm, refinement, promotion, city run or coefficient fit is included.

### Lateral-join zero-solve audit

**Conclusion: a controlled lateral-package ablation is justified.** The [stage/formula/sampling audit](experiments/joint_screen/lateral_join/audit-001/report.json) passes all 11 checks. All 15 lost reversal rows and all 225 parallel-street rows use linear interpolation with fluid contributors; an independent eight-cell reconstruction agrees with the stored canonical U values within **9.44e-15 m/s**. No new coordinate, centering or fallback defect is detected in this supported aligned geometry.

The lost rows are all negative in the legacy canyon initialization and all nonnegative immediately after the horizontal overlay. Sidewall, rooftop and solid-mask stages do not change that outcome; projection leaves them nonnegative. The ideal specified lateral law itself gives zero at the inner join and forward U outside it at these coordinates, independent of the positive incident reference magnitude. Thus interpolation is relevant to resolution, but a fallback artifact is not the source of the lost sign.

The lateral width is **0.8–1.21 cells** at the lost coordinates; every corresponding final interpolation stencil spans both velocity signs. The quarter-power core factor is continuous at its zero inner join but has an unbounded core-side gradient (distance^-0.75). At the outer edge, the lateral prescription reaches gamma times ambient U while the untouched background remains ambient U. These are properties of the specified implementation; no exponent, coefficient or width is repaired by assumption.

All 225 parallel-street U samples remain **bitwise unchanged between arms through every preprojection stage**. Their final regression is a nonlocal projection response, not a direct overwrite of those probes. Mean normalized bias shifts from -0.01854 in the projected legacy field to +0.03701 in the horizontal arm; RMSE rises from 0.12574 to 0.14161. This distinguishes the street response from the sign imposed directly at the canyon join.

**Next:** remove the lateral taper and tanh overwrite together in one diagnostic arm, retaining gamma=0.3 and the same transverse-uniform legacy core shape, spacing, W and roof protection. Verify unchanged analytic centerline forcing and reference-arm parity before scoring. Interpolated centerline probes include off-center faces, so they need not be identical when the lateral profile changes. This tests the lateral package as a unit; its two individual terms and the fine-grid limit remain unassessed. No coefficient/width fit or altered measurement mask is allowed.

### Lateral-package ablation qualification

**Result: the one ablation qualifies for its array comparison.** Both converged synthetic answers pass the [qualification report](experiments/joint_screen/lateral_join/qualification-001/report.json). The aligned arm records 7,120 transverse-uniform U/V core assignments (including traversal repeats), zero lateral tanh assignments, zero W assignments or bit changes, and zero protected roof-face changes. The unchanged analytic centerline profile, finite fields, pre-canyon samples, canonical coverage/stage parity and all mass guards pass. Oblique flow remains exactly legacy with no overlay.

The [isolated build](experiments/joint_screen/lateral_join/build-001/manifest.json) contains a private switch for this single package ablation. The fixed core gamma, streamwise shape, physical spacing, W and roof protection are inherited from the audited horizontal arm. **Next:** run that horizontal arm freshly with the switch off, require full-field/stage/W-array parity with its archive, then run the switch-on ablation. Score both against the frozen original legacy observations and gates; do not substitute the already improved horizontal reference as the physical baseline.

### Lateral-package ablation result

**Conclusion: the lateral package causes the original side-join losses, but wholesale removal sacrifices useful accuracy and still does not pass selection.** The [array report](experiments/joint_screen/lateral_join/array-001/report.json) retains **40.96% lower macro canyon U/W RMSE** versus original legacy, compared with 50.56% for the unchanged horizontal reference. U improves 46.08% and W 35.84% versus legacy. Interior-U error rises **135.89% relative to the horizontal reference**, although it remains 53.28% below legacy. The lateral package therefore supplies substantial beneficial bulk-profile structure as well as the problematic join behavior.

All **15 original lost lateral-join reversal rows recover**. Their magnitudes overcorrect: normalized RMSE on those same 15 rows rises from **0.05993 to 0.16521**, even as their signs become correct. Four different reversals are lost at three coordinates higher in the canyon (z=12 m, z/H=0.8); overall recall becomes **98.99%**, passing the frozen 2-percentage-point recall guard. Reverse-canyon U RMSE is 65.00% below legacy, also passing its guard. No reversal rows were dropped or reclassified.

The parallel-street U RMSE improves from 0.14161 in the horizontal reference to **0.13558**, while legacy is 0.12574. Its mean normalized bias falls from +0.03701 to +0.02502 (legacy -0.01854). This confirms that changing canyon lateral initialization alters the remote street error through projection, but does not eliminate it. The unchanged frozen `other` U stratum still worsens **6.13%** against legacy, leaving its 5% region gate as the remaining physical failure. Diagnostic street bins do not add or replace selection gates.

The [fresh-reference parity check](experiments/joint_screen/lateral_join/array-001/reference-parity.json) reproduces the archived horizontal whole field, every captured stage, W initialization, flags and geometry bitwise. Both new array answers converge in float64. The ablation records active uniform-core assignments and zero lateral tanh assignments; complete W initialization matches both the reference and legacy, and all protected roof, finite, mass, coverage and stage guards pass.

**Decision:** stop this four-answer investigation without refinement or promotion. Do not simply remove the entire lateral package: the reversal/street improvement comes with a large core-U accuracy loss and an unresolved other-U regression. The next development question is a targeted lateral-join treatment that preserves the beneficial lateral profile, after checking its reference geometry and finite-resolution behavior. The current experiment cannot choose between the taper and tanh terms individually, justify a fitted shift/width, or establish fine-grid transfer.

### Lateral investigation final audit and implications

The [final verdict and four-answer ledger](experiments/joint_screen/lateral_join/verdict.json) verifies source epochs, reference parity, native helper hashes, active ablation, unchanged flags/geometry/profile/measurement IDs, complete W initialization, protected roof faces and the original installed binary/policy/fingerprint. The [investigation figure](experiments/joint_screen/lateral_join/investigation.png) shows the ideal join and the distinct stage histories of the two losses.

| Metric | Horizontal arm with lateral package | Same core, lateral package removed |
| --- | ---: | ---: |
| Macro canyon U/W RMSE change vs legacy | -50.56% | -40.96% |
| Interior U RMSE change vs legacy | -80.19% | -53.28% |
| Other-region U RMSE change vs legacy | +8.92% | +6.13% |
| Parallel-street diagnostic U RMSE change vs legacy | +12.62% | +7.82% |
| Reverse-canyon U recall | 96.22% | 98.99% |
| Original low-level lateral-loss rows recovered | — | 15 of 15 |
| New lost reversal rows elsewhere | — | 4, at three upper-canyon coordinates |
| Passes every frozen physical gate | No | No |

Three conclusions are supported within this frozen setup:

1. **The sign prescription is the immediate join-loss mechanism.** It imposes zero/forward U where the affected measurements remain negative, and all original losses recover when the lateral package is removed. Independent sampling reconstruction rules out a fallback or interpolation implementation bug. The coarse grid still underresolves the narrow join; the exact fine-grid error has not been assessed.
2. **The parallel-street regression is a nonlocal projection response.** The same street U initialization persists across legacy, the horizontal reference and the ablation through every preprojection stage. Only the final projected street U differs. Changing lateral canyon forcing reduces this remote error, but does not remove it.
3. **The lateral package also provides useful bulk structure.** Its removal raises interior-U RMSE 135.89% relative to the horizontal reference and loses 9.59 percentage points of macro canyon improvement. The two lateral terms were ablated together, so neither one's individual benefit or defect is selected. The new upper-canyon reversal losses also demonstrate redistribution rather than a universal topology repair.

**Recommendation:** keep the horizontal-only arm as the reference for further development and investigate a physically supported join that retains its useful lateral variation. Review continuity, finite gradients, ambient-edge matching and coordinate support before a new native comparison. Do not fit gamma or a join width to these residuals, drop weak reversals, relax the 5% other-region guard or promote the near-passing ablation. A separate supported-geometry or finer-grid qualification remains necessary before making a general model recommendation.

**37 targeted tests pass**, including new independent affine-interpolation, out-of-grid and analytic sign-anchor checks for the zero-solve audit. No extra physical answer was used for these checks. Both new array answers converge (2,863 reference and 2,865 ablation iterations); all four workers meet their deadlines. This investigation is complete at its four-answer limit.

## Implementation plan: bounded validation behind an experimental option

**Status: implementation integrated; A/B/D/E validation is complete and the roof/grid protection failure is now fixed and verified. D measured errors still exceed legacy, so the option remains experimental. The original EPA block remains stopped.** The private selector, reference overlay, one specified join, audit snapshots, solve-scoped cleanup and fail-closed validation controller are implemented. The [join specification](experiments/joint_screen/canyon_validation/join-v1-specification.md) declares a two-sided layer of width 2delta and derives its Hermite bridge from a minimum-curvature mixing assumption. Its outer reference is explicitly the incident profile, with turning/reversed/calm sub-roof profiles unsupported. It is a new QES adaptation with no measured qualification yet. The [transfer eligibility record](experiments/joint_screen/canyon_validation/transfer-eligibility.json) leaves independent measured transfer unassessed. This sequence applies to one new join candidate. It does not reopen refinement or promotion of any arm that already failed. The objective is to integrate the qualified horizontal canyon machinery into dtcc-qes behind a private, default-off option, then decide whether one independently specified join revision earns further development.

### 1. Freeze the evidence and workloads

- Preserve all completed attempts, source/binary identities and failure decisions. Treat the horizontal-only arm as the development reference; its frozen EPA result is 50.56% lower canyon error, with other-U and reversal-recall failures. Treat the lateral-package removal as an explanatory ablation, not a replacement model.
- Reuse the full 77-cube EPA geometry, measured upstream profile, original observation IDs, repeated rows, component separation and primary/diagnostic masks. Preserve original legacy as the physical selection baseline. The 15 lost reversal rows and 225 parallel-street rows remain diagnostic subsets, never exclusions or a new fitted target.
- Freeze a second measured canyon's eligibility before opening its model results. Prefer the independent wide-building canyon identified in the literature plan; require numerical measurements, geometry/axes, signed component conventions, units, forcing, normalization, scoring masks and source hashes. Document any digitization uncertainty. A synthetic fixture or isolated building does not replace measured canyon transfer evidence.
- Timebox the second-reference eligibility search to one hour. If it remains unavailable, continue the eligible implementation/EPA work and label transfer unassessed. Keep the option experimental; reserve its two answers without substituting a convenient case or adding simulations.

**Deliverables:** an immutable validation manifest, reference hashes and a second-case eligibility record under `experiments/joint_screen/canyon_validation/`. Archive the implementation plan revision with the first executed attempt. No new native answer is needed here.

### 2. Integrate one private option and the qualified reference

Use one named selector through the existing private experiment bridge:

```python
session.run(args, research={"canyon_model": "joined_v1"})
```

The planned accepted values are `legacy` (default), `horizontal_reference_v1` and `joined_v1`. Map them to a typed native enum and record their names and schema version in result metadata. Unknown values must fail before mutation. `joined_v1` becomes runnable only after its exact specification and implementation are complete; it must never silently alias a reference model.

| Area | Planned change |
| --- | --- |
| `src/qes_core/dtcc/api/experiment_types.h` | Add the default-off selector and versioned canyon diagnostics to private experiment types. |
| `src/cpp/bindings.cpp` | Parse the private selector; expose effective model identity, support/fallback reasons, audit counters and validation snapshots. |
| `src/qes_core/dtcc/wind_runner.cpp` | Extend the existing solve-scoped cleanup; reset mode and counters after success, exceptions and reused conditions. Capture W immediately before projection when validation capture is requested. |
| `src/qes_core/winds/WINDSGeneralData.{h,cpp}` | Keep the complete legacy pass first. Dispatch the selected qualified overlay afterward, with diagnostics enabled only for research validation. |
| `src/qes_core/winds/StreetCanyonModified.cpp` and small canyon helpers | Consolidate the qualified support, horizontal reference and new kernel. Keep `streetCanyon()` unchanged. Do not port unrelated contents of temporary source trees. |
| `experiments/joint_screen/` | Add one validation controller using the existing `Session`, canonical sampler, stage capture, evidence utilities and deadline-only supervisor. Earlier scripts/attempts remain reproducible. |
| `tests/test_joint_screen.py` and native helper tests | Extend meaningful model, isolation, lifecycle and numerical-contract checks. Keep independent sampling and audit positive controls. |

The public `Parameterizations` range remains unchanged: no public `street_canyon=2` and no new qualified production default. These research modes use explicit legacy solver control; they must not inherit `pedestrian-v1` qualification or an adaptive stopping policy. Reject incompatible model combinations instead of silently running an inactive experiment: retain the frozen wake/roof/upwind/sidewall settings, specialized high-rise off, and no canopy, roof-only, wake-diffusion or turbulence candidate stacking in this sequence.

Support stays restricted to the qualified flat-ground, equal-height rectangular canyon geometry with matching spans and normal incident flow. Unsupported geometry, oblique/calm flow and a missing downstream canyon use legacy behavior, with reason counts. Ambiguous or overlapping downstream supports must fall back before any overlay write; add explicit tests for those cases. Candidate selection must not affect geometry preparation or leak through a reused runner. Every run identity must include the selector, kernel/specification revision, constants, source/binary/policy hashes, compiler settings, inputs, precision and actual threads.

**Build workflow:** make targeted source changes while preserving the existing dirty workspace. Build and load a new isolated package with the current environment; do not replace the installed module or sync dependencies during validation. A rebuilt experimental library will have new source/binary/policy hashes: record them and prove legacy-off output parity, rather than expecting a rebuilt hash to equal the archived binary.

### 3. Specify exactly one join candidate before scoring it

**This is the remaining physics design task.** The investigations establish defects and trade-offs, not an already validated replacement equation. Write `join-v1-specification.md` and a machine-readable, hashed specification before exposing new measured scores. Require a primary physical basis or a clear derivation from declared mixing/boundary assumptions; label a new QES adaptation as such, not as exact Singh reproduction.

The specification must define:

- Coordinates, canyon support and staggered component locations; x from the trailing wall, centered transverse y and the same height datum.
- The retained bulk horizontal core profile, gamma=0.3 and streamwise/spacing law. Preserve its useful interior variation away from a declared join neighborhood. State exactly which part of the existing taper the new transition replaces; retaining a zero core value at the same join while merely smoothing it does not resolve the diagnosed sign prescription.
- Inner and outer reference velocities, their signs, target-height dependence, physical support and any overlap rule. Explain how the transition joins the retained core and applicable incident/background field. Do not infer a join shift or width from the 15 residual coordinates.
- Continuity and finite one-sided gradients at both joins, ambient-edge matching, bounded transition values and finite limits as x or the mixing width approaches zero. Preserve transverse symmetry and rigid translation/rotation of the formulas.
- The unchanged legacy W field, protected roof region and ordering relative to sidewall/roof stages and projection. No new W, cavity-height, roof-vortex or turbulence law joins this candidate.
- Fixed constants, version identifier and an explicit account of departures from the earlier reference. No parameter sweep, case-dependent branch or adjustment after reviewing EPA scores.

Qualify the kernel with independent limiting-case anchors and native helper tests, including sign/derivative behavior, degenerate supports, symmetry and coordinate transforms. Keep the audit tests capable of detecting deliberately injected protected-roof/W changes. A smooth interpolant alone is not a physical justification.

**Stop rule:** if a defensible single prescription requires fitting residuals, a general canyon-support redesign or an unresolved joining/composition convention, finish the private option/reference/audit work and report the candidate unassessed. Do not spend the physical budget on a guessed formula or open a second candidate family. Bound pre-solve design/integration effort to one engineering day; report unfinished work at that limit.

### 4. Qualify the integrated implementation

Reserve **at most six small-fixture native attempts**, including one deliberate failure. Use the existing aligned pair and oblique condition, one reused runner, float64 tolerance 1e-12, at most 8,000 iterations and a 60 s deadline per attempt. Run a fixed sequence:

1. Legacy aligned; match the archived legacy fixture field and canonical samples.
2. `horizontal_reference_v1` aligned; match its archived qualified field/stages.
3. `joined_v1` aligned; require activity, finite/converged fields, mass/coverage/stage checks and direct W/roof preservation.
4. `joined_v1` oblique on the reused geometry; match archived legacy oblique output and verify no overlay. This checks direction-dependent eligibility is recomputed.
5. Deliberately throw after experimental state is attached, using a test-only native hook. Preserve and count this failed attempt; do not add a general public fault-injection option.
6. Legacy aligned again on the reused runner; require bitwise equality with attempt 1, proving cleanup after both mode changes and the failure.

The deliberate failure is expected only at its declared test hook; it passes that test only when the expected exception and subsequent cleanup/parity checks are observed. Any other failure stops the block.

Use compiled geometry/kernel tests for holes, malformed polygons, unequal/partial spans, ambiguous overlaps, zero spacing and unsupported terrain/base cases; do not create an open-ended native fixture campaign. Check native symbols and the applicable public API tests. Default-off and unsupported paths must remain legacy. No field comparison may rely on an eight-character policy prefix.

**Gate:** all applicable implementation, lifecycle, finite, sampling, solid/interior/top/flux and isolation checks pass. Failure stops physical execution. Diagnose a failed control without tuning the candidate or automatically replenishing attempts.

### 5. Execute the conditional physical sequence

| Stage | Pair | Grid and numerical limits | New answers | Advance only if |
| --- | --- | --- | ---: | --- |
| V1: frozen EPA screen | Fresh legacy vs `joined_v1` | Full array, 1.875 m; float64, tolerance 1e-12, 16,000 iterations, 60 s each | 2 | All frozen physical/numerical/isolation gates and reference-retention gate pass. |
| V2: grid sensitivity | Fresh legacy vs the same frozen `joined_v1` | Same complete domain/profile/observations, 0.9375 m; float64, tolerance 1e-12, 32,000 iterations, 180 s each | 2 | Converged benefit and common physical gates survive refinement without unexplained sign/region changes. |
| V3: measured transfer | Fresh legacy vs the same frozen `joined_v1` | Eligible second canyon; freeze domain, grid, forcing and probes from metadata before execution; float64, tolerance 1e-12, 32,000 iterations, 180 s each | 2 | The measured transfer screen passes with no parameter change. |

Use the fresh legacy answer for every physical selection gate. At V1 it must reproduce the archived coarse legacy whole field, geometry and coverage before the candidate is scored. Use archived horizontal-reference metrics as a separately identified development benchmark, with input/probe hashes checked; do not describe that archive as a newly matched runtime comparison.

**Keep the existing gates:** at least 10% lower equal-component macro canyon RMSE; no component or measured region more than 5% worse than its matched legacy; reverse-U RMSE no more than 5% worse; reversal recall loss no more than two percentage points; all finite, convergence, canonical coverage/stage, impermeability and mass guards. Preserve every eligible repeated observation and signed-component convention. Report all-observation, roof, lateral-edge, approach/recovery and frozen `other` errors plus the original residual subsets. Do not promote a near miss by changing masks or thresholds.

**Add an explicit retention gate before seeing the new candidate:** on V1, final interior-U and interior-W RMSE must each be no more than 5% worse than the archived horizontal reference on identical inputs/probes. This guards the useful bulk accuracy lost by wholesale lateral removal. It supplements, and never relaxes, the legacy-based gates. Report the candidate's overall and roof errors against that reference as well.

At V2 and V3, use the same legacy-based gates and require the protected W/roof initialization contract. Distinguish solver convergence from discretization sensitivity. Report coarse/fine changes in each arm and their effect size, reversal extent and join gradients; the coarse field need not be bitwise equal to the fine field. An unresolved grid dependence is inconclusive even if an aggregate score improves. Freeze the second-case geometry, normalization and masks before opening its scores; case-specific numerical/data gaps do not establish physical failure.

**Execution limits:** four native threads, one BLAS thread and one timed worker at a time. No memory cap or inferred cell-count rejection applies; record RSS and validate structural grid limits. Never crop the physical domain, drop probes, retune or repeat a timed-out attempt to get a pass. No numerical sweeps or hidden native solves are included. A capped, nonconverged, timed-out or identity-mismatched answer stops its stage and leaves the result unresolved.

### 6. Evidence, stopping decisions and completion

Before each stage, freeze descriptors, model/specification hashes, complete settings, eligibility and acceptance rules in a fresh manifest. Save native source/binary snapshots, worker outcomes, complete W initialization and direct roof/W audits, stage/final canonical samples, coverage, flags, mass diagnostics and measured errors. Preserve fallback reasons and actual intervention counts; an inactive candidate is an implementation failure, not physical evidence against the join.

After each fixture block or physical pair, write the result and decision into this plan before proceeding. Produce standalone figures of join behavior, stage effects and regional/transfer errors. Report paired profile/spatial uncertainty as descriptive evidence, not independent confirmation from repeated observations. Keep failure/incomplete attempts and never overwrite canonical validation records or earlier snapshots.

The total ceiling is **six fixture attempts plus six physical answers: twelve new native attempts**, including the deliberate failure. Their maximum worker allocation is **20 minutes** (six 60 s fixtures, two 60 s coarse workers, four 180 s refinement/transfer workers). Build, data eligibility and design effort are separate and timeboxed above. Pure helper tests and stored-record analysis do not consume physical answers. Stop at the first unmet advance gate; no candidate replenishment or automatic retry is included.

Completion means: the private option is documented and tested; legacy remains the default; the one candidate has an immutable specification and a recorded result at every stage it earned; outstanding data/numerical limits are explicit; and the final verdict states whether further development is justified. Passing all three stages earns an experimental engineering recommendation and a reviewable change, **not an automatic default change, public flag expansion, release qualification or deployment**. Missing measured transfer evidence leaves that claim unassessed. A broader production recommendation needs its own scope and evidence.

## Current development priorities

1. **Complete qualification of the integrated experimental option while preserving useful lateral structure.** Use the qualified horizontal-only arm as the development reference, specify exactly one supported join, and advance through coarse, refined and measured-transfer pairs only when their prerequisites pass. The option stays private and default-off; no coefficient fit or automatic promotion is selected. Earlier failed arms remain closed.
2. **Qualify the specified E3v native vertical wake component.** The prescription, edge trace, scope and limits are frozen independently of A/B scores. Full historical horizontal joining is still underdetermined. Keep roof forcing, canyon changes and turbulence options separate. Matching isolated/embedded tower data are still needed before a canopy-dependent support law can be selected.
3. **Retain roof forcing as a restricted isolated-building candidate.** Its 2 m A/B benefit is real and numerically resolved; confirmation at 1 m and on unseen isolated geometry remains necessary. Its current activation coverage and city top-band failure close urban expansion of this arm.
4. **Keep turbulence work separate from mean-flow development.** Wall distance substantially improves isolated trace-k error and covariance validity, but its A correlation failure remains. A trace-preserving covariance repair cannot improve trace-k by itself. Any viscosity/closure follow-up needs the existing fixed masks and measured stress evidence; it does not count as a mean-wind improvement.

The [cavity-amplitude diagnosis](experiments/joint_screen/cavity_strength/attempt-001/report.json) is also negative after separating regions: at 2 m, the 14 measured reverse-flow wake points in A have U bias -0.09309 Uref, while the 38 reverse-flow wake points in B have +0.06427 Uref. B's upwind and roof reversals must not be pooled into that cavity claim. Momentum feasibility, cut-cell work, non-local turbulence and comparator archives remain queued behind their stated evidence/effort gates. These results do not establish that all empirical alternatives have failed or select a new momentum backend.

**Execution ledger:** the initial campaign used 24 primary answers and ten controls ([initial ledger](experiments/joint_screen/E4/verdict.json)). Canyon qualification and its full-arm screen added ten primary answers and two controls ([canyon ledger](experiments/joint_screen/E1/qualification-verdict.json)). Roof components added six primary answers ([component ledger](experiments/joint_screen/canyon_mixing/verdict.json)), the core/lateral complement four ([complement ledger](experiments/joint_screen/canyon_core/verdict.json)), and the horizontal-only diagnostic four ([horizontal ledger](experiments/joint_screen/canyon_horizontal/verdict.json)). This investigation adds **four primary answers** ([lateral ledger](experiments/joint_screen/lateral_join/verdict.json)). Combined: **52 primary answers + 12 controls = 64 native answers**. This investigation's worker-body time is 10.22 s and supervised-worker time 14.96 s; combined worker-body time is 226.14 s. These exclude implementation, analysis, bootstrap and build effort, so they are not end-user runtime benchmarks. All completed workers meet their deadlines; no memory rejection applies. No new CFD job, public range, native release qualification or production default was changed.

Verification: **37 targeted tests pass** (`tests/test_joint_screen.py` plus `validation/tests/test_case_ab.py`), including independent lateral-audit sampling/sign checks and compiled positive controls for roof-face and whole-W audits. The [lateral investigation audit](experiments/joint_screen/lateral_join/verdict.json) verifies reference parity, source epochs, native helper hashes, unchanged geometry/flags/profile/observations, protected roof and W initialization, and the original installed binary SHA256, validation fingerprint and full solver policy. Native-symbol audits pass; all new float64 answers converge. Every physical gate failure remains recorded.

## Integrated implementation and testing preparation

The private `_solve_experiment` bridge now accepts `canyon_model="legacy"` (default),
`"horizontal_reference_v1"` and `"joined_v1"`, plus `canyon_capture=True` for the
complete preprojection W snapshot. Public `Parameterizations` still accepts
street-canyon values 0–1. The legacy canyon routine and public defaults are
unchanged. Research modes reject stacked candidates, incompatible flags,
turbulence and adaptive control; their metadata includes the selector, version,
join specification hash, fallback reasons and direct roof/W audit counters.
Mode, incident vectors and counters are cleared on every scope exit.

The integrated reference retains the archived horizontal overlay, with a
deterministic preflight that rejects tied/overlapping downstream supports before
writes. The independent roof audit now constructs eligibility from **pre-overlay
snapshots**, so corrupting a roof reference cannot hide its own audit zone.
The new join preserves bulk initialization outside its declared two-sided layer;
it changes no W or protected roof faces. Its minimum-curvature closure and incident
outer-background assumption remain physical hypotheses, not measured conclusions.

### Qualification block: stopped; stored controls diagnosed without rerunning

Two of the six reserved fixture attempts ran in `build-002`, on one cached geometry:

| Attempt | Outcome | Evidence |
| --- | --- | --- |
| Legacy aligned | Converged in 1,370 iterations; whole field, flags, stages and canonical probes bitwise equal to archived legacy. | [Worker](experiments/joint_screen/canyon_validation/campaign-001/qualification/legacy-aligned/worker.json) |
| Horizontal reference aligned | Converged in 1,364 iterations; whole field, W initialization, flags, stages and probes bitwise equal to its archive. Mass guards pass; zero roof/W changes. | [Worker](experiments/joint_screen/canyon_validation/campaign-001/qualification/reference-aligned/worker.json) |

The controller incorrectly compared the old `max_cells=20,000,000` rejection
ceiling with the new structural ceiling `2^31-1` as a physical-domain difference.
It stopped after attempt 2, then hit a relative-path error while writing the plan.
The initial supervisor also overwrote the worker's detailed report with a generic
failure; the complete arrays, worker records, manifest, source/binary snapshots,
attempt ledger and logs survived. These are implementation/reporting failures,
not evidence against canyon physics.

The corrected comparison ignores **only** that rejection ceiling, retains all
physical domain checks, resolves report links, and preserves worker reports after
supervisor errors. Stored-record diagnosis passes **36 checks** without a new
solve ([final diagnosis](experiments/joint_screen/canyon_validation/campaign-001/qualification/control-diagnosis-final.json)).
Regression tests cover the ceiling distinction, physical-grid mismatch, report
preservation, failed-worker stopping, predecessor identity and immutable budgets.

**Decision:** keep qualification incomplete and the physical gate closed. No
candidate field, oblique fallback, deliberate exception or final reused legacy
attempt was run. Do not turn the offline diagnosis into a six-attempt lifecycle
qualification. Do not rerun or replenish this block automatically. The later
scope-exit counter cleanup is compiled and unit checked but has no new field
qualification. A separately scoped qualification continuation/restart must account
for the lost live runner and the two consumed attempts before EPA execution.

This adds **two native control answers**, totaling **66 historical native answers**
(52 primary + 14 controls). Their worker bodies took 1.145 s; supervised time was
9.100 s including reporting/font-cache overhead, not a solver benchmark. Peak RSS
was recorded (318,242,816 and 329,613,312 bytes), with no memory rejection. Both
workers used four native threads and converged at float64 tolerance 1e-12. No EPA,
refined or measured-transfer answer was added.

### Testing handoff

The [controller](experiments/joint_screen/canyon_validation.py) implements separate
qualification, coarse and refinement commands, immutable source/input/native
identities, one-worker deadlines, frozen physical gates, horizontal-reference
retention, original residual-subset diagnostics, regional figures and coarse/fine
sign-volume/shear comparisons. A failed or mismatched predecessor blocks execution.
Refinement requires explicit review of grid dependence; it cannot automatically
authorize transfer. Transfer remains unassessed because an eligible independent
numerical canyon dataset/adapter has not been frozen. Neither missing transfer
data nor the reporting failure is a physical model rejection.

`--prepare-only` freezes the aligned/oblique fixtures and complete coarse/fine EPA
workloads without native preparation, a solve or budget reservation. It preserves
all 12,893 original U/W observation rows and the full domain on both grids. See the
[testing instructions](experiments/joint_screen/canyon_validation/README.md).

Both current isolated builds compile and pass native-symbol audits:
[ordinary build-003](experiments/joint_screen/canyon_validation/build-003/build-result.json)
omits the fault hook; [research build-004](experiments/joint_screen/canyon_validation/build-004/build-result.json)
includes it. The hook defaults off in CMake. Neither build inherits pedestrian
qualification. The installed native binary, full solver policy, validation
fingerprint and dtcc-core identity remain unchanged
([isolation check](experiments/joint_screen/canyon_validation/installed-isolation.json)).

The [prepared testing manifest](experiments/joint_screen/canyon_validation/campaign-001/testing-preparation-001/manifest.json)
freezes the current research build and all eligible workloads with **zero new
native attempts**. It explicitly records the stopped qualification gate.

Verification: **50 targeted tests pass**, including compiled kernel/preflight/audit
positive controls and validation-framework tests. **11 public parameterization
input/default tests pass** against the current research build, without extra native
answers. The broader solve-based public suite and the four remaining lifecycle
fixtures were not run; no production or measured-physics qualification is claimed.
The [verification record](experiments/joint_screen/canyon_validation/verification-001/report.json)
includes test-source hashes, both current build identities and isolation checks.

## Authorized full AIJ comparison: A, B, D and E

The user subsequently requested all validation cases and a comparison with the
current baseline numbers. This is a new diagnostic validation scope, separate
from the stopped EPA qualification campaign. Freeze one fresh six-attempt
implementation block and **37 matched legacy/joined_v1 pairs**: A/B at their 1 m
baselines, D at all three 2 m directions and E at all 16 directions in both
states. Preserve the earlier two attempts and all earlier failure decisions.
Complete the requested matrix even if a physical score worsens; this scope does
not change any promotion gate or authorize parameter tuning.

Use the canonical validation adapters, measured inputs, masks, default QES-Turb
and historical fixed solver work (A/B 6,000 sweeps; D/E 2,000; float32 tolerance
1.2e-7). The private bridge has an explicit allowance for the **unchanged default**
one-way turbulence model; its default remains off and wall-distance/other
turbulence candidates remain rejected. Do not represent fixed-work results as
new tolerance-converged physics evidence. Rebuilt legacy must reproduce archived
probes, planes, inputs and diagnostics. Record complete-field/W/stress hashes,
direct roof/W audits, fallback/activity counters, mass guards and actual threads.

The controller is `experiments/joint_screen/canyon_aij.py`. Its immutable
manifest, source/binary snapshots, failed attempts and outputs will go under
`experiments/joint_screen/canyon_validation/aij-001/`. Use four native threads,
one BLAS thread, one worker at a time, deadlines of 180 s (A/B), 60 s (D) and
120 s (E). Record RSS with no memory cap or inferred cell-count memory rejection.
Keep canonical baseline records and reports untouched. Report all conditions,
instrument/quantity/region scores, A/B signed-flow features and E intervention
errors. An inactive overlay demonstrates fallback/default-path regression only,
not validation of the new join's physical benefit.

### AIJ implementation block and first completed cases

The new six-attempt qualification block **passes all 78 checks** in build-005:
archived legacy/reference parity, active finite/converged join, unchanged W and
protected roof on the aligned fixture, exact oblique fallback, deliberate
exception and final legacy parity on one reused geometry. This qualifies that
small supported fixture; it does not erase the stopped earlier block or establish
support on a different vertical grid.

A and B at 1 m and D at all three 2 m directions have completed. Fresh legacy
answers match archived records. A/B and the oblique D directions are bitwise
unchanged because the overlay falls back. **D at 0° is active**: 34 buildings
qualify, 66,640 component faces change, and normalized maximum probe-vector change
is 0.16326 Uref. W initialization remains bitwise legacy and mass guards pass,
but the roof audit flags **6,800 changes**. Split-fibre MAE changes from 0.170461
to 0.175596 (+3.01%); thermistor K MAE changes from 0.217832 to 0.222344 (+2.07%).
Correlation rises slightly while hit rates fall. Keep the protection failure;
do not tune or relax it.

The saved D grid places 10 m roofs between 9 and 11 m vertical faces. The overlay
uses the voxel roof-reference face while the independent audit uses physical H.
This is a plausible source of the protection disagreement, not a proven
localization of every flagged face. The current snapshots do not contain full
pre-overlay U/V face arrays, so exact localization remains unassessed without a
separately scoped diagnostic. The result cannot earn promotion even if an
aggregate score were favorable.

All 16 E-before directions have also completed with zero intervention and
bitwise field/stress parity. E-after is running. The complete requested matrix
continues with frozen physics despite the D failure; a final verdict follows
when every case/state/direction is recorded.

### Full AIJ matrix: complete; do not promote

All **37 conditions / 74 matched answers** completed, plus the six-attempt
implementation block (five field answers and one expected exception). Every
deadline passed. The [full conclusions](experiments/joint_screen/canyon_validation/aij-001/CONCLUSIONS.md)
and [verified analysis](experiments/joint_screen/canyon_validation/aij-001/analysis-001/report.json)
record the result. All fresh legacy controls exactly reproduce their archived
baseline inputs, diagnostics, probes and planes. Shared measurement coverage,
whole-grid flags and baseline identities are preserved.

| Case/quantity | Baseline MAE | joined_v1 MAE | Change |
| --- | ---: | ---: | ---: |
| A mean speed, 1 m | 0.124956 | 0.124956 | 0% |
| B mean speed, 1 m | 0.186147 | 0.186147 | 0% |
| D split fibre, 0°, 2 m | 0.170461 | 0.175596 | +3.01% |
| D thermistor mean speed, three directions | 0.217832 | 0.222344 | +2.07% |
| D thermistor scalar-speed proxy, three directions | 0.193218 | 0.197654 | +2.30% |
| E-before mean speed, 16 directions | 0.226642 | 0.226642 | 0% |
| E-after mean speed, 16 directions | 0.201418 | 0.201418 | 0% |

Only D at 0° is active. The other **36 conditions** have bitwise whole-field and
stress parity. A/B have no downstream canyon; E's actual geometry/flow combinations
are unsupported, including explicit ambiguous/overlapping-support fallbacks. E
intervention K-change MAE stays 0.145227, R 0.40746 and clear-change sign agreement
72.89%; scalar-change MAE stays 0.142069. No A/B signed-flow feature improves.

In active D, speed correlation and median direction error improve slightly, while
MAE and hit rates worsen. W initialization remains bitwise legacy and **all mass
guards pass**, but the **6,800 protected-roof changes** remain a failed engineering
guard. The roof/grid-datum explanation above remains a hypothesis rather than a
complete face-level localization. No source change or tuning was made after the
matrix began. This two-arm comparison does not isolate the join increment from
the retained horizontal reference.

**Decision:** keep the option experimental and default off. Resolve and qualify
the roof-height/vertical-grid protection contract before further mixing-law tuning
or any general recommendation. The 36 inactive conditions establish fallback and
regression behavior, not a physical benefit. Earlier failures and the old stopped
campaign are not reopened or erased.

The new campaign uses **80 native attempts** (79 field answers and one deliberate
failure), bringing the historical ledger to **145 field answers plus one expected
failed attempt**. Matrix workers took 773.2 s including capture/startup; peak RSS
was 2.31 GiB with no memory rejection. These are not timing benchmarks. The
installed binary, full policy, validation fingerprint and dtcc-core identity are
unchanged ([isolation](experiments/joint_screen/canyon_validation/aij-001/installed-isolation.json)).
Fifty helper/framework tests and two paired-coverage tests pass; public input/default
checks are also exercised against build-005 without adding field answers.

## Roof-height/grid correction: investigation and verification

The user requested investigation and repair of the protected-roof failure.
Preserve all AIJ answers, including D's failed audit and measured-error regression.
Use a read-only traced reproduction before changing the guard, then qualify the
fix on the aligned/lifecycle block, off-face roofs in both directions and the
affected D 0° condition. This scope does not fit the join or rerun inactive cases.
Keep four native threads, one BLAS thread, one timed worker at a time and no
memory rejection. Record all source/binary identities and failed attempts.

**Investigation result:** one traced D 0° answer exactly reproduces the prior
joined probes, planes, full velocity/stress hashes and full W initialization.
Every one of the **6,800 audit failures** has matching actual write provenance:
physical roof 10 m, actual write reference 11 m, inside the physical wedge and
outside the voxel wedge. There are 4,080 U and 2,720 V changes at z=6, 8 and 10 m;
no W or roof-reference corruption explains the discrepancy. This confirms the
previous height-datum hypothesis at every flagged face
([trace report](experiments/joint_screen/roof_fix/diagnosis-001/report.json)).

**Fix selected before new measured results:** preserve the union of the physical
and legacy voxel roof bands for each U/V face. Keep the legacy reference and
distance calculation and add the physical-height inequality; neither band may
shrink when a grid represents the roof above or below H. The physical audit's
inequality and support remain unchanged. Add a separately counted voxel-band
audit and positive controls, plus default-off face/write tracing. The join
equation, coefficients and immutable join specification stay unchanged; metadata
identifies `physical-and-voxel-union-v1` separately
([protection specification](experiments/joint_screen/roof_fix/protection-specification.md)).

### Roof/grid correction: verified

Build-008 enforces the union guard before every experimental U/V write and removes
the unreachable roof-forcing blocks. The existing physical audit remains intact;
a new independent voxel-band count prevents a physical-only substitution from
shrinking the old protected support. No join coefficient, domain, observation or
solver-work setting changed. The original join specification/hash is preserved,
with a separately recorded protection revision.

The [verification](experiments/joint_screen/roof_fix/verification-001/report.json)
passes all gates. Aligned/reference/joined, oblique fallback, deliberate exception
and reused legacy checks pass **80 assertions**, including bitwise parity with
the archived aligned fields. Two active, converged nonuniform-grid pairs pass:
H=10 m represented at 11 m, and H=11.5 m represented at 11 m. Positive-control
unit tests independently catch corruption in either protected band.

In fresh D 0° answers, both joined and horizontal-reference overlays retain 34
qualified buildings and **59,840 changed faces**, while physical-roof changes fall
from **6,800 to zero** and voxel-roof changes are also zero. Complete W initialization
is bitwise legacy. Mass, finite fields, coverage, flags, geometry and thread guards
pass. Fresh legacy reproduces the archived baseline. The new trace is empty in
both fixed modes; the restoration removes exactly the 6,800 previously flagged
face changes without deactivating the canyon model.

**Decision:** the protection bug is fixed. This is an implementation correction,
not evidence for physical promotion: D split-fibre MAE is now **0.177039** versus
0.170461 legacy (+3.86%) and 0.175596 for the earlier broken joined arm. Aggregate
D thermistor K MAE is 0.222816 (+2.29%) and K_scalar MAE 0.198133 (+2.54%). The
two inactive oblique directions are reused from the unchanged archive for those
aggregate rows. Keep the option experimental; no coefficient tuning was performed.

This task adds **14 native attempts** (13 field answers and one expected exception).
The historical ledger becomes **158 field answers plus two expected failed
attempts**, or 160 native attempts. All new workers meet deadlines; no memory cap
or rejection applies. Fifty-four helper/framework tests and eleven public
input/default tests pass. Native-symbol audits and installed isolation checks pass.
See [the complete fix report](experiments/joint_screen/roof_fix/README.md). Earlier
reports and the original stopped campaign remain unchanged; the full inactive
A/B/E matrix was not repeated.

### Integrated validation: qualification

Decision: **pass**. Started native attempts: 6. Unmet checks: none. [Evidence](experiments/joint_screen/canyon_validation/aij-001/qualification/report.json). Physical execution remains a separate explicit stage.

### Integrated validation: qualification

Decision: **pass**. Started native attempts: 6. Unmet checks: none. [Evidence](experiments/joint_screen/roof_fix/verification-001/qualification/report.json). Physical execution remains a separate explicit stage.

## Full validation after the roof/grid update

The user requested a complete rerun and comparison after the fix. Run a fresh
six-attempt implementation block and all **37 matched baseline conditions / 74
matrix answers** with the unchanged build-008 (`physical-and-voxel-union-v1`).
Use A/B at 1 m, D at all three 2 m directions, and E before/after at all 16
directions, with the original measured inputs, masks, default one-way QES-Turb
and fixed solver work. Freeze results under
`experiments/joint_screen/canyon_validation/aij-002/`; preserve aij-001 and the
targeted roof-fix verification. Compare the complete new matrix with fresh legacy,
archived baseline numbers and the preceding full joined matrix. Do not infer
completion of inactive cases from the earlier run in this scope.

Keep four native threads, one BLAS thread, one timed worker at a time and the
existing per-answer deadlines. Record RSS with no memory cap. Track physical and
voxel roof protection independently, complete W initialization, full-field/stress
hashes, sampling/coverage, mass guards and actual activity. This is diagnostic
validation with frozen physics and no tuning or automatic promotion.

### Post-fix full validation: complete

All **37 paired conditions / 74 matrix answers** completed in aij-002, with a
fresh six-attempt implementation block passing **80 checks**. There were no
unexpected failures or timeouts. Every input/grid/sampling/coverage/flag/thread
check, complete W preservation, physical-roof audit, voxel-roof audit and mass
guard passes. Every fresh legacy control reproduces the archived baseline;
legacy whole-velocity and stress hashes also match the preceding full campaign
in **37/37 conditions**.

The [complete version comparison](experiments/joint_screen/canyon_validation/aij-002/version-comparison/COMPARISON.md)
includes all 15 measured quantities, with machine-readable shared-coverage and
artifact checks. All cases were rerun; the full D 0° answer exactly reproduces
the targeted roof-fix result, including probes, diagnostics and full-field hashes.

| Comparison | Legacy MAE | Previous joined MAE | Updated joined MAE | Updated vs legacy |
| --- | ---: | ---: | ---: | ---: |
| A mean speed | 0.124956 | 0.124956 | 0.124956 | 0% |
| B mean speed | 0.186147 | 0.186147 | 0.186147 | 0% |
| D split fibre, 0° | 0.170461 | 0.175596 | 0.177039 | +3.86% |
| D thermistor K, three directions | 0.217832 | 0.222344 | 0.222816 | +2.29% |
| D thermistor K_scalar, three directions | 0.193218 | 0.197654 | 0.198133 | +2.54% |
| E-before mean speed, 16 directions | 0.226642 | 0.226642 | 0.226642 | 0% |
| E-after mean speed, 16 directions | 0.201418 | 0.201418 | 0.201418 | 0% |

Only D at 0° activates the overlay (34 buildings, 59,840 changed faces). The
other **36 updated joined conditions** have bitwise velocity/stress parity with
both legacy and the prior joined version. No observation coverage was lost or
gained. E intervention K-change MAE remains 0.145227, R 0.40746 and clear-change
sign agreement 72.89%; scalar-change MAE remains 0.142069.

**Decision:** the protection correction holds across the full baseline matrix:
physical-roof changes fall from 6,800 in the old joined run to zero, and updated
voxel-roof changes are zero. It does not improve measured accuracy. Updated D
MAE is slightly higher than the previous joined version and remains above
legacy. Keep legacy as default and the option experimental. The inactive cases
establish fallback/regression behavior rather than new physics benefit.

This scope adds **80 native attempts** (79 field answers and one expected
exception). The historical ledger is now **237 field answers plus three expected
failed attempts**, totaling 240 attempts. Matrix workers took 776.4 s including
startup/capture; peak RSS was about 2.15 GiB with no memory cap. All deadlines
passed. These are matched historical fixed-work float32 comparisons, not new
tolerance-converged physical qualification or timing benchmarks. Earlier results,
baseline records and the stopped original campaign remain intact.

### Integrated validation: qualification

Decision: **pass**. Started native attempts: 6. Unmet checks: none. [Evidence](experiments/joint_screen/canyon_validation/aij-002/qualification/report.json). Physical execution remains a separate explicit stage.


### Integration C: protected private canyon extraction — 2026-11-06

**Decision: C engineering gates pass; retain legacy defaults and private model
status.** The isolated A/B/C checkout preserves the original join and union of
physical/voxel roof protection, complete legacy W initialization, conservative
fallback and exception-safe geometry reuse. The minimal bridge excludes the
other canopy/wake/stopping prototypes. Ordinary distributions omit the deliberate
failure hook.

Both full Python suites pass (**1,952 passed, 16 historical skips each**).
OpenMP/serial/sanitizer native suites pass **56/53/53** checks respectively;
six standalone helpers also pass separately instrumented ASan/UBSan checks.
The six-attempt lifecycle block passes **99 checks**, including exact archived
fields/stages/W and expected-failure cleanup. Four nonuniform roof answers and
the final D 0° legacy/joined pair reproduce the post-fix archives exactly.
Ordinary-path compatibility is exact for **429 cases per backend** against main,
B and each other. Focused default-path costs pass the existing guard. The sdist
contains all 192 checked files and its extracted Python source passes 24 smoke
tests with the frozen native module.

The D archive harness consumed two earlier legacy controls before its final
pair: first a wrong raw-helper descriptor, then a JSON/NumPy reporting mismatch.
All intermediate outputs are preserved; the final checker uses the frozen key,
saves hashes before comparison and passes. No native rule or numerical setting
was tuned to obtain parity. This engineering scope contains 14 named archive
verification attempts: 13 field answers and one expected exception; API suites,
compatibility cases and cost checks are separately recorded in the integration
index. They do not reopen or replenish any scientific campaign's attempt budget
or change the historical physical-screening ledger above.

The final D joined answer retains 34 qualified buildings and 59,840 changed
faces with zero physical/voxel roof or W violations. Its known accuracy regression
is preserved, so this adds no evidence for physical promotion. The complete new
37-condition/74-answer AIJ matrix and release requalification remain pending.
RSS was recorded without a research memory cap. The user's installed native
module is unchanged.

Implementation, test details, review patches and source/build hashes are indexed
in [the integration plan](docs/PHYSICS_EXPERIMENT_INTEGRATION_PLAN.md) and
[progress record](docs/data/physics-integration/progress.json). Local immutable
outputs are under `experiments/integration/attempt-004/`.


### Combined integration AIJ acceptance — 2026-11-06

**Pass: 74/74 fresh answers, 37/37 conditions reproduce the post-fix archive.**
Full fields, stresses, flags, initial W, canonical records/planes and contributor
stages are exact. An independent record-only check reproduces all 15 paired
quantities and shared coverage. Physical/voxel roof, complete W, sampling and
mass guards pass. Only D 0° activates (34 buildings, 59,840 changed faces); its
known +3.86% split-fibre MAE regression is unchanged. Legacy remains the default
and no physical promotion is earned. The 36 inactive conditions retain bitwise
legacy velocity/stress parity.

This adds 74 engineering comparison answers under a new immutable integration
scope, without replenishing any stopped physical campaign. All declared worker
deadlines pass; four native threads and one BLAS thread were used, with recorded
RSS and no research memory cap. Solver work and tolerances match the historical
fixed-work descriptors; no new convergence or speedup claim is made.

[Report](experiments/integration/attempt-005/aij/REPORT.md),
[acceptance](experiments/integration/attempt-005/acceptance.json) and
[paired-metric verification](experiments/integration/attempt-005/paired-metrics-verification.json)
preserve the results. Release requalification is the next separate engineering
gate, recorded in the [integration plan](docs/PHYSICS_EXPERIMENT_INTEGRATION_PLAN.md).


### Release requalification of the integrated source — 2026-11-06

**Pass for the existing supported solver policy.** Native identity
`660544978f520df395dbc0b29469ea98a82def3753309982f10e0497c64648a8`
is qualified in the isolated integration checkout after exact thread/backend
comparisons, all 24 frozen S7 workers, combined baselines, both full strict
Python suites, native/sanitizer source gates and actual installed-wheel checks.
Both qualified suites pass 1,952 tests with 16 historical skips. Final sdist/wheel
audits and 24 canyon/lifecycle checks pass again after header promotion. The
installed user package is unchanged.

The initial unpaired cost guard failed under unstable timings. A bounded,
three-round balanced comparison passes the unchanged wheel-to-main thresholds
in every category. An additional direct-build aggregate contrast remains flagged;
its two faster matched rounds and one large timing spike are retained alongside
the failed initial observations. The acceptance scope and review rationale are
explicit in [the cost review](experiments/integration/attempt-006/cost-final-assessment.json).
These observations establish no performance improvement claim.

The [integration plan](docs/PHYSICS_EXPERIMENT_INTEGRATION_PLAN.md) records the
full results, preserved artifact/setup failures, final hashes and review patches.
The candidate retains private canyon status, legacy defaults and the known D
accuracy regressions. No new physical model was qualified or stopped scientific
campaign reopened. No additional AIJ matrix answers were used by requalification;
its policy/API/runtime/cost checks are a separate engineering scope. Large ignored
artifacts still require durable archival before release; no merge or publication
has occurred.


### Qualified implementation committed to main — 2026-11-06

The tested A–D source is committed in six clean implementation changesets ending
at `c2ab9acb788972c71d455461e061c5f5f02a4aa2`; its full Git tree exactly matches the
release-qualified candidate. The accompanying documentation commitss preserve
this ledger, the literature/validation plans and the integration evidence index.
Excluded research sources are preserved in verified stash
`8a4a130a9b6db378b35a7e299a928c3368ad1a4a` (99 files, original base `6e205c0`).
Large fields, binaries, data and reports remain local. Committing the source
adds no new experiments, physical promotion or attempt allowance. The qualified
native identity remains `660544978f520df395dbc0b29469ea98a82def3753309982f10e0497c64648a8`.

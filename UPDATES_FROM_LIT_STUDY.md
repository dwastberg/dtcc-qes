# Short tests of improvements identified in the literature

Date: 2026-11-05. Status: proposed tests; none launched by writing this plan.

**First priority: test the published modified street-canyon model against measured array flow.** Use the other tests to decide whether each idea deserves development, not to build a combined model immediately. No OpenFOAM, Docker, new CFD reference simulations, or automatic resumption of E5a. Production defaults remain unchanged during screening.

The current evidence is summarized in [E1a](experiments/E1A_REPORT.md), [near/far attribution](experiments/E2_NEAR_FAR_REPORT.md), and [SE1](experiments/E2_SUPPORT_EXPOSURE_REPORT.md). SE1 remains rejected. Its failure does not test the modified canyon physics below. Preserve existing failed results and source-identity qualifications.

## Rules that keep the tests small and interpretable

- One physical change per candidate. Each candidate branches from the same frozen legacy parent; do not stack successful changes during these tests.
- Use existing experiment tools, canonical sampling and mass/flux diagnostics. Put each implemented test in `experiments/lit_<id>/`, with `experiments/run_lit_<id>.py` as its entry point. Share adapters in `experiments/tools/`.
- Freeze data, geometry, units, inflow, reference speed, masks, coefficients and metrics before running a candidate. Compute source fingerprints uncached for every worker. Never fit coefficients to Case E in this round.
- Four native threads, one BLAS thread, sequential workers. Small mechanisms: at most 60 s and 2 GiB per primary answer; city: D 20 s, E 60 s and 2 GiB. Stop on an overrun; keep its record. No automatic retry or domain reduction to obtain a pass.
- Use converged float64 for small mechanisms where affordable. A shortlisted fixed-work answer needs its own tighter same-model comparison: maximum probe-vector difference <=1e-4 Uref, or <=10% of the claimed improvement if stricter. Allow at most one additional numerical control per arm/configuration, capped at 180 s. Unresolved numerics means **inconclusive**, not physical rejection or success.
- Require finite fields, unchanged measurement coverage, impermeable solids, and the existing same-operator interior/top/flux guards. Preserve any parent boundary defect in the report. A relative guard failure rejects integration under that configuration; it does not disprove the underlying literature model.
- A suggested **exploration gate** for measured mean-flow mechanisms is >=10% lower normalized vector/profile RMSE overall, with no measured region >5% worse. Use all eligible predeclared points and report U, V, W separately. Exclude an unverified signed component; never infer its convention from whichever choice improves the model score. Improvement must exceed numerical uncertainty. These small-sample gates are engineering screens, not statistical proof or release criteria.
- Call an outcome **pursue**, **stop**, or **inconclusive**, and state its scope. Synthetic smoothness or invariance can establish implementation quality, never physical accuracy.
- Counts below are primary native solves; numerical controls are separate and bounded as above. Reuse an archived parent only when its complete relevant identity matches. No full-35 campaign, 1 m city campaign or three-repeat timing campaign during the first screens.

## Test sequence

| ID | Question | First budget | Depends on |
| --- | --- | --- | --- |
| L0 | Are the published reference datasets usable? | Data inspection only, <=1 h per dataset | Nothing |
| L1 | Does the modified canyon code implement the intended geometry? | Formula checks and <=4 small solves | L0 array metadata |
| L2 | Does canyon mixing improve measured array flow? | 2 configurations x 2 arms = 4 solves | L1 passes |
| L3 | Does the published wake envelope improve measured recovery? | 3 isolated shapes x 2 arms = 6 solves | Eligible isolated profiles |
| L4 | Is canopy-dependent tower cavity structure a missing mechanism? | 2 configurations, parent only = 2 solves | L0 tower reference |
| L5 | Do other diagnostic models differ materially on Case E? | Archived-output analysis; 0 new solves | L0 comparator metadata |
| L6 | Is geometry representation worth a cut-cell project? | Stored-field analysis; initially 0 solves | Existing grid archives |
| L7 | Does near-wall velocity reconstruction help independently? | Offline reconstruction; initially 0 solves | Eligible near-wall measurements |
| L8 | Does measured background turbulence improve turbulence output? | Offline stress analysis; initially 0 solves | Measured vector/stress data |
| L9 | Does building non-local mixing add useful spatial information? | 2 configurations x 2 arms = 4 solves | Native-path audit and eligible data |
| L10 | Is improved atmospheric inflow relevant to Case E? | Profile comparison only; 0 solves | Existing inflow measurements |
| L11 | Does one surviving mean-flow candidate warrant city expansion? | 4 E answers + 1 D answer per arm = 10 solves | Its mechanism gate passes |

Run L0 for the array and L1/L2 first. L5 can proceed using archived results independently. L3 and L4 are separate branches. Do not implement L6–L10 merely because they appear in this list.

## L0 — Check reference eligibility before building anything

Inspect three sources independently:

1. **EPA BROWN2000 array.** The [public archive](https://github.com/UtahEFD/QES-Public/blob/main/paperData/BROWN2000.zip) was downloaded and inspected during the literature study: raw U/V/W files, processed velocity/turbulence data and setup documentation are present. Verify coordinate frames, units, component locations, normalization and exact geometry. Identify complete first-canyon and downstream/recovery profiles. Do not assume the three component files share identical points.
2. **Tower/canopy measurements.** Inspect the [Hertwig 2019 data](https://zenodo.org/records/2563700) and metadata for isolated versus embedded versions of the same tower. Prefer the simpler [Mishra 2025 cluster dataset](https://doi.org/10.17605/OSF.IO/5X7WV) if its geometry is more completely reconstructable. Choose one dataset for the first test. Confirm which velocity components and heights are actually measured.
3. **URock/QUIC comparator archive.** Inspect [Zenodo 7681245](https://zenodo.org/records/7681245), including its version, Case E state/directions, geometry, inflow and sampling. The published Case E discussion covers the after-state for E and SSW; do not assume a full paired dataset exists.

**Deliverable:** one short eligibility table with hashes, exact configurations and missing information. Freeze the model/full-scale conversion and grid before scoring. Any geometric similarity scaling must apply to buildings, probes, roughness, inflow heights and domain together; preserve dimensionless velocities. Start array mechanisms with at least eight cells across a cube and check that all selected measurement heights can be sampled. **Stop that branch** if geometry, normalization or component conventions cannot be resolved within its inspection budget. Dataset availability alone does not establish eligibility. Reproduce the experiment's geometry instead of relabeling our existing synthetic mechanisms as matching references.

## L1 — Audit the existing modified canyon implementation

**Change:** none to physics. Compare the equations in Singh et al. (2008) with `StreetCanyonModified.cpp`. The native dispatch exists, but `parameterizations.py` and `model_inputs.cpp` reject street-canyon value 2; the prior public flag campaign did not test it.

**Small checks:** evaluate the model on a centered rectangular canyon, then translate and rotate that geometry. Check the canyon's own lateral center and bounds, support edges, positive fractional-power arguments, zero-width wedges and signed velocity continuity. The current code contains unfinished generalization notes, so source presence is not qualification.

**Native check:** one aligned and one oblique two-building fixture, each with legacy and modified canyon only: four solves. All other flags, inflow and projection settings stay fixed. Save before/after-canyon sections and final fields. Check formula-level rigid-transform equivalence tightly; compare native rotation only within documented voxelization error, not by demanding identical grids.

**Pursue:** equations and limiting cases agree, field guards pass, and the mixing layers occur in the intended locations. **Stop:** the implementation needs a general canyon-geometry redesign rather than a bounded correction. Record that as unfinished implementation, not failed physical evidence. Do not unlock the public flag merely to launch a city campaign.

## L2 — Test canyon mixing against measured profiles

**Change:** legacy canyon versus audited Singh modified canyon; everything else identical.

**Cases:** the EPA 7x11 array and the wide-building canyon used in [Singh et al. (2008)](https://doi.org/10.1007/s10652-008-9084-5), if the latter's numerical measurements can be obtained and checked. Start with the array pair; do not delay it waiting for the second dataset. An unavailable second geometry leaves transfer unassessed.

**Measure:** normalized signed profile/vector RMSE on all eligible canyon observations; separately assess canyon interior, roof shear layer, lateral edge, upstream approach and downstream recovery wherever observations exist. Record maximum resolved shear, negative-U extent and projection-induced changes as diagnostics. Use published parameters without a sweep.

**Pursue:** pass the common exploration gate and preserve approach/recovery accuracy. **Stop:** only gradients become smoother, total error does not improve, or genuine reverse flow is lost. If the array passes but the second geometry fails, stop generalization and report the restricted result. The EPA array helped develop this model; a pass is reproduction, not independent confirmation.

## L3 — Test lateral and vertical wake diffusion

**Change:** the [Singh et al. (2006) wake envelope](https://ams.confex.com/ams/pdfpapers/104607.pdf), retaining the same cavity law and other zones. First verify the printed equations against boundary/asymptotic limits; do not transcribe ambiguous PDF equations blindly. Preserve wake-core values during initialization and blend only the prescribed transition regions.

**Cases:** cube, wide prism and tall prism from the cited Snyder/Lawson experiment, if eligible numerical profiles are available. Published plots alone are insufficient for a 10% decision unless digitization uncertainty is explicitly bounded. AIJ A/B may be used as separately declared transfer geometries, not represented as the original experiment.

**Measure:** all eligible downstream U/W profiles, split into reverse-flow core and outer/roof transitions; deficit width, recovery and full-field changes. This envelope can spread a deficit rather than simply increase speed.

**Pursue:** common exploration gate, with no >5% reverse-core RMSE regression in any shape. **Stop:** better-looking transitions hide worse core velocities or broader excessive sheltering. The paper reports such tradeoffs and does not establish interacting-building performance. No city run on the strength of an isolated visual match.

## L4 — Diagnose tower/canopy dependence before proposing a new law

**Change:** none. Run the parent on one measured tower geometry in isolation and in its measured low-rise surroundings. Use the same experimental forcing for the matched comparison; retain any experiment-specific inflow difference rather than forcing artificial equality.

**Measure:** the change in reverse-flow depth, recirculation-center height, signed U/W profiles and wake recovery at identical physical coordinates. Estimate geometric/measurement uncertainty before evaluating the differences. Require at least three measured heights spanning the proposed structural change; otherwise the relevant feature is unassessed.

**Pursue model design:** QES fails an observed canopy-induced structural change, the discrepancy exceeds measurement/grid/numerical uncertainty, and the mismatch is visible in the signed profiles. **Stop this hypothesis:** QES captures that change or available observations cannot distinguish it.

If pursued, write one fixed canopy-dependent support rule, recovering the original isolated limit, before running it. Its first test repeats only these two configurations. Do not choose an amplitude from Case E or assume all canopies shorten wakes: [Hertwig et al. (2019)](https://doi.org/10.1007/s10546-019-00450-7) and [Mishra et al. (2025)](https://doi.org/10.1016/j.ijheatfluidflow.2025.109960) show that near-cavity structure and downstream recovery respond differently. Designing/running that revision is a separate follow-up, not an automatic extension of this diagnostic.

## L5 — Compare archived Case E predictions

**Change:** none. Compare dtcc-qes, QUIC-URB and URock for E-after E and SSW using the same experimental observations and common eligible receptors. Reconcile units, inflow, geometry and interpolation first. If a setup difference remains, show it explicitly and do not rank implementations as though inputs matched.

**Measure:** K MAE, signed bias, spatial correlation and per-receptor residuals, with tower-near and background locations fixed from geometry. Examine whether our known low-speed locations also appear in the other fields.

**Pursue an implementation-difference audit:** a comparator has >=10% lower MAE in both directions without >0.02 correlation loss, under adequately matched inputs, and an identifiable spatial discrepancy. Inspect incident reference velocities, canyon support and sheltered/backward zones one at a time. **Stop a wholesale port:** gains disappear after matching inputs, or both models share the failure. No intervention claim without both states. [URock method and evaluation](https://gmd.copernicus.org/articles/16/5703/2023/)

## L6 — Bound the value of cut-cell geometry

**Change:** none initially. Use existing 2/1/0.5 m results on their common directions and receptors. Freeze a geometry-sensitive stratum before looking at observation residuals: wall distance <4 m, recorded 2 m-grid local K span >0.15, or a changed open/closed passage connecting the receptor's local street between resolutions. Report these three categories separately as well as their union; do not choose a more favorable threshold afterward.

**Measure:** how much baseline absolute error lies in geometry-sensitive locations, and whether refinement consistently moves those predictions toward observations. Compute an explicitly optimistic bound: remove every error in that fixed stratum while leaving all other points unchanged. This is a prioritization bound, not a predicted gain.

**Pursue a small cut-cell feasibility task:** the bound exceeds 10% of total MAE and the spatial diagnosis supports a geometry error. Otherwise deprioritize it for Case E accuracy. Even a large bound does not justify a rewrite: first demonstrate one oblique-wall/narrow-gap benchmark with consistent fractional areas, projection and sampling. The supported pipeline currently fixes stair-step geometry; a source-file presence check is not a usable cut-cell arm.

The [2025 cut-cell paper](https://doi.org/10.1029/2024MS004494) supports improved near-solid grid behavior, but disabled building zones in its urban geometry comparison. Do not borrow that result as validation of interacting wakes.

## L7 — Separate near-wall reconstruction from cut-cell geometry

**Change:** an offline, wall-distance-aware logarithmic reconstruction of tangential speed at measured receptors, using existing solved fields. Keep geometry and the solved field fixed. Use independently specified roughness and an eligible wall-normal measured profile, not an arbitrary correction at all Case E points.

**Measure:** tangential profile RMSE across all measured distances, including farther points; retain normal components and raw model values separately. First verify exact reconstruction of a manufactured log profile.

**Pursue:** >=10% lower measured near-wall RMSE with no >5% deterioration farther from the wall. **Stop:** benefit depends on fitting roughness, moving receptors or extrapolating the log law through separated/reversing flow. This tests a sampling/reconstruction idea only. An iterative correction of the solved velocity field, as discussed in the [2025 paper](https://doi.org/10.1029/2024MS004494), would require a separate conservation-qualified experiment.

## L8 — Test measured background turbulence without changing the mean wind

**Change:** add a covariance contribution specified from measured upstream turbulence, with units and normalization preserved. Compare against the same baseline stress arrays offline. Use D's paired vector/turbulence observations first and the eligible EPA array as a second configuration. If upstream component variances are unavailable, do not infer them from the target observations.

**Measure:** stress components, covariance validity, TKE and RMS-speed proxy error separately. The native `backgroundMixing` value is squared when added to diagonal stresses; do not confuse a velocity standard deviation with the paper's variance coefficient. Reconcile the native TKE definition with half the stress trace before computing an observation proxy.

**Pursue:** >=10% lower turbulence error in both configurations, spatial TKE correlation improved by >=0.05 (or preserved within 0.02 if the parent already exceeds 0.8), no >5% worsening of the paired scalar proxy where measured, and no new invalid covariance. **Stop:** only the overall turbulence level improves while its spatial pattern remains wrong, or only scalar scores improve. Insufficient spatial variation to assess correlation leaves that gate inconclusive. Never copy the demonstration's dimensional constant as a universal setting. [QES-Plume turbulence discussion](https://gmd.copernicus.org/articles/16/5729/2023/)

## L9 — Test building non-local mixing separately

**Change:** enable only the existing building non-local turbulence path; retain zero added background mixing and exactly the same mean wind. First audit its rotated-coordinate, geometry and state-reuse assumptions: this path is not qualified by the supported turbulence API.

**Cases:** D 0 degrees and the EPA array, using all eligible measured stresses. Two arms per configuration, four solves. Do not combine with L8 in this screen or assume the native building model is identical to the paper's constant background term.

**Pursue:** common 10% error-improvement gate applied to measured stresses, with no >5% regional regression and valid covariance. **Stop:** stronger artificial shear-edge peaks, worse spatial agreement or geometry-dependent numerical failures. Neither L8 nor L9 may claim a mean-wind improvement: the current turbulence calculation is downstream of the wind solve.

## L10 — Close or retain the atmospheric-inflow idea cheaply

**Change:** none. Compare the currently imposed measured Case E inflow with the original measured profile at every supplied height. Check vector direction, interpolation and normalization; reuse the existing inflow audit if identities match.

**Pursue:** a reproducible adapter discrepancy exceeds documented interpolation/measurement uncertainty. Fix that discrepancy separately before any physical-model comparison. **Otherwise stop this branch for Case E.** The [2024 QUIC boundary-layer scheme](https://doi.org/10.1007/s10546-024-00860-2) addresses atmospheric shear, veer and stability; replacing measured tunnel inflow with it is not an accuracy hypothesis for this case. Retain it only as a future field-application topic.

## L11 — One small city screen for each surviving mean-flow candidate

Only L2, L3 or a separately specified L4 follow-up may enter directly. A geometry or observation-method proposal needs its own integrated qualification first.

**Cases:** E and SSW, before and after construction, plus D 0 degrees: five configurations per arm. Use the original 2 m settings and all canonical receptors, with exact matched legacy parents. These directions are development data, not holdouts. Run only one surviving candidate at a time.

**Pursue the existing eleven-condition screen:** intervention MAE improves >=10%; neither E state's MAE nor D vector RMSE worsens >5%; each E state's spatial correlation and each increase/decrease recall lose <=0.02. Retain the original clear-change definition, all genuine decreases and the covered portion of the frozen spurious-decrease stratum. Report denominators; an empty or inadequate subgroup is unassessed, never a pass. Numerical, coverage and conservation gates must also pass.

**Stop city expansion:** any required criterion fails or numerical uncertainty obscures the effect. Do not retune on these directions. A mechanism success with a city failure may remain useful for its demonstrated geometry, but is not a Case E improvement.

These thresholds decide whether further investigation is worth its cost. They do not replace the stronger full-matrix accuracy, application, independent-transfer, 1 m and performance requirements in [the governing experiment plan](QES_PHYSICS_MODEL_EXPERIMENTS.md). This document does not silently reopen rejected E1/SE1 families or spend an existing campaign's remaining model-revision budget.

## Output and stopping discipline

Each test produces a one-page verdict: exact hypothesis, changed code/formula, reference identity, primary scores, failed guards, elapsed time/RSS, and one diagnostic plot where useful. Preserve all attempts. Record implementation effort separately from solver cost.

For the first execution batch, cap work at **L0 array eligibility, L1 and L2's array pair**: at most six primary native solves, plus necessary bounded numerical controls. Review that evidence before extending to another mechanism or city directions. Run L5's archived comparison separately if its metadata is sufficient. Leave all other branches queued rather than launching the entire table.

If no isolated candidate passes, report that result and stop. Combine models only after separate benefits are established; then a later 2x2 experiment must distinguish their individual effects from their interaction.

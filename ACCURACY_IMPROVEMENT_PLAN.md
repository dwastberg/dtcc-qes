# Plan: test and fix the three accuracy findings

**Date:** 2026-11-15, revision 4 (preparation and part T carried out; see section 0). Revision 3: (end-to-end plan review: decisive checks first, resolvable gates, shrinkage comparator, shelter diagnostic; decisions closed with the user the same day: part S added, AIJ Case C added as a prerequisite delivered by separate work, M before D, D on literature constants). **Base:** `main` `4c7a8da` (0.1.0b5). **Source:** [END_TO_END_REVIEW.md](END_TO_END_REVIEW.md), section 5. The six physics fixes are implemented; the accuracy diagnostics and model proposals below are not.

## 0. Status after part T (2026-11-15)

Done: I0, I2, I3, I4 and T1–T4. Results: [validation/ACCURACY_DIAGNOSTICS.md](validation/ACCURACY_DIAGNOSTICS.md). No model code was changed. The plan is stopped at the review gate after part T.

| Step | Outcome |
|---|---|
| I0 | Scorer, tower contract and manifests in `experiments/accuracy/`; 184 runs archived on two grids. A comparator was added: shrinkage at the candidate's mean (below). |
| I3 shelter check | Fails: +0.176 [0.139, 0.210] before construction within 30 m. D is paused. |
| I3 vector smoothing | A mean-field target exists on `wake=2` only. |
| I4 | Case C passes the entry check. No probe lies in the central plot; no far field; no measured inflow k. Grids are 1 m and 2 m, not 1 m and finer. |
| T1 | K1 supported for `wake=2`; under the `wake=3` scalar the contrast is too low except in E before. Filter gains are level changes. |
| T2 | K2 supported. Cases A and B disagree on the sign of the cavity-strength error, so the optional cavity step of section 7 is dropped. |
| T3 | Locality supported. A tower correction is needed on three cases (E, D, C). |
| T4 | The excess follows distance behind the nearest building, streets along the wind and open areas. It matches S-b, speaks against S-a and does not indicate S-c. |

**Changes made to the protocol during the work** (before any candidate was scored):

- **I0, second shrinkage comparator.** K̄_candidate + s·(K − K̄): the parent shrunk to the candidate's variance and moved to the candidate's mean. A candidate that lowers the level beats plain shrinkage through the level alone; T1 showed that this accounts for every filter gain in E before. Gates that say "beyond shrinkage" use both comparators.
- **I0, synthetic layouts** must put every wall on a cell face (I2).
- **T2 sign convention.** Shortfall is measured minus simulated; a positive correlation with blockage supports K2.

**Four results conflicted with decisions fixed in sections 2 to 6.**

| # | Conflict | Affected text | Proposed change |
|---|---|---|---|
| 1 | S-b cannot be developed on Case C: points 1–2 H behind a block are already too slow there, and E before needs longer wakes. | A5 row S, S3 | Develop S on E before, district probes (≥ 60 m from the tower); hold out the 22 site probes and E after as the test; Case C becomes do-no-harm. |
| 2 | S cannot pass "Case D does not worsen": every Case D probe is near the tower and already too low. | Gate for S | Report Case D as D's target, as the gate already does for the after-state level in E. Gate S and D jointly on Case D. |
| 3 | The largest direction step is an angle switch of the sidewall and upwind-cavity zones. A spatial blend through I1 cannot remove it. | Part M, continuity path | Replace the blend at source by a native angle fade of those two zones. Bar: maximum plane RMS ≤ 0.016, largest probe step ≤ 0.035, median ≤ 0.0065. |
| 4 | M has no score target on `wake=3`, and on `wake=2` only what `wake=3` already delivers. | Part M, full gate | Close the mean-field path of M. |

**Decided 2026-11-15:** all four proposed changes are accepted, point 3 as a native weight that fades with angle. A5, part S, part M and section 8 are rewritten accordingly.

**After parts M and S (2026-11-15).** Results: [validation/ACCURACY_RESULTS.md](validation/ACCURACY_RESULTS.md). Both were prototyped as environment switches on the branch `exp/accuracy-prototypes` (worktree `/private/tmp/dtcc-qes-accuracy`, uncommitted; patch in `validation/accuracy_evidence/`).

| Part | Outcome | Open |
|---|---|---|
| M, angle fade, half-width 2.5° | **Passes** on the plane conditions (decided 2026-11-15). Largest plane step 0.032 → 0.015; holds on a turned building and at 1 m; no harm on any case. The probe step stays at 0.069: a spatial edge of the near-wake cavity, reported. | Native option (M5) with the release batch of section 7. |
| S, root sum of squares of the deficits | **Accepted as the parent for developing D** (decided 2026-11-15); S and D are judged together. Before-state error within 30 m +0.176 → +0.089 [0.049, 0.125]; district +0.104 → +0.009. Cost only where a tall building stands (E after within 30 m, Case D, Case C 2H). | No release of S without D. |
| D, downwash zone on Reiter (2010) constants | Built and tested once on the S parent. Scalar: E change within 30 m +0.230 (measured +0.262), E after R 0.559 → 0.672, Case D bias −0.120 → −0.014, Case C 1H → 2H +0.171 (measured +0.194). **Fails the common vector gate at the Case D split fibre** (vector RMSE +0.126, sign errors 5 → 10 of 29). The one revision (speed only, direction kept) restores the signs, not the vector error, and is worse on scalars. | The split between mean flow and turbulence (γ = 0.8, decided 2026-11-15) keeps the scalar results and lowers the vector excess to +0.086; the condition still fails and the sign errors stay at 10. To be decided. |

**Deviations recorded:**

- **S candidate.** T4 pointed to S-b. Its constant (the reach cut) proved inert on the development set, as `FABEL_WAKE_INVESTIGATION.md` 4.6 had already found, and the signature used against S-a was mis-specified. The development screen therefore covered the reach cut, the spread and the root sum of squares; the selection rule picked the last, the second form of S-a.
- **S gate.** The shrinkage comparator at the candidate's mean is reported, not gated: it removes the level change that S exists to make. Case C 2H is reported with Case D, as a tower state.
- **I1** was not built: both prototypes are native switches.

---

**Scope.** The three accuracy findings of the review, and its two proposals:

| Id | Finding or proposal | Review reference |
|---|---|---|
| K1 | The simulated field has about three times too much contrast | X1, X2 |
| K2 | The error follows upwind blockage: cavities and near wakes are too slow | X1 |
| K3 | The missed tower effect is local to about half a tower height | X3 |
| M | A mixing step on the initial field (closed after part T; continuity by an angle fade instead) | A2 |
| D | A tall-building downwash zone | A1 |
| S | Shelter in the `wake=3` parent, if the D prerequisite fails | X4, finding 9 |

K1–K3 are hypotheses to reassess on the corrected build. Each gets a diagnostic verdict (part T), and each proposal gets a prototype, a gate, and only then a native implementation (parts S, M and D). AIJ Case C (`validation/AIJ_C`) is a development case (A6); its setup is separate work and is assumed in place before this plan starts (I4). The scope and experimental-release policy are unchanged.

**Relation to the bug-fix plan.** [PHYSICS_BUG_FIX_PLAN.md](PHYSICS_BUG_FIX_PLAN.md) is implemented in 0.1.0b5. All decisions below use that corrected parent, not the old X1–X4 fields. Historical results remain evidence for the hypotheses, not current acceptance baselines.

---

## 1. Findings that shape the plan

**1. The historical tower table points most strongly to an error in the "before" state.**
X4 (`experiments/e2e_review/x4.py`, 2 m, pre-fix 0.1.0b4) reported:

| Distance from the tower | Measured K, before → after | `wake=2`, vector | `wake=3`, vector | `wake=3`, scalar |
|---|---|---|---|---|
| 0–15 m | 0.32 → 0.64 | 0.63 → 0.63 | 0.48 → 0.42 | 0.55 → 0.58 |
| 15–30 m | 0.34 → 0.56 | 0.55 → 0.54 | 0.40 → 0.37 | 0.49 → 0.51 |
| 30–60 m | 0.33 → 0.35 | 0.46 → 0.44 | 0.32 → 0.28 | 0.42 → 0.42 |
| 60–120 m | 0.32 → 0.36 | 0.46 → 0.44 | 0.33 → 0.29 | 0.42 → 0.41 |
| Beyond 120 m | 0.35 → 0.39 | 0.55 → 0.53 | 0.39 → 0.36 | 0.47 → 0.45 |

- Under the chosen **scalar** comparison, `wake=3` after construction is already within 0.10 of measurement in both near-tower bands (0.58 versus 0.64; 0.51 versus 0.56). Its before values, 0.55 and 0.49, are too high against 0.32 and 0.34. The former argument for D incorrectly used the lower vector values as scalar baselines.
- Agreement of distance-bin averages does not establish a momentum-transport mechanism. Downward transport of faster approach air is a hypothesis to test; these data alone do not establish that a tower cannot produce local speeds above the approach flow.
- **Consequence:** D first requires acceptable scalar shelter in the corrected parent. Only then assess whether a near-tower correction remains necessary. If shelter fails, D pauses and part S takes up the shelter error from a fixed candidate list; D resumes on the parent that passes S.

**2. The instrument and model quantities must remain separate.** Case D thermistors and Case E measure scalar speeds; A/B and the Case D split-fibre data constrain the mean vector. The model's √(|u|² + 2k) is an RMS-based scalar proxy, not an exact thermistor response. A scalar improvement alone cannot establish that the mean flow is correct. The scorer must distinguish `K` (mean-vector magnitude), `K_scalar` (QES-Turb k), `K_scalar_wake` (wake k with measured inflow k), and `K_scalar_wake_rule` (wake k with the 5.5 u*² rule); see [comparison definitions](validation/aij/compare.py) and [wake documentation](docs/spreading-wake.md).

**3. A private writable Python hook is still needed.** Native stage/building observers exist, but the public Python runner does not expose initial-field mutation. The existing experimental Python projector also needs a geometry export. I1 supplies a single agreed insertion point shared by prototypes and native implementations.

**4. Mixing and scalar-speed smoothing are different hypotheses.** Historical X2 improved Case D q from 0.23 to 0.34 with 8 m speed smoothing, while vector smoothing gave 0.15. Adding the proposed sub-filter variance to the filtered mean gives RMS speed, not smoothed speed. Converting spatial variation to temporal turbulence is an additional closure assumption; it is neither compulsory nor established by X2.

**5. The evidence base is narrow.** K3 rests on 22 probes within 30 m of one tower, sampled over multiple directions. A/B are isolated buildings. AIJ Cases A, B, D and E have already been inspected, including during bug-fix selection, so none is an untouched hold-out. Case C has not been run or scored; it enters as a declared development case, not as a hold-out. A5 limits further selection on D/E but does not erase that history.

**6. Earlier work to build on, and not to repeat:**
- Canopy columns (E1a, E1b) improved the level and damaged the pattern; that family remains closed.
- A tall-building zone with literature constants was listed as F08 in `CLAUDE_WIND_EXPERIMENTS.md`; no result was found for it.
- `wake=3` already has shelter and wake turbulence. Its default switch remains subject to C4 in `WAKE3_COMFORT_DEFAULT_PLAN.md`.

**7. The historical X1 numbers already bound K1.** From the X1 variances, the SD ratio r = σ_sim/σ_meas was 1.85 (E before), 1.27 (E after) and 1.10 (D); with R = 0.51, 0.46 and 0.43 these reproduce the slopes 0.28, 0.36 and 0.39 through b = R/r. "Three times" is the variance ratio of one case (3.4; the others are 1.6 and 1.2). In Case D the low slope is almost entirely weak correlation. These ratios compare the default mean-vector K with thermistor speeds, so they also contain the instrument mismatch of finding 2. **Consequence:** expect T1 to support excess amplitude in E before at most, and do not read the smoothing gains in Case D as an amplitude correction.

**8. Smoothing gains are partly regression to the mean.** A predictor with R ≈ 0.5 gains q and MAE from any reduction of its variance toward R·σ_meas, whether or not the removed variation was wrong. X2's gains therefore do not by themselves support a mixing mechanism. A candidate has to beat a plain shrinkage of the parent with the same variance (I0, gate for M).

**9. The historical before-state excess is district-wide, with an extra error at the tower site.** In the X4 table the `wake=3` scalar before values are 0.42–0.47 beyond 30 m against 0.32–0.35 measured, and 0.49–0.55 within 30 m of the future tower against 0.32–0.34. The first is a level error over the whole fabric (inflow, roughness or accumulated shelter); the second is specific to the open plot. They need separate diagnostics (T4). The six fixes do not change the `wake=3` spreading-wake path, so the D prerequisite is likely to fail again on the corrected build; I3 checks this first.

### 1.1 What the recent fixes change

Checked against commits `be78a1c` through `4c7a8da`, the current implementation, [release results](validation/PHYSICS_BUG_FIX_RESULTS.md), and [changelog](CHANGELOG.md).

| Completed change | Consequence for this plan |
|---|---|
| F1: corrected upwind cavity angles (`be78a1c`) | Recompute cavity diagnostics and symmetry baselines. Other parameterizations still have mirror error; distinguish the candidate's error from the parent's. |
| F2: tall wakes pass low obstacles (`acc7a50`) | Recompute `wake=2` blockage and tower comparisons. This fix is not a change to the `wake=3` spreading-wake path. |
| F3: frozen incident wind; V1 selected (`0b297b9`) | Reuse captured incident vectors/directions. There is no remaining reference-direction decision. Later canyon/sidewall/roof strengths still use local velocities; freezing direction did not replace them with approach-speed magnitudes. |
| F4: half-cell façade simplification (`2b3de21`) | Use current prepared geometry, preserving original solid masks. At 1 m versus 2 m the parameterization rings can change as well as the discretization; record that in M/D grid checks. |
| F5: spectral stress scaling (`aab96e8`) | Use current QES-Turb scalar/covariance outputs and actual cap flags. This does not directly change the separate wake-k closure or the mean wind. |
| F6: shifted-log gradients in the first two ground layers (`165ad02`) | Rebaseline QES-Turb k and its scalar proxy at measurement height. Profile roughness is retained separately; roof gradients and the κd mixing length are unchanged. Do not attribute these changes to wake k. |
| Release/archives (`4c7a8da`) | Start now from 0.1.0b5. Reuse matching immutable validation records and manifests; identify turbulence numerics v3. The build is intentionally unqualified for `pedestrian-v1`; use ordinary `Solver()` for the experiments. |

The release campaign completed 74/74 runs at 2 m and 1 m. Its all-direction tower diagnostic reports measured mean ΔK = +0.261607 versus simulated −0.002496 within 30 m (352 probe-direction pairs). **That is the default mean-vector comparison**, as implemented in `validation/physics_tower_effect.py`; it is not a post-fix `wake=3` scalar X4 table. The missing default tower response persists, but the D prerequisite still needs to be measured.

The release also records a one-hit loss at a Case D split-fibre probe at 1 m: q fell from 10/33 to 9/33 for a roughly 0.0032 change in K. Therefore report individual hit transitions and continuous errors alongside q; a 0.02 q tolerance is not a measurement-uncertainty estimate.

---

## 2. Decisions and working recommendations

**A1. Start from the completed fixes.** Use `main` `4c7a8da` (0.1.0b5), with the installed native identity checked before running. There is no wait for F1–F4 and no need for a separate bug-fix branch. Reuse archived runs only when settings, quantities, probe matching and native provenance agree; rerun missing diagnostics and `wake=3` baselines.

**A2. Parent for D: `wake=3`, conditional on shelter.** It provides an explicit deficit and wake-k field. This is a working choice, not a conclusion that only this model can represent shelter. If T3 shows a broader near-building defect, reconsider the parent at the diagnostic review. Shelter changes are limited to part S's candidate list. Passing D does not itself authorize making `wake=3` the default.

**A3. Two targets, kept separate.** Score signed measured velocity components and vector error on A/B and D split fibre; score the scalar proxy on D/E thermistors. Primary `wake=3` scalar gates use `K_scalar_wake_rule`, matching the public default inflow-k rule. Measured-inflow `K_scalar_wake` is a separately labelled sensitivity, never substituted to pass a gate. For `wake=2`, use QES-Turb `K_scalar` with fixed turbulence settings. Do not add QES-Turb k and wake k together. Candidate and parent always use the same quantity and inflow-k convention.

**A4. One insertion point for both prototypes and production.** After all building parameterizations and before the projection, apply M if enabled, then D. M softens the existing zone edges; D is written last and is not diffused, so constants set without M stay valid in the combined run. Reapply impermeable/solid-face constraints after each mutation. Nothing overwrites D. This replaces the old D6 placement before cavities, which was inconsistent with I1. D explicitly protects existing near-wake cavity mean velocities using face masks, rather than relying on subsequent cavity writes.

**A5. Development and transfer cases are declared per part; freeze before transfer scoring.**

| Part | Develops on | Transfer check, scored once after freezing | Do-no-harm |
|---|---|---|---|
| S | Case E before, the 43 probes at least 60 m from the tower site; synthetic layouts | Case E before, the 22 probes within 30 m of the site; Case E after | A/B; Case C. Case D is reported, and gated jointly with D |
| M | The 1° direction sweep (one building) | Do-no-harm only: A/B, C, D, E | – |
| D | Case C, state 2H and its paired change from 1H; synthetic layouts | Case E before and after; Case D | A/B (inactive, bit-identical) |

- Part T may inspect corrected-parent data of every case to diagnose the existing hypotheses. Record this prior use. Synthetic layouts supply invariance and physical checks, not measured accuracy targets.
- Select all constants, variants, closure choices and masks on the development column only. Then freeze the candidate and run the transfer column once. Do not screen candidates on a transfer case.
- Case D is a transfer case for D, and for S only jointly with D: every Case D probe lies within 60 m of its tower. Say so wherever a Case D score is reported.
- The 15 Case E probes between 30 and 60 m from the site are in neither S set; they are reported.
- At most one revision per part. If informed by a failed transfer gate, label it further development on those cases, record what changed, and do not claim an independent test. New unseen towers remain required before any default change (section 7).

**A6. AIJ Case C is a development case of this plan; its setup is not.** The case is being set up in separate work and is a prerequisite for starting. `validation/AIJ_C/CaseC(City_blocks).xls` holds a 3 × 3 block array whose central block is absent (0H), equal to its neighbours (1H) or twice as tall (2H), at 0°, 22.5° and 45°, with a velocity ratio (speed over the inflow speed at the same height) at about 120 points at z = 0.02 m model scale. It supplies what A/B and E lack: an empty plot inside a fabric (shelter), and a height-ratio step in an array (tower effect), each with a paired change. It has one height ratio above 1, so it cannot identify D's eligibility ramp.

**A7. D uses literature constants and is inactive around an isolated building.** An empty neighbourhood gives weight 0, so A/B are bit-identical controls. Constants start from Wise/Gandemer; Case C 2H may adjust only those it identifies (D3).

**A8. The calibrated linear map stays a reference row** (I0). If it still transfers on the corrected build, record that and propose the calibrated output separately.

---

## 3. Preparation

**I0. Baseline and scoring protocol.**
- Freeze `experiments/accuracy/score.py`, building on X1–X4 and the current archive/comparison tools. Record commit, native identity, turbulence version, options, grid, sampling, inflow-k source and common valid probe IDs/directions. Keep the pre-fix records explicitly historical.
- Report q, FAC2, R, ρ, FB and MAE by case and quantity; signed-component MAE and normalized vector RMSE for all measured components; reverse-flow sign/magnitude and reattachment location where measurements support them.
- Report contrast as SD ratio r = σ_sim/σ_meas, variance ratio r², correlation R, and regression slope b separately. Since b = R/r for measured-on-simulated regression with an intercept, slope alone is not amplitude evidence. Use the same matched samples for each statistic.
- Report blockage correlations, residuals by zone/distance, the absolute tower table, paired ΔK and directional strata. Cell flags describe final zone labels, not complete write provenance; use stage/building observers when attributing overlaps or source-building length scales.
- Report counts and 95% uncertainty intervals using resampling of spatial probe groups and direction groups, with grouping and seed frozen before candidate scoring. Do not count repeated directions at the same probe as independent measurements. With too few groups, mark inference inconclusive. Show continuous errors and hit transitions alongside q.
- Compare candidate and parent through **paired differences** on the same resampled groups (candidate minus parent, per metric). Intervals of the two scores taken separately are too wide to resolve the gates and are reported only as context.
- **Small samples.** Where one hit exceeds the tolerance (Case D split fibre: 33 probes, one hit = 0.030), state the q condition in hits (at most one hit lost) and decide on the continuous metrics. A 0.02 q tolerance is not applied to such datasets.
- **Reference rows in every score table**, per case and quantity: a null model (constant K at the case mean of the simulation's inflow-profile value); the in-sample linear map a + b·K as the ceiling of any level correction; the same map fitted on the other cases (leave one case out); and a **matched-variance shrinkage** of the parent, K̄ + s·(K − K̄), with s chosen so that its variance equals the candidate's. The last row is the comparator of finding 8.
- **Mean-speed proxy, report only.** √(|U|² + 2k) is an RMS speed. Also report the mean speed of an isotropic Gaussian vector with the same mean m = |U| and σ² = 2k/3: σ√(2/π)·exp(−m²/2σ²) + (m + σ²/m)·erf(m/(σ√2)), with the limit 2σ√(2/π) at m = 0. It is up to 8% lower where turbulence dominates. It is a labelled sensitivity for each scalar quantity and is not substituted to pass a gate.
- Archive corrected `wake=2` and `wake=3` baselines at 2 m, including Case C (I4); use matching 1 m records for robustness. The existing release archives are a starting point, not a substitute for missing wake-specific fields or signed components.
- Encode the M/D gates before fitting. Undefined scores, missing required data or unresolved measurement uncertainty do not silently pass.

**Tower scoring contract.** Distance is horizontal distance to the after-state tower footprint, used for both states. Bins are [0,15), [15,30), [30,60), [60,120) and [120,∞) m; “within 30 m” is [0,30). Match before/after by probe ID and direction, using a common finite mask for measurements, parent and candidate. Compute each probe's equal-weight mean over common directions, then the equal-weight mean over probes; compute ΔK from paired differences. Report counts and per-direction values. Do not gate against rounded historical table entries.

The gating bin is [0,30) m (22 probes historically). The [0,15) m bin has 8 probes and [15,30) m has 14; they are reported with intervals but a gate on either alone is decided only if its grouped interval is narrower than the tolerance. Also report every ΔK relative to the mean ΔK beyond 60 m: X3 found a uniform rise of +0.02 to +0.05 there that may be a normalisation difference between the two tunnel runs.

For directional strata, use the after-tower centroid and the inflow direction at the measurement height. Let a be the signed along-flow coordinate and c the absolute cross-flow coordinate: upwind if a < −c, downwind if a > c, beside otherwise. These disjoint sectors replace the overlapping windows in the old tower diagnostic. Publish historical-window results only as a labelled reproduction, not interchangeable gate values.

**Common vector gate.** On each measured vector dataset, magnitude q and R may fall by at most 0.02 (q by at most one hit on small samples, as defined in I0). For each available signed component, normalized MAE may increase by at most 0.02; normalized vector RMSE may increase by at most 0.02. Normalize with the case's documented U_ref and include vertical velocity where measured (A/B include U and W); do not invent missing components. Check reverse-flow signs separately: no new sign error where measurement uncertainty excludes zero. For reattachment, the candidate's absolute error against measurement must not exceed the parent's error plus the frozen measurement-location uncertainty. If uncertainty is undocumented, report the bracketing measurement interval; insufficient coverage makes this check inconclusive. Improvement is not limited to 10% of the parent's location.

**I1. Initial-field hook (experiment branch `exp/accuracy-prototypes`).**
- Add an optional private Python callable after `applyParametrizations` and before RHS assembly in `WindRunner::solve`. Expose writable u0/v0/w0 and required wake fields, with read-only geometry, cell/face masks, incident references and provenance. Acquire the GIL for the callback and keep views valid only for its duration.
- Both prototypes and later native versions use A4's exact order and boundary restoration. Protect cavity faces explicitly for D. Reuse current stage/building observers for diagnostics; do not change frozen incident references.
- Check bit-identical no-op results; prescribed changes to the initial field and preserved boundary/cavity faces; post-projection divergence. Pressure correction is nonlocal, so a local mutation need not have a local final-field effect.
- The hook does not ship. Compare native and prototype initial fields, wake quantities and solved outputs on identical inputs before repeating their gates.

**I3. Two decisive checks, before part T and before I1.** Both use only the corrected build and I0's scorer, and take hours.
- **Shelter check (decides D).** Run `wake=3` on Case E before and after and produce the scalar tower table under the scoring contract. If the before-state error in [0,30) m exceeds 0.10, D is paused now; T3 and T4 document why, part S follows, and D prototype work waits for a parent that passes S.
- **Vector-smoothing check (decides M's mean-field target).** Smooth the solved vector field with fluid-restricted Gaussians of 2, 4 and 8 m and score the signed components on A/B and Case D split fibre against the unsmoothed parent, for `wake=2` and `wake=3`. This is a screen, not the M operation (M acts before the projection). If no length improves normalized vector RMSE beyond the paired interval, M has no mean-field score target and continues on the continuity target only (part M).
- Record both in `validation/ACCURACY_DIAGNOSTICS.md`. A negative result removes the dependent work from section 8; it is a valid end of that branch.

**I4. AIJ Case C: entry check and baselines.** The case setup (geometry, inflow, sampling, comparison) is delivered by separate work before this plan starts. This step only confirms what the plan relies on and archives the parents.
- Confirm from that work's record: the three states 0H, 1H and 2H at 0°, 22.5° and 45°; the instrument (scalar or vector), so that the matching model quantity is scored under A3; and that the model's K uses the published reference, the inflow speed at the same height.
- Add the Case C scoring contract to I0: distance to the central block footprint; paired changes 0H → 1H and 1H → 2H by point and direction, reported also relative to the mean change at the outermost points.
- Run and archive the `wake=2` and `wake=3` parents on the corrected build with I0's scorer and manifests, at the case's standard grid and one finer grid. Reuse the setup work's runs only where settings, quantities and native provenance agree (A1).
- Record what the setup work already inspected or tuned on Case C. Any model setting chosen there by looking at Case C scores counts as prior development use, in the sense of A5.
- If the entry check fails, stop and return the gap to the setup work; do not repair the case inside this plan.

**I2. Synthetic layouts** (`experiments/accuracy/layouts.py`): an isolated cube and 1:1:3 tower; 5 × 5 arrays of 10 m blocks at plan-area densities 0.25 and 0.44, with and without a central 60 m tower; two cubes in tandem at 1, 2 and 4 H. Reuse the corrected geometry and native symmetry helpers.

---

## 4. Part T: test the three findings

No model changes. Each result is **supported**, **unsupported**, or **inconclusive**, with instrument, uncertainty and case dependence stated. Diagnostic thresholds are evidence rules, not proof of a causal mechanism.

### T1. Contrast (K1)

1. On corrected A/B and D split-fibre data, compute SD/variance ratios, R and slope for matched vector quantities. Separately repeat on D/E using each explicitly named scalar proxy.
2. Split residuals and variance by zone/provenance. On the 2 m field, measure variance removed by 4, 8, 16 and 32 m filters; compare at measured probe spacing only where coverage permits.
3. Support excess amplitude where the grouped interval for r lies above 1; test the specific “three times” claim against the measured r rather than inferring it from b. An interval entirely at or below 1 does not support excess amplitude in that comparison; overlap is inconclusive. Report weak spatial correlation separately.
4. A scalar/vector difference can support an instrument-mismatch explanation but does not prove it. No slope-above-0.7 rule and no automatic authorization of a scalar-only correction remain.
5. For each filter length in item 2, compare the smoothed field's q, MAE and R with the matched-variance shrinkage row of I0. A gain that shrinkage reproduces is regression to the mean (finding 8) and does not support a mixing target; a gain in R, or beyond shrinkage, does.

**Output:** whether excess vector amplitude exists, its zones/scales, and whether M has a supported mean-field target. Diagnostics on any case can motivate the hypothesis; filter length and variant selection remain on M's development column of A5.

### T2. Blockage (K2)

1. Relate signed/vector residuals to upwind blockage on D split fibre and A/B wake points. Check reverse-flow magnitude and measured reattachment; the old Case A −0.25 U_H versus −0.14 is a historical result to remeasure.
2. Split thermistor residuals by zone and downstream distance/H. Repeat with the corrected `wake=3` scalar proxy and report grouped correlation intervals.
3. A positive correlation whose interval excludes zero supports blockage-associated error for that quantity. An interval entirely inside [−0.2,0.2] supports absence of a material association under this chosen tolerance; otherwise report inconclusive. A large negative correlation is a different error, not success.
4. Assess the mean-flow conclusion independently using signed components and reattachment. Reduced scalar correlation cannot demonstrate correct cavity mean flow, nor uniquely distinguish a length error from a turbulence error.

**Output:** evidence for mean reverse-flow strength, cavity length or turbulence discrepancies, including what cannot be distinguished. Only the existing optional cavity-strength adjustment in section 7 is a possible extra change here.

### T3. Tower locality and the need for D (K3)

1. Repeat the Case E absolute and paired-change tables on the corrected parents, separating vector and scalar quantities. Check measured ΔK versus distance/H and wind-relative position. Test locality directly: is the near/far contrast resolved, and are effects beyond about 0.5 H small relative to those inside? Report uncertainty and actual sampled distances; sparse coverage is inconclusive, not confirmation of a universal cutoff.
2. Case D: absolute near-tower K on thermistor and split-fibre data. It has no before state and cannot independently establish intervention locality.
3. A/B: measured front, corner and wake vector quantities for isolated buildings. Same-direction errors across A/B/D may reopen the parent/design assumption; they do not refute the separate locality claim.
4. Synthetic arrays with/without towers: compare parent ΔK and explain its source. These have no measured accuracy target.
5. **Prerequisite for D:** the `wake=3` parent's scalar before-state error must be ≤0.10 in each near-tower bin under I0's scoring contract. If it fails, pause D and go to part S. If it passes, require a remaining resolved after-state or paired-response defect before developing D. Passing the absolute after-state gate alone does not prove the paired response is correct.

**Output:** separate verdicts on locality, shelter adequacy and need for a near-tower correction. Do not infer momentum transport from agreement of bin means.

### T4. Where the before-state excess comes from

Diagnostic only; its verdict selects the candidate of part S.

1. **Level:** signed scalar and vector bias in Case E before and Case D against distance from the upwind domain edge along the flow, and against upwind fetch over buildings. A bias that is present at the first rows and constant inward points to the inflow or roughness level; one that grows inward points to accumulated shelter that the model lacks.
2. **Open plot:** in Case C, the 0H state and the 0H → 1H change at and around the central plot, per direction. In Case E, bias against the size of the open area around the probe (distance to the nearest upwind building, in building heights) and against the `wake=3` deficit at the probe. Check whether the future tower site is an outlier on these axes or follows the district trend.
3. **Per direction:** for the 22 near-site probes, list the upwind buildings, their modelled deficits and the measured K. Use stage/building observers for provenance.
4. **Verdict:** level error, missing accumulation of shelter, open-plot shelter error, a combination, or inconclusive, each with its interval. The verdict maps to S's candidates as listed there. An inconclusive verdict does not start S.

**Gate after part T.** Record `validation/ACCURACY_DIAGNOSTICS.md` and stop for review. M proceeds on mean-field scores only with a supported vector-amplitude/zone-edge target, and otherwise on the continuity target. S proceeds if the shelter prerequisite fails and T4 gives a verdict. D proceeds only with its shelter prerequisite met, on the default `wake=3` or on a parent that passed S, and with a supported remaining target. Inconclusive evidence does not automatically authorize a model change.

At this review, also set the bar for M's continuity target: measure the parent's distribution of K steps in the Fabel 1° sweep in part T, and freeze the required reduction before any M run.

---

## 4a. Part S: shelter in the `wake=3` parent

Runs only if I3/T3 fail the shelter prerequisite and T4 gives a verdict.

**Starting point.** `wake=3` takes the deficit as the maximum of G over buildings and tapers each wake to zero at the end of its reach ([wake documentation](docs/spreading-wake.md)). Behind several rows the deficit is then that of the nearest building only, so shelter does not accumulate through a fabric. That is a candidate cause, not a finding.

**Candidates, fixed before part T is read.** T4's verdict selects one; a second may be used only as the A5 revision.

| Id | T4 verdict it answers | Change |
|---|---|---|
| S-a | Bias grows inward with fetch over buildings | Deficit superposition: replace the maximum by 1 − Π(1 − G_i), or by min(1, √ΣG_i²). No new constant. |
| S-b | Bias follows distance behind the nearest building; open plots are outliers | Wake reach and taper: a longer reach or a slower taper, one constant. |
| S-c | Bias is present at the first rows and constant inward | Inflow or roughness level of the approach profile, within the case's documented uncertainty. If the cause is the validation setup, correct the setup, rebaseline, and make no model change. |

Canopy columns (E1a, E1b) stay closed. No new zone type is added.

**Consistency.** The deficit also shelters each building's roof-level speed and so its cavity strength and wake turbulence, and k_w takes the maximum of U_H²·G. A candidate states how each of these follows the new rule, and uses the same rule in the prototype and the native version. A hook after the parameterizations cannot reproduce the feedback on cavity strength; where that matters, prototype S as a switch on a native experiment branch, which the unqualified build permits.

**Steps:**
1. **S1:** from T4, pick the candidate and record the reason. Check that a single building is bit-identical under S-a, and that S-b leaves the cavity unchanged.
2. **S2:** synthetic layouts: mirroring, direction continuity, monotonic deficit with added upwind rows, and no deficit above 1.
3. **S3:** develop on Case E before, the 43 probes at least 60 m from the tower site, all 16 directions. Select the constant by scalar MAE with R falling by at most 0.02, among values that pass the do-no-harm checks on A/B and Case C. Freeze. Case C cannot be the development case: its points 1–2 H behind a block are already too slow (section 0).
4. **S4:** test, once: the 22 site probes of Case E before, and Case E after. Report Case D. Apply the gate.
5. **S5:** 1 m grid, ±25% on any constant, and the Fabel direction sweep, as robustness reports.
6. **S6:** native implementation if passed, as an experimental opt-in option of `wake=3`; parity with the prototype; repeat the gate.

**Gate for S** (relative to the default `wake=3`, same scalar convention, paired intervals):
- **Shelter prerequisite:** Case E before, |mean simulated K − mean measured K| ≤ 0.10 in [0,30) m of the future tower. This is the D prerequisite; passing it reopens D on this parent.
- **District level:** Case E before, the absolute mean bias beyond 60 m decreases. This is the development set, so it is a consistency check, not evidence.
- **Scores:** q and MAE do not worsen in E before or E after; R falls by at most 0.02; A/B pass the common vector gate; in Case C no score is worse beyond its paired interval.
- **Case D: reported, not gated here.** Every Case D probe is near its tower and already too low; more shelter lowers it further. The shortfall is passed to D, and Case D is gated on S and D together.
- **Beyond shrinkage:** MAE on the site probes of E before is lower than that of both shrinkage comparators of the parent (section 0).
- **Not gated, reported:** the after-state level within 30 m of the tower. More shelter is expected to lower it below the measurement; that shortfall is D's target and is passed to D1 with its interval.
- **Robustness:** frozen continuity, grid and divergence checks.

**If the gate fails:** one recorded revision under A5, then close S. D stays paused, and the diagnosis in `validation/ACCURACY_DIAGNOSTICS.md` is the result.

---

## 5. Part M: continuity in wind direction

The mixing step is closed (section 0): it has no score target on `wake=3`, and on `wake=2` only what `wake=3` already delivers. What remains of part M is the continuity target, by a different means.

**Cause.** The sidewall zone (`Sidewall.cpp`) and the upwind cavity (`UpwindCavity.cpp`) are applied to a wall only inside ±10° of the aligned direction. At the threshold the whole zone appears or disappears. In the 1° sweep this gives the largest step (plane RMS 0.032, 5.4 × the median, at 279° → 280°); with both zones off it is 0.016.

**Change.** Replace the on/off test by a weight that fades with angle, inside the two parameterizations. The weight is 1 when the wall is aligned, and falls smoothly to 0 across a ramp centred on the present threshold; the zone's change of the velocity is multiplied by it. A wall exactly aligned gives today's field.

**Steps:**
1. **M1:** native experiment switch on the branch `exp/accuracy-prototypes`: ramp half-width as one constant, 0 reproducing today's test bit for bit.
2. **M2:** run the 1° sweep for half-widths of 2.5° and 5°. Pick the narrower one that meets the bar. Freeze.
3. **M3:** do-no-harm on A/B, C, D and E with the frozen width. Mirror symmetry and divergence on the synthetic layouts.
4. **M4:** 1 m grid; a second sweep with the building rotated by 30°, so that the bar is not met at one orientation only.
5. **M5:** native implementation as an experimental opt-in option, if passed.

**Gate for M** (parent `wake=3`):
- **Continuity:** largest plane RMS ΔK per degree ≤ 0.016 and median plane RMS ≤ 0.0065 (parent: 0.032 and 0.0059). The largest probe step is reported, not gated (decided 2026-11-15): the steps that remain at a point probe are a spatial edge of the near-wake cavity, which this change does not address.
- **Identity:** half-width 0 is bit-identical to the parent; a building aligned with the wind is unchanged at any half-width.
- **Do no harm:** no score of A, B, C, D or E worse beyond its paired interval; A/B pass the common vector gate.
- **Robustness:** the bar holds on the rotated building and at 1 m.

**If the gate fails:** one recorded revision (the ramp shape or its centre), then close M.

---

## 6. Part D: shelter and the downwash zone

**Idea.** Conditional on T3, test whether a local zone representing downward transport of approach air improves the remaining tower response. It is a modelling hypothesis, not a mechanism established by X4. The parent is `wake=3`; its deficit is a shelter indicator, not a complete diagnosis of the solved local flow.

**Design (through I1, at the same post-parameterization point as native D, after M):**
- **Eligibility.** Smooth weight from 0 at a building/neighbor mean-roof-height ratio of 1.5 to 1 at 2.5, using a 2 H neighborhood. Specify the neighbor averaging before any run. An empty neighbourhood gives weight 0: isolated buildings are bit-identical controls (A7). Case C has one ratio above 1 (2H, weight 0.5 on this ramp) and Case E about 4, so the ramp's break points are a declared choice, not a fitted one; D5 reports their sensitivity.
- **Reference.** Evaluate the unmodified approach profile at a fraction of H, starting at ⅔ H, at the prepared incident-reference location. Reuse F3's captured incident direction, including its calm fallback. Its stored roof-speed magnitude is not itself the speed at ⅔ H; turning profiles require the reference convention to be recorded.
- **Targets within reach R of façades:** front reversed ground flow c_f·U_s; corner/side flow c_c·U_s decaying over R; preserve the existing near-wake cavity mean flow and test wake-k scaling with U_s² instead of roof speed.
- **Write precedence.** D may adjust front/side velocities after the existing zones, while protecting near-wake cavity faces and all solid/boundary faces. It must update the wake quantities used by its scalar output consistently with any deficit restoration. Do not blindly multiply by a changed deficit after all zones: cavities and local stages do not all equal approach flow times (1−D). Record the exact blend and masks before fitting. No subsequent building zone overwrites D; combined runs apply M before D (A4).
- **Constants.** Height fraction, c_f, c_c and R/H. Look up and cite the Wise/Gandemer literature named in F08 before fixing starting values. They are literature values by default (A7). Case C 2H may adjust a constant only if its profile-likelihood interval on that case excludes the literature value and the others can be held fixed; otherwise the literature value stands. Nothing is fitted to D/E.

**Steps:**
1. **D1:** verify the scalar shelter prerequisite on the parent in use (default `wake=3`, or the one that passed S) and the remaining target, including the after-state shortfall reported by S. Look up and record the Wise/Gandemer starting values here, before any prototype run.
2. **D2:** prototype on synthetics; check mirroring, direction continuity, cavity preservation and inactivity for equal-height arrays. Compare candidate-induced symmetry error against the corrected parent's known residual error.
3. **D3:** run the literature constants on Case C 2H and on the 1H → 2H paired change at all three directions; adjust only identifiable constants as defined above. Check that 0H and 1H are bit-identical to the parent. Freeze all choices and constants before candidate D/E scoring.
4. **D4:** run D/E once with frozen constants and apply the gate.
5. **D5:** ±25% sensitivities, 1 m grid and eligibility break-point sensitivities are robustness reports, not a second D/E selection sweep. Any tuning informed by them counts as A5's development revision.
6. **D6:** implement natively at A4's post-parameterization insertion point, preserving the same masks, precedence and references. Compare initial fields and wake quantities with the prototype, then repeat solved-field gates.

**Gate for D:**
- **Absolute tower levels:** under I0's scalar convention and matching/weighting, |mean simulated K − mean measured K| ≤0.10 separately in [0,15) and [15,30) m, for both before and after. Recompute measured means from unrounded data. Historical scalar before values were 0.55/0.49 and after 0.58/0.51; these are not current baselines.
- **Tower effect:** mean paired scalar ΔK in [0,30) m ≥+0.15 and closer to measured ΔK than the parent's. Require the measured sign in each disjoint directional sector where the grouped measurement interval excludes zero; otherwise report that sector inconclusive, not a forced positive sign.
- **Away from the tower:** for distances ≥60 m, scalar q and R fall by at most 0.02 and MAE does not increase.
- **Case D:** thermistor scalar q and R fall by at most 0.02; pass the common vector gate on split fibre.
- **A/B:** bit-identical to the parent (D inactive).
- **Case C (development):** the 1H → 2H paired change around the central block is closer to the measurement than the parent's, with the measured sign in each directional sector where it is resolved; scores over the whole array do not worsen.
- **Inactivity/robustness:** equal-height synthetic arrays and Case C 0H and 1H are bit-identical to the parent; pass frozen continuity, grid and divergence checks. Masks preserve intended cavity means before projection; no locality claim is made for the pressure-corrected field.

**If the gate fails:** at most one recorded revision under A5. A failed before-state shelter prerequisite pauses D and goes to part S; it is not an invitation to tune the downwash constants. If there is no remaining supported tower target, do not add D.

**Dependencies.** D's parent is the default `wake=3` if it meets the prerequisite, otherwise the parent that passed S. Develop D without M first. If both pass, evaluate together as in section 7, with M applied before D.

---

## 7. Combined evaluation and release

1. **Combined run:** parent, then each passing part alone and every combination of the passing parts (S, M, D; D only on a parent that meets its prerequisite), on all cases including Case C at 2 m and 1 m, using compatible parents and frozen conventions. Record `validation/ACCURACY_RESULTS.md`. Each must still pass its gate in combination. If only one proposal passes, evaluate/release only that one; apart from D's prerequisite, none depends on another.
2. **Optional step from T2:** if vector measurements support excessive cavity reverse-flow strength, fit one cavity-strength constant on A/B and apply the same transfer/vector safeguards. Include it in the final comparisons before release; it must not be added after the reported combined gates.
3. **Native implementation** of what passed (S6, M5, D6), on a feature branch from corrected `main`, with prototype checks for symmetry, continuity, inactivity, protected faces and mass conservation. Repeat the gates on the native code.
4. **Status at release:** experimental and opt-in, as `wake=3` was: new `Parameterizations` options, outside the `pedestrian-v1` qualification. Making any of it default is a separate decision, together with the `wake=3` default.
5. **Re-qualification** once for the batch, changelog, and updates of `validation/AIJ_VALIDATION.md` and `docs/spreading-wake.md`. This remains a separate qualification activity; 0.1.0b5 deliberately deferred it, and this document does not claim that its base is qualified or bring M/D settings inside `pedestrian-v1`.
6. **More reference data.** Before any of this becomes a default, it needs unseen towers. Existing plans name H02 more AIJ cases, H03 tall-building calibration and H09 intervention transfer set. That work remains outside this plan and a condition for any default change.

---

## 8. Order and effort

| Step | Rough effort | Depends on |
|---|---|---|
| I0 scoring protocol, archive audit and corrected baselines | 1–2 days | 0.1.0b5 build identity |
| I3 shelter check and vector-smoothing check | half a day | I0 |
| I2 synthetic layouts | half a day | – |
| I4 Case C entry check and parent baselines | half a day | I0; Case C setup delivered |
| T1–T4 diagnostics and results file | 2 days | I0, I2, I3, I4 |
| **Stop: review of part T** | | |
| I1 initial-field hook and parity contract | 1 day | A4 |
| S1–S5 shelter candidate S-b, development on E before, test and robustness | 3–4 days | T4 verdict; native experiment switch |
| M1–M4 angle fade, sweep, do-no-harm and robustness | 1–2 days | native experiment branch, continuity bar |
| D1–D5 prototype, Case C development, transfer and sensitivity | 3–4 days | I1, I4, prerequisite met (possibly through S), supported target |
| **Stop: review of the gates** | | |
| Combined run and results file | 1 day | passing proposals |
| Native S6/M5/D6, tests, re-qualification | 4–7 days | gates passed |

**Most likely path.** On the historical evidence (findings 4 and 7–9), I3 fails the shelter prerequisite and leaves M without a mean-field score target. The expected order is then: I0, I3, I4, part T; at the review, S on T4's candidate and M on the continuity path; D only if S passes. Parts are built only for a branch that I3 and part T leave open, and a plan that ends with `validation/ACCURACY_DIAGNOSTICS.md` and a closed S is a valid result.

Preparation can start now on 0.1.0b5. The blockers are diagnostic evidence and prototype gates, not unfinished physics fixes. Effort is provisional; measure diffusion cost and account for missing archives and qualification work rather than promising an under-hour screening campaign.

---

## 9. Risks and limits

- **Overfitting.** D/E are previously inspected transfer benchmarks, not untouched hold-outs. Freeze candidates before their new scoring, disclose any development revision, and require independent data before defaults.
- **Shelter prerequisite.** Historical `wake=3` scalar before levels missed the near-tower target. A corrected-parent scalar table is still required (I3); the release's vector tower diagnostic does not replace it. D can be reached only through that table or through S.
- **Shelter candidates.** More shelter lowers every sheltered level, including after-state levels that agree today. S's gate holds the scores of all cases and reports the after-state shortfall instead of hiding it. S-a changes the published `wake=3` behaviour in every multi-building scene and stays opt-in.
- **Case C.** Its setup is a prerequisite from separate work; I4 checks the instrument, the reference and the prior use before relying on it. It is a regular array of identical blocks with one height ratio; agreement there does not establish behaviour in irregular fabric or the eligibility ramp. It is a development case for S and D, so their independent evidence is still only D/E.
- **Mixing closure.** Spatial smoothing may blur real features; k_mix may overlap existing turbulence. Signed-vector, reattachment and scalar gates all matter. No scalar-only fallback survives a failed mixing candidate.
- **Sparse observations.** Mean/turbulence separation and locality are only partly constrained. Do not turn low statistical power into a pass.
- **Native parity.** Identical insertion point and masks are required but not sufficient; repeat comparisons and gates after porting.
- **Storage/provenance.** Historical `experiments/e2e_review/` outputs are untracked. New scripts go under `experiments/accuracy/`; large outputs go under ignored `validation/output/`, using immutable archives and manifests. Preserve scripts/configurations and record how the required untracked A/B measurements are supplied to a fresh worktree. Do not reuse cached pre-fix arrays as corrected baselines.

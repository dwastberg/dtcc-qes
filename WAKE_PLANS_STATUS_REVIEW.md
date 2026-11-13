# Wake plans against what is implemented

- **Date:** 2026-11-13.
- **Question:** across every wake plan and design, what is done, what is left, and what should change given what has been learned since they were written.
- **Method:** read every document below and compared it with `main` (`62a40ac`, 0.1.0b3), the integration record and the research branch's experiment reports. No new runs.

## Execution update (2026-11-13)

This review is preserved below as the pre-execution assessment. The reviewed
plans and M2 registration were committed in `dcb2337`, then current `main` was
merged into the worktree. Recommendations 5.1–5.4 and 5.6–5.10 are reflected in
the docs and harness; 5.5 is recorded as the tower-research continuation, not
claimed as executed. C1 is implemented and M2 fails its registered gates.
See [execution results and outstanding work](validation/WAKE_COMFORT_RESULTS.md).
No default switch or completion of C2–C7 is claimed.

## Verdict

- **The wake model is finished and on `main`.** Everything the investigation decided is implemented, with two declared improvements. Everything its section 8 listed as "not run" has since been run. Every gate passes. `wake=3` was merged as opt-in on 2026-11-13 with a re-qualified native identity.
- **The default switch has not started.** The comfort-default plan (C1–C7) has a review, decisions and a registered candidate, but no step has been executed. The switch waits on the tower effect, which no plan has run yet.
- **The written record trails the code.**
  - The reviewed comfort plan, its review and the M2 registration exist only as uncommitted edits in the feature worktree; `main` has the pre-review plan.
  - `WAKE_UPDATE_V2.md` on `main` still says "on branch".
- **Four findings from other work bear on the plans** (section 4):
  - the instrument result in C2 duplicates the earlier experiment F14;
  - an existing attribution points at the cavity;
  - F08's prerequisite gate has passed on the research branch;
  - the user docs on `main` recommend the scalar speed for comfort without the safety caveat.
- **The comfort plan's and its review's own findings** are summarised in section 6, so that this file stands on its own.

## 1. Documents

| Document | Location | Role | State |
|---|---|---|---|
| `FABEL_DESIGN_AND_ALGORITHM_REVIEW.md` S3, S4 | main checkout, untracked | Found the wake-edge step (S4) and the direction thresholds (S3) | S4 superseded by the investigation; S3 open |
| `FABEL_WAKE_INVESTIGATION.md` | main checkout, untracked | Design and decision | Implemented; status line still says "prototype only" |
| `WAKE_UPDATE_V2.md` | `main`; worktree has a one-line fix | Implementation plan W1a–W7 | W1–W5 done, W6 declined, W7 partly done |
| `validation/WAKE_UPDATE_V2_RESULTS.md`, `docs/spreading-wake.md` | `main` | Evidence and user documentation | Current, apart from section 4.4 below |
| `MAIN_INTEGRATION_PLAN.md` | main checkout, untracked | Merge into `main` | Done 2026-11-13; leaves the plan edits to be carried over |
| `WAKE3_COMFORT_DEFAULT_PLAN.md` and its review | worktree, uncommitted (`main` has the pre-review version) | The default switch | Decided D6–D8, M2 registered; C1–C7 not started |
| `CLAUDE_WIND_EXPERIMENTS.md` F07, F08, F13, F14 | all branches | Canopy, tower effect, tower attribution, instrument | F14 done; F07, F08, F13 not run as written |
| `UPDATES_FROM_LIT_STUDY.md` L3, `JOINT_PHYSICS_SCREENING_PLAN.md` E3 | research branch / main checkout | A published wake-diffusion envelope (Singh) against the legacy wake | Not run; written before `wake=3` existed |
| `docs/WIND_SIMULATION_IMPROVEMENT_PLAN.md`, `experiments/E2_*` | main checkout, untracked | Wake/cavity attribution and composition on `wake=2` | Attribution done; composition candidate SE1 rejected |

## 2. Done

**The investigation's decision, item by item:**

| Investigation (section 7) | Implemented | Evidence |
|---|---|---|
| Spreading far wake, largest-deficit superposition, sheltered cavity, k_w = 0.08 · max U_H² G | Exactly. Two declared changes: an end taper, and the physical roof as the wake top | `WAKE_UPDATE_V2.md` 3.1; W1c matches the prototype to ΔD 7.5·10⁻⁸ |
| A new code `wake=3`, with the default left at 2 | Yes | W2 |
| D and k_w returned as result fields | `result.wake`, the sampled fields, `to_dtcc` | W2 |
| A scalar-speed accessor, used by comfort | `scalar_speed()`; `assess_results(speed="scalar")`, opt-in | W2, W5 |
| Tests: symmetry, σ → 0, order independence, direction sweep | `check_wake.cpp`, `test_wake_v3.py` | W1c, W2 |
| Gates at the prototype's values less 0.03 | All pass, by 0.02–0.04 | W4 |
| "If the gates pass, make it the default" | **No.** The policy accepts only `wake_flag == 2`, and the windy points argue against it | W6, results "The windiest points" |

**Further work done along the way:**

- **Inflow k outside the tunnel:** a 5.5 u*² rule (u* from a log fit to the profile). It scores within 0.02 of the tunnel table.
- **Cost:** +0.19–0.23 s per Case E direction, against a target of +0.5 s (W1d).
- **The `canyon_factor` defect** the investigation found is fixed for every wake code (W1b).
- **The investigation's "not run" list (section 8)** is now covered: unit tests, the full harness with turbulence on, and a 4 m and 0.5 m grid study.
- **QES-Turb's role** (investigation 7.5) was re-evaluated: its k does not improve on the new field.

**On `main` since 2026-11-13** (`MAIN_INTEGRATION_PLAN.md` part B):
- version 0.1.0b3, identity `bf48ef3f…`;
- the W4 gate values on the merged code equal the branch's own;
- under the new default stop rule, `wake=3` needs 200–225 sweeps per Case E direction, against 150–175 for `wake=2`.

## 3. Left to do

### 3.1 Records

1. **Carry the reviewed comfort plan to `main`.** Three files are uncommitted on `feat/wake-update-v2`:
   - `WAKE3_COMFORT_DEFAULT_PLAN.md`;
   - `WAKE3_COMFORT_DEFAULT_PLAN_REVIEW.md` (untracked);
   - the one-line fix to `WAKE_UPDATE_V2.md`.

   Why it matters: until they are committed, M2's registration has no timestamp, and "registered before C1" cannot be shown. `main` has not touched these files since `209ce15`, the branch tip, so they apply cleanly. The integration plan (section 8) also records them as outstanding.
2. **`WAKE_UPDATE_V2.md` status.** It should say that the work was merged as 0.1.0b3 with identity `bf48ef3f…`, and point to the integration record. The integration deliberately left it alone to avoid a conflict with item 1.
3. **`FABEL_WAKE_INVESTIGATION.md` status.** It still says "prototype only; the repository sources are unchanged". It should point to `wake=3` on `main`.
4. **Tidy-up after items 1–2** (integration D5, your call):
   - the `feat/wake-update-v2` branch and its 25 GB worktree;
   - the untracked 11-November draft of `WAKE_UPDATE_V2.md` in the main checkout, which blocks `git checkout main` there.
5. **W7.** `build/fabel-wake` is kept at your request. `experiments/fabel_wake/` is git-ignored, so "the record of the prototype" exists only on this machine. W1c reproduces the prototype in the tree, so the loss would be small.

### 3.2 The default switch (`WAKE3_COMFORT_DEFAULT_PLAN.md`)

| Step | State |
|---|---|
| C1 comfort-class test | Not started. Needs no runs; exploratory numbers exist in the review |
| C2 comparator | The instrument half is answered (see 4.1); the criteria half is open |
| C3 attribution | Attributed by zone without runs (the review); the H2 split and H4 are not run |
| C4 remedy | M2 registered. On the stored data (exploratory) it fails three gate conditions: the windy-tenth share in both Case E states; the D7 cost in Case E after at every level and in Case E before at 9.25 m/s; and the hard safety gate in Case E after at 7.75 m/s (3 of 20 against 2 of 20, section 6.3). The H1 remedy (F08) is not run |
| C5 independent data | Hamburg request unsent; needs your authorization |
| C6 `pedestrian-v2`, C7 switch | Not started; depend on C4 and C5 |

### 3.3 Gaps the wake model leaves (investigation, section 6)

| Gap | Planned in | State |
|---|---|---|
| Tower effect (downwash, corner streams) | F08 (zone), F13 (attribution), `MOMENTUM_PLAN.md` | None run on `main`. F08's prerequisite has passed (4.3). This is the switch's critical path |
| ±10° direction thresholds | Fabel review S3 | Not started. The investigation's plan wanted it in the same native batch; it was not ready |
| Case A cavity 20–30 % too long | None (two cases cannot fit a law) | Open |
| Roof flow | `JOINT_PHYSICS_SCREENING_PLAN.md` E2 (roof forcing) | Research branch; roof-only arm run, no promotion |
| Low level at oblique incidence (Case D 22.5°, 45°) | None | Open; no vector data at oblique incidence |
| Re-evaluate F07 (canopy inflow) now that the wake removes most of its bias | Investigation 7.5 | Not done; see 5.6 |

## 4. New findings that bear on the plans

### 4.1 C2's instrument result is F14

- **What is already on record.** `CLAUDE_WIND_EXPERIMENTS.md` F14 (2026-11-02, "done: negative") compared the same 33 Case D points. It found:
  - the thermistor reads the RMS speed (median ratio 0.950, 91 % within ±25 %), not the Gaussian mean speed (0.90–0.92);
  - it kept √(|u|² + 2k) as the comparator.
- **The overlap.** The end-to-end check's fix 3 found the same thing again (0.95, 0.88 and 0.85 by geometric mean).
- **What is new.** One addition is not in F14: the thermistor reads 9 % above even the RMS speed at the faster half of the points.
- **Consequence:** C2 should cite F14 and claim only the new part.

### 4.2 An existing attribution points at the cavity

- **What the research branch found** (`docs/WIND_SIMULATION_IMPROVEMENT_PLAN.md`, `experiments/E2_NEAR_FAR_REPORT.md`, 2026-11-04/05, on `wake=2`):
  - about 75 % of the negative wake increment on Case E's spurious-decrease group comes from **near-cavity** writes;
  - the source is chiefly the new tower and the two added 18 m buildings;
  - repeated attenuation and overwrites largely cancel between the two states.
- **Why it matters for `wake=3`.** `wake=3` keeps the code-2 cavity. Its only change there is the shelter scaling, and the tower is effectively unsheltered: its roof point lies far above the other buildings' wakes.
- **What remains unexplained.** `wake=3` still trails `wake=2` with inflow k on the change scores: sign agreement 0.69 against 0.73, top-10 overlap 0.53 against 0.59. C3 records which building's wake or cavity sets D at each point, but the cavity is not one of its named hypotheses.
- **How far it can reach** (the review, section 1.2):
  - Only 25 of the 135 windy points of Case E after lie in the tower's wake. There `wake=2` predicts a fall (−0.125) where the measured speed rises (+0.092), as E2's cavity finding would expect.
  - `wake=3` scalar predicts no change there (+0.010), so its wake turbulence already offsets the cavity in the scalar speed.
  - The corner streams (78 of 135 points) dominate either way.
- **What to check.** Whether the windiest tenth of Case E after overlaps E2's spurious-decrease group. If it does, the cavity is a secondary cause for `wake=3`, mainly through its mean vector and the change scores. It is not an alternative to H1.
- **Tooling caveat.** The attribution instrumentation exists (`docs/WAKE_ATTRIBUTION.md`, `experiments/run_wake_attribution.py`). It is untracked, and it patches `PolygonWake.cpp` as it was before W1a split the file.

### 4.3 F08's prerequisite has passed

- **What the plans assume.** The comfort plan (C4) and F08 itself say the tall-building zone needs gate P0: a Python projection that reproduces the native one.
- **What has happened.** The research branch's E0d ran a city P0 and passed (`experiments/E0_REPORT.md`):
  - Case E after N, E, SW and W, all 80 receptors;
  - maximum difference below 6·10⁻⁹ (F08 asks p95 ≤ 0.005, max ≤ 0.02).
- **Consequence.** F08 is runnable now as a Python prototype on stored initial fields. Its hypotheses H8a–H8c are written against the `wake=2` baseline. For the comfort switch it must also run on `wake=3`, because that is the field it would correct.

### 4.4 The user docs on `main` lack the safety caveat

- **What `docs/spreading-wake.md` says:** "use `speed="scalar"` with `wake=3` unless a criterion requires the vector."
- **What `docs/wind-comfort.md` says:** the scalar speed's classes "are never better".
  - This is true only against `wake=3`'s own mean vector.
  - It is not true against today's default (`wake=2` vector).
- **What the evidence shows.** `validation/WAKE_UPDATE_V2_RESULTS.md` ("The windiest points") and the review's exploratory comfort test show the opposite at the points that decide classes:
  - in Case E after, `wake=3` scalar is 25 % too slow at the windiest tenth, against 11 % for `wake=2`;
  - it missed 15 of 20 danger probes, against 2 for `wake=2`.
- **The windy-tenth figure is selection-biased** (the review, section 1.1). Selecting by each model's own windiest tenth, `wake=3` scalar is 11 % too fast in Case E after. Its windy points are in the wrong places, not systematically too slow.
- **The safety finding does not depend on that selection.** It comes from the comfort-class test, at the windiest climate level. At the two lower levels `wake=2` misses as much danger as `wake=3` scalar (3 of 3, and 4 of 7).
- **Comfort is the other way round** (the review, section 1.4). With equal sectors, `wake=3` scalar has the better comfort classes: the mean class error falls by 0.24–0.90 classes, with the confidence interval excluding zero at all six levels. With one dominant wind direction its optimistic share nearly doubles (21 % → 38 %, section 1.6).
- **Consequence.** A user who follows the docs gets better comfort classes in sheltered areas, but fewer safety warnings near tall buildings. This is the one finding that affects users today.

### 4.5 M2's product cost

- **Two prepared models.** `wind.prepare` fixes the parameterizations, so M2 needs two prepared models per study, not one.
- **More sweeps for `wake=3`.** Under the default solver, `wake=3`'s solve takes about 30 % more sweeps (section 2).
- **Total.** M2 costs about 2.3 times a `wake=2` direction in solves, plus a second preparation. Plan section 10.5 says only "two solves per direction".

### 4.6 The research wake-diffusion arms predate `wake=3`

- **Which arms.** `UPDATES_FROM_LIT_STUDY.md` L3 and `JOINT_PHYSICS_SCREENING_PLAN.md` E3 test the Singh wake envelope against the legacy wake.
- **What has changed.** `main` now has a validated wake-diffusion model. A result against the legacy wake alone would not say whether Singh beats what ships.
- **Merge risk.** The research branch's composition work patches `PolygonWake.cpp`, which W1a split into `prepareWake` and `applyWake`, so it will conflict.

## 5. Recommended changes

In order of priority. None of these changes the M2 rule, a_opt or any registered gate.

| # | Change | Where | Why |
|---|---|---|---|
| 5.1 | **Add the windy-point caveat to the user docs.** `speed="scalar"` with `wake=3` gives better comfort classes overall. It is more optimistic where one wind direction dominates, and it misses danger near tall buildings. Keep `wake=2` for safety assessments until the comfort plan concludes. Reword "never better" to say against what. | `docs/spreading-wake.md`, `docs/wind-comfort.md` on `main` | 4.4. Docs only; no identity change |
| 5.2 | **Commit the plan records** (3.1 items 1–3), then decide on the tidy-up (item 4) | worktree → `main` | Timestamps M2's registration; brings `main`'s plan up to date |
| 5.3 | C2: cite F14 for the instrument question; claim only the fast-half +9 % as new | comfort plan C2, section 9 fix 3 | 4.1 |
| 5.4 | C3: add the retained code-2 cavity as a candidate cause, beside H1 and H2. Test the overlap of the windy tenth with E2's spurious-decrease group (stored data). Reuse the E2 attribution tooling, ported to the split `PolygonWake`, instead of a new scratch build | comfort plan C3 | 4.2 |
| 5.5 | C4's H1 row: F08's prerequisite has passed on the research branch; run F08 on both `wake=2` and `wake=3` initial fields; F13 (tower stage attribution) before or with it | comfort plan C4; `CLAUDE_WIND_EXPERIMENTS.md` F08 | 4.3. This is the switch's critical path |
| 5.6 | Close the investigation's F07 follow-up. The bias F07 targeted is mostly gone with `wake=3` (Case E before, mean vector FB −0.43 → −0.11), and the research plan already lists canopy backgrounds as closed | `FABEL_WAKE_INVESTIGATION.md` 7.5 | Avoids a dangling follow-up |
| 5.7 | M2 section 10.5: record the cost as two prepared models and about 2.3× the solves, with the measured sweep counts | comfort plan 10.5 | 4.5. A fact, not a rule change |
| 5.8 | Mark L3 and E3 as needing `wake=3` as a second comparator, or close them as superseded | research plans (owned by the research thread) | 4.6 |
| 5.9 | **Correct the plan's section 9 record.** Add M2's safety failure at Case E after 7.75 m/s, and its D7 failure in Case E before at 9.25 m/s. Replace "not yet adopted: P1–P3 and P5–P9" with the actual state (section 6.4): P3 adopted, P1, P6, P7 and P9 partly, P2, P5 and P8 not | comfort plan section 9 | 6.3, 6.4. The record understates M2's failures and overstates what is still open |
| 5.10 | C3's H4 names no test. Use the review's M7: flank runs at θ ± 5° on Case E, 32 runs, about 4 minutes | comfort plan C3 | 6.5. The cheapest open diagnostic |

### Suggested order

1. 5.1 and 5.2 together, as one docs-and-plans commit on `main`. Python identity unaffected.
2. C1 (no runs), with 5.3–5.7, 5.9 and 5.10 written into the plan first.
3. In parallel, on the research side: F13, then F08 on both wake codes (5.5). The switch cannot pass C4 without the tower effect, so this decides when the switch is possible.
4. The Hamburg request when you authorize it. C5 is the only confirmation M2 can get.

## 6. What the comfort plan and its review contribute

This section carries over the findings and notes of `WAKE3_COMFORT_DEFAULT_PLAN.md` ("the plan") and `WAKE3_COMFORT_DEFAULT_PLAN_REVIEW.md` ("the review"), so that this file stands on its own.
- **Data and status.** All numbers come from the stored W4 runs and are exploratory.
- **Two kinds of finding.** C1 has not run; until it does, these are findings about the evidence, not results of the plan.
- **How they were computed.** The climate was computed analytically per sector, not through `comfort.assess`.

### 6.1 Decisions in force (the plan)

| # | Decision |
|---|---|
| D1 | New defaults only for mean-speed criteria (`NEN8100`). `CITY_OF_LONDON` keeps the vector speed with GEM, since the scalar speed already contains the turbulence. |
| D2 | A new policy, `pedestrian-v2`; `pedestrian-v1` stays frozen for `wake=2`. |
| D3 | The C1 test climate (details below the table). |
| D4 | The independent dataset is Hamburg (CEDVAL / Michelstadt). The request is unsent and needs your authorization. Michelstadt is untouched. |
| D5 | Constants change only from first principles or Cases A and B, never by fitting to D or E. |
| D6 | One field for comfort and safety. Separate estimators (M1, with the envelope max(`wake=2`, `wake=3` scalar) for safety) are a future option (plan, section 11). |
| D7 | Comfort cost per probe = 3 × optimistic class steps + conservative class steps, linear. Gated as T, the worst of the 16 dominant-direction climates against `wake=2` vector, with a 4000-resample probe bootstrap. Safety stays a hard gate. a_opt is never changed in response to a gate result. |
| D8 | M2 registered (plan, section 10). |

**D3, the C1 test climate:**
- Weibull speeds with shape k = 2.
- Three levels per state, set by the median measured class reaching B, C and D:
  - Case E before: 6.75, 7.80 and 9.25 m/s;
  - Case E after: 5.60, 6.50 and 7.75 m/s.
- 150 000 deterministic quantile hours through `comfort.assess`.
- 16 equal sectors, plus 16 dominant-direction climates (one sector with 30 % of the hours, rotated over all 16).

**Rules (plan, section 5):**
- no fitting to the test cases;
- safety first;
- one remedy at a time;
- gates written before runs;
- fixed weights.

### 6.2 What the stored runs show (the review, section 1)

**The windy tail is a ranking problem as much as a level problem** (1.1). Case E after, `wake=3` scalar / `wake=2` vector:

| Selection | `wake=3` scalar | `wake=2` vector |
|---|---|---|
| Windiest tenth by measured value | −25 % | −11 % |
| Each model's own windiest tenth | +11 % | +21 % |
| Unpaired 90th percentiles | −6 % | +16 % |

- In Case D, `wake=3` scalar is too slow by every measure. That is a real level deficit.

**The windy points sit in the tower's corner streams** (1.2).
- 78 of the 135 windy points of Case E after are there.
- The measured speed-up from the tower is +0.245. The models give +0.055 (`wake=3` scalar) and +0.078 (`wake=2` vector), so they capture 22–32 % of it.
- So H1, the missing tower effect, dominates.
- H2, over-sheltering, is secondary. For windy points with D between 0.2 and 0.5, `wake=3` scalar is −21 % and `wake=2` vector 0 %.

**A mean-speed comparator would make the tail worse** (1.3).
- It moves the windy tail by 4–6 points in the wrong direction, so the comparator part of H3 is closed.
- Together with F14 (section 4.1), question 1 of C2 is answered. Only the criteria question remains.

**Comfort and safety point in opposite directions** (1.4).
- `wake=2` vector is conservative by 1.2–2.4 classes per probe.
- `wake=3` scalar has the better comfort classes, with the interval excluding zero at all six levels. It also ranks best:
  - AUC for class ≥ D: 0.83–0.93, against 0.79–0.88;
  - Spearman: 0.70–0.71, against 0.58–0.64.
- The safety counts are small:
  - Case E before has 0–1 danger probes;
  - Case E after has 3, 7 and 20.
- At 5.60 m/s every model misses all 3 danger probes. That is the floor H1 sets.

**A constant margin does not transfer** (1.5).
- The factor needed for at most 5 % optimistic classes shifts by about 0.3 between the two states of the same site.
- With the bias removed, the models are within 9 points of each other in exact agreement. They differ mainly in level, not ranking.

**One dominant direction nearly doubles the optimistic share** (1.6). With 30 % of the hours in one sector (worst rotation, against equal sectors):

| Model | Equal sectors | Worst rotation |
|---|---|---|
| `wake=3` scalar | 21 % | 38 % |
| M2 | 9 % | 20 % |

**M2 keeps the Cases A and B gates** (1.8): q 0.877 and 0.876, against gates of 0.83 and 0.86. The margin for B is thin.

### 6.3 M2 against each C4 condition (stored data, exploratory)

| Condition | Result |
|---|---|
| Windiest tenth: mean no further below the measurements than `wake=2` vector | Pass: E before +14 % (+28 %), E after −10 % (−11 %), D −36 % (−42 %) |
| Windiest tenth: share more than 20 % too slow no larger | **Fail** in E before (13 % against 4 %) and E after (34 % against 27 %); pass in D (80 % against 80 %) |
| D7 comfort cost: T and its interval below zero | Pass in E before at 6.75 and 7.80 m/s. **Fail** in E before at 9.25 m/s and in E after at all three levels |
| Safety (hard): missed danger no more frequent | E after: equal at 5.60 m/s (3 of 3) and 6.50 m/s (4 of 7); **fail** at 7.75 m/s (3 of 20 against 2 of 20). E before has 0–1 danger probes, so it cannot test this |
| Exact agreement higher | Pass at all six levels: +7 to +11 points in E before, +9 to +15 in E after |
| The wake plan's gates | A and B scalar gates pass; the others were not computed |

- **The registered predictions** (plan, 10.4) all hold on the stored data. That is expected, since M2 was designed on it (10.3). Only C5 can test them.
- **What the plan's section 9 records:**
  - it has the share failure and the D7 failure in Case E after;
  - it omits the D7 failure in Case E before at 9.25 m/s and the safety failure (5.9).

### 6.4 The review's proposals P1–P9: what the plan has adopted

The plan's section 9 says "not yet adopted: P1–P3 and P5–P9". The actual state:

| Proposal | State |
|---|---|
| P1 Tail selected both ways, and a governing speed per probe | Partly. C3 also uses each model's own windiest tenth; the C4 gate still selects by measured value; no governing speed |
| P2 Iso-risk comparison against `wake=2` vector | Not adopted. D7's cost does the balancing instead |
| P3 Deterministic quantile climate through `comfort.assess` | Adopted (D3) |
| P4 Rotated dominant-direction climates | Adopted (D3, D7) |
| P5 Separate safety levels, and a continuous safety metric | Not adopted. Safety stays a point count on 3–20 probes |
| P6 Probe-bootstrap intervals | Partly. The D7 cost has them; safety and exact agreement are point comparisons |
| P7 C3 from the stored attribution; runs only to split H2 | Partly. C3 starts from the review's attribution; H3 is recast; the scratch-build runs remain |
| P8 Calibrate across cases, test on E after | Not adopted. Nothing in the plan is calibrated yet |
| P9 Discrimination, calibration and decision layers | Partly. Spearman and the mean absolute class error were added; no AUC, no margin |

- **P5 matters most of the open ones.** The hard safety gate rests on one probe at 7.75 m/s (6.3).

### 6.5 The review's methods not in the plan

| Method | What | State |
|---|---|---|
| M3 | The native form of M2: no low-rise deficit inside a tall building's downwash zone | Recorded in plan 10.5 as a later candidate if M2 survives C5 |
| M4 | A tower-effect model | Is F08 (5.5) |
| M5 | Probabilistic classes ("class C, 30 % chance of D"), calibrated across cases | Not in the plan; the long-term form of M1 |
| M7 | Flank-direction averaging over θ ± 5° | Not in the plan. It is the cheap test for H4 (5.10) and a product-side remedy for the ±10° thresholds without a native change |
| M8 | The neighbourhood max as a "low confidence" flag, not a value | Not in the plan |

**Not recommended by the review:**
- the geometric mean of the two fields, which misses all 7 danger probes at 6.5 m/s;
- one global margin, which does not transfer between states;
- the envelope for comfort, which is as conservative as `wake=2`.

### 6.6 Caveats the review attaches

- 80 probes and one site. Case E's two states share the probes, so they are not independent.
- Case D has 3 directions, so its windiest tenth is about 20 probe-directions.
- M2 was designed after looking at the data it is evaluated on.
- The zones in 6.2 are geometric approximations.
- The safety counts are too small for anything firm except the envelope's guarantee (M1).

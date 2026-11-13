# Plan: `wake=3` and the scalar speed as the pedestrian comfort defaults

- **Date:** 2026-11-12. Follows [`WAKE_UPDATE_V2.md`](WAKE_UPDATE_V2.md) (called "the wake plan" below) and its results, [`validation/WAKE_UPDATE_V2_RESULTS.md`](validation/WAKE_UPDATE_V2_RESULTS.md) ("the results").
- **Goal:** decide on evidence whether pedestrian comfort assessments should default to `Parameterizations(wake=3)` with `comfort.assess_results(..., speed="scalar")`, and make the switch if they should.
- **Status:** C1 implemented; M2 fails C4 on the stored development cases. C2/C3 diagnostics are partly complete; the switch waits for tower-remedy work and independent data. See [execution report](validation/WAKE_COMFORT_RESULTS.md). Today both are opt-in; the defaults are `wake=2` and `speed="vector"`. Reviewed 2026-11-12 in [`WAKE3_COMFORT_DEFAULT_PLAN_REVIEW.md`](WAKE3_COMFORT_DEFAULT_PLAN_REVIEW.md) ("the review"). The candidate M2 is registered in section 10.

## 1. Why the switch is not made yet

The wake plan's gates all pass, but they pool every probe. Comfort and safety classes are decided at the windiest points, and there the evidence is against a switch (the results, "The windiest points"):

| Case | Windiest 10 % of probe-directions | `wake=2` vector | `wake=3` scalar |
|---|---|---|---|
| D | mean speed vs measured | −42 % | −43 % |
| E before | mean speed vs measured | +28 % | +6 % |
| E after (new high-rise) | mean speed vs measured | **−11 %** | **−25 %** |
| E after | share more than 20 % too slow | 27 % | 64 % |

- The pooled gains of `wake=3` come mostly from sheltered, slow points, where `wake=2` is far too fast. That error is conservative for comfort.
- At the windiest points `wake=3` is no better, and in Case E after clearly more optimistic. A switch would raise comfort classes and lower safety warnings where it matters most.
- In Case D every model is about 40 % too slow at its windiest points. The tower effect is not modelled. A tall-building zone with literature constants is designed but not run (`CLAUDE_WIND_EXPERIMENTS.md`, F08); the momentum route is `MOMENTUM_PLAN.md` (in the main checkout, not on this branch).
- **Added by the review (sections 1.1, 1.2 and 1.4):**
  - This table selects points by their *measured* value, which makes any imperfect model look too slow there. Selected by each model's own windiest tenth, both models are too fast in Case E after.
  - The safety concern holds anyway. An exploratory comfort-class test shows `wake=3` scalar missing 15 of 20 danger probes, against 2 for `wake=2`.
  - 58 % of the Case E after windiest points lie in the new tower's corner streams. Both codes capture only 22–32 % of the measured speed-up there.

Two further obstacles are procedural:

- the adaptive policy `pedestrian-v1` is qualified only for `wake_flag == 2` (the wake plan, section 9, W6);
- the scalar speed √(|u|² + 2k) is a root-mean-square speed, and it is not settled which speed the comfort criteria's hourly mean corresponds to.

## 2. Scope

In scope:
- the comfort-class test that decides the question (C1);
- the definition of the scalar speed used for comfort (C2);
- the diagnosis and remedy of the windy-point bias (C3, C4);
- confirmation on an independent dataset (C5);
- the policy qualification and the switch itself (C6, C7).

Out of scope:
- the wake model's constants (0.2, 0.22, 0.9, 0.08): unchanged unless C4 requires it, and then only with the rules of section 5;
- QES-Turb, whose k does not improve on the new field (the results);
- the ±10° direction thresholds of the upwind cavity and sidewall models (S3 of `FABEL_DESIGN_AND_ALGORITHM_REVIEW.md`, in the main checkout), unless C3 shows they drive the windy-point bias;
- separate estimators for comfort and safety (the review's M1). These are not implemented (D6), and they are recorded as a future option in section 11.

## 3. Decisions to confirm before starting

| # | Question | Recommendation |
|---|---|---|
| D1 | Which criteria get the new defaults? | Mean-speed criteria (`NEN8100`) only. Gust-equivalent criteria (`CITY_OF_LONDON`) keep the vector speed with GEM: the scalar speed already contains the turbulence, and adding GEM would count it twice. A combined definition is a separate question. |
| D2 | Re-qualify `pedestrian-v1` on `wake=3` fields, or define `pedestrian-v2`? | `pedestrian-v2`. The v1 thresholds and evidence are frozen for `wake=2`; a new name keeps old results reproducible and their qualification meaningful. |
| D3 | The wind climate for the comfort-class test (C1). | A declared synthetic climate: 16 equal sectors, Weibull speeds at the reference height, scaled to three levels so that the measured classes span A to E. Report all three; gate on all three. No site climate exists for the tunnel model. A real one adds a frequency weighting by direction, which can change the result (the review, section 1.6); the dominant-direction climates below stand in for it. **Added with D7:** at each level, 16 dominant-direction climates. In each, one sector has 30 % of the hours and the other 15 share the rest equally (70/15 % each), with the same Weibull speeds. The dominant sector is rotated over all 16 directions. This is a deliberate stress test, more directional than most real climates. Full specification below the table. |
| D4 | The independent dataset (C5). | The Hamburg data (CEDVAL / Michelstadt) if it is obtained. **Status (`UNIFIED_CAMPAIGN_PLAN_REVIEW.md`, main checkout):** the request draft is ready but unsent, and sending it or accepting conditions needs the user's explicit authorization. Michelstadt is still untouched, so it can serve as confirmation data. Its pedestrian-level instrument and its number of wind directions must be known before C5's gates are written. If no dataset is available within the plan, the switch waits (section 7). |
| D5 | May C4 change the wake model's constants? | Only from first principles or Cases A and B, never fitted to Cases D or E (the wake plan's rule). Any change is then judged on D and E and confirmed on C5's data. |
| D6 | Separate estimators for comfort and safety (the review's M1)? | **Decided 2026-11-12: no.** One field serves both comfort and safety. M1 is kept as a future option (section 11). |
| D7 | A declared cost for comfort errors (the review, section 4.1)? | **Decided 2026-11-12: option A.** See below. |
| D8 | Register the review's M2 before any further look at the data? | **Decided 2026-11-12: yes.** The rule is fixed in section 10. |

D6–D8 are numbered as in the review.

**D3, full specification** (fixed 2026-11-12; the review's exploratory numbers used exactly this):
- **Weibull:** shape k = 2 in every sector. The scale c is the same in every sector.
- **Three levels per state:** c is the smallest multiple of 0.05 m/s at which the median measured comfort class (equal sectors) reaches B, C and D in turn. With the analytic Weibull exceedance this gives 6.75, 7.80 and 9.25 m/s for Case E before, and 5.60, 6.50 and 7.75 m/s for Case E after. C1 recomputes the levels with the discrete hours below and records them.
- **Hours for `comfort.assess`:** 150 000 hours per climate. Each sector gets hours in proportion to its share (equal sectors: 9375 each; dominant-direction climates: 45 000 and 7000). The speeds are the Weibull quantiles at (i − ½)/n within the sector. No random numbers are used.
- **Directions:** each hour has its sector's direction exactly.
- **Height:** the fields are at the probe height (2 m); NEN 8100 is defined at 1.75 m. Pass `height=2` and accept the warning.

**D7, option A:**
- **The comfort cost** per probe is 3 × (optimistic class steps) + (conservative class steps).
  - a_opt = 3, the initial value.
  - It is linear in class steps: two classes off costs twice one.
- **Safety** is not part of the cost. It stays a hard gate.
- **The cost replaces the optimism condition** of the C4 gate, and is judged in the worst dominant-direction climate (D3).
- **Changing a_opt:** a change is recorded here, with its date and reason, before the next gated step is run. It is never changed in response to a gate result.

## 4. Steps

Each step ends with its results recorded in this file (section 9) and the test suites passing. C1 comes first because it is the yardstick for every later step.

### C1. Comfort-class test on Case E

- Case E has 80 thermistor probes and 16 directions in both states, so measured and simulated speeds can be assessed with `comfort.assess` exactly as a study would. Case D (3 directions) and Cases A and B (1 direction) cannot be.
- Fields: the measured K per probe and direction, and each simulated model's K, all relative to the same reference (reference speed 1).
- Models:
  - `wake=2` vector (today's default);
  - `wake=2` with the inflow k;
  - `wake=3` vector;
  - `wake=3` scalar, and C2's alternative once it exists;
  - M2, exactly as registered in section 10. It needs no runs beyond the `wake=2` and `wake=3` pairs already listed.
- Output per model, state and climate level (comfort classes and safety in the equal-sector climate, unless stated otherwise):
  - NEN 8100 comfort classes: exact agreement with the classes from the measured speeds; **optimistic misclassifications** (simulated class better than measured, by one class or more); conservative misclassifications; the mean absolute class error;
  - the Spearman correlation of the per-probe log exceedance of 5 m/s with the measured one (the ranking of probes);
  - safety: points the measurements put at "limited risk" or "dangerous" that the model puts at "no risk" (**missed danger**), and the reverse;
  - **comfort cost (D7):**
    - per probe, 3 × max(0, measured class − simulated class) + max(0, simulated class − measured class), with classes indexed A = 0 … E = 4;
    - computed for the equal-sector climate and for each of the 16 dominant-direction climates (D3);
    - its mean difference from `wake=2` vector, per climate.
  - **the worst-rotation statistic T:** the largest of the 16 mean differences.
    - Its 95 % interval comes from a probe bootstrap: 4000 resamples of the 80 probes with a fixed seed, with T recomputed, including its maximum over rotations, in every resample.
    - The equal-sector difference is reported, not gated.
- Add the test to `validation/run_wake_validation.py` (a `comfort classes` report) with tests in `validation/tests/test_wake.py`; it needs no new runs.
- Record today's numbers before any change: they are the baseline every later step must beat.

### C2. The scalar speed for comfort

- √(|u|² + 2k) is the root-mean-square of the instantaneous speed. The time mean of the instantaneous speed, E|u|, is lower, and the difference is largest where the mean is small.
- C2 has two separate questions:
  1. what the validation's instruments read;
  2. which speed the criteria's thresholds assume.
- **Question 1 is already answered for the AIJ thermistor by F14** (`CLAUDE_WIND_EXPERIMENTS.md`, 2026-11-02, negative). The fast-half 9 % offset below is the new observation; the RMS-versus-mean finding is not new. The plan's earlier premise was that an omnidirectional sensor reads the time mean. The paired data contradict it.
  - At the 33 Case D 0° points, the split-fibre probe gives the mean vector and the three component variances.
  - Against the thermistor at the same points:

    | Split-fibre speed | Ratio to the thermistor | q | FB |
    |---|---|---|---|
    | RMS √(\|U\|² + 2k) | 0.95 | 0.91 | +0.06 |
    | E\|u\| (3D, Gaussian) | 0.88 | 0.85 | +0.13 |
    | E\|u_h\| (horizontal) | 0.85 | 0.82 | +0.16 |
    | Mean vector | 0.70 | 0.52 | +0.29 |

  - So the thermistor reads at or slightly above the RMS speed, not the time mean.
  - At the faster half of the points, even the RMS speed is 9 % below the thermistor. Part of every model's windy-point deficit against thermistor data is therefore instrument (C3, H3).
  - Caveats: 33 points, one direction, two separate experiments.
- **Question 2 stays open.** It is decided below.
- Add a mean-speed estimate: the expected |U| for a Gaussian velocity with the model's mean vector and k, split over the components as 2.4 : 1.9 : 1.25 in standard deviation (the surface-layer ratios behind the 5.5 u*² rule). Computed once per cell in Python; no native change.
- Choose the comfort comparator from the criteria's definitions (question 2), documented with sources. The validation comparator for thermistor data stays √(|u|² + 2k) (question 1). Report both estimates on Cases A, B, D and E and in C1, but do not choose by score.
- If the comparator changes, the comfort option gains it (for example `speed="scalar_mean"`) and `scalar_speed()` stays as it is.

### C3. Diagnose the windy-point bias

- Start from the review's attribution, made without runs (section 1.2): corner streams of the new tower (H1) dominate; over-sheltering (H2) is secondary.
- Take the windiest tenth of the Case E after probe-directions, and of Case D. Also take each model's own windiest tenth, because selecting on measured values alone biases every model towards "too slow" (the review, section 1.1).
- For each point, record:
  - the distance to the new high-rise and to the nearest wall;
  - whether it lies in a corner stream, a wake, a canyon or the open;
  - K for `wake=2` and `wake=3`;
  - D and k_w at the point;
  - the building whose wake (or cavity) sets D there.
- Separate the candidate causes with diagnostic runs of a scratch build (not committed, like the prototype; no environment switches in the product):
  - **H1, missing speed-up:** both codes too slow at the same points → the tower effect, corner streams or downwash.
  - **H2, over-sheltering:** `wake=3` much slower than `wake=2` at a point → run `wake=3` without the shelter factor, and with the deficit limited to the shadow (no lateral spreading), to see which part removes the speed.
  - **H3, comparator and instrument:**
    - A mean-speed comparator makes the tail 4–6 points worse (the review, section 1.3), so it cannot explain it.
    - The instrument offset can explain part of it: the thermistor reads 9 % above the split-fibre RMS at the faster Case D points (C2).
    - Quantify that share. No runs are needed.
  - **H4, direction thresholds:** the bias concentrates near ±10° from a face normal. Test the review's M7: Case E flank directions θ ± 5° (32 runs per state and wake code); compare centre and flank-averaged K without tuning.
  - **Retained cavity:** test overlap with E2's spurious-decrease group. Reuse its per-building attribution, ported to `prepareWake`/`applyWake`; distinguish cavity writes from the far-wake deficit. This is secondary to H1, not an alternative.
- Write the attribution (share of the windy-point bias per cause) to the results file. C4's remedy follows from it.

### C4. Remedy

Depends on C3; at most one remedy at a time, each with its own check.

| Finding | Remedy | Where |
|---|---|---|
| H2 dominates | Limit sheltering (for example, no shelter for buildings taller than the sheltering wake's top, or a cap on D in corner streams), from first principles; the A and B scores must not drop | `winds/SpreadingWake`, `applySpreadingWake` |
| H1 dominates | The tall-building zone F08 of `CLAUDE_WIND_EXPERIMENTS.md` (Gandemer/Wise literature constants, hypotheses H8a–H8c already declared; gate P0 passed on the research branch in E0d at four Case E after directions, maximum difference <6e-9; recheck on the current wake=3 fields. Run F13 before or alongside F08, on both wake codes), or the momentum route of `MOMENTUM_PLAN.md` | a separate plan; the switch waits for it |
| H3 dominates | The comparator from C2; any instrument share is reported, not remedied | Python only |
| H4 contributes | S3 of the Fabel review (continuous direction thresholds) | a separate plan |
| Any (a stopgap, independent of C3) | M2 as registered in section 10, measured alone against the C1 baseline | Python only (two solves per direction) |

**Gate for C4** (Cases D and E, 2 m, turbulence on, against the C1 baseline):
- at the windiest tenth of every case:
  - the mean speed is no further *below* the measured mean than `wake=2` vector's (corrected 2026-11-12, section 9; a candidate that is too fast there passes this part);
  - the share more than 20 % too slow is no larger;
- C1 (Case E, both states) on all three climate levels:
  - **comfort (D7):** T below zero, with the upper end of its 95 % interval below zero;
  - **safety (hard):** missed danger no more frequent than with `wake=2` vector (equal-sector climate);
  - exact agreement higher (equal-sector climate);
- the wake plan's section 6 gates still pass.

### C5. Independent confirmation

- Obtain the dataset of D4; build its geometry, inflow and probes in the harness (like `case_d`, `case_e`).
- Write its gates **before** the first run: the C4 gate's first two conditions (windiest tenth; C1), applied to this dataset, with no tuning on it. The third, the wake plan's gates, belongs to Cases A, B, D and E.
- If the dataset has fewer than 16 directions, C1's comfort test runs with the directions it has, and the windy-tail and pooled scores carry the decision.
- The D7 comfort gate's dominant-direction climates are defined over 16 directions. How they apply to this dataset (sectors, rotations, or not at all) is written with its gates, once its directions are known.

### C6. Policy qualification (`pedestrian-v2`)

- Recalibrate the adaptive policy on `wake=3` fields with the S7 tooling (`tools/run_solver_policy_study.py`, `calibrate_solver_policy.py`, `validate_solver_policy.py`, `publish_solver_policy.py`): calibration and held-out cases, thresholds, frozen workers and evidence, as in `docs/solver-control-s7.md`.
- `pedestrian-v2` accepts `wake_flag == 3`; `pedestrian-v1` stays frozen and selectable.
- If M2 is the outcome, an assessment needs both runs: the `wake=2` run stays under `pedestrian-v1`, and the `wake=3` run needs `pedestrian-v2`.
- Then re-qualify the native identity (`docs/solver-control-requalification.md`).

### C7. The switch

- `wind.run` default `Parameterizations(wake=3)` for the pedestrian path. Whether the general default also changes is a separate decision, taken at C7. `comfort.assess_results` default `speed` per criterion (D1); `Solver(policy=...)` default to `pedestrian-v2`.
- If M2 is the outcome, C7 also defines its product form: two runs per direction combined in Python, or the native single-solve candidate (section 10.5) if that has been confirmed by then.
- Re-baseline the feature-merge fixtures and the AIJ headline numbers; a migration note listing the expected class changes (C1's statistics on Case E) and how to restore the old behaviour (`wake=2`, `speed="vector"`, `pedestrian-v1`).
- Update `README.md`, `docs/spreading-wake.md`, `docs/wind-comfort.md`.

## 5. Rules

- **No fitting to the test cases.** Constants change only from first principles or Cases A and B; Cases D and E judge, C5 confirms.
- **Safety first.** A change that lowers optimistic misclassifications or missed danger is preferred over one that raises exact agreement.
- **One remedy at a time.** Each C4 change is measured alone against the C1 baseline before another is added.
- **Gates before runs.** C5's gates are written into this file before its first run.
- **Fixed weights.** The comfort-cost weight a_opt (D7) is never changed in response to a gate result. A change is recorded in D7, with its date and reason, before the next gated step is run.

## 6. Gates (summary)

| Step | Gate |
|---|---|
| C1 | Baseline recorded for five models (with M2), two states, three climate levels, the equal-sector and the 16 dominant-direction climates; tests pass |
| C2 | Comparator chosen and justified from instrument physics and the criteria, not by score |
| C3 | Windy-point bias attributed to causes, with the share of each |
| C4 | Windiest tenth no further below the measurements, and no more often more than 20 % too slow, than `wake=2` vector in any case; comfort cost (D7) lower than `wake=2` vector in the worst dominant-direction climate at every level (95 % interval below zero); no more missed danger; higher exact agreement; wake plan gates still pass |
| C5 | C4's first two conditions on the independent dataset, gates fixed in advance |
| C6 | `pedestrian-v2` qualified on calibration and held-out cases; native identity re-qualified |
| C7 | Fixtures re-baselined; migration note with Case E class-change statistics |

## 7. Risks

| Risk | Mitigation |
|---|---|
| C3 finds the tower effect (H1) dominant | The switch waits for the tower-effect work; `wake=3` stays the recommended opt-in for sheltered areas |
| No independent dataset (C5) | The switch waits. Case E alone is too thin, and C4 will have been judged on it. The Hamburg request is unsent and needs the user's authorization (D4) |
| The comfort result depends on the climate | Three declared climate levels and 16 dominant-direction climates per level (D3), gated in the worst one (D7) |
| Low-speed thermistor readings are uncertain | The windy-tail and comfort gates use the windy points and class boundaries; the low-speed bins are reported, not gated |
| C2 changes the level everywhere | C2 precedes C4, so C4's remedy is judged with the final comparator |
| The default change moves every result | C7 is a separate step with a migration note and the old behaviour one argument away |

## 8. Done when

- C1's comfort-class test and the windy-tail report are part of `validation/run_wake_validation.py`, with tests;
- the comfort comparator is decided and documented (C2);
- the windy-point bias is attributed (C3), and either remedied (C4) and confirmed (C5), or the switch is recorded as waiting for the named work (the tower effect, a dataset);
- if confirmed: `pedestrian-v2` is qualified (C6) and the defaults are switched with a migration note (C7).

## 9. Progress

Each step's outcome, in order.

- **Execution (2026-11-13):** C1 now runs through `comfort.assess`, including M2 and a Gaussian mean sensitivity estimate. Discrete climate levels match D3. M2 fails D7 at four of six levels and fails safety at Case E after 7.75 m/s. The E2 cavity stratum overlaps 15 of 135 windy pairs. Full results and the remaining C2–C7 dependencies are in [the execution report](validation/WAKE_COMFORT_RESULTS.md). The following review entries remain the historical pre-C1 record.

- **Review (2026-11-12).**
  - `WAKE3_COMFORT_DEFAULT_PLAN_REVIEW.md`, from the stored W4 runs; no new runs.
  - Decided:
    - D6: no separate comfort and safety estimators; a future option, section 11;
    - D7: option A, a comfort cost with a_opt = 3, linear, gated in the worst dominant-direction climate; added to D3, C1 and C4;
    - D8: M2 registered, section 10.
  - Adoption: P3 and P4 adopted; P1, P6, P7 and P9 partly adopted; P2, P5 and P8 not adopted. D7 supplies the declared cost instead of P2's iso-risk comparison.
- **End-to-end check (2026-11-12).** Every assumption was checked against the code, the stored runs and the referenced documents; no new runs.
  - **Verified:**
    - `pedestrian_policy.cpp` requires `wake_flag == 2` (line 44), and W6 records why a switch needs a new study;
    - the wake constants (0.2, 0.22, 0.9, 0.08) are those of the wake plan;
    - `K_scalar_wake_rule` is the run's default 5.5 u*² scalar speed, sampled exactly like K (`aij/runner.py`, `_wake_scalar`);
    - the S7 tools and documents named in C6 and C7 exist, and so does `validation/tests/test_wake.py`;
    - the NEN 8100 classes and the class indexing match `comfort.py`;
    - the section 1 figures match the results;
    - M2's K₀ equals the run profile's value at every AIJ evaluation height (section 10.1).
  - **Fixed:**
    1. The tower-effect reference was wrong. F08 is in `CLAUDE_WIND_EXPERIMENTS.md`, not `MOMENTUM_PLAN.md`. It is a designed, not-yet-run tall-building zone with literature constants, and it is now the named H1 remedy in C4. `MOMENTUM_PLAN.md` and the Fabel review are not on this branch; they are in the main checkout.
    2. "Review S3" became ambiguous once "the review" meant this plan's review. It now names the Fabel review.
    3. C2's premise, that an omnidirectional sensor reads the time mean, was contradicted by the paired Case D instruments: the thermistor reads at or above the RMS speed. C2 now separates the instrument question (answered) from the criteria question (open). C3's H3 gains the instrument offset.
    4. D3 did not declare the Weibull shape, the rule for the three levels, or how the climate becomes hours for `comfort.assess`. Now specified, and D3's sentence that a real climate "would only add a frequency weighting" is corrected.
    5. **C4's windiest-tenth condition read "no more optimistic than `wake=2` vector".** In Case E before, `wake=2` is 28 % too *fast* at those points. The wording therefore failed any candidate that came closer to the measurements: `wake=3` scalar (+6 %) and M2 (+14 %) failed for being more accurate. It now measures under-prediction only. The "share more than 20 % too slow" part is unchanged.
    6. C1 lacked two outputs that M2's registered predictions need: the mean absolute class error, and the Spearman correlation of the per-probe log exceedance. Both added. The bootstrap seed is fixed.
    7. C4 applied C1's conditions to "Cases D and E", but C1 runs on Case E only. Clarified, and safety and exact agreement are stated to use the equal-sector climate.
    8. C5 required "the C4 gate's three conditions", but the third (the wake plan's gates) belongs to Cases A, B, D and E. It now requires the first two. The D7 gate needs 16 directions, so its form for C5 is fixed with C5's gates.
    9. D4 now records the Hamburg status: the request is unsent and needs the user's authorization; Michelstadt is still untouched.
    10. C6 and C7 now cover M2: an assessment uses both policies, and its product form is decided at C7. Section 10.5 notes that M2's `wake=3` run is unqualified until C6. C7's general-default question no longer points at D1.
  - **Consequence on the stored data (exploratory).** Even with fix 5, M2 fails the windiest-tenth share condition:
    - Case E before: 13 % against 4 %;
    - Case E after: 34 % against 27 %;
    - Case D: 80 % against 80 %, a pass.

    M2 also fails the D7 comfort gate in Case E after at all three levels and in Case E before at 9.25 m/s. It fails the hard safety gate in Case E after at 7.75 m/s (3 of 20 missed, against 2 of 20). As planned, the switch waits for the tower effect (H1) and an independent dataset.

## 10. Registered candidate: M2, speed-up preservation

Registered on 2026-11-12, before C1. It comes from the review, section 3, M2.

- The rule below is fixed.
- Any change to it, its inputs or K₀ makes a new candidate with a new name, and that candidate's evidence starts from nothing.
- No parameter may be tuned on any case.

### 10.1 Rule

For each point at the evaluation height z and each direction:

```
K_M2 = max(K_2, K_3s)   where K_2 > K_0(z)
K_M2 = K_3s             elsewhere
```

- **K_2:** the magnitude of the mean velocity over U_ref, from the run with the default `Parameterizations()` (`wake=2`).
- **K_3s:** the scalar speed √(|u|² + 2k) over U_ref, from the run with `Parameterizations(wake=3)`.
  - The two runs are otherwise identical: city, grid, profile, direction, solver and turbulence settings.
  - k uses the default inflow k: 5.5 u*², `scalar_speed()` without `inflow_tke`. In the validation records this is `K_scalar_wake_rule`.
- **K_0(z):** U_in(z) / U_in(z_ref), the run's inflow profile speed at z over its speed at the reference height.
  - In the validation, from the case's inflow table, interpolated linearly in log height.
  - In the product, from the declared profile.
- **U_ref:** the run's reference speed, the same in both runs.
- **Further conditions:**
  - K_2 and K_3s are sampled the same way: the probe records' sampling in the validation, and `result.sample(z, method)` with one method for both in the product.
  - The comparison K_2 > K_0 is strict.
  - A NaN in either input gives NaN.
  - The rule is applied per point and direction, before any aggregation over directions or climate.
- **Fitted constants:** none.
- **Verification note (2026-11-12, not a change).** The run's profile is the primary definition of K_0; the table interpolation is how the validation computes it.
  - At 2 m, every AIJ evaluation height lies inside its inflow table (the lowest points are 1, 0.8, 2 and 1.25 m for A, B, D and E).
  - The table interpolation equals the run profile's `evaluate` there: K_0 = 0.654 (A), 0.610 (B), 0.575 (D), 0.750 (E).
  - Below a table's lowest point the run's profile, with its log tail, governs.

### 10.2 Basis

- Where the solve without the spreading wake accelerates the flow above the approach speed, the air comes from flow diverted around or over obstacles, not out of a wake. The shadow deficit D should not slow it below that.
- Everywhere else the spreading wake's evidence (the wake plan) holds.
- M2 does not add the missing tower effect. It only keeps the speed-up pattern that `wake=2` already has.

### 10.3 What has already been seen

- M2 was designed after looking at the windiest points of Case E after (the review, section 1.2).
- It was then evaluated on Case E before and after, Case D, and Cases A and B (the review, sections 1.1, 1.4 and 1.8).
- **No existing case can therefore confirm it.** On those cases its results are exploratory. Only C5's dataset can confirm it.
- Exploratory results on the stored runs, against `wake=2` vector:
  - Case E after: r 0.60 (0.46); windy tail by measured −10 % (−11 %);
  - exact class agreement +9 to +15 points;
  - missed danger 3 / 20 (2 / 20);
  - Case D windy tail −36 % (−42 %);
  - Cases A and B: q 0.877 and 0.876 (gates 0.83 and 0.86).

### 10.4 Expected outcomes

These are registered predictions, not gates. A failure of any of them is reported. C4's and C5's gates decide.

Against `wake=3` scalar:
1. the windiest tenth, selected by measured value, is less negative;
2. missed danger is no higher.

Against `wake=2` vector:

3. the mean absolute class error is lower;
4. exact class agreement is higher;
5. Spearman of the per-probe log exceedance is higher.

### 10.5 Cost and form

- **Cost:** two prepared models (parameterizations are fixed at preparation) and two solves per direction (`wake=2` and `wake=3`). The merged default stop rule uses 150–175 versus 200–225 sweeps: about 2.3 times the wake=2 solve cost, plus the second preparation. It is Python only, with no native change and no effect on the policy identity. Its `wake=3` run is still `unqualified_model_settings` under the adaptive policy until C6.
- **If M2 survives C5:** a native single-solve form (the review's M3, a downwash exemption in the spreading wake) is a separate candidate, with its own registration.

## 11. Future options

### Separate estimators for comfort and safety (the review's M1)

Not implemented (D6, 2026-11-12). Recorded so that it can be taken up later.

- **What it is:**
  - comfort from the best-estimate field (`wake=3` scalar, or M2);
  - safety from the envelope max(K_2, K_3s), per point and direction.
- **Why it is attractive:**
  - Exceedance never decreases as K rises, so the envelope's classes are never better than today's default's.
  - Missed danger can therefore never exceed `wake=2`'s, on any dataset or climate.
  - On the stored Case E after runs it kept missed danger at 2 / 20, gave 45–46 % exact comfort agreement (against 31 %), and had the lowest asymmetric cost (the review, sections 1.4 and 1.7).
- **Cost:**
  - two solves per direction;
  - a second speed option in `comfort.assess_results`;
  - comfort and safety maps that come from different fields, which must be explained to users.
- **When to revisit:**
  - if no single-field candidate passes C4's safety gate;
  - or if the tower-effect work (H1) is delayed and a default switch is still wanted.
- **Evidence:** C1's stored runs already contain everything needed to recompute it. It needs no new runs.

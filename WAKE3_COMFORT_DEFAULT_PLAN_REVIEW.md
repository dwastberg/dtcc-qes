# Review of WAKE3_COMFORT_DEFAULT_PLAN.md

- **Date:** 2026-11-12
- **Reviewed against:** `209ce15` (branch `feat/wake-update-v2`).
- **Data:** the stored W4 runs in `validation/output/runs` (build `2387533`, 2 m, turbulence on). **No new runs were made.** Every number below comes from exploratory scripts over those records, outside the repo. They are indicative only; C1 should rebuild them properly in `validation/run_wake_validation.py`.
- **Abbreviations:** w2v = `wake=2` vector speed (today's default); w3s = `wake=3` scalar speed with the default 5.5 u*² inflow k (`K_scalar_wake_rule`); m = measured.
- **Decisions taken (2026-11-12):**
  - D6: M1 is not implemented, and is kept as a future option (plan, section 11).
  - D8: M2 is registered (plan, section 10).
  - D7: option A, with a_opt = 3, linear in class steps, gated in the worst dominant-direction climate (plan, D7, C1 and C4; section 4.1 here).

## Verdict

The plan has the right shape: the comfort-class test comes first, gates are written before runs, and nothing is fitted to D or E. Three things should change before C1 starts.

1. **The windy-tail statistic behind the plan is biased.**
   - It selects the windiest 10 % of points by their *measured* value. With r ≈ 0.5, any model then looks too slow at those points. This is regression to the mean.
   - Selected the other way, by the model's own windiest 10 %, every model is too fast in Case E after: w3s +11 %, w2v +21 %.
   - Compared without pairing (the 90th percentile of each distribution), w3s is −6 % and w2v +16 %.
   - So in Case E after, w3s does not have the wrong speed level at windy points. It puts the windy points in the wrong places, mainly because the new tower's corner streams are not modelled. w2v passes the plan's C4 gate largely because it is too fast everywhere.
2. **The comfort-class test already separates comfort from safety.** I ran a first version of C1 on the stored runs.
   - w3s gives clearly better comfort classes. The mean class error falls by 0.24–0.90 classes, and the bootstrap confidence interval excludes zero at all six climate levels.
   - w3s is much worse on safety. At the windiest climate it misses 15 of 20 danger probes, against 2 of 20 for w2v.
   - So one field does not have to serve both purposes. Comfort and safety can come from different estimators.
3. **Two balancing methods with no fitted constants look promising on Cases D and E, and A and B do not object.**
   - The **envelope for safety**, max(w2v, w3s). It can never miss more danger than today's default, on any dataset or climate.
   - **Speed-up preservation:** use w3s, except where w2v is faster than the approach flow; there use the larger of the two.
   - Combined (preservation for comfort, envelope for safety), they have the lowest asymmetric cost of everything tested in Case E after.
   - **Decided:** speed-up preservation (M2) is registered and enters C1. The envelope (M1) is a future option only (D6).

## 1. What the stored runs already show

### 1.1 The windy tail, selected both ways

Bias = mean simulated / mean measured − 1 over the selected decile. "Unpaired q90" is the 90th percentile of the simulated distribution over that of the measured one.

| Case | Model | Top decile by measured | Top decile by simulated | Unpaired q90 | r |
|---|---|---|---|---|---|
| E after | w2v | −11 % | +21 % | +16 % | 0.46 |
| E after | w3s | −25 % | +11 % | −6 % | 0.56 |
| E after | speed-up preservation | −10 % | +21 % | +16 % | 0.60 |
| E after | envelope | −7 % | +21 % | +16 % | 0.53 |
| E before | w2v | +28 % | +75 % | +51 % | 0.51 |
| E before | w3s | +6 % | +53 % | +30 % | 0.55 |
| D | w2v | −42 % | +12 % | −11 % | 0.43 |
| D | w3s | −43 % | −10 % | −31 % | 0.55 |
| D | speed-up preservation | −36 % | +12 % | −11 % | 0.54 |

- **Case E after:** the two selections disagree in sign, so the −25 % is mostly a ranking problem. The windy points are in the wrong places; the level is not systematically low.
- **Case D:** w3s is too slow by every measure. That is a real deficit in level, and it matches the missing tower effect.

### 1.2 Where the windy points of Case E after are (the C3 attribution, without runs)

The probe-directions are classified by their position relative to the 60 m tower, in wind-aligned coordinates. The zones are rough geometry, not flow analysis.

| Zone | Windy-decile points | Measured K change from the tower | Simulated change, w3s / w2v | Windy points: w3s / w2v vs measured | D at windy points (before → after) |
|---|---|---|---|---|---|
| Beside the tower (corner streams) | 78 of 135 | **+0.245** | +0.055 / +0.078 | −22 % / −6 % | 0.25 → 0.35 |
| Tower wake | 25 | +0.092 | +0.010 / **−0.125** | −33 % / −55 % | 0.14 → 0.83 |
| Beside the tower wake | 24 | +0.084 | +0.003 / +0.002 | −26 % / −9 % | 0.21 → 0.36 |

The percentages are geometric-mean ratios.

- **H1, the missing tower effect, dominates.**
  - The models capture only 22 % (w3s) and 32 % (w2v) of the measured corner-stream speed-up.
  - In the tower's wake the measured speed *rises*. w2v predicts a fall, and w3s no change.
- **H2, over-sheltering, is real but secondary.**
  - At the windy corner points, w3 vector / w2 vector is 0.73.
  - D there is 0.35. Most of it comes from upstream low-rise wakes (0.25 before the tower existed); about 0.1 is added by the tower's own shadow.
  - By D band, over the windy decile:

    | D band | w3s vs measured | w2v vs measured |
    |---|---|---|
    | 0.2–0.5 | −21 % | 0 % |
    | > 0.5 | −35 % | −41 % |

    The 0.2–0.5 band is the clean H2 signature. Above 0.5, both models fail: those are misplaced wakes, which is H1 again.
- **The physical reading.** Near a tall building in a low-rise district, the air at pedestrian level comes down from about 0.6–0.7 H. That is above every low-rise wake. Applying the low-rise deficit D to the background there removes momentum that the downwash would bring.

### 1.3 The C2 comparator cannot fix the windy tail

I computed E|u| for a Gaussian with the model's mean and k, split over the components as 2.4 : 1.9 : 1.25.

| Case E after | Pooled FB | Windy tail (by measured) |
|---|---|---|
| √(\|U\|² + 2k), today | −0.05 | −25 % |
| E\|u\|, 3D | +0.02 | −29 % |
| E\|u_h\|, horizontal | +0.06 | −31 % |

- A mean-speed comparator moves the windy tail by 4–6 points in the wrong direction. So H3 can be closed now.
- C2 should still be decided on instrument physics, as the plan says. It just has to be expected to make the windy-point deficit slightly larger.
- One point to settle in C2: the instruments behind comfort thresholds do not all read E|u|. Irwin sensors respond roughly to the square of the speed, so they read close to the RMS speed. Thermistors have a non-linear cooling law, and cups over-speed in turbulence.

### 1.4 An exploratory C1

Setup:
- Weibull shape 2 at the reference height, 16 equal sectors.
- Scales chosen so the median measured class is B, C and D.
- NEN 8100 classes per probe, aggregated over directions.

| Case E after, c = 7.75 m/s | Exact | Optimistic | Mean class error | Missed danger | False alarms |
|---|---|---|---|---|---|
| w2v | 31 % | 2 % | +1.18 | 2 / 20 | 19 |
| w3 vector | 30 % | 50 % | −0.30 | 20 / 20 | 0 |
| w3s | 45 % | 11 % | +0.54 | 15 / 20 | 0 |
| w3s, neighbourhood max | 42 % | 2 % | +0.91 | 13 / 20 | 3 |
| geometric mean (w2v, w3s) | 40 % | 9 % | +0.76 | 8 / 20 | 4 |
| speed-up preservation | 46 % | 6 % | +0.70 | 3 / 20 | 16 |
| envelope | 34 % | 0 % | +1.27 | 2 / 20 | 19 |

- **w2v is very conservative.**
  - Its mean class error is +1.2 to +1.3 classes in Case E after and +1.6 to +2.4 in E before.
  - Its exact agreement is 1–31 %.
  - Its good safety record is paid for with that bias.
- **w3s:**
  - It discriminates best: AUC for "class ≥ D" 0.83–0.93 against 0.79–0.88, and Spearman 0.70–0.71 against 0.58–0.64.
  - Its comfort level is closer to the measurements.
  - Its safety is worst.
- **Three probes are missed by every model.** At c = 5.6 m/s, all three measured-danger probes are missed. That is the H1 floor that no estimator here reaches.

Probe bootstrap (4000 resamples, 95 % CI), each model's difference from w2v:

| Case E after, c = 7.75 | Exact | Optimistic | \|class error\| | Missed danger (share of probes) |
|---|---|---|---|---|
| w3s | +14 pp (+3, +25) | +9 pp (+4, +15) | −0.46 (−0.61, −0.31) | +16 pp (+9, +25) |
| speed-up preservation | +15 pp (+5, +25) | +4 pp (0, +9) | −0.40 (−0.54, −0.26) | +1 pp (0, +4) |

- With 80 probes, differences of about 5–8 points in shares cannot be resolved.
- The safety counts (3, 7 and 20 measured-danger probes) are very small.

### 1.5 Bias against discrimination

Sweeping a constant factor on K (0.70–1.80) separates the two.

**Margin needed for at most 5 % optimistic misclassifications:**

| Model | E before | E after |
|---|---|---|
| w2v | 0.70–0.72 | 0.96–1.02 |
| w3s | 0.88–0.90 | 1.04–1.20 |

- For both models the margin shifts by about 0.3 between the two states of the *same site*.
- **A constant margin calibrated on one case will not transfer.** The bias depends on the scene, here the tower.

**Best exact agreement over all margins (bias removed):** w2v 39–52 %, w3s 35–52 %, speed-up preservation 42–52 %.

- At each climate level the models are within 9 points of each other.
- The physics differences show up mostly in the level, not in the ranking.
- Better ranking needs H1: put the windy points in the right places.

### 1.6 Directional climates change the picture

The test puts 30 % of the hours in one sector, spreads the rest evenly, and rotates that sector over all 16 directions. Case E after, c = 6.5:

| Model | Optimistic: equal sectors | Optimistic: worst rotation | Missed danger: worst rotation |
|---|---|---|---|
| w2v | 6 % | 8 % | 67 % |
| w3s | 21 % | **38 %** | 100 % |
| speed-up preservation | 9 % | 20 % | 67 % |
| envelope | 5 % | 5 % | 67 % |

- Equal sectors average the errors of individual directions away.
- A real site has a dominant sector, and the worst rotation nearly doubles the optimistic share of the single-field estimators.
- Sensitivity: the median measured probe is 11–13 % in K from the next worse comfort class. A 10 % error in K therefore moves about half the classes.

### 1.7 An example of asymmetric cost

The costs below are an example only:
- optimistic: 3 per class;
- conservative: 1 per class;
- missed danger: 10;
- false alarm: 1.

Mean cost per probe:

| | E before (3 levels) | E after (3 levels) |
|---|---|---|
| w2v | 2.45 / 2.48 / 2.46 | 1.96 / 2.10 / 1.76 |
| w3s | 1.51 / 1.48 / 1.80 | 1.71 / 2.24 / 2.86 |
| speed-up preservation | 1.76 / 1.79 / 1.99 | 1.52 / 1.73 / 1.52 |
| w3s for comfort + envelope for safety | 1.55 / 1.80 / 2.25 | 1.71 / 1.90 / 1.48 |
| speed-up preservation for comfort + envelope for safety | 1.76 / 1.90 / 2.24 | 1.52 / 1.74 / **1.44** |

- w3s alone costs more than w2v in Case E after at the two windier climates, because of missed danger.
- Both combined estimators cost less than w2v at all six settings.

### 1.8 Cases A and B (q / R at the 2 m probes, against the scalar target)

| | A | B |
|---|---|---|
| w2v | 0.785 / 0.883 | 0.535 / 0.822 |
| w3s | 0.877 / 0.923 | 0.907 / 0.910 |
| speed-up preservation | 0.877 / 0.905 | 0.876 / 0.893 |

- Speed-up preservation keeps the A and B gates (≥ 0.83 and ≥ 0.86).
- The margin for B is small, because w2 over-predicts beside B's upwind corners (`AIJ_AB_VALIDATION.md`).

## 2. Problems with the plan's tests, and fixes

| # | Problem | Fix |
|---|---|---|
| P1 | The windy tail is selected on measured values only (section 1.1). The C4 gate built on it rewards the model that is too fast everywhere. | Report the tail selected **both ways** and **unpaired** (q90, q95), plus a per-probe *governing speed* (below). Gate on the two-sided, unpaired form. |
| P2 | The C4 gate compares against w2v, which is +1.2 to +2.4 classes conservative. "No worse than the default at the windy points" then asks the new model to share the default's bias. | Gate on **iso-risk** comparisons: at the margin where both models have the same optimistic rate (or missed danger), the new model's exact agreement must be higher. Keep a hard safety constraint (P6). |
| P3 | Most scores pool probe-directions, but classes are decided per probe over all directions. | C1 runs `comfort.assess` itself, on a **deterministic quantile climate**: per sector, n hours at the Weibull quantiles (i − ½)/n. No random numbers, and the product's code path. |
| P4 | Equal sectors (D3) hide errors in individual directions (section 1.6). | Add **rotated directional climates** (one sector at 30 %, rotated over 16). Gate the optimistic share on the worst rotation, not only the mean. |
| P5 | Safety is degenerate at the D3 levels: Case E before has 0–1 danger probes. Counts of 3–20 have no power. | Choose safety climate levels separately, so the measurements have at least about 15 danger probes. Add a **continuous** safety metric: the per-probe speed exceeded 0.05 % and 0.3 % of hours (`speed_at_exceedance`), as a log ratio to measured, for bias and spread. Do the same at 2.5 % and 20 % for comfort. |
| P6 | Gates are point comparisons on 80 probes. | **Non-inferiority with a probe-bootstrap CI** and declared margins (section 4). |
| P7 | C3 plans scratch-build runs for four hypotheses. H3 is closed (section 1.3), and the H1/H2 split can be made from the stored data (section 1.2). | C3 starts with the zone and D-band attribution (no runs). Use runs only to split H2 into shelter factor, lateral spread and δ-widening. H4 is tested with ±5° flank runs (section 3, M7). |
| P8 | Case E before and after share the probes and the site, so they are not independent. Section 1.5 shows a margin does not even transfer between them. | Any statistical calibration (margins, error spreads) is fitted across cases (A, B, D, E before), tested on E after, and confirmed on C5. |
| P9 | The metrics do not separate ranking from level. | Report three layers for every model: **discrimination** (AUC for class ≥ C, class ≥ D and danger; Spearman of per-probe log exceedance; best exact agreement over margins), **calibration** (bias by regime, margin needed), **decision** (confusion matrix at the declared operating point). |

**The governing speed (P1).**
- A probe's comfort class depends on its directions through the exceedance sum. For safety, that sum is dominated by the windiest direction.
- So the windy-point test should compare, per probe, the speed at the comfort and safety exceedance fractions. Probe-directions selected by their measured value are the wrong sample.
- This is the same continuous metric as in P5, so one statistic serves both.

## 3. Methods to balance over- and under-prediction

They are ordered by readiness. M1 and M2 need no native change.

### M1. Separate estimators for comfort and safety (not implemented, a future option: D6)

- **Comfort:** the best-estimate field (w3s, or M2).
- **Safety:** the envelope max(w2v, w3s).
- **Why the envelope is safe.**
  - The exceedance never decreases as K rises, in every direction.
  - So a cell's class can never be better than its w2v class.
  - Missed danger and optimistic safety classes are therefore never worse than today's default. That holds on every dataset and in every climate, by construction, not statistically.
- **Evidence (Case E after, c = 7.75):**
  - missed danger 2 / 20, the same as w2v;
  - comfort exact agreement 45–46 % instead of 31 %;
  - lowest asymmetric cost (section 1.7).
- **Cost:** two solves per direction. The second can be warm-started from the first's Lagrange multiplier, so it needs fewer iterations.
- **Product (a possible API):** `comfort.assess_results(..., speed="scalar", safety_speed="envelope")`, or two result sets per direction.
- **What it does not do.** It does not make safety more *accurate*; w2v still misses the corner streams. It makes the switch safe against today's behaviour while comfort improves.
- **Effect on the decisions:** it changes D1 (section 4).

### M2. Speed-up preservation (registered: plan, section 10)

- **Rule (the plan's section 10 is the binding text):** K = w3s, except where w2v > K₀(z); there K = max(w2v, w3s). K₀ is the approach-flow speed at the evaluation height over the reference speed, taken from the inflow profile.
- **Fitted constants:** none.
- **Physical argument:** where the plain mass-consistent solution accelerates the flow above the approach speed, the air comes from flow diverted around or over obstacles, not out of a wake. A deficit taken from the shadow geometry should not slow it below that.
- **Evidence:**
  - Case E after: r 0.60 (the best), windy tail −10 %;
  - exact agreement above w2v at all six Case E climate levels (the CI excludes zero at five and touches it at one);
  - missed danger as w2v (3 / 20 against 2 / 20);
  - Case D: windy tail −36 %, against −42 % and −43 % for its parents;
  - Cases A and B keep their gates.
- **Caveat: I designed it after looking at Case E after's windy points.** Until D, A, B and C5 confirm it, it is a hypothesis, and it must be pre-registered now.
- **What it does not fix:** it only recovers w2's speed-up pattern. It does not add the missing tower effect.

### M3. Downwash exemption (the physics behind M2, native)

- **Trigger:** a building whose height H is more than about 2 h̄, the local mean height.
- **Zone:** its upwind standing vortex, its corner streams and its near wake.
- **Rule inside the zone:** do not apply the D of any building lower than the stagnation height z_s ≈ 0.6–0.7 H. Also, do not apply the building's own lateral shadow upstream of its lee wall.
- **Constants:** z_s comes from first principles. The zone sizes come from Cases A and B. Nothing is fitted to D or E.
- **Test:** the scratch build of C3. This is the H2 remedy of C4, specified.

### M4. A tower-effect model (H1)

- The measured corner speed-up is +0.245; the models give +0.06 to +0.08 (section 1.2). This is the main lever for safety accuracy, and the only one for the three probes that every estimator misses.
- **A possible form:** in the corner zones of a building that is tall relative to its surroundings, set the initial horizontal speed to the approach speed at z_s, as Bernoulli suggests for downwash. Then let the mass-consistent solve distribute it.
- **The isolated case is different.** Case B shows that w2 *over*-predicts corner speeds beside an isolated low building. The model must therefore be switched on by the height contrast.
- **Constants:** Cases A and B constrain the isolated limit. The contrast term has no data in A and B and must come from first principles.
- **Where:** this is F08 of `CLAUDE_WIND_EXPERIMENTS.md`, already designed with literature constants (Gandemer, Wise) and not yet run. The other route is the momentum route of `MOMENTUM_PLAN.md`. (Corrected 2026-11-12: F08 is not in `MOMENTUM_PLAN.md`.)

### M5. Probabilistic classes

- Treat the model error in log K as normal, with a spread that depends on the regime: open, wake (D band), corner, canyon.
- Because the exceedance never decreases as K rises, P(class) per cell follows directly from that distribution.
- **Decision rule:** declare a probability threshold, and set it from the cost ratio (for example, flag danger when P ≥ 10 %).
- **Scoring:** the ranked probability score.
- **Calibration:** across cases (P8). Mondrian conformal prediction is the distribution-free alternative, but it needs exchangeable calibration data, which only C5 can supply.
- **Output:** maps that say "class C, 30 % chance of D" instead of a false certainty. This is the natural long-term form of M1.

### M6. A declared cost matrix as the balancing score

- Fix the costs before C1, as in section 1.7: how much worse an optimistic error is than a conservative one, and how much worse a missed danger is than a false alarm.
- Report the cost beside the component gates. This turns the question of balancing into one declared number. The weights are a policy decision for the user (D7).

### M7. Flank-direction averaging

- A sector of the climate covers ±11.25°, not one direction.
- Averaging the exceedance over runs at θ − 5°, θ and θ + 5° removes the ±10° threshold artefacts (H4) from the product without a native change.
- Test on Case E with 32 flank runs, about 4 minutes. The flank runs could also be made at 4 m.

### M8. Neighbourhood max as a flag, not a value

- It moves the level (Case E after: tail −20 % instead of −25 %, missed danger 13 / 20), but its AUC equals w3s's. It does not rank better.
- Use the span K_max − K_min as a "sharp gradient, low confidence" flag on the map instead.

**Not recommended:**
- the geometric mean of the two fields: it misses all 7 danger probes at c = 6.5;
- a single global margin: it does not transfer (section 1.5);
- the envelope for comfort: it is as conservative as w2v.

## 4. Proposed changes to the plan

- **D1:**
  - NEN 8100 comfort and safety from one field: w3s, or M2 if it survives C5 (D6).
  - `CITY_OF_LONDON` as in the plan.
- **D3:**
  - Keep the three equal-sector levels.
  - Add the rotated directional climates (P4).
  - Add separate safety levels (P5).
  - Use the deterministic quantile climate through `comfort.assess` (P3).
- **New decisions:**

  | # | Question | Recommendation |
  |---|---|---|
  | D6 | Separate comfort and safety estimators (M1), at twice the solves per direction? | **Decided: no.** A future option (plan, section 11). |
  | D7 | The cost matrix (M6). | **Decided: option A** (section 4.1): a_opt = 3, linear, safety as a hard gate, worst dominant-direction climate. |
  | D8 | Pre-register M2 now? | **Decided: yes.** Registered in the plan, section 10. |

- **C1:**
  - **Models:** add M2 as registered (done in the plan).
  - **Metrics:**
    - the three layers of P9;
    - the tail both ways plus the governing speed (P1);
    - bootstrap CIs (P6);
    - the asymmetric cost (M6).
  - It still needs no new runs.
- **C2:** unchanged. Add the expectation from section 1.3.
- **C3:**
  - Start from the attribution in section 1.2.
  - Close H3.
  - Run the scratch build only to split H2 (shelter factor, lateral spread, δ-widening beside the tower).
  - H4 via M7.
- **C4:**
  - **Candidates, in this order:**
    1. M2, as registered, in Python only;
    2. M3, the native form of M2;
    3. M4, in a separate plan.
  - **Gate** (Cases D and E, every climate level and rotation):
    1. **Safety (hard):** missed danger no higher than w2v's. The upper 95 % CI of the difference must be ≤ +2.5 points of the probes, and the continuous safety-speed bias at the measured-danger probes no worse. Since D6 rules out M1, every candidate must meet this with a single field.
    2. **Comfort accuracy:** mean |class error| lower than w2v's, with the 95 % CI excluding zero.
    3. **Comfort optimism:** optimistic share ≤ w2v's + 5 points with equal sectors, and + 10 points in the worst rotation. Tighten these margins if D7 weights optimism heavily.
    4. **Discrimination:** Spearman of per-probe log exceedance ≥ w2v's.
    5. **The level at windy points, two-sided:**
       - the unpaired q90 within ±15 %;
       - at the model's own windiest decile, no slower than −10 %;
       - the per-probe governing-speed bias no lower than w2v's less 5 %.
    6. The wake plan's section 6 gates still pass.
  - On the stored Case E after data, M2 alone:
    - passes gates 2, 4 and 6;
    - does not demonstrate gate 1: missed danger is +1 point (CI 0 to +4), so the upper bound exceeds +2.5;
    - narrowly fails gate 3: +3 to +6 points with equal sectors, and +12 in the worst rotation;
    - gate 5 was only partly computed: the unpaired q90 is +16 %, just outside ±15 %, and the governing speed was not computed.
  - Either the remedies get better, or D7 decides how much optimism the accuracy gain is worth.
- **C5:** pre-register M1 and M2 and the revised gates before the first run, as the plan's rules require.
- **C6 and C7:** one field for comfort and safety (D6): w3s, or M2 if it survives C5. M1 is a later, separate decision.

### 4.1 D7: the cost matrix

**Decided 2026-11-12: option A.**
- a_opt = 3, linear in class steps.
- Gated in the worst of the 16 dominant-direction climates, at every climate level.
- Safety stays a hard gate.
- The binding text is in the plan (D3, D7, C1 and C4). The explanation that led to the decision follows.

**What the decided gate gives on the stored runs** (exploratory, not C1's baseline).
- T is the worst-rotation mean cost difference from w2v; negative is better. The 95 % interval comes from the probe bootstrap.
- Pass means the upper end of the interval is below zero.

| Case E | Level c (m/s) | w3s: T (interval) | M2: T (interval) | w3s, M2 with equal sectors |
|---|---|---|---|---|
| before | 6.75 | −0.82 (−0.89, −0.64) pass | −0.71 (−0.76, −0.54) pass | −0.90, −0.69 |
| before | 7.80 | −0.34 (−0.45, −0.16) pass | −0.34 (−0.40, −0.21) pass | −0.68, −0.57 |
| before | 9.25 | −0.16 (−0.20, +0.01) fail | −0.11 (−0.17, +0.04) fail | −0.21, −0.23 |
| after | 5.60 | +0.14 (−0.19, +0.64) fail | −0.28 (−0.41, +0.06) fail | −0.25, −0.44 |
| after | 6.50 | +0.51 (+0.10, +0.95) fail | +0.04 (−0.23, +0.36) fail | −0.20, −0.36 |
| after | 7.75 | +0.04 (−0.15, +0.38) fail | −0.09 (−0.24, +0.23) fail | −0.29, −0.33 |

- **With equal sectors,** both candidates cost less than w2v at every level.
- **In the worst dominant-direction climate of Case E after,** neither demonstrates it.
  - w3s is worse than w2v in that climate at all three levels.
  - M2 is better at two levels of three, but no interval excludes zero.
  - `wake=2` with the inflow k fails everywhere (T between +0.15 and +0.39), and so does `wake=3` vector.
- **The gate is demanding.**
  - The intervals in Case E after are 0.4–0.9 cost units wide with 80 probes.
  - Taking the maximum over 16 rotations inside each bootstrap resample biases the interval upwards, which makes the gate stricter still.
  - On this evidence, a switch needs a clear gain at the windiest probes in their governing direction, which points again at the tower effect (H1).

**What it is.** A rule, fixed before C1, that gives each kind of error a cost. "Better" then means "lower mean cost per probe". There are four error kinds:

| Error | Unit | Weight |
|---|---|---|
| Comfort class too optimistic (the model says more comfortable than measured) | per class step | a_opt |
| Comfort class too conservative | per class step | 1 (the unit) |
| Missed danger (measured limited risk or dangerous, model says no risk) | per probe | c_miss |
| False alarm (measured no risk, model says risk) | per probe | c_false |

- Only the ratios matter, so a conservative class step is the unit.
- a_opt = 3 means that one probe one class too optimistic is as bad as three probes each one class too conservative.

**Why it is needed.** Every gate already sets these weights, only implicitly.
- The plan's C4 gate ("no more optimistic than w2v") sets a_opt to infinity. No gain in accuracy can then make up for a single extra optimistic class.
- Yet w2v's own conservative errors are large: 1.2–2.4 class steps per probe (below). They have real costs too: unneeded mitigation, discarded design options, and users who stop trusting the maps.
- D7 makes that trade a declared policy instead of an accident of the metric.

**The components on the stored runs.** Per probe, means over the climate levels. The cost for any weights is a_opt·O + C + c_miss·M + c_false·F.

| | O (optimistic steps) | C (conservative steps) | M (missed danger) | F (false alarm) |
|---|---|---|---|---|
| E after: w2v | 0.054 | 1.312 | 0.037 | 0.092 |
| E after: w3s | 0.212 | 0.592 | 0.104 | 0.000 |
| E after: M2 | 0.100 | 0.800 | 0.042 | 0.075 |
| All six settings: w2v | 0.027 | 1.677 | 0.019 | 0.256 |
| All six settings: w3s | 0.108 | 1.012 | 0.052 | 0.075 |
| All six settings: M2 | 0.050 | 1.173 | 0.021 | 0.188 |

**Which estimator has the lowest cost** (Case E after, c_false = 1):

| a_opt \ c_miss | 1 | 3 | 10 | 30 | 100 |
|---|---|---|---|---|---|
| 1 | w3s | M2 | M2 | M2 | M2 |
| 2 | M2 | M2 | M2 | M2 | M2 |
| 3 | M2 | M2 | M2 | M2 | w2v |
| 5 | M2 | M2 | M2 | M2 | w2v |
| 10 | M2 | M2 | M2 | w2v | w2v |
| 20 | w2v | w2v | w2v | w2v | w2v |

- **M2 against w2v.** M2 has the lower cost unless optimism is weighted about 11 times a conservative step (24 times over all six settings).
- **w3s** wins only when the weights are nearly symmetric.
- **At high c_miss, one probe decides.** M2 misses 3 of 20 danger probes against w2v's 2, and at c_miss = 100 that single probe pulls the break-even down to a_opt ≈ 2.5. A cost dominated by a handful of probes has no statistical power. So safety is better treated as a hard gate (the review's C4 gate 1) than as a weight.

**Options:**

| Option | Content | Comment |
|---|---|---|
| A (recommended) | A comfort cost only (a_opt, linear in class steps). Safety stays a hard gate. The cost replaces the review's gate 3: the candidate's cost must be lower than w2v's, with the probe-bootstrap CI excluding zero, on every climate level. | One number to declare. Safety is not traded against comfort. |
| B | The full matrix (a_opt, c_miss, c_false) as the deciding score. | Safety decisions rest on a few probes (above). |
| C | No cost. Gates only, as in the plan. | The trade stays implicit: a_opt = ∞ in the plan's C4. |

**For option A, the user must declare:**
1. a_opt;
2. whether two class steps cost twice one (linear) or more (for example squared);
3. whether the cost also includes the worst directional rotation (P4), or the equal sectors only.

**My suggestion:**
- a_opt = 3, linear;
- equal sectors and the worst rotation both reported, with the worst rotation gated;
- the sensitivity at a_opt = 1 and 10 always reported beside it.
- **Why 3:** an optimistic error usually surfaces after construction, when a fix (screens, planting, canopies) is expensive, and in the meantime people are exposed. A conservative error costs design effort that was not needed. But a_opt is a policy choice, not a fact that the data can settle.

**The link to M5.** With probabilistic classes, the same weights set the decision threshold. For example, flag danger when P(danger) ≥ c_false / (c_false + c_miss), which is 9 % for c_miss = 10.

## 5. Caveats

- Case E has 80 probes and one site. Its two states share the probes, so they are not independent.
- Case D has 3 directions. Its windiest tenth is about 20 probe-directions.
- M2 was conceived after looking at the data it is evaluated on.
- The zones in section 1.2 are geometric approximations.
- The climate calculation is analytic per sector, not `comfort.assess`.
- The safety counts are too small for anything but the M1 guarantee to be firm.
- Treat this review as an evidence-backed plan for C1, not as C1's result.

# Accuracy results: parts M and S on the experiment branch

**Date:** 2026-11-15. **Plan:** [ACCURACY_IMPROVEMENT_PLAN.md](../ACCURACY_IMPROVEMENT_PLAN.md), revision 4. **Diagnostics:** [ACCURACY_DIAGNOSTICS.md](ACCURACY_DIAGNOSTICS.md). **Status:** M and S prototyped and scored; D not started; nothing is in `main`.

**Build.** Branch `exp/accuracy-prototypes` in the worktree `/private/tmp/dtcc-qes-accuracy`, uncommitted; the diff is [accuracy_evidence/exp-accuracy-prototypes.patch](accuracy_evidence/exp-accuracy-prototypes.patch). The changes are switches read from the environment (`QES_EXP_ANGLE_FADE`, `QES_EXP_WAKE_RULE`, `QES_EXP_WAKE_SPREAD`, `QES_EXP_WAKE_REACH_CUT`). With none set, 5 runs of A, B and D are bit-identical to the released build at every probe. Parent throughout: `wake=3`.

---

## 1. Part M: angle fade of the sidewall and upwind-cavity zones

**Change.** The ±10° on/off test becomes a weight: 1 up to 10° − h, a smoothstep down to 0 at 10° + h. The zone's change of the velocity is multiplied by the weight. Cell flags keep the released threshold. Frozen half-width: **h = 2.5°** (the narrower of the two tested; 5° gives the same plane result).

**Direction sweep** (one 20 × 30 × 20 m building, 225°–315°, 1° steps):

| Sweep | Quantity | Parent | Fade 2.5° | Bar |
|---|---|---|---|---|
| 2 m | Largest plane RMS ΔK per degree | 0.0321 (5.4 × median) | **0.0154** (2.5 ×) | ≤ 0.016: met |
| 2 m | Median plane RMS | 0.0059 | 0.0061 | ≤ 0.0065: met |
| 2 m | Largest probe step | 0.069 | 0.069 | ≤ 0.035: **not met** |
| 2 m, building turned 30° | Largest plane RMS | 0.0268 (4.9 ×) | 0.0108 (2.0 ×) | met |
| 2 m, building turned 30° | Largest probe step | 0.163 | 0.046 | not met |
| 1 m | Largest plane RMS | 0.0325 (5.1 ×) | 0.0138 (2.2 ×) | met |
| 1 m | Largest probe step | 0.107 | 0.085 | not met |

- **The angle switches are gone.** At the side probe the steps at 260° → 261° and 279° → 280° (0.066 and 0.062) disappear.
- **The probe bar fails for another cause.** The remaining steps (0.069 at 243° → 244°, 0.060 at 258° → 259°) are also there with both zones switched off, and fall to 0.015 when the solved field is smoothed by 4 m. They are a sharp spatial edge of the near-wake cavity passing over a point probe, not an angle switch. The bar mixed the two causes.

**Do no harm:**

| Case | Result |
|---|---|
| A, B, D (vector and thermistor), C all states | Identical to the parent: no wall falls inside the ramp |
| E before | ΔMAE −0.0001 [−0.0004, 0.0001]; no hit changes; largest change at a probe 0.087 |
| E after | ΔMAE −0.0001 [−0.0004, 0.0000]; one hit gained |

**Gate.** Continuity: plane conditions met, probe condition not met. Identity: met. Do no harm: met. Robustness: plane conditions hold on the turned building and at 1 m.

**Open.** Either the plane conditions are the gate and the fade passes, or the cavity edge needs its own spatial blend (the variant the plan had before) to meet the probe bar.

---

## 2. Part S: shelter

### 2.1 Candidate

T4 pointed to S-b (reach and taper). Two things changed the candidate, both on development data only:

- **The reach constant is inert.** Cutting the wake at a deficit of 0.02 or 0.01 instead of 0.05 changes no score (ΔMAE 0.000). `FABEL_WAKE_INVESTIGATION.md` section 4.6 had found the same. S-b as listed has nothing to tune.
- **The signature used against S-a was wrong.** "Bias grows with buildings crossed upwind" does not describe where a superposition rule adds deficit. It adds it where several weak wakes overlap: open areas and streets in a dense fabric, which is where the excess is.

Screen on the development set (Case E before, 43 probes ≥ 60 m from the site; parent q 0.359, R 0.581, bias +0.104, MAE 0.133):

| Variant | q | R | Bias | MAE | ΔMAE vs parent [95 %] | ΔR vs parent [95 %] |
|---|---|---|---|---|---|---|
| Reach cut 0.02 or 0.01 | 0.360 | 0.581 | +0.104 | 0.133 | 0.000 | 0.000 |
| Spread 0.15 (released 0.2) | 0.432 | 0.556 | +0.066 | 0.112 | −0.021 [−0.029, −0.014] | −0.025 [−0.051, 0.000] |
| Spread 0.10 | 0.491 | 0.483 | +0.020 | 0.100 | −0.033 [−0.048, −0.019] | −0.098 [−0.166, −0.034] |
| **Root sum of squares of the deficits** | **0.506** | **0.570** | **+0.009** | **0.092** | **−0.041 [−0.056, −0.025]** | −0.011 [−0.055, 0.041] |

- The selection rule (lowest MAE with R falling by at most 0.02) picks the **root sum of squares**, D = min(1, √ΣG²). This is the second form of S-a. Frozen without a constant.
- **Every gain is a change of level.** Against the parent shrunk and moved to the candidate's mean, no variant is better (ΔMAE +0.002 to +0.011). That comparator removes what S is for, so it is reported and not gated; the gate uses plain shrinkage.
- Consistency: the roof-speed shelter of downstream buildings and the wake turbulence keep the largest-deficit rule.

**Synthetic checks:** mirror error unchanged (≤ 1.2e-3 m/s); the deficit behind the last row grows with added rows (0.25 → 0.33 at 40 m for one → five rows) and stays ≤ 1. It **reaches 1.0** in places inside the 5 × 5 arrays.

**Do no harm before freezing:** A and B identical (single buildings). Case C 0H: MAE −0.009 [−0.014, −0.004]. Case C 1H: no resolved change. Case C 2H is a tower state and is reported with Case D below.

### 2.2 Test, run once

`wake=3` scalar, Case E:

| Distance [m] | Error before, parent | Error before, candidate | Error after, parent | Error after, candidate |
|---|---|---|---|---|
| 0–15 (8 probes) | +0.229 [0.186, 0.271] | +0.138 [0.096, 0.184] | −0.063 [−0.150, 0.028] | −0.135 [−0.234, −0.039] |
| 15–30 | +0.145 [0.105, 0.184] | +0.061 [0.017, 0.103] | −0.061 [−0.123, −0.000] | −0.139 [−0.204, −0.076] |
| **0–30** | +0.176 [0.139, 0.210] | **+0.089 [0.049, 0.125]** | −0.062 [−0.116, −0.007] | −0.137 [−0.195, −0.079] |
| 30–60 | +0.083 [0.050, 0.114] | −0.003 [−0.041, 0.028] | +0.061 [0.021, 0.093] | −0.018 [−0.059, 0.013] |
| ≥ 60 | +0.104 [0.077, 0.130] | +0.009 [−0.020, 0.037] | +0.052 [0.015, 0.089] | −0.040 [−0.077, −0.003] |

Paired change ΔK within 30 m: measured +0.262, parent +0.024, candidate +0.035.

| Gate condition | Result | Verdict |
|---|---|---|
| Shelter prerequisite: error before ≤ 0.10 within 30 m | +0.089; the interval reaches 0.125 | **Met on the value, not resolved** |
| District level before, beyond 60 m | +0.104 → +0.009 | Met (development set) |
| E before, site probes | q +0.145 [0.051, 0.253]; MAE −0.058 [−0.073, −0.040]; hits 76 → 127 of 352 | Met |
| E before, R falls by at most 0.02 | All probes −0.024 [−0.059, 0.012]; site −0.030 [−0.095, 0.024] | **Marginal**: beyond 0.02 on the value, zero inside the interval |
| E after, outside 30 m | 30–60 m and ≥ 60 m: no resolved change in q, MAE or R | Met |
| E after, within 30 m (reported, not gated) | q −0.162 [−0.266, −0.053]; MAE +0.044 [0.023, 0.064]; level −0.137 | Passed to D as its target |
| Beyond shrinkage, site probes | ΔMAE −0.059 [−0.074, −0.041] | Met |
| A/B vector gate | Identical | Met |
| Case C 0H and 1H | Better; no resolved change | Met |

**Reported with D** (tower cases, already too low):

| Case | Change under the candidate |
|---|---|
| Case D thermistor | MAE +0.013 [0.005, 0.020]; hits +9 / −19; \|bias\| +0.027 |
| Case D split fibre | Vector RMSE −0.013 [−0.027, −0.000] |
| Case C 2H | MAE +0.005 [−0.001, 0.011]; R −0.069 [−0.104, −0.034]; \|bias\| +0.044 |

**Reading.**

- The before-state error halves at the site and vanishes in the district. The prerequisite is met on its value by 0.011.
- The 0–15 m bin stays at +0.138. D's own gate asks for 0.10 in each bin; with 8 probes that bin is not decidable on its own.
- All of the cost falls where a tall building stands: Case E after within 30 m, Case D, Case C 2H. The tower response is unchanged (+0.035 against +0.262), so D's target is now larger: a shortfall of 0.137 [0.079, 0.195] in the after-state level.
- Taken alone, S makes the after state worse near the tower. It is only useful together with D.

---

## 3. Decisions and completion (2026-11-15)

- **M passes on the plane conditions.** The largest probe step is reported, not gated; the cavity edge is a separate problem.
- **S (root sum of squares) is accepted as the parent for developing D.** S and D are judged together; S is not released without D.

**Robustness of S (S5):**

| Check | Result |
|---|---|
| 1 m grid, error before within 30 m | +0.179 → +0.091 [0.051, 0.128] (2 m: +0.176 → +0.089) |
| 1 m grid, district beyond 60 m | +0.110 → +0.011 [−0.020, 0.041] |
| 1 m grid, E before all probes | q +0.138; MAE −0.044 [−0.055, −0.030]; R −0.021 [−0.057, 0.016] |
| 1 m grid, E after all probes | MAE +0.005 [−0.012, 0.021]; no resolved change |
| Direction sweep, one building | Identical to the parent (one wake, nothing to combine) |
| Constants | None |

**M and S together** (2 m): A, B and D are identical to S alone. In E the fade changes the MAE by less than 0.0001 and no gate reading. Against the released parent the combination gives the S numbers: error before within 30 m +0.089 [0.049, 0.125], E before MAE −0.042 [−0.054, −0.030].

Case C was not rerun at 0.5 m, and the combination was not rerun on Case C: the fade leaves every Case C run identical.

**Remaining for M and S:** the native options (M5, S6) belong to the release batch of section 7 of the plan, after D is decided. The experiment switches stay on the branch `exp/accuracy-prototypes`.

## 4. What is open

**D** is not started. Its target after S: an after-state shortfall of 0.137 [0.079, 0.195] within 30 m of the Case E tower, a paired change of +0.035 against +0.262 measured, Case D low by 0.09–0.15 before S and lower after it, and Case C 1H → 2H short by 0.12.

## 5. D, literature step (2026-11-15)

No model run. Script: `experiments/accuracy/d_literature.py`; table: [accuracy_evidence/d_literature.md](accuracy_evidence/d_literature.md).

**Sources read.** Gandemer (1975) and Penwarden and Wise (1975) themselves were not obtained; their numbers are taken from two digests that reproduce them and from one later study.

| Source | Rule (ratio R to the undisturbed speed at pedestrian height) |
|---|---|
| BRE Digest 390, *Wind around tall buildings* | Wide slab at least 4 times its neighbours: about 1.5 in the front vortex (the digit is garbled in the scan), 2.5 in corner streams and through-flow. Sheltered areas among low buildings: 0.2–0.3. The affected area extends about one building height. |
| Schriever, NRC Canadian Building Digest, *Ground-level winds around tall buildings* | Flow divides at about three quarters of the height. Vortex up to 1.5, corner streams up to 2.0, for a slab at least 4 times its surroundings. Below twice the surrounding height R does not generally exceed 1.0. Extent roughly the building height. |
| Reiter (2010), *Environment and Planning B* 37, CFD with a Reynolds-stress model | Corner of an unsheltered building against height: 1.58, 1.68, 1.80, 1.94, 2.38, 2.74, 3.30 at 12, 24, 36, 48, 72, 96, 192 m. Front vortex: 0.12, 0.28, 0.58, 1.20, 1.36, 1.40 at 24, 36, 48, 72, 96, 192 m. Among lower buildings the corner value is multiplied by 0.55, 0.85, 0.90, 0.93, 0.97, 0.98 at H/h = 2, 3, 4, 6, 8, 16. Critical zone: a circle of radius H. A tall building is one at least twice the mean surrounding height. Corner value changes by −2 % to +13 % with wind direction. |

**The three cases** (rules converted to K with the undisturbed K at 2 m):

| Case | H | Mean neighbour height | H/h | Corner peak, literature | Measured maximum | Measured maximum per direction, median | Simulated maximum, parent / S |
|---|---|---|---|---|---|---|---|
| E after | 60 m | 7.5 m | 8.1 | 1.50–1.87 | 1.37 | 0.98 | 0.83 / 0.79 |
| D | 100 m | 10.6 m | 9.4 | 1.15–1.54 | 0.96 | 0.94 | 0.64 / 0.56 |
| C 2H | 40 m | 22.2 m | 1.8 | ≤ 0.81–1.0 (no speed-up expected) | 1.53 (1.49 already in 1H) | 1.49 | 1.23 / 1.18 |

**Reading.**

- **The literature values are in the right range, on the high side.** They are 10–40 % above the measured maximum in E and 20–60 % above it in D. The probes do not sit at the peak (none is closer than 7.5 m in E), so the measured maxima are lower bounds.
- **The model has no such peak.** Its maximum near the tower is 0.83 in E where 1.37 is measured, and 0.64 in D where 0.96 is measured.
- **The front-vortex value is the uncertain one.** For E it is 0.65 (Reiter) or 1.12 (digests) as K. The measured upwind sector rises by only +0.10 (T3), which is closer to Reiter.
- **The literature gives peaks and an extent, not a field.** Extent ≈ H; the measurement says the effect ends between 0.5 and 0.75 H. The shape between the wall and that distance has to be chosen.
- **The eligibility ramp of the plan agrees with Reiter.** Reiter's factor is 0.55 at H/h = 2 and 0.85 at 3; the plan's ramp gives 0.5 at 2 and 1 at 2.5. The digests put the threshold at 2 and the full effect at 4.
- **Case C 2H is a weak development case.** At H/h = 1.8 the literature expects little. The measured maximum is 1.5, but it is already 1.5 without the tower, at the outer corners of the array. The tower shows in the mean (+0.12) and the 90th percentile (1.09 → 1.21), not in the maximum.
- **The reference speed matters.** All rules scale the undisturbed speed at pedestrian height. The plan's design scales the approach speed at ⅔ H instead. For E that reference is 1.35 times the 15.9 m speed, so a corner factor of about 1.0–1.4 on it reproduces the same peaks; the digests' "divides at three quarters of the height" supports a reference between ⅔ and ¾ H.

## 6. Part D: downwash zone (2026-11-15)

**Built** on the experiment branch as `Downwash.cpp`, switch `QES_EXP_DOWNWASH`, written after every parameterization and before the projection, on the S parent (root sum of squares). Constants fixed before any run:

| Choice | Value | Source |
|---|---|---|
| Corner and front-vortex speed ratios against building height | Reiter (2010), Fig. 5 and Fig. 7, applied to the inflow speed at the same height | Literature |
| Eligibility | 0 at H/h = 1.5, 1 at 2.5; h = area-weighted mean roof height within 2 H; no neighbour gives 0 | Plan (agrees with Reiter's table 7) |
| Reach | 0.75 H from the walls, cosine decay | Decided 2026-11-15 |
| Vertical extent | Full to 0.25 H, zero at 0.5 H | **My choice** |
| Sector | Vortex value upwind, corner value beside, fading to zero between 90° and 150° from the upwind direction | **My choice** |
| Direction of the imposed flow | Reversed on the upwind axis, tangential around the building beside it | **My choice**; revised below |

**Synthetic checks:** isolated cube, isolated tower, equal-height array and tandem cubes are bit-identical with the zone on. In the 5 × 5 array with a 60 m tower the mirror error is unchanged (1e-5 m/s), the divergence is unchanged, and the effect ends within 45 m.

**Development, Case C** (no constant adjusted): states 0H and 1H are bit-identical. The 1H → 2H change within 15 m goes from +0.072 to +0.171 against +0.194 measured (error −0.023 [−0.059, 0.013]); the sign is right in all three sectors; whole-array MAE in 2H −0.009 [−0.018, 0.000] and R +0.093 against S.

**Test, run once** (`wake=3` scalar; S+D against the released parent):

| Gate condition | Parent | S | S+D | Verdict |
|---|---|---|---|---|
| E, error before, 0–30 m | +0.176 | +0.089 | +0.093 [0.053, 0.131] | Met on the value |
| E, error after, 0–30 m | −0.062 | −0.137 | +0.062 [0.004, 0.122] | Met |
| E, error after, 0–15 m (8 probes) | −0.063 | −0.135 | +0.117 [0.042, 0.205] | Above 0.10; not decidable alone |
| E, error before, 0–15 m (8 probes) | +0.229 | +0.138 | +0.140 [0.098, 0.184] | Above 0.10; not decidable alone |
| E, paired change within 30 m (measured +0.262) | +0.024 | +0.035 | **+0.230**, error −0.031 [−0.079, 0.013] | Met (≥ 0.15 and closer) |
| E, change by sector: upwind / beside / downwind (measured +0.10 / +0.35 / +0.25) | −0.09 / +0.09 / +0.01 | −0.06 / +0.08 / +0.05 | +0.08 / +0.37 / +0.11 | Signs met; downwind short by 0.14 |
| E after, beyond 60 m | | | q +0.019, MAE −0.011, R +0.089, none resolved as worse | Met |
| E after, all probes | q 0.462, R 0.559 | q 0.418, R 0.546 | q 0.456, **R 0.672**, MAE 0.133 | R +0.113 [0.054, 0.169] |
| Case D thermistors | q 0.414, bias −0.120, MAE 0.152 | q 0.364, MAE 0.165 | **q 0.490, bias −0.014, MAE 0.128** | Met: MAE −0.024 [−0.041, −0.006] |
| Case D, level within 15 m / 15–30 m | −0.144 / −0.155 | −0.179 / −0.177 | +0.026 / −0.047 | Within intervals of zero |
| **Case D split fibre, common vector gate** | RMSE 0.235, 5 sign errors of 29 | 0.221, 5 | **RMSE +0.126 [0.082, 0.168]; 10 sign errors** | **Not met** |
| A/B | | | Bit-identical | Met |

**The gate fails on one condition: the mean vector at the Case D split-fibre points.** Everything scalar passes.

**Revision (the one allowed).** The direction of the imposed flow is not in the literature, so the revision keeps the existing field's direction and moves only its speed toward the target (`QES_EXP_DOWNWASH=2`). This is further development on Cases D and E, not an independent test.

| | Version 1 (imposed direction) | Revision (speed only) |
|---|---|---|
| Case D split fibre, vector RMSE against parent | +0.126 [0.082, 0.168] | +0.134 [0.066, 0.198] |
| Case D split fibre, U sign errors of 29 | 10 | 5 (as the parent) |
| Case D thermistors: q, R, MAE | 0.490, 0.569, 0.128 | 0.434, 0.454, 0.160 |
| E after: R, MAE | 0.672, 0.133 | 0.624, 0.138 |
| E, paired change within 30 m | +0.230 | +0.199 (beside +0.31) |
| Case C 2H, MAE against S | −0.009 | +0.009 [0.002, 0.016] |

The revision restores the signs but not the vector error, and it is worse on every scalar score. **Version 1 stands as the better candidate; the vector condition remains failed.**

**Why the vectors get worse.** At the 33 split-fibre points (0° only) the measured mean-vector speed is 0.297 U_H and the measured k is 0.0236 U_H². The parent has 0.276 and 0.0252; S+D has 0.370 and 0.0253. The zone raises the mean vector where the instrument that resolves the mean vector does not see a rise of that size. The literature ratios and the thermistors are scalar speeds: part of what they report near a tower is turbulence, and the zone puts all of it into the mean flow. This is finding 2 of the plan, now measured.

**Other observations.**

- The zone is active in Case E before construction too (largest change at a probe 0.39): some existing building there is eligible. The mean before-state levels are unchanged (+0.093 against +0.089).
- Not done at this point: the ±25 % sensitivities, the 1 m grid and the break-point sensitivities of D5. *(Done later: section 8, and the 1 m grid in section 9.)*

### 6.1 Split between mean flow and turbulence (decided 2026-11-15, outside the revision limit)

`QES_EXP_DOWNWASH=3`. The literature ratio is treated as a scalar speed. A share γ of it is imposed on the mean flow; the rest is added as turbulence after the solve, k = W (1 − γ²) / (2γ²) |U|², with W the zone weight. **γ = 0.8**, from the Case D split-fibre data before any run of this variant: measured mean speed 0.297 U_H and k 0.0236 U_H² give |U|² / (|U|² + 2k) = 0.65. This is development on Case D; Case E has no vector data and serves as the check.

| Measure | Parent | Version 1 | Split, γ = 0.8 | Measured |
|---|---|---|---|---|
| Case D split fibre, vector RMSE against parent | | +0.126 [0.082, 0.168] | **+0.086 [0.049, 0.123]** | |
| Case D split fibre, U sign errors of 29 | 5 | 10 | 10 | |
| Case D split-fibre points, mean speed | 0.276 | 0.370 | 0.326 | 0.297 |
| Case D split-fibre points, k | 0.0252 | 0.0253 | 0.0425 | 0.0236 |
| Case D thermistors: q / bias / MAE | 0.414 / −0.120 / 0.152 | 0.490 / −0.014 / 0.128 | 0.515 / −0.033 / 0.131 | |
| Case E, change within 30 m | +0.024 | +0.230 | +0.227 | +0.262 |
| Case E after, error within 30 m | −0.062 | +0.062 | +0.058 [−0.002, 0.120] | |
| Case E after, R / MAE over all probes | 0.559 / 0.133 | 0.672 / 0.133 | 0.666 / 0.134 | |
| Case C, 1H → 2H within 15 m | +0.074 | +0.171 | +0.173 | +0.194 |
| Case C 2H, MAE against S | | −0.009 | −0.007 [−0.015, 0.002] | |
| A, B; Case C 0H, 1H | | identical | identical | |

- **The scalar results are kept**, in the check case E as well as in D and C.
- **The vector error falls by a third but the condition still fails** (+0.086 against a tolerance of 0.02), and the sign errors stay at 10.
- **The turbulence is now too high at those points** (0.0425 against 0.0236 measured), while the mean speed is still 10 % high. A smaller γ would trade one error for the other.
- **What is left is direction, not level.** The sign errors come with the imposed direction (version 1 and the split: 10; the speed-only revision: 5). The lateral component carries most of the remaining error (MAE V +0.063, U +0.039).

## 7. Where the three parts stand

| Part | State |
|---|---|
| M, angle fade | Passed. |
| S, root sum of squares | Accepted as the parent for D; together with D it closes the before-state level and the district bias. |
| D, downwash zone | Reproduces the tower effect on every scalar measure in E, D and C. Fails the mean-vector condition at the Case D split fibre in all three variants; the split between mean flow and turbulence reduces the excess by a third. |

Under the plan D does not pass. What S+D delivers is a correct scalar speed near towers, with a mean flow whose direction is wrong at half of the 29 Case D points where the direction is measured and resolved.

## 8. Acceptance and sensitivities (2026-11-15)

**Decision:** S + D in the split variant is accepted as a scalar-speed model, experimental and opt-in, with the mean-vector failure documented. The integration proposal is [ACCURACY_MAIN_INTEGRATION_PLAN.md](../ACCURACY_MAIN_INTEGRATION_PLAN.md).

**Sensitivities (D5), 2 m,** full table in [accuracy_evidence/d_sensitivity.md](accuracy_evidence/d_sensitivity.md):

| Variant | E change within 30 m (measured +0.262) | E after, error within 30 m | E after q / R / MAE | Case D q / bias / MAE | Case D vector RMSE against parent |
|---|---|---|---|---|---|
| Frozen | +0.227 | +0.058 | 0.452 / 0.666 / 0.134 | 0.515 / −0.033 / 0.131 | +0.086 |
| Ratios × 0.75 | +0.168 | −0.003 | 0.480 / 0.663 / 0.124 | 0.495 / −0.075 / 0.131 | +0.052 |
| Ratios × 1.25 | +0.289 | +0.122 | 0.424 / 0.662 / 0.149 | 0.460 / +0.013 / 0.145 | +0.126 |
| Reach 0.56 H | +0.177 | +0.005 | 0.456 / 0.648 / 0.131 | 0.470 / −0.048 / 0.141 | +0.083 |
| Reach 0.94 H | +0.251 | +0.087 | 0.462 / 0.666 / 0.138 | 0.495 / −0.026 / 0.128 | +0.083 |
| Mean-flow share 0.7 | +0.232 | +0.063 | 0.448 / 0.662 / 0.136 | 0.485 / −0.039 / 0.136 | +0.068 |
| Mean-flow share 0.9 | +0.227 | +0.059 | 0.458 / 0.669 / 0.133 | 0.515 / −0.024 / 0.129 | +0.106 |
| Eligibility ramp 1.25–2.0 or 2.0–3.0 | +0.227 | +0.058 to +0.059 | unchanged | unchanged | +0.086 |

- No variant loses the gains. The ratios and the reach move the Case E change between +0.17 and +0.29.
- The eligibility ramp has no effect in D and E (their height ratios are 8 and 9).
- The sign errors at the Case D vector points stay at 10 of 29 in every variant.

**M + S + D together** (2 m): identical to S + D to three decimals in every measure of the table. The second-grid and Case C runs of the combination were still running when this was written.

## 9. Port to the package (2026-11-16)

Steps 2 to 4 of [ACCURACY_MAIN_INTEGRATION_PLAN.md](../ACCURACY_MAIN_INTEGRATION_PLAN.md), on the branch `feat/accuracy-options`. Version 0.1.0b6, native identity `e130c2fb…`.

**Options.** `wind.Parameterizations(angle_fade=2.5)` and `wind.Parameterizations(wake=3, tall_buildings=1)`; both default to off. Documentation: [docs/angle-fade.md](../docs/angle-fade.md), [docs/tall-buildings.md](../docs/tall-buildings.md). Only the accepted variant of the zone is ported; its constants are in `TallBuildingModel` (`wake_model.h`). The zone is a named stage (`tall_buildings`) at the end of `applyParametrizations`.

**Gate 1, defaults unchanged.** 184 default runs (`wake=2` and `wake=3`; A, B, C, D, E; both grids) on the final build against the runs of the 0.1.0b5 build: probe velocities and 2 m planes are bit-identical in all 184. The audited turbulence fixtures were regenerated for the serial and the OpenMP build: all 16 arrays are bit-identical; only their recorded source hashes and native identity change.

**Gate 2, options reproduce the prototype.**

| Check | Prototype | Ported |
|---|---|---|
| `tall_buildings=1`, 37 runs of A, B, D, E | | Bit-identical to the prototype |
| `angle_fade=2.5`, same runs | | Within 1.2e-5 m/s (the half-width is converted to radians in single precision) |
| Sweep, 2 m: largest / median plane RMS ΔK per degree | 0.0154 / 0.0061 | 0.0154 / 0.0061 |
| Sweep, building turned 30° | 0.0108 | 0.0108 |
| Sweep, 1 m | 0.0138 | 0.0138 |
| Case E change within 30 m, 2 m / 1 m | +0.227 / +0.230 | +0.227 / +0.230 |
| Case E before, error within 30 m, 2 m / 1 m | +0.093 / +0.095 | +0.093 / +0.095 |
| Case E after, R, 2 m / 1 m | 0.666 / 0.662 | 0.666 / 0.662 |
| Case D bias / MAE, 2 m / 1 m | −0.033 / 0.131; −0.037 / 0.133 | the same |
| Case C, both options against `wake=3`, 1 m and 2 m | 0H better, 1H and 2H no resolved change | the same |

Tables: [accuracy_evidence/final_campaign_working_grid.md](accuracy_evidence/final_campaign_working_grid.md), [final_campaign_second_grid_and_c.md](accuracy_evidence/final_campaign_second_grid_and_c.md), [step2_port_gate.md](accuracy_evidence/step2_port_gate.md).

**Tests.** `tests/test_angle_fade.py` (16) and `tests/test_tall_buildings.py` (9) are new. The Python suites pass on the final build: 2,299 passed, 39 skipped. Native CTest, fresh Release builds: serial 66/66, OpenMP 69/69, the same counts as 0.1.0b5. Debug build with AddressSanitizer and UBSan: 68/69, no sanitizer report; `stop_rule` aborts with "Estimate depends on the thread team", and it does the same on the base commit `c9dd6d5`, so it predates this work.

**Not done.**

- `tools/check_policy_compatibility.py` was not run; the build is not qualified for `pedestrian-v1`, as 0.1.0b5. *(Later the stall-fix work ran all 24 frozen workers on `7008159`, which contains this port: 3 fail, as they do without it; see `docs/PRECISION_STAGNATION_RESULTS.md`.)*
- Case C alone with `tall_buildings=1` or with `angle_fade=2.5` on the final build; the combination was run, and the fade leaves Case C identical. *(Done in section 10: `tall_buildings=1` alone is bit-identical to the combination.)*
- `run_full_validation.py` covers defaults only, as before; the options have named campaigns instead (`angle_fade`, `tall_buildings`, `accuracy_options`, `ab_accuracy_options`, `c_accuracy_options`).
- The run cache of `validation/accuracy/common.py` still stores a variant under its parent's key in a directory of its own (`ACC_TAG`, `ACC_PARAMS`). *(Kept by decision, documented as a research tool in its docstring.)*

## 10. After the stall fix (2026-11-16)

The Case C runs at 1 m with `wake=3` in sections 1 to 9 (the parent and both options) ran to the 20,000-sweep cap because of the stop-rule stall. With the fix (`1bf644f`, build `df09ee9d…`) they stop on the new stagnation trigger after 1,650–2,225 sweeps. Rerun of the 27 runs (parent, `tall_buildings=1`, both options), [accuracy_evidence/closeout_case_c_after_stall_fix.md](accuracy_evidence/closeout_case_c_after_stall_fix.md):

- **Reported values are unchanged.** The new probe velocities differ from the stalled ones by at most 6.0e‑5 m/s (parent) and 3.0e‑5 m/s (both options). The Case C score table of both options against the parent is identical to four decimals.
- **`tall_buildings=1` alone is bit-identical to the combination with `angle_fade=2.5`** on all 9 Case C runs, as expected: no wall of Case C falls inside the angle ramp.
- No other case was affected: the stall occurred only in Case C at 1 m with `wake=3` among the stored runs.

Open follow-ups of this work: [ACCURACY_CLOSEOUT_PLAN.md](../ACCURACY_CLOSEOUT_PLAN.md), section 2.3.


# Accuracy diagnostics: preparation and part T

**Date:** 2026-11-15. **Plan:** [ACCURACY_IMPROVEMENT_PLAN.md](../ACCURACY_IMPROVEMENT_PLAN.md), steps I0, I2, I3, I4 and T1–T4. No model code was changed. **Status:** stopped at the plan's review gate after part T.

**Base.** Native extension built from `4c7a8da` (0.1.0b5), sha256 `e76cfe8c28187281…`, `src` clean. Validation modules at `c9dd6d5` (Case C setup, committed during this work; it changes no native code). All runs use the ordinary `wind.Solver()` (velocity stop rule, grid relaxation, cap 20,000 sweeps), turbulence on, float32.

**Where things are.** Scorer and run tools: `validation/accuracy/` (moved there on 2026-11-15); the one-off diagnostic scripts: `experiments/accuracy/` (git-ignored, like every other experiment folder). Runs and manifests: `validation/output/accuracy/` (git-ignored). Full tables behind every number below: [accuracy_evidence/](accuracy_evidence/).

---

## 1. Summary of verdicts

| Item | Verdict | Main evidence |
|---|---|---|
| I3 shelter check (decides D) | **Fails.** D is paused. | `wake=3` scalar error before construction within 30 m: +0.176 [0.139, 0.210]; limit 0.10 |
| I3 vector-smoothing check (decides M's target) | **Target on `wake=2` only.** None on `wake=3`. | Vector RMSE falls at 2–4 m on A, B and D for `wake=2`; no length improves `wake=3` beyond the paired interval |
| K1 contrast | **Supported for `wake=2`; largely removed by `wake=3`.** "Three times" holds for one comparison only. | r = 1.86 (E before, `wake=2`, mean vector); r = 0.68–0.88 for the `wake=3` scalar in D, E after and C |
| K2 blockage | **Supported** (too slow where blocked), weaker under the `wake=3` scalar. No single cavity-strength error. | Spearman of shortfall with blockage +0.36 to +0.65 for the mean vector; A reverse flow too strong, B too weak |
| K3 locality | **Supported** within the sampled distances. | Measured ΔK +0.26 inside 0.5 H; −0.02 [−0.07, 0.03] relative to the far field at 0.5–1 H |
| Need for a tower correction | **Supported, in three cases.** | E paired change short by 0.24; Case D near-tower level low by 0.15; Case C 1H → 2H short by 0.12 |
| T4 source of the before-state excess | **Wake recovery with distance, plus aligned streets and open areas.** Not an accumulation that grows inward; not the inflow level. | Bias +0.04 at x/H < 2, +0.16 at x/H ≥ 8; +0.24 where no building lies upwind; falls from +0.24 to +0.08 with more buildings upwind |
| M continuity bar | The largest step is an **angle switch**, not a zone edge. | Sidewall and upwind cavity off: largest plane step 0.032 → 0.016; spatial smoothing leaves it at 3.3–3.9 × the median |

Four findings change what the next parts can do. They are listed in section 8 and need a decision before any model work starts.

---

## 2. I0: protocol and baselines

- **Scorer.** `validation/accuracy/score.py`, with `data.py` (matched quantities), `tower.py` (tower contract) and `test_score.py` (4 checks pass). Intervals are 95 % percentile bootstraps over probe groups and, with at least five of them, direction groups (2,000 replicates, seed 20261115). Cases C and D have three directions, so their intervals cover probe sampling only.
- **Archive.** 92 runs on the working grid (A, B, C at 1 m; D, E at 2 m) and 92 on the second grid (A, B, C at 2 m; D, E at 1 m), each for `wake=2` and `wake=3`. Manifests are in the evidence folder.
- **Reproduction.** The release tower diagnostic is reproduced: measured ΔK +0.2616 and `wake=2` mean-vector ΔK −0.002 within 30 m (352 pairs). The historical contrast ratios are reproduced on the corrected build: r = 1.86, 1.29 and 1.11 (historical 1.85, 1.27, 1.10).

**Parents, primary scalar quantity against thermistors** (working grid):

| Case | Parent | q | R [95 %] | Bias [95 %] | MAE | r | In-sample linear map MAE | Null model MAE |
|---|---|---|---|---|---|---|---|---|
| D | `wake=3` | 0.414 | 0.55 [0.40, 0.65] | −0.120 [−0.150, −0.090] | 0.152 | 0.68 | 0.122 | 0.187 |
| E before | `wake=3` | 0.327 | 0.55 [0.46, 0.63] | +0.120 [0.097, 0.142] | 0.145 | 1.19 | 0.081 | 0.418 |
| E after | `wake=3` | 0.462 | 0.56 [0.48, 0.64] | +0.022 [−0.009, 0.053] | 0.133 | 0.75 | 0.126 | 0.341 |
| C 0H | `wake=3` | 0.561 | 0.51 [0.41, 0.60] | +0.048 [0.023, 0.073] | 0.172 | 0.78 | 0.154 | 0.346 |
| C 1H | `wake=3` | 0.439 | 0.34 [0.23, 0.43] | +0.001 [−0.026, 0.029] | 0.214 | 0.88 | 0.187 | 0.324 |
| C 2H | `wake=3` | 0.411 | −0.03 [−0.13, 0.07] | −0.069 [−0.099, −0.040] | 0.271 | 0.75 | 0.210 | 0.251 |

- The leave-one-case-out linear map does not transfer: its MAE is 0.257 in E before against 0.145 for the parent. A8 stands: the calibrated map stays a reference row.
- In Case C 2H the parent has no pattern skill (R ≈ 0) and a higher MAE than the null model.

**Vector datasets** (working grid):

| Dataset | Points | q of magnitude | Vector RMSE / U_ref [95 %] | U sign errors |
|---|---|---|---|---|
| A, `wake=2` → `wake=3` | 186 | 0.661 → 0.704 | 0.215 → 0.168 [0.134, 0.198] | 6 → 3 of 179 |
| B, `wake=2` → `wake=3` | 224 | 0.513 → 0.647 | 0.374 → 0.214 [0.159, 0.261] | 6 → 9 of 206 |
| D split fibre, `wake=2` → `wake=3` | 33 | 9 → 8 hits | 0.297 → 0.235 [0.199, 0.273] | 4 → 5 of 29 |

**Turbulence of the `wake=3` scalar.** At the Case D split-fibre points the modelled k matches the measurement: 0.0252 against 0.0236 U_H², R = 0.84 (`wake=2` QES-Turb: 0.0052, R = 0.09). The scalar proxy is not inflated there.

**Observation outside this plan: stop-rule stall.** `wake=3` on Case C at 1 m does not stop on the velocity rule in 8 of 9 runs. The change per check settles at 3.3e-5, just above the rule's float32 floor estimate of 2.7e-5, and the run goes to 20,000 sweeps (about 200 s instead of 10 s). The fields are converged (RMS divergence 5.7e-6 s⁻¹, 40 times below the `wake=2` runs that stop normally). The results are used as they are. This is a defect of the stop rule, not of the wake model.

**Version string.** `src/dtcc_qes/__init__.py` reports `0.1.0b4`; `pyproject.toml` says `0.1.0b5`.

---

## 3. I3: the two decisive checks

### 3.1 Shelter check

Tower: 602 m² footprint, 60 m. `wake=3`, `K_scalar_wake_rule`, 2 m grid:

| Distance [m] | Probes | Measured before → after | Simulated before → after | Error before [95 %] | Error after [95 %] | ΔK error [95 %] |
|---|---|---|---|---|---|---|
| 0–15 | 8 † | 0.315 → 0.639 | 0.544 → 0.576 | +0.229 [0.186, 0.271] | −0.063 [−0.150, 0.028] | −0.292 [−0.374, −0.215] |
| 15–30 | 14 | 0.336 → 0.562 | 0.481 → 0.500 | +0.145 [0.105, 0.184] | −0.061 [−0.123, −0.000] | −0.207 [−0.266, −0.156] |
| **0–30** | 22 | 0.328 → 0.590 | 0.504 → 0.528 | **+0.176 [0.139, 0.210]** | −0.062 [−0.116, −0.007] | −0.238 [−0.291, −0.185] |
| 30–60 | 15 | 0.332 → 0.352 | 0.415 → 0.413 | +0.083 [0.050, 0.114] | +0.061 [0.021, 0.093] | −0.022 [−0.057, 0.011] |
| ≥60 | 43 | 0.334 → 0.374 | 0.438 → 0.427 | +0.104 [0.077, 0.130] | +0.052 [0.015, 0.089] | −0.052 [−0.081, −0.025] |

† fewer than ten probes.

- **The prerequisite fails**: the whole interval of the before-state error lies above 0.10. At 1 m the error is +0.179 [0.142, 0.212].
- The sensitivities do not change this: +0.184 with the measured inflow k, +0.159 with the mean-speed proxy.
- The after-state level is within 0.10. The model reaches it without a tower response: the simulated change is +0.024 against +0.262 measured.
- The measured far field rises by +0.040 after construction; the simulated far field falls by 0.012.

### 3.2 Vector-smoothing check

Post-hoc Gaussian smoothing of the solved vector field, signed components against the split-fibre data; change of vector RMSE / U_ref against the unsmoothed parent:

| Dataset | Parent RMSE | σ = 2 m | σ = 4 m | σ = 8 m |
|---|---|---|---|---|
| D split fibre, `wake=2` | 0.297 | −0.007 [−0.015, −0.001] | −0.039 [−0.064, −0.013] | −0.068 [−0.123, −0.014] |
| A horizontal sections, `wake=2` | 0.218 | −0.026 [−0.038, −0.014] | −0.030 [−0.054, −0.010] | +0.008 [−0.017, 0.036] |
| B horizontal sections, `wake=2` | 0.296 | −0.014 [−0.023, −0.006] | −0.019 [−0.032, −0.009] | −0.020 [−0.042, 0.003] |
| D split fibre, `wake=3` | 0.235 | −0.003 [−0.010, 0.004] | −0.014 [−0.036, 0.008] | −0.009 [−0.054, 0.031] |
| A horizontal sections, `wake=3` | 0.142 | −0.003 [−0.016, 0.011] | +0.019 [0.000, 0.040] | +0.066 [0.042, 0.092] |
| B horizontal sections, `wake=3` | 0.211 | −0.005 [−0.013, −0.000] | −0.002 [−0.010, 0.003] | +0.013 [0.006, 0.024] |

- **`wake=2` has a mean-field target** at 2–4 m. Sign errors of U rise with the filter length (D: 4 → 7 of 29 at 4 m).
- **`wake=3` has none.** The spreading wake already removed what smoothing removes: going from `wake=2` to `wake=3` lowers the RMSE by 0.05–0.16, more than any filter does on `wake=2`.

---

## 4. I2 and I4

**I2 synthetic layouts** (`layouts.py`): cube, 1:1:3 tower, 5 × 5 arrays at densities 0.25 and 0.44 with and without a central 60 m tower, tandem cubes. One finding from the smoke check: the layout must put every wall on a cell face. With walls at cell centres the parent's mirror error is 0.6–2.6 m/s; with walls on faces it is below 1e-3 m/s (tandem `wake=2`: 0.027 m/s). The runner now refuses a layout whose walls do not share one grid offset.

**I4 Case C entry check: passes, with three limits.**

- States 0H, 1H, 2H at 0°, 22.5° and 45°; 120 probes at 2 m; 360 finite values per state.
- Thermistor scalar speed; scored with the scalar proxies (A3).
- Reference confirmed: the run normalises by its inflow at 2 m, 2.434 m/s, as the workbook does.
- Prior use: the setup ran the default `wake=2` smoke and baseline campaigns only. No model setting was chosen on Case C scores. The direction sign was chosen from the measurements alone.
- **Limit 1: no probe lies in the central plot.** The nearest probe is 5 m outside the central footprint, and every probe is within 30 m of it. Case C samples the streets around a missing block, not an open plot, and has no far field for the paired changes.
- **Limit 2: no measured inflow k** (only σ_u). `K_scalar_wake` is undefined. The rule value k_in = 0.627 m²/s² compares with σ_u² = 0.318 m²/s² at 2 m, so it is probably high by a factor 1.3–2. The scalar proxy of the undisturbed inflow is then 1.10 where the measurement is 1.00 by definition.
- **Limit 3: the working grid is 1 m and the second grid 2 m.** The 0.5 m grid (over 100 M cells, 18 runs) was not run.

**Case C paired changes, `wake=3` scalar, within 15 m of the central block (56 probes):**

| Change | Measured | Simulated | Δ error [95 %] |
|---|---|---|---|
| 0H → 1H | +0.035 | −0.024 | −0.059 [−0.096, −0.024] |
| 1H → 2H | +0.194 | +0.074 | −0.120 [−0.155, −0.085] |

The errors depend strongly on direction. At 0° (streets along the wind) the model is too fast by 0.24–0.27 within 15 m; at 45° it is too slow by 0.04–0.28.

---

## 5. T1: contrast (K1)

**Vector data** (r = σ_sim / σ_meas):

| Dataset | `wake=2` r [95 %] | `wake=3` r [95 %] |
|---|---|---|
| A, magnitude | 0.96 [0.89, 1.02] | 0.94 [0.88, 1.00] |
| B, magnitude | 1.16 [1.06, 1.27] | 1.01 [0.95, 1.07] |
| D split fibre, magnitude | 1.51 [1.22, 2.12] | 1.12 [0.95, 1.48] |
| D split fibre, U | 1.43 [1.20, 1.84] | 1.07 [0.91, 1.34] |

**Thermistor data:**

| Dataset | `wake=2`, `K` | `wake=2`, `K_scalar` | `wake=3`, `K` | `wake=3`, `K_scalar_wake_rule` |
|---|---|---|---|---|
| D | 1.11 [0.99, 1.28] | 1.06 [0.96, 1.20] | 0.75 [0.67, 0.85] | 0.68 [0.61, 0.76] |
| E before | 1.86 [1.70, 2.05] | 1.31 [1.18, 1.46] | 1.49 [1.37, 1.64] | 1.19 [1.09, 1.32] |
| E after | 1.29 [1.14, 1.47] | 1.01 [0.89, 1.15] | 0.95 [0.83, 1.10] | 0.75 [0.66, 0.87] |
| C 0H | 1.49 [1.36, 1.68] | 1.50 [1.36, 1.68] | 1.19 [1.08, 1.33] | 0.78 [0.72, 0.87] |
| C 1H | 1.52 [1.37, 1.71] | 1.51 [1.38, 1.68] | 1.24 [1.12, 1.39] | 0.88 [0.79, 0.99] |
| C 2H | 1.59 [1.47, 1.73] | 1.64 [1.50, 1.79] | 1.22 [1.12, 1.35] | 0.75 [0.68, 0.83] |

- **Excess amplitude is supported for `wake=2`** on B, on the Case D split fibre, and on the thermistors of E and C. Case A is inconclusive.
- **"Three times" is one number**: the variance ratio 3.47 of the `wake=2` mean vector in E before. Every other variance ratio is 2.7 or lower.
- **Under the `wake=3` scalar the sign reverses**: the field has too little contrast in D, E after and all of Case C. Only E before keeps an excess (1.19).
- Correlation stays weak throughout (R 0.3–0.56 on thermistors), and is zero in C 2H.

**By zone** (`wake=3`, E before): the spreading-wake cells hold 93 % of the squared error, with a bias of +0.133. Cavity and canyon cells are close (+0.03).

**Filters against shrinkage.** A second comparator was added during this step: shrinkage that also takes the candidate's mean. Without it, a filter that lowers the level beats plain shrinkage through the level alone.

| Reading of post-hoc filters at 2–8 m | Where |
|---|---|
| Gain beyond shrinkage **and** level | `wake=3`, vector filter 2–4 m: C 0H (ΔMAE −0.011), C 1H (−0.021), E after (−0.003 to −0.005) |
| Level change only | Every gain in E before, both parents; `wake=2` in E after and C 0H |
| No gain, or reproduced by shrinkage | Case D, both parents and both filter kinds; C 2H |

**Verdict for M.** On Case D, M's development case, no filter gains anything against the thermistors. The gains in E are changes of level. M has no supported mean-field target on `wake=3`, and on `wake=2` only against the vector data.

---

## 6. T2: blockage (K2)

**Thermistors.** Shortfall is measured minus simulated; a positive correlation with upwind blockage means too slow where blocked.

| Dataset | `wake=2`, `K` | `wake=3`, `K` | `wake=3`, primary scalar |
|---|---|---|---|
| D | +0.49 [0.35, 0.61] | +0.36 [0.19, 0.50] | +0.11 [−0.10, 0.31] |
| E before | +0.60 [0.51, 0.67] | +0.65 [0.58, 0.71] | +0.50 [0.42, 0.57] |
| E after | +0.62 [0.54, 0.69] | +0.50 [0.39, 0.60] | +0.25 [0.10, 0.39] |
| C 0H | +0.64 [0.58, 0.70] | +0.58 [0.50, 0.65] | +0.30 [0.17, 0.43] |
| C 1H | +0.50 [0.40, 0.58] | +0.41 [0.31, 0.51] | +0.23 [0.11, 0.35] |
| C 2H | +0.63 [0.56, 0.70] | +0.50 [0.41, 0.58] | +0.30 [0.20, 0.39] |

- **K2 is supported** for the mean vector in every case. The `wake=3` scalar halves the association and leaves Case D inconclusive.
- In E before the association is not "blocked points too slow". The blocked points are about right (+0.04 to +0.05 at x/H < 2) and the unblocked points are too fast (+0.19 at x/H ≥ 8). See section 7.2.

**Mean flow in the wake:**

| Case | Measured U where reversed | `wake=2` | `wake=3` | Reattachment measured [m] | `wake=2` | `wake=3` |
|---|---|---|---|---|---|---|
| A | −0.117 | −0.234 | −0.217 | 21.1 (stations 12 and 24) | 30.5 | 28.1 |
| B | −0.205 | −0.150 | −0.150 | 62.8–64.1 (stations 60 and 84) | 66.6–66.8 | 61.2–61.4 |
| D split fibre | −0.120 | −0.117 | −0.088 | not measured | | |

- Case A: the reverse flow is twice too strong and the cavity too long; the simulated reattachment lies beyond the two bracketing stations.
- Case B: the reverse flow is too weak and the cavity length is right.
- **The two cases disagree in sign**, so one cavity-strength constant cannot serve both. The optional cavity step of section 7 of the plan is not supported.
- The scalar data cannot separate a cavity-length error from a turbulence error.

---

## 7. T3 and T4: the tower and the shelter

### 7.1 T3: locality and the need for a tower correction

**Locality (measured, Case E):**

| Distance / H | Probes | Measured ΔK [95 %] | Relative to the mean beyond 60 m [95 %] |
|---|---|---|---|
| 0–0.25 | 8 | +0.324 [0.227, 0.438] | +0.284 [0.181, 0.399] |
| 0.25–0.5 | 14 | +0.226 [0.163, 0.296] | +0.186 [0.117, 0.259] |
| 0.5–0.75 | 8 | +0.060 [−0.007, 0.117] | +0.020 [−0.051, 0.085] |
| 0.75–1 | 7 | −0.026 [−0.071, 0.007] | −0.066 [−0.113, −0.024] |
| 1–2 | 23 | +0.047 [0.011, 0.092] | reference |
| ≥ 2 | 20 | +0.033 [0.000, 0.068] | reference |

- **Locality is supported**: the effect ends between 0.5 and 0.75 H. No probe is closer than 7.5 m, so the peak is not sampled.
- The far field rises by +0.03 to +0.05 with an interval that excludes zero; it is either a real weak effect or a normalisation difference between the two tunnel runs.

**By sector, within 30 m** (`wake=3` scalar): measured +0.10 upwind, +0.35 beside, +0.25 downwind; simulated −0.09, +0.09, +0.01. The sign is wrong upwind.

**Other cases:**

| Evidence | Value |
|---|---|
| Case D (100 m tower), level within 15 m and 15–30 m | −0.144 [−0.205, −0.089] and −0.155 [−0.215, −0.093], both parents alike |
| Case C, 1H → 2H within 15 m | short by 0.120 [0.085, 0.155] |
| Synthetic arrays, central block → 60 m tower, `wake=3` mean vector, 0–15 m | −0.04 to +0.09, depending on direction and density |

- **A tower correction is needed** on three independent pieces of evidence. All 78 Case D probes lie within 60 m of the tower, so Case D carries no district information.
- **The D prerequisite fails** (section 3.1). The before-state error does not come from the tower.

### 7.2 T4: where the before-state excess comes from

`wake=3` scalar, Case E before.

**Against distance behind the nearest upwind building:**

| x/H | District (≥ 60 m) bias [95 %] | Near the site (< 30 m) bias [95 %] |
|---|---|---|
| 0–2 | +0.041 [0.007, 0.071] | +0.087 [0.041, 0.140] |
| 2–4 | +0.083 [0.047, 0.120] | +0.128 [0.070, 0.180] |
| 4–8 | +0.148 [0.117, 0.177] | +0.181 [0.121, 0.240] |
| ≥ 8 | +0.162 [0.131, 0.190] | +0.221 [0.181, 0.261] |

The measured K rises from 0.27 to 0.42 across these bins; the simulated K rises from 0.31 to 0.58. The modelled wake recovers too quickly.

**Against buildings crossed on the upwind ray** (probes ≥ 60 m from the tower):

| Buildings upwind | 0 | 1–2 | 3–5 | 6–10 | ≥ 11 |
|---|---|---|---|---|---|
| Bias | +0.242 | +0.127 | +0.115 | +0.108 | +0.083 |

- The bias **falls** inward. Missing accumulation of shelter (S-a) would make it grow.
- The "0 buildings" pairs are not first rows at the domain edge. Over the whole case they are 49 probe-directions looking down a street for 140–420 m. The measured K there is 0.39; the model gives 0.64. The measured field is nearly flat in direction (direction means 0.31–0.37); the model channels along ENE–WSW and SSE–NNW (0.48–0.52 against 0.41–0.46 elsewhere).
- No probe lies within 120 m of the upwind edge, so E cannot test a first-row level error. The inflow is measured down to 1.25 m, so the 2 m level is not an extrapolation. **S-c is not indicated.**

**The tower site against the district.** The district relation is bias = +0.219 − 0.275 · deficit. The site has a lower deficit (0.33 against 0.42) and lies above the relation by +0.049 [0.021, 0.076]. Over the 16 directions the site bias runs from +0.09 to +0.26 and correlates with the mean deficit at −0.78.

**Verdict.**

1. The excess is where the model sees little shelter: far behind the nearest building, along streets, and on the open plot. Sheltered points are about right.
2. Of the fixed candidates, the evidence matches **S-b** (reach and taper). It speaks against S-a and does not indicate S-c.
3. About three quarters of the site error follows the district relation; +0.05 is specific to the site.
4. Aligned streets are a component that no candidate on the list addresses directly. Case C at 0° shows the same error (+0.24 to +0.27).

---

## 8. What this means for the next parts

These four points are the reason for stopping here. Each affects a decision that the plan fixed before the data were seen.

**1. S-b cannot be developed on Case C.** In Case C the points 1–2 H behind a block are already too slow under `wake=3` (−0.16 in 0H, −0.23 in 1H), and the array is only 100 m deep. The plan's selection rule (scalar MAE on C 0H and 1H) will pick no lengthening, or a shortening. E before needs the opposite. Developing on C and transferring to E is then a test that fails by construction.

**2. S cannot pass its Case D condition.** All Case D probes are near the 100 m tower and already too low by 0.09–0.15. More shelter lowers them further. The gate "q and MAE do not worsen in Case D" then fails for the same reason as the tower effect is missing, not because the shelter change is wrong.

**3. M's continuity target needs angle fading, not a spatial blend.** The largest step of the 1° sweep (plane RMS 0.032, 5.4 × the median, at 279° → 280°) comes from the sidewall and upwind-cavity zones switching at an angle threshold. With both off it is 0.016 (2.7 ×). Smoothing the solved field in space by 4 or 8 m leaves it at 3.9 × and 3.3 × the median. A blend across zone edges through the I1 hook cannot remove a zone that appears between two directions. The fix is native: fade the two zones over an angle range.

**4. M has no score target on `wake=3`.** Sections 3.2 and 5. On `wake=2` it has a vector target that `wake=3` already delivers more of.

**Continuity bar measured for M** (`wake=3` parent, one 20 × 30 × 20 m building, 225°–315°): plane RMS ΔK per degree median 0.0059, 95th percentile 0.0084, maximum 0.0321; largest probe step 0.069 (side). Proposed bar: maximum plane RMS at most 0.016, largest probe step at most 0.035, median not above 0.0065.

# Wake handling: investigation and decision

- **Date:** 2026-11-11. Follows `FABEL_DESIGN_AND_ALGORITHM_REVIEW.md` (S4) and replaces its two wake options.
- **Status:** implemented as opt-in `wake=3`, merged into `main` on 2026-11-13 (0.1.0b3). See [implementation and deviations](WAKE_UPDATE_V2.md) and [merged validation](validation/WAKE_UPDATE_V2_RESULTS.md). The historical prototype remains in `build/fabel-wake/` in the research checkout (section 9).
- **Evidence:** about 600 runs of AIJ Cases A, B, D and E at 2 m (A and B also at 1 m), plus 182 runs of one isolated building for continuity.

## 1. Decision

Replace the far wake by a **spreading wake**, and add a **wake turbulence term** to the scalar speed.

1. **Far wake.** The building's shadow, diffused across the wind by a mixing layer that grows linearly downstream (section 5). It has no cut-off and no hard edge.
2. **Superposition.** Each face takes the largest deficit of any building, applied once after all buildings.
3. **Cavity.** Keep the current cavity law. Scale its strength by the sheltered roof-level speed.
4. **Scalar speed.** Report √(|u|² + 2k) with k = sheltered inflow k + 0.08 · U_roof² · (wake shape). This is what a thermistor or a pedestrian sees.

Measured effect, baseline → decision:

| Data | Quantity | Baseline | Decision |
|---|---|---|---|
| A, isolated tower, split fibre | \|U\|/U_H, all 186 points: q / R | 0.68 / 0.89 | 0.74 / 0.93 |
| B, isolated slab, split fibre | \|U\|/U_H, all 224 points: q / R | 0.50 / 0.74 | 0.67 / 0.94 |
| A and B, 2 m | scalar speed: q / R | 0.71 / 0.79 and 0.55 / 0.72 ¹ | 0.86 / 0.91 and 0.89 / 0.89 |
| D, district, thermistor | scalar speed: q / R | 0.26 / 0.40 ¹ | 0.41 / 0.55 |
| E before, thermistor | scalar speed: q / R | 0.08 / 0.32 ¹ | 0.30 / 0.55 |
| E after, thermistor | scalar speed: q / R | 0.24 / 0.30 ¹ | 0.46 / 0.55 |
| E change (after − before) | R / sign agreement / top-10 overlap | 0.40 / 0.73 / 0.41 ¹ | 0.48 / 0.69 / 0.52 |

¹ The current scalar estimate: √(|u|² + 2k) with QES-Turb k. Section 4.3 also compares against the baseline's mean vector speed and against simpler scalar estimates.

What it does not fix: the tower effect in Case E, the ±10° direction thresholds, and the overlong cavity of Case A (section 6).

## 2. What the current wake does

Code: `src/qes_core/winds/PolygonWake.cpp`.

- **Cavity** (lines 501–514): inside an ellipsoid of length d_n(y, z) = L_r √(1 − (y/y_n)²) √(1 − (z/H)²), the flow is reversed with the roof-level speed, u = −u_H (1 − x/1.1d_n)² √(1 − |y/y_n|). L_r is Fackrell's length (line 177).
- **Far wake** (lines 492–500): for d_n < x < 3 d_n, u = u₀ (1 − (d_n/(x + 0.1 d_n))^1.5).
- **Consequences:**
  - The wake is exactly as wide and as tall as the building. Nothing spreads.
  - It ends at x = 3 d_n, where 18 % of the deficit is left.
  - The far wake is skipped where another building stands within L_r (`canyon_factor`, lines 495, 555).
- **A side finding.** With exposed faces on, which every Case E run uses, the ray stops at a solid cell before `canyon_factor` is set (lines 408–413 against 417–420). The cavity is then never shortened by a downstream building. Explored in `WAKE_UPDATE_V2.md` section 3.5: it looks unintended, the street-canyon model hides it in regular canyons, and fixing it leaves the Case E scores unchanged.

## 3. What the measurements show

Cases A and B have split-fibre profiles through the wake, so the mean vector can be compared like for like. Baseline at 1 m, U/U_H at 2 m height:

| Where | Measured | Baseline | Error |
|---|---|---|---|
| A, wake centreline, 0.25–2.75 b behind the lee face | −0.15, −0.15, 0.05, 0.31 | −0.28, −0.28, −0.07, 0.24 | −0.06 to −0.13 |
| A, at the shadow edge (y = 0.5 b), same stations | 0.13, 0.24, 0.28, 0.37 | 0.41, 0.50, 0.58, 0.61 | +0.24 to +0.30 |
| A, 0.12 b outside the shadow | 0.40, 0.39, 0.35, 0.40 | 0.75, 0.75, 0.67, 0.62 | +0.22 to +0.36 |
| B, wake centreline, 0.5–10.5 b behind | −0.14 … 0.23 | −0.19 … 0.18 | within 0.07 |
| B, at the shadow edge (y = 2 b), 3.5–10.5 b behind | 0.06, 0.10, 0.13, 0.29 | 0.54, 0.56, 0.59, 0.58 | +0.29 to +0.48 |
| B, 1 b outside the shadow, 5.5–10.5 b behind | 0.36, 0.30, 0.33 | 0.63, 0.60, 0.59 | +0.26 to +0.30 |
| B, 0.125 H above the roof level, 0.5–10.5 b behind | 0.25 … 0.63 | 1.25 … 1.01 | +0.39 to +1.00 |

- **The centreline is roughly right. The width is wrong.** The measured wake is wider than the building from the lee face on, and it widens by about 0.2 m per metre downstream. The half-deficit point lies 9 m outside the shadow 44 m behind A, and 16 m outside 84 m behind B.
- **The wake is also taller than the building**, by about 0.1 H behind A and 0.25–0.5 H behind B.
- **Scalar speed never drops below about 0.3 U_H in a wake.** At 2 m the measured √(|U|² + 2k) is 0.27–0.53 U_H everywhere behind both buildings, while the mean vector passes through zero. k in the wake is 0.03–0.10 U_H², against 0.02 in the approach flow. A thermistor reads this scalar speed.

## 4. Candidates and results

All scores use the harness metrics (`validation/aij/metrics.py`). q is the hit rate, R the Pearson correlation, FB the fractional bias (positive: model too low).

### 4.1 Isolated buildings, mean vector (2 m grid)

| Variant | A: q / R / MAE | B: q / R / MAE | Reattachment A / B [b] |
|---|---|---|---|
| Measured | – | – | 1.32–1.42 / 7.6–7.85 |
| Baseline | 0.68 / 0.89 / 0.113 | 0.50 / 0.74 / 0.181 | 1.85 / 8.38 |
| Edge value subtracted (review S4, option 1) | 0.69 / 0.89 / 0.114 | 0.50 / 0.73 / 0.186 | 1.83 / 8.34 |
| Cut-off moved from 3 d_n to 10 d_n | 0.70 / 0.89 / 0.112 | 0.51 / 0.75 / 0.180 | 1.86 / 8.38 |
| Spreading, no edge offset | 0.77 / 0.92 / 0.087 | 0.58 / 0.84 / 0.130 | 1.73 / 8.22 |
| **Spreading with edge offset (decision)** | **0.74 / 0.93 / 0.098** | **0.67 / 0.94 / 0.082** | **1.72 / 7.69** |

- **The two cheap fixes do nothing for accuracy.** They remove a step but leave the width.
- **By region, baseline → decision:**
  - stations at or outside the shadow edge: A q 0.60 → 0.90, R 0.73 → 0.96; B q 0.48 → 0.83, R 0.61 → 0.97;
  - RMS error of U below roof height in the wake: A 0.161 → 0.105 U_H; B 0.175 → 0.077 U_H.
- **At 1 m:** A 0.66 / 0.86 → 0.70 / 0.91; B 0.51 / 0.73 → 0.65 / 0.93. The gain does not depend on the grid.
- **Sensitivity to the one fitted constant** (spreading rate c_s, with the offset): 0.15 gives A 0.69 / 0.91 and B 0.70 / 0.94; 0.25 gives A 0.84 / 0.93 and B 0.65 / 0.92. Every value beats the baseline in both cases.
- **Sensitivity to the edge offset** (multiples of the 0.22 R in section 5): 0.5× gives A 0.80 / 0.93, B 0.63 / 0.90; 1.5× gives A 0.68 / 0.92, B 0.66 / 0.93.

### 4.2 Isolated buildings, scalar speed and k

Target: the measured √(|U|² + 2k) at the 2 m probes (A 65 points, B 129).

| Model of the scalar speed | A: q / R | B: q / R |
|---|---|---|
| Baseline, mean vector only | 0.78 / 0.88 | 0.53 / 0.82 |
| Baseline with QES-Turb k (current) | 0.71 / 0.79 | 0.55 / 0.72 |
| Baseline with inflow k | 0.77 / 0.90 | 0.57 / 0.83 |
| Spreading wake, mean vector only | 0.62 / 0.95 | 0.47 / 0.92 |
| **Spreading wake with wake turbulence, c_k = 0.08** | **0.86 / 0.91** | **0.89 / 0.89** |

- **The better mean wake scores lower on its own**, because it removes speed that was standing in for the missing turbulence. The two parts belong together.
- **k itself**, all probes, c_k = 0.10: FAC2 0.83 (A) and 0.70 (B), R 0.42 and 0.43, FB +0.17 and −0.02. QES-Turb: FAC2 0.28 and 0.09, R 0.25 and 0.10.
- **c_k:** the scalar speed at 2 m is best at 0.07; the level of k is best at 0.10–0.13. I chose 0.08.

### 4.3 Districts (2 m grid, K at 2 m)

Mean vector K against the instrument:

| Comparison | Baseline: q / R / FB / MAE | Spreading: q / R / FB / MAE |
|---|---|---|
| D split fibre (vector, 33 points, 0°) | 0.27 / 0.55 / −0.23 / 0.170 | 0.24 / 0.57 / +0.07 / 0.138 |
| D thermistor (198) | 0.23 / 0.43 / +0.44 / 0.218 | 0.14 / 0.39 / +0.70 / 0.249 |
| E before, thermistor (1280) | 0.16 / 0.51 / −0.43 / 0.227 | 0.38 / 0.54 / −0.11 / 0.128 |
| E after, thermistor (1280) | 0.30 / 0.46 / −0.15 / 0.201 | 0.33 / 0.46 / +0.26 / 0.173 |

Scalar speed against the thermistor:

| Comparison | Baseline + QES-Turb k (current) | Baseline + inflow k | Baseline + deficit proxy ² | **Spreading + wake turbulence** |
|---|---|---|---|---|
| D: q / R / MAE | 0.26 / 0.40 / 0.193 | 0.31 / 0.42 / 0.178 | 0.44 / 0.41 / 0.138 | **0.41 / 0.55 / 0.151** |
| E before: q / R / MAE | 0.08 / 0.32 / 0.329 | 0.14 / 0.52 / 0.264 | 0.07 / 0.53 / 0.295 | **0.30 / 0.55 / 0.151** |
| E after: q / R / MAE | 0.24 / 0.30 / 0.267 | 0.32 / 0.47 / 0.208 | 0.27 / 0.50 / 0.226 | **0.46 / 0.55 / 0.135** |
| E change: R / sign / top-10 | 0.40 / 0.73 / 0.41 | 0.44 / 0.73 / 0.59 | 0.49 / 0.71 / 0.59 | **0.48 / 0.69 / 0.52** |

² k = inflow k + 0.15 (K_bg − K)², the post-processing proxy of review X5.

- **The in-canopy level error largely goes away.** In Case E "before" the baseline mean speed is 0.50–0.59 where 0.32–0.36 is measured. The spreading wake gives 0.35–0.47. This is the bias that the canopy-inflow tuning addressed (F07).
- **Pattern correlation rises in every district set**, by 0.03–0.25. Per direction, R improves in 13 of 16 (E before) and 16 of 16 (E after) directions against the baseline mean vector, and in all three Case D angles (0.65 / 0.56 / 0.49 → 0.72 / 0.64 / 0.61).
- **The level is not settled.** With the scalar model, FB is +0.30 in D, −0.32 in E before and −0.06 in E after. One coefficient cannot close all three.
- **The change scores are mixed.** R improves over the current estimate (0.40 → 0.48), but a baseline with inflow k or the proxy keeps a better top-10 overlap (0.59 against 0.52) and sign agreement (0.71–0.73 against 0.69). Section 6 gives the reason.

### 4.4 Superposition rule (spreading wake, mean vector)

| Rule | E before: q / FB | E after: q / FB | D split fibre: R / MAE |
|---|---|---|---|
| Largest deficit (decision) | 0.38 / −0.11 | 0.33 / +0.26 | 0.57 / 0.138 |
| Root sum of squares | 0.36 / +0.27 | 0.19 / +0.65 | 0.59 / 0.133 |
| Product of (1 − D) | 0.04 / +1.08 | 0.01 / +1.29 | 0.62 / 0.155 |

- **The product collapses the district**: wakes without occlusion multiply to zero.
- **The largest deficit is bounded by one wake**, needs no occlusion logic, and is continuous.
- With the scalar model, root sum of squares is level in E before (FB 0.00) but too low in E after (+0.24). The data do not separate the two rules cleanly. I chose the simpler and safer one.

### 4.5 Around the Case E tower

Probe-directions grouped by position relative to the new 60 m tower. Mean K:

| Zone (count) | Measured before → after | Baseline vector | Spreading vector | Spreading scalar |
|---|---|---|---|---|
| Near wake, < 1.5 H behind (96) | 0.36 → 0.52 | 0.59 → 0.38 | 0.47 → 0.21 | 0.55 → 0.55 |
| Far wake, < 5 H behind (103) | 0.36 → 0.40 | 0.52 → 0.49 | 0.38 → 0.30 | 0.48 → 0.49 |
| Within 1.5 H, not in the wake (575) | 0.32 → 0.46 | 0.50 → 0.53 | 0.35 → 0.36 | 0.45 → 0.46 |
| Elsewhere (506) | 0.34 → 0.39 | 0.51 → 0.49 | 0.37 → 0.34 | 0.45 → 0.43 |

- **The tower raises the scalar speed in its own near wake**, from 0.36 to 0.52. Any multiplicative deficit lowers it.
- **Wake turbulence scaled with the roof-level speed explains the level.** The approach flow at 60 m is 1.35 U_ref, and √(2 · 0.08) · 1.35 = 0.54. The same scaling gives the 0.3–0.45 U_H of Cases A and B. In the "after" state the near-wake R rises from 0.20 to 0.45, and around the tower from 0.55 to 0.63.
- **The measured rise elsewhere is +0.05**, far from any changed building. Part of the change bias (−0.10 in every model) may therefore lie between the two measurement series, not in the model.

### 4.6 Continuity and cost

- **Wake edge** (one 20 × 30 × 20 m building, 2 m grid): the largest step in K between adjacent cells, 41 and 61 m behind the lee face, falls from 0.20 and 0.16 to 0.04 and 0.03.
- **Wind direction:** the largest 1° jump at the far-wake probe falls from 0.057 to 0.016. The jumps at ±10° stay (5.3× and 5.4× the median step). They come from the upwind cavity and the sidewall zone (review S3).
- **Cost:** one Case E direction at 2 m (1.8 M cells, 510 buildings, 8 threads) takes 5.3 s with the baseline, 6.2 s with the prototype cut at a 5 % deficit and 7.0 s cut at 2 %. The scores are identical for both cuts. The prototype evaluates every building's wake twice, once for the deficit and once for the turbulence. A single pass that stores the dominant building was considered and rejected: it makes k_w jump where wakes cross (`WAKE_UPDATE_V2.md`, section 3.1).

### 4.7 Structural choices that did not matter

Each moved every district score by 0.02 or less:
- applying the deficit before or after the street-canyon, sidewall and rooftop zones;
- scaling the cavity by the sheltered or the unsheltered roof-level speed;
- starting the mixing layers at the upwind extent or at the centroid (isolated cases: 0.04 in q).

## 5. The chosen formulation

In the wind frame of building b: x downwind from the centroid, y across, z above ground. The footprint spans [y₁, y₂] across the wind and starts at x₁; its base and top are z_b and z_t.

- **Mixing-layer width:** σ(x) = max(c_s (x − x₁), Δ/2), with c_s = 0.2 and Δ the grid spacing.
- **Edge offset:** δ = 0.22 R √(1 − ((0.45 R − L)/(0.45 R))²) for L < 0.9 R, else 0. Here R = min(W, H)^(2/3) max(W, H)^(1/3), L is the building length along the wind and W its width across it. This is the thickness, at the trailing edge, of the roof and side separation bubble that the rooftop and sidewall models already use (`PolygonWake.cpp:240-246`, `Sidewall.cpp:118-121`). The code uses half this height (0.11 R); the full 0.22 R fits Case B better and Case A slightly worse (4.1).
- **Shape:**
  - F_y = ½ [erf((y − y₁ + δ)/√2σ) − erf((y − y₂ − δ)/√2σ)]
  - F_z = the same between z_b and z_t + δ, plus its mirror image in the ground
  - G_b = F_y F_z for x > x₁, and 0 inside the shadow upstream of the lee wall
- **Deficit:** D = max over buildings of G_b. Then u₀ ← u₀ (1 − D) on every face that no cavity wrote.
- **Cavity:** the current law, with u_H replaced by u_H (1 − D) at the building's own roof.
- **Turbulence for the scalar speed:** k = k_inflow(z) (1 − D)² + c_k max_b (U_H,b² G_b), with c_k = 0.08. Scalar speed S = √(|u|² + 2k).

Properties:
- The cross-wind integral of F_y is constant, so the centreline recovers because the wake widens. No separate decay law is needed, and none improved the fit.
- With σ → 0 it is the building's shadow with zero speed, which is the current model's limit near the lee face.
- It is smooth in position and in wind direction, and independent of the building order.

Constants:

| Constant | Value | Origin |
|---|---|---|
| c_s | 0.2 | Fitted on A and B; 0.15–0.25 all beat the baseline. Plane mixing layers grow at a comparable rate. |
| 0.22 R, 0.9 R | – | The roof-cavity scaling already in the code; not fitted. |
| c_k | 0.08 | Fitted on A and B (0.07–0.13 depending on the target). |
| Superposition | largest | Chosen on D and E (4.4). |

## 6. What it does not fix

- **The tower effect.** Around the Case E tower the measured speed rises by 0.14 outside the wake; every variant gives 0.01–0.03. This needs downwash and corner streams, as `MOMENTUM_PLAN.md` and F08 say. The spreading wake makes the miss more visible in the mean vector, because the tower's wake is now wide. That is why the top-10 overlap is lower than for the baseline with inflow k.
- **Direction thresholds** in the upwind cavity and sidewall zones (review S3). Unchanged, and still needed.
- **The Case A cavity.** It stays 20–30 % too long (1.72 b against 1.32–1.42 b) and reverses too strongly. Scaling the cavity by 0.6 fixes A (q 0.81, 1.49 b) and breaks B (q 0.51). With two cases I cannot fit a law for it.
- **The roof.** The wake now extends above roof level behind the building, but the flow on the roof itself is unchanged (R18).
- **Oblique wind.** In Case D at 22.5° and 45° the pattern improves but the level is low (MAE 0.16 and 0.20, against 0.14 and 0.17 for the baseline with the proxy). There is no vector data at oblique incidence.

## 7. Implementation plan

1. **Native, one batch** (re-qualify the policy identity once; combine with review S2 and S3):
   - a new wake code, `Parameterizations(wake=3)`, leaving 2 as the default until step 4;
   - `PolygonWake.cpp`: keep the cavity; replace the far-wake write by the deficit accumulation of section 5;
   - `WINDSGeneralData`: two accumulators (deficit per u and v face), the wake turbulence per u face, and one application after the wake loop;
   - return two cell fields with the result: the deficit D and the wake turbulence source U_H² G.
2. **Python:** a scalar-speed accessor on the result that uses the two fields and the inflow k. Comfort statistics should use it where they now use the mean vector.
3. **Tests:**
   - one isolated box: symmetry, D ≤ 1, no step above 0.05 in K between adjacent cells outside the cavity;
   - σ → 0 reproduces the shadow;
   - order independence: shuffled building order gives identical fields;
   - the direction sweep of 4.6 as a regression test.
4. **Validation gates** (prototype values less a margin of 0.03), on the full harness with turbulence on:
   - A: q ≥ 0.71 and R ≥ 0.90; B: q ≥ 0.64 and R ≥ 0.91, on |U|/U_H at 2 m and 1 m;
   - D split fibre: MAE ≤ 0.15;
   - E before and after, scalar: q ≥ 0.27 and 0.43, R ≥ 0.52 in both;
   - E change: R ≥ 0.45, and report sign agreement and top-10 overlap beside the baseline.
   - If the gates pass, make it the default and re-baseline `headline.md`.
5. **After it lands, re-evaluate:** the canopy inflow (F07), **closed as a wake follow-up on 2026-11-13**: most of its bias is gone (Case E before mean-vector FB −0.43 → −0.11), and the research plan closes canopy backgrounds; the tall-building zone (F08) against section 4.5; QES-Turb's role, since the wake term now carries the scalar speed.

Relation to existing items: this replaces review S4 (both options) and is an alternative to L3 (the Singh envelope), which was not run. It leaves review S3, F08 and the momentum plan as they are.

## 8. Limits

- **Two isolated cases carry the wake shape.** Both are 32 m tall, at one wind direction, in one tunnel. c_s and c_k come from them.
- **District data are scalar.** The mean-vector wake can only be judged there through the turbulence term, so the two choices are confounded in D and E.
- **The prototype reads its switches from environment variables** and evaluates the wake for every cell in a bounding box. It is not production code.
- **Raised buildings and non-convex footprints** follow the formulas of section 5 but have no dedicated test. Case E contains both.
- **No occlusion.** A low building's wake continues behind a taller one. Under the largest-deficit rule this had no visible cost, but it was not isolated.
- **Not run:** the unit tests, the full validation, 0.5 m grids, and turbulence-on runs of the spreading wake (QES-Turb on the new field).

## 9. Reproduce

Scripts and the patch are in `experiments/fabel_wake/` (the directory is git-ignored).

```sh
experiments/fabel_wake/build.sh                       # patched copy -> build/fabel-wake/package
export PYTHONPATH=build/fabel-wake/package:validation OMP_NUM_THREADS=3
W="QES_WAKE_MODE=2 QES_WAKE_BUB=2 QES_WAKE_CS=0.2"
.venv/bin/python experiments/fabel_wake/wk_run.py base ab2,ab1,d,e
.venv/bin/python experiments/fabel_wake/wk_run.py w3 ab2,ab1,d,e $W      # zsh: ${=W}
.venv/bin/python experiments/fabel_wake/wk_score.py -v base w3
WK_MODELS="vec,amb,proxy:0.15,wake:0.08" .venv/bin/python experiments/fabel_wake/wk_scalar.py base w3
.venv/bin/python experiments/fabel_wake/wk_tower.py base w3
.venv/bin/python experiments/fabel_wake/wk_dir.py
```

| File | Purpose |
|---|---|
| `patch_tree.py`, `spread_wake.inc` | The native patch, applied to a copy of `src/qes_core` |
| `wk_run.py` | Runs AIJ cases with one variant; stores probe records in `build/fabel-wake/out/` |
| `wk_score.py`, `wk_scalar.py` | Mean-vector and scalar-speed scores |
| `wk_tower.py`, `wk_dir.py`, `w0_anatomy.py` | Tower zones, continuity, and the profile tables of section 3 |

Other switches: `QES_WAKE_COMBINE` (0 largest, 1 root sum of squares, 2 product), `QES_WAKE_EDGE=1` and `QES_WAKE_FF` (the two cheap fixes), `QES_WAKE_CAV` (cavity scale), `QES_WAKE_DMIN`, `QES_WAKE_LATE`, `QES_WAKE_SHELTER`, `QES_WAKE_ORIGIN`.

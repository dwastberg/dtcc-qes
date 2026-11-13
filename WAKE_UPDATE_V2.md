# Wake update v2: implementation plan

- **Date:** 2026-11-11. Implements the decision in `FABEL_WAKE_INVESTIGATION.md` (called "the investigation" below).
- **Goal:** a spreading far wake and a wake turbulence term for the scalar speed, as an opt-in model first and the default after validation.
- **Status:** implemented on branch `feat/wake-update-v2` (off `main`) as an opt-in `wake=3`; every W4 gate passes; the native identity is re-qualified for the default `wake=2`. The default switch is not made (section 9, W6) and is open for decision. See section 9 for each step's outcome. The prototype in `experiments/fabel_wake/` is the reference for behaviour, not for code.

## 1. Scope

In scope:
- A new wake model, `Parameterizations(wake=3)`: the current cavity, with the far wake of section 5 of the investigation.
- Two new result fields: the wake deficit D and the wake turbulence k_w.
- A scalar speed on the result, and its use in the validation harness and in comfort.
- A fix for `canyon_factor` with exposed faces (section 3.5). It applies to every wake code, including the current default.
- Tests, validation gates, and one re-qualification of the solver policy.

Out of scope (unchanged by this plan):
- The cavity law, including the overlong Case A cavity.
- The upwind cavity, sidewall, rooftop and street-canyon models, and their ±10° thresholds (review S3).
- The tower effect (F08 of `CLAUDE_WIND_EXPERIMENTS.md`; the momentum route of `MOMENTUM_PLAN.md`).
- QES-Turb. It keeps running on the final field as today.

## 2. Decisions to confirm before coding

| # | Question | Recommendation |
|---|---|---|
| D1 | Opt-in code or new default at once? | Opt-in `wake=3` through steps W1–W5; switch the default in W6 only if the gates pass. The pedestrian policy stays qualified for `wake=2` until then. |
| D2 | Where does the inflow k come from outside the AIJ cases? The profiles carry no turbulence. | **Settled (section 3.4):** an optional `inflow_tke` profile on the scalar-speed call; without it, k = 5.5 u*², with u* from a log-law fit to the inflow over the model's height range. |
| D3 | Batch other native changes into the same re-qualification? | Yes, if they are ready: review S2 (stop rule, ω) and S3 (thresholds). Do not wait for them. |
| D4 | Does comfort switch to the scalar speed by default? | Not in this plan. Add it as an option (`speed="scalar"`), report both in validation, and decide after W5. |
| D5 | Is the `canyon_factor` behaviour with exposed faces intended (`PolygonWake.cpp:408-420`)? | **Settled (section 3.5):** no, it is a defect with a small effect. The fix is step W1b. |

## 3. Design

### 3.1 Model

The model is the prototype's (`experiments/fabel_wake/spread_wake.inc`) with two changes, listed at the end of this section. It is stated here in full so that it can be reproduced without reading that file. W1c implements exactly this; anything further comes afterwards (W1d).

**Fields**, per building b in its wind frame:
- σ(x) = max(0.2 (x − x₁), Δ/2), the same across the wind and in height; Δ is the horizontal grid spacing.
- G_b = min(1, T(x) F_y F_z), with T the end taper of the truncation rule below, and
  - F_y = ½ [erf((y − y₁ + δ)/√2σ) − erf((y − y₂ − δ)/√2σ)],
  - F_z = ½ [erf((z − z_a)/√2σ) − erf((z − z_c)/√2σ)] plus the same term at −z (the ground image).
- D = max_b G_b, kept separately on u faces and on v faces.
- u₀, v₀ ← (1 − D) · u₀, v₀ on every interior face that no building's cavity wrote; w₀ is untouched. No far-wake cell flag is set.
- Shelter: s_b = 1 − max(D_u, D_v) at the face where the building reads its roof-level wind (centroid column, roof level), with D the maximum over every building, b included (b's own G is zero there unless that point lies behind its own lee wall). The cavity strength and U_H,b use s_b · u_H. The wind direction and L_r do not change.
- k_w = 0.08 · max_b (U_H,b² G_b), on u faces, with U_H,b the sheltered roof-level speed.

**Geometry rules.**

| Quantity | Rule |
|---|---|
| Frame | Origin at the footprint centroid; x along the roof-level inflow at the centroid, y across it, z above the model ground. |
| Shadow edges y₁, y₂ | The bounding extent of the footprint vertices across the wind. Not the effective width. |
| Start of spreading x₁ | The bounding upwind extent of the vertices, the same for every y. |
| Lee wall x_w(y) | The span [y₁, y₂] is cut into strips at most Δ/2 wide. x_w is the most downstream crossing of the strip's centreline with a polygon edge that counts as a face (`isFace`); hole edges count too. |
| Exclusion | G_b = 0 for x ≤ x₁ everywhere, and for x < x_w(y) inside y₁ < y < y₂. So a courtyard or a notch gets no deficit from its own building. Outside [y₁, y₂] the deficit starts at x₁, beside the building. |
| Bubble scale R | R = min(W, H)^(2/3) max(W, H)^(1/3), with W = area / (x₂ − x₁) the effective cross-wind width and H the building height above its base. |
| Edge offset δ | δ = 0.22 R √(1 − ((0.45 R − L)/(0.45 R))²) if L < 0.9 R, else 0, with L = area / (y₂ − y₁) the effective length along the wind. |
| Upper edge z_c | z_c = z_t + δ, with z_t = base + H, the physical roof. Not the modified wake height that the cavity uses. |
| Lower edge z_a | 0 for a building on the ground. For a raised building (base > 0): max(base − δ, 0). |
| Evaluation points | u faces at (iΔx, (j+½)Δy), v faces at ((i+½)Δx, jΔy), both at the cell-centre heights. |

**Truncation rule.** The cut-off limits how far downstream a building is evaluated. It does not zero individual values below a threshold.
- **Reach x_r:** march x from x₂ + Δ in steps of 2Δ. Stop at the first x where F_y F_z on the centreline y = (y₁ + y₂)/2 is below 0.05 both at z = 0 and at z = (base + z_t)/2. The domain diagonal caps it.
- **Taper start x_s:** the first x in the same march where both values are below 0.10.
- **Taper:** T = 1 for x ≤ x_s; T = s²(3 − 2s) with s = (x_r − x)/(x_r − x_s) beyond it. So the deficit fades from at most 0.10 to zero at x_r.
- **Evaluated region:** x₁ < x ≤ x_r; the grid-aligned box of faces around the rotated rectangle x₁ ≤ x ≤ x_r, |y| ≤ max(−y₁, y₂) + δ + 3σ(x_r) (so the bounds can differ by one row between the two sides); layers with z ≤ z_t + δ + 3σ(x_r).
- **Inside the region** every value is kept, except faces with T F_y < 10⁻⁴ (u and v faces of a column are tested separately) and, since W1d, layers above z_c + 6σ(x) of their own column, where F_z < 10⁻⁹.

| Truncation | Largest step it leaves in D |
|---|---|
| End of reach | None; the taper brings D to zero. |
| Lateral and top bounds | 0.0014 near x_s (the tail beyond 3σ), less elsewhere. |
| Skipped columns | 10⁻⁴. |

**Why k_w keeps the prototype's rule.** An earlier draft took k_w from the building with the largest G, to save the second evaluation. That is rejected:
- Where two wakes cross, the selected building switches. D stays continuous, but k_w jumps by the ratio of the two U_H²: a factor of four for roof speeds that differ by two.
- The maximum of U_H,b² G_b is continuous wherever each G_b is.

**One field pass, with the same values.** The prototype evaluates every building twice, because U_H,b needs the complete D. But it needs D only at one point per building. So:
1. geometry of every building (frame, extents, δ, reach);
2. shelter s_b for every building, from G_c of every other building c at b's roof point: N² point evaluations, 260,000 for Case E;
3. one pass over the field that accumulates D and k_w together;
4. cavities, with the sheltered roof speed; then the application.

This is a rearrangement, not an approximation, with one caveat found in W1c: the prototype read U_H,b for k_w after the earlier buildings' cavities had been written, the single pass reads it before any cavity. They differ only where a cavity reaches another building's roof point, which no W1c run showed (k_w agreed to 1.6·10⁻⁸ U_ref²). It did not halve the overhead (measured in W1c: +0.60 s against the prototype's +0.62 s); W1d did (section 9).

**Changes from the prototype.**

| Change | Reason | Evidence |
|---|---|---|
| End taper | Removes the largest discontinuity the model had: a step of just under 0.05 in D at the end of every wake. | Prototype with `QES_WAKE_TAPER=2` against the hard cut, A, B, D and E at 2 m: every score equal to 0.002; the 2 m speed plane changes by at most 0.002 in A, B and D and 0.036 in E (mean 0.001); no change in run time. |
| z_t is the physical roof | The prototype passed the cavity's modified height. With rooftop model 2 that already contains the shell height (0.11 R), and δ added the bubble a second time. With the high-rise model it is a fitted cavity height, not a shadow. It also makes the wake depend only on the footprint, base and height. | No validated number moves: the defaults (`rooftop=1`, `high_rise=0`) leave the height unmodified, and every baseline run and every prototype run uses them. Not tested with `rooftop=2` or `high_rise=1`; the sensitivity campaign has both settings, and W4 reports them. |

Considered and left as in the prototype:
- **R uses H above the base**, where the rooftop model uses the absolute roof height. They differ only for raised buildings, for which there is no measurement. The body's own height is the plausible scale for its separation bubble.
- **A reach cut at 0.02 in place of 0.05.** The scores are identical, and it costs 0.8 s more per Case E direction in the prototype. With the taper there is no step left to justify it.

**Differences in form only:**
- **k_w is returned at cell centres**, averaged from the two u faces, so that it samples like the other fields. **D** is averaged from the four horizontal faces (u and v).
- **No environment variables.** The constants (0.2, 0.22, 0.9, 0.08, the reach cut 0.05, the taper start 0.10, the skip 10⁻⁴ and, since W1d, the layer cut 6σ) are named constants in one QES-free header, `dtcc/api/wake_model.h`, which the kernel and the bindings share (`_qes.spreading_wake_constants`, recorded in `metadata["wake"]`). They are not user settings.

### 3.2 Native structure

| File | Change |
|---|---|
| `winds/SpreadingWake.h/.cpp` (new) | A free function that takes one building's wind-frame geometry (vertices, extents, base, top, direction) and the domain, and either returns G at one point or accumulates D on u and v faces and U_H² G on u faces. No dependence on `WINDSGeneralData` beyond the grid, so it can be unit-tested alone. |
| `winds/PolygonWake.cpp` | Split into a geometry preamble (lines 100–350 today) and the cavity/far-wake loop. For `wakeFlag == 3`: skip the far-wake writes and the flag-5 marking; record cavity faces; scale `u0_h`, `v0_h` by the shelter factor. Codes 1 and 2 must stay bit-identical through the split. The `canyon_factor` fix of section 3.5 follows as a separate commit. |
| `winds/WINDSGeneralData.h/.cpp` | Accumulators (D on u and v faces, k_w on u faces, cavity mask), sized only for code 3. In `applyParametrizations`: the four steps of section 3.1 (geometry, shelter, field pass, cavities), then one application, all before the street-canyon stage. |
| `winds/WindModelInputs.h`, `dtcc/model_inputs.cpp:183` | Accept `wake_flag` up to 3; `cavity_factor` and `wake_factor` as for code 2. |
| `dtcc/api/wind_config.h`, `dtcc/wind_runner.cpp`, `src/cpp/bindings.cpp` | Two optional float fields on the result, `wake_deficit` and `wake_tke`, centred and stripped of ghost layers like `velocity`. Absent for codes 0–2. |
| `src/qes_core/CMakeLists.txt` | Add the new source. |

Notes:
- **Friction velocity.** Computed in Python from the profile (section 3.4); no native change.
- **Threading.** The per-building loop over cells writes distinct faces, so it can use the existing OpenMP setup. The loop over buildings stays serial, which keeps the result independent of the thread count. `check_openmp` must cover it.
- **Memory.** Three float arrays and one byte mask of the grid size, for code 3 only: about 13 bytes per cell (24 MB at 1.8 M cells).
- **Precision.** The wake is computed in double and stored in float, like the other zones. It runs before the solve, so the float32 and float64 solver paths see the same initial field.

### 3.3 Python

| File | Change |
|---|---|
| `parameterizations.py` | `wake` maximum 3; docstring. No schema bump: the field set is unchanged. |
| `result.py` | `WakeFields(deficit, tke)` on `WindResult` (None unless code 3). `WindResult.scalar_speed(inflow_tke=None)` returning √(|u|² + 2k), k = k_inflow(z)(1 − D)² + k_w. `sample` and `sample_points` gain the scalar speed where the wake fields exist. `to_dtcc` exports the two fields. |
| `wind.py` | Pass the fields through; record the model constants and the k source in `metadata["wake"]`. |
| `comfort.py` | Option to assess on the scalar speed (D4). Default unchanged. |
| `solver_control.py` / policy | `wake=3` reports `unqualified_model_settings` under the adaptive policy until W6, as any non-default setting does today. |

### 3.4 Inflow k without measured turbulence

Investigated on the four AIJ inflow tables, which give U(z) and k(z), and on the stored prototype runs (`experiments/fabel_wake/wk_kin.py`).

**Rule.**
- k_inflow = 5.5 u*², constant with height. 5.5 follows from the neutral surface-layer values σ_u, σ_v, σ_w = 2.4, 1.9, 1.25 u*.
- u* = κ a, where a is the slope of a least-squares fit U(z) = a ln(1 + z/z₀) to the inflow speed at 32 log-spaced heights from 1 m to the top of the model domain. Both a and z₀ are free; the profile's declared roughness is not used.
- `UniformProfile` has no shear to fit. It uses the declared roughness: u* = κ U_ref / ln(1 + z_ref/z₀).
- A user-supplied `inflow_tke` always takes precedence. The AIJ validation keeps using the tunnel tables.

**Why this definition of u*.**

| Candidate, with k = 5.5 u*² | Model k over table k at 2 m (A, B, D, E) | Comment |
|---|---|---|
| Declared roughness at the reference height | 0.33, 0.34, 0.33, 0.19 | The harness roughness is the fitted tail of the lowest four points (10⁻⁴ m). It does not describe the profile. |
| Local slope dU/d ln z at each height | 0.21, 0.19, 0.24, 0.14 at 2 m; 2–5 at roof height | Noisy on tabulated profiles, and grows with height. |
| Slope at one height (10 m, or the reference height) | 0.2–1.5, or 1.1–4.9 | Depends on the chosen height. |
| **Log fit from 1 m to the domain top** | **0.68, 1.10, 0.64, 0.72** | Chosen. |
| Log fit over the whole table | 1.9, 2.1, 2.6, 1.7 | Needs a profile top, which analytic profiles do not have. |
| AIJ intensity law, I = 0.1 (z/z_G)^(−α−0.05) | 1.9, 2.6, 2.0, 1.6 | Needs a terrain category for z_G. |

- **For a `LogProfile` the fit is exact**: it returns κ U_ref / ln(1 + z_ref/z₀). At 10 m this gives σ_u/U = 0.17, 0.21, 0.32 for z₀ = 0.03, 0.1, 0.5 m, against 0.17, 0.22, 0.33 from the Eurocode intensity 1/ln(z/z₀).
- **The three inflow kinds of the harness agree**: measured, power-law and log fits of the same table give 0.64–1.28 of the table k at 2 m.
- **The weak point is the fit window.** Halving or doubling the top height changes k by a factor 0.4–1.7 on the tunnel tables, and by about ±20 % for a power law of exponent 0.22. The tunnel profiles are not log layers: the same fit below 20 m gives k/u*² of 11–23.

**Why the weak point is acceptable.** The scores barely depend on the inflow k, because the wake term carries the scalar speed where it matters:

| Inflow k | A, B at 2 m: q | D: q / R | E before: q / R | E after: q / R | E change: R |
|---|---|---|---|---|---|
| None | 0.86, 0.88 | 0.40 / 0.56 | 0.37 / 0.55 | 0.47 / 0.57 | 0.51 |
| Tunnel table (the investigation) | 0.86, 0.89 | 0.41 / 0.55 | 0.30 / 0.55 | 0.46 / 0.55 | 0.48 |
| Table × 3 | 0.91, 0.91 | 0.43 / 0.53 | 0.22 / 0.53 | 0.43 / 0.52 | 0.40 |
| **5.5 u*², fit to the domain top** | 0.86, 0.89 | 0.41 / 0.55 | 0.32 / 0.55 | 0.46 / 0.56 | 0.49 |
| 5.5 u*², declared roughness | 0.86, 0.88 | 0.41 / 0.55 | 0.36 / 0.55 | 0.46 / 0.57 | 0.51 |

- The chosen rule reproduces the table-based scores within 0.02 everywhere. Step V0's criterion (0.03) is met.
- Only Case E "before" reacts, and it prefers less inflow k. That is the district level bias already noted, not evidence about the rule.
- **Limit:** the tunnel inflows carry more turbulence than their near-ground shear implies, so they cannot confirm 5.5 for the atmosphere. The constant rests on the surface-layer values, the fit on the tables.

### 3.5 Fix: `canyon_factor` with exposed faces

**Problem in one line.** With exposed faces on (the default), a building's cavity is never fitted to the gap in front of a downstream neighbour, because the ray that measures the gap stops before it records the distance.

**What the code does.** Before writing a wake, `polygonWake` marches a ray downstream from each lee-wall strip at 0.75 H (`PolygonWake.cpp:400-421`). If it meets fluid and then another building within the cavity length L_r, it sets `canyon_factor = distance / L_r`. That factor then:
- shrinks the cavity ellipsoid at every height, so that it closes at the downstream wall (lines 475, 535, 595);
- switches the far wake off for that strip (lines 495, 555, 614).

With exposed faces on, the ray takes an extra branch first (lines 408-413): it skips cells of the building's own footprint, and then `if (solid) break;`. That `break` fires for any solid cell, also after fluid has been found, so the assignment four lines below is never reached. `canyon_factor` stays 1 for every strip.

**Why it looks unintended.**
- The same branch in `StreetCanyon.cpp:204-208` is guarded by `x_id_min < 0`: it stops only at a neighbour that touches the wall, and otherwise falls through to the legacy logic. The guard is missing here.
- `docs/building-contacts.md` ("Native exposure rule") says the wake search "stops at a solid neighbor". It does not say the cavity is no longer fitted to the gap.
- Both came in with one commit (b491499, canonical footprints). No test covers `canyon_factor`.

**What it changes** (`experiments/fabel_wake/cf_canyon.py`: two 80 m slabs, 15 m apart, wind across; `QES_CF_FIX=1` adds the missing assignment in the research build):

| Setup | Strict footprints | Exposed faces | Exposed faces + fix |
|---|---|---|---|
| Equal heights, canyon model on: all sampled points | – | identical to strict | identical to strict |
| Equal heights, canyon model off: cavity cells | 6,682 | 7,226 | 6,682 |
| Same: u/U_ref in the gap at 0.75 H | +0.04 | −0.22 | +0.04 |
| 20 m slab before a 10 m slab: any point | – | differs from strict | no effect |

- **The street-canyon model hides it.** Where that model accepts the gap, it overwrites the cavity, and the result is the same either way.
- **It shows where the canyon model rejects a gap** (oblique or irregular faces): the upstream cavity keeps its full isolated length and strength up to the neighbour's wall.
- **With the fix, exposed faces reproduce strict footprints exactly** in the equal-height case, flags and velocities.
- **The tall-before-short difference is a separate, documented rule**: in the second loop the ray stops at any solid neighbour at each level, so a tall building's wake no longer continues behind a lower one below its roof. The fix does not touch that.

**Effect on Case E** (32 runs each, 2 m): with the fix, 1.5 % of probe-directions change by more than 0.01 in K, 0.2 % by more than 0.05, and none by more than 0.1. Every pooled score is unchanged to 0.002, for the current wake and for the spreading wake.

**Proposed fix.** In the first search loop only (`PolygonWake.cpp:412`), record the gap before stopping at a solid neighbour, when fluid has already been found:

```cpp
// today
if (solid) break;

// fixed
if (solid) {
  if (x_id_min > 0) canyon_factor = xc / Lr;
  break;
}
```

- **Same value as the legacy branch.** `xc / Lr` at the first solid cell after fluid is what lines 417-419 compute with strict footprints.
- **A touching neighbour is unchanged.** There `x_id_min` is still −1, so the factor stays 1 and the ray stops as today. The wall is not exposed in that case anyway.
- **The second loop (line 423 onward) is not touched.** Its stop at any solid neighbour is the documented rule.
- **The street-canyon search is not touched.** It already has the guard.

**What the fix changes for users.**
- It applies to wake codes 1, 2 and 3 whenever `Footprints(exposed_faces=True)`, which is the default of `Footprints`. Strict footprints are unaffected.
- Results change only in gaps shorter than L_r that the street-canyon model does not take over. There the cavity closes at the downstream wall and the strip writes no far wake.
- **This includes the far wall of a courtyard** (found in W1b): the ray from the courtyard's upwind inner wall meets the same building across the courtyard. Strict and exposure-off footprints already fit the cavity there; with the fix, exposed faces do too (wind across, canyon model off: identical to exposure off).
- **The sidewall model keeps its own exposure rule** (found in W1b): with exposed faces it ignores mutable flags at the upwind corner, so beside a downstream slab it can differ from strict footprints at one layer (120 cells in the two-slab case). That is documented exposure behaviour, not part of this fix; the tests isolate the wake with the sidewall model off.
- The Case E scores do not move (above), so no headline number is re-baselined for this fix alone.

**What goes with it.**
- A native test and a Python test (section 5).
- One sentence in `docs/building-contacts.md`: the cavity is fitted to the gap in front of a separated downstream neighbour, with or without exposed faces.
- A commit message that states the change in default results and its measured size; the repository has no changelog.

## 4. Work steps

Each step ends in a state that builds and passes the existing tests.

- **V0. Inflow k: done** (section 3.4). Remaining work, in W2:
  - `profiles.py`: a `friction_velocity(top)` helper with the fit of section 3.4, and the `UniformProfile` fallback;
  - record u*, the fit window and the k source (`"profile fit"`, `"declared roughness"` or `"user"`) in `metadata["wake"]`;
  - tests: exact for `LogProfile`; the fallback for `UniformProfile`; `inflow_tke` overrides.
- **W1. Native kernel and wiring**, as three commits:
  - **W1a. Split `PolygonWake.cpp`** with no change in behaviour. Codes 1 and 2 are bit-identical to the current build.
  - **W1b. `canyon_factor` fix** (section 3.5), with its tests and the documentation sentence. From here on, the bit-identity reference for codes 1 and 2 is the W1b build.
  - **W1c. Spreading wake** (sections 3.1 and 3.2), exactly as stated there, with the native checks of section 5. Compare fields and scores against the prototype build with `QES_CF_FIX=1 QES_WAKE_DMIN=0.05 QES_WAKE_TAPER=2` (tolerances in section 6). **The reference is the prototype patch applied to `main`'s sources** (`patch_tree.py`, with the dump extended to D on v faces), not the stored run `t5`: that was built from the research branch, whose building reference point differs for concave and courtyard footprints. The comparison needs the result fields, so it runs after W2; W1c and W2 are separate commits.
  - **W1d. Profile, then optimise.** Only after W1c passes, and only if the cost target of section 6 is missed. Candidates: tighter evaluation regions; a cheaper error function. Each change must pass both the field and the aggregate tolerances of section 6 against the W1c build.
- **W2. Bridge and Python fields.** Section 3.3 without comfort. `wake=3` is now usable from `wind.run`.
- **W3. Harness.**
  - A `wake3` campaign: the baseline matrix with `parameterizations={"wake": 3}`; RunSpec already carries this.
  - Record `K_scalar_wake` beside `K` and `K_scalar` in `runner.run`; add it to `compare.case_d`, `case_e_comparisons` and the A/B scalar comparison.
  - Extend `run_full_validation.py` and the headline table with the new rows. **Changed in W3:** both are untracked research files in the main checkout (`validation/run_full_validation.py`, `validation/output/report/headline.md`), not on `main`. W3 adds `validation/run_wake_validation.py` instead, which runs the W4 matrix and prints the gate table of section 6.
- **W4. Validation.** Section 6. Write the outcome to `validation/WAKE_UPDATE_V2_RESULTS.md`.
- **W5. Comfort option** (D4), with one test on a stored result pair.
- **W6. Default switch.** Only if W4 passes:
  - default `wake=3`; re-qualify the policy identity with `tools/check_policy_compatibility.py`; **(found in W6: this cannot qualify a default switch.** The check, and `docs/solver-control-requalification.md`, accept a new identity only if all 24 frozen S7 workers reproduce their fields exactly, and those workers run `wind.run` with the default parameterizations; `pedestrian_policy.cpp` also requires `wake_flag == 2`. A switch needs a new policy qualification study on `wake=3` fields.)
  - re-baseline `headline.md` and the feature-merge baseline fixtures;
  - update `README.md`, `docs/`, `QES_TURBULENCE.md` (scalar speed), `PROVENANCE.md` (the new file is not from QES).
- **W7. Clean-up.** Delete `build/fabel-wake`; keep `experiments/fabel_wake/` as the record of the prototype.

Order and size: W1 (the bulk) → W2 → W3 → W4 → W5/W6 → W7. W1 and W3 can overlap once the field names are fixed.

## 5. Tests

Native (`tests/native/check_wake.cpp`, new):
- one box, wind along x: D is symmetric in y (to 10⁻⁵, and to 0.002 on the region's bound rows, see 3.1); D ≤ 1; D = 0 upstream of x₁; the cross-wind integral of F_y is constant in x to 1 % (at mid-height of a 200 m slab, where F_z ≈ 1);
- σ → 0 (c_s = 0 through a test hook): D is the shadow indicator;
- shuffled building order gives identical u₀, v₀, D and k_w;
- two boxes of 10 m and 40 m whose wakes cross: outside the cavities, k_w has no step between adjacent cells above 0.02 U_ref² (no jump where the larger wake changes owner);
- truncation: along the centreline of one box, D decays monotonically from the lee wall, has no step above 0.01 between adjacent cells from the taper start to beyond the reach, and is zero beyond it; D is below 0.002 on the lateral and top bounds. (As first written, "no step above 0.01 from the lee wall" fails for physical reasons: behind a 20 m cube at 2 m cells the centreline decays by 0.016 per cell near the lee wall, where σ grows fastest. The truncation is what the test is for.)
- shelter: the point evaluation of G equals the accumulated field value at the same face, for every building of a ten-building fixture;
- with `rooftop=2` and with `high_rise=1`, D is the same as with both off;
- geometry: an L-shaped footprint has D = 0 in its notch upstream of the lee wall; a courtyard has D = 0 from its own building; a raised building has its lower edge at max(base − δ, 0);
- codes 1 and 2: u₀, v₀, w₀ and `icellflag` bit-identical to the current build on the existing fixtures (`building_fixtures.h`) after W1a, and with strict footprints after W1b;
- thread count 1 against 8: identical fields.

Native, for the `canyon_factor` fix (extend `tests/native/check_contacts.cpp`):
- two equal slabs 15 m apart, wind across, street-canyon and sidewall models off: exposed faces and strict footprints give identical `icellflag`, u₀, v₀ and w₀ (before the fix they differ: 7,226 against 6,682 cavity cells);
- the same case: no far-wake flag behind the gap strips of the upstream slab;
- two slabs sharing a wall: fields identical before and after the fix;
- a 20 m slab before a 10 m slab: fields identical before and after the fix (the second-loop rule is untouched).
- The before/after items are checked with `tools/compare_native_builds.py --baseline <W1a>`, which gained a wake-geometry group (slab gap, shared wall, tall before short, courtyard, L-shape; exposed faces on and off) in W1a.

Python (`tests/test_wake_v3.py`, new; extend `test_parameterizations.py`, `test_feature_combinations.py`):
- flag range and wake dependencies accept 3; the bridge rejects 4;
- fields present for code 3 and absent otherwise; shapes match `velocity`;
- `scalar_speed` ≥ `speed` everywhere; equal to it where D = 0 and inflow k = 0;
- one isolated box: no step above 0.05 in K between adjacent cells outside the cavity at 2 m;
- direction sweep 225–315° in 1° steps: the far-wake probe has no jump above 0.02 (0.057 today);
- an L-shaped footprint and a courtyard run and give finite fields with D ≤ 1. (A raised building cannot be run from Python: the bridge rejects nonzero base heights on flat ground. It is covered by the native geometry test only.)
- wake=3 combined with terrain-free profiles, vertical grids and `Footprints(exposed_faces=True)`;
- the two-slab case with `street_canyon=0`: the gap velocity at 0.75 H is the same for `exposed_faces=True` and `False` (today +0.04 against −0.22 of U_ref).

Existing suites must pass with the default at 2 (W1–W5). Any stored fixture that changes at W1b is listed in the commit with the size of the change.

## 6. Validation and gates

**W1c equivalence with the prototype** (2 m, same constants, prototype fields from `QES_WAKE_DUMP`, both centred like the result fields):
- fields, on Cases A and B and four Case E directions: max |ΔD| ≤ 10⁻³ and max |Δk_w| ≤ 10⁻³ U_ref² over all faces. The two builds compute the same formulas, so only rounding should differ;
- scores, Cases A and B: |U|/U_H within 0.02 in q and 0.01 in R; reattachment within 0.05 b.

**W1d tolerances**, against the W1c build, for every optimisation:
- fields, same cases: max |ΔD| ≤ 0.005 and max |Δk_w| ≤ 0.005 U_ref²; the largest step between adjacent cells in D and in k_w must not grow;
- scores: every A, B, D and E score within 0.01.
- A change that meets the scores but not the field limits is rejected. A pooled score does not see a local defect.

**W1b check** (`canyon_factor` fix, `wake=2`, Case E at 2 m, 32 runs): no probe-direction changes by more than 0.1 in K, and no pooled score by more than 0.01. The prototype gave 0.09 and 0.002. Cases A and B have one building and must be bit-identical.

**W4 acceptance**, on the full harness with turbulence on, at the baseline resolutions. Values are the prototype's less 0.03:

| Case | Quantity | Gate |
|---|---|---|
| A | \|U\|/U_H, 2 m and 1 m grids | q ≥ 0.71 (2 m), 0.67 (1 m); R ≥ 0.90, 0.88 |
| B | \|U\|/U_H, 2 m and 1 m grids | q ≥ 0.64, 0.62; R ≥ 0.91, 0.90 |
| A, B | scalar speed at 2 m probes | q ≥ 0.83 and 0.86 |
| D | split fibre, mean vector | MAE ≤ 0.15 |
| D | thermistor, scalar | q ≥ 0.38, R ≥ 0.52 |
| E before, after | thermistor, scalar | q ≥ 0.27 and 0.43; R ≥ 0.52 both |
| E change | scalar | R ≥ 0.45 |

Also report, without a gate:
- sign agreement and top-10 overlap of the Case E change, beside `wake=2` with inflow k (the investigation found 0.69 / 0.52 against 0.73 / 0.59);
- Cases A and B with `rooftop=2` and with `high_rise=1`, beside `wake=2` with the same settings;
- QES-Turb k and K_scalar on the new field, since the smoother wake changes its gradients;
- the Case A and B grid study at 4 m and 0.5 m;
- iterative convergence: iterations to the probe tolerance against `wake=2`;
- wall time per Case E direction at 2 m: target +0.5 s after W1c (the prototype, with two field passes, takes +0.9 s). W1d applies only if this is missed.

**If a gate fails:** keep `wake=3` opt-in, record the result, and do not tune constants on D or E. The constants come from A and B only.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Refactoring `PolygonWake.cpp` changes codes 1 and 2 | The bit-identity check of section 5, run before any new behaviour is added. |
| Scores depend on the inflow k model, which the prototype took from the tunnel tables | Checked in section 3.4: the chosen rule moves no score by more than 0.02. W4 reports the validation with both the table and the rule. |
| The `canyon_factor` fix changes default results before the new wake is validated | Its own commit (W1b) with its own check (section 6); measured effect on Case E is at most 0.09 in K at single probes and 0.002 in scores. The policy is re-qualified once, in W6, for the whole batch. |
| An optimisation changes the field locally without moving a score | W1c reproduces the prototype first; W1d changes are held to field limits as well as score limits (section 6). |
| Solver convergence changes with the new initial field | Reported in W4; the fixed-work validation is unaffected, the adaptive policy is re-qualified in W6. W4: up to 50 more iterations to the probe tolerance (Case E N), well inside the fixed-work budget. |
| Level bias in districts (+0.30 in D, −0.32 in E before) | Known and reported; not gated. No coefficient is fitted to it. |
| Stored results and downstream readers see new fields | The fields are optional and absent for codes 0–2; `to_dtcc` adds them only when present. |
| The default switch moves every headline number | W6 is a separate, reviewable step with its own re-baseline. |

## 8. Done when

- `wind.run(..., parameterizations=Parameterizations(wake=3))` returns the deficit, the wake turbulence and a scalar speed;
- the tests of section 5 pass, and codes 1 and 2 are bit-identical to today apart from the `canyon_factor` fix;
- with exposed faces, the two-slab case equals strict footprints;
- `validation/WAKE_UPDATE_V2_RESULTS.md` states each gate with its measured value;
- the default is switched and the policy re-qualified, or the reason for not doing so is recorded.

## 9. Progress

Each step's outcome, in order. Commits are on `feat/wake-update-v2`.

- **W1a, done** (`1080d12`). `polygonWake` = `prepareWake` (preamble) + `applyWake` (cavity and far-wake loop). `tools/compare_native_builds.py --baseline main`: 493 cases on both backends, every field and diagnostic bitwise identical; only the native policy identity differs, as for any native edit. The tool gained a wake-geometry group (64 cases, exposed faces on and off) for the W1b and W1c checks. Native 61/61, Python 1948 passed, validation 150 passed.
- **W1b, done** (`571ba24`). Against W1a: only the exposed slab-gap and courtyard cases change; shared wall, tall before short, L-shape and all public cases are bitwise identical. Section 6 check (Case E at 2 m, 32 runs, `wake=2`, turbulence off): 1.60 % of probe-directions change by more than 0.01 in K, 0.23 % by more than 0.05, none by more than 0.1 (max 0.087); pooled K scores change by at most 0.001; Cases A and B bit-identical. Gate met. No stored test fixture changed. Two scope notes were added to section 3.5 (courtyards; the sidewall exposure rule).
- **W1c, done** (`c9d4d0b`). Kernel `winds/SpreadingWake`, `WINDSGeneralData::applySpreadingWake`, bridge fields. Codes 0–2 bitwise identical to W1b (509 cases, both backends). Native `check_wake` covers every native item of section 5; `check_openmp` runs code 3. Equivalence with the prototype rebuilt on `main` (A and B at 2 m, Case E SW, SSW, E and WSW before and after; turbulence off): max |ΔD| 7.5·10⁻⁸, max |Δk_w| 1.6·10⁻⁸ U_ref² (centring order only), every probe K identical, A and B |U|/U_H q, R and reattachment identical. Gate met. Cost: +0.60 s native initialization per Case E direction (8 threads; prototype on `main` +0.62 s), so W1d applied.
- **W2, done** (`7b43067`). Done before the W1c comparison, which needs it. `Parameterizations(wake=3)`; `WindResult.wake`, `scalar_speed(inflow_tke=None)`, the sampled fields, `to_dtcc`, `metadata["wake"]`, `profiles.friction_velocity`. Tests in `tests/test_wake_v3.py`: the wake edge 41 and 61 m behind a 20 m building has its largest step 0.041 and 0.025 (code 2: 0.197, 0.164); the 225–315° sweep's largest 1° jump at the far-wake probe is 0.016 (code 2: 0.057), as in the investigation. The sweep gives the same numbers at 400 iterations as at 3000, so the test uses 400 (12 s).
- **W1d, done** (`396f152`). Profile: the field pass took 0.57 of 0.60 s. Two changes: the ground-image terms of F_z cancel for buildings on the ground (2 erf instead of 4), and each column stops at z_c + 6σ(x). Cost +0.23 s per Case E direction (target +0.5 s). Against W1c: max |ΔD| 5.6·10⁻¹⁰, max |Δk_w| 6.0·10⁻¹¹ U_ref², largest adjacent steps unchanged, every A, B, D and E score and probe K identical (37 runs). Gate met.
- **W3, done** (`83dfd27`). Campaigns `wake3` and `ab_wake3`; probe sampling of D and k_w; `K_scalar_wake` (tunnel inflow k) and `K_scalar_wake_rule` (5.5 u*²) in the run records; `compare.ab_scalar`; `validation/run_wake_validation.py` in place of the untracked `run_full_validation.py` (see W3 above).
- **W4, done.** Every gate of section 6 passes, 0.02–0.04 above its threshold, and every gated score improves on `wake=2`. The 5.5 u*² rule scores within 0.02 of the tunnel table. Case E change: R 0.48, sign agreement 0.69, top-10 overlap 0.53 (`wake=2` with inflow k: 0.44, 0.73, 0.59). Cost +0.19 s native initialization per Case E direction. Iterations to the probe tolerance: equal, or up to 50 more. QES-Turb's own k does not improve on the new field. Full record: `validation/WAKE_UPDATE_V2_RESULTS.md`.
- **W5, done** (`2387533`). `comfort.assess_results(..., speed="scalar")`, default unchanged; not combined with GEM.
- **W6, not switched; reason recorded.** The gates allow the switch, but its re-qualification step cannot qualify it (W6 above; `validation/WAKE_UPDATE_V2_RESULTS.md`, last section). `wake=3` stays opt-in with its documentation (`docs/spreading-wake.md`, README, `docs/wind-comfort.md`, `QES_TURBULENCE.md`; PROVENANCE since W1c). Open decision for the maintainers: run a policy qualification study on `wake=3` fields, then switch. The branch's native identity (default `wake=2`) is re-qualified by the procedure of `docs/solver-control-requalification.md` and promoted in `pedestrian_qualification.h` (`6e072763…`): the only differences from `main` are the declared W1b cases, the 24 S7 workers and the combined baseline match exactly, `pytest -W error` passes on both packages (evidence in `docs/data/wake-update-v2/`, summary at the end of the results file).
- **W7, partly done.** `build/fabel-wake` in the main checkout is kept for now at the maintainer's request (2026-11-12); `experiments/fabel_wake/` stays as the record of the prototype. The comparison builds of this branch live under the worktree's `build/` and are not committed.
- **Follow-up.** The windy-point analysis (results, "The windiest points") shows `wake=3` with the scalar speed is more optimistic than today's default where comfort and safety classes are decided (Case E after). What a comfort-default switch requires is planned in [`WAKE3_COMFORT_DEFAULT_PLAN.md`](WAKE3_COMFORT_DEFAULT_PLAN.md).

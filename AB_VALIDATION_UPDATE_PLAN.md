# Improving dtcc-qes after the AIJ Case A and B validation: findings and plan

**Status (2026-11-05): plan, not started.** This builds on `validation/AIJ_AB_VALIDATION.md` (the A/B setup and results) and `validation/DTCC_REQUESTS.md` (R18, R19). It follows the governing `docs/WIND_SIMULATION_IMPROVEMENT_PLAN.md` and the experiment reports in `experiments/`. An independent review of the draft has been folded in: the corrections are marked "(review)".

## Context

Cases A and B are two isolated buildings in a boundary layer: A is a 16 × 16 × 32 m tower, and B a slab 8 m deep, 32 m wide and 32 m tall. The tunnel data are split-fibre mean vectors and k, so the comparison is like for like.

Baseline results at 1 m:

| Case | q on \|U\|/U_H | R | No-building q |
|---|---|---|---|
| A | 0.66 | 0.86 | 0.55 |
| B | 0.51 | 0.73 | 0.39 |

- **Right:** the flow topology. The sign of U agrees at 97 %.
- **Wake length:** B 8.3 b against 7.6 b measured; A 1.9 b against 1.4 b.
- **Wrong:**
  - the roof flow;
  - the shear layer above the wake;
  - the cavity strength;
  - the wake width;
  - QES-Turb's k (no skill, at its cap, non-realisable).

This file locates the errors, traces them to the code, and ranks the changes to dtcc-qes that should fix them, each with a gate against overfitting to two buildings. It ends with quick checks that need no repo edits. Everything under "Findings" was measured read-only on stored records during planning.

## Findings

### F1. Where the error is (1 m baseline)

- **All points, share of squared error:**
  - Case B: 57 % in the wake shear layer between H and 1.75 H (bias +0.39 U_H), and 19 % above the roof (+0.29).
  - Case A: wake below H 35 %, beside the building 29 %, above the roof 25 %.
- **Pedestrian level (z ≤ 2 m), which is what wind comfort depends on:**
  - **Overall:** A q 0.63 (no-building 0.51), R 0.84; B q 0.51 (0.40), R 0.77.
  - **Wake directly behind the building:** q 0.38 in both cases.
  - **Case A's 14 measured reverse-flow points** are reversed too strongly: U −0.26 against −0.12 U_H. Over the whole pedestrian wake behind the building, the U bias is only −0.01 (A) and +0.08 (B) (review).
  - **Case B wake (x > b/2) beyond the slab's width:** +0.12 U_H too fast.
  - **Windiest points:** underpredicted. A's 10 windiest measured points average 0.84 U_H, simulated 0.75 (maximum 0.96 against 0.85). B: 0.77 against 0.72.
  - **Beside the slab:** the speed is right (q 0.88). The direction is not (U +0.19 too high, median flow-angle error 15°), but that depends on the inferred sign of B's V (`compare.LATERAL_SIGN`).
- **Hit-rate headroom:** a perfect wake below H alone would lift q to 0.87 (A) and 0.79 (B).

### F2. The shear layer above the wake

The height (in H) where U/U_H first rises through 0.5, measured / dtcc-qes baseline / rooftop vortex (`rooftop=2`):

| Case | x/b | Measured | Baseline | Rooftop vortex |
|---|---|---|---|---|
| B | 1 | 1.17 | 1.00 | 1.09 |
| B | 2 | 1.18 | 0.99 | 1.09 |
| B | 4 | 1.20 | 0.95 | 1.05 |
| B | 6 | 1.19 | 0.90 | 0.99 |
| B | 8 | 1.14 | 0.83 | 0.91 |
| A | 2 | 0.88 | 0.89 | 0.93 |

- **Case A already matches** at every station.
- **In Case B** the separated roof shear layer forms the wake top, about 0.2 H above the roof. The 0.75 U_H crossing is measured at 1.21–1.31 H and simulated at ≤ 1.00 H.
- **Wilson (1979)** fits B: R = B_s^(2/3)·B_l^(1/3) = 32 m, H_c = 0.22 R gives a wake top of 1.22 H, and L_c = 0.9 R = 29 m exceeds the 8 m roof.
- **It does not fit A as a trigger (review):** Wilson's L_c is 18 m, against a measured roof reattachment X_R = 0.52 b = 8 m.
- **The simulated layer is a step (review):** the 0.25 to 0.75 crossings are about 0.01 H apart, against 0.07–0.11 H measured.
- **The existing vortex coupling (review):**
  - It closes only half of B's gap.
  - It lifts A slightly the wrong way.
  - It lengthens both wakes (A 1.91 → 2.00 b, B 8.32 → 8.41 b), because the raised wake height feeds Fackrell's L_R.

### F3. Roof flow

- **2 m above Case A's roof** (measured / baseline / rooftop vortex):
  - measured 0.95 / 0.37 / 0.28 / 0.61 U_H;
  - baseline 1.27 / 1.22 / 1.13 / 1.12;
  - vortex 0.76 / 0.17 / −0.06 / 0.46.
- The vortex turns A from about 0.3 too fast to 0.2–0.34 too slow (review); Case B improves similarly.
- **On D/E** the switch changes every score by 0.002 or less (`validation/output/report/sensitivity.json`, screen `rooftop=2`). That means it is mostly inactive there (district buildings with upwind neighbours do not qualify, and the probes are at 2 m). It is not a transfer test (review).

### F4. Zones or projection: stage attribution

The source is the other session's stored stage samples, `experiments/e2_composition/output/SE1-ab-reference-v1/{A,B}-legacy/probe-stages.npz` (2 m, legacy). Stage 0 has V = W = 0, and the final stage reproduces our stored 2 m K exactly.

| Region | Quantity | Inflow | Zones applied (u0) | After projection |
|---|---|---|---|---|
| B wake shear layer | K bias | +0.36 | +0.32 | +0.38 |
| Over the roof, A | K bias | +0.05 | +0.04 | +0.15 |
| Over the roof, B | K bias | +0.14 | +0.13 | +0.29 |
| B wake beyond its width (2 m) | K bias | +0.09 | +0.07 | +0.11 |
| Pedestrian wake behind, A | U bias | +0.56 | −0.13 | −0.01 |
| Pedestrian wake behind, B | U bias | +0.67 | −0.09 | +0.08 |
| Beside, A (2 m) | K bias | −0.06 | −0.13 | 0.00 |
| Upwind, A / B | K bias | +0.21 / +0.20 | +0.10 / +0.06 | +0.01 / +0.02 |

- **The zones' coverage is wrong:** the wake top (B) and the wake width (B).
- **The projection doubles the roof overspeed:** with no separation, the blocked flow is routed over the roof.
- **The projection already produces about the right side speed-up at 2 m,** and fixes the upwind region.
- **Cross-check:** that audit's 2 m K MAE (0.113 / 0.181) is identical to our 2 m runs.

### F5. Causes in the code

- **Rooftop code 1 (`src/qes_core/winds/Rooftop.cpp`), the default, is inert by construction:**
  - it is anchored to the undisturbed inflow at the shell top;
  - its z0 is the 1 mm wall roughness (`WINDSGeneralData.cpp:115`);
  - it changes the first cells by a few per cent, which the projection erases.
- **Rooftop code 2 (vortex)** applies to isolated rectangular buildings (`PolygonWake.cpp:184-233`) and adds the shell height to the wake height, and with it to L_R. But:
  - it uses vd = 0.11 R there, against 0.22 R in `Rooftop.cpp`;
  - its `u0_roof` is stale where the shell is higher than z_ref_u.
- **The wake (`PolygonWake.cpp`):**
  - L_R = 1.8 H(W/H) / ((L/H)^0.3 (1 + 0.24 W/H)). Case B sits at the clamp L/H = 0.3.
  - The cavity reverse flow is −U_H at the wall, at every height, for every shape (`:509`).
  - The cavity has w = 0; the tunnel shows upward W in the wake.
  - The wake does not widen laterally beyond the footprint envelope.
- **High-rise model:** Case B gets wake_height = (1.41 L/H − 1.57 W/H + 0.93) H = −7 m, which deletes its wake. The formula is used outside its validity range (a wide slab).
- **Corners:** no module models corner acceleration or outward deflection. `Sidewall.cpp` only removes momentum near the wall.
- **QES-Turb (`TURBGeneralData.cpp`):**
  - **"height" mixing length:** Lm = 0.4 z, with no bounding by buildings. That is about 13 m above a 32 m roof. "wall_distance" exists and is exposed (`wind.Turbulence(mixing_length=...)`).
  - **Gradients:** taken from the final field, zone steps included.
  - **Cap and clipping:** k is capped at 20 u*², but ν_T is not, and each stress component is clipped at ±20 u*² on its own.
    - txx already clips at tke ≈ 10.6 u*², so ½ the trace at the cap is 25–30 u*²: 0.85–1.02 (A) and 0.76–0.91 (B) U_H².
    - The observed peaks of 0.8–1.0 sit there.
    - Clipping also makes tensors non-realisable (masked at 33 A and 22 B probes).
  - **The wall model** uses one-sided differences and no z0. So the D/E finding that k follows the ground roughness came through the profile's lower-tail shear, not a wall-model z0. R11 needs restating.
- **Variational weights:** the earlier remark that E0e used an inconsistent operator was wrong. E0e used its own operator, with the ratio applied consistently (`experiments/tools/projection.py`, `E0_REPORT.md`), so E0e's closure stands (review).

### F6. Already tried on D/E, so not to be repeated

- **Rejected or closed:**
  - canopy backgrounds (E1a/E1b);
  - non-unit variational weights (E0e);
  - the existing flags (E2);
  - composition rule SE1;
  - flag tuning (Phase 5: no transfer from E to D).
- **Momentum (E5a):** the Python MAC prototype (`experiments/tools/mac_momentum.py`, `mac_pressure.py`; ν_T = l²|S|) has used 5 of its 6 allowed attempts under a frozen protocol. It never ran a city, because every city exceeds its 3 M-cell cap.
- **References:** the governing plan blocks physical selection until independent references exist. A and B now provide them, and the SE1 audit already uses them.

## Recommendations (in order)

1. **One wake/cavity candidate** (native, `PolygonWake.cpp` and `Rooftop.cpp`; this is the governing plan's "one wake/cavity candidate"). It merges the roof and wake-top fixes and has three parts:
   - a. **A roof-separation wake top, decoupled from L_R.** Keep L_R computed from H, so the wakes are not lengthened (F2). Raise the cavity and wake top by Wilson's H_c = 0.22 R, with the literature constants frozen and no fitted trigger. Use the same shell constants in `Rooftop.cpp` and `PolygonWake.cpp`, and fix the stale `u0_roof`.
   - b. **A shear layer that grows above the wake top** with downstream distance, instead of the present step (F2).
   - c. **Cavity strength** targeted at the reverse-flow core (A's 14 points), not a uniform weakening. The pedestrian-wake bias after projection is already small in A (F1).
   - **Wake widening:** test it only after separating upwind horseshoe points from wake points. It risks more of the E2 spurious decreases.
2. **QES-Turb (R19), in parallel.** It does not change the mean wind.
   - Use "wall_distance".
   - Cap ν_T consistently with the k cap, instead of clipping components.
   - Enforce realisability by eigenvalue clipping.
   - Restate R11 (F5).
   - Not "pre-zone gradients", which would remove all building shear (review).
3. **Momentum as a new, separately declared experiment, not an E5a addition (review).** Run the MAC prototype on A and B from the QES and plain starts, scored with the A/B harness.
   - Expect about 1.5 h per history.
   - At 2 m B's roof is only 4 cells deep, so roof separation is under-resolved. 1 m (7.1–7.5 M cells) exceeds the 3 M cap.
   - Its l²|S| closure must beat the diagnostic model. Steady k-ε already gets A's wake at 1.66–2.70 b, against dtcc-qes's 1.91.
4. **A corner-stream zone, last.** The projection already gives the right side speed at 2 m. Gate it on Case A only, since B's direction depends on the inferred V sign.
5. **The high-rise guard, at any time.** Keep the formulas from producing a negative wake height, or restrict them to their valid W/H range.
6. **Do not tune flags.** Single changes reach only ±0.04 on A/B and do not transfer.

Native changes (1, 2, 4, 5) change the solver policy identity. Batch them under one re-qualification (`docs/solver-control-requalification.md`).

## Gates against overfitting

- **Constants:**
  - Freeze literature constants (Wilson, Fackrell) before scoring.
  - Any fitted coefficient needs a leave-one-building-out test (fit on B, score on A, and the reverse) and a third isolated dataset (CEDVAL A1-1, Snyder & Lawson) before it can become a default.
- **A/B (1 m; A also confirmed at 0.5 m, because its wake drifts 3–4 % per grid halving):**
  - B's 0.5 and 0.75 crossings within 0.05 H at x = 1, 4 and 8 b, while A stays within ±0.05 H.
  - Wake length no worse than 3 %.
  - U sign agreement ≥ 0.97, and reverse-flow recall ≥ 0.95 (A) and ≥ 0.87 (B).
  - Bias reduced in the target strata, with no other region's MAE up by more than 5 %.
  - Pooled Δq below 0.03 counts as noise.
- **D/E (all 35 conditions at 2 m, rerun as fresh matched parents on the same native build):**
  - MAE/RMSE no more than +5 %, and R/ρ no worse than −0.03.
  - Change-sign recall no worse than −0.02, and the E2 89/31 spurious-decrease pairs not worse.
  - Report how many buildings each change actually modifies; zero means D/E did not test it.
- **Turbulence:** k skill on the A/B strata (R and FB), the D 0° split-fibre k, and the D/E √(\|U\|²+2k) against the thermistors. Case E has no measured k. "No masked probes" proves nothing once eigenvalue clipping is in.

## Quick checks (no repo edits; scratchpad scripts; about 10 minutes of compute)

Rules:
- Launch with `OMP_NUM_THREADS=7 .venv/bin/python -B`, not `uv run`. `uv.lock` and `pyproject.toml` have uncommitted changes, and a sync could rebuild dtcc-qes from other sessions' uncommitted native code. `-B` avoids writing `__pycache__` into `validation/aij`.
- Guard on `_qes.solver_policy_revision`: `2e80b9a7`, the build of the stored A/B runs. The stored D/E records are `b26d15fd`, so they are not valid parents; D/E parents are re-solved in the script.
- Modified runs get the baseline's run key (`RunSpec.turbulence` is a bool). Never call `runner.write`, and never use `load_records` on `validation/output/runs` for them; keep them in memory and in scratch JSON.

Scripts:
1. **`qc_stored.py` (no solves).** From the stored records (baseline, rooftop2, wake1, upwind_cavity0):
   - the crossing heights and the 10–90 % shear-layer thickness at the A/B stations;
   - the wake length (`compare.ab_reattachment`);
   - the region bias table.
   This fixes the targets of candidate 1.
2. **`qc_turbulence.py` (solves).** It wraps `runner.inputs` to swap in `wind.Turbulence(mixing_length=...)`, and wraps `dtcc_qes.wind.run` to keep the result, so `runner.run(spec)` returns a full record without writing anything.
   - **Parity:** A and B at 1 m with unchanged settings must reproduce the stored records' probe K and k (max \|Δ\| reported).
   - **Comparison:** "height" against "wall_distance" for A/B at 1 m, and for D 0° and E-after N/E/S/W at 2 m. In D/E the domain top is below 3 H, so "wall_distance" applies everywhere there, unlike A/B.
   - **Report, per run:**
     - the cap value, `capped_cells / computed_cells`, `invalid_stress_cells` and u*/U_H (`metadata["turbulence"]["cap"]`, `["validity"]`, `["reference"]`);
     - two separate probe fractions, `result.turbulence.capped` and tke ≥ cap value;
     - the masked-k probe count;
     - k scores (q, FAC2, FB, R) overall and per region;
     - Lm at roof height;
     - D's 33-point k and the D/E √(\|U\|²+2k) scores;
     - max \|ΔK\| between the two mixing lengths, which must be 0.

## Verification

- Parity passes before any other number is reported.
- The probe K is identical between the two mixing-length settings.
- Every number traces to a stored validation record, the stored stage samples, or a scratch JSON.

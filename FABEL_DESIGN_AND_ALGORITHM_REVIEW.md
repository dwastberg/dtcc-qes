# dtcc-qes: design and algorithm review

**Date:** 2026-11-11. **Reviewed at:** branch `research/pedestrian-wind-campaign`, `54ccb39`, native build as installed in `.venv`.

**Method.** I read the model from the source up (solver, parameterizations, turbulence, Python pipeline), then ran six small experiments through the public API and the AIJ harness to test the ideas that looked most promising. Nothing in `src/` or `validation/` was changed. I read the existing plans only afterwards, to mark overlaps. Section 6 lists them.

**Experiment scripts and outputs** are in the session scratchpad, not in the repository:
`/private/tmp/claude-501/-Users-dagwastberg-repos-dtcc-dtcc-qes/afdc2770-391b-4b2f-927c-05e24ccb356d/scratchpad`
(`x1_*.py` to `x6_*.py`). Say if you want them moved into `experiments/`.

---

## 1. Summary

| # | Suggestion | Type | Evidence from this review | Expected gain | Effort |
|---|---|---|---|---|---|
| S1 | Cache the cleaned footprints across directions | Performance | Measured: 6.0 s of an 8.6 s Case E direction is Python footprint cleaning, which does not depend on direction | ~3× on a multi-direction study at 2 m | Small, Python only |
| S2 | Stop the solve on a velocity-error estimate, with ω ≈ 1.9 | Performance | Prototype: 400 sweeps at ω = 1.9 reach the pedestrian-level error that ω = 1.78 needs 1,000 for; the validation runs use 2,000 | 2.5–5× fewer sweeps at 2 m | Small, native |
| S3 | Remove the hard direction thresholds in the building parameterizations | Accuracy (robustness) | Measured: K at a probe beside a building jumps by 0.11 when the wind turns from 279° to 280° | Removes sector-choice artefacts in comfort statistics | Medium, native |
| S4 | Give the far wake a continuous lateral edge | Accuracy | Measured: a 0.17 step in K between adjacent cells, 3 H behind an isolated building | Removes a grid-scale artefact; the likely source of spurious turbulence production | Medium, native |
| S5 | Average the initial field over a direction sector, then project once | Accuracy at low cost | Derived: the projection is linear. Measured: the parameterization pass costs 0.09 s against 1.7 s of sweeps | A 5-member direction ensemble for about +25 % solver time instead of +400 % | Medium, native |
| S6 | Report the ambient (inflow) k as the default turbulence estimate | Accuracy | Measured: inflow k beats QES-Turb on FAC2 and hit rate in Cases A, B and D | FAC2 for k from 0.10–0.24 to 0.28–0.70 | Small |
| S7 | Do not build an FFT-preconditioned solver; go straight to multigrid | Performance (negative result) | Prototype: iteration counts double with each refinement | Saves the detour | None |
| S8 | Treat grid-origin sensitivity as a reproducibility problem, not an accuracy problem | Prioritisation (negative result) | Measured: origin shifts explain 2–3 % of the squared error on Case E; an 8-member shift ensemble does not improve any score | Deprioritise cut cells and edge blending for accuracy | None |

**The main conclusion.** At 2 m, the solver is no longer the bottleneck and the numerics are not the accuracy limit. One direction of Case E spends 70 % of its time in geometry cleaning that could run once. The pooled accuracy scores do not move under any numerical perturbation I tried. The remaining accuracy is in the physics of the initial field (section 2.3), which the existing momentum plan already targets. S3 to S5 are the changes to the initial field that I can support with measurements.

---

## 2. How the model works

### 2.1 Pipeline

1. **Geometry** (`src/dtcc_qes/_city.py`, `_footprints.py`). LOD0 footprints with heights are cleaned by dtcc-core and passed as polygons.
2. **Grid** (`qes/Domain.cpp`, `vertical_grid.py`). Uniform dx = dy, explicit vertical faces. Buildings are stair-stepped: a cell is solid when its centre lies inside a footprint (`winds/PolyBuilding.cpp:187-203`).
3. **Inflow** (`winds/LogProfile.cpp`, `LayerProfile`). One horizontally uniform profile fills u0, v0; w0 = 0.
4. **Building parameterizations** (`winds/WINDSGeneralData.cpp:329-424`). Röckle-type zones overwrite u0, in a fixed order: upwind cavity, wake, street canyon, sidewall, rooftop. Buildings are processed from shortest to tallest.
5. **Projection** (`solver/solver.cpp`, `cpu_float32.cpp`). A Poisson equation for a Lagrange multiplier λ, solved by red-black SOR. The final field is u = u0 + ½∇λ.
6. **Turbulence** (`winds/TURBGeneralData.cpp`). A local mixing-length closure on the final field, with stresses clipped at a multiple of u*².
7. **Sampling and comfort** (`result.py`, `comfort.py`).

### 2.2 Structural properties that matter

- **The projection is linear in the initial field.** The operator depends only on the geometry and the grid. S5 uses this.
- **The projection only adds a gradient.** The vorticity of the final field equals the vorticity of the initial field. Every wake, vortex and shear layer in the output is one that a parameterization wrote. The solver cannot create or remove them.
- **A profile-only initial field gives potential flow around the buildings.** There is no downwash, because downwash needs the inflow shear to be tilted by the pressure field, and the model has no pressure.
- **Boundaries are open.** λ = 0 on the lateral and top boundaries, so displaced flux can leave. The ground and walls are free-slip.
- **Zone membership is decided by hard tests**, on angle (±10°, ±30°), on position (inside or outside an ellipsoid) and on precedence (the last writer wins). S3 and S4 follow from this.

### 2.3 Where the accuracy limit sits

The headline scores (Case E before: q 0.16, R 0.51; after: q 0.30, R 0.46) did not move in any of my numerical perturbations:

| Perturbation | Largest change in pooled R | Source |
|---|---|---|
| Grid origin shifted by 8 sub-cell offsets | 0.015 | X1, this review |
| Mean of the 8 shifted runs | +0.011 (before), +0.007 (after) | X1, this review |
| Solver converged far beyond the default | none (pedestrian error already below 10⁻⁵ U_ref at 2,000 sweeps) | X2, this review |

The error is in what the parameterizations write. Two code facts explain most of it, and both are known in the existing plans:
- A cell that no zone reaches keeps the approach profile. Nothing slows the air inside a built-up area.
- The upwind cavity multiplies the flow in front of a tall face by 0.4 over a region up to 0.6 H high (`winds/UpwindCavity.cpp:53-55, 206-213`). In front of a 60 m tower this is a slowdown where the wind tunnel measures a speed-up.

---

## 3. Experiments run for this review

All runs used the installed native build, float32, on the M4 Pro.

### X1. Grid-origin shifts on Case E (256 runs)

- **Setup.** Case E before and after, 16 directions, 2 m, the baseline fixed-work solver, no turbulence. The domain bounds were shifted by 8 offsets: (0,0), (1,0), (0,1), (1,1), (0.5,0.5), (1.5,0.5), (0.5,1.5), (1.5,1.5) m. Geometry and probes stayed fixed.
- **Individual probes move a lot.** The range of K over the 8 shifts has median 0.05 and 90th percentile 0.19–0.20. It exceeds 0.1 for 24–26 % of the probe values. The largest is 0.57.
- **The scores do not.** Across shifts, q varies by 0.013–0.016, R by 0.014–0.015 and the mean absolute error by 0.003.
- **Averaging does not help.** The 8-member mean changes R by +0.011 (before) and +0.007 (after), and the mean absolute error by −0.003.
- **Share of the error.** The shift variance is 2.3 % (before) and 2.9 % (after) of the mean squared error against the measurements.
- **The tower effect is insensitive.** The simulated mean ΔK is −0.014 to −0.016 at every shift, against +0.097 measured.

### X2. SOR against FFT-preconditioned CG (Python prototype)

- **Setup.** The Poisson problem of Case E "after" (WSW), rebuilt in NumPy from the run's solid mask and vertical faces, with the same boundary conditions as the native solver. The initial field is the inflow profile with zero on solid faces (no zones). Errors are the maximum horizontal velocity error in the 2 m layer, as a fraction of U_ref, against a solution converged to 10⁻¹¹.
- **Preconditioner.** The exact solve of the same operator without buildings: a sine transform in x and y and a tridiagonal solve in z. The hybrid adds one or two red-black Gauss-Seidel sweeps before and after.

Iterations (or sweeps) to reach a pedestrian-level error below 10⁻³ U_ref:

| Method | 4 m (0.25 M cells) | 2 m (1.8 M) | 1 m (15 M) |
|---|---|---|---|
| SOR, ω = 1.78 | – | 1,000 | – |
| SOR, ω = 1.90 | – | 400 | – |
| CG, Jacobi | – | 305 | – |
| CG, FFT | 19 | 29 | 99 |
| CG, FFT + 1 Gauss-Seidel sweep each side | 11 | 17 | 51 |
| CG, FFT + 2 sweeps each side | 8 | 14 | 30 |

- **The FFT preconditioner is not mesh-independent.** The count roughly doubles with each refinement, as SOR's does.
- **Cost estimate.** The transform pair cost 6–18 ns per cell in SciPy (float64, 4 workers). The native sweep costs 0.48 ns per cell (X6). One hybrid iteration is therefore about 15–25 sweep-equivalents. At 2 m, 14 iterations are 200–350 sweep-equivalents, against 400 for SOR at ω = 1.90. That is a gain of 1.1–2×. This is an estimate from a Python prototype, not a native measurement.
- **Limit.** The right-hand side has no parameterization zones. Zone edges add high-frequency content, which SOR removes quickly, so I expect the comparison to hold. I did not test it.

### X3. Continuity in wind direction (91 runs)

- **Setup.** One 20 × 30 × 20 m building, 2 m grid, wind from 225° to 315° in 1° steps, solver converged to 10⁻⁶. K sampled at five fixed points at 2 m and over the whole 2 m plane.
- **Result.** The field changes smoothly except at four directions:

| Step | RMS change of K over the plane | Multiple of the median step | Largest probe jump |
|---|---|---|---|
| 279° → 280° | 0.037 | 5.3× | 0.116 (side of the building) |
| 260° → 261° | 0.027 | 3.9× | 0.105 (side) |
| 269° → 270° | 0.026 | 3.6× | 0.018 (corner) |
| 270° → 271° | 0.018 | 2.5× | – |

- **Causes.**
  - ±10° from perpendicular: the upwind cavity switches on (`winds/UpwindCavity.cpp:53, 110`) and the sidewall zone switches on (`winds/Sidewall.cpp:57, 106`).
  - Exactly perpendicular: `perpendicular_flag` uses a tolerance of 0.01° (`winds/PolygonWake.cpp:77, 150`), so an axis-aligned building in a cardinal wind takes a different code path from the same building at 1° off.

### X4. The far-wake edge (from the X3 run at 270°)

- 61 m behind the lee face (3 H), K along a lateral line reads 0.60, 0.59, 0.58, 0.57, 0.56, **0.39**, 0.35, 0.31, … The step between adjacent 2 m cells is 0.17, or 30 % of the local value.
- 41 m behind, the step is 0.60 → 0.41.
- The step survives the projection. It comes from the far-wake formula, which ends where x = 3·d_n(y, z) (`winds/PolygonWake.cpp:79, 484, 494`). At that surface the deficit is still 18 % of the local speed, and outside it is zero. The wake has no lateral spreading.

### X5. A velocity-deficit proxy for k (negative)

- **Idea.** Replace the gradient-based closure by k = k_inflow + c·|u − u_background|², which has no zone-edge artefacts.
- **Result.** It does not track the measured pattern. Scores for k/U², with no absolute tolerance:

| Case (points) | Model | R | ρ | FAC2 | q |
|---|---|---|---|---|---|
| A (153–186) | QES-Turb | 0.17 | 0.19 | 0.24 | 0.07 |
| | Inflow k only | 0.11 | 0.05 | 0.50 | 0.38 |
| | Inflow k + 0.05·ΔU² | −0.03 | 0.11 | 0.59 | 0.36 |
| B (202–224) | QES-Turb | 0.13 | 0.09 | 0.10 | 0.02 |
| | Inflow k only | 0.25 | 0.16 | 0.28 | 0.11 |
| | Inflow k + 0.05·ΔU² | 0.03 | 0.09 | 0.46 | 0.18 |
| D, 0° (33) | QES-Turb | 0.09 | 0.35 | 0.15 | 0.03 |
| | Inflow k only | – | – | 0.70 | 0.30 |
| | Inflow k + 0.05·ΔU² | 0.19 | 0.04 | 0.52 | 0.15 |

- **Reading.** The proxy is rejected: its pattern correlation is no better than QES-Turb's. The useful by-product is the middle row of each block (S6). The coefficient 0.05 was not fitted, and 0.10 gives similar scores.

### X6. Where one direction spends its time

Case E "after", WSW, 2 m, 1.81 M cells, 2,000 sweeps, 4 threads, warm process, with turbulence:

| Phase | Seconds | Share |
|---|---|---|
| Python city preparation, almost all in dtcc-core `clean_footprints` | 6.00 | 70 % |
| SOR sweeps (0.87 ms each, 0.48 ns per cell) | 1.73 | 20 % |
| Turbulence and its extraction | 0.60 | 7 % |
| Parameterizations (the whole initial field) | 0.09 | 1 % |
| Native preparation (walls, coefficients) | 0.07 | 1 % |
| Everything else | 0.07 | 1 % |
| **Total `wind.run`** | **8.56** | |

Without turbulence the total is about 7.9 s (6.0 s preparation, 1.9 s native). The cleaning runs because the Case E specification passes `wind.Footprints(min_detail=0.1)`. A run without `footprints=` skips it.

---

## 4. Suggestions

### S1. Cache the cleaned footprints across directions

- **What.** `wind.run` repeats `prepare_footprint_domain` on every call (`src/dtcc_qes/wind.py:345`). The result depends on the city, the bounds, the resolution and the `Footprints` settings, not on the wind.
- **How.**
  - Expose the split that already exists internally (`_prepare_city` and `_solve_prepared`, `wind.py:150-158`) as a public prepared object, or memoise `_prepare_city` on a digest of its inputs.
  - Let `comfort` and the dataset interface loop over directions on one prepared object. The native `WindRunner` already supports repeated `solve` calls on one `prepare`.
- **Gain.** A 16-direction Case E study at 2 m drops from about 137 s to about 47 s. With S2 it drops to about 25 s.
- **Risk.** Low. The check is bit-identical output against separate calls.
- **Relation to existing plans.** This is F12 in `CLAUDE_WIND_EXPERIMENTS.md` and question P0 in `PERFORMANCE_REVIEW.md`. X6 answers P0: the unexplained 4 s is Python cleaning, not native preparation.

### S2. Stop on a velocity-error estimate, with ω ≈ 1.9

- **What.** The default stop rule compares the largest change of λ with an absolute tolerance. λ has units of m²/s, so the rule depends on the wind speed and the grid spacing. The validation avoids it by running a fixed 2,000 sweeps.
- **Evidence.** In X2 at 2 m, the pedestrian-level error falls below 10⁻³ U_ref after 400 sweeps at ω = 1.90, and below 10⁻⁴ after 550. The model error is 0.25 in the same unit.
- **How.**
  - Estimate the remaining velocity error from the last correction: the largest |Δλ|/dx per sweep, divided by (1 − ρ), where ρ is the observed ratio of successive corrections. Normalise by the reference speed.
  - Stop at 10⁻³ U_ref by default. Keep the fixed-work mode for validation.
  - Make ω = 1.90 the default for uniform 2 m grids. The adaptive policy already uses it (`dtcc/wind_runner.cpp:412`).
- **Gain.** 2.5× from ω alone and about 5× against the fixed 2,000 sweeps at 2 m.
- **Risk.** The profile-only test problem may flatter SOR. Check on the full Case E runs with the existing probe-history monitor before changing the default. Any native edit needs the policy re-qualification.
- **Relation to existing plans.** F02 covers ω. The dimensionless stop rule is the addition.

### S3. Remove the hard direction thresholds

- **What.** Three parameterizations switch on or off at a fixed incidence angle, and one takes a special path at exactly perpendicular flow (X3).
- **Why it matters.** A comfort study samples 12–36 directions. Buildings in a real city face every direction, so each sector lands some faces just inside or just outside ±10°. The result then depends on the sector centres, by up to 0.1 in K next to a building.
- **How.**
  - Replace each test by a weight that falls smoothly from 1 to 0 over a band, for example a cosine ramp from 10° to 20°, and blend the zone's velocity with the field it would have overwritten.
  - Remove the `perpendicular_flag` branch: the general formula with a guarded division gives the same limit.
  - Files: `winds/UpwindCavity.cpp:53,110`, `winds/Sidewall.cpp:57,106,123`, `winds/PolygonWake.cpp:77,150,189`, `winds/Rooftop.cpp` (±30°).
- **Test.** Rerun X3 and require that no 1° step exceeds twice the median step. Then rerun the AIJ baseline and require the pooled scores to stay within 0.03.
- **Risk.** The band width is a new constant. The AIJ directions are 22.5° apart, so they cannot calibrate it. Choose it by continuity alone and state that.
- **Relation to existing plans.** I found no mention of these thresholds in the repository documents. F04 (direction ensemble) would hide them at 5× the cost, and S5 would hide them at lower cost. This removes the cause.

### S4. Give the far wake a continuous edge

> **Superseded (2026-11-11) by `FABEL_WAKE_INVESTIGATION.md`.** Option 1 was tested and does not improve any score. Option 2 is replaced by a specific spreading wake with a wake turbulence term, tested on Cases A, B, D and E.

- **What.** The far-wake deficit ends in a step of 18 % of the local speed, and has no lateral or vertical spreading (X4).
- **How.** Two options, in order of effort:
  1. **Minimal.** Subtract the edge value so the deficit reaches zero at x = 3·d_n: use `(d − d_edge)/(1 − d_edge)` with `d = (d_n/(x + 0.1·d_n))^1.5` and `d_edge` its value at the edge. This keeps the zone shape and removes the step.
  2. **Better.** Replace the truncated ellipsoid by a self-similar profile: the same centreline decay, a Gaussian cross-section whose width grows with distance, and no cut-off. Wakes then overlap and accumulate through a district, which the current code prevents twice: by the cut-off, and by skipping the far wake whenever another building stands within the cavity length (`winds/PolygonWake.cpp:495, 555`).
- **Why it may help accuracy.** The level error in Case E "before" is an over-prediction inside low-rise fabric. Accumulating wakes act in the right direction. I have not tested how far they go.
- **Test.** Option 1: rerun X4 and the AIJ baseline. Option 2: Cases A and B first (wake recovery behind one building has measurements), then Case E "before" for the level bias (FB −0.43 today).
- **Relation to existing plans.** F09 blends all zone edges over a fixed half-width, and L3 in `UPDATES_FROM_LIT_STUDY.md` tests wake diffusion. This is a specific defect with a specific location, which neither names.

### S5. Average the initial field over a direction sector, then project once

- **What.** Because the projection is linear, the mean of N projected fields equals the projection of the mean of N initial fields. A direction ensemble needs N parameterization passes but only one solve.
- **Evidence.** The parameterization pass costs 0.09 s and the sweeps 1.73 s on Case E (X6). Five members cost about 0.45 s extra, or 25 %, instead of 400 %.
- **What it gives.**
  - The exact ensemble-mean velocity vector.
  - Smooth dependence on the nominal direction, whatever thresholds remain.
  - A model of the direction meander within a sector, which a wind-tunnel run lacks and the real atmosphere has.
- **What it does not give.** The ensemble mean of the scalar speed. Where the members point in different directions (wakes), the speed of the mean vector is lower than the mean speed. The per-member fields are not available either.
- **How.** In `WindRunner::solve` (`dtcc/wind_runner.cpp:292-318`), loop `applyWindProfile` and `applyParametrizations` over the member directions, accumulate weighted u0, v0, w0, then continue as today. The cell flags come from the central member.
- **Test.** Compare with the explicit 5-run ensemble at the Case D split-fibre points (vector means must agree to solver tolerance), then score both against the measurements.
- **Risk.** Whether the ensemble mean is more accurate at all is F04's open question. X1 showed that averaging over grid shifts does not help, so do not assume it. Run F04's explicit ensemble first. Build this only if F04 passes.

### S6. Report the ambient k by default

- **What.** In all three cases with measured k, the inflow k interpolated to the probe height beats QES-Turb on FAC2 and hit rate (X5). QES-Turb's pattern correlation is 0.09–0.17, so it adds no pattern in exchange.
- **How.**
  - Add a turbulence mode that returns the inflow turbulence (from a profile that carries k, or from a standard intensity profile for the terrain roughness) as the screening estimate, and make it the default for gust criteria.
  - Keep the mixing-length closure as an explicit option.
- **Gain.** FAC2 for k from 0.24 → 0.50 (A), 0.10 → 0.28 (B), 0.15 → 0.70 (D).
- **Risk.** Inflow k under-predicts in wakes and shear layers (FB +0.66 to +0.98), which is the unsafe direction for gusts. State it in the result metadata.
- **Relation to existing plans.** `compare.null_model` already computes this baseline for A and B. The suggestion is to ship it, not only to score against it. A transported k (F10) stays the route to a real pattern.

### S7. Do not build an FFT-preconditioned solver

- **What I expected.** Above the roofs the operator is separable, so an exact fast solve of the building-free problem should precondition the real one well, with no grid hierarchy to build and a direct mapping to GPU FFT libraries.
- **What X2 shows.** It works at 2 m (14–29 iterations) but the count doubles with each refinement, and the estimated native gain over SOR at ω = 1.90 is 1.1–2× at 2 m.
- **Recommendation.** Skip it. Multigrid (A1/F06 in the existing plans) keeps a flat count and is the right investment for 1 m and 0.5 m. At 2 m, S1 and S2 are worth more than any solver change.
- **One reusable piece.** The symmetric red-black Gauss-Seidel smoother around a coarse correction halved the iteration count in every case. The same smoother serves multigrid.

### S8. Grid-origin sensitivity is a reproducibility problem

- **What X1 shows.** A quarter of the probe values move by more than 0.1 in K when the grid origin moves by less than one cell. The pooled scores, the per-direction correlations and the tower effect do not move, and averaging over shifts does not improve them.
- **Consequences.**
  - Cut cells, anti-aliased zones and edge blending will not raise the AIJ scores at 2 m. The optimistic bound that L6 asks for is about 3 % of the squared error.
  - They still matter for users: a single receptor near a façade is not reproducible to better than about ±0.1 in K at the 90th percentile. That is a comfort class.
- **Recommendation.**
  - Report the shift range per receptor as an uncertainty, instead of fixing it first. Four half-cell shifts cost four solves and one preparation with S1.
  - Schedule edge blending (F09) and cut cells after the physics work, not before.

---

## 5. Smaller findings from reading the code

- **Wake strength ignores shelter.** Every building's cavity and wake scale with the initial velocity at its own roof height above its centroid (`winds/PolygonWake.cpp:100-106`). Deep inside a district this is still the undisturbed profile, so a sheltered building casts a full-strength wake.
- **The reference velocity can come from another building's zone.** All upwind cavities are written before any wake. A low building in front of a tall one reads a roof-level velocity that the tall building's cavity has already scaled or reversed, and aligns its own wake with it. The result depends on the processing order.
- **The centroid is the vertex average** (`winds/PolyBuilding.cpp:88-94`). For L-shaped or courtyard footprints it can lie outside the building or over a neighbour.
- **Solid cells are swept.** Fully solid cells get unit coefficients back (`winds/Wall.cpp:139-161`) and are relaxed like fluid cells. Their values are never used. The solid fraction is 3 % in Case E, so the cost is small there, but it grows with density.
- **Turbulence saturates.** k is clipped at `turbUpperBound·u*²` with one u* for the whole domain (`winds/TURBGeneralData.cpp:448, 477`). Where the clip is active the field has no pattern, which fits the correlations in X5.

---

## 6. Relation to the existing plans

| This review | Existing item | Status after this review |
|---|---|---|
| S1 | F12, `PERFORMANCE_REVIEW.md` P0 | P0 answered by measurement; F12 confirmed as the largest single gain at 2 m |
| S2 | F02 | ω confirmed on a prototype; a dimensionless stop rule added |
| S3 | none found | New |
| S4 | F09, L3 | New specific defect; narrower than both |
| S5 | F04 | New implementation route, gated on F04's result |
| S6 | `compare.null_model` | New as a product default |
| S7 | A1/F06 | An alternative tested and rejected; multigrid stands |
| S8 | F09 (H9d), L6 | Measured; both can be deprioritised for accuracy |
| X5 proxy | – | Tested and rejected |

I did not find a kinematic change that would produce the tower speed-up or the in-canopy slowdown. Both need momentum, or an empirical zone that stands in for it. On that point my independent reading agrees with `AIJ_VALIDATION_REVIEW.md` and `MOMENTUM_PLAN.md`.

---

## 7. Suggested order

1. **S1** (cache the preparation). Python only, no re-qualification, largest measured gain.
2. **S6** (ambient k default). Small, and it removes a result that is worse than its own null model.
3. **S2, S3 and S4 option 1 in one native batch**, so the policy identity is re-qualified once. Gate each on its test above.
4. **F04's explicit ensemble**, then **S5** if it passes.
5. **S4 option 2** together with the canopy and tower work in the momentum plan, since all three change the level inside a district.

## 8. Limits of this review

- X2 is a NumPy prototype on a profile-only right-hand side. Its native costs are estimates.
- X3 and X4 use one isolated rectangular building. The thresholds are in the code for every building, but I did not measure their effect on a district.
- X5 scores k at single wind directions in three cases. Case D has 33 points.
- All timings are from one machine and one case, with other jobs idle during X6 but not during X2.
- I did not run the unit tests or the full validation, because nothing in the repository was changed.

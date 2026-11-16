# dtcc-qes: end-to-end review

**Date:** 2026-11-14. **Reviewed at:** `main` `134396b` (0.1.0b4), built fresh from source into a scratch wheel. Nothing in `src/`, `tests/`, `tools/` or `validation/` was changed.

**Method.**
- Four independent code reviews, each reading its area in full: the Python package, the solver and bridge, the building parameterizations, and the turbulence model. Each confirmed its main claims by running the current build.
- I re-read the code behind the three bugs ranked highest below (B1, B2, B4) and confirmed them.
- I ran three experiments of my own on AIJ Cases D and E (70 runs at 2 m) for the accuracy section, and timed Case E at 2 m and 1 m.

**Scripts** are in `experiments/e2e_review/` (untracked, like the rest of `experiments/`): `t1.py`, `t2.py` (timing), `x1_*.py` to `x3.py` (accuracy), and `py/`, `native/`, `winds/`, `turb/` (bug reproductions). `runcur.py` runs a script against a wheel unpacked at `$DTCC_QES_PKG` instead of the editable install.

**Machine:** Apple M4 Pro, 4 OpenMP threads unless stated, AppleClang 17, float32.

---

## 1. Summary

**The code is in good shape numerically.** The discretisation, the red-black sweep, the stop rule, the bindings and the comfort statistics all checked out. No bug was found in the solver itself.

**The bugs are in the physics layer**, and five of them change pedestrian-level results by 0.1–0.5 in K in ordinary configurations:

| # | Bug | Effect | Reaches the default path? |
|---|---|---|---|
| B1 | With `Footprints()`, a tall building's far wake stops at the first low obstacle behind it | Speed 50 m behind a 60 m tower: 0.11 → 1.32 m/s (of 5) | Yes, `wake=2` with footprints, and the dataset interface |
| B2 | The upwind cavity uses a wrong angle for south-, south-west- and rotated east-facing façades | A building and its 180° mirror differ by up to 0.3 U_ref in front of the façade | Yes |
| B3 | A low building in front of a tall one reads a reversed reference wind | Its wake is written on its upwind side | Yes |
| B4 | The turbulence clip does not bound σ_u and depends on grid orientation | σ_u up to 3× the intended cap; σ_u 6.5 m/s where the speed is 1.1 m/s | Yes, whenever turbulence feeds comfort |
| B5 | The first cell above ground has σ_u 48 % low | Gust-equivalent mean never governs in open areas on a 2 m grid | Yes |

**Performance is no longer dominated by the solver.** A prepared direction of Case E at 2 m takes 0.42 s, of which the sweeps are 0.16 s. The largest remaining costs are footprint cleaning (3.8 s, once), turbulence (0.14 s per direction, serial), and Python metadata copying (0.07 s per direction).

**The accuracy experiments gave three results that I did not find in the existing documents:**
1. **The model's field has about three times too much contrast, in all three cases.** The best linear map from simulated to measured K has slope 0.28–0.39. Smoothing the simulated speed field with a 4–8 m Gaussian improves q, MAE and usually R in every case. The fine structure the parameterizations write is closer to noise than to signal.
2. **The error follows upwind blockage, in all three cases.** The residual (measured − simulated) correlates at R = 0.52–0.59 with a one-line geometric index of how blocked the probe is. Cavities and near wakes are too slow against scalar-speed measurements.
3. **The missed tower effect is local.** The measured speed-up is +0.32 within 15 m of the new tower and +0.23 at 15–30 m; beyond 30 m it is +0.02 to +0.05. The model gives 0.00 near the tower. That is a specific, bounded zone to model, not a district-wide momentum effect.

Section 5 turns these into proposals. The two I would do first are a **tall-building downwash zone** (A1) and a **mixing step** on the initial field (A2).

---

## 2. Environment finding

**The native extension installed in `.venv` is stale.** It was built on 12 Nov (dist-info 0.1.0b1) and lacks `SolverOptions.grid_relaxation`. Because the Python sources are an editable install of `main`, **every `wind.run` with the default `Solver()` fails in this checkout**:

```
AttributeError: 'dtcc_qes._qes.SolverOptions' object has no attribute 'grid_relaxation'
```

- **Fix now:** `uv sync --frozen --group dev --reinstall-package dtcc-qes`.
- **Fix for good:** compare a schema or revision constant between the Python package and `_qes` at import, and raise a message that names the rebuild command. An editable install with a compiled extension will drift again.

---

## 3. Bugs

Severity is my judgement of the effect on pedestrian-level results. "Upstream" means the same code is in QES-Public.

### 3.1 Building parameterizations

**B1. The far wake stops at the first low obstacle (high; confirmed by execution).**
- **Where:** `src/qes_core/winds/PolygonWake.cpp:490-495`. In the far-wake march, `if (solid) break;` runs before the upstream logic at lines 499–510.
- **What goes wrong:** upstream stops the wake only when the obstacle reaches 0.75 H of the source building. The new break ends it at any foreign solid cell, so the upstream test is unreachable.
- **When:** `wake=2` (the default) with `footprints=wind.Footprints(...)`, which is also what the dataset interface uses. `wake=3` is not affected.
- **Measured:** a 20 × 20 × 60 m tower with a 6 × 6 × 4 m kiosk 30 m behind it, wind 270°, speed at the first cell centre on the centreline:

| Distance behind the tower | No kiosk | Kiosk, `exposed_faces=False` | Kiosk, `exposed_faces=True` |
|---|---|---|---|
| 50 m | 0.20 | 0.11 | 1.32 |
| 80 m | 1.26 | 1.26 | 2.33 |
| 120 m | 1.88 | 1.88 | 2.47 |

- **Fix:** in the exposed branch, break only when the cell is also solid at level `kk` (or `canyon_factor < 1`); otherwise step over it.
- **Note:** the AIJ Case E runs use `exposed_faces=True`, so the validation scores include this behaviour.

**B2. Upwind cavity: wrong façade angle (high; confirmed by execution; upstream).**
- **Where:** `src/qes_core/winds/UpwindCavity.cpp:112-127`.
- **What goes wrong:**
  - `perpendicular_dir = atan2(…) + π/2` lies in (−π/2, 3π/2]. The wrap at line 114 tests `<= -M_PI`, which can never be true. It should test `> M_PI` and subtract 2π.
  - Normals in the third quadrant then take the `>= 0.75π` branch with the angle off by 90°. This includes every axis-aligned south face of a clockwise ring.
  - There is no final `else` for normals in [−π/4, π/4), so `effective_gamma` stays 0 for rotated east-facing faces.
- **Measured:** a building under wind d and under d + 180° must give point-mirrored fields. Largest difference at the first cell centre, U_ref = 5 m/s:

| Case | Default | `upwind_cavity=0` |
|---|---|---|
| 40 × 40 × 30 m rotated 70°, wind 200° | 1.52 m/s | 0.06 |
| Same, rotated 20°, wind 250° | 0.54 m/s | 0.06 |

- **Fix:** correct the wrap and add the missing branch. The mirror test above is a ready regression test.

**B3. The reference wind is read after other buildings' cavities were written (high; confirmed by execution; upstream).**
- **Where:** `PolygonWake.cpp:87-93`, and the same read in `Sidewall.cpp:84-89`, `Rooftop.cpp:105-110` and `StreetCanyon.cpp:99-104`.
- **What goes wrong:** every building takes its reference speed and direction from one face at its roof reference point. All upwind cavities are written first (`WINDSGeneralData.cpp:342-348`), up to 0.6 H of their own building, including the air above lower neighbours. A low building inside a tall building's upwind vortex reads a reversed wind.
- **Measured:** a 30 × 32 × 90 m tower with a 10 × 12 × 8 m building 6 m in front. The low building's cavity cells move from its lee side (70 cells) to its upwind side (114 cells), and the mean u in the strip upwind of it falls from +1.63 to −0.08 m/s.
- **When:** tower-plus-podium models split into parts, and any low building close to a tall face.
- **Fix:** take each building's reference from the approach profile, captured before any parameterization writes, and apply shelter explicitly, as `wake=3` already does.
- **Relation to earlier work:** the Fabel review noted that the reference "can come from another building's zone". This is the measured case, and it shows a sign reversal, not only a strength error.

**B6. The sidewall zone depends on the sign of the wind (medium; symptom confirmed by execution; upstream).**
- **Where:** `Sidewall.cpp:167-170, 201-202, 209-210` and the left-side twins.
- **What goes wrong:** cells are chosen with `ceil(x/dx) − 1` at points that lie exactly on grid lines, and the u-face is always the west face. The zone shifts by one cell with the wind sign.
- **Measured:** 40 × 40 × 30 m, wake and sidewall only: 270° against 90° differs by up to 0.20 m/s at the first cell centre, and 185° against 5° by 0.68 m/s.

**B7. `high_rise=1` removes the wake of slab and needle towers (medium; opt-in; confirmed by execution; upstream).**
- **Where:** `PolygonWake.cpp:146, 166, 272-274`.
- **What goes wrong:** the fitted wake height is negative for W/H ≳ 0.86, and a denominator crosses zero at W/H = 0.145.
- **Measured:** a 16 × 60 × 60 m slab goes from 72,602 wake cells to 0; an 8 × 8 × 80 m needle from 3,102 to 0.
- **Fix:** clamp W/H to the fitted range, or fall back to the standard branch outside it.

**B8. Courtyards shrink the effective width (medium; confirmed by reading).**
- **Where:** `PolygonWake.cpp:106-126`. The polygon area sums over all rings, so holes are subtracted.
- **Effect:** a 60 × 60 m block with a 40 × 40 m courtyard gets W_eff = 33 m instead of 60 m, and a cavity about 19 % shorter. The same width feeds the sidewall, the rooftop and the `wake=3` bubble.
- **Fix:** use the outer-ring area. Line 322 already restricts another quantity to the outer ring.

**B9. Façades split into short edges get short cavities (high for real GIS footprints; confirmed by execution).**
- **Where:** `UpwindCavity.cpp:130-131` computes the cavity length per polygon edge. Only exactly collinear vertices are merged, and only on the footprints path.
- **Measured:** a 60 m façade, 30 m tall, speed 30 m in front at the first cell centre:

| Footprint | Upwind cells | Speed (m/s) |
|---|---|---|
| Plain rectangle | 2,902 | 0.17 |
| A 0.1 m kink at mid-façade | 1,430 | 1.15 |

- **Why it matters:** digitised footprints almost always have near-collinear vertices. The same per-edge logic switches the sidewall off at a chamfered corner.
- **Fix:** merge consecutive edges whose normals agree within a few degrees into one façade run before computing lengths and eligibility.

**Lower severity (by reading unless stated):**
- **Sidewall strength is unsheltered** (`Sidewall.cpp:174-176`): it reads the approach profile from a solid cell's face. Measured: the sidewall beside a building in a far wake is as strong as beside an exposed one.
- **Upwind zones multiply** (`UpwindCavity.cpp:200, 240`): two overlapping zones give 0.4 × 0.4.
- **A cavity can be overwritten by the same building's far wake** on L- and U-shaped footprints (`PolygonWake.cpp:550-560, 694-700`).
- **Rooftop loop bounds** skip the east and north edge faces (`Rooftop.cpp:161-162`); the effect at pedestrian level is 0.003 m/s.

### 3.2 Turbulence

**B4. The stress clip does not bound σ_u (high; confirmed by execution).**
- **Where:** `src/qes_core/winds/TURBGeneralData.cpp:735-776`.
- **What goes wrong:** each of the six Cartesian components is clipped on its own. A fully clipped tensor is rank one with an eigenvalue of 3 × the bound, and it passes the validity mask.
- **Measured** (20 m cube, 2 m grid): σ_u² reaches 2.6–3.0 × the bound, in 956 cells. The worst cell has σ_u = 6.49 m/s at a speed of 1.14 m/s.
- **Also:**
  - The clip acts on Cartesian components, so a capped cell gives about 16 % more σ_u at 45° wind than at axis-aligned wind.
  - k is capped at 20 u*² before the anisotropy scaling, so the streamwise stress reaches the component cap at k ≈ 10.6 u*².
- **Fix:** limit once, isotropically: scale the whole tensor by min(1, k_cap/k). That is rotation invariant and keeps the tensor realizable.

**B5. The ground-adjacent gradient is wrong (high for comfort; confirmed by execution).**
- **Where:** `TURBWall.cpp:184-198` and the central stencil at `TURBGeneralData.cpp:390`.
- **Measured** in the undisturbed inflow: σ_u/u* is 1.30, 2.88, 2.59, 2.53 at 1, 3, 5, 7 m, against a target of 2.5.
- **Effect:** turbulence intensity is not monotonic in height. At 1.5 m the gust-equivalent mean is about 13 % low in open terrain, and it exceeds the mean speed on 20 % of the plane at 1.5 m against 88 % at 1.75 m.
- **Fix:** differentiate in log height for cells above a wall: dU/dz = (U_{k+1} − U_k) / (z_k ln(z_{k+1}/z_k)). It is exact for a log profile and needs no roughness.
- **Relation to earlier work:** `QES_TURBULENCE.md` hazard 9 notes the one-sided gradient. The second-cell overshoot and the comfort consequence are new.

**B10. Ambient turbulence exists only where the inflow has resolved shear (high for non-log profiles; confirmed by execution).**
- **Where:** `TURBGeneralData.cpp:428-460`: k = (L_m |S| / 0.55)², with L_m = κz unbounded.
- **Measured:**
  - `UniformProfile`: σ_u is 0.00–0.03 m/s in the free stream, so the gust-equivalent mean collapses to U/1.85.
  - `PowerLawProfile(α = 0.25)`: turbulence intensity is 0.25 at every height, so σ_u grows without bound aloft.
- **Fix:** an explicit ambient term from the profile, and a bounded mixing length (Blackadar form). See A4.

**B11. Invalid stress removes corner cells from the comfort map (medium; confirmed by execution).**
- **Where:** `_statistics.py:60-80` returns NaN σ_u for non-realizable tensors, and `comfort.py:236` marks the cell invalid.
- **Measured:** 2–4 % of fluid cells at 1.5 m, around edges and corners, where speeds are highest. A mean-only assessment classifies them; a gust assessment blanks them without a warning.
- **Fix:** B4's limiter removes most of them. Otherwise fall back to the mean there and count it.

**B12. Anisotropy axes follow the 15 m wind, not the local wind (medium; by reading).**
- **Where:** `TURBGeneralData.cpp:462-497, 554-621` against `_statistics.py:_streamwise_std`.
- **Effect:** where the pedestrian flow is turned by about 90° (channelling, corner streams), σ_u is about 20 % low.

### 3.3 Python package

**B13. `wake=3` with `MeasuredProfile(above="error")` fails after the solve (medium; confirmed by execution).**
- **Where:** `src/dtcc_qes/wind.py:485-494`. The friction-velocity fit runs to the top face, but validation only requires the table to cover the cell centres. The fallback changes only the bottom, so it raises the same error and the finished result is lost.
- **Fix:** fit up to the last cell centre.

**B14. The default domain is too small for the building, without a warning (medium; confirmed by execution).**
- **Where:** `wind.py:51`, `_city.py:217-221, 257`. Padding and clearance are 20 m whatever the building height.
- **Measured:** one 20 × 20 × 30 m building, K at 1.75 m:

| Probe | Default (20 m / 20 m) | Padding 150 m, clearance 90 m |
|---|---|---|
| Side | 0.699 | 0.807 |
| Near wake | 0.458 | 0.341 |
| Far side | 0.634 | 0.728 |

- **Fix:** scale the defaults with the tallest building (the AIJ guideline of 5 H to the sides and top is the usual reference), or warn when the wake zone is truncated by the boundary.

**B15. Comfort returns an all-invalid map on coarse grids, silently (medium-low; confirmed by execution).**
- **Where:** `comfort.py:310, 341-353`. When the criterion height is below the first cell centre (resolution above 3.5 m for NEN 8100), linear sampling has no support. Every cell gets class −1, with no warning, and the metadata reports the height as sampled.

**B16. Float32 rounding of the resolution can add a cell row (low; confirmed by execution).**
- **Where:** `_city.py:247, 312-315`. `resolution=1.8` on a 180 m extent gives 101 cells and moves a fixed 36 m top to 37.8 m.

### 3.4 Solver and bridge

No high-severity bug. Low-severity items, all by reading:
- **Stop-rule clip:** the convergence ratio is clipped at 0.99 (`solver.cpp:110-114`), so the estimate can be low once the true block contraction exceeds about 0.995. I estimate this needs 180 or more uniform layers. It is a documented risk in `SOLVER_STOP_RULE.md`.
- **Top band:** the top w-face of the last solved layer is never corrected (`solver.cpp:247`). Documented legacy behaviour.
- **Legacy tolerance includes solid cells** (`cpu_float32.cpp:157-159`). The velocity rule already skips them.
- **No default build type** (`CMakeLists.txt:111-113`): a plain `cmake` configure gives an unoptimised build that still defines `NDEBUG`.

### 3.5 Checked and found correct

- **Solver:** the stencil, right-hand side, velocity correction and divergence diagnostic use the same vertical scaling; the earlier 1/dz_k fix is consistent everywhere. Red-black colouring, reductions and boundary handling are right. Index arithmetic cannot overflow at 10⁸ cells.
- **Bindings:** every returned array is a copy; the GIL is released only around native work; no exception crosses a parallel region.
- **Conventions:** wind direction, axis order (z, y, x), half-cell offsets, and `to_dtcc` ordering, all by execution.
- **Comfort:** exceedance matches a brute-force computation exactly; thresholds, sector wrap, seasonal mapping and the gust formula are right.
- **Turbulence:** the derivative stencils (including non-uniform z), the frame rotation, the wall-distance mixing length and the sampling masks are right. Nothing is stale between directions.
- **Parameterizations:** ring orientation is enforced; the wake alone is exactly point-symmetric; swapping equal-height buildings changes nothing.

---

## 4. Performance

### 4.1 Where the time goes now

Case E "after", WSW, default `Solver()`, with turbulence, 4 threads:

| Phase | 2 m (1.8 M cells) | 1 m (13 M cells) |
|---|---|---|
| City preparation, once | 3.76 s | 3.69 s |
| Native preparation, once | 0.07 s | 0.52 s |
| **Per direction, prepared** | **0.42 s** | **4.2 s** |
| – initial field | 0.09 s | 0.55 s |
| – sweeps | 0.16 s (175 sweeps) | 2.32 s |
| – finalisation | 0.02 s | 0.15 s |
| – turbulence | 0.14 s | 1.17 s |
| – Python (metadata, statistics) | about 0.1 s | – |

A 16-direction study at 2 m is about 3.8 + 16 × 0.45 ≈ 11 s. More than a third of it is footprint cleaning.

### 4.2 Findings, in order of gain

**P1. Footprint cleaning is 3.8 s per city (dtcc-core).**
- 4.7 s under the profiler for 536 buildings: 2.7 s in `construct_coverage`, 1.8 s in `condition_walls`, 0.76 s in 38 Voronoi calls.
- One line stands out: `construction.py:124` calls `min(..., key=wkb)` 115,000 times, and a second profile on 1,600 buildings attributed 6.3 of 8 s to it. Caching the WKB key per geometry should remove most of that.
- This is a dtcc-core change; it belongs in `validation/DTCC_REQUESTS.md`.

**P2. Turbulence is serial and does dead work (0.14 s of 0.42 s at 2 m; 1.17 s of 4.2 s at 1 m).**
- No OpenMP pragma in any `TURB*` or `LocalMixing*` file.
- `divergenceStress` still runs although its output is never exported (`TURBGeneralData.cpp:303`).
- Four 3 × 3 matrix products per cell for a rotation about z, and six separate clip passes.
- **Expected gain:** 3–4× on this phase from threading and removing the dead work; all of it can be bit-exact.
- **`wall_distance` mixing length:** preparation takes 5.4 s on 3.9 M cells (`LocalMixingSerial.cpp:148-166`). An exact separable distance transform would take about 0.1 s.

**P3. The sweep kernel is about 27 % slower than it needs to be (measured at 22 M cells, 10 threads).**
- The compiler reloads seven member pointers per cell and tests the colour on every cell of a stride-1 loop (`cpu_float32.cpp:138-191`).

| Kernel variant | ms per sweep |
|---|---|
| As written | 6.85 |
| Pointers hoisted into locals | 5.60 |
| Hoisted, and stepping by 2 from the colour offset | 4.98 |

- Bit-identity of the variants was not checked; the expression order is unchanged.
- **This corrects a stored note:** float32 is now faster per sweep than float64 (6.9 against 10.4 ms).

**P4. Per-direction Python overhead: about 0.07 s of 0.42 s at 2 m.**
- `PreparedWindModel.run` deep-copies the domain and footprint metadata twice (`wind.py:320, 328`): 108,000 `deepcopy` calls per run on Case E.
- It grows with building count: 0.24 s of a 0.30 s run at 1,600 buildings.
- **Fix:** only the profile and the pedestrian-sampling entries change per condition; copy those.

**P5. Finalisation costs about 27 sweeps, the stop check about 2.3 sweeps (measured at 22 M cells).**
- Two finalisation passes are serial (`solver.cpp:254-269`, `mass_diagnostics.h:33-89`), and the per-face correction is a non-inlined cross-file call.
- Each stop check makes a serial 88 MB copy and a second pass in double (`solver.cpp:183-220`).
- Both matter little today (9–18 % of sweep time) and become dominant once multigrid cuts the sweep count.

**P6. Parameterization inner loops (0.09 s at 2 m, 0.55 s at 1 m).**
- `faceExposed` is a ray walk with a point-in-polygon test per step, and it runs before the cheap rejection tests, three times per cell (`UpwindCavity.cpp:178, 219, 260`).
- The cavity-fit search does not depend on the level but sits inside the level loop (`PolygonWake.cpp:451-477`).
- `cos` and `sin` of the wind direction are recomputed about 20 times per innermost iteration, because the compiler cannot prove the member is not aliased.

**P7. Comfort keeps every full result alive.**
- `comfort.assess_results` needs all directions' 3D results at once (`comfort.py:289-388`): about 5 GB for 16 directions at 20 M cells, 17 GB with turbulence. It should accept sampled planes.

### 4.3 What a better algorithm would buy

- **Multigrid** is still the right solver investment for 1 m and finer, where the sweeps are 55 % of a direction. A V(2,1) cycle with the existing smoother should need 20–25 sweep-equivalents against 175–475 (an estimate). At 2 m the sweeps are 0.16 s and it would not be noticed.
- **The operator is not symmetric as stored** (rows are divided by dz_k, and solid rows couple one way). A CG-based method needs the volume-scaled form with solid rows masked.
- **After multigrid, Amdahl moves to P2, P5 and the initial field.** Fix those first; they pay off either way.

### 4.4 Suggested order

1. P4 (Python only, no re-qualification).
2. P2 and P3 in one native batch with the bug fixes of section 3, so the policy identity is re-qualified once.
3. P1 as a dtcc-core request.
4. P5 with multigrid.

---

## 5. Accuracy

### 5.1 Three experiments

All runs: AIJ Cases D (3 directions) and E (16 directions × 2 states), 2 m, default settings and default `Solver()`. The baseline reproduces the published headline (q 0.16 / 0.30 / 0.23).

**X1. How the error is structured** (`x1_data.py`, `x1_an.py`).

| | E before | E after | D |
|---|---|---|---|
| Raw: q / R / MAE | 0.16 / 0.51 / 0.226 | 0.30 / 0.46 / 0.201 | 0.23 / 0.43 / 0.218 |
| Variance of K, simulated / measured | 0.048 / 0.014 | 0.061 / 0.038 | 0.040 / 0.033 |
| Best linear map, slope / intercept | 0.28 / 0.19 | 0.36 / 0.25 | 0.39 / 0.34 |
| After that map (in-sample): q / MAE | 0.55 / 0.084 | 0.47 / 0.133 | 0.49 / 0.131 |
| R of the residual with upwind blockage | +0.59 | +0.57 | +0.52 |

- **The slope is 0.28–0.39 in every case.** With R ≈ 0.45–0.5, the simulated field varies far more than its skill supports. Any deterministic use of the raw K overstates both the windy and the calm spots.
- **The in-sample linear map is the ceiling for any level correction:** q 0.47–0.55. Above that, the pattern must improve.
- **A map fitted on other cases transfers partly:**
  - Fitted on E (both states), applied to D: q 0.23 → 0.37, MAE 0.218 → 0.166.
  - Fitted on E before and D, applied to E after: q 0.30 → 0.45, MAE 0.201 → 0.142.
  - Fitted on D alone, applied to E before: no gain (q 0.18).
- **Geometric features add little to the map.** Plan-area density at 25, 50 and 100 m, mean and maximum height, wall distance and upwind blockage, added linearly, change the transferred scores by at most 0.05 in q. A linear residual correction on these features is not the route.
- **Upwind blockage** is the largest height/distance of a building on a 60 m upwind ray (`conventions.upwind_blockage`). Its correlation with the residual has the same sign and size in all three cases: the model is too slow where a building stands directly upwind.

**X2. Smoothing and a scalar floor** (`x2_data.py`, `x2_an.py`).

The 2 m speed field was smoothed with a Gaussian restricted to fluid cells, then sampled at the probes.

| Post-processing of the `wake=2` field | E before: q / R / MAE | E after | D |
|---|---|---|---|
| None | 0.16 / 0.51 / 0.226 | 0.31 / 0.45 / 0.198 | 0.23 / 0.43 / 0.218 |
| Smoothing, σ = 4 m | 0.25 / 0.55 / 0.184 | 0.41 / 0.53 / 0.155 | 0.28 / 0.43 / 0.193 |
| Smoothing, σ = 8 m | 0.29 / 0.51 / 0.166 | 0.47 / 0.55 / 0.133 | 0.34 / 0.42 / 0.180 |
| Smoothing, σ = 16 m | 0.33 / 0.37 / 0.151 | 0.50 / 0.54 / 0.124 | 0.37 / 0.34 / 0.173 |
| `wake=3` scalar speed, no smoothing | 0.31 / 0.55 / 0.151 | 0.46 / 0.55 / 0.135 | 0.41 / 0.55 / 0.150 |

- **Smoothing at 4–8 m improves every case on q and MAE, and R in Case E.** At 16 m, R falls: the real pattern starts to be removed. The model's skill sits at scales above roughly 8 m; below that it adds error.
- **`wake=3` with its scalar speed reaches the same level without smoothing**, and it is the only variant that raises R in Case D (0.43 → 0.55). This is an independent confirmation of that work. Smoothing on top of it does not help further.
- **A constant scalar floor, √(K² + c²), helps Case D and hurts Case E "before".** It is not a substitute for a turbulence estimate.
- **Smoothing the velocity vector instead of the speed is worse** in Case D (q 0.15 at σ = 8 m): it cancels opposed flows.
- **The blockage signal drops** from R ≈ 0.55 to 0.30 after 8 m smoothing with a 0.2 floor. About half of it is the over-deep, sharp-edged cavities.
- **Nothing here moves the tower effect.** The mean ΔK stays at −0.01 to −0.03 against +0.10 measured.

**X3. Where the tower effect is** (`x3.py`).

Case E, change in K from "before" to "after", by distance from the new 60 m tower:

| Distance from the tower | Probes | Measured ΔK | `wake=2` | `wake=3` scalar | Measured K, before → after |
|---|---|---|---|---|---|
| 0–15 m | 8 | +0.32 | 0.00 | +0.03 | 0.32 → 0.64 |
| 15–30 m | 14 | +0.23 | 0.00 | +0.02 | 0.34 → 0.56 |
| 30–60 m | 15 | +0.02 | −0.02 | 0.00 | 0.33 → 0.35 |
| 60–120 m | 23 | +0.05 | −0.02 | −0.01 | 0.32 → 0.36 |
| Beyond 120 m | 20 | +0.03 | −0.02 | −0.02 | 0.35 → 0.39 |

Within 60 m, by position relative to the wind:

| Position | Probe-directions | Measured ΔK | `wake=2` |
|---|---|---|---|
| Upwind of the tower | 133 | +0.08 | −0.06 |
| Beside it | 216 | +0.33 | +0.10 |
| Downwind of it | 133 | +0.21 | −0.11 |

- **The speed-up is confined to about half a tower height.** Within 30 m, the measured K roughly doubles to 0.56–0.64. That is close to the approach-flow K at 0.5–0.7 of the tower height, which is what downwash carries to the ground.
- **The model gets the sign wrong upwind and downwind.** It writes an upwind slowdown and a dead wake, where the tunnel shows faster, turbulent air at the ground on every side.
- **Beside the tower the model has a third of the effect** (+0.10 of +0.33), from the projection alone.
- **Beyond 30 m a small uniform rise remains** (+0.02 to +0.05). I cannot tell whether it is physical or a normalisation difference between the two tunnel runs.

### 5.2 Proposals

**A1. A tall-building downwash zone (new; targets the tower effect).**
- **Evidence:** X3. The deficit is local, large, and present on all sides.
- **What:** for a building much taller than its surroundings, write a ground-level zone within about 0.5 H of the façades whose speed comes from the approach profile at a stagnation-related height, not from the 2 m inflow.
  - **Eligibility:** H at least twice the mean height of the buildings within about 2 H. In Case E the tower is 60 m in a fabric of about 10–18 m.
  - **Front:** replace the 0.4 × slowdown below the stagnation height by a standing vortex whose speed scales with U(⅔ H). The upwind cavity already has the vortex shape; its reference speed and its reach are what change.
  - **Corners and sides:** a corner stream scaled by U(⅔ H), decaying over about 0.5 H.
  - **Near wake:** keep the reversed mean flow, and raise the scalar speed through the wake turbulence of `wake=3`.
- **Calibration without tuning to Case E:** Cases A and B are isolated buildings with split-fibre vectors at pedestrian height. Fit the two or three constants there, then test on Case E's ΔK and on Case D's tower, which stands in a regular array.
- **Acceptance:** mean ΔK within 30 m of the tower above +0.15 (measured +0.26), with Case D and "E before" scores not worse.
- **Relation to earlier work:** F08 in `CLAUDE_WIND_EXPERIMENTS.md` proposed a tall-building zone with literature constants. X3 supplies the missing target: its radius, its size and its presence on all sides.

**A2. A mixing step on the initial field (new; targets the excess contrast).**
- **Evidence:** X1 and X2. The field has about three times too much variance, and an 8 m smoothing raises q by 0.11–0.16 in all cases.
- **What:** before the projection, apply a few sweeps of masked diffusion to u0 and v0, with a length of about 4–8 m, or one that scales with the local building height. The projection then removes the divergence that the diffusion created.
- **Why before the projection, not after:** smoothing afterwards breaks mass conservation and cannot be used for the 3D field. Smoothing before keeps every guarantee the solver gives, costs a few sweep-equivalents, and also removes the direction jumps at hard zone edges that the Fabel review measured (S3, S4).
- **Why it is physical:** the parameterizations write time-mean zones with discontinuous edges. Real shear layers at these edges spread at roughly 0.1–0.2 of the downstream distance. The step stands in for the turbulent diffusion that the mass-consistent model lacks.
- **Test:** first reproduce X2 by diffusing the initial field in the Python prototype path (`experiments/tools`), since X2 smoothed the final speed and the two are not the same operation. Then gate on all three cases improving in q and MAE with R not lower.
- **Risk:** it blurs real sharp features, such as corner streams. X2 says the net effect is positive up to 8 m. Combine it with A1, which adds the one sharp feature that matters most.

**A3. Fix B1, B2, B3 and B9 and rerun the validation (bug fixes; unknown sign).**
- These four change K by 0.1–0.5 in configurations that occur in Case E: low buildings behind and in front of taller ones, façades facing every direction, digitised footprints.
- I did not measure their effect on the scores. Some of today's agreement may rest on them, so run the AIJ baseline per fix.
- B3 in particular bears on the tower effect: the 18 m buildings near the Case E tower may read a reference wind from inside its cavity. The E2 attribution work traced most of the spurious decreases to near-cavity writes of "the added tower and two 18 m buildings".

**A4. Ship a calibrated scalar speed as the comfort speed (builds on `wake=3`).**
- **Evidence:** X2. `wake=3` scalar speed is the best variant in all three cases, and the only one that helps Case D's pattern.
- **What remains** is the turbulence the scalar speed uses:
  - **Ambient term:** k_amb from the profile's own friction velocity. Use one constant: the wake path uses 5.5 u*² (`result.py:95`) and QES-Turb's ambient half-trace is 5.97 u*².
  - **Fix B4, B5 and B10 first**, so that QES-Turb's k is at least correct in the undisturbed inflow.
  - **Then test** k = k_amb (1 − D)² + k_w + k_shear, with the mixing-length term bounded.
- **Status:** `WAKE3_COMFORT_DEFAULT_PLAN.md` holds the default switch back on gate C4. X2 does not change that; it adds that the gain is robust across the three cases on the current build.

**A5. Report a shrunk estimate and an interval, not only the raw K (new; honest output).**
- **Evidence:** X1. The slope of 0.28–0.39 is regression to the mean: a predictor with R ≈ 0.5 and too much variance should be shrunk.
- **What:** next to the raw K, report K_cal = a + b·K with an interval, where a, b and the residual spread come from the pooled validation set and are versioned with the model identity.
- **What it buys:** MAE falls by a quarter to a third on a held-out case (X1), and comfort classes stop inheriting the model's excess contrast. A class boundary can then be reported as a probability.
- **What it does not buy:** pattern. R is unchanged, and the map compresses real extremes too.
- **Caution:** `AIJ_VALIDATION.md` finding 7 warns that tuning by compression made Case D worse. That was a physical tuning of the inflow on one case. This is a statistical statement fitted across cases, labelled as such, and it transferred to D here (q 0.23 → 0.37). With three cases the constants are weakly determined; it needs the further cases already planned.

**A6. A one-equation transport for k (medium effort; targets the turbulence pattern).**
- **Evidence:** the turbulence review measured σ_u = 0.20–0.23 m/s at 0.5–1.5 H behind a building against 0.79 m/s upstream. The algebraic closure has no memory, so wakes carry no turbulence; in the tunnel they carry the most.
- **What:** solve a steady advection–diffusion–production–dissipation equation for k on the final wind field. With an upwind scheme it is one linear system on the existing grid; the red-black kernel structure can be reused.
- **Why it is now affordable:** at 2 m a direction costs 0.42 s. A second solve of similar size keeps it under a second.
- **Relation to earlier work:** this is F10. The reason to raise it is that the solver cost that used to make it expensive has gone.

**A7. Use the scale split for a multi-fidelity model (longer term).**
- **Evidence:** X2 puts the model's skill at scales above about 8 m.
- **What:** let dtcc-qes supply the fine-scale geometry response, and learn only a smooth, coarse correction (level and large-scale deficits) from higher-fidelity runs, on an 8–16 m grid. A correction that is smooth by construction cannot overfit to probe-scale noise.
- **Relation to earlier work:** this narrows the "residual ML" step of `AIJ_VALIDATION_REVIEW.md` and gives the coarse momentum arm of `MOMENTUM_PLAN.md` a concrete target: the 8 m-filtered field, not the 2 m one.

### 5.3 What I would not pursue

- **Linear corrections on geometric features** (X1): no transferable gain.
- **A constant scalar floor** (X2): helps one case and hurts another.
- **Further grid or solver refinement for accuracy:** earlier work shows the scores do not move, and X2 shows why. The error is at scales well above the grid.

### 5.4 Suggested order

1. **Bug batch:** B1, B2, B3, B9 (parameterizations) and B4, B5 (turbulence), each scored on the AIJ baseline. One re-qualification.
2. **A2 prototype** in Python on the initial field. It is cheap and decides whether the native step is worth building.
3. **A1** calibrated on Cases A and B, tested on D and E.
4. **A4**, once B4, B5 and B10 are fixed.
5. **A5** when the planned further validation cases exist.
6. **A6**, then **A7**.

---

## 6. Limits of this review

- **B1–B3, B6, B7, B9 were measured on small synthetic layouts**, not on a district. Their effect on the AIJ scores is not known.
- **The kernel timings (P3, P5) are from a scratch harness** on one machine at 22 M cells and 10 threads. The variants were not checked for bit-identity.
- **X2 smooths the final speed field.** A2 proposes diffusing the initial vector field. The first is evidence for the second, not a test of it.
- **X1–X3 use three cases, all scalar-speed thermistor data** except where stated. The linear maps of A5 are fitted on 198 to 2,560 points.
- **X3 rests on 22 probes within 30 m of one tower.**
- **Not reviewed in depth:** `StreetCanyonModified.cpp` and the research canyon headers (not reachable from the public options), the dataset interface beyond its slice path, `tools/`, and the test suite. The test suite was not run, because the installed extension is stale and nothing was changed.
- **dtcc-core** was profiled, not reviewed.

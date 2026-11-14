# Plan: fix the six largest physics bugs

**Date:** 2026-11-14, revision 6 (implemented). Revision 2 closed decisions D1, D3 and D4. Revision 3 answered the external review of revision 2 (section 9) and re-checked the plan against the source. Revision 4 closes D6 (spectral scale) and D7 (no re-qualification in this release). Revision 5 is a final check of every file, line and formula against the source; section 10 lists what it corrected.
**Base:** `main` `033df33`. The two commits after `134396b` (0.1.0b4) touch only `.gitignore` and three test and tool files, so the native identity is unchanged.
**Source of the findings:** [END_TO_END_REVIEW.md](END_TO_END_REVIEW.md), section 3. All six fixes are implemented. [Execution results](validation/PHYSICS_BUG_FIX_RESULTS.md) record step-by-step reassessment, validation and release checks.

**Scope.** Six bugs, four in the building parameterizations and two in the turbulence model:

| Fix | Review id | Bug | File |
|---|---|---|---|
| F1 | B2 | Upwind cavity uses a wrong façade angle | `winds/UpwindCavity.cpp` |
| F2 | B1 | Far wake stops at the first low obstacle | `winds/PolygonWake.cpp` |
| F3 | B3 | Reference wind is read after other buildings' cavities | `winds/PolygonWake.cpp`, `UpwindCavity.cpp`, `Sidewall.cpp`, `Rooftop.cpp`, `StreetCanyon*.cpp` |
| F4 | B9 | A façade split into short edges gets short cavities | `winds/PolyBuilding.cpp` |
| F5 | B4 | The stress clip does not bound σ_u | `winds/TURBGeneralData.cpp/.h`, `dtcc/api/covariance_model.h` (new), `dtcc/turbulence.cpp`, `dtcc/api/wind_config.h`, `src/cpp/bindings.cpp`, `src/dtcc_qes/turbulence.py`, `tests/test_covariance_limiter_v2.py` |
| F6 | B5 | The ground-adjacent velocity gradient is wrong | `winds/TURBWallTerrain.cpp/.h` |

All paths below are under `src/qes_core/` unless they start with `src/`, `tests/`, `tools/`, `validation/`, `experiments/` or `docs/`.

**Not in scope:** the other review findings (B6–B8, B10–B16), the performance items and the accuracy proposals. Section 7 lists them; none of them joins this batch.

---

## 1. Findings that shape the plan

These come from reading the fix sites after the review, and were re-checked for revision 3.

1. **F1 and F3 are upstream bugs; F2 is ours.** The angle wrap and the reference read are in QES-Public unchanged. The far-wake break was added with the exposed-faces work. So F1 and F3 change the upstream-parity path (`footprints=None`) as well, and F2 does not.
2. **F3 also affects `wake=3`.** `applySpreadingWake` takes each building's roof wind from `prepareWake`, which reads the field after the upwind cavities (`WINDSGeneralData.cpp:438-469`). Its shelter model then scales a value that may already be reversed. Its final loop calls `prepareWake` again (`:467`), after earlier buildings' wake cavities are written, so the read there also depends on building order.
   - **Order.** Every stage loops over buildings in ascending effective height (`mergeSort`, `WINDSGeneralData.cpp:491`). So a building's wake reference is read before any taller building's wake is written. A lower building's wake stays below a taller building's roof point (`k_end`, the first cell above the roof, `PolyBuilding.cpp:226`). The contamination F3 removes therefore comes from the upwind cavities. No shelter mechanism of `wake=1` or `2` depends on it, and `wake=3` applies its shelter explicitly.
3. **The later stages use the reference only for its direction.** *(Corrected in revision 3.)* Every stage reads `u0_h, v0_h` at the roof point. Only the upwind cavity (`uh_rotation`, `UpwindCavity.cpp:128`), the wake cavity (`-u0_h`, `PolygonWake.cpp:560`) and the `wake=3` shelter (`WINDSGeneralData.cpp:468`) use its magnitude. The street canyon, sidewall and rooftop use only `upwind_dir = atan2(v0_h, u0_h)`, to orient their geometry. Their strength comes from local reads of the field beside the building (`Sidewall.cpp:175, 274`; `Rooftop.cpp:251, 408, 422`). Revision 2 described a "sheltered magnitude" for those stages; that magnitude does not exist. The shelter they see comes from the local reads, which no variant changes.
4. **A geometry simplification step already exists for F4.** `PolyBuilding::prepareParameterFaces` (`PolyBuilding.cpp:303-338`) removes exactly collinear vertices, keeps the original ring for the solid mask (`maskVertices`), and rebuilds the parameterization polygon. F4 is a tolerance on that step, not a new mechanism. Today it runs only with exposed or canonical faces.
5. **Two log profiles are in use.** The inflow is ln((z + z0)/z0) (`LogProfile.cpp:116`). The rooftop parameterization writes ln(d/z0), with d the height above the roof (`Rooftop.cpp:242, 265`). A log-space gradient is exact only for the profile it assumes.
6. **The ground and roofs share one function but not one wall object.** *(Corrected in revision 5.)* Two wall objects compute the wall derivatives (`TURBGeneralData.cpp:122-123`):
   - `TURBWallBuilding` holds the cells with a building cell (flag 0) below, which are the roofs;
   - `TURBWallTerrain` holds the cells with a terrain cell (flag 2) below. On main the only flag-2 cells are the ground ghost layer k = 0 (`WINDSGeneralData.cpp:107`), so its list holds exactly the ground cells.

   Each object has its own `wall_below_indices`. Both inherit the same `TURBWall::comp_velocity_deriv_finitediff_stairstep` (`TURBWall.cpp:177`). The terrain object runs second, so it overwrites the building object wherever their cells overlap. F6 overrides that function in `TURBWallTerrain` only, which restricts it to the ground by construction.
7. **The stress cap is a per-component variance bound.** `boundTurbFields` (`TURBGeneralData.cpp:735-777`) clips each component to ±B with B = `turbUpperBound` · u*² (`:737`), in six passes. So today each grid-axis variance is at most B. A spectral version of the same bound exists on `research/pedestrian-wind-campaign` (`24c04ef`), in `dtcc/api/covariance_model.h` (`spectral_limit`), and its contract is documented in `docs/BOUNDED_COVARIANCE.md` on that branch and on `research/unified-wind-turbulence`. The code is not on `research/unified-wind-turbulence`.
8. **The limiter tests on main fail.** Commit `033df33` added `tests/test_covariance_limiter_v2.py` and `tests/native/covariance_limiter_probe.cpp` to main. They include `dtcc/api/covariance_model.h`, which exists only on the research branch. On main the test file gives 1 failure and 2 errors. The header it needs, `dtcc/api/stress_validity.h`, is already on main and identical to the branch's. The third test also calls `uncapped_energy`, `production_scale` and `consistent_constitutive`, which belong to the production coupling that F5 does not port (step F5).
9. **The `capped` state is inferred, not recorded.** Export (`dtcc/turbulence.cpp:153-158`) and probe sampling (`dtcc/turbulence.cpp:56-57`) mark a cell capped when tke ≥ B or any |component| ≥ B. After F5 that inference is wrong.
10. **The S7 qualification workers are affected by F1 and F3.** The 24 frozen workers use rectangular boxes with winds from 150°, 195°, 210°, 225°, 240°, 270°, 300° and 315°, and buildings of mixed height (`tools/run_solver_policy_study.py:26-53`). Wind onto south-facing faces (F1) and lower buildings in front of taller ones (F3) both occur. The workers run without turbulence, so F5 and F6 do not reach them. F4 leaves boxes unchanged. So `tools/check_policy_compatibility.py`, which requires exact agreement, cannot pass after this batch. Under D7 the batch does not re-qualify.
11. **Every fix changes default results and the native identity.** The plan batches them into one release, with one commit per fix so that each can be scored and reverted alone.
12. **The `pedestrian-v1` policy is opt-in, and the code already handles an unqualified build.** Only `Solver(policy="pedestrian-v1")` uses the qualification; a plain `Solver()` does not. When the identity does not match, adaptive runs return `unqualified_build`. The tests (`test_adaptive_control.py`, `test_native_preflight.py`, `test_solver_spec.py`, `test_parameterizations.py`) and `tools/wheel_runtime_smoke.py` already accept either state.
13. **The installed extension in `.venv` is stale.** Nothing can be tested in this checkout until it is rebuilt (step P0).
14. **The Case A and B measurement files are untracked.** `validation/aij/__init__.py:14` reads `validation/AIJ_A/CaseA(1_1_2).xls` and the matching Case B file. Both folders are untracked in the main checkout, so a fresh worktree does not have them (step P0). Cases D and E are tracked.
15. **The wind direction can vary with height, and z0 has one source.**
    - Non-log profiles reach the native code as a layer table with one (u, v) per layer, and `MeasuredProfile` accepts a direction per height. So a "profile direction" exists only per height, and a layer can be calm while others are not. Every condition also carries a single direction, `site_wind_dir` (`dtcc/model_inputs.cpp:298`).
    - Every profile carries a `roughness_length`. It becomes `inflow.site_z0` (`dtcc/model_inputs.cpp:201`), the turbulence `site_z0` (`:211`) and `WGD->z0` (`WINDSGeneralData.cpp:92-100`), so the wind and turbulence code use one z0.
16. **The mixing length near the ground is κ·d, not κ·(d + z0).** The default height-based mixing length is the cell-centre height above the terrain (`LocalMixingDefault.cpp:53`), times κ (`TURBGeneralData.cpp:143`). With an exact log gradient u*/(κ(d + z0)), the local closure gives σ ∝ L·|dU/dz| = u*·d/(d + z0). That is 9 % low at d = 1 m and 17 % low at d = 0.5 m for z0 = 0.1 m. This factor and the gradient error together reproduce the measured first- and second-cell σ_u (step F6), and F6 does not remove the factor.

---

## 2. Decisions

Status after the user's review on 2026-11-14 and the external review of revision 2.

**D1. Old behaviour: decided — not preserved.**
- No runtime switches and no private flags. The fixes replace the defective code.
- The changelog describes each change and how it was checked. It does not need to offer a way back.

**D2. Direction used by the stages that run after the wake** (canyon, sidewall, rooftop): **decided — V1, by the F3 benchmark and its prescribed tie-break.**
- Because of finding 3, only the direction is in question. The upwind cavity and the wake use the frozen incident vector in every variant.
- **V1, profile direction.** The later stages use the direction of the approach profile at the roof point. Order-independent, and one frame per building.
- **V3, field direction at a stage boundary.** The later stages use the direction of the field at the roof point, captured once for all buildings after the last wake is written and before the first canyon, sidewall or rooftop write. So a building's frame cannot depend on what an earlier building's canyon, sidewall or rooftop wrote. Where that field speed is below 10 % of the profile speed, the direction is undefined and V3 uses the profile direction.
- **V2 is dropped.** It differed from V1 only in magnitude, which the later stages do not use (finding 3), so it would give the same field as V1.

**D3. F4 tolerance: decided — 0.5 × the horizontal cell size, as a modelling tolerance.**
- Revision 2 justified this by saying a smaller feature cannot change the solid mask. That is false: an arbitrarily small move of a boundary can cross a cell centre. The value is a modelling choice: a feature that deviates less than half a cell from a straight façade is treated as part of that façade for the parameterizations. The solid mask is not affected either way, since it keeps the original ring.
- With unequal spacing the tolerance is 0.5 × min(dx, dy).
- Step F4 still runs 0.25 and 1.0 × the cell size on Case E, as a recorded sensitivity. It does not reopen the choice unless the scores differ by more than 0.02 in q or R.

**D4. F4 on the strict path (`footprints=None`): decided — yes.**
- The defect is the same there, and the upstream-parity fixtures use plain rectangles, which the step leaves untouched.

**D5. Report F1 and F3 upstream to QES-Public: open.**
- My recommendation is yes, after F1 and F3 are verified here. It is outward-facing, so I draft the issue text and the user decides whether and where to post it.

**D6. Stress limiter contract: decided — spectral scale.**
- The limiter bounds the largest eigenvalue magnitude: every tensor with spectral radius above B is scaled as a whole by B/radius. Then the variance in every direction is at most B (20 u*² by default), and σ in every direction is at most √B = √`turbUpperBound` · u*.
- This is the rotation-invariant form of today's intent, which bounds each grid-axis variance by B. One factor scales the whole tensor, so its shape is kept: the anisotropy ratios and the correlation coefficients. The cost is that when one direction exceeds B, the other directions shrink with it.
- Rejected alternatives:
  - ½ trace ≤ B: it leaves a strongly directional tensor alone and limits a near-isotropic one that is not limited today, so it does not bound σ_u.
  - Clipping each eigenvalue separately: it changes the tensor's shape, needs a full eigendecomposition, and has no prior evidence here.
  - Keeping the component clip: it depends on the grid orientation.
- Realizability is a separate matter and stays out of scope. Scaling by a positive factor keeps the sign of every eigenvalue, so the limiter neither repairs nor creates an indefinite tensor.
- The energy cap on k before the anisotropy step stays where it is (step F5).
- Prior evidence: this is arm P0A0C1 of the research branch's eight-way limiter comparison (`validation/DIRECTED_IMPROVEMENT_RESULTS.md` on `research/unified-wind-turbulence`), measured on that branch, not on this base:
  - non-realizable tensors at the sample points fall by about 30 %;
  - pedestrian k RMSE averages −6.6 % over A, B and D;
  - a rough recomputation of R over all heights falls in Case A (0.25 → 0.21) and rises in Case B (0.10 → 0.12).
  The fall in Case A is expected to need an attribution note under section 5.

**D7. Re-qualification: decided — not in this release (option C).**
- The `pedestrian-v1` adaptive policy is opt-in and still under development and experiment; no active use depends on it.
- 0.1.0b5 ships with `dtcc/pedestrian_qualification.h` unchanged. The native identity changes, so `Solver(policy="pedestrian-v1")` returns `unqualified_build` in that release. Plain `Solver()` runs are not affected (finding 12).
- Re-qualification is deferred to a later release (section 7). The two options considered (a declared-change procedure, or a full rerun of the S7 study) are recorded there.

---

## 3. Preparation

**P0. Working tree and build.**
- Create a worktree and branch `fix/physics-bugs` from `main` (`033df33`). The main checkout has untracked files that have blocked checkouts before.
- Copy `validation/AIJ_A/` and `validation/AIJ_B/` from the main checkout into the worktree (finding 14). They stay untracked; committing third-party measurement files is not part of this plan.
- Build the extension there (`uv sync --frozen --group dev`), and confirm that `_qes.SolverOptions` has `grid_relaxation`.
- Configure the native test builds as in `docs/stage0-validation.md`: `cmake -S . -B build/extension -DPython_EXECUTABLE=.venv/bin/python -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_OPENMP=OFF -DCMAKE_BUILD_TYPE=Release`, the same with OpenMP in `build/openmp`, and `-DDTCC_QES_ENABLE_SANITIZERS=ON` in Debug in `build/sanitizers`. Run them with `ctest --test-dir <dir> --output-on-failure`.
- Rebuild the main checkout's `.venv` too, so that it stops failing on the default `Solver()`.

**P1. Baseline.**
- Run the unit suites (`pytest`, CTest) and record the counts. `tests/test_covariance_limiter_v2.py` fails on main (finding 8); record it as a known failure, which F5 removes.
- Run `uv run --group validate python validation/run_full_validation.py --fast` and the same without `--fast` (Cases A, B, D and E at 2 m and 1 m, every direction). Run records are keyed by code fingerprint, so every fix reruns what it changes and nothing is reused across fixes by mistake. The fast run is the reference for the per-fix tables; the full run is the reference for the release (section 5).
- Archive both (P3).
- Copy the reproduction scripts from `experiments/e2e_review/winds/` and `turb/` next to the new tests as their starting point.

**P2. Shared symmetry helper.**
- Add a point-mirror check in `tests/native/check_symmetry.cpp`. It takes any layout and wind direction d, and builds a second case with the geometry rotated 180° about the domain centre and wind d + 180°.
- Comparison: the second field is rotated back, with both horizontal velocity components negated. Here nx and ny count faces, so there are nx − 1 by ny − 1 cells. Staggered faces are mapped explicitly:
  - u at face i of cell row j, layer k, maps to face (nx − 1 − i) of row (ny − 2 − j);
  - v at face j of cell column i maps to face (ny − 1 − j) of column (nx − 2 − i);
  - w at cell (i, j) maps to cell (nx − 2 − i, ny − 2 − j), unnegated.

  The domain dimensions are chosen so that the rotation maps the grid onto itself.
- It compares two stages separately:
  - the initial field `u0` after the parameterizations and before the pressure solve, where a defect shows up in the cells it writes. It is captured through the existing `stage` callback of `applyParametrizations` at `"solid_mask"` (`WINDSGeneralData.cpp:330`, after `setVelocityZero`);
  - the final field, where the pressure correction has spread differences.
- Register the check in `CMakeLists.txt` under `DTCC_QES_BUILD_TESTS`, next to the existing native checks, and reuse `tests/native/building_fixtures.h` for the geometry.
- F1 uses it on single buildings; F3 uses it on asymmetric layouts. A symmetric layout is just the case where the rotated geometry equals the original.

**P3. Immutable result archive.**
- `run_full_validation.py` writes summaries to `validation/output/fast/` and `validation/output/full/`, which each run overwrites. Its run records are keyed by code fingerprint and reused.
- Add an `--archive LABEL` option (Python only, outside the native identity). After a run, it copies the summary, the figures and the run records it used into `validation/output/archive/LABEL-<short sha>/`, writes a SHA-256 manifest, and refuses to overwrite an existing folder.
- Labels: `baseline`, `F1` … `F6`, `F3-V1`, `F3-V3`, `release`. The results file cites these folders.

---

## 4. The fixes

Each step is one commit: failing test first, then the change, then the per-fix score. Order: simplest and most certain first.

### F1. Upwind cavity angle

- **Cause.** `perpendicular_dir = atan2(…) + π/2` lies in (−π/2, 3π/2]. The wrap tests `<= -M_PI`, which never holds, and the branch chain has no case for [−π/4, π/4) (`UpwindCavity.cpp:112-127`). `effective_gamma` is initialised to 0 (`:86`), so a face in the missing range gets γ = 0 instead of its own angle. A face in [5π/4, 3π/2] gets γ off by π/2, because it is never wrapped.
- **Change.**
  - Wrap with `if (perpendicular_dir[id] > M_PI) perpendicular_dir[id] -= 2 * M_PI;`.
  - Add the final `else { effective_gamma[id] = perpendicular_dir[id]; }`.
  - The two later tests of `abs(perpendicular_dir[id])` between π/4 and 3π/4 (`:207`, `:247`) then select the right component without further change.
- **Tests (new, failing today).**
  - Mirror check (P2), default parameterizations, 40 × 40 × 30 m building: rotated 70° with wind 200°, rotated 20° with wind 250°, and axis-aligned with wind 180° against 0° and 185° against 5°.
  - Pass limit, on `u0` before the solve: the mirror difference with the upwind cavity on is no larger than with `upwind_cavity=0` plus 0.01 m/s. Today, on the final field, it is 1.52 and 0.54 m/s against 0.06; the `u0` values are recorded in the commit.
  - A direct unit test of the angle mapping for the eight normals at 45° steps.
- **Expected side effects.** Results change in front of south-, south-west- and rotated east-facing façades, on both the strict and the footprints path. Upstream-parity fixtures and S7 workers with wind onto such a face will differ (findings 10, section 5).

### F2. Far wake past low obstacles

- **Cause.** In the far-wake march, the exposed-faces branch breaks at any foreign solid cell at level k, before the upstream logic that lets the wake pass an obstacle lower than 0.75 H (`PolygonWake.cpp:490-495` against `499-510`).
- **Change.** Replace `if (solid) break;` by a break only in the cases that should end the march:
  - the march has not yet left the building (`x_id_min < 0`): a touching neighbour;
  - the cavity was fitted to a gap (`canyon_factor < 1`);
  - the obstacle is also solid at level `kk` (0.75 H).

  Otherwise fall through to the existing upstream code, which already skips writes into solid cells.
- **One definition of solid.** The break uses `icellflag_initial` and counts flags 0, 2 and 7 as solid; the upstream code below uses `icellflag` and flags 0 and 2. Flag 7 marks cut-cell buildings in QES, and nothing on main assigns it (checked in revision 5). The parameterizations relabel only fluid cells, so solid cells read the same in both arrays. Use flags 0 and 2 from `icellflag`, as the upstream code does.
- **Tests (new, failing today).**
  - A 20 × 20 × 60 m tower with a 6 × 6 × 4 m kiosk 30 m behind it, `Footprints()`, wind 270°. Centreline speed at the first cell centre, 50, 80 and 120 m behind the tower, within 0.15 m/s of the same case with `exposed_faces=False` (0.11, 1.26, 1.88 m/s). Today: 1.32, 2.33, 2.47.
  - The same with an obstacle of 0.8 H: the wake must still stop.
  - A touching neighbour (party wall): unchanged from today.
- **Expected side effects.** Only the footprints path with `wake=1` or `2`. Wakes of tall buildings get longer wherever low buildings stand behind them, which is most of Case E.

### F3. Reference wind

The step has three parts, following the review: the incident reference, the direction the later stages use, and the magnitude each stage uses.

- **Cause.** Every stage reads `u0_h, v0_h` from one face at the roof reference point of the current field (`PolygonWake.cpp:87-93` and four other sites). All upwind cavities are written first, up to 0.6 H of their own building, so the air above a lower neighbour may already be scaled or reversed.
- **Part 1, the incident reference (all variants).**
  - In `applyParametrizations` (`WINDSGeneralData.cpp:330`), after `resetConditionState` and before the upwind-cavity loop, capture each building's incident vector: `u0` and `v0` at the face of its roof point (`domain.face(i_building_cent, j_building_cent, k_end)`), the same face every stage reads today. Nothing has written to the field at that point, so it holds the profile at height z[k_end] for both profile kinds. Store it on the building (`incident_u`, `incident_v`, `incident_dir`), and reset it in `PolyBuilding::resetConditionState` (`PolyBuilding.h:102`).
  - **Incident direction.** `incident_dir = atan2(incident_v, incident_u)`, computed exactly as the stages compute `upwind_dir` today. For a building that no cavity touches, every value then stays bit-identical. A "profile direction parameter" cannot be used instead: layer tables and measured profiles can turn with height (finding 15), and converting `site_wind_dir` would differ from today's value in the last bits for every building.
  - **Zero speed.** When the incident vector is exactly zero (a calm log profile, or a calm layer in a table), `atan2(0, 0)` gives 0, an arbitrary eastward frame. In that case only, `incident_dir` falls back to the condition's `site_wind_dir`, converted as `LogProfile.cpp` converts it. All reference magnitudes are zero, so the stages that scale by the reference write zeros, as today; the later stages still scale their local reads.
- **Part 2, the magnitude (all variants).**
  - `upwindCavity` (`UpwindCavity.cpp:90-93`) and `prepareWake` (`PolygonWake.cpp:87-93`) use the incident vector and direction instead of reading the field. Where no cavity touched the roof point this is the value they read today, so those buildings do not change.
  - `applySpreadingWake` needs no change of its own. Both of its `prepareWake` calls (`WINDSGeneralData.cpp:448`, `:467`) then return the clean roof wind, which removes the order dependence of the second call (finding 2), and the shelter is applied to that wind at `:468`.
  - The later stages keep their local reads (finding 3). No variant changes them, and the benchmark records whether the sidewall and rooftop zones of a sheltered building are weaker than those of an exposed one, rather than assuming it.
- **Part 3, the direction for the later stages (D2).** `streetCanyon`, `streetCanyonModified`, `sideWall` and `rooftop` (`StreetCanyon.cpp:100-104`, `StreetCanyonModified.cpp:129-133`, `Sidewall.cpp:85-89`, `Rooftop.cpp:106-110`) take `upwind_dir` from one shared helper. V1 returns `incident_dir`. V3 captures, at `stage("wake")` in `applyParametrizations`, the field direction at each roof point, with the 10 % fallback to `incident_dir`. Those stages keep `u0_h` and `v0_h` only for the street canyon's observer event (`StreetCanyon.cpp:105`), which is then given the vector the direction came from. During the benchmark the helper selects V1 or V3 through a build-time constant on the branch. The constant and the losing variant are removed before the F3 commit is final (D1: no switches ship). For V3 the helper reads a per-building direction captured at the stage boundary (D2), never the live field.
- **Benchmark for D2.** Parts 1 and 2 are implemented and tested first. Then V1 and V3 are built and run on:
  - **Synthetic layouts** (2 m grid, both `wake=2` and `wake=3`):
    - the tower with a low building in front (the bug case below);
    - a low building 1 H behind a tall one, inside its lee cavity, where a reversed local wind is physically right;
    - two equal cubes in tandem, 2.5 H apart, for the sheltered sidewall and rooftop;
    - a 3 × 3 array of blocks at 0°, 22.5° and 45°.
  - **AIJ:** `run_full_validation.py --fast`, on top of F1 and F2, archived as `F3-V1` and `F3-V3`.
  - **Recorded per variant:**
    - the F3 tests below, pass or fail;
    - the point-mirror error of each synthetic layout (P2), on `u0` and on the final field;
    - for every building, the angle between its later-stage direction and its wake direction, and whether the roof-point field speed fell below the 10 % threshold;
    - sidewall and rooftop cell counts and peak speeds beside the sheltered tandem cube, against the exposed one;
    - pooled q, FAC2, R and FB per AIJ comparison, and the share of probe-directions that move by more than 0.05 in K against the build without F3;
    - the Case E tower effect from `experiments/e2e_review/x3.py`: mean ΔK within 30 m of the tower and its sign upwind, beside and downwind;
    - time per direction on Case E.
  - **Decision rule, in this order.** It is deterministic: each step either decides or passes to the next.
    1. A variant that fails a required F3 test is out.
    2. Score each variant by the mean, over Cases A, B, D and E, of the case's pooled q and R (each case weighted equally). A variant wins here only if its score is higher by more than 0.02 **and** no single case's pooled q or R is lower than the other variant's by more than 0.02. A variant that improves one case and worsens another by more than 0.02 does not win here; the conflict is reported.
    3. Otherwise, the variant with the smaller mean `u0` mirror error over the synthetic layouts, if the two differ by more than 0.05 m/s.
    4. Otherwise V1, the simpler and order-independent one.
  - **Frame consistency is a criterion, not a gate.** V1 gives every building one frame; V3 can orient a building's sidewall and rooftop against its own wake. Revision 2 treated that as a failure. It is a modelling choice: a reversed local wind behind a tower is physical, and a rooftop vortex aligned with it may be closer to the real flow. The benchmark reports it, and it enters the decision only through the scores and the mirror error.
  - **Output:** a table per variant in `validation/PHYSICS_BUG_FIX_RESULTS.md`, with the rule applied step by step and a recommendation. **The user makes the choice**; work continues with F5 and F6 meanwhile, since they do not depend on it.
- **Tests (new, failing today).**
  - Required: a 30 × 32 × 90 m tower with a 10 × 12 × 8 m building 6 m in front, wind 270°. The low building's upwind cavity cells lie on its windward side, and the mean u at the first cell centre in the strip upwind of it is positive. Today: 114 cavity cells upwind, mean u −0.08 m/s.
  - Required: the same case with `wake=3`.
  - Required: for an isolated building, every stage's reference equals the profile value bit for bit, in both variants.
  - Required: order independence. Permuting the input order of buildings leaves `u0` unchanged. True today for equal heights; with V3 captured at the stage boundary it must hold for unequal heights too.
  - Recorded, not required: the frame angle per building (above).
- **Expected side effects.** Part 1 and 2 change only buildings whose roof point lies inside another building's upwind zone. Part 3 changes nothing under V3 for buildings outside other buildings' cavities and wakes, and under V1 changes the later stages of any building whose roof-point field direction differs from the profile direction. This is the fix most likely to move the Case E tower result, because the two 18 m buildings near the tower are in exactly this position.

### F4. Façade runs

- **Cause.** The cavity length, the sidewall eligibility and the wake-length interpolation are computed per polygon edge. `prepareParameterFaces` merges only exactly collinear vertices, and only on the footprints path.
- **Change.**
  - In `prepareParameterFaces`, simplify each ring with tolerance t = 0.5 × min(dx, dy) (D3).
  - **Order.** Repeatedly remove the vertex with the smallest deviation from the line through its current neighbours, ties broken by its coordinates (x, then y). The result does not depend on which vertex the ring starts at.
  - **Bound.** A removal is allowed only if every *original* vertex of the merged run stays within t of the new edge. That stops a long gentle curve from being flattened step by step.
  - **Topology.** A removal is rejected when the triangle formed by the vertex and its two neighbours contains or touches any other vertex of any ring of the building, or when the new edge crosses any other edge. This prevents self-intersection, holes touching the outer ring or each other, and a narrow passage collapsing.
  - Never reduce a ring below three vertices, and keep the ring orientation. Holes are simplified with the same rule.
  - Run the step on the strict path as well (D4): remove the early return at `PolyBuilding.cpp:305-306`. The function is called for every building from `WINDSGeneralData.cpp:148`.
  - The solid mask keeps using the original ring, as it does today. When a ring changes, the function stores the original in `maskVertices` and `maskRingOffsets`, and the mask reads those (`Building.h:113-114`). When nothing changes it returns before touching the building (`PolyBuilding.cpp:331`), which keeps plain rectangles bit-identical.
  - `setPolyBuilding` is called again on the simplified ring (`:337`), so the centroid, and with it the roof reference point, can move by up to t for a simplified building. That is intended; the reference capture in F3 runs later and uses the moved point.
- **Tests (new, failing today).**
  - A 60 × 20 × 30 m building with a 0.1 m kink at mid-façade, with and without `Footprints()`: the number of upwind-cavity cells and the speed 30 m in front are within 5 % of the plain rectangle. Today: 1,430 cells against 2,902, and 1.15 against 0.17 m/s.
  - A façade split by three collinear vertices on the strict path: same result as the rectangle.
  - A real corner (a 2 m setback on a 2 m grid) is not merged.
  - Circles, judged by deviation, not edge length. A regular 32-gon of radius R loses no vertex when R(1 − cos(2π/32)) > t (R > 52 m on a 2 m grid). A smaller one is simplified, and every original vertex lies within t of the simplified ring. On a 2 m grid a 20 m round tower becomes about a 16-gon; that is intended.
  - Start-vertex invariance: the same ring started at each of its vertices gives the same simplified ring.
  - Topology: a U-shaped footprint with a 1 m slot, a courtyard whose hole lies 0.5 m from the outer ring, and a ring with a vertex close to a non-adjacent edge all stay simple and keep their slot or wall.
  - Unequal spacing: dx = 2 m, dy = 1 m uses t = 0.5 m.
  - The solid mask is bit-identical before and after for every case above.
- **Expected side effects.** Longer upwind cavities and restored sidewall zones for digitised footprints. Case E changes; Cases A, B and D (plain boxes) should be bitwise unchanged, which is itself a test.

### F5. Stress limiter

- **Prior work.** `research/pedestrian-wind-campaign` (`24c04ef`) has `spectral_limit` (`dtcc/api/covariance_model.h`). Its oracle tests are the two files already on main (finding 8). Its optional `bounded_consistent_v1` model (`boundTurbFields`, `TURBGeneralData.cpp:768-781` on that branch) combines two steps: a production rescaling r = k_cap/k0 before the anisotropy, and the spectral scaling α. The pilot (`validation/CONSISTENCY_PILOT_RESULTS.md`, on both research branches) passed every numerical gate but failed the accuracy screen, and the model stayed optional. The eight-way comparison (D6) separated the two steps; its arm without r is F5. F5 ports only α, as a replacement for the component clip; it does not port r.
- **Cause.** `boundTurbFields` clips each Cartesian component to ±B separately (`TURBGeneralData.cpp:735-777`). The bound depends on the grid orientation, and a tensor aligned with neither axis can have a directional variance up to 3B (all six components at B gives an eigenvalue 3B).
- **Change (D6).**
  - Create `dtcc/api/covariance_model.h` on main with only `spectral_limit`, copied unchanged from the branch. Keep that path so that the probe compiles as it is. The function is header-only and uses `stress_validity` from `dtcc/api/stress_validity.h`, which is already on main. Do not copy `CovarianceModel`, `uncapped_energy`, `production_scale` or `consistent_constitutive`; they belong to r.
  - What it does: α = min(1, B / spectral radius) in double precision, and multiplies the six components by α in place. It returns α = 1 without an eigensolve when the largest absolute row sum is at most B, and for a zero tensor. For a non-finite tensor or bound it returns NaN and leaves the tensor unchanged, which is also what today's clip does with NaN.
  - Replace the six clipping passes by one loop over `icellfluid`: call `spectral_limit` on the six components, write them back, store α, and call `stress_observer(2, …)` with the result as today (`:773`).
  - Calm flow: B = 0 when u* = 0. A zero tensor gets α = 1. A non-zero tensor gets α = 0 and is zeroed, which is what the clip to ±0 does today.
  - Leave the early cap on k in place (`TURBGeneralData.cpp:453`, in `getTurbulentViscosity`). It feeds `CoEps` and `tke`, and removing it is a separate question. The second check at `:538` reads the stored `tke`, which is already capped, so the k-cap flag is set at `:453`.
  - **Record the limiter's activity.** Add two per-cell arrays to `TURBGeneralData` and size them with the other fields: `spectralScale` (α, 1 where unlimited) and `energyCapped` (the k cap at `:453` fired). Then:
    - export (`dtcc/turbulence.cpp:153-158`) and probe sampling (`dtcc/turbulence.cpp:56-57`) read these instead of inferring the state from magnitudes. A cell is capped when B > 0 and (α < 1 or the k cap fired). The `bound > 0` guard is kept, so calm flow is still reported uncapped;
    - the result struct (`dtcc/api/wind_config.h:94`, beside `capped_cells`) gains `spectral_limited_cells` (the research branch's name) and `energy_capped_cells`. Both are bound in `src/cpp/bindings.cpp` beside `capped_cells` and passed through in `src/dtcc_qes/turbulence.py`;
    - the cap policy text at `src/dtcc_qes/turbulence.py:79` is rewritten. It says "TKE or any absolute stress component", and becomes: the stress tensor was scaled to spectral radius B, or the TKE cap fired; a zero bound in calm flow is uncapped.
- **Tests (new, failing today).**
  - `tests/test_covariance_limiter_v2.py` passes (it fails on main today). Its first two tests run unchanged. The third, `test_native_zero_length_and_supported_zero_energy_branches`, asserts properties of `uncapped_energy`, `production_scale` and `consistent_constitutive`, which F5 does not port. Reduce it to its last assertion, `spectral_limit(zero, 0) == 1` on a valid zero tensor, and say in the commit message why the rest was removed.
  - On the 20 m cube case at 270°, 225° and 247.5°: in every computed cell, the largest eigenvalue magnitude is at most B (float32 tolerance), and so is the streamwise variance. Today the streamwise variance reaches 2.6–3.0 B. Equivalently, the streamwise σ is at most √B.
  - Rotation invariance: a synthetic tensor rotated about z by 45°, and by a random 3-D rotation, gives the same eigenvalues after limiting.
  - Indefinite tensors: a synthetic tensor with one negative eigenvalue, below and above the bound. The limiter keeps the sign pattern of the eigenvalues, scales them by α, and the cell is still reported non-realizable. This checks that the limiter does not claim to repair what it cannot.
  - The `capped` state from export and from probe sampling equals (B > 0 and (α < 1 or k cap fired)) cell for cell, and `capped_cells`, `spectral_limited_cells` and `energy_capped_cells` match counts of the per-cell arrays.
  - Calm flow (B = 0): no cell is reported capped, as today.
  - The share of non-realizable cells at 1.5 m is recorded before and after. Revision 2 expected it to fall. The new limiter scales by a positive factor, so it never changes whether a tensor is realizable; the share can change only in cells where the old component clip did. That is an empirical question, reported, not required.
- **Expected side effects.** σ falls in the most strongly sheared cells at edges and corners, where the tensor is oblique to the grid. Some tensors that the old clip left alone are now scaled, because every component was below B while an eigenvalue was above it. Where the old clip cut one axis variance, that variance is still bounded by B, but the other components are now scaled down with it. Cells with spectral radius at most B do not change.

### F6. Ground-adjacent gradient

- **Cause.** For a cell above a horizontal wall, dU/dz is a one-sided difference of the cell-centred velocity to the cell above (`TURBWall.cpp:184-198`). For the inflow log profile with z0 = 0.1 m on a 2 m grid, that is 43 % low at the first centre (ratio 0.57). The next cell up uses the general central difference (`TURBGeneralData::derivativeVelocity`, `:346`), which is 19 % high there. On a 1 m grid the errors are 41 % and 17 %.
- **What was measured.** In an empty domain σ_u/u* is 1.30 and 2.88 at 1 and 3 m, against 2.5 at 9 m. The gradient error alone does not explain this. Together with the mixing-length factor d/(d + z0) (finding 16) it predicts 1.31 and 2.91, so both effects are understood. F6 fixes the gradient only.
- **What the change assumes.** The proposed form is exact for the neutral shifted log profile U ∝ ln((z + z0)/z0). Applied to anything else it is a model that assumes log behaviour between the samples. That covers the stable and unstable log profiles (`site_one_overL ≠ 0`, `LogProfile.cpp:110-116`), layer tables and measured profiles. For uniform flow it is exact (zero). For linear shear it overestimates: with cell centres at 1 and 3 m and z0 = 0.1 m it gives 1.75 × the true gradient at the first centre. That is acceptable where the flow is a surface layer over the ground, and not established above roofs, in the rooftop vortex or in separated flow.
- **Scope.** The change applies to the **ground** only, which is exactly the cells in `TURBWallTerrain`'s `wall_below_indices` (finding 6). Cells above roofs are handled by `TURBWallBuilding` and keep today's difference. Roofs have a different log profile (finding 5) and often reversed or separated flow, and extending the change to them needs its own justification and tests.
- **Change.**
  - Add a member `comp_ground_velocity_deriv` to `TURBWallTerrain` and select it in the constructor where `terrainWallFlag == 2`, the default (`TURBWallTerrain.cpp:47-48`). The member pointer is already typed on `TURBWallTerrain` (`TURBWallTerrain.h:59`), so no cast is needed. The new member calls the inherited `comp_velocity_deriv_finitediff_stairstep` for every wall, then rewrites the ground rows as below. `TURBWallBuilding` keeps the base function, so roofs are unchanged by construction. The terrain object runs after the building object (`TURBGeneralData.cpp:122-123`, `:422-424`), so its values are final.
  - Wall elevation and roughness: the wall is the bottom face of the ground cell, `domain.z_face[k]`, rather than an assumed z = 0. The roughness is `WGD->z0`, which is the profile's `roughness_length` for every profile kind (finding 15, checked in revision 5). Terrain is not on main; when it lands, it reuses this with the terrain face as the wall, and is tested then.
  - Velocities are cell-centred, as today: U_k = ½(u at faces i and i+1 of cell k), V_k likewise from the v faces.
  - For a ground cell k with fluid at k+1, with d_k = z[k] − z_face[k] the height of a cell centre above the wall:
    dU/dz = (U_{k+1} − U_k) / ((d_k + z0) · ln((d_{k+1} + z0)/(d_k + z0))). The same for V.
  - For the cell above it, when cells k, k+1 and k+2 are fluid:
    dU/dz at k+1 = (U_{k+2} − U_k) / ((d_{k+1} + z0) · ln((d_{k+2} + z0)/(d_k + z0))). This replaces the central difference that `derivativeVelocity` wrote for that cell.
  - **Where the stencil is not available.** When the cell above a ground cell is solid (a one-cell gap under an elevated building or an overhang), no difference across fluid cells exists. Use the wall-function form from the ground alone, dU/dz = U_k / ((d_k + z0) · ln((d_k + z0)/z0)). This is the shifted-log form of the wall function that `set_loglaw_stairstep` uses (U/(½dz · ln(½dz/z0)), `TURBWallTerrain.cpp:92-93` and `TURBWallBuilding.cpp:85-86`). Never difference into a solid cell. When k+2 is solid, cell k+1 is left as the building object set it (its wall-above difference to k, both fluid).
  - Do not switch `terrainWallFlag` to 1 to get a log-law treatment. That path's left-wall loop iterates the wall-below list (`TURBWallTerrain.cpp:180`) and overwrites lateral derivatives on every ground cell. `QES_TURBULENCE.md` hazard 6 records the same defect in the building class.
- **Tests (new).**
  - Manufactured profiles, imposed directly on u and v of a small domain, comparing the computed Gxz and Gyz with the analytic derivative at the first two centres:
    - neutral shifted log, uniform and stretched dz: relative error ≤ 1e-5;
    - uniform flow: exactly zero;
    - linear shear: the error equals the analytic value of the log-space formula (documented, not hidden);
    - a profile at a direction oblique to x and y: Gxz and Gyz each correct.
  - Above a flat roof, with a reversed rooftop profile: the gradient is bit-identical to today's. This is the test that the restriction to the ground holds.
  - A one-cell gap under an elevated building: the wall-function form is used and no stencil touches a solid cell.
  - Empty domain, full solver, neutral log profile, z0 = 0.1 m. In every layer, the ratio of σ_u to its value at 9 m is within 2 % of the prediction [d/(d + z0)] / [9/(9 + z0)] (finding 16). On the 2 m grid that is σ_u/u* ≈ 2.30 and 2.45 at 1 and 3 m, against 1.30 and 2.88 today. Repeat on the 1 m grid (≈ 2.11 and 2.37 at 0.5 and 1.5 m) and on a stretched vertical grid. Turbulence intensity decreases monotonically with height in the undisturbed column.
  - Revision 4 asked for σ_u within 5 % of its 9 m value in every layer. That cannot pass while the mixing length is κ·d: the first cell stays 8 % low on 2 m and 16 % low on 1 m. Shifting the mixing length is a separate model change (section 7).
- **Expected side effects.** In the first cell above the ground (2 m grid, z0 = 0.1 m), dU/dz rises by 1.75 ×. In the local closure σ scales with the shear and k with its square, so σ_u rises by about 1.75 × (1.30 → 2.30 u*) and k by about 3.1 ×. Both rises are smaller where the k cap or the stress limiter acts. In the second cell σ_u falls by about 16 % (2.88 → 2.45 u*) and k by about 29 %. On a 1 m grid: 1.70 ×, 2.9 ×, −15 % and −27 %. This changes every gust-based comfort result at 1.5 and 1.75 m, and the turbulence scores of Cases A, B and D. It is the fix with the largest visible effect on users.

---

## 5. Verification of the whole batch

**Per fix** (after each commit):
- The new tests pass and the full unit suites pass, OpenMP and serial.
- `run_full_validation.py --fast --archive F<n>`, with a table of the change in q, FAC2, R and FB per comparison, and the share of probe-directions that move by more than 0.05 in K.
- For F5 and F6: the k scores of Cases A, B and D, and the gust-equivalent-mean map of the comfort example.

**Before release:** the full `run_full_validation.py --archive release` (Cases A, B, D and E at 2 m and 1 m, every direction), compared with the full baseline from P1. The fast set has four diagonal Case E directions at 2 m. That is enough to iterate on, but not to judge angle-sensitive fixes (F1, F3) or a tolerance tied to the cell size (F4).

**Acceptance.** These are bug fixes, so a lower score does not block a fix on its own. The rule:
- Each fix must pass its own tests.
- A fix whose pooled q or R falls by more than 0.02 in any case gets an attribution note before the batch proceeds: which probes moved and why. A score that depended on a defect is recorded, not restored.
- The batch as a whole is reported against the P1 baseline in `validation/PHYSICS_BUG_FIX_RESULTS.md`, citing the archive folders.

**Tower effect.** After F2 and F3, rerun `experiments/e2e_review/x3.py`: the change in K within 30 m of the Case E tower, measured +0.23 to +0.32, simulated 0.00 today. This shows whether part of the missed tower effect was a bug.

**Locality.** A fix's direct effect is checked where it acts, not on the final wind:
- wind fixes on `u0` before the pressure solve: the cells that differ lie in the zones the fix writes (cavity, wake, sidewall, rooftop of the affected buildings);
- turbulence fixes on the turbulence fields with the mean wind held fixed: F5 changes only cells with α < 1, F6 only the first two ground cells and their dependants;
- on the final field, differences spread through the pressure correction. They are reported as magnitude statistics (maximum, 99th percentile, share of cells above 0.05 m/s), not held to the zones.

**Reference fixtures.**
- `tests/fixtures/reference/*` and `turbulence/upstream/*` compare against upstream QES. F1 and F3 change the wind fixtures only if their wind strikes an affected face; F5 and F6 change every turbulence fixture.
- For each fixture that changes: confirm the locality above, then move it from "upstream parity" to "audited" with `tools/make_reference.py`, and record the difference in `docs/turbulence-reference-differences.md` (and a matching note for winds).
- Unchanged fixtures must stay bit-identical.

**Sanitizers.** One Debug ASan/UBSan run of the native tests, since F3 adds per-building state, F4 changes vertex arrays and F5 adds a per-cell array.

**Unqualified build (D7).** The full `pytest -W error` suite and `tools/wheel_runtime_smoke.py` run against the new build, which reports `solver_policy_build_supported = False`. Both already accept that state (finding 12); they confirm that adaptive runs return `unqualified_build` and that nothing else depends on the qualification.

---

## 6. Release

No re-qualification in this release (D7). `dtcc/pedestrian_qualification.h` and the evidence in `docs/data/` are left unchanged.

1. **Build checks:** fresh serial, OpenMP and ASan/UBSan builds; CTest and `check_native_symbols`; an sdist and a wheel built from it, with `tools/check_artifacts.py` and `tools/wheel_runtime_smoke.py`.
2. **Version 0.1.0b5**, with a changelog entry per fix: what changes and how it was checked. The previous behaviour is not kept (D1). The changelog also says that `Solver(policy="pedestrian-v1")` returns `unqualified_build` in this release, because the native identity changed and the policy has not been re-qualified.
3. **Documentation:**
   - `QES_TURBULENCE.md`: hazard 9 (ground-cell gradient) closed for the ground by F6, with the remaining mixing-length factor (finding 16) stated; hazard 14 (stress validity) updated with the spectral limiter contract and the fact that it does not repair indefinite tensors;
   - `docs/wind-comfort.md`: gust results change;
   - `src/qes_core/PROVENANCE.md`: the new native identity, marked unqualified;
   - `validation/AIJ_VALIDATION.md`: a short note with the new headline block.
4. **Merge to `main`** after the user has seen the results file. Check first that `main` has not moved.
5. **Draft the upstream issue** for F1 and F3 (decision D5).

---

## 7. Left out of this batch

Most of these are small native changes in files this batch touches. They stay out anyway: six interacting changes already need careful attribution, and adding more would make each score harder to explain. When `pedestrian-v1` is re-qualified (last row), whatever native changes have landed by then are qualified together.

| Review id | Change | Size |
|---|---|---|
| B8 | Use the outer-ring area for the effective width and length | A few lines in `PolygonWake.cpp` |
| B7 | Clamp W/H in the `high_rise=1` fit | A few lines; opt-in feature |
| B6 | Sidewall face selection independent of the wind sign | Medium; can reuse the mirror check from P2 |
| B10 | Ambient turbulence term and bounded mixing length | Medium; a model change more than a bug fix |
| — | F6 above roofs | Needs its own profile assumption and tests |
| — | Mixing length κ·(d + z0) near the ground (finding 16) | A few lines in `LocalMixingDefault.cpp`; it would bring the first-cell σ_u to the surface-layer value. It is a model change and changes every turbulence result again, so it gets its own scoring. |
| — | Re-qualify `pedestrian-v1` (D7) | 1–1.5 days. The exact-match check cannot pass (finding 10). Two routes were considered. (a) Declared change: list the affected S7 workers by comparing their initial fields before the solve, require an exact match for the rest, and rerun the references and adaptive workers for the affected ones. (b) Rerun all 24 workers from scratch. Either way the gate is the original one, zero false acceptances (`validate_solver_policy.py:152`), and changed decisions are reported. |
| P2 (performance) | Remove `divergenceStress`, thread the turbulence loops | Medium; bit-exact |

---

## 8. Effort and order

| Step | Rough effort | Depends on |
|---|---|---|
| P0–P3 | 1 day (the full baseline at 1 m dominates) | – |
| F1 | half a day | P2 |
| F2 | half a day | P0 |
| F3 | 2 days: parts 1 and 2, two variants, the D2 benchmark; then a stop for the user's choice | P2, F1, F2 |
| F4 | 1–1.5 days (topology checks) | F1 (the tests share fixtures) |
| F5 | 1–1.5 days (port, activity arrays, export, sampling, bindings and Python result) | P0, D6 |
| F6 | 1 day | P0 |
| Full validation, fixtures | 1 day | all |
| Release checks and notes (section 6) | half a day | all |

The two turbulence fixes are independent of the four wind fixes and can be done in either order. Within the wind fixes, F1 and F2 go first because they are certain and small; F3 follows so that its D2 comparison runs on a field that no longer has the F1 and F2 defects; F4 is last because its effect depends on the cavities that F1 and F3 correct.

---

## 9. Response to the external review of revision 2

Each point, what was checked, and what changed.

| Point | Verdict | Change in revision 3 |
|---|---|---|
| F5: ½ trace bounds the eigenvalues only for a PSD tensor; scaling cannot repair an indefinite one | Agreed | Contract chosen: directional variance cap (D6), which is also the rotation-invariant form of today's bound. A trace cap would have loosened the bound to 2B in one direction. Indefinite tensors are tested; the non-realizable share is reported, not predicted. |
| F5: variance against σ | Agreed | Bounds stated in variance (B) and σ (√B). |
| F5: `capped` is inferred in `turbulence.cpp` | Confirmed at `dtcc/turbulence.cpp:56-57, 153-158` | Limiter activity recorded per cell and used by export and sampling. |
| F5: the limiter tests are tracked and already use a spectral limiter | Confirmed; they also fail on main, because their header is only on the research branches | F5 ports that limiter (α only) and makes the tests pass. The research model's failed accuracy screen is read first. |
| F3: sidewall and rooftop read local velocities | Confirmed, and it goes further: the later stages use the reference only for direction | Finding 3 corrected. D2 reduced to a direction choice; V2 dropped because it equals V1 there. |
| F3: separate reference, direction and magnitude | Agreed | Parts 1–3 of F3. |
| F3: capture V2's reference at a stage boundary | Applies to V3 instead | V3 captures its direction once, after the wakes and before the later stages. |
| F3: "one frame per building" prejudges V3 | Agreed | Demoted from a required test to a recorded criterion. |
| F3: zero incident speed | Agreed | Incident direction from the captured incident vector, with `site_wind_dir` only when that vector is zero (revision 5); V3 falls back below 10 % of the profile speed. |
| F6: exact only for one profile | Agreed | Stated as a model assumption. Scope restricted to the ground; roofs unchanged and listed in section 7. |
| F6: manufactured-profile tests | Agreed | Log, uniform, linear and oblique profiles; reversed rooftop shear as an unchanged-roof test. |
| F6: wall elevation and roughness sources | Agreed | Ground face and the profile's z0, with a check that they agree. Terrain is not on main, so it is deferred. |
| F6: fallback differentiates through a solid | Agreed | Wall-function form from the ground alone; no stencil into a solid cell. |
| F6: "k roughly doubles" | Agreed, it was wrong | σ_u about 1.75 ×, k about 3.1 × on the 2 m grid (revision 5; revision 3 said 1.9 × and 3.7 ×). |
| F4: half-cell rationale is false | Agreed | Restated as a modelling tolerance (D3). |
| F4: topology, start vertex, unequal spacing, 32-gon criterion | Agreed | Global smallest-deviation order, triangle and crossing checks, t = 0.5 · min(dx, dy), deviation-based circle test. |
| Re-qualification: the compatibility checker cannot qualify intended changes | Confirmed; the S7 workers include winds onto south faces and mixed heights | Revision 3 proposed a declared-change procedure. Revision 4 (D7): no re-qualification in this release, since the policy is opt-in and experimental; the procedure is kept in section 7. |
| Full validation before release | Agreed | Full set at 2 m and 1 m in P1 and before release. |
| Deterministic D2 ranking | Agreed | Rule rewritten: mean score with a per-case veto, then mirror error, then V1. |
| Immutable archives | Confirmed: the runner overwrites its summary folders | P3, `--archive` option. |
| Stage-aware symmetry and locality | Agreed | P2 rotates geometry and maps faces; locality judged on `u0` and the turbulence stage, not the final field. |
| Repository facts | Confirmed: HEAD is `033df33` | Base updated; the extra commits do not touch native code. |
| Leave section 7 out | Agreed; it was already not planned | Section 7 now says it is excluded. |

---

## 10. Corrections in revision 5

A final pass checked every file, line number, function and formula in the plan against `033df33` and the research branches. What changed:

| Where | Revision 4 said | Revision 5 |
|---|---|---|
| F6, finding 6 | Ground and roofs share one `wall_below_indices`; change `TURBWall.cpp` | Separate wall objects: roofs in `TURBWallBuilding`, ground in `TURBWallTerrain`. F6 is a new member of `TURBWallTerrain`, so roofs are unchanged by construction. |
| F6, cause | Gradient 48 % low, 15 % high | Those are the measured σ_u errors. The gradient errors are 43 % and 19 % (2 m grid, z0 = 0.1 m). The rest comes from the mixing length κ·d (finding 16), and the two together reproduce the measurements. |
| F6, test | σ_u within 5 % of its 9 m value in every layer | Cannot pass with mixing length κ·d. The test now checks against the predicted profile; shifting the mixing length is listed in section 7. |
| F6, side effects | σ_u × 1.9, k × 3.7; second cell −13 %, −25 % | × 1.75 and × 3.1; second cell −16 % and −29 % (2 m grid). |
| F6, z0 | Check that `WGD->z0` equals the profile's z0 | Checked: one source for every profile kind (finding 15). |
| F6, flag-1 warning | Cited hazard 6 | The terrain defect is at `TURBWallTerrain.cpp:180`; hazard 6 is the building analogue. |
| F5, source | `spectral_limit` on `research/unified-wind-turbulence` | It is on `research/pedestrian-wind-campaign` (`24c04ef`); only the documents are on both branches. |
| F5, port | Header and implementation | Header only, and only `spectral_limit`; `stress_validity.h` is already on main. |
| F5, limiter test | Passes after the port | The third test calls the production-coupling functions that are not ported; it is reduced to its spectral assertion. |
| F5, files | `TURBGeneralData.cpp`, `turbulence.cpp` | Also the result struct, the bindings, the Python result and its cap policy text. Calm flow and non-finite input are specified. |
| F5, line numbers | `boundTurbFields` 741-778, B at 743 | 735-777, B at 737. |
| F3, direction | From the profile's direction parameter | From `atan2` of the captured incident vector, which is bit-identical to today for untouched buildings. Profiles can turn with height, and converting `site_wind_dir` would change every building in the last bits. `site_wind_dir` is used only when the incident vector is zero. |
| F3, calm | "A calm profile writes no parameterization" | Not true today: the stages run and write zero magnitudes. Stated as such. |
| F3, `wake=3` | One read after the cavities | Two reads; the second also follows earlier buildings' wake cavities. Both become clean. The ascending-height order is now recorded (finding 2). |
| F1 | Three later tests, "and the w block" | Two (`:207`, `:247`). |
| F2 | Confirm what flag 7 marks | Nothing on main assigns flag 7; use flags 0 and 2 from `icellflag`. |
| F4 | Strict path "as well" | The early return to remove, the mask fields that keep the original ring, and the centroid moving with the simplified ring are named. |
| P0, P1 | — | Copy the untracked Case A and B files into the worktree; CTest build and `uv run --group validate` commands. |
| P2 | v mapping "the same" | u, v and w mappings written out; `u0` captured at the `"solid_mask"` stage; registration in CMake. |
| Section 6 | `PROVENANCE.md`; "hazard 9 … the spectral limiter contract" | `src/qes_core/PROVENANCE.md`; hazard 9 is the ground gradient (F6) and hazard 14 the stress validity (F5). |

## 11. Implementation corrections (revision 6)

- Finding 15 overlooked a later overwrite of `WGD->z0` by building-wall
  roughness. F6 now retains the profile roughness in `groundRoughness` and
  refreshes it for each profile; wall and roof behaviour is preserved.
- F6's all-layer analytic 2% target was incompatible with retaining central
  differences above layer two (about 5.7% gradient bias at z=5 m on the 2 m
  grid). The manufactured test uses the exact shifted-log derivative in the
  corrected two layers and the unchanged discretized derivative elsewhere.
- D2's benchmark tie-break selected V1; no runtime direction variant ships.
- Current audited fixtures are separately labelled embedded schema-2 snapshots.
  Historical standalone upstream/audited fixtures are preserved, with independent
  manufactured tests establishing the new physics checks.

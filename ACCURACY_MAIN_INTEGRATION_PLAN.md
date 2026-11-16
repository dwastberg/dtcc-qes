# Plan: bringing the accuracy work into `main`

**Date:** 2026-11-15. **Base:** `main` `c9dd6d5` (0.1.0b5 plus the Case C validation). **Sources:** [ACCURACY_IMPROVEMENT_PLAN.md](ACCURACY_IMPROVEMENT_PLAN.md) (revision 4), [validation/ACCURACY_DIAGNOSTICS.md](validation/ACCURACY_DIAGNOSTICS.md), [validation/ACCURACY_RESULTS.md](validation/ACCURACY_RESULTS.md). **Status:** done and merged into `main` (section 0).

## 0. Status (2026-11-16)

| Step | State |
|---|---|
| 1 Record and tooling | Done, commit `5259f62` |
| 2 Angle fade | Done: `Parameterizations.angle_fade`; 16 tests; sweep values reproduced exactly |
| 3 Shelter and tall-building zone | Done: `Parameterizations.tall_buildings`; 9 tests; bit-identical to the prototype on 37 runs |
| 4 Validation and release | Done: 184 default runs bit-identical to 0.1.0b5 on both grids; options reproduce the reference values; 0.1.0b6; 2,299 tests pass |
| Native tests | Serial 66/66, OpenMP 69/69; sanitizers 68/69 with a failure that predates this work (`stop_rule`, also on `c9dd6d5`) |
| Merge into `main` | Done 2026-11-16, fast-forward; `exp/accuracy-prototypes` deleted |

Record of the port: [validation/ACCURACY_RESULTS.md](validation/ACCURACY_RESULTS.md), section 9.

**Deviations from the steps below.**

- Steps 2 to 4 are one commit, not three series: the two options touch the same plumbing files.
- The policy compatibility check was not run.
- The options have named validation campaigns; `run_full_validation.py` stays a defaults-only run.
- Step 1 item 3 is done in a reduced form: a variant is stored in its own directory under its parent's key.
- The experiment branch was deleted after the port was verified against it; `validation/accuracy_evidence/exp-accuracy-prototypes.patch` keeps it reproducible.

---

**What existed before step 1.** Prototypes on the branch `exp/accuracy-prototypes` (worktree `/private/tmp/dtcc-qes-accuracy`, uncommitted), switched by environment variables. The diff is `validation/accuracy_evidence/exp-accuracy-prototypes.patch`. Before step 1 the scripts were in `experiments/accuracy/`, which git ignores. Three documents and one evidence folder are untracked in `main`.

---

## 1. What should go into `main`

| # | Item | Go in? | Reason |
|---|---|---|---|
| 1 | Diagnostics, results, plans and the evidence folder | **Yes** | They are the record of what was measured, including the negative results. |
| 2 | Scoring protocol (scorer, tower contract, data matching, tests) | **Yes**, moved into `validation/` | Every later model change needs the same paired intervals, shrinkage comparators and tower table. In `experiments/` it is untracked. |
| 3 | Angle fade of the sidewall and upwind-cavity zones (M) | **Yes**, opt-in | Passed its gate. Halves the largest direction step; no case gets worse. |
| 4 | Root-sum-of-squares shelter with the tall-building zone (S + D, split variant) | **Yes**, opt-in, as **one** option | Accepted as a scalar-speed model. S alone makes the after state near towers worse, so the two must not be separable. |
| 5 | Version string fix (`__init__.py` says 0.1.0b4) | **Yes** | One line; found on the way. |
| 6 | Stop-rule stall of `wake=3` on Case C at 1 m | **Record only** | A defect of the velocity stop rule at the float32 floor. It belongs to the stop-rule work, not to this batch. |
| 7 | Mixing step, reach cut, spread constant, the two rejected zone variants, all `QES_EXP_*` switches | **No** | Closed, inert or rejected. The patch in the evidence folder keeps them reproducible. |
| 8 | Any change of a default | **No** | Needs unseen towers (plan section 7.6) and the `wake=3` default decision. |

### 1.1 What the two model options deliver

`wake=3` scalar speed, 2 m grid (Case C at 1 m):

| Measure | Released `wake=3` | With both options | Measured |
|---|---|---|---|
| Largest direction step of the 2 m plane, one building | 0.032 | 0.015 | |
| Case E before, error within 30 m of the tower site | +0.176 | +0.093 | |
| Case E before, q / MAE | 0.327 / 0.145 | 0.450 / 0.105 | |
| Case E, change within 30 m when the tower is built | +0.024 | +0.227 | +0.262 |
| Case E after, q / R / MAE | 0.462 / 0.559 / 0.133 | 0.452 / 0.666 / 0.134 | |
| Case D thermistors, q / bias / MAE | 0.414 / −0.120 / 0.152 | 0.515 / −0.033 / 0.131 | |
| Case C, 1H → 2H within 15 m | +0.074 | +0.173 | +0.194 |
| Cases A and B; Case C 0H and 1H under the tall-building zone | | bit-identical | |

**Stable under ±25 % on every constant** (speed ratios, reach, the mean-flow share, the eligibility ramp): the Case E change stays between +0.17 and +0.29, and every variant keeps the gains in E before, E after and Case D.

### 1.2 Known limits that ship with it

These go into the documentation of the option, not into a footnote.

1. **Mean flow direction near towers is wrong.** At the 29 Case D points where the direction is measured and resolved, sign errors of the streamwise component rise from 5 to 10, and the vector error rises by 0.086. The option is a scalar-speed model. It should not be used for the mean vector near a tall building.
2. **No independent test.** Cases D and E were scored for three variants of the zone. The constants are from the literature and were not fitted, but the choice between variants was made on these cases.
3. **Downwind of the tower the rise is short** (+0.09 against +0.25 measured in Case E).
4. **The nearest 15 m** (8 probes in Case E) are still off by +0.14 before and +0.12 after construction.
5. **The speed ratios are in metres.** Reiter's curves are a function of building height at full scale. A model-scale geometry gives wrong ratios.
6. **Sectors use the building centroid.** For a long slab the corner position is approximate.
7. **The shelter rule saturates.** In dense synthetic arrays the deficit reaches 1.0 in places.
8. **The zone is active for any eligible building**, including existing ones (Case E before construction: one probe changes by 0.39, mean levels unchanged).

---

## 2. Proposed user interface

Two new fields of `wind.Parameterizations`, both off by default, both outside `pedestrian-v1`:

| Field | Type, default | Meaning | Requires |
|---|---|---|---|
| `angle_fade` | float, degrees, default `0.0` | Half-width of the ramp that replaces the ±10° switch of the sidewall and upwind-cavity zones. `2.5` is the validated value. | – |
| `tall_buildings` | int, default `0`; `1` on | Root-sum-of-squares shelter and the tall-building zone, together. | `wake=3` |

- **One switch for S and D.** There is no way to turn on the shelter rule alone.
- **Constants are not user settings.** They live beside the `wake=3` constants in `wake_model.h` (ratios table, reach 0.75 H, eligibility 1.5–2.5, mean-flow share 0.8).
- **Result.** `result.wake.tke` already carries the turbulence of `wake=3`; the turbulent share of the zone is added there, so `result.scalar_speed()` and the validation quantity `K_scalar_wake_rule` need no change.
- **Open naming question** (section 6): `tall_buildings` against a new wake code 4.

---

## 3. Order of work

Four steps, each a separate commit series on one feature branch from `main`, each leaving the default behaviour bit-identical. The order puts the certain items first.

### Step 1: record and tooling (no native code)

1. Commit the three documents, this plan and `validation/accuracy_evidence/`.
2. Move the reusable scripts from `experiments/accuracy/` to `validation/accuracy/`: `score.py`, `data.py`, `tower.py`, `planes.py`, `features.py`, `common.py`, `layouts.py`, `sweep.py`, `compare_variant.py`, `test_score.py`. Leave the one-off diagnostics (`part_t.py`, `i3.py`, `i4.py`, `s_*.py`, `d_*.py`) in `experiments/`; the evidence folder holds their output.
3. Replace the experiment-build mechanism in `common.py` (run tags and `QES_EXP_*`) by run specifications that carry the new `Parameterizations` fields, so that a variant has its own run key. This is done with steps 2 and 3, when the fields exist; until then `experiments/accuracy/exp` runs a script against the experiment build.
4. Fix the version string.

**Check:** `validation/tests` and the four scorer tests pass; no file under `src/` changes.

### Step 2: angle fade (M)

**Reference values for the port** (prototype, `QES_EXP_ANGLE_FADE=2.5`):

| Check | Value to reproduce |
|---|---|
| Sweep, 2 m: largest / median plane RMS ΔK per degree | 0.0154 / 0.0061 (parent 0.0321 / 0.0059) |
| Sweep, building turned 30° | 0.0108 (parent 0.0268) |
| Sweep, 1 m | 0.0138 (parent 0.0325) |
| A, B, C, D | Identical to the parent |
| E before / after, ΔMAE | −0.0001 / −0.0001 |

1. Port the weight into `Sidewall.cpp` and `UpwindCavity.cpp` as in the patch, reading the half-width from the model settings.
2. Plumb `angle_fade` through `parameterizations.py`, `bindings.cpp`, `wind_config.h`, `model_inputs.cpp` and `WindModelInputs.h`. A non-zero value makes an adaptive run `unqualified_model_settings` (`pedestrian_policy.cpp`).
3. Tests:
   - `angle_fade=0` is bit-identical to the released build (already shown on 5 runs; make it a native test).
   - A building aligned with the wind is unchanged at any half-width.
   - The 1° sweep as a regression test: largest plane step ≤ 0.016 at 2.5°. This is the test `FABEL_WAKE_INVESTIGATION.md` 7 asked for.
4. Document in `docs/` and the changelog.

**Check:** the M gate of the plan, rerun on the ported code: sweep at 2 m, turned building, 1 m; do-no-harm on A–E.

### Step 3: shelter and tall-building zone (S + D)

**Reference values for the port** (prototype, `QES_EXP_WAKE_RULE=1 QES_EXP_DOWNWASH=3`, run tag `s-d3`; with the fade, tag `all`): the table of section 1.1, and at 1 m: E before error within 30 m +0.095, E change +0.230, E after R 0.662, Case D bias −0.037 and MAE 0.133. Evidence: `validation/accuracy_evidence/d_split.md`, `d_sensitivity.md`, `combined_run.md`.

1. `SpreadingWake::accumulate`: the root-sum-of-squares rule under the new setting. The roof-speed field keeps the maximum.
2. `Downwash.cpp` becomes a proper stage:
   - Keep only the split variant; remove the two rejected modes and the sensitivity switches.
   - Call it from `applyParametrizations` as a named stage after the solid mask, so that stage observers and captures see it, instead of from `wind_runner.cpp`.
   - Move the constants to `wake_model.h`.
3. The turbulent share: keep it after the solve, where the mean flow is known, but in one function beside `wake_fields`, and cover the float64 path.
4. Plumb `tall_buildings` as in step 2; reject it without `wake=3`.
5. Tests:
   - Off: bit-identical to the released build.
   - On: isolated building, equal-height array and tandem cubes bit-identical to `wake=3` with the shelter rule only.
   - Mirror symmetry and divergence on the 5 × 5 array with a tower.
   - Deficit ≤ 1 and non-decreasing with added upwind rows.
   - A numeric regression on Case C 2H (the 1H → 2H change).
6. Documentation: a section in `docs/spreading-wake.md` with the constants, their sources and the eight limits of section 1.2.

**Check:** native code against the prototype on identical inputs (initial field, wake fields, solved field), then the S and D gate tables of `ACCURACY_RESULTS.md` rerun on the ported code. The numbers must reproduce; they are not re-judged.

### Step 4: validation and release

1. Add campaigns for the two options to the validation runner (D, E at 2 m and 1 m; A, B; C at 1 m and 2 m) and to `run_full_validation.py`.
2. Run the full validation once. Two gates:
   - **Defaults unchanged:** every default run is bit-identical to the 0.1.0b5 archive.
   - **Options reproduce** the tables of section 1.1.
3. Update `validation/AIJ_VALIDATION.md`, the changelog and the version (0.1.0b6).
4. Native edits change the policy identity: run `check_policy_compatibility.py` and record the new identity. The build stays unqualified for `pedestrian-v1`, as 0.1.0b5 is.

---

## 4. Effort

| Step | Rough effort | Risk |
|---|---|---|
| 1 Record and tooling | half a day | Low |
| 2 Angle fade | 1 day | Low: small, passed, already bit-identical when off |
| 3 Shelter and tall-building zone | 2–3 days | Medium: the stage placement and the post-solve turbulence are new code paths |
| 4 Validation and release | 1 day, plus run time | Low |

Case C at 1 m with `wake=3` takes about 200 s per run because of the stop-rule stall; nine runs per variant. Fixing the stall first would shorten step 4, but it is separate work.

---

## 5. What stays open after this batch

1. **Unseen towers.** No default changes before the option is tested on tall-building data that was not used here (H02, H03, H09 of the earlier plans).
2. **Mean flow near towers.** The literature gives no direction rule. A fix needs vector data around a tall building in a fabric, or a reference simulation.
3. **The 0–15 m bin and the downwind sector** of Case E.
4. **The cavity edge.** The remaining step at a point probe in the direction sweep (0.069) is a spatial edge of the near-wake cavity. It is the candidate for a later blend at source.
5. **Aligned streets.** The model channels along streets where the measurement is flat. The shelter rule removes the level error but not the pattern (R in E before falls by 0.02).
6. **Case C inflow turbulence.** The rule value is probably 1.3–2 times the measured one; the scalar proxy of the undisturbed inflow is 1.10 where the measurement is 1.00.
7. **Stop-rule stall** (item 6 of section 1).

---

## 6. Decisions needed before starting

**Decided 2026-11-15:** all five as recommended: one option; named `tall_buildings`; both options in this batch; the scorer moves to `validation/accuracy/`; the experiment branch is committed once and not merged. It is deleted after the port is verified in step 3.

| # | Question | Recommendation |
|---|---|---|
| 1 | One option for S and D, or two? | One. S alone is worse near towers. |
| 2 | Name: `tall_buildings=1`, or a new wake code `wake=4`? | `tall_buildings=1`. It leaves the QES wake codes alone and says what it does; a wake code would hide that it also changes the superposition rule. |
| 3 | Ship the tall-building option in this batch, or the angle fade first and the rest after unseen-tower data? | Both in this batch, as opt-in. The scalar gain is large and stable, and the limits are documented. Holding it back does not produce the missing data. |
| 4 | Move the scorer into `validation/accuracy/`? | Yes. |
| 5 | Commit the experiment branch as it is, for the record? | Yes, one commit on `exp/accuracy-prototypes`, not merged. The patch in the evidence folder is the fallback. |

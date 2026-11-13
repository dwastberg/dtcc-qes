# Bring the stop rule and the spreading wake into main

- **Date:** 2026-11-12.
- **Goal:** merge the two finished feature branches into `main`, each with the qualification evidence the repository requires, without disturbing the research work in the main checkout.
- **Status:** done (2026-11-13). Parts A and B are complete, with D1–D5 as recommended, except D5 for the wake worktree (section 8). `main` is at `62a40ac`, version 0.1.0b3, native identity `bf48ef3f…`, qualified and supported. Nothing has been pushed (D4).

## 1. Scope

| Branch | What it brings | State |
|---|---|---|
| `feat/solver-stop-rule` (`d1466dd`, 14 commits on `main` `d968aa7`) | Velocity-estimate and fixed-work stop rules, `relaxation` including `"grid"`, and the **default switch**: `Solver()` now stops on the velocity estimate. Includes the study harness, the evidence and the docs. | Complete (`SOLVER_STOP_RULE.md` P1–P7). Native identity `1319a43d…` qualified and promoted. G1–G6 passed. |
| `feat/wake-update-v2` (`209ce15`, 14 commits on `33f743f`) | Opt-in `wake=3` (spreading far wake and wake turbulence), `scalar_speed`, `comfort.assess_results(speed="scalar")`, and the `canyon_factor` fix for exposed faces, which applies to the default `wake=2`. | W1–W5 done, W6 (default switch) declined pending a policy study. Native identity `6e072763…` qualified against `33f743f`. |

**Not in scope:**
- `research/pedestrian-wind-campaign`, the current checkout. It holds uncommitted changes to `comfort.py`, the docs and the examples, plus untracked plans.
- `research/unified-wind-turbulence`.
- The open follow-ups of either branch: the wake=3 policy study, `WAKE3_COMFORT_DEFAULT_PLAN.md`, and 0.5 m validation of the stop rule.

## 2. Findings

1. **The stop rule merges without conflicts and needs no new qualification.** Its base is `main`'s tip, so a `--no-ff` merge produces exactly the tree that was tested. Its re-qualification (`docs/data/solver-stop-rule/requalification*.json`) was made against `d968aa7`, which is `main`.
2. **The wake branch is two commits behind `main`** (`4d7e975`, prepared wind reuse). Merging `main` into it conflicts only in `src/dtcc_qes/wind.py` `__all__`, where one side adds `prepare`/`PreparedWindModel` and the other `WakeFields`.
3. **The two branches overlap in 13 files.** A trial merge (`git merge-tree`) leaves three conflicts:
   - `wind.py` `__all__`: take the union.
   - `src/qes_core/PROVENANCE.md`: keep both entries.
   - `pedestrian_qualification.h`: both promote a different identity from `04c8ce…`.

   The other ten files merge cleanly.
4. **The combined native sources have a third identity.** Neither `1319a43d…` nor `6e072763…` describes them, so after the second merge adaptive acceptance stays off until that identity is re-qualified. The wake's evidence was also made against `33f743f`, not the current `main`. One re-qualification of the combined identity, against `main` after the first merge, settles both.
5. **The stop rule's default switch changes the meaning of the wake branch's tests.**
   - `tests/test_wake_v3.py`, `test_parameterizations.py` and `test_building_contacts.py` call `Solver(max_iterations=N)` five times, assuming N fixed multiplier sweeps. For example, the sweep test chose 400 because the result matched 3,000.
   - Under the new default these become velocity-rule solves capped at N. They need `stop="multiplier_change"`, the same treatment as the tests pinned in `06b2e7d`.
   - The wake branch's tools and AIJ campaigns are unaffected. Its `compare_native_builds.py` cases are native-level, and the AIJ runner now passes the rule explicitly.
6. **The wake branch is itself a declared change to default outputs.** The W1b `canyon_factor` fix changes 22 records in the exposed slab-gap and courtyard cases (W1b gate met). The combined comparison against `main` must show exactly that set and nothing else.
7. **The main checkout is busy.** It is on the research branch with uncommitted work and untracked copies of `SOLVER_STOP_RULE.md` and `WAKE_UPDATE_V2.md`. Both become tracked files on `main`, so the untracked copies would block a later `git checkout main`. All merging should happen in a separate worktree of `main`.
8. **Other repository facts:**
   - `main` is 15 commits ahead of `origin/main` and has not been pushed.
   - The version has been `0.1.0b1` since the initial commit, and the repository has no changelog.
9. **Evidence is small:**
   - stop rule: 477 KB in 15 files
   - wake: 33 KB
10. **Re-qualification needs about 10 GB of scratch space and untracked data.**
    - The run's own builds take about 12 GB; delete each stage's builds after it is recorded.
    - The AIJ Case A and B tables (`validation/AIJ_A`, `AIJ_B`) are untracked and must be copied into any worktree that runs the AIJ checks.

## 3. Decisions

| # | Question | Recommendation |
|---|---|---|
| D1 | Order | **Stop rule first, then wake.** The stop rule is complete and merges with no new qualification. The wake branch must be re-qualified against the new `main` in any case (finding 4). Merging both in one step would save one bitwise comparison (about 2 minutes), but would tie a finished change to a branch whose follow-ups are still open. |
| D2 | Merge the wake branch now, as opt-in, or wait for its W6 policy study? | **Now, as opt-in.** Its gates passed and its default (`wake=2` plus the `canyon_factor` fix) is declared and validated. Every further change to `main` costs it another re-qualification. Switching to `wake=3` stays a separate declared change. |
| D3 | Version | **Bump to `0.1.0b2`** with the stop-rule merge. The default solver's results change, and consumers (the `qes_wind` dataset, downstream apps) can then tell the two apart. Bump to `0.1.0b3` with the wake merge, since it changes the default wake fields. |
| D4 | Push `origin/main` | Your call. It is not part of this plan's steps, and `main` is already 15 commits ahead. |
| D5 | Delete the merged branches and their `/private/tmp` worktrees | **Yes, after each merge passes its post-merge check.** The stop-rule worktree holds 2.6 GB, the wake worktree 25 GB. The branches' commits stay reachable from `main`. Keep `build/fabel-wake` in the main checkout, as previously requested. |

## 4. Steps

All work happens in a fresh worktree of `main` (`/private/tmp/dtcc-qes-main-integration`), never in the main checkout.

### Part A: the stop rule

- **A1. Prepare the branch.** On `feat/solver-stop-rule`:
  - Add an [API migration](README.md#api-migration) row for the default change: former behaviour `Solver(stop="multiplier_change")`.
  - Mark `SOLVER_STOP_RULE.md` as merged.
  - Bump the version (D3).

  Python and docs only, so the native identity is unchanged.
- **A2. Merge.**
  - `git merge --no-ff feat/solver-stop-rule` into `main` in the worktree.
  - Verify that `git diff feat/solver-stop-rule main` is empty: the tested tree is the merged tree.
- **A3. Post-merge check on `main`.** The precedent is `a833c4d`, "post-merge reference qualification on main".
  - Fresh Release build; the extension reports `1319a43d…` as supported.
  - Native CTest (OpenMP and serial).
  - `pytest -W error`, and the validation tests.
  - The wheel smoke with a 4-thread team.

  About 10 minutes. Record the result in `validation/SOLVER_STOP_RULE_RESULTS.md` and commit it on `main`.
- **A4. Tidy.**
  - Remove the untracked `SOLVER_STOP_RULE.md` copy from the main checkout, after checking that it matches the tracked file.
  - Delete the stop-rule worktree and branch (D5).

### Part B: the spreading wake

- **B1. Bring the branch up to date.** Merge the new `main` into `feat/wake-update-v2` in its worktree:
  - `wind.py` `__all__`: take the union.
  - `PROVENANCE.md`: keep both entries, the stop rule's first.
  - `pedestrian_qualification.h`: keep `main`'s `1319a43d…` for now. The build is unqualified until B4, as for any native edit.
- **B2. Adapt to the new default solver** (finding 5):
  - Pin `stop="multiplier_change"` in the five wake test solves that assume fixed sweeps.
  - Check the wake docs (`docs/spreading-wake.md`, the README wake section, `docs/wind-comfort.md`) for statements about default sweeps.
  - Run native CTest, `pytest -W error` and the validation tests.
- **B3. Confirm the wake's validation still holds on the merged code.** Rerun:
  - its W4 gate campaigns (`wake3`, `ab_wake3`; `validation/run_wake_validation.py`);
  - the stop rule's G6 (`stop_rule_g6`).

  Expected: unchanged. The harness pins the multiplier rule, and the stop rule leaves `wake=2` fields alone. G6 now runs on the `canyon_factor` fix, so its fixed-work side changes in the W1b cases only, and the gate compares default against fixed work on the same code. About 15 minutes.
- **B4. Re-qualify the combined identity.** Run the full `docs/solver-control-requalification.md` procedure against `main` after A2, using the driver from P5. The only declared differences are the W1b exposed-face records; everything else must match bitwise.
  - S7: 24 workers.
  - Combined baseline, non-adaptive and adaptive.
  - `pytest -W error` on both isolated packages.
  - sdist and wheel; artifact checks; wheel smoke with a 4-thread team.

  Then promote the new identity, add a PROVENANCE entry, store the evidence under `docs/data/wake-update-v2/`, and bump the version (D3). About 30 minutes; remove the build directories after each stage.
- **B5. Merge and check.**
  - `git merge --no-ff feat/wake-update-v2` into `main`, then verify that the tree equals the qualified branch.
  - Post-merge check as in A3.
  - Tidy as in A4: the `WAKE_UPDATE_V2.md` copy, and the 25 GB worktree.

## 5. Gates

| Gate | Pass when |
|---|---|
| M1 Tested tree | After each merge, `main`'s tree equals the branch tree that was qualified (`git diff` empty). |
| M2 Post-merge | On `main`, after each merge: the extension reports its identity as supported; CTest, `pytest -W error`, validation tests and the 4-thread wheel smoke pass. |
| M3 Declared differences only | The combined identity's comparison against `main` after A2 differs only in the W1b records. All 24 S7 workers and the combined baseline match exactly. |
| M4 Validation unchanged | After B1–B2, the wake W4 gates still pass and the stop rule's G6 still holds (pooled-score changes ≤ 0.01). |

## 6. Risks

- **The combined comparison shows differences outside W1b.**
  - Cause: an unexpected interaction between the wake's native edits and the stop rule's runner changes.
  - Response: stop before B4's promotion. The stop rule is already on `main` and unaffected.
- **Wake tests calibrated on fixed sweeps fail after pinning.**
  - This would mean they relied on something else that changed.
  - Response: diagnose before adjusting thresholds; thresholds are not loosened without a recorded reason.
- **Consumers notice the default change.**
  - It is declared in `SOLVER_STOP_RULE.md` section 6a, in `docs/solver-control.md` ("Differences from the former default") and in the README.
  - `Solver(stop="multiplier_change")` restores the former behaviour exactly.
- **Disk.** About 26 GB is free now; B4 needs about 12 GB at its peak. Delete the stop-rule worktree (A4) before B4.

## 7. Effort

| Part | Hands-on work | Compute | Main cost |
|---|---|---|---|
| A | 30 minutes | about 10 minutes | |
| B | 1–2 hours | about 1 hour | conflict resolution, the five test pins, and the re-qualification |

## 8. Outcome

| Step | Commit on `main` | Result |
|---|---|---|
| A1–A2 | `3c80254` (merge), `5e65fa9` (0.1.0b2) | The merged tree equals the qualified branch tree (M1). |
| A3 | `b374dfb` | Post-merge check passed (M2): identity `1319a43d…` supported; CTest 62/62 and 59/59; `pytest -W error` 2,016; validation 160; artifacts; wheel smoke. |
| B1 | `2058682` | Three conflicts, as predicted: `__all__` union, `PROVENANCE.md` both entries, header. |
| B2 | `0f80df8` | Five wake test solves pinned to the multiplier rule. The suite had also passed without the pins. |
| B3 | `11582db` | M4: the W4 gate values equal the branch's own; G6 passes (0.0053). `wake=3` takes 200–225 sweeps per Case E direction under the default solver, against 150–175 for `wake=2`. |
| B4 | `640dd5e` (0.1.0b3), `11582db` | Combined identity `bf48ef3f…` re-qualified (M3), with every stage passed. |
| B5 | `baeca7f` (merge), `62a40ac` | M1 and M2 passed: CTest 63/63 and 60/60; `pytest -W error` 2,032; validation 186; artifacts; wheel smoke. |

**M3 in detail.** The differences from `main` are:
- the 22 declared W1b records;
- 23 `metadata/versions` records, which differ only in the package version. I bumped it before the comparison; all 115 values were checked.

The combined baseline differs only in that version and the declared identity pair. All 436 arrays are bitwise identical.

**Deviations from the plan:**
- The wake work ran on a new branch, `integrate/wake-update-v2`, now merged and deleted, rather than in `feat/wake-update-v2`'s worktree. That worktree holds uncommitted edits to `WAKE_UPDATE_V2.md` and `WAKE3_COMFORT_DEFAULT_PLAN.md` and an untracked `WAKE3_COMFORT_DEFAULT_PLAN_REVIEW.md` from 2026-11-12 13:35. So it and `feat/wake-update-v2` are kept, and those edits still need to be carried onto `main` by whoever owns them.
- `WAKE_UPDATE_V2.md` on `main` was not edited for the merge, to avoid conflicting with them. The merge is recorded in `validation/WAKE_UPDATE_V2_RESULTS.md`.

**Housekeeping:**
- Removed:
  - the stop-rule and integration worktrees;
  - the `feat/solver-stop-rule` and `integrate/wake-update-v2` branches;
  - the untracked `SOLVER_STOP_RULE.md` copy in the main checkout, an older copy of the merged file.
- Copied into this checkout's `validation/output/runs` by key, without overwriting, so it stays reusable: the raw E1, G6 and W4 run records (420 files).
- Left in place: the untracked `WAKE_UPDATE_V2.md` (an 11 November draft that differs from `main`) and `UNIFIED_CAMPAGNE_PLAN_V2.md`. They will block `git checkout main` here until moved.

**Follow-up (2026-11-13).** Merged after this plan:
- release blocker R1, the sdist without the qualification evidence (`7bf2115`, 21.6 MB instead of 1.4 GB);
- the footprint reference-point fix (`3cbe316`, version 0.1.0b4, identity `31f6d956…`; `FOOTPRINT_REFERENCE_POINT.md`).

Release notes are in `CHANGELOG.md`.

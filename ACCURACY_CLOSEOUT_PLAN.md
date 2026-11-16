# Plan: closing the accuracy task

**Date:** 2026-11-16. **State reviewed:** `main` = `origin/main` = `7008159` (pushed), plus the uncommitted working tree as of 15:00.

## Progress (2026-11-16)

Decisions of section 4: 1, 2, 3, 4 and 6 as recommended; **no push** (the user pushes after review).

| Step | State |
|---|---|
| 2 Wind-comfort follow-ups | Committed, `613db74` |
| 3 Stall fix, its evidence and the investigation record; duplicate fixture deleted (A3) | Committed, `1bf644f` |
| 4 Checks B1 and B2 | Done: `tall_buildings=1` alone is bit-identical to the combination on Case C; after the stall fix the Case C probes move by at most 6e‑5 m/s and the score table is identical to four decimals |
| 5 A4, A5, A6, B3, B4 | Done in the records commit: closing status in the three accuracy documents, `END_TO_END_REVIEW.md` committed, run cache documented as a research tool, the broken helper deleted |
| 6 Release 0.1.0b7 | See the release commit |
| 8 Housekeeping H1–H4 | After the release |

**The overall task**, from the request to review the accuracy plan to now:

1. The accuracy plan ([ACCURACY_IMPROVEMENT_PLAN.md](ACCURACY_IMPROVEMENT_PLAN.md)): diagnostics, then the parts M, S and D.
2. The port to `main` ([ACCURACY_MAIN_INTEGRATION_PLAN.md](ACCURACY_MAIN_INTEGRATION_PLAN.md)): released as 0.1.0b6.
3. The two solver problems found on the way ([STOP_RULE_STALL_INVESTIGATION.md](STOP_RULE_STALL_INVESTIGATION.md)): the `stop_rule` sanitizer failure, and the velocity-rule stall.

This plan lists every question still open across the three, says which block closing and which do not, and gives the order of work to close.

---

## 1. Where things stand

| Piece | State |
|---|---|
| Diagnostics, scorer, evidence | Committed (`5259f62`) |
| `angle_fade` and `tall_buildings`, 0.1.0b6 | Committed and pushed (`c706f46`, `2ba9a47`); native tests 66/66 and 69/69 |
| `stop_rule` sanitizer failure | Fixed and pushed (`807e1e0`) |
| Stall of the velocity rule | Fix implemented and **fully validated**, **not committed**. Results: `docs/PRECISION_STAGNATION_RESULTS.md`. All 70 numerical cases pass at most 1e‑3 U_ref; native 69/69, 66/66, sanitizers 66/66; Python 2,174 per backend; packaging audits pass; exact parity with `7008159` |
| Demo history for the stagnation test | Moved to `tests/fixtures/reference/stop-rule/` and staged |
| Wind-comfort follow-ups | Uncommitted, separate from this task (see 2.1, item A1) |

---

## 2. Open questions

### 2.1 Blocking: must be done to close

| # | Item | Evidence | Proposed resolution | Decision needed |
|---|---|---|---|---|
| A1 | **The working tree mixes three pieces of work.** (a) The stagnation fix with its tests, tools, evidence and results document. (b) Wind-comfort follow-ups: the `max_cells` default falls from 200 M to 50 M cells, a non-converged direction now warns instead of aborting, and the README test is made offline and headless. (c) My document edits (`ACCURACY_MAIN_INTEGRATION_PLAN.md`, `STOP_RULE_STALL_INVESTIGATION.md`). | `git status`; the results document says the full-suite work "repaired the README test" and "aligned the cell-limit assertion with the pre-existing 50-million-cell default" | Three commits: (b) first, because the stagnation evidence was produced with it in the tree; then (a) together with the investigation record and the fixture move; then (c) with the document updates of A4. | Who commits (b) and (a): another session produced them |
| A2 | **Version and changelog of the stagnation fix.** It changes default results for runs that would otherwise stall (by at most 1.3e‑4 U_ref in the validation) and gives a new native identity (`df09ee9d…`). The changelog has it under "Unreleased", and the 0.1.0b6 entry still says "Known, not fixed: … stall". | `CHANGELOG.md` lines 7–37 | Release as **0.1.0b7** with the identity, and change the 0.1.0b6 line to point to the fix. Check that the 0.1.0b6 entry still describes what shipped: the wind-comfort dataset was added to it after the release commit, and the `max_cells` change in (b) alters a documented default. | Release now as 0.1.0b7, or keep "Unreleased" |
| A3 | **Duplicate fixture.** `docs/data/precision-stagnation/baseline-demo-float32.json` is identical to the staged test fixture, and nothing reads it. Its folder is whitelisted, so it would be committed twice. | `cmp`; `grep` | Delete it before commit (a). | – |
| A4 | **Documents out of step with the final state.** (1) `ACCURACY_IMPROVEMENT_PLAN.md` section 0 still lists D as "to be decided" and the parts as prototypes. (2) `validation/ACCURACY_RESULTS.md` section 6 says "Not done: the ±25 % sensitivities", which section 8 later did. (3) Its section 9 says the policy check was not run; the stagnation work has since run all 24 frozen workers on `7008159` (section 2.3, D1). (4) The integration plan's section 0 says "not merged". | Read in this review | Add a closing status to each, without rewriting their history: what shipped, in which commit, and a pointer to this plan. | – |
| A5 | **Broken link on the pushed `main`.** `ACCURACY_IMPROVEMENT_PLAN.md` links `END_TO_END_REVIEW.md`, which was never committed. | Link check | Commit `END_TO_END_REVIEW.md`. It is the source of findings K1–K3 and proposals M and D, and is cited throughout. | Commit it, or drop the link |
| A6 | **Results computed on stalled runs.** The Case C tables at 1 m (`wake=3` parent, the options) came from runs capped at 20,000 sweeps. With the fix they stop at about 2,000 sweeps. Fields change by at most 1.3e‑4 U_ref, below the third decimal of every table. | `docs/PRECISION_STAGNATION_RESULTS.md`; ACCURACY_DIAGNOSTICS section 2 | No rerun. Add one sentence to `ACCURACY_RESULTS.md` section 9: the stall fix leaves the reported values unchanged at their precision. Optional check in B2. | – |

### 2.2 Cheap checks that remove doubt (not strictly blocking)

| # | Item | Proposed resolution | Cost |
|---|---|---|---|
| B1 | **`tall_buildings=1` alone on Case C** was not run on the final build; the combination with the fade was. The fade leaves every Case C run identical, so the two must agree. | Run the 9 Case C runs at 1 m on the stagnation build and confirm identity with the combination. | About 3 min now that the stall is fixed (it was 30 min) |
| B2 | **Reference values after the stall fix.** | Re-score the Case C and headline tables of `ACCURACY_RESULTS.md` sections 8–9 on the stagnation build; expect agreement to three decimals. | About 15 min |
| B3 | **The run cache in `validation/accuracy/common.py`** still stores a variant under its parent's key in its own folder (`ACC_TAG`, `ACC_PARAMS`). The options are now ordinary `Parameterizations` fields with their own campaigns and run keys. | Simplify it to use the campaigns' run specifications, or document it as a research tool. | Half an hour |
| B4 | **`experiments/accuracy/exp`** ran scripts against the deleted experiment build. It is git-ignored and now broken. | Delete it; the patch in `validation/accuracy_evidence/` keeps the prototype reproducible. | Minutes |

### 2.3 Not blocking: separate follow-ups, recorded and handed over

| # | Item | Status and evidence | Owner or condition |
|---|---|---|---|
| D1 | **`pedestrian-v1` requalification.** The last qualified build is `fe2dcd3` (`31f6d956…`). Since then 659 records differ per backend and team, and 3 of the 24 frozen S7 workers fail (`release-online-02`, `-09`, `-20`; `val_mixed_195`). This predates this task, and the stagnation fix leaves it unchanged. | `docs/PRECISION_STAGNATION_RESULTS.md`, requalification section | Separate qualification work. Until then every release says, as 0.1.0b5 and 0.1.0b6 do, that `pedestrian-v1` is unqualified. |
| D2 | **No independent test of `tall_buildings`.** Cases D and E were used to choose between three variants. | `docs/tall-buildings.md`, limit 2 | Before any default change: unseen tall-building data (H02, H03, H09 in the earlier plans) |
| D3 | **Mean-flow direction near towers is wrong** (sign errors 5 → 10 of 29 at the Case D vector points). | `ACCURACY_RESULTS.md` 6.1 | Needs vector data around a tower in a fabric, or a reference simulation |
| D4 | **Remaining tower shortfalls:** the downwind sector (+0.09 against +0.25 measured) and the 0–15 m bin (+0.14 before, +0.12 after, 8 probes). | `ACCURACY_RESULTS.md` 6 | With D2 |
| D5 | **Cavity edge at point probes:** a step of 0.069 in K per degree remains at the side probe of the direction sweep. It is a spatial edge of the near-wake cavity. | `docs/angle-fade.md` | Candidate for a blend at source |
| D6 | **Aligned streets:** the model channels along streets where the measurement is flat. The shelter rule fixes the level, not the pattern. | `ACCURACY_DIAGNOSTICS.md` 7.2 | Research |
| D7 | **Case C inflow turbulence:** the rule value k = 5.5 u*² is 1.3–2 times the measured σ_u², so the scalar proxy of the undisturbed inflow is 1.10 where the measurement is 1.00. | `ACCURACY_DIAGNOSTICS.md` 4 | Validation setup |
| D8 | **Case C coverage:** no probe in the central plot, no far field, and the 0.5 m grid not run. | `ACCURACY_DIAGNOSTICS.md` 4 | Accept as a limit of the data |
| D9 | **Why `wake=3` slows the SOR contraction** (0.835 → 0.922 on Case C). It is harmless since the stall fix, but it costs sweeps. | `STOP_RULE_STALL_INVESTIGATION.md` 2 | Performance work, if wanted |
| D10 | **The `wake=3` default.** Still governed by C4 of `WAKE3_COMFORT_DEFAULT_PLAN.md`; the new options do not change that decision. | – | Together with D2 |

### 2.4 Housekeeping

| # | Item | Proposed resolution | Decision needed |
|---|---|---|---|
| H1 | Branch `feat/accuracy-options` is merged into `main`. | Delete it. | – |
| H2 | Worktrees `/private/tmp/dtcc-qes-physics-bugs` (`fix/physics-bugs` = `4c7a8da`, contained in `main`) and `/private/tmp/dtcc-qes-physics-f2-attribution` (detached) date from the bug-fix plan. | Remove them, and the merged branch `fix/physics-bugs`. | Yes: they predate this task |
| H3 | Disk: `build/precision-stagnation` 13 GB, `validation/output/accuracy` 2.1 GB, `build/native-*` 0.6 GB. All are rebuildable or summarized in committed evidence. | Delete `build/precision-stagnation` and `build/native-*` after the commits. Keep `validation/output/accuracy` until B1 and B2 are done, then delete or archive it. | Yes |
| H4 | Memory notes for this task. | Collapse into one closed record with pointers to the follow-ups. | – |

---

## 3. Order of work to close

| Step | Content | Depends on |
|---|---|---|
| 1 | Decisions of section 4 | – |
| 2 | Commit (b), the wind-comfort follow-ups, with a changelog line for the `max_cells` default | Decision 1 |
| 3 | Delete the duplicate fixture (A3). Commit (a): the stagnation fix, its tests, tools, evidence, results document, the fixture move and `STOP_RULE_STALL_INVESTIGATION.md` | Step 2 |
| 4 | B1 and B2 on the committed build | Step 3 |
| 5 | A4, A5, A6: closing status in the three accuracy documents; commit `END_TO_END_REVIEW.md` | Step 4 |
| 6 | A2: release 0.1.0b7. Changelog with the native identity; the 0.1.0b6 line corrected; version bump; full Python suite and native tests once more | Decision 2 |
| 7 | B3, B4 if wanted | – |
| 8 | Housekeeping H1–H4; push if wanted | Decisions 4, 5 |

After step 8 the task is closed. What remains is section 2.3, recorded as separate follow-ups.

---

## 4. Decisions needed

| # | Question | Recommendation |
|---|---|---|
| 1 | Who commits the stagnation fix and the wind-comfort follow-ups, which another session produced? | I commit them as two separate commits, using that session's documents as the commit text, once you confirm that session is done. |
| 2 | Release the stagnation fix as 0.1.0b7 now? | Yes. It fixes a real stall on default settings (the demo city at 1 m) and is fully validated. |
| 3 | Commit `END_TO_END_REVIEW.md`? | Yes, it is cited by committed plans. |
| 4 | Remove the old physics-bug-fix worktrees and branch, and the large build folders? | Yes, after step 6. |
| 5 | Push after step 6? | Your call; `main` is currently pushed. |
| 6 | Do B3 (run-cache simplification)? | Optional; I would leave it documented as a research tool. |

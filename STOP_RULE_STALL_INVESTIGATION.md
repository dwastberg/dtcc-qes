# Investigation: the `stop_rule` sanitizer failure and the `wake=3` stall on Case C

**Date:** 2026-11-16. **Base:** `main` `2ba9a47` (0.1.0b6). Both problems were found during the accuracy work ([ACCURACY_MAIN_INTEGRATION_PLAN.md](ACCURACY_MAIN_INTEGRATION_PLAN.md)); neither was caused by it.

## 0. Status (2026-11-16): what later work has fixed

Re-checked against `main` `7008159` and the uncommitted working tree.

| Item | Status | Where |
|---|---|---|
| 1. `stop_rule` sanitizer failure | **Fixed and committed** | `807e1e0` (with the wind-comfort dataset) contains the field-by-field comparison and `validation/replay_stop_rule.py` |
| 2. Stall of the velocity rule | **Fixed, validated and committed** together with this record | `PrecisionStagnation` in `src/qes_core/solver/solver.h`, wired into `check_estimate` in `solver.cpp`; results in [docs/PRECISION_STAGNATION_RESULTS.md](docs/PRECISION_STAGNATION_RESULTS.md) |

**The implemented rule** stops at `precision_floor` when the change has made no new minimum for 8 checks **and** the last 8 counted checks were all within 2 × the floor. It is stricter than the proposal in section 3, which asked only that the current check be within 2 × the floor. The estimate and two-check floor stops keep precedence; fixed work and the adaptive controller are unchanged. `stop_estimate` gains `stagnation_checks`, `stagnation_floor_factor` and `floor_trigger` (`stagnation`, `consecutive_checks` or null). The raw estimate is kept, and a stagnation stop does not claim the tolerance was met. Tests: a unit test of the tracker in `check_stop_rule.cpp`, a recorded plateau in `tests/test_solver_stop_rule.py`, a replay test in `tests/test_precision_stagnation.py`, and replay support in `validation/aij/stop_rule.py`. Declaration of the change and its acceptance gates: `docs/data/precision-stagnation/declaration.md`.

**Independent check of the replay.** On the 1,391 stored histories, the implemented rule and the proposal of section 3 give identical stops. 87 runs change, all Case C at 1 m with `wake=3`: the 84 capped ones, and 3 that had stopped on the estimate and now stop earlier. Section 3 said "no other run changes", which stays true for runs outside that group but left out those 3. New stops: median 1,975 sweeps, range 1,650–2,225. `docs/data/precision-stagnation/replay.json` reports the same.

**Correction to section 2: the stall is not limited to `wake=3` on Case C.** The demo city of the wind-comfort dataset stalls with the **default** settings (`wake=2`, 570 × 570 × 105 cells at 1 m). Its recorded float32 history (now `tests/fixtures/reference/stop-rule/wind-comfort-demo-float32.json`) ran to the 20,000-sweep cap; the implemented rule stops it at 1,050. In the validation campaign, 3 of the 16 demo directions at 1 m end on the stagnation trigger. This makes the fix matter for default users, not only for an experimental option.

**Validation result** (`docs/PRECISION_STAGNATION_RESULTS.md`). All 70 numerical cases pass at most 1e‑3 U_ref on every assessed fluid face against stable float64 references: 32 demo cases (3 stopped on stagnation, largest error 5.2e‑4) and 38 AIJ cases (24 on stagnation, largest 4.7e‑4). The E1 stop-rule study keeps its probe gates in all 98 runs × 5 tolerances. Native tests 69/69, 66/66 and 66/66 with sanitizers; Python 2,174 per backend; packaging audits pass; exact parity with `7008159` on 5,503 records per backend and team.

**Items found in this review, all resolved before commit:**

- The demo history the test replays was git-ignored. It is now `tests/fixtures/reference/stop-rule/wind-comfort-demo-float32.json`, and the test no longer needs `docs/data`. The duplicate copy in `docs/data/precision-stagnation/` is deleted.
- `docs/PRECISION_STAGNATION_RESULTS.md` now exists and is whitelisted with its evidence folder.
- The qualification identity mismatch predates this change: the last qualified build is `fe2dcd3` (`31f6d956…`), and builds since then differ in 659 records and in 3 of the 24 frozen workers. It is recorded as a separate follow-up in [ACCURACY_CLOSEOUT_PLAN.md](ACCURACY_CLOSEOUT_PLAN.md), item D1.

Sections 1 to 3 below are the original investigation, unchanged except where marked.

## 1. `stop_rule` fails in the sanitizer build

**Symptom.** In the Debug build with AddressSanitizer and UBSan, the native check `stop_rule` aborts with "Estimate depends on the thread team". It passes in the Release builds. It fails identically on `c9dd6d5`.

**Cause: the test, not the solver.** `thread_independent()` compares the estimate history of 1, 2 and 4 threads with `memcmp` over whole `EstimateCheck` structs. The struct is `int iteration` followed by four `double`s, so bytes 4–7 are padding. In the failing build all 24 differing bytes were at offset 4. Every field was identical across thread teams. The Release builds pass only because their padding happens to match.

**Fix (committed in `807e1e0`).** `tests/native/check_stop_rule.cpp` compares the fields: `iteration` by value, the doubles by their bits, so that NaN contractions stay comparable. It also checks that the histories have the same length. `stop_rule` now passes in the sanitizer, serial and OpenMP builds. No solver code changes.

## 2. `wake=3` on Case C at 1 m runs to the sweep cap

**Symptom.** Of 87 stored runs of Case C at 1 m with `wake=3`, 84 end at the 20,000-sweep cap instead of stopping on the velocity rule (about 200 s instead of 10 s). Every other stored combination of case, grid and wake setting stops normally (1,304 runs). *(Later finding, section 0: the demo city stalls with default settings too.)*

**What the rule does.** Every 25 sweeps it measures the largest change of the face velocity over the block, relative to the reference speed. It stops when either:

- the estimate 2·c·r/(1−r) of the remaining change is at or below the tolerance (1e‑3) at two counted checks in a row (c is the change, r the larger of the last two block ratios, clipped at 0.99); or
- the change itself is at or below the float32 floor, 6·ε·max|λ| / (smallest spacing · reference speed), at two counted checks in a row.

**What happens in Case C.**

1. **The float32 iteration reaches a noise plateau.** From about 1,000 sweeps the change is quantized in steps of about 1.6e‑6, the rounding step of the multiplier λ, and repeats exact values. It settles at 1.2–1.5 × the floor (median 1.26), so the floor rule never triggers.
2. **The estimate rule asks for a change inside that plateau.** With the late contraction r ≈ 0.92, the estimate falls below the tolerance only when the change is below 1e‑3·(1−r)/(2r) ≈ 4.2e‑5, which is 1.4 × the floor. Near the noise the ratio r jumps between about 0.9 and above 1, so single checks pass but two in a row never do. In the run examined, 13 of 797 checks passed, never two consecutively.
3. **`wake=3` causes the slow contraction.** Before the noise sets in, the block contraction rises with `wake=3` in every case, and most in Case C:

| Case | Contraction, `wake=2` → `wake=3` | Change the estimate rule needs, as a multiple of the floor, `wake=3` |
|---|---|---|
| A | 0.854 → 0.891 | 4.3 |
| B | 0.899 → 0.910 | 2.3 |
| C | 0.835 → 0.922 | **1.4** |
| D | 0.759 → 0.813 | 2.2 |
| E | 0.602 → 0.704 | 4.8 |

Case B is the next closest; its 1 m `wake=3` runs end on the floor rule with the change at 0.97 × the floor, only just. Why the spreading wake slows the late contraction is not established; a smooth deficit over a whole array plausibly leaves low-frequency error that red-black SOR damps slowly.

**The stall costs time, not accuracy.** Case C, state 1H, 0°, 1 m, `wake=3`, against a float64 reference converged over 5,000 sweeps:

| Field | Sweeps | Largest error over the 2 m plane / U_ref | Largest probe \|ΔK\| |
|---|---|---|---|
| float32, 800 sweeps | 800 | 1.6e‑3 | 5.1e‑4 |
| float32, 1,000 sweeps | 1,000 | 7.6e‑4 | 2.4e‑4 |
| float32, 1,250 sweeps | 1,250 | 3.2e‑4 | 1.1e‑4 |
| float32, 2,000 sweeps | 2,000 | 6.0e‑5 | 3.4e‑5 |
| float32, stalled at the cap | 20,000 | 5.1e‑5 | 3.0e‑5 |
| float64, velocity rule | 1,150 | 4.1e‑4 | 1.1e‑4 |

The field reaches float32 precision by about 2,000 sweeps; the remaining 18,000 change nothing. In float64 the rule works as designed and stops after 1,150 sweeps.

## 3. Candidate changes to the rule

Replayed on the 1,391 stored histories with `validation/replay_stop_rule.py`. The replay of the current rule reproduces the stop sweep of all 1,391 runs.

| Candidate | Case C 1 m `wake=3`: stop sweep, median (max) | Still capped | Other runs that would stop earlier |
|---|---|---|---|
| **Stagnation stop:** no new minimum of the change for 8 checks (200 sweeps), and change ≤ 2 × floor | 1,975 (2,225) | 0 | **0** |
| Same with change ≤ 3 × floor | 1,975 (2,225) | 0 | 0 |
| Same with 12 checks | 2,100 (2,375) | 0 | 0 |
| Floor factor 9 instead of 6 | 1,525 (1,850) | 0 | 15 (by up to 250 sweeps) |
| Floor factor 12 | 1,325 (1,475) | 0 | 15 (by up to 350 sweeps) |

**Recommendation: the stagnation stop, 8 checks, change ≤ 2 × floor.** *(Implemented in a stricter form; see section 0.)* It ends every stalled run at about 2,000 sweeps, where the field is within 6e‑5 U_ref of the converged one, and it changes the stop of no other stored run. It is reported as its own termination (or as `precision_floor`), so a stall stays visible. Raising the floor factor also works, but it moves 15 runs that stop correctly today and weakens the floor rule everywhere.

**What the change would touch.**

- Native solver code (`check_estimate` in `src/qes_core/solver/solver.cpp`), so the native identity changes. The audited turbulence fixtures need their metadata regenerated, as in 0.1.0b6.
- Default results change only for runs that would otherwise stall. For the stored validation runs that is only Case C with `wake=3` at 1 m. Their fields change by less than 6e‑5 U_ref, and the runs take about 10 % of the time.
- `pedestrian-v1` uses the adaptive controller, not this rule; the policy compatibility check would confirm that.
- The study behind the current constants is `validation/SOLVER_STOP_RULE_RESULTS.md` (E1); the new condition should be added to it and checked on its cases too, not only on the AIJ runs.

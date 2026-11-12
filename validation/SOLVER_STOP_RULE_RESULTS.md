# Solver stop rule: study E1 results

- **Date:** 2026-11-12. Implements step P3 of `SOLVER_STOP_RULE.md` (section 6). The decisions it feeds are P4.
- **Build:** branch `feat/solver-stop-rule` at `297fa18` plus the study's harness edits, native identity `6b62eb8a…` (unqualified; G1 passed). M4 Pro, 3 runs at a time, so per-sweep times below are not cost evidence.
- **Runs:** `validation/run_stop_rule_study.py`.
  - 84 float32 study runs: Case D at 0°, 22.5°, 45° and Case E "after" at N, E, S, W, at 2 m and 1 m, each at ω ∈ {1.78, 1.85, 1.90, 1.93, 1.95, 1.97}. Turbulence off, measured inflow. `stop="fixed"` with 4,000 (2 m) or 12,000 (1 m) sweeps, probe history and estimate history every 25 sweeps.
  - 14 float64 references at ω = 1.90, 8,000 or 16,000 sweeps. Their own estimate histories end at a block change of at most 5.7e-14 and an estimate of at most 1.1e-11, so they are converged far below every error reported here.
  - Full-field subset: Case D 0° and Case E W at 2 m and 1 m, native `stop="velocity"` solves at ω ∈ {1.78, 1.90, 1.95, 1.97} and τ ∈ {3e-3, 1e-3, 3e-4, 1e-4, 3e-5}, compared over the whole volume with an in-process float64 reference.
- **Wall time:** 2 m stage 230 s; 1 m stage 58 min; the full-field runs at ω 1.95 and 1.97, both resolutions, 7 min.
- **Not run:** 0.5 m. Case D there is 142 M cells (about 5 h for the planned matrix); decided to skip it on 2026-11-12. The rule is validated down to 1 m only.
- **Evidence:** `docs/data/solver-stop-rule/e1-*.json` (analysis summaries and full-field rows). Records are in `validation/output/runs/{D,E}` (not in git).

Stop sweeps of any tolerance are replayed offline from the fixed-work histories with the native rule (`aij.stop_rule.replay`). A harness test checks that the replay stops on the same sweep as a native `stop="velocity"` solve. Probe errors are |K − K_ref| over the probes sampled linearly in both runs (78 in D, 79 in E). Estimates and K share one normalisation, the approach-profile speed at the reference height.

## 1. Answers

**1. The rule is safe on the real cases, with one caveat at the first checks.**
- At every stop the rule makes for τ ≤ 5e-3, the probe errors are within gate G2 (p95 ≤ 0.0025, max ≤ 0.01) by a factor of 3 or more.
- Over the whole volume, at every native `velocity_estimate` stop of the subset, the actual largest error is 0.11–0.52 of the estimate (38 stops, 2 m and 1 m, four ω). In 32 of them the largest error lies in the pedestrian band (z ≤ 10 m); in the others the band holds at least 0.69 of it.
- The estimate can be exceeded only at the first one or two checks where it exists (sweeps 75–100): there the contraction is still small (0.12–0.48), from the initial transient. Those checks have e ≥ 2e-3 at 2 m and e ≥ 2e-2 at 1 m, so they matter only for loose tolerances: τ = 1e-2 at 2 m fails G2 (p95 up to 5.0e-3), τ = 5e-3 passes.

**2. τ against the probe targets.** The estimate bounds the worst face anywhere; the probes see far less. At τ = 1e-3 the worst probe error over all 84 runs is 3.1e-4 (2 m) and 6.3e-4 (1 m), 30× below the F02 maximum. At τ = 3e-3 it is 9.5e-4 and 8.8e-4.

**3. Speed.** Today's `Solver()` runs 1,000 sweeps at ω = 1.78 (the λ rule stalls in float32). Sweeps to the stop at τ = 1e-3, median (range) over 7 cases:

| ω | 2 m | 1 m |
|---|---|---|
| 1.78 | 725 (700–1,125) | 2,875 (2,725–4,050), all at the rounding floor |
| 1.85 | 475 (475–725) | 2,050 (1,975–2,925) |
| 1.90 | 300 (300–475) | 1,475 (1,250–2,125) |
| 1.93 | 200 (200–325) | 1,075 (925–1,500) |
| 1.95 | **200 (200–225)** | 625 (600–1,100) |
| 1.97 | 300 (300–375) | **350 (325–525)** |

- At 2 m the best ω cuts today's work 5× (1,000 → 200 sweeps) at a worst probe error of 2.1e-4.
- At 1 m today's 1,000 sweeps leave p95 errors of 0.006–0.013 (`AIJ_VALIDATION.md`). The rule at ω = 1.97 stops after 350 sweeps with a worst probe error of 1.4e-4. A correct ω = 1.78 solve needs 2,875.
- The 2 m gain is as large as the X2 prototype predicted; the parameterization zones did not erode it.

**4. Constants.**
- **ω depends on the grid.** The best ω is 1.93–1.95 at 2 m (250–300 cells across) and 1.97 at 1 m (500–600 across), and 1.97 is the highest value tested. No single value is within 20 % of the best at both resolutions, so decision D5 calls for a grid-dependent ω. ω = 1.97 is above the optimum at 2 m and the estimate stays safe there.
- **The floor factor κ = 4 is marginal for fast ω at 1 m.** In the float32 tail, the block change divided by the floor reaches at most 0.99 at 2 m but up to 1.38 at 1 m for ω ≥ 1.95. Two consecutive checks below the floor then come late: Case E W at 1 m, ω = 1.97, τ = 1e-4 stopped only after 5,450 sweeps. Section 3 replays other κ.
- **What float32 can certify.** The estimate only resolves remaining errors down to about floor·r/(1 − r). Below that, the maximum block change is rounding noise even while the error still falls, and no contraction test separates the two (r ≥ 1 in both). Where the rule then stops on `precision_floor`, the actual whole-volume error at 1 m is 2.3e-4–9.2e-4 for ω ≤ 1.90 and 2.2e-5–8.7e-5 for ω = 1.95–1.97. With ω ≥ 1.95, τ = 1e-3 always stops on the estimate at both resolutions; τ ≤ 3e-4 at 1 m usually ends on the floor.

## 2. Gates

| Gate | Result |
|---|---|
| G1 Defaults unchanged | Passed at P1 (`docs/data/solver-stop-rule/g1-*`). |
| G2 Safe stop | **Passed** for τ ≤ 5e-3 at every ω, both resolutions (worst at τ = 3e-3: max 9.5e-4, p95 8.8e-4). Full-field: actual ≤ 0.52 e at every estimate stop. τ = 1e-2 fails at 2 m. |
| G3 Speed at 2 m | **Passed** for ω ≥ 1.90 at τ = 1e-3 (medians 300, 200, 200, 300 for 1.90–1.97); fails at ω ≤ 1.85. |
| G4 Fine grids finish | **Passed at 1 m**: every stop is on the estimate or the floor, the latest at 4,050 sweeps in the matrix and 5,450 in the subset (cap 20,000). Not tested at 0.5 m. |
| G5 Same answer | **Passed**: the end of every run agrees with float64 to 7.9e-6 (2 m) and 2.9e-5 (1 m) in K at the probes, the float32 floor. |
| G6 Scores unchanged | Stage 2, after the default switch. |

## 3. Floor factor κ, replayed

The floor scales linearly with κ, so other values are replayed from the same histories (median and latest stop, floor stops, worst probe error):

| | κ = 4 (now) | κ = 6 | κ = 8 |
|---|---|---|---|
| 1 m, ω 1.97, τ 3e-4 | 700, latest 1,525, 4/7 floor, 2.1e-5 | 425, latest 675, 4/7, 4.1e-5 | 425, latest 650, 4/7, 5.7e-5 |
| 1 m, ω 1.97, τ 1e-4 | 850, latest 5,450, 7/7, 1.9e-5 | 425, latest 675, 7/7, 4.1e-5 | 425, latest 650, 7/7, 5.7e-5 |
| 1 m, ω 1.95, τ 1e-3 | 625, 0/7, 1.5e-4 | 625, 2/7, 1.5e-4 | 625, 2/7, 1.7e-4 |
| 1 m, ω 1.78, τ 1e-3 | 2,875, 7/7, 6.3e-4 | 2,650, 7/7, 9.8e-4 | 2,500, 7/7, 1.3e-3 |
| 2 m, every ω, τ 1e-3 | unchanged | unchanged | unchanged |

κ = 6 removes the long tail at fast ω and leaves τ = 1e-3 unchanged; its cost is earlier floor stops at slow ω, which a fast default ω avoids.

## 4. Recommendations for P4

| # | Decision | Recommendation |
|---|---|---|
| R1 | Default τ | **1e-3.** 30× below the F02 probe maximum, at least 4× inside G2 at every ω and 13× with ω ≥ 1.95; τ = 3e-3 saves only 10–15 % of the sweeps. It is also the tightest τ that float32 certifies by its estimate at 1 m with a fast ω. |
| R2 | Default ω | **Grid-dependent (D5).** For example ω = 2 − 13.5/N with N the cell count across the shorter horizontal side, clipped to [1.90, 1.98]: it gives 1.95 at 2 m and 1.975 at 1 m on these domains. This fit rests on two resolutions and on 1.97 being the highest ω tested. Before adopting it, run ω ∈ {1.98, 1.99} at 1 m (14 runs, about 15 min) to find where the 1 m optimum lies. The fallback is a constant 1.95: optimal at 2 m, 1.8× the best at 1 m, still 4.6× faster there than a correct ω = 1.78 solve. |
| R3 | Floor factor | **κ = 6** (section 3). |
| R4 | Earliest stop | **Count passes from the fourth check** (instead of the third). It removes every observed underestimate that could stop a solve (they are all at checks 3–4) at the cost of one block for loose tolerances. |
| R5 | `precision_floor` | **Keep it as a converged outcome**, documented as "float32 cannot certify a smaller error". With a fast ω its actual errors are at most 8.7e-5 at 1 m. Reporting it as a failure would bring back the false alarms of the λ stall. |

R3 and R4 are native changes to the opt-in rule. They change no default and go into the P5 re-qualification together.

## 5. Limits

- Two cases, two resolutions; no 0.5 m and no Cases A and B.
- Turbulence off: QES-Turb runs on the final field and does not change it, but its cost is not included.
- Sweep counts are the cost metric. The estimate's own overhead per check, predicted at about 8 %, and wall times on an idle machine are measured in P7.
- The full-field comparison uses cell-centred velocities, which the face bound also bounds.
- The ω(N) fit is an extrapolation outside 250–600 cells across.

## 6. P4 follow-up (2026-11-12): decisions, ω above 1.97, and the candidate defaults

R1–R5 were accepted (decisions D6–D10 in `SOLVER_STOP_RULE.md`).

**ω = 1.98 and 1.99 at 1 m** (14 more runs, 12 min; same references). Medians of the stop sweep over the 7 cases, with the rule of D8 and D9 replayed:

| ω | τ 3e-3 | τ 1e-3 | τ 3e-4 | probe error / e |
|---|---|---|---|---|
| 1.95 | 500 | 625 | 750 | up to 1.15 |
| 1.97 | 300 | **350** | 425 | 0.15–0.82 |
| 1.98 | 425 | 500 | 525 | 0.09–0.16 |
| 1.99 | 925 | 1,000 | 1,100 | 0.03–0.08 |

The 1 m optimum is 1.97. Above it the decay oscillates and the estimate becomes conservative (error at most 0.16 e), so stops come late but stay safe. With 2 − ω_opt ≈ 0.06 at N = 250–290 and 0.03 at N = 500–580, the optimum scales as 1/N.

**Rule fitted (D7):** ω = clip(2 − 16/N, 1.78, 1.98) rounded to 0.001, with N the physical cells across the shorter horizontal side. It gives 1.936 (Case E, 2 m), 1.945 (Case D, 2 m), 1.968 (Case E, 1 m) and 1.972 (Case D, 1 m), slightly below each optimum. The upper clip keeps finer grids (N > 800) below their optimum, where the estimate is safe; the lower clip keeps today's 1.78 on small grids. Available as `wind.Solver(relaxation="grid")`, resolved natively and reported in `result.solver["relaxation"]`.

**Native rule changes (D8, D9):** κ = 6; passes count from the fourth check, so the earliest stop is at 125 sweeps. The estimate history reports both (`floor_factor`, `first_counted_check`).

**Candidate defaults, run natively** (`relaxation="grid"`, `stop="velocity"`, τ = 1e-3, cap 20,000; campaign `stop_rule_candidate`, native identity `1319a43d…`), against the float64 references:

| Case | N | ω | Sweeps | Termination | p95 \|ΔK\| | max \|ΔK\| |
|---|---|---|---|---|---|---|
| D 0°, 22.5°, 45°, 2 m | 290 | 1.945 | 250 each | velocity_estimate | 0.9–1.3e-4 | 1.2–1.4e-4 |
| E N, E, S, W, 2 m | 250 | 1.936 | 150–175 | velocity_estimate | 0.8–1.6e-4 | 0.9–1.9e-4 |
| D 0°, 22.5°, 45°, 1 m | 580 | 1.972 | 475 each | velocity_estimate | 1.2–1.6e-4 | 1.6–1.8e-4 |
| E N, E, S, W, 1 m | 500 | 1.968 | 325–375 | velocity_estimate | 0.6–1.1e-4 | 0.7–1.3e-4 |

- Every solve stops on its estimate and reports converged. The worst probe error is 1.9e-4: 50× inside G2 and 100× below the F02 maximum.
- Against today's `Solver()` (1,000 sweeps at 1.78): 4–6.7× less work at 2 m. At 1 m, 2.1–3.1× less work, and converged where today's default leaves p95 errors of 0.006–0.013.
- Evidence: `docs/data/solver-stop-rule/e1-candidate.json`.

## 7. P5: stage 1 re-qualified (2026-11-12)

Candidate `f99661e`, native identity `1319a43d89ce2abf951c3eae48d8047457049e31c28a9938e10b4722fbcf4bf6`, by every stage of `docs/solver-control-requalification.md` (evidence `docs/data/solver-stop-rule/requalification*.json`):

- Fresh Release builds: CTest OpenMP 62/62, serial 59/59, ASan/UBSan 59/59. Native symbol checks pass, and serial and OpenMP identities are equal. The first sanitizer build found a heap-use-after-free in a test (`check_stop_rule.cpp` bound a reference into a returned temporary), fixed in `f99661e`. The product code was unaffected.
- `compare_native_builds.py` against `d968aa7`, with the declared identity pair: 429 cases and 4,783 records identical for OpenMP at 1, 2, 4 and 8 threads and serial, thread teams and backends, with no differences.
- The isolated copy with the new identity keeps it and reports build support. All 24 frozen S7 workers match exactly.
- The combined feature baseline, non-adaptive and adaptive, matches.
- `pytest -W error`: 2,042 passed, 16 skipped, on both isolated packages.
- sdist, wheel from the sdist, `check_artifacts.py`, and the wheel runtime smoke with a 4-thread team: adaptive run accepted, identity supported. With the machine's default team the smoke's adaptive run is correctly unaccepted (`unqualified_thread_team`).

The identity is promoted in `pedestrian_qualification.h`. The rebuilt extension reports it as supported: `pytest -W error` 2,008 passed, 50 skipped; validation tests 158 passed.

## 8. P6: the default switch and gate G6 (2026-11-12)

`wind.Solver()` now means `stop="velocity"`, `velocity_tolerance=1e-3`, `relaxation="grid"`, `max_iterations=20000` for legacy and bounded solves (commit `06b2e7d`). It is declared in section 6a of `SOLVER_STOP_RULE.md`, which was written before G6 ran. `Solver(stop="multiplier_change")` is the former default exactly, and stored specs without `stop` keep it.

**Gate G6: passed.** The AIJ 2 m baseline of Cases A, B, D and E (37 runs, turbulence on; campaign `stop_rule_g6`) was run with the new default and at the baseline's fixed work (2,000 multiplier sweeps). Over 15 pooled comparisons, the largest change in q, FAC2, R, ρ or FB is **0.0053**, against the limit of 0.01. Evidence: `docs/data/solver-stop-rule/g6-scores.json`.

| Comparison | n | Largest \|Δ\| | Where |
|---|---|---|---|
| A: \|U\|, U, k | 144–186 | ≤ 0.0003 | |
| A: W | 186 | 0.0053 | FB −1.061 → −1.066 |
| B: \|U\|, U, k | 196–224 | ≤ 0.0003 | |
| B: W | 224 | 0.0022 | FB 1.172 → 1.170 |
| D: split fibre, thermistor K | 33, 198 | ≤ 0.0001 | |
| D: thermistor K_scalar | 196 | 0.0051 | q 0.265 → 0.260 (one probe) |
| E before/after, K and K_scalar | 1,271–1,280 | ≤ 0.0008 | |

All 37 default runs stop on the estimate:

| Cases | Sweeps |
|---|---|
| D and E | 150–250 |
| A | 325 |
| B | 425 |

The former default ran 1,000 sweeps; the baseline's fixed work is 2,000. At the stop, the maximum divergence is 0.8–2.4e-3 s⁻¹, against 1.5–4.8e-5 after 2,000 multiplier sweeps. This is the declared divergence difference: the rule bounds velocity error, which the scores show is what matters here.

**Verification tools after the switch.** With the new defaults installed, the native qualification checks still match exactly. The tools pin the multiplier rule, version-tolerantly:

- `compare_native_builds.py` against `d968aa7` with `06b2e7d` as candidate is bitwise identical: 429 cases, OpenMP at 1, 2, 4 and 8 threads and serial, backend parity.
- All 24 frozen S7 workers match on the qualified builds with the stage 2 Python.
- The combined feature baseline, non-adaptive and adaptive, matches the `main` capture.

Python suites: `pytest -W error` 2,016 passed, 50 skipped; validation tests 159 passed.

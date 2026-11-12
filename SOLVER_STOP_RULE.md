# Solver stop rule and relaxation: implementation plan

- **Date:** 2026-11-12.
- **Implements:** suggestion S2 of `FABEL_DESIGN_AND_ALGORITHM_REVIEW.md`. This is not stage S2 of the solver-control refactor (`docs/solver-control-s2.md`).
- **Also closes:** R14 in `validation/DTCC_REQUESTS.md` (a stop rule at fine grids), and F02's H2a–H2c in `CLAUDE_WIND_EXPERIMENTS.md` (the best ω).
- **Goal:** a stop rule that bounds the remaining velocity error, as a fraction of the reference speed, together with a better default ω. With these, `Solver()` stops early on coarse grids and keeps going on fine ones.
- **Status:** D1–D5 accepted as recommended (2026-11-12). P1a–P1c implemented on branch `feat/solver-stop-rule` (worktree `/private/tmp/dtcc-qes-solver-stop-rule`, from `main` at `d968aa7`), independent of `feat/wake-update-v2`. Gate G1 passed at P1 (section 7). P2 and P3 (study E1) done: results in `validation/SOLVER_STOP_RULE_RESULTS.md`. P4 done (D6–D10, `0877136`): `relaxation="grid"`, κ = 6 and passes from the fourth check are in the opt-in rule, native identity `1319a43d…`. G1 passed again for that identity. P5 done: `1319a43d…` re-qualified and promoted (results, section 7). P6 done: the velocity rule is the default (`06b2e7d`), and G6 passed (worst pooled-score change 0.0053; results, section 8). P7 (the 16-direction comfort timing) is next.

## 1. Findings that shape the plan

**How the solver stops today.**

| Mode | ω | Stop rule | Source |
|---|---|---|---|
| `Solver()` (legacy) and bounded | 1.78 | λ change ≤ `tolerance` (default 1e-4), at most `max_iterations` (default 1,000) | `solver_control.py:104-105`, `wind_runner.cpp:354, 412` |
| Adaptive (`pedestrian-v1`) | 1.90 | Fixed sweeps; the monitor decides acceptance | same |
| AIJ validation | 1.78 | Fixed work: tolerance 1.2e-7, below the float32 stall; 2,000 sweeps at 2 m, 6,000 at 1 m | `validation/aij/campaigns.py:21-22` |

**The λ rule cannot tell when the solve has converged.** In float32 the λ change stalls at 0.8–1.5e-4, which is about the default tolerance, even after the probe values have stopped changing (`validation/AIJ_VALIDATION.md:404`). λ is in m²/s, so the rule also depends on the wind speed and the grid spacing.

**A fixed 1,000 sweeps is more than 2 m needs and less than 1 m needs.** From the convergence campaign (`AIJ_VALIDATION.md:394-408`), at ω = 1.78:

| | Case D, 2 m | Case D, 1 m | Case E, 2 m | Case E, 1 m |
|---|---|---|---|---|
| Sweeps until p95 \|ΔK\| ≤ 0.005 and max ≤ 0.02, and staying there | 375–450 | 1,425–1,675 | 275–300 | 1,075–1,150 |
| p95 \|ΔK\| after 1,000 sweeps (the default) | 3–4e-4 | **0.009–0.013** | 2–3e-5 | **0.006–0.007** |

The work needed grows about 4× for each halving of the cell size. A stop rule therefore fixes accuracy at 1 m and below, and saves time at 2 m and above.

**The ω gain has only been shown on a simplified problem.** In the review's X2, the whole 2 m plane reached a maximum error of 1e-3 U_ref after 400 sweeps at ω = 1.90, against 1,000 at ω = 1.78. That problem's initial field had no parameterization zones.

**The review's estimator would be too cautious.** The review proposed max |Δλ| per sweep, divided by dx and by (1 − ρ). It has two problems:
- The slowly converging error modes are smooth, with wavelengths near the domain size L. Dividing by dx overstates their velocity error by about L/(π dx), which is around 80 at 2 m on Case E.
- The per-sweep max |Δλ| is the quantity that stalls at float32 rounding.

Section 3.1 replaces it with the actual velocity change over a block of sweeps.

**Changing the default has to be its own step.** Re-qualification (`docs/solver-control-requalification.md`) requires exact agreement on two things: the outputs of the non-adaptive runs (step 2) and the 24 frozen S7 workers (step 4). A deliberate numerical change needs its affected cases, its correctness criteria and its measured impact declared before it is accepted (the last paragraph of that document). The wake update was blocked at exactly this point (`validation/WAKE_UPDATE_V2_RESULTS.md` on `feat/wake-update-v2`). This plan therefore:
- adds everything as opt-in first, with the defaults bit-identical, which the standard procedure can re-qualify;
- switches the default afterwards, as a separate declared numerical change;
- leaves the adaptive policy alone throughout.

**ω cannot be set from Python today.** The AIJ inflows are tabulated profiles, so an adaptive request for them is excluded from the policy and falls back to 1.78. The ω study therefore needs the native option first. That option is the first commit of this plan, not a throwaway debug branch.

## 2. Scope

In scope:
- `Solver(relaxation=...)` for the legacy and bounded modes.
- A velocity-estimate stop rule, `Solver(stop="velocity", velocity_tolerance=...)`, and an explicit `stop="fixed"`.
- Stop diagnostics on the result.
- The study that chooses ω and τ, and the declared switch of the defaults.

Out of scope:
- The `pedestrian-v1` policy. It keeps fixed sweeps at ω = 1.90, its monitor and its qualification. The new options are rejected in adaptive mode.
- The AIJ harness's fixed-work settings. Validation records keep fixed work.
- Chebyshev acceleration (F02 H2d), multigrid (A1/F06) and the GPU backends. Section 3.2 keeps the rule compatible with all three.

## 3. Design

### 3.1 The estimator

The rule checks every m = 25 sweeps. At check n:

- **Block change:** D = λ_n − λ_{n−m}. λ_{n−m} is a snapshot taken at the previous check.
- **Velocity change:** c_n = max over fluid faces of |δu_f| / U_ref. δu_f uses the same expression as `corrected_face` (`cpu_float32.cpp:229-241`), applied to D instead of λ; for u, ½ · a.f · dx · (D_i − D_{i−1}). Wall faces have a zero coefficient, so they drop out without a separate mask.
- **Contraction per block:** r_n = max(c_n / c_{n−1}, c_{n−1} / c_{n−2}), the larger of the last two block ratios, clipped to at most r_max = 0.99.
- **Remaining error:** e_n = S · c_n · r_n / (1 − r_n), with safety factor S = 2. Without S, this is the change still to come if the decay continues at rate r_n.
- **Why the larger ratio and S (measured in P1b, `tests/native/check_stop_rule.cpp`).** The plan first used √(c_n / c_{n−2}) without S. On a 64 × 48 × 24 grid with three buildings, measured against a double-precision reference:
  - At ω = 1.78 the contraction rises through the early transient (0.04, 0.15, 0.27, 0.42) before it settles at 0.39. The two-block mean lagged behind: the rule stopped at sweep 100 with e = 5.2e-4, while the actual error was 1.4e-3, which is 2.7× more and above τ = 1e-3.
  - At ω = 1.90, which is above the optimum on that small grid, the decay oscillates (block ratios 0.05–0.11) and the mean underestimated by up to 1.7×.
  - Once the decay is geometric, the estimate without S is exact (actual / e = 0.97–1.00), so it has no margin.
  - With the larger ratio and S = 2, every stop for τ ∈ {1e-3, 1e-4, 1e-5} at both ω has actual / e between 0.3 and 0.7, and the actual error is 8–86× below τ. ω = 1.90 stops at sweep 100, 125 and 150; ω = 1.78 at 175, 225 and 300.
- **Stop** when e_n ≤ τ at two consecutive checks. Passes count from the fourth check, so the earliest stop is the fifth (125 sweeps); P4 decision R4, since E1 found the estimate short only at the third and fourth checks. (P1 counted from the first check, with no stop before the third.) The termination reason is `velocity_estimate`.
- **Rounding floor:** also stop when c_n ≤ c_floor at two consecutive checks, with termination reason `precision_floor`. c_floor = κ · ε · max |λ| / (h_min · U_ref), where ε is the machine epsilon of the arithmetic, h_min the smallest spacing, and κ = 6 (P4 decision R3; P1 used 4, which E1 found too tight for fast ω at 1 m).
  - Without this term, a float32 run that has reached rounding level has r ≈ 1, gets e ≈ 99 c, and may never stop.
  - The measured λ stall (about 1e-4 m²/s) corresponds to roughly 3e-5 m/s at 2 m, or about 1e-5 U_ref.

Notes:
- **Scope of the maximum (D2).** The maximum runs over the whole fluid volume, not just the pedestrian layers, so the bound holds for the whole returned field.
- **Velocity scale (D3).** U_ref is the condition's reference speed (`native.speed`, `wind.py:616`). It is the same speed that K and the adaptive controller normalise by. A calm condition (U_ref = 0) rejects `stop="velocity"`.
- **When the estimate is valid.** The estimate assumes one dominant real eigenvalue. That holds for SOR with ω at or below ω_opt; above it the eigenvalues are complex and the decay oscillates. E1 checks this for every ω studied. The defaults must stay at or below the best ω that E1 finds.
- **Cost.** A snapshot copy plus one gradient pass every 25 sweeps, about 2 sweep-equivalents per 25, or 8 %. One extra array of the cell count: 7 MB at 1.8 M cells, 60 MB at 15 M. The array is allocated only when the estimate is enabled.
- **Thread independence.** The maximum reduction is exact, so the estimate does not depend on the thread count.

### 3.2 Native

| File | Change |
|---|---|
| `solver/solver.h`, `solver.cpp` | Add `StopRule::VelocityEstimate` and `Termination::VelocityEstimate` / `PrecisionFloor`. `begin()` takes an `EstimateOptions{enabled, reference_speed, tolerance, interval}`. The snapshot and the check live in the `advance()` loop and run only when the estimate is enabled. `estimate_report()` returns the check history: (sweep, c, r, e, floor), at most 2,000 entries. The block-change pass is one generic template (OpenMP, exact max reduction); the sweep kernels in `cpu_float32.cpp` and `cpu_float64.cpp` are untouched. `SolveDiagnostics::converged` keeps its multiplier-change meaning, so the control record's `legacy_tolerance_satisfied` stays correct. |
| `dtcc/api/wind_config.h` | `SolverOptions` gains `relaxation = 0` (0 means today's choice: 1.78, or 1.90 when adaptive), `stop_rule`, `velocity_tolerance`, and `record_estimate`. |
| `dtcc/wind_runner.cpp:354, 412` | Choose the rule and ω from the options. Pass `condition.speed` as the scale. Reject the new options when adaptive is enabled. |
| `dtcc/solver_control.cpp` | Bounded mode ends on the new termination values in the same way as `LegacyTolerance`, and records the reason. |
| `src/cpp/bindings.cpp` | Expose the new fields. |

**GPU.** Checks happen only at block boundaries and need no per-sweep host synchronisation, as section "Stopping without per-sweep host syncs" of `PERFORMANCE_REVIEW.md` requires.

### 3.3 Python

`wind.Solver` gains three fields:

| Field | Default (stage 1) | Meaning |
|---|---|---|
| `relaxation: float \| None` | None | ω for legacy and bounded runs; None keeps 1.78. Must satisfy 0 < ω < 2. |
| `stop: Literal["multiplier_change", "velocity", "fixed"]` | `"multiplier_change"` | `"fixed"` runs exactly `max_iterations` sweeps. It replaces the harness's tolerance-below-the-stall trick for new work. |
| `velocity_tolerance: float` | 1e-3 | τ, as a fraction of U_ref. Used only with `stop="velocity"`. |

- **Estimate history.** It is recorded with `"velocity"` and with `"fixed"`, so that one fixed-work run gives the full estimate trajectory for E1.
- **Adaptive mode** (`policy="pedestrian-v1"`) raises `ValueError` if any of the three fields is not at its default.
- **`to_dict` omits the new keys while they hold their defaults**, and old payloads load unchanged. The stored solver specs of the frozen workers therefore stay identical.
- **Diagnostics.** The new keys appear on the result (`result.solver`, `result.qualification`) only for `stop` values other than `"multiplier_change"`. Absent, not None, as the wake fields do for codes 0–2.
- **`converged`.** For `stop="velocity"`, `result.diagnostics.converged` means e ≤ τ or the precision floor was reached; `stop_estimate["termination"]` says which. `qualification["solver"]["legacy_converged"]` and the control record's `legacy_tolerance_satisfied` keep the multiplier-change meaning for every rule. For `stop="fixed"`, completing the work is not a convergence failure (no `ConvergenceError`, no warning). The qualification view gains `stop_rule` only for the two new rules.
- **Docs.** Update the mode table in `docs/solver-control.md`, and the sentence there that says convergence measures the multiplier change.

## 4. Decisions

D1–D5 were accepted as recommended on 2026-11-12, and D6–D10 (the P4 choices from study E1) later the same day.

| # | Question | Decision |
|---|---|---|
| D1 | Opt-in first and a declared default switch afterwards, or both at once? | **Two stages** (section 1, last finding). Stage 1 is re-qualifiable by the standard procedure; stage 2 is a declared numerical change. |
| D2 | Should the estimate cover the whole fluid volume or only the pedestrian layers? | **The whole volume.** The solver returns the whole field, and a pedestrian-only bound would be a policy decision, not a solver default. |
| D3 | What velocity scale? | **The profile's reference speed**, the same one K and the controller use. |
| D4 | What iteration cap once the rule is the default? | **20,000.** The rule stops far earlier at 2 m. At 0.5 m the campaign needed 16,000 at ω = 1.78. A cap keeps a failing case finite, and the result then reports that it did not converge. |
| D5 | One default ω or a grid-dependent one? | **One constant**, if it is within 20 % of the best ω's sweep count at 2 m, 1 m and on the 0.5 m subset. Otherwise a fitted ω(N) for N cells per side, decided in P4. |
| D6 | Default τ (P4, R1, accepted 2026-11-12) | **1e-3.** E1: 30× below the F02 probe maximum, at least 4× inside G2 at every ω; τ = 3e-3 saves only 10–15 % of the sweeps. |
| D7 | Default ω (P4, R2, accepted 2026-11-12) | **Grid-dependent:** ω = clip(2 − 16/N, 1.78, 1.98), rounded to 0.001, for N physical cells across the shorter horizontal side (`Solver(relaxation="grid")`). No constant is within 20 % of the best at both 2 m and 1 m (D5); ω 1.98 and 1.99 at 1 m confirmed 1.97 as the 1 m optimum (results, section 6). |
| D8 | Floor factor κ (P4, R3, accepted 2026-11-12) | **6.** Native change to the opt-in rule. |
| D9 | Earliest stop (P4, R4, accepted 2026-11-12) | **Passes count from the fourth check** (earliest stop at 125 sweeps). Native change to the opt-in rule. |
| D10 | `precision_floor` (P4, R5, accepted 2026-11-12) | **A converged outcome**, documented as "the arithmetic cannot certify a smaller error". |

## 5. Work steps

- **P1. Native and Python, opt-in.** Three commits:
  - (a) `relaxation`;
  - (b) the estimate and the `velocity` and `fixed` rules;
  - (c) the Python fields, diagnostics and docs.
  - Gate G1 after (c).
- **P2. Harness.**
  - Add `relaxation`, `stop` and `velocity_tolerance` to the RunSpec later fields. The defaults keep the existing run keys, as F02's snippet already shows.
  - Pass them through `runner.inputs`.
  - Add a `stop_rule_study` campaign (section 6).
- **P3. Study E1.** Section 6. Write the results to `validation/SOLVER_STOP_RULE_RESULTS.md`.
- **P4. Choose ω and τ.** Take the largest τ, and the ω, that pass G2–G5. Record the declaration that stage 2 needs: affected cases, criteria and measured impact.
- **P5. Re-qualify stage 1** with `tools/check_policy_compatibility.py` and the procedure in `docs/solver-control-requalification.md`. The defaults are bit-identical, so every frozen worker must match exactly. If other native changes are on `main` by then, qualify the combined identity once.
- **P6. Stage 2: switch the defaults.**
  - Legacy and bounded `Solver()` get `stop="velocity"`, the chosen τ and ω, and `max_iterations=20000`.
  - Do it under the P4 declaration, then gate G6.
  - The adaptive policy is untouched, so its frozen workers still match. The non-adaptive comparison in step 2 of the re-qualification changes by declaration.
- **P7. Measure the user-facing gain.** A 16-direction Case E comfort study at 2 m on one `PreparedWindModel` (the S1 path), before and after P6. Report the wall time and the sweeps per direction.

## 6. Study E1

> **As run (2026-11-12):** 2 m and 1 m only. Case D at 0.5 m is 142 M cells (about 5 h for its part of the matrix), and the 0.5 m part was dropped by decision; the rule is validated down to 1 m. The full-field subset also ran at ω 1.95 and 1.97. Results and P4 recommendations: `validation/SOLVER_STOP_RULE_RESULTS.md`.

**Runs.**
- The convergence-campaign matrix: Case D at 0°, 22.5° and 45°, and Case E "after" at N, E, S and W, at 2 m and 1 m.
- Plus Case D at 0° at 0.5 m.
- All float32, `stop="fixed"`, with the probe-history monitor (every 25 sweeps) and the estimate history.
- Budgets: 4,000 sweeps at 2 m, 12,000 at 1 m, 32,000 at 0.5 m.
- ω ∈ {1.78, 1.85, 1.90, 1.93, 1.95, 1.97}, which is F02's set without 1.99.
- In total 90 runs, about 1.5 h on the M4 Pro. Sweep counts, not wall times, are the metric, so the runs can share the machine.

**References.**
- The existing float64 end points of the convergence campaign. The converged field does not depend on ω, so they serve every ω.
- For the full-field check, one float64 reference with the whole 2 m and 1 m pedestrian planes saved, for Case E "after" W and Case D 0°. The full-field subset reruns those two cases with `stop="fixed"` at n ∈ {100, 200, 400, 800, 1,600}, at the default ω and the chosen ω.

**Measured.**

| # | Quantity | Source |
|---|---|---|
| M1 | Sweeps to the F02 probe target, per ω and case (H2a, H2b) | `aij.numerics` against the float64 end points |
| M2 | Reliability of the estimate: actual remaining error divided by e_n at every check, at the probes (all runs) and over the whole pedestrian plane (the subset) | probe histories, full-field subset |
| M3 | For τ ∈ {3e-3, 1e-3, 3e-4, 1e-4}: the stop sweep and the probe error at the stop | replayed offline from the estimate histories |
| M4 | The float32 floor of c, and κ | the tail of the long runs |
| M5 | Converged probe values across ω (H2c) | end of each run |

## 6a. Stage 2 declaration (P4 → P6, written 2026-11-12 before gate G6 ran)

An intentional numerical change of the default solver (`docs/solver-control-requalification.md`, last paragraph).

- **Change.** `wind.Solver()` (legacy and bounded modes, the direct API and the dataset default) moves from the multiplier rule (tolerance 1e-4, 1,000 sweeps, ω = 1.78) to `stop="velocity"`, `velocity_tolerance=1e-3`, `relaxation="grid"`, `max_iterations=20000`. This is a Python-only change: the native identity `1319a43d…` and its qualification are untouched.
- **Affected.** Every legacy or bounded solve that does not choose a stop rule: its sweeps, field, diagnostics and `converged` meaning (now the velocity estimate).
- **Unaffected.**
  - pedestrian-v1 adaptive solves, which keep their qualified rule and sweeps.
  - Solves that set `stop`.
  - Stored solver specs without `stop`, which keep the multiplier rule.
  - Calm conditions, which keep the multiplier rule.
  - The frozen verification tools (`compare_native_builds.py`, `feature_merge_baseline.py`, the S7 worker), which pin the multiplier rule.
- **Independent correctness criteria.**
  - G2: probe error ≤ half of F02 against float64 (E1, and the 14 candidate runs: ≤ 1.9e-4).
  - G5: converged values agree.
  - G6: on the AIJ 2 m baseline (Cases A, B, D, E: 37 runs) the default against the fixed-work records changes no pooled q, FAC2, R, ρ or FB by more than 0.01. The comparisons are `compare.case_d`, `case_e_comparisons` and `isolated`.
- **Expected impact.**
  - 4–7× fewer sweeps at 2 m. At 1 m, 2–3× fewer, and converged where the former default was not (p95 0.006–0.013).
  - Maximum divergence at the stop may exceed that after 1,000 sweeps.
  - A field with no buildings needs 125 sweeps instead of one.

## 7. Gates

| Gate | Requirement |
|---|---|
| G1 Defaults unchanged | `tools/compare_native_builds.py` matches exactly on the non-adaptive subset, and all 24 frozen S7 workers match exactly, at P1 and at P5. **Passed at P1 (2026-11-12)** for candidate `883d758`, identity `6b62eb8a…`, and **again after P4** for `0877136`, identity `1319a43d…` (same counts; the evidence files hold the later run). Against `d968aa7`, 429 cases (4,783 records) are bitwise identical for OpenMP at 1, 2, 4 and 8 threads and for serial, with backend parity required. All 24 S7 workers match on isolated packages that carry the new identity. Evidence: `docs/data/solver-stop-rule/g1-*`. |
| G2 Safe stop | At the chosen τ and ω, every E1 run stops with probe p95 \|ΔK\| ≤ 0.0025 and max ≤ 0.01, which is half of F02's targets. On the full-field subset, the actual maximum error over the plane is ≤ e_n at the stop sweep. **Passed in E1** for τ ≤ 5e-3 at every ω; whole-volume error 0.11–0.52 of e at every estimate stop. |
| G3 Speed at 2 m | The median stop sweep on Cases D and E at 2 m is ≤ 1/2.5 of today's default work (1,000 sweeps), that is ≤ 400. **Passed in E1** for ω ≥ 1.90 (median 200 sweeps at ω 1.93–1.95). |
| G4 Fine grids finish | At 1 m and on the 0.5 m subset, every run stops through `velocity_estimate` or `precision_floor` before 20,000 sweeps. **Passed at 1 m in E1** (latest stop 5,450); 0.5 m not run. |
| G5 Same answer | The converged probe values agree across the ω values within 1e-4 in K (H2c). **Passed in E1** (≤ 2.9e-5). |
| G6 Scores unchanged (stage 2) | The AIJ baseline (Cases A, B, D, E at 2 m) with the new default `Solver()`, against the fixed-work records: every pooled score within 0.01. **Passed (2026-11-12):** worst change 0.0053 over 15 pooled comparisons of Cases A, B, D and E. |

## 8. Tests

**Native** (`tests/native`, outside the policy hash):
- On a synthetic geometric sequence, r and e are exact.
- The termination value and reason are right for each rule.
- The snapshot is allocated only when the estimate is enabled.
- The estimate is identical at 1, 2, 4 and 8 threads.
- With the defaults, λ after N sweeps is bitwise unchanged.

**Python:**
- `Solver` rejects invalid values, and rejects the new fields in adaptive mode.
- `to_dict` omits default keys, and old payloads round-trip.
- Legacy output on the one-building fixture is identical before and after P1, by field hash.
- `stop="velocity"` converges on the fixture with e ≤ τ.
- A calm condition raises `ValueError`.
- `PreparedWindModel` keeps per-solve stop settings across directions.

## 9. Risks

| Risk | Mitigation |
|---|---|
| The estimate is not conservative on some geometry, for example oscillatory decay above ω_opt or an early non-geometric phase | Two consecutive checks, a minimum of three checks, and r clipped at 0.99. G2 is measured on every E1 run and the full-field subset, not assumed. |
| Zone edges in the real initial field change the X2 picture | E1 runs the full parameterized cases. If ω = 1.90 gains less than 1.5× there, the default switch carries τ only, at ω = 1.78. |
| New result keys or spec keys break the frozen-worker comparison | Keys are absent while the options are at their defaults (section 3.3), and G1 checks this directly. |
| float32 floor above τ on large or fast domains | The `precision_floor` term. M4 measures it, and the result records which termination happened. |
| Users relying on `max_iterations=1000` behaviour | Stage 2 is a declared change with release notes. `stop="multiplier_change"` remains available. |

## 10. Done when

- Stage 1 is merged and re-qualified (G1).
- E1's results are recorded, with ω and τ chosen (G2–G5).
- The defaults are switched with G6 passed, or the reason for not switching is recorded.
- P7's before-and-after timing is in the results file.
- `AIJ_VALIDATION.md` R14 and `CLAUDE_WIND_EXPERIMENTS.md` F02 point to the results.

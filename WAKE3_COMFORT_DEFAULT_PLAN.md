# Plan: `wake=3` and the scalar speed as the pedestrian comfort defaults

- **Date:** 2026-11-12. Follows [`WAKE_UPDATE_V2.md`](WAKE_UPDATE_V2.md) (called "the wake plan" below) and its results, [`validation/WAKE_UPDATE_V2_RESULTS.md`](validation/WAKE_UPDATE_V2_RESULTS.md) ("the results").
- **Goal:** decide on evidence whether pedestrian comfort assessments should default to `Parameterizations(wake=3)` with `comfort.assess_results(..., speed="scalar")`, and make the switch if they should.
- **Status:** plan only. Today both are opt-in; the defaults are `wake=2` and `speed="vector"`.

## 1. Why the switch is not made yet

The wake plan's gates all pass, but they pool every probe. Comfort and safety classes are decided at the windiest points, and there the evidence is against a switch (the results, "The windiest points"):

| Case | Windiest 10 % of probe-directions | `wake=2` vector | `wake=3` scalar |
|---|---|---|---|
| D | mean speed vs measured | −42 % | −43 % |
| E before | mean speed vs measured | +28 % | +6 % |
| E after (new high-rise) | mean speed vs measured | **−11 %** | **−25 %** |
| E after | share more than 20 % too slow | 27 % | 64 % |

- The pooled gains of `wake=3` come mostly from sheltered, slow points, where `wake=2` is far too fast. That error is conservative for comfort.
- At the windiest points `wake=3` is no better, and in Case E after clearly more optimistic. A switch would raise comfort classes and lower safety warnings where it matters most.
- In Case D every model is about 40 % too slow at its windiest points: the tower effect is not modelled (`MOMENTUM_PLAN.md`, F08).

Two further obstacles are procedural:

- the adaptive policy `pedestrian-v1` is qualified only for `wake_flag == 2` (the wake plan, section 9, W6);
- the scalar speed √(|u|² + 2k) is a root-mean-square speed, and it is not settled which speed the comfort criteria's hourly mean corresponds to.

## 2. Scope

In scope:
- the comfort-class test that decides the question (C1);
- the definition of the scalar speed used for comfort (C2);
- the diagnosis and remedy of the windy-point bias (C3, C4);
- confirmation on an independent dataset (C5);
- the policy qualification and the switch itself (C6, C7).

Out of scope:
- the wake model's constants (0.2, 0.22, 0.9, 0.08): unchanged unless C4 requires it, and then only with the rules of section 5;
- QES-Turb, whose k does not improve on the new field (the results);
- the ±10° direction thresholds of the upwind cavity and sidewall models (review S3), unless C3 shows they drive the windy-point bias.

## 3. Decisions to confirm before starting

| # | Question | Recommendation |
|---|---|---|
| D1 | Which criteria get the new defaults? | Mean-speed criteria (`NEN8100`) only. Gust-equivalent criteria (`CITY_OF_LONDON`) keep the vector speed with GEM: the scalar speed already contains the turbulence, and adding GEM would count it twice. A combined definition is a separate question. |
| D2 | Re-qualify `pedestrian-v1` on `wake=3` fields, or define `pedestrian-v2`? | `pedestrian-v2`. The v1 thresholds and evidence are frozen for `wake=2`; a new name keeps old results reproducible and their qualification meaningful. |
| D3 | The wind climate for the comfort-class test (C1). | A declared synthetic climate: 16 equal sectors, Weibull speeds at the reference height, with the mean scaled to three levels so that the measured classes span A to E. Report all three; gate on all three. No site climate exists for the tunnel model, and a real one would only add a frequency weighting. |
| D4 | The independent dataset (C5). | The Hamburg data (draft request in the research checkout) if it is obtained. Its pedestrian-level instrument must be known. If no dataset is available within the plan, the switch waits (section 7). |
| D5 | May C4 change the wake model's constants? | Only from first principles or Cases A and B, never fitted to Cases D or E (the wake plan's rule). Any change is then judged on D and E and confirmed on C5's data. |

## 4. Steps

Each step ends with its results recorded in this file (section 9) and the test suites passing. C1 comes first because it is the yardstick for every later step.

### C1. Comfort-class test on Case E

- Case E has 80 thermistor probes and 16 directions in both states, so measured and simulated speeds can be assessed with `comfort.assess` exactly as a study would. Case D (3 directions) and Cases A and B (1 direction) cannot be.
- Fields: the measured K per probe and direction, and each simulated model's K, all relative to the same reference (reference speed 1).
- Models: `wake=2` vector (today's default), `wake=2` with the inflow k, `wake=3` vector, `wake=3` scalar (and C2's alternative once it exists).
- Output per model, state and climate level:
  - NEN 8100 comfort classes: exact agreement with the classes from the measured speeds; **optimistic misclassifications** (simulated class better than measured, by one class or more); conservative misclassifications;
  - safety: points the measurements put at "limited risk" or "dangerous" that the model puts at "no risk" (**missed danger**), and the reverse.
- Add the test to `validation/run_wake_validation.py` (a `comfort classes` report) with tests in `validation/tests/test_wake.py`; it needs no new runs.
- Record today's numbers before any change: they are the baseline every later step must beat.

### C2. The scalar speed for comfort

- √(|u|² + 2k) is the root-mean-square of the instantaneous speed. An omnidirectional sensor, and the hourly mean of the comfort criteria, are the time mean of the instantaneous speed, which is lower; the difference is largest where the mean is small.
- Add a mean-speed estimate: the expected |U| for a Gaussian velocity with the model's mean vector and k, split over the components as 2.4 : 1.9 : 1.25 in standard deviation (the surface-layer ratios behind the 5.5 u*² rule). Computed once per cell in Python; no native change.
- Choose the comfort comparator from the instrument physics and the criteria's definitions, documented with sources. Report both estimates on Cases A, B, D and E and in C1, but do not choose by score.
- If the comparator changes, the comfort option gains it (for example `speed="scalar_mean"`) and `scalar_speed()` stays as it is.

### C3. Diagnose the windy-point bias

- Take the windiest tenth of the Case E after probe-directions, and of Case D.
- For each point, record:
  - the distance to the new high-rise and to the nearest wall;
  - whether it lies in a corner stream, a wake, a canyon or the open;
  - K for `wake=2` and `wake=3`;
  - D and k_w at the point;
  - the building whose wake (or cavity) sets D there.
- Separate the candidate causes with diagnostic runs of a scratch build (not committed, like the prototype; no environment switches in the product):
  - **H1, missing speed-up:** both codes too slow at the same points → the tower effect, corner streams or downwash.
  - **H2, over-sheltering:** `wake=3` much slower than `wake=2` at a point → run `wake=3` without the shelter factor, and with the deficit limited to the shadow (no lateral spreading), to see which part removes the speed.
  - **H3, comparator:** the bias shrinks with C2's estimate.
  - **H4, direction thresholds:** the bias concentrates near ±10° from a face normal.
- Write the attribution (share of the windy-point bias per cause) to the results file. C4's remedy follows from it.

### C4. Remedy

Depends on C3; at most one remedy at a time, each with its own check.

| Finding | Remedy | Where |
|---|---|---|
| H2 dominates | Limit sheltering (for example, no shelter for buildings taller than the sheltering wake's top, or a cap on D in corner streams), from first principles; the A and B scores must not drop | `winds/SpreadingWake`, `applySpreadingWake` |
| H1 dominates | The tower-effect / corner-stream model of `MOMENTUM_PLAN.md` (F08) | a separate plan; the switch waits for it |
| H3 dominates | The comparator from C2 | Python only |
| H4 contributes | Review S3 (continuous direction thresholds) | a separate plan |

**Gate for C4** (Cases D and E, 2 m, turbulence on, against the C1 baseline):
- at the windiest tenth of every case, the mean speed is no more optimistic than `wake=2` vector and the share more than 20 % too slow is no larger;
- C1 on all three climate levels: optimistic misclassifications and missed danger no more frequent than with `wake=2` vector, exact agreement higher;
- the wake plan's section 6 gates still pass.

### C5. Independent confirmation

- Obtain the dataset of D4; build its geometry, inflow and probes in the harness (like `case_d`, `case_e`).
- Write its gates **before** the first run: the C4 gate's three conditions, applied to this dataset, with no tuning on it.
- If the dataset has fewer than 16 directions, C1's comfort test runs with the directions it has; the windy-tail and pooled scores carry the decision.

### C6. Policy qualification (`pedestrian-v2`)

- Recalibrate the adaptive policy on `wake=3` fields with the S7 tooling (`tools/run_solver_policy_study.py`, `calibrate_solver_policy.py`, `validate_solver_policy.py`, `publish_solver_policy.py`): calibration and held-out cases, thresholds, frozen workers and evidence, as in `docs/solver-control-s7.md`.
- `pedestrian-v2` accepts `wake_flag == 3`; `pedestrian-v1` stays frozen and selectable.
- Then re-qualify the native identity (`docs/solver-control-requalification.md`).

### C7. The switch

- `wind.run` default `Parameterizations(wake=3)` for the pedestrian path; the decision whether the general default also changes is taken with D1. `comfort.assess_results` default `speed` per criterion (D1); `Solver(policy=...)` default to `pedestrian-v2`.
- Re-baseline the feature-merge fixtures and the AIJ headline numbers; a migration note listing the expected class changes (C1's statistics on Case E) and how to restore the old behaviour (`wake=2`, `speed="vector"`, `pedestrian-v1`).
- Update `README.md`, `docs/spreading-wake.md`, `docs/wind-comfort.md`.

## 5. Rules

- **No fitting to the test cases.** Constants change only from first principles or Cases A and B; Cases D and E judge, C5 confirms.
- **Safety first.** A change that lowers optimistic misclassifications or missed danger is preferred over one that raises exact agreement.
- **One remedy at a time.** Each C4 change is measured alone against the C1 baseline before another is added.
- **Gates before runs.** C5's gates are written into this file before its first run.

## 6. Gates (summary)

| Step | Gate |
|---|---|
| C1 | Baseline recorded for four models, two states, three climate levels; tests pass |
| C2 | Comparator chosen and justified from instrument physics and the criteria, not by score |
| C3 | Windy-point bias attributed to causes, with the share of each |
| C4 | Windiest tenth no more optimistic than `wake=2` vector in any case; no more optimistic misclassifications or missed danger; higher exact agreement; wake plan gates still pass |
| C5 | The same three conditions on the independent dataset, gates fixed in advance |
| C6 | `pedestrian-v2` qualified on calibration and held-out cases; native identity re-qualified |
| C7 | Fixtures re-baselined; migration note with Case E class-change statistics |

## 7. Risks

| Risk | Mitigation |
|---|---|
| C3 finds the tower effect (H1) dominant | The switch waits for the tower-effect work; `wake=3` stays the recommended opt-in for sheltered areas |
| No independent dataset (C5) | The switch waits. Case E alone is too thin, and C4 will have been judged on it |
| The comfort result depends on the climate | Three declared climate levels (D3), gates on all three |
| Low-speed thermistor readings are uncertain | The windy-tail and comfort gates use the windy points and class boundaries; the low-speed bins are reported, not gated |
| C2 changes the level everywhere | C2 precedes C4, so C4's remedy is judged with the final comparator |
| The default change moves every result | C7 is a separate step with a migration note and the old behaviour one argument away |

## 8. Done when

- C1's comfort-class test and the windy-tail report are part of `validation/run_wake_validation.py`, with tests;
- the comfort comparator is decided and documented (C2);
- the windy-point bias is attributed (C3), and either remedied (C4) and confirmed (C5), or the switch is recorded as waiting for the named work (the tower effect, a dataset);
- if confirmed: `pedestrian-v2` is qualified (C6) and the defaults are switched with a migration note (C7).

## 9. Progress

Each step's outcome, in order.

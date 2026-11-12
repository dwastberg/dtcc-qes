# Wake update v2: validation results (step W4)

- **Date:** 2026-11-12. Step W4 of [`WAKE_UPDATE_V2.md`](../WAKE_UPDATE_V2.md), section 6.
- **Build:** branch `feat/wake-update-v2` at `2387533` (native code as of `396f152`, W1d), native policy identity `6e072763067b…` (unqualified during these runs; re-qualified afterwards for the default `wake=2`, last section).
- **Runs:** `validation/run_wake_validation.py --jobs 1`: the baseline matrix with turbulence on and the fixed-work solver (Cases D and E at 2 m, 35 runs; Cases A and B at 2 m and 1 m), each with `wake=3` and with the default `wake=2` as the reference; A and B at 1 m with the rooftop vortex and the high-rise model; probe-history runs; `--grid` for A and B at 4 m and 0.5 m. One run at a time on 14 cores, so the wall times are cost evidence. Summary: `validation/output/wake/summary.json`.

## Outcome

**Every gate passes**, and every gated score improves on `wake=2`. The default nevertheless stays `wake=2`; the reason is in the last section.

## Gates

The scalar rows use `K_scalar_wake`: √(|U|² + 2k)/U_ref with k = k_in (1 − D)² + k_w and k_in the tunnel inflow table at the probe height. The `wake=2` column uses √(|U|² + 2 k_in) (the investigation's "inflow k" reference), since `wake=2` has no wake fields.

| Case | Quantity | Grid | Score | Gate | `wake=3` | `wake=2` | Pass |
|---|---|---|---|---|---|---|---|
| A | \|U\|/U_H | 2 m | q | ≥ 0.71 | 0.737 | 0.683 | yes |
| A | \|U\|/U_H | 1 m | q | ≥ 0.67 | 0.704 | 0.661 | yes |
| A | \|U\|/U_H | 2 m | R | ≥ 0.90 | 0.927 | 0.887 | yes |
| A | \|U\|/U_H | 1 m | R | ≥ 0.88 | 0.914 | 0.864 | yes |
| B | \|U\|/U_H | 2 m | q | ≥ 0.64 | 0.670 | 0.504 | yes |
| B | \|U\|/U_H | 1 m | q | ≥ 0.62 | 0.647 | 0.513 | yes |
| B | \|U\|/U_H | 2 m | R | ≥ 0.91 | 0.936 | 0.744 | yes |
| B | \|U\|/U_H | 1 m | R | ≥ 0.90 | 0.933 | 0.733 | yes |
| A | scalar speed, 2 m probes | 2 m | q | ≥ 0.83 | 0.862 | 0.769 | yes |
| B | scalar speed, 2 m probes | 2 m | q | ≥ 0.86 | 0.891 | 0.566 | yes |
| D | split fibre, mean vector | 2 m | MAE | ≤ 0.15 | 0.138 | 0.170 | yes |
| D | thermistor, scalar | 2 m | q | ≥ 0.38 | 0.409 | 0.308 | yes |
| D | thermistor, scalar | 2 m | R | ≥ 0.52 | 0.548 | 0.425 | yes |
| E before | thermistor, scalar | 2 m | q | ≥ 0.27 | 0.302 | 0.140 | yes |
| E before | thermistor, scalar | 2 m | R | ≥ 0.52 | 0.548 | 0.522 | yes |
| E after | thermistor, scalar | 2 m | q | ≥ 0.43 | 0.462 | 0.318 | yes |
| E after | thermistor, scalar | 2 m | R | ≥ 0.52 | 0.554 | 0.472 | yes |
| E change | scalar | 2 m | R | ≥ 0.45 | 0.477 | 0.436 | yes |

The margins are 0.02–0.04 above each gate (the gates are the prototype's values less 0.03), so the implementation reproduces the prototype's scores within about 0.01.

## Reported without a gate

### The inflow k: tunnel table against 5.5 u*² (section 3.4)

q / R / FB of the scalar speed at 2 m:

| Inflow k | A | B | D | E before | E after |
|---|---|---|---|---|---|
| Tunnel table | 0.862 / 0.912 / +0.10 | 0.891 / 0.890 / +0.04 | 0.409 / 0.548 / +0.30 | 0.302 / 0.548 / −0.32 | 0.462 / 0.554 / −0.06 |
| 5.5 u*², fitted (the run's default) | 0.877 / 0.923 / +0.08 | 0.907 / 0.910 / +0.01 | 0.424 / 0.551 / +0.31 | 0.323 / 0.549 / −0.31 | 0.463 / 0.559 / −0.05 |

The rule is within 0.02 of the table everywhere, slightly better in every case: section 3.4's finding holds for the implementation.

### Case E change

| Model | R | Sign agreement | Top-10 overlap | MAE |
|---|---|---|---|---|
| `wake=3`, table inflow k | 0.477 | 0.688 | 0.531 | 0.138 |
| `wake=3`, 5.5 u*² | 0.487 | 0.696 | 0.537 | 0.137 |
| `wake=3`, QES-Turb k | 0.294 | 0.645 | 0.394 | 0.166 |
| `wake=2`, inflow k | 0.436 | 0.728 | 0.587 | 0.141 |
| `wake=2`, QES-Turb k | 0.401 | 0.734 | 0.425 | 0.142 |

As in the investigation (0.69 / 0.52 against 0.73 / 0.59): the spreading wake correlates better with the measured change but agrees slightly less often on its sign and on the ten largest changes.

### The mean vector and QES-Turb on the new field

| Case | `wake=3`: \|U\| q / R / FB | `wake=2`: \|U\| q / R / FB | `wake=3`: QES-Turb scalar q / R | `wake=2`: QES-Turb scalar q / R |
|---|---|---|---|---|
| A | 0.737 / 0.927 / +0.06 | 0.683 / 0.887 / −0.08 | 0.708 / 0.852 | 0.714 / 0.791 |
| B | 0.670 / 0.936 / +0.01 | 0.504 / 0.744 / −0.22 | 0.527 / 0.886 | 0.550 / 0.722 |
| D (split fibre / thermistor) | 0.242 / 0.565 / +0.07 | 0.273 / 0.549 / −0.23 | 0.222 / 0.298 | 0.265 / 0.409 |
| E before | 0.378 / 0.541 / −0.11 | 0.156 / 0.514 / −0.43 | 0.319 / 0.383 | 0.076 / 0.334 |
| E after | 0.329 / 0.456 / +0.26 | 0.299 / 0.457 / −0.15 | 0.378 / 0.295 | 0.242 / 0.315 |

- FB is (measured − simulated) / mean, so a negative FB is too fast. `wake=2` is too fast in every case; `wake=3` removes more momentum, because its wake spreads across the wind and reaches further. At the pedestrian probes the mean K falls by 0.07–0.08 in A, B and D (0.30 → 0.22 in D) and by 0.15 in Case E (0.51 → 0.35); 68 % of the Case E probe-directions drop by more than 0.1, and almost none rises by that much. `wake=3` is then close to the measured level in A, B, D and E before and too slow in E after.
- The scalar speed is a median 1.1 (A), 1.3 (B), 1.5 (D) and 1.2 (E) times the vector speed, and 2.6–4 times at the 90th percentile (the stillest points). It is the speed that matches the omnidirectional measurements, and it restores the level the lower vector speed loses.
- QES-Turb's own k, recomputed on the smoother field, does not benefit: its scalar speed correlates less well in D and E after. Its k against the split-fibre k (q / R / FB): A 0.013 / 0.35 / −1.21 (`wake=2`: 0.104 / 0.18 / −1.01), B 0.011 / 0.05 / −1.01 (0.026 / 0.10 / −0.71), D 0° 0.00 / −0.12 / +1.27 (0.030 / 0.09 / +1.16). The wake turbulence k_w, not QES-Turb, carries the scalar speed.

### Cases A and B at 1 m with the cavity variants

| Variant | A q / R | B q / R | Reattachment at 2 m (H): A, B |
|---|---|---|---|
| `wake=3`, rooftop vortex | 0.688 / 0.934 | 0.652 / 0.958 | 0.90, 1.96 |
| `wake=2`, rooftop vortex | 0.656 / 0.889 | 0.509 / 0.844 | 1.00, 2.10 |
| `wake=3`, high-rise model | 0.747 / 0.910 | 0.594 / 0.917 | 0.67, none |
| `wake=2`, high-rise model | 0.672 / 0.826 | 0.424 / 0.596 | 0.69, none |

The spreading wake improves both variants as much as the default; the far wake no longer depends on the cavity's modified height (section 3.1).

### Iterative convergence

Iterations until the probe K stays within 0.005 (p95) and 0.02 (max) of the run's own end point (8000 iterations, no turbulence, 2 m):

| Run | `wake=3` | `wake=2` |
|---|---|---|
| A | 175 | 175 |
| B | 275 | 250 |
| D 0° | 450 | 450 |
| E N, after | 325 | 275 |

The fixed-work budget (2000 iterations at 2 m) covers both with a wide margin. The adaptive policy is qualified for `wake=2` only.

### Cost

Mean per Case E direction at 2 m (32 runs each, 1.8 M cells, turbulence on, default thread team): native initialization (which contains the parameterizations) 0.249 s with `wake=3` against 0.057 s with `wake=2`, **+0.19 s** (target +0.5 s; W1d measured +0.23 s with 8 threads); wall time per run 6.76 s against 6.50 s.

### Grid study, Cases A and B

\|U\|/U_H, q / R (turbulence on; 4 m: 0.1 M cells, 0.5 m: 55–58 M cells and about 5 min per run):

| Grid | A, `wake=3` | A, `wake=2` | B, `wake=3` | B, `wake=2` |
|---|---|---|---|---|
| 4 m | 0.785 / 0.924 | 0.774 / 0.882 | 0.656 / 0.913 | 0.518 / 0.760 |
| 2 m | 0.737 / 0.927 | 0.683 / 0.887 | 0.670 / 0.936 | 0.504 / 0.744 |
| 1 m | 0.704 / 0.914 | 0.661 / 0.864 | 0.647 / 0.933 | 0.513 / 0.733 |
| 0.5 m | 0.688 / 0.905 | 0.667 / 0.840 | 0.647 / 0.931 | 0.504 / 0.725 |

`wake=3` is better at every spacing, most for B. Its correlation hardly moves from 4 m to 0.5 m; q falls by about 0.1 for A, as with `wake=2` (in A the near-wall points sharpen with refinement).

## The default stays `wake=2`

The gates pass, so the plan's W6 would switch the default. It is not switched, because the plan's re-qualification step cannot qualify that switch:

- The adaptive `pedestrian-v1` policy is defined for `wake_flag == 2` (`src/qes_core/dtcc/pedestrian_policy.cpp`), and its frozen S7 evidence runs `wind.run` with the default parameterizations.
- `tools/check_policy_compatibility.py`, and the procedure in `docs/solver-control-requalification.md`, re-qualify a native identity only when every frozen worker reproduces its fields, diagnostics and decisions exactly. With `wake=3` as the default every field hash changes, so the check fails by construction.
- Switching the default without re-qualifying would make every default adaptive run `unqualified_model_settings`; accepting `wake=3` in the policy without a study would claim a qualification that no evidence supports.

Switching therefore needs a new policy qualification on `wake=3` fields (an S7-style calibration and held-out study), which is outside this plan. That is a decision for the maintainers; until then `wake=3` stays opt-in and the comfort option stays `speed="vector"` by default (D4).

## Native identity re-qualification (default `wake=2`)

The branch's native edits disabled adaptive acceptance until its identity was re-qualified. Done on 2026-11-12 by the procedure of `docs/solver-control-requalification.md`, for candidate `cfd0c1f` (identity `6e072763067beed0fdced05d906f7be9172fa9f78c85ca72f6eaf3c19e823de3`, previously `04c8ce76…` on `main`). Evidence: `docs/data/wake-update-v2/` (`requalification.json`, `native-build-identity.txt`, `s7-workers.json`, `compare-native.json`).

| Stage | Result |
|---|---|
| Fresh Release builds, CTest | OpenMP 62/62, serial 59/59, ASan/UBSan 59/59; `check_native_symbols` passes; serial and OpenMP identities equal |
| `compare_native_builds.py` against `main`, OpenMP at 1, 2, 4 and 8 threads and serial, backend parity required, identity pair declared | 509 cases each; thread teams and backends identical; 22 differing records, all in the declared W1b cases (exposed-face slab gap and courtyard, codes 1 and 2) |
| Isolated copy with the new identity in the qualification header | identity unchanged, build supported, serial and OpenMP |
| 24 frozen S7 release workers (`check_policy_compatibility.py --allow-disabled-turbulence-monitor`) | all match exactly |
| Combined feature baseline against `main`, non-adaptive and adaptive | no differences |
| `pytest -W error` on both isolated packages, native executables set | 1974 passed, 16 skipped, each |
| sdist and wheel from the sdist, `check_artifacts.py`, `wheel_runtime_smoke.py` (4 threads) | pass; adaptive run accepted |

The identity was then promoted in `src/qes_core/dtcc/pedestrian_qualification.h`; the rebuilt production extension reports the same identity and build support, and every suite passes. This qualifies the branch with the default `wake=2`; it does not qualify `wake=3` for the adaptive policy.

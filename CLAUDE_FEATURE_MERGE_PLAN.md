# Make solver controls, turbulence and wind profiles work as one tool

Status: review and plan written 2026-10-31. Revised the same day after comparison with `ASTRA_FEATURE_MERGE_PLAN.md`, and again after ASTRA's own revised plan. Nothing is implemented yet.

## Context

Three features were built on separate branches and merged one after another:

- **Solver**: `SolverControl`/`MonitorSpec`, bounded and adaptive `pedestrian-v1` modes, and float64.
- **Turbulence**: QES-Turb. `Turbulence`, `TurbulenceFields`, domain growth and GEM screening.
- **Wind profiles**: `Log`/`Measured`/`PowerLaw`/`UniformProfile` and a native layer table.

All three are reachable from `wind.run`, but each was attached separately, with its own code paths, its own way of describing maturity, and only partial reach into the dataset and comfort modules. The goal is for them to read and behave as one tool.

Decisions (2026-10-31):

- **Breaking changes are allowed.** Breaking the public API, or changing results slightly, is acceptable when it gives better results or cleaner code. This replaces the earlier "internal + additive" scope.
- **`run()` takes one spec per feature**: a profile for the inflow, a `Solver` for every solver setting, and `Turbulence | None`.
- **Add a results→comfort adapter** and `profile.with_direction()`. Each direction still gets its own fresh solve.
- **Add turbulence to the `qes_wind` dataset.**
- **Align `log_law_transfer` with the solver's log law, ln((z+z0)/z0), on the side that produces the QES inflow.** The function converts a weather-station wind into a QES inflow reference speed. Its target side must match the inflow it feeds. Its station side describes a real measurement and keeps the meteorological ln(z/z0). This narrows the earlier "switch both sides" plan after ASTRA's F9.
- **Native consolidation is the last phase, followed by re-qualification.**
  - CMakeLists.txt:91-109 hashes every `.h/.cpp` under `src/qes_core` and `src/cpp`, plus both CMakeLists files and the compiler flags, into `solver_policy_revision`.
  - Any native edit disables adaptive acceptance until `pedestrian_qualified_revision` is updated.
  - So all native work is batched into Phase 9. It must leave every adaptive-eligible output bit unchanged and ends with re-qualification.
  - Phases 0–8 change only Python, docs, tests and tools.

## Findings

### How the features interact today

| Combination | What happens now |
|---|---|
| Profiles + turbulence | Works. Metadata records a caveat (friction velocity comes from a log-law conversion). |
| Profiles + bounded controls | Works. The monitor normalises by the profile's reference speed. |
| Profiles + adaptive | Runs, but is never accepted (`unqualified_inflow_profile`). Documented only in docs/wind-profiles.md:134-140. |
| Turbulence + adaptive | Runs, but is never accepted (`turbulence_outside_assessment_scope`, pedestrian_policy.cpp:21). No .md file mentions this reason. |
| Turbulence + bounded controls | Turbulence is computed even on a wind solution stopped by the time limit. Nothing records this. Untested. |
| Dataset | Accepts profile and solver_control. No turbulence. Uses different solver defaults from `run()` (finding 13). |
| Comfort | Every user writes about 40 lines of glue (examples/wind_comfort.py). There is no way to rotate a profile for each direction. |
| All three together | No test and no example. The README has no solver-control section and no snippet. |

An unsupported adaptive request keeps `mode="adaptive"` in its record but runs the bounded/legacy-tolerance path with relaxation 1.78 instead of 1.90. Native code reports only the first failing scope check, and only after preparation and the solve, so users find out about the exclusion late.

### Duplicated code and inconsistencies in `src/`

1. The profile record is built in two places:
   - inline for log profiles at wind.py:138-147;
   - via `_layer_record` for other profiles at wind.py:292-295.

   `native_reference_scalars` is set twice, and `effective_condition` and `boundary_layer` are patched afterwards (wind.py:216-221).
2. Legacy scalar inputs are validated by `wind._validate_condition`, while `LogProfile` validates itself in `__post_init__`. The float32 log checks and their messages are duplicated.
3. There are five scalar validators with slightly different semantics and messages:
   - `_city.number`
   - `profiles._number`
   - `solver_control._number`/`_integer`
   - `comfort._number`
   - the `_AutoSettings.__post_init__` loop
4. `datasets._field_slice` reimplements speed-up and solid validity (datasets.py:341-346) instead of using `WindResult.reference_speed` and `solid_mask`.
5. Two log-law forms are in use:
   - `comfort.log_law_transfer` uses ln(z/z0) on both its station side and its target side;
   - the solver inflow, `LogProfile` and the README formula (README.md:526) use ln((z+z0)/z0).

   So the reference speed that `log_law_transfer` hands to QES follows a different law from the inflow profile QES then builds. The difference is about 0.2% at z0 = 0.1 m and several percent for rough sites. ASTRA's example, a 10 m transfer from z0 = 0.03 m to 0.5 m with a 60 m blending height, moves the multiplier from 0.818744 to 0.830265 (+1.41%) when both sides are switched. On the station side the shift is negligible for open-terrain stations (about 0.05% at z0 = 0.03 m) and has no model basis, so only the target side should change.
6. The automatic grid's `pedestrian_sampling` K metadata (_city.py:354-368) assumes a log profile even when a non-log profile is used. With `UniformProfile` it reports `flat_profile_exact_K ≈ 0.601` at 1.5 m; the true ratio is 1.0. Archived evidence (`docs/data/solver-control-s0/runs/*.json`) contains these fields for log profiles.
7. Turbulence metadata does not record which wind solution it came from: converged, time-limited or unaccepted. The domain-growth explanation does already exist: `_city.py:339-345` records `default_top`, `effective_top`, `raised`, `added_layers` and `extension_policy`.
8. A measured profile with `above="error"` fails after turbulence raises the domain top, and the error does not mention turbulence.
9. Maturity is reported in four different ways:
   - `experimental` on profiles;
   - "provisional"/"screening" on turbulence;
   - `accepted`/`accuracy_status` on solver controls;
   - `policy_status` on vertical grids.

   The no-controls mode is called "legacy" in some places and "disabled" in others.
10. The turbulence reference (z_ref = 3·mean building height, and with it z0 = 0.1·H and d = 0.7·H) and the margin extension exist in **three** places:
    - Python `_turbulence_domain.py` plans the domain growth;
    - `dtcc/turbulence.cpp:43` (`check_turbulence_margin`) guards it;
    - vendored `winds/TURBGeneralData.cpp:186-191` computes the reference the model uses.

    All three are native or tied to native code, so the cleanup is in Phase 9.
11. Specs serialize inconsistently:
    - profiles have `to_dict`/`profile_from_dict` with a `schema_version`;
    - `SolverControl` has only `from_dict` (datasets.py uses `asdict`);
    - `Turbulence` has neither;
    - `VerticalGrid` has only `to_metadata`.
12. Smaller naming inconsistencies:
    - the run argument `solver_control=` and `metadata["solver_control"]` are read through the property `result.control`;
    - profile metadata uses `type` while the JSON payload uses `kind`;
    - the caveat is `turbulence_caveat` in the profile record and `profile_caveat` in turbulence metadata.
13. Dataset and run defaults differ, so the same request behaves differently depending on the entry point:

    | Setting | `wind.run` (wind.py:42) | Dataset (datasets.py:89-91) |
    |---|---|---|
    | tolerance | 1e-5 | 1e-4 |
    | max_iterations | 500 | 1000 |
    | max_cells | 20M | 200M |
14. `WindResult.to_dtcc()` runs the stress eigensolver twice: `_stress_validity` at result.py:397, then again inside `self.streamwise_std` → `_streamwise_std`.
15. The run signature splits the solver across two places: `tolerance`, `max_iterations`, `solver_precision`, `raise_on_nonconvergence` and `raise_on_unaccepted` are `run()` kwargs, while budget, monitor and mode live in `SolverControl`. `run()` also rejects some combinations of the two (wind.py:125-130). `roughness_length` means the profile's z0 for `LogProfile` but ground roughness for every other profile.
16. `max_solve_seconds` covers only the native solve. Preparation, turbulence and transfer run outside it, and nothing records the time of the whole public call. Native code already measures 13 phase timings, from `preparation_seconds` through `native_total_seconds` (control_bindings.h:136-137). It returns them only inside the solver-control record, so legacy runs have no timings at all.
17. `preview_grid` without a profile passes speed 0 and direction 0 as placeholders (wind.py:264-266). Nothing breaks today, because previews of log runs record no profile. But once every profile kind gets a record (Phase 2), a grid-only preview would describe itself as a calm log inflow. A preview without a profile must record the inflow as unknown.
18. The dataset works out its own domain top. For 4-coordinate bounds, `_dataset_city.prepare_city` computes `ground + default_domain_top(...)` without the turbulence reference (_dataset_city.py:101). It then passes 6-coordinate bounds to `run()`. `run()` accepts only 6-coordinate bounds (wind.py:396-398) and treats every top as fixed by the user, so a computed top can never grow for turbulence.
19. The dataset keeps a second copy of the profile schema as typed payload dicts (`_ProfilePayload`, `_AnalyticPayload`, `_MeasuredPayload`, datasets.py:21-64) next to the profile dataclasses. Nothing checks that the two stay in step.
20. Python tests cannot drive deadlines deterministically. The native runner takes a `native_test_clock` (api/wind_runner.h:21), but it is not bound to Python. Python deadline tests use a 1e-12 s budget, which stops before the first sweep (tests/test_solver_control.py:50).

### Duplicated helpers in tests and tools

- **Case builders**
  - The 2×2 "tower" city is built in five places:
    - tests/test_adaptive_control.py:17-23
    - tools/wheel_runtime_smoke.py:22-26
    - tools/run_auto_grid_controls.py:35-52
    - tests/test_sampling.py:194-201
    - tests/native/check_pedestrian_policy.cpp:54-57

    tests/test_turbulence_domain.py:17-27 is a parameterised variant.
  - The ONE_BUILDING footprint is hardcoded again instead of using tests/fixtures/cases.py:103:
    - tools/verify_wind_profiles.py:27-33
    - tools/compare_native_builds.py:228
    - tests/native/check_turbulence.cpp:59-60
  - The native three-block contract is duplicated between tests/test_condition_state.py:8-44 and tools/compare_native_builds.py:195,269-298.
- **Feature settings**
  - `TurbulenceSettings` is built in eight places, for example tests/test_runner.py:54-58, tests/test_turbulence_domain.py:168,236,256 and tools/run_turbulence_benchmark.py:221.
  - `SolverControl` settings are built in tests/test_solver_control.py:18-20, tests/test_adaptive_control.py:26-28 and tools/wheel_runtime_smoke.py:27-29. The last two are identical.
  - The "qualified build" and toolchain-parity gates are copied in tests/reference_checks.py:14-18, tests/test_turbulence.py:519-522 and tests/test_turbulence_reference.py:29-35.
- **Reference comparisons and oracles**
  - The legacy npz comparison is in tests/test_runner.py:34-39 and tests/test_wind.py:25-30.
  - The audited turbulence npz comparison is in tests/test_turbulence_reference.py:45-56 and tests/test_turbulence.py:532-536.
  - The analytic covariance oracle is in tests/test_turbulence.py:252-261 and tests/test_turbulence_reference.py:129-139.
  - The stress-validity eigen check duplicates `result._stress_validity` in tests/test_runner.py:111-115, tools/check_stress_validity.py:52-55 and tools/run_turbulence_benchmark.py:112-129.
  - Synthetic `WindResult`/`TurbulenceFields` objects are built in tests/test_sampling.py:16-24, tests/test_dataset_vertical_grid.py:15-28 and tests/test_turbulence.py:24-33. Some pass positional arguments, which is fragile.
- **Statistics and plumbing**
  - The delta-K p95 statistic is computed in three tools, and the denominators differ (tools/check_turbulence_domain.py:72-78 differs from the other two).
  - The tail extension is duplicated in tools/check_turbulence_domain.py:40-47 and tools/run_turbulence_benchmark.py:178-183.
  - Other repeated plumbing:
    - the `TrackedRunner` wrapper;
    - the "no native allocation" monkeypatch;
    - the thread-deadlock subprocess scripts;
    - the `spec_from_file_location` tool loader (about 25 test files);
    - tests importing other test modules (test_comfort→test_turbulence→test_sampling, test_solver_control→test_condition_state).
- **Reimplementations of `run()`**: tools/run_turbulence_benchmark.py:214-254 rebuilds `wind.run` step by step from private functions, so changes to `run()` do not show up in the benchmark.
- **Cross-feature test coverage**
  - Present:
    - profiles + turbulence, checked for finiteness and caveat only (tests/test_profiles.py:149-159);
    - turbulence + adaptive is unaccepted (tests/test_adaptive_control.py:82-88);
    - a native layer table + adaptive is unaccepted (tests/native/check_pedestrian_policy.cpp:80-87);
    - a native layer table + bounded control (tests/test_profiles.py:192-200).
  - Missing:
    - all three together;
    - turbulence + bounded controls;
    - public `run(profile=..., solver_control=...)`;
    - LogProfile versus legacy with turbulence;
    - profile + turbulence on nonuniform grids, in float64, or through sampling/export;
    - comfort GEM from a non-log profile;
    - dataset turbulence.

Each evidence archive under `docs/data/*/sources` keeps its own copy of the tools and sources it was produced with, so the live tools can be refactored without losing audit value.

### Documentation

- README.md reads as a milestone log:
  - "Wind profiles" comes before "Build and install".
  - Solver controls appear only as prose under "OpenMP" (README.md:89-131), with no snippet.
  - Turbulence is mixed into "Run a city" (README.md:243-298).
- Stale README text:
  - The options table (README.md:586-591) says speed/direction are required and omits profile, turbulence, solver_control and raise_on_unaccepted.
  - Dataset speed-up is described as "divided by wind_speed" (README.md:432).
  - The field names (README.md:411) omit speedup.
  - The deferred list (README.md:764-765) conflicts with README.md:288.
- README.md:121-122 implies adaptive acceptance works with turbulence on; the code rejects it.
- Stale plan-doc status lines:
  - QES_TURBULENCE.md:257-265 and :1051;
  - SOLVER_CONTROL_REFACTOR.md:64-66;
  - docs/solver-control-s7.md:19.

  None of the three plan docs points to the others.
- There is no written procedure for re-qualifying the adaptive policy after a native change.
- Examples:
  - None uses `SolverControl`.
  - None combines more than turbulence + comfort.
  - examples/city_dataset.py has no profile or turbulence option.

## Comparison with ASTRA_FEATURE_MERGE_PLAN.md

Both plans reviewed the same revision (3ae4157). I checked ASTRA's claims against the code before taking them.

### Taken from ASTRA

1. Dataset and run defaults differ (now finding 13).
2. `to_dtcc()` runs the eigensolver twice (now finding 14).
3. A third copy of the turbulence reference in vendored `TURBGeneralData.cpp` (now part of finding 10).
4. **Keep five things apart in the result:** execution status, legacy convergence, numerical assessment (`not_requested` / `accepted` / `unaccepted`), field validity, and model qualification. Never report "accepted" for a legacy or bounded run. This replaces the `accepted` field the earlier version of this plan had for every mode.
5. **Report adaptive eligibility before the run**, listing every exclusion reason, with the native rules staying authoritative (Phase 9).
6. **More detail for the K diagnostics:** a vector error for turning profiles, and null with a reason for a calm reference.
7. **Record a contract baseline before refactoring** (ASTRA Stage A; Phase 0 here).
8. **More test invariants:**
   - turbulence on/off on a frozen grid leaves the mean wind unchanged;
   - controls do not change the fields when the completed work is the same;
   - alternating log and table profiles with turbulence on do not leak condition state;
   - calm, turning, jet, stretched-grid and float64 cases.
9. **Timing scope:** document it and record the time of the whole public call (now finding 16).
10. **Comparison rule:** turbulence can grow the domain, so every turbulence on/off comparison must use an explicit grid.
11. **Cache identity covers the turbulence numerics version.**
12. **Stage G** as a follow-up: a separate study of mean-wind acceptance with turbulence on.

### Not taken

- **Five new private types** (`ResolvedRunRequest`, `PreparedRunDescription`, `ExecutionAssessment`, `ModelContext`, `OutputContext`). Most of their content already exists: the domain-growth record (_city.py:339-345), `metadata["turbulence"]["reference"]` and the profile record. Specs per feature plus one qualification record cover the rest.
- **Provenance on `WindSample`.** The comfort adapter takes whole results, so samples don't need it.
- **A three-way versioned dataset turbulence request.** `Turbulence.to_dict()` or `None` is enough.
- **The Stage F performance campaign and memory estimates.** Out of proportion for this work; Phase 0's bitwise comparison and `compare_native_builds` cover regressions.

### Reversed now that breaking changes are allowed

- **ASTRA:** keep compatibility views, keep the dataset's historical defaults, and label the old K fields instead of replacing them.
- **This plan's earlier version:**
  - keep private signatures, error messages and the `_layer_record` alias stable;
  - leave the evidence tools untouched;
  - make no native changes at all.

### In this plan but not in ASTRA's first version

- the `log_law_transfer` mismatch;
- `with_direction`;
- the 13 groups of duplicated test and tool helpers;
- the stale README and plan-doc text;
- the maturity vocabulary;
- the inconsistent spec serialization;
- the examples.

### Second round: ASTRA's revised plan

ASTRA revised its plan using this one and the breaking-change decision. It now adopts the shared profile record, a growable computed top for the dataset, `with_direction`/`reference_direction`, fixture consolidation and an integrated guide. The two plans now agree on the main design. ASTRA states principles and evidence gates; this plan names the concrete API, files and steps.

**Taken from the revision** (checked against the code):

1. A grid-only preview must record the inflow as unknown, not as a calm wind (finding 17; Phases 1–2).
2. Keep a fixed top apart from a computed top, and let only a computed top grow. Here this becomes `bounds` with `zmax=None`. That replaces this plan's earlier private "top policy" flag and the dataset's own top calculation (finding 18; Phases 1 and 5).
3. `log_law_transfer`: change only the target side, measure how comfort classes change, and never apply the conversion to non-log profiles (finding 5; Phase 4).
4. Choose the shared solver defaults from measured accuracy and cost against a tightly converged reference. This replaces the earlier rule "raise `max_iterations` if it does not converge" (Phase 5).
5. Test combined states: accepted but not converged under the legacy tolerance, and time-limited but converged under it (Phase 7).
6. Test oracles stay independent of production code. Duplicated oracles are merged into one test-side module, not replaced by calls to `result._stress_validity` (Phase 7).
7. A parity test between a direct run and a dataset run with the same prepared geometry and settings (Phase 7).
8. Report phase timings for every solver mode, with stated inclusion rules, not just the total (finding 16; Phase 3).
9. A parity test between the dataset's payload schemas and the specs' `from_dict` (finding 19; Phase 5).
10. One rule for accepted number types: reject booleans, strings and arrays; check float32 range only where native code needs it (Phase 6).
11. State how each intended result change will be judged before updating any expected value. A result that differs is neither a failure nor an improvement on its own (Phase 0).
12. Record which requirement set the domain top (Phase 3), and check that runs don't allocate turbulence arrays or monitor histories they don't need (Phase 7).

**Still not taken:**

- **Sending log profiles through the native layer table** (ASTRA §6, Stage B). This would change every field adaptive mode currently accepts. pedestrian-v1 would then need a fresh calibration, not just a parity check and a new hash. The native log code it would remove is small. Listed as a follow-up, batched with Stage G, which needs new calibration anyway.
- **Native work before the downstream work** (ASTRA Stage C before Stage E). That leaves builds without adaptive acceptance in between; ASTRA §9 itself says such a build must be flagged as incomplete. Here all native work is the last phase, so the build stays qualified until then.
- **An optional higher-precision rewrite of the turbulence domain arithmetic.** The consolidation should keep results bit-identical; any change to the numerics is a separate study.
- The five context types (now softened in ASTRA), the three-way dataset turbulence request, and the performance campaign beyond the allocation checks.

**Missing from ASTRA's revision:**

- **A concrete API.** It doesn't give the new `run()` signature, doesn't merge `SolverControl` and the five solver arguments, and doesn't fix the double meaning of `roughness_length`. For the raise flags it says only "replace if needed".
- **A written re-qualification procedure.** None exists in the repo.
- **Python access to the native test clock.** ASTRA's Stage A relies on it for deadline tests, but it is not bound to Python (finding 20).
- **A turbulence `numerics_version` bump** if consolidating the reference changes any output bit.
- **Specifics:**
  - the naming fixes (`result.control`, `type`/`kind`, the two caveat names, the bool form of `turbulence`);
  - the exact stale README lines and plan-doc status lines;
  - examples that use solver controls;
  - `tools/run_turbulence_benchmark.py` rebuilding `run()` by hand.

## Implementation

### Phase 0: Record a baseline of current behaviour

- Add `tools/feature_merge_baseline.py --api old|new --output DIR` and `--compare A B`.
- It runs a fixed case matrix and saves arrays and metadata:
  - **Profiles:** legacy log, `LogProfile`, measured turning, power law, uniform.
  - **Turbulence:** off, height, wall_distance.
  - **Solver:** legacy, bounded (capped by iterations, not time, so it is deterministic), and adaptive on the qualified tower case.
  - **Grids:** explicit, automatic, stretched.
  - **Precision:** one float64 case.
- Run it with `--api old` at HEAD before any change. Later phases compare against it.
- Before changing anything, write down the intended result changes and how each will be judged. A result that differs from the baseline is neither a failure nor an improvement on its own.

  | Intended change | Judged by |
  |---|---|
  | Shared solver defaults (Phase 5) | Pedestrian-height speed-up error against a tightly converged reference, plus run time, on the tower case and `examples/city_dataset.py` |
  | `log_law_transfer` target side (Phase 4) | Analytic identities (a transfer to the same roughness is 1), and the change in comfort classes for the example climate |
  | Non-log K diagnostics (Phase 3) | Uniform profile gives exactly 1; log profiles stay bit-identical |
  | Preview inflow recorded as unknown (Phase 2) | Metadata only; no field changes |
  | Phase 9 consolidation | Bit-identical wind and adaptive results; any turbulence difference recorded under `dtcc-qes-turbulence-v2` |

  Everything else must match the baseline bit for bit.

### Phase 1: One spec per feature (breaking API)

```python
wind.run(city, profile=None, *, speed=None, direction=None,
         solver: Solver = Solver(), turbulence: Turbulence | None = None,
         resolution=2.0, bounds=None, horizontal_padding=20.0, vertical_clearance=20.0,
         max_cells=20_000_000, vertical_grid=None, terrain=None, height_policy="measured")
wind.preview_grid(city, profile=None, *, speed=None, direction=None,
                  turbulence=None, solver=None, <same grid kwargs>)
```

- **Profiles.**
  - Pass either `profile` or the `speed=`/`direction=` shorthand, which builds `LogProfile(speed, direction)`.
  - `reference_height=` and `roughness_length=` are removed from `run` and `preview_grid`.
  - `preview_grid` needs no inflow. Without a profile it plans the domain with the default reference height (10 m) and records the inflow as unknown, with no placeholder speed or direction (finding 17).
  - Every profile class carries `roughness_length` (default 0.1 m), used for ground roughness, lower tails, turbulence without buildings and the native z0. This removes the double meaning in finding 15.
  - The profile schema moves to `schema_version=2`; v1 payloads raise with a migration message.
- **`Solver` replaces `SolverControl` and five run kwargs** (`tolerance`, `max_iterations`, `solver_precision`, `raise_on_nonconvergence`, `raise_on_unaccepted`):

  ```python
  Solver(tolerance=1e-5, max_iterations=500, precision="float32",
         max_solve_seconds=None, monitor=None, policy=None,
         checkpoint_interval=25, residual_interval=0, raise_on_failure=False)
  ```

  - `mode` is a derived property: `"adaptive"` if `policy` is set, `"bounded"` if `max_solve_seconds` is set, otherwise `"legacy"`.
  - A monitor is required exactly when a budget is set. The adaptive rules are the same as today (cadence 25, windows 1/4, `history_limit >= 5`).
  - `raise_on_failure` raises the non-convergence error in legacy and bounded mode, and `UnacceptedResultError` in adaptive mode. The conflict between adaptive mode and `raise_on_nonconvergence` disappears.
  - `MonitorSpec`, `Receptor`, `MassRegion`, `BudgetExhaustedError`, `NumericalFailureError` and `UnacceptedResultError` stay.
- **`turbulence`** takes `Turbulence | None`; the bool form is removed.
- **Bounds.** `bounds=(xmin, ymin, zmin, xmax, ymax, None)` means "compute the top". A computed top is planned exactly like the no-bounds case. It includes the turbulence reference, and an automatic grid may be regenerated or extended for turbulence. A numeric `zmax` is fixed by the user and stays check-only, as do explicit faces (finding 18).
- **Serialization.** `Solver`, `Turbulence` and the profiles all get `to_dict()`/`from_dict()` with a `schema_version`. The dataset uses these instead of `asdict`.
- **Results.**
  - `metadata["solver"]` holds the spec plus the execution record, merging today's `solver` and `solver_control` entries.
  - `result.solver` replaces `result.control`.
- **Naming.**
  - The profile record uses `kind` instead of `type`.
  - Caveats go in one `caveats` list (replacing `turbulence_caveat` and `profile_caveat`).
  - The no-controls mode is called "legacy" everywhere.
- **Callers.** Update every caller: about 5 examples, 23 tools and 117 test call sites. Tools are migrated in Phase 7.

### Phase 2: One wind-condition path inside `wind.py`

- `_resolve_condition` always returns a profile.
- `profiles._profile_record(profile, heights)` is called once in `_prepare_city` for every profile kind. It replaces:
  - the inline log record at wind.py:138-147;
  - the patch-ups at wind.py:216-221;
  - the double `native_reference_scalars`;
  - `_layer_record` (no alias kept).

  `preview.domain["profile"]` then exists for log runs too. A preview without a profile records `domain["profile"] = None` and an `inflow="unknown"` marker, never a calm record.
- The float32 log check lives in one function in `profiles.py`, called by `LogProfile.__post_init__`.
- Native inputs for every log case must stay bitwise identical; check with Phase 0 `--compare`.

### Phase 3: One result record across features

- **`metadata["qualification"]`, exposed as `result.qualification`:**

  ```python
  dict(
      solver=dict(mode="legacy" | "bounded" | "adaptive",
                  execution="completed" | "iteration_limit" | "time_limit" | "failed",
                  legacy_converged=bool,
                  assessment="not_requested" | "accepted" | "unaccepted",
                  assessment_reason=..., exclusions=[...]),
      profile=dict(kind=..., experimental=bool, caveats=[...]),
      turbulence=None | dict(status="screening", mixing_length=..., numerics_version=...,
                             wind_basis=dict(execution=..., assessment=...)),
      vertical_grid=dict(mode="uniform" | "explicit" | "auto", policy_status=...),
  )
  ```

  Field validity stays in the turbulence `validity` record and the result masks; model limitations stay in each feature's `limitations`.
  The record must be able to express combined states. Examples: `assessment="accepted"` with `legacy_converged=False`, and `execution="time_limit"` with `legacy_converged=True`. No field summarises them into one exclusive label.
- **Warnings.**
  - Warn once when turbulence is computed on wind that is unconverged or time-limited.
  - Re-raise profile-coverage errors with the top after turbulence growth and its reason.
- **Top requirements.** Add `domain["top_requirements"]`, listing each height that constrained the top with its source: roof clearance, profile reference, or turbulence reference plane. Coverage errors cite it.
- **`pedestrian_sampling`.**
  - Compute K from the actual profile, and keep the log arithmetic bit-identical so the archived log values keep their meaning.
  - Add `profile_kind`, a vector interpolation error for turning profiles, and null with a reason when the reference is calm.
- **Timing.** Add `metadata["timings"]` for every solver mode (finding 16):
  - move the native phase timings there, out of the solver-control record;
  - add Python `city_preparation_seconds`, covering geometry extraction and grid planning;
  - add `public_call_seconds`, using one `perf_counter` pair around `run()`.

  Document which phases each value includes, and add no overlapping timers. If native code fills phase timings only when controls are on, legacy runs report the Python values until Phase 9 makes native code always fill them.

### Phase 4: Comfort

- `result.py`: add `WindResult.reference_direction`, the counterpart of `reference_speed`. It reads the profile record's reference direction and is `None` in calm wind.
- `profiles.py`: add `_Profile.with_direction(direction)`, which rotates the whole profile rigidly through `to_dict`, as `scaled()` already does, and keeps `roughness_length`:
  - analytic profiles replace their direction;
  - measured `direction`/`directions` are shifted modulo 360;
  - measured `u`/`v` are rotated;
  - a calm reference raises.
- `comfort.py`: add `directional_fields(results, height, *, method="linear", peak_factor=None, gust_ratio=1.85) -> DirectionalFields`.
  - Use duck typing on `.sample()`, `.reference_speed`, `.reference_direction` and `.metadata`, so comfort stays numpy-only.
  - Check that all results share the grid, origin, CRS, reference height and roughness. Reference speeds may differ between directions.
  - Raise for calm or duplicate directions.
  - Build GEM only when `peak_factor` is given, and raise if any result lacks turbulence.
  - Build `gem_metadata` the way the current example does: model, numerics_version, mixing_length, QES revision, limitations and per-direction runs. Add each direction's `qualification` and profile caveats. Never turn mean-wind acceptance into gust qualification.
  - `DirectionalFields.assess(speeds, directions, criterion=NEN8100, *, times=None)` passes `gem_fields` only for criteria with `gust_equivalent`.
- `log_law_transfer`:
  - The target side (blending height → QES reference height over the site roughness) uses the shifted form via `profiles._shifted_log`, so it matches the inflow `LogProfile` QES builds.
  - The station side (station height → blending height over the station roughness) keeps ln(z/z0).
  - The docstring names both laws and says the result is a QES `LogProfile` reference speed. Keep the input guards.
  - Tests:
    - transfer to the same roughness and height is exactly 1;
    - the target side agrees with `LogProfile.evaluate`;
    - roughness extremes;
    - the change in comfort classes for the example climate, reported rather than just updating the constants in tests/test_comfort.py:394-402.
  - The adapter never applies this conversion automatically, and never to a non-log profile. The caller chooses the station climate and how to convert it.
- Rewrite `examples/wind_comfort.py` to use all three specs:
  - a profile turned with `.with_direction(d)`;
  - `turbulence=Turbulence()`;
  - a bounded `Solver`;
  - `directional_fields(...).assess(...)`.

  Keep `tests/test_example.py::test_wind_comfort_example` passing.

### Phase 5: Dataset

- **`QESWindArgs`** mirrors `run`:
  - `profile` or the `speed`/`direction` shorthand;
  - `solver: dict | None`, parsed with `Solver.from_dict`;
  - `turbulence: dict | None`, parsed with `Turbulence.from_dict`.
  - `QESWindArgs` keeps typed payload schemas for DTCC's argument documentation, for the profile, `Solver` and `Turbulence`. A test checks that each payload schema and its spec's `from_dict` accept the same fields and kinds (finding 19).
- **Defaults** are shared: the solver defaults come from `Solver()`. There are no per-entry-point solver defaults.
  - Choose `tolerance` and `max_iterations` by measurement. Run the tower case and `examples/city_dataset.py` at the current run defaults (1e-5/500), the current dataset defaults (1e-4/1000) and one or two values in between. Compare the pedestrian-height speed-up error against a reference converged to 1e-7, and the run time. Pick the cheapest setting whose error stays within the budget written down in Phase 0.
  - Report the differences from both previous default sets in the release notes.
  - `max_cells` stays a per-entry-point safety limit (dataset 200M, run 20M), because it guards memory rather than accuracy. The README documents it.
- **Cache identity** covers the serialized specs, which include `schema_version` and, when turbulence is on, the turbulence `numerics_version`. The adaptive policy revision stays bound as it is today. Check how DTCC derives cache keys before finalising the fields. Old request identities change; note this in the release notes.
- **Domain top.**
  - For 4-coordinate dataset bounds, `_dataset_city.prepare_city` passes `zmax=None` (Phase 1). It no longer calls `default_domain_top` itself, so the dataset and direct runs plan the top through the same code, including turbulence growth and automatic-grid regeneration.
  - Bounds given by the user (6-coordinate) and explicit faces stay check-only.
- **`_field_slice`.**
  - Use `result.reference_speed` and `result.solid_mask` instead of reimplementing them.
  - Add `streamwise_std` and `turbulence_intensity` fields. z slices take them from the sample, which interpolates stress before projecting; x/y slices take the nearest cell of the 3D property. Never interpolate the derived statistics.
- **Double eigensolve.** In `to_dtcc`, compute validity once and pass it into `_streamwise_std`.
- **Reporting.** `describe()`, `presentation_limitations`, `health` and `warnings`:
  - add turbulence field names, turbulence counts and the screening limitation;
  - read maturity from `metadata["qualification"]`;
  - mention experimental profiles.
- Add `--turbulence` and `--profile` to `examples/city_dataset.py`.

### Phase 6: One scalar validator

- Add `src/dtcc_qes/_validation.py` with `real(value, name, *, positive=False, nonnegative=False, float32=False)` and `integer(value, name, *, minimum, maximum)`.
- One rule for accepted types:
  - accept finite Python and NumPy real scalars;
  - reject booleans, strings and arrays, including 0-d arrays;
  - check float32 range only where native code receives the value as float32.

  Arrays and strings are converted explicitly where data comes in, such as dataset payloads and measured-profile arrays, not inside the validator. Signed values (coordinates, velocities) and positive or nonnegative ones (lengths, speeds) keep their own range checks.
- Replace the five validators from finding 3, and the integer checks in `wind._validate_grid`/`_validate_solver`. Some inputs that were accepted before may now be rejected; test the new rule rather than the old coercions. The wording of the error messages may be unified; update the `match=` assertions.

### Phase 7: Tests, fixtures and tools

- Add `tests/test_feature_combinations.py`, covering:
  - `speed=`/`direction=` shorthand versus `LogProfile`, with and without turbulence, bitwise equal;
  - non-log profile + turbulence + bounded solver: the fields, the solver record and `qualification` agree;
  - `run(profile=MeasuredProfile, solver=adaptive)` is not accepted, with the reason asserted only on qualified builds, following the pattern in test_adaptive_control.py:35;
  - turbulence + time-limited bounded solve gives `wind_basis.execution="time_limit"` and a warning. Use the 1e-12 s budget so the test is deterministic (finding 20); after Phase 9, use the bound test clock for deadlines after completed sweeps;
  - combined states: an adaptive run accepted with `legacy_converged=False`, and a time-limited run with `legacy_converged=True`;
  - turbulence on/off on a frozen grid leaves the mean wind bitwise unchanged;
  - controls do not change the fields when the completed work is the same;
  - alternating log and table profiles with turbulence on do not leak condition state;
  - preview/run `domain["profile"]` parity for all four profile kinds;
  - calm, turning, jet, stretched-grid and float64 cases;
  - `with_direction` round trips;
  - `directional_fields` end to end with a profile and turbulence;
  - dataset turbulence field and slice products, and spec round trips through the dataset payload;
  - a direct run and a dataset run give identical arrays and matching metadata when given the same prepared geometry and specs. Compare the prepared geometry, not the source download, so that differences in data fetching or footprint cleaning are not taken for solver differences;
  - a grid-only preview records the inflow as unknown;
  - `bounds` with `zmax=None` grows for turbulence, while a numeric `zmax` is only checked;
  - wind-only runs allocate no turbulence arrays, and legacy runs allocate no monitor histories.

  Every turbulence on/off comparison uses an explicit grid.
- Consolidate fixtures into `tests/fixtures/` and `conftest.py`:
  - the tower city;
  - use of the existing ONE_BUILDING fixture;
  - `Solver` and `TurbulenceSettings` builders;
  - keyword-argument synthetic `WindResult`/`TurbulenceFields` builders;
  - a single tool-module loader.
- Keep test oracles independent of production code. Merge the duplicated oracles into one test-side module, `tests/fixtures/oracles.py`: the analytic covariance oracle, the stress-validity eigen check and the npz comparisons. Do not replace them with calls to `result._stress_validity` or other production helpers, or the tests would check the code against itself.
- Remove the places where tests import other test modules.
- Migrate the tools to the new API and the shared fixtures. `tools/run_turbulence_benchmark.py` calls `run()` instead of rebuilding it. The archives under `docs/data/*/sources` keep the old copies.

### Phase 8: Docs and examples

- Restructure README.md into a user guide:
  1. Quick start
  2. Wind conditions (profiles, `roughness_length`, `with_direction`)
  3. Grids (fixed versus computed top with `zmax=None`, `domain["top_requirements"]`, previews without an inflow)
  4. Turbulence
  5. Solver: `Solver` modes legacy/bounded/adaptive, precision, a `MonitorSpec`/`Receptor` snippet and `result.solver`
  6. **Combining features**: the compatibility matrix, the adaptive exclusion reasons, `result.qualification`, and the frozen-grid rule for comparisons
  7. Comfort (adapter)
  8. Dataset (profile, solver, turbulence; shared defaults; `max_cells` per entry point)
  9. Results, including the timing scope
  10. One status/validation table linking the reports
  11. Migration from the old API: a table of old call → new call

  Move the S5–S9 milestone narrative out of "Build and install" into a `docs/solver-control.md` overview.
- Fix the stale README text listed under Documentation.
- Make minimal status corrections in the plan docs (QES_TURBULENCE.md, SOLVER_CONTROL_REFACTOR.md, docs/solver-control-s7.md), with cross-links between them. In docs/solver-control-s9.md, state plainly that adaptive mode excludes turbulence.
- Update docs/wind-comfort.md for the adapter and for `log_law_transfer`. State which law each side uses, why, and how much the comfort classes changed in the example climate. Move "Profile reference normalization" before "Sources".
- Use one term for the input wind ("inflow profile") and one set of solver mode names (legacy/bounded/adaptive).

### Phase 9: Native consolidation and re-qualification

- **Turbulence reference.**
  - Create a new QES-free `src/qes_core/dtcc/turbulence_reference.{h,cpp}` covering:
    - reference height, roughness and displacement from building heights;
    - the margin check;
    - a sufficient constant-tail extension.
  - Keep the float32 operation order and the sorted accumulation used in `dtcc/turbulence.cpp`.
  - `dtcc/turbulence.cpp` and `winds/TURBGeneralData.cpp:186-191` call the new helper. The vendored edit is one call, marked `// dtcc-qes:`, and listed with the audited fixes in the turbulence metadata.
  - `_turbulence_domain.py` becomes a thin binding wrapper that only formats errors.
  - If turbulence output changes in any bit, bump `numerics_version` to `dtcc-qes-turbulence-v2` and record the differences. Turbulence is outside the adaptive scope, so this cannot change an adaptive decision.
- **Eligibility.**
  - Split `pedestrian_scope` into `pedestrian_exclusions(...)`, which returns every failed check in today's order. `pedestrian_scope` returns the first one, so decisions are unchanged.
  - Expose a QES-free binding that takes the inputs known after grid planning: profile kind, precision, turbulence, grid counts, spacing and layers, inflow scalars, model settings, buildings and monitor spec.
  - `preview_grid(..., solver=)` returns `solver_eligibility`, and `run()` warns before native preparation. `qualification.solver.exclusions` is filled from it.
  - The thread count stays a runtime check.
  - Add a native test that the first exclusion equals `pedestrian_scope` for every case in `check_pedestrian_policy`.
- **Timings.** Make native code fill the phase timings for every solver mode, not only when controls are on (finding 16).
- **Test clock.** Bind `native_test_clock` for tests only, through a private entry point, so Python tests can place deadlines after a set number of sweeps (finding 20).
- **CMakeLists** adds the new source file.
- **Re-qualification.** Write the procedure in `docs/solver-control-requalification.md`:
  1. Run `compare_native_builds --baseline <commit before Phase 9> --backends openmp serial`. Every wind-only and adaptive case must be bitwise identical.
  2. Set `pedestrian_qualified_revision` in `pedestrian_qualification.h` to the new `solver_policy_revision`. That header is excluded from the hash.
  3. Run the full `validate_solver_release.py`, including the policy and campaign checks.
  4. Confirm that adaptive runs are accepted again.

## Not in this plan (follow-ups)

- **ASTRA Stage G:** a versioned policy that accepts mean wind with turbulence on. Turbulence runs after the solve, so this is the most plausible first extension, but it needs its own evidence: same grid, same iterates, same decisions with turbulence on and off.
- **Adaptive acceptance for non-log profiles:** needs calibration and held-out cases for shear, turning and jets.
- **One native profile path** (ASTRA §6): evaluate log profiles through the layer table too, and remove `ProfileKind::Log`. This changes every field adaptive mode accepts. The policy would then need to check the declared profile family and evaluation revision rather than the storage format, and pedestrian-v1 would need fresh calibration. Do it only together with Stage G or the non-log calibration, compared at cell centres, roof-level supports and reference heights across roughness extremes and grid refinement.
- **Prepared-model reuse and a `run_directions` API:** still deferred, as S8a decided (docs/solver-control-s8a.md).
- **Native C++ test helpers** (`require()`/`rejects()` in every `tests/native/check_*.cpp`): not part of the policy hash; tidy up when convenient.

## Verification

1. **Phases 0–8 (Python only).**
   - `git diff --stat -- src/qes_core src/cpp CMakeLists.txt` is empty.
   - `_qes.solver_policy_revision` equals `pedestrian_qualified_revision` on the qualified build.
   - `tools/feature_merge_baseline.py --compare` against the Phase 0 baseline shows bitwise equality, except for the intended changes in the Phase 0 table. Each of those meets its stated criterion, and the differences are reported:
     - the shared solver defaults;
     - the target side of `log_law_transfer`;
     - the non-log K diagnostics;
     - the preview inflow recorded as unknown.
2. **The full suite** from README §Validate passes:

   ```sh
   cmake -S . -B build/native -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DCMAKE_BUILD_TYPE=Release
   cmake --build build/native --parallel 8
   ctest --test-dir build/native --output-on-failure
   DTCC_QES_NATIVE_TEST="$PWD/build/native/check_safety" uv run --frozen python -W error -m pytest -q
   ```
3. **Phase 9.**
   - `uv run --frozen python tools/compare_native_builds.py --baseline <pre-Phase-9 commit> --backends openmp serial`;
   - `uv run --frozen python tools/validate_solver_release.py --output build/solver-release-check`;
   - a test that adaptive acceptance is restored on the qualified build;
   - turbulence fields bitwise equal, or a recorded `dtcc-qes-turbulence-v2` difference.
4. **Examples.** `examples/wind_comfort.py`, `examples/wind_profiles.py` and `examples/city_dataset.py --turbulence --profile` all run. Inspect `result.qualification` and the comfort metadata.

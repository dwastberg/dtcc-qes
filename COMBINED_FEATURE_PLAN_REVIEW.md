# Review of COMBINED_FEATURE_PLAN.md

- **Date:** 2026-10-31
- **Reviewed against:** `3ae4157` (claims below were checked in the code)
- **Reviewer:** Claude (author of CLAUDE_FEATURE_MERGE_PLAN.md)

## Verdict

Adopt COMBINED_FEATURE_PLAN.md as the single working plan, and mark the CLAUDE and ASTRA plans as superseded. It contains everything in my plan and corrects two errors in it (see below).

Five points should be fixed before implementation starts. They concern exception semantics, the status vocabulary, phase ordering and one formula. None changes the overall structure: Python first, native last, then re-qualify.

## What the combined plan gets right that my plan got wrong

1. **The `not_assessed` state already exists in native code.**
   - The native record defaults `accuracy_status` to `"not_assessed"` (`src/qes_core/dtcc/api/control_types.h:28`).
   - An excluded adaptive request sets it explicitly (`src/qes_core/dtcc/solver_control.cpp:31`).
   - My three-state vocabulary would have merged "excluded from the policy" into "assessed and failed". The four-state version is correct.
2. **Re-qualification tool.**
   - My Phase 9 said to run `tools/validate_solver_release.py`. That tool requires the frozen S9 native identity (`tools/validate_solver_release.py:112`), so after any native change it fails by design.
   - The right check is `tools/check_wind_profile_policy.py`, which reruns the 24 frozen S7 workers. Its docstring says the native revision is the only value allowed to change.
3. **Comfort provenance for mean-only criteria.**
   - `comfort.assess` raises when `gem_metadata` is given without `gem_fields` (`src/dtcc_qes/comfort.py:206-207`). It also rejects `gem_fields` for mean-only criteria (`comfort.py:211-212`).
   - So my `directional_fields` adapter could not have recorded provenance for NEN8100. The plan's separate `run_metadata` argument fixes this.
4. **Timings in metadata.** Wall-clock values in `metadata["timings"]` would break the byte-for-byte self-comparisons in `compare_native_builds.py` unless they are excluded. The plan excludes them.
5. **`validate_solver_policy.py` reads `result.control`** (`tools/validate_solver_policy.py:120`). It must be migrated, or the frozen-worker check stops working.

The plan also adds three things to keep:
- `pending_runtime_checks=["thread_team"]` for previews;
- explicit `from_law`/`to_law` arguments on `log_law_transfer`, which still allow the old convention;
- a written order of precedence for exceptions.

## Must fix before implementation

### 1. Bounded `time_limit` should not raise `BudgetExhaustedError` (§4.2)

**What the plan says.** With `raise_on_failure=True`, a bounded run that stops at `time_limit` after at least one sweep raises `BudgetExhaustedError`, "even if `legacy_converged=True`".

**What happens today.**
- `BudgetExhaustedError` means that no whole sweep completed, so no field exists (`solver_control.py:176-180`, `solver_control.cpp:64`).
- A time-limited bounded run that has not converged raises `ConvergenceError` with the control record (`wind.py:180-183`). That message already includes the termination reason (`result.py:126`).
- A run that converged on its last sweep returns normally. The deadline check runs after the convergence update, so `time_limit` together with `legacy_converged=True` can happen; §4.3 of the plan lists that combination itself.

**Problems.**
- One exception type would mean both "no result exists" and "a partial result exists". A caller who catches `BudgetExhaustedError` in order to retry with a larger budget can no longer tell the two apart.
- The run would also reject a field that meets the legacy tolerance, only because the deadline check fell in the same sweep.

**Recommendation.**
- In legacy and bounded mode, raise `ConvergenceError` if and only if `legacy_converged` is false.
- Keep `BudgetExhaustedError` for the zero-sweep case only.
- Add every change to exception behaviour, including item 6 below, to the Phase 0 table of intended changes.

### 2. Map from the native vocabulary to the public one, and keep the raw record (§4.3, Phases 3 and 7)

**Two native states need different public labels.**
- Natively, bounded runs and excluded adaptive runs both report `accuracy_status="not_assessed"`.
- The plan correctly reports bounded runs as `not_requested`, but it never states the mapping.
- The mapping should be:

  | Native `accuracy_status` | Mode | Public assessment |
  | :--- | :--- | :--- |
  | `not_assessed` | bounded | `not_requested` |
  | `not_assessed` | adaptive | `not_assessed` |
  | any other value | any | passed through unchanged |

**The frozen evidence compares raw native keys.**
- Both `validate_solver_release.py:194` and `check_wind_profile_policy.py:57-63` compare the raw keys `accuracy_status`, `method`, `assessment_reason` and `policy_revision` against frozen rows.
- Keep the native record verbatim inside `metadata["solver"]` and derive `qualification` from it. If the native keys are renamed, every frozen comparison needs a translation table.

**The schema example names the wrong method.** The method id is `"s5c-rb-sor-float-omega-v1-omega-1.90"` (`src/qes_core/dtcc/api/policy_types.h:9`), not `"pedestrian-v1-sor-1.90"`.

**`effective_mode` is undefined for excluded adaptive runs.**
- Native code keeps `mode="adaptive"` and only switches `method` to 1.78 (`solver_control.cpp:28-32`).
- `mode`, `assessment="not_assessed"` and `method` already describe this case, so drop `effective_mode`.
- If it stays, define its value for this case. State also that the raise rules depend on the requested mode.

### 3. `exclusions` before Phase 9 (Phase 3)

**The gap.**
- Phase 3 promises `exclusions` as "all failed scope checks" and adds `pending_runtime_checks` to previews.
- Until Phase 9 adds `pedestrian_exclusions`, native code returns only the first failed check (`pedestrian_policy.cpp:17-60`). Python cannot produce the full list.

**Behaviour for Phases 3–8.**
- `exclusions=[assessment_reason]` when the run is `not_assessed`, and `[]` otherwise.
- Previews report no solver eligibility.

**Phase 0 table.** Add the longer list that appears in Phase 9 as a declared metadata change.

### 4. Tools must be migrated in Phase 1, not Phase 7

Phase 1 requires the test suite to stay green, but tools are only migrated in Phase 7. Breaking the API in Phase 1 breaks four things.

- **A pytest test fails in Phases 1–2.**
  - `tests/test_turbulence_benchmark.py:49` runs `tools/run_turbulence_benchmark.py --self-test`.
  - That tool rebuilds `run()` from `wind._validate_grid` and `wind._prepare_city(city, condition, grid, ...)`, and both signatures change in Phases 1–2.
- **The re-qualification chain breaks.**
  - `check_wind_profile_policy.py` reruns `validate_solver_policy.py`.
  - That tool calls `wind.run(city, speed, direction, solver_control=SolverControl(..., mode='adaptive'))` and reads `result.control` (`tools/validate_solver_policy.py:88-91,120`).
- **The native comparison breaks.** `compare_native_builds.py:260` calls `wind.run(c, speed, direction, **options)`.
- **The dataset breaks in Phase 2.**
  - `datasets.py:133` calls `wind._validate_condition`, which Phase 2 deletes.
  - Phase 2's file list does not include `datasets.py`.

**Which of these can guard the refactor.**
- `check_wind_profile_policy.py` runs the live `validate_solver_policy.py` against the live Python tree and compares against frozen S7 rows recorded with the old API. It is the existing check across the API break, so leaving it broken through Phases 1–6 removes it exactly when it is needed.
- `compare_native_builds.py` is *not* such a check. Its `evaluate()` runs the current tool's cases against each staged package (`compare_native_builds.py:345-348`), so it cannot compare across the API break. It stays a native-revision check for Phase 9, with the Phase 8 commit as baseline. *(Correction: an earlier version of this review proposed it as a gate for Phases 1–3.)*

**Recommendation.**
- In Phase 1, migrate `run_turbulence_benchmark.py`, `compare_native_builds.py` and `validate_solver_policy.py`.
- In Phase 2, update `datasets.py:133`.
- Add `check_wind_profile_policy.py` to the gates of Phases 1–3. The Phase 0 baseline tool covers the remaining cases across the API break.

### 5. Say which terms each law applies to in `log_law_transfer` (§4.4)

**The formula has two terms on each side** (`comfort.py:320-323`):

```
station side: ln(h_b / z0_from) / ln(z_from / z0_from)
target side:  ln(z_to / z0_to)  / ln(h_b / z0_to)
```

**Recommendation.**
- State that `from_law` applies to both station terms and `to_law` to both target terms. Only then does the gate "exact target-ratio agreement with `LogProfile.evaluate`" hold.
- Apply the check that height exceeds roughness (`comfort.py:317-319`) only to the sides that use `"standard"`.

## Should consider

6. **Raise before the solve when the exclusion is already known.**
   - With `raise_on_failure=True`, an excluded adaptive request still runs its full budget before raising (`wind.py:174-178`).
   - Python already knows three of the exclusions from the inputs: turbulence, a non-log profile and float64. After Phase 9 it knows every input and grid check.
   - Raise before native preparation, and declare this change in Phase 0.
7. **Reuse the existing re-qualification procedure instead of adding a third verifier.**
   - The wind-profile merge already re-qualified in this way: `docs/wind-profiles-verification.md:23-36` plus `tools/check_wind_profile_policy.py`. `pedestrian_qualification.h` was last updated in `3ae4157`.
   - Generalise that section into `docs/solver-control-requalification.md`, and rename the tool (for example to `check_policy_compatibility.py`). Do not add `qualify_solver_candidate.py`.
   - The plan is right to keep `validate_solver_release.py` out of this procedure.
8. **Dataset argument names.**
   - `QESWindArgs` keeps `wind_speed`/`wind_direction` (`datasets.py:76-77`), while `run` takes `speed`/`direction`.
   - The plan says the dataset mirrors `run`, and breaking changes are allowed. Either rename them or state why they stay.
9. **README:121-122 is ambiguous rather than false.**
   - It says the policy does not qualify turbulence, which is true.
   - What it omits is that runs with turbulence are excluded entirely (`pedestrian_policy.cpp:21`). The fix is a wording change.
10. **Native test fixtures.**
    - §3 item 8 lists the duplicated native 3-block fixture, but no phase removes the duplication.
    - `tests/native` is outside the policy hash, so Phase 7 can do it.

## Claims checked and confirmed

- **Turbulence logic is duplicated** between Python and native code.
  - The margin check and constant-tail extension appear in both `src/dtcc_qes/_turbulence_domain.py:38-80` and `src/qes_core/dtcc/turbulence.cpp:36-70`, with the same five limit reasons. So moving the extension into one native helper is genuine consolidation.
  - The other turbulence-domain rules — two physical layers above the reference height and a 15 m minimum top — match the code.
- **Termination reasons:** `legacy_tolerance`, `iteration_limit`, `time_limit`, `accepted`, `stagnation` and `invalid_support` are all the native values. `numerical_failure` always raises.
- **`native_call` is GIL-free** (`src/cpp/bindings.cpp:34`). **`$<LINK_ONLY:qeswindscore>`** is set at `CMakeLists.txt:134`.
- **`compare_native_builds.py`** has `--thread-counts` and `--require-backend-parity`. The 429-case matrix is the one `validate_solver_release.py:179` uses.
- **Comfort:** `comfort.py` imports only NumPy. `reference_speed` can be a scalar or one value per direction.
- **K diagnostics:** `UniformProfile` K at 1.5 m is ln(16)/ln(101) = 0.6008 today.
- **Dataset:** `_dataset_city.py:101` precomputes a 6-coordinate top. Not checked here: the 35-layer versus 38-layer example, which only matters once the dataset supports turbulence.

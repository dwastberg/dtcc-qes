# Solver execution and numerical assessment

The current API uses `wind.Solver`. See the [user guide and migration table](../README.md#api-migration).

| Requested configuration | Mode | Assessment | Method |
| --- | --- | --- | --- |
| `Solver()` | legacy | not_requested | 1.78 |
| Budget and monitor | bounded | not_requested | 1.78 |
| Budget, monitor and `policy="pedestrian-v1"`, eligible | adaptive | accepted/unaccepted | 1.90 |
| Adaptive request excluded from scope | adaptive | not_assessed | 1.78 |
| Legacy or bounded with `relaxation=ω` | legacy/bounded | not_requested | ω |

Defaults are tolerance `1e-4`, iteration limit 1,000, float32. The
[two-city selection study](data/feature-merge/phase5.json) checks pedestrian
vector errors against converged and further-tightened float64 references.
Choose explicit settings when reproducing older work. With the default
`stop="multiplier_change"`, convergence measures multiplier change; it does not
certify a residual or physical accuracy.

## Stop rules (opt-in)

Legacy and bounded solves accept three stop rules; the pedestrian-v1 policy
rejects all but the default, and `relaxation` with it
([plan and evidence](../SOLVER_STOP_RULE.md)).

| `stop` | Ends when | `termination_reason` |
| --- | --- | --- |
| `"multiplier_change"` (default) | largest multiplier change ≤ `tolerance` | `legacy_tolerance` |
| `"velocity"` | estimated remaining face-velocity error ≤ `velocity_tolerance` (default `1e-3`) × the reference speed at two consecutive checks, or the change reaches the rounding floor | `velocity_estimate`, `precision_floor` |
| `"fixed"` | exactly `max_iterations` sweeps | `fixed_work` |

`max_iterations` caps every rule (`iteration_limit`). Every 25 sweeps the
`"velocity"` and `"fixed"` rules measure c, the largest change of the corrected
face velocities over the block relative to the reference speed. With r the
larger of the last two block ratios, clipped at 0.99, they estimate the
remaining error as 2·c·r/(1−r). Passes count from the fourth check, so the
earliest stop is after 125 sweeps. The rounding floor is
6·ε·max|λ|/(h_min·U_ref), with ε the machine epsilon of the arithmetic; a
`precision_floor` stop means that the arithmetic cannot certify a smaller
error, and counts as converged. Study E1 (Cases D and E at 2 m and 1 m,
`validation/SOLVER_STOP_RULE_RESULTS.md`) found the actual whole-volume error
at 0.11–0.52 of the estimate at every estimate stop. The history is in
`result.solver["stop_estimate"]` (values not yet available are None). For
`"velocity"`, `result.diagnostics.converged` reports the estimate;
`qualification["solver"]["legacy_converged"]` keeps the multiplier meaning.
`"fixed"` reaching its work is not a convergence failure. `"velocity"` needs a
positive reference speed; calm `"fixed"` solves record no estimate. The
estimate bounds the corrected faces over the whole fluid volume; it is
numerical evidence only, not physical accuracy.

## Outcomes and failure policy

`result.solver` stores `spec`, the verbatim native `record` (None for legacy),
and `environment`. A fresh `result.qualification` derives execution,
legacy convergence, assessment, scope and model caveats. An accepted result
may fail legacy tolerance, and a converged result may carry a deadline.
No single summary enum replaces those facts. Cell masks remain independent.

`raise_on_failure=False` returns completed work and emits at most one solver
outcome warning. Requested turbulence is included in that warning as screening
based on the returned mean wind. Independent profile caveats still apply.
With `raise_on_failure=True`, legacy/bounded non-convergence raises
`ConvergenceError`; adaptive unaccepted/not-assessed output raises
`UnacceptedResultError`. A known input exclusion raises before native
preparation with `diagnostics=None`. Invalid inputs and numerical breakdown
always raise. `BudgetExhaustedError` means zero completed sweeps and no field;
a converged field at a completed-work deadline can return normally.
Exceptions expose the native `.record`.

## Scope and monitoring

Adaptive eligibility depends on the qualified source/arithmetic build, analytic
Log inflow, actual thread team, float32 precision, no turbulence, supported grid,
model flags, geometry and observables. An exclusion remains an adaptive request;
1.78 fallback never inherits numerical acceptance. Turbulence explicitly gives
`turbulence_outside_assessment_scope`. All final exclusions are stored in native check order in
`result.solver["record"]["exclusions"]`. The first remains `assessment_reason`.
`preview_grid(..., solver=solver)` reports provisional eligibility without
allocating native fields. Adaptive preview requires explicit inflow and leaves
`actual_thread_team` pending. Preflight and runtime share float32 narrowing and
policy predicates. Strict requests reject known exclusions before preparation.


`MonitorSpec` defines a half-open pedestrian ROI, heights, optional required
`Receptor`s and bounded history. The policy requires required receptors at
1.5 and 1.75 m, cadence 25 and sufficient history. Coordinates use the declared
local/world frame. Histories summarize completed iterates, without full-field
checkpoint copies. Numerical acceptance is restricted to the declared ROI and
receptors; full-volume, grid-independent, turbulence and physical accuracy are
outside that scope.

For bounded runs with turbulence enabled, `MonitorSpec(turbulence=True)` adds
stress, the native velocity gradient, mixing length, TKE, reconstructed uncapped
TKE and stress-validity information to each receptor checkpoint. It defaults to
false and is rejected for adaptive runs. Each requested checkpoint reruns the
turbulence calculation on the completed mean-flow iterate, so it adds work and
can consume a time budget sooner. It does not change the fixed-work trajectory
or establish turbulence accuracy. Receptor payloads count toward the monitor's
existing history and memory limits.

The private native `WindRunner._solve_trace` entry point captures selected
physical `(i, j, k)` cells through the ordered mean-flow stages and native stress
construction. It requires bounded control, enabled turbulence and legacy
physics. Tensor stages are `pre_anisotropy`, `post_anisotropy` and `post_bound`;
`uncapped_constitutive` is explicitly a reconstruction, not an executed stage.
The result owns its storage, and observers detach on success and failure.

Captures allow at most 512 face cells, 4,096 tensor cells, 1,024 frames and
100,000 canyon decision rows (50,000 by default). Duplicate or out-of-domain
cells and invalid actor indices fail. Reaching a frame or decision limit raises
instead of silently truncating. `building_frames=False` retains whole-stage
frames and suppresses per-building frames for large scenes. The building index
table scales with the prepared scene. Tracing is opt-in; ordinary solves do not
allocate trace buffers. This private diagnostic interface provides evidence for
investigations and is not a supported alternative physics model.

## Timings and reproduction

`metadata["timings"]` documents nested public-call, preparation and native
measurements. Parent totals include children. Native phases are measured for legacy, bounded and adaptive execution. Legacy
records remain None; their phase timers live in `metadata["timings"]["native"]`. Budgets are native cooperative
limits; process wall time also includes preparation, output and cleanup.
Time-budgeted dataset realizations preserve their actual work and declare
`execution_deterministic=False`.

Use the [existing isolated requalification procedure](solver-control-requalification.md)
after native changes. Frozen S7 workers compare fields, convergence, method,
assessment and histories exactly, excluding validated elapsed-time values.
`validate_solver_release.py` verifies the immutable S9 archive and deliberately
requires its original identity; it is not the requalification entry point.

## Historical S5–S9 milestone notes

> Historical narrative and commands below retain their original API and identities. Use the current [migration table](../README.md#api-migration) for live calls; reproduce frozen campaigns from archived drivers.

Completed-iterate residual diagnostics, bounded hotspot investigation and two
qualified small same-grid references are documented in the
[S5 completion report](docs/solver-control-s5.md). The oblique urban solid-mask
defect is corrected and independently frozen. Large urban accuracy remains
unqualified, and the disabled-controls performance review target was missed;
bounded results still report unassessed accuracy.

The [S6 method study](docs/solver-control-s6.md) selects internal SOR relaxation
`1.90f` for the qualified opt-in policy on its measured small-grid scope.
Public legacy and bounded calls retain `1.78f`.

[S7's opt-in pedestrian policy](docs/solver-control-s7.md) is now qualified on
its declared small-domain scope. Use `SolverControl(..., mode="adaptive")`
with an explicit ROI and required receptors at both 1.5 and 1.75 m. Acceptance
is separate from legacy convergence and covers only those outputs. Larger or
unsupported configurations remain unaccepted; full-volume, turbulence and
physical/model accuracy are not qualified by this policy. Qualification is tied
to a frozen native source/arithmetic identity. The footprint-enabled build was
requalified against all 24 frozen S7 workers, with exact fields, diagnostics and
assessment decisions ([verification evidence](docs/data/feature-merge/head-requalification.json)).
This preserves the existing policy scope; it adds no adaptive scope for touching
or canonical footprints. Result metadata records the current
decision under `versions.native_build.solver_policy_build_supported`.

The [S9 closure report](docs/solver-control-s9.md) closes the solver-control
refactor within that qualified numerical scope and records the release checks,
defaults, errors, dataset cache identity and remaining limitations. No default
policy is promoted. [S8a](docs/solver-control-s8a.md) measured modest preparation
reuse savings and deferred a public reuse API; S8b comfort sensitivity is
explicitly deferred. Large-domain accuracy, grid independence and physical
comfort/gust qualification remain separate work.

```sh
# Build and run the complete release verification in a new directory.
.venv/bin/python tools/validate_solver_release.py --output build/solver-release-check
```


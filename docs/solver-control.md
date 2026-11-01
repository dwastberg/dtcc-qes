# Solver execution and numerical assessment

The current API uses `wind.Solver`. See the [user guide and migration table](../README.md#api-migration).

| Requested configuration | Mode | Assessment | Method |
| --- | --- | --- | --- |
| `Solver()` | legacy | not_requested | 1.78 |
| Budget and monitor | bounded | not_requested | 1.78 |
| Budget, monitor and `policy="pedestrian-v1"`, eligible | adaptive | accepted/unaccepted | 1.90 |
| Adaptive request excluded from scope | adaptive | not_assessed | 1.78 |

Defaults are tolerance `1e-4`, iteration limit 1,000, float32. The
[two-city selection study](data/feature-merge/phase5.json) checks pedestrian
vector errors against converged and further-tightened float64 references.
Choose explicit settings when reproducing older work. Convergence measures
multiplier change; it does not certify a residual or physical accuracy.

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
`turbulence_outside_assessment_scope`. Profile and precision exclusions are also
checked before preparation. Remaining scope checks run natively during solve.
The current result lists the first native reason; full preflight and complete
exclusion lists are the native consolidation step.

`MonitorSpec` defines a half-open pedestrian ROI, heights, optional required
`Receptor`s and bounded history. The policy requires required receptors at
1.5 and 1.75 m, cadence 25 and sufficient history. Coordinates use the declared
local/world frame. Histories summarize completed iterates, without full-field
checkpoint copies. Numerical acceptance is restricted to the declared ROI and
receptors; full-volume, grid-independent, turbulence and physical accuracy are
outside that scope.

## Timings and reproduction

`metadata["timings"]` documents nested public-call, preparation and native
measurements. Parent totals include children. Unavailable legacy native phases
are None until native instrumentation is added. Budgets are native cooperative
limits; process wall time also includes preparation, output and cleanup.
Time-budgeted dataset realizations preserve their actual work and declare
`execution_deterministic=False`.

Use the [existing isolated requalification procedure](wind-profiles-verification.md)
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


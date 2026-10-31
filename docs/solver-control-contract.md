# Solver-control contract frozen in S0

This is the interface and lifecycle specification for S1–S4, prepared against
`bbfd20005e0bd7d7e648438a1bc8d5a9a4358a71`. It implements no control mode or
accuracy policy. Existing calls retain float32, 500 iterations, tolerance 1e-5
and the current backend-specific ordering. Automatic grids remain experimental
within the restricted scope of the closed vertical-grid study.

## Ownership and phases

The prepared model owns geometry, original geometry flags, empirical model
objects, an immutable operator and optional turbulence setup. Coefficients do
not change with the condition. Condition inputs contain original staggered
velocities **and the current cell flags after parameterizations**, with explicit
grid identity. Solid masking and diagnostic eligibility use those current flags,
including existing model behavior that may differ from the geometry flags.
They remain alive and unchanged through finalization. A device backend uploads
them once per condition, separately from the prepared operator.

The solver package owns the precision-specific workspace and exposes:

| Operation | Contract |
| --- | --- |
| `build_operator(geometry)` | Validate once; retain exact coefficients, boundary extents and per-layer factors. |
| `begin(operator, condition_inputs, kernel_options)` | Validate the condition; zero multipliers and RHS; build RHS once. No retained iterate from a previous condition. |
| `advance(work_limit, stop_rule)` | Complete whole sweeps, including both colors and ground mirror; return cumulative and block work, measured change, legacy criterion and numerical-failure status. CPU bounded mode checks time after each sweep. |
| `observe(layer_ranges, destination)` | Pure reconstruction into bounded slab buffers, matching finalization's rounding, prescribed faces, current solid mask and center averaging. |
| `diagnose(regions, destination)` | Pure current-iterate six-face mass checks, returning scalar summaries and counts; no full-volume transfer. A future device implementation performs the reduction on the device. |
| `finalize(destinations)` | Reconstruct from original velocities, never a previous corrected field. Provide staggered faces required by host turbulence and physical cell-centered output; transfer complete fields once. |
| `copy_state_for_study()` | Explicit internal access/copy for fixed-work studies. Neither controller nor monitors index backend workspace. |

Names and representation are finalized in S1. CPU finalization can reuse the
model's existing face buffers; the destination contract must not force another
face volume. Preserve QES notices and update provenance when moving derived code.
Precision-specific arithmetic expressions and statement boundaries stay intact.
S1 can wrap the existing coefficient arrays with immutable views, retaining
their geometry lifetime; transfer storage ownership when diagnostics migrate in
S2. Avoid a second full operator allocation just to extract the interface.

Compact operator lookups must reconstruct coefficient values and retain the
current divergence expressions. Boolean open areas are insufficient for bitwise
diagnostic parity: the existing expressions recover areas from rounded float32
coefficients. Remove cut-cell storage only after guarding or replacing every
active reader, including `Wall::defineWalls`' building-volume-fraction test.

## Runner state and failure behavior

| Entry state / operation | Success | Failure |
| --- | --- | --- |
| Unprepared / `prepare` | Prepared | Unprepared |
| Prepared / `prepare` | New Prepared model | Previous Prepared model retained |
| Prepared / `solve` initialization | Initialized for this condition | Prepared; no resumable state |
| Initialized / `begin` | Solving | Prepared; discard partial workspace |
| Solving / `advance`, `observe`, `diagnose` | Solving with complete latest iterate | Prepared; discard partial workspace |
| Solving / finalization and turbulence | Finalized, then Prepared for next call | Prepared; discard partial workspace |

All blocks belong to one native call. No public resumable state or warm start is
introduced. Preparation, condition changes and precision changes invalidate
workspace identity. Native mutex/GIL ordering and input snapshots are retained.

S1 is strictly the phase extraction and reproduces existing runner-reuse outputs.
After its required review, a separate **S1a condition-state correction** resets
`PolyBuilding::rooftop_flag`, audits other per-condition members and validates
wake-model dependencies. Its expected numerical differences are confined to
reproduced reuse defects; input rejection is tested separately. Freeze the S1a
revision as an additional comparison baseline. Test a condition fresh, after
other directions, after precision changes and after an injected numerical
failure. Keep both the original S0 and corrected baselines. S2 performance
changes compare against the corrected baseline, and a future reusable Python
model requires S1a. No state correction is included in S0 or the pure S1 move.

## Proposed control and result fields

Public settings live in QES-free `dtcc/api` types and Python value types. All
input arrays and receptor definitions are copied before releasing the GIL.

| Setting | Initial validation / semantics |
| --- | --- |
| `solver_control=None` | Existing behavior and warnings. |
| `mode="bounded"` | The only initial opt-in mode; legacy tolerance plus resource limits, never accuracy acceptance. |
| `max_solve_seconds` | Required positive finite seconds, measured by `steady_clock` from native solve entry before mutex acquisition. |
| `checkpoint_interval` | Positive integer number of complete sweeps. Does not govern CPU deadline checks. |
| `monitor` | Explicit heights, region, receptors, local/global coordinate frame, strict support and interpolation policy; validate grid identity and bounded slab allocation. |
| `history_limit` | Positive integer; bounded records, retaining terminal decision and clearly identified iteration-zero baseline. Define eviction in S3 without changing the policy's required working windows. |
| Existing `max_iterations`, `tolerance`, `solver_precision` | Single source of these settings; no competing limits inside the control object. |

The control record contains `termination_reason`, `accuracy_status`, total
completed `iterations`, bounded checkpoint history, satisfied criteria, phase
timings, measured overshoot, execution and grid/monitor identity. Execution
records the actual team size, precision, backend, compiler/build/source identity
and `fp_contract` (the same name exposed by `_qes` and `metadata.versions.native_build`).
`policy_id` and `policy_version` are absent in bounded mode; its
`accuracy_status` is always `not_assessed`.

Invalid settings raise input exceptions before model mutation where possible.
Nonfinite numerical failures raise a numerical exception and cannot yield an
accepted result. If no sweep completes before budget expiry, raise
`SolveBudgetExhausted` with completed work, phase and timing diagnostics. If at
least one finite sweep completes, return its finalized field and `time_limit`
or `iteration_limit` as appropriate. Final reconstruction, turbulence, output
extraction and transfer remain required after stopping and are timed separately;
they can exceed the solve budget. No API wall-time guarantee is implied.

Check time before initialization, after initialization, after RHS, after every
CPU sweep and after diagnostics. Mutex wait is included; inspect expiry as soon
as the lock is acquired. Bounded-mode expiry takes precedence once observed;
record any simultaneously satisfied legacy criterion independently. Legacy mode
retains success when convergence occurs on its last allowed sweep. Adaptive
mode is reserved for S7, with fresh same-iterate acceptance checks completed
before the deadline and its own warning/exception contract.

## Study caps and parity gates

S0 profiling workers run sequentially with 30 s subprocess limits and a 180 s
total matrix limit, excluding builds. Import/setup is inside worker limits but
outside API timers. Failed or timed-out workers are archived and never retried
with expanded budgets. Profiling uses the existing 9,420,800-cell tower and
actual 92-layer automatic grid. It does not run new reference trajectories.

Revision parity runs all 429 cases in each backend, with OpenMP teams 1, 2, 4
and 8 and serial team 1. Each case-matrix subprocess has a 180 s limit.
Serial/OpenMP differences are reported as expected until S2 deliberately changes
the ordering; `--require-backend-parity` becomes mandatory at that gate. The
S0-only `--allow-added-contraction` exception permits only the new provenance
field against an older baseline; all arrays and numerical diagnostics remain
strictly bitwise. Team comparisons are always strict. Baseline and working-tree
builds use the same compiler and configuration.

Effective bandwidth from modeled logical bytes and measured sweep time is
reported as an estimate. It does not measure DRAM traffic or establish a memory
bottleneck by itself. Record array sizes/capacities and process high-water RSS
separately; do not present summed allocations as measured resident memory.


## S5b completed-iterate diagnostics

The native phase API now provides `equation_residual(region, floors)` and
`diagnose_cell(i,j,k)` as pure observations. The former evaluates `b-A*lambda`
with `A=D-sum(neighbor coefficients)`, `b=-R`, no row scaling, and double
reduction arithmetic on the stored iterate. It reports maximum/volume-weighted
RMS, initial/RHS norms, explicit positive normalization floors and assessed
counts; empty assessments have absent relative results. Ground ghosts,
prescribed shell values and the existing fluid mask are retained. No physical
length or acceptance threshold is inferred. The latter exposes a small cell
record of row, neighbor and initial/corrected-face evidence. Neither allocates
another persistent volume or changes sweeps, legacy convergence or controller
metadata. See the [S5b contract and evidence](solver-control-s5b.md).


## S5c condition-mask invariant

Condition parameterizations may classify existing fluid cells but must preserve
prepared solid/ground flags 0/2. Both canyon routines now respect this invariant;
solid-owned initial faces remain zero and the immutable wall operator agrees
with condition eligibility. This is a separately archived numerical correction,
not a diagnostic exclusion. Historical 429-case outputs remain exact; the
explicit added corner cases record the intended changes. See the
[S5 completion ledger](solver-control-s5.md) for the measured performance
non-pass disposition and the remaining large-grid accuracy limitations.

# S4: bounded native execution through Python

This records the S4 implementation. The current adaptive/API/dataset status
and release scope are documented in the [S9 closure](solver-control-s9.md).

S4 adds optional bounded execution to `wind.run`, with a compiled monitor and
structured timing/termination/history record. Accuracy is always `not_assessed`.
The existing multiplier-change boolean remains `result.diagnostics.converged`.

```python
from dtcc_qes import wind

control = wind.SolverControl(
    max_solve_seconds=5.0,
    monitor=wind.MonitorSpec(
        region=(100, 420, 100, 420),  # xmin,xmax,ymin,ymax, local metres
        heights=(1.5, 1.75),
        receptors=(wind.Receptor("crossing", 180, 200, 1.5),),
        history_limit=16,
    ),
    checkpoint_interval=25,
    residual_interval=0,
)
result = wind.run(city, 5, 270, solver_control=control)
print(result.control["termination_reason"])
print(result.control["timings"])
```

The ROI must fit the prepared physical domain. `frame="world"` interprets x/y
in the input city's frame; origin and CRS come from the prepared geometry.
Heights are always metres above flat ground. Required receptors remain visible
when their support is invalid. Python value objects copy mutable input sequences
into tuples, and bindings copy every input before releasing the GIL.

## Time and output contract

`max_solve_seconds` begins at native solve entry, including process-wide mutex
wait, condition initialization, workspace/RHS preparation, whole sweeps and
checkpoints. Checks occur immediately after lock acquisition, around preparation
phases, before and after every sweep, around monitor compilation/capture and
before finalization. Deadline expiry takes precedence over simultaneous legacy
tolerance/iteration events; the legacy tolerance flag remains recorded separately.
Without controls the original legacy path and warnings remain available.

This is a cooperative budget. A running native phase and an uninterruptible
mutex wait can overrun it. Once at least one sweep completes, expiry returns the
latest finite completed iterate with `termination_reason="time_limit"`.
Necessary face reconstruction, conservative mass diagnostics, turbulence and
owned output construction follow stopping. Prior geometry preparation and
NumPy transfer have separate timers. Applications needing hard process limits
must retain an external subprocess deadline.

If no sweep completes, `wind.BudgetExhaustedError` exposes a JSON-serializable
`record` with phase and timing evidence and returns no wind field. Invalid inputs
and numerical failures retain their exception paths. Failed calls clear the
runner workspace so a subsequent condition starts cleanly. Native and Python
configuration validation reject adaptive mode and invalid budgets/intervals.

`result.control` is also stored in `result.metadata["solver_control"]`. It includes:

- Termination reason (`legacy_tolerance`, `iteration_limit`, `time_limit`),
  completed sweeps, legacy tolerance satisfaction and accuracy status.
- Effective monitor coordinates/CRS/Uref, region bounds and excluded-cell counts,
  monitor buffer bytes, total captures and bounded chronological summary history.
- Initial reconstruction explicitly marked iteration zero; it provides no
  stability interval. Full plane/volume histories are not returned.
- Actual team size, precision, backend, ordering, native build information and
  effective result shape; the result metadata retains the effective grid/model.
- Preparation, mutex wait, initialization, workspace allocation, RHS, sweeps,
  monitoring, finalization, postprocessing and output-transfer timers. Solve
  elapsed/overshoot exclude necessary post-stop output work; native total
  includes that work. Python preprocessing is outside the native solve budget.

`checkpoint_interval` controls expensive slab/regional observations independently
of clock checks. `residual_interval=0` disables residual collection; a positive
interval collects on those numbered sweeps. An intermediate trend is not silently
reused at a later checkpoint. Global mass at checkpoints is optional through
`MonitorSpec(global_mass=True)`. Final conservative diagnostics remain available.
Residual trends retain native algebraic RHS units on a partly updated sweep;
they are not physical divergence in s^-1 or a velocity-error estimate. Regional
and final six-face divergence records remain in s^-1.
The S3 memory cap applies to compiled monitor buffers; returned compact summary
copies and Python serialization have their own bounded-history overhead.

Legacy `raise_on_nonconvergence` and warning behavior also apply in bounded mode,
with the termination reason added to the message. A legacy tolerance success
does not imply an accuracy assessment. Dataset calls accept the JSON-compatible
`asdict(control)` form in `solver_control`; settings participate in dataset
arguments/identity, execution history is serialized into provenance/health, and
time-budgeted output is marked nondeterministic. Actual completed work must be
inspected when comparing or reusing such results.

## Validation and next milestone

Native fake-clock tests exercise every deadline boundary, zero-work failure,
simultaneous deadline/convergence precedence, output overrun scope, bounded
history and fresh/reused/failed-then-retried solves. Both precisions compare
controlled fields with legacy fields at equal completed work. Python tests cover
world coordinates, configuration snapshots, JSON round trips, warnings,
exceptions, dataset provenance and a hard-capped multithreaded subprocess.

The [S4 evidence manifest](data/solver-control-s4/manifest.json) records the source
identity and final numerical, native, Python, sanitizer and artifact gates.
Frozen S0–S3 evidence remains unchanged. The comparison harness stages a
`sitecustomize.py` that removes this package's editable import redirector;
archived comparisons must import both Python and native code from their intended
package. Dependency installations remain available.

The reproducible S4 source identity is
`sha256:b2d4cd6e8708a4058187a8284195a67805f78b226e156a3f13981b903a8d63fe`.
This is an uncommitted source snapshot, with no new git revision claimed.

| Check | Result |
| --- | --- |
| Release native, OpenMP / serial | 45 / 42 passed |
| Full Python suite, each frozen backend | 1,021 passed, 16 historical-order skips |
| ASan/UBSan lifecycle/phases/monitor/controller | 4 passed; final controller timing refinement also passed |
| Packaged-wheel build/condition-state/controller tests | 62 passed |
| Native symbol audits, all three builds | Passed |
| Strict S3 comparison | 429 cases, 3,872 records, all 12 revision/team/backend comparisons passed |
| Urban integration smoke | 12 workers completed; all 8 candidate/baseline comparisons bitwise equal |
| Wheel/source contents and S4 evidence audits | Passed |

During final validation an independent edit to the live `datasets.py` added an
incomplete slice speedup expression. Tests staged during that edit reported 34
slice failures in each backend. The concurrent edit is preserved outside the
S4 source snapshot. Final Python suites and release packaging use the frozen
snapshot above; those passes do not claim that the independently edited live
file is valid. Failed logs are retained separately from accepted validation.
The packaged wheel is also checked against the frozen Python source hashes.

Validate the frozen evidence locally or in a source distribution with:

```sh
.venv/bin/python docs/data/solver-control-s4/audit.py
.venv/bin/python docs/data/solver-control-s4/audit.py \
  --sdist build/s4-artifacts/dtcc_qes-0.1.0b1.tar.gz
```

The next milestone is the [urban benchmark suite](urban-wind-benchmarks.md).
It provides frozen neighbourhood geometry/grids, isolated archived-source
builds, bounded sequential shards and offline field comparisons. Initial smoke
execution verifies the machinery; S5's repeated realistic-resolution cost
campaign and any matched-error qualification remain separate work. S6 decides
the iteration method before S7 calibrates automatic accuracy acceptance.

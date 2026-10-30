# S1: phase-based solver extraction

Completed 2026-10-29. S1 reproduces the S0 solver bitwise and is ready for the
required review before S1a. The public API retains float32, 500 iterations,
tolerance 1e-5 and each backend's existing ordering. No public continuation,
deadline or accuracy-acceptance policy is introduced.

## Implementation

[`src/qes_core/solver`](../src/qes_core/solver/solver.h) now contains one phase
driver and separate float32/float64 CPU arithmetic. The original `Solver`,
`Solver_CPU`, `Solver_CPU_RB`, `SolverFactory` and `PrecisionSolver` files are
removed, including the unused CUDA factory hooks. Original contributor notices
remain in the derived kernels; [provenance](../src/qes_core/PROVENANCE.md) records
their new locations. The frozen S0 sources remain the numerical oracle.

`PoissonOperator` validates the explicit coefficient arrays once during
preparation and borrows them immutably from `WINDSGeneralData`; it does not
duplicate six volumes. The prepared model outlives the operator, which outlives
the solver workspaces. S2 will transfer storage ownership when introducing the
compact representation.

`SolverState<float>` and `SolverState<double>` provide these internal operations:

| Operation | Behavior in S1 |
| --- | --- |
| `begin(condition, total_sweeps, stop_rule)` | Validate original faces and current post-parameterization flags; clear workspace; build RHS once. |
| `advance(work_sweeps)` | Complete whole sweeps up to the cumulative budget or legacy tolerance; return block work, cumulative diagnostics and termination. |
| `observe([first,last))` | Return physical cell-centered layers with flags, without changing the iterate or writing corrected model faces. |
| `diagnose(region)` | Stream reconstructed faces into conservative mass summaries, without a full field allocation. |
| `finalize(faces, optional_centers, optional_mass)` | Reconstruct into caller-owned model faces; optionally collocate output and diagnose the materialized faces. |
| `copy_state_for_study()` | Return explicitly owned multiplier/RHS copies for internal diagnostics. |

Float32 expressions, statement boundaries, lambda copies and norm passes are
preserved. Float64 retains its original operand promotions and fused
update/change calculation. Both use the configured contraction mode (`on` for
the AppleClang 17 builds here). Serial stays lexicographic and OpenMP stays
red/black. S1 makes no performance or memory-reduction claim.

`WindRunner` now explicitly tracks prepared, initialized, solving and finalized
states. It calls the same phases for either precision, reusing allocated
workspace but zeroing each condition. Any exception through initialization,
solving, finalization, turbulence or output discards workspace and restores the
prepared phase. Cell-center averaging has moved from the runner into the
solver's shared reconstruction path. Final global mass diagnostics read the
already-materialized faces to avoid reconstructing the entire field again.

The native checks, `vertical_grid_study` and `near_wall_probe` use the package.
The study's N/2N/4N calculations remain independent zero-start fixed-work solves;
they are not reinterpreted as continuation. Target names and study protocols are
unchanged. Active precision, diagnosis, horizontal, joint-grid and turbulence
source-provenance lists include the new solver files. Closed study records and
their historical snapshots remain unchanged. S0 profiling now explicitly reads
its archived source layout rather than trying to instrument the extracted code.

## Verification

The expanded comparison starts at S0 revision
`bbfd20005e0bd7d7e648438a1bc8d5a9a4358a71`, using the same compiler and build
configuration for each revision:

```sh
.venv/bin/python tools/compare_native_builds.py --baseline bbfd200 \
  --thread-counts 1 2 4 8 --backend-pair --allow-added-contraction \
  --report build/solver-control-s1/parity.json
```

Every revision comparison passed: 429 cases and 3,872 records per matrix,
covering both precisions, stretched grids, long iteration budgets, turbulence,
parameterization combinations, reused runners and precision changes. Outputs,
iteration counts, convergence flags and numerical diagnostics match bitwise.
The provenance exception permits only the contraction attribute added in S0.
OpenMP teams 1, 2, 4 and 8 also agree bitwise. Serial/OpenMP comparisons retain
888 expected record differences per team, because their sweep orders still
differ; those comparisons are recorded, not treated as an S1 failure.

| Check | Result |
| --- | --- |
| Release native tests, OpenMP | 43 passed |
| Release native tests, serial | 40 passed |
| ASan/UBSan native tests, OpenMP | 43 passed |
| Python suite, OpenMP | 953 passed, 18 skipped |
| Python suite, serial | 971 passed |
| Native symbol audits, all three configurations | Passed |
| Near-wall probe build and bounded smoke | Passed |
| Source/wheel contents and wheel import/solve smoke | Passed |
| Frozen S0 archive audit | Passed |

The new phase check covers both precisions and orderings, uniform and stretched
grids, and OpenMP teams 1, 2 and 4. It compares 83 contiguous sweeps with
1+7+75, observing and diagnosing between blocks, and checks exact copied states
and outputs. It verifies early tolerance stops within a block, at a boundary
and on the final permitted sweep; fixed-work completion; no extra sweep after
termination; repeated zero starts; changed condition flags; invalid phase/range
requests; nonfinite failures; recovery; output aliases; and independent study
copies. Observed slabs and global/regional mass summaries match materialized
same-iterate output, including prescribed, ground, solid and upper faces.

The [evidence manifest](data/solver-control-s1/manifest.json) hashes the source
snapshot, parity report and test reports. The source snapshot identifies this
uncommitted work independently of HEAD. Test counts establish implementation
correctness on this machine, not model accuracy or cross-compiler reproducibility.
No new long-running reference trajectory was attempted.

## Review and next steps

The extraction supports the remaining plan. Three constraints must remain
explicit:

1. **Condition inputs stay immutable until the next `begin` or workspace
   destruction.** Observation and repeated finalization reconstruct from the
   original faces and current condition flags, never previously corrected
   faces. The standalone operator borrows storage; only a prepared-model owner
   can ensure this lifetime. Future device uploads must preserve that separation.
2. **Existing boundary exclusions remain deliberate.** Slab indices are physical,
   zero-based, half-open layers. Mass regions are rectangular subsets of the
   legacy assessed interior, excluding lateral cells and the highest physical
   layer, with the last solved band reported separately. S3 must expose assessed
   counts and exclusions when compiling named monitoring regions. These checks
   cannot qualify excluded cells or inadequate pedestrian support.
3. **Runner recovery does not fix empirical-model persistence.** Workspace is
   discarded on failure, but S1 intentionally preserves rooftop-state reuse
   behavior and wake-model input acceptance. S1a must audit and correct those
   separately before a reusable public model or a corrected comparison baseline.

The next implementation is **S1a**: reproduce the rooftop-state defect, reset
condition-specific building state, validate wake dependencies, and compare fresh
versus reused conditions across directions, precision changes and injected
failures. Record the exact changed cases and freeze a corrected baseline while
retaining S0/S1 evidence. Then implement S2's traffic/storage changes one at a
time with bitwise gates and bounded timing/memory measurements. S2's planned
serial ordering change needs its separate backend-parity gate. Monitoring and
public bounded controls remain S3/S4; automatic accuracy acceptance remains
disabled.

Implementation stops after S1 for this review.

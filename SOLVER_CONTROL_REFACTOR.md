# Native solver-control refactor

> Historical implementation plan/report. The integrated API and status are in the [user guide](README.md), [migration table](README.md#api-migration) and [combined plan](COMBINED_FEATURE_PLAN.md). Original snippets below retain their stage vocabulary.

**Status, closed 2026-10-31: scoped solver-control refactor complete; S8b explicitly deferred.**
S5a publishes the five campaigns and tolerance study, completes cadence/thread/
real-deadline studies and explicitly disposes of the missed disabled-controls
performance target. S5b provides coherent diagnostics and two qualified small
same-grid references. S5c separately repairs the diagnosed canyon solid-mask
inconsistency. The [S5 completion report](docs/solver-control-s5.md) and
[portable evidence](docs/data/solver-control-s5/manifest.json) record the gates,
intentional changes and limitations. Broader-domain numerical qualification
remains separate work. [S6's method study](docs/solver-control-s6.md) selects internal red/black
SOR with `1.90f` as the scoped S7 calibration candidate; public calls retain
`1.78f`. Its 43 main workers and eight first-sweep checks are
[archived and replayable](docs/data/solver-control-s6/manifest.json).
[S7's opt-in pedestrian policy](docs/solver-control-s7.md) is qualified on its
declared 80×80×32 uniform/graded scope, with zero false acceptances on the
held-out matrix. Legacy/bounded defaults remain unchanged; larger domains and
other unsupported configurations remain unaccepted. [S8a's measured reuse
pilot](docs/solver-control-s8a.md) defers a public prepared-model API: eight
directions save 49 ms / 6.9% in legacy and 26 ms / 2.5% in adaptive, below
the predeclared benefit gate. S8b is deferred at the user's request.
[S9's release closure](docs/solver-control-s9.md) freezes the qualified
pedestrian scope, compatibility/release evidence and explicit follow-up ledger.

The corrected urban hotspots no longer contain prepared solids relabeled as
fluid. Large-core fields remain numerically unqualified and the prescribed
top-band convention is unchanged. The <=5% disabled API regression review target
is not met (+11–15% in the new confirmation; +12.3% in one selected follow-up).
This is a documented non-pass disposition permitted by S5's exit contract,
not a performance pass or an exemption from numerical safeguards. See the
[S5b diagnostic report](docs/solver-control-s5b.md) for the preserved pre-fix
investigation.

The [S4 implementation](docs/solver-control-s4.md) exposes bounded native
execution through Python and datasets. The [urban benchmark suite](docs/urban-wind-benchmarks.md)
freezes four neighbourhood layouts with 42–160 buildings, realistic-resolution
grids, multiple directions and bounded baseline/candidate comparison shards.
The [S3 implementation and handoff](docs/solver-control-s3.md) records compiled
slab/receptor monitoring, bounded histories, regional mass and optional
algebraic trends. Bounded public controls are implemented; automatic numerical
acceptance is opt-in only within S7's qualified pedestrian scope. The current legacy benchmark candidate is the frozen S5c archive
`f138616b7796f20b3f66e04c2c52f01f6f27c5fcd4122bccc373caf82156adeb`;
the default S1a/S3 comparison baselines carry the same mask correction.
Historical S4 archive `b2d4cd6e8708a4058187a8284195a67805f78b226e156a3f13981b903a8d63fe`
remains unchanged in the evidence.
The [S2 implementation and review](docs/solver-control-s2.md) records norm
fusion, owned compact coefficients, conditional allocation and unified ordering.
Output-copy removal is deferred to preserve the existing ownership contract. The
[S1a corrections and review](docs/solver-control-s1a.md) record the condition-state
audit, intended changes and corrected source baseline. The
[S1 results and next-step review](docs/solver-control-s1.md) record the extracted
solver, bitwise parity and implementation constraints. The
[S0 results and next-step review](docs/solver-control-s0.md) record the baseline,
archives, timings, memory, parity and limitations. The
[S0 interface contract](docs/solver-control-contract.md) resolves the phase and
condition-state prerequisites. This revision replaces the
2026-10-28 plan (prepared against root revision `3f18072`). Since then the QES
core has been vendored into `src/qes_core`, the bridge merged into it, and the
model is constructed from in-memory inputs (`merge-qes-core`, commits `6c2c65c`
to `bbfd200`). Every one of those steps kept all outputs bitwise identical, so
the evidence below still describes the current numerics. The vertical-grid task
is closed under its restricted scope (see the
[closure decision](DYNAMIC_VERTICAL_GRID.md#numerical-review-closed-experimental-automatic-scope)).
The native phase interface, monitoring, bounded Python API and datasets are
implemented. The acceptance policies and later integration described below are
planned work. Updating this plan closes the planning review, not those stages.

## What the merge changes in this plan

The previous plan was shaped by one constraint: the QES solvers lived in a
third-party submodule that should not change. So it put a second kernel in the
bridge, kept the QES solvers as in-tree bitwise oracles, and allowed memory
savings only after "confirming that no later phase reads the QES-owned arrays".
That constraint is gone, and several design decisions change with it:

| Before | Now | Consequence for this plan |
| --- | --- | --- |
| QES solvers in a submodule, kept unchanged as oracles | `winds/Solver*` are owned code | Refactor the solvers in place into one phase-based solver package; no duplicate kernel. |
| In-tree oracle classes | `tools/compare_native_builds.py` builds a baseline revision and compares 429 cases bitwise, including S0's additions | The baseline revision is the oracle. Native tests check invariants, not a second implementation. |
| Coefficients and fields owned by QES's `WINDSGeneralData` | `WINDSGeneralData` is owned | Storage and lifetime are designed, not negotiated: a solver-owned operator replaces `e..n`. |
| Bridge fabricated XML inputs per prepare | Plain inputs (`winds/WindModelInputs.h`, `dtcc/model_inputs.*`) | The per-condition pipeline is explicit and cheap to reason about; state carried between conditions becomes visible (see decision 9). |
| Bindings could include QES headers | `dtcc/api` is the only header set the bindings see (enforced) | New control and result types go in `dtcc/api`; QES types stay inside the solver and runner. |
| GPU deferred, QES CUDA classes "untouched" | A CUDA backend is planned for an upcoming release; QES's GPU solvers were not vendored | Design the phase contract so a device backend fits (decision 8); implement it separately. |
| Evidence hashed live files | Records verify archived source snapshots | New studies archive their sources beside the record. |

Unchanged: the purpose, the evidence and its qualifications, monitoring
semantics, mass diagnostics, termination and acceptance semantics, cooperative
deadlines, deciding the iteration method before calibration, and the candidate
accuracy contract.

## Purpose and sequencing

Provide fast, bounded wind calculations for urban wind and pedestrian comfort
analysis. Keep the default arithmetic **float32**, with **OpenMP enabled by
default**, and let a single native solve continue in blocks while observing wind
at 1.5 and 1.75 m, important receptors, and mass consistency. Return an explicit
reason for stopping and distinguish numerical acceptance from legacy convergence.

The storage/traffic work has delivered substantial speed and memory gains at
equal completed work. The original float32/float64 cost comparison below
predates S2 and must not be presented as a current performance result. The next
question is measured repeated-direction integration and release closure.
S5/S6 supply coherent diagnostics and a method decision; S7 qualifies a
versioned pedestrian stopping policy on new held-out data within a restricted
grid/model envelope. Broader configurations still require their own qualification.

The first deliverable, now implemented, is **native continuation, checkpoint diagnostics and
bounded execution, with automatic accuracy acceptance disabled**, running on an
owned solver package whose per-sweep memory traffic has been reduced with
bitwise-unchanged results. S6 preserves that default and freezes the internal
`1.90f` candidate used by S7's qualified opt-in policy. Promotion to a default operating policy
is a separate decision requiring validation across the supported scope.

Closure requires the explicit gates in S9. A useful bounded result is already
available; it does not make S7 complete. If a reference or calibrated policy
cannot be qualified within its declared envelope, retain the bounded-only
behavior, record the missing qualification and a named follow-up. Closing that
restricted milestone must be an explicit scope decision, never an automatic
substitute for completing the acceptance roadmap.

Preserve uniform x/y spacing, explicit and automatic vertical grids, and the
pedestrian-height support established by the grid work. Monitoring cannot fix
inadequate vertical support or make a receptor lie in the third cell. Grid
construction stays geometry-only, with its roughly 0.1 s planning objective.
This refactor must not reopen the vertical-grid task: do not resume the stopped
hours-long finest-grid reference or turn its missing result into a pass.

## Current urban evidence and consequences

The five completed campaigns below contain **324 completed workers and 216
candidate/baseline comparisons**. All comparisons have matching grids, completed
work and bitwise-equal full velocity/flag fields. All workers used float32,
Release/AppleClang 17, `fp_contract=on`, and an actual four-thread OpenMP team.
Each case/direction/variant has three process repetitions. These are local
measurements on deterministic synthetic urban morphology, not physical
validation or a portable timing guarantee.

| Campaign | Completed workers | Main observation |
| --- | ---: | --- |
| [4 m, S1a → S4, 500 iterations](build/urban-benchmarks/20261030T113311Z-44150a27/results.json) | 36 | Controls disabled: 1.66–1.76× API speedup, approximately 10–14% lower peak RSS. |
| [2 m, S1a → S4, 500 iterations](build/urban-benchmarks/20261030T113701Z-fb78576f/results.json) | 108 | 1.74–1.99× speedup and approximately 26–30% lower peak RSS across four neighbourhoods and three directions. |
| [4 m, S3 → S4, 500 iterations](build/urban-benchmarks/20261030T114345Z-c5e93cfb/results.json) | 36 | Disabled-controller API cost within approximately 2% of S3. |
| [2 m, S1a → S4, 2,000 iterations](build/urban-benchmarks/core-2000-20261030-clean/long-run-comparison.json) | 108 | 1.80–2.16× speedup; RSS reduction 10.8–30.0%, median 27.0% across case/direction medians. |
| [4 m, S3 → S4, 2,000 iterations](build/urban-benchmarks/controls-2000-20261030/long-run-comparison.json) | 36 | Disabled-controller API change −0.9% to +1.1% using ratios of variant medians. |

The corrected S1a archive is the baseline for combined storage/traffic/control
gains. S3 isolates S4's controller overhead. They do not isolate S2 from S3;
use the stage reports for that attribution. S0 retains its historical adapter,
condition-state defects and serial-ordering qualifications; a new S0 adapter is
not required to finish S5.

The 2 m grids contain 3.6–6.3 million cells, 42–160 buildings, and winds FROM
225°, 270° and 315°. Reuse verified source builds with the
[single-command runner](tools/run_urban_benchmarks.py); generate fresh fixtures
and results for each protocol. The long-run command is:

```sh
.venv/bin/python tools/run_urban_benchmarks.py --tier core \
  --iterations 2000 --solve-seconds 20
```

The 2,000-iteration runs deliberately used a **20 s native solve budget**, not
the original 5 s. External limits remained 30 s per worker and 180 s per
six-worker shard; all 144 long-run workers completed exactly 2,000 iterations.
The initial attempt at `build/urban-benchmarks/core-2000-20261030` overlapped an
independent pytest process and is explicitly interrupted/excluded. Only the
`-clean` campaign above contributes timing evidence.

Consequences for the remaining work:

- **The architectural performance case is established locally.** Preserve the
  measured gains and strict legacy trajectory gates. More equal-work timing
  alone will not answer the remaining accuracy question. Peak RSS is variable
  between repetitions, especially in the longer baseline runs; report ranges
  and allocation bytes separately. Do not promise a universal 26–30% saving.
- **Cadence is not closed.** Enabled-monitor API overhead is 3.2–16.0% on the
  2,000-iteration core and 10.3–17.1% on its control pilot. The 10% review target
  is not uniformly met. Continuous residual collection was already expensive
  in S3; coherent residual checks will have their own measured cost.
- **Legacy convergence is not numerical acceptance.** None of the 324 workers
  satisfied `tolerance=1e-5`. At 2,000 core iterations, maximum multiplier
  changes remain approximately 66–626 times that threshold. Do not attribute
  all failures to a float32 floor or relax the threshold to obtain passes.
- **Small recent changes can hide substantial remaining motion.** Downtown at
  225° changed by approximately 0.4% of Uref at pedestrian vector p95 over
  iterations 475–500, yet by 5.5% at p95 and 14.6% at maximum between 500 and
  2,000. These are iterate differences, not errors against a qualified reference.
- **Persistent mass hotspots need diagnosis first.** At 2,000 iterations,
  interior maximum divergence remains about 3.58 and 3.92 s^-1 for downtown
  225°/315°, and 3.30 s^-1 for courtyard 225°, despite improved RMS values.
  Baseline/candidate field equality makes this inherited behavior, not a newly
  demonstrated S4 regression. Locate and classify the cells before deciding
  whether they represent iterative error, mask/operator inconsistency or a
  documented model/boundary limitation. Do not discard them to pass a gate.
- **Real deadline behavior still needs its own experiment.** Long-run native
  solve times were approximately 4.20–6.84 s under the 20 s budget. These runs
  validate long equal-work execution, not time-limited quality or overshoot.

The [courtyard tolerance-scaling study](build/legacy-tolerance-investigation-20261030/results.json)
adds six fixed-cap numerical runs. At 4 m, an illustrative absolute multiplier
tolerance of `0.01` stops after 584/797/970 iterations at Uref 2/5/10 m/s.
Equal-2,000-work normalized fields are nearly identical (p95 vector difference
about 3.2e-6 for 2 versus 5 m/s). This supports nondimensional observable
criteria, not a new `0.01` default. It is one case and one direction, not a
universal inflow-linearity qualification.

The original records above remain at their historical `build/` paths. S5a has
published their original bytes, source/driver identities and independent replay
under the [S5 evidence identity](docs/data/solver-control-s5/manifest.json).
Frozen S0–S5b archives are unchanged. Large-urban accuracy remains unqualified.

## Evidence motivating the work

This section preserves the historical pre-S2 measurements and their original
qualifications. Use the current urban evidence above for present cost claims.

The bounded local benchmarks use a tower, a 270-degree wind, Uref = 5 m/s,
0.5 m horizontal spacing, the actual 92-layer automatic grid, and 9,420,800
physical cells. API timings include preparation, solving, final diagnostics and
full-volume output; they exclude imports, City creation and pedestrian sampling.
The following are observations on the local machine, not universal iteration
prescriptions or comfort qualification:

| Arithmetic / backend | Iterations | API time | p95 speed error at 1.5 m | Largest relative error at the five mandatory points, 1.5 m |
| --- | ---: | ---: | ---: | ---: |
| float32 / OpenMP, 4 threads | 500 | 5.24 s, median of two | 0.1284 m/s | 6.25% |
| float32 / OpenMP, 4 threads | 1000 | 9.79 s | 0.0440 m/s | 2.24% |
| float32 / OpenMP, 4 threads | 2000 | 19.36 s | 0.00752 m/s | 0.412% |
| float64 / OpenMP, 4 threads | 2000 | 11.78 s | 0.00739 m/s | 0.404% |
| float64 / serial, fresh control | 500 | 26.21 s | Not measured in this control | Not measured in this control |

Errors above use an accepted, longer-running **same-grid** serial reference.
They do not measure grid error or physical model accuracy. All these runs still
failed the legacy multiplier-change tolerance of 1e-5. The public and archived
cases use different positions for their single profile sensor; the initialized
profile is horizontally uniform, but initial-field equality was not directly
measured in this API comparison. Preserve that qualification.

At 500 sweeps, OpenMP gave similar pedestrian errors to serial but worse interior
mass residuals. At 2000 sweeps, float64 OpenMP improved both interior maximum and
RMS divergence relative to serial 500, while the separately reported top-band
maximum increased. Thus neither equal iteration counts nor one residual scalar
establish equal accuracy. Float64 being faster in this measurement does not
justify changing the float32 default; it exposes avoidable overhead in the
float32 implementation, described under performance implications below.

These records predate the merge. The merge left outputs bitwise identical
(verified per commit), but per-solve work changed slightly (sensor validation
and Barnes dispatch are gone), so S0 re-measures timings before using them as a
baseline. S0 has now archived this evidence under
[`docs/data/solver-control-s0`](docs/data/solver-control-s0/manifest.json), with
original hashes and source snapshots. Original local evidence locations:

- [Benchmark tool](tools/benchmark_openmp.py),
  [combined local results](build/openmp-benchmark/20261028T194857Z/results.json),
  [benchmark protocol](build/openmp-benchmark/20261028T194857Z/protocol.json),
  and [supplement protocol](build/openmp-benchmark/20261028T194857Z/supplement-protocol.json).
- [Float32 protocol](build/accuracy-budget-float32/protocol.json),
  [1000-sweep record](build/accuracy-budget-float32/1000.json), and
  [2000-sweep record](build/accuracy-budget-float32/2000.json).
- [Accepted generated-grid pilot](docs/generated-grid-pilot.md),
  [refinement findings](docs/vertical-refinement.md),
  [stopped reference and runtime review](docs/finest-reference.md), and
  [OpenMP build verification](docs/validation.md#openmp-validation).

The `build/` links are local evidence and are not portable archives. Do not
edit existing frozen evidence or pretend these exploratory results were
evaluated against a predeclared production acceptance contract.

### Performance implications

The same records support the following engineering conclusions for the local
machine (Apple M4 Pro, 14 cores). S0 measured pass costs and allocations; S2
must measure the corrected S1a implementation before making changes. These
observations are not hardware-independent guarantees.

- **Float64 scaling suggests bandwidth pressure.** Float64/OpenMP at 500 sweeps took
  10.39, 5.58, 3.25 and 3.11 s with 1, 2, 4 and 8 threads. Additional threads
  stop helping at about four in this float64 measurement. S0 also finds a
  float64 plateau, but float32 still improves at eight threads. Reducing
  traffic remains worthwhile; no hardware DRAM counters were collected, so
  the bottleneck mechanism is not established by these timings alone.
- **The float32 default costs more per sweep than float64.** Its marginal cost
  is about 9.1 to 9.6 ms per sweep (the 500, 1000 and 2000 rows above), against
  about 5.5 ms for float64 (3.25 s at 500 sweeps, 6.02 s at 1000), although
  float32 moves fewer bytes. Each float32 red/black sweep copies lambda to
  lambda_old over the whole volume, runs two color passes that each stream all
  six coefficient arrays and the RHS, and runs a separate full-volume change
  pass, with two more barriers than the float64 kernel.
- **The coefficients are exactly compressible in the current configurations.**
  `Wall` sets each of e, f, g, h, m and n to 0, 1 or a neighbor's value, then
  `Wall::solverCoefficients` divides them once by dx², dy² or a per-layer dz
  product. Each stored value is therefore zero or one of a few per-axis or
  per-layer constants. The cut-cell building path (kept, not built) can assign
  fractional values instead.
- **Convergence is slow and geometric.** The p95 speed error at 1.5 m fell by a
  factor of about 0.34 from 500 to 1000 sweeps and about 0.41 per 500 sweeps
  from 1000 to 2000, roughly 0.998 per sweep. The accepted same-grid reference
  needed 16,000 sweeps, and the maximum multiplier change after 2000 float32
  sweeps was still 9.2e-4. After 2000 sweeps, in both precisions, K was below
  the reference at all five mandatory points at both heights. This one-sided
  bias is consistent with a slowly decaying smooth error mode, as expected for
  fixed ω = 1.78 on grids with hundreds of cells per side, where the optimal SOR
  factor is likely closer to 2. Anisotropy, vertical stretching and buildings
  change the optimum, so it must be measured.
- **Successive checkpoint differences understate the remaining error.** With a
  geometric decay ratio q per checkpoint interval and a latest change d, the
  remaining error is approximately d·q/(1 − q). The ratios above give q of about
  0.81 to 0.84 for 100-sweep intervals, so the remaining error is about four to
  five times the last change; for 250-sweep intervals it is about 1.4 to 1.8
  times.
- **The legacy tolerance is dimensional.** Multipliers scale with Uref while K
  does not: an earlier three-building check found K independent of Uref = 2, 5
  and 12 m/s to about 2e-6. A fixed 1e-5 multiplier-change tolerance therefore
  demands more relative accuracy at higher wind speeds, and in float32 it can
  lie below the roundoff floor on large domains; canyon cases stalled near 5e-5.
- **Compiler contraction affects bitwise parity.** AppleClang 17 fuses
  `a*b + c` within one expression into a fused multiply-add by default, but not
  across separate statements. S0 queries and pins each configured compiler's
  actual mode, rather than assuming GCC shares the Apple default. Expression
  shape, not only operation order, therefore determines bitwise results, and
  cross-compiler bitwise equality is not an S0 requirement.
- **Memory is dominated by arrays the sweep barely needs.** A wind-only float32
  solve holds, per cell (approximate accounting, measured in S0): six coefficients
  (24 B), six face velocity arrays (24 B), the solver's RHS, lambda and
  lambda_old (12 B), cell flags and their copy (8 B), cut-cell arrays that the
  stair-step model never uses (`building_volume_frac`, `ni/nj/nk`,
  `wall_distance`, `center_id`; 24 B), `ibuilding_flag` (4 B) and the
  turbulence-only `mixingLengths` (8 B, allocated even without turbulence),
  about 104 B, plus output copies. Turbulence adds about 110 B. Roughly half of
  the wind-only footprint can go without changing arithmetic (decision 2), which
  matters for the 40–100 M cell cases and for device memory.

## Current structure

| Location | Current behavior | Consequence for the refactor |
| --- | --- | --- |
| [`dtcc/api/wind_config.h`](src/qes_core/dtcc/api/wind_config.h), [`control_types.h`](src/qes_core/dtcc/api/control_types.h) | QES-free solver and bounded-control/result contracts; legacy defaults remain 1e-5, 500, float32. | Extend opt-in policy evidence without silently replacing defaults or exporting QES internals. |
| [`dtcc/wind_runner.cpp`](src/qes_core/dtcc/wind_runner.cpp) | S1 prepares one operator and routes each condition through initialization, `begin`, `advance` and `finalize`, then turbulence. Failed solves discard workspaces and return to prepared state. S1a resets rooftop state and validates wake dependencies. | Repeated Python calls remain independent zero starts; retain S1a's reuse and failure-recovery checks. |
| [`solver/`](src/qes_core/solver/solver.h) | Shared phase driver and precision-specific CPU kernels. S2 uses red/black defaults in both builds, with explicit lexicographic controls. Both precisions retain RHS, lambda and small relaxation tables; no old-iterate array. | Monitoring preserves the trajectory; S5b adds pure completed-iterate diagnostics. |
| [`solver/solver.cpp`](src/qes_core/solver/solver.cpp) | Operator coefficients are checked once per preparation; condition fields once per `begin`. Pure slab observations and streamed mass diagnostics share reconstruction with finalization. | Preserve original face arithmetic, condition flags and borrowed-input lifetime in later backends. |
| [`winds/WINDSGeneralData`](src/qes_core/winds/WINDSGeneralData.h), [`Wall.cpp`](src/qes_core/winds/Wall.cpp) | Owns geometry, flags and face velocities. `Wall` builds coefficients once; production transfers/releases them into the immutable compact/explicit operator. Optional cut-cell and mixing-length arrays allocate on use. | Current condition flags remain independent of operator masks. |
| [`winds/LogProfile.cpp`](src/qes_core/winds/LogProfile.cpp), parameterization files | Per condition: zero-fill `u0/v0/w0`, single-sensor log profile, reset condition-dependent building state, empirical models in height order. S1a audited the supported pipeline. | Initialization happens once per condition; current post-parameterization flags remain separate from the geometry operator. |
| [`dtcc/divergence.cpp`](src/qes_core/dtcc/divergence.cpp), [`mass_diagnostics.h`](src/qes_core/solver/mass_diagnostics.h) | Shared conservative six-face diagnostics and S3 named regions; exclude lateral cells/highest physical layer and report the last solved band separately. | Preserve eligibility and classify persistent interior hotspots before calibrating acceptance. |
| [`dtcc/monitor.cpp`](src/qes_core/dtcc/monitor.cpp), [`solver_control.cpp`](src/qes_core/dtcc/solver_control.cpp) | Compiled ROI/receptor observations, bounded short/long histories, regional mass and optional update-time trends; S4 controls time/iteration stops with quality unassessed. | Add coherent checks and policy decisions while retaining clock, purity and memory contracts. |
| [`src/cpp/bindings.cpp`](src/cpp/bindings.cpp) | Inputs copied before releasing the GIL; one process-wide mutex (required because the `qes::log` handler is global); output vectors copied once more into NumPy. | Keep continuation inside one native call; no Python callbacks or full-volume output per checkpoint. |
| [`tools/compare_native_builds.py`](tools/compare_native_builds.py) | Baseline/candidate revisions or source archives; strict 429-case array/diagnostic comparisons, team and backend pairs. S2 adds an explicit serial migration policy that requires the unchanged OpenMP oracle and the exact old-serial change set. Valid wake-free inputs remain separate S1a tests. | The parity oracle for every stage; strict revision comparison remains the default. |
| [`tools/run_urban_benchmarks.py`](tools/run_urban_benchmarks.py), [`benchmark_urban_wind.py`](tools/benchmark_urban_wind.py) | One-command frozen-source build/cache checks, fresh fixtures, sequential shards and terminal/JSON reports; explicit iteration/native-budget overrides preserve external deadlines. | Reproduce and audit the accepted local cost baseline; add only finite, declared study protocols. |
| Native tests and study tools | Use `SolverState`, fixed sweeps, prepared operators and copied current state. Diagnostic studies own a pre-final-sweep snapshot. Precision probes follow the selected order; historical drivers explicitly request their archived order. | Keep source identities and avoid full-volume production checkpoint copies. |
| [`result.py`](src/dtcc_qes/result.py), [`wind.py`](src/dtcc_qes/wind.py), [`comfort.py`](src/dtcc_qes/comfort.py) | `converged` describes multiplier change; height sampling interpolates collocated float32 components in float64 with strict validity. Each `wind.run` creates a runner and prepares the geometry again; comfort assesses fields the caller solved one direction at a time. | Monitoring must reproduce the sampled observable. Multi-direction reuse is a later stage (S8), measured first. |

## Target architecture

```text
src/cpp/bindings.cpp            Python boundary; sees only dtcc/api
src/qes_core/dtcc/api/          QES-free config, control and result types
src/qes_core/dtcc/              runner state machine, solver controller,
                                monitors, model inputs, output, diagnostics
src/qes_core/solver/            Poisson operator, solver state, kernels
                                (CPU now, a device backend later)
src/qes_core/winds/ qes/ util/  model: geometry, initial field,
                                parameterizations, turbulence
```

`winds/` builds the model, `solver/` solves the mass-consistency problem, and
`dtcc/` orchestrates. The solver sources join the `qeswindscore` target, so the
symbol audit and the no-I/O link check cover them without CMake changes. Code
derived from `Solver_CPU*` keeps its QES notices, and `src/qes_core/PROVENANCE.md`
records the replacement.

Ownership and lifetime:

- **Per prepared geometry:** `WINDSGeneralData` (flags, initial and corrected
  faces), the solver's `PoissonOperator` (built from it once, validated once),
  optional turbulence. Reused for every condition.
- **Per condition:** the initial field (profile plus parameterizations) and a
  fresh `SolverState` (RHS, multipliers, iteration count, last measured change,
  termination). A new condition, precision change or preparation invalidates
  the state. Condition inputs include current post-parameterization cell flags,
  separately from the immutable geometry operator; masking and diagnostic
  eligibility use those flags. See the [S0 contract](docs/solver-control-contract.md).
- **Per solve call:** the controller, monitors and bounded checkpoint history.

Runner states: `prepared → initialized(condition) → solving(blocks) →
finalized`. A failed solve returns to `prepared` with no resumable partial
state. Failed preparation keeps the previous geometry, as today. Destruction
order stays: solver state and operator, then turbulence (which points at the
wind data), then the wind data.

## Design decisions

### 1. One phase-based solver package, with the baseline revision as oracle

Refactor `Solver`, `Solver_CPU`, `Solver_CPU_RB`, `SolverFactory` and
`PrecisionSolver` into one package in `src/qes_core/solver/` with explicit
phases. Names are finalized in S1:

```text
PoissonOperator::build(wind)   # once per geometry: coefficients, open faces,
                               # per-layer factors; validates finiteness once
begin(operator, condition)     # velocities AND current flags; zero state, build RHS
advance(work, stop_rule)       # whole sweeps; keep state; report work, last change
observe(layers, destination)   # finalize a layer range into a monitor buffer
diagnose(regions, destination) # current-iterate six-face mass summaries, no volume copy
finalize(destinations)         # corrected faces for turbulence AND centered output
```

Each precision keeps its arithmetic. Float32 reproduces the expressions,
operand promotion and sweep order of `Solver_CPU` and `Solver_CPU_RB`, and
float64 reproduces `PrecisionSolver`. Loop drivers can be shared; innermost
expressions and statement boundaries cannot, because contraction applies within
an expression. The two precisions measure their update norms differently; do
not unify them by accident. Ordering (lexicographic, red/black) and the
relaxation factor (default `1.78f`) are kernel parameters. S1 keeps each
build's current ordering, so every existing path can be matched bitwise.

No duplicate kernel is kept as an oracle. `tools/compare_native_builds.py`
against the S0 baseline revision checks outputs and iteration diagnostics
bitwise in both backends and precisions. Native tests check what the harness
cannot see: block-partition invariance, observation purity, early stopping at
block boundaries, and state invalidation. After S1 the old classes are deleted.
The fixed-sweep study control becomes an explicit kernel option instead of a
negative tolerance in a subclass.

State requirements:

- Retain RHS, multipliers, cumulative iterations, the last measured update and
  termination state between blocks. Do not reapply parameterizations, rebuild
  RHS, or allocate full-volume arrays at each block.
- A red/black sweep includes both colors, their barriers and the ground mirror
  boundary. Only expose a checkpoint after a complete sweep. Preserve each
  build's sweep order until S2 changes it deliberately, operand promotion,
  boundary loop extents, and the existing nonfinite checks.
- For legacy mode, test multiplier convergence every sweep, including the first
  one. A block boundary must not force an extra sweep after convergence or reset
  the measured-change sentinel.
- Reconstruct velocity from the original `u0/v0/w0` and the current multipliers.
  Never accumulate a new correction onto already corrected velocity.
- Validate the operator once at preparation and the initial field once per
  condition, instead of re-checking constant coefficients on every solve.
- Keep all blocks inside one `WindRunner::solve()` call initially. Public
  cross-call continuation, serialized restart files and warm starts between
  directions are later features, each needing separate invalidation rules.

### 2. Reduce per-sweep traffic and memory without changing arithmetic

Per-sweep traffic is substantial, and resident bytes per cell set the largest
feasible grid. S0 separates measured pass costs from the unconfirmed bandwidth
bottleneck hypothesis. Make these changes in S2, each measured separately.
Items 1 to 3 must be bitwise against the corrected S1a source archive on the
same compiler/configuration, backend, precision and ordering. Item 4 has a
separate gate for its deliberate serial trajectory change:

1. **Fuse the change measurement into the update.** Compute each cell's change
   from its value immediately before the update, reduce the maximum in the same
   pass, and remove `lambda_old`, its copy pass and the separate change pass.
   In both red/black and lexicographic order, each updated cell is written once
   per sweep, so its pre-update value equals its start-of-sweep value. The
   existing float32 norm excludes the mirrored ground ghost (`k=0`); unchanged
   lateral and highest-layer cells remain at their finite zero-start values.
   Preserve the ground mirror after both colors and include every currently
   updated cell in the reduction, including solid cells. Store the updated
   float32 value in a named float before subtracting, keep the update expression
   and float64 change as they are, and preserve nonfinite detection and failure
   invalidation. Port study diagnostics that require `previous_multipliers`:
   for diagnostic fixed-work runs only, copy the iterate before the last sweep
   and pass that study-owned snapshot explicitly. Production must retain no
   previous-iterate array or copy pass.
2. **Store the operator compactly.** At operator build, check that every
   coefficient read by the sweep, RHS, finalization and divergence code is zero
   or bitwise equal to its per-axis (e to h) or per-layer (m and n) constant,
   computed with the expression used by `Wall::solverCoefficients`. Preserve
   the unscaled ghost/highest-layer coefficients too: `Wall` scales only
   `1 <= k < nz-2`. Compare exact float bits, including zero signs; an
   unrepresentable value selects the explicit fallback. If representable, use
   one six-face mask byte per cell and small tables of the original float
   coefficients. The mask comes from coefficients, never condition flags.
   Precompute ω/diagonal per (mask, layer) in precision-specific workspace,
   since relaxation belongs to `SolverState`. Retain float32 summation versus
   float64's widened sum, the exact division and existing expression shapes;
   do not replace division with multiplication by a separately rounded inverse.
   Do not introduce a new preparation failure for zero diagonals that currently
   fail during solving. Dispatch compact/explicit kernels outside the cell
   loop where practical, and measure table/mask decoding overhead.
   Transfer coefficient ownership before releasing `e..n`: the present
   `PoissonOperator` and `KernelFields` borrow them. The explicit fallback must
   own its arrays. Port all later readers, including `dtcc/divergence.cpp`,
   native fixtures and `vertical_grid_diagnostics.cpp`, to the prepared operator;
   none may reconstruct it from emptied wind-data arrays. Retain mass
   diagnostics' coefficient-based area recovery and expression order; rounded
   coefficients do not recover exactly Boolean areas.
3. **Allocate only what the configuration uses.** Allocate the cut-cell arrays
   only when cut cells are built (never, today) and `mixingLengths` only with
   turbulence, before either supported local-mixing method uses it. Guard or
   replace active readers before removing allocations: in particular,
   `Wall::defineWalls` reads `building_volume_frac` for stair-step buildings too.
   Its absent-array behavior must retain the current stair-step value of 1.
   Cover that path with buildings under sanitizers, plus both turbulence methods
   and repeated preparation. S1 already finalizes into caller-owned face and
   centered-output vectors. Keep the remaining NumPy copy in core S2: existing
   public and binding tests require `OWNDATA=True`. A later measured output
   optimization can allocate NumPy-owned destinations and expose a QES-free
   writable-buffer interface, with GIL and lifetime tests. A capsule-backed
   view would require an explicit ownership-contract change; it is not a
   transparent S2 optimization. Measure peak RSS before and after each item.
4. **Use red/black ordering in every build.** Red/black results should not
   depend on team size: each color reads only the other color, and maximum
   reductions are order-independent. Test this bitwise. Using red/black in
   serial builds gives one trajectory per precision, makes serial/OpenMP and
   team-size comparisons bitwise, and halves the trajectories to calibrate. It
   deliberately changes serial-build outputs, so document and review it, and
   keep lexicographic order as an internal option for comparison. Update study
   refinement code and tests that infer ordering from `_OPENMP`; an explicit
   lexicographic request must remain lexicographic in either build.
5. **Later, only if measured as useful.** Updating red cells on layer k and
   black cells on layer k − 1 in one pass streams the operator once per sweep
   with unchanged results, but needs slab-wise OpenMP synchronization. Separate
   red/black storage enables contiguous vector loads. Take these only if the
   kernel is still bandwidth limited after items 1 to 4.

S0 attributed 10.2% of float32 sweep time to change measurement and 4.0% to
the old-iterate copy. Removing those costs entirely would give about 1.17×
speedup if update time were unchanged; fusion also has a cost. The earlier
two-to-three-times estimate is not supported by those measurements. Compact
coefficients may give additional gains but require measurement, and changing
serial ordering does not accelerate the existing OpenMP trajectory. The memory
reductions remain substantial even with the NumPy copy retained. Report actual
gains against S1a, including setup and output costs, without a prescribed speedup.

### 3. Observe exactly what the user samples

Compile a monitor specification once, after preparation and initialization. It
contains heights, an explicit pedestrian region of interest, receptor
coordinates, coordinate frame, interpolation policy and required valid support.
For the initial implementation, monitor native x/y cell centers over that region.
Represent off-center receptors by precomputed bilinear x/y weights, using all
nonzero-weight contributors and strict validity. This is a defined monitor
operation, not a change to the public height sampler. Check it against the
existing study collocation helpers.

Reconstruct monitored values with the package's `observe`, which is
`finalize` restricted to a layer range: full x/y slabs covering every layer that
contributes to a monitored height or receptor, plus the neighboring layers needed
for vertical faces and solid masking, written into monitor-owned buffers rather
than the output arrays. S1 moved cell-centre averaging into shared solver
finalization code, so slabs and final output agree by
construction and no per-receptor face lists are needed. Several heights share
one slab; a distant receptor height adds its own. A slab holds about
nx·ny·(monitored layers)·3 float32 values, about 5 MB for four layers of the
tower case. The slab inherits these finalization semantics:

1. Form corrected staggered face values with the selected solver arithmetic,
   then round to float32 as final output currently does.
2. Apply the same solid mask: either adjacent solid cell makes its shared
   velocity component zero. Respect prescribed faces and unchanged top faces.
   The OpenMP implementation must keep one writer per face.
3. Average to centers with the existing float32 expression and operand order,
   `0.5f * (positive_face + negative_face)`.
4. Widen stored centers and collocated velocities to float64. Locate the original
   requested height without snapping it to float32. Interpolate components,
   then compute speed; never interpolate speed magnitudes instead.
5. Reproduce exact-center behavior, out-of-center-range invalidity, solid flags
   0/2 and nonfinite handling from `WindResult.sample(method="linear")`.

Validity decisions (support, solid flags, out-of-range heights and nonfinite
values) must match `WindResult.sample` exactly. Interpolated values must agree
within a declared tolerance of a few float32 units in the last place rather than
bitwise, because the monitor drives stopping decisions, not published output.

Do not store every sampled plane in the result history. Keep the small number
needed for successive comparisons, plus aggregate checkpoint records. Memory
should scale with the monitored slab layers and the configured history bound,
never with another O(nx·ny·nz) checkpoint field. Check the slab size against
the memory estimate before allocating it.

Monitor both vector change and speed-factor change, percentile and maximum,
each required receptor, peak speed and peak location, validity counts, and the
ratios of successive changes needed for remaining-error estimates (see the
candidate accuracy contract). Include the current and preceding hotspot
locations and the fixed critical set; stable aggregate statistics must not hide
a migrating peak. For the tower fixture retain all five mandatory points at
both heights: (27,21), (21,23), (51,35), (15,47), (15,29). Archive the physical
coordinate frame with them.

### 4. Keep mass diagnostics independent of multiplier change

Retain the existing final conservative maximum and volume-weighted RMS in s^-1,
the separate top-band maximum, counts, and excluded-region metadata. Add the
same measures for the declared pedestrian region/band. Reuse the six-face flux
construction in `dtcc/divergence.cpp`, reading open faces from the operator; do
not substitute the algebraic stencil residual without documenting and testing
its relationship to physical flux balance.

For a cell of volume V, let q_f be the outward signed volume flux through an open
face, including its effective open area. Record:

```text
net_flux = sum(q_f)
divergence = net_flux / V
throughflow = 0.5 * sum(abs(q_f))
relative_imbalance = abs(net_flux) / throughflow   # only for resolved throughflow
```

Use a declared, dimensionally consistent low-flow threshold based on Uref times
open-face area. Below it, mark the relative quantity unavailable and retain
absolute flux/divergence and low-flow counts. Do not divide by an arbitrary tiny
number or silently classify a near-zero denominator as zero error. Calibrate
the threshold; record its definition and value with every accepted policy.
For a region, report signed boundary-flux imbalance and an aggregate of absolute
cell imbalance separately, because local source/sink errors can cancel.

Cheap regional checks can run at each pedestrian checkpoint. For a continuous
global trend, accumulate the algebraic residual inside the sweep, which already
forms it: `next − λ = ω·(neighbors − RHS − diagonal·λ)/diagonal`. The legacy
maximum multiplier change is therefore a maximum-norm residual scaled per cell
by ω/diagonal. Accumulate the residual's maximum and volume-weighted RMS in the
same pass, at the cost of one more reduction. In red/black order it is evaluated
against a partly updated iterate, so treat it as a trend, not an acceptance
quantity. Derive and test its conversion to s^-1 against the six-face divergence
on interior fluid cells of a final iterate before reporting it in those units.

Any future acceptance decision must use fresh checks from the **same completed
iterate**, including its ground mirror, condition flags and prescribed faces.
S5b adds a coherent equation-residual pass and tests its relationship to the
reconstructed six-face flux diagnostics. The existing update-time trend must
never be relabeled as that residual or used directly for acceptance. Residual
reduction does not replace an independently calibrated mass safeguard when
operator eligibility and final face masking differ. Evaluate both global and
required regional checks without another persistent velocity volume; measure
their cadence and final-check costs.

Study a normalized true-residual criterion with relative reduction and an
absolute floor, such as `norm(r_k) <= max(atol, rtol*norm(b))`. Specify the
operator sign, row/volume scaling, assessed cells, norm, RHS/initial-residual
normalization and calm-flow handling. A copied `rtol=1e-5` is not the legacy
test and is not a pedestrian accuracy guarantee. Componentwise/backward-error
checks are an optional diagnostic for severe row scaling, not another required
solver project. See [PETSc's convergence definition](https://petsc.org/main/manualpages/KSP/KSPConvergedDefault/)
and [NASA's residual/observable guidance](https://www.grc.nasa.gov/WWW/wind/valid/tutorial/iterconv.html).

No universal production residual cutoff has yet been established. Set it through
reference calibration in S7. Do not interpret a divergence value in s^-1 as a
percentage velocity error. A small multiplier change may indicate stagnation;
a small checkpoint change may hide a slowly decaying error mode. The legacy 1e-5
multiplier-change tolerance is dimensional and can lie below the float32
roundoff floor; keep it unchanged for legacy semantics, but express every new
threshold, including stagnation, in K or Uref-normalized units.

The last solved band has an uncorrected upper face. Its residual increased in
the bounded benchmark while pedestrian errors decreased. Keep it visible and
test domain-height sensitivity; do not impose an unsupported requirement that
every residual decrease monotonically or change the boundary condition here.

### 5. Separate stopping reason, convergence and acceptance

Keep `SolveDiagnostics.converged` tied to the existing measured multiplier-change
criterion. Add a structured control record rather than overloading that boolean:

| Proposed field | Meaning |
| --- | --- |
| `termination_reason` | `legacy_tolerance`, `iteration_limit`, `time_limit`, `fixed_budget`, `stagnation`, or, after calibration, `target_reached`. |
| `accuracy_status` | `not_assessed`, `target_not_met`, or `accepted`; bounded diagnostic mode can never return `accepted`. |
| `policy_id` / version | Identifies the calibrated contract, scope, normalization and threshold definitions; absent in unqualified mode. |
| `assessment_scope` / numerical checks | For a future policy: the specific ROI/heights/receptors and outputs assessed, true-residual and flux evidence, predictor availability and failed criteria. Pedestrian acceptance does not qualify every returned 3D or turbulence quantity. |
| `iterations` | Total completed sweeps across all blocks, not the last block size. |
| `checkpoint_history` | Bounded records of iteration, elapsed time, changes, validity, mass diagnostics and decision evidence. |
| `timings` | Separately measured preparation, lock wait, initialization, RHS, sweeps, observations, finalization and output transfer where measurable. |
| `execution` | Precision, backend, actual OpenMP team size, requested settings, grid/monitor identity, contraction mode and source/build provenance. |

Invalid inputs and nonfinite numerical failures still raise exceptions; they
must not produce an accepted result. A time or iteration cap may return the
latest finite completed iterate, explicitly marked as unaccepted unless the
calibrated checks were actually satisfied. If no sweep completed, do not invent
convergence or return an initial field disguised as a solved one: raise a
specific budget-exhausted exception with phase/timing diagnostics.

For controlled execution, check deadlines before launching another block and
after observations. If the deadline has expired, report `time_limit`; do not
start an expensive acceptance check to obtain a better status. Otherwise give
`target_reached` precedence over an iteration limit only when all acceptance
checks completed on the current iterate before the deadline. Record satisfied
criteria separately so simultaneous events remain inspectable. In legacy mode,
convergence on the final permitted sweep retains its existing success semantics.

### 6. Use cooperative deadlines with honest timing scope

Use `std::chrono::steady_clock`. Proposed `max_solve_seconds` measures native
solve time from entry, including mutex wait, initialization, RHS, sweeps and
observations. It excludes prior geometry preparation and permits necessary final
reconstruction/output after stopping, including required turbulence
postprocessing. Record these excluded costs separately.
The process-wide mutex cannot interrupt a wait; inspect the deadline immediately
after acquiring it and do no solve work if the budget has already expired.

Read the clock after every complete sweep in controlled mode, independently of
expensive pedestrian checkpoints. A `steady_clock` read costs tens of
nanoseconds against sweeps of several milliseconds on the reference case, so no
coarser cadence is needed; revisit this only for very small grids or a device
backend, where the block, not the sweep, is the natural check point.
Initialization/RHS and diagnostic phases also need phase-boundary checks. This
is a cooperative work budget, not a hard API wall deadline: a running phase,
mutex wait and final output can exceed it. Report measured overshoot. Do not
advertise a bound that these phases cannot provide.

Keep external subprocess deadlines for hard-capped benchmarks and applications
that require them. A killed worker yields no accepted result. Do not attempt
unsafe thread cancellation or claim prompt Python signal handling while native
execution owns the solve. Cancellation tokens can be added separately if needed.

Use finite iteration and wall budgets for every new study. Start from the
existing 30 s per-worker benchmark envelope on the declared local setup, with a
predeclared total matrix cap. A worker deadline includes import/setup time, so it
is distinct from both `max_solve_seconds` and the recorded API timer. Budget
changes need an explicit runtime/accuracy review; do not automatically double
work until a gate passes.

20 million cells remains a soft planning target. Useful 40-million-cell cases
are permitted, and 100 million may be feasible on suitable hardware, more so
after decision 2's memory items. Retain explicit allocation/index guards and
memory estimates; this refactor neither imposes a new hard ceiling nor removes
resource safety checks.

### 7. Decide the iteration method before calibrating a stopping policy

A stopping policy is calibrated against one method's convergence behavior.
Changing the relaxation factor or the method afterwards would invalidate that
calibration, and the evidence suggests fixed ω = 1.78 converges far more slowly
than SOR can on the measured small grids. S6 is complete: `1.90f` is the
scoped internal calibration candidate, `1.78f` remains the public default, and
no Krylov/preconditioner implementation is required. The requirements used
for that decision were:

1. Reuse the existing internal `SolverState` relaxation option, default `1.78f`,
   available to tests and studies. No new public omega parameter is required.
   The useful factor depends on domain size, anisotropy, stretching, buildings
   and the slowest error modes. Verify the actual operator and boundary
   properties rather than inferring optimality from an ideal uniform stencil.
2. Run a bounded fixed-work experiment, for example ω in {1.78, 1.85, 1.90,
   1.95}, on the tower fixture and at least one canyon case. Measure pedestrian
   error against accepted same-grid references, mass diagnostics and cost. Watch
   for transient error growth near the optimum, which affects checkpoint-based
   stopping.
3. If a fixed or grid-dependent factor gives a large gain, decide whether to
   adopt it as a documented opt-in or default trajectory, or to evaluate adaptive
   relaxation or Chebyshev acceleration. If anisotropy limits SOR, evaluate
   conjugate gradients with multigrid or vertical-line preconditioning; the
   actual operator's symmetry/definiteness must first be verified, including
   stretched layers, the ground mirror and solid cells. S6 establishes no SPD
   claim. Because
   the operator is a first-class object built once per geometry and independent
   of wind direction, preconditioner setup can live beside it and be reused
   across directions. Any new method is another kernel behind the same phase
   contract, with `advance` counting method-neutral work.
4. Record the decision with measured cost-versus-error curves. A method change
   is its own reviewed task, with its own parity and validation evidence, and it
   must finish before S7 begins.

### 8. Keep the phase contract backend-neutral

A CUDA backend is planned for an upcoming release. QES's GPU solvers (not
vendored; still in the reference submodule) allocate, copy and free every array
on each monolithic `solve()`, which fits neither continuation nor monitoring.
They are useful as a reference for kernels, not as an interface. Design the
CPU package so that a device backend can implement the same contract later
without changes to the controller, monitors or Python API:

- The backend owns the operator and solver state; the runner and controller
  never index multipliers or coefficients directly. Studies that need them use
  explicit copy accessors.
- `PoissonOperator` is uploaded once per geometry and reused for every
  condition; the compact representation (decision 2) is what makes large grids
  fit in device memory.
- The initial field is produced on the host (profile and parameterizations)
  and transferred with current cell flags once per condition; `begin` builds
  the RHS on the device.
- `advance(n)` runs whole blocks without host round trips and returns only
  scalars (work done, last change, nonfinite flag).
- `observe` transfers only slab buffers; `finalize` transfers the full output
  once, including staggered faces needed by host turbulence. `diagnose` computes
  regional/global six-face reductions on the backend and returns scalar summaries.
  Checkpoints are the only synchronization points, so deadlines are checked per
  block on a device.
- Float32 is the default on both backends; float64 on a device is optional.

Do not implement the device backend in this refactor. Remove the obsolete
`HAS_CUDA` hooks with `SolverFactory` in S1, and record in the CUDA task that it
starts from this contract after S2.

### 9. Make model state explicit across conditions

The model is prepared once and initialized per condition. S1 preserved the old
reuse behavior for extraction parity; S1a corrects the condition-state defects
before any new reuse API. Python still builds a new runner per call. See the
[S1a audit and corrected baseline](docs/solver-control-s1a.md).

- **Corrected in S1a:** `PolyBuilding::rooftop_flag` is written only for
  some wind directions (the block at `PolygonWake.cpp:182`) and otherwise keeps
  the previous condition's value (read at `Rooftop.cpp:91`). Reset per-condition building
  state in initialization, with a reproducing test. The harness records exactly
  seven changed rooftop-vortex reuse cases; all other cases remain bitwise equal.
- S1 deliberately pins the existing reuse behavior for pure-extraction parity.
  After its review, S1a makes the condition-state and input-dependency corrections
  as deliberate changes, with fresh/reused/failed-then-retried equivalence tests and
  narrowly documented expected differences. Retain S0 as the original oracle and
  record the S1a source snapshot as the corrected baseline for S2 performance changes.
- **Validated in S1a:** `wake_flag=0` leaves
  `width_eff` and `Lr` unset, so sidewall produces NaN and an undefined cast
  (`Sidewall.cpp:185`) while rooftop and street canyon silently do nothing.
  Reject enabled rooftop, street-canyon or sidewall models with wake disabled.
  Wake-free upwind cavity remains supported when those dependents are off.
- **Measure, then decide on multi-direction runs (S8):** comfort solves 16–36
  directions of one geometry, each through a fresh `wind.run` that repeats
  Python geometry processing, model construction and, with turbulence, mixing
  lengths. S0 measures what share of a direction's time that is. Reusing the
  prepared model and operator across directions needs the fixes above;
  multi-right-hand-side sweeps are an option once the operator is compact,
  because its traffic is then small compared with the multiplier fields.

S5b confirms that StreetCanyon's solid-to-fluid relabeling causes an inherited
operator/mask/reconstruction inconsistency at all three persistent oblique core
mass maxima. The float64 and canyon-off pilot controls support this diagnosis;
the courtyard pilot without relabeling is a negative control. S5c has repaired
this in a separately frozen numerical change with declared expected differences.
The large urban scope still cannot receive adaptive acceptance without its own
independent observable/residual/mass qualification. The
exposed `street_intersection_flag` still has no model and remains a separate
tracked question. Top-band prescribed-face behavior is a separate documented
boundary limitation; S5b preserves its reporting and boundary convention.

### 10. Match acceptance to the requested output

The product needs more than one operating contract:

| Use case | Contract to implement or retain |
| --- | --- |
| Interactive preview | Existing bounded execution with explicit resource stop, work count and `not_assessed` quality unless a named policy actually qualifies it. |
| Pedestrian screening | Opt-in, calibrated vector and K error predictors at declared ROI/heights/receptors, plus fresh residual/mass safeguards. |
| Full 3D or turbulence output | A separate volume/derived-output assessment scope. A stable pedestrian slice cannot qualify velocities elsewhere, gradients, stresses or gust estimates. |
| Comfort/climate aggregation | Use qualified directional numerical-error estimates to assess sensitivity of classifications to those estimates; retain model/climate/gust limitations. |
| Numerical verification | Fixed-work studies, precision controls, coherent normalized residuals, actual flux checks and independently qualified references. |

Keep the legacy absolute multiplier criterion as a compatibility diagnostic.
Relative or Uref/length-scaled multiplier updates are useful comparative
diagnostics but remain dependent on method, grid and multiplier scale. They
are not the primary user-facing accuracy target. Public defaults, the meaning
of `SolveDiagnostics.converged`, and old reference gates do not change here.

The proposed production policy is a conjunction of observable remaining-error
predictors, individual critical-point/hotspot limits, valid support and fresh
mass/numerical checks. Use both vector and speed-factor quantities so a correct
speed with an incorrect direction cannot pass. Global signed balance alone
cannot detect canceling local sources/sinks. Residual tolerances and low-flow
normalization must be independently calibrated, including a separate calm-wind
contract; a budget stop or numerical stagnation is never accuracy acceptance.

For comfort, evaluate lower/upper directional K scenarios through the existing
climate/classification calculation. Equal classes under credible bounds support
robustness to those numerical errors only. A borderline class needs more work
or an uncertainty label. Use actual contributions to threshold exceedance;
low-frequency directions can still control safety tails. This requires S7
directional bounds and is a conditional S8 integration, not a shortcut to
physical validation or a statistical confidence interval.

## Proposed interfaces and compatibility

Native, all names finalized in S1:

- `src/qes_core/solver/`: `PoissonOperator`, `SolverState<Real>`, the CPU
  kernels (serial and OpenMP, both precisions), `FixedSweeps` as an explicit
  option, and the stop-rule and work-report types.
- `src/qes_core/dtcc/solver_control.{h,cpp}`: the controller (blocks, deadlines,
  modes, termination record). `src/qes_core/dtcc/monitor.{h,cpp}`: compiled
  monitor specification, slab buffers, receptor weights, regional mass
  diagnostics.
- `src/qes_core/dtcc/api/`: plain `SolverControl` settings and `ControlRecord`
  results, extending `wind_config.h` or a sibling header. No QES types.

Python: S4 implements optional `solver_control` in `wind.run`, with `None`
preserving legacy behavior and value types in `src/dtcc_qes/solver_control.py`.
Retain validation in Python and at the native entry point; copy monitor inputs
before releasing the GIL when extending these types.

The implemented first opt-in mode is `bounded`: legacy tolerance stopping plus a required
positive finite native time budget, checkpoint interval, explicit monitor
specification and history bound. `max_iterations`, `tolerance` and
`solver_precision` remain the existing arguments and the single source for those
settings. Avoid competing limits in two objects. Initial history should record
the uncorrected baseline as iteration zero, explicitly identified; it cannot
qualify a solve or count as evidence of converged checkpoint stability.

Later `adaptive` mode continues after the legacy tolerance if its own criteria
remain unmet, until acceptance, a resource limit, or detected stagnation. Record
the legacy boolean independently. A named, validated policy is mandatory for
acceptance; arbitrary user thresholds do not become a certified preset.

Use one existing call with native-internal blocks, not public `step()` calls.
Preserve the native mutex/GIL lock ordering, buffered logging, input snapshots,
owned output arrays and no-I/O behavior. Do not call Python progress handlers
from OpenMP workers or while holding the native mutex. Return compact history
with the completed result; streaming progress is outside the initial scope.

Keep fixed-sweep execution an internal testing/reference capability, with
normal reset semantics and explicit budgets. It must bypass early stopping
without bypassing nonfinite checks or a study's external timeout. The relaxation
factor and lexicographic ordering remain internal kernel options; S6 introduces
no public omega parameter. Distinguish one continued N/2N/4N trajectory from
the historical **independent zero-start** triples; continuation data do not
retroactively certify those protocols.

Legacy calls retain current warning/`raise_on_nonconvergence` behavior. The first
bounded mode also retains it, adding the termination reason to the message.
When adaptive mode becomes public, add a separate `raise_on_unaccepted` control:
an accepted adaptive result with `converged=False` must not emit the misleading
legacy warning, and `converged=True` must not suppress an unaccepted-result
warning. Reject `raise_on_nonconvergence=True` combined with adaptive mode, with
guidance to use the acceptance-specific option. Document the distinction and
test it before exposing adaptive mode.

Add diagnostics with defaults so existing result construction remains compatible.
Include controls, monitor coordinates/support, policy version, effective grid,
precision and numerical options in provenance and any relevant dataset cache
identity. Time-limited outputs can differ with machine load; record actual
iterations and avoid presenting cached partial results as deterministic outputs
of a portable accuracy policy. Revisit the completed B2 integration explicitly.

## Candidate accuracy contract for calibration

The following are **proposed solver-error budgets**, not validated presets,
published comfort standards or replacements for the archived reference gates.
Freeze the selected contract before collecting its calibration/validation runs.
Use K = |U_ped| / Uref, with a positive, declared Uref. Keep solver, spatial-grid,
empirical-model and climate uncertainty separate.

| Quantity, compared with an accepted same-grid reference | Preview candidate | Routine-analysis candidate |
| --- | ---: | ---: |
| p95 absolute speed-factor error over each required pedestrian region/height | <= 0.03 | <= 0.01 |
| Each fixed critical receptor and hotspot, when reference K >= 0.1 | <= 10% relative speed error | <= 2% relative speed error |
| Each such location when reference K < 0.1 | <= 0.01 absolute K error | <= 0.005 absolute K error |
| Required support | Valid, with no validity transitions | Valid, with no validity transitions |

All table entries remain hypotheses, not selected defaults. Freeze an explicit
vector-error budget on `|U - U_reference| / Uref` alongside the speed budgets
before calibration; matching speed alone misses direction error. Record maximum errors and failure locations even
where p95 is the aggregate acceptance statistic. Percentiles must declare their
point set, weighting and calculation method; use the fixed common physical
lattice for existing comparisons and do not silently change it to favor a grid.

Set each budget as a fraction of the measured grid sensitivity for the same
metric, not as a free-standing number. On the tower fixture, refining from 92 to
184 layers changed region p95 K by only about 0.0009 and 0.0018 at 1.5 and
1.75 m, but moved the mandatory points (15,47) and (15,29) by 13 to 18%
([refinement findings](docs/vertical-refinement.md)). The routine candidates
above are therefore looser than grid sensitivity for p95 and much tighter for
those points. Solver effort spent far below a metric's grid and model
uncertainty buys little.

Acceptance requires independently calibrated mass-consistency safeguards as
well as pedestrian error control. Reference error is available offline, not at
runtime. The runtime policy therefore needs calibrated predictors from current
diagnostics: checkpoint changes over multiple intervals, residual measures and
stagnation behavior. Do not equate the table's reference-error limits to raw
successive-checkpoint differences.

Start from a geometric remaining-error estimate. For a norm of the checkpoint
change in a tracked quantity, such as the p95 or maximum change in K, take the
two latest changes d_(n-1) and d_n, estimate the decay ratio q = d_n / d_(n-1),
and estimate the remaining error as d_n·q/(1 − q). This is a heuristic under
stable geometric decay, not a proven bound for changing modes or percentile
supports. Calibration then sets a safety factor and the conditions under which
the estimate is trusted: q stable
over several intervals and clearly below 1, never rising or near 1. On the tower
evidence, raw 100-sweep differences understate the remaining error about four to
five times.

Begin policy experiments with at least three post-initialization checkpoints
and two consecutive stability intervals, an explicit minimum interval in
sweeps, and a minimum work requirement selected during calibration. Compare
short and longer windows to catch slow drift. Stable support, fixed receptors,
moving hotspots and fresh mass checks must all pass. Initial candidate
checkpoint spacings of 100 and 250 sweeps remain possible policy experiments;
S5a first screens 25/50/100 for observation cost. Freeze the actual sweep spans
of short/long windows and calibrate for the selected cadence; a threshold on a
25-sweep difference cannot be reused unchanged for a 250-sweep difference.
The 500/1000/2000 observations do not establish a universal schedule. Stagnation
without acceptance stops as `stagnation`, never `target_reached`.

K was independent of Uref to about 2e-6 in an earlier three-building check
(Uref = 2, 5 and 12 m/s); the new courtyard study confirms near-invariance at
equal work but exposes the speed dependence of absolute-tolerance stopping.
Calibrate positive-inflow policies in normalized vectors/K. Check scaling on
at least one urban case per claimed model/profile scope; branch changes,
precision and future stability-dependent models can invalidate extrapolation.

Explicitly handle Uref = 0: normalized K metrics are undefined. Initially reject
adaptive acceptance for zero reference speed and support legacy/bounded
diagnostics with absolute velocities only. Any special calm-wind acceptance
path needs its own tests and contract.

The original reference criteria remain unchanged: three independent N/2N/4N
zero starts; scaled interior maximum divergence <= 1e-3 and RMS <= 1e-4 at all
three checkpoints; maximum vector change/Uref <= 1e-3 and p95 <= 5e-4 over both
successive pairs, with stable support. In the tower study the divergence scale
is L/Uref = 23.7/5. Retain its separate spatial-comparison thresholds and all
recorded failures. A new production contract cannot make an old failed
reference pass.

## Implementation stages and acceptance checks

Every stage is a series of small commits. Unless a stage states a deliberate
output change, each commit passes `tools/compare_native_builds.py` bitwise
against the previous commit in OpenMP and serial builds, plus CTest (OpenMP,
serial, sanitizers), the symbol audit, pytest in both backends and the
sdist/wheel artifact check.
These are implementation/behavior gates. Documentation-only reviews check
consistency, links and evidence identities without rerunning compute matrices.

### S0 — Baseline, profile and prerequisites (complete)

1. Re-read the source against this plan; record the S0 baseline revision that
   every later harness run starts from.
2. Archive the local benchmark evidence above in a new study directory with
   hashes, hardware/build/team information, measurement exclusions and an
   archived source snapshot. Preserve existing immutable archives.
3. Make the contraction mode explicit and record it in build provenance
   (`_qes` attributes and the control record), pinned to each compiler's
   current behavior so no output changes. A portable `-ffp-contract=off` is a
   separate, reviewed baseline change if cross-compiler bitwise reproducibility
   becomes a requirement.
4. Profile the representative case in both precisions: Python geometry
   processing, model construction, operator-equivalent setup, turbulence
   setup, initialization, RHS, time per sweep and estimated effective bandwidth,
   each pass, finalization, output transfer, vector sizes/capacities by array
   and phase high-water RSS. Distinguish these from hardware DRAM counters or
   per-array resident-memory measurements. This decides the
   priority of decision 2's items and of S8.
5. Extend the harness where later stages need it: a same-tree backend pair
   (serial against OpenMP), team-size variants, larger iteration budgets on
   one case, and a stretched-grid float64 case.
6. Define the runner state machine, the proposed control fields, exception
   behavior and benchmark caps. Record unqualified automatic grids as
   experimental inputs.

**Exit:** a recorded baseline revision, archived evidence, a profile that says
where time and memory go, and no solver change. Do not generate new hours-long
references simply to start this refactor.

Completed against `bbfd20005e0bd7d7e648438a1bc8d5a9a4358a71`; see the
[S0 report](docs/solver-control-s0.md). All 16 bounded profiling workers
completed; the expanded 429-case revision comparison passed in both backends
and all requested OpenMP teams. No solver arithmetic, storage or ordering
changes were made. Its required review preceded the S1 extraction below.

### S1 — Phase-based solver package (complete)

1. Create `src/qes_core/solver/` with `PoissonOperator` (explicit arrays at
   first), `SolverState` and CPU kernels with `begin`, `advance`, `observe` and
   `finalize`, reproducing the float32 arithmetic of `Solver_CPU` and
   `Solver_CPU_RB` and the float64 arithmetic of `PrecisionSolver`, with each
   build's current ordering. Move the runner's cell-centre averaging into
   `finalize`.
2. Route `WindRunner` through the package for both precisions; validate the
   operator once per preparation and the initial field once per condition.
3. Port `check_openmp`, `check_physics`, `check_vertical_grid`, `check_safety`,
   `check_precision`, `tools/vertical_grid_study.cpp` and
   `tools/near_wall_probe.cpp` to the package (explicit fixed sweeps, state
   accessors). Keep `vertical_grid_study`'s target name and source path.
4. Delete `Solver`, `Solver_CPU`, `Solver_CPU_RB`, `SolverFactory` (with its
   `HAS_CUDA` hooks) and `PrecisionSolver`; update `tools/check_artifacts.py`,
   the provenance lists in the study tools and `PROVENANCE.md`.
5. Add native tests: contiguous N sweeps equal partitions such as
   1 + 7 + (N − 8), with observations between partitions; early stopping inside
   a block, at a block boundary and on the last permitted sweep; repeated
   zero-start solves; condition and precision changes; failure recovery.

**Exit:** harness bitwise against the S0 baseline in both backends and
precisions, including iteration diagnostics. Stop for a plan review, since
phase extraction may expose new state or boundary constraints.

Completed on 2026-10-29; see the [S1 report](docs/solver-control-s1.md) and
[archived evidence](docs/data/solver-control-s1/manifest.json). All 429 cases,
including numerical diagnostics, match S0 bitwise in serial and OpenMP teams
1, 2, 4 and 8. Native continuation, observation purity, termination and failure
recovery checks pass. The review retains the S1a prerequisite, borrowed-input
lifetimes and legacy diagnostic exclusions. That review preceded S1a below.

### S1a — Reviewed condition-state corrections (complete)

After S1's review, implement decision 9's rooftop-state reset and explicit wake
dependency validation as deliberate behavior changes. Audit other per-condition
members. Test fresh versus reused conditions, precision changes and recovery
after an injected numerical failure. Record the exact affected cases and the
corrected baseline revision; S2 uses that baseline while preserving the S0
record. See the [S0 contract](docs/solver-control-contract.md).

Completed 2026-10-29; see the [S1a report](docs/solver-control-s1a.md). Fresh,
reused, precision-switched and failed-then-retried conditions agree bitwise.
Against S1, exactly 21 records in seven rooftop-vortex reuse cases change in
each backend/team; the other 422 cases remain identical. Invalid wake/model
combinations are rejected separately from that historical matrix. The corrected
baseline is the SHA-256-identified
[source archive](docs/data/solver-control-s1a/manifest.json), usable through
`compare_native_builds.py --baseline-archive`; it does not claim a new git
revision for this uncommitted workspace. S0/S1 evidence stays unchanged.
That review preceded S2 below.

### S2 — Per-sweep traffic and memory (complete)

**Review 2026-10-29:** still relevant and ready to implement in the sequence
below. S1/S1a satisfy the phase and condition-state prerequisites. The review
corrects the baseline, adds the study-state and coefficient-lifetime migrations,
separates the serial-ordering gate and defers output-copy removal. No S2 code or
new performance results are included in this review.

Before optimization, establish a bounded timing/memory baseline from the
corrected [S1a source archive](docs/data/solver-control-s1a/manifest.json)
(`6fcdfab1abe30e254721495d2fe453f9e4c7eb89be89421df29eb44663e08d76`).
The old `profile_solver_baseline.py` instruments the archived pre-extraction
classes and cannot profile S1a by changing its source-archive argument. Add a
separate phase-aware profiler or explicit new-layout support that leaves the
S0 replay/audit intact. S1 changed orchestration, validation and finalization;
output parity with S0 does not establish timing parity.

1. **Fuse the float32 change norm.** Remove `lambda_old` and its passes, port
   diagnostic study runs to a snapshot immediately before their final sweep,
   and update workspace-byte reporting/state tests. Preserve one-sweep behavior,
   fixed and tolerance stopping, partition invariance, pure observations,
   repeated finalization, both orders and nonfinite failure recovery. Check a
   small diagnostic study, including its per-cell `lambda_update`, against S1a;
   the 429-case Python matrix does not cover this internal output.
2. **Own and compact the operator.** Migrate all consumers before releasing
   coefficient storage, including standalone mass diagnostics and study probes.
   Test compact against forced-explicit storage for both precisions and orders,
   multiple relaxation values, uniform/stretched grids, boundaries and supported
   face-mask patterns. Include a finite nonrepresentable-coefficient fixture
   that selects fallback, signed-zero preservation, invalid size/nonfinite input
   rejection and the existing zero-diagonal failure behavior. Check coefficient
   bits, RHS, iterates, change/termination, observed and finalized fields, and
   mass diagnostics. Verify fallback owns its arrays and production retains no
   duplicate full coefficient set after preparation; report representation and
   retained/setup-peak bytes.
3. **Remove unused allocations.** Make cut-cell storage conditional and allocate
   mixing lengths at turbulence setup; guard the active wall reader first.
   Verify wind-only and both supported turbulence methods with buildings,
   repeated preparation/conditions and sanitizers. Caller-owned finalization
   is already complete. Preserve NumPy ownership, dtype, shape, contiguity and
   independence from later solves/runner destruction; output-copy removal is a
   separate follow-up, outside the S2 exit gate.
4. **Unify the default sweep order.** Change serial defaults to red/black, keep
   explicit lexicographic controls, and migrate study refinement ordering and
   backend-specific test expectations. Record this numerical behavior change
   separately from the preceding storage/traffic changes.

Measure before and after each item, using both precisions, OpenMP teams 1, 2,
4 and 8, and serial controls. Declare matched fixed sweep counts, geometry,
compiler/contraction settings, warmup and repetitions before each matrix;
confirm completed work and actual teams. Keep the S0-sized bounded experiment
(30 s per worker, 180 s per matrix), choosing counts that fit; archive timeout
or incomplete outcomes instead of silently extending the budget. Report plain
API time, phase/sweep time, preparation, retained bytes and process peak RSS.
If instrumentation is used, require output parity with the plain build and
keep its timing overhead visible. Report modeled logical bytes per sweep and
effective GB/s with the byte model; call it measured DRAM bandwidth only if
hardware counters establish it. Archive the complete relevant native, binding,
study/test and build sources alongside new records; preserve all S0/S1/S1a
archives. No long reference trajectory is needed for S2.

**Numerical gates:**

| Stage | Required comparison |
| --- | --- |
| Items 1 to 3 | All 429 cases and numerical diagnostics bitwise against corrected S1a, in serial and OpenMP teams 1/2/4/8. Retain the separate S1a condition-state, valid wake-free/dependency-rejection and failure-recovery tests. |
| Item 4, unchanged OpenMP | Still bitwise against corrected S1a OpenMP for every team and precision. |
| Item 4, new serial default | Bitwise against candidate OpenMP and S1a OpenMP, apart from the existing backend metadata exclusions. Record and check the exact expected differences against S1a serial. |
| Every item | Relevant native phase/operator/study tests and Python regressions; sanitizers for changed storage/lifetimes; final artifact and symbol audits. |

The current harness's `--require-backend-parity` also requires revision parity
for serial, so it must fail on the intended item-4 change. Before that item,
extend the harness with an explicit ordering-migration comparison policy that
enforces all three item-4 comparisons above, tests unexpected differences still
fail, and keeps strict revision comparison as the default. Do not treat a
failed combined report as a pass or suppress all serial differences. Explicit
lexicographic requests retain their S1a trajectory in native checks.

**Exit:** all applicable numerical/ownership gates pass, each implementation
step has separate source identity and bounded timing/memory evidence, and the
measured gains or regressions are documented. Performance estimates are not
acceptance thresholds. Review the resulting S2 baseline before starting S3.

Completed 2026-10-29; see the [S2 report](docs/solver-control-s2.md) and
[evidence manifest](docs/data/solver-control-s2/manifest.json). Items 1 to 3
match corrected S1a bitwise in all 429 cases, both backends and OpenMP teams
1/2/4/8. Final OpenMP still matches S1a; new serial matches OpenMP with exactly
the 888 expected differences from old serial. Explicit lexicographic studies
retain their S1a trajectory. Native, Python, sanitizer, wheel, symbol and source
artifact checks pass. Five bounded profiling matrices completed with paired
numerical parity. At four threads, the local float32 sweep is 2.12× faster and
peak RSS is 29.8% lower than S1a; short matched-work measurements do not establish
an accuracy or timing guarantee. NumPy ownership/copying remains unchanged.
The stage's reviewed next step was S3 monitoring against the frozen S2 source
identity; S3 and S4 have since completed without rewriting this evidence.

### S3 — Pedestrian and mass monitoring (complete)

1. Implement the compiled monitor specification and slab observation through
   `observe`, with pure observations of the current iterate.
2. Add checkpoint summaries, required-receptor validity, peak tracking,
   two-window comparisons, successive-change ratios, regional mass diagnostics
   and the in-sweep residual trend. Bound history and memory.
3. Compare checkpoint planes and receptors with full finalization followed by
   `WindResult.sample` and the study collocation at the same iteration. Cover
   exact centers, fractional heights, solid neighbors, prescribed boundaries, no
   valid support, zero flow and nonfinite failures on uniform and stretched
   grids.
4. Verify that enabling observations leaves subsequent sweeps and final output
   bitwise unchanged; test multiple team sizes and race-sensitive solid faces.

**Exit:** monitoring parity, unchanged solver trajectory, measured overhead and
bounded memory. There is still no automatic accuracy acceptance.

Completed 2026-10-30; see the [S3 report and S4 handoff](docs/solver-control-s3.md)
and [evidence manifest](docs/data/solver-control-s3/manifest.json). Exact masks
and four-float32-ULP sampling parity pass in both precisions and coordinate
frames on uniform/stretched grids. Enabled monitoring preserves solver bytes
across both orders, operator formats and OpenMP teams. The full 429-case S2
comparison passes without differences. Bounded native, Python, sanitizer,
packaging and symbol checks pass. The sequential 60-worker cost matrix retains
8.32 MiB of fixed monitor buffers; slab checkpoints add about 3.4% to the local
four-thread float32 native total. Continuous residual collection adds about
93%, so cadence must remain explicit and optional. Public API overhead and
disabled-path variation were still open at this freeze; the urban evidence now
addresses four-thread execution, with the remaining S5 follow-up defined below.
At the S3 freeze, automatic accuracy acceptance and the S4 controller were not
implemented. S4 subsequently added bounded controls; acceptance remains open.

### S4 — Bounded controller and Python API (complete)

1. Add the controller, cooperative deadlines, iteration accounting and the
   structured termination and history record. Thread the optional
   `solver_control` configuration through `dtcc/api`, native validation, the
   bindings and `wind.run`.
2. Keep the default float32/500/1e-5 and OpenMP selection unchanged. Expose
   bounded mode only, with `accuracy_status=not_assessed`.
3. Test deadlines before work, after initialization, between sweeps, during
   checkpoint evaluation and before acceptance would be possible. Use a fake
   monotonic clock for deterministic boundary tests and a small real subprocess
   timeout test for integration. Cover zero completed sweeps and output overhead.
4. Test the no-GIL deadlock guard, native exceptions, input snapshots, owned
   arrays, repeated solves, legacy warning behavior, metadata and dataset
   serialization.

**Exit / first usable milestone:** bounded native continuation with diagnostics,
no full-volume checkpoint copies and no accuracy claims. A caller can tell
whether the solve met the legacy tolerance or exhausted its budget.

Completed 2026-10-30; see the [S4 report](docs/solver-control-s4.md) and
[evidence manifest](docs/data/solver-control-s4/manifest.json). The default
429-case trajectory gate remains strict. Fake-clock tests cover each deadline
boundary and zero-work errors; Python/dataset histories and metadata serialize.
The first usable bounded API is available. Twelve eight-sweep urban smoke
workers completed, with identical baseline/candidate fields at equal work.
The 2 m core suite is frozen at 3.6–6.3 million cells per case; its 108 rows are
split into eighteen six-worker shards. The five completed 500/2,000-iteration
campaigns and their qualifications are recorded in the current-evidence section;
S5's remaining diagnostics, publication and cadence gates are below.

### S5 — Qualify numerical evidence and close the performance follow-up

**Completed 2026-10-30.** See the [completion ledger](docs/solver-control-s5.md)
and [portable audit](docs/data/solver-control-s5/audit.py). The original 324
workers/216 comparisons, six-run tolerance study and excluded attempt are
preserved. Sixteen corrected-numerics workers and 52 finite API follow-up workers
complete the remaining qualification/cost/resource studies. Source-matched
baselines are used for new architecture/control comparisons. Large-grid reference
qualification remains visibly absent, as allowed by the S5b exit contract;
there is no remaining diagnosed assessed-solid inconsistency on the tested scope.
The disabled-controls <=5% review target remains explicitly missed and reviewed;
no accuracy threshold or historical reference gate was loosened to close S5.

#### S5a — Publish measured costs, select cadence and exercise resource stops

**Complete.** All five campaigns and the tolerance study are portable under the
S5 evidence identity. Cadence 100 is recommended on the measured two-case scope;
public default 25 is unchanged. Actual teams 1/2/4/8 preserve fields. All ten
0.25–5 s runs stop on time limits, both tiny-budget checks fail with zero work,
and both selected same-work replays are exact. The original monitoring review
target is met on the three-repeat confirmation; its negative downtown overhead
is variance, not a speedup claim. The disabled-controls target is missed by
11–15%; a six-worker reversed-order check retains +12.3%. The published
disposition retains correctness/controls and carries cost into S6. Requirements
below remain the historical execution/exit contract.

1. Publish the five existing campaigns and the tolerance-scaling study under a
   new `docs/data/solver-control-s5/` evidence identity. Include source archives
   and build recipe/environment, fixture/driver hashes, original protocols,
   outcomes, comparisons, compact planes, logs, failed/excluded attempts and an
   independent audit. Do not edit S0–S4 evidence. Preserve S1a→S4 and S3→S4
   attribution, ratios of medians versus medians of paired ratios, three-repeat
   limitations, actual four-thread scope and the wider long-run RSS range.
2. Screen checkpoint intervals 25/50/100 on courtyard 225° and downtown 225°
   using one fixed-work repetition each: six workers. Confirm the selected
   cadence against controls disabled with three paired repetitions per case:
   twelve workers. Retain both heights, all required receptors, hotspot tracking
   and bounded history. Do not reduce coverage to meet an overhead target.
   Account for S5b's fresh residual/final-check cost when S7 is integrated.
3. On one representative case, check actual teams 1/2/4 with controls off/on
   (six workers), plus a separately bounded 8-thread off/on check if hardware
   and memory permit. Use affordable fixed work, not a 2,000-iteration serial
   S1a case that the measured cost predicts will exceed the worker deadline.
   Keep this a sensitivity study, not another full Cartesian product.
4. Exercise real native budgets 0.25/0.5/1/2/5 s on two urban cases with a
   sufficiently high iteration cap: ten initial workers. Verify actual resource
   stops, zero-work failure where applicable, completed whole sweeps, overshoot,
   finalization/output cost and honest quality status. Repeat only selected
   boundary cases when new failures or material variance justify it. Expensive
   observation cadence must not coarsen per-sweep CPU deadline checks.
5. Freeze each matrix before running it. Preserve 30 s process limits, six-worker
   shards and 180 s shard limits; explicitly select the finite campaign size.
   Build outside clocks, reuse only verified cache entries and isolate tests,
   builds and host-sleep-contaminated attempts from accepted timing. Archive
   source/ABI/toolchain/package-integrity cache decisions. Budget failures are
   outcomes, never permission for automatic retries with larger limits.

**Exit:** portable audited evidence; a documented cadence and measured runtime,
RSS/allocation and resource-stop envelope. Review targets remain <=5% median
API regression against S3 with controls disabled and <=10% monitoring overhead
on the declared representative scope. For any missed performance target,
publish the measured tradeoff and disposition; do not label it met or turn a
performance target into an accuracy exemption.

#### S5b — Coherent diagnostics, hotspot classification and reference qualification

**Completed 2026-10-30 for the declared finite study.** See the
[S5b report](docs/solver-control-s5b.md) and
[portable evidence](docs/data/solver-control-s5b/manifest.json). All sixteen
workers completed; both independent 500/1000/2000 reference triples pass on
their new 2 m calibration grids. The historical finer tower and large urban
cases remain outside that qualification. The diagnostic change preserves all
429-case S4 outputs bitwise in serial and OpenMP teams 1/2/4/8. The requirements
below are retained as the implementation/review contract.

1. Add pure completed-iterate equation-residual diagnostics to the native phase
   API, alongside the existing update-time trend. Specify A, b, sign, row
   scaling, norm, fluid eligibility and boundary convention. Report maximum
   and volume-weighted RMS, initial/RHS normalization, normalization floors and
   assessed counts. Declare any physical reference length before measuring;
   do not choose a domain-dependent scale after seeing difficult residuals.
   Verify against an independently assembled small-stencil
   oracle on uniform/stretched grids, ground mirrors, prescribed boundaries,
   solids, calm flow and nonfinite failures. Observation must not mutate the
   trajectory, allocate another persistent full velocity volume, or change
   legacy outputs. Measure checkpoint/global-check costs.
2. Reproduce and locate the downtown 225°/315° and courtyard 225° mass maxima
   at 500 and 2,000 iterations. Map coordinates, layer/height, flags before and
   after parameterization, neighboring faces/coefficients and diagnostic
   eligibility. Compare true equation residual, corrected-face divergence and
   regional signed/absolute flux on exactly the same iterate. Include a 270°
   control and separate top-band/domain-boundary behavior from assessed interior.
   S5b has now confirmed the solid relabeling inconsistency at all three
   oblique core maxima; preserve its raw controls and distinguish the
   unaffected coarser courtyard pilot.
3. Classify each persistent discrepancy as iterative error, precision floor,
   an operator/mask/reconstruction defect, or a documented model/boundary
   limitation. A small float64 control on the same inputs helps isolate the
   first two; it does not change the default precision or make output arrays
   float64. Do not assume the current 66–626× tolerance misses are roundoff.
   Keep any necessary numerical correction in a separately frozen change with
   exact expected differences, affected-case tests, repeatability and provenance.
   Do not silently exclude difficult cells, loosen old reference gates, smooth
   empirical branches or change boundaries as part of diagnostic code.
4. Inventory compatible references before generating new ones. Require matching
   geometry, grid/faces, initial fields, condition flags, model options,
   coordinate frame, source/numerics identity and sampling definition. The old
   tower reference applies only after that compatibility check; it is not a
   reference for the new neighbourhoods. Public tolerance stopping is not an
   exact-work study protocol: use the existing internal `FixedSweeps` option
   and record actual completed work.
5. Predeclare a finite per-case N/2N/4N independent-zero-start protocol that fits
   the measured 30 s worker envelope. Start on affordable compatible tower and
   urban canyon/passage inputs; include the hotspot cases in diagnostics even
   if they remain unqualified. Preserve the original reference gates and any
   failures. Continuation histories can inform cost/decay, but cannot replace
   the independent reference protocol. If large-grid references are unaffordable,
   use a separately declared smaller calibration scope and retain the large
   case as unqualified. Never call 2,000 iterations the truth or repeatedly
   double work until a reference passes.
6. Archive field/receptor error, residual and mass versus work/time, using only
   qualified same-grid references for error labels. Collect bounded histories
   long enough for the predeclared replay study: the existing 16-summary ring
   omits early checkpoints and cannot recover an entire acceptance trajectory.
   Keep production history bounded and label truncated studies insufficient.
   Separate solver error from grid/domain sensitivity, empirical model error,
   climate uncertainty and physical validation.

**Exit:** tested coherent diagnostics, an evidence-backed hotspot disposition,
and an explicit reference-qualification inventory and cost/error dataset. Missing
qualification remains visible. An unresolved assessed-interior inconsistency
blocks acceptance for the affected scope; it does not block publishing S5a or
justify silently weakening the numerical target.

#### S5c — Repair solid-mask consistency as a separate numerical change

**Completed 2026-10-30.** Prepared solid/ground flags survive both canyon
routines; all 384 supported model/direction combinations preserve solids/faces
in the new small regression. The sixteen-worker corrected study has zero
relabeled assessed solids, with two requalified small references. All 429
historical cases remain exact; four of twelve targeted corner cases change with
recorded guard hits and explicit per-record differences; eight controls stay
exact. All fourteen candidate team/backend checks pass. See the
[S5 report](docs/solver-control-s5.md). The requirements below describe the
separately frozen correction; S6's subsequent method decision is recorded below.

1. Freeze S5b's unmodified numerical behavior as the comparison baseline.
   Audit StreetCanyon and the other parameterization flag writes against the
   authoritative prepared stair-step geometry. Prevent initially solid/ground
   cells from becoming condition-fluid, and ensure parameterized faces, fluid
   eligibility and the immutable wall operator agree. Preserve legitimate
   relabeling among fluid model classes. Do not repair this by excluding cells
   in diagnostics or by disabling the canyon model for callers.
2. Add a small targeted regression reproducing solid-to-fluid relabeling and
   the inconsistent coefficient/masked-face pattern. Check flags before/after,
   face ownership, operator compatibility and repeated prepared solves in
   both precisions/backends. Audit flag-changing model combinations so the
   correction is not just a hard-coded patch for one hotspot coordinate.
3. Predeclare and rerun the finite affected core/pilot/control matrix at
   500/2000 fixed sweeps with existing 30 s worker/180 s shard caps. Retain
   both heights, required receptors, regional/global flux, true residual and
   top-band reporting. The corrected cases may retain ordinary iterative
   error; do not require fabricated tolerance convergence or qualify them
   from a small equation residual alone. Keep the prescribed-top-face
   limitation separate; a boundary change would need its own frozen decision.
4. Freeze the numerical correction, expected changed cases and exact outputs
   separately from S5b. Report every difference against the S5b baseline and
   justify it by geometry/condition consistency; preserve strict unchanged-case
   gates, repeatability and team/backend parity. Recheck reference compatibility
   and numerical/method identity before S6/S7. No blanket tolerance relaxation
   or silent reference replacement is allowed.

**Exit:** solid-mask consistency is tested and the diagnosed defect is removed
on the affected matrix, with numerical differences explicitly reviewed and
archived. Large-grid acceptance still requires qualification under its own
residual/mass/observable gates. S5a's performance/resource studies are now
complete with the explicit missed-target disposition. S6's method selection
is recorded below; S7's subsequently qualified pedestrian scope is recorded
separately, and broader numerical qualification remains open.

### S6 — Freeze the iteration-method decision before policy calibration (complete)

1. Reuse the existing internal relaxation option; screen omega
   {1.78,1.85,1.90,1.95} on an affordable compatible tower and urban canyon case
   under fixed work and explicit budgets. Use the S5b diagnostics/references,
   both pedestrian heights and critical/hotspot locations. Check transient
   growth, slowly decaying modes, precision plateaus and mass behavior.
2. Confirm the promising option against 1.78 with paired repetitions and at
   least one held-out morphology/direction. Select by total cost to the frozen
   observable-plus-mass target. Equal sweeps, a lower multiplier update or one
   residual scalar are not enough to establish an improvement.
3. Record one finite outcome: retain 1.78; select a documented opt-in factor;
   or open a separately scoped acceleration task. Verify symmetry/definiteness
   of the actual stretched-grid, ground and solid-boundary operator before
   choosing conjugate gradients. Chebyshev, vertical-line preconditioning and
   multigrid are candidates, not mandatory implementations in this refactor.
   State their setup/reuse costs if evaluated.
4. Preserve the legacy default trajectory unless a deliberate numerical change
   is separately recorded. Freeze the selected method/kernel version for the
   policy; intentional trajectory changes require new reference compatibility
   checks and validation. Changing the method after S7 invalidates calibration.

**Exit:** a recorded, reproducible method decision. Keeping the current method
is a valid outcome. If adequate cost/quality requires a different solver, define
that separate task and the restricted bounded-only disposition explicitly;
opening it does not make the adaptive-policy stage complete.

**Recorded result:** [S6 report](docs/solver-control-s6.md),
[frozen method identity](docs/data/solver-control-s6/method-decision.json) and
[portable evidence](docs/data/solver-control-s6/manifest.json). The predeclared
four-factor screen selected `1.90f`; three paired repetitions on the tower,
20-building passages and held-out 225° passages met the per-case cost rule.
Median paired cost ratios versus `1.78f` were 0.505, 0.599 and 0.554. One
held-out pair regressed (1.246); it remains in the result. Costs include native
preparation, sweeps, all preceding numerical/observable checks and compact
sample writes, and exclude full-volume API finalization/turbulence.

All three same-grid references qualify. Six float64 controls pass; the two
original default reference histories are byte-identical. Eight separately
predeclared first-sweep checks expose approximately 2.8–2.9x initial growth for
`1.90f`; late float32 residual plateaus near 1e-5 preclude treating small drift
as zero error. The short-budget probes establish no public numerical acceptance;
only one of eight meets even this offline three-checkpoint target.

Freeze `s5c-rb-sor-float-omega-v1-omega-1.90` for the scoped S7 candidate and
retain `1.78f` for every existing public/default/bounded call. The S5 production
sources are unchanged; only the standalone probe differs in the measured
snapshot. Neither stretched-grid applicability, large-city numerical accuracy,
an online policy nor API-wide speedup is established. All S6 cases/directions
are method-development data and cannot be reused as unseen S7 validation.

### S7 — Implement and validate a policy tied to requested outputs (complete for pedestrian-v1)

1. Freeze versioned contracts and supported scope before calibration. Distinguish
   latency-bounded preview (`not_assessed` unless a policy qualifies it),
   pedestrian screening, and numerical/full-volume verification. Keep the
   candidate K table provisional until vector, critical-point and independent
   mass/residual limits and their normalizations are selected. A pedestrian
   policy does not qualify turbulence, full-volume derivatives or gust/GEM.
   Bind the candidate policy to S6's recorded `1.90f` method identity; do not
   change existing `1.78f` public calls. Requalification is required when the
   method, condition mask, boundaries or compiler arithmetic change.
   Reject adaptive acceptance for Uref=0 initially; retain calm legacy/bounded
   output. Include a scoped inflow-scaling check.
2. Separate calibration from held-out geometries/directions. Cover both heights,
   fixed required receptors and moving/current/previous hotspots; uniform and
   supported stretched grids; passages/shelter; oblique winds; domain controls;
   branch-sensitive cases; slow drift, float32 stagnation and invalid support.
   Unsupported or reference-unqualified configurations remain bounded/unaccepted.
   Freeze a finite matrix and budgets instead of expanding until it passes.
   All S6 conditions, including its 225° confirmation, are method-development
   data; reserve new unseen conditions for S7's online validation.
3. Replay sufficient checkpoint histories. Require multiple post-initialization
   checkpoints, short/long windows, a calibrated minimum work interval and
   stable support. Start with the geometric-tail estimate and a calibrated
   safety factor. Account for S6's measured 2.8–2.9x initialization growth and
   float32 residual plateaus. Treat unstable decay ratios, q near/above one, changing
   modes/support and plateaued diagnostics as unavailable evidence, never as
   zero error. Track maxima and every required point even when p95 is the ROI
   target. A generic small-change threshold alone is not acceptance.
4. Implement native controller decisions without Python callbacks in the mutex
   or OpenMP workers. Adaptive execution may continue after legacy tolerance;
   use explicit stop rules rather than corrupting the tolerance to force work.
   Accept only when observable predictors, every required point/support check,
   and fresh global/regional numerical/mass safeguards pass on one current
   iterate before the deadline. Retain per-sweep budget checks. Time/iteration
   limits, stagnation and numerical failure remain separate outcomes; no work
   yields the existing budget-exhausted error.
5. Validate online on the held-out matrix against qualified references. Report
   every false acceptance, missed acceptance, invalid receptor, timeout,
   stagnation, achieved error and total API cost, including final checks/output.
   Declare maximum allowed false acceptances as zero for release on that matrix;
   the result is empirical qualification, not a universal error bound. A failed
   case requires a scope restriction or a new policy version and new held-out
   validation, not post-hoc threshold changes on the same validation set.
6. Expose only a qualified opt-in policy. Preserve `diagnostics.converged` as the
   legacy multiplier test; record policy/version/method, assessment scope,
   numerical evidence, acceptance and failure reasons separately. Implement
   acceptance-specific warning/exception behavior and dataset health/cache
   provenance. An accepted adaptive result with legacy `converged=False` must
   not emit the old failure warning; a legacy-converged but unaccepted result
   must not be presented as accepted. Test serialization, deadline precedence,
   stale/initial evidence, cache identity, unsupported modes, GIL/mutex safety,
   owned outputs and bounded history/memory.

**Exit:** a documented opt-in policy with a frozen method and supported scope,
zero false acceptances on the declared held-out matrix, accurate API/dataset
status and a rollback to legacy/bounded mode. Defaults remain unchanged. If no
useful scope passes, keep adaptive disabled and record S7 as unqualified/open
pending an explicit restricted-closure decision; do not claim it completed.

**Recorded result:** [S7 report](docs/solver-control-s7.md) and
[portable evidence](docs/data/solver-control-s7/manifest.json). A failed fresh-tail
calibration draft is preserved. The separately frozen revised predictor uses
safety 8, minimum 150 sweeps, ratio cap 0.8 and a nonzero anchor transported by
measured maximum drift for at most 100 sweeps. All decisions and fresh
residual/mass guards run natively; deadline precedence, explicit stop rules,
method-aware workspace reuse, acceptance-specific warnings/errors and dataset
cache/source identities are implemented.

The finite study has 100 workers: 33 fixed/reference workers and 67 API workers.
Nine independent same-grid reference triples qualify. The 96×80 graded domain
control fails its original mass gate and is explicitly excluded without budget
escalation or relaxed thresholds. Six new held-out conditions cover staggered,
courtyard and mixed-height districts, oblique winds, a graded grid and Uref
2/10 scaling. There are zero false/missed acceptances on the qualified matrix
and zero measured predictor underestimates. Thirty-four full-budget acceptances
plus two budget acceptances pass their output targets; final serial and
provenance-only builds preserve the fields and decisions exactly.

Freeze `pedestrian-v1` and method `s5c-rb-sor-float-omega-v1-omega-1.90` only
for the recorded 80×80×32, 2 m uniform or specified graded, float32 rectangular
building/default-model envelope on the matching arithmetic/source build.
Unsupported configurations remain bounded/unaccepted with the 1.78 method.
Full-volume/turbulence/physical accuracy and large-core qualification remain
open. Default 429-case revision/team/backend comparisons are exact. Validation:
48 OpenMP native, 45 serial, five focused ASan/UBSan and 1,076 Python tests pass
(16 Python skips). This completes S7's useful qualified opt-in exit; it does
not promote a default, qualify broader configurations or close S8/S9.

### S8 — Measure and integrate repeated directions without expanding the physics scope

#### S8a — Prepared-model reuse (complete: measured public API deferral)

1. Measure repeated-condition preparation, geometry extraction, operator setup,
   sampling and output cost separately on one affordable neighbourhood. The
   original S0 preparation share does not establish current user-level savings.
   Predeclare four/eight-direction pilot sequences that fit the worker limit;
   do not put an over-budget core sequence inside one worker.
2. If reuse gives a worthwhile measured benefit, expose a reusable prepared
   Python model or multi-direction call around the existing native runner. Keep
   `wind.run` unchanged. Snapshot geometry/options, reuse the immutable operator,
   and start every condition from zero; no warm starts or new numerical kernel.
   Validate reprepare/precision/model changes, direction ordering, failure then
   success, both turbulence methods, geometry mutation, output ownership,
   concurrent-call locking and fresh-versus-reused parity. Count preparation
   once in series totals and keep requested multi-direction output memory guarded.
3. Publish repeated-series end-to-end time, allocation/RSS and field/diagnostic
   parity against independent fresh calls. If the benefit is negligible, record
   the decision and defer a public reuse API explicitly rather than introducing
   an unmeasured convenience abstraction.

**Exit:** a measured reuse decision and, when adopted, a tested minimal API with
fresh-call parity. It can proceed independently of S7 only in legacy/bounded
mode; policy state and monitoring identity must reset between conditions.

**Recorded result:** [S8a report](docs/solver-control-s8a.md) and
[portable evidence](docs/data/solver-control-s8a/manifest.json) publish a
predeclared four/eight-direction, 20-building pilot: 24 timing workers plus
four isolated profiling and eight untimed allocation workers. All 216
condition solves preserve exact field/diagnostic/control parity against
fresh calls, excluding checkpoint clocks. Reuse reduces native model,
operator and workspace construction from eight to one, but eight-direction
median savings are only 6.9% / 49 ms in legacy and 2.5% / 26 ms in adaptive;
both miss the required 10% or 100 ms. Preparation, operator subphases,
sampling/output, owned arrays and RSS are recorded separately. Defer the
public API under item 3; production/default/policy sources are unchanged.
The original clock-comparison harness failure is preserved and corrected
only in the audit. Focused validation: 38 tests pass. This completes S8a's
measured-decision exit, not S8b or S9.

#### S8b — Conditional comfort sensitivity and separately scoped optimization (deferred)

**Disposition, 2026-10-30:** explicitly deferred at the user's request. No
comfort sensitivity/refinement implementation or qualification is claimed.
Directional bounds, real-climate validation and mean/GEM/physical comfort
qualification remain separate follow-ups. This deferral is recorded in S9's
scope ledger and does not block closure of the scoped solver-control refactor.

After S7 provides qualified directional uncertainty estimates, propagate lower/
upper K scenarios through the existing climate/comfort calculation. Report
borderline classifications and refine only directions that can change the
decision, including rare directions affecting safety tails, under a total
budget. Preserve missing-direction/support rules, mean/GEM distinctions and
model/climate qualifications. Use synthetic climate fixtures for numerical
tests; obtaining or validating a real climate is a separate input task.

Comfort refinement is not available while directional estimates are unqualified.
Multi-right-hand-side kernels, preconditioner reuse, warm starts, GPU backends
and physical comfort/gust validation are named follow-ups when justified, not
implicit requirements for closing the control refactor. The S9 scope ledger
must state whether comfort sensitivity was implemented or remains conditional;
do not mark the entire S8 product roadmap complete by completing S8a alone.

### S9 — Release evidence and explicit closure (complete for the declared pedestrian scope)

1. Publish an implementation/closure report mapping S0–S8 to completed work,
   measured decisions, conditional/deferred integrations and unresolved numerical
   limitations. Include the original restricted vertical-grid closure and all
   reference/hotspot failures. Full acceptance-roadmap completion requires S7's
   validated scope. A bounded-only closure is a different, explicitly named
   scope decision, with the unqualified policy tracked as unfinished follow-up.
2. Freeze the final sources and numerical/policy identities. Audit portable
   evidence, source members, inputs, outputs, build/compiler/ABI/team metadata,
   excluded attempts and qualifications. Never regenerate old evidence under
   an unchanged identity. Stage isolated reviewable sources so unrelated live
   workspace edits do not enter the release or invalidate attribution.
3. Run the applicable OpenMP/serial native and full Python suites, focused
   ASan/UBSan lifecycle/monitor/controller/new-diagnostic checks, symbol audits,
   wheel runtime and sdist/wheel content checks. Preserve the strict 429-case
   default/disabled trajectory gate with teams 1/2/4 and bounded 8, plus serial
   parity. Test new policy/method paths against their declared accuracy and
   repeatability contracts. Scope any intentional numerical differences exactly;
   do not add a broad tolerance exception to the legacy parity gate.
4. Verify one-command campaign reproduction, same-input build reuse, rebuild on
   changed source/toolchain/ABI or damaged packages, fresh fixtures and immutable
   prior outcomes. Add new sources, tests and the high-level runner to packaging
   and provenance checks. Recheck history/allocation limits and worker deadlines.
5. Update README, API/dataset docs, stage reports and benchmark instructions.
   Publish defaults, supported grids/frames/precisions/outputs, status and error
   meanings, measured cadence/cost envelope and calibrated policy limitations.
   Numerical acceptance cannot be advertised as grid independence, physical
   validation or regulatory comfort qualification. Default promotion, model/
   boundary corrections and acceleration remain explicit separate decisions.

**Task closure:** the scoped mandatory exits above are satisfied, evidence is
portable and audited, release checks pass with unrelated failures separated,
and the closure report names every remaining conditional/follow-up item. Neither
a completed benchmark nor an exhausted research budget is task completion.

**Recorded result:** [S9 closure report](docs/solver-control-s9.md),
[scope ledger](docs/data/solver-control-s9/scope.json) and
[portable evidence](docs/data/solver-control-s9/manifest.json). Isolated builds
retain S7's native revision and pass 48 OpenMP, 45 serial and six ASan/UBSan
tests. The final full Python run passes 1,095 tests with 16 explicitly historical
ordering/toolchain skips. All twelve strict revision/team/backend comparisons
retain the 429-case default matrix exactly; all 24 final-build policy workers
match the frozen S7 fields/diagnostics/decisions. Three fresh smoke campaigns
confirm verified build reuse, damaged-package rebuild and immutable earlier
outcomes. Distribution content and installed-wheel runtime are release gates;
their final command results and package hashes are recorded in the evidence.
Prior source/outcome identities, failed attempts and restricted reference/grid
closures are retained. S8a's cache-only packaging metadata repair has a new
identity and preserves its original manifest; no measured outcome is replaced.
S8b is deferred explicitly, and no broader numerical/physical/comfort scope or
default promotion is claimed.


## Verification, file ownership and deferred work

Expected changes: new files in `src/qes_core/solver/`, `dtcc/solver_control.*`,
`dtcc/monitor.*`, new types in `dtcc/api`, edits to `dtcc/wind_runner.*`,
`dtcc/divergence.*`, `winds/WINDSGeneralData.*` (storage), `src/cpp/bindings.cpp`,
`src/dtcc_qes/wind.py`, `result.py` and the new `solver_control.py`. Deleted in
S1: `winds/Solver*`, `winds/SolverFactory*`, `dtcc/precision_solver.*`. Add
focused native tests under `tests/native/`, Python API and monitor tests under
`tests/`, and bounded benchmark and audit tools under `tools/` that archive
their sources beside their records. Update `tools/check_artifacts.py`, the study
tools' provenance lists and `src/qes_core/PROVENANCE.md` whenever QES-derived
files are replaced. When shipping this plan in source archives, keep its root
filename in the anchored `sdist.include` and the artifact checks.

Report unrelated existing failures separately; do not claim a full-suite pass
from focused checks. Numeric fixtures and archived studies retain their source
identity and acceptance definitions. Suitable stage commit messages include
`Extract a phase-based solver package`, `Reduce per-sweep memory traffic`,
`Add pedestrian checkpoint monitoring`, `Add bounded solver controls`,
`Record iteration method decision` and `Validate adaptive stopping policy`.

Deferred: the device backend itself (designed for in decision 8, planned for a
separate release), empirical branch smoothing, new boundary conditions,
changing the default precision, automatic thread-count tuning, warm starts
between directions, and per-runner logging to remove the process-wide mutex.
S6 selected a scoped internal relaxation factor without changing public
defaults. Krylov methods, Chebyshev, line preconditioning and multigrid remain
named acceleration candidates; S6 does not require one before S7 calibration.
If fast acceptable fields remain unattainable within the declared scope, use the
new diagnostics to justify a separate solver acceleration task rather than
silently expanding iteration budgets.

## Remaining execution checklist

- [x] S0–S4: baseline, phase extraction, S1a condition-state fixes, storage/traffic
  reduction, monitoring and bounded Python/dataset controls, with frozen evidence.
- [x] Run and audit the five 500/2,000-iteration urban campaigns: 324 workers,
  216 bitwise-equal candidate/baseline comparisons, no legacy-tolerance passes.
- [x] Investigate tolerance semantics and run the inflow-scaling check; retain
  absolute multiplier stopping as a compatibility diagnostic.
- [x] S5b: pure completed-iterate residual diagnostics and persistent hotspot
  classification, with strict legacy trajectory preservation.
- [x] S5c: solid-mask/operator consistency correction, separately frozen with
  explicit targeted numerical differences and strict unchanged-case parity.
- [x] S5a: portable evidence bundle, measured cadence/thread sensitivity and
  actual budget stops/replays; missed disabled-controls performance target
  explicitly recorded and reviewed, not claimed as passed.
- [x] S5b: two affordable same-grid references qualified and cost/error curves
  published; incompatible historical and large-grid cases remain unqualified.
- [x] S6: 43 main workers and eight early-transient checks select the internal
  `1.90f` calibration candidate on three qualified small same-grid conditions;
  native cost-to-target medians improve, public `1.78f` defaults remain exact,
  and the frozen method identity, limitations and portable replay are published.
- [x] S7: qualified native pedestrian-v1, frozen method/source identity,
  acceptance/warning/cache integration and zero false acceptances on the scoped
  held-out matrix; unsupported domains remain bounded/unaccepted.
- [x] S8a: publish four/eight-direction preparation/operator/sampling/output and
  memory measurements, exact fresh/reused parity and the predeclared measured
  public API deferral. Frozen-source replay confirms the decision.
- [x] S8b disposition: explicitly deferred by the user; comfort sensitivity,
  directional bounds and climate/model qualification remain separate follow-ups.
- [x] S9: isolated final source/evidence freeze, release validation, package/runtime
  checks and an explicit qualified-pedestrian closure ledger. S8b is deferred;
  larger-domain/reference/boundary/physical/comfort work remains separately scoped.

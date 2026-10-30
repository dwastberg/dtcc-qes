# Native solver-control refactor

**Status: S4 complete 2026-10-30; urban benchmark suite designed and smoke-tested.**
The [S4 implementation](docs/solver-control-s4.md) exposes bounded native
execution through Python and datasets. The [urban benchmark suite](docs/urban-wind-benchmarks.md)
freezes four neighbourhood layouts with 42–160 buildings, realistic-resolution
grids, multiple directions and bounded baseline/candidate comparison shards.
The [S3 implementation and handoff](docs/solver-control-s3.md) records compiled
slab/receptor monitoring, bounded histories, regional mass and optional
algebraic trends. Acceptance and public Python controls remain deferred.
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
The native phase interface is implemented; public controls and acceptance
policies described here remain unimplemented.

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

Stopping control alone cannot make the solver fast: it only avoids sweeps that
would otherwise be wasted. Sweeps dominate the measured wind-only runtime, the
float32 default costs more per sweep than float64, and the fixed relaxation
converges slowly (see [performance implications](#performance-implications)).
The plan therefore also reduces per-sweep memory traffic and memory footprint
without changing arithmetic, and decides the iteration method before
calibrating any stopping policy against that method's convergence behavior.

The first deliverable is **native continuation, checkpoint diagnostics and
bounded execution, with automatic accuracy acceptance disabled**, running on an
owned solver package whose per-sweep memory traffic has been reduced with
bitwise-unchanged results. Decide the iteration method next, then calibrate an
opt-in stopping policy for that method. Promotion to a default operating policy
is a separate decision requiring validation across the supported scope.

Preserve uniform x/y spacing, explicit and automatic vertical grids, and the
pedestrian-height support established by the grid work. Monitoring cannot fix
inadequate vertical support or make a receptor lie in the third cell. Grid
construction stays geometry-only, with its roughly 0.1 s planning objective.
This refactor must not reopen the vertical-grid task: do not resume the stopped
hours-long finest-grid reference or turn its missing result into a pass.

## Evidence motivating the work

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
| [`dtcc/api/wind_config.h`](src/qes_core/dtcc/api/wind_config.h) | QES-free contract seen by the bindings. `SolverOptions` holds tolerance, maximum iterations and precision; defaults 1e-5, 500, float32. | New control and result types go here. Add controls without silently replacing the defaults. |
| [`dtcc/wind_runner.cpp`](src/qes_core/dtcc/wind_runner.cpp) | S1 prepares one operator and routes each condition through initialization, `begin`, `advance` and `finalize`, then turbulence. Failed solves discard workspaces and return to prepared state. S1a resets rooftop state and validates wake dependencies. | Repeated Python calls remain independent zero starts; retain S1a's reuse and failure-recovery checks. |
| [`solver/`](src/qes_core/solver/solver.h) | Shared phase driver and precision-specific CPU kernels. S2 uses red/black defaults in both builds, with explicit lexicographic controls. Both precisions retain RHS, lambda and small relaxation tables; no old-iterate array. | S3 monitoring uses the phase interface without changing the S2 trajectory. |
| [`solver/solver.cpp`](src/qes_core/solver/solver.cpp) | Operator coefficients are checked once per preparation; condition fields once per `begin`. Pure slab observations and streamed mass diagnostics share reconstruction with finalization. | Preserve original face arithmetic, condition flags and borrowed-input lifetime in later backends. |
| [`winds/WINDSGeneralData`](src/qes_core/winds/WINDSGeneralData.h), [`Wall.cpp`](src/qes_core/winds/Wall.cpp) | Owns geometry, flags and face velocities. `Wall` builds coefficients once; production transfers/releases them into the immutable compact/explicit operator. Optional cut-cell and mixing-length arrays allocate on use. | Current condition flags remain independent of operator masks. |
| [`winds/LogProfile.cpp`](src/qes_core/winds/LogProfile.cpp), parameterization files | Per condition: zero-fill `u0/v0/w0`, single-sensor log profile, reset condition-dependent building state, empirical models in height order. S1a audited the supported pipeline. | Initialization happens once per condition; current post-parameterization flags remain separate from the geometry operator. |
| [`dtcc/divergence.cpp`](src/qes_core/dtcc/divergence.cpp) | Conservative six-face flux/volume diagnostic reads the passed prepared operator; excludes lateral cells and the highest physical layer; reports the last solved band separately. | Keep the definitions and add named regions in S3. |
| [`src/cpp/bindings.cpp`](src/cpp/bindings.cpp) | Inputs copied before releasing the GIL; one process-wide mutex (required because the `qes::log` handler is global); output vectors copied once more into NumPy. | Keep continuation inside one native call; no Python callbacks or full-volume output per checkpoint. |
| [`tools/compare_native_builds.py`](tools/compare_native_builds.py) | Baseline/candidate revisions or source archives; strict 429-case array/diagnostic comparisons, team and backend pairs. S2 adds an explicit serial migration policy that requires the unchanged OpenMP oracle and the exact old-serial change set. Valid wake-free inputs remain separate S1a tests. | The parity oracle for every stage; strict revision comparison remains the default. |
| Native tests and study tools | Use `SolverState`, fixed sweeps, prepared operators and copied current state. Diagnostic studies own a pre-final-sweep snapshot. Precision probes follow the selected order; historical drivers explicitly request their archived order. | Keep the study target/source names and historical evidence; S3 must not reintroduce full-volume checkpoint copies. |
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

Any future acceptance decision must still use a fresh global check from the
**same iterate**, together with current local checks: either an exact
end-of-sweep residual pass or the six-face divergence. Compute global checks
without an extra persistent velocity volume, or materialize into the existing
output buffers only when needed. Measure their cost.

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
than SOR can on these grids. Decide the method in S6, after monitoring and the
bounded controller exist and before S7 calibration:

1. Expose the relaxation factor as an internal kernel option, default `1.78f`,
   available only to tests and studies. Red/black ordering of this seven-point
   stencil is consistently ordered, so standard SOR theory applies; the optimum
   depends on the slowest error mode, which domain size, anisotropy, vertical
   stretching and buildings all affect.
2. Run a bounded fixed-work experiment, for example ω in {1.78, 1.85, 1.90,
   1.95}, on the tower fixture and at least one canyon case. Measure pedestrian
   error against accepted same-grid references, mass diagnostics and cost. Watch
   for transient error growth near the optimum, which affects checkpoint-based
   stopping.
3. If a fixed or grid-dependent factor gives a large gain, decide whether to
   adopt it as a new, documented default trajectory or to evaluate adaptive
   relaxation or Chebyshev acceleration. If anisotropy limits SOR, evaluate
   conjugate gradients with multigrid or vertical-line preconditioning; the
   operator appears symmetrizable by scaling each row by its layer thickness,
   which must be verified including the ground mirror and solid cells. Because
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

The other known defects (StreetCanyon can relabel solid cells as fluid; the
exposed `street_intersection_flag` has no model) are model questions, not
solver-control prerequisites. Track them separately.

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

Python: add an optional `solver_control` object to `wind.run`, with `None`
preserving the current API behavior. Put the value types in a small new
`src/dtcc_qes/solver_control.py`. Validate in Python and at the native entry
point; copy monitor inputs before releasing the GIL.

The first opt-in mode is `bounded`: legacy tolerance stopping plus a required
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
factor and lexicographic ordering are internal kernel options of the same kind
until S6 decides otherwise. Distinguish one continued N/2N/4N trajectory from
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

The preview low-speed threshold above is an initial design proposal. Vector
error must also be measured; a candidate matching p95 budget on
`|U - U_reference| / Uref` should be tested before accepting a policy, since speed
alone misses direction error. Record maximum errors and failure locations even
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
and estimate the remaining error as d_n·q/(1 − q). Calibration then sets a
safety factor and the conditions under which the estimate is trusted: q stable
over several intervals and clearly below 1, never rising or near 1. On the tower
evidence, raw 100-sweep differences understate the remaining error about four to
five times.

Begin policy experiments with at least three post-initialization checkpoints
and two consecutive stability intervals, an explicit minimum interval in
sweeps, and a minimum work requirement selected during calibration. Compare
short and longer windows to catch slow drift. Stable support, fixed receptors,
moving hotspots and fresh mass checks must all pass. Initial candidate
checkpoint spacings of 100 and 250 sweeps are reasonable bounded experiments;
the 500/1000/2000 observations do not establish a universal schedule. Stagnation
without acceptance stops as `stagnation`, never `target_reached`.

K was independent of Uref to about 2e-6 in an earlier three-building check
(Uref = 2, 5 and 12 m/s), so calibrate all policy quantities in K and treat Uref
as a scale. One linearity check per policy replaces a wind-speed sweep. Repeat
it if stability-dependent profiles or turbulence models are bridged.

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

### S2 — Per-sweep traffic and memory

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
The reviewed next step is S3 monitoring against the frozen S2 source identity;
implementation stops here.

### S3 — Pedestrian and mass monitoring

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
93%, so cadence must remain explicit and optional. S5 still needs to qualify
public API overhead, including the observed disabled-path timing variation.
No automatic accuracy acceptance or S4 controller is implemented here.

### S4 — Bounded controller and Python API

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
split into eighteen explicitly selected, six-worker shards. The realistic
resolution performance campaign is the next S5 milestone.

### S5 — Overhead and cadence

Execute S5 in two parts. S5a runs repeated public API runtime/memory and
equal-completed-work comparisons with the urban suite. S5b adds time versus
measured error where a compatible same-grid reference is already qualified.
Unavailable references must not block S5a or be replaced by unqualified
baseline differences. S6 uses these cost/error observations for the method
decision; S7/S8 do not delay the first end-to-end benchmark campaign.

1. Compare the S0 baseline, the refactored path with controls disabled, and
   bounded execution with monitoring. Compare equal sweep counts and,
   separately, equal measured error; label the distinction. Report the S2 gain
   separately from monitoring overhead.
2. Use warm, repeated measurements on a declared machine, recording actual teams
   (1/2/4 and a bounded 8-thread check), phase timings and peak RSS. Avoid
   concurrent timing workers and host-sleep-contaminated timing claims.
3. Review targets, not guarantees: no more than 5% median API regression with
   controls disabled, and no more than 10% overhead for useful monitoring at the
   same sweep count on the representative case.

**Exit:** a documented cadence and runtime envelope. If monitoring dominates,
reduce duplicate work or its frequency while keeping the required checks; do
not drop difficult receptors to meet the target.

### S6 — Decide the iteration method

1. Run the bounded relaxation experiment from decision 7 with the S3 monitors
   and S4 budgets.
2. Plot cost against pedestrian error and mass diagnostics for each candidate
   on the tower fixture and at least one canyon case.
3. Keep the current method, adopt a new relaxation default, or open a separate
   solver task for acceleration, Krylov or multigrid methods as new kernels
   behind the phase contract.

**Exit:** a recorded method decision with its evidence. If the method changes,
that task, with its own parity and validation evidence, completes before S7.

### S7 — Calibrate and validate an opt-in adaptive policy

1. Freeze candidate error contracts, diagnostics, checkpoint rules, scope and
   matrix limits for the method chosen in S6. Separate calibration cases from
   held-out validation cases.
2. Cover uniform, explicit and automatic grids within the supported scope;
   different aspect ratios; tower, canyon, passage and sheltered geometries;
   oblique winds; one wind-speed linearity check; both pedestrian heights;
   domain-height and lateral controls; and the known upwind-cavity and sidewall
   branch sensitivity. Include float32 plateaus, slow drift, invalid support and
   moving hotspots.
3. Prefer accepted same-grid references to isolate iterative error. Treat grid
   sensitivity and physical model validation separately. If a case lacks an
   affordable qualified reference, mark it unqualified and restrict the policy
   scope; do not infer correctness from a final small residual alone.
4. Replay recorded checkpoint histories to design the predictor, starting from
   the geometric remaining-error estimate, then run it online on held-out cases.
   Report every false acceptance, failure to accept, timeout, achieved reference
   error and cost. A finite validation matrix gives empirical evidence, not a
   universal mathematical error bound.
5. Enable `adaptive` only after the declared held-out cases satisfy the frozen
   contract without false acceptance. Cases outside validated scope remain
   unqualified. Publish policy identity, limitations and measured tradeoffs.

**Exit:** an opt-in, versioned policy with separate acceptance status, accurate
warning/exception behavior, reproducible evidence and a rollback to legacy mode.
Default promotion requires a later explicit review.

### S8 — Multi-direction runs and comfort orchestration

1. With decision 9's fixes in place and S0's profile showing a worthwhile
   preparation share, add execution of several conditions on one prepared
   model and operator, exposed through a reusable Python model object or a
   multi-direction call. Keep `wind.run` unchanged.
2. Evaluate multi-right-hand-side sweeps on the compact operator and, if S6
   chose a preconditioned method, preconditioner reuse across directions.
   Warm starts between directions remain a separate, measured question.
3. After the native policy is validated, carry estimated numerical uncertainty
   in directional speed factors into the comfort calculation. Reassess
   classifications using the uncertainty range; mark classifications sensitive
   to that range as borderline and refine only contributing directions under an
   overall time budget. Do not call empirical numerical-error estimates
   statistical confidence intervals. Mean-field accuracy does not supply missing
   gust/GEM information.

Items 1 and 2 can start after S2 and S4 independently of S6 and S7. Item 3
needs S7. None of this substitutes for physical validation of QES for the
intended use.

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
Relaxation changes, Krylov methods and multigrid are not simply deferred: S6
decides whether one becomes a separate solver task before policy calibration.
If fast acceptable fields remain unattainable within the declared scope, use the
new diagnostics to justify a separate solver acceleration task rather than
silently expanding iteration budgets.

## Start checklist

- S0 complete: baseline revision, archived evidence, phase/pass timings and array
  allocation inventory recorded in [the report](docs/solver-control-s0.md).
- Implement the phase-based solver package, delete the old solver classes, and
  prove bitwise parity with the harness (S1); then stop for review.
- Reduce traffic and memory with bitwise checks (S2) before adding monitoring.
- Fix per-condition model state before any reuse across conditions (decision 9).
- Decide the iteration method (S6) before calibrating any stopping policy (S7).

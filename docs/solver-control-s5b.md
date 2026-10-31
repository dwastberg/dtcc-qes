# S5b: coherent residuals and numerical qualification

This is the historical S5b diagnostic stage. Later S5c/S7 changes and the final
qualified scope are recorded in the [S9 closure](solver-control-s9.md).

S5b adds pure completed-iterate diagnostics and completes a bounded hotspot and
reference study. Default numerical behavior is unchanged: the 429-case revision
gate passes bitwise in serial and at OpenMP teams 1/2/4/8, including team/backend
comparisons. Adaptive acceptance remains unimplemented.

The study confirms an inherited solid-mask inconsistency in oblique urban
cases. The subsequent [S5 completion](solver-control-s5.md) repairs that defect in a
separately frozen S5c change. Increasing iterations or loosening tolerance cannot
repair it. The diagnostic implementation deliberately
preserves those outputs and the evidence needed to review a separate correction.

## Native contract

`SolverState<Real>::equation_residual(region, floors)` reads the current complete
iterate. It is available after `begin`, between whole sweeps and after
`finalize`. It neither advances nor mutates the state. There are no new
persistent arrays or full velocity volumes; extra storage is constant.

For the immutable row coefficients `e,f,g,h,m,n`, define

```
D = e + f + g + h + m + n
(A lambda)c = D lambda[c] - sum(a[c,neighbor] lambda[neighbor])
b[c] = -R[c]
r[c] = b[c] - (A lambda)c
```

No row or diagonal scaling is applied. Diagnostic products and reductions use
double precision on the stored float coefficients and float32/float64 iterate
and RHS. The sign matches the existing update-time trend, but all neighbors now
belong to the same completed iterate. Native RHS units are retained; this value
is not labeled physical corrected-face divergence.

The assessed region uses the same physical indices and condition-fluid mask as
`diagnose`: lateral interior cells, physical layers `[0,nz-1)`, excluding flags
0/2. The last solved layer is included in the equation norm and separately
reported as the top band by mass diagnostics. The highest physical layer and
lateral shell are prescribed, not solved; their multiplier values still enter
neighbor terms. The ground ghost has the completed sweep's mirrored multiplier.
At zero sweeps, the entire multiplier array is zero.

The result reports maximum and volume-weighted RMS residuals, RHS norms, fluid
and excluded-solid counts, volume and iteration. Because every `begin` zeros
lambda, the RHS norm is also the initial residual norm on that assessment.
Relative results divide each norm by `max(initial norm, corresponding floor)`.
The explicit positive finite floors default to `1e-30` in native RHS units;
they prevent division by zero and do not define an acceptance threshold or a
physical length. Empty assessments return absent relative norms; calm nonempty
zero RHS/iterate returns zero. Nonfinite operands, norms or ratios fail visibly.
The serial fixed-order diagnostic reduction is reproducible across teams.

`diagnose_cell(i,j,k)` returns a small value record for one solved physical cell:
current flag/eligibility, multiplier/RHS/residual, six coefficients, neighboring
multipliers, six initial and corrected faces, and top-band membership. Excluded
solid rows remain inspectable but are never counted as assessed fluid. It does
not expose mutable workspace storage. The existing `ResidualTrend`, controller,
Python metadata and legacy convergence semantics are unchanged.

## Finite study and evidence

The [protocol](data/solver-control-s5b/protocol.json) declares sixteen sequential
workers in six-worker shards, four actual OpenMP threads, 30 s per worker and
180 s per shard. Builds/tests precede the study. All sixteen completed; the
largest worker took 8.53 s. This is a native diagnostic study, not a new public
API performance comparison. No work budgets were expanded.

Four core workers reproduce downtown 225°/270°/315° and courtyard 225° on the
exact frozen 2 m benchmark grids. They capture residuals, both pedestrian
heights, required receptors and global signed/absolute flux at 0/500/1000/1500/
2000 sweeps, and locate hotspots at 500/2000. Four 4 m workers compare float32
and float64 from identical initial float fields/condition flags; two further
workers disable canyon parameterization as counterfactual controls. Six workers
run independent zero-start reference triples on the two new affordable cases.

The [reference inventory](data/solver-control-s5b/reference-inventory.json)
rejects automatic reuse of the historical 0.5 m/92-layer serial tower reference:
the new calibration grids/geometries differ, ordering/source compatibility and
complete initial-field equality are not established. The urban 2,000-sweep
benchmarks are measurements, not references. Historical failures are unchanged.

## Hotspot disposition

Coordinates below are native local metres; layers in the raw records are
physical zero-based indices. The [raw results](data/solver-control-s5b/results.json)
retain neighboring flags before/after parameterization, coefficient rows,
multipliers, faces, individual-cell flux and global flux on the same iterate.
The [independent replay](data/solver-control-s5b/hotspot-disposition.json)
reassembles residual and six-face divergence for all fifty saved hotspot records.

| Core case | Maximum divergence at 500 → 2000, s⁻¹ | 2000-sweep hotspot (x,y,z), m | Initial → current flag | Cell equation residual |
| --- | ---: | --- | --- | ---: |
| Downtown 225° | 3.43034 → 3.58086 | (213,215,16.9643) | solid 0 → canyon 6 | −0.007717 |
| Downtown 315° | 3.97643 → 3.92169 | (329,129,20.7143) | solid 0 → canyon 6 | +0.004070 |
| Courtyard 225° | 3.36221 → 3.30357 | (253,305,9.1099) | solid 0 → canyon 6 | −0.0000839 |
| Downtown 270° control | 0.34400 → 0.01600 | (153,305,0.6429) | fluid 1 → fluid 1 | −0.032001 |

These three oblique cases contain respectively 145/359/527 assessed cells that
were solid during geometry/operator preparation. `StreetCanyon.cpp`'s final
flag assignment protects flags 7/8 but can overwrite 0/2. The operator was
prepared before this change: initially solid rows keep couplings that disagree
with adjacent fluid wall rows and with current face masking. The exported
downtown cell, for example, has east/north/south nonzero coefficients while all
three corresponding faces are masked to zero. Its individual signed flux is
−15.7558 m³/s, despite a small equation residual. The defect is a
**condition-mask/operator/reconstruction inconsistency**, not an S4 regression,
a difficult cell to discard, or a residual threshold to relax.

The downtown pilot keeps essentially the same 2,000-sweep maximum in float32
and float64: 2.847121 versus 2.847125 s⁻¹, on identical initial fields/flags.
Disabling canyon parameterization removes relabeling and yields 0.004343 s⁻¹.
The courtyard pilot has no relabeling, unlike its finer core grid; it is a
negative control. Its float64 maximum is smaller than float32's (0.000405
versus 0.000568 s⁻¹), but it is still decaying. These controls do not justify
attributing all unfinished solves to a precision floor.

Genuinely fluid interior maxima closely follow `divergence ≈ r/2` where shared
stencils/masks are consistent. The large core residuals still decay, so there
is ordinary iterative error alongside the defect. The last solved top band is
a separate limitation: the equation has a coupling to the prescribed highest
layer, while the upper reconstructed face is left at its initial value. Top-band
maxima remain visible (about 0.0455–0.0624 s⁻¹ in these core runs). Preserve this
boundary convention and separate reporting; do not quietly count it as repaired.

Acceptance for the affected urban scope remains blocked until a separately
frozen numerical change repairs and validates solid-mask consistency.

## Qualified small references and cost/error curves

The two new calibration cases use 160×160×64 m domains, uniform 2 m cells
(204,800 physical cells), 270° winds, Uref=5 m/s and float64 arithmetic. One has
the four historical tower footprint sizes/heights in a newly declared local
grid; the other has twenty buildings, passages and sheltered street space.
Neither is the historical tower reference or a reference for the large cities.

Each case uses independent zero starts at 500/1000/2000 fixed sweeps. The
predeclared length is 23.7 m for both cases. Every checkpoint must meet scaled
interior maximum/RMS mass ≤1e-3/1e-4; both successive pairs must meet vector
maximum/p95 change divided by Uref ≤1e-3/5e-4 at both heights, with stable valid
support and every required receptor valid. Both triples pass. The largest
scaled mass maximum is 5.71e-5 for the tower and 1.01e-5 for passages; largest
successive vector maxima are 4.55e-6 and 6.78e-7 Uref. No old gate was loosened.

The longest worker per case streams 81 checkpoints, including iteration zero,
into [compact NPZ histories](data/solver-control-s5b/12.npz) and the
[cost/error dataset](data/solver-control-s5b/cost-error-curves.json). Production
history stays bounded at four summaries. Curves compare each iterate to the
qualified same-grid final reference; this is numerical qualification on that
scope, not exact truth, physical validation or a grid/domain error bound.
The passage history is [15.npz](data/solver-control-s5b/15.npz).

Completed-iterate global residual scans took approximately 16–34 ms on the
core grids; global mass with signed/absolute flux took 95–180 ms. Pedestrian
monitor captures without global mass took about 6–7 ms. These are individual
local observations, not repeated overhead estimates; S5a must account for this
cost when choosing cadence. No global scans are added to the public controller
by this change.

## Verification, provenance and running

The [validation record](data/solver-control-s5b/validation.json) and logs record:

- Native OpenMP: 46 passed; serial: 43 passed. An independently assembled dense
  small-row oracle covers both precisions/orders/storage forms, uniform and
  stretched grids, ground mirrors, prescribed boundaries, solids, calm flow,
  restarts, nonfinite failure, normalization and trajectory/storage purity.
- ASan/UBSan: all four focused residual/phase/monitor/controller tests pass.
- Strict S4 comparison: all twelve revision/team/backend comparisons pass,
  429 cases per revision comparison and 3,872 records per comparison.
- Native forbidden-symbol audit passes.
- The broader live-workspace Python run has 1,037 passed, 16 skipped and 13
  failures. One failure used the obsolete default study executable and passes
  with this build's executable. All twelve remaining dataset-slice failures
  reproduce against the frozen S4 package; live tests depend on unfinished
  dataset work outside S5b. No dataset code is changed here. The focused study
  tests and evidence replay are recorded separately.

The first supervisor's analysis rejected NaN velocities on explicitly invalid
samples after all native workers had completed. Corrected analysis uses validity
masks and still rejects nonfinite **valid** samples. No native workers were
rerun; the original driver and failed-analysis log are retained. The measured
source archive and final implementation archive have separate hashes. Their
four new/modified native diagnostic files are identical; the final archive adds
the corrected runner, independent analysis and Python tests.

Run a fresh complete bounded study from the repository root:

```sh
.venv/bin/python tools/run_solver_numerics.py --output build/numerics-s5b-new
```

The runner builds the frozen S4 source plus explicit diagnostic overlays,
checks native tests, runs the finite matrix and writes results. It uses the
published case files when historical `build/urban-benchmarks` fixtures are absent.
The output directory must be new. Reanalysis of an existing result is explicit:

```sh
.venv/bin/python tools/run_solver_numerics.py --output build/numerics-s5b-new --analyze
.venv/bin/python tools/analyze_solver_numerics.py build/numerics-s5b-new
.venv/bin/python docs/data/solver-control-s5b/audit.py
```

The portable audit checks source/evidence hashes, independently replays hotspot
arithmetic, reference qualification and all saved cost/error comparisons, and
checks strict parity outcomes. It performs no native solve. S0–S4 evidence is
unchanged. At the S5b handoff, publication of the earlier campaigns, cadence sensitivity
and real budget-stop experiments remained open. The subsequent
[S5 completion report](solver-control-s5.md) records their completed evidence
and the separate S5c numerical correction.

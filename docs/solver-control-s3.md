# S3: pedestrian and mass monitoring

S3 implements internal native monitoring against the frozen S2 baseline. It
does not add Python controls, a controller, an accuracy decision or a stopping
policy. Legacy defaults and output ownership remain unchanged. The next stage
is S4; implementation stops before it.

## Native contract

`dtcc/monitor.{h,cpp}` compiles a `MonitorSpec` after a condition begins. The
plain records live in `dtcc/api/monitor_types.h`. A specification declares an
explicit half-open rectangle of native x/y centers, original double heights in
metres AGL, named required/optional receptors, local/world x/y coordinates,
origin/CRS, Uref, window spans, history and memory limits. The interpolation
policy is fixed: linear components vertically, bilinear components horizontally,
all nonzero-weight contributors valid, no extrapolation. World origins affect
x/y only; height remains AGL.

The monitor merges the union of contributing physical layers, keeping distant
supports in separate slabs. `SolverState::observe` writes rounded float32
centers and current condition flags into reusable monitor buffers. It shares
face reconstruction, solid masking and center averaging with full finalization.
Interpolation widens those stored centers to double and locates the original
height without narrowing it to float32. Exact centers ignore inactive neighbors;
solid flags 0/2, absent center support and nonfinite components produce invalid
samples. Speed is computed after interpolating components.

Captures require the same live state/condition epoch, increasing completed
sweeps and monotone finite elapsed time. Rebeginning a solver invalidates its
old monitor. Observation never writes the borrowed input fields or the solver
workspace; destination aliasing is rejected. Backend/capture failures invalidate
the monitor. A small native read-only source adapter permits independent
manufactured sampling tests without modifying live borrowed condition inputs.

Each checkpoint records validity counts, all individual required receptors,
peak speed/location, absolute vector/speed changes, Uref-normalized vector and
speed-factor changes, equal-weight linear p95 and maximum. Uref=0 leaves
normalized quantities unavailable while retaining absolute measurements.
Short/long windows are configurable checkpoint spans with explicit endpoint
sweep counts. Their support is the intersection across every intervening frame;
an invalid intermediate sample remains a validity transition after recovery.
Successive ratios require stable support, equal sweep intervals and a finite
positive preceding change. Ratios predict no remaining error. Each plane window
tracks both its current and preceding peak locations and the values at both
endpoints, so constant peak magnitudes cannot hide a migrating hotspot.
Iteration-zero reconstruction is labeled initial and contributes no stability
interval.

Memory is checked before allocating slab, sample-ring, scratch and summary-ring
buffers. The sample ring holds `long_window + 1` frames; summary history has its
own fixed configured capacity. Complete checkpoint volumes and stored histories
of planes are absent. Capacity accounting includes owned metadata and buffers;
small coordinate axes scale with nz, while sample storage scales with requested
slabs, ROI size and configured window/history bounds. Per-capture capacities do
not grow. Returned references last until their ring slot is reused; the caller
must keep the compiled condition alive and serialize captures with advancement.

## Independent mass and algebraic measurements

Regional checks retain conservative maximum and volume-weighted RMS divergence
in s^-1, the separate last-solved-band maximum and counts. Each height's
contributing band is checked over the ROI; optional global and additional
physical index boxes use the same implementation. Compiled region metadata
records requested lateral/highest-layer exclusions. Prescribed top behavior is
unchanged, and the last solved band remains separate.

Extended six-face diagnostics report summed signed cell flux, actual signed
region-boundary flux, summed absolute cell imbalance and throughflow in m³/s.
Interior and top-band regions are separated when computing boundary flux.
Rounded opposite stencil coefficients need not cancel identically, so boundary
and summed cell flux are retained independently. Canceling local source/sink
errors therefore remain visible.

Relative imbalance is unavailable by default. An explicitly supplied,
experimental positive fraction defines the dimensionally consistent threshold
`fraction * Uref * 0.5 * sum(abs(effective_face_area))`. Resolved-throughflow
cells report maximum and volume-weighted RMS `abs(net_flux)/throughflow`;
low-flow and unassessed counts remain explicit. This is a diagnostic option,
not a calibrated production cutoff or an acceptance policy.

`advance(work, true)` optionally gathers widened algebraic residual maximum
and volume-weighted RMS before each cell update, using the original stencil
and the partly updated iterate. Specialized disabled kernels compile out this
work; enabled kernels retain the original update expressions. Accumulation uses
thread-local scalars and a per-thread merge, without another volume or pass.
Only the latest completed sweep's trend is retained. Disabling collection or
beginning another condition clears it. Parallel sums need not be bitwise equal
between teams; the solver trajectory must be.

The trend is explicitly in **native algebraic RHS units**, never s^-1 or a
velocity-error estimate. A single-cell oracle checks its first and second
sweeps and ground-mirror timing. Existing independent staggered-flux and study
diagnostic tests remain in the suite. No physical-unit conversion of this
partly updated trend is published. Any later acceptance still needs a fresh
global diagnostic from the current iterate and separate reference calibration.

## Verification

The frozen source identity is
`sha256:c0d2f0260170482fe195e3a7541205a5c5487810bebf4a25c7be0d0e86a86c0c`.
Its complete native, binding, Python, build, study and test sources are archived
in [sources.tar.gz](data/solver-control-s3/sources.tar.gz), with a member hash
index. This identifies an uncommitted workspace; no new commit is claimed.
S0/S1/S1a/S2 evidence hashes remain unchanged.

The strict 429-case, 3,872-record comparison against S2's
`sha256:931408afbf86a578b978f17dc15b8bb9f8fdccc9522ebe86da8c6c499f13d803`
passes without numerical differences in serial and OpenMP teams 1/2/4/8.
Candidate teams and backend pairs also match. No ordering-migration allowance
is used. The separate enabled-monitor trajectory tests compare workspace and
final face bytes after 83 sweeps in both precisions, both orders, compact and
explicit operators, uniform/stretched grids and all four requested teams.

Eight native-to-Python parity configurations compare every queried plane and
receptor with full finalization followed by `WindResult.sample(method="linear")`
and the existing study collocation helper. Validity masks must be exact;
components must agree within four float32 ULPs at `max(1, abs(reference))`.
Tests include exact centers and nextafter heights, fractional support, all five
mandatory tower receptors at both heights, fractional x/y, local/world frames,
prescribed faces and top/bottom center-range limits. Manufactured tests add
inactive solid corners, flags 0/2, NaN/infinity, zero flow, no support, changing
validity, moving peaks, bounded rings, memory rejection, wrong conditions and
malformed source lengths. Independent flux oracles check units, cancellation,
low-flow handling and the legacy diagnostic region.

| Check | Result |
| --- | --- |
| Release native, OpenMP / serial | 44 / 41 passed |
| ASan/UBSan native, OpenMP | 44 passed |
| Full Python suite, each backend | 997 passed, 16 historical-order skips |
| Packaged-wheel build/condition-state/sampling tests | 54 passed |
| Native symbol audits, all three builds | Passed |
| Wheel and source-distribution content/evidence audit | Passed |
| Final strict revision/team/backend comparisons | All 12 passed |
| Sequential bounded profiling matrix | 60 workers completed, matching outputs |

The [manifest](data/solver-control-s3/manifest.json) hashes the source snapshot,
parity report, validation logs, complete cost records and rejected attempts.
Reproduce the strict numerical gate with:

```sh
.venv/bin/python tools/compare_native_builds.py \
  --baseline-archive docs/data/solver-control-s2/final-sources.tar.gz \
  --candidate-archive docs/data/solver-control-s3/sources.tar.gz \
  --thread-counts 1 2 4 8 --require-backend-parity \
  --report build/s3-recheck.json
```

## Bounded cost evidence

The [protocol](data/solver-control-s3/profile/protocol.json) and
[derived summary](data/solver-control-s3/performance-summary.json) compare
frozen S2/S3 native probes at **40 fixed sweeps**, with checkpoints every ten
sweeps. Geometry uses S0's four-building tower layout, with four 12 m squares,
0.5 m x/y spacing, the archived automatic 92-layer profile, 9,420,800 physical
cells, Uref=5 m/s and direction 270. This native probe places the domain at
[0,160) × [0,160) m, with blocks starting at x/y=22/42 m and origin (0,0,0).
S0's public API profile used world bounds [-40,120) × [-40,120), so lateral
placement differs. Cost comparisons here use only the identical native S2/S3
inputs; no timing gain against S0's API run is inferred.
The ROI is [0,80) × [0,80) m; both heights and
all five mandatory receptors at each height remain present. No optional global
six-face scan is included in the per-checkpoint cost; global conservative
diagnostics are still included in finalization in every mode.

All workers ran sequentially, under 30 s each and a 180 s total matrix cap.
The final matrix took 59.56 s. Both precisions and actual OpenMP teams 1/2/4/8
completed; four-thread runs have three process repetitions, other teams one.
Every mode/revision retains identical field fingerprints and exact final norm
and mass diagnostics within a precision. Full bytewise parity is checked
separately by the numerical tests above. Probe sources, actual teams, compiler
configuration, phase clocks, grid, platform and RSS are archived. The machine
is the same local Apple Silicon host with 14 CPUs; these are short native
measurements, not public Python API or matched-error qualification. Process
setup, input parsing and fingerprinting are outside the timer; preparation,
initialization, full centered finalization and mass diagnostics are included.

Four-thread medians, native seconds:

| Precision | Mode | Total | Sweep ms | Checkpoint seconds, all four | Peak RSS, MiB |
| --- | --- | ---: | ---: | ---: | ---: |
| float32 | S2, disabled | 0.555 | 4.686 | — | 682.0 |
| float32 | S3, disabled | 0.585 | 4.763 | — | 685.8 |
| float32 | Slabs/regional mass | 0.605 | 4.782 | 0.0265 | 691.3 |
| float32 | Slabs + trend on checkpoint sweeps | 0.645 | 6.141 | 0.0266 | 690.5 |
| float32 | Slabs + trend on every sweep | 1.129 | 17.777 | 0.0270 | 693.1 |
| float64 | S2, disabled | 0.606 | 5.039 | — | 827.5 |
| float64 | S3, disabled | 0.623 | 5.497 | — | 830.5 |
| float64 | Slabs/regional mass | 0.639 | 5.164 | 0.0261 | 839.1 |
| float64 | Slabs + trend on checkpoint sweeps | 0.653 | 5.475 | 0.0257 | 836.9 |
| float64 | Slabs + trend on every sweep | 0.784 | 8.603 | 0.0258 | 838.3 |

Compiling the monitor and taking the initial reconstruction costs about
6.3–6.6 ms in these four-thread medians. Two shared slab layers, three sample
frames and eight summary slots retain **8,719,574 bytes (8.32 MiB)**, unchanged
across all five captures. There is no extra checkpoint volume. Process peak
RSS also includes transient preparation allocations, so its variation is not
the monitor's allocation size.

Against S3 disabled mode, slabs add 3.4%/2.5% total native cost for
float32/float64. Collecting the trend only on each checkpoint's final sweep
adds 10.3%/4.8%; collecting it continuously adds 93.1%/25.8%. Recomputing the
widened residual and reducing its RMS is materially expensive, especially in
float32; it must remain optional. These timings support separate cadence
choices, not a claim that continuous diagnostics are cheap.

The disabled S3 native total is 5.4%/3.0% above S2 in this small matrix. There
is phase variation, and disabled float64 sweeps here are slower than the
slab-mode sample, which reinforces the limits of short timings. This is not
evidence that S5's public API regression target has been met. S5 must measure
that target and investigate any persistent disabled-path regression; the
current measurements provide an explicit risk for that review.

The first probe build omitted `DTCC_QES_BUILD_TESTS=ON` and therefore lacked
the candidate target. Its sources/logs are retained under `attempts/`.
An initial complete timing matrix overlapped the final numerical comparison;
its output parity passed, but its timings are excluded. After all competing
workers ended, the archived `rerun_profile.py` wrapper executed the same
unchanged matrix code against those same built probes. Only that sequential
matrix supplies the results above. The corrected standalone profiler reproduces
the full build and matrix with:

```sh
.venv/bin/python tools/profile_solver_monitor.py \
  --baseline-archive docs/data/solver-control-s2/final-sources.tar.gz \
  --candidate-archive docs/data/solver-control-s3/sources.tar.gz \
  --output build/s3-cost-recheck \
  --work-dir build/s3-cost-recheck-build
```

## S4 handoff

The internal phase and monitor interfaces are ready for the bounded controller.
Keep public defaults unchanged, expose bounded mode with accuracy unassessed,
and retain acceptance for S7. S4 must own the live state/monitor lifetime and
serialize observations with sweeps. Its failure path must preserve any desired
last trusted summary before attempting a capture that could fail. Enforce
cooperative monotonic deadlines around initialization, whole sweeps,
checkpoint evaluation and output, with explicit zero-work/overhead accounting.
Use fake-clock boundary tests plus a small subprocess deadline integration
check. Include no-GIL, exception, ownership, repeated-condition and serialization
checks when threading configuration through the native/Python API.

Cadence is an explicit controller choice: distinguish slab checkpoints, optional
global six-face scans and in-sweep trend collection. The cost evidence measures
these native operations at matched work; S5 still owns repeated public API
overhead/cadence qualification and matched-error comparisons. It must not infer
accuracy or change difficult required receptors to meet a timing target.

# S7 — Qualified opt-in pedestrian numerical acceptance

> Historical stage report: original snippets and identities are preserved. Use the current [migration table](../README.md#api-migration) and [solver guide](solver-control.md) for live calls.

S7 is complete for the `pedestrian-v1` scope below. Existing calls and bounded
controls retain their default 1.78 relaxation and legacy stopping behavior.
Qualified adaptive calls use S6's internal 1.90 method and can stop independently
of the legacy multiplier tolerance. Neither mode changes the meaning of
`diagnostics.converged`.

The [portable evidence](data/solver-control-s7/manifest.json) contains 100 study
workers: 33 fixed-work/reference workers and 67 full Python API workers. Six
new held-out conditions cover staggered streets, courtyards, mixed heights,
oblique winds, a graded vertical grid and Uref scaling. There were **zero false
acceptances, zero missed acceptances on the qualified full-budget matrix, and
zero recorded predictor underestimates**. Nine reference triples qualified;
one larger-domain triple failed and its scope remains unaccepted.

This is empirical same-grid **numerical** qualification. It establishes no
full-volume, turbulence, gust, physical wind or comfort-classification accuracy.
Large urban benchmark domains remain unqualified. S8 and S9 are still open.

## Use

Set `OMP_NUM_THREADS=4` and `OMP_DYNAMIC=FALSE` before starting Python (or use
the serial build). A larger default OpenMP team is outside this qualification.

```python
from dtcc_qes import wind

monitor = wind.MonitorSpec(
    region=(8, 152, 8, 152),
    heights=(1.5, 1.75),
    receptors=(
        wind.Receptor("street-1.5", 19, 31, 1.5),
        wind.Receptor("street-1.75", 19, 31, 1.75),
    ),
    history_limit=16,
)
result = wind.run(
    city, 5, 240,
    bounds=(0, 0, 0, 160, 160, 64), resolution=2,
    max_iterations=2000,
    solver_control=wind.SolverControl(1.0, monitor, mode="adaptive"),
    raise_on_unaccepted=True,
)
print(result.control["accepted"], result.control["assessment_reason"])
```

The example assumes a city and receptors satisfying the scope; a receptor in a
solid building is not accepted. `policy="pedestrian-v1"` is set explicitly in
the serialized control configuration, including when omitted by the caller.
Cadence is fixed at 25; effective short/long windows are 1/4 checkpoints and
fresh global safeguards are enabled. History must have at least five slots;
its configured memory limit includes the policy's bounded scalar history.

With default `raise_on_unaccepted=False`, an unaccepted adaptive result logs a
scope/acceptance warning and returns its available fields. With `True`, it
raises `wind.UnacceptedResultError` carrying diagnostics and the control record.
Accepted output with `converged=False` does not emit the old nonconvergence
warning. Legacy-converged output without acceptance remains unaccepted.
Adaptive mode rejects `raise_on_nonconvergence=True` and calm wind; use the
acceptance-specific option instead. No completed sweep raises the existing
`BudgetExhaustedError`. Adaptive numerical execution failure raises
`NumericalFailureError` with its record and does not fabricate finite output.

## Frozen scope and targets

| Property | Qualified envelope |
| --- | --- |
| Physical grid | **80×80×32** cells, 2 m horizontal spacing |
| Vertical grid | Uniform 2 m; or explicit layers `1.2 * 1.03**k`, k=0..31, within the documented float-coordinate rounding allowance |
| Arithmetic | Float32, AppleClang 17 arm64, Release arithmetic, fp contraction on, matching the frozen implementation identity |
| Backend/team | Serial or OpenMP teams 1–4 |
| Condition | Neutral log law, Uref 2–10 m/s at 10 m, roughness 0.1 m |
| Models | Existing default building-model flags and wall roughness; wind without turbulence |
| Buildings | 4–32 axis-aligned flat-base rectangles, sides 8–16 m, heights 4–24 m, at least 12 m from the horizontal domain boundary |
| Observables | Both 1.5 and 1.75 m, ROI at least 20×20 m, at least 16 valid ROI samples per height |
| Required receptors | At least one at each height, at most 16 total receptors; required interpolation support inside the ROI with a conservative 2 m inset |

Arbitrary stretched/automatic grids, larger domains, other model flags,
precisions/builds and derived outputs have no acceptance claim. Unsupported
configurations execute the existing bounded/legacy-tolerance trajectory with
1.78, `accepted=False`, `accuracy_status="not_assessed"` and a specific
`assessment_reason`. Unsupported does not silently select the 1.90 method.

| Numerical criterion | Limit |
| --- | --- |
| ROI vector error / Uref, p95 at each height | 5e-4 |
| ROI vector error / Uref, maximum at each height | 1e-3 |
| Speed-factor error, p95 / maximum | 5e-4 / 1e-3 |
| Every required receptor and moving hotspot | Maximum vector/speed-factor error <=1e-3 |
| Support | Stable masks and valid required/peak support |
| Interior mass maximum / RMS × 23.7 m / Uref | 1e-3 / 1e-4, globally and in every compiled region |
| Completed-iterate residual maximum / RMS | 1e-3 / 1e-4, using global RHS maximum/RMS normalization, globally and in every compiled region |

ROI p95, maxima, required points and current/preceding peaks are separate gates;
a favorable p95 cannot hide a failed required point. Nonnegative bilinear
receptor weights allow the ROI's uniform maximum envelope to bound a required
receptor whose entire interpolation support lies inside that ROI.

The mass convention is unchanged: excluded lateral/highest-shell cells remain
excluded, the last solved top band is reported separately, and its inherited
prescribed-face limitation is not qualified by this interior criterion. The
coherent equation residual includes the solved top band. Primitive residual
norms are producer diagnostics, tested independently in S5b; pedestrian sample
archives cannot reconstruct multiplier residuals themselves.

## Calibration and native decisions

The first finite calibration draft required fresh, consistent decay estimates
at three consecutive checkpoints. **None of its twelve parameter combinations
qualified usefully.** Float32 reached its precision floor before the required
sequence completed. The rejected protocol, predictor and trial table remain
in `rejected-fresh-tail-draft/`; no held-out workers had run at that point.

A separately declared second draft reused those same development histories,
without increasing work. It considers safety factors 2/4/8, minimum work
150/200 and ratio caps 0.8/0.9. Selection requires no false acceptance anywhere
in the development histories and useful acceptance on all three development
conditions; minimize mean first-accept iteration, breaking ties conservatively.
The [freeze](data/solver-control-s7/policy-freeze.json), written before held-out
reference workers, selects **safety 8, minimum 150, ratio cap 0.8**.

For positive finite changes and stable support, estimate a remaining vector or
speed-factor tail from both 25- and 100-sweep windows:

```
8 * max(delta25 * q/(1-q), delta100 * q**4/(1-q**4))
```

Use the more conservative observed ratio, require 0.02 <= q < 0.8 and restrict
cross-window ratio disagreement. Changing/unstable modes and plateaued ratios
supply no fresh estimate. A recent trusted **nonzero** uniform bound can be
transported by adding the accumulated maximum measured short-window drift.
The triangle inequality motivates that transport; it does not turn an
empirically calibrated anchor into a universal mathematical error bound.
Transport also uses the uniform maximum as a conservative p95 bound. An anchor
expires after 100 sweeps, a work gap or changing/invalid support. No anchor
means unavailable evidence, never zero error. Current tail availability,
anchor iteration, estimate and reason are recorded separately.

Native `SolverController` requires three consecutive eligible checkpoints,
current required support, fresh global/regional residual and mass safeguards,
and one final deadline check before committing acceptance. It advances with
`FixedSweeps`, so a legacy-tolerance hit cannot prevent policy work. Per-sweep
budget checks remain independent of expensive monitor cadence. No Python
callback runs inside the native mutex or OpenMP workers. Deadline, iteration
limit, invalid support, stagnation and numerical failure remain separate from
acceptance. Stagnation with unavailable estimates does not grant acceptance.

The controller owns bounded scalar policy state/history; the existing monitor
owns its slab and checkpoint rings. It does not retain full-volume checkpoint
fields. Method-aware workspace reuse prevents a subsequent legacy call from
reusing a 1.90 workspace as though it were 1.78. Native regression tests cover
that transition, continuation past legacy tolerance, support failures, expiring
anchors, plateau behavior and deadline precedence at the acceptance commit.

## Held-out results and limitations

All references are independent float64 500/1000/2000 zero-start triples. Both
successive pairs, both heights, every required receptor and every triple's
interior mass diagnostics must pass the unchanged S5 qualification gates.
The 96×80 graded mixed-district control fails the 500-sweep mass RMS gate
(1.064e-4 versus 1e-4). Later iterate agreement is not a replacement for that
gate. There is no budget escalation: release scope is restricted to 80×80×32,
and all four corresponding API control runs remain unassessed/unaccepted.

| Qualified held-out condition | Target sweeps | Initial 3-run median full API cost |
| --- | ---: | ---: |
| 20 staggered buildings, 240° | 225 | 0.127 s |
| 24 courtyard buildings, 315° | 225 | 0.128 s |
| 25 mixed-height buildings, 195° | 225 | 0.128 s |
| Staggered buildings, graded grid, 150° | 250 | 0.140 s |
| Courtyards, 210°, Uref 2 m/s | 225 | 0.128 s |
| Courtyards, 210°, Uref 10 m/s | 225 | 0.127 s |

The initial 43 API workers include three repetitions, seven legacy controls,
short-budget/invalid-support/unsupported/iteration controls and teams 1/2.
After adding implementation/cache identity guards, a separate predeclared
24-worker regression checks the final build, legacy controls and all six
qualified conditions in serial. No method or threshold changes follow the
held-out results. The total remains at the declared **100 workers**.

The audit verifies **34 full-budget held-out acceptances**, plus two accepted
150 ms budget runs; the 50 ms runs are unaccepted and the two 1 ns requests
raise zero-work errors. Every accepted vector/speed/required-point target
passes. Largest accepted ROI vector maximum error is **1.52e-6 Uref**, and
largest p95 is **8.26e-7 Uref**. All recorded predicted bounds also cover their
measured errors. Accepted iteration counts and full returned-field hashes
repeat exactly across repetitions, teams, serial and the provenance-only build
changes.

Final-build API times are 0.128–0.144 s on the six accepted conditions. Its
single legacy control per condition takes 0.299–0.552 s and reaches the
2,000-iteration cap; the 0.552 s mixed-case observation is retained. These are
small-case descriptive comparisons, not a universal latency/speedup guarantee.
API timers include geometry extraction, preparation, native work, finalization
and NumPy conversion; sampling/hash/output are outside that timer. The solve
budget still excludes preparation and necessary final output, as in S4.
S5's disabled-control performance miss remains a separate unresolved finding.

## Provenance, dataset behavior and verification

The frozen native identity is
`d0775583915762bbe2accfcad81d38e21b4c79037ea2dd0fa4c6c7cd5a24fde3`.
CMake hashes the native sources and arithmetic/compiler flags. A changed
implementation/build no longer matches the explicit qualification identity and
falls back unaccepted. `policy_revision`, policy/method, targets, current
assessment and bounded histories travel with the result. Dataset arguments
normalize the policy version and bind the implementation revision into cache
identity; stale implementation requests are rejected. Dataset health records
acceptance **with its assessment scope**, preserves legacy diagnostics and
identifies time-budgeted execution as nondeterministic. It does not present a
pedestrian qualification as whole-volume quality.

The measured initial and final source archives are independently retained:

- Initial: `9f09e014c3150a40e56dc2785d33c614ea4253120539e844d52230b4da6b7c6b`.
- Final: `9fea55965c617631378047467ec9c449f2cfa978a2d59756a1062b8e19e9360c`.

Their production solver kernels, stencils, condition masks and boundary
expressions remain byte-identical to S6/S5. Subsequent usage-docstring edits do
not change the measured implementation. All old stage archives remain intact.

Validation on the final build: **48 OpenMP native tests, 45 serial native tests,
five focused ASan/UBSan checks and 1,076 Python tests passed** (16 Python skips).
The full suite's earlier failures are not concealed: initial S7 dataset-fixture
attempts selected an unsupported padded grid; the corrected test explicitly
accounts for the provider's mandatory halo. Native forbidden-symbol audit
passes. The default 429-case matrix is exact against S5 in serial and teams
1/2/4/8, with twelve revision/team/backend comparisons. Portable default parity
replays per-array hashes and the comparator's documented module/backend
metadata handling; it does not archive every default full-volume array.

Twelve focused audit/legacy-study tests also pass. A fresh-build reproduction
reran 57 workers and reproduced all 24 final API fields/diagnostics exactly,
with the same nine qualified references, failed domain control and zero false
or missed acceptances. Its actual input manifest and results are preserved in
`reproduction/`. The older S5 numerical-study overlay builder still compiles
after including the new study-only JSON header dependency.

## Replay and reproduce

No build or original `build/` directory is needed for the portable audit:

```sh
.venv/bin/python docs/data/solver-control-s7/audit_solver_policy.py \
  docs/data/solver-control-s7
```

Rebuild both backends and rerun the frozen 57-worker reference/calibration/final
API matrix in one command, in a fresh destination:

```sh
.venv/bin/python docs/data/solver-control-s7/reproduce_solver_policy.py \
  --evidence docs/data/solver-control-s7 \
  --output build/solver-policy-reproduction
```

The command verifies source/input hashes, runs native tests, replays the frozen
calibration choice, rechecks the failed domain reference without extending it,
and compares final fields and diagnostics against the archived final build.
On unqualified arithmetic builds, adaptive output remains unaccepted; that is
not a passing reproduction of this qualified release scope.

S8 should now measure preparation/reuse on the qualified scope before adding a
multi-direction API. Broader grids/morphologies/builds require a new qualified
policy scope and unseen validation. Comfort sensitivity remains conditional on
credible directional numerical estimates and separate model/climate inputs;
S9 still owns release packaging and explicit overall task closure.

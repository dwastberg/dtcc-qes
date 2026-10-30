# Finest-reference attempt and runtime correction

**Status: stopped for runtime review.** The proposed hours-long fixed-sweep
reference conflicts with the tool's purpose: fast approximate urban-wind and
pedestrian-comfort analysis. Both validation processes have stopped. No new
accepted finest reference exists; its dependent comparisons remain withheld.
The original frozen protocol below records the attempted study, not the current
next action. The revised plan prioritizes bounded production-runtime/accuracy
assessment and forbids continuing this iteration-budget escalation.

## Frozen protocol

Execute exactly one OpenMP float64 solver case using the existing regular
triple worker mode at 40,000 / 80,000 / 160,000 independent zero-start sweeps.
Retain the previous failed finest certification and charge all additional work
separately. No adaptive budget expansion is authorized by this protocol.

Reuse the preceding vertical-refinement manifest's exact 368-layer split-4
operands, 160 m square extent, 0.5 m horizontal cells, tower geometry, 270 degree
wind, 5 m/s reference at 10 m, production model flags and 1.5/1.75 m sampling.
Freeze the worker, numerical sources, stdin, references and protocol before
execution. The worker clears lambda and RHS on every solve and rebuilds the
velocity from the original initialization. Its base-N guard permits 40,000;
regular triple mode executes the three budgets without a kernel change.

The 37,683,200 physical cells exceed the 20-million soft target intentionally.
Retain the explicit 40-million allocation guard for this bounded experiment;
it is not a public hard cell limit. One worker uses two OpenMP threads. Record
estimated memory, observed peak RSS and all preparation/solve/residual/sampling
costs. Shared-host elapsed timings cannot establish speedups.

Require scaled maximum divergence <= 1e-3 and RMS <= 1e-4 at ALL three
checkpoints (L=23.7 m, Uref=5 m/s). Require maximum vector change/Uref <= 1e-3
and p95 <= 5e-4 at BOTH successive checkpoint pairs at BOTH heights, with
unchanged valid support. A good final checkpoint alone cannot certify a run.
If the bounded triple fails, withhold every dependent spatial comparison and
review error/cost before any further expansion; do not loosen thresholds.

Once accepted, reopen base-to-finest, middle-to-finest and alignment-to-finest
comparisons. Retain accepted base-to-middle and alignment-to-base failures.
Use the preceding study's unchanged full and away-from-wall regions, common
lattice, union of both historical critical sets, and all five mandatory
locations at both heights: (27,21), (21,23), (51,35), (15,47), (15,29).
The first three are outside the away4m region; the last two belong to both.
Require p95 absolute delta K < .05, peak relative change < 5%, and each critical
and mandatory point < 5% relative to the second run when its K >= .1, otherwise
absolute delta K < .05, with valid support and no solid/fluid transitions.

Archive the complete native triple atomically, with execution/input/source
identity and distinct checkpoint budgets. Independently reproduce every
acceptance/comparison from frozen analysis sources without the executable.
Check that native faces, roofs, initial fields and support match the historical
finest zero starts. Preserve source-driven non-monotonic initialization evidence;
do not assume convergence order or use an unexamined Richardson extrapolation.
This single case cannot qualify pedestrian comfort, select an automatic preset,
or justify changing model branches, numerical kernels or public sampling.


## What went wrong

The worker forced 40,000, 80,000 and 160,000 independent sweeps: **280,000 total
sweeps on 37,683,200 cells**, or 10.551 trillion planned cell-sweeps per complete
attempt. It intentionally bypassed normal early stopping. Subdividing every
vertical layer also multiplied work throughout the upper domain. This approach
was unsuitable as the next step toward a fast approximation tool. Labeling it
an offline validation study does not justify open-ended solve costs.

The first execution session disappeared without a saved triple or matching
native crash report. Its cause is undetermined. A detached retry preserved its
supervisor across subsequent host sleep. That retry was then explicitly stopped
following the user's runtime clarification. No completed checkpoint data were
saved by either attempt, so neither receives a numerical acceptance decision.
All original failed certifications and source-driven initialization evidence
remain unchanged. Do not treat either lost or stopped work as zero-cost work.
The archived observations establish at least 32,072 CPU-seconds across both
attempts; exact iteration counts, final fields and total cell-sweeps are unknown.
The cost archive retains broad bounds and the original observations.

## Grid planning is already fast

The generator selects layers from geometry constraints without running the wind
solver. Warm timings, excluding imports and creation of City objects:

| Operation | Typical measured time |
| --- | ---: |
| Generate layers, 4 building heights | 0.33 ms |
| Generate layers, 100,000 heights (four repeated height values) | 0.61 ms |
| Full preview, 4 buildings | 0.79 ms |
| Full preview, 1,000 buildings | 66.7 ms |
| Historical native preparation, 37.68 million cells | 1.47 s |

The first four operations select layers, extract/check geometry or construct
coordinate metadata. They do not allocate full-volume wind arrays. Native
preparation includes array allocation, wind-profile/parameterization
initialization and solver workspace. It is a separate cost. A roughly 0.1 s
planning target is reasonable for representative inputs; large-city geometry
extraction must be measured separately. These small synthetic tests are not
universal hardware or large-city guarantees.

## Bounded normal API measurements

Each case had a strict 30 s subprocess deadline. The installed Python extension
reports **serial CPU / Release / Apple Clang 17**. It is separate from the
historical study's two-thread OpenMP executable. Both cases use the actual
92-layer generator, 0.5 m x/y, 160 m extent, 9,420,800 cells, tower/270 degrees,
normal tolerance 1e-5 and normal maximum 500 iterations, with early stopping
enabled. API time includes normal preparation, solving, diagnostics and output
construction, excluding imports and City creation.

| Precision | API time | Iterations | Converged | Max divergence | RMS divergence |
| --- | ---: | ---: | --- | ---: | ---: |
| float32 | 28.00 s | 500 | No | 0.044099 s^-1 | 0.0024222 s^-1 |
| float64 | 26.13 s | 500 | No | 0.044066 s^-1 | 0.0024216 s^-1 |

This establishes a practical timing baseline, not accepted wind-comfort
accuracy. Both hit their iteration limit and emit the nonconvergence warning.
Precision alone does not cure the short-budget convergence deficit. No timing
speedup follows from one repetition, and no field is qualified by finishing
quickly. The longer reference attempts also encountered host sleep; their
elapsed measurements are unsuitable for performance comparisons.

## Revised next step

Profile the actual production path under an explicit practical budget. Check
the existing Release OpenMP build option and record actual threads, hardware,
cell count and phase costs. Benchmark representative grids, including useful
sizes above the soft 20-million target; preserve the user's 40/100-million-cell
hardware guidance. More threads are not a convergence guarantee.

Compare practical-budget pedestrian vectors, speed factors, fixed critical and
local checks, validity and mass-consistency diagnostics with accepted existing
references. Define the product's acceptance scope before those comparisons.
Preserve historical residual criteria and failures; do not loosen them after
seeing results or count a nonconverged short run as an accepted approximation.
Scientific reference certification and product acceptance serve different
purposes and must have explicit, separate contracts.

If adequate practical-budget results cannot be obtained, investigate solver/grid
conditioning and acceleration, including unnecessary upper-domain refinement,
before another expensive matrix. Retain the empirical branch sensitivity as a
separate model issue. Do not silently change the public sampler, model physics
or generator to hide the failure. Full comfort qualification, preset selection
and the finest-dependent comparisons remain pending.

## Reproduction and evidence

These commands audit saved records or run bounded timing diagnostics:

```sh
.venv/bin/python tools/audit_finest_reference.py
.venv/bin/python tools/benchmark_grid_planning.py
.venv/bin/python tools/benchmark_fast_wind.py  # two cases, each capped at 30 s
```

The archive audit needs source files, NumPy and saved data, without the native
executable or installed QES extension. Integrity success means that frozen inputs,
source identities, timing records and the stopped disposition reproduce; it is
not completion or numerical acceptance of the abandoned reference. The original
`run_finest_reference.py` remains a frozen historical study instrument and must
not be resumed as the next step.

[Status](data/finest-reference/status.json),
[frozen manifest](data/finest-reference/manifest.json),
[frozen protocol](data/finest-reference/protocol.md),
[interruption](data/finest-reference/interruption.json),
[explicit stop](data/finest-reference/runtime-review-stop.json),
[cost accounting](data/finest-reference/costs.json),
[planning timings](data/finest-reference/planning-timings.json),
[normal API timings](data/finest-reference/runtime-review.json),
[archive audit](data/finest-reference/audit.json).


## Verification of this review

132 focused validation/tool tests pass. The stopped archive reproduces from
its source distribution with `dtcc_qes` and `dtcc_core` imports blocked and
without a worker executable. Source-artifact checks include the frozen protocol,
inputs, source snapshots, interruption/stop/cost records, both bounded API
measurements and the explicit unqualified disposition. No production solver,
model parameterization, public defaults or sampling behavior changed in this
runtime correction.

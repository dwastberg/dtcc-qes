# Bounded finest vertical reference

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

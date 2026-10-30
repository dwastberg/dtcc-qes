# Bounded vertical refinement and centre alignment

## Protocol frozen before field measurements

This follows the completed [generated-grid pilot](generated-grid-pilot.md).
Measure sensitivity to systematic z refinement and lower-band centre alignment
at fixed x/y=0.5 m, 160 m square extent, tower/270 degrees, requested 64 m top,
original production parameterizations and sensor (5,5), 5 m/s at 10 m. Preserve
both 1.5 and 1.75 m observables, centred component sampling and float64 solver
arithmetic with float32 geometry/output. Existing horizontal failures remain.

The baseline is the accepted actual 92-layer generator output from the pilot.
The three systematic levels are 92, 184 and 368 layers: split EVERY baseline
layer into 1, 2 or 4 equal parts, including the upper tail. These are explicit
study grids derived from one frozen policy. They measure subdivision sensitivity,
not the effects of retuning the generator or changing x/y. Record planned and
native faces, thicknesses, roofs and parent-face accumulation error. Accept
parent-face disagreement <=1e-4 m from float32 accumulation; do not silently
translate the ground or change the requested physical top. Refinement changes
roof voxelization, which must be reported and precludes assuming a smooth
asymptotic order from three levels alone.

Use one additional 92-layer alignment control. Redistribute only the first
eight layers to put the fifth native centre exactly at 1.75 m, preserving every
native face and solver operand above face eight (about 3.49 m). Fit the lower
four layers geometrically with growth <=1.15, followed by four nearly equal
layers and a native rounding correction at the eighth face. Keep fine thickness
<=0.5 m, thin-cell aspect <=8, and support at or above the third physical cell
at both pedestrian heights. The original baseline has 1.5 m at a centre.
Compare analytical logarithmic-profile interpolation on every grid: those
biases isolate interpolation arithmetic. The solved alignment comparison also
changes lower-cell operators and is not a pure interpolation experiment or a
correction to the observed flow. Roof representation is identical for this
control and the baseline.

Use OpenMP with two native threads for the two new refinement levels and the
alignment control. Add a selected serial alignment solve, compared with the
accepted serial baseline and paired OpenMP control. Prior pilot CPU parity is
retained; no new serial validation of the 184/368-layer cases is claimed here.
Full supported-preset decisions require the appropriate later coverage.

Retain the original common lattice, union of both historical families' frozen
critical sets and three near-wall points. Also freeze the observed largest-error
locations (15,47) and (15,29) at BOTH heights before new measurements. Thus five
mandatory locations apply to the full region. In the diagnostic 4 m setback
region, only the two added points belong; the three near-wall points remain
mandatory full-region checks. Record all validity transitions.

Require the established residual/stability gate on three independent zero-start
N/2N/4N checkpoints: scaled max/rms residual <=1e-3/1e-4 at ALL checkpoints;
maximum/p95 vector change divided by Uref <=1e-3/5e-4 on BOTH successive
comparisons, with stable validity. Start N=8000 for each OpenMP case and N=4000
for the selected serial control. Double when necessary, up to N=16000; retain
failed triples and reuse identical already-completed checkpoints. Exhausting
the cap yields a recorded failure and withholds dependent comparisons.

Apply unchanged spatial budgets: p95 absolute delta K <0.05, peak relative
change <5%, each frozen critical and mandatory point <5% relative for reference
K>=0.1 or absolute delta K <0.05 otherwise. Require valid critical/local support
and no validity transitions. Compare base->2, 2->4, base->4, aligned->base and
aligned->4, always using the latter as reference. Report components, vector
changes, low-speed and worst-error locations alongside speed metrics. A
sensitivity-budget pass requires all six full-region subdivision comparisons
(three pairs, two heights); report alignment decisions separately. A pass
establishes these metrics on this fixture, not everywhere-relative 5% accuracy,
a formal convergence order, physical comfort accuracy or a preset.

Use at most two study processes concurrently, with a 20-million soft cell target
and a 40-million allocation ceiling. The refinement cases have 18.84/37.68
million cells, estimated process footprints 3.01/5.94 GB; the 92-layer control
has 9.42 million cells and an estimated 1.55 GB footprint. Maximum simultaneous
estimate for the two refinement workers is 8.95 GB on this 51.5 GB host. Retain
the fine case above the soft target. These worker estimates exclude public
full-volume NumPy output copies. Save memory, unique executed cell-sweeps,
preparation, solve, residual and sampling costs, including rejected work.
Shared-host/sleep-interrupted timing is diagnostic; no speedup claim or policy
choice follows from a single repetition.

Freeze source snapshots, protocol, task matrix, configurations, binary and
reference fingerprints before new fields are available. Keep historical data
immutable; changed source, input or binary requires a new study directory.
Provide manufactured tests, case/request audits and a data-only reproducible
summary. Finish this bounded matrix and review its outcome before expanding
wind/geometry coverage or tuning policy parameters.

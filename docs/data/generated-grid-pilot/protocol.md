# Bounded generated vertical-grid pilot

## Protocol fixed before measurements

This C2c pilot measures the additional vertical-discretization difference at
fixed x/y=0.5 m. It does not qualify horizontal grid independence or physical
comfort accuracy. The [near-wall findings](near-wall-validation.md), failed
full-region horizontal checks and production parameterizations remain unchanged.

Use the actual public `VerticalGrid.auto(pedestrian_height=1.5)` policy with
all other settings at their current defaults, generated separately for the
160 and 240 m square domains. Keep the tower fixture, roofs 7.9/23.7 m, requested
64 m top, world sensor (5,5), 5 m/s at 10 m and 270-degree wind. Require identical
vertical solver operands across the lateral control. Store planned/effective
faces, solver thicknesses, policy/version, roof representation and preview cost.
The policy generates 92 layers here, rather than the 42 layers frozen from the
old 2 m horizontal preview; do not substitute that older family for this test.

Execute both serial and OpenMP CPU backends with the existing opt-in float64
solver, float32 geometry/output and original centred component sampler. Compare
with each backend's accepted uniform-z=0.5 m joint-study references at the same
extent. Evaluate both 1.5 and 1.75 m at the original fixed physical lattice,
the union of BOTH historical vertical families' frozen critical sets, and all
three mandatory near-wall points (27,21), (21,23), (51,35). No new exclusion rule,
spatial averaging, parameter tuning or threshold relaxation is permitted.

Require the established solve gate: scaled maximum/rms residual <=1e-3/1e-4
at all three checkpoints and maximum/p95 vector change divided by Uref
<=1e-3/5e-4 on both successive N/2N/4N comparisons. Every checkpoint starts
from zero. Start N=4000 for serial/160 and N=8000 for the other three cases;
double N when needed, up to 16000. Save rejected triples and unique checkpoints.
An exhausted failed solve withholds its spatial comparisons; do not silently
increase the cap or reuse a previous family's solution.

Apply unchanged spatial budgets: p95 absolute delta K <0.05, relative peak
change <5%, and each frozen critical/local point <5% relative for reference
K>=0.1, otherwise absolute delta K <0.05. Require no validity transitions and
no invalid critical/local support. Include the generated-grid 160-to-240 m
lateral control. Report the 4 m setback region separately as a diagnostic;
its regional decision excludes the three full-region near-wall checks.
A pilot pass requires all six full-region comparisons per backend, matching
CPU decisions, and CPU field differences within the iterative stability budget.
Even a pass cannot qualify a comfort preset or remove the horizontal failures.

Run at most two workers, one per backend, larger extent first. Keep the
20-million-cell target soft: the generated cases have 9,420,800 and 21,196,800
physical cells, versus 13,107,200 and 29,491,200 in the accepted uniform references.
Use a 40-million allocation ceiling and record array estimates and worker RSS.
Report preview, preparation, solve, residual and sampling costs separately,
including rejected/certification work. One shared-host diagnostic repetition
and historical reference timings cannot establish a speedup; three controlled
repetitions and a cheapest-qualifying-uniform comparison remain later work.

Archive the frozen sources, protocol, reference hashes and executable identities
before any new solve. Reuse only identical checkpoint requests. Provide a
saved-data audit that verifies sources, inputs, atomic checkpoint contents,
assembled runs, stability and all comparison decisions without executing binaries.
No production API, solver or generator change is part of this pilot.

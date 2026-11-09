# Surrey background-profile benchmark, version 1

> Historical research protocol/results, retained from `54ccb39`. Reproduction
> commands with research-only build paths describe that revision. The portable
> tools and current integration qualification are documented in
> [REFERENCE_INTEGRATION_RESULTS.md](../docs/REFERENCE_INTEGRATION_RESULTS.md).


This protocol is fixed before running the first baseline. The machine-readable
settings are [surrey_background_v1.json](specifications/surrey_background_v1.json).
The benchmark tests local mean-profile shape and turbulence predictions
conditional on measured horizontal means. It does not reconstruct the roughness
array or predict its downstream adjustment. No model constants are fitted.

## Observations and coordinates

Use the exactly exported `Urban_roughness` summary table from
[the reference audit](SURREY_REFERENCE_AUDIT_RESULTS.md). The compressed source
and original MAT file identities are pinned in the protocol. No MATLAB reader,
network access or raw time-trace reduction is needed to run this benchmark.

The table contains 101 observations: eleven heights at the Suburban reference
station x-hat/l_D=-10, and nine heights at each of ten Urban adjustment stations.
The [paper](https://openresearch.surrey.ac.uk/esploro/outputs/journalArticle/Tall-Building-Clusters-in-Urban-Canopies/991008866202346),
section 2.2 and Figure 5, establishes l_D=70 mm, x-hat=x+735 mm, and the Suburban
reference classification. Preserve original coordinates and add SI coordinates
for both origins. Classify stations 1,2,3,5,6 as developing and 7,8,9,15,20 as
developed, following the Figure 5 grouping. Keep every station individually.

Normalize each row's means by its supplied `Reference_speed` and variances by
its square. Define physical k as half the sum of the three variances, and
directional fractions as each variance divided by their sum. Do not substitute
the nominal 2 m/s for the recorded references. Model runs use nominal 2 m/s;
their dimensionless predictions are compared with these normalized observations.

## Baseline comparisons

1. **Published log-law context.** Evaluate U/Uref=(u_star/Uref)/0.4 times
   log((z-d)/z0), using Table 1 parameters. This is a published fitted profile,
   not an independent prediction or a fit performed in this benchmark. The
   exact original log-fit height window is unknown; report height strata and
   do not treat departures throughout the boundary layer as fit failures.
2. **Current public log-profile baseline.** Run one Suburban and one Urban
   `LogProfile`, with the published z0 and a speed at 240 mm calculated from
   the published log law. The current shifted log profile has no displacement
   parameter. Report its differences without compensating z0, shifting the
   floor, or fitting the anchor to these observations. The developing Urban
   stations are context comparisons, not equilibrium-profile validation.
3. **Measured-mean turbulence diagnostic.** Run one `MeasuredProfile` per
   station, prescribing U/Uref and V/Uref times nominal 2 m/s. Use log-height
   interpolation, a declared log lower tail and constant upper tail. Prescribed
   U/V agreement is a numerical/profile-interpolation check, not independent
   mean-flow accuracy. W cannot be prescribed; its measured values are retained
   and W=0 is reported as a model restriction. Measured variances and k are
   never supplied to the model. No experimental incoming-energy arm is enabled.

Run both native comparisons with the current default height mixing length and
legacy covariance, on vertical spacings 10 and 5 mm below 1 m. This gives 26
small native solves: (2 log controls + 11 measured-mean controls) times 2 grids.
Keep horizontal extent 320 mm and spacing 40 mm fixed. Use an empty flat domain;
the source station coordinate labels identify local profiles, not query points
in a resolved roughness geometry. These controls cannot predict fetch evolution.

The current turbulence domain planner requires a 15 m rotation-reference
height even at wind-tunnel scale. Preserve the experimental metre units and
extend the numerical domain to 16 m using graded upper layers above 1 m.
Only 40–750 mm is scored. Measured means are held constant above 750 mm;
the selected rotation direction therefore comes from that unmeasured tail.
Record this restriction, reference/cap values and rotation diagnostics. Do not
interpret the extended domain as the experimental tunnel or as a physical
full-scale mapping. This is a conditional closure diagnostic, not a complete
boundary-layer simulation.

## Metrics and evidence

Report counts, missing/invalid counts, bias, MAE and RMSE of U/Uref, V/Uref,
W/Uref, each variance/Uref², physical k/Uref² and the three energy fractions.
Report the ratio of summed predicted to measured k. Summarize Suburban,
developing Urban and developed Urban separately; provide every station and
height too. Split heights at 3 times the relevant roughness-element height
(60 mm Suburban, 210 mm Urban) as a diagnostic of canopy proximity, not a
claimed universal log-law region.

Strict turbulence metrics require every source covariance contributor to be
valid on the complete fixed observation population. Missing or invalid points
make a score incomplete; never drop them to improve a score. Retain explicitly
labelled raw diagonal diagnostics as well. Report QES internal `tke` separately
from half the final stress trace; only the latter is compared as physical k.
Report paired grid changes on identical IDs. Two grids quantify sensitivity;
they do not establish asymptotic convergence or grid independence.

Execution guards cover source identity, observation identity/coverage, solver
convergence, finite supported samples, interior divergence and preservation of
the prescribed mean profile at native centres. Covariance validity is reported
as a finding, not repaired or made a prerequisite for retaining a failed result.
No physical pass threshold is invented. The paper's generic measurement errors
are not a complete pointwise uncertainty model. Numerical guards do not confer
physical or pedestrian acceptance.

Archive observations, per-observation predictions, metrics, profile plots,
native centre-column fields and sample support, complete run metadata/timings,
source/native/environment identities and checksums. Preserve the previous
campaign archives. Reserve a separate dataset for future confirmation.

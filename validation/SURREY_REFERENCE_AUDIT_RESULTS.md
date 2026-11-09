# Surrey reference data and eligibility audit

> Historical research protocol/results, retained from `54ccb39`. Reproduction
> commands with research-only build paths describe that revision. The portable
> tools and current integration qualification are documented in
> [REFERENCE_INTEGRATION_RESULTS.md](../docs/REFERENCE_INTEGRATION_RESULTS.md).


2026-11-09. **The acquired Surrey MATLAB tables are now readable and their
numeric exports are structurally checked. They do not qualify the planned
pedestrian retained-energy experiment.** Wake-component height coverage and
measurement reduction provenance remain insufficient. This is an assessment
of the acquired public files, not a claim that suitable reference data cannot
be obtained elsewhere.

**Correction after reviewing the general modelling uses:** the original audit
incorrectly said that a suburban three-component reference was absent.
`Urban_roughness` includes the upstream Suburban reference identified in the
paper's Figure 5, as well as the Urban roughness-adjustment profiles. All have
three means and three variances. Condition matching to the cluster inlet still
needs investigation; the wake-height limitation above is unchanged. The frozen
original report is retained as historical evidence; the audit tool now records
the corrected station inventory.

## Origin and intended use

The data come from the University of Surrey's EnFlo wind tunnel and accompany
Mishra, Bi, Carpentieri, Barlow, Robins and Placidi's 2025 paper,
[Tall Building Clusters in Urban Canopies](https://openresearch.surrey.ac.uk/esploro/outputs/journalArticle/Tall-Building-Clusters-in-Urban-Canopies/991008866202346).
The public [OSF dataset](https://doi.org/10.17605/OSF.IO/5X7WV) supplies
`Data_SemiUrban.mat`, `Data_Urban.mat`, `Data_TimeTrace.mat` and `Readme.pdf`.
The study uses a 4×4 cluster of 60 mm square, 240 mm high buildings and two
surrounding roughness conditions. The file label `SemiUrban` corresponds to
the paper's suburban condition.

The intended wind-development uses are:

| Product | Information | Intended question |
| --- | --- | --- |
| `Urban_roughness` | Mean U/V/W and all three variances in a Suburban reference and ten Urban adjustment profiles | How do background energy and component structure change with roughness and fetch? |
| `*_4x4_lat` | Wake U and lateral momentum flux uv | Is sheltering and lateral wake structure predicted correctly? |
| `*_4x4_longitudinal` | Wake U and W along downstream stations | Is wake recovery and vertical motion predicted correctly? |
| `*_4x4_timetrace` plus coordinate tables | Time, instantaneous U/V/W and sample positions | What are component variances, covariances and k after the flow interacts with buildings? |

The retained-energy question is whether incoming turbulent energy survives
through an interacting-building flow, and how additional local production is
distributed between directions. It needs measured inflow and wake statistics
independent of the AIJ development cases. Concentration fields are included in
the public files but are outside this wind audit. Using Surrey to select a
closure would make it development evidence; a separate confirmation dataset
must remain untouched.

## What was decoded and verified

All four original file SHA256 values still match the initial acquisition
manifest, as does the accepted manuscript PDF. The isolated reader is
[mat-io](https://github.com/foreverallama/matio) version 1.0.2; it is installed
under a build directory without changing production dependencies or requiring
MATLAB. It decodes the MCOS objects that SciPy exposed as opaque tables.

The export contains **11 summary/coordinate tables and 13 three-component time
traces, comprising 645,136 time samples**. Table dimensions, column names and
numeric columns are checked against the decoded raw MCOS properties. All CSV
and NPZ exports round-trip exactly. Top-level variable names match the original
SciPy MAT-file inventory, and each condition's number of coordinate rows equals
its number of trace cells.

The author readme establishes mm coordinates, m/s velocities and the named
component conventions. Exports retain those original columns and units; trace
coordinates are additionally reported in metres. No full-scale pedestrian
mapping or roughness-coordinate offset is silently applied. The upstream
lateral tables actually contain `Y_mm`, `Z_mm`, `U_mean`, differing from the
readme's listed upstream names; the exports use the actual file schema.

Structural checks establish a usable numeric export. They do not independently
validate the measurement processing or reproduce an author-approved MATLAB
reduction.

## Why the required height coverage fails

| Wake time-trace condition | Locations | Actual height | Height/building height |
| --- | ---: | ---: | ---: |
| Suburban (`SemiUrban`) | 6 | 60 mm | 0.25 |
| Urban | 7 | 120 mm | 0.50 |

Each condition supplies one three-component wake height. The lateral and
longitudinal mean-velocity surveys are at 120 mm. The roughness-only flow has
multiheight vector/variance profiles, but these are not the cluster wake.
The concentration tables also have multiple heights; concentration observations
cannot supply missing velocity variances.
The three-component traces lie on or within 0.003 mm of the wake centreline;
they describe downstream development at that height, rather than a lateral
covariance map across streets and passages.

Thus the acquired files do not supply near-ground plus two elevated levels of
matched wake component statistics. Mixing the two roughness conditions as if
they were vertical levels of one flow would be invalid. Arbitrarily rescaling
one height to 2 m would still leave the required higher wake levels absent.

## Statistical reduction remains unqualified

All thirteen decoded traces have finite U/V/W values and strictly increasing
time. Their durations are approximately 118.9 s in the suburban case and
58.9–59.2 s in the urban case. The paper describes 3D LDA and nominal acquisition
conditions, but the files do not document residence/transit-time weighting or
the resampling history of the supplied series.

The audit reports two explicitly descriptive reductions: unweighted population
moments and trapezoidal node-weighted moments. Their maximum mean difference
is 6.95e-6 m/s and their maximum relative component-variance difference is
0.0412%. Small sensitivity to these two choices does not establish correct
LDA residence-time weighting.

Seven urban traces have matching coordinates in the supplied longitudinal
summary, within 0.005 mm and at the same 120 mm height. Simple trace U means
differ from those summary means by approximately 0.054–1.932%. The matched W
means also differ. The suburban traces and longitudinal summaries are at
different heights and are not compared as equivalent measurements.

The differences do not prove measurement error: the files may describe distinct
acquisitions or differently processed records. They do mean that we cannot
claim to reproduce the supplied reduction without additional provenance. No
weighting or calibration was fitted to force agreement.

## Eligibility decision

| Criterion | Decision | Remaining evidence |
| --- | --- | --- |
| Independent physical experiment | Pass | EnFlo measurements are independent of AIJ |
| Geometry and roughness reconstruction | Partial | Dimensions documented; roughness layout and coordinate-origin mapping need explicit reconstruction |
| Mean inflow and three variances | Partial | Suburban reference and Urban adjustment profiles exist with three variances; correspondence to cluster inlet/acquisition is unresolved |
| Pedestrian and two higher wake levels | Fail | One component time-trace height per condition |
| Wake mean vectors and three variances | Partial | Components are readable; reductions need qualification |
| Instrument, averaging and uncertainty | Fail for admission | Generic paper uncertainties exist; weighting/resampling and acquisition mapping are unresolved |
| Normalization and physical scale | Partial | Units and freestream reference are known; eligible full-scale mapping is not frozen |
| Readable, quality-checked data | Partial | Structural export passes; physical/statistical reduction remains unqualified |

Surrey can support scoped development on background profiles, roughness
adjustment, elevated wake means and component organization. It cannot open the
frozen retained-energy factorial under the existing acceptance requirements.

The concrete missing items are matched near-ground and elevated component
measurements, verified matching of the available incoming component profiles, the documented
LDA reduction/resampling convention, and trace-to-summary acquisition mapping.
A complete geometric/roughness reconstruction is also needed before modelling.

## General wind and turbulence modelling uses

The dataset has broader value than its eligibility for the pedestrian campaign.
The following are recommended development uses, not completed validation runs.

1. **Background mean and turbulence profiles.** `Urban_roughness` has 101 rows:
   an 11-height Suburban reference at approximately -700 mm and ten nine-height
   Urban adjustment profiles. The paper uses a roughness-origin coordinate
   here: `X_mm` is interpreted as x-hat, with x-hat = x + 735 mm and l_D = 70 mm.
   The Suburban station is x-hat/l_D = -10; the others are 1, 2, 3, 5, 6, 7, 8,
   9, 15 and 20. The Suburban heights span 40–750 mm; the downstream heights
   span 90–750 mm. All supplied variances are finite and positive. These
   author-provided summaries support k = (U_variance + V_variance +
   W_variance)/2, normalized variance profiles and directional energy fractions.
   They can challenge our friction-velocity, mixing-length and component-energy
   assumptions without first reducing raw wake traces. The three variances
   alone do not supply a full covariance tensor or an energy-transport budget.

   Profile presence does not resolve acquisition matching. At z=120 mm, the
   Suburban reference has U=1.1929 m/s, while the centre of the supplied
   `SemiUrban_Upstream_lat` table has U=1.2934 m/s, a 7.77% difference relative
   to the latter. This is a diagnostic discrepancy, not a correction factor or
   evidence of measurement error. Origins, fetch, acquisition and normalization
   must be reconciled before treating either as the cluster inlet.

2. **Cluster mean-flow structure and recovery.** The lateral surveys contain
   278 Urban and 290 Suburban U observations at z=120 mm (= half the tall
   building height). Longitudinal tables supply 7 Urban and 9 Suburban U/W
   observations at the same height. Useful targets are wake deficit and width,
   channel acceleration, centreline recovery and vertical motion. The two
   roughness cases also test whether model responses to surrounding low-rise
   geometry are physically credible. Start with the supplied summary means;
   uncertainty about reducing the raw traces need not block all mean-flow work.

3. **Lateral momentum exchange.** The lateral surveys include uv covariance.
   After confirming sign and normalization, compare covariance sign, peaks and
   lateral shape alongside U. A suitably supported lateral derivative permits
   the partial production term -uv*dU/dy. This is not total turbulent production:
   the other covariance/gradient contributions are unavailable from that survey.
   It can test the stress–strain relationship, but cannot uniquely identify a
   complete closure or a transport length scale.

4. **Wake component energy and covariance.** The thirteen three-component
   traces can support k, directional fractions and off-diagonal covariances
   once their reduction is qualified. These are valuable tests of whether a
   change improves measured turbulence, beyond producing a valid stress tensor.
   Each condition has one trace height, and the two conditions use different
   heights, so their differences cannot be attributed to roughness alone.
   Spectra, integral times and gust statistics are lower priority while LDA
   weighting/resampling provenance is unresolved; the steady solver does not
   predict instantaneous gust histories.

The recommended first benchmark is a separately scoped background-profile
case, followed by cluster mean-wake comparisons and then covariance tests.
Freeze coordinate transforms, geometry, acquisition matching, normalization
and comparison metrics before running models. The current profile API takes
horizontal mean velocities and a scalar roughness length; it does not ingest
measured three-component turbulent inflow. Representing the roughness step
also needs an explicit geometry/roughness decision. The profiles can initially
be validation targets without implying that the current model can transport
their measured energy downstream. A successful Surrey development result
would still need separate confirmation and the existing pedestrian criteria.

The [background-profile benchmark](SURREY_BACKGROUND_RESULTS.md) is now built
and its first 26-run baseline is complete. It uses the supplied profile
summaries for local mean-profile and conditional turbulence comparisons;
the pedestrian eligibility decision above is unchanged.

The [Hamburg catalogue](https://www.mi.uni-hamburg.de/en/arbeitsgruppen/windkanallabor/data-sets.html)
was rechecked on 2026-11-09. It describes password-protected measurement archives
and requests contacting the laboratory for access; the COST ES1006 Michelstadt
collection also requires a signed data policy. No contact was sent, no policy
was signed and no reserved confirmation measurements were inspected. Access
and qualification are concrete next dependencies, not an eligible reference
already available to the model.

## Evidence and reproducibility

The [evidence index](../docs/data/next-pedestrian-campaign/stress-reference-audit/README.md)
contains the audit report, numeric exports, table/reader/source checksums,
current catalogue evidence and test results. Raw source downloads remain under
`build/reference-intake/`, with original identities preserved.
The [audit tool](audit_surrey_reference.py) requires the isolated optional reader.
Its final run passes with warnings treated as errors, while explicitly recording
one known third-party pandas-option import deprecation. Earlier audit logs are
retained. No wind solver, new retained-energy model or physical coefficient
was introduced.

The corrected station inventory was checked in the data-only follow-up
`validation/output/next-pedestrian-campaign/reference-audit-004/`. All eleven
summary/coordinate CSV exports match the frozen original exports exactly.
The six targeted reference-audit tests pass with warnings treated as errors,
including regression checks that the Urban-named table contains the Suburban
reference and that downstream profiles alone do not imply its presence. The
original archived audit and replay evidence have not been rewritten.

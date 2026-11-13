# Pedestrian wind comfort Dataset implementation plan

## Status and scope

**Implementation is on hold until dtcc-core provides the historical weather
data described below.** This document records the design to implement once that
dependency is available. It does not authorize or schedule changes to dtcc-core;
the core developers own that work and the final weather API.

Create `QESWindComfortDataset`, registered as `datasets.qes_wind_comfort`, with
an associated `QESWindComfortArgs` model. It will build on the geometry and
simulation pipeline of `QESWindDataset`, fetch the wind climate through
`dtcc_core.datasets.weather`, run the required wind directions, and return a
georeferenced comfort map with safety, validity, and provenance information.

The user supplies an assessment area and can make a few understandable choices.
The Dataset handles weather selection, reference conversion, domain preparation,
directional simulations, pedestrian sampling, classification, and presentation.
The initial geographic scope follows the existing QES Dataset: EPSG:3006 and
Swedish city/weather sources. Terrain remains flattened as in QESWindDataset.

## Agreed decisions

- Support every currently implemented built-in criterion: NEN 8100 and City of
  London Lawson (2019). Use the existing `comfort.Criterion` definitions and
  classification routines rather than copying threshold tables.
- Default to NEN 8100. Select evaluation height, turbulence requirements, and
  seasonal aggregation from the criterion.
- Use the constant `comfort.SCREENING_PEAK_FACTOR = 3.0` for gust screening.
  Users do not need to choose a peak factor in the Dataset API.
- Document this assumption in source code and result metadata. Estimating a
  dynamic factor is future work.
- Keep historical weather acquisition in dtcc-core. Do not add a separate SMHI
  downloader or a synthetic-weather fallback in dtcc-qes.
- Wait for historical weather support before starting Dataset implementation.

## Proposed user API

The following examples describe the intended interface; it is not available yet.

```python
import dtcc_qes  # Registers the optional QES datasets.
from dtcc_core import datasets

result = datasets.qes_wind_comfort(
    bounds=[319720, 6397660, 320720, 6398660],
)
result.plot(field_name="comfort")

london = datasets.qes_wind_comfort(
    bounds=[319720, 6397660, 320720, 6398660],
    criterion="city_of_london",
    years=(2016, 2025),
)
```

| Parameter | Proposed default | Meaning |
| --- | --- | --- |
| `bounds` | Required | Assessment area in EPSG:3006; preserve Bounds-object handling and document four/six-coordinate semantics consistently with QESWindDataset. |
| `source` | `"LM"` | Building source, with `"OSM"` as the existing alternative. |
| `resolution` | `2.0` m | Horizontal solver spacing; finer spacing increases cost. |
| `criterion` | `"nen8100"` | Also accept `"city_of_london"`. |
| `years` | Latest ten complete calendar years | Inclusive first/last years; resolve the default to explicit dates in provenance and cache identity. |
| `station_id` | Automatic | Optional selection of a known representative station; it must still pass data checks. |
| `exposure` | `"open"` | Documented terrain category for upstream exposure outside explicitly modelled buildings. |

Retain applicable DatasetBaseArgs controls such as `strict_live`. Reject
irrelevant single-condition arguments such as `speed`, `direction`, or `profile`.
Do not inherit the entire QESWindArgs interface. Building filtering, footprint
cleaning, direction count, reference speed, grid construction, padding, solver
controls, and display sampling are internal policies with recorded values.
Specialist peak-factor overrides remain available through the existing low-level
comfort helpers.

Exposure categories must map to explicit, versioned roughness assumptions.
The proposed `"open"` default is an assumption users can review, not an inference
that every site has open surroundings. Final category values and the treatment
of unknown station exposure must be settled before release.

## Required historical-weather support from dtcc-core

The current local WeatherDataset accepts only `period="latest-hour"`. A snapshot
cannot supply the multi-year wind climate needed for this Dataset. The core
extension must preserve existing snapshot behavior and add historical station
records. Suggested calling syntax, subject to agreement with core developers:

```python
weather = datasets.weather(
    bounds=station_search_bounds,
    parameters=["wind_speed", "wind_direction"],
    period="historical",
    start="2016-01-01T00:00:00Z",
    end="2026-01-01T00:00:00Z",  # Exclusive.
    station_ids=None,           # Optional explicit selection.
)
```

Required capabilities and data contract:

1. Discover candidate stations by area and parameter availability, including
   historical/inactive stations. Supply station IDs, coordinates/CRS, names,
   operating periods, and available record coverage. Discovery should not
   require downloading the complete archive for every nearby station.
2. Fetch multi-year speed and direction observations for a station and explicit
   date interval. Provide timestamps normalized to UTC, units, observation
   interval, and actual averaging duration for each parameter. Preserve native
   sampling semantics: observations reported hourly are not necessarily hourly
   means, and must not be relabelled as such.
3. Preserve missing values, quality flags and their meanings, duplicate/revision
   information, and requested versus actual coverage. Distinguish a failed
   upstream request from a successfully retrieved record containing gaps.
4. Supply measurement height above ground separately from station elevation.
   Include exposure/roughness metadata and relocation or instrument changes
   where known; explicitly represent unknown metadata.
5. Return source provenance, retrieval time, source terms, and stable data
   identity/checksum suitable for caching and reproducible downstream results.
6. Support strict failure reporting and cached historical retrievals. If archive
   segments overlap, define deterministic revision precedence and deduplication.

Timestamped fields in a SensorCollection are suitable if consistent with core's
time-series model. Agree on array layout, time association, metadata names, and
error behavior with core developers before writing the adapter. A snapshot
SensorCollection containing one value per station is insufficient.

Optional future inputs are gust observations and turbulence variance with their
measurement durations. They are not required for the initial constant-factor
implementation and do not directly determine local pedestrian peak factors.

The dependency is ready when an installable dtcc-core version exposes this
contract and can retrieve a representative multi-year paired wind record.
Update the QES dependency and adapter against that actual API, rather than
assuming the proposed keyword names have been implemented.

## Processing pipeline

### 1. Resolve and validate the request and weather

Resolve the criterion, years, exposure, and internal policy version first.
Search outside the small assessment bounds for weather stations using a bounded,
documented search distance. Check paired speed/direction availability, duration,
quality, and seasonal coverage; rank eligible stations by distance. Record the
selected station, distance, rejected candidates, and selection rationale.
Nearest does not guarantee representative exposure, hence the station override.

Use one station consistently. Do not combine unrelated stations or stitch
relocations silently. Align speed/direction on timestamps, apply the agreed
quality policy, deduplicate, retain calm hours, and count excluded observations.
Require adequate coverage in each year and season; finalize numerical coverage
limits against core's delivered records and document them as a versioned policy.
Do not silently shorten a requested interval when data are inadequate.

Fail before expensive simulation if no suitable station or historical capability
exists. Unknown measurement height must not be replaced with station elevation.
Any assumed station height/exposure needs an explicit documented policy and
visible provenance; if a defensible reference cannot be established, fail.

Convert the station wind climate to the simulation reference height and upstream
roughness through `comfort.log_law_transfer`, with explicit standard/shifted log
law conventions. Record station/site references, blending height, assumptions,
and the first-order neutral-flow limitations. Check averaging-duration
compatibility with the selected criterion; flag an approximation explicitly or
reject incompatible data rather than claiming exact criterion compliance.

### 2. Fetch and prepare geometry once

Share city fetching/conditioning and provenance helpers with QESWindDataset,
including canonical footprints, height handling, terrain flattening, courtyard
policy, and fallback diagnostics. Preserve existing qes_wind behavior with
regression checks; compose reusable helpers instead of inheriting all arguments.

Treat requested bounds as the output area. Fetch surrounding buildings in a
buffer, plan a larger simulation domain, and crop results back to the requested
area. Derive the buffer and vertical clearance from relevant building heights
and spacing; a preliminary geometry fetch may be needed to size the final fetch.
Check buffer/domain sensitivity before fixing the policy.

Create explicit vertical layers with a cell centre at the criterion height:
1.75 m for NEN 8100 and 1.5 m for City of London. Avoid nearest sampling at an
unintended height. Existing automatic grids are experimental; do not describe
them as a qualified comfort preset without verification.

### 3. Solve the directional sweep

Use a provisional default of 16 evenly spaced meteorological directions over
360 degrees, including all sectors regardless of their observed frequency.
Compare against 32 directions and refine the default if class maps are sensitive,
especially for seasonal City of London results. Direction count is an internal
accuracy choice, not an ordinary user parameter.

Use one positive reference speed (initially 5 m/s at 10 m) with a consistent
logarithmic inflow reference across directions. Prepare the model once through
the existing reusable wind preparation path and run each direction sequentially.
Sample each result immediately and release its full volume; retain only the
pedestrian plane, validity, required turbulence, references, and diagnostics.

For City of London enable QES-Turb and retain streamwise standard deviations and
stress validity. NEN 8100 requires mean speed only. Apply a documented solver
failure/acceptance policy; an unsuccessful direction must not be dropped and the
remaining directions reweighted. Numerical acceptance does not establish model
accuracy or gust qualification. Record progress and enforce a memory guard.

### 4. Assess comfort and safety

Reuse `comfort.assess` on aligned directional planes and the reference-matched
climate. Maintain meteorological FROM directions and existing nearest-sector
assignment. Keep geometry masks, unsupported samples, and invalid stress as
invalid values throughout; never replace missing data with zero wind.

| Criterion | Evaluation height | Assessment |
| --- | --- | --- |
| NEN 8100 | 1.75 m AGL | Mean-speed comfort A–E, separate danger classes, and sitting/strolling/traversing suitability. |
| City of London Lawson (2019) | 1.5 m AGL | Separate mean/GEM assessment using the worse class, seasonal comfort and worst-season summary, annual safety. |

For City of London compute:

```text
estimated_gust = mean_speed + SCREENING_PEAK_FACTOR * streamwise_std
gust_equivalent_mean = estimated_gust / 1.85
SCREENING_PEAK_FACTOR = 3.0
```

The constant applies across all locations and directions. It is a pragmatic,
uncalibrated QES screening assumption, not a peak factor prescribed by the
guideline. QES mean/stress output currently has no established averaging
duration; record that as unspecified. The separate divisor 1.85 is the existing
City of London GEM conversion. Preserve the unvalidated-gust warning and record
the constant, basis, arithmetic version, and validity policy in GEM provenance.
The source commentary already lives beside `SCREENING_PEAK_FACTOR` in
`src/dtcc_qes/comfort.py`.

Do not duplicate criterion thresholds or weaken their boundary behavior. Support
both built-ins through a mapping to the existing Criterion objects; custom
criteria remain available through the low-level API.

### 5. Return and present the map

Return a DTCC FieldSlice with georeferenced pedestrian samples and fields for
`comfort`, `safety`, `valid`, criterion threshold exceedance probabilities, and
activity suitability where defined. Include seasonal comfort fields for City
of London. Derive labels and units from the criterion; use -1 for unassessed
classes and NaN for unassessed probabilities, consistently with ComfortResult.

Keep the computational map at solver sampling density. Presentation may reduce
display density, but must not interpolate categorical classes or change the
assessment. Provide categorical colours/legends, visibly unassessed cells, a
weather coverage summary, and a wind rose. Verify FieldSlice plotting/export
can retain these fields rather than assuming wind-vector adapters already do.

Attach DatasetContext with geometry and weather upstream contexts, requested and
resolved arguments, actual climate period, station/reference metadata, quality
and missing-data counts, preparation policies, per-direction diagnostics,
requested/actual sample heights, qualification, timings, and all warnings.
Results remain QES screening output, consistent with the existing comfort guide.

## Caching and reproducibility

Keep weather caching in core. Cache directional pedestrian planes independently
from the climate assessment so a changed station or year range can reuse solves
when geometry, inflow reference, and numerical settings match. Changing exposure
can change that reference and must invalidate the appropriate simulation cache.

Simulation identity includes geometry/source identity, domain/grid, profile
reference, directions, solver/turbulence settings and arithmetic versions,
sampling height/method, and policy version. Assessment identity additionally
includes weather identity and quality policy, transfer assumptions, criterion,
and peak factor. Cache actual diagnostics and never disguise time-budgeted work
as deterministic. Do not cache transient upstream failures as successful maps.

## Implementation sequence after the weather dependency is ready

1. Confirm the released core API and add a narrow weather adapter with recorded
   fixtures. Finalize station metadata, exposure, and coverage policies.
2. Extract shared QES Dataset preparation helpers and verify existing Dataset
   behavior. Add buffered assessment-domain preparation.
3. Add QESWindComfortArgs, descriptor registration/discovery, criterion mapping,
   explicit grid policy, and directional preparation reuse.
4. Add weather reference transfer and both comfort assessments with the constant
   peak-factor policy and full provenance.
5. Add the FieldSlice product, categorical presentation/export, caching, and a
   user example requiring only bounds for the default case.
6. Run integration and sensitivity checks, finalize/version defaults, and update
   user documentation and dependency requirements.

## Verification and completion criteria

- Test weather alignment, duplicate handling, quality rejection, calm hours,
  missing records, station selection/override, seasonal gaps, and insufficient
  coverage using deterministic fixtures; do not require network access in tests.
- Verify reference/exposure transfer, timestamp and averaging semantics, height
  selection, buffer cropping, coordinates, and provenance serialization.
- Compare synthetic climate classifications with the existing comfort helpers,
  including threshold equality, seasonal aggregation, invalid cells, and GEM.
- Verify geometry is prepared once and directional volumes are released; test
  failure of any required direction and resource limits.
- Run a small native end-to-end case for each criterion, plus one real historical
  weather example after core support is installed. Check plotting and export.
- Compare 16/32 directions, baseline/finer spacing, and larger domain buffers.
  Evaluate peak-factor sensitivity using the same mean/turbulence planes. Record
  changes in classifications and their area, then finalize defaults from evidence.
- Run applicable existing Dataset, wind, and comfort regression tests.

Completion means both built-in criteria produce an inspectable map from bounds
and automatically retrieved historical observations, with adequate coverage,
documented assumptions, correct masks, and traceable diagnostics. Fixtures alone
do not establish completion of the automatic weather workflow.

## Future work

- Replace the constant peak factor only after a dynamic model is calibrated and
  independently validated. Possible inputs include geometry, local turbulence
  timescales, incoming gust statistics, and explicit gust/observation durations.
  Do not identify QES mixing length with a validated integral turbulence scale.
- Improve station representativeness, direction-dependent exposure, and weather
  transfer where suitable upstream data become available.
- Consider multiple criteria in a single call, sharing simulations and sampling
  both criterion heights, if this provides a useful user-facing product.
- Broader geographic support and terrain-aware comfort are separate extensions.

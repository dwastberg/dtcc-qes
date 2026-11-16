# Pedestrian wind comfort

For automatic historical weather and geometry retrieval, import `dtcc_qes` and
call `datasets.qes_wind_comfort(bounds=[xmin,ymin,xmax,ymax])` in EPSG:3006.
It uses the installed Core `weather_history` dataset for wind speed and direction.
By default the period is twelve calendar months ending at the first of the
previous month, exclusive; `start`/`end` or inclusive `years=(first,last)` override
it. The default criterion is `nen8100`; `city_of_london` includes seasonal and
constant-factor GEM screening. Results have `.plot(field_name="comfort")`,
`.plot_wind_rose()`, separate safety and validity fields, PNG/GeoJSON exports and
weather/geometry provenance. See [Dataset policies](../WIND_COMFORT_DATASET.md)
for assumptions, coverage checks and the [example](../demo/wind_comfort_dataset.py).

Version 0.1.0b5 changes gust screening through the spectral stress bound and
corrected first two ground-layer derivatives, as well as the building wind
corrections. Recompute cached directional results before comparing comfort
maps across versions. The twelve-direction example's F5 comparison changes
GEM by at most 1.356 m/s, with 0.136% of valid samples changing by more than
0.05 m/s. F6 leaves that example's 1.5 m maps unchanged because it samples the
third cell centre; uniform grids can change. These are numerical checks, not
physical gust calibration. [Full results](../validation/PHYSICS_BUG_FIX_RESULTS.md).

`dtcc_qes.comfort` turns per-direction pedestrian wind speeds and an hourly wind
climate into comfort and safety classes. Its helper dependency closure uses only NumPy and the standard library; an
isolated-load test enforces this. Any source of pedestrian-level mean speeds can
be used: QES, other CFD or wind-tunnel probes.

## Preparing a city once

Use `wind.prepare` when solving multiple directions on one city and grid:

```python
from dtcc_qes import wind, comfort

profile = wind.LogProfile(5, 270)
with wind.prepare(city, profile, resolution=2, bounds=(0, 0, 0, 80, 60, 40),
                  turbulence=wind.Turbulence()) as model:
    results = [model.run(profile.with_direction(direction))
               for direction in range(0, 360, 30)]
    setup = model.preparation_timings

# Fields and metadata remain valid after the model has closed.
hourly_speeds, hourly_directions = [3, 5, 7], [0, 90, 270]  # Toy climate.
assessment = comfort.assess_results(results, hourly_speeds, hourly_directions)
```

Python geometry extraction, footprint cleaning, grid planning, native building
voxelization, the pressure operator and turbulence geometry are retained.
Each run recomputes the inflow, building parameterizations, right-hand side,
velocity solution and turbulence fields. Solver workspaces are reset to zero;
previous directions do not warm-start subsequent solutions.

The profile supplied to `prepare` establishes reference height and roughness;
both must remain unchanged. Subsequent profiles may change direction, speed,
family and shape, subject to normal layer-coverage validation. Each run accepts
a profile or both `speed=` and `direction=`. `solver=` at preparation supplies
the default, and a per-run override can change numerical settings and monitoring.
Geometry, bounds, layers, terrain, cleaning, building-model and turbulence
settings are fixed. Prepare another model to change them. Preparation snapshots
the inputs, so later edits to the source city or bounds do not affect the model.

Use a context manager or `close()` for prompt release. Closing twice is harmless;
running a closed model raises. Concurrent or reentrant run/close calls on one
model raise immediately. Independent models retain the native process-wide
execution lock. Failed conditions leave the model available for retry, with
the same failure policy as `wind.run`. Every result owns its arrays and editable
metadata independently of the model and other results.

`model.preparation_timings` returns a copy of the one-time setup measurements:
`total_seconds` includes `city_preparation_seconds` and
`native_preparation_seconds`; the native measurement includes binding work and
lock wait. Each result's `metadata["timings"]["public_call_seconds"]` measures
only its `model.run` call. Its city and native preparation timers are zero,
and `condition_preparation_seconds` records profile metadata/layer evaluation.
Add setup `total_seconds` once to the sum of per-run public-call times. Model
teardown, caller sampling and file output require separate timing. The raw
`result.solver["record"]`, when present, remains untouched and retains the
native runner's original preparation timer; use the result timing report for
series accounting.

The example above retains full volumes to use `assess_results`. For large
direction series, sample each result and discard its volume, then pass the
stacked pedestrian fields to `comfort.assess`. The prepared model itself does
not accumulate results. The complete [example](../examples/wind_comfort.py)
uses preparation reuse for both mean-speed and gust-equivalent assessment.

## Method

The criteria below share one method, described in Annex A of the City of
London guideline:

1. A model gives the pedestrian-level speed for each simulated direction d,
   relative to a reference speed upstream: `K_d = field_d / reference_speed_d`.
2. Each valid hour t of the climate is assigned to the nearest simulated
   direction. Its pedestrian speed is `K_d(t) * V_t`.
3. The fraction of hours above a threshold speed is summed over all
   directions. This is the total exceedance, not a per-direction value.
4. Ordered rules map exceedances to classes.

Step 2 assumes that `K` does not depend on wind speed. For QES this holds to
float32 precision (about 2e-6 between 2, 5 and 12 m/s inflow). For RANS and
wind-tunnel data it holds approximately, through Reynolds-number independence.

The hourly speeds must be expressed at the simulations' reference: the same
height and the same upstream roughness as the inflow profile. Station winds
(usually 10 m in open terrain) need converting first. `log_law_transfer`
offers a simple neutral log-law conversion matched at a blending height
(60 m by default) with no displacement height.

### Conventions

- **Directions.** Directions are meteorological (where the wind comes from)
  in degrees clockwise from north, for both the hourly data and the fields.
  Ties between two equally near field directions go to the earlier field.
  Interpolating between directions is not supported.
- **Hours.** An hour is excluded and counted as missing if its speed is not
  finite, or if its direction is not finite while its speed is above zero.
  Calm hours (speed 0) count in the total even without a direction.
  Exceedance fractions use the number of valid hours.
- **Invalid cells.** A field cell that is NaN for any direction gets class
  -1 and NaN exceedance.
- **Exceedance.** Exceedance is the fraction of hours strictly above a speed.
  The empirical hourly distribution is used directly; no Weibull fit is made.
- **Rules.** Each rule allows a speed to be exceeded for at most a given
  fraction of hours, and the first rule a cell satisfies sets its class.
  Speeds and fractions may not decrease from rule to rule. Each rule states
  whether the boundary fraction itself passes (`inclusive`).
- **Mean and GEM.** For criteria defined on both mean and gust equivalent mean
  (GEM) speeds, each threshold uses the larger of the mean and GEM exceedances.
  With non-decreasing rules this equals the guideline's "worse category of
  the two assessments".

## NEN 8100 (`comfort.NEN8100`)

The criterion uses hourly mean speed at 1.75 m above ground, over all hours of
the year. NEN 8100 defines its climate as potential wind at 60 m.

**Comfort.** The class depends on the fraction of hours above 5 m/s. The
classes are half-open bins:

| Class | Hours above 5 m/s | Traversing | Strolling | Sitting |
|---|---|---|---|---|
| A | < 2.5 % | good | good | good |
| B | 2.5 % to < 5 % | good | good | moderate |
| C | 5 % to < 10 % | good | moderate | poor |
| D | 10 % to < 20 % | moderate | poor | poor |
| E | ≥ 20 % | poor | poor | poor |

**Danger.** The class depends on the fraction of hours above 15 m/s:

| Fraction of hours | Class |
|---|---|
| ≤ 0.05 % | no risk |
| 0.05 % < p < 0.30 % | limited risk (acceptable for traversing only) |
| ≥ 0.30 % | dangerous |

`ComfortResult.activity("traversing" | "strolling" | "sitting")` returns the
activity ratings for each cell.

## City of London Lawson criteria, 2019 (`comfort.CITY_OF_LONDON`)

**Comfort** uses the mean and GEM speed exceeded 5 % of the time, at 1.5 m.
Each category allows exactly 5 %:

| Category | Speed exceeded 5 % of the time |
|---|---|
| Frequent sitting | ≤ 2.5 m/s |
| Occasional sitting | ≤ 4 m/s |
| Standing | ≤ 6 m/s |
| Walking | ≤ 8 m/s |
| Uncomfortable | > 8 m/s |

**Seasons.** The guideline requires the worst season, plus summer (June to
August) reported separately.

- With `times` (hourly datetime64), comfort is classified for each of
  winter (December to February), spring, summer and autumn.
  `ComfortResult.comfort` is the worst class per cell, and
  `ComfortResult.seasonal` holds each season's map. Every season must contain
  valid hours.
- Without `times`, all hours are used and the result carries a warning.

**Safety** uses all hours of the year. A cell is unsafe if 15 m/s is exceeded
for more than 0.022 % of hours.

GEM is gust speed divided by 1.85. The [City of London guideline (2019)](https://www.cityoflondon.gov.uk/assets/Services-Environment/wind-microclimate-guidelines.pdf),
printed page 11, specifies that conversion; Annex A, printed page 23, requires
separate mean/GEM assessments and the worse category for comfort and safety.
`assess` implements this through the larger mean/GEM exceedance at each threshold.
City of London assessments remain mean-only unless `gem_fields` are supplied.

For optional QES-Turb output, `comfort.gust_equivalent_mean` estimates
`(speed + peak_factor * streamwise_std) / gust_ratio`, with `gust_ratio=1.85`.
`peak_factor` is required: this guideline does not establish a peak factor or
gust averaging time for this algebraic model. QES mean/stress output has no
established averaging duration here. These are unvalidated gust screening
estimates. `comfort.SCREENING_PEAK_FACTOR = 3.0` is the shared constant for
automatic comfort screening and the example. It is a pragmatic assumption,
with no claimed QES calibration or validated averaging time. It applies to
every location and wind direction; local mean speed and turbulence still vary
with the simulated geometry. The low-level helpers retain explicit factor
selection for specialist use.

### Future work: dynamic peak factor

Investigate factors varying by location and direction using estimated turbulence
timescales and explicitly defined gust and observation durations. Historical
gust observations can help constrain incoming conditions, but do not directly
determine pedestrian-level factors. A dynamic model must be checked against
independent measurements or time-resolved simulations before replacing the
constant; QES mixing length is not automatically an integral turbulence scale.

### Gust-field validity

The helper returns float64 arrays of the same shape as its two inputs. It
preserves NaN values, including invalid stress and undefined mean directions.
Negative speeds/deviations, infinities, mismatched shapes and non-positive or
non-finite scalar factors raise `ValueError`; an overflowing estimate also raises.
Do not replace masked values with zero: NaN in any direction leaves that cell
unassessed (`comfort`/`safety` = -1, exceedance = NaN).

For each direction, solve with `turbulence=wind.Turbulence()`, sample at the criterion height,
and build the fields explicitly:

```python
from dtcc_qes import comfort, wind

gust_result = wind.run(city, speed=5, direction=270,
    bounds=(0,0,0,80,60,40), turbulence=wind.Turbulence())
screening = comfort.assess_results([gust_result], [5], [270],
    comfort.CITY_OF_LONDON, peak_factor=comfort.SCREENING_PEAK_FACTOR)
assert any("screening estimate" in warning for warning in screening.warnings)
```


Pass the stacked arrays as `fields` and `gem_fields` to `assess`, together with
`gem_metadata`, a mapping copied into `ComfortResult.metadata["gem"]`. Record
`source`, `model`, `numerics_version`, `peak_factor`, `gust_ratio`,
`mean_averaging_time`, `gust_averaging_time`, `validity_policy` and `limitations`.
Use `"unspecified"` for unknown averaging times. The complete
[example](../examples/wind_comfort.py) records these assumptions for its QES runs.

QES provenance in `source`, `model` or `numerics_version` retains an explicit
unvalidated-gust screening warning. Supplying GEM removes the mean-only warning;
seasonal/height warnings still apply. Generic externally supplied GEM fields
remain supported; missing source/model provenance produces an unspecified-source
warning. Metadata records the caller's claims and does not certify gust validation
or guideline compliance. `gem_metadata` without `gem_fields` is rejected.

The original Lawson LDDC table (4 / 6 / 8 / 10 m/s comfort at 5 %) is not
built in, because its safety thresholds could not be verified from a primary
source. It can be defined as a `comfort.Criterion`.

## Limitations

- **Screening only.** Planning guidelines (City of London 2019, Toronto 2022)
  require RANS CFD with a two-equation turbulence model, or LES. QES is a
  diagnostic model with empirical parameterisations. Use QES-based comfort
  maps for screening and early massing, not for planning submissions.
- **Height.** Use fields at the criterion height: 1.5 m for City of London,
  1.75 m for NEN 8100. On the default uniform 2 m grid, the first QES cell
  centre is at 1 m. An explicit vertical grid (`wind.VerticalGrid`) can place
  a cell centre at the right height. Passing `height=` records the fields'
  height and warns about any mismatch.
- **Station data.** Transferring station data to the site reference is a
  first-order log-law estimate. Stability, displacement height and
  direction-dependent upstream roughness are ignored.

## Sources

- [City of London Wind Microclimate Guidelines (2019)](https://www.cityoflondon.gov.uk/assets/Services-Environment/wind-microclimate-guidelines.pdf)
- [SimScale: NEN 8100 wind comfort](https://www.simscale.com/blog/nen-8100-wind-comfort/)
- NEN 8100 danger bounds as quoted in Dutch planning studies, e.g.
  [Groningen wind study](https://gemeenteraad.groningen.nl/Documenten/Document/Bijlage-2-windstudie-2.pdf)
  and [Commissie m.e.r. wind climate report](https://commissiemer.nl/docs/mer/p20/p2034/2034-043f_windklimaat.pdf)
- [Janssen, Blocken & van Hooff (2013), comparison of wind comfort criteria](https://research.tue.nl/en/publications/pedestrian-wind-comfort-around-buildings-comparison-of-wind-comfo/)


## Results, references and provenance

`comfort.assess_results` samples each result at the requested or criterion height.
It checks x/y coordinates, origin, CRS, reference height and roughness. Each
run may have a different positive reference speed; direction comes from the
declared profile reference, never a locally deflected pedestrian vector.
Calm references and duplicate directions modulo 360 are rejected.

Nearest sampling must select the same actual height in every direction; that
actual height is passed to the criterion warning. Linear sampling retains the
requested height wherever supported; unavailable support remains NaN with
`sampled_height=None`. Invalid stress contributors remain invalid even if their
interpolated tensor is positive semidefinite. No missing data are filled by zero.

Both mean-only NEN8100 and GEM City of London results copy per-direction
qualification, references, caveats and requested/actual sample heights into
`metadata["runs"]`. `assess(..., run_metadata=...)` supports independent provenance
for other field sources. GEM-specific factors stay separately in `metadata["gem"]`.
Only a gust-equivalent criterion with an explicit peak factor computes GEM;
otherwise the existing single mean-only warning applies. No exposure transfer
is implicit, and numerical mean-wind acceptance never qualifies gusts.

`assess_results(..., speed="scalar")` assesses the scalar speed √(|u|² + 2k)
of the [spreading wake](spreading-wake.md) instead of the mean vector's
magnitude. Every result needs `Parameterizations(wake=3)`; the run's default
inflow turbulence is used and recorded per direction in
`metadata["runs"]["inflow_tke"]`, and `metadata["runs"]["speed"]` names the
measure. The scalar speed is at least the same `wake=3` run's vector speed, so
its classes are never better than that run's vector classes. This does not hold
against the default `wake=2` vector: exploratory Case E results show better
overall comfort agreement but more missed safety warnings near the new tower
(15 of 20 risk probes versus 2 at the highest climate level). A dominant wind
direction also increases optimistic comfort classifications. Keep `wake=2`
vector for safety screening pending the [comfort plan](../WAKE3_COMFORT_DEFAULT_PLAN.md). It already contains the turbulence and is not combined with GEM. It is
experimental: NEN 8100 and the Lawson criteria are defined on mean speeds, and
which of the two speeds they intend at a pedestrian probe is not settled.

## Explicit exposure-transfer laws

`log_law_transfer(..., from_law="standard", to_law="shifted")` converts a station
measurement to the shifted LogProfile convention at a common blending height
(default 60 m). Standard means ln(z/z0), requiring z>z0; shifted means
ln(1+z/z0), requiring positive z and z0. Each selected law applies to **both**
terms on its own side:

`L_from(hb,z0_from)/L_from(z_from,z0_from) * L_to(z_to,z0_to)/L_to(hb,z0_to)`.

Matching laws give identity and reciprocity within float64 roundoff. Standard
station and shifted target laws intentionally give a convention conversion,
even with matching nominal heights/roughness. Shifting only the target numerator
would fail the blending-height agreement with LogProfile. Non-log profiles
receive no automatic transfer. Rigid profile rotation uses `with_direction`;
`scaled` changes amplitude while retaining shape.

On the example's seeded 8,760-hour station climate (10 m, z0=.03 m transferred
to 10 m, z0=.1 m), the old standard/standard factor is 0.9419485938616713;
the corrected standard/shifted factor is 0.943738171406828. With identical solved
fields and a 1.5 m sample, 2 of 1,175 valid NEN comfort cells change class and
none change safety class. None of 1,039 London comfort cells change; one changes
safety class. This records a convention effect, not physical validation. See
[reproducible Phase 4 evidence](data/feature-merge/phase4.json).

Turning beyond 45° warns because building wakes follow roof-level direction.
QES-Turb converts sampled solved speed at its morphometric reference through a
log law, which can conflict with jets or strong shear. Its output remains
algebraic screening. See the [profile guide](wind-profiles.md).

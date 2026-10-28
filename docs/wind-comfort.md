# Pedestrian wind comfort

`dtcc_qes.comfort` turns per-direction pedestrian wind speeds and an hourly wind
climate into comfort and safety classes. It imports only numpy and the standard
library; a test enforces this. Any source of pedestrian-level mean speeds can
be used: QES, other CFD or wind-tunnel probes.

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
estimates. The example's factor **3.0 is a user-selected screening assumption**;
it has no claimed QES calibration or validated averaging time.

The helper returns float64 arrays of the same shape as its two inputs. It
preserves NaN values, including invalid stress and undefined mean directions.
Negative speeds/deviations, infinities, mismatched shapes and non-positive or
non-finite scalar factors raise `ValueError`; an overflowing estimate also raises.
Do not replace masked values with zero: NaN in any direction leaves that cell
unassessed (`comfort`/`safety` = -1, exceedance = NaN).

For each direction, solve with `turbulence=True`, sample at the criterion height,
and build the fields explicitly:

```python
sample = result.sample(1.5, method="linear")
mean_fields.append(sample.speed)
gem_fields.append(comfort.gust_equivalent_mean(
    sample.speed, sample.streamwise_std, peak_factor=3.0,
))
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

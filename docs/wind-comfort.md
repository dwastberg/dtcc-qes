# Pedestrian wind comfort

`dtcc_qes.comfort` turns per-direction pedestrian wind speeds and an hourly wind
climate into comfort and safety classes. Its helper dependency closure uses only NumPy and the standard library; an
isolated-load test enforces this. Any source of pedestrian-level mean speeds can
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

For each direction, solve with `turbulence=wind.Turbulence()`, sample at the criterion height,
and build the fields explicitly:

```python
from dtcc_qes import comfort, wind

gust_result = wind.run(city, speed=5, direction=270,
    bounds=(0,0,0,80,60,40), turbulence=wind.Turbulence())
screening = comfort.assess_results([gust_result], [5], [270],
    comfort.CITY_OF_LONDON, peak_factor=3.0)
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

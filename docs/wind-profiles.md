# Experimental horizontal background profiles

`dtcc_qes.wind` exports immutable `LogProfile`, `MeasuredProfile`,
`PowerLawProfile` and `UniformProfile` specifications. Legacy scalar calls
retain the existing neutral shifted-log numerical path. New families describe
steady horizontal background wind across the domain before building models and
mass correction. They do not enforce interior observations or add stability,
terrain, vegetation, transient turbulence or momentum transport.

| Specification | Contract |
| --- | --- |
| `LogProfile(speed, direction, reference_height=10, roughness_length=.1)` | Existing neutral shifted log; roughness is carried by this specification |
| `MeasuredProfile(heights, speeds, direction=..., reference_height=..., below="error", above="constant", interpolation="log_height")` | Two or more strictly increasing positive heights; nonnegative speeds; one shared FROM direction |
| `MeasuredProfile.from_directions(heights, speeds, directions, ...)` | Direction per height; also accepted as the constructor's `directions=` keyword |
| `MeasuredProfile.from_components(heights, u, v, ...)` | Horizontal component vectors; no inferred directions at calm knots |
| `PowerLawProfile(speed, direction, reference_height, exponent)` | `Uref * (z/zref)**exponent`; explicit finite positive exponent |
| `UniformProfile(speed, direction, reference_height=10)` | Constant vector, including ground evaluation; verification/control use |

Heights are metres above flat ground, speeds are m/s, directions are
meteorological FROM clockwise from north, and `w=0`. Each profile accepts
`metadata={...}` for explicit source, location, timestamp, averaging period,
scalar/vector-mean provenance or other JSON information. Missing provenance
remains absent. Input arrays and nested metadata are copied and frozen.

## Interpolation, tails and native supports

Measured u/v components interpolate linearly in **ln(z)** by default.
`interpolation="linear"` interpolates in physical z. Each query locates its
bracket directly, so coarse grids can skip many knots. Nonmonotonic speed,
interior maxima, calm knots, reversals and turning are supported. Component
interpolation can reduce speed or cancel vectors between differently directed
knots; it deliberately does not interpolate scalar speed and angle.

Below the first knot, the default `below="error"` rejects evaluation. Explicit
`below="log"` scales the lowest vector by
`log1p(z/z0)/log1p(z_low/z0)`, using **the run's roughness_length**. This matches
the knot, reaches zero at ground and keeps calm knots calm. Above the last knot,
`above="constant"` holds the last vector by default; `above="error"` rejects
it. There are no inferred high-altitude slopes or polynomial tails.

All new-profile evaluation occurs in Python float64 at the final float32
physical cell-centre heights, including the top physical layer. The declared
reference height is checked separately. Coverage errors happen before native
preparation. Knots above the domain can bracket its upper layers without growing
the domain. `preview_grid(city, profile=..., ...)` runs the same preparation and
records the same table in `preview.domain["profile"]`.

Native code receives only an owned table of one u and v per physical layer,
plus reference scalars. It validates kind, lengths, finiteness and float32
representability before replacing active inputs. All new families share this
one table-copy path. It writes exactly the physical bands written by the legacy
log path; lower ghosts and the upper face remain zero. Every solve initializes
all bands deterministically. The table velocity limit uses the maximum physical
layer speed, so jets are not limited by only the top layer.

## Calling and evaluating

```python
from dtcc_qes import wind

profile = wind.MeasuredProfile(
    [2, 5, 10, 20, 40], [2.1, 3, 4.2, 5.6, 7],
    direction=270, reference_height=10, below="log",
)
result = wind.run(city, profile=profile, roughness_length=.1)
preview = wind.preview_grid(city, profile=profile, roughness_length=.1)
u, v = wind.evaluate(profile, [1, 5, 10, 20], roughness_length=.1)
vectors = profile.evaluate([1, 5, 10, 20], roughness_length=.1)
restored = wind.profile_from_dict(profile.to_dict())
faster = profile.scaled(2)  # positive amplitude; same shear and turning
```

`speed`/`direction` and explicit `reference_height` conflict with `profile=`.
For `LogProfile`, supplying run-level roughness also conflicts, because the
specification carries it. For all other profiles, run-level roughness is
allowed and retains its preparation-time ground/turbulence meaning as well as
supplying measured lower log tails. Omitted roughness defaults to .1 m.

The declared reference vector supplies monitor normalization, dataset speedup,
`result.reference_speed`, `result.speedup` and profile metadata. It is evaluated
from the profile, not the highest measurement. With a calm reference, mean-flow
solves remain possible, speedup is NaN, and comfort rejects normalization by zero.
`result.to_dtcc(include_speedup=True)` optionally exports speedup, preserving the
default legacy field set.

`result.metadata["profile"]` records schema version, requested inputs, height
datum, interpolation/tail policies, float64 layer vectors, effective float32
layer vectors, the reference, lower/upper tail layer counts and
`max_turning_deg`. Existing legacy metadata keys remain available. The log
profile's float64 preview is a reference evaluator; actual legacy arithmetic
and its rounding stay native and unchanged.

## Datasets

```python
from dtcc_core import datasets

slice_result = datasets.qes_wind(
    bounds=[0, 0, 0, 80, 60, 40], profile=profile.to_dict(),
    roughness_length=.1, product="slice", slice_height=1.5,
)
```

`QESWindArgs.profile` is a JSON payload discriminated by `kind`: `log`,
`measured`, `power_law` or `uniform`, with `schema_version=1`. Validation occurs
before fetching city data; coverage is rechecked after final grid preparation.
Explicit `wind_speed`, `wind_direction` and `reference_height` conflict with a
profile. Explicit roughness conflicts only with a log profile. Canonical request
serialization includes the complete profile and tails, omits inactive scalar
defaults and preserves relevant run roughness. Requests round-trip through JSON;
different shapes/policies cannot share request identity. Dataset slices and
profile-based field products normalize with the same reference as direct runs.

## Turning, turbulence and scope

Turning is supported without opt-in. `max_turning_deg` measures the span of
unwrapped non-calm layer directions across the domain. More than **45 degrees**
produces a warning. Existing building models sample the vector at their own
roof heights, so wakes use each roof-level direction even where lower layers
turn. A calm roof vector has deterministic `atan2(0,0)=0` orientation and zero
sampled magnitude. Rooftop/canyon empirical log-shaped adjustments remain.

`turbulence=True` and the existing `Turbulence` settings work with every family.
QES-Turb derives friction velocity from sampled **solved** wind using its
morphometric log-law conversion (building-derived roughness/displacement and
reference height, or configured roughness without buildings). Arbitrary input
shear or jets can be inconsistent with that conversion. Metadata records this
caveat; no undisclosed log fit to measurements is introduced. New profiles do
not create independent physical, gust or planning-submission validation.

Measured, power-law and uniform inputs ship as experimental. See the
[numerical evidence](wind-profiles-verification.md),
[measured/power-law example](../examples/wind_profiles.py) and
[comfort reference guidance](wind-comfort.md). Profile-per-sector selection,
new exposure transfer and independent physical validation remain separate
follow-up work in `WIND_PROFILES.md`.

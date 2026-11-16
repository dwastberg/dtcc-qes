# Pedestrian wind comfort Dataset

`datasets.qes_wind_comfort` is implemented using the `weather_history` API in
this project's installed dtcc-core. The dependency and lockfile are unchanged.
The public entry point requires only assessment bounds in EPSG:3006.

```python
import dtcc_qes
from dtcc_core import datasets

result = datasets.qes_wind_comfort(bounds=[319920, 6397860, 320000, 6397940])
result.plot(field_name="comfort")
result.plot_wind_rose()
result.write_artifact("comfort.png")
result.write_artifact("comfort.geojson", format="geojson")
```

## Arguments and dates

| Argument | Default | Meaning |
| --- | --- | --- |
| `bounds` | Required | Four coordinates `[xmin,ymin,xmax,ymax]`, or six `[xmin,ymin,zmin,xmax,ymax,zmax]`; Bounds objects also work. XY bounds select the assessment, six-coordinate bounds also set flat ground and domain top. |
| `source` | `"LM"` | City source; also `"OSM"`. |
| `resolution` | `2.0` m | Horizontal solver spacing; output retains solver cell centres inside the assessment. |
| `max_cells` | `200_000_000` | Positive integer cell limit for the full buffered simulation domain; the demo sets `50_000_000`. |
| `criterion` | `"nen8100"` | Also `"city_of_london"`. |
| `start` | Twelve calendar months before end | Inclusive UTC boundary. |
| `end` | First of the previous month | Exclusive UTC boundary, leaving the previous month outside the record. |
| `years` | None | Alternative inclusive pair of calendar years, e.g. `(2016,2025)`; conflicts with explicit start/end. |
| `weather_source` | `"smhi"` | Station observations; `"open_meteo"` explicitly selects ERA5 reanalysis. No automatic fallback. |
| `exposure` | `"open"` | Assumed upstream site exposure: open z0=.03 m, suburban .3 m, urban 1 m. |
| `strict_live` | False | Core upstream error policy. QES still refuses failed weather retrievals or incomplete cities. |

On 2026-11-16 the default interval is **[2025-10-01 00:00 UTC,
2026-10-01 00:00 UTC)**. All boundaries must fall on UTC hours. Offset timestamps
are normalized by Core. Supplying only `end` chooses the preceding twelve
calendar months; supplying only `start` retains the default cutoff. Leap-day
subtraction clamps to February 28. Resolved dates and policy version enter the
validated request and provenance; a month rollover cannot change an existing
request's dates. At most 3,660 days are supported by Core's default history limit.

Single-condition settings (`speed`, `direction`, `profile`, etc.) are rejected.
The installed historical API chooses the nearest common station automatically;
it does not expose a station override, so `station_id` is not accepted here.

## Historical weather policy: paired-hourly-v1

Acquisition and caching stay in `dtcc_core.datasets.weather_history`.
SMHI is requested at the assessment centre with both wind parameters and a
100 km search radius. Core selects one common station for the entire interval,
checks advertised archive/position coverage, and lets corrected records replace
provisional records. QES preserves the station selection and exclusions in its
provenance. It refuses station relocations, mixed stations, duplicate/unordered
or off-hour timestamps, unexpected units, and any upstream retrieval error.
There is no separate SMHI downloader and no synthetic fallback.

Speed and direction are joined on exact UTC hours with no interpolation.
Missing readings, missing/unknown SMHI quality flags, and every SMHI flag other
than G are excluded. Negative speeds, out-of-range directions and infinities
are excluded; 360 degrees becomes north. Calm speed zero remains valid with no
direction. Coverage requires at least 90% valid pairs overall and 80% in every
requested calendar month, before any geometry fetch or solve. London also
requires valid observations in every season. Missing hours remain NaN and
contribute to neither annual nor seasonal denominators.

The source's averaging description is retained verbatim. SMHI ten-minute means
reported hourly and ERA5 instantaneous samples are **not hourly means**; this is
explicitly an approximate screening assessment. Unknown measurement height is
assumed to be 10 m AGL and warned about; station elevation is never substituted.
Station/ERA5 exposure is assumed open with z0=.03 m, separately from site
exposure. Climate transfer uses the existing neutral `log_law_transfer`, standard
station law to shifted QES law, 10 m target height and 60 m blending height.
These assumptions do not establish station representativeness or compliance.

Provenance records the full requested interval, actual record envelopes, station
position/distance and history, source archive revisions, units/averaging semantics,
quality/invalid/missing counts, monthly coverage, reference assumptions,
retrieval time and a SHA-256 climate identity. The wind rose counts non-calm
observations in 16 FROM-direction sectors and reports calm hours separately.

## Geometry, solves and products: comfort-screening-v1

City fetching/completeness checks and height-preserving footprint preparation
are shared with `qes_wind`. Source courtyards are filled and terrain is flattened.
The isotropic fetched buffer starts at max(40 m, ten grid cells), increases to
five times the tallest fetched roof (rounded upward in 20 m steps), and must
stabilise within four fetches.
The simulation extends another max(20 m, three cells) beyond those bounds.
Default top is max(40 m, three roof heights + 20 m); explicit six-coordinate
bounds must provide sufficient building/pedestrian clearance.

Explicit layers put a centre at 1.75 m (NEN) or 1.5 m (London), using a dedicated
0.5 m layer, lower cells no taller than 1 m, and growing layers above it capped
by horizontal spacing (the final top layer closes the exact endpoint). Geometry
and native storage are prepared once. All sixteen directions, 22.5 degrees
apart, run sequentially at 5 m/s and 10 m reference with the same shifted log
profile. The configurable `max_cells` guard defaults to 200 million cells and
bounds the full simulation domain, including buffers. Solver nonconvergence or
any failed required direction aborts the assessment; directions are never
dropped or reweighted. Full solved volumes are released after sampling.

The existing `comfort.assess` routines determine classes and threshold equality.
NEN returns comfort A–E, separate danger, and sitting/strolling/traversing
suitability. London enables QES-Turb and assesses the worse of mean and GEM,
seasonal comfort, worst-season comfort and annual safety. Its constant policy is
`GEM = (mean_speed + 3.0 * streamwise_std) / 1.85`; provenance records arithmetic,
validity, unspecified averaging durations and unvalidated-gust limitations.

Results are FieldSlice objects with categorical plotting and wind-rose helpers.
Fields include `comfort`, `safety`, `valid`, `exceedance_<speed>`, NEN activity
fields, and London `comfort_<season>` fields. Invalid samples have class -1 and
NaN probability, including when any direction has invalid stress. Plotting uses
cell polygons and discrete legends, with unassessed cells grey; categories are
never interpolated. PNG and GeoJSON exports retain useful maps and all sample
fields respectively. `dataset_context` stores weather and geometry upstream
contexts, explicit dates, per-direction references/diagnostics/qualification,
requested/actual height, geometry policy, timings and warnings.

Historical retrieval uses Core's cache. Directional planes are reused within a
request; persistent simulation caching is not provided in this version. Calls
recompute the directional sweep, so there is no risk of a stale result being
reused for a changed climate, geometry or solver policy.

## Verification and qualification

`tests/test_comfort_dataset.py` exercises dates including January/leap-year
rollover, weather alignment, quality rejection, calms, exposure transfer,
station relocation, seasonal gaps, failure before geometry fetching, both native
criteria, single preparation/release, coordinates, provenance, plots and exports.
Existing wind, prepared-wind, Dataset and comfort tests cover shared behavior.
The runnable real-data example is `demo/wind_comfort_dataset.py`. Set its variables
at the top of the script; it takes no command-line arguments and plots by default.
Set `SAVE_RESULT = True` to save PNG, GeoJSON and context JSON in `OUTPUT_DIR`.

Live SMHI verification on 2026-11-16 selected Göteborg A (71420), 3.25 km from
the example assessment centre. For [2025-10-01,2026-10-01) it returned 8,757 valid
paired hours of 8,760 (99.966%), including 445 calm hours; measurement height was
10 m and the preserved averaging description was ten-minute means once hourly.
Both criteria also completed the full live city/weather workflow at 4 m spacing:
all sixteen directions converged, each map contained 400 solver samples (228
valid, 172 unassessed), and PNG, GeoJSON and complete context JSON were saved
under `build/wind-comfort-live` and `build/wind-comfort-live-london`. The applicable
wind, Dataset, prepared-model and comfort regression suite passed 346 tests.

This is an operational screening Dataset, not a qualified comfort preset.
16/32-sector, finer-grid, larger-buffer and peak-factor sensitivity remain
site-dependent checks. The default spacing/buffer/direction policy is provisional,
and empirical QES mean/stress fields and gust factors do not qualify planning
submissions. A dynamic peak factor, station overrides (when Core supports them),
persistent simulation caching, improved exposure inference and terrain-aware
assessment remain future extensions.

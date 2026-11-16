# Changelog

Versions before 0.1.0b2 were not released. Their features (unified `run()` API, solver control and the `pedestrian-v1` policy, turbulence, wind profiles, prepared models) are described in [README.md](README.md) and `docs/`.

Every version below changes default results. Each one states what changes, how it was checked, and how to keep the previous behaviour where that is possible. The native identity is the qualified source and arithmetic identity of the build. Adaptive `pedestrian-v1` acceptance needs the build to report it as supported.

## 0.1.0b6 (2026-11-16)

- **Historical wind comfort Dataset:** importing `dtcc_qes` registers
  `datasets.qes_wind_comfort`. It uses the installed Core `weather_history`
  dataset for paired wind speed/direction, defaults to twelve calendar months
  ending at the first of the previous month (exclusive), and supports NEN 8100
  and seasonal City of London GEM screening. It prepares geometry once, samples
  all 16 directions at the criterion height, and returns comfort/safety maps,
  coverage, wind rose and provenance. See [policies](WIND_COMFORT_DATASET.md)
  and [example](demo/wind_comfort_dataset.py). `max_cells` defaults to 200 million
  for the full buffered domain; the demo sets 50 million. Existing wind defaults are unchanged.

Native identity `e130c2fbf47179923862c037a9a370ec17b91788a01f6719cd282506ba43471a`
(AppleClang 17 Release, default arithmetic); the build is not qualified for `pedestrian-v1`, as 0.1.0b5.

No default result changes: every default run of the validation cases is bit-identical to 0.1.0b5. Two experimental, opt-in settings of `wind.Parameterizations` are added; both are outside `pedestrian-v1`. Measurements: [diagnostics](validation/ACCURACY_DIAGNOSTICS.md) and [results](validation/ACCURACY_RESULTS.md).

- **`angle_fade` (degrees, default 0):** the sidewall zone and the upwind cavity fade with angle instead of switching on at 10° from alignment. With `2.5` the largest step of the 2 m field between wind directions one degree apart falls from 0.032 to 0.015 in K (one building, `wake=3`); the AIJ scores do not move. Cell flags keep the switch. See [the angle fade](docs/angle-fade.md).
- **`tall_buildings` (0 or 1, default 0; needs `wake=3`):** far-wake deficits combine by the root sum of squares, and a building much taller than its neighbours gets a zone of faster air near the ground, from the speed ratios of Reiter (2010); part of the rise is carried as turbulence in `result.wake.tke`. In AIJ Case E the change within 30 m of the new 60 m tower goes from +0.024 to +0.227 (measured +0.262) and the error before construction from +0.176 to +0.093; in Case D the bias goes from −0.120 to −0.033. **It is a scalar-speed model:** at the Case D points where the flow direction is measured, sign errors rise from 5 to 10 of 29. It has no independent test yet. See [tall buildings](docs/tall-buildings.md) for the eight documented limits.
- **Scoring protocol** in `validation/accuracy/`: paired bootstrap intervals over probe and direction groups, shrinkage comparators, the tower table, the 1° direction sweep.
- **Version string:** `dtcc_qes.__version__` now follows `pyproject.toml` (it still said 0.1.0b4 in 0.1.0b5), with a test.
- **Known, not fixed:** with `wake=3` on AIJ Case C at 1 m the velocity stop rule does not trigger and the run goes to the sweep cap; the fields are converged.

## 0.1.0b5 (2026-11-14)

Native identity `b69e655c0ca10190b72b95c2c08c3296e0267c3312b1301a83f9dd0268222761`
(AppleClang 17 Release, default arithmetic). The six corrections replace the
old behaviour without switches. See [measurements and per-fix comparisons](validation/PHYSICS_BUG_FIX_RESULTS.md).

- **Upwind cavity angles:** wrap face normals correctly and cover the missing
  angle sector. Rotated-building and opposite-wind tests check initial and solved fields.
- **Low obstacles in exposed wakes:** stop a wake only at an actual blocking
  solid at the reference height. A low kiosk no longer truncates a tower wake;
  tall-obstacle and touching-building controls preserve blocking.
- **Incident wind:** capture every building's roof wind before writing cavities.
  Wake, canyon, sidewall and rooftop frames use this incident direction; local
  stage strengths remain local. Order, calm-flow and turning-profile tests pass.
  Both proposed direction variants were benchmarked; the specified tie-break selected V1.
- **Split façades:** simplify parameterization rings within half the smaller
  horizontal cell size while preserving original solid masks and topology.
  Kinked façades, courtyard/slot, unequal-spacing and tolerance-sensitivity tests pass.
- **Stress bound:** scale the complete tensor when its spectral radius exceeds
  `20 u*²`, bounding variance in every direction while retaining tensor shape.
  The earlier energy cap remains. Cap flags record actual limiter activity;
  this does not repair indefinite tensors. Full-tensor and export/probe tests pass.
- **Ground gradients:** use shifted-log derivatives in the first two ground
  layers with profile roughness and a solid-aware fallback. Roofs are unchanged.
  Manufactured uniform/stretched-grid profiles pass; mixing length remains κd.

Turbulence metadata now identifies `dtcc-qes-turbulence-v3`, so dataset requests
for earlier numerics cannot silently reuse the corrected model.

The native identity is intentionally **unqualified** for the experimental
`pedestrian-v1` policy. Adaptive runs report `unqualified_build`; ordinary
`Solver()` runs remain available. Qualification evidence is unchanged.

## 0.1.0b4 (2026-11-13)

Native identity `31f6d956fecfa24654a34b7ed43941c38876f38b26d0800ca5868e7b54396f87`.

### Fixed

- **Building reference point for concave footprints.** The reference point samples the incident wind and anchors the wind-aligned frame of the wake and canyon parameterizations. For L- and U-shaped buildings and blocks with courtyards, it now stays inside the footprint. The vertex mean is kept when it lies inside, which covers every convex footprint, so results change only for buildings whose vertex mean fell outside.
  - **Checked** ([FOOTPRINT_REFERENCE_POINT.md](FOOTPRINT_REFERENCE_POINT.md)):
    - AIJ Cases A, B and D are bitwise identical.
    - In Case E, pooled scores change by at most 0.0031, and 0.35 % of probe-directions change by more than 0.05 in K.
    - The `wake=3` gates still pass.

### Added

- **`comfort.SCREENING_PEAK_FACTOR = 3.0`.** One documented peak factor for gust screening, used by the comfort example and the documentation. It is a pragmatic assumption with no QES calibration or validated averaging time. `gust_equivalent_mean` and `assess_results` still take an explicit `peak_factor`. See [docs/wind-comfort.md](docs/wind-comfort.md).

### Packaging

- **sdist size.** The sdist no longer contains the qualification evidence (`docs/data`, 1.8 GB): 21.6 MB instead of 1.4 GB. The evidence stays in the repository. `tools/check_artifacts.py` audits it on the checkout.
- **Tests without the evidence.** Tests of archived evidence skip when `docs/data` is absent, as in an unpacked sdist.

## 0.1.0b3 (2026-11-13)

Native identity `bf48ef3f660d09c3c57a8198ceeac13e4ce9511383a119ea2a17714c5de22ab7`.

### Added (experimental, opt-in)

- **Spreading far wake: `Parameterizations(wake=3)`.** A far wake with a continuous edge and a wake turbulence term. It brings `result.wake` (`WakeFields`), `result.scalar_speed()` and `metadata["wake"]`; see [docs/spreading-wake.md](docs/spreading-wake.md).
  - Adaptive `pedestrian-v1` runs with it are `unqualified_model_settings`.
  - The default stays `wake=2`.
- **Scalar speed in comfort.** `comfort.assess_results(..., speed="scalar")` assesses comfort on that scalar speed. It is not combined with GEM.

### Changed

- **Exposed-face wake cavities.** With exposed faces, the wake cavity now fits the gap (`canyon_factor`) for every wake code, including the default `wake=2`. Results change in exposed slab gaps and courtyards.
  - **Checked:** on AIJ Case E, 1.6 % of probe-directions change by more than 0.01 in K and pooled K scores by at most 0.001 ([validation/WAKE_UPDATE_V2_RESULTS.md](validation/WAKE_UPDATE_V2_RESULTS.md)).

## 0.1.0b2 (2026-11-13)

Native identity `1319a43d89ce2abf951c3eae48d8047457049e31c28a9938e10b4722fbcf4bf6`.

### Changed: the default solver

`Solver()` for legacy and bounded solves now stops when the estimated remaining face-velocity error is at most 1e-3 of the reference speed:

| Setting | New default | Former default |
|---|---|---|
| `stop` | `"velocity"` | `"multiplier_change"` |
| `velocity_tolerance` | 1e-3 | |
| `relaxation` | `"grid"` (2 − 16/N, clipped to [1.78, 1.98]) | 1.78 |
| `max_iterations` | 20,000 | 1,000 |

- **Former behaviour:** `Solver(stop="multiplier_change")` reproduces the former default exactly.
- **Stored specs:** solver specs without a `stop` key keep the multiplier rule.
- **Adaptive:** `pedestrian-v1` solves are unchanged.
- **Speed and accuracy:** on AIJ Cases D and E, 150–250 sweeps at 2 m and 325–475 at 1 m, against 1,000. Every probe is within 1.9e-4 in K of a float64 reference. At 1 m the former default left p95 errors of 0.006–0.013.
- **Scores:** AIJ pooled scores (Cases A, B, D, E at 2 m) change by at most 0.0053.
- **User-facing gain:** a 16-direction Case E comfort series takes 10.1 s instead of 19.4 s.
- **Differences to expect:**
  - The maximum divergence at the stop is higher than after 1,000 multiplier sweeps: the rule bounds the velocity error, not divergence.
  - A field with no buildings needs 125 sweeps instead of one.
  - A calm condition ends on the multiplier rule and records `result.solver["calm_stop"]`.

See [SOLVER_STOP_RULE.md](SOLVER_STOP_RULE.md) and [docs/solver-control.md](docs/solver-control.md).

### Added

- **`Solver(stop=...)` options:** `"velocity"`, `"multiplier_change"` and `"fixed"` (exactly `max_iterations` sweeps, with the estimate recorded), and `velocity_tolerance`.
- **`Solver(relaxation=...)`:** a number, None (1.78) or `"grid"`. The factor used is in `result.solver["relaxation"]` and the method label.
- **`result.solver["stop_estimate"]`:** the history of the velocity estimate.

## Known limitations

- **Stop rule:** validated on AIJ grids down to 1 m; 0.5 m was not studied.
- **Platforms:** verified on macOS arm64 with Python 3.14 only.
- **dtcc-core:** resolved from the git branch `dev/qes-updates` for development; the package metadata does not pin it.
- **`wake=3`:** opt-in, and outside the `pedestrian-v1` qualification. Switching the default wake or the comfort speed awaits a policy study ([WAKE3_COMFORT_DEFAULT_PLAN.md](WAKE3_COMFORT_DEFAULT_PLAN.md)).

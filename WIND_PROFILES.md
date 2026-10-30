# Wind profiles: findings and implementation plan

**Status:** implementation plan, revised 2026-10-30 after a review against the
working tree. The features described below are not implemented. Source
inspection covers the current working tree and the reference QES fork at
`dce15d7e` (upstream base v2.3.1). Research findings draw on established
guidance and publications through October 2026.

## 1. Decision and purpose

Add a small set of inflow profiles that serve dtcc-qes's existing goals:
fast, reproducible urban mean-wind calculations, early massing comparisons,
pedestrian-wind screening, and integration with DTCC city data. Preserve the
in-memory CPU architecture and the legacy path's numerical results.

Scope, delivered together:

1. Keep the current neutral logarithmic profile as the default, unchanged.
2. Add tabulated (measured) horizontal velocity profiles.
3. Add power-law profiles for experimental and engineering comparisons.
4. Add uniform profiles for verification and controlled experiments.

Measured speeds at several heights, with one shared direction or a direction
at each height, must be directly usable. Profiles describe the approaching
background wind, not constraints enforced at interior sensors.

Not in this plan: stability physics, a universal urban-canopy profile,
time-dependent turbulence, weather-model dependencies, and wind-sector
profiles with exposure transfer (a separate plan; see section 6). Externally
generated mean profiles enter through the tabulated interface.

The model remains a steady diagnostic mass-consistent model with empirical
building parameterizations. A better profile does not establish experimental
accuracy, gust accuracy or suitability for planning submissions. See
[comfort scope](docs/wind-comfort.md) and
[existing validation limitations](docs/validation.md).

## 2. Current implementation

`wind.run` accepts scalar `speed`, `direction`, `reference_height` and
`roughness_length`. Direction is meteorological FROM, clockwise from north.
Heights are metres above the flat ground plane; speeds are m/s. The neutral
profile is the shifted log law:

```text
U(z) = Uref * log((z + z0) / z0) / log((zref + z0) / z0)
u(z) = -U(z) * sin(direction)
v(z) = -U(z) * cos(direction)
w(z) = 0
```

These expressions describe the convention. The legacy path keeps the existing
implementation's expressions and rounding.

Execution path:

1. `wind.py` `_validate_condition` checks the scalars; `_city.py`
   `prepare_domain` builds the grid.
2. `WindCondition` crosses the bindings into `ModelInputs::set_condition`.
3. `WINDSGeneralData::applyWindProfile` clears `u0, v0, w0` and calls
   `applyLogProfile`. That writes physical layers `k = 1 … nz` (native
   `domain.nz() = nz + 2`) at the cell-centre heights `z[k]`. The faces below
   ground and above the top physical layer stay zero.
4. Building parameterizations modify `u0, v0`; the solver then applies its
   mass-conservation correction.

| Layer | Files |
| --- | --- |
| Public API, preparation | `src/dtcc_qes/wind.py`, `src/dtcc_qes/_city.py` |
| Dataset and climate integration | `src/dtcc_qes/datasets.py`, `src/dtcc_qes/comfort.py` |
| Binding boundary | `src/cpp/bindings.cpp` |
| QES-free native inputs | `src/qes_core/dtcc/api/wind_config.h` |
| Input validation and runner | `src/qes_core/dtcc/model_inputs.{h,cpp}`, `src/qes_core/dtcc/wind_runner.cpp` |
| Field initialization | `src/qes_core/winds/WindModelInputs.h`, `LogProfile.cpp`, `WINDSGeneralData.cpp` |
| Turbulence | `src/qes_core/winds/TURBGeneralData.cpp`, `src/qes_core/dtcc/turbulence.cpp` |

### How the rest of the model consumes the inflow

- **Building direction.** Every parameterization computes its own
  `upwind_dir = atan2(v0_h, u0_h)` from `u0, v0` at the building centroid at
  roof level (`PolygonWake.cpp:106`, `Rooftop.cpp:110`, `StreetCanyon.cpp:95`,
  `StreetCanyonModified.cpp:106`, `Sidewall.cpp:89`, `UpwindCavity.cpp:93`).
  Each building therefore already sees the inflow direction at its own roof
  height. A calm vector there gives `atan2(0, 0) = 0`: a deterministic
  east-facing wake with zero magnitude.
- **Velocity limit.** `applyWindProfile` sets `max_velmag` to 1.2 × the largest
  speed in the top physical layer only. `StreetCanyon` and
  `StreetCanyonModified` stop a canyon above that speed. A profile whose
  maximum lies below the top would cut canyons off wrongly.
- **Reference speed.** Solver monitors normalize by `condition.speed`
  (`wind_runner.cpp:81`). Dataset speedup divides by `args.wind_speed`
  (`datasets.py`, NaN when zero). Comfort takes a caller-supplied reference
  speed for each direction (`comfort._ratios`).
- **Roughness.** `roughness_length` is a preparation-time `ModelSettings`
  field, not part of the condition. It sets the inflow log profile, the ground
  roughness used by turbulence wall functions (`z0_domain_u/v`,
  `TURBWallTerrain.cpp`) and the turbulence `site_z0` used when there are no
  buildings. Each `wind.run` builds a fresh runner.
- **Turbulence.** `TURBGeneralData::frictionVelocity` never reads the inflow
  parameters. It averages the *solved* speed at `zRef = 3 × mean building
  height` (or `100 z0` without buildings) and converts it to u* with a
  morphometric log law (`z0 = 0.1 H`, `d = 0.7 H`).
- **Linearity.** Every parameterization is homogeneous of degree 1 in `u0`,
  and `max_velmag` scales with it. Speed-up ratios were verified independent
  of the reference speed to about 2e-6 for the log profile. This holds for any
  fixed profile shape.

The internal logarithmic evaluator retains stability corrections, but the
adapter sets inverse Obukhov length to zero, so public use is neutral only.
The core's former general sensor/profile system was removed; this is not
simply a missing Python binding. The `QES-Public` submodule is reference-only.
See [core provenance](src/qes_core/PROVENANCE.md).

### Full QES capabilities and reuse assessment

| QES flag | Profile | dtcc-qes status |
| --- | --- | --- |
| 0 | Uniform | Not exposed |
| 1 | Logarithmic, including stability corrections | Neutral only |
| 2 | Power law | Not present in the compiled profile path |
| 3 | Canopy: exponential within canopy, logarithmic above | Not present |
| 4 | Data-entry arrays of heights, speeds and directions | Not present |
| 5 | HRRR-specific meteorological profile | Not present |

Full QES also supports multiple sensors, Barnes horizontal interpolation and
time-indexed inputs. A single measured vertical profile needs none of them.
The documentation describes the main user-facing flags 1–4 [1].

Do not copy flag 4. In `QES-Public/src/winds/WindProfilerSensorType.cpp`:

- The angular wrap subtracts an endpoint from itself
  (`dir[ii+1] - 360 - dir[ii+1]`), giving a change of ±360 degrees.
- The logarithmic fit compares speed against height
  (`u_new > site_z_ref[ii+1]`) and tests convergence against the lower
  measurement rather than the upper target.
- The segment index advances only one interval per grid level, so a coarse
  grid that skips several measurement heights selects the wrong interval.
- Above the top knot it extrapolates the last segment's quadratic or log fit
  without bound.

These are source-review findings, not a numerical validation of upstream QES.

## 3. Research findings and model selection

**Established engineering profiles remain useful.** Neutral log and power laws
remain practical approach-flow descriptions; the AIJ guidance uses a power-law
mean profile [2]. RANS boundary-condition work stresses consistency between
velocity profile, turbulence closure and ground treatment [3, 4], so a more
complicated velocity formula alone does not ensure a better incident flow.
Do not import RANS turbulence-boundary formulas as though QES solved the same
equations.

**Measurements are high-value inputs.** Inferred profile parameters depend on
measurement coverage; uncertainty grows with a higher lowest measurement and
fewer observed profiles [5, 6]. Preserve measured vectors instead of fitting a
single analytical law, and make extrapolation visible. Measurements above
roofs do not establish the approaching wind near the ground.

**Urban-canopy profiles are not inlet laws.** Morphology-based models target
the roughness sublayer [7], and LES shows strong local directional sensitivity
and multiple inflection points in urban mean profiles [8]. Applying a
canopy-attenuated profile everywhere and then resolving the same buildings
would count their sheltering twice.

**Atmospheric forcing belongs to a larger model.** PALM's mesoscale nesting
supplies evolving boundary conditions and synthetic turbulence [9]; QES solves
mass conservation without a momentum equation [10]. External atmospheric mean
profiles are acceptable input, but a stability-shaped input adds no buoyancy,
and repeated steady solutions are not a transient simulation.

| Capability | Decision | Qualification |
| --- | --- | --- |
| Existing shifted neutral log | Retain default | Legacy outputs unchanged |
| Tabulated `u(z), v(z)` | Implement | Turning allowed and recorded |
| Power law | Implement | Explicit exponent; no universal urban default |
| Uniform | Implement | Verification use only |
| Wind-sector profiles/exposure transfer | Separate plan | See section 6 |
| Displaced log | Defer | Needs a declared valid height range; never clamp below `d` |
| Monin–Obukhov stability | Defer | Requires more than a mean-profile switch |
| Exponential canopy/RSL models | Defer | Needs unresolved-canopy scope and validation |
| Deaves–Harris or other full-ABL laws | Defer | Tabulation covers advanced input initially |
| Multiple spatial sensors/assimilation | Defer | Separate observation problem |
| Synthetic turbulence/precursor LES | Out of scope | Requires time-dependent dynamics |

## 4. Input contract

### Public API

Add immutable profile specifications in `src/dtcc_qes/profiles.py`, exported
through `dtcc_qes.wind`:

- `LogProfile(speed, direction, reference_height=10, roughness_length=0.1)`.
- `MeasuredProfile(heights, speeds, direction, reference_height, below="error",
  above="constant", interpolation="log_height")`, with classmethods for
  per-height `directions` and for `from_components(heights, u, v, ...)`.
- `PowerLawProfile(speed, direction, reference_height, exponent)`.
- `UniformProfile(speed, direction, reference_height=10)`.

Names and signatures are to be finalized in step 1. A representative call:

```python
profile = wind.MeasuredProfile(
    heights=[2, 5, 10, 20, 40],
    speeds=[2.1, 3.0, 4.2, 5.6, 7.0],
    direction=270.0,
    reference_height=10.0,
    below="log",
)
result = wind.run(city, profile=profile, resolution=2.0, roughness_length=0.1)
```

`wind.run(city, speed, direction, ...)` keeps working unchanged. `speed` and
`direction` become `None` by default, and `reference_height` and
`roughness_length` get sentinel defaults, so omitted and explicit arguments
can be told apart. Exactly one of `speed`/`direction` or `profile=` is
accepted; mixed specifications raise. `LogProfile` carries `roughness_length`
and routes to the legacy path. For other profiles `roughness_length` stays a
`run` argument. The same rules apply to `preview_grid` and dataset requests.

### Tabulated data

- Require at least two positive, strictly increasing heights. Use an analytic
  profile for a single measurement.
- Require equal-length finite arrays and nonnegative speeds. Accept either
  speed/direction or `u, v`, never both.
- Copy the input arrays; mutation by the caller must not alter a prepared
  condition. Preserve the input knots in metadata.
- Permit decreasing speed, interior maxima, calm knots and wind turning. Do
  not enforce monotonic speed or infer missing directions.
- Interpolate the `u, v` components piecewise linearly in `ln z` by default,
  with `interpolation="linear"` (linear in `z`) as an option. For knots at
  10 m and 40 m read at 20 m, linear-in-z is 4.3 % low for both a log law
  (`z0 = 0.1 m`) and a power law (`α = 0.25`). Log-height interpolation is
  within 0.02 % and 1.5 % respectively.
- Locate each height's bracketing interval directly (for example with
  `searchsorted`), so a coarse grid can skip several knots per layer.
- Component interpolation can reduce the speed between knots with different
  directions. This is deliberate; it is not scalar speed/angle interpolation.
- The first version is horizontal only (`w = 0`).

### Extrapolation and grid coverage

| Region | Policies | Default |
| --- | --- | --- |
| Below the lowest knot | `error`; `log` | `error` |
| Above the highest knot | `constant`; `error` | `constant` |

`below="log"` scales both components of the lowest knot by the shifted log
ratio, using the run's `roughness_length`. It preserves the lowest knot's
direction, reaches zero at the ground and matches that knot; a calm lowest
knot stays calm. `above="constant"` holds the highest vector: the default
domain top is 20 m above the tallest roof plus margins, which masts rarely
reach, and the upper layers have little influence on pedestrian flow. Do not
add an inferred high-altitude slope or polynomial tail.

After grid preparation, evaluate at every physical cell-centre height,
including the top layer, and at the reference height. With `error`, fail
before native preparation. Record the number of layers filled by each tail in
metadata. Knots above the domain may still bracket the top layers; they do
not force the domain to grow.

### Reference condition and normalization

Every profile declares a reference height. Derive the reference speed and
direction from the evaluated vector at that height, never from the highest
knot or an average. Use that reference for solver monitors, dataset speedup,
comfort scaling and metadata.

With a zero reference vector, mean-flow solves remain possible, speedup is
undefined (NaN, as today), comfort normalization rejects the input, and the
vector supplies no direction.

Changing amplitude is a uniform positive scaling of every vector. It
preserves shear and turning, and by linearity it rescales the result exactly.
Changing shape or turning requires another solve.

### Native boundary

All profile evaluation happens in Python in float64. Native code receives a
complete per-layer table, not knots or profile parameters:

- `WindCondition` gains an explicit kind, `log` or `layer_table`. `log` keeps
  the existing scalar fields. `layer_table` carries one `u` and one `v` value
  per physical layer (length `nz`), plus the reference speed and direction for
  monitors and metadata.
- Python evaluates the table at the same float32 cell-centre heights the
  native domain uses, `0.5 (z_face[k] + z_face[k+1])` (as in `preview_grid`).
- `ModelInputs::set_condition` checks the kind, the table length, finiteness
  and float32 representability into temporary storage before replacing the
  active condition. A malformed condition leaves the previous one intact.
- `applyWindProfile` dispatches on the kind. The table path writes exactly the
  layers `applyLogProfile` writes (`k = 1 … nz`, `w0 = 0`, everything else
  zero), so ghost and top-face behaviour matches the legacy path by
  construction.
- On the table path, `max_velmag` is 1.2 × the largest speed over all physical
  layers. For monotone profiles that equals the legacy top-layer value. The
  legacy path keeps its arithmetic.
- The table is owned by the condition and the runner. There are no borrowed
  Python buffers or callbacks during native computation.

This keeps one native code path for every new profile kind. Power law and
uniform are Python-only. Under future terrain, QES indexes the log profile by
layers above local ground (`k_mod_sens` in `LogProfile.cpp`). A layer table
supports the same rule, but the terrain plan must still decide it explicitly
(see [terrain plans](ADD_TERRAIN.md)).

### Turning profiles

Turning profiles are supported, not opt-in: each building already takes its
direction from its own roof-level inflow (section 2). Record the maximum
turning across the domain height (`max_turning_deg`) in metadata. Log a
warning when it exceeds a documented threshold. Wakes follow the roof-level
direction even where lower layers turn; document this, along with the
calm-at-roof `atan2(0, 0)` behaviour.

### Turbulence

`turbulence=True` is allowed with every profile kind. QES-Turb derives u* from
the solved field, not the inflow, so the log inflow is no more qualified than
the others. For non-log profiles, metadata records the caveat. Friction
velocity comes from a morphometric log-law conversion of the sampled speed at
`zRef`, and strongly sheared or jet-shaped profiles make that conversion
inconsistent with the applied shear. Do not infer u* from measured shear with
an undisclosed log fit.

### Metadata

Record the profile kind, schema version, the requested inputs, the evaluated
per-layer vectors, the reference vector, the height datum, the
interpolation/extrapolation policies, the layer counts per tail,
`max_turning_deg` and any caveats. Keep the existing legacy metadata keys,
and replace the hard-coded `boundary_layer="neutral logarithmic"` for new
kinds. Accept optional source, location, timestamp and averaging-period
metadata without inventing missing values.

## 5. Implementation steps

### Step 0 — Baseline

Run the existing Python and native suites (wind, sampling, physics, runner,
datasets, serial/OpenMP, both solver precisions) before and after. Do not
regenerate reference cases to hide differences.

### Step 1 — Profile specifications and evaluator

1. Implement the specifications, validation and serialization in
   `profiles.py`. Include `LogProfile` (which resolves to the legacy scalars)
   plus measured, power-law and uniform profiles.
2. Implement one float64 evaluator: `evaluate(profile, heights,
   roughness_length) -> (u, v)`, with tail policies and reference evaluation.
3. Power law is `U(z) = Uref (z / zref)**exponent` for `z >= 0`. Require a
   finite positive exponent and reference height. Use `UniformProfile` for
   zero shear; ship no default exponent.

**Exit:** tests cover knots, midpoints, skipped intervals, both
interpolations, 350/10-degree directions, reversals, calm knots, nonmonotonic
speed, both lower policies, both upper policies, power-law reference
normalization and `z = 0`, bad arrays, invalid references and immutability.

### Step 2 — Native layer-table condition

1. Extend `wind_config.h` and the bindings with the condition kind and the
   owned layer table. Native scalar construction stays valid as `log`.
2. Validate atomically in `ModelInputs::set_condition`.
3. Dispatch in `applyWindProfile`, including the table-path `max_velmag`.
4. Route the table's reference speed to the monitor normalization in
   `wind_runner.cpp`.

**Exit:** the table is copied exactly into the expected faces on uniform and
nonuniform grids. A malformed table leaves a prepared condition intact.
Sequential conditions match fresh runners. Legacy reference velocities are
bitwise unchanged. A table holding the legacy log values agrees with the
legacy path within float32 rounding.

### Step 3 — Python run and preview integration

1. Resolve legacy scalars or `profile=` into one canonical condition before
   geometry preparation in `wind.run` and `preview_grid`. The legacy path
   keeps `_validate_condition`, including the log-ratio check; new kinds are
   not subjected to it.
2. Evaluate the profile at the final cell-centre heights after
   `prepare_domain`, enforcing coverage before native preparation.
3. Write the metadata (section 4) and the turbulence caveat.

**Exit:** API tests cover old and new calls, mixed-argument errors,
preview/run agreement, coverage failures, metadata serialization, a turning
profile with buildings, a calm-at-roof case and failed-condition recovery.
One test at two speeds with a non-log tabulated shape confirms that speedup
is independent of the reference speed.

### Step 4 — Dataset support

1. Add a discriminated, JSON-serializable `profile` field to `QESWindArgs`.
   Detect conflicts with explicitly supplied scalar fields using pydantic's
   `model_fields_set`; omitted defaults never conflict.
2. Validate the profile before fetching city data; check coverage again
   against the final grid before solving.
3. Include the complete profile and policies in request identity, cache
   inputs and exported metadata.
4. Compute speedup from the same evaluated reference as `wind.run`.

**Exit:** dataset and direct runs agree for identical geometry, grid and
profile; old requests are unchanged; distinct profiles never share cached
results; invalid profiles fail before remote data is fetched.

### Step 5 — Verification, documentation and release

1. Run the focused suites plus the serial/OpenMP, precision and sanitizer
   coverage relevant to the new owned arrays.
2. Compare analytic power-law and densely tabulated representations on empty
   and building domains, allowing for the declared interpolation error.
   Check that empty flat domains have the expected zero divergence.
3. Measure profile-evaluation cost relative to the solve.
4. Update README/API documentation, dataset examples, comfort guidance and
   core provenance. Add one measured-profile example and one power-law
   example, both showing the applied profile and its reference.
5. Ship the new kinds as experimental and state that they have no independent
   physical validation.

**Exit:** reproducible verification evidence; documented supported versus
experimental scope.

## 6. Follow-up plans

These are deliberately outside this plan and need their own write-ups:

- **Wind sectors and exposure transfer.** Profile-per-sector specifications
  using the comfort module's direction and tie conventions. Sector direction
  comes from the reference vector. Keep `comfort.log_law_transfer` and add
  any sector-aware transfer only with explicit station/site roughness,
  reference and blending heights. Group regimes with different shear or
  turning into separate solves rather than pooling them under one speedup
  field. The existing comfort functions already accept one reference speed per
  direction, so fixed-shape profiles work with them as soon as this plan
  ships.
- **Independent physical validation.** Compare measured-profile predictions
  with a wind-tunnel or field dataset that documents its approach profile. Keep
  input profiles separate from withheld evaluation data. Fix the tolerances
  before running. Vary measurement spacing, tails and grid resolution
  separately. Evaluate local vector errors, pedestrian speeds, direction and
  divergence, not just aggregate error.
- **Vegetation.** Upstream canopy code fits logarithmic flow above crowns.
  [Vegetation support](ADD_VEGETATION.md) must not assume every incoming
  profile is logarithmic.
- **Displaced log, stability, canopy/RSL laws.** As deferred in section 3.

This plan adds no temperature/buoyancy transport, time-resolved gusts, spatial
data assimilation, inlet-face constraints, native meteorological file I/O or
terrain support. Those may reuse the tabulated profile interface.

## 7. Sources

The implementation choices above are engineering decisions for dtcc-qes, not
claims that the cited papers prescribe this API. Some publisher full texts
were unavailable; those findings rely on accessible abstracts and indexed
article excerpts, without importing unverified equations or parameter values.

1. [QES-Winds documentation — initial wind field and sensor profiles](https://qes-documentation.readthedocs.io/en/latest/QES-Winds.html).
2. [Tominaga et al. (2008), AIJ guidelines for practical applications of CFD to pedestrian wind environment around buildings](https://www.sciencedirect.com/science/article/pii/S0167610508000445).
3. [Richards and Hoxey (1993), Appropriate boundary conditions for computational wind engineering models using the k-epsilon turbulence model](https://www.sciencedirect.com/science/article/pii/0167610593901247).
4. [Application of a comprehensive atmospheric boundary layer model to a realistic urban-scale wind simulation (2024)](https://doi.org/10.1016/j.buildenv.2024.111330), [institutional manuscript](https://dipot.ulb.ac.be/dspace/bitstream/2013/373044/3/Srikumar2024.pdf).
5. [Picozzi et al. (2025), Probabilistic framework for the calibration of mean wind profiles in urban areas](https://doi.org/10.1016/j.jobe.2025.112720).
6. [Calibration of Mean Wind Profiles Using Wind Lidar Measurements (2023)](https://www.mdpi.com/2076-3417/13/8/5077).
7. [Gao et al. (2024), Development of a morphology-based wind speed model in the urban roughness sub-layer](https://doi.org/10.1016/j.jweia.2024.105871).
8. [Duró et al. (2026), Impact of Wind Direction on Flow and Turbulent Statistics Over a Realistic Urban Area: A Large-Eddy Simulation Study](https://link.springer.com/article/10.1007/s10494-026-00790-8).
9. [PALM 25.10 — mesoscale nesting](https://docs.palm-model.org/25.10/Guide/LES_Model/Modules/Mesoscale_nesting/).
10. [Bozorgmehr et al. (2025), Improving the Performance of a Reduced-Order Mass-Consistent Model for Urban Environments and Complex Terrain With a Higher-Order Geometrical Representation](https://doi.org/10.1029/2024MS004494), [author summary](https://gibbs.science/test/publication/2025b/).

# Unified campaign V2: targeted correctness and usability improvements

Date: 2026-11-11. Status: proposed implementation and qualification plan,
revision 2.

Base: `main` at `a833c4d`. The experimental covariance model exists only on
`research/pedestrian-wind-campaign` at `4eb119d`; Stage D starts there. The two
branches have diverged (33 commits are research-only and 5 are main-only), so
recheck both identities before each stage. The filename intentionally follows
the requested `UNIFIED_CAMPAGNE_PLAN_V2.md`.

## 1. Decision and purpose

Build four bounded improvements, in this order:

1. **Physical turbulent kinetic energy (`physical_k`).** Derive it explicitly
   from the final covariance, next to QES's internal `tke`.
2. **A compact result-quality report.** Build it from evidence the package
   already records.
3. **Geometry-resolution witnesses.** Report erased passages and false
   connections in the solver's actual solid mask.
4. **Covariance-model verification.** Verify the experimental
   `bounded_consistent_v1` limiter, and decide whether to port the model to
   `main` as an opt-in model.

Stages A–C are Python-only changes on `main`. They need no adaptive-policy
requalification, and each can ship on its own once its gates pass. All native
work is collected into one optional PR with a single requalification (§2.2,
§8). This plan authorizes no default covariance promotion. It makes no new
claim about pedestrian wind, gust or comfort accuracy.

The [bounded campaign report](validation/UNIFIED_CAMPAIGN_BOUNDED_RESULTS.md)
is the starting evidence:

- S1 did not establish acceptable endpoints.
- S2 failed its registered continued-work screen.
- S3 passed numerical and mass checks, but its measured H10 cost projected to
  about 82 minutes for the minimum endpoint sequence. Only about 47 minutes of
  normal work remained. That is a feasibility estimate, not proof of physical
  nonconvergence.

Fractional momentum, tower F, transfer, refinement, new closure fitting and
model promotion remain conditional on the original unmet prerequisites. Keep
all old failures, immutable records and per-slot balances. V2 does not consume
or reset any unused S1, S2, S3 or E balance.

## 2. Baseline and constraints

### 2.1 What exists where

| Area | On `main` | Research branch only | V2 work |
| --- | --- | --- | --- |
| Covariance validity | `_statistics._stress_validity`: chunked float64 eigensolver, 32·eps(float32) relative tolerance, raw tensors kept | — | Reuse for `physical_k` and the report |
| Derived statistics | `_streamwise_std`, which clamps tolerance-accepted negative variance to zero; `turbulence_intensity` | — | Add `physical_k` with the same convention |
| Turbulence output | `TurbulenceFields`: stress, `tke`, computed/capped/valid masks | Viscosity, production-scale and spectral-scale arrays | `physical_k` on result and sample types |
| Sampling | `sample_points(..., diagnostics=True)`, `SamplingSupport`, reason codes, retained contributor validity | — | Aggregate in the report |
| Qualification | `WindResult.qualification`, solver record, divergence diagnostics | — | Build the report on it |
| Covariance model | Legacy only | `Turbulence(covariance_model='bounded_consistent_v1')`, `covariance_model.h` with coupled production scaling and spectral limiting | Verify, then decide whether to port |
| Geometry | `preview_grid`/`GridPreview` (Python preparation, no native mask); `near_contacts` (STRtree, pairs closer than one cell); validation-only `sampling_geometry.summarize` | — | Witnesses on the solver mask; two-cell gap warnings |

`main` ported the Surrey benchmarks and frozen stress replay without the
research runtime APIs (`292f659`).

### 2.2 Cost of native changes

CMake computes `solver_policy_revision` over:

- every `.h` and `.cpp` file under `src/qes_core` and `src/cpp`;
- both CMakeLists files;
- the compiler, flags and fp-contract setting.

Any edit to these, including a new Python binding, makes adaptive runs return
`unqualified_build` until the build is requalified. Requalify with
`tools/check_policy_compatibility.py`, following
`docs/solver-control-requalification.md`, then update
`pedestrian_qualification.h`. Tests under `tests/native` are not hashed.

The 24 policy workers use only rectangular box footprints. Native changes that
affect concave or holed footprints therefore also need native contact tests
(`tests/native/check_contacts.cpp`).

Consequences for this plan:

- Stages A–C stay Python-only.
- The covariance port and the prepared-mask binding (§6.2) form one native PR
  with one requalification.

### 2.3 Facts the design relies on

- QES marks a horizontal cell as building when its centre lies inside a
  footprint ([PolyBuilding.cpp:234](src/qes_core/winds/PolyBuilding.cpp#L234)).
- No current API returns the native solid mask without a solve.
  `preview_grid` stops before `WindRunner.prepare`, which returns nothing.
- The spectral limiter in `bounded_consistent_v1` is **not numerically
  identical** to the campaign's uniform component-bound limiter. The campaign
  supports the correction's rationale, but its numerical, trade-off and timing
  receipts do not transfer to the spectral implementation.
- The research-branch metadata already records the model's measured outcome:
  A elevated correlations degrade, and measured D turbulence is unchanged.
- `_city.py` imports Shapely and pyproj directly, but both currently arrive
  only through `dtcc-core`. Stage C relies on Shapely 2's vectorized API.

Source locations:

- [Statistics](src/dtcc_qes/_statistics.py), [results](src/dtcc_qes/result.py),
  [turbulence specification](src/dtcc_qes/turbulence.py),
  [wind assembly and preview](src/dtcc_qes/wind.py).
- [City preparation and near contacts](src/dtcc_qes/_city.py),
  [canonical footprints](src/dtcc_qes/_footprints.py),
  [validation geometry summaries](validation/aij/sampling_geometry.py),
  [sampling contracts](docs/SAMPLING_DIAGNOSTICS.md).
- Research branch only: `src/qes_core/dtcc/api/covariance_model.h`,
  `src/qes_core/dtcc/turbulence.cpp`, `src/qes_core/winds/TURBGeneralData.cpp`.

The new module and API names below are proposals; none of them exist yet.

## 3. Shared contracts

- Preserve physical coordinates, units, frames and every requested observation
  ID.
- **Raw tensors are never modified.** Invalid or unavailable derived quantities
  return NaN, with explicit evidence. They never become calm values.
- **One sign convention for derived statistics.** A negative value accepted by
  the existing PSD tolerance is roundoff and is clamped to zero, as
  `streamwise_std` already does. A value outside the tolerance is invalid and
  becomes NaN.
- **Zero is valid.** Finite zero covariance is valid, including at zero mean
  speed. `physical_k` does not require a wind direction; streamwise
  turbulence intensity does.
- **Validity is recomputed.** Derived values recompute validity from the
  current arrays. Stored masks and native counts are labelled solve-time
  snapshots.
- **Contributor invalidity propagates.** A sample retains the validity of every
  positive-weight source contributor. A valid interpolated tensor cannot erase
  an invalid source.
- **Feature-off paths are free.** They allocate no new full-grid fields and
  perform no new full-grid scans or geometry analyses.
- **Bounded memory.** Result and sample arrays are owned and contiguous.
  Helpers reuse the existing 65,536-tensor chunking, so scratch memory beyond
  the output stays bounded.
- **One authority each.** There is one solver record and one covariance
  classifier. Report views consume them and implement no acceptance
  thresholds of their own.
- **Versioning.** New numerical behaviour gets a distinct provenance and cache
  identity. Additive report schemas carry versions, and readers keep
  unavailable old fields.

## 4. Stage A — explicit physical turbulent kinetic energy

### What users get

```python
result = wind.run(city, ..., turbulence=Turbulence())
k = result.physical_k            # m²/s², half the final covariance trace; NaN where unusable
qes_k = result.turbulence.tke    # QES internal energy before anisotropy scaling
probe = result.sample_points(points, "linear")
probe.physical_k                 # same definition, with contributor evidence
grid = result.to_dtcc(include_physical_k=True)
```

### Why

QES's internal `tke` and half the final covariance trace differ after
anisotropy scaling and capping, and also after spectral scaling in the
experimental model. Treating them as interchangeable invalidates model
comparisons and downstream calculations. This API correction is worth making
even though no turbulence model is promoted. In incoming-turbulence mode,
`tke` is already defined as half the final trace, and the two quantities
agree.

### Definition and masking

For stress order `(xx, xy, xz, yy, yz, zz)`, computed in float64:

```python
k = 0.5 * (Rxx + Ryy + Rzz)
usable = coverage & current_covariance_valid
physical_k = where(usable, maximum(k, 0), nan)   # negatives here are within tolerance
```

- **Full results:** `coverage = computed & ~solid_mask`, the same rule as
  `WindResult.streamwise_std`.
- **Samples:** `coverage = valid & contributors_valid`, the same as
  `_SampleStatistics.streamwise_std`, but without the direction requirement.
  Zero-speed samples therefore keep a finite value.
- **Scope:** the property lives on `WindResult`, `WindSample` and
  `WindPointSample` only. `TurbulenceFields` has no cell flags, so it cannot
  apply the solid exclusion. One name gets one masking rule.
- **Missing turbulence:** raise the same `ValueError` as `streamwise_std`.

### Implementation

- Add `_physical_k(stress, coverage, *, validity=None)` to `_statistics.py`,
  chunked like `_streamwise_std`.
- The optional precomputed `validity` lets `to_dtcc` classify tensors once for
  all derived fields.
- The property lives on `WindResult` and on the `_SampleStatistics` mixin.
- Do not cache it against mutable arrays, and do not compute it during solves.

Add `to_dtcc(include_physical_k=False)`. The field carries:

- units `m^2/s^2`;
- its definition and masking policy;
- the existing provenance string.

Default export field sets stay unchanged. Docstrings and examples show both
quantities and explain why they can differ.

### Acceptance

- **Analytic tensors:** diagonal and rotated tensors, nonzero off-diagonals,
  and calm zero (valid, k = 0).
- **Invalid inputs:** indefinite tensors with positive trace give NaN;
  nonfinite input gives NaN.
- **Tolerance edge:** a negative trace inside the tolerance gives 0.
- **Coverage:** post-construction mutation is reclassified; solid and
  uncomputed cells give NaN.
- **Sampling:** an invalid contributor under a valid interpolant gives NaN;
  zero-speed samples stay finite.
- **Incoming-turbulence oracle:** `physical_k` equals `tke`, within float32
  storage rounding, on computed, valid fluid cells.
- **Export:** round trip, units and metadata are correct; the default export
  is unchanged.
- **Off path:** existing fields and queries match the baseline exactly.

Benchmark the helper separately from the solve at 3M cells. The existing
eigensolve dominates. Target scratch below 64 MiB, excluding inputs and the
24 MB float64 output. Validity plus tolerance is about 27 MB.

Effort: about one engineering day.

## 5. Stage B — result-quality report

### What users get

```python
report = result.quality_report()                       # scalar evidence only
sample = result.sample_points(points, "linear", diagnostics=True)
report = result.quality_report(sample=sample)          # adds sampling evidence
print(report.summary())
payload = report.to_dict()                             # strict JSON
```

### Why

The package already records useful numerical, sampling and model evidence, but
users must assemble it from several places. A concise report makes failed
coverage and incomplete assessment visible without implying a new accuracy
qualification.

### Design

Add `quality.py` with an immutable, schema-versioned `QualityReport` and a
`WindResult.quality_report(sample=None)` convenience wrapper.

- **Sources:** `result.qualification`, the single public interpretation of the
  metadata, plus `result.diagnostics`, the turbulence metadata and an optional
  existing `SamplingSupport`.
- **No field access:** the report never reads full fields and never resamples.
  Its cost is independent of grid size.

Contents:

- **Solver:** execution and termination, legacy convergence, adaptive
  assessment and scope, and exclusions.
- **Divergence:** max and RMS in s⁻¹, the assessed cell count, exclusions and
  the top-band status. Keep the currently unassessed highest physical layer.
- **Turbulence, as a solve-time snapshot:**
  - model and version, and experimental status;
  - computed, capped and invalid counts;
  - reference speed and height;
  - the definitions of both `tke` and `physical_k`.
  - The current field state is available only through derived properties.
- **Sample, if given:**
  - requested, valid, invalid and unsupported counts, plus per-reason counts;
  - reasons can overlap, so their sum is not the invalid count;
  - support evidence is reported unavailable when the sample was taken
    without diagnostics;
  - the report records that samples are owned snapshots whose source support
    cannot be refreshed from an interpolant.
- **Missing evidence:** unknown historical metadata is reported as unavailable,
  with a reason.

Serialization converts unavailable or nonfinite values to `null` with a reason,
and uses `allow_nan=False`. The report has no single numerical confidence
score. It never marks a simulation physically validated because its solver
completed.

Not in v1: height-band coverage and energy summaries, full-field scans, and
volume-weighted summaries on stretched grids. Each needs its own design for
band edges, denominators, weighting and O(N) cost, and should wait for a
concrete user request.

### Acceptance

- **Legitimate states that look contradictory:** a completed solve with poor
  coverage, valid calm tensors, an invalid contributor under a valid
  interpolation, unknown historical metadata, missing turbulence, and an
  absent top-layer assessment.
- **Snapshot independence:** editing the result afterwards does not change an
  existing report.
- **Unchanged sampling:** values and validity are unchanged; the report always
  produces strict JSON.
- **Cost:** benchmark the default report below 1 MiB of allocation,
  independent of grid size. Metadata size scales with building count, not
  cells.

Effort: about one engineering day.

## 6. Stage C — geometry-resolution witnesses

### What users get

```python
preview = wind.preview_grid(city, resolution=2.0)
early = wind.check_geometry(city, preview, points=points, routes=route_pairs)
result = wind.run(city, ...)
report = wind.check_geometry(city, result, points=points, routes=route_pairs, heights=(2.0,))
print(report.summary())
```

`check_geometry` takes the same geometry options as `run`: `footprints`,
`height_policy` and `terrain`. It returns witnessed cells, points and routes,
physical and represented widths, the examined scope and a hash of the examined
solid mask.

### Why

A grid can preserve sampled values yet join physically disconnected pedestrian
spaces or erase a passage. Global volume fractions and connectivity counts
miss these local failures; AIJ E's connectivity rejection is the archived
example. Catching them before results are interpreted has direct value.

### 6.1 Python-only tier on `main`

- **On a `GridPreview` (before the solve):** physical checks only.
  - Extend `near_contacts` from pairs closer than one cell to pairs closer than
    two cells, filtered for vertical overlap using base and roof intervals.
  - Flag critical points inside, or within one cell of, a footprint.
  - Flag route pairs that are physically disconnected at the slice height.
  - Raster witnesses report `unavailable` with reason
    `solver_mask_not_prepared`.
- **On a `WindResult` (after the solve):** exact witnesses against
  `result.cell_flags`, the solver's own mask.

### 6.2 Prepared-mask binding (native PR)

Add a binding that returns cell flags after `WindRunner.prepare`, without
iterating. `preview_grid(..., include_solid_mask=True)` then carries the
native mask, at the cost of one native preparation, and `check_geometry`
produces exact witnesses before any solve. Tests must show that the preview
mask hash equals the hash of the subsequent solve's mask. The binding is
native, so it ships only in the batched native PR (§8).

### Algorithm

For each requested height z (default: pedestrian height), use the layer that
contains z:

1. **Physical free space.** Rebuild the canonical footprints with the same
   Python preparation `run` uses, in the result's local frame.
   - A footprint is active when `base <= z < roof`.
   - Free space is the domain rectangle minus the union of active footprints;
     its components are the polygons of that MultiPolygon.
   - A valid polygon has a connected interior. Point and diagonal contacts
     therefore separate components automatically, so zero-width contacts never
     count as passages.
   - Small components are retained.
2. **Grid alignment.** Check that the grid's origin, resolution and shape match
   the preparation. A mismatch makes the slice `unavailable`.
3. **Labels.** Assign each fluid cell centre (flags other than 0 and 2) to a
   physical component with `STRtree.query(points, predicate="within")`. A
   centre on a component boundary is labelled unknown.
4. **Self-check.** Under QES's centre rule, a cell is solid exactly when its
   centre lies inside an active footprint. Any disagreement makes the slice
   `unavailable` with reason `mapping_not_reproduced`. The Python geometry is
   an oracle checked against the solver mask, never a substitute for it.
5. **Witnesses:**
   - `false_join`: two face-adjacent fluid cells with different physical
     labels. This is a vectorized comparison of shifted label arrays.
     Diagonal adjacency never counts.
   - `disconnection`: one physical component whose fluid cells lie in two or
     more raster components. Raster components come from 4-connected
     labelling of the slice over flat index arrays.
   - `erased_space`: a physical component with at least one cell of area and
     no fluid centre.
   - `closed_passage`: for each pair with a gap below two cells, examine the
     cells crossed by the shortest line between the two footprints. If all are
     solid, the passage is closed even when a detour keeps the components
     connected. A represented width below two cells is an `under_resolved`
     warning. It is a resolution warning, not a universal physical rejection
     threshold.
   - **Points:** whether the containing cell is solid, horizontal clearance to
     the footprint union, and bounded passage widths along x and y.
     `bounded_passage` moves from `validation/aij/sampling_geometry.py` into
     the package.
   - **Routes:** physical connectivity (same physical component) compared with
     represented connectivity (same raster component). A mismatch is a
     witness.
6. **Statuses:** `issue`, `no_issue_in_examined_scope`, `unavailable` (with
   reason) and `budget_limited`. Each report records the examined heights,
   layers and footprints.

Scope of the first version:

- **Terrain:** flat terrain only. Terrain-flagged cells make the slice
  `unavailable`.
- **Roof-crossing footprints:** a footprint whose roof or base lies strictly
  inside the examined layer is reported as `roof_crossing`. Witnesses
  touching its cells are reported `unavailable`.
- **Slices:** horizontal slices only; a later 3D scope uses six-face
  connectivity.
- **Preparation paths:** both the strict and the `Footprints` paths are
  covered. Geometry that fails the self-check is `unavailable`.

### Cost and limits

- STRtree construction is O(B log B) over B footprints.
- Each slice needs one union, plus point queries, label comparisons and
  labelling that are linear in the slice's cell count.
- There are no per-cell polygon overlays, no Python object per cell, and no
  dense adjacency matrices.

Initial limits:

- 64 critical points or routes;
- 4 slices;
- 30 s of analysis, excluding preparation, which is reported separately.

Reaching a limit gives `budget_limited`, never a passing report. Limits change
only through explicit options.

### Acceptance

Fixtures cover:

- aligned and oblique narrow gaps;
- diagonal corner contacts;
- disconnected pockets within one cell;
- holes and courtyards;
- touching and overlapping prisms;
- elevated bases and roof-crossing layers;
- shifted origins and domain boundaries;
- unsupported terrain.

Compare against analytically known routes, with SciPy `ndimage.label` and
face connectivity as a test-only oracle. Reuse the archived E false-join
witnesses and the A, B and D passing layouts from archived masks. Fixture wind
solves are limited to tiny grids. IDs and ordering must be deterministic.

The checks never refine the grid, move origins, alter buildings, relocate
receptors or search for a passing grid. They present evidence so the caller
can make an explicit new geometry decision. This is a geometry diagnostic. It
is neither fractional-cell momentum admission nor validated pedestrian
accessibility.

Effort: Python tier 2–3 days. Prepared-mask binding about half a day, plus the
shared requalification.

## 7. Stage D — covariance-model verification and port decision

### Why

Coupled energy/viscosity scaling and uniform final tensor scaling address
reproduced realizability failures. In the campaign, mean fields were unchanged
and strict covariance coverage improved. However:

- the model exists only on the research branch;
- its spectral limiter differs from the campaign's component bound;
- its recorded outcome shows no predictive gain.

Promotion is out of scope, so the decision this stage informs is narrow:
**should `bounded_consistent_v1` reach `main` as an opt-in experimental
model?** The evidence is sized to that decision.

### Algorithm to retain and verify

For uncapped energy k0, capped internal energy kc and uncapped viscosity nu0:

```text
r = min(1, kc / k0), for finite k0 > 0
r = 1, for the explicitly supported k0 = kc = 0 case
nu_eff = r * nu0
R1 = r * R_uncapped
R2 = existing qualified anisotropy/rotation construction applied to R1
alpha = min(1, B / spectral_radius(R2))
R_final = alpha * R2
```

- **Explicit branches:** use explicit branches for zero radius and the
  supported calm or zero-bound cases. Invalid inputs propagate diagnostic
  invalidity.
- **Preserved definitions:** keep the internal energy and dissipation
  definitions.
- **Limits of uniform scaling:** it preserves a PSD input, but it cannot repair
  a tensor that was already indefinite before limiting.
- **Inactive shortcut:** the helper first bounds the spectral radius by the
  maximum absolute row sum. When that bound is at most B, alpha is exactly
  one and no eigensolve is needed.
- **Eigensolver:** otherwise use the established scaled symmetric 3×3 solver
  with a float64 independent oracle. Do not use an unchecked closed-form
  cubic, a generic nonsymmetric eigensolver or eigenvalue clipping.
- **Native constraints:** work stays in the existing native cell loop with
  fixed-size local storage. There are no per-cell heap allocations or Python
  callbacks, and the existing OpenMP ownership and determinism are kept.

### D1 — verification on the research branch

No new wind solves are needed.

1. **Freeze and reproduce.** Freeze the current Python, native, source and
   package identities, and reproduce the existing covariance tests.
2. **Limiter unit tests:**
   - rotation covariance of the limiter alone;
   - nearly repeated eigenvalues;
   - tiny and large magnitudes;
   - the exact row-sum shortcut boundary (row sum equal to B);
   - tolerance-edge inputs;
   - zero mixing length, including zero length with nonzero viscosity, which
     must give explicit invalidity;
   - the calm k0 = kc = 0 case.
3. **Offline replay.** Replay the saved source tensors through the legacy,
   coupled-only, final-limit-only and combined paths. Run both final-limit
   formulations, spectral and the historical
   `alpha_component = min(1, B / max(abs(Rij)))`, without tuning
   coefficients. Report:
   - stage-by-stage validity on the original support;
   - recovered and lost valid queries;
   - `physical_k` differences;
   - spectral versus component differences, including under coordinate
     rotation.

The component rule stays offline for attribution only. It does not become
another public model option.

Hardening fixes found during D1 are made on the research branch. They reach
`main` only through the port.

### Port decision

Port only when all of the following hold:

- every replayed computed tensor is PSD under the existing tolerance;
- no previously valid query is lost;
- the spectral and component differences are reported and explained.

Otherwise stop, record the failed gate and diagnose before any further
measurement. Do not adjust gates retrospectively.

The port runs in the native PR (§8). It brings to `main`:

- `covariance_model.h`;
- the `Turbulence.covariance_model` field and its metadata;
- the optional `TurbulenceFields` arrays;
- the tests.

Gates within a paired build:

- **Legacy path:** the legacy model is bitwise identical to `main` before the
  port.
- **Unchanged under v1:** mean velocity, flags, solver counters and
  internal-energy fields under `bounded_consistent_v1` match legacy exactly.
- **PSD:** final tensors satisfy the PSD tolerance on every computed cell.
- **Build checks:** serial/OpenMP parity, sanitizers and deterministic output.
- **Memory:** extra diagnostic grids stay opt-in, and the report separates
  allocated array bytes from allocator RSS.

### D2 — public qualification, only when promotion is proposed

Do not run D2 until someone proposes promotion. Its specification is
reserved here:

1. **Matched current binaries:**
   - A/B pedestrian and elevated observations;
   - D measured components;
   - Surrey backgrounds and coarse transitions.
   - Primary IDs are preserved. Report recovered samples, correlation changes,
     physical-k and component RMSE, and coverage separately. A lower pointwise
     absolute error does not erase correlation losses or supply measurement
     uncertainty.
2. **Whole-workflow benchmark:** complete public solves plus sampling in
   alternating fresh workers, including all warmups, failed runs, output
   extraction and diagnostic options. Use the existing 1.3× complete-solve
   cost envelope as the initial screen.
3. **Uncertainty assessment:** assess current-epoch perturbations and
   measurement uncertainty against the existing frozen protected margins.
   Missing eligible evidence gives `inconclusive`. Equivalence is never
   inferred from a nonsignificant difference, and deterministic timing
   repetitions are not independent physical observations.

Fine Surrey transitions exceed the 3M-cell cap. They need a separately costed,
compiled larger-grid preflight, and coarse evidence never qualifies them.
Production promotion stays on hold until precision, coverage, the applicable
release checks and the exact implementation identity all qualify. No
automatic default switch is planned.

## 8. Delivery order, budgets and stop rules

| # | Deliverable | Branch | Native edit | Effort | Gate before proceeding |
| --- | --- | --- | --- | --- | --- |
| PR1 | `physical_k`, masking, optional export, examples | `main` | No | ~1 day | Analytic, sampling and incoming-mode tests; 3M-cell benchmark |
| PR2 | Quality report, strict JSON, examples | `main` | No | ~1 day | Evidence semantics, no field access, snapshot independence |
| PR3 | Geometry witnesses, Python tier | `main` | No | 2–3 days | Analytic and SciPy oracle fixtures, self-check, archived E witnesses |
| D1 | Limiter tests and offline replay | research | Unhashed tests only | 1–2 days | Port decision (§7) |
| PR4 | Native batch: covariance port and/or prepared-mask binding | `main` | Yes | 2–3 days plus requalification | Paired-build invariants, policy compatibility pass, updated `pedestrian_qualification.h` |
| D2 | Public covariance qualification | `main` | — | Evidence-dependent | Only on a promotion proposal |
| Review | Accepted independent pieces | `main` | — | ~1 day | Applicable package, native and policy checks |

PR4 is optional. It contains whichever of its two parts is wanted; if neither
is wanted, it is skipped. These are planning estimates. Update the findings and
the next step in this plan after each deliverable. When a line's gate fails,
stop that line without blocking independent accepted work.

Budgets:

- **PR1–PR3** are ordinary engineering PRs: tests, one benchmark each, and the
  regression threshold below. They keep no worker-minute ledger.
- **D1 replay:** 15 worker-minutes, reusing frozen means and source tensors.
- **PR4 qualification:**
  - the policy compatibility run (24 frozen S7 workers);
  - 30 worker-minutes of native qualification;
  - every failed attempt counts;
  - larger release builds get a separate measured budget.
- **Geometry archive replay:** zero new validation-case wind solves. Only
  tiny-grid fixture solves are allowed.
- **D2:**
  - at most 40 fresh mean-solve invocations at 120 s each, plus six targeted
    diagnostics at 300 s each, for a 110 worker-minute maximum;
  - all warmups and repeats count toward the 40;
  - freeze the exact condition, arm and repetition manifest before launch;
  - if the required coverage does not fit, split the claim or revise the
    allocation prospectively.
- **Experiment caps:**
  - 3M physical cells;
  - 8 GiB self RSS per worker;
  - 2 GiB of new staging;
  - serial workers with four OpenMP threads and one BLAS thread for comparable
    timing;
  - other supported thread modes tested separately.

These ceilings authorize planning, not a hidden implementation campaign. They
exclude a fine-grid cap promotion, a new precision population, external
simulation and the full release matrix. Each of those needs its own scope,
cost and stop rules first.

**Regression threshold.** For feature-off and metadata-only paths, investigate
a median regression that exceeds both 5 % and 0.01 s in a matched, balanced
timing epoch. This is an engineering threshold, not a confidence interval or a
physical equivalence margin.

- Disabled paths add no per-cell storage.
- Record raw times, median and p95, peak RSS, explicit array and native bytes,
  package hashes and failures.
- Never select favourable repetitions or compare unrelated timing epochs.

## 9. Verification, packaging and retained research

**Tests.** Run the affected tests first. Add tests only for meaningful
numerical, semantic, ownership or performance risks, and avoid tests that
merely restate implementation formulas.

**Python-only PRs** need installed-wheel and export smoke coverage.

**The native PR** additionally needs:

- serial and OpenMP parity, sanitizers and feature intersections;
- packaging and installed-runtime tests;
- adaptive-policy requalification against the exact candidate. Old policy
  receipts never transfer automatically.

**Dependencies.**

- Declare `shapely>=2.0` and `pyproj` as direct dependencies in
  `pyproject.toml`, with a pinned supported range. The package already imports
  both directly, and Stage C uses Shapely 2's vectorized API.
- SciPy and PyAMG stay in research and test tooling unless a separate
  dependency decision justifies more.

**Retained research.**

- Keep independent pressure, force and checkpoint fixtures as developer
  regression assets wherever they exercise shared code.
- Do not port the S1 zero-increment repair to the production QES multiplier
  iteration until its state variables and algorithms are shown to be
  equivalent.
- Public SIMPLEC, Anderson, AMG momentum and new closures remain research work
  that needs new feasibility evidence.

**PR contents.** Each PR states:

- why the change is needed;
- the exact user-visible behaviour;
- the algorithm and its invariants;
- comparisons with the current baseline;
- performance and memory receipts;
- failed or unrun checks;
- remaining limitations.

The final V2 review reports four things separately: correctness and usability
improvements, any demonstrated predictive gains, runtime costs, and the
comfort claims that remain unsupported.

## 10. First implementation task

Branch from `main` at `a833c4d`. In order:

1. Implement `_physical_k` with the shared sign convention and an optional
   precomputed validity argument.
2. Add the property to `WindResult` and `_SampleStatistics`.
3. Write the analytic, strict-contributor and incoming-mode tests.
4. Benchmark at 3M cells.
5. Add the export option and the examples.

Then record the results here and start PR2. Do not restart the closed momentum
campaign as part of these changes.

## Implementation log (2026-11-11)

Implementation is isolated at `/private/tmp/dtcc-qes-unified-v2` on
`implement/unified-campaign-v2`, from main `a833c4d`. The original research
worktree and its untracked campaign records are preserved.

### PR1 / Stage A

Implemented current-array `physical_k` on full results and both sample types,
strict contributor masking, optional DTCC export, and documentation. The
3M-cell receipt is `docs/data/unified-v2/physical-k.json`: median 0.713 s,
p95 0.763 s, traced scratch 33,882,592 bytes beyond the 24 MB output (<64 MiB).
No solve-time allocation or scan was added. Analytic/sampling/export and
existing turbulence tests: 67 passed, 8 toolchain-specific skips.

Plan corrections before PR2: incoming turbulence is absent on main (also a
research-only API), so its native oracle belongs in D1, not PR1. A negative
trace cannot pass the current 3D relative PSD tolerance: at least one positive
eigenvalue dominates the two allowed negative ones. The helper still clamps
accepted energy to zero consistently; tests exercise negative eigenvalue
edges and valid zero rather than fabricating a valid negative-trace tensor.
PR2 retains its metadata-only scope; no change to its intended behavior.

### PR2 / Stage B

Added an immutable schema-v1 quality snapshot from the existing qualification,
scalar diagnostics, turbulence metadata and optional sampling support. Missing
and nonfinite evidence has null values plus path-specific reasons. The default
report never accesses field arrays. Tests cover calm covariance, bad sampling,
unknown metadata, strict JSON and independent snapshots. Performance receipt:
`docs/data/unified-v2/quality.json` (metadata-only cost, <1 MiB allocation).

Next-step assessment: Stage C must mirror actual production preparation,
including explicitly flattened bases, rather than infer elevated solids from
input surfaces. Roof-crossing layers will conservatively be unavailable as a
whole in v1; this retains evidence without certifying unaffected connectivity
through an ambiguous layer. Terrain cells and mapping disagreement likewise
cannot pass. The prepared-mask binding remains optional native work.

### PR3 / Stage C

Added `wind.check_geometry`, immutable strict-JSON geometry reports, four-face
labels, free-space and mask self-checks, deterministic cell/point/route
witnesses, closed-passage and two-cell warnings, source scope and mask hashes.
Both preparation paths use the existing canonical native-prism inputs.
`bounded_passage` now lives in the package; validation imports it. Direct
Shapely/pyproj supported major ranges and the lockfile are declared.

Geometry/sampling/footprint checks: 86 passed. The full Python suite at this
point: 1,919 passed, 50 environment/toolchain-specific skips. The 1M-cell
labeling receipt has median 0.411 s, p95 0.414 s and 19,040,769 traced bytes,
including output and queue. Archived A/B/D native masks pass at 1.5 m.
Archived E retains 845 narrow-gap warnings but is unavailable (`roof_crossing`)
in that layer; no geometry pass or exact physical false-join claim is made.
See `docs/data/unified-v2/geometry-archive.json`. No archive wind solve ran.

Next-step assessment: preserve conservative E status and the existing archived
coarsening rejection; a finer layer would be a new geometry decision. D1 is
independent and can proceed. The optional prepared-mask native binding is
not selected for this delivery: exact post-solve evidence and honest early
unavailability suffice for the Python tier, without introducing a new policy
build identity. Do not perform requalification for unchanged native sources.

### D1 / Stage D and optional-deliverable decisions

Rechecked branch identities: main `a833c4d`, research `4eb119d`. Froze Python,
compiler, native package, native sources and five replay input hashes before
running `tools/verify_covariance_v2.py` on research. Receipts are in
`docs/data/unified-v2/covariance-d1/`. The native covariance unit test passed;
12 Python/native integration and independent-oracle tests passed, including
rotation, repeated eigenvalues, 1e-30–1e30 scales, tolerance boundaries, exact
row-sum equality, calm zero and explicit zero-length invalidity.

Offline replay: 4,792 computed source tensors and 813 original queries, zero
new campaign wind solves, 1.216 worker-seconds including compilation, within
the 900-second ceiling. All combined tensors are PSD, no previously valid
query is lost, and native replay agrees with the float64 oracle. Query coverage
recovers 41 A, 38 B-horizontal and 28 B-reference queries; D is unchanged.
Stage-by-stage counts, unsupported support and physical-k differences are
retained. Spectral scaling is rotation covariant; component scaling is frame
dependent and typically retains more energy. Maximum observed spectral-minus-
component physical-k reduction: 5.9781 m²/s². This is a numerical difference,
not a measured predictive gain. Zero source tensors stay valid.

The deferred Stage A incoming-mode oracle also passed on a tiny research
fixture: 20,216 computed valid fluid cells, maximum absolute energy difference
7.45e-9 m²/s² (`incoming-oracle.json`). Research verification sources and prior
E coarsening witnesses are retained in `research/unified_v2/`.

**Port decision:** retain the covariance model on research. The numerical gate
passes, but substantial energy changes and the already recorded absence of
predictive gain do not justify expanding the public native API in this
correctness/usability delivery. This is an explicit optional-port decision,
not a claim that the model failed PSD verification.

**PR4:** skipped. Neither the optional covariance port nor the optional
prepared-mask binding is selected; no hashed native source or CMake file was
changed. Policy requalification, paired native builds and sanitizer/release
checks that apply specifically to a native PR are consequently not invoked.

**D2:** skipped under its stated prerequisite: no promotion proposal exists.
No default change, new physical qualification, or closed-campaign ledger
consumption occurs.

### Packaging, off-path comparison and final review

Installed-wheel smoke covers physical k, strict-JSON quality reporting, sample
support, DTCC export and exact geometry witnesses. An isolated baseline/candidate
comparison uses the same native binary with baseline Python sources from main;
it bypasses editable import redirects. Velocity and flags are bit-identical.
Five balanced epochs give a median difference of 0.000100 s (ratio 1.0202),
which does not exceed both 5% and 0.01 s. Raw times, p95, RSS, array bytes,
package identity and failures are retained in `wheel-and-off-path.json`.
Quality-report median cost is 19.4 µs with 6,251 traced allocation bytes.

All unconditional implementation stages and their next-step assessments are
complete. Final review distinguishes:

1. Correctness/usability: explicit current physical energy, immutable evidence
   reports and mask-checked geometry diagnostics with honest scope/limits.
2. Predictive gains: none demonstrated or claimed; replay coverage improvement
   is a numerical validity result only.
3. Costs: physical-k classification ~0.71 s at 3M cells; quality report ~19 µs;
   1M-slice labeling ~0.41 s; all are opt-in. No new feature-off grid storage.
4. Unsupported claims: pedestrian gust/comfort accuracy, accessibility and
   physical validation remain unqualified. Archived E exact comparison at
   1.5 m remains unavailable and its previous rejection remains intact.

Final verification after the alignment/shape guards: **1,924 passed, 50 skipped**
(full suite, 91.82 s); geometry fixtures **18 passed**; research verification
**12 passed** plus native covariance executable success. The final installed
wheel smoke passed and its matched median feature-off delta was **0.000100 s**
(**1.0202×**), below the investigation threshold. `git diff --check` passed.
No unresolved test failure remains. Final receipt paths and identities are in
`docs/data/unified-v2/final-identities.json`; all new evidence totals <1 MiB.

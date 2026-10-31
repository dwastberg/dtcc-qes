# Touching and overlapping buildings: findings and implementation plan

**Status:** implemented and reviewed; plan dated 2026-10-30, scope revised
2026-10-31. Integrated with committed main `3ae4157` during end-to-end review.
Steps 1–4 are implemented: reproducible baseline, Python preparation, native
rings/exposure, and public `Footprints` wiring in `run` and `preview_grid`.
The dataset-adapter migration in step 6 is also implemented: it reuses prepared
canonical cells, preserves height steps and records versioned provenance.
End-to-end verification passes: 1,274 Python tests (24 conditional skips),
290 OpenMP integration tests and 144 native checks across serial, OpenMP and
sanitizer configurations. Review fixes, package checks and the unchanged adaptive
qualification limit are recorded in `docs/building-contacts.md`.


**Scope:** generic support for touching, overlapping, stepped, multipart and
holed building footprints. AIJ Case E motivates the required building types but
is not an implementation or acceptance fixture. AIJ conversion, case runs,
parameter tuning and comparison with measurements are outside this task.

Findings come from three sources:
- reading the working tree (`src/dtcc_qes`, `src/qes_core/winds`,
  `src/qes_core/dtcc`) and dtcc-core cleaning (`builder/cleaning`);
- scratch-session experiments with the adapter's contact check bypassed;
- a parse of AIJ Case E (`data/AIJ_E`, which is not committed).

The worktree tracks dtcc-core `dev/footprint-cleaning-update`, locked to
`80a4bbae2760e891e2a0be4175d67bf3340a8e67`, which includes `building_cells`.
No further dtcc-core changes are required: multipart preservation and the
explicit tallest-height fallback policy are implemented in the adapter.

## 1. Problem and purpose

AIJ Case E (Niigata) is a pedestrian-wind benchmark whose buildings touch and
overlap. After its roof faces are merged per height, it has 528 parts:

| Contact | Pairs | Heights |
| --- | --- | --- |
| Overlapping | 26 | all differ |
| Exactly touching | 38 | 29 differ |
| Gap under 0.5 m | 657 | down to 3 cm |

- Where parts touch or overlap, the height steps have a median of 1.5 m, a
  minimum of 0.2 m and a maximum of 12 m.
- There are no holes.
- The three buildings added after construction stand alone.

`wind.run` rejects touching and overlapping footprints, so Case E cannot run as
supplied. The same geometry is common in city data: terraced houses,
extensions, podiums with towers, and GIS outlines that overlap by digitising
error.

The goal is to accept such cities with deterministic, documented treatment:
- Equivalent canonical solids give the same result regardless of input order
  or source decomposition. Identical masks alone do not imply equivalence.
- Parameterizations are not seeded from walls that are not exposed to the flow.
- Existing results stay unchanged unless the caller opts in.

The model remains a diagnostic, mass-consistent model with empirical building
parameterizations. This plan removes decomposition artifacts. It does not
establish physical accuracy at height steps. Measurement-based validation,
including any future use of AIJ cases, is a separate task.

## 2. Where the limitation lives

### 2.1 Bindings (dtcc-qes)

**The contact rejection.**
- `_city.py:80-86` `reject_intersections` raises for any pair whose footprints
  `intersects`, including corner contact.
- It runs after extraction (`_city.py:177`) and again after float32 narrowing
  (`_city.py:395`).
- It is documented as a deliberate contract choice in three places:
  - `docs/milestone1-audit.md:57`: "Extra input restrictions are intentional";
  - the README "Geometry" section;
  - the `wind.run` docstring at `wind.py:77`.

**Other limits.**
- Holes, MultiSurface footprints and `BuildingPart`s are also rejected
  (`_city.py:97-129`).
- The bridge rejects a nonzero base height (`model_inputs.cpp:159-160`). That
  matters only for elevated structures and is out of scope here.

**The check does not protect results.** It tests topology, not what the grid
sees. Two buildings 0.3 m apart pass, yet on a 1 m grid they rasterise as
touching and give the same artifacts (section 3). Whether a sub-cell gap opens
as a fluid slot depends on where the cell centres fall.

**The dataset path flattens merged blocks.**
- `_dataset_city.py:75-91` passes each cleaned dtcc-core block to QES as its
  outline at the block height. A block's height is the largest part height
  (documented upstream: "a block describes an envelope, not a building"). So a
  tower on a podium becomes a slab of tower height.
- **Precedence may be wrong.** The path copies source footprints with their
  original z (`_dataset_city.py:43`). When no raster exists,
  `_ground_elevation` (`:66-67`) treats that z as ground. dtcc-core, however,
  reads footprint z as the roof level. Footprints at a nonzero ground elevation
  therefore give overlaps to the building on higher ground, not the taller one.
- **Height policy differs.** dtcc-core ranks overlaps by `estimated_height`
  before `measured_height`, while the path's height policy is measured first.

### 2.2 Core (vendored QES-Winds)

**What the core handles correctly (mask-based):**
- `PolyBuilding::setCellFlags` (`PolyBuilding.cpp:131-236`) rasterises each
  polygon by cell-centre point-in-polygon, with even-odd fill. The solid mask is
  the union of all footprints, so overlap does no harm to the mask.
- Wall cells, solver coefficients, final velocity zeroing and mixing length
  depend only on the mask (`Wall.cpp:131-164, 342-348`; `TURBWall.cpp:50-70`;
  `LocalMixingDefault`/`Serial`).
- Writes into solid cells are guarded or zeroed, so none survive.
- No zero-width canyon can form between touching parts: StreetCanyon requires
  fluid before solid (`:176`) and `s > 0.9·dxy` (`:441`).
- The rasteriser already accepts several rings in one vertex list (outer ring
  plus counter-clockwise holes, returning to v0) through the `start_poly` reset
  (`:199-215`).

**What depends on decomposition: the empirical parameterizations.** Every
parameterization takes faces, extents, centroid and height from the building's
own polygon. None checks whether an edge is internal, meaning another
building's solid lies directly outside it.

*Wake and canyon projected through neighbours*
- PolygonWake (`:411-425`) and StreetCanyon (`:146-176`) march downstream,
  skipping solid cells until they first reach fluid. A shared downwind wall
  therefore casts this building's wake or canyon *through* the neighbour, with
  distances measured from the shared wall.
- Where wakes overlap, far-wake deficits multiply (PolygonWake `:604`).
- StreetCanyon's `u0`/`v0` writes are not mask-guarded (`:473-474, :497-498`).

*Upwind cavity*
- Each upwind face gets its own ellipse (`UpwindCavity.cpp:110-177`), so
  side-by-side parts leave a gap at the junction. A collinear vertex splits a
  face the same way.
- A rear part's cavity can land in front of a shallow front part, applying the
  slowdown twice.
- Rooftop later overwrites a taller neighbour's cavity over a low roof, because
  it skips flags 4 and 6 but not 3.

*Sidewall*
- Sidewall regions can start mid-block at a junction.
- Whether they are disabled depends on flag-9 state left by earlier buildings
  (`Sidewall.cpp:164-174`).
- Flags reset per face, not per level.

*Rooftop*
- The roof boundary layer restarts at internal edges (`Rooftop.cpp:115-129`).

*Order and ownership*
- `ibuilding_flag` gives a cell to whichever building comes first in the input.
  That choice decides three things:
  - StreetCanyon's "downstream building lower" cancellation (`:264-266`);
  - which polygon StreetCanyon searches for the downstream face (`:292-393`).
    The face direction stays stale if none is found.
  - PolygonWake's march re-entry (`:416`).
- Equal heights are processed in merge-sort tie order
  (`WINDSGeneralData.cpp:440`), which also depends on input order.

*Local wind direction*
- Every pass reads the local direction at the building's centroid face from the
  already-modified `u0`.
- A low part next to a tower can read a reversed direction.

*Ring closure*
- PolygonWake finds the end of the ring with an absolute 0.1 m box around
  vertex 0 (`:330-334`).
- A vertex within 0.1 m of v0 truncates faces or gives a NaN `Lr`, which
  StreetCanyon then reuses.

*Courtyards*
- UpwindCavity (`:94`), StreetCanyon (`:103`) and Sidewall (`:100-151`) treat
  the jump edges between rings as faces.
- PolygonWake uses only the outer ring and distorts its values at v0.
- The centroid averages hole vertices too.

*Unrelated pristine bugs* (out of scope):
- `StreetCanyon.cpp:167` (`&&` bounds check);
- `PolygonWake.cpp:212-213` (`ceil` precedence);
- `TURBWallBuilding.cpp:157` (wrong index list, unused);
- the per-building mean H in turbulence (`TURBGeneralData.cpp:171-187`).

### 2.3 dtcc-core cleaning (after the 2026-10-30 response)

`builder.clean_footprints` merges footprints closer than the detail δ into
blocks, and divides each block by walls. Overlaps go to the highest roof, or to
the tallest building when footprints sit at z = 0. Each source keeps its own
cell and height.

The new `builder.building_cells(cleaned)` lists every cell as a
`FootprintCell`. Its fields:
- `polygon`, which can have holes;
- `height` (estimated, else measured) and `roof_z`;
- `ground_height`;
- `building_id` and `part_id`;
- `source_ids`.

Within a block, the cells tile the region without overlap.

| Reported issue | dtcc-core outcome | Consequence for dtcc-qes |
| --- | --- | --- |
| Fallback block averaged heights | **Fixed.** Tallest height and highest roof when roofs **or** heights span more than 2 m. | A fallback no longer cuts a tower down, but it raises the lower sources to tower height. Detect and handle it (5.1). |
| `strict=True` turns wall warnings into fallbacks | Kept and documented. Fallbacks are logged, marked `footprint_walls.outcome == "fallback"`, and listed in `footprint_cleaning.walls.fallback_ids`. | Use `strict=False`, which keeps cells when walls are closer than δ. |
| Precedence reads z as roof; estimated before measured | Documented. Estimated before measured is by design: `estimated_height` is DTCC's modelling height. The rule is recorded in `footprint_walls.precedence`. | Clean flat copies at z = 0 with `estimated_height` set to dtcc-qes's chosen height and `measured_height` cleared. |
| Block height is a maximum | Documented: a block is an envelope. | Extrude cells, never blocks. |
| Zero detail keeps overlaps | It now warns and names the pairs. `strict=True` raises `UnresolvedFootprintCleaningError`. No exact walls at zero detail. | Always use δ > 0. For precise inputs, δ = 0.01 m (moves geometry ≤ 5 mm, or 7.5 mm on retry). |
| No flat cell list | **Added:** `building_cells`. | This is the basis of 5.1 and 5.3. |
| Part cells can have holes | Documented. | Ring support in the core (5.2) is required. |

A positive δ moves geometry by up to δ/2, or 3δ/4 when a merge group needs the
retry. The cleaning record reports `fidelity_budget_used`.

## 3. Measured artifacts

The numbers below are historical scratch-session observations. Step 1 adds an
explicit synthetic recipe, machine-readable provenance and a reproducible
baseline in `docs/building-contacts.md`. The saved baseline is the reference
for subsequent comparisons; the scratch values are not exact regression targets.

**Setup.**
- Domain 240 × 120 × 100 m; wind from 270° at 5 m/s with the default log
  profile and default parameterizations.
- Grid: 1 m horizontally; vertically either 1 m uniform, or 0.5 m faces up to
  20 m and stretched above.
- Footprints are 20 × 20 m units at x = 60–100 and y = 50–70.
- The bindings' contact check was bypassed.
- Each compared pair ran the same number of iterations (1500–3000).
- The error is the speed difference at 2 m divided by the 5 m/s inflow speed.
- Except in the stepped rows, both models in a comparison have **identical
  solid masks**.

| Comparison | Max error | RMS error |
| --- | --- | --- |
| 40×20×10 m block split across the flow into two touching parts, vs one block | 0.46 | 0.018 |
| same split, parts in reverse input order, vs one block | 0.14 | 0.013 |
| block split along the flow, vs one block | 0.52 | 0.030 |
| two parts with a 0.3 m gap (accepted today), vs one block | 0.46 | 0.019 |
| 0.3 m gap, input order reversed, vs original order | 0.59 | 0.018 |
| 3 m gap, input order reversed, vs original order | 0.000 | 0.000 |
| 10 m + 9.9 m parts (same represented roof), vs one 10 m block | 0.46 | 0.018 |
| low 40 m footprint covering a tall 20 m one (overlap), vs the same shape partitioned | 0.86 | 0.035 |
| overlap, tall first vs low first | 0.000 | 0.000 |
| touching parts with one inset by 0.05 m, vs touching | 0.14 | 0.002 |
| stepped, 10 m upstream + 6 m downstream, vs one 10 m block | 0.20 | 0.016 |
| stepped, 6 m upstream + 10 m downstream, vs one 10 m block | 0.40 | 0.022 |

**What the table shows.**
- A split block, a 9.9/10 m pair and a sub-cell gap all give the same wrong
  answer, even though the solver sees the same solid.
- Results jump as heights converge: 10.0/10.0 m can be merged, but
  10.0/9.9 m behaves like a split.
- Input order matters once buildings touch or nearly touch.
- Insetting one part by 0.05 m only gets past the check.

**Changed flags.** Comparing split with merged, 3692 fluid cells change
parameterization flag: wake flags 4 and 5 move, and there are extra sidewall (9)
and rooftop (10) cells. Comparing overlap with partition, 1588 cells change.

The experiment scripts become `tools/contact_artifacts.py` (section 6).

## 4. Conclusion

The rejection belongs to the bindings and is easy to lift. Lifting it alone is
not a solution: it would expose decomposition dependence in the core's
parameterizations. That dependence already affects near-touching cities that
are accepted today. The core's solver and mask are sound; its parameterizations
assume every polygon is an isolated, fully exposed obstacle.

A general solution has two layers:

1. **Bindings: canonical solids.**
   - dtcc-core cleaning provides the partition: it merges footprints closer than
     δ, gives overlaps to the taller building, and gives each source its own
     cell.
   - dtcc-qes adds a merge of cells whose roofs the grid cannot tell apart, ring
     orientation and a fixed order.
   - Together these remove overlap ownership, splits at equal or
     indistinguishable heights, sub-cell gaps and input order as sources of
     variation.
   - The city path and the dataset path share this pipeline.
2. **Core: ring-aware, exposure-aware parameterizations.**
   - Seed only from faces exposed to fluid, and never march through another
     building.
   - Iterate faces ring by ring, so the holed cells from dtcc-core and
     courtyards work.
   - The strict default preserves existing reference results; exposure-mode
     compatibility is checked on named synthetic fixtures.

## 5. Design

### 5.0 Prerequisite: the dtcc-core dependency

- Use the existing `dev/footprint-cleaning-update` revision recorded above.
  The worktree's source configuration and lockfile are updated; offline lock
  validation passes. Merging that branch upstream is not a prerequisite.
- Rerun `tests/test_datasets.py` and the dataset docs. The fallback-height fix
  and the new zero-detail warning or raise may change dataset outcomes even
  before 5.3.
- Record the dtcc-core revision in result metadata; `versions.dtcc_core`
  already does this.

### 5.1 Bindings: `wind.Footprints`

**API**

```python
from dtcc_qes import wind

result = wind.run(city, 5.0, 270.0,
                  footprints=wind.Footprints(min_detail=0.5, exposed_faces=True,
                                             fallback="error"))
```

- `Footprints` is a frozen dataclass in `src/dtcc_qes/footprints.py`, following
  `Turbulence` and `VerticalGrid`. It is exported in `wind.__all__`, and `run`
  and `preview_grid` accept it.
- `footprints=None` keeps today's strict contract and today's results.
- In strict mode, metadata also records `near_contacts`: pairs closer than one
  cell, found with the existing STRtree. One warning is logged through
  `get_python_logger("dtcc-qes")`. It is not a Python warning, because the test
  suites run with warnings as errors.

**Fields**
- `min_detail` (metres, must be > 0, default 0.5 m, matching dtcc-core and the
  dataset path). It is dtcc-core's `min_building_detail` δ: footprints closer
  than δ merge, features smaller than δ go, and geometry moves by at most δ/2
  (3δ/4 on retry). For precise inputs (CAD, wind-tunnel models) use 0.01 m;
  overlaps are still divided, but gaps stay open. δ does not depend on
  resolution, so a grid study keeps one geometry.
- `exposed_faces` (default `True`): the core rule in 5.2.
- `fallback`, what to do with a block that keeps one footprint:
  - `"error"` (default): raise, naming the block, its sources and the fallback
    reason;
  - `"tallest"`: explicitly use the largest resolved source height, overriding
    dtcc-core's fallback height, which can be an average for close heights.
    Record output volume and the original upper-envelope volume within the
    output footprint; their difference is `added_volume`. Count a fallback
    once per block even when it has multiple polygon components.

**Accepted input:** touching or overlapping LOD0 `Surface`s, footprints with
holes, and `MultiSurface`. Heights follow `height_policy` per source.
`BuildingPart`s remain rejected on the city path.

**Pipeline** (`src/dtcc_qes/_footprints.py`)

1. **Extract.**
   - Extract sources as today, but allow contact, holes and MultiSurface.
   - Expand MultiSurface components into separately validated Surfaces before
     cleaning, preventing lossy upstream flattening. Give components stable
     internal IDs and retain their original source IDs in `component_sources`.
   - Resolve each height by `height_policy`.
   - Keep the base ranges for the flat-ground check.
2. **Flat copies.** Build a copy city in the existing float64 anchor frame. For
   each source:
   - LOD0 at z = 0, with holes kept;
   - `estimated_height` set to the chosen height and `measured_height` cleared;
   - its stable component ID, with an explicit mapping to the original source.

   Precedence then follows dtcc-qes's heights, never ground elevation or a
   stale estimate.
3. **Clean.** Call
   `builder.clean_footprints(copy, min_building_detail=δ, min_area=0.0, lod=LOD0, strict=False, remove_holes=False)`.
   - Catch `UnresolvedFootprintCleaningError`, and re-raise its
     `diagnostics["unresolved_groups"]` as a `ValueError`.
   - Keep `footprint_cleaning` in metadata, including the outcome, fidelity
     budget used, wall outcomes, `fallback_ids` and `excluded`.
4. **Cells.**
   - `builder.building_cells(cleaned)` provides the cells.
   - Use the block's explicit `footprint_walls.outcome == "fallback"` record
     to apply the fallback policy, rather than inferring failure from source
     count or `part_id`.
   - A source with no cell, because it lost its cell to taller neighbours or was
     excluded, is recorded as `covered` or `excluded`, never dropped silently.
5. **Merge on the grid.**
   - In `prepare_domain`, once the vertical faces are known, union the cells of
     the same cleaned building whose roofs fall on the same vertical face. The
     merged height is the maximum.
   - This uses the `roof_representation` lookup (`_city.py:369-374`) and covers
     equal heights and the 10 m / 9.9 m case.
   - Cells of different buildings are at least δ apart, so they never merge.
6. **Rings.**
   - Explode merged cells into polygons: outer rings clockwise, holes
     counter-clockwise.
   - Remove repeated vertices.
   - Remove a collinear vertex only where no neighbouring cell has a vertex
     there, so that shared walls keep identical vertices for rasterisation.
7. **Canonical order:** descending height, then centroid, then the full polygon
   coordinates. Canonicalize ring starts and hole/component order. Remove exact
   consecutive duplicates and unprotected collinear vertices; node shared
   boundaries so that T-junction vertices occur on both sides.
8. **Validate.**
   - Keep the per-solid checks: two-cell clearance, roof clearance below the top
     cell centre, and float32 edge and area validity (`_city.py:376-395`).
   - Replace the `intersects` test with a no-shared-area test, both before and
     after narrowing.

**Metadata**
- `footprints`: settings, the dtcc-core cleaning record, and counts (sources,
  cells, solids, merges, covered, excluded, fallbacks).
- `solids[]`: `native_id`, `source_ids`, `building_id`, `part_ids`, height,
  area, represented roof and roof error.
- `buildings[]`, per source: gains `solids` and a status of `solid`, `covered`
  or `excluded`, plus the reason.
- `model`: records `exposed_faces`.

**Files**
- New: `src/dtcc_qes/footprints.py`, `src/dtcc_qes/_footprints.py`.
- `src/dtcc_qes/_city.py`: extraction in resolve mode, solid arrays with ring
  offsets, and the overlap test.
- `src/dtcc_qes/wind.py`: arguments, metadata and docstring.

**Pipeline handoff (implemented and wired publicly)**
- `prepare_footprints(city, height_policy=..., settings=Footprints(...))`
  returns anchored float64 sources/cells and cleaning/source-accounting metadata.
- `finalize_footprints(prepared, effective_faces=..., origin=..., resolution=...,
  shape=..., terrain=..., max_cells=...)` consumes the final planned physical
  grid, merges represented roofs, checks original source elevations, domain
  clearance and float32 validity, and returns solids, arrays and final metadata.
- Shape is `(nz, ny, nx)`; origin is global `(x, y, ground)`. Final faces must
  include any turbulence extension. Finalization does not plan a grid or allocate
  flow storage. Public planning iterates until the grid's building-height
  collection agrees with finalization, including turbulence's mean height.
  Unstable dependencies raise after at most 16 passes, recommending explicit faces.
- Arrays include global vertex boundaries for all closed rings and aligned
  building vertex offsets. Native ring support accepts holes after topology checks.
- `wind.run` and `preview_grid` accept `footprints=Footprints(...)`; `None`
  retains strict input restrictions. Metadata records sources, solids and settings.

### 5.2 Core: ring-aware, exposure-aware parameterizations

**Bridge**
- `BuildingArrays` gains `ring_offsets`. `ModelSettings` gains `exposed_faces`
  (bool, default `false` = pristine). Files:
  `src/qes_core/dtcc/api/wind_config.h`, `src/cpp/bindings.cpp`.
- `WindModelInputs.h`: `BuildingFootprint` carries rings, and
  `BuildingParameterizations` carries `exposedFaces`.
- `model_inputs.cpp:151-185` validates each ring:
  - closed;
  - outer clockwise, holes counter-clockwise;
  - positive net area;
  - two-cell clearance.

  It also builds the return-to-v0 vertex list that `setCellFlags` already fills
  correctly, plus explicit ring boundaries.

**Rings (implemented; existing reference fixtures retain parity)**
- `PolyBuilding` stores ring boundaries. Every face loop iterates edges ring by
  ring, so jump edges no longer exist. Loops to change:
  - UpwindCavity `:94`;
  - StreetCanyon and StreetCanyonModified `:103`;
  - Sidewall `:100-151`, wrapping previous and next within a ring;
  - PolygonWake, including inner-ring faces; only the common wake scale is
    averaged over outer-ring faces.
  - Rooftop face loops and own-footprint support checks.
- Canonical/explicit ring inputs use exact ring ends. Legacy single-ring inputs
  without exposure retain the 0.1 m closure heuristic, with a finite wake-length
  guard. Bounds checks protect both modes.
- Canonical parameterization faces combine exact collinear segments, preserving
  the original shared mask vertices. This is independent of the exposure switch.
- The centroid stays the vertex average of the outer ring.
- PolygonWake's area (`:120`) becomes the net area.

**Exposure rule (only when `exposed_faces` is set)**

A face cell of building b at level k is exposed if the first cell outward from
the face, outside b's own footprint, is fluid in the initial mask
(`icellflag_initial`). The own-footprint test is even-odd PNPOLY, factored out
of `setCellFlags` into a shared building helper; it never uses `ibuilding_flag`.
For a candidate, project onto its face and trace the outward normal by DDA,
starting on the outward side with `nextafter`. Grid-corner ties advance both
indices. Use cell-centre even-odd membership and the initial mask at each level.
Parameterizations seed only from exposed face cells.

| File | Change |
| --- | --- |
| PolygonWake `:411-425`; StreetCanyon `:146-176`; StreetCanyonModified `:303-332` | Skip only cells inside the building's own footprint. A solid cell outside it, met before fluid, ends that march. No wake or canyon is cast through a neighbour. |
| UpwindCavity seeding `:177-290` | Skip unexposed face cells and levels. |
| Sidewall `:164-174` | Test the upwind corner per level, and reset `right_flag`/`left_flag` per level. |
| StreetCanyon `:292-397` | Initialise the face direction for each search. Skip when no downstream face is found. |

**Compatibility.** Strict-mode and isolated reference fixtures retain their
numerical results. A fluid gap alone is not a universal bitwise-equivalence
promise between exposure modes: corner eligibility and parameterization state
interactions can also change. Nonfinite wake lengths and bounds receive safety
checks in both modes.

Rooftop support is restricted to the owning footprint for holes and exposure
mode, and exposure mode preserves upwind-cavity flags. Turbulence retains its
per-building mean-height formula, applied to finalized canonical solids.

Every modification is recorded in `src/qes_core/PROVENANCE.md`.

**Open modelling question.** No decomposition of a real height step is exact
with these Röckle-type parameterizations. Examples are a 6 m house against a
9 m one, or a tower in a podium, which dtcc-core gives as a podium cell with a
hole.
- **Planned:** partitioned prisms with exposure. Every vertical face belongs to
  one solid and seeds only where it is exposed.
- **Rejected alternative:** nested columns, each level `{H ≥ h}` extruded from
  the ground. They double-seed coincident faces, and fail for towers flush with
  a podium face.

Generic synthetic fixtures compare `exposed_faces` on and off to verify the
exposure rules (section 7). These checks do not establish physical accuracy.

### 5.3 Dataset path

**Status:** implemented. Dataset preparation reuses the shared canonical-cell
planner and solve handoff. No additional native changes were needed.

**Shared handoff: clean once, plan once to stability, solve once.**

- Split `prepare_footprint_domain` into a planner accepting `PreparedFootprints`
  and a wrapper that first prepares an input city. Preserve the existing
  canonical-solid/grid stabilization loop, including its turbulence-height
  handling and explicit failure on an unstable dependency.
- Extract the native solve and result/metadata assembly from `wind.run` into a
  private function accepting validated condition/solver settings, geometry and
  `PreparedDomain`. Public `wind.run` and the dataset builder use this function.
  Keep public signatures and strict-mode behavior intact.
- The dataset builder must not pass cleaned cells or a reconstructed city back
  through the public cleaning path. One dataset request calls
  `builder.clean_footprints` exactly once; planning passes reuse its result.

**Source preparation and ground.**

- `_dataset_city` copies fetched geometry into the established global
  EPSG:3006 frame without mutating the source. Keep original measured/estimated
  heights, source IDs and footprint elevations for provenance and validation.
  Multipart components use the shared component-preserving extraction.
- Determine ground before any flattening: explicit 3D bounds supply it;
  otherwise use the terrain raster, ignoring nodata/nonfinite values, or the
  original footprint elevations as today. Preserve the empty-city rules.
- Use `height_policy="allow_estimated"`: valid measured height first, estimated
  height only when measured height is absent. Invalid measurements still raise.
  The shared pipeline resolves this policy and creates its own z = 0 cleaning
  copies with the chosen modelling heights. Do not duplicate that normalization
  in the dataset adapter or erase which source height was chosen.

**Courtyard policy.**

- Retain the dataset's existing source-courtyard and cleaned-region filling
  semantics, including accounting for filled areas and excluded components.
  Add an explicit internal policy to shared preparation so the dataset can use
  `remove_holes=True`; in-memory `Footprints` preparation keeps its current
  hole-preserving default. No new public configuration field is required here.
- Apply filling at the source/region cleaning stage. Never clear holes from
  individual `building_cells` outputs: a podium cell's hole can contain its
  tower cell. Preserve those partition holes through finalization and the native
  bridge, preventing overlapping solids or a tower-height envelope.
- Record source-hole filled areas and input-union void areas after source filling,
  plus cleaned occupied area and net area change. The pinned Core API does not
  expose exact post-conditioning region-fill area: record it as unavailable,
  rather than treating conditioning/exclusion changes as pure courtyard filling.
  This accounting limit does not require another cleaning pass or Core changes.

**Bounds and final grid.**

- After cleaning, combine the query rectangle with cleaned cell extents in the
  global frame, then apply horizontal padding exactly once. Use the existing
  minimum of three effective horizontal cells. Raw source extents alone are
  insufficient because cleaning can move walls beyond them.
- Retain explicit 3D ground/top constraints. For 2D queries derive the required
  top from cleaned cell heights, reference height and vertical clearance through
  the shared domain policy. Keep existing effective-grid rounding, roof-clearance,
  float32 and resource checks before native flow allocation.
- Uniform and automatic dataset grids use the shared finalization/stabilization
  path. Do not reimplement roof grouping or derive bounds from flattened block
  envelope heights.

**Dataset defaults and failures.**

- Use `Footprints(min_detail=args.min_building_detail, exposed_faces=True,
  fallback="tallest")`, with the internal courtyard policy above. Retain the
  existing `min_building_detail` dataset argument and record all effective
  settings; additional tuning arguments are outside this migration.
- `"tallest"` applies only to explicitly reported wall-partition fallbacks,
  using the shared maximum resolved source-height policy and volume accounting.
  It does not suppress unresolved cleaning exceptions, invalid geometry/heights,
  partial upstream results, grid/resource failures or solver errors.
- Preserve solver convergence reporting and `raise_on_nonconvergence`. Surface
  fallback counts and excluded-source counts in dataset health/provenance, with
  a dataset-context warning when a tallest-height fallback is used.

**Provenance and documentation.**

- Version the preparation schema and identify the canonical-cell pipeline.
  Store the shared cleaning record, courtyard policy/filling records, effective
  settings, source → component/part → solid mappings, covered/excluded sources,
  fallback reasons/volumes and the pinned dtcc-core revision.
- Replace `blocks[].measured_height/estimated_height` and `block_height_policy`
  with the shared source/solid records. A retained block summary may contain
  IDs/source IDs for compatibility, but must not imply that a block is one
  constant-height obstacle. Update consumers/tests for the versioned schema.
- Update the README dataset section, descriptor processing steps and presentation
  limitations, examples and building-contact documentation. Dataset geometry now
  preserves height steps; default courtyard filling and flat-ground treatment
  remain explicit. Ordering and exposure corrections can change dataset flow
  results even when cleaned occupancy is unchanged, so blanket numerical parity
  with the previous dataset path is not an acceptance requirement.

**Acceptance and implementation order.**

1. Extract the shared prepared-geometry planner and prepared-domain solve path;
   run existing in-memory API tests to establish unchanged behavior.
2. Migrate dataset source preparation, courtyard policy, bounds and solve handoff.
3. Update provenance, descriptor/docs and dataset regression expectations.

Use synthetic/fetched-city mocks only. Tests must cover:

- exactly one cleaning call per dataset request, including automatic-grid
  stabilization passes;
- stepped overlaps and towers in podiums, preserving partition holes and each
  represented height;
- multipart components, source/region courtyard filling, and complete accounting
  for covered, partially excluded and fully excluded sources;
- measured-first precedence with stale estimates, nonzero source elevations,
  terrain nodata, absolute translations and source immutability;
- explicit 3D limits and 2D-derived bounds enclosing the cleaned geometry, including
  cleaning tolerances larger than cell spacing and minimum-padding requests;
- reported tallest-height fallbacks, their volume accounting, and propagation of
  unresolved cleaning failures;
- empty cities, resource/roof checks before allocation, uniform field products,
  automatic-grid slices, and existing sampling/convergence behavior;
- dataset results matching the shared pipeline under identical courtyard,
  footprint, ground, bounds, grid and solver settings.

Run the dataset tests and the full existing Python/native regression checks.
Keep strict reference fixtures unchanged; update dataset expectations where the
new semantics intentionally differ. Implement this migration as a separate
change. AIJ conversion, case runs and measurement validation remain excluded.

## 6. Tests, tools and documentation

- **`tools/contact_artifacts.py`** reproduces the comparison types in section 3
  with explicit fixtures and a new saved baseline.
  - Options: `--footprints baseline|strict|resolve`, `--exposed-faces on|off`,
    `--min-detail`, `--resolution`, `--iterations`, `--height`, `--case`,
    `--output`.
  - Baseline mode bypasses only the adapter contact rejection within the
    standalone experiment. Strict mode records unsupported contacts as rejected.
    Resolve mode now uses the public pipeline and supports exposure-on/off.
    Cleaning tolerance is not applied in baseline/strict mode.
  - Output: JSON plus a terminal table.
- **`tests/test_footprints.py`, adapter around dtcc-core (no solve):**
  - Overlap goes to the taller building by dtcc-qes height:
    - with measured 60 m and a stale estimated 6 m under
      `height_policy="measured"`;
    - with footprints at a nonzero ground elevation.
  - Tower in podium gives a holed podium cell with counter-clockwise rings, plus
    the tower cell.
  - Equal-height touching sources merge into one solid.
  - T-junction walls keep shared vertices on both sides.
  - A covered source is recorded.
  - `fallback="error"` raises and `"tallest"` records the fallback. Force a wall
    warning to get one, as the dtcc-core developers did.
  - A permuted city gives identical arrays.
  - Float32 narrowing checks.
  - Strict mode is unchanged and records `near_contacts`.
- **`tests/test_footprints.py`, invariance on small grids** (exact equality of
  velocity and flags), with `Footprints(min_detail=0.01)` unless noted:
  - split vs single block;
  - overlap vs partition;
  - permuted order;
  - 10 m + 9.9 m vs one 10 m block;
  - with `min_detail=0.5`, a 0.3 m gap vs the merged block;
  - with `exposed_faces`, no wake (4/5) or canyon (6) flags beyond a neighbour
    behind a shared wall;
  - the solid mask equals a shapely rasterisation of the cells at cell centres
    more than 1e-3 m from any boundary.
- **Native (`tests/native/check_contacts.cpp`):**
  - `exposed_faces` off is bit-identical to today on the canonical fixtures.
  - On/off isolated `one_building` results are bit-identical; compatibility
    with other separated geometries is measured rather than inferred.
  - Ring validation: jump edges are never faces, and a hole that is not
    counter-clockwise is rejected.
  - A vertex within 0.1 m of v0 no longer gives a NaN `Lr`.
- **Existing tests:**
  - `tests/test_city_adapter.py:91` stays as the strict-mode test.
  - `tests/test_datasets.py` is updated for 5.0 and 5.3. The monkeypatched
    `clean_footprints` tests (`:308-324`) move to the shared pipeline.
  - The reference and parity suites must not change.
- **Docs:**
  - new `docs/building-contacts.md`: findings, pipeline, exposure rule and the
    regenerated table;
  - the README "Geometry" and dataset sections, and the `wind.run` docstring;
  - a link from `docs/validation.md`.

## 7. Generic acceptance fixtures

All new acceptance fixtures are small, synthetic geometries committed with the
tests. No AIJ files, converters, case runs or measurement comparisons are needed
to implement or complete this task.

- **Building types:** touching equal-height blocks, overlapping unequal-height
  blocks, height steps, towers on podiums, courtyards, disconnected multipart
  footprints, partial-wall contact and corner contact.
- **Exposure:** exercise axis-aligned and oblique walls, both wind orientations
  across a height step, and partial coverage at different vertical levels.
  Compare exposure on/off to check which faces may seed parameterizations.
- **Cleaning and grid sensitivity:** exercise positive cleaning tolerances,
  gaps above and below those tolerances, and uniform and nonuniform vertical
  grids. Keep cleaning geometry fixed when varying grid resolution.
- **Determinism:** compare source permutations, ring rotations and component
  ordering. Require exact numerical equivalence for equivalent canonical
  solids; identical masks alone do not imply identical parameterizations.
- **Compatibility:** use existing non-AIJ reference fixtures and synthetic
  separated buildings to check the strict path and documented parity claims.
- **Public API:** run both `preview_grid` and `run` on the generic fixtures,
  checking complete source-to-solid accounting and explicit fallback behavior.

Future AIJ Case E work can consume this generic capability. Its conversion,
benchmark campaigns and physical validation require a separate plan and are not
release gates for this task.

## 8. Order of work

0. The dtcc-core dependency (5.0).
1. `tools/contact_artifacts.py` and `docs/building-contacts.md` as a baseline,
   with a saved JSON artifact and focused tool tests. **Complete:** 15 synthetic
   solves, 12 comparisons, all at 1500 iterations on a serial Release build;
   `docs/data/building-contacts/baseline.json` records the recipe and provenance.
2. 5.1, the pipeline and `Footprints`, on the pristine core. Cells with holes
   were rejected until step 3. **Complete:** preparation, canonical cells,
   final-grid merging, arrays, validation and source accounting.
3. 5.2, rings and exposure in the core, with native tests and parity checks.
   **Implemented:** explicit validated rings, ring-aware traversals, canonical
   parameter faces and initial-mask exposure.
4. Wire `exposed_faces`, enable holed cells, add the exposure and invariance
   tests, rerun the tool and update the docs. **Implemented:** public API,
   source metadata, preview/solve agreement and turbulence planning.
5. Generic synthetic acceptance checks (section 7). **Complete:** public fixtures,
   native contact/occlusion checks and the refreshed 15-solve comparison artifact;
   eight equivalent-canonical/order comparisons have identical velocities/flags.
6. 5.3, the dataset path, as a separate change. **Implemented:** clean-once
   prepared-geometry handoff, height-preserving solids, source/region courtyard
   policy, cleaned bounds, versioned provenance and synthetic dataset coverage.

## 9. Verification

- `uv lock` resolves a dtcc-core that provides `dtcc_core.builder.building_cells`.
- `uv run --frozen pytest tests/test_footprints.py tests/test_city_adapter.py tests/test_datasets.py`
- Native CTests (`check_contacts` plus the existing physics, runner, safety and
  OpenMP checks) pass for the serial and OpenMP builds.
- The applicable non-AIJ regression suite passes. Existing non-AIJ reference
  fixtures, urban benchmark fixtures and turbulence references are unchanged.
  Running AIJ cases is not part of this verification.
- `uv run --frozen python tools/contact_artifacts.py --footprints resolve --exposed-faces on`
  shows exact agreement for equivalent canonical solids, and reports
  identical-mask/different-geometry and stepped comparisons as sensitivity
  results alongside the baseline values.
- `wind.preview_grid(..., footprints=wind.Footprints())` succeeds for both
  touching and overlapping synthetic cities, including stepped, multipart and
  holed fixtures. Metadata accounts for every supplied source.

## 10. Follow-ups noted by dtcc-core (not needed here)

dtcc-core lists these as possible follow-ups. dtcc-qes does not need them,
because it cleans flat copies and extrudes cells:
- precedence by ground + height;
- block height as roof − ground.

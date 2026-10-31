# Vegetation support

**Status: investigation complete 2026-10-30; not implemented. Depends on
[terrain T1](ADD_TERRAIN.md#t1-stair-step-terrain-end-to-end).**
dtcc-qes ignores vegetation. Every city child that is not a `Building`,
including DTCC `Tree` objects, is counted in the result's
`ignored_city_objects` and left out of the model (`src/dtcc_qes/_city.py:178-182`).
Wind under and behind trees is therefore overestimated.

This document describes how vegetation can be represented in a
mass-consistent model like QES, what upstream QES provides, what DTCC can
supply, how vegetation combines with terrain and buildings, and a phased
plan. It builds on [ADD_TERRAIN.md](ADD_TERRAIN.md), which defines the ground
sampler and per-column ground that vegetation needs.

Upstream references are to the `QES-Public` submodule at the vendored fork
revision `dce15d7e` (see `src/qes_core/PROVENANCE.md`). dtcc-core references
are to the installed `dtcc_core` (develop, 0.9.8.dev0 at `ecd56669`).

## Answers in brief

| Question | Answer |
| --- | --- |
| How should vegetation be represented? | As porous canopy elements that reduce the initial wind inside and above crowns and in their wakes, never as solid cells. QES has no momentum equation, so vegetation cannot be drag in the solver. Upstream QES has these canopy models; they were not vendored because nothing reached them. |
| What does it need from the city model? | Vegetation as separate geometry, like buildings, on a bare-earth terrain ([input contract](ADD_TERRAIN.md#2-what-the-terrain-must-provide)). DTCC `Tree` objects give position, height and crown radius. Crown base height and leaf density are missing and need documented defaults. |
| How does it combine with terrain and buildings? | Crown base and top are placed above each column's ground, taken from the terrain sampler. Buildings and terrain always win: vegetation never overwrites a solid cell and skips building footprints. |

## 1. How a mass-consistent model represents vegetation

QES finds the mass-consistent field closest to an initial guess. It has no
momentum equation, so there is nowhere to put a drag force. Upstream QES
instead encodes vegetation in the initial guess, and the solver then makes
that field mass-consistent:

1. **Setup (once per geometry).** Canopy cells get their own flags and a
   per-cell attenuation coefficient. Only fluid cells outside building
   footprints become canopy (`CanopyIsolatedTree.cpp:101-139`).
2. **Before building models (per solve).** `canopyRegression` fits a log
   profile, with a friction velocity and roughness, to the initial wind just
   above each canopy column, measuring height above the terrain
   (`Canopy.cpp:318-378`). Each element then reduces the initial wind inside
   and above its crown (`WINDSGeneralData.cpp:702-705`).
3. **Building models** run next and overwrite the field where they overlap
   (`WINDSGeneralData.cpp:707-763`).
4. **Canopy wakes** are applied last, as a multiplicative velocity deficit
   behind elements (`WINDSGeneralData.cpp:768-771`; `Canopy.cpp`, `applyCanopyWake`).
5. **Turbulence** adds canopy wake turbulence and canopy stresses
   (`TURBGeneralData.cpp:332-344`).

**The main limitation:** the vegetation's whole effect is in the initial
guess. The solver can redistribute part of that slowdown, so speeds in and
behind trees are approximate. For pedestrian wind comfort this is usually
acceptable, but result metadata must say so.

## 2. Upstream canopy models

| Element | Flags (canopy / wake) | Inputs | Use in cities |
| --- | --- | --- | --- |
| `CanopyIsolatedTree` | 22 / 23 | Crown polygon, height, crown width, crown base, LAI | Single trees. **First priority.** |
| `CanopyHomogeneous` | 20 / 21 | Polygon, height, base, attenuation coefficient (or LAI) | Forest and park patches. |
| `CanopyWindbreak` | 24 / 25 | Rotated rectangle, height, base, understory height, optical porosity, fence model, fetch | Hedges and tree rows. Optional. |
| `CanopyROC` | 26 / 27 | Row-organized crops | Not relevant for cities. |

Flags are listed in `Canopy*.h` (`getCellFlagCanopy`, `getCellFlagWake`).
The vendored flag comment still says "11 = Canopy vegetation"
(`src/qes_core/winds/WINDSGeneralData.h:189-192`); that is outdated.

**Velocity model** (isolated tree, `CanopyIsolatedTree.cpp:171-290`). With
crown height `h`, displacement height `d`, canopy roughness `z0`, attenuation
`a` and height above the crown base `z_rel`:

- **Inside the crown:**
  `u0 *= log((h - d)/z0) * exp(a*(z_rel/h - 1)) / log(z_rel/z0)`. This is the
  exponential attenuation profile, matched to the log profile at the crown top.
- **From the crown top up to twice the top height:** a blend of
  `log((z_rel - d)/z0) / log(z_rel/z0)` with 1, so the change fades out
  linearly.
- **`d`** is found by bisection (`Canopy.cpp:384-422`), with a slope-matching
  fallback when bisection fails (`Canopy.cpp:424`).
- Fractions outside [0, 1] are reset to 1.

**Wake model** (`CanopyIsolatedTree::canopyWake`, `CanopyIsolatedTree.cpp:292`
onward). A velocity deficit spreads behind the crown, scaled with the tree
height and width. It is skipped when the crown centre sits in a building
cavity or street canyon (flags 3, 4, 6; `:359`).

**Size:** about 4,100 lines across `Canopy.cpp`, `CanopyElement.cpp`, the four
element files and `Canopy_io.cpp`. Only the driver, the element base class,
the isolated tree and the homogeneous canopy are needed at first.

## 3. Options

| Option | Effect | Verdict |
| --- | --- | --- |
| Ignore vegetation (today) | Trees are listed as ignored objects. | Acceptable for the first terrain release; overestimates wind near trees. |
| Raise roughness (z0) | Changes only the inflow profile; QES has one domain-wide roughness. | Represents forest upwind of the site only; does nothing for street trees. |
| Trees as solid cells | Blocks all flow through crowns. | Wrong: crowns are porous. Rejected. |
| **Port the upstream canopy models** | Slows the wind in and behind each crown and adjusts the profile above it. | **Recommended.** |
| Drag or porosity in the solver | Not possible without a momentum equation. | Would need a CFD solver. |

## 4. What DTCC provides

**Available**

- **`Tree` objects** (`dtcc_core/model/object/tree.py`), read with
  `city.trees` (`dtcc_core/model/object/city.py:50-52`). Each has:
  - `position`: x, y and the ground elevation;
  - `height`: crown top above ground;
  - `crown_radius`: plan-view radius.
- **Tree builders.** `trees_from_pointcloud` (`dtcc_core/builder/trees/create.py:218`)
  builds a canopy height raster (vegetation height above the terrain), finds
  tree tops as local maxima and estimates crown radii. The ground z is the
  terrain-raster cell at the tree top (`create.py:276-285`). There is also a
  city method (`builder_mixin.py:512`) and a trees dataset
  (`dtcc_core/datasets/trees.py:176`).
- **Land use** polygons with `FOREST`, `GRASS` and other classes
  (`dtcc_core/model/object/landuse.py`), usable as outlines for canopy patches.

**Missing (needs documented defaults recorded in metadata)**

- **Crown base height** (trunk height). Upstream's isolated tree needs it.
- **Leaf density** (LAI or attenuation coefficient). Neither species nor season
  is available. A `leaf_on` / `leaf_off` choice should be explicit, because
  deciduous trees are nearly transparent in winter, when many comfort
  assessments matter most.
- **Patch heights.** The canopy height raster is built internally by the tree
  builder; it is not clear whether it is kept on the city (see Open questions).

**Input contract.** This extends the terrain contract in
[ADD_TERRAIN.md](ADD_TERRAIN.md#2-what-the-terrain-must-provide) and its
[decisions](ADD_TERRAIN.md#decisions). The terrain is bare earth without
trees, and vegetation is always separate geometry, like buildings. Trees
baked into the terrain or into building geometry are not detected.

## 5. Combining with terrain and buildings

**Terrain** (needs [terrain T1](ADD_TERRAIN.md#t1-stair-step-terrain-end-to-end))

- Vegetation uses the same ground as buildings: the per-column ground from the
  terrain sampler ([ADD_TERRAIN.md §1](ADD_TERRAIN.md#1-mesh-or-raster)). The
  ground z stored on a DTCC tree is ignored, since it is a nearest-cell sample
  of the DEM.
- Upstream's isolated tree already places the crown above each column's
  ground: base at `terrain + base_height` and top at `terrain + H`
  (`CanopyIsolatedTree.cpp:107-119`). The canopy regression also measures
  height above the terrain (`Canopy.cpp:349`). Both need `terrain[]` filled,
  which terrain T1 provides.
- **The wake is not terrain-aware.** It compares absolute z with
  `base_height`, `0.75·H + base_height` and `1.5·(H + base_height)`
  (`CanopyIsolatedTree.cpp:340-353`). It must measure from the tree's own
  ground, the same fix as the street canyon in
  [terrain T2](ADD_TERRAIN.md#t2-terrain-aware-turbulence-automatic-grid-and-street-canyon).
- A crown on a slope spans columns with different ground. Upstream follows
  the ground per column, so the crown is sheared along the slope rather than
  kept level. That is acceptable for crowns a few cells wide.

**Buildings**

- Buildings and terrain always win. A canopy column is skipped when its
  footprint flag marks a building (`icellflag_footprint == 0`,
  `CanopyIsolatedTree.cpp:101-102`), and solid cells (flags 0 and 2) are never
  overwritten (`:133-135`).
- `icellflag_footprint` was removed from the vendored core as write-only
  (`src/qes_core/PROVENANCE.md`, "Unreachable code removed"). It must be
  restored, or replaced by an equivalent mask.
- The order is fixed by upstream: vegetation attenuation, then building
  models, then canopy wakes (`WINDSGeneralData.cpp:702-771`).
- Overlapping vegetation: a later element overwrites an earlier one's column.
  Define a precedence; individual trees should win over patches.

**Results**

- Canopy flags (20 to 27) are fluid. `WindResult` already treats only flags 0
  and 2 as solid (`src/dtcc_qes/result.py:239, 308-313`), so sampling,
  including the ground-relative sampling from terrain T1, works unchanged.

## 6. Grid resolution

- A crown needs several cells across to register. A 3 m crown radius on a
  2 m grid covers about 7 columns, which is enough.
- Crowns narrower than about two cells should be merged into a canopy patch or
  ignored, with a warning and a count in metadata.
- Vertically, the crown and the band above it (up to twice the top height)
  need several layers. The isolated tree requires the domain to reach 1.5
  times the crown-top layer index (`CanopyIsolatedTree.cpp:163`). With the
  automatic vertical grid, this depends on the terrain-aware fine band in
  [terrain T2](ADD_TERRAIN.md#t2-terrain-aware-turbulence-automatic-grid-and-street-canyon).

## 7. Wind comfort statistics and inflow speed

Comfort statistics use one solve per direction, which relies on the result
scaling linearly with inflow speed. The canopy terms should keep this:

- the regression's friction velocity scales with speed, while its roughness
  intercept does not;
- the displacement height and all velocity fractions are ratios that do not
  depend on speed;
- the wake uses a friction velocity divided by speed (`ustar_wake`).

This must still be verified numerically, as for buildings.

**Zero speed fails.** The regression divides by a zero friction velocity, and
the NaN check throws "canopy regression gives nan" (`Canopy.cpp:363-366`).
dtcc-qes accepts a speed of 0, so vegetation must be skipped for zero inflow,
or zero rejected when vegetation is enabled.

## Decisions (proposed)

- **Porous canopy models only.** Vegetation is never solid.
- **Isolated trees first**, then homogeneous canopies. Windbreaks are optional;
  row crops are out of scope.
- **Plain input structs.** Vegetation crosses the bindings as plain arrays,
  like buildings and terrain (in `winds/WindModelInputs.h` and
  `dtcc/api/wind_config.h`).
- **One leaf-area relation.** Choose and document a single relation between
  leaf area and attenuation (see the defects below).
- **Explicit leaf state** (`leaf_on` / `leaf_off`), recorded in metadata with
  every default used.
- **Off by default** (`vegetation=None`) until validated, so existing results
  do not change.

## Plan

### V0: prerequisite

[Terrain T1](ADD_TERRAIN.md#t1-stair-step-terrain-end-to-end) provides the
per-column ground (`terrain[]`), base-relative building placement and
ground-relative sampling. Vegetation on flat ground needs only `terrain[] = 0`,
so V1 can start in parallel with terrain T1 as long as it uses the same
terrain array.

### V1: isolated trees

**Native**

- Port from `QES-Public/src/winds`:
  - the `Canopy` driver: regression, bisection, slope match, wake
    application;
  - `CanopyElement`;
  - `CanopyIsolatedTree`.
- Remove the XML and shapefile parsing (`Canopy_io.cpp`, `parseValues`).
  Construct the elements from a new `TreeCrown` struct (crown polygon, crown
  base, top, leaf area) in `src/qes_core/winds/WindModelInputs.h`.
- Restore `icellflag_footprint` (or a building-column mask).
- Make the wake measure from the tree's ground.
- Hook the stages into the per-solve order shown in section 1, from
  `src/qes_core/dtcc/wind_runner.cpp`.
- Validate inputs in `src/qes_core/dtcc/model_inputs.cpp`: finite values,
  crown base below top, crowns inside the domain with clearance, positive
  inflow speed.
- Bindings (`src/cpp/bindings.cpp`): tree arrays passed to `prepare`.

**Python**

- New `src/dtcc_qes/_vegetation.py`:
  - read `city.trees`, applying transforms as for buildings;
  - build crown polygons from the radius (a regular polygon);
  - drop trees narrower than the grid threshold;
  - apply the defaults;
  - take the ground from the terrain sampler.
- `wind.run(..., vegetation=None | "leaf_on" | "leaf_off")`.
- Trees leave `ignored_city_objects` when vegetation is enabled.
- Metadata: defaults, counts of used and dropped trees, and the vegetation
  simplification statement.

### V2: canopy patches

- Port `CanopyHomogeneous`. Outlines come from land-use `FOREST` polygons (or
  user polygons); heights come from a canopy height raster.
- Upstream uses one height per polygon. Either split patches by height or
  extend the element to per-column heights.
- Optionally port `CanopyWindbreak` for hedges and tree rows.

### V3: vegetation turbulence

Port canopy wake turbulence and canopy stresses (`TURBGeneralData.cpp:332-344`,
`Canopy::applyCanopyTurbulenceWake`, `Canopy::applyCanopyStress`). This comes
after [terrain T2](ADD_TERRAIN.md#t2-terrain-aware-turbulence-automatic-grid-and-street-canyon)
makes turbulence terrain-aware.

## Verification

**Python unit tests**

- Crown polygons have the expected area.
- Tree transforms are applied once.
- Narrow crowns are dropped with a count.
- Defaults and leaf state appear in metadata.
- Trees are ignored by default and used when enabled.

**Native checks**

1. With no vegetation, outputs are bitwise identical
   (`tools/compare_native_builds.py`).
2. **Single tree on flat ground.** Before the solve, the initial wind in the
   crown matches the attenuation profile in section 2 analytically, and `d`
   satisfies the bisection equation.
3. **Tree inside a building footprint.** The tree has no effect.
4. **Tree on a slope.** In every column, the crown base and top follow that
   column's ground. The wake is placed relative to the tree's ground.
5. **Inflow speed.** Speed-up ratios do not depend on the inflow speed (to
   float precision). Zero speed with vegetation gives a clear error rather
   than NaN.
6. Six-face divergence passes; the `converged` flag alone is not accepted.

**Comparison with upstream**

Build upstream with `tools/make_reference.py` and run XML cases with an
isolated tree and with a homogeneous canopy, on flat ground and on the
Gaussian hill used in
[terrain verification](ADD_TERRAIN.md#verification). Differences must come
only from the deliberate fixes: the leaf-area relation, the terrain-relative
wake and the zero-speed guard.

**Physical plausibility**

The wake recovery length and the speed reduction under a crown should be
compared with published isolated-tree wind-tunnel or field data. That is
outside the native checks and needs sourcing.

## Upstream defects not to copy

| Defect | Where |
| --- | --- |
| Inconsistent leaf-area relations: the homogeneous canopy sets `a = 2·LAI`; the isolated tree sets cell attenuation to `0.5·LAI` and derives `LAI = 2·a` from its XML coefficient. The same LAI gives attenuations a factor of 4 apart. | `CanopyHomogeneous.cpp:47`; `CanopyIsolatedTree.cpp:135`; `CanopyIsolatedTree.h:66` |
| The isolated-tree wake uses absolute heights, so it is misplaced over terrain. | `CanopyIsolatedTree.cpp:340-353` |
| Zero inflow speed makes the regression produce NaN, which throws. | `Canopy.cpp:356-366` |
| The vendored flag comment lists vegetation as 11; the canopy elements use 20 to 27 (18 and 19 in the base class). | `src/qes_core/winds/WINDSGeneralData.h:189-192`; `Canopy*.h` |

## Open questions

- What defaults should be used for crown base height and leaf area, in leaf-on
  and leaf-off states? They need a sourced table, for example by broad tree
  type.
- Does the DTCC city keep the canopy height raster, or must vegetation patches
  get their heights another way?
- Do DTCC city models carry hedges or tree rows, which would make the
  windbreak model worth porting?
- Should vegetation be enabled by default once V1 is validated?

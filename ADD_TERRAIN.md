# Terrain support

**Status: investigation complete 2026-10-30; not implemented.**
dtcc-qes solves over flat ground only. A city with terrain is refused unless
the caller passes `terrain='flat'` or a ground elevation
(`src/dtcc_qes/_city.py:213-214`). Every footprint is then placed on one plane
(`_city.py:217-227`), the native arrays carry `base_heights=0`
(`_city.py:405-407`), and the native layer rejects any other base
(`src/qes_core/dtcc/model_inputs.cpp:159-160`, "Flat-ground buildings must have
zero base height"). The dataset path always flattens: it passes
`terrain=bounds[2]` (`src/dtcc_qes/datasets.py:157-158`), where the ground is
the minimum of the terrain raster (`src/dtcc_qes/_dataset_city.py:55-68`).
The fetched terrain raster and each building's `ground_height` are already
available and discarded.

This document answers three questions and gives a phased plan:

1. Must a terrain mesh be converted to a raster, or can the mesh be used?
2. What does the terrain need to provide for good results?
3. How are buildings and terrain merged?

Upstream references are to the `QES-Public` submodule at the vendored fork
revision `dce15d7e` (see `src/qes_core/PROVENANCE.md`); the terrain code there
is unchanged from UtahEFD v2.3.1. dtcc-core references are to the installed
`dtcc_core` (develop, 0.9.8.dev0 at `ecd56669`).

## Answers in brief

| Question | Answer |
| --- | --- |
| Mesh or raster? | No raster is needed. QES only ever consumes one ground height per grid column (cell centres for stair-step, cell corners for cut cells). Upstream itself turns its DEM into a triangle mesh and ray-casts it at cell centres, using `util/Mesh`/`BVH`/`Triangle`, which are already vendored and compiled. A mesh can be sampled exactly. What matters is sampling onto the QES grid well, not the input format. |
| What must the terrain provide? | The input is assumed to be a clean bare-earth mesh or DEM, with buildings always supplied as separate geometry. It must cover the whole padded domain without holes, in the buildings' frame and vertical datum, with resolution at or finer than the grid spacing. The edges should be flat, slopes moderate, and the domain top must clear the relief. |
| How are buildings and terrain merged? | In QES there is no geometric merge: terrain and buildings are both solid cell flags (2 and 0) in one voxel grid. Terrain is filled first, then each building fills its footprint from its base to its roof, overwriting terrain. Walls, solver and diagnostics treat both flags as one solid. The only real decisions are each building's base and roof elevations. |

## 1. Mesh or raster

### What QES consumes

QES uses a Cartesian voxel grid, so terrain always becomes a ground elevation
per column, whatever its source:

- **Stair-step:** one height per column at the cell centre, (nx-1)×(ny-1)
  values. A cell is terrain (flag 2) when its centre is at or below the ground
  (`QES-Public/src/winds/WINDSGeneralData_io.cpp:384-412`).
- **Cut cells:** heights at the four corners of each column, nx×ny values,
  clipped against each layer (`QES-Public/src/winds/DTEHeightField.cpp:629-719`).

### Upstream already goes through a mesh

The upstream raster path loads a GDAL DEM, triangulates it at the QES spacing
(two triangles per dx×dy quad, `DTEHeightField.cpp:451-498`), and wraps the
triangles in a `Mesh` with a BVH. `initializeTerrain` then queries
`DTE_mesh->getHeight(x, y)` at every cell centre
(`WINDSGeneralData_io.cpp:214-231`). There is no mesh file loader upstream, but
`Mesh(const std::vector<Triangle *> &)` accepts any triangles.

The classes are vendored byte-identical and compiled into `qesutil`:

| Function | Location | Behaviour |
| --- | --- | --- |
| `Mesh::getHeight(x, y)` | `src/qes_core/util/Mesh.cpp:47` | Delegates to the BVH. |
| `BVH::heightToTri(x, y)` | `src/qes_core/util/BVH.cpp:186` | Descends boxes containing (x, y); returns the highest hit. |
| `Triangle::getHeightTo(x, y)` | `src/qes_core/util/Triangle.cpp:42` | Ray from (x, y, 0) straight up; barycentric hit test. |

Quirks to handle in a caller: the ray starts at z = 0, so triangles below zero
are missed and z must be shifted to be nonnegative; a miss returns −1; and the
arithmetic is float32, so vertices must be in local coordinates (as building
rings already are, `_city.py:378-395`).

The cut-cell path is different: `DTEHeightField::setCells` samples the GDAL
scanline directly at cell corners (`DTEHeightField.cpp:629-680`), so it is not
reusable as is (see T3).

### Conversions to avoid

- `dtcc_core.builder.mesh_to_raster` (`dtcc_core/builder/meshing/convert.py:7-31`)
  interpolates the **mesh vertices only** by inverse distance, ignoring the
  triangles. It discards exactly the information a mesh adds and returns
  `nodata=0`.
- `Raster.get_value` (`dtcc_core/model/values/raster.py:224-252`) is a
  nearest-cell lookup with no interpolation; `int()` truncation lets slightly
  negative indices wrap to the other side of the array.

### Recommendation

One sampler that takes a DTCC `Raster` or `Mesh` (or a `Terrain` holding
either) and returns the ground elevation for each QES column:

- **Raster:** bilinear interpolation between pixel centres, the same contract
  as dtcc-core's builder (`dtcc_core/builder/model_conversion.py:85-130`):
  north-up affine, no rotation or skew, NaN/nodata masked.
- **Mesh:** exact interpolation on its own triangles through the vendored BVH,
  exposed as a native helper with a QES-free signature (arrays in, heights
  out), in keeping with the bindings boundary.
- **Box filter to the grid:** average a 4×4 set of sub-samples per column
  rather than taking the single centre value. A point sample aliases sub-cell
  features: a ditch or kerb that happens to hit a centre becomes a full-cell pit
  or step.

For DTCC dataset cities the raster is the better source. `build_terrain`
creates a 2 m raster from ground points and derives the mesh from it, with
triangles up to 5 m and three smoothing passes
(`dtcc_core/model/mixins/city/builder_mixin.py:25-82`). A mesh is the right
input when it is the primary data, for example a surveyed or designed terrain.

## 2. What the terrain must provide

1. **Input contract: clean bare earth, separate buildings.** When simulating
   with terrain, the city model is assumed to always contain a clean terrain
   mesh or DEM with no buildings or trees, and buildings are always separate
   geometry. dtcc-qes does not detect or remove buildings or vegetation from
   the terrain, and it does not accept merged city meshes (terrain and
   buildings in one mesh). The DTCC raster built from LAS class-2 points
   (`build_terrain_raster(..., ground_only=True)`) and the terrain mesh derived
   from it meet this contract. A city may also contain terrain and no
   buildings; that is a supported simulation, not an edge case. Trees and
   other vegetation are also separate geometry; see
   [ADD_VEGETATION.md](ADD_VEGETATION.md).
2. **Full coverage, no holes.** The terrain must cover the whole QES domain
   including padding, and contain no NaN, nodata or (for a mesh) uncovered
   columns, including under the footprints, where it sets each building's
   base. Missing data should be an error by default, with nearest-value filling
   as an explicit option for domains that reach past the terrain's edge.
3. **Same frame and datum as the buildings.** The terrain must use the
   buildings' planar frame and the same vertical datum as their ground and roof
   elevations. The terrain's transforms go through the same `_resolve_frame`
   rules as the buildings (`_city.py:130-137`, `_dataset_city.py`).
4. **Resolution at or finer than the grid.** Features smaller than about two
   cells cannot be represented by stair steps and should be filtered out (the
   box filter above, optionally followed by smoothing). Each stair step is about
   slope × dx high, so keep dz ≤ dx through the vertical band the relief spans,
   or steps become flat terraces with tall risers.
5. **Moderate slopes.** QES is a diagnostic, mass-consistent model: it has no
   momentum and cannot produce separation on lee slopes. Upstream applied
   stair-step terrain to the gentle Askervein hill "without any complex terrain
   flow parameterizations" (user guide, §4.1). Results on steep slopes are
   qualitative. Report the maximum slope in result metadata and warn above a
   threshold.
6. **Flat edges.** The solver never updates the outermost x/y ring or the top
   layer, and the multiplier is zero there (user guide §3 and §7), so the
   terrain-following initial profile is simply imposed at the boundaries. The
   guide states that QES "cannot model the wind field ... correctly" when a
   building or terrain crosses the domain boundary (§3.1). Blend the terrain to
   a constant elevation across the padding band (a cosine ramp, with at least
   the outer two cells exactly flat), and record the largest change. Terrain
   probably needs more padding than flat ground; a minimum based on the relief
   is an open question.
7. **A domain top above the relief.** The top must clear the highest roof and
   the highest ground plus the clearance, measured from the lowest ground. The
   reference height is measured above the sensor column's ground. Turbulence
   additionally needs the top 15 m above the highest terrain (upstream
   `TURBGeneralData` check; flat-only today at
   `src/qes_core/winds/TURBGeneralData.cpp:65-67`).
8. **One roughness.** `z0` is uniform over the domain
   (`src/qes_core/winds/WINDSGeneralData.cpp:90-100`). Land cover is not
   represented; record this as a simplification.
9. **A representative reference column.** The log profile is anchored to the
   ground of the sensor column (`src/qes_core/winds/LogProfile.cpp:85`). The
   sensor sits at cell (5, 15), or at the domain corner if that cell is inside a
   building (`_city.py:401-404`). With the edge blending, that column is on the
   flat rim.

## 3. How buildings and terrain are merged

### In DTCC's mesh builders (for reference)

`build_city_surface_mesh` merges real geometry, through
`build_city_surface_mesh_from_terrain_mesh_impl`
(`dtcc_core/cpp/include/MeshBuilder.h:236-635`):

- Buildings that share a vertex form a block with one base: the lowest terrain
  under the block (`MeshBuilder.h:305-315`).
- Terrain faces under each block are flattened to that base and frozen
  (`:317-347`); the surrounding terrain is then smoothed towards the frozen pads
  (`:349-352`).
- Walls run from the block base to the roof; terrain faces inside buildings are
  removed and everything is welded into one mesh.

DTCC's building conventions matter for QES too. The LOD0 footprint z holds the
**absolute roof elevation** (`footprint.set_z(roof)`,
`dtcc_core/builder/geometry_builders/buildings.py:170, 318`).
`attributes["ground_height"]` holds the ground that was used, and the height
attributes are roof minus ground. Cleaned blocks take the lowest
`ground_height` of their parts (`dtcc_core/builder/cleaning/blocks.py:668-691`).

### In QES

QES needs no geometric merge. Terrain and buildings are cell flags in the same
grid, applied in this order:

1. The ghost layer k = 0 is flag 2 (`WINDSGeneralData.cpp:102-107`).
2. Terrain: in each column, every cell whose centre is at or below the ground
   becomes flag 2 (upstream `WINDSGeneralData_io.cpp:384-412`).
3. Buildings: `PolyBuilding::setCellFlags` marks each cell whose centre is
   inside the footprint as flag 0, from `k_start` (the first layer whose top
   face is above `base_height`) to `height_eff = base_height + H`
   (`src/qes_core/winds/PolyBuilding.cpp:165-229`). This overwrites terrain
   inside the footprint.
4. Wall boundary conditions zero the coefficient towards any neighbour with
   flag 0 or 2 (`src/qes_core/winds/Wall.cpp:131-165, 291-326`). The solver and
   mass diagnostics also treat 0 and 2 as solid
   (`src/qes_core/solver/solver.h:180`,
   `src/qes_core/solver/mass_diagnostics.h:37`). The solver sees one solid.

The parameterizations are mostly relative to the building base already:

| Model | Terrain handling |
| --- | --- |
| Upwind cavity | `z_front = z[k] - base_height` (`UpwindCavity.cpp:167`); skips flags 0 and 2. |
| Polygon wake | `z_build = z[k] - base_height` (`PolygonWake.cpp:361`); skips flags 0 and 2. |
| Rooftop | Uses `H + base_height` (`Rooftop.cpp:134-254`). |
| Sidewall | Skips flags 0 and 2 (`Sidewall.cpp:195, 292`). |
| Street canyon | **Not terrain-aware.** Uses absolute `z_face[k+1]/S` and `log(z[k]/z0)`, marked "WILL NOT WORK ABOVE/OVER TERRAIN" (`StreetCanyon.cpp:267, 442`; `StreetCanyonModified.cpp:306, 498`). It is on by default (`src/qes_core/dtcc/api/wind_config.h:23`). |

On a slope, wake and cavity zones are tied to the building base, not to the
local ground downstream; cells that fall inside terrain are skipped.

### Base and roof

**Base.** Upstream takes the lowest terrain at the footprint **vertices**
(`QES-Public/src/winds/WINDSGeneralData.cpp:413-430`). If the ground inside the
footprint is lower than at every vertex, the building floats above an air gap.
dtcc-qes should instead take the lowest stair-step ground over every column the
building fills, together with the vertex samples. `k_start` then reaches the
ground in every footprint column.

**Roof (decided: preserve the absolute roof elevation).** The roof is what the
point cloud measured; the QES base is a property of the grid. So:

- With `attributes["ground_height"]`: roof = `ground_height + height`, and the
  QES height is roof − QES base.
- Without it: the height is taken above the QES base, and metadata records
  `roof_reference="qes_base"`.
- The LOD0 z is **not** read directly. dtcc-core stores the roof there, while
  dtcc-qes and its tests treat it as the base (`_city.py:140`,
  `tests/test_city_adapter.py:129-141, 175-182`). The meaning depends on the
  producer.
- A QES height that is not positive, or below one cell, is an error. Metadata
  records `ground_height`, the QES base, the roof and their difference per
  building.

## Current state of the code

| Piece | State |
| --- | --- |
| `util/Mesh`, `BVH`, `Triangle` | Vendored, compiled, unused for terrain. |
| `WINDSGeneralData::terrain`, `terrain_face_id` | Allocated as 0 and 1 (`WINDSGeneralData.cpp:261-262`); never changed. |
| Flag 2 in physical layers | Only the ghost layer (`WINDSGeneralData.cpp:102-107`). |
| `LogProfile` terrain shift | Intact (`LogProfile.cpp:85, 129-169`); inert because `terrain_face_id` is 1. |
| `PolyBuilding` base | `base_height`, `height_eff` and `k_start` work (`PolyBuilding.cpp:51-78, 165-170`); the native guard blocks nonzero bases. |
| Turbulence | `TURBWallTerrain` runs for the ground ghost layer; mixing lengths use `z - terrain` (`LocalMixingDefault.cpp:53`); `terrain_top` and `terrainH_max` are hard-coded to 0 (`TURBGeneralData.cpp:65-67, 159-166`). |
| Cut cells | `CutCell` compiled but orphaned; `cut_cell` is a null pointer (`WINDSGeneralData.h:248`); `meshTypeFlag` fixed at 0 (`WINDSGeneralData.h:140`). |
| Never vendored | `DTEHeightField`, `Terrain.h`, `WINDSGeneralData_io.cpp` (`initializeTerrain`, shapefile base heights). |
| Removed after vendoring | `terrain_volume_frac`, `terrain_id`, `ti/tj/tk`, `Wall::wallLogBC` (`src/qes_core/PROVENANCE.md`, "Unreachable code removed"). |
| Results | Sampling heights are above flat ground (`src/dtcc_qes/result.py:132-135, 272-273`); flags 0 and 2 are invalid. |
| Cities without buildings | Supported on flat ground, but only with explicit bounds (`_city.py:215-216`, `tests/test_wind.py:56-59`). The native core accepts zero buildings (`WINDSGeneralData.cpp:131-146`); turbulence then uses a reference height of 100·z0 (`src/dtcc_qes/_turbulence_domain.py:14-15`, `TURBGeneralData.cpp:196`). |

## Decisions

- **Input contract.** Terrain is a clean bare-earth mesh or DEM without
  buildings or trees; buildings are always separate geometry. Merged city
  meshes are not supported.
- **Terrain without buildings.** A city with terrain and no buildings must
  run. Every phase supports it, and it is the first validation case.
- **Stair-step first.** Cut cells are a later, gated phase.
- **One sampler** for rasters and meshes, box-filtered to the grid.
- **QES-free bindings.** Terrain crosses the binding as plain arrays.
- **Preserve absolute roofs.** The base is the lowest ground under the filled
  columns and vertices.
- **Flat behaviour unchanged.** Flat ground must stay bitwise identical, so all
  existing references and parity archives remain valid.

## Plan

### T1: stair-step terrain, end to end

Turbulence, `VerticalGrid.auto` and the street canyon model are rejected with
a clear error when terrain is not flat, until T2. The street canyon check
applies only when there are buildings, since the model only loops over
buildings (`WINDSGeneralData.cpp:356-361`).

**Terrain without buildings**

- With terrain present, remove the "empty city requires explicit grid bounds"
  rule (`_city.py:215-216`). Automatic bounds become the terrain's extent,
  shrunk to whole cells. The edge blend then lies inside the terrain, and
  metadata records it.
- Explicit bounds remain allowed but must lie inside the terrain coverage.
- The domain top comes from the relief alone: highest minus lowest ground,
  plus the clearance, and at least the reference height above the sensor's
  ground. `default_domain_top` already treats missing buildings as height 0
  (`_city.py:200-204`).
- Nothing else is building-specific: the native arrays are already empty for
  zero buildings (`_city.py:405`), and the dataset path finds the ground from
  the terrain (`_dataset_city.py:55-68`).

**Python**

- New `src/dtcc_qes/_terrain.py`:
  - `resolve_terrain(city, terrain)`. `terrain=` keeps `None`, `'flat'` and a
    number. It adds `'city'` (the city's terrain: the raster first, then
    `get_geometry(id="dem")`, then the mesh) and accepts a `Raster`, `Mesh` or
    `Terrain` object.
  - `sample_ground(source, grid, supersample=4)` returns the global ground
    elevation for each column: bilinear for rasters, the native BVH helper for
    meshes. It applies edge blending and the hole policy.
  - Datum: `origin_z` is the lowest blended ground, so relative ground is
    nonnegative.
  - Building bases and roofs as in section 3, with metadata: source,
    sub-sampling, maximum slope, maximum blend change, and per-building values.
- `src/dtcc_qes/_city.py`:
  - In `prepare_domain`, replace the flat-only block (L213-227) with the terrain
    branch.
  - Include relief in `default_domain_top` (L200-204).
  - Support uniform and explicit vertical grids.
  - Send relative terrain heights and nonzero `base_heights` to native.
- `src/dtcc_qes/result.py`: add `WindResult.ground` (the stair-step ground the
  solver used, plus the sampled ground) and
  `sample(height, reference="ground" | "datum")`, interpolating within each
  column at ground + height.
- `src/dtcc_qes/datasets.py`: add a `terrain=` option (default `"flat"` until
  validated). `_field_slice` (L195-253) slices relative to the ground.
  `_source_city` keeps the source terrain.

**Native**

- `src/qes_core/dtcc/api/wind_config.h`: terrain heights in the prepare inputs.
- `src/cpp/bindings.cpp:166-184`: `prepare(..., terrain=None)` and a
  `sample_mesh_heights(vertices, faces, x, y)` helper over `util/Mesh`.
- `src/qes_core/dtcc/model_inputs.cpp:157-162`:
  - Accept nonzero bases when terrain is supplied.
  - Make the roof clearance use base + height.
  - Validate the terrain's shape, finiteness, sign and clearance below the top.
- `src/qes_core/winds/WINDSGeneralData.{h,cpp}`: the constructor takes the
  terrain heights and, after the ghost layer and before buildings:
  - fills `terrain[]`;
  - marks flag-2 cells by the centre rule;
  - sets `terrain_face_id` to the index of the **first fluid cell**, extended to
    the nx×ny face grid by copying the last row and column.
- `src/qes_core/winds/LogProfile.cpp:129-169`: evaluate the profile in each
  column at `z[k] - z_face[terrain_face_id(column)]`, not by shifting the
  sensor profile by an index offset. The index shift is only right for uniform
  dz. With flat ground the arithmetic is unchanged.

### T2: terrain-aware turbulence, automatic grid and street canyon

- Restore `terrain_top` and `terrainH_max` from the terrain heights
  (`TURBGeneralData.cpp:65-67, 159-166`). Apply the 15 m margin above the
  highest terrain in `src/dtcc_qes/_turbulence_domain.py`.
- The turbulence reference height (3 × mean building height, or 100·z0
  without buildings) is an absolute z today (`TURBGeneralData.cpp:191-196,
  347`). Measure it above the ground, which matters most for terrain without
  buildings.
- `VerticalGrid.auto`: the fine band currently starts at z = 0
  (`src/dtcc_qes/_auto_grid.py:67-72`). It must span from the lowest ground to
  the highest ground plus twice the pedestrian height. Re-run the C2 grid-study
  tooling on a terrain case.
- Street canyon: measure heights from the canyon base (`z - base_height`, and
  H/S from `height_eff - base_height`), then validate it on a sloping canyon.

### T3 (gated on T1 validation): cut-cell terrain

- Port `setCellPoints` and `getIntermediate`
  (`QES-Public/src/winds/DTEHeightField.cpp:682-1217`) without GDAL, fed with
  corner heights from the same sampler.
- Allocate a real `CutCell`; upstream calls it through a null pointer.
- Re-allocate `terrain_volume_frac`.
- Add a terrain-only switch; `meshTypeFlag` also switches buildings to
  `CutBuilding` and the turbulence walls to cut-cell mode.
- Cost: fractional coefficients disable the compact operator, which falls back
  to six explicit arrays (`src/qes_core/solver/solver.cpp:44-61`). Since SOR is
  bandwidth-bound, consider compact tables plus a sparse override list for cut
  cells.

## Verification

**Python unit tests**

- A tilted plane given as a raster and as a mesh reproduces the analytic
  heights, point by point and as the sub-sample average.
- A mesh below z = 0 is handled by the shift.
- Holes raise an error, and nearest filling works when requested.
- Edge blending leaves an exactly flat outer ring.
- Building bases equal the minimum over their filled columns, and the roof rule
  holds with and without `ground_height`.

**Native checks** (`tests/native/check_physics.cpp` or a new `check_terrain.cpp`)

1. All-zero terrain is bitwise identical to today's flat outputs
   (`tools/compare_native_builds.py`).
2. Uniform terrain raised by N·dz on a uniform grid reproduces the flat field
   shifted up N layers. This tests flags, walls and the profile together.
3. An inclined plane and a Gaussian hill, with no buildings, pass on six-face
   divergence (not the `converged` flag), with no flux into solids and no
   fluid cell below the ground of its column.
4. Every footprint column of a building on a slope is solid from the ground to
   the roof.

**Comparison with upstream**

`tools/make_reference.py` already builds upstream QES with GDAL. Run
`QES-Public/tests/runTestsFiles/winds_GaussianHill.xml`
(`GaussianHill_200x200.tiff`, stair-step, 1 m cells, no buildings) through
both, and an analytic Gaussian hill through dtcc-qes. Flags and the speed-up over the hill
top should agree, except where explained by the deliberate differences:
`terrain_face_id`, the per-column profile and the datum.

**Field case (optional)**

Askervein, with the DEM in `QES-Public/scratch/DEM/askervein.tif`. The
measured speed-ups along line A must come from the literature.

**End to end**

`examples/city_dataset.py` with `terrain="city"` on a sloping site, with
`preview_grid` checked first, in OpenMP and serial builds. Run it once with
the buildings and once with only the terrain.

**Documentation**

Update the flat-ground statements in `README.md` (L6 and "Geometry,
coordinates and flat ground"), the `wind.run` docstring
(`src/dtcc_qes/wind.py:73-76`) and `DYNAMIC_VERTICAL_GRID.md`.

## Upstream defects not to copy

| Defect | Where |
| --- | --- |
| `terrain_face_id` uses a face threshold while stair-step solids use cell centres, so the profile ground can be one cell off. Terrain exactly at 0 gives id 0, putting the profile ground at `z_face[0] = -dz`. | `WINDSGeneralData_io.cpp:224-230` vs `:384-412` |
| A halo corner copies `terrain_id` into `terrain_face_id`. | `WINDSGeneralData_io.cpp:286` |
| XML buildings are shifted by the halo before the terrain query, but the mesh is unshifted. | `WINDSGeneralData.cpp:408-421` |
| `cut_cell` is never allocated; cut-cell methods are called through a null pointer. | `WINDSGeneralData.h:331`, `DTEHeightField.cpp:1061-1102` |
| Cut-cell halo corners are forced to z = 0, so the terrain drops at the DEM edge. | `DTEHeightField.cpp:673-677` |
| `DEMDistancex` is compared with the y extent. | `DTEHeightField.cpp:396` |
| The log profile shifts by an index offset, which assumes uniform dz. | `LogProfile.cpp:129-169` (vendored as is) |
| The left-wall loop of the stair-step log law iterates `wall_below_indices`. Present in the vendored file, but only on the `terrainWallFlag == 1` path; dtcc-qes uses 2 (`src/qes_core/dtcc/turbulence.cpp:24`). | `src/qes_core/winds/TURBWallTerrain.cpp:195-197` |

## Open questions

- What padding and blend width should terrain use by default: a fixed number
  of cells, or a multiple of the relief?
- At what slope should results carry a warning?
- Should `terrain="city"` become the dataset default once T1 is validated?

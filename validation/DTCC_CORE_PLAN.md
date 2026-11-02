# Proposal for dtcc-core: footprints from block geometry, and buildings from footprints

**Audience:** dtcc-core developers.
**Origin:** the AIJ benchmark validation of dtcc-qes (`dtcc-qes/validation/`, see `AIJ_CITY_MODELS.md`).
**Status (2026-11-01): mostly implemented** in dtcc-core `dev/qes-updates` (`66c81a2`): F2 `building_from_footprint`, F1 `footprints_from_lod1` and the mesh-loader option. One gap remains: 33 non-conforming AIJ Case E solids (T-junctions, internal walls; see `DTCC_REQUESTS.md` R5). The validation uses F2 for every Building and F1 for Case D. The text below is the original proposal, kept for reference.
**Reviewed against:** dtcc-core `dev/footprint-cleaning-update` at `80a4bba` (2026-10-30). File references are to that commit.
**Revised 2026-10-31** after dtcc-qes merged contact-aware footprints (`wind.Footprints`, main `889c629`), which consumes `clean_footprints` and `building_cells` from the same dtcc-core commit. The changes:
- §1 now covers `building_cells`.
- The precision lessons in §3.2 are reversed: do **not** snap.
- §3.3 aligns the output with `FootprintCell` and dtcc-qes.
- §3.3.2 corrects a claim about cleaning touching levels (see request R6 in `DTCC_REQUESTS.md`).

Building the AIJ City models required two pieces of general geometry code that dtcc-core does not have. Both are working and tested in the validation folder. This document describes how they work, what went wrong on the way, and how I recommend adding them to dtcc-core.

| # | Feature | Validation code | Proposed dtcc-core home |
|---|---|---|---|
| F1 | **Footprints and roof levels from 3D block geometry**: turn closed, vertical-walled solids (a mesh, a LOD1 MultiSurface or a face soup) into LOD0 footprints with ground and roof heights, one per roof level | `validation/aij/prisms.py` | new `builder/geometry_builders/prisms.py`, plus `footprints_from_lod1` in `builder/geometry_builders/buildings.py` |
| F2 | **A Building from a footprint and a height**: one call that gives a valid, saveable Building with LOD0, heights and LOD1 | `validation/aij/cityutil.py:make_building` | `building_from_footprint` in `builder/geometry_builders/buildings.py` |

F2 is small and has no dependencies, so it can land first. F1 uses F2 for its output.

---

## 1. Background: what dtcc-core has today

| Capability | Where | Gap |
|---|---|---|
| Load a mesh as a City (`.obj/.ply/.stl/.vtk/.vtu`): split into disconnected parts, one Building per part with an **LOD1 MultiSurface** | `io/meshes.py:116` `_load_meshio_city_mesh`, `:735` `load_mesh_as_city`; `builder/meshing/meshing.py:473` `disjoint_meshes` | These Buildings get **no LOD0, no heights and no `ground_height`**, so footprint-based tools (cleaning, height builders, dtcc-qes, dtcc-solar sampling…) cannot use them directly. |
| Derive one footprint from any LOD | `Building.footprint(geom_type=...)` (`model/object/building.py:54`) → `flatten_geometry` → `MultiSurface.to_polygon` (`builder/geometry/multisurface.py:58`) | Gives **one** outline at `zmax`, keeping only the largest piece of a MultiPolygon, with **no heights and no roof levels**. `to_polygon` also drops surfaces under 0.01 m² and simplifies at 1 cm. On a triangulated roof, the small triangles disappear and leave notches. |
| Footprint cleaning reads LOD1 by default | `builder/cleaning/clean.py:146` `_AUTO_LOD_ORDER = (LOD1, LOD2, LOD3, LOD0)`, `_extract_source` (`:1054`) | Same single-outline extraction, with roof = `zmax`. A stepped building becomes one region at its tallest roof. |
| Extrude LOD0 to LOD1 | `extrude_building` (`buildings.py:53`), `extrude_surface` (`geometry_builders/surface.py:32`), `build_lod1_buildings` (`buildings.py:362`) with `record_lod1`/`invalidate_lod1` | Works well. F1 and F2 should produce LOD1 through this path so that the LOD1 records stay consistent. |
| Construct a Building | `Building(id=...)`, `Surface().from_polygon(poly, z)`, `add_geometry(..., GeometryType.LOD0)`, attributes | **No helper exists.** Every caller builds LOD0, heights and `ground_height` by hand, and some get the z convention wrong (see §2.2). Callers include dtcc-qes tests and examples, the validation code, demos, and dtcc-qes's own cleaning copies (`dtcc_qes/_footprints.py:291-301`, LOD0 at z = 0 with `estimated_height`). |
| List the pieces of cleaned footprints | `builder.building_cells` (`builder/cleaning/clean.py:957`) returns `FootprintCell(polygon, roof_z, height, ground_height, building_id, part_id, source_ids)`, one per footprint piece with one roof; cells of a block tile it | Already the hand-off format dtcc-qes uses (`prepare_footprints`). It is the natural output shape for F1 too (§3.3.1). It only reads buildings that already have LOD0, so it cannot start from block geometry. |

The LOD0 z convention in dtcc-core is: the LOD0 z is the **absolute roof**, `attributes["ground_height"]` is the base, and `measured_height` or `estimated_height` is the height. `set_building_heights_from_attribute` (`buildings.py:96`, `footprint.set_z(roof)` at `:170`) and `extrude_building` (extrudes LOD0 z down to `ground_height`) depend on it, and so does `Building.footprint(z="geometry")`. The proposal follows this convention throughout.

---

## 2. F2: `building_from_footprint`

### 2.1 Why
Creating a Building from a polygon and a height is the most common thing tests, demos, synthetic benchmarks (AIJ, CEDVAL, Mock Urban Setting Test…) and importers do, and dtcc-core has no API for it. Callers currently write something like this:

```python
b = Building(id="0"); b.measured_height = 8.0
b.add_geometry(Surface(vertices=np.array([[30,25,0],[30,35,0],[40,35,0],[40,25,0]], float)), GeometryType.LOD0)
```

This puts the LOD0 at z = 0, the ground, which is **the opposite of the dtcc-core convention**. dtcc-qes reads it as the base (see dtcc-qes request R3 in `DTCC_REQUESTS.md`). `extrude_building` on such a building gives a flat prism from z = 0 to `ground_height` = 0. A helper would make the convention impossible to get wrong.

### 2.2 How the validation does it
`validation/aij/cityutil.py`:

```python
def make_building(id, polygon, height, **attributes) -> Building:
    building = Building(id=id)
    building.measured_height = float(height)
    building.attributes["ground_height"] = GROUND_Z            # 0.0
    building.attributes.update(attributes)
    building.add_geometry(Surface().from_polygon(polygon, GROUND_Z), GeometryType.LOD0)   # dtcc-qes contract
    roof = Surface().from_polygon(polygon, GROUND_Z + float(height))
    building.add_geometry(extrude_surface(roof, GROUND_Z), GeometryType.LOD1)
    return building
```

- The LOD0 is placed at the **ground** only because current dtcc-qes requires it. The LOD1 prism is correct for every dtcc-core tool.
- It round-trips through `City.save(".dtcc")` and `load_city`: ids, heights, footprints, attributes and `CityObject`s are all preserved (`validation/tests/test_cities.py::test_round_trip`).

The dtcc-core version should **not** copy the ground-z LOD0; it should follow the dtcc-core convention (§2.3).

### 2.3 Proposed API
In `dtcc_core/builder/geometry_builders/buildings.py`, exported through `builder/__init__.py` (`_LAZY_IMPORTS` and `__all__`, next to `build_lod1_buildings`):

```python
def building_from_footprint(
    footprint: Polygon | Surface | np.ndarray,
    height: float,
    *,
    ground_height: float = 0.0,
    id: str | None = None,
    attributes: dict | None = None,
    height_attribute: Literal["measured_height", "estimated_height"] = "measured_height",
    lod1: bool = True,
) -> Building:
    """A Building with this footprint, standing on ground_height and `height` tall.

    LOD0 is the footprint at the roof level (ground_height + height), following
    the dtcc-core convention; attributes["ground_height"] is the base and
    `height_attribute` the height. With lod1=True the LOD1 prism is built by
    extrude_building and recorded (record_lod1), exactly as build_lod1_buildings
    would, so a later height or ground change invalidates it.
    """
```

Plus a vectorised convenience function for tables of footprints (GeoDataFrame rows, CSV, synthetic grids):

```python
def buildings_from_footprints(footprints, heights, *, ground_heights=0.0, ids=None,
                              attributes=None, height_attribute="measured_height",
                              lod1=True) -> list[Building]
```

The arguments `ground_heights`, `ids` and `attributes` each take a scalar or a sequence (or a mapping for `attributes`) and are broadcast.

**Behaviour, step by step**
1. **Normalise the footprint to a shapely `Polygon`:**
   - `Surface`: exterior ring and holes, z ignored. Use `Polygon(surface.vertices[:, :2], [h[:, :2] for h in surface.holes])`, **not** `Surface.to_polygon()`, which simplifies at 1 cm.
   - `(N, 2)` or `(N, 3)` arrays: the exterior ring.
   - A closing vertex is optional, and exact consecutive duplicates are removed.
2. **Validate**, raising `ValueError` with the building id on failure:
   - Coordinates must be finite.
   - The polygon must be valid (`explain_validity` in the message) with area > 0.
   - `height` must be finite and > 0, and `ground_height` finite.
   - A `MultiPolygon` is an error: "use one building per part, or clean_footprints". Merging silently would hide data problems.
3. **Holes are allowed.** dtcc-core `Surface` carries them, and `extrude_surface` already winds them correctly.
4. **Build the Building:**
   - `Building(id=id or uuid)`.
   - `attributes` are copied first, so that the explicit arguments win.
   - Set `attributes["ground_height"] = ground_height` and `setattr(building, height_attribute, height)`.
   - Add LOD0 as `Surface().from_polygon(polygon, ground_height + height)`.
5. **Build LOD1** if `lod1` is true: `extrude_building(building)`, then `add_geometry(..., LOD1)`, then `record_lod1(building)`. This is the same code path as `build_lod1_buildings`, so `invalidate_lod1` works later.
6. **Return** the Building, without adding it to a City. Adding it is up to the caller; `City.add_buildings` already exists.

**Decisions for the dtcc-core developer**
- **Default height attribute:** `measured_height` or `estimated_height`? The dtcc-core docstrings say `measured_height` is a source measurement and `estimated_height` a modelling result. A footprint and height given by the caller are source data, so I recommend `measured_height`, with the parameter for callers who model.
- **Model method:** decide whether to also register a City method (for example `City.add_building_from_footprint`) in `model/mixins/city/builder_mixin.py`. It is optional; the builder function is enough.
- **Footprint orientation:** decide whether to normalise it. `extrude_surface` already fixes the winding for LOD1. For LOD0, keep the input winding unless dtcc-core has a canonical orientation. dtcc-qes normalises on its side.

### 2.4 Tests (dtcc-core)
In `tests/builder/test_building_from_footprint.py`:
- **Square, height 10, ground 2:** LOD0 z all 12; `ground_height == 2`; `measured_height == 10`; LOD1 bounds z = [2, 12]; LOD1 volume = area × 10. Compute the volume from the closed MultiSurface with the divergence theorem; `extrude_surface` guarantees outward normals.
- **Polygon with a hole:** LOD0 and LOD1 keep the hole, and the LOD1 volume excludes it.
- **Input types:** `Surface` and array inputs give geometry identical to the `Polygon` input. The closing vertex is optional.
- **`height_attribute`:** `"estimated_height"` sets only `estimated_height`.
- **Errors:** `ValueError` for zero area, a self-intersecting polygon, `height <= 0`, NaN and a MultiPolygon.
- **Interplay with existing builders:**
  - `build_lod1_buildings([b], rebuild=False)` keeps the recorded prism.
  - After `b.measured_height = 20; set_building_heights_from_attribute(...)`, `invalidate_lod1` removes the stale prism.
  - `clean_footprints` reads the right roof: `_extract_source` returns roof = ground + height.
- **Round trip:** `City.save(.dtcc)` → `load_city` keeps it unchanged, and `.json` (CityJSON) too.
- **Vectorised version:** `buildings_from_footprints` broadcasts scalars and checks sequence lengths.
- **Coverage:** the strict public-API check (`make verify-public-api-strict`) needs both functions to execute in a test.

---

## 3. F1: footprints and roof levels from block geometry ("prism decomposition")

### 3.1 Why
A lot of urban geometry arrives as **3D blocks without footprints**:
- CAD drawings (DXF 3DFACE, as in the AIJ cases);
- OBJ, STL or PLY city models loaded with `load_mesh_as_city`;
- CityGML and CityJSON LOD1 solids without a LOD0;
- wind-tunnel and benchmark geometries;
- output of other tools.

Most dtcc tools are footprint-based: cleaning, height builders, terrain-aware LOD1, meshing pipelines, dtcc-qes. Today the only bridge is `Building.footprint(LOD1)`, which loses every roof level except the highest and drops small faces (§1).

For **2.5D block geometry**, meaning vertical walls with flat roofs at one or more heights, the conversion is lossless. Every column of the solid runs from one ground level to one roof level, so the solid is exactly a set of footprint polygons, each extruded from the ground to its own roof. Stepped buildings, such as a podium with a tower or a row of houses of different heights modelled as one solid, are the common case in real data. In AIJ Case E, 27 of 495 solids are stepped, with up to three levels.

### 3.2 What the validation implementation does
`validation/aij/prisms.py`, about 230 lines with shapely 2 and numpy, used for both AIJ cases. The pipeline:

```
faces (list of (3|4, 3) arrays)
  → unique()            drop repeated faces
  → components()        connected solids (vertices welded by rounding to 1e-4 m)
  → solid()             per solid: classify faces, base footprint, roof levels, checks
  → solid_parts()       one Part per (roof level, polygon piece)
  → overlay()           make parts disjoint, highest roof wins (exact boolean operations)
  → clean()             orient CCW; coordinates kept exactly (no snapping since 2026-10-31)
  → make_building()     one Building per part (F2)
```

**Step details**

1. **Face input.**
   - A DXF 3DFACE always has 4 vertices; a triangle repeats the third. `aij/dxf.py:faces` drops consecutive repeated vertices, so faces come back with 3 or 4 vertices.
   - For dtcc-core input this step becomes: a `Mesh` (triangles; `faces` index into `vertices`) or a `MultiSurface` (polygons, possibly with holes). Both reduce to a list of planar 3D polygons.

2. **`unique(faces)`.**
   - The key is the sorted tuple of vertices rounded to 1e-4 m; the first occurrence is kept.
   - **Observed:** AIJ Case D draws 48 of its 83 boxes twice. Without de-duplication, the raw "sum of top-face area × height" volume was 2,142,500 m³ instead of the true 1,374,500 m³. The footprint union is unaffected; volume checks are not.

3. **`components(faces)`.**
   - Union-find over vertex keys rounded to 1e-4 m; faces that share a vertex belong to the same solid.
   - In dtcc-core, prefer `snap_vertices(mesh, d)` (C++, `builder/meshing/meshing.py:421`) followed by `disjoint_meshes` (scipy connected components, `:473`). Rounding to a grid can split two vertices that sit on either side of a rounding boundary; distance-based snapping cannot. Rounding was safe for the AIJ data only because its coordinates are exact decimals.
   - **Welding is mandatory for face soups.** In a DXF 3DFACE list, or a MultiSurface assembled from separate faces, every face has its own vertex copies. Without welding, every face is its own component.
     - Files loaded through `load_mesh_as_city` are already welded for exact duplicates: meshio merges identical STL vertices. I checked this with an STL of two unwelded boxes (24 triangles, 72 vertices), which loads as 2 buildings.
     - Near-coincident vertices (export noise) still need distance-based snapping.

4. **`solid(faces)`: classification and checks.**
   - **Horizontal face:** `ptp(z) < 1e-6`.
   - **Vertical face:** the Newell normal satisfies `|n_z| <= 1e-6 · |n|`. The Newell method is robust for slightly non-planar quads.
   - **Anything else** raises `ValueError("neither horizontal nor vertical")`. This means sloped roofs, which are LOD2.
   - **Base:** `zmin` is the solid minimum. Base faces are the horizontal faces at `zmin`, and `footprint = union_all(base faces)`.
   - **Roof levels:** the horizontal faces above `zmin`, grouped by z rounded to 1e-4 m, with `levels[z] = union_all(faces at z)`.
   - **2.5D check:** `area(union_all(levels)) == area(footprint)` within `footprint.length × 1e-4` (perimeter × snapping grid). A mismatch means part of the roof has no base under it (an overhang or an elevated part) or part of the base has no roof (an open solid). Either way the solid is rejected.
   - **`face_volume`:** Σ over top faces of area × (z − zmin), kept for verification.
   - **No face orientation is used.** DXF 3DFACE winding is arbitrary, so top and bottom are decided by z only. See §3.4.4 for the orientation-aware variant.

5. **`solid_parts(solid)`.** One part per level and per polygon of that level; a level can be a MultiPolygon, for example two towers at the same height. Each part's height is `roof_z − zmin`.

6. **`overlay(parts)`.**
   - Parts are ranked by `(−height, key)`.
   - For each part, the union of the *original* polygons of every higher-ranked part that intersects it (found with an `STRtree` query) is subtracted, with `grid_size = 1e-4`.
   - Pieces under 0.01 m² are dropped and reported.
   - This is the same rule as the cleaning module's `precedence` "roof" rule (`builder/cleaning/blocks.py:244`).
   - **Observed in Case E:**
     - 5 solids contain stacked top faces: a lower roof face drawn under a tower. This is a modelling artefact or an internal face.
     - Across the city, 28 parts lost area to higher parts, 14.9 m² and 108.8 m³ in total, with no slivers dropped. With the earlier snapped overlay the count was 30, because snapping made two touching parts overlap.
     - The validation ran the overlay **across** solids as well, because neighbouring solids overlap by up to 2.45 m². In dtcc-core, cross-building overlap belongs to `clean_footprints` (§3.4.3).

7. **`clean(polygon)`.** Now just `orient(sign=1)`, and `overlay` runs without `grid_size`. Until 2026-10-31 it was `shapely.set_precision(p, 1e-4)`, then `simplify(1e-4, preserve_topology=True)`, with `grid_size=1e-4` in the overlay. **Both turned out to be mistakes** (next list).

**Precision lessons learned (important for the dtcc-core version; revised 2026-10-31)**
- **Do not snap at all; keep the input coordinates.** The faces of a block model share exact vertices, so exact boolean operations (`grid_size=None`) keep shared edges identical. A grid only perturbs them.
  - *First lesson:* per-level unions with `grid_size=1e-4` opened hairline T-junction gaps. The base covered 0.0014 m² more than the levels, against a perimeter × grid bound of 0.022 m². Exact level unions fixed it.
  - *Second lesson, found with dtcc-qes `wind.Footprints`:* snapping only the final pieces was still wrong.
    - Independently snapped neighbours overlapped by up to 1.9e-4 m² (20 pairs in Case E).
    - Downstream, `clean_footprints` then raised a GEOS `TopologyException` ("unable to assign free hole to a shell") while building the walls of one block, at every δ ≥ 0.2 m. That block fell back to one footprint at the tallest height.
    - With exact overlay and no `set_precision`/`simplify` (the validation's current code), the same City's worst overlap is 2e-14 m². It cleans with no fallback at δ = 0.1, 0.2 and 0.5 m. The overlay totals did not change (14.93 m², 108.84 m³).
- **Node T-junctions instead of snapping.** Where one piece's vertex lies on a neighbour's edge, insert that vertex into the neighbour's ring, so both sides carry identical vertices. Then remove only *exactly* collinear redundant vertices, keeping the inserted ones. This is what dtcc-qes does to cleaned cells before they reach native code (`dtcc_qes/_footprints.py:209` `_node_cells`, `:26` `_ring_key`). The decomposition should hand over the same shape.
- **Test with `shapely.coverage_is_valid`** over the pieces of each solid, using exact input. No coverage simplification is needed.
- **Do not use `Surface.to_polygon()` or `MultiSurface.to_polygon()` inside the decomposition.** They simplify at 1 cm and drop faces under 0.01 m². Build shapely polygons directly from the vertex arrays.
- **Weld vertices by distance, but keep the representative's exact coordinates.** Connectivity needs a tolerance; geometry does not.

**Verification invariants (all hold on the AIJ data and are covered by `validation/tests`)**
- **(a) Area:** area(union of parts) = area(union of base faces) within 1e-2 m² over the whole of Case E (51,603.66 m²).
- **(b) Volume:** Σ part area × height = `face_volume` − overlay-removed volume, to a relative 1e-4 (Case E before: 311,090.8 versus 311,202.0 − 108.8). The remaining 2.3 m³ comes from non-identical overlapping faces within one level.
- **(c) Disjoint parts:** no two parts overlap by more than 1e-9 m² (worst case 2e-14 m², floating-point noise of the exact overlay); touching is allowed (68 pairs). The snapped version reached 1.9e-4 m². For dtcc-core the target should be `coverage_is_valid` per solid, and overlap ≤ perimeter × float64 epsilon between solids.
- **(d) Case D exactness:** the volume equals 82 × 16,000 + 62,500 m³ exactly.
- **(e) Before and after agree:** the decomposition is identical for the same solids in different runs.

**Performance:** building the whole Case E City (4,953 faces, 495 solids, 533 parts), including reading the DXF, takes about 1 s on a laptop in pure Python and shapely. Shapely 2's vectorised functions and `STRtree` make the cost roughly linear in the number of solids.

### 3.3 Proposed dtcc-core design

#### 3.3.1 Geometry layer: `dtcc_core/builder/geometry_builders/prisms.py` (new)
This layer works on plain polygons and arrays and has no model mutation, so it is easy to test and reusable by the meshing and io layers.

```python
@dataclass(frozen=True)
class PrismLevel:
    roof_z: float
    polygon: Polygon            # one connected piece; may have holes

@dataclass(frozen=True)
class PrismDecomposition:
    ground_z: float
    footprint: Polygon | MultiPolygon     # union of the base faces
    levels: tuple[PrismLevel, ...]         # disjoint coverage of footprint, sorted by (roof_z, centroid)
    duplicate_faces: int                   # dropped by de-duplication
    stacked_area: float                    # top-face area removed where levels overlapped
    stacked_volume: float

class NotAPrismError(ValueError):
    """Geometry that is not a closed, vertical-walled solid on one base level.

    Attributes: reason ("sloped_face" | "overhang" | "open" | "multiple_bases"),
    location (x, y, z) of the first offending face or point.
    """

def decompose_prism(
    geometry: MultiSurface | Mesh | Sequence[np.ndarray],
    *,
    tolerance: float = 1e-4,          # metres: vertex weld, height grouping, snapping grid
    vertical_tolerance: float = 1e-6, # |n_z|/|n| below this is a wall
    min_level_area: float = 0.01,     # m², smaller level pieces are dropped (and counted)
) -> PrismDecomposition:
    ...
```

- **Align with `FootprintCell`.** A level is the same thing as a cleaning cell: one footprint piece with one roof. Use the same field names, `polygon`, `roof_z`, `height` (= `roof_z − ground_z`), `ground_height` and `source_ids`, or return `FootprintCell`s directly with `building_id` set to the source id and `part_id=None`. Consumers such as dtcc-qes `prepare_footprints`, which already iterates over `building_cells`, can then take either source without a translation layer.
- **Input:** one solid. Callers split multi-solid input with `disjoint_meshes`, or take one Building's LOD1.
- **MultiSurface surfaces:** surfaces can carry holes (a roof with a courtyard), so build `Polygon(exterior, holes)`.
- **Mesh input:** convert triangles to polygons directly, or call `merge_coplanar` first to cut the face count (it exists: `builder/surface/modify.py:29`). The algorithm is correct either way, because unions handle triangulated faces.
- **Steps:** de-duplication, classification, base, levels, the 2.5D check and the in-solid overlay are as in §3.2, with the precision rules above.
- **Errors:** raise `NotAPrismError` with a reason, never a bare `ValueError`, so batch callers can count failures by reason.

#### 3.3.2 Model layer: `footprints_from_lod1` in `buildings.py`

```python
def footprints_from_lod1(
    buildings: City | Sequence[Building],
    *,
    lod: GeometryType = GeometryType.LOD1,
    levels: Literal["split", "highest"] = "split",
    height_attribute: Literal["measured_height", "estimated_height"] = "measured_height",
    on_error: Literal["raise", "warn", "skip"] = "warn",
    tolerance: float = 1e-4,
    min_level_area: float = 0.01,
    overwrite_lod0: bool = False,
) -> City | list[Building]:
    """Derive LOD0 footprints, ground_height and heights from block geometry.

    Each building's `lod` geometry (flatten_geometry) must be one or more closed,
    vertical-walled solids with flat roofs. levels="split" returns one Building
    per roof-level piece (ids "<id>" for a single level, "<id>#<n>" otherwise,
    attributes source_id=<id>, roof_level=<n>), each built with
    building_from_footprint (F2) on the solid's ground. levels="highest" keeps one
    Building per input with its full footprint at the highest roof (lossy,
    like Building.footprint) and leaves its LOD1 untouched.
    """
```

**Behaviour**
1. **Select inputs:**
   - For each Building, use `geometry = building.flatten_geometry(lod)`.
   - Skip buildings that already have LOD0 unless `overwrite_lod0` is set.
   - A Building whose LOD1 holds several disconnected solids: split them first, using the same weld-and-components step, and treat each as a solid with ids `<id>/<k>`. Alternatively raise; decide which.
2. **Decompose:** `decompose_prism(solid)`. On `NotAPrismError`, follow `on_error`: re-raise, or keep the building unchanged and log a warning or an info message. Count the failures by reason in a summary returned in `city.attributes["footprints_from_lod1"]`, mirroring how `clean_footprints` records `footprint_cleaning`.
3. **`levels="split"`** (default, lossless):
   - Each level piece becomes `building_from_footprint(piece, roof_z − ground_z, ground_height=ground_z, id=..., attributes=source attributes + {source_id, roof_level})`.
   - The new LOD1 prisms reproduce the input solid exactly (invariant (b)), so the input LOD1 is not copied, and the output carries no stale geometry.
   - The ids follow the cleaning module's `<source id>#<n>` convention (`blocks.py` module docstring).
4. **`levels="highest"`:**
   - The Building gets LOD0 = full footprint at the highest roof, `ground_height = ground_z`, and height = max roof − ground.
   - The original LOD1 is left in place. It is unrecorded, so `invalidate_lod1` will preserve it.
   - This is the lossy mode that matches what `clean_footprints` does today.
5. **Return the same type as the input:** a City (copied, like `clean_footprints` does with `_copy_city_without_buildings`) or a list.

**Why one Building per level rather than BuildingParts or a "block"**
- A **block** in dtcc-core is a Building with `merged_from`, `BuildingPart`s, source footprints and a **versioned walls record** (`footprint_walls`, `WALLS_VERSION = 2`). `walls_of` (`blocks.py:419`) raises for any block not made by `clean_footprints`. Writing that record by hand would couple F1 to the cleaning internals.
- A **non-block Building with parts** is not extruded per part by `build_lod1_buildings`, which handles parts only for blocks (`buildings.py:411-431`). Other consumers, such as dtcc-qes today, reject parts entirely.
- **dtcc-qes now confirms this choice.**
  - Both of its modes reject `BuildingPart`s and nested Buildings outright (`dtcc_qes/_city.py:107-138`).
  - Its contact-aware mode, `wind.Footprints`, expects exactly this input: separate, touching or overlapping LOD0 Buildings with their own heights.
  - It runs `clean_footprints` itself, once, on flat copies.
  - So F1's "split" output can go straight into `wind.run(city, ..., footprints=wind.Footprints(...))`. A City that has already been cleaned into blocks cannot, because its parts are rejected.
- **Separate Buildings with `source_id`** are fully supported by every existing builder.
- **Correction (2026-10-31): cleaning the output into blocks.** I first wrote that users who want blocks can run `clean_footprints` on the output and that cleaning at any positive `min_building_detail` merges touching levels into a block with proper walls. That is not true today.
  - At δ ≤ 0.05 m, `clean_footprints` fails with `no_fixed_fallback_satisfied_handoff` even on two hexagons that share one full edge (a plain two-level building), or on two quads touching at a corner. Request R6 has the WKT.
  - It works at δ ≥ 0.1 m on exact input.
  - Until R6 is fixed, document δ ≥ 0.1 for this use.
- **Follow-up for the dtcc-core team: `block_from_cells(cells, region)`.** This would be the inverse of `building_cells`: a constructor that writes a valid walls record with outcome `single` or `strict` for exact, already-disjoint cells. F1 output is exactly such cells, so F1 could emit blocks without the cleaning search, which would also avoid R6 for this input. This is a design decision inside the cleaning module, so I list it as an option, not a requirement.

#### 3.3.3 io integration (optional, opt-in)
- Add `derive_footprints: bool = False` to `load_mesh_as_city` (`io/meshes.py:735`), which calls `footprints_from_lod1(city, on_error="warn")` after loading.
- Keep it opt-in so the existing loader output does not change.
- Consider an optional `snap` distance for exports with near-coincident vertices. meshio already merges exact duplicates, so unwelded STL splits correctly, but the loader's `disjoint_meshes` split relies on shared vertex indices, so vertices that differ by export noise would split a building.
- **A DXF reader is not part of this proposal.** The AIJ files need case-specific handling of nested blocks (a recursive resolve duplicated the whole city, including a copy lifted by 2.4 m), and adding ezdxf as a dtcc-core dependency for that is not worth it. If dtcc-core wants DXF later, the generic part is roughly 40 lines over ezdxf: 3DFACE vertices plus `Insert.matrix44()` (`validation/aij/dxf.py`).

#### 3.3.4 Relation to existing functions
- **`Building.footprint(LOD1)`:** keep it unchanged. Document that it returns only the outer outline at the highest roof, and point to `footprints_from_lod1` for heights and levels.
- **`clean_footprints`:**
  - F1 resolves overlaps **inside one solid** only (stacked faces), with the same "highest roof wins" rule as `blocks.precedence`.
  - Overlaps **between** buildings remain `clean_footprints`' job.
  - Recommended pipeline for messy CAD or mesh input: `load_mesh_as_city(..., derive_footprints=True)`, then `clean_footprints(city, min_building_detail=δ)`, then `build_lod1_buildings`.
- **`build_lod1_buildings`:** F1's "split" output already carries recorded LOD1 prisms from F2, so `rebuild=False` keeps them and `rebuild=True` regenerates identical ones.

### 3.4 Things the validation did not need but dtcc-core should consider

1. **Elevated and overhanging volumes (phase 2).**
   - AIJ Case E has 32 raised slabs: arcade roofs at 2.4–2.9 m, canopies at 3.0–3.5 m and pilotis volumes at 4–6 m. Real data also has cantilevers and passages through buildings.
   - The 2.5D check rejects all of these today. The general algorithm is a **z-interval decomposition**:
     1. Overlay all horizontal faces of a solid into a planar arrangement, using `shapely.union_all` of the boundaries and `polygonize`.
     2. For each arrangement cell, take the sorted z values of the horizontal faces covering it.
     3. Pair them into solid intervals: by face orientation (down-facing face = interval start) when the input is consistently oriented, otherwise by even–odd parity after de-duplication.
     4. Merge adjacent cells with identical interval lists.
   - The result is a set of prisms `(polygon, z_bottom, z_top)`; the 2.5D case is the special case of one interval starting at the ground.
   - **Representation:**
     - Geometrically, dtcc-core can already express a raised prism: LOD0 at `z_top`, `ground_height = z_bottom`, and `extrude_building` produces it.
     - Semantically, though, `ground_height` means terrain level and `set_building_heights_from_attribute` overwrites it from terrain.
     - So raised volumes need a separate attribute (for example `base_height`) or object type.
     - This is the same need as dtcc-qes request R2. The AIJ validation currently stores the slabs as generic `CityObject`s with `kind`, `zmin` and `zmax` and an LOD1 box (`cityutil.make_elevated`).
     - **Keep raised prisms out of 2D footprint cleaning.** `clean_footprints` and dtcc-qes `prepare_footprints` work in plan view with height precedence. An arcade slab next to a façade would be merged into the building or cut by it, as if it stood on the ground. Raised prisms need their own path, or cleaning per z-interval.
2. **Sloped faces.** These are LOD2 and out of scope. A `sloped="highest"|"mean"` policy could flatten them into LOD1 levels, but that is generalisation, a different feature. The default stays raising `NotAPrismError("sloped_face")`.
3. **Terrain.** The base of a solid is its own `zmin`, and F1 stores it as `ground_height`. Solids on sloping terrain have non-flat bases (multiple base z values, `"multiple_bases"`). Options are to take the lowest base z (`ground_height = zmin`, which slightly buries the building as the terrain-aware builders already do) or to reject. I recommend the lowest base z with an info-level report, consistent with `ground_height_strategy="vertex"`.
4. **Orientation use.** When a `Mesh` has consistent normals, use them for up and down classification. This removes the ambiguity of stacked faces (internal face or overhang underside) that the z-only method resolves by taking the highest roof.
5. **Units.** All tolerances are in metres in the local frame, and the transform and CRS are kept from the input Building.

### 3.5 Tests (dtcc-core)
In `tests/builder/test_prism_decomposition.py` (geometry layer) and `tests/builder/test_footprints_from_lod1.py` (model layer):

**Synthetic fixtures** (no data files needed), each built as a closed MultiSurface and also as a triangulated, unwelded Mesh:

| Fixture | Expected |
|---|---|
| Box 10×10×6 on ground 2 | 1 level, `ground_z = 2`, roof 8 |
| L-shape | 1 level, non-convex polygon kept exactly |
| Podium 20×20×6 with a centred tower 6×6×30 | 2 levels; the podium level has a hole; areas 364 and 36 |
| Tower at the podium edge | 2 levels, touching, no hole |
| Two towers on one podium at the same height | the level is a MultiPolygon, giving 2 pieces with ids `#n` |
| Stacked internal face (a podium top drawn under the tower too) | 2 levels, `stacked_area == 36` |
| Each box drawn twice | `duplicate_faces == 6`, same result as once |
| Unwelded face soup (every face with its own vertex copies), plus a variant with 1e-6 noise | same result as welded |
| Hip roof (sloped faces) | `NotAPrismError(reason="sloped_face")` |
| Cantilever (top face larger than base) | `NotAPrismError(reason="overhang")` |
| Box floating at z 3–4 | `NotAPrismError` in phase 1, a raised prism in phase 2 |

**Assertions**
- `coverage_is_valid(levels)`.
- The union of levels equals the footprint within perimeter × tolerance.
- Σ level area × (roof − ground) equals the solid's divergence-theorem volume, for oriented input.
- The "split" output, run through `build_lod1_buildings(rebuild=True)`, reproduces the volume.
- Ids and `source_id` are set.
- `on_error` modes behave as specified, and the failure summary is recorded in the City attributes.
- The output passes `clean_footprints(min_building_detail=δ)` for δ in {0.1, 0.5}, giving blocks for touching levels with no wall fallbacks. Add δ = 0.01 once R6 is fixed.
- No vertex is snapped: every output vertex is an input vertex or a T-junction node, and `coverage_is_valid` holds per solid.

**Real-data regression (optional):** the AIJ DXFs (Case D 352 KB, Case E 3.5 MB) exercise duplicate faces, T-junction precision, stacked faces and 27 stepped solids. **Check redistribution terms first** (AIJ guidebook data) before copying them into `tests/data`. The synthetic fixtures above cover every behaviour seen in them.

---

## 4. Suggested PR sequence (following dtcc-core `AGENTS.md`)

1. **PR 1, F2:** `building_from_footprint`, `buildings_from_footprints` and tests. Small; no sensitive paths.
2. **PR 2, F1 geometry layer:** `prisms.py` with `decompose_prism`, `PrismDecomposition` and `NotAPrismError`, and tests. Pure functions.
3. **PR 3, F1 model layer:** `footprints_from_lod1`, the City-attribute summary, docs in the `Building.footprint` docstring, and tests (including the `clean_footprints` and `build_lod1_buildings` interplay).
4. **PR 4 (optional):** `load_mesh_as_city(..., derive_footprints=False)` and an STL welding check or fix.
5. **Later:** the phase 2 z-interval decomposition and a `base_height` convention, together with dtcc-qes R2. A `block_from_cells` constructor if the cleaning owners want it.
6. **Independent of F1/F2, for the cleaning owners:** fix R6 (`clean_footprints` unresolved at δ ≤ 0.05 on a shared edge or a corner contact), with the two WKT pairs from `DTCC_REQUESTS.md` as regression tests. F1's δ = 0.01 test depends on it.

Each PR follows the dtcc-core checks:
- `make verify-public-api-strict` (every new `__all__` function executed in a test);
- `uv run ruff check . && uv run ruff format --check .`;
- one demo run end to end.

No C++ changes are needed. The working plan belongs in dtcc-core's `.agent/plans/`; per `AGENTS.md`, this document is not to be committed there.

## 5. Open decisions for the dtcc-core developer
1. **Height attribute:** should geometry-derived and caller-given heights go to `measured_height` (my recommendation) or `estimated_height` by default?
2. **Multi-solid LOD1:** split into `<id>/<k>`, or reject?
3. **Stepped output:** separate Buildings with `source_id` (my recommendation) for now, or invest in `block_from_cells` so F1 can emit blocks?
4. **Default tolerances:** 1e-4 m weld and grid, and 0.01 m² minimum level piece.
5. **Raised volumes:** confirm the semantics of `ground_height` versus a new `base_height` before phase 2, and align with dtcc-qes (R2, R3).
6. **Level type:** should `decompose_prism` return `FootprintCell`s directly, or a `PrismLevel` with the same field names (§3.3.1)?

## 6. What changes in dtcc-qes and the validation afterwards
- **Already possible, without F1 or F2.** Since the dtcc-qes merge, the validation's exact Case E City (touching parts) runs through `wind.Footprints(min_detail=0.1)`. The merged "QES-ready" City (+5 % volume) is no longer needed for the simulation.
- **dtcc-qes (R3):** once dtcc-qes reads the dtcc-core convention (LOD0 z = roof, `ground_height` = base), the AIJ builders replace `cityutil.make_building` with `builder.building_from_footprint` and `aij/prisms.py` with `builder.footprints_from_lod1`. R3 is still open: two buildings with roof-z LOD0 are rejected as "incompatible base elevation", and with `terrain="flat"` the ground silently moves to the lowest roof.
- **Faces in a City:** to get the DXF faces into a City, wrap each AIJ solid's faces in a `MultiSurface` as the LOD1 of a Building. Only the AIJ-specific DXF composition (`aij/dxf.py`, `aij/case_e.py:load`) stays in the validation folder.
- **Acceptance test for the migration:** `validation/tests` passes unchanged against the dtcc-core implementation. That means the same 83, 533 and 536 building counts, volumes and touching pairs, overlaps below 1e-9 m², and acceptance by `wind.Footprints` with no fallback.

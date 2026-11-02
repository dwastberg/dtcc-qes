# CAD building import for dtcc-core

Investigation and implementation proposal, 2026-11-01.

Audience: the dtcc-core development team. The immediate evidence comes from
the AIJ wind-validation models in dtcc-qes, but the proposed interfaces and
geometry operations are intended for general CAD building models.

## 1. Recommendation

Add a DXF reader to dtcc-core, integrated with `io.load_city`, and reuse the
existing building construction and LOD1-to-footprint conversion APIs. A common
user workflow can reasonably be:

```python
# Proposed API; DXF support is not implemented yet.
from dtcc_core import io

city = io.load_city("district.dxf", layers=["Buildings"], derive_footprints=True)
```

This is achievable for drawings containing polygonal building geometry with
sufficient layer or block organization. It does not require a new CAD kernel.
It does require precise contracts for selection, instances, units, geometry
grouping and failed conversions.

The implementation should separate three things:

1. **Reading the drawing:** select entities, resolve instances and coordinates,
   and preserve source information.
2. **Interpreting building geometry:** identify components and optionally derive
   footprint/height representations, with validated normalization or repair.
3. **Preparing an application model:** resolve overlaps, simplify buildings,
   choose physical roles, or adapt to a particular solver.

These stages should be independently usable and testable. The convenience
loader can compose them without making users write the intermediate plumbing.

For the particular AIJ Case E file, layers alone cannot express the desired
selection: buildings, canopies, markers and the ground plate all use the same
layer. Block and instance selection are therefore essential additions to the
simple layer-based interface. This is a general CAD requirement, not a reason
to add AIJ-specific branches to dtcc-core.

## 2. Scope and evidence

### 2.1 Code and versions inspected

The investigation covered these dtcc-qes files:

- [validation/build_cities.py](validation/build_cities.py): orchestration,
  serialization, plots and geometry/grid reports.
- [validation/aij/dxf.py](validation/aij/dxf.py): DXF face extraction and block
  placement.
- [validation/aij/prisms.py](validation/aij/prisms.py): duplicate removal,
  connected components, roof-level decomposition and overlap resolution.
- [validation/aij/cityutil.py](validation/aij/cityutil.py): DTCC object
  construction, QES adaptation and diagnostics.
- [validation/aij/case_d.py](validation/aij/case_d.py) and
  [validation/aij/case_e.py](validation/aij/case_e.py): benchmark-specific choices.
- [validation/tests/test_cities.py](validation/tests/test_cities.py): regression
  and agreement tests.
- [validation/AIJ_CITY_MODELS.md](validation/AIJ_CITY_MODELS.md) and
  [validation/DTCC_REQUESTS.md](validation/DTCC_REQUESTS.md): earlier observations
  and outstanding requests, especially R5.

The installed dtcc-core and the neighboring source checkout identify revision
`66c81a296ccea390466d20b2962fd7e33542ea41`, branch `dev/qes-updates`.
Relevant core implementation files are:

- `dtcc_core/io/city.py` and `dtcc_core/io/generic.py`;
- `dtcc_core/io/meshes.py`;
- `dtcc_core/builder/geometry_builders/buildings.py`;
- `dtcc_core/builder/geometry_builders/prisms.py`;
- `dtcc_core/builder/geometry_builders/prism_buildings.py`;
- `docs/buildings-from-footprints.md`, `docs/buildings-from-lod1.md` and
  `docs/design/lod1-prism-decomposition.md`.

The dtcc-qes checkout HEAD was `fafa08b`; the validation directory and dependency
changes were present in the working tree. Consequently, the linked validation
files, rather than that commit alone, define the investigated implementation.
The installed ezdxf version was 1.4.5. Conclusions about existing APIs refer to
this inspected revision, not an assertion about all released versions.

### 2.2 Checks performed

1. Read the orchestration and all relevant support code, following the actual
   construction paths for both cases.
2. Read both DXFs with ezdxf and counted layers, model-space entities, direct
   block faces and nested references.
3. Recursively decomposed Case E and counted both raw and deduplicated faces.
4. Selected Case E's two building blocks at their model-space placements,
   extracted direct faces, and ran the existing prism/overlay pipeline.
5. Constructed deliberately invalid face sets to check what the lightweight
   custom prism validation actually guarantees.
6. Ran the complete city test module:

   ```sh
   .venv/bin/python -m pytest validation/tests/test_cities.py -q
   ```

   Result: **28 passed in 44.40 seconds**. This includes DTCC round trips,
   geometry counts, point checks, QES checks and comparison with core's strict
   footprint decomposition.

These checks establish the behavior of the current workflow. They do not
validate a new general importer: no production importer or repair algorithm
was implemented in this investigation. The API examples marked “proposed”
below are design suggestions.

## 3. What the one-off solution does

### 3.1 `build_cities.py` is an orchestration script

The script builds five variants: Case D, Case E before and after construction,
and two historically QES-compatible merged Case E variants. It saves `.dtcc`
files, makes plots, checks measurement points and runs grid preparation checks.

Most of that code is benchmark tooling. It should not become part of CAD I/O.
The reusable work is further down the call graph:

```text
DXF file
  -> selected direct faces + composed insertion transforms
  -> units and experiment scale
  -> duplicate removal and connected components
  -> LOD1 solids / horizontal roof-level parts
  -> optional overlap resolution
  -> DTCC Buildings and other CityObjects
  -> application-specific checks and transformations
```

### 3.2 Case D: simple solids, duplicate faces, external model scale

The drawing has 786 `3DFACE` entities in model space, all on layer `一般`.
Its layer table is `0`, `一般`, `寸法`, `Defpoints`. `$INSUNITS` is 4
(millimetres). There are no model-space INSERTs.

The drawing represents 83 boxes, with 48 boxes drawn twice. After duplicate
removal there are 82 low blocks and one tower. The essential current code is:

```python
# Extract from validation/aij/case_d.py; imports omitted.
factor = scale / 1000.0
faces = prisms.unique([face * factor for face in dxf.faces(doc.modelspace())])
solids = prisms.components(faces)
source = City()
for i, solid_faces in enumerate(solids):
    source.add_building(lod1_building(f"solid-{i:03d}", solid_faces))
derived = footprints_from_lod1(source)
```

Here `scale=400` converts the wind-tunnel model to full scale, in addition to
millimetres-to-metres conversion. The effective coordinate factor is 0.4.
The result is 82 buildings of 40 × 40 × 10 m and a tower of 25 × 25 × 100 m.
Their volume is 1,374,500 m³.

The rest of the Case D builder checks expected counts and dimensions, identifies
the tower, assigns grid row/column IDs and attaches measurement metadata.
Those are benchmark assertions, not importer defaults.

**General lesson:** drawing units and physical-model scale are different inputs.
An importer can read millimetres from the file; it cannot infer a 1:400
experimental scale from those units.

### 3.3 Case E: semantics live in blocks, not layers

The file declares metres (`$INSUNITS=6`). Its layer table is `0`, `一般`, `寸法`,
`木`, `Defpoints`, but all relevant direct faces and INSERTs use `一般`.

The five model-space INSERTs refer to the arcade, pilotis, canopy, new complex
and existing city blocks. The useful semantic categories are:

| Block | Direct 3DFACE count | Interpretation in this study |
|---|---:|---|
| `市街地地図 (3D)` | 4,953 | Existing buildings |
| `高層建築・集合住宅 (3D)` | 18 | Three new buildings |
| `アーケイド (3D)` | 167 | Arcade roof slabs |
| `屋根 (3D)` | 62 | Canopies |
| `ピロティ- (3D)` | 18 | Raised volumes |
| `NW4 (3D)` | 5,760 | Measurement-marker spheres |
| `敷地 (3D)` | 6 | Ground plate |

The existing city and new buildings have direct model-space placements with
translation `(26.5, -35.5, 0)`. Other objects have elevated placements. Markers
and the ground plate are reached through the new-complex block.

The blocks repeatedly insert other blocks. In particular, the new-complex
block repeats existing-city, arcade and canopy references; the arcade itself
also contains an existing-city reference. Following those placements creates
both coincident duplicates and a copy of the city shifted upward by 2.4 m.

The current workaround is explicit:

```python
# Extract from validation/aij/dxf.py.
def block_faces(doc, name: str, matrix: Matrix44) -> list[np.ndarray]:
    """The block's own 3DFACEs (no nested INSERTs), placed with matrix."""
    return faces(doc.blocks.get(name), matrix)
```

`faces()` deliberately skips INSERTs, and `case_e.load()` chooses one placement
for each category. `insert_matrix()` requires exactly one matching insertion
in the supplied parent; it raises otherwise. Nested placements compose matrices
innermost first with `Matrix44.chain`.

This is an intentional interpretation of this drawing. It is not a correct
default for all CAD: repeated block references commonly represent distinct,
legitimate objects.

### 3.4 Quantitative reproduction

The fresh inventory and extraction checks produced:

| Operation | Result |
|---|---:|
| Recursively expand Case E model space | 57,443 faces |
| Deduplicate those expanded faces using the existing helper | 15,980 faces |
| Select direct existing-city block geometry | 495 connected solids |
| Select direct new-complex geometry | 3 connected solids |
| Convert selected ground buildings to roof-level parts | 536 parts |
| Parts trimmed by highest-roof overlay | 28 |
| Parts dropped by the configured area threshold | 0 |
| Overlay removed area | 14.929535564973776 m² |
| Overlay removed volume | 108.83846121787792 m³ |
| Final ground-building volume | 356,173.1768509952 m³ |

The 15,980 count is the output of the current rounded-vertex deduplication
function, not a claim about an exact CAD equivalence relation.

The result before adding the new complex is 533 parts. There are also 32 raised
objects: 21 arcade slabs, 8 canopies and 3 pilotis volumes. They are represented
as generic CityObjects rather than ground-supported Buildings in this study.

Case E's documented experiment scale is 1:250, but its DXF coordinates are
already full-scale metres. Applying 250 again would be incorrect. The current
City's `scale=250` is experiment metadata, not the coordinate conversion factor.
The proposed import report must distinguish those concepts explicitly.

## 4. What dtcc-core already provides

### 4.1 Building construction is already solved

The validation helper is almost entirely a wrapper:

```python
# validation/aij/cityutil.py
GROUND_Z = 0.0

def make_building(id, polygon, height, **attributes):
    return building_from_footprint(
        polygon, height, ground_height=GROUND_Z, id=id, attributes=attributes
    )
```

The public core constructor accepts a Shapely Polygon, DTCC Surface or exterior
ring array. It preserves holes and creates consistent height attributes, LOD0
and optional LOD1 extrusion records. No second implementation belongs in a DXF
module.

The important convention is:

```text
ground_height = absolute base elevation
measured_height = roof elevation - base elevation
LOD0 z = roof elevation
LOD1 = extrusion between base and roof
```

The generic importer must retain nonzero bases. `GROUND_Z=0` is a benchmark
assumption and must not be copied into core's importer.

### 4.2 Strict prism decomposition already exists

The public entry point at the inspected revision is:

```python
def footprints_from_lod1(
    buildings,                  # City or sequence of Buildings
    *,
    tolerance=0.002,             # local metres
    wall_angle_tolerance=0.1,    # degrees
    overwrite_lod0=False,
    on_error="raise",           # or "warn"
):
    ...
```

It handles closed vertical-column solids with a flat base and horizontal roofs,
including concavities, holes and multiple roof levels. It returns independent
objects, assigns stable split IDs, and records provenance and numerical
residuals. It rejects unsupported geometry rather than approximating it.

The private kernel already contains vertex clustering, edge noding, duplicate
face handling, shell checks, roof/base coverage checks, wall validation and
volume budgets. Extend those mechanisms rather than introducing a second
unrelated decomposition algorithm in `io/dxf.py`.

Case D already uses this API successfully. For Case E, the agreement test wraps
all 530 solids (495 existing, 3 new, 32 raised) as LOD1 Buildings for comparison.
Core converts 497 and rejects 33, all from the existing buildings. On the
converted solids, ground and height agree with the custom method, and footprint
symmetric-difference area is below 1e-6 m².

`on_error="warn"` retains a complete source copy when conversion fails. It does
not produce a usable footprint for every object. The CAD loader must preserve
and explain this distinction.

### 4.3 Mesh loading supplies an integration precedent

Core already has:

```python
from dtcc_core import io

city = io.load_mesh_as_city("buildings.stl", derive_footprints=True)
```

It composes geometry loading with the public footprint converter. DXF loading
can follow this pattern. The current `io/city.py` format registry contains
`.dtcc`, CityJSON and several mesh formats, but no `.dxf` entry.

One integration detail: at this revision, `io.city._load_mesh_city` does not
forward the new footprint-conversion options, even though
`load_mesh_as_city` supports them. A DXF adapter should explicitly accept and
forward its own supported options rather than assuming every format handler
already has an identical signature.

## 5. Why the custom prism helper is not ready to become a core API

The validation implementation works because the source data was inspected and
the outputs have benchmark-specific checks. Its acceptance conditions are
weaker than its intended geometric interpretation.

### 5.1 Equal areas do not establish spatial coverage

The current `solid()` check is:

```python
covered = shapely.union_all(list(levels.values()))
if abs(covered.area - footprint.area) > footprint.length * GRID:
    raise ValueError("... roofs do not cover the base exactly ...")
```

Two disjoint polygons can have the same area. A general implementation must
compare the actual base/roof coverage, using symmetric difference and boundary
residuals with documented tolerances. Core's existing `_coverage` machinery is
a better starting point than this scalar test.

### 5.2 Wall orientation is not shell validation

`solid()` checks that any nonhorizontal faces are vertical, but does not require
walls to exist or prove that they enclose the base and roof. The following
reproducer was run against the current helper:

```python
import sys
import numpy as np

sys.path.insert(0, "validation")
from aij import prisms

base = np.array(
    [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=float
)
roof = base + [0, 0, 1]

assert prisms.solid([base, roof]).face_volume == 1.0
assert prisms.solid([base, roof + [2, 0, 0]]).face_volume == 1.0
```

Both calls are accepted: the first has no walls; the second also has its roof
completely displaced from its base. These should become rejection tests for
the core implementation, not examples of an acceptable automatic repair.

### 5.3 Grouping and deduplication require explicit contracts

The helper groups faces by shared vertices rounded to four decimal places.
This can join buildings that only touch at a point, and it can miss meaningful
edge adjacency where vertices do not coincide. Rounding also does not implement
a true distance threshold: arbitrarily close points on opposite rounding-cell
boundaries may remain separate.

Duplicate faces are identified by a sorted set-like sequence of rounded
vertices. This ignores winding, but also ignores cyclic boundary connectivity
and does not recognize all equivalent triangulations. Core should distinguish:

- duplicate faces within a source shell;
- duplicate shells within one selected source;
- coincident but distinct inserted objects;
- overlapping surfaces with different tessellations.

Do not collapse all four categories with one global coordinate hash. Preserve
source membership, report geometric deduplication, and retain valid separate
instances by default.

### 5.4 The overlay has stronger assumptions than its signature shows

`prisms.Part` stores a relative height but no base elevation. The overlay sorts
by that height and removes areas covered by higher-ranked parts:

```python
# Essential operations from validation/aij/prisms.py.
ranked = sorted(parts, key=lambda p: (-p.height, p.key))
cover = shapely.union_all([originals[j] for j in higher])
geometry = shapely.difference(part.polygon, cover)
```

This is correct for the chosen common-ground envelope model. With different
bases, relative height does not establish which roof is higher. Even ranking
absolute roofs cannot represent a bridge and a building separated vertically.

The helper also drops pieces smaller than `min_area=0.01` m². That is a modeling
policy, not numerical noise removal. A core operation should preserve positive
features by default and require an explicit threshold for intentional deletion.

## 6. Proposed public interface

All API additions in this section are proposals. The exact names should follow
core conventions; the behavioral distinctions matter more than the spelling.

### 6.1 Simple loading and explicit derivation

```python
from dtcc_core import io

# Proposed: selected source surfaces, without deriving footprint prisms.
source = io.load_city("district.dxf", layers=["Buildings"])

# Proposed: convenience composition with the existing builder contract.
city = io.load_city(
    "district.dxf", layers=["Buildings"], derive_footprints=True
)
```

Default `derive_footprints=False` follows the mesh-loader precedent and avoids
silently flattening an arbitrary building model. The two-line convenience
still gives the desired user experience.

The reader should retain polygonal surfaces without claiming that every input
is a valid closed LOD1 solid. Selected building geometry can be wrapped in
Buildings under an explicit representation contract; unusual or sloped source
geometry must not be advertised as a validated prism. A later, richer CAD
object API can support source roles/LoDs where required.

### 6.2 Inspection before interpretation

```python
# Proposed: inspect without building or repairing geometry.
info = io.inspect_dxf("district.dxf")
print(info.layers)
print(info.blocks)
print(info.instances)
print(info.units)
```

Return a structured result with a readable representation, including:

- raw layer names and direct entity counts by type;
- block definitions and direct versus descendant counts;
- model-space instance handles, block names and insertion paths;
- unit metadata, extents and transform summaries;
- selected versus unselected unsupported entity types;
- nested reference relationships, unresolved references and expansion limits;
- potential coincident instances as diagnostics, not automatic deletions.

This is especially useful when layer names are unfamiliar or everything uses
layer `0` or a generic layer. Expensive recursive counts and transformed bounds
can be opt-in; inspection should not require solid reconstruction.

### 6.3 Layer semantics

Use layer names, including numeric names. If integers are accepted, normalize
`layers=[12]` to the layer named `"12"`, not the thirteenth layer in a table.
An inspection UI may expose row numbers, but should return stable names or
handles for API use. Apply the DXF library's name lookup rules, retain original
spelling, and handle Unicode names without transliteration.

Specify whether filtering uses the entity's raw layer or its effective layer
inside an INSERT. Recommend effective-layer selection by default, with raw-layer
selection available explicitly. Layer `0` inside a block inherits the insertion
context; a child on an explicitly named layer retains that layer. Track both
values in provenance. The installed ezdxf drawing implementation demonstrates
this resolution in `addons/drawing/properties.py`.

Do not prune an entire INSERT solely because its own layer is unselected:
descendants may lie on selected named layers. Conversely, selecting an INSERT
layer should not implicitly override explicit child layers. If selecting whole
subtrees is needed, expose block/instance selection for that purpose.

Visibility is separate from selection. A useful reproducible default is to load
explicitly selected layers regardless of CAD display state, recording hidden
or frozen status; a visible-only mode can be explicit.

### 6.4 Blocks and instances

```python
# Proposed Case E selection: use both direct model-space building blocks.
city = io.load_city(
    "CaseE(Niigata).dxf",
    blocks=["市街地地図 (3D)", "高層建築・集合住宅 (3D)"],
    include_nested=False,
    derive_footprints=True,
    repair="vertical_prisms",
    overlaps="highest_roof",
)
```

For a minimal initial implementation, define `blocks=` as selection of matching
model-space INSERT instances. It selects every matching instance, not one copy
of the block definition. `include_nested=True` should be the normal traversal
default. `False` selects only the directly owned geometry of those instances.
If both layers and blocks are given, apply layer filtering within the selected
instances; document the intersection rather than implying a union.

Selecting a block that exists only as a nested reference should produce a clear
message and available paths, not silently import an unplaced definition.
An advanced selector should accept explicit insertion paths, for example a
sequence of INSERT handles returned by inspection. Handles in the following
example are placeholders:

```python
# Proposed later addition: choose one nested occurrence unambiguously.
city = io.load_city(
    "district.dxf", instance_paths=[("ROOT_HANDLE", "CHILD_HANDLE")]
)
```

Never infer a unique placement from a block name when multiple instances exist.
Guard recursive cycles using the active insertion path, not a global visited
block-name set: a global set would incorrectly remove legitimate reuse.

### 6.5 Units, scale and coordinate frames

```python
# Proposed: units read as millimetres; explicit experimental enlargement.
city = io.load_city(
    "CaseD(Highrise+Blocks).dxf",
    layers=["一般"], model_scale=400, derive_footprints=True,
)

# Proposed: resolve a unitless drawing using supplied source units.
city = io.load_city("district.dxf", layers=["Buildings"], units="mm")
```

Use `$INSUNITS` when meaningful, with an explicit override. For unitless or
unusable metadata, raise an actionable error requiring units; do not guess
metres from the drawing's size. An override should be recorded alongside the
original declaration.

For source coordinates, the intended pipeline is:

```text
block-local point
  -> composed INSERT placement into drawing coordinates
  -> drawing-unit conversion to metres
  -> explicit physical-model scale, default 1
  -> optional documented local-origin/frame transformation
```

Block-unit metadata does not justify multiplying an additional factor after
applying the INSERT transform: unit differences are normally represented in
the insertion's scaling. Validate and report inconsistencies rather than
double-scaling. See the [ezdxf units documentation](https://ezdxf.readthedocs.io/en/stable/concepts/units.html).

Preserve the drawing frame by default. Do not automatically centre the city,
move its ground to zero, infer north, or invent a CRS. If a local origin is
requested for numerical stability, retain a reversible transform and test
save/load behavior. Setting a CRS label and reprojecting coordinates are
different operations.

Apply rotations and scales to CAD vertices before invoking the current prism
kernel, whose geometry frame contract permits translation-only metre frames.
Check whether the transformed geometry still satisfies vertical-prism
assumptions. A tilted box is legitimate source geometry but not a vertical
prism. Reflections require winding/orientation handling. Anisotropic scaling
must be tested or rejected explicitly, not silently approximated.

For georeferenced drawings, applying a physical-model scale about world zero
can move the site unintentionally. Document that `model_scale` scales the source
frame about its origin; require an explicit anchor/frame operation when another
scaling origin is intended.

## 7. Implementation architecture

### 7.1 Reader boundary

Suggested implementation locations:

```text
dtcc_core/io/dxf.py
    inspect_dxf
    load_dxf_city
    selection and instance traversal
    DXF entities -> source face records

dtcc_core/io/city.py
    register .dxf and forward documented options

dtcc_core/builder/geometry_builders/
    existing prism decomposition and Building adapter
    geometry-only CAD normalization / optional reconstruction

tests/io/test_dxf.py
tests/builder/test_cad_prisms.py
```

Keep ezdxf-specific objects inside I/O. Geometry builders should receive DTCC
geometry or internal face records so that OBJ/STL/other readers can use the
same improvements. Do not make the public API depend on private
`_decompose_prisms` types.

An optional `cad` dependency extra with a lazy ezdxf import is a reasonable
starting point. The tested parser version was 1.4.5; select supported bounds
through CI rather than claiming all releases behave identically. Missing CAD
dependencies should produce an installation hint without preventing unrelated
dtcc-core functionality from importing.

### 7.2 Intermediate records and provenance

An internal record could conceptually contain:

```python
# Design sketch, not an existing DTCC type.
@dataclass
class CadFace:
    vertices: np.ndarray
    source_handle: str
    raw_layer: str
    effective_layer: str
    block_name: str | None
    instance_path: tuple[str, ...]
    source_group: str
```

Source groups and instance paths must survive until component assignment and
deduplication are complete. The same face handle inside two instances identifies
two placed faces, so a handle alone is insufficient.

Preserve enough information to explain which source entities produced a Building.
Avoid copying thousands of face handles into every split part: a City-level
source table with compact per-object references can reduce duplication, subject
to native serialization and schema constraints.

### 7.3 Entity support and traversal

First implement `3DFACE` and `INSERT`, which cover both investigated drawings.
Handle a triangle encoded as a quad with a repeated final vertex; reject
degenerate/nonfinite faces. Distinguish exact duplicate closure removal from
tolerance-based repair. The existing helper's `np.allclose` closure test uses
relative tolerance by default and should not be copied unchanged for large
coordinate offsets.

Use ezdxf's placement machinery for block base points, rotation, scale and
extrusion orientation. Support MINSERT expansion via its explicit instance
iterator or reject it with a specific diagnostic. See the
[INSERT API](https://ezdxf.readthedocs.io/en/stable/blocks/insert.html).

`recursive_decompose()` is useful for reconnaissance, but a provenance-aware
walker is preferable for selection, instance identity and limits. Its documented
limitations include unsupported external references and ignoring XCLIP clipping;
these must not silently become “complete” imported cities. See
[ezdxf decomposition](https://ezdxf.readthedocs.io/en/stable/disassemble.html).

Classify selected unsupported entities before conversion. Text and dimensions
can be excluded as declared annotations and counted; selected `3DSOLID`/ACIS,
unresolved XREFs or unsupported geometry should produce a clear failure or
incomplete-import diagnostic. The reader must not silently treat a partial
surface subset as the full building.

Subsequent increments can add polyface meshes and polygon meshes. Closed 2D
polylines are a separate useful workflow, but need an explicit height source:
an attribute, layer mapping or default supplied by the user. A closed XY ring
does not by itself determine a building height. Curved rings also require an
explicit tessellation tolerance. Do not include all of these formats in the
initial acceptance target.

### 7.4 Component assignment

Use explicit CAD grouping/instance identity where available, then geometric
connectivity within the selected source scope. A block can contain an entire
city, so “one INSERT equals one Building” is insufficient. Conversely, a
Building can comprise several source entities and roof-level pieces.

Avoid both global vertex clustering across unrelated instances and premature
splitting of a noisy shell into separate Buildings. Use topology-aware edge
connectivity after bounded normalization, preserving source boundaries. Point
contacts, shared walls and mixed semantic groups need explicit handling and
tests. If an unstructured face soup does not determine separate building
identities, report that ambiguity rather than inventing cadastral semantics.

Expose geometric parts with source-group relationships even when original
real-world building ownership is unknown. The existing one-Building-per-roof-
part convention is usable by current consumers; retaining a shared source ID
allows later BuildingPart aggregation without guessing lost relationships.

## 8. Extending core's geometry support safely

### 8.1 Resolve non-conforming junctions first

The agreement test confirms 33 Case E failures with reason `nonmanifold`.
The earlier R5 investigation classifies them as 22 solids with T-junctions only
and 11 with internal walls, four of those also having stacked caps. This
investigation re-ran the failure-count test; it did not independently reclassify
all 33 face sets. Treat that breakdown as a useful starting diagnosis.

Core already nodes rings against vertices, but `_node_ring` uses the numerical
epsilon passed by the kernel. Therefore the fix is not merely “add noding.”
Investigate why these CAD junctions remain non-conforming: normalization,
tolerance, segmentation or genuinely overlapping/internal surfaces may be
involved.

Use one documented positional budget across welding, projection and edge
noding. Simply substituting a larger tolerance can insert off-edge vertices,
bend rings, collapse small features or change wall topology. Charge displacement
and area/volume residuals to the existing diagnostics. Split/nod faces without
altering the represented solid where possible, then retain strict shell checks.

If this work accepts additional valid solids without weakening the existing
contract, it belongs in the default normalization path and benefits every
format that uses `footprints_from_lod1`.

### 8.2 Internal-face repair must be opt-in

A podium/tower CAD model may draw the tower's walls all the way to ground, even
where those walls are internal to the represented building. The current strict
kernel rejects such surfaces by design. The importer should not silently change
that contract.

An optional `repair="vertical_prisms"` is a proposed convenience spelling for
a narrowly scoped reconstruction policy. The reusable implementation belongs
in a geometry builder and must be callable independently of DXF. It should:

1. Check finite, planar, horizontal/vertical faces within a documented budget.
2. Establish base candidates and horizontal coverage spatially, preserving holes.
3. Build candidate roof cells and vertical occupancy intervals.
4. Verify that occupancy is a supported base-to-roof column arrangement.
5. Derive its expected exterior walls and check them against source wall coverage.
6. Classify redundant internal walls/caps against the validated occupancy, and
   remove them only when unambiguous under the selected policy.
7. Produce a closed canonical exterior and pass it through strict validation.
8. Record removed faces, generated surfaces, area/volume changes and ambiguity.

This is a proposed algorithm outline, not a demonstrated complete repair method.
The difficult step is proving occupancy from imperfect input without treating
every horizontal surface as a roof. A highest-roof envelope can fill real
passages or erase overhangs; it should remain a separate explicit approximation
if the exact occupancy cannot be established.

Do not recover the missing-wall or displaced-roof counterexamples simply by
extruding roofs. A separate “build from roof outlines” operation could exist,
but its inference should be explicit and distinct from repairing supplied solids.

If a nonmanifold input has no reliable shell volume, report that the input volume
is unavailable. The validation's `sum(roof_area * height)` is a model-specific
volume estimate, not an independent volume proof for arbitrary CAD.

### 8.3 Tolerances and exact shared boundaries

Use tolerances in output metres after units/model-scale conversion. Keep
positional tolerance, angular tolerance and intentional detail removal separate.
Avoid globally rounding every coordinate or snapping each output polygon
independently.

The Case E workflow previously snapped neighboring pieces independently. The
validation notes record overlaps around 2e-4 m² and downstream wall-construction
failures. Exact shared-edge boolean operations reduced the residual overlaps
to roughly 2e-14 m². The current helper therefore orients exact parts without
snapping them; only intentionally approximated merged envelopes are snapped.

For general input, this is not proof that exact operations always suffice.
The transferable rule is to normalize a shared arrangement consistently and
validate it, rather than apply unrelated simplifications to each neighbor.

### 8.4 Overlap policy is a separate operation

Default import should preserve source objects and report overlaps. Strict
decomposition within an individual source still applies its own validity rules.
An opt-in `overlaps="highest_roof"` can compose a reusable builder operation
after derivation, provided inputs satisfy a declared common-base envelope model.

The operation should compare absolute roofs, use deterministic tie handling,
retain contributing source IDs and report removed geometry. Differing bases,
vertically separated volumes or unsupported semantics should fail or require
another operation. Do not infer that an overlaid model preserves independent
building identity or interior spaces.

Before adding a new overlay implementation, assess reuse of core's existing
footprint cleaning/cell infrastructure. Ensure that exact partitioning can be
used without implicitly activating detail removal, hole filling or tallest-
building approximation.

## 9. Errors, reports, IDs and persistence

Reuse the existing conversion error philosophy: fail explicitly by default;
`on_error="warn"` preserves a complete readable source when possible and
records that it was not converted. A parser cannot preserve an unsupported
entity as DTCC geometry if no representation exists; distinguish that condition
from a readable LOD1 object whose footprint conversion failed. Never claim full
success after dropping selected content.

Use stable reason codes plus source path/handle, instance path, component,
face index, coordinate location and a practical next step. Distinguish invalid
input from unsupported-but-valid geometry. Do not catch programming errors as
ordinary CAD failures.

Suggested City report structure:

```python
# Illustrative schema; values abbreviated.
city.attributes["cad_import"] = {
    "version": 1,
    "format": "dxf",
    "source": {"name": "district.dxf", "sha256": "..."},
    "reader": {"name": "ezdxf", "version": "1.4.5"},
    "selection": {"layers": ["Buildings"], "include_nested": True},
    "coordinates": {
        "declared_units": "mm", "effective_units": "mm",
        "unit_to_metre": 0.001, "model_scale": 1.0,
    },
    "parameters": {"derive_footprints": True, "repair": None},
    "counts": {},
    "warnings": [],
    "failures": [],
    "repairs": [],
    "complete": True,
}
```

Keep `footprints_from_lod1`'s existing report rather than replacing it. Define
`complete` as complete selected-source ingestion; derive a separate footprint
conversion status from its report. A fully read City may still contain objects
without derived LOD0. Include units for residual metrics and record actual
options, not only defaults. Bound report size without silently truncating the
fact that failures occurred; full diagnostics can be an explicit sidecar.

IDs should incorporate stable source/instance identity and deterministic part
ordering. Document stability under a repeat import of the same drawing, without
promising unchanged IDs after arbitrary CAD re-export changes handles. Preserve
original identifiers independently from generated IDs, and reserve IDs across
all City descendants to avoid collisions.

Recalculate bounds after placement and conversion. Test `.dtcc` round trips for
geometry, transforms, provenance, reports and non-building objects. At the
inspected core revision, City-root reports have no mapping in strict CityJSON
export; keep native persistence as the complete round-trip target and document
the limits of other formats rather than silently discarding diagnostics.

## 10. What should remain outside CAD import

### 10.1 Benchmark semantics

Keep the following in dtcc-qes's validation application:

- expected counts, known dimensions and source hashes used to pin study inputs;
- before/after experiment labels and the choice of which buildings to include;
- probe locations, marker interpretation and measurement-frame checks;
- wind directions, reference velocities and normalization heights;
- tower IDs, grid row/column labels and plot conventions.

Core should make these choices easy to express through selectors and metadata,
not recognize Japanese names or expected counts internally.

### 10.2 QES adaptation

`cityutil.qes_city()` currently deep-copies a City and moves Building LOD0 to
`ground_height` because the inspected QES contract reads LOD0 z as the base.
Core's constructor uses roof-height LOD0. This mismatch is a separate consumer
integration issue; it must not influence canonical CAD output.

Likewise `qes_check()` runs solver-specific grid preparation. Grid acceptance
does not prove a general CAD import is geometrically or semantically correct.

### 10.3 Merging at maximum height

`merge_touching()` clusters footprints within 1 mm, merges their outlines,
fills holes and assigns each cluster its maximum height. The Case E notes
report approximately 15,443 m³ of added volume, about 5%, for the benchmark's
merged envelope variants. This was a solver workaround and is now retained
mainly as a sensitivity case because QES supports contact-aware footprints.

Do not make it an importer default or disguise it as mesh repair. If exposed in
core, it belongs in an explicit generalization operation with area/volume
reports and a clear approximation contract.

### 10.4 Elevated objects

The current `make_elevated()` constructs a generic CityObject with `kind`,
`zmin`, `zmax` and an extruded LOD1 slab. That illustrates useful representation
support, but geometry alone cannot decide whether a raised box is a canopy,
bridge, building on terrain or unsupported floating geometry.

Preserve absolute vertical placement and let caller-supplied role mappings
determine object semantics. Do not classify every nonzero base as a canopy or
move it to ground. Additional role mappings can follow the initial building-only
reader; the selection mechanism should already retain the necessary source
categories. QES currently ignoring the 32 generic objects is not a reason for
the CAD reader to discard them.

## 11. Implementation sequence and acceptance criteria

### Stage 1: DXF inspection and faithful polygonal import

Implement optional parser dependency, inspection, 3DFACE extraction, INSERT
placement, layers/blocks, source grouping, units and provenance. Register `.dxf`
and retain source geometry by default. Detect unsupported selected content.

Acceptance: transformed source coordinates agree with synthetic CAD fixtures;
duplicate instances remain distinct; layer inheritance is tested; no units or
semantic role is silently guessed. Case D can be loaded as correctly placed
source geometry. Case E's direct-block selection excludes marker/site geometry
and unintended nested copies.

### Stage 2: Strict footprint convenience

Compose loading with `footprints_from_lod1`. Reuse its copying, IDs, error
handling and diagnostics. Fix only demonstrably geometry-preserving topology
normalization issues within the strict contract.

Acceptance: Case D yields 83 Buildings and 1,374,500 m³ after explicit 400×
model scaling. Case E returns a clear failure report for still-unsupported
solids; warn mode preserves those sources. A test should fail when the known
33-failure baseline changes so that the cause is reviewed, not blindly retain
33 as the desired final behavior.

### Stage 3: Validated CAD prism repair and optional overlay

Develop the opt-in reconstruction policy with small targeted fixtures before
using the complete Case E drawing as the acceptance gate. Add exact envelope
overlay only as an explicit operation with a common-base contract.

Acceptance: recover the intended supported Case E solids, reproduce 533/536
ground-building parts when the explicit overlay policy is enabled, preserve
footprint coverage and expected volume, and reject the malformed counterexamples.
Compare geometry and residuals, not merely object counts.

### Stage 4: Broader entity and workflow support

Add polyface/mesh entities, explicit 2D footprint extrusion, richer instance-path
selectors and semantic role mappings as separate increments. Use additional
independently sourced or synthetic drawings to establish generality.

The first two stages are bounded Python-side integration work over existing
libraries. The third is the main geometry-engineering effort and deserves its
own design review. Supporting arbitrary ACIS solids, curved CAD, all external
references or automatic semantic inference is a substantially larger scope and
is not necessary to deliver the useful two-line workflow.

## 12. Test matrix

Use small synthetic DXFs generated with ezdxf for most tests. They isolate
behavior, avoid dependence on large benchmark files and provide expected
coordinates analytically. Keep AIJ fixtures as end-to-end regressions where
repository/data-distribution arrangements permit.

| Area | Required examples and expected behavior |
|---|---|
| Selection | Unicode/numeric layer names, absent selector errors, layer 0 inheritance, named child layers, layer/block intersection |
| Instances | Two instances of the same block, nested transforms, repeated sibling references, active-path cycles, explicit direct-only selection |
| Transforms | Nonzero block base, translation, rotation, reflection, nonuniform scale, extrusion direction, MINSERT, large offsets |
| Units | Metres, millimetres, unitless override, conflicting metadata, block scaling without double conversion, explicit model scale |
| Face decoding | Triangle-as-quad, reversed winding, degeneracy, nonfinite coordinates, nonplanar quad policy, duplicate faces |
| Components | Disjoint boxes, one block containing many buildings, corner contacts, shared walls, noisy split shells, separate instance identity |
| Valid solids | Concave footprint, courtyard, stepped roofs, multiple equal-height roof pieces, nonzero base, disconnected components |
| Junctions | One long edge meeting several short edges, near-edge vertices inside/outside tolerance, alternate triangulation |
| Repair | Redundant internal wall/cap accepted only under declared repair; removed surfaces and residuals reported |
| Rejection | Missing walls, displaced equal-area roof, open shell, overhang, cavity, sloped roof under prism derivation, ambiguous stacked volumes |
| Overlay | Common-base height envelope, ties, holes, slivers retained by default, different-base refusal, complete contributing-source mapping |
| Errors | Strict atomic failure, warn preservation, unsupported entity versus geometry failure, no silent selected-content deletion |
| Persistence | Native save/load preserves coordinates, transforms, IDs, source mapping, reports and elevated objects |
| Determinism | Repeated import, shuffled face order, reversed winding, stable canonical part ordering |
| Resource behavior | Many instances, large face counts, expansion limits, bounded diagnostics, predictable failure on malformed nesting |

For geometry-preserving paths, assert symmetric-difference area, base/roof
elevations, exterior wall coverage and volume within documented budgets. For
intentional approximation, assert the recorded change against an independently
computed expected result. Do not use QES acceptance or a matching polygon count
as the sole correctness criterion.

## 13. Reproduction helpers for the development team

Run from the dtcc-qes repository with its validation dependencies installed:

```sh
uv run --group validate python validation/build_cities.py
uv run --group validate pytest validation/tests/test_cities.py -q
```

The first command writes the full validation outputs and runs QES grid checks;
it is useful for end-to-end comparison but unnecessary for isolated DXF tests.
The direct virtualenv pytest command in section 2 was the command actually run
during this investigation.

To inspect the raw drawing without DTCC conversion:

```python
from collections import Counter
from pathlib import Path
import ezdxf

for path in Path("validation").glob("AIJ_*/*.dxf"):
    doc = ezdxf.readfile(path)
    print(path.name, "units:", doc.units)
    print("layers:", [layer.dxf.name for layer in doc.layers])
    print("model space:", Counter(
        (entity.dxftype(), entity.dxf.layer) for entity in doc.modelspace()
    ))
    for block in doc.blocks:
        if block.name.startswith("*"):
            continue
        print(block.name, Counter(
            entity.dxf.layer for entity in block
            if entity.dxftype() == "3DFACE"
        ))
```

To reproduce the block-selection experiment with the existing helpers:

```python
import sys
sys.path.insert(0, "validation")
from aij import case_e, dxf, prisms

doc = dxf.read(case_e.CASE_E_DXF)
selected = [
    entity for entity in doc.modelspace()
    if entity.dxftype() == "INSERT"
    and entity.dxf.name in (case_e.EXISTING, case_e.NEW)
]
parts = []
for instance_index, insert in enumerate(selected):
    faces = dxf.block_faces(doc, insert.dxf.name, insert.matrix44())
    for component_index, solid in enumerate(prisms.solids(faces)):
        parts.extend(prisms.solid_parts(
            solid, (instance_index, component_index)
        ))
disjoint, report = prisms.overlay(parts)
assert len(disjoint) == 536
print(report)
print("volume:", sum(part.volume for part in disjoint))
```

This reproducer demonstrates selection and the existing interpretation. It
inherits the helper's limitations and is not a suggested production importer.

To reproduce strict-conversion failures and successful-solid agreement, use:

```sh
uv run --group validate pytest validation/tests/test_cities.py::test_footprints_from_lod1_agrees_with_the_validation_decomposition -q
```

Start individual geometry debugging from `case_e.load().existing[i].faces`,
wrap it with `cityutil.lod1_building`, and call the public converter. R5 records
solid 55 as a useful non-conforming stepped example. Its index depends on the
current centroid sorting and pinned drawing; capture a minimal synthetic
equivalent before encoding a durable kernel regression.

## 14. Decisions to settle before implementation

The recommended defaults throughout this report form a coherent starting point.
The team should explicitly settle these boundaries in the API review:

1. Source-representation semantics for arbitrary polygonal CAD before prism
   validation, including whether a lower-level geometry reader is public.
2. Effective-layer filtering, block selection scope and explicit instance-path
   selectors; keep these distinct from CAD visibility.
3. The split between strict geometry-preserving normalization and opt-in
   occupancy reconstruction.
4. Provenance storage compatible with the current model schema and conversion
   adapter's restrictions on child-specific metadata.
5. Which overlap operation can reuse existing core infrastructure without
   introducing implicit geometry simplification.
6. Dependency packaging and the initial entity support matrix.

The useful target is a short user API backed by explicit, inspectable behavior.
AIJ Case D shows that core already has most of the construction machinery.
Case E identifies the necessary selection controls and the remaining geometry
work. Neither requires benchmark-specific behavior in dtcc-core.

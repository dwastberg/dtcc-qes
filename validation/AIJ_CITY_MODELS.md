# AIJ Cases D and E: dtcc-core City models

Step 1 of validating dtcc-qes against the AIJ pedestrian-wind benchmarks. This step turns the drawings in `AIJ_D/` and `AIJ_E/` into `dtcc_core.model.City` objects. Simulation and comparison with the measurements are step 2, planned in [`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md).

Changes needed in dtcc-core or dtcc-qes are listed in [`DTCC_REQUESTS.md`](DTCC_REQUESTS.md). This step changes neither code base.

## How to run

```sh
uv run --group validate python validation/build_cities.py   # -> validation/output/*.dtcc, *.png, summary.json
uv run --group validate pytest validation/tests -q          # 58 checks; 23 cover step 1 (test_cities.py)
```

`summary.json` records two dtcc-qes checks per City: `qes` (strict default) and `qes_footprints` (`wind.Footprints`, `--min-detail`, 0.1 m by default). dtcc-qes is a native extension. After pulling native changes, rebuild it with `uv sync --frozen --inexact --group dev --group validate --reinstall-package dtcc-qes`.

The dependencies (ezdxf, xlrd, matplotlib) are in the `validate` dependency group in `pyproject.toml`. The repo's `testpaths = ["tests"]` does not collect `validation/tests`.

## Outputs

dtcc-qes main `889c629`.

*Re-verified 2026-11-01:*
- On main `f277a69`, after the unified wind API: all 23 checks pass, and `summary.json` is regenerated identically.
- With dtcc-core `dev/qes-updates` (`66c81a2`) and the builders below: `summary.json` is again identical to 1e-9.
- **strict** = the default `footprints=None`;
- **Footprints** = `footprints=wind.Footprints(min_detail=0.1)`.

| File | Content | strict | Footprints |
|---|---|---|---|
| `aij_d.dtcc` | 83 buildings: 82 blocks of 40×40×10 m, a 25×25×100 m tower | accepted | accepted, geometry unchanged |
| `aij_e_before.dtcc` | exact: 533 roof-level parts + 32 elevated objects | rejected (touching) | **accepted**, no fallback |
| `aij_e_after.dtcc` | exact: as before + 60 m tower and two 18 m blocks (536 parts) | rejected (touching) | **accepted**, no fallback |
| `aij_e_before_qes.dtcc` | QES-ready: 47 touching clusters merged at max height (468 buildings) | accepted | accepted |
| `aij_e_after_qes.dtcc` | QES-ready (471 buildings) | accepted | accepted |

Common conventions:
- All Cities are in **full-scale metres** in the AIJ measurement frame, with no CRS, flat ground at z = 0 and no Terrain.
- **Each Building follows the dtcc-core convention** (since 2026-11-01). It is built by `builder.building_from_footprint`:
  - an LOD0 `Surface` at the absolute roof;
  - `ground_height = 0` and `measured_height`;
  - an LOD1 prism carrying dtcc-core's `lod1_extrusion` record;
  - provenance (`role`/`source`, `dxf_block`, `component`, `roof_level`, `merged_parts`). `merged_parts` was `merged_from`, which dtcc-core reserves for cleaned blocks.
- **Case D buildings come from `builder.footprints_from_lod1`** and carry its `prism_decomposition` record; the City keeps the `footprints_from_lod1` report.
- **dtcc-qes still reads LOD0 z as the base (R3),** so every City passes through `cityutil.qes_city` on its way to dtcc-qes. That function moves each LOD0 to its `ground_height` in a copy; it is the only place that knows about the mismatch.
  - Before 2026-11-01 the Cities stored LOD0 at z = 0 directly.
- Elevated slabs are generic `CityObject`s. Each has an LOD1 box and the attributes `kind`, `zmin` and `zmax`; dtcc-qes ignores them for now (R2).
- City attributes record the case, state, scale, units, frame, measurement height, reference heights and the sha256 of each source file.

A coarse smoke run before the merge solved `aij_d` and `aij_e_after_qes` at 4 m (`wind.run(city, 5, 270, resolution=4)`), and dtcc-qes reported the 32 `CityObject`s as ignored. Neither run set the converged flag within 500 iterations, but divergence stayed small (3.4e-5 and 8.3e-6 s⁻¹). This is the known λ-tolerance stall. After the merge, `aij_e_after` itself solves at 4 m with `Footprints(min_detail=0.1)`: 536 sources become 507 solids, with `exposed_faces=True`.

## Running the Cities in dtcc-qes (after the 2026-10-31 building-footprints merge)

dtcc-qes now accepts touching and overlapping footprints through `wind.Footprints` (request R1, done). It cleans them into height-preserving cells, and a native exposure rule stops Röckle zones starting at hidden walls. This changes the plan for the simulation step.

- **Use the exact Case E Cities, with `footprints=wind.Footprints(min_detail=0.1, exposed_faces=True, fallback="error")`.** The cell-level change against the exact parts is tiny: area −0.02 m², symmetric difference 9 m², volume −1.3 m³. No probe falls inside a building, and the closest wall stays 0.83 m away.
  - **Solid mask:** at 2 m and 4 m it differs from the exact parts in 47 of 13,112 and 7 of 3,287 built columns. That is cell-centre tie-breaking: strict mode on the merged City differs from its own input by more (186 and 33 columns).
  - **Why δ = 0.1:**
    - δ ≤ 0.05 fails in dtcc-core cleaning (R6).
    - δ does not depend on the grid, so one geometry serves the whole grid study.
    - δ = 0.1, 0.2 and 0.5 all clean with no fallback, so a sensitivity run is cheap.
- **Demote the QES-ready Cities** to a sensitivity case ("blocky envelope"). They add 15,443 m³ (+5 %), while Footprints cleaning at δ = 0.1 changes the volume by about 0.
- **Solver controls:**
  - The merge changed native code, so the `889c629` build reported `solver_policy_build_supported = False`.
  - *Update 2026-11-01:* main `02dc4eb` re-qualified the build (`True`).
  - Adaptive acceptance still cannot cover the AIJ cases, because `pedestrian-v1` covers at most 32 rectangular buildings, log inflow and 16 receptors. The simulation step uses legacy or bounded controls (see [`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md), F2).
- **Diagnostics to record:**
  - `metadata["footprints"]`: sources, cells, solids, fallbacks;
  - `metadata["solids"]` and `vertical_grid.roof_representation`;
  - `near_contacts` for strict runs: 493 pairs closer than one cell at 2 m in the QES-ready City.
- **Unchanged:** elevated slabs are still ignored (R2, which needs a native change), and the LOD0 z convention still differs (R3).

### Validation code changes made for the merge (2026-10-31)
1. **No snapping of exact parts (`aij/prisms.py`).** `clean` now only orients, and `overlay` uses exact boolean operations. `GRID` remains as the tolerance of the coverage check in `solid()`.
   - Before, snapped neighbours overlapped by up to 1.9e-4 m², and dtcc-core's wall construction raised a GEOS TopologyException for block E-164/E-187/E-190 at δ ≥ 0.2. That block then needed `fallback="tallest"` (+208 to +470 m³).
   - Now the worst overlap is 2e-14 m², and δ = 0.1, 0.2 and 0.5 all clean with no fallback.
   - The merged envelopes of the QES-ready Cities are still snapped, but by `merge_touching` itself (`_snapped`). Their 1 mm mitred closing leaves vertices that collapse in dtcc-qes's float32 check otherwise.
2. **`cityutil.qes_check(city, resolution, footprints=None)`** passes the setting through. It reports `near_contacts` in strict mode, and the cleaning counts, fallbacks and cleaned area with Footprints. `OVERLAP_AREA` (the touching/overlapping threshold) is now 1e-6 m².
3. **`build_cities.py`** records both checks (`--min-detail`, 0.1 m by default).
4. **New tests:**
   - the exact Cities are accepted with δ = 0.1 and 0.5 and no fallback, losing no source;
   - overlaps are below 1e-9 m²;
   - δ = 0.01 still fails. This documents R6 and will flag the dtcc-core fix.

## Findings

### Case D: high-rise in city blocks (`CaseD(Highrise+Blocks)`)
- **DXF geometry:** 786 3DFACEs in model space, in model-scale mm (`$INSUNITS = 4`). They form 83 closed, axis-aligned boxes:
  - 82 blocks of 100×100×25 mm and a 62.5×62.5×250 mm tower centred on the origin.
  - Streets alternate 50 and 75 mm, which the XLS Fig. 3 confirms.
  - No boxes touch.
  - 48 of the boxes are drawn twice, so faces are de-duplicated before analysis.
- **Scale:** the AIJ model scale is 1:400. That gives 40×40×10 m blocks, a 25×25×100 m tower (H = 100 m, the U_H reference height), 20 m and 30 m streets, and probes at 5 mm → 2 m. Sources: the SimScale and Dlubal validation pages, which cite the AIJ guidebook (2008).
- **XLS content:**
  - 78 points.
  - An inflow profile with U_H = 6.65 m/s at 250 mm.
  - `Exp_S` (split fibre at 0°) and `Exp_T` (thermistor at 0°, 22.5° and 45°).
  - Points inside the central ±50 mm plaza have no data (`'-'`), as the guidebook says.
- **Probe clearance:** every probe lies outside all footprints; the nearest is 2.5 m from the tower.

### Case E: Niigata district (`CaseE(Niigata)`)
- **Units:** full-scale metres (`$INSUNITS = 6`), model scale 1:250. Z_R = 250 m and U_R = 7.8 m/s. Results are normalised by the velocity at 15.9 m and measured at 2 m, at 80 points for 16 directions, before and after construction.
- **Nested blocks:** all geometry sits in blocks, and every INSERT is a pure translation with a model-space offset of (26.5, −35.5). The blocks re-insert each other:
  - A recursive resolve gives 57k faces, of which only 16k are unique, including a copy of the whole city lifted by 2.4 m.
  - So each block's **own** faces are taken once, placed by the INSERT in the table below.
  - `aij.case_e.load` checks block names, face counts and offsets, and raises if the input changes.

| Block | Placed by | Content | Use |
|---|---|---|---|
| 市街地地図 (city map) | model space, z+0 | 495 flat-roofed prisms, 1.5–30 m | existing buildings |
| 高層建築・集合住宅 | model space, z+0 | 60 m tower and two 18 m blocks; overlap no existing building | "after" only |
| アーケイド (arcade) | model space, z+2.4 | 21 slabs, 2.4–2.9 m, over sidewalks | elevated `CityObject` |
| 屋根 (roof) | model space, z+3.0 | 8 canopy slabs, 3.0–3.5 m, over open ground | elevated `CityObject` |
| ピロティ (pilotis) | model space, z+4.0 | 3 boxes, 4.0–4.5 m and 4.0–6.0 m | elevated `CityObject` |
| NW4 | inside 高層建築, z+2.0 | 80 spheres, 4 m across, centred at z = 2 m; a median 2.3 m (max 12 m) from the 80 points, matching 78 distinct points | probe markers, excluded |
| 敷地 (site) | inside 高層建築, z+0 | 500×500×0.1 m ground plate | excluded (flat ground) |

- **Coordinate frame:** the DXF frame, after the offset, is the measurement frame, with its origin at the centre of the reproduced area. Buildings fill a disc of r ≈ 204 m. No point lies inside a footprint, and the closest wall is 0.83 m from a point.
- **Stepped buildings:** 27 solids have several roof levels (up to three), giving 533 parts ("before").
- **Overlaps:** 28 parts overlapped higher parts, either within stepped solids or across neighbouring solids. The overlay keeps the higher roof and removes 14.9 m² and 108.8 m³; no slivers are dropped and no holes appear. Raw face volume minus the removed volume matches the City volume to within 1e-4.
- **Touching parts:** after the overlay, 68 part pairs still touch. The overlay is exact, and the largest remaining overlap is 2e-14 m² of floating-point noise.
- **QES-ready merge:**
  - 47 clusters are merged, 25 of which needed a 1 mm closing to fuse corner contacts or hairline gaps.
  - Filling holes adds 6.9 m².
  - Raising lower parts to the cluster roof adds **15,443 m³ (+5.0 %)**.
  - The largest additions are `E-m043` (11/14.5/18 m, +3,331 m³), `E-m041` (4.5/14.5/6 m, +2,163 m³) and `E-m024` (+1,996 m³). The QES-ready Cities therefore overstate stepped buildings. Since R1 was merged, the exact Cities run instead (see "Running the Cities in dtcc-qes").
- **Narrow gaps:** many gaps between separate buildings are under 1 m (the smallest is 0.03 m). The grid resolution decides whether they close.
- **Before and after:** "before" is "after" without the 3 new buildings, and the existing building ids and footprints are identical in both. This assumes the site was empty before construction; the DXF contains no demolished buildings.

### Open items for the simulation step
The simulation step is planned in [`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md) (2026-11-01).

- **Case E wind directions: resolved.** The XLS map carries an "N" arrow pointing to +y, which the DXF files lack. The 16 result columns run clockwise from N, so the meteorological direction is 22.5°·i for N to NNW. "N" is taken as wind *from* the north; a model-independent check is planned (plan F8).
- **Case D wind directions: resolved.** An arrow glyph in the XLS shows 0° flowing toward +x, with 22.5° and 45° turning toward +y. The meteorological directions are therefore 270°, 247.5° and 225° (plan F8).
- **Case E elevated slabs:** they are not simulated until R2. All 32 stand over open ground or sidewalks, and no probe lies beneath one.
- **Case E geometry setting:** `Footprints(min_detail=0.1)` as the baseline, with 0.2 and 0.5 as a sensitivity check.
- **Solver policy:**
  - The build is re-qualified (main `02dc4eb`), but the AIJ cases are outside the `pedestrian-v1` scope.
  - Use legacy or bounded controls, with the validation's own convergence evidence.
- **Inflow and result tables:** only the measurement points are parsed so far (`aij/tables.py`). The sheets and cell ranges of the inflow and result tables are documented in plan F9–F10.

## Code map (`validation/`)
- `aij/dxf.py`: ezdxf access. A block's own 3DFACEs, explicit insertion matrices, and an error on unexpected entities.
- `aij/prisms.py`: face components, a check that each solid is vertical-walled 2.5D, roof levels → parts, and the exact max-height overlay (no snapping).
- `aij/cityutil.py`:
  - Building construction: `make_building` = `building_from_footprint`, and `lod1_building` for `footprints_from_lod1` input;
  - `CityObject` construction;
  - `qes_city` (the R3 adapter), `merge_touching`, `qes_check` (`wind.preview_grid` on `qes_city`, strict or with `wind.Footprints`) and `summary`.
- `aij/case_d.py`, `aij/case_e.py`: the case builders.
  - Case D decomposes its de-duplicated boxes with dtcc-core `footprints_from_lod1`.
  - Case E keeps `aij/prisms.py`, because `footprints_from_lod1` rejects 33 of its non-conforming CAD solids (R5). A test checks that both agree on every solid dtcc-core converts. `aij/tables.py`: the measurement points, plus the inflow and result readers added in step 2 (code map in [`AIJ_VALIDATION.md`](AIJ_VALIDATION.md)).
- `build_cities.py`: writes the outputs. `tests/test_cities.py`: geometry, contract, round-trip and point checks.

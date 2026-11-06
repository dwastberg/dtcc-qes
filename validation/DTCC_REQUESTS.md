# Change requests from the AIJ validation

R1–R6 would let the AIJ Case D and E Cities (see [`AIJ_CITY_MODELS.md`](AIJ_CITY_MODELS.md)) run without approximation. R7–R13 would make the validation itself ([`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md)) simpler to run and to interpret. R14–R17 come from its results (Phases 2–5, [`AIJ_VALIDATION.md`](AIJ_VALIDATION.md)). R18–R19 come from Cases A and B ([`AIJ_AB_VALIDATION.md`](AIJ_AB_VALIDATION.md)).

## Summary for maintainers (Phase 6, 2026-11-02)

Open requests in priority order, each with the evidence that sets its priority:

| Priority | # | Request | Evidence | Native? |
|---|---|---|---|---|
| 1 | R3 | One LOD0 z convention | dtcc-qes rejects dtcc-core's own `building_from_footprint` output; the validation needs an adapter | No (Python, both packages) |
| 2 | R17 | A canopy-aware background inside built-up areas | The largest lever on the AIJ scores. A domain-wide canopy inflow raises Case E "before" q by 0.34, but it overshoots in Case D | Yes |
| 3 | R14 | A stopping rule or resolution-aware iterations at fine grids | The default 1,000 iterations leave p95 errors of 0.006–0.013 in K at 1 m; the λ criterion stalls in float32 | Option 3 is documentation only; options 1–2 change behaviour (option 1 may touch native monitoring) |
| 4 | R16 | A neighbourhood range on samples; smoother zone edges | Probes near walls change by a median 18 % from 1 to 0.5 m, not asymptotically; the local range predicts it | Part 1 no, part 2 yes |
| 5 | R11 | A separate QES-Turb ground roughness, or an inflow turbulence reference | The profile tail z0 doubles as the wall-model z0. k is 0.3–0.4× the inflow upstream, and no single z0 fits both cases | Yes |
| 6 | R8 | A vertical-grid helper centred on a target height | Every pedestrian study needs it; `auto` is unvalidated | No |
| 7 | R4 | Report gaps and solids lost to the grid | 853 sub-4 m gaps in Case E, decided by the grid | No |
| 8 | R2 | Elevated obstacles | Filling the 32 slabs moves AIJ pooled scores by ≤ 0.014 (local effect at 7 points) | Yes |
| 9 | R5 follow-up | Non-conforming CAD solids in `footprints_from_lod1` (dtcc-core) | 33 of 495 Case E solids rejected | dtcc-core |
| 10 | R12 | Monitor histories without a time budget | The large-budget workaround works | No |

- **On hold:** R10, which needs a k pattern QES-Turb does not have yet.
- **Dropped:** R9.
- **Done:** R1, R6, R7, R13 and R15.
- **Native requests:** they change the solver policy identity, so batch them (R17, R11, R16 part 2, R2) under one re-qualification. The validation's Phase 5 protocol is ready to test them on both cases.

**Status on 2026-10-31, after the building-footprints merge into dtcc-qes main (`889c629`).** The merge brought `wind.Footprints` and pins dtcc-core `dev/footprint-cleaning-update` at `80a4bba`.

| # | Request | Status |
|---|---|---|
| R1 | dtcc-qes: touching and overlapping footprints | **Done** (opt-in `wind.Footprints`), verified on AIJ E below |
| R2 | dtcc-qes: elevated obstacles | Open, **low for AIJ**: the Phase 5 bracket moves pooled scores by ≤ 0.014 (local effect at 7 points). Needs a native change and must bypass footprint cleaning |
| R3 | dtcc-qes and dtcc-core: one LOD0 z convention | **Open, now high**: dtcc-qes rejects dtcc-core's own `building_from_footprint` output; the validation uses an adapter |
| R4 | dtcc-qes: report footprints and gaps lost to the grid | Partly done; the remaining items are listed, with Phase 4 evidence |
| R5 | dtcc-core: footprints from block geometry, buildings from footprints | **Mostly done** (`dev/qes-updates` `66c81a2`); follow-up: 33 non-conforming Case E solids |
| R6 | dtcc-core: footprint cleaning fails at small detail on simple contacts | **Done** in dtcc-core `dev/qes-updates` (`66c81a2`); verified at δ = 0.01 |
| R7 | dtcc-qes: sample at arbitrary world points | **Done** (`WindResult.sample_points`, `fafa08b`); used by the validation |
| R8 | dtcc-qes: a vertical-grid helper that centres a layer on a target height | **New**, medium |
| R9 | dtcc-qes: multi-direction runs with shared preparation | **Dropped**: preparation costs 4 s per Case E run (Phase 2) |
| R10 | dtcc-qes: scalar-speed (thermistor-equivalent) estimate | **On hold**: the estimator works on measured k, but QES-Turb's k pattern is wrong (R ≈ 0) even when its level is right (Phase 5) |
| R11 | dtcc-qes: turbulence reference from the inflow | Medium, native; **revised in Phase 5**: the low k level comes mostly from the profile's ground roughness, which doubles as the wall-model z0; no single z0 fits both cases |
| R12 | dtcc-qes: monitor histories without a time budget | Low; the large-budget workaround works (Phase 2) |
| R13 | dtcc-qes: stale positional `wind.run` call in the docs | **Done** (fixed directly, 2026-11-01) |
| R14 | dtcc-qes: an iteration count or stopping rule that works at fine grids | **New**, medium |
| R15 | dtcc-qes: expose the building-parameterisation flags | **Done** (`wind.Parameterizations`, 2026-11-02); used by the validation as `RunSpec.parameterizations` |
| R16 | dtcc-qes: flag grid-sensitive receptors; smoother zone edges | **New** (Phase 4): medium for the Python flag, low for the native change |
| R17 | dtcc-qes: a canopy-aware background inside built-up areas | **Open, medium** (filed in Phase 6); native |
| R18 | dtcc-qes: roof separation on isolated buildings | **New** (Cases A/B, 2026-11-05), medium; native |
| R19 | dtcc-qes: QES-Turb k in shear layers and non-realisable stresses | **New** (Cases A/B, 2026-11-05), medium; native, joins R11 |

## Recommendation before Phase 5 (2026-11-02)

**Implement R15 before Phase 5; nothing else is needed first.** R15 was implemented on 2026-11-02 (see R15), and Phase 5 ran on it. This section is kept as the record of that decision.
- **Why R15:** the two main Phase 3 findings point at the building parameterisations.
  - The background flow outside every zone keeps the approach profile.
  - The wakes behind the new tower are too strong.
  - The flags are therefore the main Phase 5 sensitivity after the in-canopy inflow.
- **Why not patching instead:**
  - Patching means changing private code in two places (`wind.prepare_domain` and `_city.prepare_domain`). That breaks silently when dtcc-qes is refactored, and it is not part of a run key.
  - With R15 the flags become a `RunSpec` field: keyed, recorded, and tracked per revision like every other setting.
- **Why it is cheap:** most of the work is already done.
  - The native bridge validates the flag ranges and wake dependencies (`model_inputs.cpp:178-196`).
  - The adaptive preflight already rejects non-default flags (`pedestrian_policy.cpp:43-45`, `unqualified_model_settings`).
  - `wind.py:201` already records the flags.
  - What is left is a Python spec, a keyword, the assignment to the prepared `ModelSettings`, and tests. It does not change the policy identity.

**Optional in the same batch:**
- **R14 option 3 (documentation):** a tiny change, and the 1 m and 0.5 m evidence is complete.
- **R3, if it is planned soon anyway.** The validation is a ready regression check for it: drop `cityutil.qes_city`, rerun the 2 m baseline, and expect max |ΔK| = 0.

**Land them together, before the first Phase 5 run.**
- The run fingerprint covers the dtcc_qes package, so any change to it reruns stored runs.
- Phase 5 compares each variant with the baseline, so both must come from one revision.
- Rerunning the 2 m baseline takes about 5 minutes. With default flags it must reproduce Phase 3 exactly.

**Not before Phase 5:**

| # | Why not now |
|---|---|
| R2 | Native, with re-qualification. At 2 m, slab-adjacent probes score no worse than open ones (Phase 3). Phase 5 can bracket the effect first: slabs ignored (today) against slabs filled down to the ground. |
| R3 | The adapter works and is pinned by a test; see the optional batch above. |
| R4, R16 (Python part) | Diagnostics. The validation already computes sub-cell gaps and the neighbourhood span itself. |
| R5 follow-up | Would only let Case E drop `aij/prisms.py`; both agree exactly on every converted solid. |
| R8, R12 | The validation's workarounds work. |
| R10, R11 | Wait on Phase 5 evidence about k. For R11, sample k at upstream probes in a run *with* buildings. A run without buildings uses the other reference branch (100·z0 instead of 3·H̄; `turbulence_reference.cpp:14-26`), so it would not test the morphometric u\*. |
| R14 options 1–2 | The validation uses fixed, checked work. |
| R16 (native part) | Low; batch it with R2 and R11 under one re-qualification, after Phase 5. |

**Phase 5 needs no other request.**
- The ground roughness of the QES-Turb wall model is the profile's `roughness_length` (`_city.py:437`, `model_inputs.cpp:167,177`), so it can be varied today. Below the lowest table point it also shapes the inflow, but only under 2 m (D) and 1.25 m (E).
- The in-canopy inflow is a `MeasuredProfile` built with `comfort.log_law_transfer`.

**Update 2026-11-01 (dtcc-qes main `f277a69`).**
- **The combined feature plan is merged** (unified profile, `Solver`, `Turbulence` and `result.qualification`), and the native build is re-qualified: `solver_policy_build_supported = True`.
- **R1–R6 are unchanged; I re-checked R2, R3 and R13 against the source:**
  - `model_inputs.cpp:231` still rejects a nonzero base;
  - both modes still raise "incompatible base elevation" (`_city.py:240`, `_footprints.py:555`);
  - `_validate_partition` still tests `area > 0` (`_footprints.py:194`).
- **R7–R13 come from planning the simulation step** ([`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md)).
  - The AIJ cases fall outside the adaptive `pedestrian-v1` scope: more than 32 buildings, non-log inflow, more than 16 receptors. The validation therefore runs legacy or bounded solves and needs its own probe sampling and convergence evidence.
  - Python-only requests (R7–R10, R12, R13) do not change the native policy identity.

All numbers below come from `validation/output/aij_e_after.dtcc`, regenerated without snapping, and the matching builders. `summary.json` records both dtcc-qes checks for every City. They were measured against a native extension rebuilt from `889c629`, which reports `solver_policy_build_supported = False`. That is expected after native edits.

## R1 (dtcc-qes): accept touching and overlapping footprints. Done.

**What was merged.** `wind.run` and `wind.preview_grid` take `footprints=wind.Footprints(min_detail, exposed_faces, fallback)`.
- **Inputs:** touching, overlapping, multipart and holed LOD0 footprints.
- **Pipeline:**
  - Flat copies are cleaned once by dtcc-core (`clean_footprints`, then `building_cells`).
  - Cells with the same represented roof are unioned within a block.
  - Shared boundaries are noded without snapping.
  - Native code receives the rings with holes.
- **Exposure rule:** a native rule suppresses parameterisations from walls hidden by neighbours.
- **Default:** `footprints=None` keeps the strict contract.

This goes beyond what I asked for: a cleaned partition plus exposure rules is better than union-only rasterisation, because Röckle zones no longer start at shared walls.

**Verified on AIJ Case E (exact City, 536 parts).**

| `min_detail` δ | Result |
|---|---|
| ≤ 0.05 m | Fails in dtcc-core cleaning (R6) |
| **0.1 m** | **Passes with no fallback.** Cell-level change against the exact parts: area −0.02 m², symmetric difference 9 m², volume −1.3 m³. No probe falls inside a building, and the closest wall is still 0.83 m away. |
| 0.2–0.5 m | Passes with no fallback. At 0.5 m the cell-level change is −55 m² and −314 m³ (−0.09 %). Before the validation stopped snapping parts to 1e-4 m (2026-10-31), one block hit a GEOS TopologyException in the wall construction and needed `fallback="tallest"` (+208 to +470 m³). |

- **Solid mask:** a 1-iteration `wind.run` with δ = 0.1 was compared with the exact parts sampled at cell centres, using QES's roof rule (a cell is solid if its centre is at or below the roof):
  - at 2 m, 47 of 13,112 built columns differ;
  - at 4 m, 7 of 3,287 columns differ.
  - Strict mode on the merged City differs from its own input by more (186 and 33 columns), so the remainder is tie-breaking where cell centres fall on footprint edges.
- **End to end:** `wind.run` at 4 m solves the exact City (536 sources → 507 solids, `exposed_faces=True`).

**Remaining notes (minor, not blocking).**
- **Shared-area check is exact.** With raw, overlapping parts as input (no validation overlay), δ = 0.1 and 0.2 raise "Cleaned footprints share area: ('E-423-0',), ('E-441-0',)". Two cells of one dtcc-core block share 1.6e-6 m² in the anchor frame. The cause is `_validate_partition` in `_footprints.py:187`, which tests `area > 0`. A tolerance of a small multiple of perimeter × float64 epsilon would accept this noise. dtcc-core could also guarantee exact tiling (R6). The validation's overlaid parts do not trigger it.
- **Documentation:** `docs/building-contacts.md` recommends 0.01 m for precise input, which fails on this CAD data (R6). Until R6 is fixed, document 0.1 m or catch the error with a hint.

## R2 (dtcc-qes): elevated obstacles. Open.

**Need.** Case E has 32 slabs with open space beneath:
- 21 arcade roofs at 2.4–2.9 m;
- 8 canopies at 3.0–3.5 m;
- 3 pilotis volumes, at 4.0–4.5 m and 4.0–6.0 m.

They are stored as `CityObject`s with `kind`, `zmin`, `zmax` and an LOD1 box. Both dtcc-qes modes ignore them.

**Request.**
- Accept an obstacle base above ground, for example a `base_height` or `zmin` attribute on a Building or `CityObject`, and pass it through `base_heights`. Both paths still hard-wire zeros: `_city.py:456` for strict mode, `_footprints.py:617` for Footprints mode.
- **Correction to my earlier note: this is not Python-only.** The native bridge rejects any nonzero base (`src/qes_core/dtcc/model_inputs.cpp:230`, "Flat-ground buildings must have zero base height"). `PolyBuilding` itself does honour `base_height` (`PolyBuilding.cpp`). So R2 is a native edit and needs the solver policy re-qualified, although the merge has already left this build unqualified.
- **Keep elevated objects out of footprint cleaning.** `prepare_footprints` cleans 2D copies with height precedence. A slab that touches or overlaps a ground building in plan, such as an arcade along a façade, would be merged into it or cut away as if it stood on the ground. Elevated objects should therefore bypass cleaning, or cleaning should run per z-interval.
- **Revisit the exposure rule.** It traces from each wall through the initial solid mask (`docs/building-contacts.md`, "Native exposure rule"). Walls under a slab must stay exposed through the fluid cells beneath it. Also review the Röckle upwind, wake and street-canyon parameterisations, which assume ground-based buildings.
- **Report slabs thinner than one cell.** The slabs here are 0.5 m.

**Phase 5 bracket (2026-11-02, `AIJ_VALIDATION.md`).** The validation filled the 32 slabs down to the ground (`cityutil.fill_slabs`), the opposite extreme to ignoring them.
- **Pooled scores:** they move by at most 0.014.
- **Locally:** probes change by up to p95 0.09. At the 7 slab-adjacent points (112 values), "before" q goes 0.23 → 0.32 and FB −0.36 → −0.12; "after" q goes 0.26 → 0.27.
- **So:** R2 would change at most this much for AIJ, so it is a low priority here. It still matters for comfort under arcades.

**Acceptance.** The 32 `CityObject`s in `aij_e_*.dtcc` are rasterised between `zmin` and `zmax`, with open cells beneath.

## R3 (dtcc-qes and dtcc-core): one LOD0 z convention. Open, now high

**Update 2026-11-01.** dtcc-core `dev/qes-updates` (`66c81a2`) adds `builder.building_from_footprint` and `builder.footprints_from_lod1`. Both put LOD0 at the absolute roof with `ground_height`, so dtcc-core's own builders now produce Cities that dtcc-qes rejects:
- `wind.preview_grid` on two `building_from_footprint` boxes of 10 and 20 m fails with "incompatible base elevation".
- With `terrain="flat"` it accepts them and moves the ground to z = 10 (origin z = 10).

The validation now builds every City in the dtcc-core convention. It passes them through one adapter, `validation/aij/cityutil.py::qes_city`, which moves LOD0 to `ground_height` in a copy. `tests/test_cities.py::test_dtcc_qes_still_reads_lod0_as_the_base` pins the rejection.

**Not a small fix in dtcc-qes.** I looked, and the base is read from LOD0 z in `extract_city` (`_city.py:155`), extended by hole z in `prepare_footprints` (`_footprints.py:283-285`), and checked in two places (`_city.py:236-240`, `_footprints.py:550-556`). It is also part of the terrain design (`ADD_TERRAIN.md`).

**A minimal rule:**
- When a Building has a finite `ground_height` and its flat LOD0 lies at `ground_height + height` (within float32 tolerance), use `ground_height` as the base, for its holes too.
- Otherwise keep reading LOD0 z (today's contract, which existing tests and Cities use).


**Need.** This is unchanged by the merge. Both dtcc-qes modes still read LOD0 z as the building base:
- `CityGeometry.base_ranges` and `FootprintSource.base_range` hold it;
- `prepare_domain` (`_city.py:248-258`) and `finalize_footprints` (`_footprints.py:550-556`) check it.

dtcc-core builders put the absolute roof in LOD0 z, with a `ground_height` attribute.

**Re-verified.** I built two buildings in the dtcc-core convention (LOD0 z = 10 and 20, `ground_height = 0`).
- **Default:** both modes reject them with "incompatible base elevation".
- **`terrain="flat"`:** both modes accept them and silently put the ground at z = 10, the lowest roof. Heights stay correct, but the output coordinates are shifted by 10 m.

**Request.** Agree on one convention. dtcc-qes could read `ground_height` when it is present and treat LOD0 z as the roof, or dtcc-core could document a base-z variant. Add a test with a City built by `build_lod1_buildings`. This blocks the validation from adopting dtcc-core's F2 builder (R5). Related: `ADD_TERRAIN.md`.

## R4 (dtcc-qes): report footprints and gaps lost to the grid. Partly done.

**Already in metadata.**
- **Strict mode:** `near_contacts` (pairs closer than one cell), plus one logged warning. The merged Case E City has 493 such pairs at 2 m and 766 at 4 m.
- **Both modes:** `vertical_grid.roof_representation` (requested versus represented roof).
- **Footprints mode:**
  - per-source status (`solid`, `covered` or `excluded`);
  - fallbacks with `added_volume`;
  - per-solid `area`/`native_area` (float32 area, not raster area).

**Still missing.**
- Buildings or solids with zero solid cells. Case E has parts as small as 2.75 m².
- Represented (rasterised) footprint area versus input area, per solid or in total.
- Gaps narrower than one cell in **Footprints** mode. `near_contacts` runs only in strict mode, but gaps between δ and one cell survive cleaning (for example 0.1–2 m at δ = 0.1), and the grid decides whether they open.

**Phase 4 evidence (`AIJ_VALIDATION.md`).**
- **Gap counts:** the exact Case E "after" City has 853, 528, 223 and 122 pairs of separate footprints closer than 4, 2, 1 and 0.5 m.
- **Grid sensitivity:** the near-wall probes are the ones that keep changing under refinement (median 18 % from 1 to 0.5 m; R16).
- **What the metadata cannot say:** whether a gap near a given receptor was open on the grid.

**Acceptance.** For `aij_e_after.dtcc` with `Footprints(min_detail=0.1)` at 2 m and 4 m, the metadata lists vanished solids, the area error and sub-cell gaps.

## R5 (dtcc-core): footprints from block geometry, and buildings from footprints. Mostly done

**Status 2026-11-01 (dtcc-core `dev/qes-updates` `66c81a2`).**
- **Done:** F2 `building_from_footprint` (`bfeeffe`) and F1 `footprints_from_lod1` (`d9a5a82`, kernel `67a3d94`), plus `load_mesh_as_city(derive_footprints=True)` (`8270a30`). The geometry kernel is private (`_decompose_prisms`), and the public entry is `footprints_from_lod1`.
- **Used by the validation:**
  - `cityutil.make_building` is `building_from_footprint`.
  - Case D is decomposed by `footprints_from_lod1`: all 83 boxes after de-duplication, with exactly the expected volume of 1,374,500 m³.
- **Agreement with the validation's decomposition.** On every Case E solid that `footprints_from_lod1` converts (462 existing, 3 new and 32 elevated), it equals `aij/prisms.py`: footprints within 1e-6 m², exact heights and grounds (`tests/test_cities.py::test_footprints_from_lod1_agrees_with_the_validation_decomposition`).
- **The elevated slabs** convert with `ground_height = zmin` (2.4–4.0 m). That is the raised-prism representation R2 needs. They stay CityObjects until dtcc-qes accepts raised bases.

**Follow-up request: non-conforming CAD solids.** `footprints_from_lod1(on_error="warn")` rejects **33 of the 495 existing Case E solids**, all with `nonmanifold: each atomic shell edge requires exactly two incident faces`. They include all 27 stepped solids, which are the buildings this feature exists for. Two causes:
- **22 have T-junctions only.** These are closed, vertical-walled 2.5D solids whose faces do not conform.
  - Typically one base face spans both parts of a stepped building, while the walls are drawn per part. The base edge is then split by wall vertices.
  - Example: solid 55 of `aij.case_e.load().existing`, 12 faces, roofs at 5.4 and 6.0 m, failing at (105.0, −139.0, 0).
  - The kernel already nodes rings (`_node_ring`). Noding every face edge against all vertices within `tolerance` before the manifold check would accept these.
- **11 have walls drawn from the ground inside the footprint,** 4 of them also with stacked caps. Example: the tower wall of a podium drawn down to z = 0.
  - These are internal faces, which the kernel rejects by design.
  - An opt-in `internal_faces="drop"` would recover them: drop faces whose both sides are inside the solid.
  - The validation handles both causes by taking unions of the horizontal faces by height and checking that the base equals the union of the roofs (`aij/prisms.py`).

To reproduce: wrap each `aij.case_e.load().existing[i].faces` in a Building's LOD1 MultiSurface (`aij.cityutil.lod1_building`) and run `footprints_from_lod1(city, on_error="warn")`. The report lists the 33 failures with locations. When this is fixed, Case E can drop `aij/prisms.py` as well, and the pinned test flags the change.


Two general features from this validation should move into dtcc-core:
- `building_from_footprint`: a Building from a polygon and a height, with LOD0, heights and LOD1 that follow the dtcc-core convention.
- `decompose_prism` / `footprints_from_lod1`: LOD0 footprints and roof levels from closed, vertical-walled LOD1 or mesh solids.

The full design is in [`DTCC_CORE_PLAN.md`](DTCC_CORE_PLAN.md). It was revised after the dtcc-qes merge:
- **No snapping:** snapping caused the TopologyException above.
- **Output format:** the output feeds `wind.Footprints` directly.
- **Alignment with `FootprintCell`:** output fields match `building_cells`.
- **Correction:** I had claimed that cleaning always merges touching levels; it does not (R6).

## R6 (dtcc-core): `clean_footprints` fails at small detail on simple contacts. Done

**Status 2026-11-01:** fixed.
- dtcc-qes now pins dtcc-core `dev/qes-updates` at `66c81a2` (an uncommitted change in `pyproject.toml`/`uv.lock` at the time of writing).
- With it, `wind.preview_grid(aij_e_after, footprints=wind.Footprints(min_detail=0.01))` cleans the exact Case E City with no fallback and every source kept. That is the acceptance below.
- `validation/tests/test_cities.py::test_case_e_small_detail_cleans` replaces the test that pinned the failure.
- The validation baseline keeps δ = 0.1, whose cell-level change from the exact parts is already negligible; δ = 0.01 joins the Phase 5 sensitivity.

**Need.** For CAD and wind-tunnel input, dtcc-qes recommends a small δ (0.01 m) so that geometry stays exact. On the exact Case E City, `clean_footprints(min_building_detail=δ, lod=LOD0, strict=False, min_area=0)` raises `UnresolvedFootprintCleaningError` (reason `no_fixed_fallback_satisfied_handoff`) for:
- 6 groups at δ = 0.01–0.02;
- 3–4 groups at δ = 0.05.

It succeeds at δ ≥ 0.1. Every failing group also fails **in isolation**, and the result does not depend on snapping or translation. The smallest cases are below, translated to a local origin, and need no AIJ data. Both are flat copies with LOD0 at z = 0 and `estimated_height`, which is what dtcc-qes passes in.

```text
# Two quadrilaterals touching at one corner (7, 11), both 6 m tall.
POLYGON ((10 4, 7 11, 0 7.5, 3 0, 10 4))          h = 6   (E-126-0)
POLYGON ((17 5, 12.5 13.5, 7 11, 11 2, 17 5))     h = 6   (E-126-1)
# Two hexagons sharing the full edge (5.5 21)-(14 24.5), 12 m and 24 m tall: a plain stepped building.
POLYGON ((0 24, 3 15.5, 7.5 17, 5.5 21, 14 24.5, 12 29.5, 0 24))            h = 12  (E-079-0)
POLYGON ((11.5 9.5, 7 7, 9.5 0, 23 7, 14 24.5, 5.5 21, 11.5 9.5))           h = 24  (E-079-1)
```

| δ | Both pairs |
|---|---|
| 0.01, 0.05 | unresolved |
| 0.1 | resolved, walls `warning` |
| 0.5 | resolved, walls `strict` |

The other failing groups are E-067/E-070, E-087/E-111-0…4, E-154/E-163-0…2 and E-268-0/1. To reproduce them, take those parts from `aij.case_e.build_case_e("after")` and clean flat copies as above. A self-contained repro script can be added to `validation/` on request.

**Request.**
- Resolve point contacts and exactly shared edges at any δ > 0. These are the easiest contacts: no gap to close and no overlap to divide.
- If a group cannot be resolved, fall back per group, keeping the input polygons as cells (they are already disjoint), instead of failing the whole City.
- Add both pairs to the cleaning tests at δ = 0.01.
- **Minor:** `building_cells` documents that cells in a block tile without overlap, but one block in the raw-input run overlaps by 1.6e-6 m² (see R1). Either guarantee exact tiling or document a tolerance.

**Acceptance.** `wind.preview_grid(aij_e_after, footprints=wind.Footprints(min_detail=0.01))` succeeds with no fallbacks. `validation/tests/test_cities.py::test_case_e_small_detail_fails_in_dtcc_core` pins the current failure and will fail once this is fixed.

## R7 (dtcc-qes): sample at arbitrary world points. Done

**Status 2026-11-01:** implemented as `WindResult.sample_points(points, method, frame)` (dtcc-qes `fafa08b`), returning `WindPointSample`. The validation uses it with `method="linear", frame="global"`. The nearest-fluid fallback and the wall distance stay in `validation/aij/sampling.py`; the request text below is kept for the record.

**Need.**
- The AIJ probes are points at 2 m: 78 in Case D, and 80 per direction and state in Case E.
- `WindResult.sample(height, method)` (`result.py:303`) returns only a horizontal plane on the native cell centres, in the local frame, and `"linear"` interpolates only vertically. Every caller therefore writes its own x/y interpolation, frame shift and invalid-contributor handling.
- The same need appears in:
  - comfort receptors;
  - `tools/benchmark_urban_wind.py:214` (`receptor`);
  - `tools/run_auto_grid_controls.py:114` (`collocate`);
  - `tools/run_horizontal_sensitivity.py:143` (`audit_point`).
- Native monitor receptors already sample points (`monitor.cpp:312-323`).

**Request.**
- API: `WindResult.sample_points(points, *, frame="world"|"local", method="linear"|"nearest", invalid="nan"|"nearest_fluid")`, where `points` is an (n, 3) array with z above flat ground.
- Return a `PointSample` with:
  - velocity, speed and speed-up;
  - `valid`, the number of valid contributors, and the fallback used;
  - the distance to the nearest solid cell centre;
  - the stress, with the same contributors, when turbulence is present.
- Keep the conservative contributor rules of `sample()`; `invalid="nearest_fluid"` is an explicit opt-in that is recorded per point.
- The rule for points inside a solid cell must be explicit, because a probe can sit within one cell of a wall (0.83 m in Case E).

**Acceptance.**
- Bilinear and trilinear interpolation is exact for a linear field.
- It agrees with `sample()` at the cell centres.
- The validation's interim `aij/sampling.py` serves as an oracle on the AIJ probes.

## R8 (dtcc-qes): a vertical-grid helper that centres a layer on a target height. New, medium

**Need.** Pedestrian results are wanted at one height: 2 m for AIJ, 1.5 m for most comfort criteria. With a uniform grid the first centres are at dz/2, 3dz/2 and so on.
- At dz = 1 and 2 m, 2 m falls on a face.
- `docs/wind-comfort.md:166-170` tells users to build a `VerticalGrid` that puts a centre at the target height, but no helper does it.
- `VerticalGrid.auto` (`pedestrian_height=`) is `prototype_unvalidated`.

**Request.** Add a fixed, documented constructor, for example `VerticalGrid.uniform(dz, centre_at=2.0, top=None)`, and optionally a stretched variant: uniform up to a height, then a geometric growth rate. The validation builds the faces by hand meanwhile (`aij/grids.py`):
- 0, 1, 3, 5, … at 2 m;
- 0, 0.5, 1.5, 2.5, … at 1 m.

## R9 (dtcc-qes): multi-direction runs with shared preparation. Dropped

**Status 2026-11-01:** dropped.
- Phase 2 measured City preparation at a constant 4.0–4.3 s per Case E run, about 3 s of it dtcc-core cleaning, and about 0 s for Case D.
- Over the whole plan (about 150 Case E runs) that adds roughly 10 minutes, which is not worth a new API.

**Need.** Each AIJ configuration is solved for 3 directions (D), or for 16 directions × 2 states (E), at 3–4 resolutions and with sensitivity variants. Every `wind.run` call repeats City preparation and, in Case E, the `wind.Footprints` cleaning of 536 parts. S8a measured only modest reuse savings and deferred a public API (`docs/solver-control-s8a.md`).

**Request (conditional).** Phase 2 of the validation records the cost split per run. If preparation and cleaning are at least about 20 % of the run time on Case E, then add one of these, both Python-only:
- `wind.run_directions(city, profile, directions, ...)`;
- a reusable prepared City or footprint object.

Otherwise this request is dropped.

## R10 (dtcc-qes): scalar-speed (thermistor-equivalent) estimate. New, to be decided

**Need.** QES returns the mean vector speed |⟨u⟩|. The thermistors in AIJ Case D (Exp_T) and Case E measure the mean scalar speed ⟨|u|⟩, which is larger where turbulence is high. Case D at 0° has both at the same 33 points, so the gap can be measured.

**Evidence from the measured data (2026-11-01, `AIJ_VALIDATION.md`).** On those 33 points, the split fibre's own values were compared with the thermistor.
- **Mean vector alone:** it matches within ±25 % at only 52 % of the points (Spearman 0.70).
- **√(|mean vector|² + 2k):** it matches at 91 % (Spearman 0.91, median ratio 0.95).

A mean-vector model is therefore capped well below a perfect score against thermistor data, which is all of Case E, before any model error.

**Phase 3 result (2026-11-01).** QES-Turb's k at the 33 split-fibre points averages 0.0062 U² against 0.024 measured: about 4× too low, R = 0.09, FAC2 0.15. With it, √(|U|² + 2k) lowers the Case E hit rate (0.16 → 0.08), so this request waits on R11.

**Request (conditional).** If QES-Turb's k becomes good enough for this, checked against the split-fibre k, add the estimate to `WindSample` and `PointSample`. The estimate is K_scalar = √(|⟨u⟩|² + 2k)/U_ref, or a better one. The same matters for comfort assessment, whose criteria are usually calibrated against omnidirectional anemometers. The validation computes the estimate itself until then.

## R11 (dtcc-qes): turbulence reference from the inflow. Medium, native

**Phase 5 result (2026-11-02, `AIJ_VALIDATION.md`, part A, finding 4): the cause is mostly the ground roughness, not u\*.**
- **Upstream k:** in the undisturbed approach flow (≥ 25 m from and upwind of every building), QES-Turb's k at 2 m is 0.31 (E) and 0.44 (D) of the tunnel's inflow k with the base profile.
  - The base profile's `roughness_length` is the tunnel tail fit, 10⁻⁴–10⁻⁵ m. It is also the z0 of the QES-Turb ground wall model (`_city.py:437` → `model_inputs.cpp:167,177` → `TURBWallTerrain.cpp:103`).
  - With 0.05 m the ratio becomes 1.07 (E) and 2.43 (D). At the split-fibre points, FAC2 goes 0.15 → 0.45 and FB +1.16 → +0.32, while R stays near zero (−0.02).
- **Request, refined:**
  1. Give the QES-Turb ground roughness its own setting, for example on `Turbulence`. The profile's tail roughness describes the inflow shape below the lowest measurement, which is a different quantity.
  2. Keep the inflow-based reference (a k(z) table, or u\*) as the better option. No single ground roughness matches both cases' approach-flow k, and the in-city k pattern is wrong at any z0.
  - Both are native or near-native and need re-qualification.
- **The open question below** is answered for the level. The pattern (R ≈ 0) remains open.

**Phase 3 result (2026-11-01).** At Case D 0° and 2 m, the k from QES-Turb is about 4× lower than the split-fibre k at the 33 measured points: mean 0.0062 U_ref² against 0.024 U_H², R = 0.09, FAC2 0.15.
- **The inflow itself is already turbulent:** k/U_H² is 0.012–0.017 below 200 m in the approach flow.
- **Open question:** a separate run is needed to tell whether the morphometric u\* is the cause or the mixing-length model. The candidate check is QES-Turb's k in the undisturbed approach flow against the inflow table. That k must come from upstream probes in a run *with* buildings: without buildings, `turbulence_reference.cpp:14-26` takes the other branch (z0 from the profile, reference height 100·z0), which does not test the morphometric u\*.
- **Ground roughness:** the measured profile's tail roughness is 3.5e-5 m. It reaches only the QES-Turb ground wall model, which is a second suspect (Phase 5).


**Need.** QES-Turb takes u\* from the solved field at z_ref = 3·H̄, with z0 = 0.1·H̄ and d = 0.7·H̄ (`turbulence_reference.cpp:15-26`). The AIJ inflow tables give k(z), but profiles carry only u and v.

**Request (conditional).** If the Case D comparison of k at the 33 split-fibre points shows that the morphometric reference is the main error, allow a reference taken from the inflow, such as u\* or a k(z) table on the profile or on `Turbulence`. This is a native change, so batch it with the policy re-qualification.

## R12 (dtcc-qes): monitor histories without a time budget. Low

**Status 2026-11-01:** the workaround works.
- `Solver(max_solve_seconds=86400, monitor=MonitorSpec(receptors=<80 probes>, heights=(), history_limit=<iterations/25 + 2>))` recorded full 16,000-iteration histories at 1 m (641 checkpoints × 80 receptors), with `memory_limit_bytes` set to 512 MiB; whether the default 64 MiB is enough was not tested.
- The iterates equal those of a legacy solve exactly.
- Only documentation would help: the README could say that a bounded run with a large budget is the way to monitor a legacy-equivalent solve.

**Need.** Receptor histories (`MonitorSpec(receptors=...)`) are the best per-probe convergence evidence for runs outside the adaptive scope. They are available only in bounded mode, which needs `max_solve_seconds`.

**Request.** Allow `Solver(monitor=...)` in legacy mode, or document that a large `max_solve_seconds` is the supported way to monitor a legacy-equivalent run. Check whether 80 receptors in bounded mode have limits beyond `memory_limit_bytes`.

## R13 (dtcc-qes): stale positional call in the docs. Done

**Status 2026-11-01:** fixed directly in `docs/building-contacts.md`; `tests/test_user_documentation.py` passes. `docs/solver-control-s4.md:26` keeps its old call on purpose, because historical milestone notes retain their original API.

`docs/building-contacts.md:27` calls `wind.run(city, 5.0, 270.0, footprints=policy)`. Since the API break, `speed` and `direction` are keyword-only, so this raises `TypeError`. Use `wind.run(city, speed=5.0, direction=270.0, footprints=policy)` or a `LogProfile`.

## R14 (dtcc-qes): an iteration count or stopping rule that works at fine grids. New, medium

**Evidence (step 2 Phase 2, `AIJ_VALIDATION.md`).** Seven AIJ configurations were run at 2 m and 1 m: 13–19 M cells at 1 m, with float32 probe histories and float64 end points.
- **At the 2 m probes**, K meets p95 |ΔK| ≤ 0.005 and max ≤ 0.02 against the float64 end point within 450 iterations.
- **At 1 m that takes up to 1,675 iterations**, roughly 4× per halving of the cell size. The default `Solver()` stops at 1,000 iterations and leaves p95 errors of 0.006–0.013 in K. That matters for comfort classes, whose thresholds sit only a few tenths of a K unit apart.
- **Such a run reports `converged=False`, but that flag cannot be made reliable.** In float32 the multiplier change stalls at 0.8–1.5e-4, around the default tolerance of 1e-4, even after the probe K has stopped changing (|ΔK| < 1e-5).
- **float32 itself is not the problem.** It agrees with float64 to 3e-5 at the probes.

**Request.** One of these, in order of preference:
1. **A stopping rule on the monitored output.** For example, stop when the monitored plane or receptor speeds change by less than a tolerance over a window. `MonitorSpec` already records `short_change`/`long_change`; this would make it usable outside the adaptive policy.
2. **A resolution-aware default `max_iterations`.** For example, scale with the number of cells along the largest horizontal axis, with documented headroom.
3. **At least documentation.** Say that the λ tolerance cannot certify convergence in float32, and give the AIJ numbers as a guide: fine at 2 m with 1,000 iterations, 4,000 or more at 1 m.

Option 3 is a small docs change. Options 1 and 2 change behaviour, so they are requests. The validation itself uses fixed work (2,000 iterations at 2 m, 6,000 at 1 m) and checks it with probe histories.

**Phase 4 (0.5 m).** A monitored 100 M-cell Case E run met the probe target at 4,500 iterations. That fits the 4× per halving trend. It stayed within 1e-4 of its 32,000-iteration end point from 13,200 iterations on, so the validation uses 16,000 at 0.5 m. The default `Solver()` would stop at 1,000.

## R15 (dtcc-qes): expose the building-parameterisation flags. Done

**Status 2026-11-02: implemented directly in dtcc-qes and committed as `c9e31e8` on `main`** (Python only; the policy identity is unchanged).
- **API:** `wind.Parameterizations(rooftop=1, upwind_cavity=2, street_canyon=1, wake=2, high_rise=0, sidewall=1, wall_roughness=0.001)` (`src/dtcc_qes/parameterizations.py`), passed as `parameterizations=` to `wind.run` and `wind.preview_grid`. The defaults are the native defaults; a test checks that they match `_qes.ModelSettings()`.
- **Checks on construction:** the native code ranges, wake > 0 when rooftop, street canyon or sidewall is on, and a positive wall roughness that is finite in float32. The native bridge still checks the same at preparation.
- **Recording:** `metadata["model"]` keeps the native flag names and adds a versioned `parameterizations` payload (`Parameterizations.from_dict` restores it).
- **Adaptive runs:** non-default settings give `unqualified_model_settings` in the preview eligibility and at runtime (`not_assessed`, 1.78 fallback), and `raise_on_failure=True` raises before the native runner exists.
- **Not offered:** `street_intersection` has no model.
- **Not covered:** the `qes_wind` dataset keeps the defaults.
- **Two scope notes from the source:**
  - `high_rise` acts only on buildings at least twice as tall as their effective length (`PolygonWake.cpp:159`). The AIJ Case D tower qualifies, at 100 m on a 25 m footprint.
  - `wall_roughness` is the z0 of the sidewall and street-canyon log laws (`WINDSGeneralData.cpp:113`). QES-Turb's wall model uses the ground roughness field instead (`TURBWallTerrain.cpp:103`).
- **Tests:**
  - `tests/test_parameterizations.py`: the defaults, construction checks, that each setting changes the solved field and is recorded, the adaptive exclusion, and type errors.
  - The spec JSON round trip, and the `run`/`preview_grid` signature contract.
- **Full dtcc-qes suite:** 1,722 passed and 1 failed with `OMP_NUM_THREADS=4`. The failure predates R15: `test_dataset_footprints.py:112` pins dtcc-core `80a4bba`, but `pyproject.toml` now pins `66c81a2`.
  - With the default team (14 threads on this machine), 10 adaptive tests also fail with `unqualified_thread_team`. They pass with a team of 4.
- **Validation regression:** the 35 baseline runs were rerun under the new fingerprint. Every probe value is bit-identical to Phase 3 (K, K_scalar, speed, span, k), and the headline table is unchanged. `RunSpec` keys of default runs are unchanged.

The original request follows.

**Need.** The QES building parameterisations decide much of the pedestrian wind, and the AIJ comparison points at them (`AIJ_VALIDATION.md`, Phase 3).
- **Background flow:** probes outside every zone keep the approach profile (Case E is overpredicted, FB −0.43).
- **Wakes:** strong wake reductions appear where the tunnel shows speed-ups behind the new tower.
- **Not reachable from Python:** the flags are fixed at their native defaults (`api/wind_config.h:26-27`: rooftop 1, upwind cavity 2, street canyon 1, street intersection 0, wake 2, high rise 0, sidewall 1). They are only recorded in `metadata["model"]`.
- **The scratch test:** `high_rise_flag = 1`, set by patching the `ModelSettings` that `prepare_domain` returns, changes Case D probes by p95 0.09–0.16 in K and some Case E probes by up to 0.39. It is a real sensitivity, and the validation cannot study it without patching private code.

**Request.** A public, immutable spec, for example:

```python
wind.run(..., parameterizations=wind.Parameterizations(rooftop=1, upwind_cavity=2, street_canyon=1,
                                                     wake=2, high_rise=0, sidewall=1, wall_roughness=...))
```

- **Defaults unchanged.** It is passed to `_qes.ModelSettings`, whose fields are already read-write from Python (`src/cpp` bindings: `wake_flag`, `high_rise_flag`, …).
- **Validation:** check against the native ranges (`model_inputs.cpp:179-185`) and `validateWakeDependencies` before preparation.
- **Recording:** record the spec in metadata.
- **Adaptive runs:** non-default flags should exclude a run from `pedestrian-v1`, which is qualified only for the defaults.

This is Python-only, so it does not change the policy identity.

**Scope check (2026-11-02): smaller than written above.**
- **Native validation exists:** `model_inputs.cpp:178-185` checks every flag range and the wall roughness, and line 196 calls `validateWakeDependencies`.
- **Adaptive exclusion exists:** `pedestrian_policy.cpp:43-45` already marks any non-default flag or wall roughness as `unqualified_model_settings`.
- **Recording exists:** `wind.py:201` already records the flags in `metadata["model"]`.
- **Left to do:** the spec, the `wind.run` (and `preview_grid`) keyword, the assignment to the prepared `ModelSettings`, and tests.
- **`street_intersection_flag` need not be exposed:** it is validated but has no model (`model_inputs.cpp:186`).

## R16 (dtcc-qes): flag grid-sensitive receptors, and smooth the zone edges. New

**Evidence (step 2 Phase 4, `AIJ_VALIDATION.md`).** Case E was refined from 1 m to 0.5 m at 4 directions × 2 states (640 probe values).
- **The pooled agreement scores do not move** (q, FB and R within 0.03), **but individual probes do.**
  - p95 |ΔK| is 0.06–0.07, against the repo budget of 0.05.
  - 17–19 % of the probe values change by more than 5 %.
- **The changes sit near walls and at sharp features.**
  - The 5 probes within 2 m of a wall change by a median 18 %. That is the 10–18 % that `docs/near-wall-validation.md` traced to the sidewall initialisation.
  - Probes more than 5 m from a wall change by p95 0.02.
- **The changes are not asymptotic.**
  - Of the probes that still change by more than 0.02, only 58 % move in the same direction as on the refinement before, and the median ratio of the two changes is 0.95.
  - One point 10 m from a wall has K = 0.40, 0.12 and 0.53 at 2, 1 and 0.5 m.
  - This fits zone edges snapped to cells, but it was not traced zone by zone.
- **One run can flag them.** The range of K within max(1 m, dx) of the probe predicts the change on the next refinement.
  - Probes with a range below 0.05 change by p95 ≤ 0.016 from 1 to 0.5 m.
  - Probes with a range above 0.15 change by 0.12–0.13.

**Request.**
1. **Python-only, medium: a neighbourhood range on samples.**
   - For example, `sample_points(..., neighbourhood=1.0)` returning the minimum and maximum speed-up within the radius, as the validation's `sampling.probe_sample` computes it.
   - `comfort.assess_results` could then flag receptors whose comfort class depends on the grid instead of reporting them with false precision.
2. **Native, low: smoother zone edges in the initialisation,** starting with the sidewall branch documented in `docs/near-wall-validation.md`.
   - This changes the policy identity, so it belongs in a batch with re-qualification, like R2 and R11.

## R17 (dtcc-qes): a canopy-aware background inside built-up areas. Open, medium

**Phase 6 decision (2026-11-02): filed.** Two concerns were weighed against the evidence.
- **The instrument gap:** the thermistors read higher than the mean vector in sheltered spots, so slowing the background could merely fit that bias.
  - Against this concern: Case E is overpredicted mainly at fast, open probes, where the gap is small (Phase 3).
  - And with the canopy inflow alone, the like-for-like Case D split-fibre R rises from 0.55 to 0.62, although its level is then too low.
- **Per-probe grid sensitivity:** it does not apply. The gain shows in pooled scores, and it holds at 1 m.

What fails is the strength and the reach of a background applied over the whole domain, not the direction of the change.

**Evidence (step 2 Phase 5, `AIJ_VALIDATION.md`).** The near-ground background is the largest lever on the AIJ scores.
- **What the data show:**
  - In Case E, probes outside every building zone keep the approach profile (Phase 3, finding 1).
  - A log-law inflow, slower near the ground, raises the Case E "before" hit rate by 0.12.
  - An in-canopy inflow (z0_u = 0.1·H̄ below z_b = 6·H̄) raises it by 0.34.
- **Applied over the whole domain, it is a blunt tool.**
  - It slows the open approach flow and every building zone as well.
  - It overshoots in Case D: split-fibre FB −0.23 → +0.37.
  - It cannot tell a dense low-rise district from open space.

**Request.** An opt-in initial-field model that slows the background *inside* built-up areas, from the local plan-area and frontal-area densities, and leaves the approach profile outside them. QES's vegetation canopy model is a possible template. This is a native model change, with re-qualification.

**Acceptance** (AIJ_VALIDATION_PLAN.md, Phase 5 protocol). One setting derived from the morphometry, the same for both cases, must:
- raise q and keep or raise R and ρ, against the defaults, on Case E "before", Case E "after" and the Case D split fibre;
- not worsen the Case D thermistor scores beyond the instrument-gap effect;
- do this at 2 m and at 1 m;
- improve the Case E change scores, or at least keep them.

A per-case or per-district calibration does not satisfy it.


## R18 (dtcc-qes): roof separation on isolated buildings. New, medium, native

**Evidence (Cases A and B, `AIJ_AB_VALIDATION.md`, 1 m).**
- The default rooftop model (code 1) has no effect on either isolated building: switching it off changes no mean-flow score by more than 0.004.
- **Case A:** the tunnel's roof separation (reattachment at X_R = 0.52 b) is absent. 2 m above the roof the simulated U is 1.13–1.27 U_H; the tunnel measures 0.28 and 0.37 U_H over the roof centre and 0.95 at its windward edge.
- **Case B:** 1.6 m above the slab, the measured U of 0.46, −0.05 and −0.13 U_H is simulated as 1.42, 1.26 and 1.14 U_H. The |U| bias above the roof is +0.29.
- The vortex model (code 2) lifts the Case B pattern R by 0.11 but leaves q unchanged.

**Request.**
- Document when the code-1 model applies, and why it does not here.
- Consider a roof-separation zone for buildings whose along-wind length is short relative to H (the Case A and B shapes), as the URock/QUIC-URB comparisons also miss it.

**Acceptance.** It must:
- raise the roof-region scores of both cases;
- keep the wake scores;
- keep the Case D/E scores within ±0.03.

## R19 (dtcc-qes): QES-Turb k in shear layers and non-realisable stresses. New, medium, native

**Evidence (Cases A and B).** These are like-for-like split-fibre k data.
- **No skill:** QES-Turb scores q = 0.07 and 0.02, with R = 0.17 and 0.13.
- **It overpredicts at roof height:** k/U_H² reaches 0.8–1.0 against at most 0.17 measured. The mixing length acts on the velocity step that the rooftop and wake zones impose.
- **It is not realisable:** at 33 (A) and 22 (B) probes the stress tensor has a negative eigenvalue, and dtcc-qes masks k as invalid.
- **Contrast with the districts:** in Cases D and E, k is 0.3–0.4 times too low (R11). One closure is wrong in opposite directions in the two settings.

**Request.**
- Bound the shear-layer mixing length, or smooth the parameterised velocity jumps before the gradients are taken.
- Report the masked fraction in `result.turbulence`.

Batch it with R11 under one re-qualification.

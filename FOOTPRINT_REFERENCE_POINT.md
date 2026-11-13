# Keep the building reference point inside the footprint

- **Date:** 2026-11-13.
- **Change:** `PolyBuilding::setPolyBuilding` uses the vertex mean of the outer ring as the building's reference point. That point samples the incident wind and anchors the wind-aligned frame of the wake and canyon parameterizations. For L- and U-shaped footprints and blocks with courtyards, the mean can lie outside the building. When it does, the reference point is now the midpoint of the widest interior span on a horizontal scan line that passes through no vertex. When the mean is inside, which is always the case for convex footprints, it is kept bit for bit.
- **Origin:** `4eb119d` on `research/pedestrian-wind-campaign`, cherry-picked without changes. It includes a native test (`check_contacts`: a courtyard block and an L-shape).
- **Status:** declaration written before any measurement (section 1); every criterion passed (section 2); identity re-qualified and promoted.

## 1. Declaration

An intentional numerical change of default results (`docs/solver-control-requalification.md`, last paragraph). The native identity moves from `bf48ef3f…` (`main`) to `31f6d956…`; version 0.1.0b4.

- **Affected:** every solve with a building whose outer-ring vertex mean lies outside its footprint, for every wake and canyon code and both stop rules.
- **Predicted, bitwise comparison (`compare_native_builds.py`):** only the `courtyard` and `l_shape` geometry cases may change, since their vertex means, (42, 32) and (41.3, 33.3), are outside. Every other case must stay bitwise identical, including `slab_gap`, `shared_wall`, `tall_short`, all public and native block cases, and therefore the W1b records. The version string differs in the `metadata/versions` records, as in the previous merge.
- **Predicted, AIJ:** Cases A, B and D have no such footprint, so they stay bitwise identical. Case E has 5 such buildings in each state, out of 533 and 536 before footprint cleaning, none with a courtyard. Only Case E may change.
- **Unaffected:** the 24 frozen S7 workers (rectangular footprints) and the combined feature baseline must match exactly.
- **Independent criteria:**
  - Case E pooled q, FAC2, R, ρ and FB change by at most 0.01, with the default solver and with fixed work.
  - The `wake=3` W4 gates still pass.
  - No probe K changes outside Case E.

## 2. Results

Every prediction held; every criterion passes. Evidence in `docs/data/footprint-reference-point/`.

- **Bitwise comparison** against `main` `7bf2115`: 509 cases, OpenMP at 1, 2, 4 and 8 threads and serial, thread teams and backends identical. 95 records differ from `main`:
  - 72 in the declared geometries, `l_shape` (48) and `courtyard` (24);
  - 23 `metadata/versions` records that differ only in `dtcc_qes` 0.1.0b3 → 0.1.0b4 (115 of 115 checked).

  Every other case, including `slab_gap` and its W1b records, is bitwise identical.
- **AIJ, 2 m baseline** (Cases A, B, D, E, turbulence on; campaign `stop_rule_g6`, the same 74 runs on `main`'s staged package and on the fix):
  - **A, B and D:** bitwise identical (probe values and the 2 m planes) with both solvers.
  - **Case E:** every run changes. Of 2,560 probe-directions, 2.58 % move by more than 0.01 in K, 0.35 % by more than 0.05, and 0.04 % (one) by more than 0.1 (max 0.111).
  - **Pooled scores:** q, FAC2, R, ρ and FB change by at most **0.0031** with the default solver and with fixed work (limit 0.01). Default-solver sweep counts are unchanged.
- **`wake=3` W4 gates:** all 18 pass. A, B and D values are identical; Case E values move by at most 0.0031.
- **Re-qualification** (`docs/solver-control-requalification.md`, candidate `df7d285`, identity `31f6d956fecfa24654a34b7ed43941c38876f38b26d0800ca5868e7b54396f87`):

| Check | Result |
|---|---|
| Native builds | CTest OpenMP 63/63, serial 60/60, ASan/UBSan 60/60; symbol checks; equal identities |
| Isolated copy | keeps the identity and reports support |
| S7 workers | 24/24 match exactly (rectangular footprints, as predicted) |
| Combined feature baseline | 436/436 arrays identical; metadata only in the identity pair and the version |
| `pytest -W error` on both isolated packages | 2,066 passed |
| Artifacts | sdist (21.6 MB) and wheel pass `check_artifacts.py`, including its evidence audit |
| Wheel runtime smoke (4-thread team) | passes; adaptive run accepted |

The identity is promoted in `pedestrian_qualification.h`.

## 3. Merged into main (2026-11-13)

Merged as `3cbe316`, version 0.1.0b4. `main` had moved to `86c9723` during the qualification (wake-comfort plans, docs and validation harness; no product code). The merge equals the qualified tree `fe2dcd3` plus exactly those changes, with no file in common. Post-merge check on `main` (`docs/data/footprint-reference-point/merged-main-verification.json`):

| Check | Result |
|---|---|
| Release build | identity `31f6d956…` supported |
| Native CTest | OpenMP 63/63, serial 60/60 |
| `pytest -W error` | 2,032 passed |
| Validation tests | 191 passed, including the new wake-comfort tests, now on the fixed code |
| Artifacts and evidence audit | pass |
| Wheel runtime smoke (4-thread team) | passes; adaptive run accepted |

The wake-comfort evidence in `docs/data/wake-comfort/` (`86c9723`) was computed before this fix. It records its native identities and stays valid as a record, but its Case E numbers would move slightly if rerun on 0.1.0b4.

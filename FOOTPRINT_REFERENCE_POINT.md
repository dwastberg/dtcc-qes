# Keep the building reference point inside the footprint

- **Date:** 2026-11-13.
- **Change:** `PolyBuilding::setPolyBuilding` uses the vertex mean of the outer ring as the building's reference point. That point samples the incident wind and anchors the wind-aligned frame of the wake and canyon parameterizations. For L- and U-shaped footprints and blocks with courtyards, the mean can lie outside the building. When it does, the reference point is now the midpoint of the widest interior span on a horizontal scan line that passes through no vertex. When the mean is inside, which is always the case for convex footprints, it is kept bit for bit.
- **Origin:** `4eb119d` on `research/pedestrian-wind-campaign`, cherry-picked without changes. It includes a native test (`check_contacts`: a courtyard block and an L-shape).
- **Status:** declaration written before any measurement (below); results in section 2.

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

To be filled in after the runs.

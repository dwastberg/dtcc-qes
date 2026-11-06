# AIJ Cases A and B: validation setup and results

This file covers the validation of dtcc-qes against AIJ benchmark Cases A and B: two single buildings in a turbulent boundary layer. It uses the same framework as Cases D and E:
- **Cities:** [`AIJ_CITY_MODELS.md`](AIJ_CITY_MODELS.md);
- **Framework plan:** [`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md);
- **D/E results:** [`AIJ_VALIDATION.md`](AIJ_VALIDATION.md).

The A/B code adds one module (`aij/case_ab.py`) and extends the shared ones. The D/E run keys and results are unchanged.

**Status (2026-11-05, dtcc-qes `6e205c0+dirty`, native policy `a6df05f6`):** the setup is done. All campaigns have run (baseline, iterative convergence, grid study 4/2/1/0.5 m, 16 sensitivity variants), with 128 validation tests. The `+dirty` marks someone else's uncommitted research changes in `src/`; their default path is unchanged.

The results and the summary of how well dtcc-qes matches are under "Summary", after the evidence sections.

## How to run

```sh
uv run --group validate python validation/build_cities.py                                  # also writes aij_a/aij_b .dtcc + .png
uv run --group validate python validation/run_validation.py --campaign ab_smoke            # 4/2/1 m, default solver, ~20 s
uv run --group validate python validation/run_validation.py --campaign ab_baseline --jobs 2   # 1 m, 2 runs, ~30 s
uv run --group validate python validation/run_validation.py --campaign ab_convergence --jobs 3  # probe histories, ~5 min
uv run --group validate python validation/run_validation.py --campaign ab_grid             # 4, 2, 0.5 m, ~20 min, ~16 GiB
uv run --group validate python validation/run_validation.py --campaign ab_sensitivity --jobs 3  # 16 variants x 2, ~8 min
uv run --group validate python validation/report_validation.py --only ab                   # -> output/report/ab_*, isolated*.json
uv run --group validate pytest validation/tests -q                                         # 128 checks (22 for A/B)
```

- **Report:** `report_validation.py` without `--only` reports every case. `--only de` skips A and B.
- **Tracking a new revision:** rerun `ab_baseline` (30 s) and the report, then paste `output/report/headline_ab.md` under "Headline metrics" below. The steps are the same as for D/E (`AIJ_VALIDATION.md`, "Tracking a new revision").
- **Runs and keys:** as for D/E. Each run gets its own process and its record goes to `output/runs/<A|B>/<key>.json`; the run key is the hash of the `RunSpec`.
  - The new `RunSpec.downstream` field is left out of the JSON at its default, so every D/E key is unchanged. A test pins `3af75ea91b3dfde2`.

## Findings from the data

The two spreadsheets were read with xlrd, including their embedded figures. The Case A figures are OLE bitmaps, extracted and viewed. A web search filled in what the sheets leave out (sources at the end).

- **F1. Sheets.** Cell ranges are Excel A1. In both cases k = ½ Σ variances exactly.
  - **Case A (`CaseA(1_1_2).xls`):**
    - `Inflow` B3:G26: 24 rows of z/b, U, σu, σv, σw and k, from z/b = 0.0625 to 7.5.
    - `Results (Ver. sec.)` A3:K68: 66 points on y = 0, up to z = 3.5b.
    - `Results(Hol. sec.; z=0.125b）`: 60 points, z = 0.125 b.
    - `Results (Hol. sec.; z=1.25b）`: 60 points, z = 1.25 b.
    - Every result sheet has No., x/b, y/b, z/b, U, V, W, σu, σv, σw and k.
  - **Case B (`CaseB(4_4_1).xls`):**
    - `Inflow` B4:H15: 12 rows of z [mm], U, a "1/4 power" column, u'², v'², w'² and k, from 5 to 1000 mm.
    - `Results (Ver. sec.)` A4:K112: 109 points on y = 0, from 5 to 350 mm.
    - `Results (Hol. sec.)` A4:K118: 115 points at z = 12.5 mm.
    - Every result sheet has No., x, y, z [mm], U, V, W, u'², v'², w'² and k.
  - **Only one wind direction, 0°.** The "WIND" arrows of Fig. 2 point to +x, and the data agree: U > 0 upstream and above, reverse flow behind the building. The meteorological direction is therefore **270°**.
- **F2. Geometry.** There is no drawing; the shapes follow from the point layouts and figures.
  - **Case A:** a square prism b × b × 2b with b = 80 mm, so H = 160 mm (Meng & Hibi 1998). The origin is the centre of the footprint.
  - **Case B:** a slab b = 50 mm deep (along the wind), 4b = 200 mm wide and 4b = 200 mm tall, with the wide face normal to the wind.
    - Points at x = −25, 0 and 25 mm exist only above z = 200 mm.
    - In the horizontal section they start at y = −110 mm.
    - x = −75 mm and x = 50 mm are measured down to the floor.
    - Shirasawa et al. (2003) confirm this. The 2024 AIJ page renames the case "1:4:4".
  - **Origins:** the footprint centre on the floor, in both cases.
- **F3. Quirks of the sheets.**
  - **Case A, z = 1.25b sheet:** the z column repeats 0.125 under a "z/b" header. The sheet name, Meng & Hibi's Table 4 and the values (U = 1.51 m/s at point 1, against 0.21 m/s at 0.125b) put it at 1.25 b. The reader sets z = 1.25 b, and a test pins this.
  - **Horizontal sections:** both cases measured only the y ≤ 0 half.
  - **Points measured twice:** 5 in Case A and 7 in Case B lie at the same position in two sheets. They give the tunnel's own repeatability (results below).
  - **Case B centreline asymmetry:** in the wake near the floor, the y = 0 points have V up to 0.14 U_H, so that flow is not symmetric.
  - **Case A sign conventions:** the sign of V is physically consistent. Flow leaves the leading corners outward (V < 0 at y < 0), as Meng & Hibi's Fig. 5 shows.
- **F4. Instruments.** Both cases used Dantec split-fibre probes, which resolve reverse flow.
  - **Case A:** the streamwise component was measured in one traverse (55R55 probe) and the cross components in another (55R57). The approach flow was measured without the model at x/b = −4, 0 and 4, and averaged (Meng & Hibi 1998).
  - **This is like for like with dtcc-qes:** both give mean vectors. Unlike the thermistor data of Cases D and E, there is no scalar-versus-vector gap.
- **F5. The Case B lateral velocity has the opposite sign convention.** This is an inference.
  - **As tabulated, V cannot be right:**
    - 10 mm outside the side face (x = −25 mm, y = −110 mm), V = +3.63 m/s = 0.71 U_H. That is flow straight into the wall.
    - Across the horizontal section, V correlates with the simulated V at ρ = −0.81. In Case A the same correlation is +0.89.
  - **Negated, it is consistent:**
    - The flow leaves the leading corners outward, as in Case A.
    - The correlation becomes +0.81.
    - Horizontal flow directions within 30° of the simulation rise from 0.52 to 0.76.
  - **Treatment:** `tables` keeps the sheet values, and the comparisons negate Case B's V (`compare.LATERAL_SIGN`).
  - **Effect:** only the flow-direction score and the V profiles change. |U|, U, W and k do not depend on the sign of V.
- **F6. Published references.** These are context, not targets. The sources are Tominaga et al. (2004, Tables 1–2), Mochida et al. (2002) and Shirasawa et al. (2003).

  | | Case A | Case B |
  |---|---|---|
  | Wake reattachment X_F/b near the floor, from the leeward face: experiment | 1.42 | 7.6 (at 12.5 mm) |
  | Standard k-ε | 1.66–2.70 | 9.2–11.6 |
  | Revised k-ε (LK, RNG, MMK, Durbin, …) | 2.70–3.34 | 9.2–13.6 |
  | LES | 1.02–2.10 | 7.6 |
  | Roof reattachment X_R/b from the windward edge: experiment | 0.52 | — |

  - **URock (Bernard et al. 2023)** ran QUIC-URB and its own Röckle-type model on Cases A and B. It reports correlations between the two models only, not against the tunnel. Its qualitative failures:
    - speeds are overpredicted beside the upwind corners;
    - near-floor W is far too small;
    - the Case B roof deficit is missed;
    - W has the wrong sign in the upwind vortex.
  - No published comparison of QES-Winds with AIJ A or B was found.
- **F7. Inflow.**
  - **Case A** follows AIJ terrain category IV, with α ≈ 0.27 quoted. A power law fitted up to 2H gives α = 0.17 here, because the near-floor profile is fuller than a power law.
  - **Case B** quotes α = 1/4. Its "1/4 power" column misses the measured speed near the floor (2.62 against 3.11 m/s at 12.5 mm), so the measured column drives the runs. The fitted α up to 2H is 0.18.
  - **Tail roughness:** the fitted log tail below the lowest point has z0 = 2.8e-4 m (A) and 8.7e-5 m (B) at full scale. The AIJ CFD specifications used z0 = 0.036 m and 0.0154 m (scaled). That z0 reaches dtcc-qes only through the QES-Turb wall model and the tail, which the "ground z0" variant tests.

## Decisions

- **D1. Full scale.** The near-floor section is put at the 2 m pedestrian height, as in Cases D and E.
  - **The resulting buildings:**
    - Case A at 1:200: b = 16 m, 16 × 16 × 32 m.
    - Case B at 1:160: b = 8 m, 8 × 32 × 32 m.
  - **Why:** both buildings are 32 m tall, and every face lies on a grid face at 4, 2, 1 and 0.5 m.
  - **Other scales exist:** Meng & Hibi state 1:500 (an 80 m tower) for Case A, and URock used yet other scales.
  - **dtcc-qes is nearly scale-free.** Its only absolute lengths are:
    - the wall roughness (1 mm);
    - the profile tail z0, which scales with the table;
    - the QES-Turb mixing lengths.
  - A run at another scale with the same b/Δx is a cheap check, not yet done (see Limitations).
- **D2. Normalisation and quantities.**
  - Every speed is divided by U_H, the tabulated approach-flow speed at H: 4.491 m/s (A) and 5.133 m/s (B). dtcc-qes is divided by its own inflow at H, which passes through the same table point.
  - **Compared quantities:**
    - |(U, V, W)|/U_H, the same "K" as for D/E;
    - the signed U/U_H, which carries the recirculation;
    - W/U_H;
    - k/U_H², scored with W = 0 as for Case D.
  - **The "no building" reference.** It is the undisturbed approach flow at every probe: U = U_in(z), W = 0, and the inflow k. dtcc-qes has to beat it to show that its building models add information.
- **D3. Grid.**
  - **Vertical faces** sit at multiples of the layer thickness (`grids.layer_centre`), uniform to 2H = 64 m and stretched above (1.15, capped at 4×). The roof (32 m) is a face, and a test checks that the solid cells hold exactly the building's volume. The 2 m section falls on a face, where it is interpolated linearly between the 1.5 and 2.5 m centres (1 m grid).
  - **Domain:** 3H upwind and to the sides, 8H behind, and the top at 5H (`runspec.AB_DOMAIN`).
  - **The AIJ guideline** (5H, ≥ 10H behind) is checked by the "domain 5 H / 15 H" variant. The top cannot go below about 3.5 H, because QES-Turb needs two layers above its 3H reference height.
- **D4. Solver work.** The D/E fixed work per resolution is reused: 1000/2000/6000/16000 iterations at 4/2/1/0.5 m, float32, with the tolerance below the stall. `ab_convergence` checks it with probe histories and float64 end points.
- **D5. Baseline.**
  - **Spacing:** 1 m, with turbulence on. That is b/16 in Case A and b/8 through the Case B slab; the Case D tower had b/12.5 at its 2 m baseline.
  - **Grid study:** 4, 2, 1 and 0.5 m, all with turbulence on. The small domains allow this: about 55 M cells at 0.5 m.
- **D6. What is scored.**
  - **Point scores:**
    - the hit rate (D = 0.25, W = 0.05), FAC2, R, ρ and FB, as for D/E;
    - the same scores by section, by region (upwind, roof, side, wake) and by measured flow sense.
  - **Features:**
    - the sign agreement of U where |U|/U_H > 0.05, with the reverse-flow recall;
    - the wake reattachment length on the centreline at 2 m, from a 0.25 m line sample. The measured value is interpolated between stations, and the bracketing stations are stored.
  - **Flow direction:** the horizontal angle error at the horizontal-section points.
  - **Repeatability:** the tunnel's own, from the points measured twice.

## Headline metrics per dtcc-qes revision

`report_validation.py` writes this table to `output/report/headline_ab.md`.
- **Scores:** q is the hit rate (D = 0.25, W = 0.05); FB > 0 means underprediction.
- **Settings:** 1 m, the measured inflow, 6,000 iterations, turbulence on.
- **"No building":** the approach flow alone (D2).

**2026-11-05, `6e205c0+dirty`** (native policy `2e80b9a7`; the `+dirty` is other sessions' uncommitted research changes in `src/`, default path unchanged):

| dtcc-qes | policy | Case | Model | n | q | FAC2 | R | ρ | FB |
|---|---|---|---|---|---|---|---|---|---|
| `6e205c0+dirty` | `2e80b9a7` | A (1:1:2) | \|U\|/U_H | 186 | 0.66 | 0.88 | 0.86 | 0.86 | -0.10 |
| `6e205c0+dirty` | `2e80b9a7` | A (1:1:2) | U/U_H | 186 | 0.61 | 0.84 | 0.89 | 0.88 | -0.08 |
| `6e205c0+dirty` | `2e80b9a7` | A (1:1:2) | W/U_H | 186 | 0.84 | 0.46 | 0.81 | 0.73 | -1.14 |
| `6e205c0+dirty` | `2e80b9a7` | A (1:1:2) | k/U_H² | 153 | 0.07 | 0.24 | 0.17 | 0.19 | -1.12 |
| `6e205c0+dirty` | `2e80b9a7` | A (1:1:2) | no building, \|U\|/U_H | 186 | 0.55 | 0.74 | 0.50 | 0.52 | -0.23 |
| `6e205c0+dirty` | `2e80b9a7` | B (4:4:1) | \|U\|/U_H | 224 | 0.51 | 0.74 | 0.73 | 0.73 | -0.23 |
| `6e205c0+dirty` | `2e80b9a7` | B (4:4:1) | U/U_H | 224 | 0.45 | 0.75 | 0.83 | 0.81 | -0.42 |
| `6e205c0+dirty` | `2e80b9a7` | B (4:4:1) | W/U_H | 224 | 0.63 | 0.18 | 0.72 | 0.53 | +1.17 |
| `6e205c0+dirty` | `2e80b9a7` | B (4:4:1) | k/U_H² | 202 | 0.02 | 0.10 | 0.13 | 0.09 | -0.79 |
| `6e205c0+dirty` | `2e80b9a7` | B (4:4:1) | no building, \|U\|/U_H | 224 | 0.39 | 0.57 | 0.51 | 0.42 | -0.41 |

| dtcc-qes | Case | X_F/b at 2 m, measured (tabulated, published) | X_F/b dtcc-qes | U sign agreement | reverse-flow recall | flow angle within 30° |
|---|---|---|---|---|---|---|
| `6e205c0+dirty` | A (1:1:2) | 1.32, 1.42 | 1.91 | 0.97 | 1.00 | 0.97 |
| `6e205c0+dirty` | B (4:4:1) | 7.85, 7.60 | 8.32 | 0.97 | 0.87 | 0.76 |

FB is not meaningful for W, whose mean is near zero.

## Results

### The measured data

- **Repeatability.** These are the points measured twice (F3); the mean |difference| is in units of U_H.
  - **Case A (5 pairs):** |U| 0.014, U 0.004, W 0.049, k 0.001. One measurement scored against the other gives q = 1.00 for |U|, U and k, but only 0.40 for W. W comes from a separate traverse (F4), so the W scores have a low ceiling.
  - **Case B (7 pairs):** |U| 0.039, U 0.020, W 0.041; q = 0.71 (|U|), 1.00 (U), 0.43 (W), 0.86 (k).
  - **So:** differences of about 0.02–0.05 U_H are within the tunnel's own scatter. Unlike Cases D and E, no instrument gap bounds the mean-vector scores.
- **Reattachment from the tabulated stations.** At 2 m it interpolates to:
  - Case A: 1.32 b (between the stations at 0.75 b and 1.5 b);
  - Case B: 7.85 b (between 7.5 b and 10.5 b).
  - The published values are 1.42 b and 7.6 b, from finer data.

### Baseline at 1 m

- **Mean flow.**
  - **Case A** reaches q = 0.66 on |U|/U_H, the VDI 3783-9 reference line, with R = 0.86. **Case B** reaches q = 0.51 and R = 0.73.
  - The undisturbed approach flow alone already scores q = 0.55 (A) and 0.39 (B), because most points lie in nearly undisturbed flow. dtcc-qes adds about 0.11–0.12 in q and lifts R from 0.50 to 0.86 (A) and from 0.51 to 0.73 (B). The building models carry real information, but the hit rate overstates it.
  - **For comparison**, the like-for-like Case D split-fibre comparison scores q = 0.27, R = 0.55. Single buildings are where the Röckle-type models do best. The same holds at 2 m: q = 0.68 for A, so the grid does not explain the gap.
- **Flow topology.**
  - The sign of U agrees at 97 % of the points with a clear sign in both cases.
  - **Reverse flow:** every measured reverse-flow point in Case A is simulated as reverse flow (recall 1.00, false reverse 0.06). In Case B, recall is 0.87: wake 0.89, upwind vortex 0.83, and 0 of the 1 roof point.
  - **Horizontal flow direction:**
    - Case A: median error 3.8°, 97 % within 30°.
    - Case B: median error 15°, 76 % within 30°, after the V sign of F5.
- **Wake length.**
  - **Case A:** 1.91 b, against 1.32–1.42 b measured. That is about 35–45 % too long, inside the standard k-ε range (1.66–2.70 b) and shorter than the revised k-ε models (2.70–3.34 b).
  - **Case B:** 8.32 b, against 7.6–7.85 b measured. That is 6–9 % too long, and closer than any steady RANS model listed in F6 (9.2–13.6 b).
  - The empirical Röckle wake is calibrated for exactly this geometry class, so this is its strongest point.
- **Where it fails.** The per-region breakdown, the profiles and the centre-plane maps show:
  - **Roof flow.**
    - In Case A, dtcc-qes has no roof separation: the default rooftop model (code 1) has no effect on either building, since "rooftop off" changes nothing. The tunnel shows the slowed separation layer (measured X_R = 0.52 b).
    - In Case B, the roof deficit is missed: |U| bias +0.29 above the roof, and 1.6 m above the slab, the measured U of 0.46, −0.05 and −0.13 U_H (front, middle, back) is simulated as 1.42, 1.26 and 1.14 U_H. URock reports the same for QUIC-URB.
  - **Corner speed-up.** Beside Case B (region "side"), U is overpredicted by 0.19 U_H (q = 0.29). This is the overprediction beside the upwind corners that URock also reports.
  - **Reverse-flow magnitude.** The Case A wake reverses too strongly: about −0.25 U_H against −0.14 measured, a U bias of −0.12 at the 14 reverse-flow points (q = 0.07). Near-zero points (|U| < 0.05 U_H) score poorly in both cases, as expected for a relative tolerance.
  - **Near-floor W** is mostly too small; FAC2 for W is 0.18–0.46.
- **Turbulence (QES-Turb).** It shows no skill: q = 0.07 and 0.02, R = 0.17 and 0.13.
  - **It overpredicts** where the D/E districts were underpredicted: k/U_H² reaches 0.8–1.0 in the roof shear layer, against at most 0.17 measured. The mixing length acts on the sharp velocity step that the rooftop and wake zones create.
  - **Non-realisable stresses:** at 33 (A) and 22 (B) probes, mostly at roof height, the stress tensor has a negative eigenvalue. dtcc-qes then masks k as invalid.
  - **Wall and ground roughness** leave k nearly unchanged: Δq ≤ 0.01, ΔR ≤ 0.04.
  - **The inflow shape matters more:** a log-law inflow lifts the Case A k score from q = 0.07 to 0.21.

### Iterative convergence

- **Probe histories** against float64 end points (`ab_convergence`): every probe stays within the D/E targets (p95 0.005, max 0.02) from:
  - 175 (A) and 250 (B) iterations at 2 m;
  - 625 (A) and 975 (B) at 1 m.
- **The fixed work** of 2,000 and 6,000 iterations is therefore 3–10 times what is needed.
- **Precision:** float32 and float64 end points agree within 3e-5.

### Grid study (4, 2, 1, 0.5 m)

All four levels use the baseline settings with turbulence on.

| Spacing | Cells A / B | Wall time A / B | Peak memory A / B |
|---|---|---|---|
| 4 m | 0.13 / 0.14 M | < 1 s | 0.3 GiB |
| 2 m | 0.9 / 1.0 M | 1–2 s | 0.5 GiB |
| 1 m (baseline) | 7.1 / 7.5 M | 23–28 s | 1.8–1.9 GiB |
| 0.5 m | 55 / 58 M | 285 / 286 s | 8.0 / 10.6 GiB |

- **Probe changes per refinement:** |Δ(|U|/U_H)|, with the D/E budget of a p95 below 0.05.
  - **4 → 2 m:** p95 0.085 (A), 0.100 (B).
  - **2 → 1 m:** p95 0.090 (A), 0.063 (B).
  - **1 → 0.5 m:** p95 0.074 (A), 0.018 (B).
  - **Case B converges by 0.5 m.** Only 5 % of its probes change by more than 5 %.
  - **Case A does not.** 13 % of its probes (24) still change: 16 in the wake, 6 beside the building and 2 upwind. The mean shift is +0.006 to +0.014 per halving.
- **Pooled scores** are grid-independent from 2 m:

  | | 4 m | 2 m | 1 m | 0.5 m |
  |---|---|---|---|---|
  | A \|U\| q / R | 0.77 / 0.88 | 0.68 / 0.89 | 0.66 / 0.86 | 0.67 / 0.84 |
  | B \|U\| q / R | 0.52 / 0.76 | 0.50 / 0.74 | 0.51 / 0.73 | 0.50 / 0.73 |

  The coarse 4 m grid flatters Case A, whose 16 m building is then only 4 cells wide.
- **Wake reattachment at 2 m, in b:**
  - **Case A:** 1.72, 1.85, 1.91 and 1.97 at 4, 2, 1 and 0.5 m. It grows by 3–4 % per halving and is not converged, and it moves away from the measured 1.32–1.42 b.
  - **Case B:** 8.05, 8.38, 8.32 and 8.34. It has converged from 2 m.
- **QES-Turb k** has no skill at any spacing (q ≤ 0.10, R ≤ 0.27).

### Sensitivity at 1 m (`ab_sensitivity`, 16 variants)

- **The setup does not matter:**
  - domain 5 H / 15 H (the AIJ guideline);
  - top at 4 H or 8 H;
  - a uniform vertical grid;
  - linear profile interpolation;
  - power-law or log-law inflow;
  - the AIJ CFD ground roughness;
  - a wall z0 of 0.01 m.

  Each moves the mean-flow scores by 0.03 or less and the wake length by 1.5 % or less.
- **The building parameterizations do matter:**
  - **Rooftop vortex (code 2):** pattern R +0.11 (B) and +0.02 (A), with lower speeds (FB +0.03 to +0.09), and q unchanged. It partly recovers the Case B roof deficit. It is the only change that improves the pattern.
  - **Upwind cavity off:** q +0.03 (A) and +0.04 (B) on |U|. The MVP cavity (default) does slightly worse than no cavity at these probes; Röckle and HMVP are within ±0.02.
  - **Original Röckle wake (code 1):** shorter wakes, 1.75 b (A) and 7.77 b (B). Both move toward the measured values, but q drops by 0.03–0.04.
  - **Sidewall off:** R −0.01 to −0.05.
  - **High-rise model:** breaks Case B. The wake reattaches at 0.14 b, q drops by 0.09–0.14 and R by 0.14–0.19.

### Figures (`output/report/`)

| File | What it shows |
|---|---|
| `ab_a_speed_grid.png`, `ab_b_speed_grid.png` | Computed against measured \|U\|/U_H at 2, 1 and 0.5 m, with hit rate and FAC2; grey: the hit-rate acceptance band |
| `ab_scatter.png` | \|U\|, U, W and k at 1 m, coloured by region |
| `ab_a_vertical.png`, `ab_b_vertical.png` | Vertical section y = 0: U, W and k profiles at every station, at 2, 1 and 0.5 m |
| `ab_a_z0p125b.png`, `ab_a_z1p25b.png`, `ab_b_z12p5mm.png` | Horizontal sections: U and V across the wind at every station |
| `ab_a_centre.png`, `ab_b_centre.png` | Simulated U/U_H on the centre plane, its zero contour, the measured points and the reattachment points |
| `ab_inflow.png` | The approach flow and the power-law and log fits |
| `ab_convergence.png`, `ab_grid_scores.png`, `ab_sensitivity.png` | Iterative convergence, scores against grid spacing, sensitivity effects |

In the Case B speed plot, two groups lie off the diagonal:
- **At computed ≈ 0.6 (25 points):** 21 of them are 2 m probes just outside the slab's edges (|y| = 2–4 b), either upwind (x = −1.5 b) or in the far wake (x = 6–11 b). There dtcc-qes keeps the approach-flow speed at 2 m (0.61 U_H), while the tunnel shows slower flow: the upwind vortex and a wider wake.
- **At computed 1.0–1.3 against measured 0.1–0.4 (14 points):** points at roof height (z = 32–36 m), 3 above the roof and 11 in the shear layer behind it. The roof separation is missing there (R18).

## Summary

**How well does dtcc-qes match Cases A and B?** In short: the flow topology is right, the mean speeds are moderately right, and the roof, the corners and the turbulence are wrong.

1. **Mean speeds: at the reference line for the tower, below it for the slab.**
   - **Case A:** q = 0.66 on |U|/U_H, the VDI 3783-9 / COST 732 line, with R = 0.86.
   - **Case B:** q = 0.51, R = 0.73.
   - These are like-for-like mean vectors from split-fibre probes, and the scores are the best of the four AIJ cases. The Case D split-fibre comparison, also like for like, scores q = 0.27.
   - **Much of Case A's hit rate is free flow:** the approach flow alone scores q = 0.55 (A) and 0.39 (B). What the building models add is clearest in the pattern, R 0.50 → 0.86 (A) and 0.51 → 0.73 (B), more than in q (+0.11 and +0.12).
2. **The flow topology is right.**
   - The sign of U agrees at 97 % of the points in both cases.
   - Every measured reverse-flow point in Case A is reversed in the model; in Case B, 87 % are.
   - **Wake length:**
     - Case B: 8.3 b against 7.6–7.85 b measured, closer than any published steady RANS (9.2–13.6 b).
     - Case A: 1.9 b against 1.3–1.4 b, inside the standard k-ε range (1.66–2.70 b) but 35–45 % too long, and longer still on finer grids.
   - **Horizontal flow direction:** within 30° at 97 % (A) and 76 % (B) of the near-floor and mid-height points.
3. **What it gets wrong** is the same in every setting tried:
   - **No roof separation:** Case A's roof flow is 3–4 times too fast just above the roof. Case B's roof deficit and reverse flow are missing (requested as R18).
   - **The corner speed-up** beside the Case B slab is overpredicted by about 0.2 U_H.
   - **Case A's wake** reverses nearly twice as strongly as measured (−0.25 against −0.14 U_H).
   - **Near-floor W** is too small.
   - **QES-Turb k** has no skill (R ≤ 0.27). It is about 5 times too high in the roof shear layer and non-realisable at 10–18 % of the probes (R19). In the D/E districts it was too low instead.
4. **Numerics and setup do not explain it.**
   - The iterations are 3–10 times what convergence needs.
   - Domain, top, inflow fit, vertical grid and roughness move the scores by 0.03 or less.
   - Pooled scores are grid-independent from 2 m.
   - Case B's probes converge by 0.5 m; Case A's do not quite (p95 0.074 from 1 to 0.5 m), and its wake keeps lengthening.
5. **The parameterization flags offer little.**
   - The best single changes are turning the upwind cavity off (q +0.03/+0.04) and the rooftop vortex (Case B R +0.11).
   - None restores the roof flow.
   - The high-rise model breaks the slab case.

**What this means.**
- **Cases A and B are the most favourable test for a Röckle-type model:** single, axis-aligned prisms normal to the wind, with like-for-like data. dtcc-qes passes it for the location and size of the recirculation zones, and for the tower's mean speed field.
- **The large deficits in Cases D and E therefore do not come from the single-building zones.** They come from what happens between buildings: the canopy background (R17) and the speed-up of a tall building within a district.
- **Two defects are common to both settings:** the missing roof separation and the corner speed-up.
- **The verdict in `AIJ_VALIDATION.md` stands:** a fast screening tool for mean-wind patterns, not decision-grade, and not a source for turbulence or gust estimates.

## Limitations

- **One direction per case, and two buildings.** The scores describe isolated, axis-aligned prisms normal to the wind. That is the most favourable situation for Röckle-type models.
- **Scale (D1).** Full scale was chosen to put the near-floor section at 2 m, and no second scale was run. dtcc-qes has few absolute lengths, but the claim of scale independence is not tested.
- **The Case B V sign (F5)** is an inference. It affects only the flow-direction score and the V profiles.
- **Wake lengths** are interpolated between stations 0.75 b (A) and 3 b (B) apart. Published values are quoted for context only.
- **Hit-rate tolerances:** the absolute tolerance W = 0.05 is that of the D/E framework. Near-zero points (reverse-flow edges) are scored on it, so q depends on how many such points a section has.
- **The k comparison** uses dtcc-qes's validity mask. Masked probes (non-realisable stress) are left out, not counted as misses, which flatters k slightly.

## Code map (A/B additions)

```
aij/case_ab.py      Case A/B geometry: one Building per case, size(), regions(), surface_distance()
aij/tables.py       + load_inflow_ab, load_results_ab (VectorResults), load_points_ab; full-scale b, sections
aij/conventions.py  + AB_LABEL "0 deg.", AB_DIRECTION 270°
aij/grids.py        + A/B bounds (padding upwind/laterally, downstream behind), layer_centre (faces on the roof)
aij/runspec.py      + cases A/B, FINE_TOP 64 m, AB_DOMAIN, RunSpec.downstream (a later field: D/E keys unchanged)
aij/runner.py       + A/B inputs, 3D wall distance, centreline speeds (record), section planes and centre plane (.npz)
aij/inflow.py       + FIT_HEIGHT for A/B (2 H)
aij/campaigns.py    + case_ab, ab_baseline, AB_SENSITIVITY; campaigns ab_smoke/ab_convergence/ab_baseline/ab_grid/ab_sensitivity
aij/compare.py      + isolated() comparisons, null_model, sign_scores, ab_reattachment, ab_angle_error,
                      ab_repeatability, LATERAL_SIGN (F5), LITERATURE (F6)
aij/report.py       + plot_vector_scatter, plot_vertical_profiles, plot_horizontal_profiles, plot_centre_plane
report_validation.py  + isolated_report, isolated_grid_report, isolated_sensitivity_report; --only de|ab
build_cities.py     + aij_a, aij_b
tests/test_case_ab.py  22 checks
```

## Sources

Bibliographic details as found by the web search; titles are left out where they were not checked.

- Meng, Y. & Hibi, K. (1998). *J. Wind Eng. (JAWE)* 76, 55–64. doi:10.5359/jawe.1998.76_55 (Case A experiment).
- Mochida, A. et al. (2002). *Wind & Structures* 5, 227–244 (Case A, k-ε variants and DSM).
- Shirasawa, T. et al. (2003). *AIJ J. Technol. Des.* 18, 169–174. doi:10.3130/aijt.9.169_2 (Case B: geometry, domain, X_F).
- Tominaga, Y. et al. (2004). *JAABE* 3, 63–70 (cross-comparison tables for A and B).
- Yoshie, R. et al. (2007). *JWEIA* 95, 1551 (AIJ cooperative project).
- Tominaga, Y. et al. (2008). *JWEIA* 96, 1749 (AIJ guidelines).
- Bernard, J. et al. (2023). *GMD* 16, 5703 (URock and QUIC-URB on AIJ A, B, C, E, G).
- The AIJ CFD guideline benchmark pages (2010 and 2024 snapshots), read through the Wayback Machine because aij.or.jp blocks automated fetches.

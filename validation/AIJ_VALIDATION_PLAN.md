# AIJ Cases D and E: validation framework plan (step 2)

Step 1 ([`AIJ_CITY_MODELS.md`](AIJ_CITY_MODELS.md)) turned the AIJ drawings into dtcc-core Cities. This step plans how to simulate them with dtcc-qes and compare the results with the wind-tunnel measurements.

**Status (2026-11-02): all phases (0–6) are done.** The results, summary, conclusions and limitations are in [`AIJ_VALIDATION.md`](AIJ_VALIDATION.md); the prioritised requests, with R17 filed in Phase 6, are in [`DTCC_REQUESTS.md`](DTCC_REQUESTS.md).
- **How the plan changed along the way:**
  - Phase 3 added an in-canopy inflow and the parameterisation flags (R15, then implemented) to Phase 5.
  - Phase 4 set Phase 5 at 2 m, with the main effects confirmed at 1 m.
- **The outcome of Phase 5:** tuning to Case E "before" carries over to Case E "after" but not to Case D, so the defaults stay the reference.
- **Tracking:** new dtcc-qes revisions are tracked with the procedure in `AIJ_VALIDATION.md`, "Tracking a new revision".

The plan is written against dtcc-qes main `f277a69`. That revision includes the whole of `COMBINED_FEATURE_PLAN.md` (Phases 0–9, commits `7176559` to `02dc4eb`):
- one profile object per run;
- `Solver(...)` with legacy, bounded and adaptive modes;
- `Turbulence | None`;
- `result.qualification`;
- `comfort.assess_results`;
- a re-qualified native build.

The rules from step 1 still apply:
- Write only inside `validation/`.
- Validation libraries go in the `validate` dependency group.
- Changes to dtcc-qes or dtcc-core are written as requests in [`DTCC_REQUESTS.md`](DTCC_REQUESTS.md). This plan adds R7–R13 there.

## Decisions (2026-11-01)

- **Characterise and track; no pass/fail gate.**
  - Metrics are reported against the VDI 3783-9 / COST 732 reference lines.
  - Every report is keyed by the dtcc-qes git revision and the native `solver_policy_revision`.
  - `AIJ_VALIDATION.md` keeps a short table of headline metrics per revision, so accuracy changes across versions stay visible.
- **Compute budget.** Run 4, 2 and 1 m on every direction and state. Run 0.5 m on a subset of directions, and only if memory allows.
- **Results storage.**
  - Runs and figures go in the gitignored `validation/output/`.
  - Key numbers and figures are summarised in `AIJ_VALIDATION.md`, as step 1 did in `AIJ_CITY_MODELS.md`.

## Findings that shape the framework

### From the dtcc-qes updates

- **F1. The run API.**

  ```python
  wind.run(city, profile, *, solver=Solver(), turbulence=None, footprints=None,
           resolution=2.0, bounds=None, vertical_grid=None,
           horizontal_padding=20.0, vertical_clearance=20.0, max_cells=20_000_000)
  ```

  (`src/dtcc_qes/wind.py:41-49`)
  - **Direction is meteorological:** the direction the wind comes from, in degrees clockwise from north, with x = east and y = north. The conversion is u = −S·sin φ, v = −S·cos φ (`profiles.py:62-64`).
  - **`speed=`/`direction=`** are keyword-only shorthands for a `LogProfile` at 10 m with z0 = 0.1.
  - **Measured tables go in directly:** `MeasuredProfile(heights, speeds, direction=, reference_height=, roughness_length=, below="error"|"log", above="constant", interpolation="log_height"|"linear")`. `PowerLawProfile` and `LogProfile` serve as sensitivity variants.
  - **A profile carries only horizontal u and v.** It cannot carry inflow turbulence intensity or k.
- **F2. Adaptive acceptance can never apply to the AIJ cases.**
  - The build is qualified again: `solver_policy_build_supported = True`, revision `b26d15fd…`, recorded in `docs/data/feature-merge/phase9.json`.
  - But `pedestrian-v1` only covers:
    - 4–32 axis-aligned rectangular buildings;
    - an 80×80×32 grid at 2 m;
    - log inflow at z_ref = 10 m with z0 = 0.1;
    - at most 16 receptors;
    - no turbulence (`pedestrian_policy.cpp:18-66`).
  - AIJ runs are therefore legacy or bounded, with `qualification["solver"]["assessment"] = "not_requested"`. **The framework has to produce its own convergence evidence.**
  - Bounded mode records per-receptor histories (`MonitorSpec(receptors=...)`, `monitor.cpp:312-323`), so the AIJ probes can serve as receptors.
- **F3. Sampling.**
  - `WindResult.sample(height, "nearest"|"linear")` returns a horizontal plane on the native cell centres, in the local frame (global = local + `result.origin`) (`result.py:303`). `"linear"` interpolates only vertically.
  - **There is no public sampler at an arbitrary (x, y, z).**
  - A value is NaN when any contributing cell is solid.
  - `result.speedup` divides by `profile.reference["speed"]`.
- **F4. Turbulence does not change the mean wind** (`tests/test_feature_combinations.py:35`).
  - Enabling it costs time and memory and adds `result.turbulence.stress` (xx, xy, xz, yy, yz, zz), from which k = ½·trace.
  - QES's own `tke` field is a scaled value, not ½·trace.
  - The friction velocity u\* comes from the solved field at z_ref = 3·H̄ (with z0 = 0.1·H̄ and d = 0.7·H̄), not from the inflow.
  - The status is `"screening"`.
- **F5. Numerical caveats that matter at the AIJ probes.**
  - **The vertical right-hand-side defect is fixed** (`docs/stage0-validation.md`; `src/qes_core/solver/solver.cpp:37-38` divides by dz).
  - **Near-wall sensitivity:** at points about 1 m from a wall, refining x/y from 1 m to 0.5 m changes K by 10–18 %. The cause is a discontinuity in the sidewall initialisation (`docs/near-wall-validation.md:71-133`). The closest Case E probe is 0.83 m from a wall.
  - **No extrapolation:** the repo warns against unexamined Richardson extrapolation (`docs/finest-reference.md:54`). Its grid budgets are pairwise: p95 |ΔK| < 0.05, and peak and critical points within 5 % (`tools/run_horizontal_sensitivity.py:82-110`).
- **F6. There is nothing to reuse for metrics.**
  - The repo has no validation metrics (hit rate, FAC2, NMSE and so on), no comparison with wind-tunnel data, and no arbitrary-point sampler.
  - Patterns worth copying (not importing, to keep `validation/` isolated):
    - `digest` and the atomic `write` in `tools/benchmark_urban_wind.py`;
    - `clean`, `write_json`, `fingerprint` and `changes` in `tools/run_turbulence_benchmark.py`.
  - **Cost reference:** 2 m urban grids of 3.6–6.3 M cells take about 4–7 s for 2,000 sweeps and 0.5–0.75 GiB RSS on 4 threads (`docs/final-solver-benchmark.md:26-40`). Memory is about 110 B per cell at 52 M cells (`docs/near-wall-validation.md:162-164`).
- **F7. Corrections to step 1.**
  - `AIJ_CITY_MODELS.md` said the build was unqualified (true at `889c629`, no longer) and that the wind directions were unknown (now resolved, see F8). Both notes are corrected there.
  - `docs/building-contacts.md:27` still calls `wind.run(city, 5.0, 270.0, ...)`, which now raises `TypeError` (request R13).

### From the measured data

Both XLS files were read with xlrd, including their drawing objects (pictures, text boxes, arrows). Cell references below are Excel A1.

- **F8. Wind directions.** This resolves step 1's open items.
  - **Case D.**
    - A glyph left of Fig. 2 shows three arrows: "0°" pointing to +x, and "22.5°" and "45°" rotated counter-clockwise, toward +y. An x→/y↑ axis glyph sits next to them.
    - The point labels in Fig. 2 fit the coordinate table with no mirroring.
    - The data agree: at 0°, U < 0 just upstream of the tower (points 8 and 9: −1.77 and −2.46 m/s).
    - The meteorological direction is therefore φ = (270 − θ) mod 360. **0°, 22.5° and 45° become 270°, 247.5° and 225°.**
  - **Case E.**
    - The "N" arrow next to the map points to +y, and the 80 point labels fit the table with X right and Y up.
    - The result columns run clockwise: N, NNE, …, NNW.
    - Hence **φ = 22.5°·i for N (i = 0) to NNW (i = 15)**.
    - The file does not say whether "N" means wind *from* the north. That is the meteorological convention, and Hågbo & Giljarhus (2022) use the same data with "wind from N (0°)". *Phase 1 confirmed it without the model:* of the eight rotations and senses of the labels, only this one makes sheltered points clearly slower in the "before" data (median ρ −0.47, against −0.12 at best for the others; `AIJ_VALIDATION.md`).
- **F9. Case D (`CaseD(Highrise+Blocks).xls`).**
  - **`Geometry&Points` B42:J67:** 78 points in three (No., x, y) column groups, in model mm with the origin at the tower centre. The full-scale factor is ×0.4 m and z = 5 mm (2 m). `aij.tables.load_points_d` already reads them.
  - **`Inflow` B4:G16:**
    - 13 rows of z, z/H, U, U/U_H, k and k/U_H², with z in model mm, U in m/s and k in m²/s².
    - H = 250 mm (100 m full scale). U_H = 6.65 m/s is stated in C17; the table interpolates to 6.63 m/s at 250 mm.
    - No exponent is stated. The local α rises from 0.14 near the ground to about 0.30 above H.
  - **`Results (Exp_S)` A4:M81: split-fibre probe, 0° only.**
    - Columns: U, u′², V, v′², W, w′², K = |(U, V, W)|, K/U_H and k = ½ Σ variances. The identities hold exactly.
    - **Only 33 of the 78 points are measured**, all with y > 0; the other rows hold only the id, with `''` in every cell.
  - **`Results (Exp_T)` A6:J83: thermistor scalar speed at 0°, 22.5° and 45°.**
    - E:G hold m/s and H:J the ratio to U_H; H:J = E:G / 6.65 exactly.
    - 12 central-plaza points are missing (`'-'`): 26–29, 32, 33, 36, 37 and 40–43.
    - **At 0°, all 33 mirror pairs (x, ±y) are identical**, so the y < 0 values were copied by symmetry and are not independent.
- **F10. Case E (`CaseE(Niigata).xls`).**
  - **`Inflow` B3:D14:** 12 rows of z/Z_R, U/U_R and k/U_R², with Z_R = 250 m (the boundary-layer height) and U_R = 7.8 m/s. The lowest point is at 1.25 m full scale. The local α is about 0.25 for z/Z_R between 0.05 and 0.4.
  - **`Results (Before Construction)` and `Results (After Construction)`, B4:R83:** 80 points × 16 directions, with no gaps.
    - The quantity is "velocity ratio at 2 m (velocity value normalised by the inflow velocity at 15.9 m)". 15.9 m is the height of the Niigata meteorological station.
    - Ranges: 0.099–0.714 before and 0.099–1.368 after.
  - **Every value is an integer multiple of 0.0198 (= 0.01/0.5045).**
    - The data were apparently U/U_R rounded to 0.01, then divided by U(15.9 m)/U_R ≈ 0.5045. This is an inference.
    - The measurement resolution is therefore about ±0.01 in K, which sets a floor for the absolute tolerance W.
  - The file does not name the instrument. Hågbo & Giljarhus (2022) describe multi-point thermistor anemometers at 2 m full scale, so these are scalar speeds.
- **F11. What is like for like.**
  - QES returns the mean *vector* speed |⟨u⟩|. A thermistor measures the mean *scalar* speed ⟨|u|⟩, which is larger wherever turbulence is high, mostly in wakes.
  - Case D at 0° has both at the same 33 points (Exp_S vector, Exp_T scalar), so the gap can be measured directly.
  - Case D Exp_S also gives the flow direction and k.

## Framework design

All code lives in `validation/`. Dependencies: dtcc-qes, dtcc-core, numpy, shapely, plus the `validate` group (xlrd, ezdxf, matplotlib). No pandas.

```
aij/
  tables.py        existing point readers + inflow and result readers
  conventions.py   AIJ direction -> meteorological degrees (F8); labels; states
  inflow.py        MeasuredProfile from the tables at full scale; PowerLaw/Log fits; reference speed
  grids.py         per-case horizontal bounds; vertical faces with a cell centred at 2 m
  sampling.py      probe sampling from a WindResult (interim, until R7)
  runspec.py       RunSpec dataclass -> canonical JSON -> sha256 key; campaign matrices
  runner.py        one spec: wind.run -> probe record (.json) + 2 m plane (.npz), with provenance
  metrics.py       hit rate, FAC2, FB, NMSE, R, Spearman, MAE, RMSE, bias; change metrics
  report.py        figures and metric tables
run_validation.py     --campaign smoke|convergence|baseline|... [--case D|E] [--force] [--list]
report_validation.py  -> output/report/{summary.json, tables.md, figures/*.png}
tests/  test_tables.py, test_conventions.py, test_inflow.py, test_sampling.py,
        test_metrics.py, test_runner_smoke.py
AIJ_VALIDATION.md     results and findings (started in Phase 1 and kept up to date)
```

### Readers (`aij/tables.py`)
- Missing cells are detected by cell type (`ctype != XL_CELL_NUMBER`), because there are two markers, `''` and `'-'`. Missing values become NaN.
- Each reader returns a `Measurements` record:
  - `case`, `state`, `quantity`, `instrument`;
  - `point_ids`, `xyz` (full-scale metres, measurement frame);
  - `labels` and `directions` (meteorological degrees from `conventions.py`);
  - `values[point, direction]`;
  - `reference` (height and speed of the normalisation).
- Case D quantities:
  - `vector_speed_ratio` (Exp_S, column L);
  - `scalar_speed_ratio` (Exp_T, H:J), with a `mirrored` mask for the copied 0° values;
  - `components` (U, V, W from Exp_S);
  - `k_ratio` (k/U_H², from Exp_S M divided by 6.65²).
- Case E quantity: `scalar_speed_ratio` for `before` and `after`.
- Inflow readers return heights at full scale, speeds and k.
  - Case D: z·0.4 m and U in m/s.
  - Case E: z/Z_R·250 m and U/U_R·7.8 m/s.

### Normalisation
- Each side is normalised by its own reference:
  - **Case D:** K = speed(2 m) / U_inflow(100 m).
  - **Case E:** K = speed(2 m) / U_inflow(15.9 m).
- On the model side, U_inflow is `profile.evaluate(z_ref)` of the inflow actually used, not the nominal value.
- Record the offsets:
  - Case D: the table gives 6.63 against the stated 6.65 (0.3 %).
  - Case E: at 15.9 m, log-height interpolation gives 0.509·U_R and linear interpolation 0.504·U_R. The 0.5045 factor inferred in F10 matches the linear value.
- QES is linear in the inflow speed (K agrees to about 2e-6 across speeds), so runs use the table's speeds as they are.

### Inflow (`aij/inflow.py`)
- **Baseline: `MeasuredProfile` built from the inflow table.**
  - Heights are scaled to full scale.
  - The lower tail is `below="log"`, with `roughness_length` fitted to the lowest 3–4 points.
  - `above="constant"` and `interpolation="log_height"`.
  - `reference_height` is 100 m (D) or 15.9 m (E).
- **Sensitivity variants:**
  - a `PowerLawProfile` fitted below 2·H (D) or below 100 m (E);
  - a `LogProfile` with z0 fitted.
- All non-log profiles are flagged experimental by dtcc-qes. That has no cost here, because adaptive acceptance is out of scope anyway (F2).

### Grids (`aij/grids.py`)
- **Horizontal bounds** are fixed per case and shared by every direction and by both Case E states, so "before" and "after" differ only by the three new buildings.
  - Case E: the site plate (−246, −250) to (254, 250).
  - Case D: the footprint box ± padding (20 m in the baseline). At 2 m the strict check gives 290×300 columns with origin (−300, −290).
- **Vertical grid:** faces from `VerticalGrid.from_faces`, built so that a cell centre lies exactly at 2 m. Then `sample(2.0)` reads one layer and needs no vertical interpolation.

  | Spacing | Faces | Centres |
  |---|---|---|
  | 4 m | 0, 4, … | 2, … |
  | 2 m | 0, 1, 3, 5, … | 0.5, 2, … |
  | 1 m | 0, 0.5, 1.5, 2.5, … | 0.25, 1, 2, … |
  | 0.5 m | 0, 0.25, 0.75, … | …, 2, … |

  - Spacing stays uniform up to 24 m (D) or 36 m (E), then grows by 1.15 per layer, up to 4 × the probe-layer thickness, until it reaches the top.
  - *Phase 2 change:* the plan had 1.2·H_max, which would keep Case D uniform up to its 100 m tower; at 1 m that is 42 M cells.
  - The top is H_max + `vertical_clearance` and must also cover the turbulence requirement.
  - Both Case E states use the "after" faces (H_max = 60 m).
  - A fully uniform grid is the control (Phase 5).
- **Footprints:**
  - Case D: strict (`footprints=None`); it has no contacts.
  - Case E: the exact Cities with `wind.Footprints(min_detail=0.1, exposed_faces=True, fallback="error")`.
- **Measured size at 1 m (Phase 2):** Case D 18.8 M cells, Case E 13.2 M. Both stay under the default `max_cells`.
  - Memory is about 165 B per cell without turbulence and roughly twice that with it.
  - At 0.5 m, about 90 M cells would need `max_cells` raised and roughly 15 GB without turbulence.

### Solver and turbulence
- **Solver (decided in Phase 2):** float32 legacy with fixed work: 1,000 iterations at 4 m, 2,000 at 2 m, 6,000 at 1 m and 24,000 at 0.5 m.
  - `tolerance=1.2e-7` lies below the float32 stall, so every run does exactly that work (`aij/campaigns.py`).
  - Bounded runs with `MonitorSpec(receptors=<the probes>)` and a large budget provide the convergence evidence.
- **Turbulence:** `Turbulence()` is on in every run up to 1 m and off at 0.5 m. Phase 2 measured about twice the memory and a small extra time. The mean wind is unchanged (F4), and it gives k and K_scalar_est at no extra solve. Phase 1 made K_scalar_est a primary comparison for the thermistor data (next section).

### Sampling (`aij/sampling.py`)
1. Sample the probes with `WindResult.sample_points(xyz, "linear", frame="global")` (dtcc-qes `fafa08b`, request R7). The exact 2 m layer makes this bilinear in the probe layer.
2. If one of the four contributing cells is solid, fall back to the nearest valid fluid centre within one cell, and flag the point (`method="nearest_fluid"`).
3. Record:
   - the sampling method and the sampled point;
   - the distance from the probe to the nearest wall, computed from the City footprints with shapely;
   - the minimum and maximum of K within a radius of max(1 m, dx), as a spatial tolerance;
   - k = ½·trace(stress) and K_scalar_est when turbulence is on.

### Runs (`aij/runspec.py`, `aij/runner.py`)
- **`RunSpec` fields:**
  - case and state;
  - city variant (`exact` or `qes_ready`);
  - direction label and degrees;
  - resolution and vertical-grid kind;
  - inflow kind and its parameters;
  - footprints δ, padding and clearance;
  - solver settings, turbulence and sampling.

  The spec serialises to canonical JSON, and its sha256 is the run key.
- **Campaign matrices** are defined in code (`baseline`, `convergence`, `grid`, `sensitivity`).
- **Each run record** (`output/runs/<case>/<key>.json`) holds:
  - the spec;
  - dtcc-qes version, git revision and dirty flag;
  - `versions.native_build` with `solver_policy_revision`;
  - the dtcc-core version;
  - sha256 of the `.dtcc` City and of the XLS;
  - `metadata["timings"]`, `diagnostics` and `qualification`;
  - the footprints and solids summaries, `vertical_grid`, the grid shape and the peak RSS;
  - per probe: u, v, w, speed, K, the validity and fallback flags, the wall distance, the neighbourhood minimum and maximum, k and K_scalar_est.

  The 2 m plane goes to a compressed `.npz` file for maps.
- **Resume (default):** a run is skipped when its key exists and the code fingerprint matches; `--force` reruns it. The fingerprint is the sha256 of the run modules (not `campaigns`, `report` or `metrics`), the dtcc_qes Python files and the extension.
- **Execution** is sequential in one process, with OpenMP threads for the solve.

### Metrics (`aij/metrics.py`)
Metrics are computed per direction, pooled per case and state, and per stratum. NaNs are excluded, and the counts are reported.
- **Hit rate q (VDI 3783-9 / COST 732 style):**
  - A point hits when |Ks − Ke| ≤ D·|Ke| or |Ks − Ke| ≤ W.
  - D = 0.25, with q ≥ 66 % drawn as a reference line, not a gate.
  - W is provisional at 0.05 and is reported over a sweep {0.02, 0.05, 0.08}, which keeps it at or above the Case E resolution (F10).
  - The guideline's own W for normalised speeds still has to be confirmed from VDI 3783-9 itself. A vendor case study cites W = 0.08 for case C5.
- **Other scores:** FAC2, fractional bias FB, NMSE, Pearson R, Spearman ρ (whether the windy spots are ranked correctly), MAE, RMSE and bias.
- **Case E change metrics (the planning question: what does the new tower change?):**
  - ΔK = K_after − K_before per point and direction, compared on R, MAE and sign agreement where |ΔKe| > 0.04 (twice the resolution);
  - the overlap of the 10 windiest points per direction.
- **Case D extras at the 33 Exp_S points:**
  - the angle error of the horizontal mean vector;
  - k/U_H² against the QES-Turb k.
- **Strata:**
  - wall distance (< 2, 2–5 and > 5 m);
  - Ke band (< 0.2, 0.2–0.6, > 0.6);
  - direction;
  - Case D measured vs mirrored points;
  - Case E points within 5 m of an elevated slab in plan (R2 is still open, and no probe lies beneath one).

### What is compared with what

| Model | Measured | Purpose |
|---|---|---|
| K_vec = \|⟨u⟩\|(2 m) / U_ref | Case D Exp_S | like for like (vector speed) |
| K_vec | Case D Exp_T, Case E | what the AIJ guidebook compares |
| K_scalar_est = √(\|⟨u⟩\|² + 2k) / U_ref | Case D Exp_T, Case E | primary for thermistor data; needs turbulence |
| k / U_ref² | Case D Exp_S k | tests the k that K_scalar_est relies on |
| Exp_T / Exp_S | — | the measured scalar-to-vector gap at 33 points, for context |

K_scalar_est was my proposal. Phase 1 tested it on the measured data alone:
- On the 33 Case D points with both instruments, √(|mean vector|² + 2k) from the split fibre matches the thermistor within ±25 % at 91 % of the points (Spearman 0.91).
- The mean vector alone matches at only 52 % (Spearman 0.70).

So every hit rate against thermistor data is reported next to its **instrument ceiling**: the score the measured mean vector itself gets against the thermistor. With dtcc-qes, K_scalar_est is only as good as QES-Turb's k, which the Exp_S k tests.

## Phases

### Phase 0: re-baseline step 1 on the new API
- Rebuild: `uv sync --frozen --inexact --group dev --group validate --reinstall-package dtcc-qes`.
- Run `uv run --group validate pytest validation/tests -q` and `build_cities.py`. `cityutil.qes_check` calls only the grid-only `preview_grid`, which is still valid.
- Record the dtcc-qes revision in `AIJ_CITY_MODELS.md`.

### Phase 1: data layer
- Write `tables.py` (inflow and result readers), `conventions.py` and `inflow.py`, with tests.
- Plot the measured K at the probes per direction, and the inflow tables with their power-law and log fits.
- **Case E direction check, independent of the model.** *Done; it changed during Phase 1.*
  - The first version expected lower speeds in the new tower's near wake (0.5–3 H downstream). It failed: the tower raises speeds around itself in almost every direction.
  - It was replaced by `conventions.mapping_check`, an upwind-blockage rank correlation over all eight label mappings on the "before" data. That confirms the meteorological mapping.
  - Case D uses the reverse flow in front of the tower and the 45° diagonal symmetry instead.
  - See `AIJ_VALIDATION.md`.

### Phase 2: run harness and numerics
*Done; results in `AIJ_VALIDATION.md`.*
- Wrote `grids.py`, `sampling.py`, `runspec.py`, `campaigns.py`, `runner.py`, `numerics.py`, `run_validation.py` and `report_validation.py`.
- **Smoke runs** at 8, 4 and 2 m, with turbulence on and off at 2 m. They decided:
  - R9 is dropped: preparation is a constant 4 s per Case E run;
  - turbulence stays on up to 1 m.
- **Iterative-convergence study:** Case D at 3 directions and Case E "after" at 4 directions, at 2 m and 1 m.
  - *Changed from the plan:* instead of separate legacy settings, one bounded float32 run per configuration recorded the probe speeds every 25 iterations. Its iterates equal a legacy solve exactly. A float64 run of the same length gave the end point.
  - The targets (p95 |ΔK| ≤ 0.005, max ≤ 0.02) are met after at most 450 iterations at 2 m and 1,675 at 1 m.
  - The fixed work chosen leaves about 1e-4 or less. The default `Solver()` is insufficient at 1 m (R14).

### Phase 3: baseline campaign at 2 m
*Done (2026-11-01); results and findings in `AIJ_VALIDATION.md`.*
- Case D: 3 directions. Case E: 16 directions × 2 states.
- Extend `metrics.py` and `report.py` (started in Phase 1), and write `report_validation.py`.
- Compare both K_vec and K_scalar_est. Report every hit rate against thermistor data with its instrument ceiling.
- Compare the QES-Turb k with the Case D split-fibre k at the 33 points.
- Fill the headline table in `AIJ_VALIDATION.md` for this revision.

### Phase 4: grid study (done)
- Run 4, 2 and 1 m on the full matrix. Run 0.5 m on a subset if memory allows: Case D at 0°, and Case E at the 4 directions with the largest after − before change.
- Report the probe changes per refinement with the repo's budgets (p95 |ΔK| < 0.05; points changing by more than 5 %), and how each metric moves with resolution.
- No Richardson extrapolation (F5).
- Report near-wall probes (< 2 m from a wall) separately, because of F5.

### Phase 5: sensitivity, then tuning (done)

**Design fixed on 2026-11-02, before any Phase 5 run.** Every run uses the Phase 3 base settings except for the one change named: 2 m, measured inflow, 2,000 iterations, `Turbulence()`, Case E with `Footprints(min_detail=0.1)`, and default `Parameterizations`. Phase 4 sets the resolution of the scores: a change of less than about 0.03 cannot be told apart from grid error.

**Part A, sensitivity on the base settings** (35 runs per variant, unless only one case applies):
- **Inflow:** power law; log law; measured with linear interpolation.
- **Case E geometry:**
  - Footprints δ = 0.5 m and 0.01 m.
  - The QES-ready "blocky" Cities.
  - The 32 elevated slabs filled down to the ground. This brackets R2: today they are ignored, the opposite extreme.
- **Domain:** Case D padding of 100 m instead of 20 m; top clearance 2·H_max instead of 20 m; a uniform vertical grid.
- **Turbulence:** a ground roughness of 0.05 m full scale for the QES-Turb wall model, against the 10⁻⁴–10⁻⁵ m of the tunnel tail fit.
- **Sampling:** nearest instead of linear, computed from the stored 2 m planes. It needs no runs.

**Part B, tuning to the AIJ data.** The user asked for it on 2026-11-02, as tuning for this case followed by a comparison.
- **Tuned settings:**
  - the `Parameterizations` codes and wall roughness (R15);
  - an **in-canopy inflow**. Below a blending height z_b, the approach profile is replaced by a shifted log law with urban roughness z0_u, U(z) = U_a(z_b)·ln(1 + z/z0_u)/ln(1 + z_b/z0_u), and it is unchanged above z_b. K stays normalised by the *approach* flow at the reference height.
  - Both canopy settings are multiples of the case's area-weighted mean building height H̄: z0_u = a·H̄ and z_b = b·H̄. That makes them transferable between cases.
- **Training set: Case E "before"**, 16 directions, 1,280 values.
- **Objective:** maximise the pooled hit rate q of K against the thermistor (D = 0.25, W = 0.05). Ties within 0.01 go to the higher Spearman ρ.
- **Search: greedy coordinate descent from the base.**
  - At each step, try every single change: each other code of each flag; wake off together with the models that need it; the wall roughness at 10⁻⁴, 10⁻² and 10⁻¹ m; and the canopy grid a ∈ {0.03, 0.1, 0.3} × b ∈ {3, 6, 10}, or no canopy.
  - Keep the best change only if it raises q by at least 0.01. Stop when nothing does.
- **Test sets, never used for the choice:**
  - Case E "after" (the same site with the new tower);
  - the Case E change scores (after − before);
  - Case D (another geometry and scale), both split fibre and thermistor.
- **Confirmation at 1 m:** the tuned and base settings are compared at 1 m too.
- **Reporting:** the base and tuned scores side by side, on the training and test sets, with the instrument ceiling. The defaults stay the reference configuration for the per-revision headline table.

### Phase 6: write-up (done)
- Bring `AIJ_VALIDATION.md` up to date with the results, figures and limitations.
- Update `DTCC_REQUESTS.md` with the evidence: near-wall bias (a candidate new request), the need for R2 at slab-adjacent probes, and R9–R11 where the phases above support them.

## Requests to dtcc-qes

Added to [`DTCC_REQUESTS.md`](DTCC_REQUESTS.md) as R7–R13. Python-only requests (R7–R10, R12, R13) do not change the native policy identity, so they are cheap to accept.

| # | Request | Priority |
|---|---|---|
| R7 | `WindResult.sample_points`: sample at arbitrary world points | high |
| R8 | A vertical-grid helper that centres a layer on a target height | medium |
| R9 | Multi-direction runs that share City and footprint preparation | medium, decided by Phase 2 |
| R10 | Scalar-speed (thermistor-equivalent) estimate on samples | decided by Phase 5 |
| R11 | Turbulence reference from the inflow instead of the morphometric 3·H̄ | low, native |
| R12 | Monitor histories without a time budget | low |
| R13 | Stale positional `wind.run` call in `docs/building-contacts.md:27` | trivial |

R2 (elevated obstacles) and R4 (grid-loss reporting) stay open. The near-wall sidewall discontinuity (F5) is filed as R16, with the Phase 4 evidence.

## Verification of the framework

- `uv run --group validate pytest validation/tests -q`:
  - **Readers:**
    - the Exp_S identities K = |(U, V, W)|, L = K/6.65 and M = ½ Σ variances;
    - the 33 measured Exp_S ids;
    - Exp_T H = E/6.65, with the 12 missing ids;
    - Case E 80 × 16 values, all multiples of 0.0198;
    - inflow knots reproduced at full scale.
  - **Conventions:** D 0°/22.5°/45° → 270°/247.5°/225°; E N → 0°, E → 90°, … in clockwise order.
  - **Metrics:** analytic cases. Perfect agreement gives q = 1, FAC2 = 1 and FB = 0; a uniform 30 % overestimate gives q = 0 with W = 0; the W sweep is monotone.
  - **Sampling:** bilinear interpolation is exact for a linear field, the frame offset is handled, a solid contributor triggers the fallback, and the 2 m layer is exact.
  - **Smoke run:** Case D, one direction, 8 m, a small iteration cap. The record is written, reloaded and given the same key.
- `run_validation.py --campaign baseline --case D` reruns nothing on a second call.
- `report_validation.py` regenerates `summary.json` byte for byte from the stored runs.

## Sources

- Hågbo, T.-O. and Giljarhus, K. E. T. (2022), Frontiers in Built Environment 8:858067: a comfort-map study on AIJ Case E. It gives the thermistors, 80 points, 16 directions and "wind from N (0°)". The title is not checked here. <https://www.frontiersin.org/articles/10.3389/fbuil.2022.858067>
- SimScale, AIJ Case E validation: velocities normalised by the inlet velocity at 15.9 m, power-law exponent 0.25. <https://www.simscale.com/blog/pedestrian-wind-comfort-validation/>
- COST 732 / VDI 3783-9 hit rate: D = 0.25, q ≥ 66 %. <https://etmm.ercoftac.org/downloads/pdfs/news-from-2009-and-past-years/spring-festival-2009/mbalczo.pdf>, <https://www.harmo.org/Conferences/Proceedings/_Cambridge/publishedSections/Pp031-035.pdf>
- W = 0.08 for case C5 (a vendor source, unverified against the guideline): <https://www.dlubal.com/en/downloads-and-information/examples-and-tutorials/verification-examples/009971>
- Tominaga, Y. et al. (2008), *AIJ guidelines for practical applications of CFD to pedestrian wind environment around buildings*, JWEIA 96, 1749–1761.

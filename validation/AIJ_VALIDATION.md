# AIJ Cases D and E: validation results (step 2)

This file records the results of validating dtcc-qes against the AIJ wind-tunnel data. The plan, its findings F1–F11 and the framework design are in [`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md). The City models come from step 1 ([`AIJ_CITY_MODELS.md`](AIJ_CITY_MODELS.md)).

**Status (2026-11-02, dtcc-qes main `c9e31e8`, dtcc-core `dev/qes-updates` `66c81a2`):** all phases (0–6) are done. The summary, the fitness for urban wind comfort studies, the conclusions and the limitations below draw on the phase sections that follow, which hold the evidence. New dtcc-qes revisions are tracked as described under "Tracking a new revision".

## Summary

**What was done.**
- **Model:** dtcc-qes (QES-Winds with QES-Turb) at the 2 m measurement height.
- **Cases:**
  - AIJ **Case D**: a 100 m tower in a regular array of 10 m blocks, 1:400, 3 directions.
  - AIJ **Case E**: the Niigata district before and after a new 60 m tower, 1:250, 16 directions × 2 states.
- **Measurements:** split fibre (mean vector and k) at 33 Case D points, and thermistors (scalar speed) at 66 Case D and 80 Case E points.
- **Runs:** one configuration is 35 runs. In all there were 1,799:
  - spacings of 4, 2 and 1 m, and a 0.5 m subset;
  - iterative-convergence checks;
  - 12 sensitivity variants;
  - a tuning search over the building parameterizations and an in-canopy inflow.
- **Scores:** each is reported against the VDI 3783-9 / COST 732 reference line, with the instrument ceiling next to it. There is no pass/fail gate; results are tracked per revision.

**Findings** (default settings, 2 m, unless stated):
1. **Agreement is well below the reference line.**
   - Hit rate q (D = 0.25, W = 0.05) is 0.16 (E before), 0.30 (E after), 0.27 (D split fibre, like for like) and 0.23 (D thermistor), against a reference of q ≥ 0.66. FAC2 is 0.56–0.72.
   - Part of the gap is the instrument: even an exact mean-vector model scores only 0.52 against the thermistors at the Case D points (Phase 1).
2. **The pattern is partly right.**
   - Rank correlation ρ is 0.40–0.54.
   - Per-direction Pearson R in Case E is 0.33–0.64 (before) and 0.19–0.69 (after), with medians of 0.57 and 0.48. That is below the 0.61–0.84 that Hågbo & Giljarhus (2022) report for steady RANS.
3. **In the dense low-rise district the level is wrong.**
   - Case E "before" is overpredicted: FB −0.43, mean K 0.51 against 0.33 measured.
   - Probes outside every building zone keep the approach-flow value (0.75 at 2 m), where the tunnel shows about 0.3.
   - The near-ground inflow is the strongest lever (Phases 3 and 5).
4. **The effect of the new tower is poorly reproduced.**
   - The tunnel shows mostly speed-ups (mean ΔK +0.10); dtcc-qes predicts a slight slowdown (−0.02).
   - Its sign is right for 73 % of the clear changes, and the top-10 overlap of the windiest points is 0.59.
   - No grid, setting or tuning changes this.
5. **The numerics do not explain the findings.**
   - The pooled scores stop depending on the grid at 1 m, and 2 m is within 0.03.
   - The iteration error at the probes is 1e-4 or less, and the setup choices move the scores by 0.014 or less (Phases 2, 4 and 5).
   - **Single probes near walls and at sharp features are grid-sensitive even at 0.5 m:** p95 |ΔK| 0.06–0.07, and the changes are not asymptotic. The local K range (span) flags them in one run (Phase 4).
6. **Turbulence (QES-Turb).** The level of k follows the ground roughness given to its wall model; its pattern is wrong (R ≈ 0). The thermistor-equivalent √(|U|²+2k) does not improve the agreement (Phases 3 and 5).
7. **Tuning works on the tuned case only** (Phase 5).
   - Tuning to Case E "before" (in-canopy inflow, wake models off) triples its q, 0.16 → 0.55. It carries over to Case E "after" (0.30 → 0.48).
   - It makes Case D worse: split fibre 0.27 → 0.21, thermistor 0.23 → 0.05.
   - It works by compressing the field to the measured level (regression slope 0.95 → 0.35), not by a better pattern. The defaults stay the reference.

**Verdict.**
- **What it does well:** dtcc-qes ranks the windy and sheltered spots of these districts moderately well, and it is fast (7 s per Case E direction at 2 m).
- **What it does badly:** it does not reproduce the measured speed levels in the dense low-rise district, nor the speed-up effect of a new tall building. Single receptors near walls depend on the grid.
- **So:** it is **not yet good enough for wind comfort studies that inform decisions**. It can serve as a fast screening tool (see the next section).
- **Comparisons with this data need care.** The tunnel's thermistors measure a different quantity, which bounds any mean-wind model.

## Fitness for urban wind comfort studies

**Bottom line (2026-11-02).** In this validation, dtcc-qes is **not yet accurate enough for wind comfort studies that inform decisions**: comfort classification, compliance with criteria such as NEN 8100, or choosing between design schemes. It is useful as a fast screening and communication tool, provided its output is treated as indicative and checked with a validated method before anyone relies on it.

**Why** (each point from the phases below):
1. **Accuracy is far below accepted practice.**
   - VDI 3783-9 and COST 732 expect q ≥ 0.66. dtcc-qes reaches 0.16–0.30 in Case E and 0.23–0.27 in Case D.
   - Part of the gap is the instrument: a perfect mean-wind model reaches about 0.52 against these thermistors.
   - The like-for-like split-fibre comparison is also low, at 0.27, with a median flow-direction error of 34° (Phases 1 and 3).
2. **Absolute speeds can be badly wrong, and comfort classes amplify the error.**
   - In the dense low-rise district, mean K at 2 m is about 55 % too high (0.51 against 0.33).
   - In wake and cavity zones the model drops close to zero where the tunnel measures moderate speeds (Phase 3).
   - Comfort classes depend on how often a threshold is exceeded, which is very sensitive to speed. As an illustration (not a result of this validation), take Weibull-distributed hourly speeds with shape 2:
     - speeds 25 % too high turn a 2.5 % exceedance of 5 m/s into 9.4 %;
     - speeds 50 % too high turn it into 19 %.
   - Under NEN 8100 that moves a location from the A/B boundary to class C or D.
3. **It missed the effect that planners usually commission a study for.**
   - The new 60 m tower made the pedestrian wind stronger around it (measured mean ΔK +0.10); dtcc-qes predicted a slight slowdown (−0.02).
   - Its sign is right for 73 % of the clear changes, but the net effect is wrong. No grid, setting or tuning changed that (Phases 3–5).
4. **The pattern is only moderately right.**
   - Rank correlation is 0.40–0.54.
   - Per direction, about 6 of the 10 windiest measured points are among the 10 windiest simulated ones (Case E "after").
   - Per-direction R in Case E is 0.19–0.69, against 0.61–0.84 reported for steady RANS of the same district (Hågbo & Giljarhus 2022). That study's setup was not checked here.
5. **Locations next to façades are the least reliable.** Entrances and pavements are often what a study is about. Within 2 m of a wall, values changed by a median 18 % between the 1 m and 0.5 m grids, without converging (Phase 4).
6. **No setting fixes this for a project.** Tuning to one state of the district tripled its hit rate, but made the other case clearly worse (Phase 5). A planner without measurements cannot calibrate dtcc-qes, and a calibration would not carry over to another site.
7. **Gust-based criteria are not supported.** The QES-Turb turbulence pattern does not correlate with the measured one (R ≈ 0), whatever its level (Phases 3 and 5).

**Where it is useful.**
- A 16-direction study at 2 m runs in a few minutes on one workstation.
- That makes it practical for exploring many early massing options, spotting likely corner streams and channelling, deciding where a detailed study is needed, and explaining wind behaviour qualitatively.
- Even then its output is a set of hypotheses. It can miss problems, as it missed the tower speed-up, as well as invent them.

**Recommendation to planners.**
- **Do not use it on its own** to classify comfort, demonstrate compliance or choose between schemes. This applies especially to buildings much taller than their surroundings and to dense low-rise fabric. Use a wind tunnel, or CFD validated to the relevant guidelines (AIJ, COST 732, NEN 8100).
- **For screening:**
  - use a grid of 2 m or finer, with the iterations set explicitly (see the settings below);
  - use mean-wind criteria only;
  - report the inflow profile;
  - flag or ignore single points near walls;
  - read patterns and relative differences, not absolute speeds;
  - never tune settings per project;
  - tell stakeholders plainly that the results are indicative.

**How firm this is.**
- **The evidence is limited:** two wind-tunnel cases (a Japanese low-rise district and a regular block array) at one height, with no field data and no European perimeter-block layouts. The thermistor data also penalise any mean-wind model.
- **A broader validation could shift the picture somewhat.** But the level error and the missed tower effect are large and did not move with grid, settings or tuning, so a reversal needs model changes.
- **Revisit the verdict when:**
  - a canopy-aware background (R17) passes its two-case acceptance test;
  - the QES-Turb turbulence improves (R11);
  - dtcc-qes has been validated on more building types, or compared side by side with RANS on the same metrics.

## Conclusions and recommendations

**Settings for anyone running dtcc-qes** (from this evidence; for whether to use it at all, see "Fitness for urban wind comfort studies"):
- **Grid:** 2 m is enough for pooled statistics of districts like these. 1 m changes scores by at most 0.03.
- **Iterations:** set them explicitly at 1 m and below, because the default `Solver()` stops at 1,000 (R14). The evidence gives 2,000 at 2 m, 6,000 at 1 m and 16,000 at 0.5 m.
- **Single receptors:** treat any receptor whose K varies by more than 0.15 within max(1 m, dx) as grid-sensitive. Its value can change by 0.12–0.19 under refinement (Phase 4).
- **Inflow:** report the inflow profile near the ground. It changes the scores more than any geometric option.
- **Instruments:** comparing mean-vector speeds with scalar-speed (omnidirectional) measurements is biased in sheltered spots.
- **Parameterization flags:** keep the defaults. The flags changed by tuning (Phase 5) are a calibration to one district and degrade the other case.

**For dtcc-qes development**, in priority order (details in [`DTCC_REQUESTS.md`](DTCC_REQUESTS.md)):
1. **R3 (high):** one LOD0 z convention between dtcc-core and dtcc-qes.
2. **R17 (medium, native):** a canopy-aware background inside built-up areas. It is the largest physical lever found, and its acceptance test is both cases without per-case tuning.
3. **R14 (medium):** a stopping rule, or resolution-aware iterations, at fine grids.
4. **R16 (medium, Python):** a neighbourhood range on samples, so that grid-sensitive receptors can be flagged.
5. **R11 (medium, native):** a separate QES-Turb ground roughness, or a turbulence reference from the inflow.
6. **R8 (medium):** a vertical-grid helper that centres a layer at the target height.
7. **Lower priority:** R4 (sub-cell gap reporting), R2 (elevated obstacles; ≤ 0.014 on the AIJ scores), R5 follow-up (non-conforming CAD solids, dtcc-core), and R12.
- **Not needed:** R10 is on hold and R9 was dropped. R1, R6, R7, R13 and R15 are done.

**For this validation:**
- **Tracking:** rerun the 2 m baseline for each dtcc-qes revision and add a headline block (see below). Commit the dtcc-qes change first, so the block is not marked `+dirty`.
- **When R17, R11 or R16 lands:** rerun Phase 5 (part A, and part B step 1). The tuning protocol in the plan can then test a new model against both cases.

## Limitations

- **Instruments.** All Case E values and the Case D thermistor values are scalar speeds; dtcc-qes gives mean vector speeds. The gap is measured at 33 Case D points only (ceiling 0.52). The √(|U|²+2k) correction needs a k that QES-Turb does not provide.
- **Measurements:**
  - Case E is quantised at ±0.01 in K.
  - At Case D 0°, the y < 0 thermistor values are mirrored copies. Scores on independent points only are in `comparisons.json`.
  - The Case D plaza points next to the tower have no data, so no measured point is closer than 5 m to a wall in Case D.
- **Normalisation.** Each side divides by its own approach flow at the reference height. Interpolating the inflow table adds ±0.3 % (D) and 1.1 % (E).
- **Directions.** The Case E direction mapping comes from the drawings and an upwind-blockage check (median ρ −0.47 against −0.12 or more for the alternatives). It was not stated in the data.
- **Geometry.**
  - The 32 elevated slabs of Case E are ignored; the filled bracket changes pooled scores by at most 0.014.
  - Buildings are stair-stepped prisms on flat ground.
  - 853 pairs of Case E footprints are closer than 4 m, and the grid decides whether those gaps open.
- **Numerics.**
  - Probes near walls are not grid-converged at 0.5 m.
  - There is no Richardson extrapolation, because the changes are not asymptotic.
  - Convergence is checked at the probes: float64 at 2 m and 1 m, and a self-converged float32 history at 0.5 m.
  - The adaptive `pedestrian-v1` policy does not apply to AIJ, so its numerical qualification was not available.
- **Scores.**
  - W = 0.05 is provisional; the VDI value was not checked against the guideline text. q varies by at most 0.04 for W in 0–0.08, except Case D split fibre (0.24 → 0.39 at 0.08).
  - q is coarse and rewards matching the level. FAC2, FB, R and ρ are reported next to it.
- **Tuning.**
  - It used one objective, a greedy search on a 3 × 3 canopy grid and the flag codes, and one training set (Case E "before").
  - A hold-out by direction was not tried.
  - The tuned settings are not a general calibration.
- **Scope.** There are only two cases, one height (2 m), wind-tunnel scale with Reynolds-number independence assumed, steady mean wind, and no gust validation.
- **Versions.** Phases 2–5 ran on dtcc-qes `fafa08b` with uncommitted changes, then committed as `c9e31e8`: the dtcc-core pin (`0c8a316`), the R13 fix and R15. The 2 m baseline rerun on `c9e31e8` is bit-identical. The native policy is `b26d15fd`. dtcc-core `66c81a2` is a development branch (`dev/qes-updates`), not a release.

## How to run

```sh
uv run --group validate python validation/build_cities.py        # step 1: Cities -> validation/output/*.dtcc
uv run --group validate python validation/plot_measurements.py   # Phase 1 -> validation/output/measurements/
uv run --group validate python validation/run_validation.py --campaign smoke        # Phase 2, ~1 min
uv run --group validate python validation/run_validation.py --campaign convergence  # Phase 2, ~30 min
uv run --group validate python validation/run_validation.py --campaign baseline     # Phase 3, ~5 min
uv run --group validate python validation/run_validation.py --campaign grid         # Phase 4, 4 m and 1 m, ~25 min
uv run --group validate python validation/run_validation.py --campaign fine_check   # Phase 4, 0.5 m iterations, ~15 min
uv run --group validate python validation/run_validation.py --campaign fine         # Phase 4, 0.5 m subset, ~70 min, 10 GiB
uv run --group validate python validation/run_validation.py --campaign sensitivity --jobs 6    # Phase 5 A, ~12 min
uv run --group validate python validation/run_validation.py --campaign tuning_screen --jobs 6  # Phase 5 B step 1, ~23 min
uv run --group validate python validation/tune_validation.py --jobs 6                          # Phase 5 B search + 1 m, ~47 min
uv run --group validate python validation/report_validation.py   # -> validation/output/report/
uv run --group validate pytest validation/tests -q               # 106 checks
```

- **Run files:** each run executes in its own process and writes `validation/output/runs/<case>/<key>.json`, plus a 2 m plane in `.npz`.
- **Run key:** the hash of every setting that can change the result (`aij.runspec.RunSpec`).
- **Skipping:** a run is skipped when its record exists with the same code fingerprint (the run modules and the dtcc_qes package); use `--force` to rerun it.
- **Listing:** `--list` shows a campaign. Campaign matrices live in `aij/campaigns.py`, outside the fingerprint, so adding one does not invalidate stored runs.
- **Parallel runs:** `--jobs N` runs N processes, with OMP_NUM_THREADS = cores // N. The results do not depend on the thread count.

### Tracking a new revision

After a dtcc-qes change (committed, so that the identity is not `+dirty`):

```sh
uv run --group validate python validation/run_validation.py --campaign baseline --jobs 6   # 35 runs, ~2 min
uv run --group validate python validation/report_validation.py                            # writes headline.md
uv run --group validate pytest validation/tests -q
```

- **New block:** copy `output/report/headline.md` into "Headline metrics" as a new dated block. The table carries the dtcc-qes revision and the native policy revision.
- **When the scores move by more than about 0.03:** rerun `--campaign grid` (1 m) to see whether the change survives refinement, and `--campaign sensitivity` if the change touches inflow or geometry handling.
- **Unchanged run modules:** stored runs of other campaigns remain readable; only their fingerprint marks them as older.

`plot_measurements.py` takes about 5 s and runs no solver. It writes:
- `measurements.json`: every number quoted in Phase 1 below;
- the figures listed at the end of Phase 1.

## Headline metrics per dtcc-qes revision

One block per dtcc-qes revision and native `solver_policy_revision`, written by `report_validation.py` to `output/report/headline.md`.
- **Scores:** q is the hit rate (D = 0.25, W = 0.05); FB > 0 means underprediction.
- **Settings:** 2 m, the measured inflow, 2,000 iterations, turbulence on, Footprints δ = 0.1 for Case E.
- **`+dirty`:** marks uncommitted changes in `src/`, `CMakeLists.txt` or `pyproject.toml`. In the 2026-11-01 block it was the dtcc-core switch to `dev/qes-updates` and then R15; both are committed in `c9e31e8`.

**2026-11-02, `c9e31e8`** (the dtcc-core pin, the R13 fix and R15 committed; all 35 runs rerun on `main`, every probe bit-identical to 2026-11-01):

| dtcc-qes | policy | Comparison | Model | n | q | FAC2 | R | ρ | FB |
|---|---|---|---|---|---|---|---|---|---|
| `c9e31e8` | `b26d15fd` | D-split_fibre | \|U\| | 33 | 0.27 | 0.61 | 0.55 | 0.40 | -0.23 |
| `c9e31e8` | `b26d15fd` | D-thermistor | \|U\| | 198 | 0.23 | 0.56 | 0.43 | 0.40 | +0.44 |
| `c9e31e8` | `b26d15fd` | D-thermistor | √(\|U\|²+2k) | 197 | 0.26 | 0.66 | 0.40 | 0.39 | +0.29 |
| `c9e31e8` | `b26d15fd` | E-before-thermistor | \|U\| | 1280 | 0.16 | 0.67 | 0.51 | 0.54 | -0.43 |
| `c9e31e8` | `b26d15fd` | E-before-thermistor | √(\|U\|²+2k) | 1277 | 0.08 | 0.51 | 0.32 | 0.35 | -0.66 |
| `c9e31e8` | `b26d15fd` | E-after-thermistor | \|U\| | 1280 | 0.30 | 0.72 | 0.46 | 0.46 | -0.15 |
| `c9e31e8` | `b26d15fd` | E-after-thermistor | √(\|U\|²+2k) | 1274 | 0.24 | 0.68 | 0.30 | 0.32 | -0.40 |

**2026-11-01** (uncommitted changes; the same numbers):

| dtcc-qes | policy | Comparison | Model | n | q | FAC2 | R | ρ | FB |
|---|---|---|---|---|---|---|---|---|---|
| `fafa08b+dirty` | `b26d15fd` | D-split_fibre | \|U\| | 33 | 0.27 | 0.61 | 0.55 | 0.40 | -0.23 |
| `fafa08b+dirty` | `b26d15fd` | D-thermistor | \|U\| | 198 | 0.23 | 0.56 | 0.43 | 0.40 | +0.44 |
| `fafa08b+dirty` | `b26d15fd` | D-thermistor | √(\|U\|²+2k) | 197 | 0.26 | 0.66 | 0.40 | 0.39 | +0.29 |
| `fafa08b+dirty` | `b26d15fd` | E-before-thermistor | \|U\| | 1280 | 0.16 | 0.67 | 0.51 | 0.54 | -0.43 |
| `fafa08b+dirty` | `b26d15fd` | E-before-thermistor | √(\|U\|²+2k) | 1277 | 0.08 | 0.51 | 0.32 | 0.35 | -0.66 |
| `fafa08b+dirty` | `b26d15fd` | E-after-thermistor | \|U\| | 1280 | 0.30 | 0.72 | 0.46 | 0.46 | -0.15 |
| `fafa08b+dirty` | `b26d15fd` | E-after-thermistor | √(\|U\|²+2k) | 1274 | 0.24 | 0.68 | 0.30 | 0.32 | -0.40 |

For context:
- **Instrument ceiling:** the measured split-fibre mean vector itself reaches only q = 0.52 against the thermistor (Case D 0°, 33 points).
- **RANS reference:** Hågbo & Giljarhus (2022) report a per-direction Pearson R of 0.61–0.84 for their steady RANS simulations of Case E. The construction state and turbulence model are not checked here.

## Phase 0: step 1 on the new API

- **Extension:** the installed dtcc-qes extension reports `solver_policy_revision = b26d15fd…`, the qualified revision in `pedestrian_qualification.h`, and `solver_policy_build_supported = True`. It was therefore built from the current native sources, and no reinstall was needed.
- **Tests:** the 23 step 1 checks pass on main `f277a69`.
- **Build:** `build_cities.py` regenerates `validation/output/summary.json` identical to the copy from `889c629`. `cityutil.qes_check` uses only the grid-only `preview_grid`, which the API change kept.

## Phase 1: the measured data

### Inflow profiles

| | Case D | Case E |
|---|---|---|
| Table points (full scale) | 13, from 2 to 480 m | 12, from 1.25 to 250 m |
| Reference height (normalisation) | 100 m (tower height H) | 15.9 m (station height) |
| Stated reference speed | U_H = 6.65 m/s | none; U_R = 7.8 m/s at Z_R = 250 m |
| Profile speed at the reference, log-height interpolation (baseline) | 6.667 m/s (+0.26 %) | 3.973 m/s = 0.509·U_R |
| Same, linear interpolation | 6.632 m/s (−0.27 %) | 3.929 m/s = 0.504·U_R |
| Tail roughness z0, shifted log fitted to the 4 lowest points | 3.5e-5 m (rms 0.018 m/s) | 1.4e-4 m (rms 0.011 m/s) |
| Power-law fit up to 200 m (D) or 100 m (E) | α = 0.154, rms 0.29 m/s | α = 0.181, rms 0.20 m/s |
| Log-law fit, same range | z0 = 0.038 m, rms 0.39 m/s | z0 = 0.061 m, rms 0.30 m/s |

![Inflow profiles and fits](output/measurements/inflow.png)

- **The table profiles fit neither a single power law nor a log law.**
  - In Case D the local exponent rises from 0.14 near the floor to about 0.30 above H.
  - In Case E it reaches the literature value of 0.25 only between about 12 and 100 m. The fit over the lowest 100 m gives 0.18.
  - The power-law and log variants therefore differ from the baseline in *shape*, by up to 0.4 m/s, not only in amplitude. That makes them a meaningful Phase 5 sensitivity.
- **The floor is nearly smooth near the ground.**
  - The fitted tail roughness is 10⁻⁴–10⁻⁵ m. It shapes the inflow only below the lowest table point (2 m in D, 1.25 m in E).
  - In native code, ground roughness otherwise reaches only the QES-Turb wall model (`TURBWallTerrain.cpp`). It is therefore a sensitivity parameter for the turbulence comparison, not for the mean wind.
- **Normalisation is self-consistent.** Each side divides by its own inflow speed at the reference height (plan, "Normalisation"). The ±0.3 % (D) and 1.1 % (E) interpolation offsets above bound the uncertainty this adds.

### Direction conventions

All three checks use the measurements alone, without the model.

**Case D: 0°, 22.5° and 45° are 270°, 247.5° and 225°.** Three pieces of evidence:
1. **The arrow glyph in the XLS** (plan F8).
2. **Reverse flow upstream of the tower.**
   - At 0°, points 8 and 9 sit 22.5 m west of the tower face. They have U = −1.77 and −2.46 m/s, the two strongest reverse flows of the 33 split-fibre points.
   - This is the standing vortex in front of a tall building. In a wake under the opposite flow, the near-ground flow would instead run toward the tower (U > 0).
3. **Diagonal symmetry at 45°.** The field is more symmetric about y = x (mean |Δ| = 0.186 between mirror points) than about y = −x (0.289). At 0° it is symmetric about the x-axis by construction (Δ = 0, the copied values).

The upwind-blockage check used for Case E (next) is inconclusive in Case D: the 100 m tower raises nearby speeds and confounds it. It is not used there.

**Case E: N, NNE, … are 0°, 22.5°, … clockwise, with "N" = wind *from* +y.**
- **The check.** `conventions.mapping_check` correlates the measured K with an *upwind blockage* index, for every rotation and sense of the 16 labels. The index is the largest building height ÷ distance on a 60 m ray from the probe toward where the wind comes from. Sheltered points should be slower.
- **The data.** It uses the "before" state.

| Label mapping (label i → φ) | Median Spearman ρ | Directions with ρ < 0 |
|---|---|---|
| **clockwise, N at 0° (meteorological)** | **−0.470** | **16 / 16** |
| clockwise, N at 180° ("blows toward") | −0.123 | 11 |
| counter-clockwise, N at 270° | −0.123 | 14 |
| the other five | −0.08 to +0.12 | 5–11 |

- **The meteorological reading stands out clearly.** It agrees with the XLS north arrow and with Hågbo & Giljarhus (2022).
- **The first attempt failed, and why matters.**
  - The first check looked for lower speeds in the new tower's near wake, 0.5–3 H downstream. Under the meteorological reading it gave a mean change of +0.058, not a negative one.
  - The new 60 m tower **raises** pedestrian-level speeds around itself in almost every direction. Of the 1,280 point-direction values, 634 rise and 229 fall by more than 0.04 (two quantisation steps).
  - The near-wake heuristic was therefore replaced by the blockage check. The finding matters for Phase 3: the Case E change is dominated by tall-building speed-ups (downwash and corner streams), not by sheltering.

### What the instruments measure

At Case D 0°, the split fibre (mean vector, with k) and the thermistor (mean scalar speed) measured the same 33 points.

| Estimate of the thermistor value from the split fibre | Median ratio to thermistor | Within ±25 % | Spearman ρ |
|---|---|---|---|
| \|mean vector\| / U_H | 0.765 | 52 % | 0.70 |
| √(\|mean vector\|² + 2k) / U_H | 0.950 | 91 % | 0.91 |

![Scalar-speed estimates](output/measurements/case_d_scalar_estimates.png)

- **The thermistor reads well above the mean vector speed in sheltered spots.** The ratio is 0.86–3.37 (median 1.31, mean 1.50), and up to three times the vector speed where the vector speed is below 0.3 U_H.
- **So comparing a mean-vector model with thermistor data penalises even a perfect model.** A model that reproduced the measured mean vector exactly would score only a 52 % hit rate (D = 0.25, W = 0) against the thermistor at these points.
  - The Case D thermistor data and all of the Case E data are thermistor measurements.
  - Phase 3 therefore reports this **instrument ceiling** next to every hit rate against them.
- **Adding the turbulence energy closes most of the gap.** √(|U|² + 2k), proposed in the plan as K_scalar_est, reaches 91 % within ±25 %. It is now supported by measured data, not only proposed, at least for wind-tunnel turbulence at these 33 points.
  - Whether it works with dtcc-qes depends on QES-Turb's k, which the Case D split-fibre k (0.008–0.084 U_H²) can test directly.

### The measured fields

- **Case D, split fibre (0°):** 33 points, |mean vector| / U_H from 0.086 to 0.715 (median 0.235).
- **Case D, thermistor:** 66 points per direction (12 plaza points missing; at 0° the 33 points with y < 0 are copies). Median Vs/U_H is 0.37 at 0°, 0.44 at 22.5° and 0.48 at 45°.
- **Case E:** 80 points × 16 directions, no gaps. Before: 0.099–0.714 (median 0.317). After: 0.099–1.368 (median 0.396).
  - 1,167 of the 1,280 values change between the states.
  - Every value is an exact multiple of 0.019820405, to a largest residual of 1.4e-14, so the measurement resolution is ±0.01 in K.

Figures in `validation/output/measurements/`:
- `case_d_thermistor.png` and `case_d_split_fibre.png`;
- `case_e_before.png`, `case_e_after.png` and `case_e_change.png` (16 maps each; the arrow shows the flow);
- `inflow.png` and `case_d_scalar_estimates.png`.

### Consequences for the plan

These changes are applied to [`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md):
1. **K_scalar_est** = √(|⟨u⟩|² + 2k) / U_ref becomes a primary comparison for thermistor data (Case D Exp_T, all of Case E), next to K_vec.
   - So `Turbulence()` should be on in the baseline unless Phase 2 finds it too expensive.
   - The Case D k comparison moves from Phase 5 to Phase 3.
2. **Every hit rate against thermistor data** is reported next to its instrument ceiling (52 % for the vector speed on the Case D points above).
3. **Case E direction check:** it is the upwind-blockage mapping check; the near-wake check is dropped.
4. **Request R10** (a scalar-speed estimate in dtcc-qes) is supported by measured data; it remains conditional on QES-Turb's k (Phase 3).

## Phase 2: run harness and numerics

### Setup used by every run
- **Domain:**
  - Case D: the footprint box ± 20 m (600 × 580 m).
  - Case E: the site plate (500 × 500 m), shared by both states.
- **Vertical faces** put a cell centre exactly at 2 m:
  - 0, 1, 3, … at 2 m; 0, 0.5, 1.5, … at 1 m (a thinner first layer, a 2:1 step at the ground).
  - Uniform up to 24 m (D) or 36 m (E), then growing by 1.15 per layer, up to 4 × the probe-layer thickness.
  - Top: the tallest roof + 20 m, so 120 m for D and 80 m for E. Both Case E states use the "after" faces.
  - Stretching keeps Case D at 1 m to 18.8 M cells, below the default `max_cells`; a uniform grid would need 42 M.
- **Probe sampling:** `WindResult.sample_points(..., "linear", frame="global")` (dtcc-qes `fafa08b`; request R7, done).
  - A probe whose interpolation touches a solid cell takes the nearest valid fluid centre within one cell instead, flagged `nearest_fluid`.

  | Spacing | Fallback probes, Case D | Fallback probes, Case E |
  |---|---|---|
  | 8 m | 12 | 32 |
  | 4 m | 4 | 7 |
  | 2 m | 0 | 1 |
  | 1 m | 0 | 0 |

  - Each record also keeps the minimum and maximum K within max(1 m, dx), as the spatial tolerance, and the wall distance.
- **Inflow:** the measured baseline profile (Phase 1).

### Cost

| Run | Cells | Wall time | Of which preparation | Peak memory |
|---|---|---|---|---|
| D, 4 m, 1,000 it | 0.4 M | 0.4 s | 0.0 s | 0.34 GiB |
| E, 4 m, 1,000 it | 0.2 M | 5.0 s | 4.1 s | 0.42 GiB |
| D, 2 m, 1,000 it, turbulence / none | 2.6 M | 1.9 / 1.1 s | 0.0 s | 0.93 / 0.44 GiB |
| E, 2 m, 1,000 it, turbulence / none | 1.8 M | 6.2 / 5.5 s | 4.1 s | 0.88 / 0.51 GiB |
| D, 1 m, 16,000 it, float32 / float64, no turbulence | 18.8 M | 86–95 / 127–130 s | 0.0 s | 2.4 / 2.1 GiB |
| E, 1 m, 16,000 it, float32 / float64, no turbulence | 13.2 M | 65–68 / 78–85 s | 4.0 s | 2.0 / 1.6 GiB |

- **Case E preparation is a constant 4.0–4.3 s.** About 3 s of it is dtcc-core footprint cleaning.
  - Over the whole plan (about 150 Case E runs) that adds roughly 10 minutes, so **R9 (shared preparation across directions) is dropped**.
- **Turbulence doubles the memory** (×2.1 for D and ×1.7 for E at 2 m) and adds about 0.8 s per 2.6 M cells. The mean wind is unchanged.
  - **It stays on in every run up to 1 m.**
  - At 0.5 m it is off. The estimate here was 15 GB without it and 30 GB with it for about 90 M cells; Phase 4 measured 6.8–9.9 GiB without it at 100–142 M cells.

### Iterative convergence at the probes

The campaign covers Case D at 0°, 22.5° and 45°, and Case E "after" at N, E, S and W, at 2 m and 1 m, in two runs each:
- a bounded float32 run of 8,000 or 16,000 iterations that records the probe speeds every 25 iterations;
- a float64 run of the same length, the reference end point.

The comparison uses the probes sampled linearly in both runs: 78 in D, and 79 (2 m) or 80 (1 m) in E.

| | Case D, 2 m | Case D, 1 m | Case E, 2 m | Case E, 1 m |
|---|---|---|---|---|
| Iterations until p95 \|ΔK\| ≤ 0.005 and max ≤ 0.02 (and stays) | 375–450 | 1,425–1,675 | 275–300 | 1,075–1,150 |
| p95 \|ΔK\| at 1,000 iterations (the dtcc-qes default) | 3–4e-4 | **0.009–0.013** | 2–3e-5 | **0.006–0.007** |
| p95 \|ΔK\| at 2,000 / 4,000 / 8,000 iterations | 1e-5 / 1e-5 / 1e-5 | 2.4–3.3e-3 / 3–4e-4 / 2e-5 | ≤ 1e-5 | 1e-3 / 5e-5 / 2e-5 |
| float32 against float64 at the end (max) | 6e-6 | 1.8e-5 | 8e-6 | 2.9e-5 |
| Max divergence at the end, float32 / float64 [s⁻¹] | 3.6–4.2e-5 / 4–6e-7 | 1.6–1.8e-4 / 1.0–1.1e-6 | 2.6–3.5e-5 / 3–4e-7 | 1.2–2.0e-4 / 0.8–1.3e-6 |

![Convergence at the probes](output/report/convergence.png)

- **K converges exponentially to a floor of about 1e-5.** That is float32 roundoff, and float64 agrees with it. **float32 is sufficient.**
- **About 4× the iterations per halving of the cell size.**
- **The multiplier-change criterion cannot confirm convergence.** In float32 it stalls at 0.8–1.5e-4, around the default tolerance of 1e-4, even after the probe K has stopped changing. The float32 divergence floor (about 1e-4 s⁻¹ at 1 m) does not affect the probes.
- **The default `Solver()` (1,000 iterations) is not enough at 1 m.** It leaves p95 errors of 0.006–0.013 in K, close to the Case E measurement step (0.02).
  - The run does report `converged=False` (λ change 6e-3 to 1.3e-2).
  - But raising `max_iterations` cannot make that flag reliable, because of the stall.
  - At 2 m, 1,000 iterations are ample.
  - This is a finding for dtcc-qes users, not only for this validation (`DTCC_REQUESTS.md`, R14).
- **Consistency checks, all exact (|ΔK| = 0):**
  - a legacy 1,000-iteration solve against the bounded history at 1,000 (monitoring changes nothing);
  - the native receptor values against `sample_points` at the last checkpoint.

**Chosen solver settings** (`aij/campaigns.py`): float32 with a fixed amount of work per resolution.

| Spacing | Iterations |
|---|---|
| 4 m | 1,000 |
| 2 m | 2,000 |
| 1 m | 6,000 |
| 0.5 m | 16,000 (set by the Phase 4 monitored check; the 4× rule gave 24,000) |

The tolerance (1.2e-7) lies below the float32 stall, so every run does exactly that work. The iteration error left at the probes is about 1e-4 in K or less, 1/200 of the Case E measurement step. A Case E baseline run at 1 m with turbulence should take about 35 s and 4 GiB. The full 1 m matrix (35 runs) takes about 20 min.

**Record note.** The convergence records carry an older code fingerprint. After they ran, the campaign matrices moved from `runspec.py` to `campaigns.py`; no `RunSpec` field or default changed, so their keys and results stand.
- `report_validation.py` reads them as they are.
- `run_validation.py --campaign convergence` would rerun them (about 30 min).
- The smoke runs were redone under the current fingerprint.

## Phase 3: baseline comparison at 2 m

**Setup.** 35 runs: Case D at 3 directions, and Case E at 16 directions × 2 states.
- Grid: 2 m with the stretched faces; float32 with 2,000 iterations; `Turbulence()` on.
- Inflow: the measured profile.
- Case E: the exact City with `Footprints(min_detail=0.1)`.
- Versions: dtcc-qes `fafa08b`, native policy revision `b26d15fd`, dtcc-core `66c81a2`.
- Model flags: the defaults, recorded per run (`rooftop 1, upwind cavity 2, street canyon 1, wake 2, high rise 0, sidewall 1`).
- Outputs: `output/report/comparisons.json` and the figures listed below.

### Findings

1. **dtcc-qes gets the pattern partly right but the level wrong in Case E.**
   - Rank correlation with the measured points is ρ = 0.54 (before) and 0.46 (after); Pearson R is 0.51 and 0.46.
   - Case E "before" is overpredicted on average: mean K 0.51 against 0.33 measured, FB −0.43, hit rate 0.16.
   - Per direction the hit rate is 0.05–0.24 before and 0.11–0.45 after.
   - The distribution shows why (`distributions.png`):
     - The simulated K piles up just below the approach-flow speed at 2 m (0.75 of the 15.9 m reference) and almost never exceeds it.
     - The measured K peaks at about 0.25.
     - Probes outside every building parameterisation keep the undisturbed approach profile, which initialises the whole domain. The in-canopy slowing of a dense low-rise district is not represented.
     - Where a wake or cavity zone applies, speeds instead drop close to zero.
2. **The effect of the new buildings is poorly reproduced** (`case_e_change.png`).
   - The tunnel shows mostly speed-ups: mean ΔK +0.10, and 634 of the 863 clear changes are increases.
   - dtcc-qes predicts on average a slight decrease (−0.02). It has a cluster of strong wake reductions (−0.3 to −0.7) where the tunnel saw no change or an increase.
   - Change scores: R 0.41, ρ 0.52; sign agreement 0.73 on the clear changes; top-10 overlap of the windiest points 0.59.
   - The better "after" score (q 0.30) is partly coincidental: the measured level rose while the simulated level fell.
3. **Case D, like for like (split fibre, mean vector, 0°, 33 points):** q = 0.27, FAC2 0.61, R 0.55, FB −0.23.
   - The overprediction is concentrated at the sheltered points (K < 0.2: bias +0.16, q 0.08).
   - The simulated flow direction differs from the measured one by a median of 34°; 45 % of points are within 30°.
4. **Against the thermistor in Case D, the model underpredicts** (FB +0.44). This is consistent with the instrument gap from Phase 1: the scalar speed exceeds the mean vector speed.
5. **QES-Turb's k is about 4× too low.**
   - At the 33 split-fibre points, mean k/U² is 0.0062 against 0.024 measured, with R = 0.09 and FAC2 0.15.
   - So √(|U|² + 2k) cannot close the instrument gap. It helps a little in Case D (q 0.23 → 0.26, FB +0.44 → +0.29), and in Case E it adds to an existing overprediction (q 0.16 → 0.08).
   - The turbulence model, not the estimator, is the limit. The estimator itself reaches 91 % on measured k (Phase 1).
   - **Corrected in Phase 5 (part A, finding 4):** most of the low k level comes from the ground roughness the profile passes to the QES-Turb wall model (the tunnel tail fit, 10⁻⁴–10⁻⁵ m). With z0 = 0.05 m the level is close, but the pattern stays wrong (R ≈ 0).
6. **Strata.**
   - Near-wall probes (< 2 m, 5 Case E points) do no worse than the rest: q 0.28 both before and after.
   - Probes within 5 m of an elevated slab: q 0.23 before and 0.26 after, against 0.15 and 0.30 in the open. Ignoring the slabs (R2) is not visible at 2 m in these data.
   - The mirrored Case D thermistor copies score a little better than the independent points (q 0.30 against 0.21). Independent-only scores are recorded as `independent`.
   - All measured Case D points are at least 5 m from a wall; the near-tower plaza points have no data.
7. **The high-rise parameterisation is not the explanation.**
   - In a scratch experiment, `high_rise_flag = 1` (off by default and not exposed in the API) was set by patching `ModelSettings` for Case E at N, E, S and W in both states.
   - It changed individual probes by up to 0.39 (W after) but left the scores almost unchanged: q 0.14 → 0.15 before and 0.28 → 0.29 after; change R 0.45 → 0.51; sign agreement 0.77 → 0.75.
   - In Case D the flag changes K by p95 0.09–0.16, so it belongs in the Phase 5 sensitivity. That needs the flags exposed (`DTCC_REQUESTS.md`, R15; done 2026-11-02, now `RunSpec.parameterizations`).

### Figures (`output/report/`)
- `headline.md` and `comparisons.json`: pooled, per-direction and per-stratum scores, change scores, the instrument ceiling and the split-fibre extras.
- `case_d_scatter.png` and `case_e_scatter.png`: simulated against measured K, coloured by wall distance, with the 1:1 and ±25 % lines.
- `distributions.png`: measured and simulated K, with the approach flow at 2 m.
- `case_e_hit_rate.png`: hit rate per direction and state, with the instrument ceiling.
- `case_e_change.png`: the effect of the new buildings.
- `case_e_after_error.png` and `case_d_error.png`: simulated − measured maps.
- `case_d_split_fibre.png`: k and the flow-direction error.

### Consequences for Phases 4–6
- **Phase 4 (grid study)** goes ahead. Findings 1 and 2 look structural rather than numerical, and Phase 4 will show whether 1 m changes them. (It does not; see Phase 4.)
- **Phase 5 priorities follow from the findings:**
  - **An in-canopy inflow:** transfer the approach flow at a blending height to an urban log profile (z0, d from the morphometry) with `comfort.log_law_transfer`, still normalised by the approach flow at 15.9 m. This tests finding 1.
  - **The parameterisation flags** (R15, done 2026-11-02: `RunSpec(parameterizations=dict(high_rise=1))`).
  - **The QES-ready "blocky" Cities** and Footprints δ = 0.01, now possible after R6.
  - **The QES-Turb ground roughness** for finding 5.
- **Requests:** R10 (scalar estimate) waits on a better k (R11); R15 is new; R3 is now high (see the dtcc-core section below).

### Changes made with the new dtcc-core (2026-11-01)
dtcc-qes now pins dtcc-core `dev/qes-updates` (`66c81a2`). Using it in the validation:
- **Every Building is built by `builder.building_from_footprint`** (dtcc-core convention, LOD0 at the roof).
  - dtcc-qes still reads LOD0 z as the base (R3), so Cities reach dtcc-qes through `cityutil.qes_city`, which moves LOD0 to `ground_height`.
  - A pinned test (`test_dtcc_qes_still_reads_lod0_as_the_base`) flags when that adapter can go.
- **Case D is decomposed by `builder.footprints_from_lod1`:** all 83 boxes, exact volume.
- **Case E keeps `aij/prisms.py`.** `footprints_from_lod1` rejects 33 of its non-conforming CAD solids, including all 27 stepped ones.
  - A test checks that both agree exactly on the other 497 solids, and pins the 33 (R5 follow-up).
- **R6 is fixed:** Footprints δ = 0.01 now cleans the exact Case E City.
- **Results are unchanged:**
  - `summary.json` is regenerated identically (to 1e-9).
  - The 29 baseline runs completed before the refactor give identical probe K afterwards (max |ΔK| = 0).
  - The attribute `merged_from` became `merged_parts`, because dtcc-core reserves `merged_from` for cleaned blocks.

## Phase 4: grid study

**Setup.**
- **Full matrix at 4, 2 and 1 m:** the 35 Phase 3 runs (Case D at 3 directions, Case E at 16 directions × 2 states) at each spacing, with the Phase 3 settings. The 2 m runs are the Phase 3 baseline.
- **0.5 m subset (9 runs):** Case D at 0°, and Case E at SW, SSW, E and WSW in both states. These are the four directions whose measured K changes most between the states (mean |ΔK| 0.17–0.22).
  - Turbulence is off at 0.5 m. It leaves the mean wind unchanged (F4), so K compares directly with the 1 m runs. K_scalar is not compared at 0.5 m.
- **Solver work:** float32 with 1,000, 2,000, 6,000 and 16,000 iterations at 4, 2, 1 and 0.5 m. The 0.5 m value comes from the check below.
- **Vertical faces:** the Phase 2 rule. At 0.5 m the probe layer spans 1.75–2.25 m.
- **Budgets:** the repo's pairwise budgets (`docs/joint-grid-verification.md`).
  - p95 |ΔK| < 0.05.
  - A probe value "changes" when |ΔK| exceeds 5 % of K, or 0.05 where K < 0.1.
  - No Richardson extrapolation.
- **Outputs:** `output/report/grid.json`, `grid_scores.png`, `grid_scores_subset.png` and `grid_refinement.png`.

**Cost** (per run; turbulence on except at 0.5 m):

| Spacing | Cells, D / E | Wall time, D / E | Peak memory, D / E | Campaign |
|---|---|---|---|---|
| 4 m | 0.4 / 0.2 M | 0.7 / 4.7–5.2 s | 0.33 / 0.39–0.44 GiB | 35 runs, 3 min |
| 2 m | 2.6 / 1.8 M | 3.1 / 6.8–7.2 s | 0.93 / 0.81–0.89 GiB | 35 runs, 4 min |
| 1 m | 18.8 / 13.2 M | 37 / 31–34 s | 5.2 / 3.8–3.9 GiB | 35 runs, 19 min |
| 0.5 m | 142 / 100 M | 642 / 440–459 s | 9.9 / 6.8–8.5 GiB | 9 runs, 70 min |

At 0.5 m the solver used 70–90 bytes per cell, about half the Phase 2 estimate. The full matrix at 0.5 m (35 runs, about 4.5 h) would therefore fit in memory if it is ever needed.

**Iterations at 0.5 m.** A monitored Case E "after" SW run (100 M cells, 32,000 iterations, 904 s, 7.4 GiB) recorded the probes every 100 iterations.
- **Target:** against its own end point, the probes reach p95 |ΔK| ≤ 0.005 and max ≤ 0.02 at 4,500 iterations. That fits the "4× per halving" trend from Phase 2 (1,075–1,675 at 1 m).
- **Remaining error:** p95 |ΔK| is 2.2e-3 at 6,000 iterations and 1.4e-4 at 12,000. The probes stay within 1e-4 of the end point from 13,200 iterations on, so 16,000 iterations are used.
- **Not checked:** float64 was not run at 0.5 m. Phase 2 found float32 within 3e-5 of float64 at 1 m.

### Probe changes per refinement

All probe values present at both spacings. The 1 → 0.5 m rows cover the subset only.

| Refinement | Case | Probe values | p95 \|ΔK\| | Max \|ΔK\| | Changed | Mean shift |
|---|---|---|---|---|---|---|
| 4 → 2 m | D | 234 | 0.108 | 0.16 | 55 % | +0.005 |
| 4 → 2 m | E before / after | 1,280 each | 0.193 / 0.198 | 0.46 | 59 / 64 % | +0.03 |
| 2 → 1 m | D | 234 | **0.033** | 0.08 | 22 % | +0.002 |
| 2 → 1 m | E before / after | 1,280 each | 0.137 / 0.143 | 0.71 / 0.70 | 37 / 43 % | +0.01 |
| 1 → 0.5 m | D (0°) | 78 | **0.014** | 0.02 | 5 % | −0.001 |
| 1 → 0.5 m | E before / after (4 directions) | 320 each | 0.058 / 0.072 | 0.20 / 0.41 | 17 / 19 % | −0.002 |

Case E by wall distance. Each cell gives p95 |ΔK| and, in brackets, the share of values that change; "before / after" where the states differ.

| Refinement | < 2 m (5 points) | 2–5 m | > 5 m |
|---|---|---|---|
| 4 → 2 m | 0.37 / 0.36 (85–88 %) | 0.21 (76–77 %) | 0.13 / 0.12 (38–48 %) |
| 2 → 1 m | 0.29 / 0.28 (79–82 %) | 0.15 (47–53 %) | 0.05 / 0.06 (22–27 %) |
| 1 → 0.5 m | 0.14 / 0.13 (65–75 %) | 0.05 / 0.06 (24 %) | 0.02 (4–7 %) |

Case E by the *span* on the coarser grid. The span is the K range within max(1 m, dx) of the probe, stored in every record since Phase 2. Same layout as above.

| Refinement | span < 0.05 | 0.05–0.15 | > 0.15 |
|---|---|---|---|
| 2 → 1 m | 0.028 / 0.035 (5–9 %; 355 / 224 values) | 0.07 (28–30 %) | 0.19 / 0.18 (61–62 %) |
| 1 → 0.5 m | 0.016 / 0.014 (2 %; 169 / 130 values) | 0.04 / 0.03 (12–20 %) | 0.12 / 0.13 (44–47 %) |

At 4 m the neighbourhood radius is 4 m, and the span does not separate the probes: values with span < 0.05 still change by p95 0.23–0.33 on the way to 2 m.

![Probe K under grid refinement](output/report/grid_refinement.png)

**Findings on the probes.**
1. **Case D converges; Case E does not, probe by probe.**
   - Case D is within the budget from 2 → 1 m (p95 0.033) and reaches 0.014 at 1 → 0.5 m.
   - Case E roughly halves its p95 change with each refinement but is still above the budget at 1 → 0.5 m (0.058–0.072), with 17–19 % of values changing.
2. **The remaining changes sit near walls and at sharp features.**
   - From 1 to 0.5 m, the 5 Case E points within 2 m of a wall change by a median 18 %. `docs/near-wall-validation.md` measured the same 10–18 % for the sidewall initialisation at about 1 m from a wall.
   - Probes more than 5 m from a wall change by p95 0.02.
3. **One run can flag its grid-sensitive probes.**
   - Probes whose span is below 0.05 change by at most p95 0.035 from 2 m and 0.016 from 1 m, within the budget.
   - Probes whose span exceeds 0.15 change by 0.12–0.19.
   - The span is now a stratum in `comparisons.json` and `grid.json`.
4. **The changes are not asymptotic.**
   - 118 Case E values still change by more than 0.02 from 1 to 0.5 m. Only 58 % of them move in the same direction as from 2 to 1 m, and the median ratio of the two changes is 0.95. The 4 → 2 → 1 m figures are 56 % and 0.87.
   - The p95 falls because fewer probes change, not because each probe settles. A probe on a sharp feature jumps when the feature moves by a cell: point 25 of E "after" WSW, 10 m from a wall, has K = 0.40, 0.12 and 0.53 at 2, 1 and 0.5 m.
   - This fits the cell-snapped edges of the building-parameterisation zones (`docs/near-wall-validation.md` documents one, in the sidewall zone), but it was not traced zone by zone.
   - Richardson extrapolation would be meaningless here, as the repo warns.
5. **The geometry itself changes near walls.**
   - The exact Case E "after" City has 853, 528, 223 and 122 pairs of separate footprints closer than 4, 2, 1 and 0.5 m. Case D has none.
   - A gap narrower than a cell can close on the grid, so each refinement opens passages the coarser grid closed.
   - Nearest-fluid fallbacks over the whole matrix are 12 (D) and 224 (E) probe values at 4 m, 32 (E) at 2 m, and none at 1 or 0.5 m.

### Scores against resolution

Full matrix (q / FB / R):

| Comparison | 4 m | 2 m (Phase 3) | 1 m |
|---|---|---|---|
| D split fibre, 33 | 0.33 / −0.22 / 0.54 | 0.27 / −0.23 / 0.55 | 0.30 / −0.23 / 0.55 |
| D thermistor \|U\|, 198 | 0.22 / +0.45 / 0.43 | 0.23 / +0.44 / 0.43 | 0.24 / +0.43 / 0.43 |
| E before \|U\|, 1,280 | 0.20 / −0.36 / 0.54 | 0.16 / −0.43 / 0.51 | 0.15 / −0.45 / 0.50 |
| E after \|U\|, 1,280 | 0.34 / −0.07 / 0.50 | 0.30 / −0.15 / 0.46 | 0.28 / −0.17 / 0.44 |
| E change: R / sign agreement / top-10 overlap | 0.40 / 0.72 / 0.56 | 0.41 / 0.73 / 0.59 | 0.38 / 0.73 / 0.58 |

The 0.5 m subset (q / FB / R):

| Comparison | 4 m | 2 m | 1 m | 0.5 m |
|---|---|---|---|---|
| D split fibre, 33 | 0.33 / −0.22 / 0.54 | 0.27 / −0.23 / 0.55 | 0.30 / −0.23 / 0.55 | 0.30 / −0.22 / 0.55 |
| D thermistor at 0°, 66 | 0.30 / +0.07 / 0.62 | 0.30 / +0.07 / 0.65 | 0.33 / +0.07 / 0.65 | 0.30 / +0.07 / 0.65 |
| E before, 4 directions, 320 | 0.20 / −0.37 / 0.52 | 0.12 / −0.44 / 0.48 | 0.13 / −0.46 / 0.47 | 0.13 / −0.46 / 0.47 |
| E after, 4 directions, 320 | 0.38 / −0.02 / 0.55 | 0.34 / −0.10 / 0.49 | 0.33 / −0.11 / 0.48 | 0.34 / −0.11 / 0.48 |
| E change: R / sign agreement / top-10 overlap | 0.43 / 0.71 / 0.70 | 0.42 / 0.70 / 0.70 | 0.40 / 0.70 / 0.70 | 0.40 / 0.70 / 0.68 |

![Scores against grid spacing, 0.5 m subset](output/report/grid_scores_subset.png)

The y-axes of `grid_scores.png` and `grid_scores_subset.png` are scaled to the data, so differences of 0.01 look large; read the numbers from the tables above.

**Findings on the scores.**
1. **The pooled scores stop depending on the grid at 1 m, and 2 m is within 0.03 of them.**
   - From 1 to 0.5 m, q moves by at most 0.03 (2 of 66 points), FB by at most 0.01 and R by at most 0.01.
   - From 2 to 1 m, q moves by at most 0.03, FB by 0.02 and R by 0.03. Spearman ρ moves by at most 0.02 from 2 m on.
2. **4 m flatters Case E.** It gives q 0.20 and FB −0.36 "before", against 0.15 and −0.45 at 1 m. That is too coarse for these probes: 224 fallback values, and p95 changes of 0.19 on the way to 2 m.
3. **So the Phase 3 findings are structural, not numerical.**
   - The overprediction of Case E is strongest at the probes the grid has settled. At 1 m, the 615 "before" values with span < 0.05 score q 0.07 and FB −0.53. The other two span classes score q 0.22–0.24 and FB −0.30 to −0.38.
   - The settled probes are mostly the fast, near-undisturbed ones: mean simulated K 0.65 against 0.38 measured, and 81 % above 0.6, where the approach flow is 0.75. This is the pile-up of Phase 3, finding 1.
   - The probes that the grid has not settled score no worse than the rest.
   - The missed effect of the new buildings (Phase 3, finding 2) is the same at every spacing: sign agreement 0.70–0.73, R 0.38–0.43.

### Consequences
- **Phase 5 runs at 2 m.**
  - A Case E run takes 7 s there, and its pooled scores are within 0.03 of 1 m.
  - A sensitivity whose effect on the scores is below about 0.03 cannot be told apart from grid error.
  - The main sensitivities are confirmed at 1 m.
- **Per-probe results need the span next to them.**
  - Maps and point comparisons should mark or drop probes with span > 0.15.
  - Scores are now also reported per span class.
  - This matters beyond AIJ: a comfort receptor near a wall can change class between grids.
- **Requests:**
  - **R16 (new):** grid-sensitive receptors, with a neighbourhood range on samples (Python) and smoother zone edges (native).
  - **R4:** Phase 4 evidence for reporting sub-cell gaps.
  - **R14:** the 0.5 m iteration count.

## Phase 5: sensitivity, then tuning to the AIJ data

The design was fixed in [`AIJ_VALIDATION_PLAN.md`](AIJ_VALIDATION_PLAN.md) (Phase 5) before the first run.
- **Base:** every variant changes one setting from the Phase 3 base. That base is 2 m, the measured inflow, 2,000 iterations, `Turbulence()`, Case E Footprints δ = 0.1, and default `Parameterizations`.
- **Base check:** the base was rerun on the Phase 5 code, and it reproduces Phase 3 bit for bit.
- **Scale:** 1,111 runs for part A and the first tuning step (all 35 runs per candidate), 480 new runs for tuning steps 2–3 (Case E "before" only), and 89 new confirmation runs at 2 m and 1 m.
- **Parallel runs:** `run_validation.py --jobs 6` runs 6 processes with 2 threads each. A Case E and a Case D run gave bit-identical probes with 3 threads and with the default team.
- **Reading the scores:** Phase 4 sets their resolution. A change below about 0.03 cannot be told apart from grid error. In Case D split fibre, 0.03 is one of 33 points.

### Part A: sensitivity of the base settings

Score change from the base (Δq = hit rate; ΔFB > 0 means lower speeds). The probe change is p95 |ΔK| for Case E / Case D. Base hit rates: E before 0.16, E after 0.30, D split fibre 0.27, D thermistor 0.23.

| Variant | Δq E before | Δq E after | Δq D split fibre | Δq D thermistor | ΔFB E before | p95 \|ΔK\| E / D |
|---|---|---|---|---|---|---|
| **Log-law inflow** | **+0.12** | **+0.08** | +0.09 | +0.01 | +0.16 | 0.12 / 0.07 |
| **Power-law inflow** | +0.05 | +0.04 | +0.09 | +0.01 | +0.08 | 0.06 / 0.03 |
| Linear profile interpolation | 0.00 | 0.00 | 0.00 | 0.00 | −0.01 | 0.005 / 0.003 |
| Footprints δ = 0.5 m | 0.00 | −0.01 | – | – | 0.00 | 0.011 / – |
| Footprints δ = 0.01 m | 0.00 | 0.00 | – | – | 0.00 | 0.001 / – |
| QES-ready City | +0.01 | 0.00 | – | – | +0.01 | 0.05 / – |
| Slabs filled to the ground | +0.01 | 0.00 | – | – | +0.02 | 0.09 / – |
| Padding 100 m | – | – | 0.00 | 0.00 | – | – / 0.001 |
| Top clearance H_max (2·H_max top) | 0.00 | −0.01 | +0.03 | +0.01 | 0.00 | 0.012 / 0.007 |
| Uniform vertical grid | 0.00 | 0.00 | 0.00 | +0.01 | 0.00 | 0.001 / 0.003 |
| Ground z0 0.05 m | 0.00 | 0.00 | 0.00 | −0.01 | 0.00 | 0.006 / 0.004 |
| Nearest-cell sampling | 0.00 | −0.01 | 0.00 | 0.00 | −0.02 | 0.14 / 0.00 |

![Phase 5 sensitivity](output/report/sensitivity.png)

**Findings.**
1. **The setup is robust.** The geometry preparation (δ, the QES-ready City), the domain (padding, top, vertical grid) and the profile interpolation move every pooled score by at most 0.014 in Case E. In Case D the largest move is 0.03, one point. None of them explains the Phase 3 findings.
2. **The inflow shape near the ground matters most.** The fitted laws are slower near the ground than the table.
   - At 2 m, relative to the reference height, the ratio is 0.75 (table), 0.69 (power law) and 0.63 (log law) in Case E; and 0.58, 0.55 and 0.51 in Case D.
   - The probes that keep the approach value then move toward the measurements: E "before" q +0.12 and FB +0.16 with the log law.
   - The pattern does not change (ΔR ≤ 0.02). It is the lever of Phase 3, finding 1, and the reason for the canopy inflow in part B.
3. **Elevated slabs (the R2 bracket) matter only locally.**
   - Filling the 32 slabs down to the ground changes probes by up to p95 0.09, but the pooled scores by at most 0.014.
   - At the 7 slab-adjacent points (112 values), "before" q goes 0.23 → 0.32 and FB −0.36 → −0.12; "after" q goes 0.26 → 0.27.
   - The truth lies between ignoring and filling the slabs, so R2 would change at most this.
4. **The QES-Turb ground roughness sets the turbulence level, not its pattern.** This corrects Phase 3, finding 5.
   - The base passes the profile's tail z0 (10⁻⁴–10⁻⁵ m, fitted to the smooth tunnel floor) to the QES-Turb wall model.
   - Upstream of every building (≥ 25 m away, upwind of all of them), QES-Turb's k at 2 m is then only 0.31 (E) and 0.44 (D) of the tunnel's inflow k.
   - With z0 = 0.05 m the ratio becomes 1.07 (E) and 2.43 (D). At the 33 split-fibre points, mean k rises 0.0062 → 0.0172 U² (measured 0.024): FAC2 0.15 → 0.45 and FB +1.16 → +0.32.
   - R stays near zero (0.09 → −0.02), and the √(|U|²+2k) scores barely move (D thermistor q 0.26 → 0.27; Case E only gets faster).
   - The mean wind is unchanged (p95 |ΔK| ≤ 0.006).
   - So most of the "4× too low" k comes from the input roughness, and no single z0 fits both cases (see R11).
5. **Sampling: the pooled scores hold, single probes do not.**
   - Nearest-cell instead of linear sampling moves pooled scores by at most 0.02, but single Case E probes by up to p95 0.14, as in Phase 4.
   - If each simulated K may sit anywhere within max(1 m, dx) of the probe, q rises to 0.44 (E before), 0.58 (E after), 0.45 (D split fibre) and 0.37 (D thermistor). Positional sensitivity is as large as any model change below.

### Part B: tuning to Case E "before"

**Search** (`tune_validation.py`; the log is in `output/tuning/search.json`).
- **Objective:** the pooled hit rate of K against the Case E "before" thermistors. Ties within 0.01 go to the higher ρ.
- **Candidates per step:** every single change.
  - Each other code of each flag; the wakes off together with the models that need them; the wall roughness at 10⁻⁴–10⁻¹ m.
  - The canopy inflow on a 3 × 3 grid, z0_u = a·H̄ and z_b = b·H̄. H̄ is 6.03 m in E and 10.43 m in D, the area-weighted mean building height.

| Step | Start q | Best single change | q | ρ | Kept |
|---|---|---|---|---|---|
| 1 | 0.156 | canopy a = 0.1, b = 6 | 0.491 | 0.545 | yes |
| 2 | 0.491 | wake off, with rooftop, street canyon and sidewall | 0.554 | 0.520 | yes |
| 3 | 0.554 | `upwind_cavity=3` | 0.559 | 0.520 | no (< 0.01) |

![Tuning search](output/report/tuning_search.png)

- **Single changes in step 1** (`tuning_screen.png`, all 35 runs each):
  - Every flag and wall-roughness change moves the pooled q by at most 0.035, and R by at most 0.06, except switching the wakes off (q: E before −0.08, D thermistor +0.12).
  - `high_rise=1` is the only flag with a consistent but small gain: D thermistor q +0.035, R +0.06; change R +0.05.
  - The canopy inflow is the one large lever. With a = 0.1, E before rises by +0.33 to +0.34 for every b.
- **The tuned settings:**
  - the canopy inflow with z0_u = 0.6 m and z_b = 36 m in Case E (1.0 m and 63 m in Case D);
  - `Parameterizations(wake=0, rooftop=0, street_canyon=0, sidewall=0)`, which leaves only the upwind cavity.
  - At 2 m, K normalised by the approach flow is then 0.43 (E) and 0.23 (D) in the approach, against 0.75 and 0.58 for the base.

**Base against tuned** (q / FAC2 / FB / R / ρ). The 1 m rows confirm 2 m within 0.03.

| Comparison | Role | Base, 2 m | Tuned, 2 m | Tuned, 1 m |
|---|---|---|---|---|
| E before, 1,280 | **training** | 0.16 / 0.67 / −0.43 / 0.51 / 0.54 | **0.55** / 0.94 / −0.04 / 0.48 / 0.52 | 0.54 / 0.93 / −0.07 / 0.46 / 0.50 |
| E after, 1,280 | test, same site | 0.30 / 0.72 / −0.15 / 0.46 / 0.46 | **0.48** / 0.87 / +0.20 / 0.50 / 0.48 | 0.49 / 0.88 / +0.17 / 0.49 / 0.47 |
| E change: R / ρ / sign agreement / top-10 overlap | test | 0.41 / 0.52 / 0.73 / 0.59 | 0.53 / 0.51 / 0.73 / 0.51 | 0.50 / 0.48 / 0.72 / 0.53 |
| D split fibre, 33 (like for like) | test, other case | 0.27 / 0.61 / −0.23 / 0.55 / 0.40 | **0.21** / 0.42 / +0.66 / 0.48 / 0.29 | 0.21 / 0.45 / +0.64 / 0.49 / 0.29 |
| D thermistor, 198 | test, other case | 0.23 / 0.56 / +0.44 / 0.43 / 0.40 | **0.05** / 0.29 / +0.90 / 0.42 / 0.37 | 0.05 / 0.32 / +0.89 / 0.42 / 0.38 |

![Base and tuned](output/report/tuning_scatter.png)

**Findings.**
1. **On the training set the hit rate triples, from the level alone.**
   - q goes 0.16 → 0.55 and FAC2 0.67 → 0.94; FB is close to zero.
   - The pattern does not improve: R 0.51 → 0.48 and ρ 0.54 → 0.52.
   - The tuned field is compressed. The simulated standard deviation goes 0.22 → 0.09, against 0.12 measured, and the regression slope of simulated on measured goes 0.95 → 0.35.
   - q rewards a field that sits within 25 % of the measured level everywhere. It does not reward a field that ranks the windy spots better.
2. **It carries over within the site.**
   - Case E "after" goes 0.30 → 0.48 with R 0.46 → 0.50, but it now underpredicts (FB +0.20), because the new tower raised the measured speeds.
   - The effect of the new buildings is still missed: sign agreement stays at 0.73, the top-10 overlap falls 0.59 → 0.51, and the change bias stays −0.09. Change R rises to 0.53.
3. **It does not carry over to Case D.**
   - Against the split fibre (mean vector, the like-for-like comparison) every score gets worse: q 0.27 → 0.21, R 0.55 → 0.48, ρ 0.40 → 0.29, and FB +0.66 (now far too slow).
   - Against the thermistor, q falls 0.23 → 0.05.
   - The canopy law scaled by H̄ is too strong for the regular 10 m blocks, whose reference is the flow at 100 m.
4. **The second step probably compensates for the instrument, not for missing physics.**
   - With the canopy inflow alone, the Case D split-fibre R *rises* to 0.62, from 0.55, while q falls to 0.21 (FB +0.37).
   - Switching the wakes off then takes R back to 0.48. It removes the near-zero wake speeds that a mean-vector model should produce, and that a scalar-speed thermistor does not see (Phase 1: the instrument ceiling).
   - This is consistent with the data, but not proven point by point.
5. **The tuned k level is right by accident.** The canopy law's strong shear near the ground raises QES-Turb's k at the split-fibre points: FAC2 0.15 → 0.58, FB +1.16 → +0.15. Its pattern stays poor (R 0.14).

### Consequences
- **The defaults stay the reference configuration,** and the headline table stays on them.
  - The tuned settings are a calibration to one district. They triple the in-sample hit rate, carry over to the same site, and make the second case and the like-for-like vector comparison worse.
  - Reporting them as the validation result would overstate dtcc-qes.
- **What does carry over is a direction for dtcc-qes, not a setting.**
  - Below roof level, the dense low-rise Case E district needs a slower background than the approach profile: the canopy inflow and the log-law inflow both improve it.
  - A background applied over the whole domain is a blunt tool. It also slows the open approach flow and every building zone, and it overshoots in Case D.
  - A canopy-aware initial field *inside* built-up areas, from the local morphometry, would be the targeted version. Phase 6 filed it as R17, with an acceptance test on both cases.
- **Turbulence (R11):** the input ground roughness, not the morphometric u\*, explains most of the low k level. No single z0 matches both cases, and the pattern stays wrong (R ≈ 0). R11 is updated.
- **Elevated slabs (R2):** a local effect at 7 of 80 points, under 0.014 on the pooled scores. It stays a low priority for AIJ.
- **Per-probe sensitivity remains the largest open uncertainty** (Phase 4 and part A, finding 5). A positional tolerance of one neighbourhood moves q by as much as the tuning does.

Figures in `output/report/`:
- `sensitivity.png` and `tuning_screen.png`: score changes per variant and per single change;
- `tuning_search.png`, `tuning_scatter.png`, `tuning_distributions.png` and `tuning_change.png`.

Data: `sensitivity.json` and `tuning.json` (with the 1 m rows, the neighbourhood scores and the upstream k).

## Code map (step 2)

- `aij/conventions.py`: direction mappings, `flow_vector`, and the model-independent checks `upwind_blockage`, `mapping_check` and `mirror_symmetry`.
- `aij/tables.py`: points, `load_inflow_d`/`load_inflow_e`, `load_exp_s` (`SplitFibre`), `load_exp_t` and `load_results_e` (`Measurements`). Non-numeric cells become NaN.
- `aij/inflow.py`: `measured_profile` (baseline; optional ground-roughness override), `power_law_profile`, `log_profile`, `canopy_profile` (Phase 5), `profile(kind)`, `approach_profile` (the normaliser), `fit_log`, `fit_power_law` and `reference_speed`.
- `aij/metrics.py`: `ranks` (ties averaged) and `spearman`. The Phase 3 scores come next.
- `aij/report.py`: `plot_inflow`, `plot_maps` and `plot_scalar_estimates`.
- `aij/grids.py`: horizontal bounds per case, and vertical faces with a layer centred at 2 m.
- `aij/sampling.py`: `probe_sample` (linear via `sample_points`, the nearest-fluid fallback, the neighbourhood span, k from stress) and `wall_distance`.
- `aij/runspec.py`: `RunSpec` and its key. Fields added later (`LATER_FIELDS`) are left out at their defaults, so default runs keep their keys: `parameterizations` (the changes from the `wind.Parameterizations` defaults), and `canopy_roughness`, `blending_height` and `ground_roughness` (Phase 5). The cities are `exact`, `qes_ready` and `slabs_filled`.
- `aij/campaigns.py`: the `smoke`, `convergence`, `baseline`, `grid` (4 m and 1 m), `fine_check`, `fine` (the 0.5 m subset, `fine_subset`), `sensitivity` (`SENSITIVITY`) and `tuning_screen` matrices; the solver work per spacing; and the tuning space (`CANOPY_HEIGHT`, `canopy`, `tuned`, `tuning_candidates`).
- `aij/runner.py`: `run(spec)` → record and plane, `write`/`load`, `fingerprint`, `city_digest`.
- `aij/numerics.py`: the smoke cost table, the convergence analysis, and `self_convergence` (a monitored run against its own end point, Phase 4).
- `aij/compare.py`: `Comparison` (simulated and measured values shaped (point, direction), with strata, including the Phase 4 `span`), `case_d`, `case_e_comparisons`, `instrument_ceiling`, `split_fibre_extras`, `inflow_ratio`, `background_fraction`.
- `aij/gridstudy.py` (Phase 4): `changes` (refinement budgets per case and state, by wall distance and by span), `trend`, `scores` (with a span breakdown), `fallbacks` and `subcell_gaps`.
- `aij/report.py` (Phase 4): `plot_scores_by_resolution` and `plot_refinement`; (Phase 5) `plot_effects` and `plot_search`.
- `aij/sensitivity.py` (Phase 5): `effect` (probe and score changes against the base), `nearest` (resampling from the stored planes), `neighbourhood_best`, the tuning `objective`, `choose` and `accepted`, and `upstream_turbulence` (the R11 diagnostic).
- `aij/cityutil.py`: `fill_slabs` (Phase 5, the R2 bracket).
- `aij/metrics.py` (Phase 3): `scores` (hit rate, FAC2, FB, NMSE, R, ρ, bias, MAE, RMSE, the W sweep), `change_scores`, `angle_error`.
- `plot_measurements.py` (Phase 1), `run_validation.py` (runs, one process each; `--jobs N` in parallel), `tune_validation.py` (Phase 5 search) and `report_validation.py` (reports).
- `tests/test_compare.py` holds 11 Phase 3 checks: the metric definitions, the change and angle metrics, perfect-model pairing for both cases, the span stratum, the instrument ceiling and the inflow ratio.
- `tests/test_sensitivity.py` holds 10 Phase 5 checks: the canopy height scale, the canopy profile and its normaliser, the new `RunSpec` fields, one change per variant, valid tuning candidates, the tie rule, a perfect model and the neighbourhood score, nearest resampling, filled slabs, and the upstream-k selection.
- `tests/test_gridstudy.py` holds 8 Phase 4 checks: the refinement budget rule, missing runs, the span strata, the refinement trend, sub-cell gaps, fallbacks, self-convergence and the 0.5 m subset.
- `tests/test_cities.py` holds 4 dtcc-core integration checks: the convention, the `qes_city` adapter, the R3 pin, and the `footprints_from_lod1` cross-check.
- `tests/test_runner.py` holds 12 Phase 2 checks:
  - the vertical faces;
  - the run keys staying stable, also with `RunSpec.parameterizations` (R15);
  - a small monitored Case D solve, whose linear probes match an independent bilinear interpolation of the stored plane;
  - fallbacks within one cell;
  - the history ending at the record.
- `tests/test_tables.py`, `test_conventions.py` and `test_inflow.py` hold the 35 Phase 1 checks:
  - the reader identities;
  - the mirrored copies and the quantisation;
  - the direction checks;
  - the profiles reproducing the tables;
  - the tail law, the reference speeds and the fits.

# QES physical-model experiments

**Status:** proposed development experiments. Baseline audits explicitly marked as reproduced below have been checked against stored data; proposed model improvements and runtime targets remain unproven.

**Date:** 2026-11-02.

**Objective:** improve transferable pedestrian mean-wind predictions, especially the effect of changing buildings, while retaining an interactive fast mode. Allow **up to 60 seconds per wind direction for Case E at 2 m when clear accuracy improvements are demonstrated**, and up to **three minutes per direction** for the complex/detail tier on a workstation. A full multi-direction study may take longer; these limits are per direction.

The evidence baseline is [AIJ_VALIDATION.md](validation/AIJ_VALIDATION.md), dtcc-qes `c9e31e8`, native policy `b26d15fd`, and the dtcc-core/geometry identities recorded there. [DTCC_REQUESTS.md](validation/DTCC_REQUESTS.md) contains the related requests. This document defines a new development round; the earlier validation-only restriction on modifying solver code is not the scope of these proposed experiments.

This revision integrates the useful Group 1 proposals and subsequent critiques in [CLAUDE_WIND_EXPERIMENTS.md](CLAUDE_WIND_EXPERIMENTS.md). It keeps one experiment sequence, one evaluation protocol and one performance contract. Cross-references to F-numbered experiments identify provenance, not additional campaigns to run.

## 1. Decision this round must enable

Compare targeted improvements to the empirical-field-plus-mass-projection architecture with an early limited-momentum prototype. Choose the development path from physical gains and measured cost, within the user's per-direction latency requirement.

Run the foundation first, then the bounded physical screens described below. E5a starts alongside the first E1/E2 screens; it does not wait for empirical-zone development to fail.

| ID | Experiment | Main question | Priority |
| --- | --- | --- | --- |
| E0a–f | Reuse, application metrics, SOR, projector parity, variational weights and conditional multigrid | Can we trust comparisons and afford the physical tests? | Foundation; advanced solver work conditional |
| E1 | Algebraic canopy control and local column momentum balance | Does a geometry-dependent background improve canopy exposure, and is the column worth its extra complexity? | Core screen |
| E2 | Tower/wake attribution, circulation and zone interactions | Can we correct intervention magnitudes, especially spurious strong decreases, while retaining local sign skill? | Core screen |
| E3a/b | Receptor flags, continuous zone edges and near-wall treatment | Can we identify unstable receptors and stabilize predictions without suppressing real jets? | Flags early; model changes after architecture decision |
| E4a/b | Direction ensemble; inflow turbulence and transport | Can we improve scalar observations and turbulence patterns with separately tested mechanisms? | Conditional, bounded |
| E5a/b | Early 2 m momentum pilot; conditional 4 m transfer/detail mode | Does momentum transport justify an enhanced mode within three minutes per direction? | Early competing screen; scaling conditional |

E1 and E2 are separate hypotheses: a slower canopy background is not evidence that tower flow has improved. E3 cannot compensate for a wrong district-scale field. E4b cannot claim improved mean flow while turbulence remains a postprocessing calculation.

**Architecture decision:** after E1's cheap control, E2 attribution and E5a, compare accuracy versus measured cost. If momentum supplies the required improvement within a credible budget, prioritize E5b and stop expanding tower templates. Retain empirical initialization only if its separate warm-start test earns it. Otherwise continue only the already bounded E1/E2 candidates. Independent references are required for promotion, not for launching this early screen.

The round is successful only if a frozen candidate improves both physical accuracy and transfer to unseen layouts within its runtime tier. A higher pooled hit rate alone is insufficient. Outcomes may be a better fast model, a useful slower model, or evidence that neither merits promotion.

## 2. Performance contract

### 2.1 Workloads and limits

Use the current validation workstation as the reference machine. Record its CPU, RAM, OS, compiler, build flags and actual OpenMP team before running E0. Use four physical CPU threads, one direction at a time, no concurrent benchmark jobs, and no required GPU. Historical timings below are context; remeasure them under this common configuration.

| Workload | Existing evidence | Development target per direction | Maximum per direction |
| --- | --- | --- | --- |
| AIJ D at 2 m | About 3 s in the historical validation | At most 12 s for the fast candidate | 20 s |
| AIJ E at 2 m, before and after | About 7 s, including about 4 s preparation; D/E grids span approximately 1.8–2.6 million cells | Prefer ≤12 s; target ≤30 s when additional physics earns the extra time | **60 s with the accuracy gate below**; otherwise retain the 20 s fast limit |
| Existing urban core fixtures at 2 m, approximately 3.6–6.3 million cells | About 4–7 s in the historical four-thread solver benchmark; output/timing scope differs | At most 20 s for the fast candidate | 30 s |
| Complex/detail tier: AIJ D/E at 1 m, approximately 13–19 million cells, plus a frozen mixed-height district of comparable size | AIJ D/E about 31–37 s per direction in the validation | At most 120 s | **180 s** |

These are proposed product budgets, not hardware-independent guarantees. Case E's 60 s allowance covers the complete answer for one nominal direction, including preparation, all ensemble members or momentum iterations, requested turbulence, sampling and output. It applies to E1–E5 at 2 m; an ensemble or momentum implementation cannot bypass it by relabelling that workload as complex. The 1 m/detail tier retains its 180 s limit. An explicitly selected enhanced mode on other smaller domains may use the complex-tier limit, but must not be presented as meeting the fast-mode budget.

**Case E accuracy-for-time gate.** A candidate may be screened within 60 s before its benefit is known. To retain that allowance, a physical model must pass its experiment-specific accuracy gates and the final dense-district/intervention gates in §10.2: at least 15% lower speed MAE in each E state, at least 20% lower ΔK MAE, and the stated bias, sign-recall and spatial-skill requirements. An E4-only capability instead passes its declared scalar/turbulence gates on a frozen physical parent; it cannot claim mean-flow improvement. In either case, additionally demonstrate at least 10% improvement in the predeclared primary error metric over the best numerically valid ≤20 s comparator (the frozen baseline if no improved fast candidate exists), with a paired 95% interval excluding no improvement. Preserve all non-target, application, numerical and independent-evidence gates. A higher pooled q alone does not earn extra time. Promotion remains blocked until the relevant confirmation gates pass.

For single-solve E1–E3 and E4b, aim for at most **1.5×** the matched baseline's compute time; a combined fast candidate may reach **2×** if its accuracy gates pass. Absolute limits also apply. E4a is an optional ensemble with an explicit member count and the applicable workload cap; it qualifies for the original fast tier only if it meets both fast limits. E5 may use more of the applicable 60/180 s budget, but must outperform the best fast candidate, not merely the original baseline. Do not multiply an E5 solve by five ensemble members in this round.

For a qualifying Case E candidate, the 60 s allowance supersedes the 1.5×/2× compute limits and individual physics modules' 10–20% runtime-overhead targets. Those remain optimization goals, not reasons to discard a clear accuracy gain within 60 s. It does not relax convergence, memory limits or the measured-benefit requirements of cache/solver-acceleration experiments. E5 uses the applicable workload limit: 60 s for Case E at 2 m, 180 s for the complex/detail tier.

Measure full 16-direction studies and the 32-direction/state Case E comparison. Report actual elapsed time and peak memory rather than extrapolating a single favourable direction. At the 60 s limit, one Case E state takes up to 16 minutes and both states up to 32 minutes sequentially. Sixteen complex directions at 180 s take 48 minutes. State these study-level costs clearly in the app.

Peak process RSS limits: at most 2 GiB for fast AIJ at 2 m, 4 GiB for fast urban-core fixtures, and 8 GiB for the complex/enhanced tier, including an enhanced mode on a 2 m domain. No swapping. Include retained geometry caches and temporary field copies. Stream direction results rather than retaining 16 full volumes.

### 2.2 Timing protocol

- A **cold workflow** starts in a fresh worker and includes imports, loading a local City, geometry preparation, all model calculations, the pressure/mass solve, requested turbulence, receptor/plane sampling, and writing a standard compressed pedestrian plane. Exclude building the software, network fetching and offline reference generation; report those separately when relevant.
- A **warm workflow** uses the same app process and an unchanged City/grid, retaining only permitted geometry/operator caches. Every wind direction still requires a fresh calculation; cached final answers do not count as performance evidence.
- Report cold and warm timings separately, including preparation, physical initialization, solve, turbulence, sampling and output. Do not add a parent timer to its children.
- During screening use three repetitions of N, E, SW and W for Case E and the three Case D directions. For promotion, use three complete sequential direction sweeps for every required workload, alternating baseline/candidate order. Report median, empirical p95 and maximum without removing slow runs.
- Require every direction's median and the empirical p95 across all measured runs to meet its table limit. No completed Case E 2 m run may exceed its applicable 60 s allowance, and no completed complex-tier run may exceed 180 s. A reproducible timeout or allocation failure is a failed performance gate. Evaluate both cold and warm workflows, without using warm timings to hide a slow first answer.
- Compare physics variants under the same cache policy, grid, thread count and requested outputs. Separately show the user-visible benefit of improved caching. Saving preparation time is useful, but must not conceal a large increase in solve cost.

Add an end-to-end deadline for the applicable mode, including preparation: 60 s for the Case E allowance and 180 s for the complex/detail tier. A timed-out result is explicitly incomplete/unassessed. It must not silently revert to an easier geometry, omit turbulence that was requested, or report a partially converged field as an accurate answer.

## 3. Evidence and evaluation protocol

### 3.1 Preserve the current baseline

Keep the measured inflow, its reference normalization, geometry adapter, bounds, pedestrian layer, sample coordinates and defaults from the AIJ baseline. Use 2 m for screening and confirm shortlisted models at 1 m. Reproduce the existing fixed-work counts initially: 2,000 and 6,000 iterations, respectively. E0c/f compare time to equivalent accuracy, so they may use different iteration counts; freeze the accepted numerical policy and rerun the matched parent before comparing physics. Fixed work is a comparison control, not proof that a changed model is converged.

For every shortlisted initialization, repeat monitored convergence checks. Require the remaining iteration error at receptors to have p95 at most 0.005 in K and maximum at most 0.02 against a longer same-model solve. Use tighter references for assessing effects near those tolerances. Inspect mass residuals and wall-normal flux as well as receptor speeds. Changes to E5's momentum equations require their own convergence evidence.

The existing `pedestrian-v1` qualification does not cover these cases or new models. Native model changes get new identities; existing solver qualification must not be inherited as physical validation.

### 3.2 Reference sets and data separation

Freeze a manifest of geometry, measurement files, inflow, probes, directions and reference versions before selecting coefficients.

| Set | Use | Independence and limitation |
| --- | --- | --- |
| Existing AIJ D and E, all 35 runs | Diagnose and track known failures; calibrate only explicitly allowed parameters | Already inspected extensively. Neither E-after nor D is now an untouched test set |
| Small physical mechanisms | Isolate canopy, tower and wall behaviour; develop coefficients | Use the finite matrix below and available published AIJ isolated-building data after ingestion checks |
| New AIJ regular-array case C | External experimental confirmation | Freeze its predictions before inspecting errors; acquire and verify the fixture in E0 |
| Three existing numerical benchmark families: `perimeter_neighbourhood`, `slab_estate`, `mixed_downtown` | Test physical transfer using newly generated, independent reference fields | Freeze these geometries for confirmation; their earlier numerical benchmarks supplied no measured physical accuracy |

For each of the three benchmark families, freeze a baseline and one added-tower variant, four directions (0°, 90°, 225°, 270°), and the same bounds and probes in each pair: **24 reference runs**. The tower must fit an existing clear site; record the chosen footprint, height and any geometry constraints before viewing reference results. Keep the perimeter-block family entirely out of coefficient development. Unchanged geometry outside the declared intervention must remain byte-identical.

Use a validated steady RANS setup for these new reference runs, with consistent inflow, appropriate domain clearances, mesh/iteration checks, and vertical as well as pedestrian samples. Budget up to six additional refinements selected by geometry difficulty before inspecting QES errors. If RANS uncertainties are comparable to a proposed gain, the conclusion is inconclusive; use available experimental data or a small LES follow-up, rather than treating RANS as truth. Reference generation may take hours and is an offline research cost, not a runtime feature.

Do not crop references using QES's relatively shallow top by default. Verify the reference solver's own domain requirements. Use compatible physical inflow and region of comparison; identical cell counts are not required across methods.

The new experimental fixture and physical reference cases are prerequisites for a transfer claim. Their absence does not block E1/E2 or E5a prototyping, but does block promotion. Once confirmation errors are viewed, freeze the result; retuning consumes that set and requires a new untouched set.

**Near-wall reference eligibility:** a wall-function RANS result is not automatically a physical reference for the 0.5–1 m wall transects. Record local mesh spacing, wall treatment, y+, separation/reattachment and refinement sensitivity. Require spatially matched tunnel measurements or independently validated, suitably resolved numerical evidence before scoring near-wall physical accuracy. Otherwise use these transects only for numerical consistency; mark the physical gate unassessed. Distance in metres alone neither validates nor invalidates a wall function. Its assumptions are particularly questionable near corners and separation. [OpenFOAM wall-function documentation](https://doc.openfoam.com/2606/tools/processing/models/turbulence/ras/wall-functions/)

### 3.3 Finite mechanism matrix

Construct these reproducible flat-ground cases. H denotes the background building height, not the tower height. All numerical values and generated geometry hashes belong in the manifest.

- Empty domain: two measured/log profiles and four wind directions; checks ambient-profile preservation and the scalar observation calculation.
- Canopy: 6 × 6 square blocks, H = 10 m, footprint side 20 m; plan densities 0.16 and 0.36; aligned and staggered arrangements; directions 0° and 45°. This gives eight flow cases. Include upstream, row-by-row interior, roof and downstream sections.
- Tower: the lower-density aligned canopy at 0° and 45°, with a centred 20 × 20 m tower of height 30 or 60 m replacing one block; compare with the unchanged canopy. Four tower cases reuse two canopy references. Add one 60 m tower with a 40 × 40 × 10 m podium at 0° as a development challenge, without expanding the coefficient search.
- Wall/corner: one isolated 30 × 20 × 20 m rectangular building (length × width × height) at 0° and 30°, sampled along fixed physical lines 0.5, 1 and 2 m from the wall, plus corner and wake transects. Repeat with a translated grid origin, preserving world geometry and probes.

This is 15 non-empty mechanism configurations before numerical refinements. They are controlled diagnostics, not 15 independent real-world validation sites. The cost ceiling for new RANS generation is 45 runs: 15 mechanisms, 24 confirmation runs, and six preselected refinements. Stop and review if a reliable reference cannot be obtained within that scope.

### 3.4 Metrics and baselines

Define K as speed divided by the original external reference speed, and ΔK as after minus before. Use the same finite-data mask for all paired comparisons; report lost/invalid probes. Compute turbulence k from half the stress trace, matching the existing validation, not the differently scaled raw QES `tke` output.

| Question | Primary measurements | Supporting measurements |
| --- | --- | --- |
| Mean-flow physics | Vector RMSE against vectors; speed MAE against matched speed observations | Component bias, direction error, vertical sections, R and Spearman ρ |
| Dense-canopy level and pattern | Bias and MAE, both pooled and by exposure stratum | q, FAC2, variance and regression slope; interior versus open approach |
| Effect of construction | ΔK MAE, mean ΔK bias, balanced sign accuracy, strongest-speed-up recall | Separate increase/decrease recall, ΔK correlation and magnitude calibration |
| Local numerical robustness | Same-point changes under grid refinement and grid-origin shifts | Wall distance, neighbourhood span, corner-jet maxima and profiles |
| Turbulence | k MAE/RMSE and spatial correlation, inflow and in-city separately | Component variances, positive-semidefinite stress validity, scalar-speed error |

For balanced sign accuracy, use measured clear changes with |ΔK| > 0.04, report recall of positive and negative changes separately, and average the two recalls. A predicted zero is an abstention counted as incorrect for either class. The stored 2 m baseline audit, reproduced on 2026-11-02, gives increase recall **0.6845**, decrease recall **0.8515**, and balanced accuracy **0.7680** on 634 increases and 229 decreases. Ordinary sign agreement is about 0.729 versus **634/863 = 0.7346** for always-increase, whose balanced accuracy is 0.5. The model has substantial local sign skill; its negative mean change does not mean most predicted local signs are wrong.

On all 1,280 finite paired E observations, the same audit gives mean predicted ΔK **−0.0153**, measured **+0.0974**, and ΔK MAE **0.1452**. Treat intervention magnitude and excessive wake deficits as primary failures. A declared diagnostic stratum, measured ΔK > 0.04 with baseline predicted ΔK < −0.10, contains 89 pairs and contributes about 25.1% of total absolute change error. Freeze these IDs for reporting; never feed them to the model. Report signed-error contributions by measured increase/decrease, baseline error decile, direction and geometry-defined wake/exposure strata. Do not fix the mean merely by adding a positive offset.

Define strongest-speed-up recall per direction as overlap between the ten largest *measured positive changes* and the ten largest predicted changes, using fewer than ten when fewer positive measured changes exist. Use stable probe-ID ordering for ties and macro-average over directions with at least one measured increase; report omitted directions. Recompute the baseline with this exact definition rather than importing a median from another report. This is distinct from the existing top-ten overlap for absolute after-state speed; retain both metrics with distinct names.

Include the unchanged-before prediction for ΔK, the existing measured-inflow model, and a constant-speed predictor fitted only on development data. Add a simple upstream-blockage predictor as a cheap spatial baseline. Report whether extra complexity beats these controls.

Thermistors measure mean scalar speed, while the model predicts a mean vector. Keep the historical vector-versus-thermistor score for continuity, but label it as a mismatched observable. Do not tune mean-flow physics solely to that score. Under the conventional 3D definition of k,

\[
|\overline{\mathbf U}| \leq \overline{|\mathbf U|}
\leq \sqrt{|\overline{\mathbf U}|^2+2k}.
\]

The final expression is RMS speed. The 52% score obtained from the paired Case D instruments is a diagnostic of mismatch at those points, not a transferable ceiling. E4a tests direction variability separately. E4b retains RMS as a labelled empirical instrument proxy; the isotropic Gaussian expected-speed alternative has already failed the measured-data comparison below, so quadrature development is removed. A Case E scalar ΔK also contains changes in fluctuations; it is not by itself proof of a mean-flow mechanism. Always retain the raw mean-vector scores and identify the observable used by each candidate; an observation correction cannot pass a mean-flow gate on its own.

Keep q at D = 0.25 and W = 0.05 with the existing W sweep, but treat it as a secondary development metric. These thresholds and the new gates below are not a standards-compliance assessment.

Estimate paired uncertainty by resampling spatial groups and directions, keeping before/after values paired and mirrored D observations together. Publish per-direction results and leave-one-direction-out sensitivity. With only 33 independent D vector probes, report effect sizes and uncertainty rather than treating each mirrored value as extra evidence. A 0.03 grid-related change in pooled q is not a universal error bar for every metric or paired model difference.

### 3.5 Common guardrails

Every physics candidate must preserve solid impermeability, finite fields, the fixed external inflow and consistent normalization. Near/far exterior fields can respond physically to buildings; only the imposed boundary and the empty-domain solution are required to be unchanged.

For physical candidates in E0e and E1–E5, no non-target AIJ comparison or held-out family may worsen its primary MAE/RMSE by more than 5% relative to the matched parent, and R or ρ may not fall by more than 0.03, unless a tighter experiment-specific gate applies. Apply these independently, not after pooling families. A module passing only in combination is recorded as such and must pass the combined tests. Any larger regression stops automatic promotion and requires a new, explicitly justified experiment rather than averaging it away. E0b's application guardrails also apply, regardless of whether application scores rank candidates differently from q.

### 3.6 How to read the implementation sketches

The examples below are design sketches, not implemented features. Blocks marked **existing API** use current repository interfaces. **Standalone prototypes** are small NumPy calculations suitable for checking a formula on mechanisms; they are not production grid solvers. Blocks marked **proposed integration** show the functions or operators that would need to be implemented. Do not pass their settings directly to today's `wind.run`, `Parameterizations` or `Turbulence` objects.

All new numerical values are **initial experimental choices**, not calibrated constants or published recommendations. Only the explicitly listed candidate parameters may vary in this round. Fixed lengths, tolerances and closure choices must be recorded in the experiment manifest too. Change them only through the documented revision step, not by expanding a Cartesian-product search.

For a first implementation, keep new configuration in a versioned validation-side payload, then translate it through a dedicated experimental native bridge. The public defaults remain the frozen baseline until a candidate passes. For example:

```python
# Proposed configuration format; not accepted by the current wind.run API.
experiment = {
    "schema": "qes-physics-experiment-v1",
    "id": "E1-directional-cd0.8",
    "parent_model_digest": "<digest of complete frozen parent settings>",
    "canopy": {"mode": "directional", "drag_coefficient": 0.8},
    "tower": {"mode": "legacy"},
    "zone_edges": {"mode": "legacy"},
    "turbulence": {"mode": "legacy"},
    "momentum": {"mode": "off"},
    "projection": {"alpha1": 1.0, "alpha2": 1.0, "policy": "baseline-fixed-work"},
    "observation": {"mode": "mean-vector", "direction_offsets_deg": [0.0]},
}
```

Materialize every default from the parameter tables into that payload before hashing it. Store SI units, native/build identities, grid and boundary definitions, numerical limits and the complete parent payload alongside the digest. A digest of only the two changed settings is insufficient to reproduce an experiment.

## 4. E0 — establish trustworthy comparisons and recover runtime budget

### E0a — preparation reuse and stage attribution

**Hypothesis.** Geometry preparation can be reused across directions without changing outputs, leaving more runtime available for physical modelling; stage-level diagnostics can identify where physically useful circulation is lost.

**Why.** Case E spends about four of seven seconds in preparation. Existing final-field scores cannot identify whether a tower correction was never generated, overwritten by another zone, or weakened by mass projection.

**Experiment.** Compare the frozen baseline with a preparation-reuse branch, with physical calculations unchanged. Cache cleaned footprints, static geometry descriptors and compatible grid/operator data. Invalidate on geometry, grid, relevant settings, library or native identity changes; direction-dependent descriptors need direction/profile keys. Do not reuse direction-dependent velocities. Check a sequence A → B → A and after → before → after to detect stale state.

In a separate diagnostic mode record sampled fields after inflow, each parameterization family and mass projection; retain full intermediate volumes only for small mechanisms. Track model contributions and zone ownership, roof-level incident velocity, vertical momentum-flux proxies, and receptor changes. Use these outputs diagnostically; they do not supply measured truth.

**Pass/stop.** Reuse must preserve velocity and turbulence outputs bit-for-bit when arithmetic is unchanged, correctly invalidate every mutated input, and reduce the median complete 16-direction Case E workflow time by at least **40%**, with peak RSS no more than 10% above the matched single-run peak and within the absolute cap. Compare 16 fresh preparations in the same process with one preparation plus 16 fresh direction solves; include first preparation, all requested outputs and cache storage. With historical preparation/solve times of 4/3 s, the ideal saving is about 54%; 40% leaves implementation overhead. Remeasure rather than assuming this fraction. A smaller safe saving may be retained as maintenance, but does not pass this experiment or justify a cache redesign. Diagnostic overhead is measured separately and excluded from production timings only when disabled there.

**App benefit and cost.** Faster repeated directions and reliable attribution of errors. Cap this work at one cache prototype and one diagnostic implementation. Establish the fresh baseline metrics and all timing tiers here before choosing physical coefficients.

#### E0a implementation sketch and starting parameters

Start with a small run through the **existing API**. With `validation/` on `PYTHONPATH`, the existing `aij.runner.inputs` supplies the exact baseline City, profile and run settings:

```python
# Existing API: this example performs one actual baseline simulation if run.
from time import perf_counter
from dtcc_qes import wind
from aij.campaigns import case_e, fixed_work
from aij.runner import inputs

spec = fixed_work(case_e("SW", "after", resolution=2.0))
started = perf_counter()
args = inputs(spec)
result = wind.run(args["city"], args["profile"], **args["run"])
sample = result.sample_points(args["probes"].xyz, "linear", frame="global")
print({
    "prepare_run_sample_seconds": perf_counter() - started,
    "phase_timings": result.metadata["timings"],
    "valid_probes": int(sample.valid.sum()),
})
```

This diagnostic timer excludes imports and file output; it is not the cold-workflow timing gate. Use `aij.sampling.probe_sample` for campaign scoring so the existing nearest-fluid fallback and span definitions remain consistent.

The C++ [WindRunner](src/qes_core/dtcc/api/wind_runner.h) already separates preparation and solve. The following is an **existing-interface fragment**, assuming the native argument objects have been constructed by the bridge:

```cpp
dtcc_qes::WindRunner runner;
runner.prepare(grid, model, buildings, turbulence_settings, messages);
for (const auto &condition : conditions) {
    auto output = runner.solve(condition, solver_options, messages);
    // Sample/write this direction, then release its full-volume output.
}
```

Build the experimental Python session around this lifecycle rather than constructing a second native domain. Initially reuse one City/grid only, with an LRU capacity of **one prepared domain**. Include model settings and turbulence preparation in the key: they are used by `prepare`. Keep an independently reusable cleaned-footprint cache only if it has a measured benefit and fits the memory limit. Never cache mutable direction state as geometry. The current native `preparation_seconds` is retained on the runner; an end-to-end timer must avoid charging the same preparation again to each warm direction.

| Parameter | First value | Purpose |
| --- | --- | --- |
| Threads / simultaneous direction workers | 4 / 1 | Comparable CPU and memory budget |
| Cold repetitions | 3 | Each uses a fresh process |
| Warm direction sequence | 270°, 0°, 270°, then all 16 directions | Detect stale directional state and measure reuse |
| Retained prepared domains | 1 | Bound cache memory |
| Diagnostic stages | Inflow, canopy, cavity, wake, sidewall/canyon, rooftop, projection | Track which stage creates or removes a flow feature |
| Diagnostic output | Existing receptors plus three tower sections | Avoid full-volume snapshots on city cases |
| Snapshot precision | float32; comparisons accumulated in float64 | Keep data volume small without losing metric precision |

For cache invalidation checks, change one item at a time: wind direction, profile speed/table, one building height, geometry coordinates, vertical faces, parameterizations, turbulence settings and native identity. Reuse versus fresh preparation must agree under each change. Observability overhead is measured with diagnostics on/off; target **under 5%** in receptor-only mode, otherwise retain diagnostics only for research runs.

### E0b — application decisions and error decomposition (F01)

**Hypothesis and purpose.** A higher pooled q can conceal more missed windy locations or worse threshold-exceedance estimates. Test this on stored baseline/tuning runs before selecting new physics. There is no solver cost and no new physical coefficient.

Use Case E's complete 16-direction roses. Freeze two synthetic climates: uniform sector probabilities; and 60% probability shared equally by N/NNE/NE, with the other 40% shared by the remaining 13 sectors. Use a Weibull reference-speed distribution with shape 2 and mean 5 m/s at the original K reference height. A scalar factor K then gives the analytic probability of exceeding 5 m/s. Freeze research bands at probabilities `[0.025, 0.05, 0.10, 0.20]`; label the resulting bands 0–4. These are synthetic application tests, not NEN 8100 compliance, a measured local climate or a gust model. Do not invent a full rose from Case D's three measured directions.

**Measurements and gate.** Rank the stored variants by q and by exceedance MAE/class agreement; report Spearman rank agreement, with <0.7 as the diagnostic hypothesis. Report false negatives where the measured band is at least 2 and the prediction is lower, denominator = all measured band-2-or-higher receptors. Report population MSE as `bias² + (sd_sim - sd_measured)² + 2*sd_sim*sd_measured*(1-R)` using the same paired mask and ddof=0; handle constant arrays through covariance. A working audit must reproduce perfect/constant controls and the decomposition to float64 roundoff. Reject data transformations that change reference height or normalization between candidates.

Regardless of the rank result, later candidates must not increase exceedance MAE by more than 5% or the false-negative rate by more than **2 percentage points**, in either climate and either E state, relative to their matched parent. Also report comparison with the original baseline. If a denominator is empty, mark that metric unassessed. A class score cannot qualify a physical model that fails vector/intervention gates. Keep raw-vector and declared scalar-proxy application scores separate.

```python
# Standalone prototype: exact synthetic-climate exceedance, K=(receptor, sector).
import numpy as np
from math import gamma

def exceedance_probability(K, sector_probability, threshold=5.0,
                           mean_reference=5.0, shape=2.0):
    K = np.asarray(K, dtype=float)
    p = np.asarray(sector_probability, dtype=float)
    if (K.ndim != 2 or p.shape != (K.shape[1],) or not np.isfinite(K).all()
            or not np.isfinite(p).all() or np.any(K < 0) or np.any(p < 0)
            or not np.isclose(p.sum(), 1) or min(threshold, mean_reference, shape) <= 0):
        raise ValueError("Invalid factors or synthetic climate")
    scale = mean_reference / gamma(1 + 1 / shape)
    ratio = np.full_like(K, np.inf)
    np.divide(threshold, scale * K, out=ratio, where=K > 0)
    return np.exp(-ratio**shape) @ p
```

Exclude receptors with any missing required direction using one common mask and report coverage. Do not renormalize a different incomplete climate for each candidate. Archive the audit even if the ranking hypothesis is refuted; the application guardrails remain.

### E0c — time to accuracy with SOR acceleration (F02)

**Hypothesis.** A different relaxation factor can reduce projection wall time by at least 30% without changing the converged field. The current runner uses 1.78, or 1.90 in eligible adaptive mode; AIJ runs do not inherit that adaptive qualification.

**Matrix.** Test `omega = [1.78, 1.85, 1.90, 1.93, 1.95, 1.97, 1.99]` on D's three directions and E-after N/E/S/W at 2 and 1 m. Use the stored float64 convergence runs where identities match, otherwise regenerate them. Compare time to §3.1's receptor accuracy plus mass/flux criteria, not equal sweep counts. Monitor residuals and retain oscillatory/divergent failures. Select one global omega, not one per site. Only if fixed omega cannot transfer, allow one Chebyshev prototype with a spectrum estimate from 50 startup sweeps and a documented stability safeguard; no coefficient search for it.

**Pass/stop and cost.** Require at least 30% median projection-time reduction at 1 m, no tested direction more than 10% slower end-to-end, and converged normalized receptor-vector differences ≤1e-4 against the original operator's converged answer. Confirm on the simple mechanism and urban-core workloads before adoption. Report total cold/warm savings separately. If the gate fails, keep the original policy; do not claim a physical improvement from reduced numerical error at the old iteration count.

```python
# Proposed integration: experimental bridge only; not current wind.Solver arguments.
omegas = (1.78, 1.85, 1.90, 1.93, 1.95, 1.97, 1.99)
for omega in omegas:
    record = run_monitored_projection(frozen_initial_field, omega=omega,
                                     reference=converged_reference)
    save_time_to_accuracy(record, p95_K=0.005, max_K=0.02,
                          require_mass_and_wall_checks=True)
```

### E0d — projector equivalence gate P0

**Hypothesis and entry.** A prototype projector can reproduce the native mass adjustment before new physics is evaluated through it. Required for E0e/f or any Python/prototype field modification; direct native changes still require the equivalent regression checks. Export the actual native operator coefficients and boundary/face mapping rather than reconstructing undocumented defaults.

On empty, blocked and stretched-grid mechanisms, test solid faces, top/lateral boundaries, disconnected fluid components and the pressure/null-space convention. Confirm on E-after N/E/SW/W at 2 m, streaming comparisons rather than retaining several full fields. With identical unit variational weights and converged float64 references, require normalized receptor-vector difference p95 ≤1e-4 and max ≤5e-4, and volume-weighted field-vector RMS difference ≤1e-4. Normal solid-face velocity must remain ≤1e-6 Uref. Dimensionless divergence `L*div(U)/Uref`, L=min grid spacing, must be no worse than 1.1 times the reference or the numerical floor (RMS 1e-6, max 1e-4), whichever is larger. Check net boundary flux as well. A matching speed magnitude alone does not pass.

**Stop/app benefit.** No physics claims through a projector that fails P0. Cap work at one operator adapter and one parity suite; if export exceeds memory limits, keep full comparisons on mechanisms and use streamed city diagnostics. This prevents numerical changes from masquerading as canopy/tower improvements. It is validation infrastructure, with no production overhead when disabled.

### E0e — variational-weight sensitivity (F05)

**Hypothesis.** The relative penalty on vertical versus horizontal mass corrections may suppress useful circulation or over-divert flow; it is a modelling sensitivity, not a null test assumed to fail. After P0, hold the unprojected baseline field fixed and test `alpha2/alpha1 = [0.5, 1, 2]`, with alpha1=1, first on tower mechanisms and then on the 35 AIJ runs. Keep E0c's numerical policy fixed but reconverge each changed operator.

```python
# Proposed integration: C and both operators must use the same coefficients.
for ratio in (0.5, 1.0, 2.0):
    C = face_diagonal(horizontal=0.5, vertical=0.5 / ratio**2)
    lam = solve_elliptic(D @ C @ G, -D @ initial, boundary_conditions)
    corrected = initial + C @ G @ lam
    record_projection_attribution(corrected, initial)
```

**Pass/stop.** Retain a non-unit ratio only if it improves D vector RMSE or E ΔK MAE by at least 10%, preserves the other within 5%, preserves both sign recalls within 0.02, and passes common guardrails and mechanism vertical-flow checks. Otherwise retain ratio 1 and close this axis. If attribution later shows a new tower term is uniquely suppressed, allow one paired unit-versus-selected-ratio check on that frozen term; no ratio-by-physics Cartesian product. Promotion still needs the independent gates. Cost should remain close to one projection; record conditioning, iterations and end-to-end time rather than assuming it is unchanged.

Freeze at most one selected ratio as part of the common physical parent for E1/E2, alongside a unit-weight control. Preserve the original baseline for all absolute gates. A ratio change invalidates the cached operator/hierarchy even when geometry is unchanged; it is not merely a sampling option.

### E0f — bounded multigrid feasibility (F06)

**Entry and hypothesis.** After P0 and E0c, open one CPU AMG-preconditioned Krylov prototype if measured projection cost threatens E5a's repeated-solve budget or E4a's ensemble budget. This may happen early; it need not wait for E1/E2 to fail. The hypothesis is at least 2× lower projection time at matched accuracy on 1 m cases, including amortized setup across 16 directions, while preserving P0 parity. Report cold setup separately and keep the single-answer deadline.

Use the exact stretched-grid operator, with volume weighting/sign convention that makes the solved system symmetric positive definite before using CG. Handle isolated components explicitly. Test 4/2/1 m grids of the same mechanisms and D/E; these are numerical tests, not permission to use a 4 m physical model without validation. Record hierarchy/operator complexity, setup time, cycles, memory and iteration scaling. Start relative residual at 1e-8 for the parity checks; final stopping uses field/flux accuracy. A ≤30-iteration result is a diagnostic target, not a substitute for wall time.

**Pass/stop and benefit.** Require the speed gain, unchanged fields, memory caps and no >10% end-to-end regression in simple cases. Reuse only geometry/operator hierarchies with valid keys. Translate to native code only if measured prototype operations and a native kernel benchmark support the intended workflow budget; a work-unit estimate alone does not qualify the product. Retain SOR if this fails. Avoid GPU work, 0.5 m whole-city grids and a second multigrid implementation in this round.

## 5. E1 — local canopy momentum balance

**Hypothesis.** A local, direction-dependent canopy background, matched to the external flow above roofs, will reduce Case E-before's excessive interior speeds while preserving open approach flow and Case D vector accuracy.

**Why.** The present field often retains the approach speed outside building influence zones. Globally reducing the inflow improves one district's level but damages another case. A local physical response must depend on exposure and vertical exchange, not just global mean height. LES research finds that height variability and aligned versus staggered layouts produce substantially different canopy behaviour. [Lu et al., 2024](https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4584)

**Model to test.** Construct coarse patches of local plan/frontal density, height distribution, directional open fetch and street alignment. First test a cheap algebraic canopy prior (E1a below), then a small vertical momentum-balance model per occupied patch (E1b), with turbulent exchange and a canopy drag closure. The column solves `d/dz(K_m dU_i/dz) - C_d a_f |U| U_i = 0`: roof-driven vertical mixing balances canopy drag. Here `K_m` is an eddy diffusivity, `a_f` is frontal area per unit volume, and `C_d` is a dimensionless drag coefficient. Update `K_m = ell² |dU/dz|` from the column's own shear at every nonlinear iteration, with the declared floor. The external profile initializes the iteration and supplies the top condition; its shear is not the converged canopy closure. Do not require measured in-city turbulence as an app input.

Set the top velocity from the unchanged external profile, with no extra fetch attenuation in this round, and use a ground-stress boundary law. Treat top stress as a diagnostic, not an additional boundary condition that overdetermines the column. Freeze patch scale, mixing-length law, density definition and the two closure-strength choices before the city screen. This first prototype has no independent horizontal pressure-gradient forcing; its inability to reproduce pressure-driven street flows is a hypothesis limitation for E5 to test. Taper smoothly at canopy edges and match to the original profile above the modelled canopy.

This is an averaged background prior, not an additional volumetric drag force applied on top of every resolved wall. Building-zone models must use locally incident velocities and replace or perturb this background through a declared composition rule. Do not simply multiply a canopy slowdown by every existing wake deficit. Audit total attenuation and compare a small case with/without explicit local wake corrections to expose double-counting.

**Arms.** Original baseline; the already studied global-canopy inflow as a negative control; one directional algebraic control; isotropic and direction-aware columns. For the column arms allow two predeclared drag strengths each on mechanisms: four column candidates plus the algebraic control. Select one shared drag strength before city screening, leaving only three new city candidates (algebraic, isotropic column, directional column). Fit on the mechanism set and existing AIJ development data only. Use one coefficient set for both cities and all directions. Compute descriptors separately from the actual before/after geometry, without observed wind changes.

**Measurements.** Row-by-row wind recovery, roof-to-canopy shear, mean and vector errors, and separate results for interior, edge and open-exposure probes. Include approach-to-first-row and downstream recovery sections in the existing eight canopy mechanisms; no extra RANS geometries are needed. Report how many probes remain near the undisturbed K, whether a gain only reduces variance, and whether algebraic and column models recover too abruptly outside the canopy. Inspect vertical profiles so a plausible 2 m value cannot hide an unphysical roof transition.

**Pass.** At 2 m, reduce E-before speed MAE by at least 20% and absolute mean bias by at least 30%; retain its R and ρ within 0.02 of baseline. Case D vector RMSE must not worsen and its median direction error must not increase by more than 3°. E-after and construction-change MAE must meet common guardrails. Require the direction-aware arm to improve mean vector/profile RMSE by at least 10% over the isotropic arm on the canopy mechanisms; otherwise keep the simpler arm. Confirm the principal gains at 1 m, and apply the final transfer gate before promotion.

**Complexity gate.** A column must additionally improve canopy-mechanism vector/profile RMSE by at least 10% over the algebraic control without worsening the E-before MAE. Otherwise keep the algebraic arm if it passes the physical gates. If no arm passes, retain the original background; the early E5a pilot continues independently. Updating shear is O(n) per column iteration, but extra iterations and total runtime must still be measured.

**Performance and app benefit.** Target at most 20% added native calculation time and 10% additional peak memory. Compute geometry features once; solve short column systems rather than a second fine 3D problem. Expected benefit is more realistic street/background exposure across districts. If only the global attenuation control wins, or spatial variation collapses as in the previous tuning exercise, reject the hypothesis in this implementation.

### E1a — algebraic control (F07)

**Hypothesis.** A cheap local roof-matched profile captures most of the canopy benefit, making a column solver unnecessary. Use the same directional descriptors, patch lattice and exposure/taper support as E1b. Let H be the background H50 and lambda_f the projected frontal area divided by plan support area. Within the canopy set `U_trial(z) = U_external(H) * exp[-a * (1-z/H)]`, `a = 9.6 * min(lambda_f, 0.3)`, and blend the ratio `clip(U_trial/U_external(z), 0.2, 1)` to one at H. The values 9.6, 0.3 and 0.2 are fixed experimental choices adopted from F07 for this control, not verified universal constants or a new tuning sweep. Use a smooth roof blend over 0.8H–H and the existing 10 m horizontal edge taper. Leave empty/open patches unchanged and diagnose the artificial floor and recovery length.

```python
# Standalone prototype: E1a interior attenuation; edge taper applied separately.
import numpy as np

def algebraic_canopy_factor(z, external_speed, roof_speed, height, lambda_f):
    if height <= 0 or lambda_f <= 0:
        return np.ones_like(np.asarray(z, dtype=float))
    eta = np.clip(np.asarray(z, dtype=float) / height, 0, 1)
    trial = roof_speed * np.exp(-9.6 * min(lambda_f, 0.3) * (1 - eta))
    external = np.asarray(external_speed, dtype=float)
    ratio = np.ones_like(trial)
    np.divide(trial, external, out=ratio, where=external > 0)
    t = np.clip((eta - 0.8) / 0.2, 0, 1)
    roof_blend = t * t * (3 - 2 * t)
    return roof_blend + (1 - roof_blend) * np.clip(ratio, 0.2, 1)
```

Insert this background **before** building-zone evaluations. Multiplying every post-zone air velocity is not equivalent because those zones depend on incident velocities. This control does not represent an internal boundary layer rigorously; if its canopy-edge/recovery tests fail, do not fix it with an unbounded fetch/roughness search. Use E1's accuracy gates and target ≤10% extra native time; compare E1b with it before choosing complexity.

### E1b — column implementation sketch and starting parameters

Begin with a **20 m horizontal patch lattice**, smoothly interpolate its profiles to the fine grid, and use **24 vertical cells** from ground to `2 * H95`, where H95 is the footprint-area-weighted 95th percentile of local roof height. Exclude a separately detected exposed tower from the background-height estimate; its geometry remains present in the actual obstacle model and E2. For sparse patches without enough surrounding buildings, use the external background rather than deriving a canopy from the tower itself. Freeze a minimum sample criterion of three surrounding buildings.

Estimate descriptors in a 60 m radius. For the directional arm, weight upstream obstacles with `exp(-s / (3 * H50))`, truncated at an upstream distance of `6 * H50` and the descriptor radius; H50 is the local weighted median height. The isotropic arm uses uniform spatial weights within the same descriptor radius. Integrate exposed, wind-normal facade area in each layer and divide by the correspondingly weighted fluid volume **over that same descriptor support** to obtain `a_f(z)` in m⁻¹. Do not divide all the facades in the 60 m neighbourhood by the volume of one 20 m patch. State whether a facade is occluded; do not count hidden faces as fully exposed. Generate descriptors through spatial indexing/raster accumulation, not a full building search at every fine cell.

| Parameter | First value | Allowed comparison |
| --- | --- | --- |
| Patch pitch / descriptor radius | 20 m / 60 m | Fixed for this round |
| Vertical column cells / top | 24 / `2 * H95` | Refine columns to 48 on mechanisms as a numerical check |
| Drag coefficient `C_d` | 0.8 | 0.8 versus 1.2, for each of isotropic/directional arms |
| Mixing length | `min(0.4 * (z + z0_ground), 0.15 * H50)` | Fixed |
| Updated eddy diffusivity | `ell**2 * abs(dU_column/dz)` at faces | Floor `1e-4 * U_top * H50`; report floor usage and sensitivity to halving it on mechanisms |
| Ground roughness | Physical case input; 0.03 m on synthetic mechanisms | Preserve recorded AIJ baseline value unless independently justified; no fit to receptor errors |
| Nonlinear relaxation / maximum iterations | 0.5 / 60 | Convergence study only; double cap on mechanisms, not a physics tuning axis |
| Column stopping tolerance | Maximum update / `U_top` < 1e-3 and relative equation residual < 1e-3 | Reassemble residual with updated shear and drag |
| Horizontal canopy-edge taper | 10 m in physical coordinates | Fixed under grid refinement |

For directional layers with no exposed frontal area, set `a_f = 0`; leave entirely open patches on the original profile. The isotropic/directional descriptor comparison is a modelling hypothesis, not an assertion that canopy flow always decreases monotonically with density.

The following **standalone prototype** implements one streamwise column with updated shear-dependent diffusivity, a linearized ground-stress law, and implicit drag. Its dense solve is only for readable 24–48-cell checks. Use an O(n) tridiagonal solver across patches in native code.

```python
# Standalone prototype: E1 finite-volume column.
import numpy as np

def canopy_column(external, frontal_area, dz, top_speed, ground_z0, h50,
                  cd=0.8, relaxation=0.5, max_iter=60):
    external = np.asarray(external, dtype=float)  # cell centres, m/s
    af = np.asarray(frontal_area, dtype=float)    # n cells, 1/m
    n = len(external)
    if (n < 2 or af.shape != (n,) or min(dz, ground_z0, h50, cd) <= 0
            or top_speed < 0 or not 0 < relaxation <= 1
            or not np.isfinite(external).all() or not np.isfinite(af).all()
            or np.any(af < 0)):
        raise ValueError("Invalid column geometry, diffusivity or drag")
    if top_speed == 0:
        return np.zeros(n), True
    if not np.any(af):
        return external.copy(), True  # preserve the prescribed open profile

    ell = np.minimum(0.4 * (np.arange(1, n + 1) * dz + ground_z0), 0.15 * h50)
    km_floor = 1e-4 * top_speed * h50
    wall_cf = (0.4 / np.log1p(0.5 * dz / ground_z0))**2

    def assemble(v):
        shear = np.r_[np.diff(v) / dz, (top_speed - v[-1]) / (0.5 * dz)]
        km = np.maximum(ell**2 * np.abs(shear), km_floor)
        g = km[:-1] / dz**2
        matrix = np.diag(np.r_[g, 0] + np.r_[0, g] + cd * af * np.abs(v))
        matrix += np.diag(-g, 1) + np.diag(-g, -1)
        matrix[0, 0] += wall_cf * abs(v[0]) / dz
        top_weight = 2 * km[-1] / dz**2
        matrix[-1, -1] += top_weight
        rhs = np.zeros(n)
        rhs[-1] = top_weight * top_speed
        return matrix, rhs

    u = external.copy()
    for _ in range(max_iter):
        matrix, rhs = assemble(u)
        solved = np.linalg.solve(matrix, rhs)
        updated = (1 - relaxation) * u + relaxation * solved
        check_matrix, check_rhs = assemble(updated)
        residual = np.linalg.norm(check_matrix @ updated - check_rhs, ord=np.inf)
        relative_residual = residual / max(np.linalg.norm(check_rhs, ord=np.inf),
                                           top_speed**2 / (n * dz))
        converged = (np.max(np.abs(updated - u)) / top_speed < 1e-3
                     and relative_residual < 1e-3)
        u = updated
        if converged:
            return u, True
    return u, False  # retain this status; do not silently call it converged
```

This streamwise sketch assumes a locally fixed wind direction. Extend to two coupled horizontal components using their shared vector speed in the drag coefficient if testing directional veer. No measured in-city velocity is used as a top condition. Keep units and the original external reference speed unchanged.

**Proposed integration:** insert the patch field after `applyWindProfile` and before building-zone proposals. Evaluate each local model against that incident field. At occupied cells keep solid velocity zero; after blending, use the existing fine-grid mass correction. Record the no-canopy fraction, minimum/maximum attenuation, column residuals, and roof matching error. There is no arbitrary final multiplication of the solved field by a fitted attenuation map.

## 6. E2 — exposed-tower circulation and zone composition

**Hypothesis.** Correcting excessive tower/wake deficits and the redistribution of incident momentum, while preserving useful local sign skill, will improve intervention magnitude and location. Exposure-aware circulation or composition changes are candidate mechanisms, not a presumption that the entire failure is missing downwash.

**Why.** E-after's mean measured change is about +0.10 in K; the model predicts about −0.02, despite baseline balanced sign accuracy of 0.768. Excessive negative changes contribute substantially to that mean error (§3.4). The current high-rise switch changes wake geometry and vertical velocities as well as wake length; it is not evidence that windward circulation and incident momentum are represented adequately. Diagnose the existing terms before adding a new one.

**Experiment A: attribution before new physics.** On the tower mechanisms and the E5a development subset (E SW/SSW/E/WSW, both states; D's three directions), inspect E0a stage outputs with baseline settings, `high_rise=1`, and the alternative upwind-cavity setting, one switch at a time. Compare paired before/after stage changes, strongest measured increases, and the fixed spurious-decrease diagnostic stratum. Quantify whether each error is created by wake attenuation, missing circulation, a later overwrite or projection. These causes can coexist. Reverse building order and permute equal-height IDs as regression checks, but do not make negligible order effects the justification for a composition rewrite. A canonical sort alone does not establish correct overlap physics.

**Experiment B: a small circulation model.** Create a dimensionless tower correction conditioned on exposed tower height above surrounding roofs, façade width, incidence angle, local roof-level wind and podium presence. Use a small analytic/template family constrained by the tower mechanism references, not a city-sized ML model. Represent windward descent, a near-ground outward/sideways flow, and the associated return circulation; mass projection enforces the final flux constraints. Examine momentum redistribution against reference vertical sections rather than adding an arbitrary uniform pedestrian speed increase.

Have influence zones propose vector corrections and combine them with an explicit, deterministic rule based on exposure and physical region. Smooth competing supports. Do not use last-writer-wins or repeated multiplicative attenuation. A new tower correction replaces the corresponding old tower contribution, rather than duplicating it.

**Arms.** On the winning E1 parent, use a 2 × 2 comparison: existing/new tower model × existing/new composition rule. Repeat the best tower/composition arm on the original background to identify interaction with E1. Limit to two predeclared tower-strength choices on mechanisms, then freeze one before the 35-run AIJ screen. If E1 fails, use the original baseline as the parent.

**Measurements.** Vertical flow on the windward face, direction and magnitude of ground jets, wake recovery, ΔK MAE and mean bias, negative-error tails, both sign recalls and strongest-speed-up recall. Report the contribution of the 89 baseline spurious decreases without selecting new favourable IDs after tuning. Verify that a scalar-speed gain is supported by mean-vector improvements in D and mechanism/reference fields; do not attribute every thermistor increase to downwash. If attenuation is the main source, use the one allowed revision to replace that term rather than adding a compensating positive zone.

**Pass.** The combined E1/E2 candidate must reduce full-matrix Case E ΔK MAE by at least 20% relative to the original baseline, achieve absolute mean ΔK bias at most 0.05, and reach balanced sign accuracy **≥0.82**, compared with the reproduced 0.768 baseline. Strongest-speed-up recall must increase by at least 0.10. Neither sign recall may fall more than 0.02, and error on measured decreases may not worsen by more than 5%; simply suppressing every negative prediction fails. Reduce MAE on the fixed spurious-decrease stratum by at least 20% as a diagnostic mechanism check, alongside the all-point gates. On tower mechanisms, reduce mean-vector RMSE by at least 20% and reproduce reference windward-flow and ground-jet directions. Preserve common guardrails and confirm at 1 m. Improvements to after-state rankings alone do not pass.

**Performance and app benefit.** Target at most 20% added native time over its parent, with no extra global fine-grid solve. Use cached exposure, spatial indexing and bounded correction supports. The intended app gain is a useful answer to “what does this new building change?” If a correction only works for one tower aspect ratio or violates paired intervention tests, stop expanding its template family. E5a is already running as an alternative; compare its evidence at the architecture decision.

### E2 implementation sketch and starting parameters

Use the background height from E1's descriptor pass. Define exposure as `H_exposed = max(H_tower - H_background, 0)`. Activate the new correction smoothly as `H_tower / H_background` rises from **1.5 to 2.0**; where there is no surrounding canopy, use a distinct isolated-building branch rather than dividing by an invented small height. Obtain incident wind above the surrounding roofs on the upwind side, outside the tower's existing correction zone.

| Parameter | First value | Allowed comparison |
| --- | --- | --- |
| Tower/background height activation | Smooth transition over ratio 1.5–2.0 | Fixed |
| Upwind incident sample location | One facade width upstream; height `H_background + 0.5 * H_exposed` | Use a small valid-fluid patch average, not one possibly solid cell |
| Windward-roll length `Lx` | `0.5 * H_exposed`, limited to `[0.5 W, 2 W]` | Fixed, W = exposed facade width |
| Roll height `Hz` | `H_tower` above local ground | Existing intervening solids remain impermeable |
| Crosswind envelope scale | `0.6 * W` | Fixed |
| Dimensionless roll amplitude | 0.10 | 0.10 versus 0.20 on mechanisms; freeze one before city screening |
| Zone overlap rule | Exposure-weighted proposals | Compare against original composition in the declared 2 × 2 matrix |

A useful first kernel is a windward recirculation roll generated from a vector potential. In local coordinates, x increases with the wind, the windward facade is x = 0, and z is height above ground. The kernel below occupies `-Lx < x < 0`, `0 < z < Hz`. It produces upstream motion near the ground and downward motion in the half nearer the facade, with a return circulation upstream/aloft.

```python
# Standalone prototype: E2 windward-roll contribution, local coordinates.
import numpy as np

def windward_roll(x, y, z, incident_speed, width, lx, hz, amplitude=0.10):
    if min(width, lx, hz) <= 0 or incident_speed < 0 or amplitude < 0:
        raise ValueError("Invalid roll dimensions, speed or amplitude")
    x, y, z = np.broadcast_arrays(x, y, z)
    xi = np.clip((x + lx) / lx, 0.0, 1.0)
    eta = np.clip(z / hz, 0.0, 1.0)
    inside = (x > -lx) & (x < 0) & (z > 0) & (z < hz)
    g = np.sin(np.pi * xi)**2
    dg = np.pi * np.sin(2 * np.pi * xi)
    h, dh = eta * (1 - eta), 1 - 2 * eta
    crosswind = np.exp(-0.5 * (y / (0.6 * width))**2)
    scale = amplitude * incident_speed * crosswind
    # A_y = amplitude * U * lx * g(xi) * h(eta) * crosswind.
    # curl(A_y e_y): u = -dA_y/dz, w = dA_y/dx.
    du = -scale * lx / hz * g * dh
    dw = scale * dg * h
    return np.stack((np.where(inside, du, 0.0),
                     np.zeros_like(du), np.where(inside, dw, 0.0)), axis=-1)
```

This is only the **windward-roll term**, not a complete tower model or a fitted result. The tangential velocity has an outer-height transition that E3 must blend; clipping by neighbouring solids also breaks the continuous divergence identity. In native code evaluate compatible staggered curls where practical, rotate into world coordinates, apply obstacle constraints and mass-project. Initially retain the baseline sidewall/corner and far-wake terms, replacing only the corresponding windward contribution. Inspect the resulting corner jets; do not count this small kernel as satisfying E2 without the three-dimensional reference tests. If an independently fitted corner/wake template is required, add it only through the one documented model revision, without adding amplitude search axes.

For overlap handling, have each zone provide a proposed **total velocity** and a nonnegative support/exposure weight. One bounded, order-independent starting rule is:

```python
# Standalone prototype: E2 composition rule at fluid samples.
import numpy as np

def combine_zone_proposals(background, velocities, weights):
    # background: (..., 3), velocities: (zones, ..., 3), weights: (zones, ...)
    background = np.asarray(background, dtype=float)
    velocities = np.asarray(velocities, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if np.any(weights < 0) or not np.all(np.isfinite(weights)):
        raise ValueError("Zone weights must be finite and nonnegative")
    total = weights.sum(axis=0)
    average = np.zeros_like(background)
    np.divide((weights[..., None] * velocities).sum(axis=0), total[..., None],
              out=average, where=total[..., None] > 0)
    coverage = np.minimum(total, 1.0)[..., None]
    return (1 - coverage) * background + coverage * average
```

Construct the new tower's total proposal as the canopy background plus its activated roll contribution, not as the already cavity-modified velocity plus another roll. Start exposure weights in [0, 1] from visible upstream facade fraction, multiplied by the zone's smooth support. Canonically accumulate proposals for reproducible floating-point results. Do not include both old and replacement windward proposals. In regions where averaging cancels the observed tower circulation, the rule has failed its mechanism test; deterministic averaging alone is not evidence of correct interaction physics. Track proposal weights and pre/post-projection contributions to diagnose that failure.

## 7. E3 — continuous zone edges and near-wall predictions

### E3a — test whether receptor flags are useful (F03, flag arm)

**Hypothesis.** A 2 m neighbourhood K span >0.15 within `max(1 m, dx)` identifies at least 80% of receptors whose synthetic application band changes between 2 and 1 m, while flagging fewer than 30% of all eligible receptors. This tests the usefulness of a warning, not physical accuracy.

Run first on stored E-before/after fields using E0b's two fixed climates. A receptor is flagged if any sector in that climate exceeds the span threshold; report that aggregation explicitly. Use the same complete-rose mask at both grids. Also report per-direction recall for |K_2m−K_1m|>0.05, precision, flagged fraction, wall-distance strata and lost probes. Recompute on the final parent; smooth fields must not create falsely reassuring flags. No threshold fitting in this round.

**Pass/stop and benefit.** Both 80% recall and <30% flagged fraction must hold in each E state and climate, then be checked on the independent families' refinement comparisons. With no class-changing receptors, recall is unassessed. If the fixed flag fails, retain span as a raw diagnostic only; do not claim useful detection or probabilities. Flag overhead must be ≤5% of sampling time and ≤1% of workflow time, with no additional flow solve in production. The app can then mark numerically sensitive receptors. Do not build the nine-member probabilistic-class ensemble: arbitrary model variants and two inspected sites cannot establish calibrated coverage.

For that transfer check, run the frozen QES candidate at 2 and 1 m for the 16-sector synthetic roses in each of the three families' two states: at most 192 QES runs, reusing overlapping confirmation/timing outputs. These compare numerical predictions with each other, not with new CFD truth, and do not expand the 45-run RANS budget. They are required only to promote the flag beyond the AIJ development cases.

### E3b — continuous treatment, conditional on the architecture decision

**Hypothesis.** Expressing zone transitions and near-wall profiles in physical coordinates will reduce grid-origin/refinement sensitivity without reducing genuine peak-speed accuracy.

**Why.** Case E receptors near façades remain sensitive at 0.5 m. Entrances and pavements need stable values, but smoothing a corner jet away could make the field look numerically better while making the app less useful.

**Arms.** Winning E1/E2 parent; continuous empirical-zone blending only; blending plus physical wall-distance evaluation of the near-wall profile. Use at most two transition-width laws tied to physical geometry scales, not a fixed number of cells. Evaluate the same laws under every grid refinement. Keep impermeable solid boundaries and reproject after initialization changes. Do not smooth the final speed map as a substitute for changing the velocity model.

Run these arms only if an empirical fast model or its initialization remains useful after E5a. The momentum solver uses its own wall stress; do not add this wall-law attenuation to a solved momentum field. If only the momentum path is retained, continue the numerical sensitivity checks without the E3b zone-development arms.

Test 2 and 1 m grids, plus small 0.5 m wall/tower mechanisms. On the wall mechanisms and the four-direction Case E subset N/E/SW/W, translate the grid origin by (0,0), (dx/2,0), (0,dy/2) and (dx/2,dy/2), keeping world geometry, bounds of the evaluation region and physical probes fixed. Report any outer-domain adjustment needed to align the grids. Treat grid-origin spread and refinement differences separately.

**Pass.** Reduce p95 receptor changes by at least 30% for both grid-origin shifts and 2→1 m refinement in near-wall/high-span strata. For the wall-law arm, physical near-wall speed MAE must improve by at least 10% **only against eligible references under §3.2**; without those references this arm remains unassessed and cannot be promoted as an accuracy improvement. For either arm, corner-jet peak and top-decile errors may not worsen by more than 5% where reference quality is established. Report excluded reference locations. Retain intervention and common guardrails. A continuous-zone-only candidate may pass numerical robustness and the global physical gates without claiming validated sub-metre wall speeds. A smaller neighbourhood span alone does not pass.

**Performance and app benefit.** Target at most 10% added native time and memory over the parent. Cache geometry-only distances; avoid all-building searches per cell. The benefit is more stable entrances, pavement receptors and design comparisons. If geometric stair-stepping dominates after this experiment, specify a separate cut-cell project; do not silently grow this round into a geometry rewrite. Recent QES cut-cell work supports that later option, but does not establish a cure for canopy or tower errors. [Bozorgmehr et al., 2025](https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2024MS004494)

#### E3b implementation sketch and starting parameters

Define signed distance to an empirical zone boundary as positive inside the zone. Use a smooth transition across a **physical** half-width epsilon. Compare `epsilon = clip(0.05 * H, 0.25, 1.5)` m with twice that width on mechanisms, then freeze one law for the three city arms. A 1 m grid and a 0.5 m grid must evaluate the same physical function.

```python
# Standalone prototype: E3 zone support and tangential wall law.
import numpy as np

def zone_weight(signed_distance, epsilon):
    if epsilon <= 0:
        raise ValueError("Transition half-width must be positive")
    t = np.clip((np.asarray(signed_distance) + epsilon) / (2 * epsilon), 0, 1)
    return t * t * (3 - 2 * t)

def wall_tangent_velocity(reference_velocity, unit_normal, distance,
                          reference_distance=2.0, wall_z0=0.001):
    # Reference velocity is sampled in fluid at a fixed physical wall distance.
    if wall_z0 <= 0 or reference_distance <= 0:
        raise ValueError("Wall lengths must be positive")
    reference_velocity = np.asarray(reference_velocity, dtype=float)
    unit_normal = np.asarray(unit_normal, dtype=float)
    tangent = reference_velocity - np.sum(reference_velocity * unit_normal,
                                         axis=-1, keepdims=True) * unit_normal
    d = np.clip(np.asarray(distance), 0.0, reference_distance)
    ratio = np.log1p(d / wall_z0) / np.log1p(reference_distance / wall_z0)
    return ratio[..., None] * tangent
```

The wall helper supplies only the tangential initialization term. Retain the parent field's normal component in fluid and enforce zero normal flux on the actual solid face. It replaces the corresponding empirical tangential wall contribution; multiplying an existing log-law result again would over-attenuate it. Do not overwrite the complete velocity vector with the helper's output.

| Parameter | First value | Treatment |
| --- | --- | --- |
| Reference wall distance | 2.0 m | Fixed across grids |
| Wall roughness | Existing `Parameterizations.wall_roughness`, 0.001 m by default | No tuning in E3 |
| Transition width | Geometry law above | Two mechanism choices, one frozen city law |
| Valid reference stencil | Fluid contributors only; same exposed facade | Reject ambiguous corners/opposite-wall crossings and record them |
| Grid-origin offsets | `(0,0)`, `(dx/2,0)`, `(0,dy/2)`, `(dx/2,dy/2)` | Same world probes and geometry |
| High-span diagnostic | K span > 0.15 within `max(1 m, dx)` | Retain existing definition |

Cache the nearest exposed facade and distance at affected cells only. At a narrow passage with no valid 2 m reference point, preserve the parent treatment and flag the unavailable correction; do not sample through the opposite wall. Report the skipped fraction by location. If most relevant receptors are skipped, this arm cannot claim broad near-wall improvement even if a favourable subset passes.

## 8. E4 — direction variability and turbulence, tested separately

### E4a — quasi-steady direction ensemble (F04)

**Hypothesis.** Directional variability explains a useful part of the scalar/vector observation gap without using the current QES-Turb field. Averaging speeds and averaging vectors across the same member fields gives distinct, testable predictions. This is an observation hypothesis and a sensitivity to approach direction, not a replacement for canopy/tower momentum.

**Entry and matrix.** After E0a and numerical qualification, first use the original mean-flow baseline at D 0°, where both instruments are available. Solve offsets `[-15, -7.5, 0, 7.5, 15]°`, with weights proportional to `exp[-offset²/(2*sigma²)]`. Declare sigma=10° primary and 5°/15° sensitivities; the sensitivities reweight the same fields and are not selected by best AIJ score. This is a truncated discrete distribution, not an exact Gaussian integral; record its actual variance. The directional spread needs independent inlet/meteorological justification before it becomes a physical app input. Without that evidence, results remain a directional sensitivity study.

Use identical geometry, speed profile, reference speed and numerical policy in every member. Transform vectors to the global frame before averaging. Let `M = sum(w_i U_i)`, `S = sum(w_i |U_i|)`. Compare M with measured vectors and S with thermistors, preserving the actual sensor component convention. Report the predicted scalar/vector gap and its relation to the 33 paired D observations; avoid unstable ratios at very low mean speeds.

```python
# Standalone prototype: members=(member, receptor, xyz), all in global coordinates.
import numpy as np

def direction_observables(members, offsets=(-15, -7.5, 0, 7.5, 15), sigma=10.0):
    u = np.asarray(members, dtype=float)
    offsets = np.asarray(offsets, dtype=float)
    if (u.ndim != 3 or u.shape[0] != offsets.size or u.shape[2] != 3
            or not np.isfinite(u).all() or sigma <= 0):
        raise ValueError("Use the common valid-receptor mask and positive spread")
    weight = np.exp(-0.5 * (offsets / sigma)**2)
    weight /= weight.sum()
    mean = np.einsum("m,mrc->rc", weight, u)
    scalar = weight @ np.linalg.norm(u, axis=2)
    deviation = u - mean
    covariance = np.einsum("m,mrc,mrd->rcd", weight, deviation, deviation)
    return mean, scalar, covariance
```

**Screen and pass.** Continue beyond D 0° only if primary-sigma scalar MAE improves by at least 10%, vector RMSE worsens by no more than 5%, and median direction error rises by no more than 3°. Then use the full 35-run matrix, at most 175 member solves before deduplication. Require ≥10% scalar MAE improvement separately on D thermistors, E-before and E-after, no loss of R beyond 0.02, and no degradation of intervention ΔK MAE or balanced accuracy beyond common guardrails (sign accuracy tolerance 0.02). Report q improvement of 0.04 as a supporting hypothesis, not a replacement for MAE. Keep vector controls and E0b application guardrails. Failure does not prove that small-scale turbulence caused the remaining discrepancy.

**Distribution/accuracy gate.** On D 0° and E-after SW, check one wider/finer rule, offsets −30°…30° every 3.75°, at primary sigma. Require p95 change ≤0.005 and max ≤0.02 in normalized scalar/vector estimates relative to the five-member approximation. If truncation or angular sampling changes the apparent gain materially, classify the cheap rule as inconclusive; do not silently substitute 17 production members. Freeze any independently supported spread before confirmation on new measurements; steady RANS references cannot validate a time-varying observation model by themselves.

**Cost and app benefit.** Reuse geometry and stream sampled member results; never retain five city volumes. Charge all solves and aggregation to one nominal-direction answer: target ≤30 s and cap 60 s for Case E at 2 m under §2.1; target ≤120 s and cap 180 s for the complex/detail tier. The enhanced-mode memory cap remains 8 GiB. A library of already-computed directions helps only when its angular coverage is adequate and its creation cost is reported. Do not convolve a climatic direction distribution again with variability already represented in it. No gust or calibrated probability claim follows from ensemble spread. If the baseline screen passes, allow one confirmation on the frozen improved fast parent; do not cross the ensemble with every physics candidate or E5.

Do not add E4b's total k to the ensemble variance: both may contain the same fluctuations. Any future combination must use independently justified conditional within-direction turbulence, with `Cov(total) = E[Cov(within direction)] + Cov(direction means)`. That combined model is outside this round.

### E4b — independent turbulence input and transport (F10)

**Hypothesis.** Separating incoming turbulence from ground roughness and transporting locally produced wake turbulence will improve the spatial k field. RMS speed may then be a better empirical instrument proxy, without retuning the mean velocity.

**Entry condition.** Run after a mean-flow candidate passes its mechanism gates, or test input decoupling alone on the baseline. It is not a prerequisite for E1/E2/E5a or E4a. Use one frozen, single-direction mean-flow parent, not the direction-averaged E4a field.

**Arms, in order.** (a) Existing QES-Turb; (b) independent inflow k(z)/stress reference and ground roughness with the existing spatial model; (c) the same reference plus one transported scalar k equation on fixed mean flow. Use the fixed mixing-length closure below. Incoming k is a boundary/reference condition, not a uniform addition that double-counts production. Stop before (c) if usable mean flow or stress-reference data is absent.

**Pass.** The input arm must reproduce upstream k within 10% without changing mean velocities. Transport must reduce in-city k MAE by at least 20% and raise spatial correlation by at least 0.20 relative to the corrected-input arm on D and available independent stress references. RMS-proxy scalar MAE must improve by at least 10% on paired D data, with no more than 5% regression on other scalar comparisons. Report raw mean-vector scores, tail errors and quantiles. If only k level improves, retain at most input decoupling; do not claim repaired turbulence physics. Independent stress evidence is needed for promotion of transport, not merely for its first prototype.

**Performance and benefit.** Target ≤20% added calculation time over the matched turbulent parent, within the combined fast-mode cap. Solve a scalar equation and evaluate proxies only at requested receptors/planes. This improves the inputs available to scalar-speed assessment, not gust maxima. Momentum feedback belongs to E5.

#### Settled observation audit: no quadrature development (F14)

Using the 33 measured Case D vectors and k values, reproduced on 2026-11-02:

| Estimate | MAE in K | q at D=0.25, W=0 |
| --- | ---: | ---: |
| Mean-vector magnitude | 0.1033 | 0.5152 |
| RMS speed | **0.0374** | **0.9091** |
| Isotropic Gaussian expected speed | 0.0477 | 0.8485 |

The Gaussian model does improve on the vector magnitude but fails the hypothesis that it beats RMS on these observations. This does not establish an instrument-response mechanism or universal superiority of RMS. Keep RMS explicitly labelled as a proxy and retain the scalar/vector bounds in §3.4. k alone fixes the covariance trace, not a velocity distribution; the closed form additionally assumes a 3D isotropic Gaussian. Noncentral-chi moments have closed-form treatments. [Lawrence, 2023](https://link.springer.com/article/10.1007/s13171-021-00262-3)

The following is a reproducible audit helper, not a new production feature or candidate. It handles zero mean and zero variance correctly; a direct `1/lambda` formula with a small denominator substitute does not give the zero-mean limit.

```python
# Standalone prototype: exact expected norm for an isotropic Gaussian only.
import numpy as np
from scipy.special import erf

def isotropic_gaussian_speed(mean_speed, k):
    mu, k = np.broadcast_arrays(np.asarray(mean_speed, float), np.asarray(k, float))
    if not np.isfinite(mu).all() or not np.isfinite(k).all() or np.any(mu < 0) or np.any(k < 0):
        raise ValueError("Finite nonnegative speed and k required")
    shape = mu.shape
    mu, k = mu.ravel(), k.ravel()
    out = mu.copy()
    active = k > 0
    sigma = np.sqrt(2 * k[active] / 3)
    lam = mu[active] / sigma
    value = np.empty_like(lam)
    small = lam < 1e-3
    value[small] = sigma[small] * np.sqrt(2 / np.pi) * (2 + lam[small]**2 / 3 - lam[small]**4 / 60)
    x = lam[~small]
    value[~small] = (sigma[~small] * np.sqrt(2 / np.pi) * np.exp(-0.5 * x*x)
                     + (mu[active][~small] + sigma[~small] / x) * erf(x / np.sqrt(2)))
    out[active] = value
    return out.reshape(shape)
```

No anisotropic quadrature or new sensor-distribution fitting is budgeted. Reopen this only with additional instrument-response or fluctuation evidence, not another score-tuning pass.

#### E4b transport implementation sketch and starting parameters


The current `wind.Turbulence` accepts only `mixing_length="height"|"wall_distance"`; it does **not** accept a k table or separate ground roughness. Add these as experimental native inputs, with provenance. The existing inflow readers already expose the measured arrays:

```python
# Existing data reader; the payload below is proposed, not a Turbulence API.
from aij.tables import load_inflow_e

table = load_inflow_e()
inflow_turbulence = {
    "source": "AIJ-E measured inflow",
    "heights_m": table.heights.tolist(),
    "k_m2_s2": table.k.tolist(),
    "covariance_assumption": "isotropic where only k is available",
}
```

Validate table units and heights against the readers, interpolate nonnegative k in physical height, and declare the below/above-table treatment. First retain the baseline ground-roughness value; varying it would confound the new inflow reference. Physical field measurements may later supply an independent ground value, but it is not a fitted turbulence knob here.

For the transported arm, use

\[
\partial_t k + \mathbf U\cdot\nabla k
= \nabla\cdot[(\nu+\nu_t/\sigma_k)\nabla k]
+ 2\nu_t S_{ij}S_{ij} - C_\epsilon k^{3/2}/\ell.
\]

Start with **no extra empirical wake source**: resolved mean shear already supplies production, including in wakes. If it is insufficient, record the missing production spatially rather than adding a source to match the total k. Keep the mean velocity fixed for this experiment.

| Parameter | First value | Numerical confirmation |
| --- | --- | --- |
| Scalar grid | 4 m horizontally; retain fine near-ground vertical layers | Compare selected mechanisms at 2 m |
| Mixing length | `min(0.4 * (z + z0_ground), 0.15 * H_local)` in canopy | Use an above-canopy continuation and wall distances; record floors |
| Eddy viscosity | `nu_t = 0.1 * ell * sqrt(k)` | Provisional one-equation closure |
| `sigma_k` / `C_epsilon` | 1.0 / 0.7 | Fixed, no additional city sweep |
| Advection | Conservative first-order upwind, CFL ≤ 0.5 | Bound diffusion implicitly |
| Dissipation | Implicit `C_epsilon * sqrt(k_old) / ell * k_new` | Avoid negative k without arbitrary clipping |
| Scalar iterations / relaxation | At most 60 / 0.5 | Double work on selected mechanisms |
| Stop checks | Relative equation residual ≤ 1e-3 and max monitored Δk / Uref² ≤ 1e-4 for 5 checks | Report non-convergence rather than returning a silent pass |

Use a fine-to-coarse flux restriction that preserves wall impermeability; a coarse cell must not connect streets separated by a solid wall. Preserve measured k on inflow faces and use declared outflow/ground boundary conditions. If 60 iterations cannot meet convergence, the transported arm fails. Exceeding the 20% time-overhead target fails the original fast tier, but a Case E candidate may still qualify under §2.1’s 60 s accuracy-for-time gate. Do not loosen tolerances to manufacture a pass. Reconcile the old QES stress caps with the new inflow reference explicitly; caps must be reported, not used to force agreement.

## 9. E5 — early momentum screening and a bounded enhanced mode

**Hypothesis.** Three-dimensional momentum transport can improve canopy and intervention magnitudes more directly than additional empirical zones, and a QES initial field may reduce the work needed to reach a credible answer within 60 s per direction for Case E at 2 m or 180 s in the complex/detail tier.

### E5a — early full-grid 2 m pilot (F11)

**Entry and purpose.** Start after E0's baseline/operator checks and a feasible repeated-projection implementation, alongside E1's cheap control and E2 attribution. Do not wait for E1–E3 to finish or fail. Cap this at one momentum prototype shared with E5b; do not start a neural surrogate or another solver backend. The first AIJ pilot does not require new external CFD results, but promotion does.

**Matrix.** Use the full 2 m horizontal AIJ grid: E SW/SSW/E/WSW in both states plus D's three directions = **11 cases**. These E directions were selected for large known measured changes and are explicitly development data. Add plain-inflow starts for E-after SW and D 0° = **13 histories**. Initialize the main runs from the frozen original QES field so the pilot can start before E1/E2 finish; later compare one shortlisted solver configuration with the best fast parent on all 35 cases. Match domain, discretization, closure and stopping between initialization arms, including the cost of obtaining the QES start.

Resolve momentum on the existing fine grid first, with conservative advection, turbulent diffusion, wall stresses and pressure correction. Avoid coarse-to-fine transfer and extra empirical wake corrections during this pilot. Use the table below, with no unresolved-building drag where geometry is explicitly resolved. Record roof representation and narrow-passage connectivity; a 2 m grid is a pilot resolution, not presumed sufficient. Allow up to **3 million cells** initially and the enhanced-tier memory cap. If adequate domain clearance or vertical layers exceed that size, report it and reduce to mechanisms before committing city work; do not truncate a relevant flow interaction.

**Iteration budget.** Examine checkpoints at 200 and 800 iterations from the same history, every 25 iterations for diagnostics. Use at most 2,000 iterations for longer mechanism/reference histories and the two initialization comparisons. Reaching a checkpoint or a flat probe curve is not convergence: require momentum residual, probe stability and pressure/flux checks. One overnight development campaign is acceptable, but Python prototype time and a hypothetical native time are reported separately.

**Screening gate.** Relative to the matched QES subset, require ≥15% lower ΔK MAE, ≥10% lower D vector RMSE, absolute mean E change bias ≤0.075, and no >5% regression in either E state's speed MAE. Preserve balanced accuracy and each sign recall within 0.02 of the subset baseline; do not import the full-matrix 0.768 into the selected subset. Inspect spurious negative changes and three-dimensional tower/canopy sections. Principal gains must persist with longer solves; no pass if they are transient numerical diffusion. Use E0b application gates only on complete roses at the later 35-run check.

**Warm-start hypothesis.** QES initialization reaches the same credible endpoint in at most half the momentum iterations of the plain profile. Compare actual total time too. If the physical screen passes but this warm-start hypothesis fails, momentum remains a possible backend, but the empirical initialization has not earned its complexity. Do not keep engineering zones solely for that unproven benefit.

**Architecture/cost gate.** Before E5b, require a credible budget from measured native momentum/projection kernels and measured setup/output costs, targeting ≤30 s for Case E at 2 m and ≤120 s in the complex/detail tier. An assumed nanosecond-per-cell work unit is insufficient. Full native end-to-end timing must subsequently meet the applicable 60/180 s cap and 8 GiB before promotion. If the early physical screen fails, stop this prototype after one documented numerical/model review; do not compensate with an open-ended closure search. If it passes, prioritize its all-direction validation over expanding tower templates.

### E5b — resolution, transfer and production qualification

**Entry.** Open only after E5a shows useful physical gains and a credible native cost. First implement/time the successful full-grid 2 m model. If it already meets the accuracy and latency need, keep that simpler architecture. A **4 m horizontal** momentum/transfer arm is justified only if it reduces measured cost or enables the 1 m detail output. Remove the former 8 m physical arm: it is a poor primary test of Case E's narrow streets. Horizontal spacing is distinct from vertical spacing; a 6 m building was not intended to fit in one 8 m vertical cell.

**Conditional transfer model.** The full-grid solver remains the control. For the 4 m arm, solve steady or pseudo-transient mean momentum with advection, turbulent diffusion and pressure coupling on the coarser 3D grid. Use fractional obstruction or a scale-aware drag treatment for unresolved buildings. Do not add full obstacle drag for buildings already resolved as impermeable surfaces. Initialize from QES; transfer a background/correction field to the fine grid; blend with unresolved local building effects; perform fine-grid mass correction. Separate the coarse resolved contribution from the fine empirical residual so the same wake is not represented twice.

Compare the 2 m pilot with the conditional 4 m arm on mechanisms using 200/800-iteration checkpoints from each history: at most four resolution/work comparisons, not four new closures. Check 1 m detail output on shortlisted cases. For 4 m, audit how much frontal area, height distribution and street connectivity are unresolved; do not allow one coarse fluid cell to join streets through a wall. If no admissible subgrid treatment preserves those constraints, reject the 4 m arm rather than treating lost buildings as open flow. Do not infer accuracy from residuals alone.

**Controls.** Best fast candidate; full coarse momentum solution before downscaling; transferred fine solution with/without local corrections. Compare selected reference-domain padding/top choices because a momentum solver need not tolerate the shallow QES baseline domain. Freeze any justified domain extension for all E5 arms and charge its cells and runtime to E5. A 2D horizontal solver is not an acceptable tower-flow substitute: vertical momentum transport is central to this hypothesis.

**Pass.** On the independent confirmation set, reduce vector RMSE and intervention ΔK MAE by at least 15% relative to the best fast candidate, with no family worsening by more than 5%. Pass the final intervention gates and applicable workload time/memory limits, including the Case E 60 s accuracy-for-time gate. Retain the gains after increasing momentum solve work and refining its grid; if the remaining numerical uncertainty is comparable to the gain, classify the result as inconclusive. Compare with the reference solver's directly measured runtime too: a complicated hybrid is not justified if it offers no meaningful accuracy/cost advantage.

Before confirmation, use the dense aligned canopy and 60 m tower mechanisms at 0° for the declared second-order advection check, half-time-step check and tighter pressure tolerance. Require at least 75% of the original vector/intervention error reduction to remain where those metrics exist, with no new guardrail failure. Otherwise classify the apparent physical gain as numerically unresolved and stop promotion. These are numerical confirmations of one closure, not new city tuning candidates.

**App benefit and cost.** An explicitly selected enhanced mode for exposed towers, mixed heights and difficult street interactions. Show elapsed time and assessment status; do not promise fast-mode latency. Stop if the credible solution exceeds the applicable deadline (60 s for Case E at 2 m; 180 s for complex/detail cases) or 8 GiB, or if downscaling recreates the original errors. A failed E5 is evidence for using an external validated CFD workflow on those geometries. Fast momentum-solving urban approaches have precedent, but their reported speed is not a timing forecast for this implementation. [QUIC-CFD](https://scholarworks.boisestate.edu/mecheng_facpubs/21/), [CityFFD](https://www.sciencedirect.com/science/article/abs/pii/S2212095521002935)

#### E5 shared implementation sketch and starting parameters

E5a starts on the 2 m pilot grid and records its vertical resolution. For the E5b 4 m arm, use vertical spacing at most **1 m below 15 m**, then 2 m to 30 m, growth **1.15** above that to at most 8 m. Require at least four vertical layers across the representative low canopy, refining further when needed. Limit the 4 m prototype to **two million total cells**. The 8 m vertical cap aloft is not an 8 m street-resolution arm. If justified domain enlargement exceeds a prototype budget, report it rather than cropping away the interaction.

| Parameter | First value | Allowed comparison |
| --- | --- | --- |
| Horizontal spacing | 2 m full grid | Conditional 4 m transfer; 1 m confirmation on shortlisted cases |
| Outer momentum work | Checkpoints at 200 / 800 | Up to 2,000 on declared longer reference/initialization histories |
| Advective CFL | 0.4 | Numerical control only |
| Momentum discretization | Conservative upwind initially; implicit diffusion/drag | Diagnose diffusion at 2/4 m; one second-order check on mechanisms before promotion |
| Turbulent viscosity | Fixed mixing-length law; update `nu_t = ell_eff² * sqrt(2*S:S)` from the current velocity each outer iteration | Under-relax viscosity by 0.5; no coupled two-equation model or closure sweep |
| Unresolved-building drag coefficient | 1.0 | Fixed; zero for obstacles represented entirely by resolved impermeable faces |
| Pressure correction | New flux-consistent operator; relative residual ≤ 1e-4 | Check physical divergence after every correction |
| Momentum stop checks | Relative residual ≤ 1e-3 and max probe ΔU/Uref < 0.005 for 5 checks | Both required; an iteration/deadline exit is not convergence |
| Fine-grid composition | Coarse correction plus retained unresolved fine residual | Compare with coarse-only transfer on mechanisms |

For the pilot, obtain `ell_eff` from the existing geometry-only wall-distance mixing-length calculation, with its exact definition recorded. `TURBGeneralData::Lm` already includes the von Kármán factor; multiply raw `WINDSGeneralData::mixingLengths` by 0.4 once if exporting that field instead. Do not multiply Lm by 0.4 again. Add molecular viscosity 1.5e-5 m²/s and record any extra viscosity floor; none is a tuning axis. Keep this same closure and boundary data in both initialization arms; updating shear gives the same target equations for either start. A closure requiring an in-city measured k field is inadmissible.

E5a uses a completed QES field for its explicit warm-start comparison, charging that solve. For the conditional E5b transfer arm, use the unprojected best empirical initial field and project its restriction on the coarse grid, avoiding a redundant complete fine solve. Compare with a completed-QES start on mechanisms; do not silently change the initialization in the timing comparison.

The following **proposed integration** assumes an `ops` object that implements staggered finite-volume advection, implicit diffusion/drag, gradient, divergence and pressure correction. These methods do not exist in the current Python API:

```python
# Proposed integration: one momentum/projection step, kinematic pressure p.
def momentum_step(velocity, pressure, dt, eddy_viscosity, drag_rate, ops):
    # One global scalar dt; a local dt requires a different weighted operator.
    rhs = (velocity - dt * ops.advection(velocity)
           - dt * ops.gradient(pressure))
    predictor = ops.solve_implicit_diffusion_drag(
        rhs, dt=dt, viscosity=eddy_viscosity, drag_rate=drag_rate)
    # Solve D G phi = D(predictor) / dt with consistent flux boundary data.
    phi = ops.solve_pressure_correction(ops.divergence(predictor) / dt)
    corrected = predictor - dt * ops.gradient(phi)
    return corrected, pressure + phi
```

Here pressure has units m²/s² and `drag_rate = C_d * a_f * |U_old|` has units s⁻¹. Resolve obstruction consistently: the divergence/gradient operators must share fluid volumes, open-face fractions and boundary conditions. Do not use the old QES Lagrange multiplier directly as this pressure, or assume its weighted mass-correction stencil is already the required pressure operator. Reuse storage and solver infrastructure only after verifying the discrete operator pair.

Use one global time step for the first prototype. A local pseudo-time step would require `D(dt_face G phi) = D(predictor)` and the corresponding face-weighted correction; the scalar-dt sketch cannot be reused unchanged. Enforce prescribed inlet flux through the correction boundary conditions, not by resetting velocities after projection. Freeze a pressure gauge/outlet condition and verify boundary flux after every step. Do not cap pressure work at two Krylov iterations if the divergence gate is unmet.

P0 qualifies reproduction of the QES mass projection; it does not qualify these different momentum boundary conditions. Before city momentum runs, verify empty-profile preservation with a consistent inflow/ground treatment, a manufactured divergence/gradient problem, and an impermeable obstacle with fixed inlet flux. Require the same dimensionless divergence floors and solid-flux limits as P0, and check the complete momentum residual at steady state.

To avoid double-counting, transfer the difference from the coarse representation of the same initial field:

```python
# Proposed integration: R = consistent restriction, P = prolongation.
coarse_initial = R(fine_empirical_initial)
coarse_final = solve_coarse_momentum(coarse_initial)
fine_candidate = fine_empirical_initial + P(coarse_final - coarse_initial)
fine_final = project_mass_with_solid_boundaries(fine_candidate)
```

The target consistency check is `R(fine_candidate) ≈ coarse_final`; establish its tolerance on mechanisms. Otherwise a nominal correction can duplicate a resolved wake or leave the coarse flow unrealized. Preserve unresolved fine geometry through the final solid-boundary projection. Inspect how much that projection changes tower downwash and near-ground jets.

Use a single workload-specific end-to-end deadline with provisional E5b transfer allocations; for full-grid E5a, unused transfer budget can fund iterations while preserving measured output/margin reservations:

| Stage | Case E 2 m: within 60 s | Complex/detail: within 180 s |
| --- | ---: | ---: |
| Loading/preparation and empirical initialization | 8 s | 25 s |
| Coarse momentum iterations | 35 s | 100 s |
| Transfer and final fine mass correction | 12 s | 40 s |
| Requested turbulence, sampling and output | 3 s | 10 s |
| Scheduling/termination margin | 2 s | 5 s |

These allocations are profiling targets; the total cap is authoritative. At entry to the coarse solve, reserve measured time for transfer, fine projection and requested outputs. If coarse convergence cannot fit the remaining budget, return an explicit unassessed outcome. The current `Solver.max_solve_seconds` covers a narrower native solve scope; a proposed workflow controller or parent-worker deadline is required to enforce the end-to-end cap. A post hoc `elapsed < deadline_seconds` assertion alone cannot prevent a long-running request.

## 10. Execution limits and combined-model decision

### 10.1 Keep the search small

1. **Foundation:** E0a/b, baseline audit, E3a stored-data flags, E0c and P0. Freeze the manifests, observables, gates and finite matrices. Run E0e's three ratios separately; E0f opens only when profiling identifies a budget need. New reference generation can proceed independently of these screens.
2. **Early architecture screen:** E1a, E2 attribution and E5a's 13 histories alongside each other. Start the small E4a D test once its input/parity prerequisites are ready. Do not wait for completed zone engineering to decide whether momentum is promising. Concurrency here describes independent research tasks; timed benchmarks remain serial with four threads.
3. **Bounded empirical work:** at most five E1 mechanism candidates and three E1 city candidates. E2 permits its two strengths on mechanisms, then the declared 2×2 composition comparison and one original-background interaction check. Across E1/E2, at most **eight distinct new initialization configurations** may reach the full 35-run city screen, excluding the original baseline and stored negative controls; duplicate parents do not count twice. One documented model revision total is allowed within this cap. Stop expanding zones if the early momentum evidence makes them unnecessary.
4. **Selected architecture:** E3b tests at most three arms and two transition widths on mechanisms, freezing one width before city runs. E3a's optional independent flag confirmation adds at most 192 QES runs and no new CFD references. E5b uses at most four resolution/work comparisons and **two city solver configurations**; iteration checkpoints do not create new tunable models. Allow one second-order scheme check on the two declared mechanisms, not another discretization sweep. Use 0.5 m only on small mechanisms in this round.
5. **Optional observations/turbulence:** E4a uses five members, three reweightings, one 17-member numerical check on two declared cases, and at most two parents (original diagnostic parent and one frozen improved fast parent). A successful improved parent gets the full 175-member matrix; a failed D screen stops its expansion. E4b uses only its three arms on one frozen single-direction parent. No cross-product with E4a, E5, multiple roughness choices or sensor distributions.
6. **Confirmation:** select one fast physical candidate and, if justified, one enhanced physical candidate. Freeze coefficients and numerical policies, perform 1 m checks, then expose the independent experimental/reference errors and run full timing sweeps. Optional E4a/E4b capabilities keep their own evidence gates; they are not required for promotion of a mean-flow improvement. Report failures as well as wins.

Use one global coefficient set per candidate. Directional coefficients must be functions of declared geometry/flow features, not direction labels. No site IDs, measurement coordinates or measured before/after differences may enter model inputs.

Research campaigns may run overnight, and offline references may cost much more than application inference. Record both costs. Do not confuse total experimental effort with per-direction product latency.

### 10.2 Final gates

The final candidate must satisfy the following together. They are deliberately stronger than “one metric improved” and are proposed development gates, not a claim of comfort compliance.

| Gate | Required result |
| --- | --- |
| Mean-vector improvement | D vector RMSE at least 15% below original baseline; median horizontal direction error at most 30°; report low-speed exclusions separately without removing them from vector RMSE |
| Dense-district improvement | E-before and E-after speed MAE each at least 15% below baseline, with R/ρ falling by no more than 0.02; interpretation still includes the instrument mismatch |
| Intervention skill | ΔK MAE at least 20% below baseline; absolute mean change bias at most 0.05; balanced sign accuracy ≥0.82 (baseline 0.7680); neither sign recall falls >0.02; measured-decrease MAE does not worsen >5%; strongest-speed-up recall at least 0.10 above baseline |
| Transfer | At least 10% improvement in mean-vector RMSE against the independent reference fields, macro-averaged across the three families, with no family worse by more than 5%; new experimental case C's matched speed MAE must not worsen by more than 5% |
| Numerical robustness | Principal gains persist at 1 m, with acceptable iteration error and impermeable walls; any selected E3b module passes its targeted sensitivity gate; physical wall/peak claims use only eligible references |
| Application decisions | E0b exceedance MAE and false-negative guardrails hold in both climates/states, against both the matched parent and original baseline; observation proxies are identified |
| Optional capabilities | E3a flags, E4a ensemble or E4b transport pass their individual gates before those capabilities are promoted; no probability, gust or near-wall accuracy claim beyond available evidence |
| Cost | Selected mode satisfies its absolute timing and memory limits; fast mode also satisfies the matched compute-overhead cap, except that qualifying Case E 2 m candidates may use up to 60 s under §2.1's accuracy-for-time gate |

Compute the final AIJ gates on the complete fixed 35-run matrix. For matched reference fields, use mean-vector speed for ΔK; for AIJ E, retain the scalar label. For independent before/after references, also require improvement in ΔK MAE over the original baseline in every family; E5 has the additional 15% gain over the best fast model specified above.

For a new physical mean-flow candidate, evaluate the dense-district and intervention gates using its raw mean-vector output against the historical thermistors, retaining the mismatch label, and show any scalar proxy separately. For E4-only capability claims, keep the physical parent fixed and use the declared observable-specific gates; a better proxy score alone cannot pass this table's mean-flow gates. Record both the baseline quantity and candidate quantity in every comparison. Whole-plan success does not require every optional module to pass.

Use paired uncertainty intervals to assess whether apparent gains are stable. A threshold crossing driven by a few locations or one direction, with a gain interval spanning zero, is inconclusive rather than a clear pass. Report uncertainty on the small experimental sample; do not manufacture statistical power from dense neighbouring CFD cells.

If only some modules pass their targeted tests, retain them as opt-in experimental components and state the narrower evidence. Do not weaken gates after viewing results. If only bias improves while intervention/transfer fails, the empirical model has not demonstrated the desired app-level advance. If the enhanced model passes, preserve both speed/accuracy choices with explicit provenance. None of these outcomes alone establishes regulatory or gust qualification.

## 11. Implementation and evidence deliverables

Reuse the validation framework rather than creating a second competing harness:

- Extend [runspec.py](validation/aij/runspec.py) with versioned experiment/model settings and parent identities; include every coefficient, cache-relevant setting and closure in fingerprints. Give new experiments a separate schema/version so historical cached runs cannot be mistaken for new evidence.
- Add finite matrices beside [campaigns.py](validation/aij/campaigns.py), paired/intervention and synthetic-climate metrics beside [metrics.py](validation/aij/metrics.py), and stage/timing records through [runner.py](validation/aij/runner.py). Hash nominal direction, member offsets/weights and actual member profiles separately; do not overwrite records that share a nominal label. Existing campaign names and baseline outputs remain reproducible. Archive the 2026-11-02 baseline sign/magnitude and measured sensor audits with exact masks, W=0 for the sensor table, source hashes and scripts; do not treat scratchpad results as new held-out evidence.
- Put mechanism/confirmation manifests and reference provenance under a proposed `validation/physics/` package, with generated records under `validation/output/physics/`. These are proposed additions, not existing commands or APIs.
- Put physical initialization work near [WINDSGeneralData.cpp](src/qes_core/winds/WINDSGeneralData.cpp), [PolygonWake.cpp](src/qes_core/winds/PolygonWake.cpp), [UpwindCavity.cpp](src/qes_core/winds/UpwindCavity.cpp) and [wind_runner.cpp](src/qes_core/dtcc/wind_runner.cpp). E0c–f touch solver policy/operator qualification; E4a touches direction orchestration and sampling; E4b touches turbulence inputs/stages. E5 needs an explicit momentum module, not more mass-solver sweeps.
- Add meaningful invariance tests: empty flow, speed scaling in neutral conditions, geometry/flow rotation on comparable grids, uniform geometric scaling at fixed normalized inflow/roughness, input-order invariance, solid flux, and cold/warm parity. Check k scaling with squared inflow speed, zero-spread ensemble identity, `|mean U| ≤ mean |U|`, analytic synthetic-climate limits, and P0 parity. Separate discretization tolerances from exact identities. Do not spend major model-development effort on an order effect already below numerical significance.
- Every experiment report includes hypothesis, frozen configuration list, parent, primary/secondary metrics, per-case regressions, failed candidates, numerical uncertainty, runtime/RSS, and a pass/fail/inconclusive decision with an explanation.

For the app, carry numerical status, physical model identity, tested geometry scope and receptor sensitivity separately. A spatial span is not a calibrated confidence interval, and solver convergence is not physical correctness. Flag exposed towers and unsupported morphology from geometry independently of whether the resulting wind map appears sheltered. More stable sampling and clearer limitations are useful product improvements even before a new physical model passes.

## 12. Deliberately deferred work

- **General ML replacement:** keep learned residuals as a later alternative if E1/E2 establish which corrections are missing. The [FLUME work](https://arxiv.org/abs/2503.19708v3) and [UrbanTALES dataset](https://journals.ametsoc.org/view/journals/bams/aop/BAMS-D-25-0061.1/BAMS-D-25-0061.1.xml) offer useful directions, but training-data generation, periodic-versus-finite-domain mismatch and whole-neighbourhood holdouts deserve their own experiment. Do not add a training programme to this round.
- **Full cut-cell integration, vegetation, terrain and buoyancy:** relevant future capabilities, but they do not isolate the present flat-ground canopy and tower failures.
- **Universal solver optimization:** beyond E0c/f's bounded SOR and conditional CPU multigrid tests, defer general solver redesign. Measured cost must motivate it; theoretical work counts alone do not establish speed.
- **Calibrated class probabilities, sensor-distribution fitting and gust/comfort certification:** synthetic E0b decision tests, E3a flags and the E4a ensemble do not establish these. Additional independent fluctuation, instrument and application evidence is required. The Gaussian sensor comparison is already negative relative to RMS and does not justify quadrature work.

The spending decision after this round is concrete: retain the empirical architecture if its frozen corrections improve interventions and unseen layouts; offer a momentum-assisted mode if it supplies further accuracy within the applicable 60/180 s per-direction budget; otherwise keep QES explicitly exploratory and direct difficult decisions to an independently validated solver.

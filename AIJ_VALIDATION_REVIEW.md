# Review of the AIJ validation, and where dtcc-qes should go next

- **Date:** 2026-11-02
- **Reviewed:** [`validation/AIJ_VALIDATION.md`](validation/AIJ_VALIDATION.md) (dtcc-qes `c9e31e8`, native policy `b26d15fd`), with `validation/DTCC_REQUESTS.md` and the native sources under `src/qes_core/winds/`.
- **Reviewer:** Claude
- **Asked for:** an honest opinion of the tool and its future. Can it be made more useful and more accurate without a large performance cost, or has the approach reached its limits? The state of the art was surveyed for this review (section 3).
- **Evidence levels:** each claim is marked as one of three kinds:
  - from the validation, cited by its phase;
  - from the code, cited as `file:line`;
  - from the literature, with sources at the end. Some sources were read only as abstracts, and some are not peer-reviewed; these are flagged.
  
  Judgements and estimates are labelled as such.

## Verdict

1. **The validation is careful, and its conclusion is right.** dtcc-qes is not accurate enough for wind comfort studies that inform decisions. I would qualify the report in two ways.
   - **The q ≥ 0.66 line is out of reach on Case E even for steady RANS.**
     - The realistic target is parity with RANS: per-direction R of 0.6–0.85 (Hågbo & Giljarhus 2022) and a hit rate of perhaps 0.3–0.6 (not peer-reviewed; section 3).
     - Against that target, the gap in level and pattern is smaller than "0.16 against 0.66" suggests.
     - The gap in the effect of the new tower is larger: change R 0.41, against about 0.8 for RANS (not peer-reviewed).
   - **"Useful for fast screening" is too generous for the case that matters most.**
     - Screening for tall buildings needs few false negatives. The model's error there is a false negative: it predicted a slowdown where the tunnel measured a speed-up.
     - Its screening value is real for sheltering in low-rise fabric and for relative comparisons of massing without towers. It is unproven, or negative, for towers.
2. **The diagnostic core has reached its limits for pedestrian comfort; the tool has not.**
   - The two errors that matter, the missing slowdown in the canopy and the missing speed-up around the tower, are both **momentum effects**. A mass-consistent adjustment cannot produce them (section 2).
   - Phase 5 already showed that flags and global settings move the level, not the pattern. More flags would not change that.
   - Everything around the solver is sound and reusable:
     - the geometry pipeline, grids and samplers;
     - the comfort chain;
     - a validation harness that scores a new idea in minutes.
3. **What I would do, in one paragraph.**
   - First, run a RANS reference through the same harness, so that "good" has a number in this setup.
   - Then prototype, outside the native code, a **momentum-relaxation step that starts from the Röckle field**: a QUIC-CFD-style simplified RANS that reuses the Poisson solve.
   - In parallel, replace SOR with **multigrid**, which pays for that step.
   - Use high-fidelity CFD of many layouts (IBOFlow at Fraunhofer-Chalmers, public LES datasets) as reference and training data for a **learned residual correction** on top.
   - Two missing parameterizations, a canopy-aware background (R17) and a tall-building amplification zone, are the fallback if the momentum step proves too slow. They are not the main line.
   - **Expected result (judgement):** near-RANS accuracy at about 10× today's CPU cost per direction, which multigrid and the CUDA backend can largely win back.

## 1. The validation: what it shows and how much weight it bears

**What is unusually good about it.**
- **Numerics are separated from physics.** It checks iterative convergence at the probes, runs a grid study down to 0.5 m, and reports per-probe grid sensitivity with a one-run predictor (the span).
- **It measures the instrument ceiling** (0.52) instead of hiding it.
- **The tuning protocol was declared before the first run.** It used a train/test split and reports a negative transfer result.
- **Every number is reproducible and tracked per revision.**

Few published validations of fast urban wind models are this rigorous. The literature search found no published pedestrian-level validation of QES-Winds at all (section 3).

**Points I would weigh differently.**

1. **The reference line.**
   - On Case E, steady RANS (realizable k-ε) reaches q ≈ 0.30–0.41 against the mean vector speed. Against the scalar speed √(U²+2k) it reaches 0.47–0.61 (Eddy3D AIJ validation, SW wind only; not peer-reviewed).
   - Peer-reviewed per-direction R is 0.61–0.84 (Hågbo & Giljarhus 2022).
   - VDI 3783-9's q ≥ 0.66 comes from simple obstacle cases.
   - The headline should say how far dtcc-qes is from RANS, with VDI as context, not the other way round.
2. **Statistical resolution.**
   - The Case D split-fibre q of 0.27 rests on 33 points. Its 95 % binomial interval is ±0.15, so "0.27 → 0.21" in Phase 5 is one or two points.
   - The 1,280 Case E values are spatially correlated and come from 16 correlated directions, so their effective sample size is much smaller.
   - Case D conclusions should be stated as directions, not as numbers.
3. **A trivial baseline is missing.**
   - Phase 1's model-free upwind-blockage index (largest height ÷ distance on a 60 m upwind ray) is a fair floor.
   - I scored it like for like against the 2 m baseline (script in the session scratchpad, not in the repo):

   | Case E, per-direction Spearman ρ with the measurements | dtcc-qes, median (range) | −blockage, median (range) | Directions where dtcc-qes is better |
   |---|---|---|---|
   | Before (low-rise district) | 0.57 (0.33–0.67) | 0.47 (0.36–0.62) | 11 / 16 |
   | After (with the 60 m tower) | 0.48 (0.24–0.73) | 0.20 (0.06–0.56) | 16 / 16 |

   - In the low-rise district, the full model ranks probes only modestly better than a one-line geometric index.
   - With the tower it is clearly better, because the index cannot represent anything non-local.
   - This is encouraging and humbling at once. The solve adds value where the flow is non-local, and that is exactly where better physics will pay.
   - It also says that morphometric features carry much of the signal, which matters for the ML option (section 4, D).
4. **No end-use metric.**
   - The 80 × 16 measured Case E values can be combined with a wind climate to give measured comfort classes per point. A Weibull rose is enough; a Niigata station record is better.
   - Scoring class agreement and false negatives at the windy points answers "is it fit for comfort studies" directly. The Weibull example in the report only illustrates the sensitivity.
5. **The hit rate rewards level.**
   - Phase 5 showed that compression alone triples q.
   - Add a decomposition of the mean-square error into bias, amplitude and pattern (or a Taylor diagram) to the headline, so that a future model change cannot score by flattening the field.
6. **No RANS run in the harness.**
   - Without a RANS run on the same geometry, inflow, probes and metrics, every comparison with the literature mixes pipelines.
   - This is the single most useful addition (section 5, step 0). It would also give full-field error maps showing *where* dtcc-qes goes wrong, not only how often.

## 2. Why the model fails where it does

**What the solver can and cannot do.**
- The mass-consistent step returns the initial field plus the gradient of a multiplier. The variational weights are fixed at α1 = α2 = 1 (`src/qes_core/solver/solver.h:195`).
- The result is the divergence-free field closest to the initial guess. It moves volume flux around obstacles. It has no momentum, no pressure and no drag.
- It therefore produces speed-ups only where continuity forces flux through a smaller section.

**The two first-order errors follow from that.**

| Finding | Mechanism | Can a new parameterization fix it? |
|---|---|---|
| **Level:** E "before" is overpredicted; probes outside every zone keep the approach profile (Phase 3) | A built-up area slows the near-ground flow by drag and blockage. In the model, nothing slows the air outside the building zones, so the approach profile survives. | Partly. A morphometric background (R17) imposes the slowdown kinematically. It is an empirical substitute for drag. |
| **Tower effect:** measured mean ΔK +0.10 against −0.02 simulated (Phases 3–5) | Downwash in front of the tower and corner streams carry high-momentum air from aloft to street level, driven by the pressure field. | Only empirically. No element of the current set produces a speed-up. The high-rise flag only changes the wake length (`src/qes_core/winds/PolygonWake.cpp:159-179`). The only tall-building scheme in the QUIC literature (Nelson et al. 2008, HMVP) only decelerates. |

**Two secondary problems.**
- **Grid sensitivity that does not converge (Phase 4):**
  - The zones are binary regions snapped to cells, and overlapping zones are resolved by precedence.
  - A probe near a zone edge jumps when the edge moves by one cell, as point 25 does (0.40, 0.12, 0.53).
  - This is a property of the parameterizations, not of the solver.
- **Turbulence pattern R ≈ 0:**
  - QES-Turb is a local mixing-length closure on the diagnostic field (`src/qes_core/winds/TURBGeneralData.cpp:447-473`). Its strain is largely the artefact of zone edges.
  - **This weakness is shared:** steady RANS also fails the Case D k pattern (R −0.14; not peer-reviewed).
  - So this is not where dtcc-qes falls behind its peers. Gust screening should not wait for a better k.

**Phase 5 is consistent with this picture.** Every global knob moved the level, and none improved R or ρ. The pattern is fixed by the mechanisms the model lacks.

## 3. State of the art

The survey covered diagnostic models, fast hybrid CFD, RANS/LES/LBM, ML surrogates and uncertainty quantification. Full texts were sometimes unavailable. "(np)" marks a source that is not peer-reviewed or is a vendor claim.

**Diagnostic models (QUIC-URB / QES-Winds lineage).**
- Development since 2010 has been mostly numerical, notably a GPU SOR solver (Bozorgmehr et al. 2021: 10 km² at 1–3 m in under a minute). There were few new parameterizations.
- **Oklahoma City field data** (Neophytou et al. 2011), share of points within 50 % in speed and within 30° in direction:

  | Model | Speed | Direction |
  |---|---|---|
  | Röckle-type diagnostic | 49 % | 43 % |
  | LES | 53 % | 50 % |
  | RANS | 62 % | 58 % |

  The diagnostic model is not far behind on a real city.
- Hayati et al. 2017 found that QUIC-URB, RANS and LES all made wakes too coherent in step-down canyons.
- **Three gaps no published work fills:**
  - a downwash or corner-stream parameterization;
  - data-driven calibration of the Röckle constants;
  - an in-canopy, drag-based background in a diagnostic model. QUIC-URB has only an urban log-law inflow option.

**Hybrid fast CFD.**
- **QUIC-CFD** (Gowardhan et al. 2011) is a simplified RANS: explicit projection with a zero-equation mixing-length closure, reusing the SOR Poisson solve without full convergence each step.
  - It is about 10× slower than QUIC-URB and orders of magnitude cheaper than full CFD: about 20 min for 2 M cells on one core in 2012 (np).
  - It captured urban flow features that QUIC-URB missed.
- **WindNinja**, for terrain, saw the same split: a momentum solver clearly beat mass conservation on windward and lee slopes (Wagenbrenner et al. 2019).
- **GRAL**, a simplified prognostic model, passes the VDI 3783-9 cases (Oettl 2015).

**Steady RANS on the AIJ cases.**
- **Blocken, Stathopoulos & van Beeck 2016**, summarising the AIJ cross-comparison: about 10–20 % accuracy where speeds are amplified, and up to 5× underprediction in wakes. Discomfort is dominated by the amplified zones, so a model that gets the speed-ups right is useful even if its wakes are poor.
- **Hågbo & Giljarhus 2022:** Case E with realizable k-ε gives R 0.61–0.84 per direction.
- **Eddy3D AIJ validation (np):**
  - Case E SW: q 0.41 / 0.30 (before / after) against the vector speed, and 0.61 / 0.47 against the scalar estimate.
  - Change R 0.83.
  - Case D: q 0.39–0.70, R 0.80–0.85, and k pattern R −0.14.

**LES / lattice Boltzmann on GPUs.**
- **Throughput:** FluidX3D reports 5.6 GLUPs/s on an RTX 4090 and 17.6 GLUPs/s on an H100 (np). Its licence excludes commercial use.
- **Resolution:** pedestrian-wind LBM-LES needs a spacing of about b/32 for building width b (Han, Ooka & Kikumoto 2020). For Case E's small buildings that means 0.5 m or finer, about 10⁸ cells.
- **SimScale/Pacefish on Case E (np):** ~100 M cells, 5–10 h, R 0.70–0.86.
- **Within DTCC:** Fraunhofer-Chalmers' **IBOFlow** is an immersed-boundary octree solver with GPU parallelisation. It was validated against wind-tunnel data for urban flow (Vanky et al. 2024), and its urban work acknowledges DTCC.

**ML surrogates.**
- **Geometry-to-wind networks** (Kastner & Dogan 2023; Wang et al. 2025; Snaiki et al. 2026 on the public UrbanTALES LES set of ~500 layouts at 1 m) run in milliseconds. Their weaknesses:
  - they are scored against their own CFD, never against a wind tunnel;
  - they struggle in dense layouts and smooth out peaks and jets.
- **Commercial tools** (Forma rapid wind, Infrared.city, Orbital Stack AI) present themselves as screening tools (np).
- **Residual correction is the relevant line.** Nowak et al. 2025 (Fraunhofer-Chalmers, *Diff-KNN*) add a nearest-neighbour model trained on fine-minus-coarse residuals to a coarse CFD on AIJ Case E. That cut the error by 57 % against the coarse CFD (target: fine CFD).
  - Zhao et al. 2024 warn that **cruder baselines are harder to correct**.

**Gusts and uncertainty.**
- **Gust equivalent mean (GEM):** mean + g·σ, with peak factors g from 1 to 3.5 in use. Vita et al. 2020 question the peak factor itself.
- **Inflow uncertainty can dominate:**
  - a 729-run RANS ensemble bracketed field data at 13 of 13 stations for speed (García-Sánchez et al. 2014);
  - one year of wind-climate data can shift comfort ranks by up to three levels (Kikumoto et al. 2021).
- No comfort standard issues probabilistic classes. That is an opening for a fast model, which can afford ensembles.

## 4. Options, by cost

**Reference cost:** Case E at 2 m takes 7 s per direction, of which about 4 s is geometry preparation and about 3 s the solve with turbulence (Phase 2). Cost factors below are relative to the solve.

### A. Numerics and outputs (no physics change, ≤ 1×)

**A1. Multigrid for the Poisson solve.** This is the enabler.
- **Today:**
  - SOR needs 2,000 sweeps at 2 m, 6,000 at 1 m and 16,000 at 0.5 m: about 4× per halving (Phase 2; R14).
  - ω = 1.78 is well below optimal for grids with hundreds of cells per side, and the kernel is bandwidth-bound (measured 2026-10-28 on a 9.4 M-cell tower case).
- **The change:**
  - Geometric multigrid, or multigrid-preconditioned CG, needs a roughly resolution-independent 10–30 cycles. It handles irregular solid masks well (McAdams et al. 2010).
  - The stretched vertical grid needs semi-coarsening or z-line smoothing; hypre's structured multigrid solvers handle that.
- **Estimate (judgement):** 10–50× fewer sweep-equivalents at 1 m and below.
- **Effects:**
  - 1 m costs what 2 m costs today, which matters for near-wall receptors (Phase 4).
  - R14 is solved by construction.
  - It frees the budget for C1.
- **A cheaper first step:** retune ω, or add Chebyshev acceleration, for perhaps 2–4×.
- **Cost of the change:** both alter the native policy identity and need re-qualification.

**A2. Honest output.**
- R16, the neighbourhood range on samples, flags grid-sensitive receptors.
- Comfort classes become probabilistic over a small ensemble: inflow profile variants, ±5–10° of direction, and the positional range.
- Because K is linear in the inflow speed, each member is one solve.
- Phase 5 found that a positional tolerance of one neighbourhood moves q as much as all the tuning did. That uncertainty belongs in the output, not hidden.

**A3. A quasi-steady direction ensemble for the scalar speed. This is a hypothesis.**
- **The idea:**
  - The thermistor gap (Phase 1) comes from fluctuations. Near the ground, the low-frequency part is largely meandering of the wind direction.
  - Averaging |U| over solves at θ ± σθ (σθ ≈ 10–15°) fills in wakes that are too sharp and lowers peaks, as a scalar-speed instrument sees them.
  - The spread across members is also a cheap low-frequency gust proxy that does not depend on QES-Turb.
- **The test:** Case D at 0° with 5–7 sub-directions, against both instruments, in under a minute of compute. It would not fix the Case E level.

### B. Missing parameterizations (≈ 1–1.5×; native)

**B1. R17, specified physically.**
- **Per cell outside the building zones:**
  - Compute λp, λf and the height spread over an upwind, fetch-weighted footprint of 100–300 m.
  - Derive zd and z0 with Kanda et al. 2013. The height spread matters: methods without it underestimate in more than 95 % of London cases (Kent et al. 2017).
  - Grow an internal boundary layer from the edge of the built-up area, so that the open approach keeps the approach profile.
  - Attenuate down to pedestrian height. The pedestrian-level ratio regressed on λp over 22 Japanese neighbourhoods (Kubota et al. 2008) is a ready-made cross-check for Case E. Macdonald's exponential is the textbook option, but Castro 2017 shows such profiles are rarely exponential.
- **Why it suits the acceptance test:**
  - It is direction-aware and derived from morphology.
  - It needs no per-case constant, which is what R17's acceptance test demands.
  - It should treat Case D's open plaza and Case E's dense fabric differently. The domain-wide canopy inflow of Phase 5 could not.

**B2. A tall-building amplification zone.**
- **The zone:** for buildings much taller than the local canopy (H/H̄_local ≳ 2), impose in the initial field:
  - corner streams on the windward corners;
  - the base vortex ("Wise effect") with its ground-level jet;
  - passage jets under or between towers.
- **Starting amplitudes and extents** come from Gandemer 1975 and Wise. The corner amplification is about 1.4 for a 35–45 m tower and 2.2 for one of about 100 m, reaching sideways about one building width.
- **The solver then redistributes the flux.**
- **It fills a gap** in the QUIC/QES lineage.
- **Calibration:**
  - Calibrate on isolated-building data, such as AIJ Case B (a 4:4:1 prism), Tsang et al. 2012, or LES.
  - Test on Cases D and E, which stay held out. Calibrating on D and testing on E repeats Phase 5's single-case risk.

**B3. Smooth zone edges** (R16, native part).
- Blend overlapping zones with weights that fall off over a cell or two, instead of binary masks with precedence.
- This targets the non-asymptotic probe jumps of Phase 4.

**Expected ceiling of B (judgement):**
- B1 should close much of the Case E level error.
- B2 could fix the sign of the tower effect.
- The pattern would still be bounded by kinematics: I would guess R ≈ 0.6, not 0.8.
- Each new zone adds constants and more zone-edge sensitivity. This is the path QUIC took for 20 years, and it has diminishing returns.

### C. A momentum step (≈ 10× on CPU, much less with A1 and GPU)

**C1. Momentum relaxation from the Röckle field (QUIC-CFD style).**
- **Starting point:** the diagnostic field, which is a far better initial condition than the inflow profile.
- **Each pseudo-time step:**
  - explicit advection, upwind or TVD;
  - eddy viscosity from the mixing length QES-Turb already computes;
  - log-law wall functions on building faces and the ground;
  - a projection with the existing Poisson operator, warm-started and loosely converged.
- **What it gains:**
  - Drag and blockage then slow the canopy flow without a background parameterization. This makes B1 largely redundant.
  - Pressure-driven downwash and corner streams appear without B2.
- **Cost estimate (judgement):**
  - At 2 m with Δt ≈ dx/U, a few flow-throughs from a good start take 1,000–3,000 steps.
  - With one multigrid cycle per step, that is roughly 10× today's solve: 20–40 s per direction, or 5–10 min for 16 directions on a CPU. This is consistent with the literature's ~10×.
  - On a GPU it should be faster than today's CPU solve.
- **Risks:**
  - Mixing-length RANS on a 2 m grid will have its own errors.
  - Wall functions on stair-stepped cells need care.
- **Target:** parity with RANS, not more.

**C2. A frozen-velocity k transport.** It is cheaper than C1, but RANS itself does not get the k pattern. Low priority.

### D. Data-driven corrections (≈ 1× at inference)

**D1. A residual correction on the physics output.**
- **Inputs:**
  - the dtcc-qes (or C1) speed-up;
  - zone masks;
  - wind-aligned morphometric features:
    - the blockage index at several fetches;
    - λp and λf in upwind windows;
    - distance and bearing to taller buildings, normalised by their height;
    - local H/H̄.
- **Target:** the high-fidelity speed-up.
- **Model:** start with gradient-boosted trees on probe features, which need far less data and stay interpretable, before trying U-Nets.
- **Training data:**
  - UrbanTALES (public LES);
  - IBOFlow runs on DTCC cities and on the four synthetic neighbourhoods already in `docs/urban-wind-benchmarks.md`;
  - generated layouts.
- **The AIJ cases never enter training.** Section 1, point 3, shows the features carry signal. Diff-KNN shows the method on Case E itself.
- **Do C or B first:** a better baseline is easier to correct (Zhao et al. 2024).

**D2. Learned parameterization constants.**
- **Fit:** fit the Röckle constants jointly over many cases, as functions of local morphology, with leave-one-case-out validation. The constants include the wake length coefficients, the cavity strength and the B1/B2 coefficients.
- **Differs from Phase 5:** many cases, physically meaningful parameters, cross-validation.
- **Status:** no published precedent.

### E. A high-fidelity tier (10–100× on GPU)

- **For decision-grade answers,** a study needs LES or RANS meeting the AIJ and COST guidelines.
- **Use an existing solver before building one.** IBOFlow is developed by a DTCC partner.
- **If an in-house GPU tier is wanted later,** lattice Boltzmann is the natural fit for the planned CUDA backend:
  - simple kernels, bandwidth-bound like SOR;
  - gusts come out directly.
- **The cost:** b/32 resolution means ~10⁸ cells for Case E, minutes to hours per direction on one GPU. That is a different product tier, not a replacement.

## 5. Recommended sequence

Each step has a gate scored by the existing harness. That keeps the work honest, as Phase 5 did.

| Step | Work | Effort (judgement) | Gate |
|---|---|---|---|
| 0 | RANS reference through the same probe pipeline: Case E at 4 directions in both states, and Case D at 0°, with OpenFOAM or IBOFlow. Add the blockage baseline, the end-use comfort-class metric and the error decomposition to the report. | 1–2 weeks | A RANS row in the headline table. Error maps show where dtcc-qes departs from RANS. |
| 1 | **Prototype C1 in Python** on the 2 m output. NumPy for the momentum step and pyamg for the projection, with no native change and so no re-qualification. | 2–4 weeks | On Case E at 4 directions: does the tower change get its sign, and does the "before" level drop? Does Case D hold? How many pseudo-steps does it take? |
| 2 | A1 multigrid, native (CPU first, then the CUDA backend). | 1–2 months | Bit-level regression of the converged fields; the iteration count independent of resolution. |
| 3a | If step 1 passes: C1 native on the multigrid projection. | 2–3 months | RANS parity on the step 0 metrics at ≤ 10× today's cost. |
| 3b | If step 1 fails or is too slow: B1 and B2 native, with B3. | 1–2 months | R17's two-case acceptance test, extended to change sign. B2 calibrated on non-AIJ data. |
| 4 | D1 residual correction, once a training corpus exists. | Open-ended | Improvement on the held-out AIJ cases, not on the CFD test split. |
| Ongoing | Broaden validation: AIJ A (2:1:1), B (4:4:1), C (block array) and F (Shinjuku), and a European perimeter-block case. | — | Conclusions stated per morphology. |

**Why C1 comes before B1/B2 even though it costs more:**
- If it works, it fixes both first-order errors with one mechanism and no new constants.
- If it fails, the prototype has still produced the evidence of where momentum matters, and that is where the B zones belong.
- Doing B first risks a year of parameterization work that C1 then makes redundant.

## 6. What I would not do

- **Tune flags per project, or add more flags without new physics behind them.** Phase 5 settled this.
- **Optimise the hit rate by compressing the field.** This needs a score that separates level from pattern (section 1, point 5).
- **Make a geometry-to-wind neural network the core of the product.** It learns CFD errors, cannot be checked against physics, and fails in dense fabric. Use ML only as a correction on a physical baseline.
- **Build an in-house LES before a RANS reference exists in the harness.**
- **Spend effort on the k pattern before the mean wind is right.** RANS does not get it either.
- **Expect much from the α1/α2 ratio.** It only chooses between flow over and flow around obstacles. One cheap sensitivity run at most.

## 7. Sources

Peer-reviewed unless marked (np). Sources marked † were read as abstracts or secondary summaries only.

- Blocken, Stathopoulos & van Beeck 2016, *Build. Environ.* 100:50–81. doi:10.1016/j.buildenv.2016.02.004
- Bozorgmehr et al. 2021, *Environ. Model. Softw.* 137:104958. doi:10.1016/j.envsoft.2021.104958
- Castro 2017, *Boundary-Layer Meteorol.* doi:10.1007/s10546-017-0258-x †
- Eddy3D AIJ data validation (np): <https://github.com/Eddy3D-Dev/AIJ-Data-Validation>, <https://aij.eddy3d.com>. The q figures came via the literature search and were not found on the landing pages.
- Gandemer 1975, 4th Int. Conf. Wind Effects on Buildings, 423–432; NBS TN 710-9 (1978) †
- García-Sánchez, Philips & Gorlé 2014, *Build. Environ.* †
- Gowardhan, Pardyjak, Senocak & Brown 2011, *Environ. Fluid Mech.* 11:439–464. doi:10.1007/s10652-011-9211-6 †
- Hågbo & Giljarhus 2022, *Front. Built Environ.* 8:858067. doi:10.3389/fbuil.2022.858067
- Han, Ooka & Kikumoto 2020, *J. Wind Eng. Ind. Aerodyn.* 206:104277 †
- Hayati et al. 2017, *Boundary-Layer Meteorol.* 164:217–247. doi:10.1007/s10546-017-0245-2 †
- Kanda et al. 2013, *Boundary-Layer Meteorol.* 148:357–377. doi:10.1007/s10546-013-9818-x
- Kastner & Dogan 2023, *Build. Environ.* 242:110384. doi:10.1016/j.buildenv.2023.110384 †
- Kent et al. 2017, *Boundary-Layer Meteorol.* 164:183–213. doi:10.1007/s10546-017-0248-z †
- Kikumoto, Choi & Ooka 2021, *Build. Environ.* doi:10.1016/j.buildenv.2020.107419 †
- Kubota et al. 2008, *Build. Environ.* 43:1699–1708. doi:10.1016/j.buildenv.2007.10.015 †
- Macdonald 2000, *Boundary-Layer Meteorol.* 97:25–45
- McAdams, Sifakis & Teran 2010, "A parallel multigrid Poisson solver for fluids simulation on large grids", SCA 2010
- Nelson et al. 2008, AMS conference paper (HMVP high-rise scheme) †
- Neophytou, Gowardhan & Brown 2011, *J. Wind Eng. Ind. Aerodyn.* 99:357–368. doi:10.1016/j.jweia.2011.01.010 †
- Nowak et al. 2025, "Diff-KNN: Residual correction of baseline wind predictions in urban settings", *Mach. Learn. Knowl. Extr.* 7(4):131. doi:10.3390/make7040131
- Oettl 2015, *J. Wind Eng. Ind. Aerodyn.* 142 †
- SimScale/Pacefish AIJ validation (np, vendor) †
- Snaiki et al. 2026, *Build. Environ.* 294:114354 (arXiv 2510.27101; UrbanTALES) †
- Tominaga et al. 2008, *J. Wind Eng. Ind. Aerodyn.* 96:1749–1761. doi:10.1016/j.jweia.2008.02.058 (cases A–G)
- Tsang, Kwok & Hitchcock 2012, *Build. Environ.* 49:167–181. doi:10.1016/j.buildenv.2011.08.014 †
- Vanky et al. 2024, IBOFlow urban wind evaluation: <https://research.chalmers.se/publication/542738> †
- Vita et al. 2020, *J. Wind Eng. Ind. Aerodyn.* 203:104200 †
- Wagenbrenner et al. 2019, *Atmosphere* 10:672 †
- Wang et al. 2025, *Build. Environ.* 269:112426 †
- Yoshie et al. 2007, *J. Wind Eng. Ind. Aerodyn.* 95:1551–1578. doi:10.1016/j.jweia.2007.02.023 †
- Zhao et al. 2024, *Sustain. Cities Soc.* 112:105607. doi:10.1016/j.scs.2024.105607 †

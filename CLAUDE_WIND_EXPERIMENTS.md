# Wind model experiments

- **Date:** 2026-11-02 (rewritten the same day into two groups, then revised after a cross-check with `QES_PHYSICS_MODEL_EXPERIMENTS.md`)
- **Basis:**
  - [`AIJ_VALIDATION_REVIEW.md`](AIJ_VALIDATION_REVIEW.md) proposes the ideas tested here.
  - [`validation/AIJ_VALIDATION.md`](validation/AIJ_VALIDATION.md) holds the evidence and the harness.
  - [`QES_PHYSICS_MODEL_EXPERIMENTS.md`](QES_PHYSICS_MODEL_EXPERIMENTS.md) is a parallel plan. Section 5 lists what was adopted from it and where this document disagrees.
- **Author:** Claude
- **Status:** design only. Nothing here has been implemented or run.

**Purpose.** This document gives every idea from the review a concrete experiment. Each experiment has:
- a falsifiable hypothesis;
- the reason for testing it;
- how a positive result would improve dtcc-qes;
- a performance budget;
- a design and a decision rule, fixed before any run;
- code showing how to set it up.

The hypotheses and thresholds are pre-registered. A change after the first run is logged here with its date and reason, as Phase 5 of the validation did.

## How the experiments are grouped

| | **Group 1: fast, inside dtcc-qes** | **Group 2: heavy, with outside tools and validation** |
|---|---|---|
| Needs | dtcc-qes, the validation harness and the AIJ Case D/E data already in `validation/` | At least one of: an external CFD solver (OpenFOAM, IBOFlow, a lattice Boltzmann code); new external measurements; a generated training corpus; a cluster or a GPU |
| May also use | A short-lived debug branch of dtcc-qes, and pure-Python libraries (pyamg replaces a solver; it is not an outside tool) | Data licences, collaborators (Fraunhofer-Chalmers for IBOFlow) |
| Compute per experiment | Minutes to one night on the workstation | Days to weeks, offline |
| Scored against | The existing AIJ measurements | New references: RANS/LES fields, more wind-tunnel cases, held-out corpora |
| Purpose | Decide quickly which ideas deserve investment | Establish the realistic target, calibrate, and test generalisation |

**Three ideas span both groups.**

| Idea | In Group 1 | In Group 2 |
|---|---|---|
| Tall-building zone | Literature constants | Calibration |
| Momentum relaxation | A screening run on 11 directions | Full scale, at 1 m and against RANS |
| Multigrid | The Python prototype | — (the native version is a product follow-up, section 3) |

Group 1 runs first. Its results decide which Group 2 experiments are worth their cost. The exception is the RANS reference (H01), which has a long lead time and is the yardstick for all of Group 2, so it starts at once.

**Development data versus confirmation data.** Cases D and E have been inspected in depth, and Phase 5 tuned on Case E "before", so neither is an untouched test set any more.
- Group 1 uses them to *screen* ideas.
- Promoting a model change also needs untouched data from Group 2: the new AIJ cases (H02), the mechanism matrix (H08) and the intervention transfer set (H09).

## Contents

0. [Common ground](#0-common-ground): performance targets, cases and data, statistics
1. [Group 1: fast experiments inside dtcc-qes](#1-group-1-fast-experiments-inside-dtcc-qes)
   - [1.0 Infrastructure](#10-infrastructure): harness, debug branch, Python projection with gate P0, morphometry, simple-case benchmark
   - F01 end-use metrics
   - F02 SOR relaxation
   - F03 grid flags and probabilistic classes
   - F04 direction ensemble
   - F05 variational weights
   - F06 multigrid prototype
   - F07 canopy background
   - F08 tall-building zone (literature constants)
   - F09 smooth zone edges
   - F10 turbulence transport
   - F11 momentum relaxation (screening)
   - F12 preparation reuse
   - F13 stage attribution of the tower effect
   - F14 observation operator (done: negative)
2. [Group 2: heavy experiments with outside tools](#2-group-2-heavy-experiments-with-outside-tools-and-validation)
   - [2.0 Infrastructure](#20-infrastructure): CFD pipeline, external data, compute
   - H01 RANS reference
   - H02 more AIJ cases
   - H03 tall-building calibration
   - H04 momentum at scale and against RANS
   - H05 residual correction
   - H06 learned constants
   - H07 GPU lattice Boltzmann
   - H08 mechanism matrix
   - H09 intervention transfer set
3. [From experiments to product](#3-from-experiments-to-product)
4. [Schedule and decisions across the groups](#4-schedule-and-decisions-across-the-groups)
5. [Cross-check with QES_PHYSICS_MODEL_EXPERIMENTS.md](#5-cross-check-with-qes_physics_model_experimentsmd)

## Summary

### Group 1

| ID | Idea (review section) | Main hypothesis, in one line | Compute | Code change |
|---|---|---|---|---|
| F01 | End-use metrics (§1) | Ranking variants by hit rate disagrees with ranking them by comfort-class agreement | none (stored runs) | validation only |
| F02 | SOR relaxation (A1) | A better ω halves the iterations at 1 m | ~1 h | small, debug branch |
| F03 | Grid flags, probabilistic classes (A2) | The span flag catches ≥ 80 % of class changes; a raw ensemble is under-dispersive | ~1 h | validation only |
| F04 | Direction ensemble (A3) | Averaging over ±σθ improves the thermistor scores without hurting the split fibre | ~30 min | validation only |
| F05 | α1/α2 (§6) | Null test: the weight ratio is not a lever (≤ 0.03) | ~10 min | Python prototype |
| F06 | Multigrid prototype (A1) | The AMG-CG iteration count stays flat as the grid is refined, at ≤ 1/10 of SOR's work at 1 m | ~2 h | Python prototype |
| F07 | Canopy background, R17 (B1) | A morphometric background passes R17's two-case acceptance test with no fitted constant | ~1 h | Python prototype |
| F08 | Tall-building zone, literature constants (B2) | Corner and base-vortex zones with Gandemer/Wise constants turn the predicted mean tower effect positive and raise strongest-speed-up recall | ~1 h | Python prototype |
| F09 | Smooth zone edges (B3) | Blended edges bring the 1 → 0.5 m probe changes within budget | ~3 h | small, native branch |
| F10 | k transport (C2) | Transported k has a better pattern than local equilibrium (R ≥ 0.3) | ~30 min | Python prototype |
| F11 | Momentum relaxation, screening (C1) | Starting from the Röckle field, a simplified RANS fixes the tower-effect magnitude and the low-rise level, within budget at 2 m | one night | Python prototype |
| F12 | Preparation reuse (from QES_PHYSICS E0) | Preparing once and solving every direction is bit-identical and cuts a 16-direction Case E study by ≥ 40 % | ~30 min | Python, in dtcc-qes |
| F13 | Stage attribution (from QES_PHYSICS E0/E2) | Tracing the tower's contribution through each zone and the projection shows where its speed-ups are lost | ~1 h | debug branch |
| F14 | Observation operator (from QES_PHYSICS E4) | **Done, refuted:** the Gaussian expected speed matches the thermistors worse than the RMS speed | none (measured data) | validation only |

### Group 2

| ID | Idea (review section) | Main hypothesis, in one line | Outside requirement | Compute |
|---|---|---|---|---|
| H01 | RANS reference (§1, step 0) | RANS beats dtcc-qes by ≥ 0.15 in per-direction R, and most of the difference sits in two regions | OpenFOAM, a cluster | ~11 runs × 1–3 h on 16–32 cores |
| H02 | More AIJ cases (§5) | The two failure mechanisms appear in isolation on simple cases | AIJ data (Eddy3D or AIJ), licence | seconds per run |
| H03 | Tall-building calibration (B2) | A calibrated zone matches isolated towers within ±20 % and reproduces the tower effect on held-out Case E | H01 tooling or H02 data | ~6 RANS runs, then minutes |
| H04 | Momentum at scale and against RANS (C1) | The relaxed field matches RANS within 0.05 in R, and reaches 1 m within the ceiling | H01 results, longer compute | ~1–2 days |
| H05 | Residual correction (D1) | A correction trained on non-AIJ high-fidelity CFD improves the held-out AIJ scores | A training corpus (RANS/LES) | ~3,000 core-hours |
| H06 | Learned constants (D2) | Constants calibrated on many cases improve every held-out case | Multi-case references (H01–H03) | ~10 h search |
| H07 | GPU LBM tier (E) | LBM-LES at 1 m reaches R ≥ 0.7 within 5 min per direction | A GPU, an LBM code, the CUDA backend | GPU hours |
| H08 | Mechanism matrix (from QES_PHYSICS §3.3) | Controlled canopy, tower-in-canopy and wall cases reproduce the two failures in isolation and give development references away from D and E | OpenFOAM, a cluster | ~15 RANS runs |
| H09 | Intervention transfer set (from QES_PHYSICS §3.2) | A promoted candidate predicts the effect of an added tower in three unseen districts better than the baseline | OpenFOAM, a cluster | 24 RANS runs |

**Mapping from the first version of this document:**

| Old ID | New ID |
|---|---|
| EX-01 | F01 |
| EX-02 | H01 |
| EX-03 | H02 |
| EX-04 | F02 |
| EX-05 | F06 (prototype) + section 3 (native) |
| EX-06 | F03 |
| EX-07 | F04 |
| EX-08 | F07 |
| EX-09 | F08 (literature constants) + H03 (calibration) |
| EX-10 | F09 |
| EX-11 | F05 |
| EX-12 | F11 (screening) + H04 (scale and RANS) |
| EX-13 | F10 |
| EX-14 | H05 |
| EX-15 | H06 |
| EX-16 | H07 |
| — | F12, F13, F14, H08, H09: adopted from `QES_PHYSICS_MODEL_EXPERIMENTS.md` (section 5) |

## 0. Common ground

### 0.1 Performance targets

Every experiment is judged on accuracy *and* cost. The targets come from the request: complex cases must run in a few minutes per direction, and simple cases in seconds.

**Reference machine:** the validation workstation, an Apple M4 Pro with 14 cores, in float32 unless stated.

| Class | Example | Today, end to end per direction | Target | Hard ceiling |
|---|---|---|---|---|
| Simple | One building or a small group, ≤ 1 M cells at 2 m (section 1.0.5) | ~1 s | ≤ 5 s | 10 s |
| District, standard | Case D/E at 2 m (1.8–2.6 M cells) | 3–7 s | ≤ 30 s | 60 s |
| District, fine | Case D/E at 1 m (13–19 M cells); the "mixed downtown" benchmark at 2 m (6.3 M) | 31–37 s | ≤ 2 min | 3 min |
| District, very fine | Case D/E at 0.5 m (100–142 M cells) | 440–642 s (**fails today**) | ≤ 3 min | 5 min |

- **Memory (peak RSS):** ≤ 2 GiB for "standard" and ≤ 8 GiB for "fine", adopted from QES_PHYSICS §2.1; ≤ 32 GiB for "very fine".
- **Today's numbers:** from Phases 2 and 4 of the validation.
- **Studies:** a study needs 16–36 directions. A ceiling of a few minutes per direction therefore means 1–2 hours for a fine 36-direction study, which is the outer limit of what is acceptable.

**Cost accounting.** Prototypes run in Python and are slower than native code. They are judged on two numbers:
1. **The measured prototype time.** It only needs to be practical for the experiment.
2. **An estimate for a native implementation, in work units (WU).** One WU is one red-black SOR sweep over the grid. It costs about **1.0 ns per cell** in today's float32 kernel: 9.1–9.6 ms per sweep on the 9.4 M-cell tower case, measured 2026-10-28. For Case E at 2 m (1.8 M cells), one WU is about 1.8 ms. Today's 2,000 sweeps then take about 3.6 s, which matches the measured solve.

An idea whose native estimate breaks the hard ceiling for its class is rejected or redesigned, whatever its accuracy. This applies in both groups. Group 2's offline tools (RANS, training) are not app features, so they are exempt. Anything Group 2 proposes to *ship* is not.

**Timing protocol for promotion** (adopted from QES_PHYSICS §2.2). Screening may rely on the WU estimate. Promoting a change needs measured timings:
- full 16-direction sweeps, and the 32-run Case E comparison, not one favourable direction;
- cold workflows and warm workflows, reported separately:
  - cold: a fresh process, including imports, preparation and output;
  - warm: the same process, with the preparation reused (F12);
- 4 threads, with one direction at a time. The SOR kernel is bandwidth-bound and flat beyond 4 threads (solver measurements of 2026-10-28), so this costs little and makes timings comparable across machines;
- the median, p95 and maximum over three repetitions, with no run removed;
- peak RSS, including caches.

### 0.2 Cases and data

| Use | Group 1 | Group 2 |
|---|---|---|
| Test cases | AIJ Case D (3 directions) and Case E (16 directions × 2 states), at 2 m with the baseline settings of `validation/aij/campaigns.py`; main effects confirmed at 1 m | The same, plus H02's cases |
| Held out from all fitting | Cases D and E. Group 1 fits no constant, so this holds by construction. | Cases D and E are never used to choose a constant in H03, H05, H06 or H07. |
| Calibration and diagnosis | — | AIJ Cases A, B, C and F (H02); the mechanism matrix (H08); the `industrial_residential` synthetic neighbourhood of `docs/urban-wind-benchmarks.md`, with RANS fields |
| Confirmation only, never used for development | — | The intervention transfer set (H09): `perimeter_neighbourhood`, `slab_estate` and `mixed_downtown`, each with and without an added tower |
| Simple-case performance | A synthetic single prism built with dtcc-core (section 1.0.5); it needs no measurements | The same |

### 0.3 Statistics and decision rules

1. **Uncertainty.** Every score difference is reported with a 95 % paired bootstrap interval.
   - It resamples probe points, keeping all directions of a point together, because those values are correlated. For change scores it also keeps both states of a point together, and mirrored Case D copies go with their source point.
   - An "improves" claim needs the lower bound of the interval above zero.
   - A "does not degrade" claim needs the lower bound above the stated tolerance.
2. **Resolution.** Phase 4 sets a floor: differences in pooled scores below 0.03 are grid noise, so thresholds are set above it.
3. **No compression.** The hit rate rewards a flattened field (Phase 5). Every gate therefore also requires two things:
   - a regression slope of simulated on measured of at least 0.7;
   - an R no lower than the baseline's.
4. **One setting for all cases.** Per-case constants fail a gate, as R17 requires.
5. **Metrics.** If F01 confirms H1a, every later gate in both groups also reports class agreement and the false-negative rate at windy points.
6. **Intervention metrics** (adopted from QES_PHYSICS §3.4).
   - **Plain sign agreement cannot tell the model from a trivial predictor.** On the 863 clear Case E changes (|ΔK| > 0.04), 634 are increases. Measured 2026-11-02 on the stored 2 m baseline:

     | Predictor | Sign agreement | Recall of increases | Recall of decreases | Balanced accuracy |
     |---|---|---|---|---|
     | dtcc-qes 2 m baseline | 0.729 | 0.685 | 0.852 | **0.768** |
     | Always increase | 0.735 | 1.000 | 0.000 | 0.500 |

   - **Strongest-speed-up recall** compares, per direction, the ten largest measured increases with the ten largest predicted changes. It is 0.60 for the baseline (median over directions).
   - **Gates on the tower effect** therefore use ΔK MAE, mean ΔK bias, balanced accuracy and strongest-speed-up recall, never plain sign agreement.
   - **The baseline gets the direction of most changes right.** Its failure is the magnitude: a mean ΔK of −0.02 against +0.10 measured, driven by a cluster of spurious strong wake decreases. The gates are set accordingly.

## 1. Group 1: fast experiments inside dtcc-qes

Each Group 1 experiment runs on the workstation, from minutes up to one night. It is scored against the AIJ measurements already in `validation/`. Its code lives in two places:
- `validation/experiments/` for the experiments;
- `validation/proto/` for Python prototypes of model changes.

Neither place touches `src/`. The exceptions are the debug branch (section 1.0.2) and F09's native branch. Neither is merged without re-qualification.

### 1.0 Infrastructure

**New dependency:** `uv add --group validate pyamg`. The user approved a `validate` group for validation libraries.

#### 1.0.1 Experiment harness

Some variants only post-process stored runs. They become "pseudo-records": copies of run records with one probe quantity replaced. These go through `aij.compare` and `aij.metrics` unchanged, so every experiment is scored by exactly the validation's code.

```python
# validation/experiments/harness.py
"""Shared plumbing for CLAUDE_WIND_EXPERIMENTS.md: keys, pseudo-records, scoring, bootstrap, cost."""
import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from aij import compare, metrics
from aij.runspec import RunSpec

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "output" / "runs"
OUT = ROOT / "output" / "experiments"
NS_PER_CELL_SWEEP = 1.0e-9  # s per cell per red-black float32 sweep, M4 Pro (section 0.1)


@dataclass(frozen=True)
class Variant:
    experiment: str      # "F04"
    name: str            # "sigma10"
    params: tuple = ()   # sorted (name, value) pairs, part of the key

    def key(self, base: RunSpec) -> str:
        text = json.dumps(dict(e=self.experiment, v=self.name, p=list(self.params), base=base.key),
                          sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]


def with_probe_values(records: dict, values: dict, quantity: str = "K") -> dict:
    """Copies of run records, keyed (case, state, label), with one probe quantity replaced."""
    out = {}
    for key, value in values.items():
        record = copy.deepcopy(records[key])
        record["probes"][quantity] = [float(v) if np.isfinite(v) else None for v in value]
        out[key] = record
    return out


def comparisons(records: dict) -> dict:
    """Comparison name -> aij.compare.Comparison, for the mean-vector speed-up K."""
    found = compare.case_d(records, quantities=("K",)) + compare.case_e_comparisons(records, quantities=("K",))
    return {c.name: c for c in found}


def _slope(s, m):
    s, m = metrics._pairs(s, m)
    return float(np.polyfit(m, s, 1)[0])


SCORES = dict(
    q=metrics.hit_rate, r=metrics.pearson, rho=metrics.spearman, slope=_slope,
    fb=lambda s, m: float((np.nanmean(m) - np.nanmean(s)) / (0.5 * (np.nanmean(m) + np.nanmean(s)))))


def paired_bootstrap(a, b, score="q", n=2000, seed=0) -> dict:
    """score(b) - score(a) with a 95 % interval, resampling points together with all their directions."""
    f, rng = SCORES[score], np.random.default_rng(seed)
    points = a.simulated.shape[0]
    draws = np.empty(n)
    for i in range(n):
        idx = rng.integers(0, points, points)
        draws[i] = f(b.simulated[idx], b.measured[idx]) - f(a.simulated[idx], a.measured[idx])
    low, high = np.percentile(draws, [2.5, 97.5])
    return dict(delta=f(b.simulated, b.measured) - f(a.simulated, a.measured), low=float(low), high=float(high))


def per_direction(c, score="r") -> np.ndarray:
    return np.array([SCORES[score](c.simulated[:, d], c.measured[:, d]) for d in range(c.simulated.shape[1])])


def native_estimate(work_units: float, cells: int) -> float:
    """Seconds a native kernel would need for ``work_units`` sweep-equivalents (section 0.1)."""
    return work_units * cells * NS_PER_CELL_SWEEP


def write(experiment: str, name: str, payload: dict) -> Path:
    path = OUT / experiment / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=float) + "\n")
    return path
```

#### 1.0.2 Native debug branch (`exp/debug-export`)

**Why.** The Python prototypes (F05–F08, F10, F11) need native state that the API does not return:
- the **initial field after the building parameterizations**, before the mass-consistent solve. QES sets it in `data.applyWindProfile` and `data.applyParametrizations` (`src/qes_core/dtcc/wind_runner.cpp:126-127`);
- the **Poisson stencil** and its right-hand side;
- the **QES-Turb mixing lengths**.

F02 also needs the **relaxation factor** exposed. It is fixed at 1.78, or 1.90 in adaptive mode (`wind_runner.cpp:162`).

**The rule for this branch.** It is never merged as it stands. Any edit to `src/qes_core` or `src/cpp` changes the native policy identity. AIJ runs are outside the adaptive policy, so the validation can use the branch freely; the harness fingerprint changes with it, and the run keys stay correct.

```cpp
// src/qes_core/dtcc/api/wind_config.h  (branch exp/debug-export)
struct SolverOptions {
  // ... existing fields ...
  float relaxation = 0.0f;     // F02; 0 keeps the legacy 1.78 (adaptive 1.90)
  bool export_debug = false;   // section 1.0.2
};
struct DebugFields {           // QES layout, ghost layers included
  std::vector<float> u0, v0, w0;       // staggered faces after applyParametrizations()
  std::vector<int> icellflag;
  std::vector<float> stencil;          // 6 per cell: e f g h m n, from PoissonOperator::stencil
  std::vector<float> rhs;              // R after build_rhs()
  std::vector<float> mixing_length;    // WINDSGeneralData::mixingLengths
  std::vector<float> dz_array;         // layer thickness per k (row weights for F06)
  int nx = 0, ny = 0, nz = 0;
};
// WindData gains: std::optional<DebugFields> debug;

// src/qes_core/dtcc/wind_runner.cpp, WindRunner::solve, right after data.applyParametrizations():
if (options.export_debug) {
  auto &d = result.debug.emplace();
  d.u0 = data.u0; d.v0 = data.v0; d.w0 = data.w0;
  d.icellflag = data.icellflag; d.mixing_length = data.mixingLengths; d.dz_array = data.domain.dz_array;
  d.nx = data.domain.nx(); d.ny = data.domain.ny(); d.nz = data.domain.nz();
  d.stencil.resize(6 * d.icellflag.size());
  for (std::size_t c = 0; c < d.icellflag.size(); ++c) {
    const auto s = state.poisson->stencil(c, layer_of(c));   // layer_of: k index of cell c (Domain helper)
    const float values[6] = {s.e, s.f, s.g, s.h, s.m, s.n};
    std::copy_n(values, 6, &d.stencil[6 * c]);
  }
}
// ...and replace the fixed factor at line 162:
const float relaxation = options.relaxation > 0 ? options.relaxation
                       : (controller && controller->adaptive_enabled() ? 1.90f : 1.78f);
// After finalize, d.rhs comes from workspace.copy_state_for_study().rhs.
```

```python
# src/dtcc_qes/_experimental.py  (branch exp/debug-export only; not a public API)
"""Experiment-only access to native internals (CLAUDE_WIND_EXPERIMENTS.md, section 1.0.2)."""
from . import wind


def run_debug(city, profile, *, relaxation=None, **run_kwargs):
    """wind.run with the native debug export. Returns (WindResult, dict of numpy arrays).

    The arrays keep QES's layout (ghost layers included); validation/proto/qes_faces.py
    converts them to the MAC layout. Gate P0 (section 1.0.3) checks that conversion.
    """
    native_options = dict(export_debug=True, relaxation=relaxation or 0.0)
    # New on the branch: threads native options through wind._solve_prepared.
    return wind._run_with_native_options(city, profile, native_options=native_options, **run_kwargs)
```

#### 1.0.3 A Python projection, and gate P0

**What it is.** A Python version of QES's mass-consistent adjustment, on a MAC grid and solved with algebraic multigrid (pyamg).
- F07, F08, F10 and F11 modify the initial field and then project it here.
- F05 varies its weights.
- F06 measures it against SOR.

**The equations (QES form).**
- The adjusted field is u = u0 + (1/2α1²)∂λ/∂x, v = v0 + (1/2α1²)∂λ/∂y and w = w0 + (1/2α2²)∂λ/∂z.
- Requiring ∇·u = 0 gives an elliptic equation for λ.
- **Boundaries:** λ = 0 on the open lateral and top boundaries (QES ghost cells), and zero normal flux at the ground and at building faces.
- **Symmetry:** rows are weighted by cell volume, which makes the matrix symmetric on the stretched vertical grid.

**Smoke test (2026-11-02, scratchpad, scipy CG in place of pyamg).** On a 12 × 20 × 24 toy grid with two buildings and stretched layers:
- the operator is symmetric with a positive diagonal;
- the maximum divergence fell from 5.4 to 6e-12;
- closed faces stayed untouched;
- with fixed (inflow) sides, the result stays divergence-free and those boundary faces are left unchanged.

```python
# validation/proto/projection.py
"""Mass-consistent adjustment in the QES variational form (CLAUDE_WIND_EXPERIMENTS.md, section 1.0.3).

MAC layout: lambda at cell centres; u (nz, ny, nx+1), v (nz, ny+1, nx), w (nz+1, ny, nx).
Faces between fluid and solid cells, and the ground, are closed. Lateral and top boundary
faces are open, with lambda = 0 one cell outside, unless a side is fixed (closed, prescribed flux).
"""
from dataclasses import dataclass

import numpy as np
import pyamg
import scipy.sparse as sp

SIDES = dict(west=np.s_[:, :, 0], east=np.s_[:, :, -1], south=np.s_[:, 0, :], north=np.s_[:, -1, :])


@dataclass
class MacGrid:
    dx: float
    dy: float
    dz: np.ndarray      # (nz,) layer thickness
    fluid: np.ndarray   # (nz, ny, nx) bool

    @property
    def shape(self):
        return self.fluid.shape

    def dzc(self):
        """Centre-to-centre spacing at the nz + 1 z faces (ghost spacing at ground and top)."""
        return np.r_[self.dz[0], 0.5 * (self.dz[1:] + self.dz[:-1]), self.dz[-1]]


def divergence(g, u, v, w):
    return ((u[:, :, 1:] - u[:, :, :-1]) / g.dx + (v[:, 1:] - v[:, :-1]) / g.dy
            + (w[1:] - w[:-1]) / g.dz[:, None, None])


class Projector:
    """Assembles the operator and its AMG hierarchy once; project() can be called many times (F11)."""

    def __init__(self, g: MacGrid, alpha1=1.0, alpha2=1.0, fixed_sides=()):
        self.g, self.cu, self.cw = g, 0.5 / alpha1 ** 2, 0.5 / alpha2 ** 2
        self.fixed = set(fixed_sides)                     # closed, prescribed-flux sides, e.g. the inflow (F11)
        f, dz = g.fluid, g.dz[:, None, None]
        self.index = np.full(g.shape, -1)
        self.index[f] = np.arange(f.sum())
        n = int(f.sum())
        diag = np.zeros(n)
        rows, cols, vals = [], [], []

        def interior(axis, coef):                         # open faces between two fluid cells along ``axis``
            lo, hi = [slice(None)] * 3, [slice(None)] * 3
            lo[axis], hi[axis] = slice(None, -1), slice(1, None)
            lo, hi = tuple(lo), tuple(hi)
            both = f[lo] & f[hi]
            ia, ib = self.index[lo][both], self.index[hi][both]
            c = np.broadcast_to(coef, both.shape)[both]
            rows.extend([ia, ib]); cols.extend([ib, ia]); vals.extend([-c, -c])
            np.add.at(diag, ia, c); np.add.at(diag, ib, c)

        def boundary(side, coef):                         # open boundary face to a lambda = 0 ghost
            cells = f[side]
            np.add.at(diag, self.index[side][cells], np.broadcast_to(coef, f.shape)[side][cells])

        cx, cy = self.cu * g.dy * dz / g.dx, self.cu * g.dx * dz / g.dy
        interior(2, cx)
        interior(1, cy)
        interior(0, self.cw * g.dx * g.dy / g.dzc()[1:-1, None, None])
        for name, side in SIDES.items():
            if name not in self.fixed:
                boundary(side, cx if name in ("west", "east") else cy)
        boundary(np.s_[-1, :, :], self.cw * g.dx * g.dy / g.dz[-1])   # top; the ground is closed
        self.matrix = sp.csr_matrix((np.concatenate(vals + [diag]),
                                     (np.concatenate(rows + [np.arange(n)]),
                                      np.concatenate(cols + [np.arange(n)]))), shape=(n, n))
        self.ml = pyamg.smoothed_aggregation_solver(self.matrix, symmetry="symmetric")

    def project(self, u, v, w, *, x0=None, tol=1e-8, maxiter=200):
        g, f = self.g, self.g.fluid
        b = (divergence(g, u, v, w) * g.dx * g.dy * g.dz[:, None, None])[f]
        residuals = []
        x = self.ml.solve(b, x0=x0, tol=tol, maxiter=maxiter, accel="cg", residuals=residuals)
        lam = np.zeros(g.shape)
        lam[f] = x
        open_x = f[:, :, 1:] & f[:, :, :-1]
        open_y = f[:, 1:] & f[:, :-1]
        open_z = f[1:] & f[:-1]
        u[:, :, 1:-1] += self.cu * np.diff(lam, axis=2) / g.dx * open_x
        v[:, 1:-1] += self.cu * np.diff(lam, axis=1) / g.dy * open_y
        w[1:-1] += self.cw * np.diff(lam, axis=0) / g.dzc()[1:-1, None, None] * open_z
        if "west" not in self.fixed:                                  # open boundary, ghost lambda = 0
            u[:, :, 0] += self.cu * lam[:, :, 0] / g.dx * f[:, :, 0]
        if "east" not in self.fixed:
            u[:, :, -1] -= self.cu * lam[:, :, -1] / g.dx * f[:, :, -1]
        if "south" not in self.fixed:
            v[:, 0] += self.cu * lam[:, 0] / g.dy * f[:, 0]
        if "north" not in self.fixed:
            v[:, -1] -= self.cu * lam[:, -1] / g.dy * f[:, -1]
        w[-1] -= self.cw * lam[-1] / g.dz[-1] * f[-1]                 # top; the ground (w[0]) stays closed
        return u, v, w, x, len(residuals) - 1
```

**`proto/qes_faces.py`** converts the debug export to the MAC layout:
- it strips the ghost layers;
- it maps QES face index i, the west face of cell i, to MAC face i;
- it marks cells with flags 0 and 2 as solid.

It also writes Python faces back into a `WindResult`, so that probes are sampled by the same `sample_points` code as the native result. Other helpers it provides:
- `cell_flags` returns the MAC-layout flags;
- `mixing_length` returns the MAC-layout mixing lengths;
- `inflow_faces` and `profile_faces` build boundary and start fields from a profile;
- `centres_to_faces` maps cell-centred edits back to faces.

```python
# validation/proto/qes_faces.py (excerpt)
import dataclasses
import numpy as np


def to_result(result, g, u, v, w):
    """A copy of ``result`` whose velocity is the cell-centred average of the given faces (as QES does)."""
    centres = np.stack([0.5 * (u[:, :, 1:] + u[:, :, :-1]), 0.5 * (v[:, 1:] + v[:, :-1]),
                        0.5 * (w[1:] + w[:-1])], axis=-1).astype(np.float32)
    centres[~g.fluid] = 0.0
    return dataclasses.replace(result, velocity=centres)
```

**Gate P0, the projection's fidelity.** F05, F07, F08, F10 and F11 are trusted only after it passes.

```python
# validation/experiments/p0_projection_gate.py
from dataclasses import replace

import numpy as np

from aij import campaigns, runner, sampling
from dtcc_qes import _experimental
from proto import projection, qes_faces

for label in ("N", "E", "S", "W"):
    spec = replace(campaigns.case_e(label, "after"), max_iterations=8000, tolerance=1e-12, precision="float64")
    args = runner.inputs(spec)
    result, debug = _experimental.run_debug(args["city"], args["profile"], **args["run"])
    g, (u0, v0, w0) = qes_faces.mac_from_debug(debug, result)
    u, v, w, _, cycles = projection.Projector(g).project(u0.copy(), v0.copy(), w0.copy(), tol=1e-10)
    python = sampling.probe_sample(qes_faces.to_result(result, g, u, v, w), args["probes"].xyz)["speed"]
    native = sampling.probe_sample(result, args["probes"].xyz)["speed"]
    err = np.abs(python - native) / args["reference_speed"]
    print(label, f"p95 {np.nanpercentile(err, 95):.2e}  max {np.nanmax(err):.2e}  cycles {cycles}")
    assert np.nanpercentile(err, 95) <= 0.005 and np.nanmax(err) <= 0.02
```

- **Hypothesis P0:** the Python projection reproduces the native float64 end point at the Case E probes within p95 |ΔK| ≤ 0.005 and max ≤ 0.02, in all four directions.
- **If it fails:** the difference must be traced first, for example to the boundary treatment or a post-solve step. No prototype result counts until then.

#### 1.0.4 Morphometry

**Used by:** F07 (the canopy background), F08 (local mean height), and later by H05 (features).

**The frame.** Everything is computed on a raster rotated so that the wind blows along +x.

**The fetch average.** An "upwind fetch" average uses an exponential kernel along −x, with length L, and a Gaussian lateral spread of L/4. A recursive filter evaluates it, so the cost is O(cells) and does not depend on L.

**Smoke test (scratchpad).** On a toy raster, wind from 270° gives λp = 0.175 just east of a building and 0 just west of it. That is the right upwind sense.

```python
# validation/proto/morphometry.py
"""Wind-aligned, fetch-weighted urban morphometry (CLAUDE_WIND_EXPERIMENTS.md, section 1.0.4)."""
import numpy as np
import shapely
from scipy import ndimage, signal

KAPPA = 0.4


def height_raster(rows, bounds, cell=1.0):
    """Max building height per cell from aij.cityutil.footprints(city) rows (id, polygon, height)."""
    xmin, ymin, xmax, ymax = bounds
    x, y = np.arange(xmin + cell / 2, xmax, cell), np.arange(ymin + cell / 2, ymax, cell)
    X, Y = np.meshgrid(x, y)
    H = np.zeros(X.shape).ravel()
    for _, polygon, height in rows:
        x0, y0, x1, y1 = polygon.bounds
        window = np.flatnonzero(((X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)).ravel())
        inside = window[shapely.contains_xy(polygon, X.ravel()[window], Y.ravel()[window])]
        H[inside] = np.maximum(H[inside], height)
    return x, y, H.reshape(X.shape)


def _rotation(direction):
    """Degrees that rotate the raster so that wind FROM ``direction`` (meteorological) blows along +x."""
    flow = np.array([-np.sin(np.radians(direction)), -np.cos(np.radians(direction))])
    return np.degrees(np.arctan2(flow[1], flow[0]))


def fetch_mean(field, direction, L, cell=1.0):
    """Upwind exponential-kernel mean of ``field`` (y, x raster) for wind FROM ``direction``."""
    angle = _rotation(direction)
    rotated = ndimage.rotate(field, angle, reshape=True, order=1, mode="nearest")
    a = np.exp(-cell / L)
    smoothed = signal.lfilter([1 - a], [1, -a], rotated, axis=1)        # causal along +x = upwind kernel
    smoothed = ndimage.gaussian_filter1d(smoothed, sigma=L / 4 / cell, axis=0, mode="nearest")
    back = ndimage.rotate(smoothed, -angle, reshape=True, order=1, mode="nearest")
    oy, ox = (np.array(back.shape) - field.shape) // 2
    return back[oy:oy + field.shape[0], ox:ox + field.shape[1]]


def frontal(H, direction, cell=1.0):
    """Frontal area per plan area: positive height steps facing the wind, per metre of fetch."""
    angle = _rotation(direction)
    rotated = ndimage.rotate(H, angle, reshape=True, order=0)
    step = np.maximum(np.diff(rotated, axis=1, prepend=rotated[:, :1]), 0.0) / cell
    back = ndimage.rotate(step, -angle, reshape=True, order=0)
    oy, ox = (np.array(back.shape) - H.shape) // 2
    return back[oy:oy + H.shape[0], ox:ox + H.shape[1]]


def morphometry(H, direction, L, cell=1.0):
    built = (H > 0).astype(float)
    lp = fetch_mean(built, direction, L, cell)
    lf = fetch_mean(frontal(H, direction, cell), direction, L, cell)
    mean_h = fetch_mean(H, direction, L, cell) / np.maximum(lp, 1e-6)
    sigma_h = np.sqrt(np.maximum(fetch_mean(H ** 2, direction, L, cell) / np.maximum(lp, 1e-6) - mean_h ** 2, 0))
    max_h = ndimage.maximum_filter(H, size=int(2 * L / cell))   # a crude H_max; refined per experiment
    return dict(lp=lp, lf=lf, mean_h=mean_h, sigma_h=sigma_h, max_h=max_h)


def macdonald(lp, lf, mean_h, A=4.43, beta=1.0, cd=1.2):
    """Macdonald et al. (1998) displacement height and roughness length."""
    zd = mean_h * (1 + A ** (-lp) * (lp - 1))
    z0 = mean_h * (1 - zd / np.maximum(mean_h, 1e-6)) * np.exp(
        -(0.5 * beta * cd / KAPPA ** 2 * (1 - zd / np.maximum(mean_h, 1e-6)) * np.maximum(lf, 1e-6)) ** -0.5)
    return zd, z0


def kanda(lp, lf, mean_h, sigma_h, max_h):
    """Kanda et al. (2013): Macdonald corrected for height variability.
    Coefficients as recalled (a0 1.29, b0 0.36, c0 -0.17, a1 0.71, b1 20.21, c1 -0.77): VERIFY against the paper."""
    zd_mac, z0_mac = macdonald(lp, lf, mean_h)
    X = np.clip((sigma_h + mean_h) / np.maximum(max_h, 1e-6), 0, 1)
    zd = max_h * (-0.17 * X ** 2 + (1.29 * lp ** 0.36 + 0.17) * X)
    Y = lp * sigma_h / np.maximum(mean_h, 1e-6)
    z0 = z0_mac * (20.21 * Y ** 2 - 0.77 * Y + 0.71)
    return np.minimum(zd, 0.95 * max_h), np.maximum(z0, 1e-3)
```

#### 1.0.5 Simple-case performance benchmark

The "seconds for simple cases" target needs a simple case, and the *speed* test does not need measurements. Every Group 1 experiment that changes the solve also reports its cost on a synthetic prism:
- one building, 20 m × 20 m in plan and 60 m tall, in a 300 × 200 × 120 m domain;
- at 2 m, which is about 0.9 M cells;
- at 0° and 45°.

H02 later adds measured simple cases.

```python
# validation/aij/case_simple.py   (new; mirrors case_d/case_e)
from dtcc_core import builder
from dtcc_core.model import City
from shapely.geometry import box


def build_prism(width=20.0, depth=20.0, height=60.0, centre=(0.0, 0.0)) -> City:
    """One rectangular building on flat ground (dtcc-core convention: LOD0 at the roof)."""
    x, y = centre
    building = builder.building_from_footprint(box(x - width / 2, y - depth / 2, x + width / 2, y + depth / 2),
                                               height=height)
    city = City()
    city.add_building(building)
    return city


SIMPLE_BOUNDS = (-100.0, -100.0, 0.0, 200.0, 100.0, 120.0)
```

#### 1.0.6 Invariance tests

Cheap regression tests that every prototype and native branch must pass (adopted from QES_PHYSICS E2 and §11):
- **Empty domain:** with no buildings, the field equals the inflow profile, for two profiles and four directions.
- **Speed scaling:** K does not depend on the reference speed (verified to about 2e-6 on 2026-10-26).
- **Building order:** reversing the input order of the buildings leaves K unchanged.
  - **Measured 2026-11-02:** Case E SW "after" and Case D at 0° are bit-identical. Footprint cleaning reorders the Case E buildings, so order cannot matter there.
  - **Case D at 45°**, which has no footprint cleaning, changes 8 of 78 probes by up to 4.6e-4 in K. Zone precedence leaks into the result where oblique wakes overlap.
  - **Weight:** the effect is far below every gate, so it is a regression test and a check for F09's composition arm, not a design driver.
- **Solid flux:** zero normal flux on every solid face, and zero velocity in solid cells.
- **Cold/warm parity:** a reused preparation gives bit-identical output (F12).

```python
# validation/tests/test_invariance.py (sketch)
def test_building_order_invariance(case_d_45_inputs):
    args = case_d_45_inputs
    forward = solve_probes(args["city"], args)
    backward = solve_probes(reversed_city(args["city"]), args)
    assert np.nanmax(np.abs(forward - backward)) <= 1e-3   # today 4.6e-4 at Case D 45 deg; exact after F09's composition arm
```

### F01: metrics that match the use

- **Idea tested:** the review's §1, points 3–5: the blockage baseline, an error decomposition, and comfort-class agreement as the end-use metric.
- **Why:**
  - dtcc-qes is sold for comfort studies, but every validation score is a speed score.
  - Phase 5 showed that the hit rate can be raised by compressing the field.
  - A metric that rewards the wrong thing would steer every later experiment, in both groups, the wrong way.
- **Hypotheses:**
  - **H1a.** Ranking the Phase 5 variants (part A and the first tuning step, 1,111 stored runs) by pooled q on Case E "before" gives a different order from ranking them by NEN 8100 class agreement. The Spearman ρ between the two rankings is < 0.7.
  - **H1b.** The tuned configuration (Phase 5, part B) has more *false negatives* at windy points than the baseline. A false negative is a simulated class better than the measured one, where the measured class is C or worse. The hypothesis is that compression hides problems.
  - **H1c.** The error decomposition is MSE = bias² + (σs − σm)² + 2σsσm(1 − R).
    - In the baseline's Case E "before" error, the bias term dominates (> 50 %).
    - In the tuned configuration's error, the pattern term dominates.
- **Improvement for the app:**
  - a headline metric that measures what users decide on;
  - a guard against "improvements" that flatten the field;
  - a false-negative rate per design, which is the number a planner needs to know about a screening tool.
- **Performance:** no solver runs; a few minutes of post-processing.
- **Design:**
  - **Climates:** a neutral climate (uniform rose, Weibull shape 2, mean 5 m/s at the reference height) and a skewed one (60 % of hours from three sectors) as a sensitivity.
  - **Classes:** measured and simulated K go through the same climate and the same transform, so the comparison is consistent. NEN 8100's 60 m potential-wind convention is not reproduced, and does not need to be.
  - **Intervention metrics and controls:** ΔK MAE, mean ΔK bias, balanced sign accuracy and strongest-speed-up recall (section 0.3, rule 6), on all 16 directions and on F11's 4-direction subset. They are scored against four controls: no change, always increase, a constant speed fitted on development data, and the upwind-blockage index.

```python
# validation/experiments/f01_end_use.py
import math

import numpy as np

from aij import campaigns, compare, metrics
from dtcc_qes import comfort
from experiments import harness


def climate(years=10, shape=2.0, mean_speed=5.0, rose=None, seed=1):
    """Synthetic hourly speeds/directions at the reference height: Weibull speeds, 16-sector rose."""
    rng = np.random.default_rng(seed)
    n = years * 8760
    rose = np.full(16, 1 / 16) if rose is None else np.asarray(rose, float) / np.sum(rose)
    sector = rng.choice(16, n, p=rose)
    direction = (22.5 * sector + rng.uniform(-11.25, 11.25, n)) % 360
    scale = mean_speed / math.gamma(1 + 1 / shape)
    return scale * rng.weibull(shape, n), direction


def classes(K, field_directions, hourly):
    """NEN 8100 comfort class per probe; K is (point, direction), simulated at 1 m/s reference."""
    speeds, directions = hourly
    return comfort.assess(speeds, directions, np.moveaxis(K, 1, 0), field_directions, 1.0,
                          comfort.NEN8100).comfort


def end_use(c: compare.Comparison, hourly) -> dict:
    measured = classes(c.measured, c.directions, hourly)
    simulated = classes(c.simulated, c.directions, hourly)
    ok = (measured >= 0) & (simulated >= 0)
    m, s = measured[ok], simulated[ok]
    windy = m >= 2                                          # class C or worse
    return dict(agreement=float(np.mean(m == s)), within_one=float(np.mean(np.abs(m - s) <= 1)),
                false_negative_windy=float(np.mean(s[windy] < m[windy])) if windy.any() else None,
                windy_points=int(windy.sum()))


def decomposition(c) -> dict:
    s, m = metrics._pairs(c.simulated, c.measured)
    r = np.corrcoef(s, m)[0, 1]
    parts = dict(bias=(s.mean() - m.mean()) ** 2, amplitude=(s.std() - m.std()) ** 2,
                 pattern=2 * s.std() * m.std() * (1 - r))
    total = sum(parts.values())
    return {k: v / total for k, v in parts.items()} | dict(mse=float(np.mean((s - m) ** 2)))


if __name__ == "__main__":
    hourly = climate()
    rows = []
    for name, specs in campaigns.sensitivity_variants() + campaigns.tuning_variants_for_report():
        records = compare.load_records(harness.RUNS, specs)
        c = harness.comparisons(records).get("E-before-thermistor-K")
        if c is None:
            continue
        rows.append(dict(variant=name, q=metrics.hit_rate(c.simulated, c.measured), **end_use(c, hourly),
                         **decomposition(c)))
    rho = metrics.spearman([r["q"] for r in rows], [r["agreement"] for r in rows])
    harness.write("F01", "ranking", dict(rows=rows, rank_rho=rho))
    print(f"H1a: rank correlation q vs class agreement = {rho:.2f} (hypothesis: < 0.7)")
```

`campaigns.tuning_variants_for_report()` is a small new helper. It returns `(name, specs)` pairs for the tuning steps stored in `output/tuning/search.json`.

**Decision rule.**
- **H1a holds:** class agreement and the false-negative rate join q in the headline. All later gates use the three together (rule 5 in section 0.3).
- **H1a fails:** q stays primary, and only the decomposition is added.

### F02: SOR relaxation and Chebyshev acceleration

- **Idea tested:** the cheaper first step under A1.
- **Why:**
  - ω = 1.78 is far below optimal on grids with hundreds of cells per side. The probe error decays by only ~0.998 per sweep (solver measurements of 2026-10-28).
  - For red-black SOR, the optimal ω approaches 2 − O(1/N).
  - Chebyshev acceleration changes ω every half-sweep from an estimate of the Jacobi spectral radius ρ. It is near-optimal without tuning.
- **Hypotheses:**
  - **H2a.** The best ω lies in 1.90–1.97 for Cases D and E at 2 m and at 1 m. "Best" means fewest iterations to the probe target: p95 |ΔK| ≤ 0.005 and max ≤ 0.02, and staying within it.
  - **H2b.** Against ω = 1.78, it reduces the iterations at 1 m by ≥ 2×.
  - **H2c.** The converged probe values stay within 1e-4.
  - **H2d.** Chebyshev acceleration, with ρ estimated from the first 50 sweeps, comes within 20 % of the best fixed ω.
- **Improvement for the app:** a pure speed gain, with no change to the converged physics:
  - Case E at 1 m drops from 31–34 s to about 15 s;
  - 0.5 m drops from 440–642 s to perhaps 200–300 s, inside the hard ceiling;
  - R14's default iteration count goes further.
- **Performance:** a sweep costs the same, so every gain comes from fewer iterations.
- **Design:**
  - **Runs:** monitored runs, as in the convergence campaign: Case D at 0°, 22.5° and 45°, and Case E "after" at N, E, S and W, at 2 m and 1 m.
  - **ω values:** {1.78, 1.85, 1.90, 1.93, 1.95, 1.97, 1.99}, plus Chebyshev.
  - **Reference:** the existing float64 end points.

```python
# validation/aij/runspec.py: one new later field (its default keeps the old keys)
LATER_FIELDS = dict(parameterizations=(), canopy_roughness=None, blending_height=None, ground_roughness=None,
                    relaxation=None)
#   relaxation: float | None = None   # F02; None = native default (1.78)
# runner.inputs passes it on: wind.Solver(..., relaxation=spec.relaxation) on branch exp/debug-export.

# validation/aij/campaigns.py
OMEGAS = (1.78, 1.85, 1.90, 1.93, 1.95, 1.97, 1.99)


def relaxation_study() -> list[RunSpec]:
    specs = []
    for resolution, its in ((2.0, 4000), (1.0, 12000)):
        base = [case_d(a, resolution=resolution) for a in D_ANGLES]
        base += [case_e(l, "after", resolution=resolution) for l in CONVERGENCE_E_LABELS]
        specs += [replace(s, monitor=True, max_iterations=its, tolerance=FIXED_WORK_TOLERANCE, relaxation=w)
                  for s in base for w in OMEGAS]
    return specs
```

```sh
uv run --group validate python validation/run_validation.py --campaign relaxation_study --jobs 6
```

**Analysis.**
- **Iterations to the target:** from `aij.numerics.self_convergence(record)` for each record.
- **Converged values:** compared against the float64 end points.
- **Chebyshev:** it changes the native sweep loop to ω₀ = 1, ω₁/₂ = 1/(1 − ρ²/2), then ω(n+1/2) = 1/(1 − ρ²·ω(n)/4). That is about 20 lines in `src/qes_core/solver/cpu_float32.cpp`, on the same branch.

**Decision rule.**
- **H2b holds:** the new ω goes into native batch 1 (section 3), and R14's guidance is updated.
- **In either case:** F06 is measured against the *best* SOR, not the old one.

### F03: grid-sensitivity flags and probabilistic comfort classes

- **Idea tested:** A2 (R16, and ensembles).
- **Why:**
  - Phase 4 found single receptors near walls that do not converge.
  - Phase 5 found that a positional tolerance of one neighbourhood moves q as much as tuning does.
  - Reporting that uncertainty honestly is the cheapest accuracy gain available.
- **Hypotheses:**
  - **H3a (flags, stored runs).** Consider the Case E probes whose NEN 8100 class (F01's climate) changes between the 2 m and 1 m runs.
    - Recall: ≥ 80 % of them have span > 0.15 at 2 m.
    - Selectivity: < 30 % of *all* probes are flagged. Otherwise the flag is useless.
  - **H3b (raw ensemble).** An ensemble of 9 members per direction is under-dispersive: the measured class lies within the predicted class range at < 50 % of points. The members are {measured, power-law, log inflow} × {−7.5°, 0, +7.5°}.
  - **H3c (calibrated ensemble).** Inflating the spread by one factor, fitted on Case E "before", gives ≥ 70 % coverage on Case E "after" and on Case D. This calibrates only the *uncertainty*, not the field.
- **Improvement for the app:** comfort maps that mark grid-dependent receptors, and a probability per class instead of false precision. A planner can then tell "B for sure" from "B or C".
- **Performance:**
  - The flags are free: the neighbourhood range comes from the sampled plane.
  - The ensemble needs 9× the solves.
    - At 2 m, with the preparation shared across members, that is ≤ 35 s per direction, inside the "standard" target.
    - **This revives R9 (shared preparation).** It was dropped because 4 s per run did not matter. With 9 members it does.

```python
# validation/experiments/f03_flags_and_ensembles.py
from dataclasses import replace

import numpy as np

from aij import campaigns, compare
from experiments import harness
from experiments.f01_end_use import classes, climate

hourly = climate()

# H3a: span flags against class changes between 2 m and 1 m (stored baseline and grid runs).
coarse = compare.load_records(harness.RUNS, campaigns.baseline(2.0))
fine = compare.load_records(harness.RUNS, campaigns.baseline(1.0))
for state in ("before", "after"):
    c2 = harness.comparisons(coarse)[f"E-{state}-thermistor-K"]
    c1 = harness.comparisons(fine)[f"E-{state}-thermistor-K"]
    changed = classes(c2.simulated, c2.directions, hourly) != classes(c1.simulated, c1.directions, hourly)
    span = (c2.strata["span"] == "span >0.15").any(axis=1)          # flagged in any direction
    recall = np.mean(span[changed]) if changed.any() else np.nan
    harness.write("F03", f"flags_{state}", dict(recall=recall, flagged=float(span.mean()),
                                                changed=int(changed.sum())))

# H3b/H3c: the ensemble members.
OFFSETS = (-7.5, 0.0, 7.5)
INFLOWS = ("measured", "power_law", "log")


def members(spec):
    return [replace(spec, inflow=i, direction=(spec.direction + o) % 360) for i in INFLOWS for o in OFFSETS]


specs = [m for s in campaigns.baseline(2.0) for m in members(s)]   # 35 x 9 = 315 runs at 2 m
# Registered as campaign "ensemble" in aij/campaigns.py, then:
#   uv run --group validate python validation/run_validation.py --campaign ensemble --jobs 6
```

**Analysis.**
- **Coverage (H3b):** each member's class for a probe gives a set of classes. Coverage is the share of probes whose measured class lies in that set.
- **Inflation (H3c):** H3c widens each probe's K range by a factor f around the member median.
  - f is the smallest value that reaches ≥ 70 % coverage on Case E "before".
  - It is then tested on the other cases.

**Decision rule.**
- **H3a holds:** implement R16's Python part. `sample_points(..., neighbourhood=r)` returns the neighbourhood range, and `comfort.assess` gains a `grid_sensitive` mask.
- **H3c holds:** add an opt-in `comfort.assess_ensemble`, with shared preparation (R9).

### F04: a quasi-steady direction ensemble

- **Idea tested:** A3, a hypothesis about what the thermistors see.
- **Why:**
  - The thermistor-versus-vector gap (Phase 1) comes from fluctuations. Near the ground, the low-frequency part is largely meandering of the wind direction.
  - A small ensemble over direction predicts **both** instruments from one set of solves:
    - its *vector* average is the mean vector, which the split fibre measures;
    - its *scalar* average of |U| is the mean scalar speed, which the thermistors measure.
  - That makes the test unusually sharp.
- **Hypotheses.** Members sit at θ + {−15, −7.5, 0, 7.5, 15}° with Gaussian weights, σθ ∈ {5, 10, 15}°. σθ = 10° is pre-declared as the primary value.
  - **H4a.** Scored by the scalar average, the thermistor comparisons (D thermistor, E before, E after) improve their q by ≥ 0.04, with the bootstrap interval above zero, and R does not fall.
  - **H4b.** Scored by the vector average, the Case D split fibre does not degrade: ΔR ≥ −0.02 and Δq ≥ −0.03.
  - **H4c.** At the 33 Case D points, the ensemble's scalar-to-vector speed ratio correlates with the measured thermistor-to-split-fibre ratio with ρ ≥ 0.4.
- **Improvement for the app:**
  - a physically motivated scalar-speed estimate that does not depend on QES-Turb. Most comfort criteria are defined on scalar speed (R10, without the k problem);
  - wakes that are less sharp and less slow;
  - a cheap low-frequency gust proxy, the spread across members.
- **Performance:**
  - **As tested:** 5 members, so 5× the solves. Case E at 2 m costs about 15 s of solving plus preparation, inside the "standard" target.
  - **In a real study it is free.** With 36 directions at 10° spacing, smearing over σθ = 10° is a weighted sum of solves that already exist.

```python
# validation/experiments/f04_direction_ensemble.py
from dataclasses import replace

import numpy as np

from aij import campaigns, compare
from experiments import harness

OFFSETS = np.array([-15.0, -7.5, 0.0, 7.5, 15.0])


def weights(sigma):
    w = np.exp(-0.5 * (OFFSETS / sigma) ** 2)
    return w / w.sum()


def member_specs(spec):
    return [replace(spec, direction=(spec.direction + o) % 360) for o in OFFSETS]


def _velocity(record):
    """Probe velocity vectors (global frame); invalid probes become NaN."""
    return np.array([[np.nan] * 3 if v is None else v for v in record["probes"]["velocity"]], float)


bases = campaigns.baseline(2.0)
specs = [m for s in bases for m in member_specs(s)]                       # run these first (175 runs)
records = {o: compare.load_records(harness.RUNS, [replace(s, direction=(s.direction + o) % 360) for s in bases])
           for o in OFFSETS}

for sigma in (5.0, 10.0, 15.0):
    w = weights(sigma)
    scalar, vector = {}, {}
    for key, base in records[0.0].items():
        uref = base["profile"]["reference_speed"]
        vel = np.stack([_velocity(records[o][key]) for o in OFFSETS])                         # (member, probe, 3)
        scalar[key] = np.tensordot(w, np.linalg.norm(vel, axis=2), axes=1) / uref
        vector[key] = np.linalg.norm(np.tensordot(w, vel, axes=1), axis=1) / uref
    as_scalar = harness.comparisons(harness.with_probe_values(records[0.0], scalar))
    as_vector = harness.comparisons(harness.with_probe_values(records[0.0], vector))
    base = harness.comparisons(records[0.0])
    out = {name: harness.paired_bootstrap(base[name], as_scalar[name], "q")
           for name in ("D-thermistor-K", "E-before-thermistor-K", "E-after-thermistor-K")}
    out["D-split_fibre"] = dict(q=harness.paired_bootstrap(base["D-split_fibre"], as_vector["D-split_fibre"], "q"),
                                r=harness.paired_bootstrap(base["D-split_fibre"], as_vector["D-split_fibre"], "r"))
    harness.write("F04", f"sigma{sigma:g}", out)
```

The member velocities are in the global frame, because the probes are sampled with `frame="global"`. The vector average is therefore meaningful across directions.

**Decision rule.**
- **H4a and H4b hold:** add `comfort.direction_smearing(sigma)` as an option of the comfort assessment, with σθ documented.
- **H4c holds too:** propose it as the basis of R10.
- **H4a fails:** the gap is small-scale turbulence, not meandering. Drop the idea, and leave R10 to F10.

### F05: the variational weights α1/α2, a null test

- **Idea tested:** the review's §6, a knob that should *not* help. It is run once so the question is closed.
- **Why:** the ratio only decides whether the correction goes over obstacles or around them. It cannot create momentum. A 10-minute run prevents a future tuning detour.
- **Hypothesis H5 (null):** for α2/α1 ∈ {0.5, 1, 2}, pooled scores change by ≤ 0.03, and the sign of the Case E mean ΔK does not change.
- **Improvement for the app:** none expected. It narrows the search.
- **Performance:** unchanged.

```python
# validation/experiments/f05_alpha.py   (reuses the F07 loop; only the projector changes)
for ratio in (0.5, 1.0, 2.0):
    P = projection.Projector(g, alpha1=1.0, alpha2=ratio)
    u, v, w, _, _ = P.project(u0.copy(), v0.copy(), w0.copy(), tol=1e-8)
    ...  # sample probes, write pseudo-records, harness.paired_bootstrap against ratio 1.0
```

**Decision rule.**
- **H5 holds:** document it, and leave α fixed.
- **H5 fails:** the ratio *is* a lever, which would be surprising. It then goes into H06's set of constants rather than being hand-tuned.

### F06: a multigrid prototype

- **Idea tested:** A1, the performance enabler. This group holds the prototype only; the native implementation is native batch 1 in section 3.
- **Why:**
  - Even with a good ω, SOR's iteration count grows with the grid size. Multigrid's stays roughly constant.
  - The momentum step (F11) needs one projection per pseudo-step, which only multigrid makes affordable.
  - Very fine grids (0.5 m) need it to meet the ceiling.
- **Hypotheses:**
  - **H6a.** Smoothed-aggregation AMG-preconditioned CG (pyamg) on the *exact native operator* reaches the probe target at 4, 2 and 1 m (and 0.5 m if memory allows) in ≤ 30 iterations. The count varies by less than ±30 % across resolutions.
  - **H6b.** At 1 m, the work in WU is ≤ 1/10 of what F02's best SOR needs. Here WU = iterations × operator complexity × about 4 smoothing passes.
- **Improvement for the app:**
  - If native multigrid follows: 1 m costs what 2 m costs today, so near-wall receptors (Phase 4) get affordable resolution;
  - 0.5 m meets its target;
  - R14 is solved by construction;
  - F11 becomes affordable.
- **Performance:** a direct cost reduction. The multigrid setup is per geometry, so it is shared across directions.

```python
# validation/experiments/f06_multigrid.py
import time

import numpy as np
import pyamg
import scipy.sparse as sp

from aij import campaigns, runner
from dtcc_qes import _experimental
from experiments import harness

OFFSETS = {0: (1, 0, 0), 1: (-1, 0, 0), 2: (0, 1, 0), 3: (0, -1, 0), 4: (0, 0, 1), 5: (0, 0, -1)}  # e f g h m n


def native_matrix(debug):
    """A = D - sum(neighbours) over fluid cells, from the exported stencil (ghost lambda = 0 drops out)."""
    nz, ny, nx = debug["nz"], debug["ny"], debug["nx"]
    flags = debug["icellflag"].reshape(nz, ny, nx)
    stencil = debug["stencil"].reshape(nz, ny, nx, 6)
    fluid = (flags != 0) & (flags != 2)
    fluid[[0, -1]] = False; fluid[:, [0, -1]] = False; fluid[:, :, [0, -1]] = False   # ghosts
    index = np.full(fluid.shape, -1); index[fluid] = np.arange(fluid.sum())
    k, j, i = np.nonzero(fluid)
    rows, cols, vals = [index[k, j, i]], [index[k, j, i]], [stencil[k, j, i].sum(axis=1)]
    for a, (di, dj, dk) in OFFSETS.items():
        nb = index[k + dk, j + dj, i + di]
        keep = nb >= 0
        rows.append(index[k, j, i][keep]); cols.append(nb[keep]); vals.append(-stencil[k, j, i, a][keep])
    A = sp.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))))
    b = -debug["rhs"].reshape(nz, ny, nx)[fluid]
    dz_weight = debug["dz_array"][k]                 # row scaling that symmetrises stretched layers
    return sp.diags(dz_weight) @ A, dz_weight * b, fluid


for resolution in (4.0, 2.0, 1.0):
    spec = campaigns.fixed_work(campaigns.case_e("SW", "after", resolution=resolution))
    args = runner.inputs(spec)
    result, debug = _experimental.run_debug(args["city"], args["profile"], **args["run"])
    A, b, fluid = native_matrix(debug)
    assert abs(A - A.T).max() < 1e-6 * abs(A).max(), "not symmetric: check the dz weighting"
    t0 = time.perf_counter()
    ml = pyamg.smoothed_aggregation_solver(A, symmetry="symmetric")
    setup = time.perf_counter() - t0
    history = []
    x = ml.solve(b, tol=1e-9, accel="cg", maxiter=100, residuals=history)   # plus a probe-sampling callback
    cells = int(fluid.size)
    work_units = (len(history) - 1) * ml.operator_complexity() * 4
    harness.write("F06", f"sw_after_r{resolution:g}", dict(
        cells=cells, setup_seconds=setup, iterations=len(history) - 1, work_units=work_units,
        native_estimate_seconds=harness.native_estimate(work_units, cells),
        sor_iterations=campaigns.ITERATIONS[resolution]))
```

**Probe-target bookkeeping.** At every CG iteration, rebuild the faces from λ and sample the probes, with `qes_faces.to_result` and `sampling.probe_sample`. "Iterations to target" is then defined exactly as for SOR.

**Decision rule.**
- **H6a and H6b hold:** native multigrid goes into native batch 1 (section 3), before F11 or H04 go native.
- **H6a fails:** for example, the count grows with resolution because of the cut cells. Then try hypre's structured multigrid when native work starts. If that also fails, keep F02's SOR, and limit the momentum step to 2 m.

### F07: a canopy-aware background (R17)

- **Idea tested:** B1, specified physically.
- **Why:**
  - Phase 3 found the largest error: probes outside every zone keep the approach profile.
  - Phase 5's domain-wide canopy inflow tripled the Case E "before" hit rate, but overshot in Case D.
  - A background that follows the *local* morphometry, and leaves the open approach alone, is the targeted version.
- **Hypotheses.** There is no fitted constant; every value below is fixed before the run.
  - **H7a (R17 acceptance).** Against the defaults, on Case E "before", Case E "after" and the Case D split fibre:
    - q improves, with the bootstrap interval above zero;
    - R and ρ do not fall by more than 0.02.
  - **H7b (no overshoot).** The Case D split-fibre FB stays within ±0.25. Phase 5's canopy inflow reached +0.37 to +0.66.
  - **H7c (variant).** Scaling every air cell below the internal boundary layer beats scaling only the flag-1 cells by ≥ 0.03 in q on Case E "before". The first variant approximates a native version applied before the zones.
  - **H7d (resolution).** H7a also holds at 1 m.
- **Improvement for the app:** it fixes the error that dominates in dense low-rise fabric, the commonest European residential context, without calibrating per site.
- **Performance:**
  - The morphometry takes < 1 s per direction (recursive filters on a 1 m raster).
  - The native cost is one multiplication of the initial field, ≪ 1 WU, so the solve cost is unchanged.
  - The prototype's Python projection takes about 30–60 s at 2 m. That is not the product.

**The model, fixed before the run:**
- **Fetch length:** L = 15·H̄, where H̄ is the domain's plan-area-weighted mean height. It is derived, not fitted. L ∈ {10, 20}·H̄ is reported as a sensitivity and never selected.
- **Displacement height and roughness:** zd and z0 come from Kanda et al. (2013), on top of Macdonald et al. (1998). They use the fetch-weighted λp, λf, H̄ and σh (section 1.0.4).
- **Profile above zd:** U_l(z) = (u\*/κ) ln((z − zd)/z0). It is matched to the approach profile at the blending height z_b = min(δ, 3·H_max,local).
- **Profile in the canopy:** U_l(z) = U_l(H̄)·exp(a(z/H̄ − 1)), with a = 9.6·λf (Macdonald 2000; λf capped at 0.3).
  - Castro (2017) warns that real profiles are rarely exponential, so this is the weakest assumption.
  - A declared variant uses a linear profile instead.
- **Internal boundary layer:** δ(x) = 0.75·z0·(x/z0)^0.8, where x is the upwind distance from the first built cell along the wind (Elliott). Above δ, the factor fades to 1 over 0.5·δ.
- **The factor:** F = clip(U_l/U_approach, 0.2, 1). It multiplies u0 and v0, not w0.

**Smoke test (scratchpad).** On a toy block array with a tower, F at 2 m is 1.0 upwind of the built area and about 0.44 inside it. At 40 m it is ≥ 0.91.

```python
# validation/proto/canopy.py
import numpy as np
from scipy import ndimage

from proto import morphometry as mm


def upwind_distance(H, direction, cell=1.0, threshold_lp=0.05):
    """Distance along the wind from the first upwind built cell (the built-area edge), per raster cell."""
    angle = mm._rotation(direction)
    built = ndimage.rotate((H > 0).astype(float), angle, reshape=True, order=0) > 0
    started = np.maximum.accumulate(built, axis=1)                   # True from the first built cell onward
    distance = np.cumsum(started, axis=1) * cell
    back = ndimage.rotate(distance, -angle, reshape=True, order=0)
    oy, ox = (np.array(back.shape) - H.shape) // 2
    return back[oy:oy + H.shape[0], ox:ox + H.shape[1]]


def factor(H, direction, z, approach, cell=1.0, L_over_h=15.0, a_coef=9.6, floor=0.2):
    """Background factor F(z, y, x) on the raster; ``approach(z)`` is the approach speed profile."""
    mean_domain_h = H[H > 0].mean()
    m = mm.morphometry(H, direction, L_over_h * mean_domain_h, cell)
    zd, z0 = mm.kanda(m["lp"], m["lf"], np.maximum(m["mean_h"], 1.0), m["sigma_h"], np.maximum(m["max_h"], 1.0))
    x = upwind_distance(H, direction, cell)
    delta = 0.75 * z0 * (np.maximum(x, 1.0) / z0) ** 0.8
    zb = np.minimum(delta, 3.0 * m["max_h"])
    ustar = mm.KAPPA * approach(zb) / np.log(np.maximum(zb - zd, 1.1 * z0) / z0)
    hbar = np.maximum(m["mean_h"], 1.0)
    u_top = ustar / mm.KAPPA * np.log(np.maximum(hbar - zd, 1.1 * z0) / z0)
    F = np.ones((len(z),) + H.shape)
    for k, zk in enumerate(z):
        above = ustar / mm.KAPPA * np.log(np.maximum(zk - zd, 1.1 * z0) / z0)
        inside = u_top * np.exp(a_coef * np.minimum(m["lf"], 0.3) * (zk / hbar - 1.0))
        local = np.where(zk < hbar, inside, above)
        fade = np.clip((zk - delta) / (0.5 * delta), 0.0, 1.0)            # 0 inside the IBL, 1 well above it
        F[k] = (1 - fade) * np.clip(local / approach(zk), floor, 1.0) + fade
    F[:, m["lp"] < 0.02] = 1.0                                             # open ground keeps the approach
    return F
```

```python
# validation/experiments/f07_canopy_background.py
import numpy as np

from aij import campaigns, cityutil, runner, sampling
from dtcc_qes import _experimental, wind
from experiments import harness
from proto import canopy, morphometry, projection, qes_faces

VARIANTS = dict(background_only=lambda flags: flags == 1,
                all_air_below_ibl=lambda flags: (flags != 0) & (flags != 2))

values = {v: {} for v in VARIANTS}
specs = campaigns.baseline(2.0)
records = harness.compare.load_records(harness.RUNS, specs)
for spec in specs:
    args = runner.inputs(spec)
    result, debug = _experimental.run_debug(args["city"], args["profile"], **args["run"])
    g, (u0, v0, w0) = qes_faces.mac_from_debug(debug, result)
    x0, y0 = result.origin[0] + result.x[0], result.origin[1] + result.y[0]
    bounds = (x0 - g.dx / 2, y0 - g.dy / 2, x0 + g.dx * (g.shape[2] - 0.5), y0 + g.dy * (g.shape[1] - 0.5))
    _, _, H = morphometry.height_raster(cityutil.footprints(args["city"]), bounds, cell=g.dx)  # on the solver grid
    approach = lambda z: np.hypot(*wind.evaluate(args["profile"], np.ravel(z))).reshape(np.shape(z))
    F = canopy.factor(H, spec.direction, np.asarray(result.z), approach, cell=g.dx)
    flags = qes_faces.cell_flags(debug)
    P = projection.Projector(g)
    for name, select in VARIANTS.items():
        Fc = np.where(select(flags), F, 1.0)
        u = u0.copy(); v = v0.copy(); w = w0.copy()
        u[:, :, 1:-1] *= 0.5 * (Fc[:, :, 1:] + Fc[:, :, :-1]); v[:, 1:-1] *= 0.5 * (Fc[:, 1:] + Fc[:, :-1])
        u, v, w, _, _ = P.project(u, v, w, tol=1e-8)
        speed = sampling.probe_sample(qes_faces.to_result(result, g, u, v, w), args["probes"].xyz)["speed"]
        values[name][(spec.case, spec.state, spec.label)] = speed / args["reference_speed"]

base = harness.comparisons(records)
for name in VARIANTS:
    new = harness.comparisons(harness.with_probe_values(records, values[name]))
    harness.write("F07", name, {c: {s: harness.paired_bootstrap(base[c], new[c], s) for s in ("q", "r", "rho", "fb")}
                                for c in ("E-before-thermistor-K", "E-after-thermistor-K", "D-split_fibre")})
```

**Controls:**
- the baseline;
- Phase 5's best domain-wide canopy inflow (stored), so that F07 is compared with the blunt version as well as with the default.

**Additional arms** (adopted from QES_PHYSICS E1):
- **Isotropic descriptors:** the same model with uniform weights within the fetch radius instead of upwind ones. The directional arm must beat it by ≥ 0.03 in q on Case E "before"; otherwise the simpler arm is kept.
- **Column momentum balance:** below the blending height, solve d/dz(K_m dU/dz) = C_d·a_f(z)·|U|·U per 20 m patch, with C_d ∈ {0.8, 1.2} pre-declared. This replaces the exponential profile.
  - **Why:** the layer-wise frontal area a_f(z) represents mixed heights, which the exponential law cannot (Castro 2017).
  - **One change from QES_PHYSICS's sketch:** K_m comes from the column's own shear in the same nonlinear iteration. Freezing it from the external profile's shear would use a shear that does not exist inside the canopy.
  - **Cost:** 24–48-cell tridiagonal solves on a 20 m lattice, ≪ 1 WU.
  - **Smoke test (scratchpad):** it converges, and U at 2 m falls from 2.29 (open) to 0.34 (λp 0.16) and 0.17 (λp 0.36) under a 5 m/s top speed.

```python
# validation/proto/canopy_column.py
"""Steady 1D canopy momentum balance per patch (F07 column arm; after QES_PHYSICS_MODEL_EXPERIMENTS.md E1)."""
import numpy as np
from scipy.linalg import solve_banded

KAPPA = 0.4


def column(z_faces, frontal_area, top_speed, ground_z0, h50, cd=1.2, iterations=40, relax=0.5):
    """Solve d/dz(Km dU/dz) = Cd a_f |U| U with U(top face) = top_speed and a log-law ground stress.

    Km = l^2 |dU/dz| uses the column's own shear (updated every iteration), with
    l = min(kappa (z + z0), 0.15 h50). Returns (U at cell centres, converged).
    """
    z_faces = np.asarray(z_faces, float)
    af = np.asarray(frontal_area, float)
    dz, zc = np.diff(z_faces), 0.5 * (z_faces[1:] + z_faces[:-1])
    ell = np.minimum(KAPPA * (z_faces[1:-1] + ground_z0), 0.15 * h50)          # interior faces
    cf = (KAPPA / np.log1p(0.5 * dz[0] / ground_z0)) ** 2
    u = top_speed * np.log1p(zc / ground_z0) / np.log1p(z_faces[-1] / ground_z0)  # start: log profile
    for _ in range(iterations):
        km = np.maximum(ell ** 2 * np.abs(np.diff(u)) / np.diff(zc), 1e-4 * top_speed * h50)
        g = km / np.diff(zc)                                                    # face conductances
        diag = np.r_[g, 0.0] + np.r_[0.0, g] + cd * af * np.abs(u) * dz
        diag[0] += cf * abs(u[0])                                               # ground stress
        g_top = 2.0 * km[-1] / dz[-1]                                           # half cell to the top face
        diag[-1] += g_top
        rhs = np.zeros_like(u)
        rhs[-1] = g_top * top_speed
        new = solve_banded((1, 1), np.vstack([np.r_[0.0, -g], diag, np.r_[-g, 0.0]]), rhs)
        if np.max(np.abs(new - u)) < 1e-3 * top_speed:
            return new, True
        u = (1 - relax) * u + relax * new
    return u, False
```

**Decision rule.**
- **H7a, H7b and H7d hold:** native batch 2 gets an opt-in `Background(model="morphometric")`, applied in `applyWindProfile`. R17 is then closed.
- **H7a holds only on Case E:** the morphometry-to-profile chain is wrong for open plazas. Inspect the Case D factor maps; any change becomes a new pre-registration.

### F08: a tall-building amplification zone, with literature constants

- **Idea tested:** B2, without calibration. The literature has no downwash or corner-stream parameterization in the QUIC/QES lineage. H03 calibrates the zone with outside data.
- **Why:**
  - The tower effect is the planner's main question, and the model gets its sign wrong.
  - The current high-rise flag only lengthens the wake (`src/qes_core/winds/PolygonWake.cpp:159-179`).
  - If published constants already make the mean tower effect positive, the idea is confirmed cheaply, and calibration becomes a refinement.
- **Hypotheses**, with constants taken from Gandemer (1975) and Wise and nothing fitted:
  - **H8a (direction).** On Case E:
    - the predicted mean ΔK becomes positive (baseline −0.02; measured +0.10);
    - strongest-speed-up recall rises from 0.60 to ≥ 0.65;
    - balanced sign accuracy stays at or above the baseline's 0.768 (section 0.3, rule 6).
  - **H8b (no collateral damage).** On Case E "before", where in most directions no building qualifies as tall, q changes by ≤ 0.02. In Case D, the split-fibre R does not fall.
  - **H8c (amplitude).** The predicted mean ΔK reaches ≥ +0.04, and ΔK MAE falls by ≥ 20 %. This is the stronger claim, which calibration (H03) may be needed for.
- **Improvement for the app:**
  - it fixes the false negative that makes dtcc-qes unsafe for screening tall-building proposals;
  - its cost is negligible.
- **Performance:** a few zone evaluations per tall building, ≪ 1 WU.

**The zone, with the literature constants:**
- **Which buildings qualify:** a building is tall when H ≥ 2·H̄_local, the mean height within 100 m, excluding the building itself.
- **Activation** (adopted from QES_PHYSICS E2): the zones are weighted by w = smoothstep((H/H̄_local − 1.5)/0.5), so a building near the threshold does not switch on or off abruptly.
- **The frame:** the zone is defined in each tall building's wind-aligned frame. W is the building's crosswind width.
- **Corner streams:**
  - **Where:** a strip on each side, below z_c = min(0.15·H, 10 m).
    - Crosswind, it runs from the building's edge out to c_w·min(W, H).
    - Streamwise, it runs from the windward face to c_l·min(W, H) downstream.
  - **What:** the speed there is set to A(H)·U_approach(z), along the wind.
  - **Constants:**
    - A(H) = 1 + a·H, with a = 0.012 m⁻¹. This is my fit to Gandemer's corner values (1.2 at 15 m, 1.4 at 35–45 m, 2.2 at 100 m).
    - c_w = 0.5 and c_l = 1.0.
- **Base vortex (the Wise effect):** inside the existing upwind cavity and below z_c, the reversed near-ground flow is raised to at least A_v·U_approach(z), with A_v = 1.3 (Wise's standing vortex).

**Smoke test (scratchpad).** In a block array of 6–8 m buildings plus a 60 m tower, only the tower qualifies.

```python
# validation/proto/tall_buildings.py
import numpy as np
import shapely

DEFAULT = dict(a=0.012, c_w=0.5, c_l=1.0, a_v=1.3, tall_ratio=2.0, z_cap=10.0, z_frac=0.15)


def tall_buildings(rows, radius=100.0, ratio=2.0):
    """Buildings with H >= ratio x the mean height of their neighbours within ``radius`` metres."""
    polygons = [p for _, p, _ in rows]
    heights = np.array([h for _, _, h in rows])
    tree = shapely.STRtree(polygons)
    out = []
    for i, (bid, polygon, height) in enumerate(rows):
        near = [j for j in tree.query(polygon.centroid.buffer(radius)) if j != i]
        local = heights[near].mean() if near else 0.0
        if height >= ratio * max(local, 1.0):
            out.append((bid, polygon, height))
    return out


def apply(u, v, flags, X, Y, Z, rows, direction, approach, c=DEFAULT):
    """Impose corner-stream and base-vortex speeds on a cell-centred copy of the initial field.
    X, Y, Z are cell-centre coordinates (z, y, x); qes_faces.centres_to_faces maps the edits back to faces."""
    flow = np.array([-np.sin(np.radians(direction)), -np.cos(np.radians(direction))])
    cross = np.array([-flow[1], flow[0]])
    air = (flags != 0) & (flags != 2)
    for _, polygon, H in tall_buildings(rows, ratio=c["tall_ratio"]):
        cx, cy = polygon.centroid.x, polygon.centroid.y
        s = (X - cx) * flow[0] + (Y - cy) * flow[1]            # along-wind coordinate
        n = (X - cx) * cross[0] + (Y - cy) * cross[1]          # crosswind coordinate
        coords = np.asarray(polygon.exterior.coords)[:, :2] - (cx, cy)
        s_face = (coords @ flow).min()
        n_lo, n_hi = (coords @ cross).min(), (coords @ cross).max()
        size = min(n_hi - n_lo, H)
        low = Z < min(c["z_frac"] * H, c["z_cap"])
        streamwise = (s >= s_face) & (s <= s_face + c["c_l"] * size)
        corner = air & low & streamwise & (((n > n_hi) & (n <= n_hi + c["c_w"] * size)) |
                                           ((n < n_lo) & (n >= n_lo - c["c_w"] * size)))
        target = np.where(corner, (1 + c["a"] * H) * approach(Z), 0.0)
        raise_ = target > np.hypot(u, v)
        u[raise_], v[raise_] = target[raise_] * flow[0], target[raise_] * flow[1]
        vortex = air & low & (flags == 3) & (s < s_face) & (n >= n_lo) & (n <= n_hi)   # 3: upwind cavity (verify)
        back = c["a_v"] * approach(Z)
        weak = vortex & (np.hypot(u, v) < back)
        u[weak], v[weak] = -back[weak] * flow[0], -back[weak] * flow[1]
    return u, v
```

**The run** follows F07's script, with `tall_buildings.apply` in place of the canopy factor.

**Declared variants:**
- **The reference speed:** the approach profile (primary, because corner streams draw on high-level flow) or F07's local background.
- **Combined with F07's background:** this checks that the two do not interfere.
- **Divergence-free kernels** (adopted from QES_PHYSICS E2). The corner streams and the windward descent are added as the curl of a vector potential, instead of as imposed speeds. A solenoidal perturbation passes through the projection intact; an imposed speed is partly redistributed.
  - The windward roll is QES_PHYSICS's A_y kernel.
  - Each corner jet uses A_z = A(H)·U·F(n)·g(s)·h(z), where F′ is the crosswind jet profile. That gives u = ∂A_z/∂n along the wind and v = −∂A_z/∂s, which is divergence-free by construction.
  - **Which arm survives:** F13 predicts it. Imposed speeds should do well if the stages already raise K and the projection keeps it; kernels should do better if the projection is what removes the rise.

**Check before the run:** the flag codes in the native sources. Flag 3 is set three times, and flag 4 in `PolygonWake.cpp:621`. Confirm which one is the upwind cavity.

**Decision rule.**
- **H8a and H8b hold:** the idea is confirmed, and H03 calibrates the amplitude.
- **H8c also holds:** the literature constants may ship as they are in native batch 2 (`Parameterizations(tall_building=1)`). H03 then confirms or refines them.
- **H8a fails:** imposing speeds kinematically does not survive the projection. That argues for the momentum route (F11), not for more zone constants, and H03 is dropped.

### F09: smooth zone edges

- **Idea tested:** B3, R16's native part.
- **Why:**
  - Phase 4 found probe values that jump under refinement, for example 0.40, 0.12 and 0.53 at 2, 1 and 0.5 m. That fits binary zone edges snapped to cells.
  - Comfort receptors near façades change class between grids.
- **Hypotheses:**
  - **H9a.** Blending the initial field across zone edges, over a physical half-width ε = clip(0.05·H, 0.25 m, 1.5 m) that is the same function on every grid (adopted from QES_PHYSICS E3), brings the Case E p95 |ΔK| from 1 to 0.5 m from 0.058–0.072 to ≤ 0.05, the repository budget.
  - **H9b.** The share of changes that move in the same direction as on the previous refinement rises from 58 % to ≥ 75 %, so the changes become asymptotic.
  - **H9c.** Pooled scores at 2 m change by ≤ 0.03. This is a change to the numerics, not the physics.
  - **H9d (grid origin;** adopted from QES_PHYSICS E3**).** The grid origin is shifted by (dx/2, 0), (0, dy/2) and (dx/2, dy/2), with the world geometry and probes fixed.
    - At 2 m and 1 m, the spread of the Case E receptors (N, E, SW, W, both states) shrinks by ≥ 30 % with blending.
    - The origin spread and the refinement change are reported separately.
    - The shift is a new later `RunSpec` field, `origin_shift`, applied to `grids.horizontal_bounds`.
- **Improvement for the app:**
  - receptor values that converge with resolution;
  - fewer grid-sensitive flags (F03);
  - Richardson extrapolation becomes possible.
- **Performance:** one smoothing pass over the zone-edge cells after the parameterizations, ≪ 1 WU.

**Why this one is native from the start.** The test needs 0.5 m runs (100–142 M cells), which are too large for the Python projection. Smoothing the initial field natively takes about 30 lines on a branch, and SOR then does the rest. It stays entirely inside dtcc-qes, and it is the slowest Group 1 experiment after F11 (about 3 h, dominated by nine 0.5 m runs).

```cpp
// branch exp/zone-smoothing: WINDSGeneralData::applyParametrizations(), at the end
if (parameterizations.zoneSmoothingCells > 0) {
  // Edge band: air cells with a different flag among their 6 neighbours.
  std::vector<uint8_t> band(numcell_cent, 0);
  for (int k = 1; k < nz - 2; ++k) for (int j = 1; j < ny - 1; ++j) for (int i = 1; i < nx - 1; ++i) {
    const auto c = i + j * (nx - 1) + k * (nx - 1) * (ny - 1);
    if (icellflag[c] == 0 || icellflag[c] == 2) continue;
    for (const auto o : neighbour_offsets) if (icellflag[c + o] != icellflag[c] && icellflag[c + o] != 0) band[c] = 1;
  }
  dilate(band, parameterizations.zoneSmoothingCells);          // widen to the blend width
  box_filter_faces(u0, v0, w0, band, icellflag);               // 3x3x3 mean over air faces, only inside the band
}
```

```python
# validation/aij/campaigns.py: the 2 m baseline, the 1 m grid and the 0.5 m subset, with smoothing on
def zone_smoothing():
    specs = []
    for resolution in (2.0, 1.0):
        specs += [replace(s, parameterizations=dict(zone_smoothing=1)) for s in baseline(resolution)]
    specs += [replace(s, parameterizations=dict(zone_smoothing=1)) for s in fine_subset(FINE_RESOLUTION)]
    return specs
```

**Analysis:** `aij.gridstudy.changes` and `aij.gridstudy.trend` on the smoothed runs, against the stored unsmoothed ones.

**Additional arms** (adopted from QES_PHYSICS E2/E3), tested together with blending because all three act on zone edges:
- **Order-independent composition.** Each zone proposes a total velocity with a non-negative weight, and the proposals are averaged, instead of resolved by precedence. The order test (1.0.6) must then be exact.
- **A wall-law tangential initialisation at physical wall distance.** It replaces the cell-based sidewall initialisation, which `docs/near-wall-validation.md` links to the 10–18 % near-wall change.
- **The reference for both** is consistency under refinement and origin shifts. RANS with wall functions is not near-wall truth within 0.5–1 m of a wall (section 5).

**Decision rule.**
- **H9a and H9c hold:** the change goes into native batch 2.
- **H9a holds but H9c fails** (scores move by more than 0.03): the sharpness of the zones was doing physical work. Narrow the blend width and repeat.

### F10: turbulence by transport

- **Idea tested:** C2. It is low priority, because RANS also fails the Case D k pattern, but it is cheap and entirely in-house. The Case D split fibre provides measured k.
- **Why:**
  - QES-Turb's local closure gives k a pattern with R ≈ 0 (Phases 3 and 5).
  - A one-equation k model on the frozen mean field carries wake turbulence downstream, instead of placing it on zone edges.
  - Gust criteria (GEM) need a usable σ.
- **Hypotheses.** On the dtcc-qes field (primary, runnable at once) and on F11's field (once F11 has run):
  - **H10a.** At the 33 Case D points, transported k reaches R ≥ 0.3 and FAC2 ≥ 0.5 against the split-fibre k. QES-Turb gets R 0.09 and FAC2 0.15.
  - **H10b.** √(U² + 2k) with the transported k improves the thermistor q in Case D and in Case E "after" by ≥ 0.03, and does not make Case E "before" worse.
- **Improvement for the app:**
  - gust-equivalent criteria (City of London) move from "unvalidated screening" toward usable;
  - a thermistor-equivalent speed becomes available.
- **Performance:** about 300 scalar pseudo-steps at about 4 WU each, so about 1,200 WU. That is about 2 s natively at 2 m, inside the target.

**Arms, in order** (adopted from QES_PHYSICS E4):
- **(a)** QES-Turb as today.
- **(b) An inflow k(z) reference.** It comes from the measured tunnel table (`tables.Inflow.k` exists), and it is decoupled from the ground roughness that now sets the k level (Phase 5, R11). The spatial model is unchanged.
  - **Gate:** the upstream k profile is within 10 % of the table, without changing the mean velocity.
- **(c) Transport**, below, with (b)'s inflow.
  - It runs only if (b) leaves the pattern at R < 0.3.

**The model.** A one-equation k model, with mixing length L_m:
- **Transport:** ∂k/∂t + u·∇k = ∇·((ν + ν_t/σk)∇k) + P − C_D·k^{3/2}/L_m.
- **Closure:** ν_t = C_μ^{1/4}·L_m·√k and P = ν_t·|S|², with C_μ = 0.09 and C_D = C_μ^{3/4}.
- **Inflow k:** from the tunnel inflow turbulence where the tables provide it, and u\*²/√C_μ otherwise.

```python
# validation/proto/k_transport.py
import numpy as np

from proto.momentum import strain_rate, upwind

C_MU, SIGMA_K = 0.09, 1.0
C_D = C_MU ** 0.75


def solve_k(g, u, v, w, lm, k_inflow, steps=300, cfl=0.5):
    uc, vc, wc = 0.5 * (u[:, :, 1:] + u[:, :, :-1]), 0.5 * (v[:, 1:] + v[:, :-1]), 0.5 * (w[1:] + w[:-1])
    s = strain_rate(g, u, v, w)
    k = np.where(g.fluid, k_inflow, 0.0)
    for _ in range(steps):
        nut = C_MU ** 0.25 * lm * np.sqrt(np.maximum(k, 1e-8))
        production = nut * s ** 2
        dissipation = C_D * np.maximum(k, 0) ** 1.5 / np.maximum(lm, 1e-3)
        rate = (-upwind(k, uc, g.dx, 2) - upwind(k, vc, g.dy, 1) - upwind(k, wc, g.dz[:, None, None], 0)
                + laplacian_weighted(g, k, nut / SIGMA_K) + production - dissipation)
        dt = cfl * min(g.dx, g.dz.min()) / (np.abs(uc) + np.abs(vc) + np.abs(wc) + 1e-3)
        k = np.where(g.fluid, np.maximum(k + dt * rate, 0.0), 0.0)
        k[inflow_cells(g)] = k_inflow[inflow_cells(g)]
    return k
```

**Decision rule.**
- **H10a holds:** native batch 2 gets an opt-in `Turbulence(model="transport")`, and the gust paths of `comfort` are rerun.
- **H10a fails:** gusts stay unvalidated, and F04's ensemble spread is the documented gust proxy.

### F11: momentum relaxation from the Röckle field, a screening run

- **Idea tested:** C1, QUIC-CFD style. This is the review's main recommendation, screened on the existing AIJ data. H04 tests it at full scale, at 1 m and against RANS.
- **Why:** both first-order errors are momentum effects: no canopy drag, and no pressure-driven downwash or corner streams. A simplified RANS started from the diagnostic field:
  - gets both from one mechanism, with no new constants;
  - reuses the projection;
  - starts much closer to steady state than the inflow profile would.
- **Screening design.** 11 runs at 2 m:
  - Case E SW, SSW, E and WSW in both states. These are the four directions whose measured K changes most between the states, the same as the Phase 4 subset.
  - Case D at all three directions.
  - Two more runs from the plain profile, for H11b: Case E SW "after" and Case D at 0°.
  - **Baseline on this subset** (Phase 4, 2 m): E before q 0.12 and FB −0.44; E after q 0.34; change R 0.42; D split fibre R 0.55. F01 recomputes the intervention metrics on this subset before the run.
- **Hypotheses:**
  - **H11a (physics).** After relaxation, all of these hold on the subset:
    - Case E:
      - ΔK MAE at least 20 % below the baseline;
      - |mean ΔK bias| ≤ 0.05;
      - balanced sign accuracy ≥ 0.82 (baseline 0.768 over all 16 directions);
      - strongest-speed-up recall ≥ 0.70 (baseline 0.60);
    - Case E "before": |FB| ≤ 0.2;
    - median per-direction R ≥ 0.6 in both Case E states;
    - Case D split fibre: R ≥ 0.55, and median angle error ≤ 25° (34° today).
  - **H11b (the hybrid's value).** From the Röckle field, the probe K reaches steady state (max |ΔK| < 2e-3 over 100 steps) in ≤ 50 % of the pseudo-steps the plain inflow profile needs.
  - **H11c (cost at 2 m).** ≥ 80 % of the final improvement in change R is reached within N80 ≤ 800 pseudo-steps. The native estimate at N80 is then ≤ 30 s per direction for Case E at 2 m, and ≤ 10 s for the simple case (section 1.0.5).
- **Improvement for the app:** if it holds, dtcc-qes moves from a screening-only tool to near-RANS accuracy at seconds to minutes per direction. Both of the review's main findings would be closed.
- **Performance:**
  - **Native cost per pseudo-step:** momentum for 3 components is about 12 WU, and one multigrid cycle about 6 WU, so a step is about 18 WU.
  - **Case E at 2 m:** 800 × 18 × 1.8 M cells × 1 ns ≈ 26 s, inside the "standard" target.
  - **At 1 m:** the same estimate gives about 380 s, which breaks the ceiling. That is H04's problem.
- **Prototype time:**
  - About 1–1.5 s per step in NumPy at 2 m, with at most 2,000 steps and early stopping.
  - That makes the 13 runs one night (8–12 h). It is the slowest Group 1 experiment.

**The method:**
- **Grid:** the MAC grid of the projection (section 1.0.3).
- **Advection:** first-order upwind, chosen for robustness. A second-order TVD scheme is a declared variant.
- **Eddy viscosity:** ν_t = (κ·L_m)²·|S|, where L_m is QES-Turb's own mixing length from the debug export. This is the same as `TURBGeneralData.cpp:150`, so there is no new constant.
- **Walls:** log-law wall drag on faces next to solids, with z0 = `Parameterizations.wall_roughness` for walls and the profile's ground roughness for the ground.
- **Boundaries:** inflow faces are held at the approach profile, outflow faces have zero gradient, and the top is held at the profile.
- **Time step:** local, with CFL 0.5 and the diffusion limit Δt ≤ 0.2·h²/ν_t.
- **Projection:** every step, warm-started from the previous λ, with at most 2 AMG-CG iterations.
  - **The upwind sides are closed** (prescribed flux), with `Projector(g, fixed_sides=...)`; the outflow and top stay open.
  - **Why:** QES's projection treats every lateral boundary as open (λ = 0), which would let it change the inflow that the momentum step holds fixed.
  - QES_PHYSICS E5 makes the same point about needing a consistent operator pair.
- **Probes:** recorded every 25 steps. That gives the accuracy-against-steps curve for H11c directly.

**Smoke test (scratchpad).** For u = z on a stretched grid, `strain_rate` returns 1.0 in the interior, as it should.

```python
# validation/proto/momentum.py
"""Pseudo-time relaxation of a simplified RANS from the diagnostic field (CLAUDE_WIND_EXPERIMENTS.md, F11)."""
import numpy as np

KAPPA = 0.4


def strain_rate(g, u, v, w):
    """|S| at cell centres from the face velocities (central differences of the centred field)."""
    uc, vc, wc = 0.5 * (u[:, :, 1:] + u[:, :, :-1]), 0.5 * (v[:, 1:] + v[:, :-1]), 0.5 * (w[1:] + w[:-1])
    z = np.cumsum(g.dz) - 0.5 * g.dz
    grads = [np.gradient(q, z, g.dy, g.dx, edge_order=1) for q in (wc, vc, uc)]   # d/dz, d/dy, d/dx
    (dwz, dwy, dwx), (dvz, dvy, dvx), (duz, duy, dux) = grads
    s2 = 2 * (dux ** 2 + dvy ** 2 + dwz ** 2) + (duy + dvx) ** 2 + (duz + dwx) ** 2 + (dvz + dwy) ** 2
    return np.sqrt(s2)


def upwind(q, vel, h, axis):
    """vel * dq/dx_axis, first-order upwind; one-sided at the domain edges (zero gradient)."""
    pad = [(0, 0)] * q.ndim
    pad[axis] = (1, 1)
    qp = np.pad(q, pad, mode="edge")
    sl = lambda a, b: tuple(slice(a, b) if d == axis else slice(None) for d in range(q.ndim))
    back = (q - qp[sl(0, -2)]) / h
    fwd = (qp[sl(2, None)] - q) / h
    return np.where(vel > 0, vel * back, vel * fwd)


class Relaxation:
    def __init__(self, g, projector, mixing_length, inflow_faces, wall_z0, ground_z0):
        self.g, self.P, self.lm = g, projector, mixing_length
        self.inflow = inflow_faces            # dict comp -> (mask, values) of held faces
        self.walls = wall_drag_coefficients(g, wall_z0, ground_z0)   # per-face C_w = (kappa / ln(h/2 / z0))^2
        self.lam = None

    def step(self, u, v, w, cfl=0.5):
        g = self.g
        nu = (KAPPA * self.lm) ** 2 * strain_rate(g, u, v, w)       # cell centres
        for comp, q in enumerate((u, v, w)):
            vu, vv, vw = velocity_at(comp, g, u, v, w)              # the three components at q's faces
            hz = face_dz(comp, g)
            rate = (-upwind(q, vu, g.dx, 2) - upwind(q, vv, g.dy, 1) - upwind(q, vw, hz, 0)
                    + diffusion(comp, g, q, nu)
                    - self.walls[comp] * np.sqrt(vu ** 2 + vv ** 2 + vw ** 2) * q / near_wall_h(comp, g))
            dt = local_dt(comp, g, vu, vv, vw, nu, cfl)
            q += dt * rate * open_faces(comp, g)
            mask, values = self.inflow[comp]
            q[mask] = values
        u, v, w, self.lam, _ = self.P.project(u, v, w, x0=self.lam, tol=1e-4, maxiter=2)
        return u, v, w
```

**Helpers.** `velocity_at`, `diffusion`, `local_dt`, `face_dz`, `near_wall_h`, `open_faces` and `wall_drag_coefficients` are standard MAC-grid helpers of 5–15 lines each. They are written once, with two unit tests:
- a channel flow, which must reach the log law;
- a uniform flow, which must stay uniform.

```python
# validation/experiments/f11_momentum_screen.py
import time

import numpy as np

from aij import campaigns, runner, sampling
from dtcc_qes import _experimental
from experiments import harness
from proto import momentum, projection, qes_faces

STEPS, EVERY = 2000, 25
SCREEN = ([campaigns.fixed_work(campaigns.case_e(l, s)) for l in campaigns.FINE_E_LABELS for s in ("before", "after")]
          + [campaigns.fixed_work(campaigns.case_d(a)) for a in campaigns.D_ANGLES])
FROM_PROFILE = (SCREEN[1], SCREEN[-3])                       # Case E SW "after" and Case D 0 deg (H11b)


def relax(spec, start="rockle", steps=STEPS, keep_fields=False):
    args = runner.inputs(spec)
    result, debug = _experimental.run_debug(args["city"], args["profile"], **args["run"])
    g, (u, v, w) = qes_faces.mac_from_debug(debug, result)
    if start == "profile":
        u, v, w = qes_faces.profile_faces(g, args["profile"])        # inflow profile everywhere, solids zeroed
    P = projection.Projector(g, fixed_sides=qes_faces.upwind_sides(spec.direction))   # inflow held fixed
    u, v, w, _, _ = P.project(u, v, w, tol=1e-8)
    R = momentum.Relaxation(g, P, qes_faces.mixing_length(debug),
                            qes_faces.inflow_faces(g, args["profile"], spec.direction),
                            wall_z0=spec.parameterization_spec().wall_roughness,
                            ground_z0=args["profile"].roughness_length)
    history, t0 = [], time.perf_counter()
    for n in range(1, steps + 1):
        u, v, w = R.step(u, v, w)
        if n % EVERY == 0:
            K = sampling.probe_sample(qes_faces.to_result(result, g, u, v, w), args["probes"].xyz)["speed"]
            K = K / args["reference_speed"]
            history.append((n, K.tolist()))
            if len(history) > 4 and np.nanmax(np.abs(K - np.array(history[-5][1]))) < 2e-3:
                break                                               # steady over 100 steps
    cells = int(np.prod(g.shape))
    out = dict(history=history, steps=n, prototype_seconds=time.perf_counter() - t0,
               native_estimate_seconds_per_step=harness.native_estimate(18, cells), cells=cells)
    if keep_fields:                                                 # H04's two-level start
        out["fields"] = (g, u, v, w)
    return out


if __name__ == "__main__":
    for spec in SCREEN:
        harness.write("F11", f"{spec.name}-rockle", relax(spec, "rockle"))
    for spec in FROM_PROFILE:
        harness.write("F11", f"{spec.name}-profile", relax(spec, "profile"))
```

**Analysis.**
- For each checkpoint n, build pseudo-records from the history and score them. This gives q, R, the change scores and the angle error as functions of n.
- **N80** is the first n at which the change R has gained 80 % of its final improvement.
- **H11a** uses the final checkpoint. **H11c** uses N80 together with the per-step native estimate.

**Decision rule.**

| Outcome | Next step |
|---|---|
| H11a and H11c hold | H04 becomes the priority in Group 2. F07 and F08 become fallbacks; F08 stays only if the tower effect is still too weak (H11a's ΔK bias and recall gates). |
| H11a holds, H11c fails | H04 must find a cheaper schedule (fewer steps, a two-level start) before anything goes native. |
| H11a fails | Diagnose it against H01's RANS fields when they arrive: the closure, the wall treatment or the resolution? Meanwhile take the B route (F07–F09 to native batch 2). Drop H04. |

### F12: preparation reuse across directions

- **Idea tested:** QES_PHYSICS E0, which revives R9. The first version of this document only noted it under F03.
- **Why:** preparation is about 4 of the 7 s per Case E direction at 2 m, and it does not depend on the direction (about 3 s of it is dtcc-core footprint cleaning). Every study, every ensemble (F03, F04) and every multi-direction run repeats it.
- **Hypotheses:**
  - **H12a (parity).** A session that prepares the City once and then solves each direction gives output bit-identical to `wind.run`. Two further checks:
    - **Stale state:** in the sequences 270° → 0° → 270° and after → before → after, no state carries over between solves.
    - **Invalidation:** after a single change of input, reused and fresh preparation must agree. The changes tried are the direction, the profile, one building height, the vertical faces, the parameterizations and the turbulence settings.
  - **H12b (gain).** It cuts the median warm time of a 16-direction Case E study at 2 m by ≥ 40 %, with peak RSS within 10 % of a single run. QES_PHYSICS's bar of 20 % is low, given that preparation is most of the time.
- **Improvement for the app:**
  - a 16-direction Case E study at 2 m drops from about 2 min to about 1 min;
  - 5–9-member ensembles (F03, F04) fit even the tighter fast-tier budget of QES_PHYSICS (≤ 12 s per direction).
- **Performance:** a pure gain. It is Python-only inside dtcc-qes, built over the existing `_prepare_city` / `_prepare_profile` / `_solve_prepared` split in `src/dtcc_qes/wind.py`, so it needs no native re-qualification.

```python
# validation/experiments/f12_session.py  (prototype of a public wind.Session)
import time

import numpy as np

from aij import campaigns, runner, sampling
from dtcc_qes import wind


class Session:
    """Prepare a City once; solve many wind conditions on it."""

    def __init__(self, city, profile, **run_kwargs):
        self.kwargs = run_kwargs
        grid = wind._grid_for(city, profile, run_kwargs)          # the grid construction inside wind.run
        self.geometry, self.prepared = wind._prepare_city(
            city, profile, grid, run_kwargs.get("terrain"), "measured",
            turbulence=run_kwargs.get("turbulence") is not None, footprints=run_kwargs.get("footprints"),
            parameterizations=run_kwargs.get("parameterizations", wind.Parameterizations()))

    def solve(self, profile):
        wind._prepare_profile(self.prepared, profile)             # the direction-dependent part only
        return wind._solve_prepared(self.geometry, self.prepared, profile, self.kwargs["solver"],
                                    vertical_grid=self.kwargs.get("vertical_grid"),
                                    turbulence_spec=self.kwargs.get("turbulence"))


specs = [campaigns.fixed_work(campaigns.case_e(label, "after")) for label in campaigns.E_LABELS]
args = runner.inputs(specs[0])
t0 = time.perf_counter()
fresh = [wind.run(args["city"], runner.inputs(s)["profile"], **args["run"]) for s in specs]
t_fresh = time.perf_counter() - t0
t0 = time.perf_counter()
session = Session(args["city"], args["profile"], **args["run"])
reused = [session.solve(runner.inputs(s)["profile"]) for s in specs]
t_reused = time.perf_counter() - t0
assert all(np.array_equal(a.velocity, b.velocity) for a, b in zip(fresh, reused))   # H12a: bit-identical
print(f"16 directions: fresh {t_fresh:.1f} s, reused {t_reused:.1f} s ({1 - t_reused / t_fresh:.0%} saved)")
```

`wind._grid_for` stands for the few lines in `wind.run` that build the grid. The prototype factors them out, and a public `wind.Session` would follow if H12a and H12b hold.

### F13: stage attribution of the tower effect

- **Idea tested:** QES_PHYSICS E0 (its diagnostic mode) and E2 experiment A.
- **Why:** final-field scores cannot tell why a speed-up near the tower is missing. Each possible cause points to a different fix:

  | Cause | Fix |
  |---|---|
  | No zone generated the speed-up | A new zone (F08) or momentum (F11) |
  | A later zone overwrote it | A composition rule (F09) |
  | The projection removed it | Divergence-free kernels (F08's second arm) |

- **Design:**
  - **Snapshots:** on the debug branch, record the receptor velocities, and three vertical sections through the tower, at each stage:
    - after the inflow;
    - after each parameterization family, in native order;
    - after the projection.
  - **Ownership:** for every cell, record which zone wrote it last.
  - **Runs:** Case E "after" at F11's four directions, with `high_rise` 0 and 1, and with `upwind_cavity` 2 and 3.
- **Hypotheses.** There are two exclusive outcomes, and either one is informative.
  - **H13a.** At the strongest-speed-up probes (the ten largest measured increases per direction), the zone stages raise K before the projection, and the projection removes ≥ 50 % of that rise. This favours F08's divergence-free arm.
  - **H13b.** The zone stages never raise K there, or a later zone overwrites the rise. Then no kernel or composition fix inside today's zones can help, which favours F08's new zones or F11.
- **Improvement for the app:** it directs the parameterization and momentum work at the actual loss mechanism.
- **Performance:** about 1 h. Snapshots exist only on the debug branch, and only at the receptors and the three sections, never as full volumes.

```cpp
// branch exp/debug-export: WINDSGeneralData::applyParametrizations(), after each family
if (stage_recorder) stage_recorder->snapshot("upwind_cavity", u0, v0, w0, icellflag);  // receptors + 3 sections
```

```python
# validation/experiments/f13_attribution.py (analysis excerpt)
stages = debug["stages"]                         # ordered: name -> (receptor velocities (n, 3), last-writer zone ids)
K = {name: np.linalg.norm(vel, axis=1) / uref for name, (vel, _) in stages.items()}
before_projection = K[list(stages)[-1]]          # after the last zone, before the solve
created = before_projection - K["inflow"]
kept = (K_final - K["inflow"]) / np.where(np.abs(created) > 0.02, created, np.nan)
top = strongest_speedup_probes(measured_change, n=10)      # per direction, as in section 0.3 rule 6
harness.write("F13", f"{spec.name}", dict(created=created[top].tolist(), kept=kept[top].tolist(),
                                          owner=[stages[s][1][top].tolist() for s in stages]))
```

### F14: an observation operator for scalar-speed instruments (done: negative)

- **Idea tested:** QES_PHYSICS E4's sensor model, using an exact formula instead of quadrature.
- **Why:**
  - The thermistors measure the mean scalar speed E|U|.
  - √(|Ū|² + 2k) is the RMS speed, an upper bound: |Ū| ≤ E|U| ≤ √(|Ū|² + 2k).
  - For a Gaussian velocity with isotropic covariance σ² = 2k/3, E|U| has a closed form, the mean of a noncentral χ distribution with 3 degrees of freedom:

    E|U| = σ√(2/π)·e^(−λ²/2) + σ(λ + 1/λ)·erf(λ/√2), with λ = |Ū|/σ.

    It agrees with Monte Carlo to four digits. With diagonal variances, which the Case D split fibre provides, Monte Carlo over 400,000 samples is used instead.
- **Hypothesis H14:** at the 33 Case D points, the Gaussian E|U| matches the thermistors better than the RMS speed.
- **Result (2026-11-02, scratchpad, measured data only): refuted.**

  | Estimate of the thermistor value | Median ratio | Within ±25 % | MAE | ρ |
  |---|---|---|---|---|
  | Mean vector \|Ū\| | 0.765 | 0.52 | 0.103 | 0.70 |
  | **RMS √(\|Ū\|² + 2k)** | **0.950** | **0.91** | **0.037** | 0.91 |
  | Gaussian E\|U\|, isotropic (closed form) | 0.919 | 0.85 | 0.048 | 0.90 |
  | Gaussian E\|U\|, measured diagonal variances | 0.903 | 0.85 | 0.054 | 0.90 |
  | Gaussian E\|U_h\|, horizontal components only | 0.851 | 0.79 | 0.064 | 0.91 |

- **Interpretation:** the more principled operator fits worse. The thermistors read above the Gaussian expected speed. Their response to turbulence is a plausible cause, but it is not tested here.
- **Decision:** keep √(|Ū|² + 2k) as the scalar-speed estimate in F04, F10 and the headline. QES_PHYSICS E4's quadrature work is unnecessary (section 5).

```python
# validation/experiments/f14_observation.py (as run)
import numpy as np
from scipy.special import erf

from aij import metrics, tables


def mean_speed_isotropic(mean_speed, k):
    """E|U| for U ~ N(mean, (2k/3) I) in 3D: the mean of a noncentral chi distribution with 3 dof."""
    sigma = np.sqrt(2 * np.asarray(k, float) / 3)
    lam = np.asarray(mean_speed, float) / np.maximum(sigma, 1e-12)
    return (sigma * np.sqrt(2 / np.pi) * np.exp(-lam ** 2 / 2)
            + sigma * (lam + 1 / np.maximum(lam, 1e-12)) * erf(lam / np.sqrt(2)))


exp_s, exp_t = tables.load_exp_s(), tables.load_exp_t()
m = exp_s.measured
thermistor = exp_t.values[m, 0]
U = exp_s.velocity[m] / tables.U_H
k = exp_s.k[m] / tables.U_H ** 2
vector = np.linalg.norm(U, axis=1)
for name, estimate in (("rms", np.sqrt(vector ** 2 + 2 * k)), ("gaussian", mean_speed_isotropic(vector, k))):
    print(name, metrics.hit_rate(estimate, thermistor), np.mean(np.abs(estimate - thermistor)))
```

### Group 1: order and decision points

1. **Week 1:**
   - infrastructure (1.0.1–1.0.6) and gate P0;
   - F01, F05, F12 and F03's flag part, all on stored runs or quick to run;
   - F14 is already done.
2. **Week 2:** F02, F04, F03's ensemble (on F12's session), and F13.
3. **Weeks 2–3:** F06, F07 and F08.
4. **Weeks 3–5:**
   - F11, the momentum code (2–3 weeks of development) and one night of runs;
   - F09, at about 3 h;
   - F10 on the dtcc-qes field.
5. **Decision point G1, after F11.** It chooses between momentum (H04) and zones (H03), and it fills the content of native batch 2.

## 2. Group 2: heavy experiments with outside tools and validation

Each experiment here needs at least one of four things: an external solver, external measurements, a generated corpus, or a cluster or GPU. Compute runs from days to weeks. These experiments supply what Group 1 cannot:
- the realistic target;
- calibration data that never touches Cases D and E;
- tests of generalisation beyond the two AIJ cases.

### 2.0 Infrastructure

#### 2.0.1 CFD pipeline (OpenFOAM)

**Used by:** H01, H03, H04 and H05.

**What it does.** It writes a simpleFoam case from any `RunSpec`:
- **Geometry:** the City's footprint prisms, as STL. The geometry is rotated so that the wind always enters at x_min.
- **Inflow:** the measured profile, mapped onto the inlet with `timeVaryingMappedFixedValue`. A log fit would change the inflow, as Phase 5 showed.
- **Probes:** the AIJ points, plus a 2 m plane on the dtcc-qes plane grid.

**What it reads back.** The probe output becomes pseudo-records, so CFD is scored by the validation's own code.

**New dependency:** `uv add --group validate trimesh`, plus an OpenFOAM installation (external).

```python
# validation/experiments/cfd/build_case.py
"""Write an OpenFOAM simpleFoam case for one AIJ run spec (geometry, inflow, probes)."""
import shutil
import subprocess
from pathlib import Path
from string import Template

import numpy as np
import trimesh
from shapely import affinity

from aij import cityutil, runner
from aij.runspec import RunSpec
from dtcc_qes import wind

TEMPLATE = Path(__file__).with_name("template")   # 0/, constant/, system/ with $placeholders


def rotate_to_x(geometry, direction, origin=(0.0, 0.0)):
    """Rotate so that wind FROM ``direction`` blows along +x."""
    angle = -(270.0 - direction)                     # met. 270 (from west) already blows along +x
    return affinity.rotate(geometry, angle, origin=origin, use_radians=False)


def write_case(spec: RunSpec, out: Path) -> Path:
    args = runner.inputs(spec)
    shutil.copytree(TEMPLATE, out, dirs_exist_ok=True)
    parts = [trimesh.creation.extrude_polygon(rotate_to_x(polygon, spec.direction), height)
             for _, polygon, height in cityutil.footprints(args["city"])]
    trimesh.util.concatenate(parts).export(out / "constant" / "triSurface" / "buildings.stl")

    z = np.geomspace(0.5, 200.0, 60)                 # inlet profile points (rotated frame: along the x_min boundary)
    speed = np.hypot(*wind.evaluate(args["profile"], z))
    write_mapped_inlet(out / "constant" / "boundaryData" / "inlet", z, speed)

    probes = args["probes"].xyz.copy()
    probes[:, :2] = [rotate_to_x_point(p, spec.direction) for p in probes[:, :2]]
    fill(out / "system" / "controlDict", probes=foam_points(probes))
    fill(out / "system" / "blockMeshDict", **domain_extents(args, spec.direction))
    return out


def run_case(out: Path, cores=16):
    for cmd in (["blockMesh"], ["surfaceFeatureExtract"], ["decomposePar"],
                ["mpirun", "-np", str(cores), "snappyHexMesh", "-overwrite", "-parallel"],
                ["mpirun", "-np", str(cores), "simpleFoam", "-parallel"], ["reconstructPar", "-latestTime"]):
        subprocess.run(cmd, cwd=out, check=True)


def fill(path: Path, **values):
    path.write_text(Template(path.read_text()).safe_substitute(**values))
```

```python
# validation/experiments/cfd/import_probes.py
import numpy as np

from experiments import harness


def read_probes(path):
    """Last time step of postProcessing/probes/0/<field>: an array (probe, components)."""
    last = [l for l in path.read_text().splitlines() if l and not l.startswith("#")][-1]
    values = last.replace("(", " ").replace(")", " ").split()[1:]
    return np.array(values, float).reshape(-1, 3 if path.name == "U" else 1)


def cfd_records(base_records, case_dirs):
    """Pseudo-records with K (vector) and K_scalar (sqrt(U^2 + 2k)) from the CFD probes."""
    values_k, values_ks = {}, {}
    for key, folder in case_dirs.items():
        uref = base_records[key]["profile"]["reference_speed"]
        U = read_probes(folder / "postProcessing/probes/0/U")
        k = read_probes(folder / "postProcessing/probes/0/k")[:, 0]
        speed = np.linalg.norm(U, axis=1)
        values_k[key], values_ks[key] = speed / uref, np.sqrt(speed ** 2 + 2 * k) / uref
    records = harness.with_probe_values(base_records, values_k)
    return harness.with_probe_values(records, values_ks, quantity="K_scalar")
```

`write_mapped_inlet`, `foam_points`, `domain_extents` and `rotate_to_x_point` are plain formatting helpers.

**An alternative.** IBOFlow, from Fraunhofer-Chalmers (a DTCC partner), could replace OpenFOAM through the same import, if a collaboration is set up.

#### 2.0.2 External data

| Source | For | Before use |
|---|---|---|
| AIJ Cases A, B, C and F: Eddy3D's cleaned AIJ data, or the AIJ guidebook data | H02, H03, H06 | Check the licence. Verify the case geometries; for example, check the dimensions in Case B's "4:4:1" notation. |
| UrbanTALES public LES (~500 layouts at 1 m) | H05 | Check the licence and the coverage of AIJ-like morphologies. |
| Generated layouts plus RANS (2.0.1) | H05, H06 | ~200 layouts × 8 directions; a generator in `validation/experiments/corpus.py` |

#### 2.0.3 Compute

| Experiment | Resource |
|---|---|
| H01, H03, H04 (RANS) | 16–32 cores per run, 1–3 h per 10–15 M-cell case |
| H05 corpus | ~3,000 core-hours on a cluster |
| H06 search | The workstation, ~10 h with `--jobs 6` |
| H07 | One RTX 4090- or A100-class GPU, and the CUDA backend or an external LBM code |

### H01: a RANS reference in the harness

- **Idea tested:** the review's §1 point 6 and step 0.
- **Why:** every comparison with RANS in the literature mixes pipelines: different inflow, probes and normalisation. A RANS run through *this* harness:
  - fixes the realistic target;
  - gives full-field error maps of dtcc-qes;
  - proves the CFD pipeline that H03–H05 reuse.
- **Hypotheses:**
  - **H01a.** Steady RANS (realizable k-ε, OpenFOAM, the measured inflow table) reaches per-direction Pearson R ≥ dtcc-qes + 0.15 on Case E, at 4 directions × 2 states. Its change R is ≥ 0.7, and its sign agreement ≥ 0.85.
  - **H01b.** Against the thermistors, RANS's √(U² + 2k) reaches q ≥ 0.45 on Case E. If it does not, the ceiling for *any* model on these data is lower than assumed, and the targets of all later gates are scaled down.
  - **H01c.** At 2 m, ≥ 60 % of the squared difference between dtcc-qes and RANS lies in two regions:
    - cells within 1.5 H of the 60 m tower;
    - dense-fabric cells outside every parameterization zone (cell flag 1, local λp > 0.3).
    This tests the review's diagnosis (§2) directly.
- **Improvement for the app:**
  - a defensible target ("parity with RANS");
  - a map of where the model is wrong, which points F07, F08 and F11 at the right cells;
  - a proven CFD pipeline.
- **Performance:** offline, not an app feature. About 11 runs (Case E SW, SSW, E and WSW × 2 states, and Case D × 3), at 1–3 h each.
- **Design:**
  - **Mesh:** snappyHexMesh, with a 4 m background, 1 m around buildings up to 2·H̄, and 0.5 m on building surfaces within 50 m of a probe. That is about the 12 M cells of Hågbo & Giljarhus (2022).
  - **Inlet turbulence:** k and ε come from the tunnel's turbulence profile if the tables have one, and from Richards & Hoxey otherwise.
  - **Directions:** the same as F11's screening set, so that H04 can compare them like for like.

```python
# validation/experiments/h01_rans.py
from pathlib import Path

from aij import compare
from experiments import harness
from experiments.cfd import build_case, import_probes
from experiments.f11_momentum_screen import SCREEN as SPECS      # the same 11 runs as F11

CASES = Path("/scratch/aij_rans")                                 # cluster scratch, outside the repo

dirs = {}
for spec in SPECS:
    folder = build_case.write_case(spec, CASES / spec.name)
    build_case.run_case(folder, cores=32)                          # or submit to the cluster queue
    dirs[(spec.case, spec.state, spec.label)] = folder

base = compare.load_records(harness.RUNS, SPECS)
rans = harness.comparisons(import_probes.cfd_records(base, dirs))
qes = harness.comparisons(base)
for name in rans:
    harness.write("H01", name, dict(r_per_direction=harness.per_direction(rans[name]).tolist(),
                                    r_qes=harness.per_direction(qes[name]).tolist(),
                                    q=harness.SCORES["q"](rans[name].simulated, rans[name].measured)))
```

**Decision rule.**
- **H01a holds:** RANS parity becomes the target of H03–H07, and of the Group 1 follow-ups.
- **H01a fails:** RANS is no better than dtcc-qes in this harness. Investment shifts to output honesty (F03, F04) and to cheap fixes, because expensive physics would not pay.
- **H01c holds:** F07 and F11 aimed at the right regions.
- **H01c fails:** the error map names the region to look at instead.

### H02: more AIJ cases, as clean tests of the two mechanisms

- **Idea tested:** the review's "broaden validation".
- **Why:**
  - Cases D and E mix every effect. An isolated tall prism isolates the speed-up mechanism, and a block array isolates the canopy level.
  - The new cases also give H03 and H06 calibration data that never touches D or E.
- **Hypotheses:**
  - **H02a.** On the isolated prism (Case A, and Case B if it is the taller prism), dtcc-qes underpredicts two things at 2 m:
    - the maximum corner speed-up, by ≥ 25 %;
    - the area with K > 1, by ≥ 50 %.
  - **H02b.** On the simple block array (Case C), the mean level is overpredicted (FB < −0.2), as in Case E "before".
  - **H02c.** If F07 and F08 passed, their effects carry over: Case C's FB moves toward zero with F07, and Case A/B's corner speed-up rises with F08, without any refitting.
- **Improvement for the app:**
  - measured simple cases that run in seconds, so a model change can be screened before the 35-run campaign;
  - calibration data for H03 and H06.
- **Performance:** a single building at 2 m is about 0.2–0.9 M cells, ~1 s per run. The cost is in acquiring the data, not in the compute.

```python
# validation/aij/tables.py (a new reader next to load_results_e; the format depends on the source, Eddy3D CSV shown)
import pandas as pd


def load_case_simple(path, case: str, instrument="thermistor", reference=None) -> Measurements:
    """Points and K per direction for AIJ Case A/B/C from a cleaned CSV (columns: id, x, y, z, direction, K)."""
    df = pd.read_csv(path)
    pivot = df.pivot_table(index="id", columns="direction", values="K")
    directions = pivot.columns.to_numpy(float)
    xyz = df.drop_duplicates("id").set_index("id").loc[pivot.index, ["x", "y", "z"]].to_numpy(float)
    quantity = "scalar_speed_ratio" if instrument == "thermistor" else "vector_speed_ratio"
    return Measurements(case=case, state=None, quantity=quantity, instrument=instrument,
                        ids=pivot.index.to_numpy(), xyz=xyz, labels=tuple(f"{d:g}" for d in directions),
                        directions=directions, values=pivot.to_numpy(float), reference=reference or {})
```

**Using the data.**
- The specs reuse `RunSpec` with a new case code (`case="A"`), and the geometry comes from `case_simple.build_prism` with the AIJ dimensions.
- Two extra metrics matter here: the maximum K, and the area with K > 1, for H02a.

**Decision rule.**
- **H02a holds:** Cases A/B become H03's calibration set.
- **H02b holds:** Case C joins the check of F07's acceptance.
- **Either fails:** the mechanism behaves differently in isolation, which is itself a finding to bring into the review.

### H03: calibrating the tall-building zone

- **Idea tested:** B2 with calibrated constants. F08 tested the literature constants.
- **Why:** F08 shows whether the zone points the right way. The amplitude and extent need reference data that is independent of the test cases.
- **Precondition:** F08's H8a holds.
- **Calibration data:**
  - **Primary:** the tower-in-canopy cases of the mechanism matrix (H08): 30 and 60 m towers in the low-density aligned array at 0° and 45°, plus the podium case. They are closer to the failure than isolated towers, because the model fails on a tall building among low ones.
  - **Fallback:** RANS of 3 isolated towers (H/W = 2, 4 and 6; 0° and 45°), only if H08's cases cannot separate the four constants.
  - **And/or** AIJ Cases A/B (H02).
- **Hypotheses:**
  - **H03a (fit).** On the calibration towers, the calibrated zone brings the maximum corner K at 2 m within ±20 % of the reference. Without it the underprediction is ≥ 25 % (H02a).
  - **H03b (held-out tower effect).** On Case E:
    - ΔK MAE falls by ≥ 20 %;
    - |mean ΔK bias| ≤ 0.05. The baseline's is −0.12: −0.02 predicted against +0.10 measured;
    - balanced sign accuracy reaches ≥ 0.82 (baseline 0.768);
    - strongest-speed-up recall reaches ≥ 0.70 (baseline 0.60).

    On H09, the same metrics must improve against RANS in every family.
  - **H03c (no collateral damage).** On Case E "before", q changes by ≤ 0.02. In Case D, the split-fibre R does not fall.
- **Improvement for the app:** the tower effect with the right sign *and* a defensible amplitude, at no runtime cost.
- **Performance:**
  - **Runtime:** unchanged from F08.
  - **Offline:** 6 RANS runs, then a least-squares fit that takes minutes, because each evaluation is a 2 m dtcc-qes run of about 1 s.

```python
# validation/experiments/h03_tall_calibration.py
import numpy as np
from scipy.optimize import least_squares

from proto import tall_buildings

TOWERS = [(20.0, 20.0, h) for h in (40.0, 80.0, 120.0)]          # fallback isolated towers; primary: H08 tower-in-canopy
DIRECTIONS = (270.0, 225.0)                                      # 0 and 45 deg relative to a face
NAMES = ("a", "c_w", "c_l", "a_v")


def residuals(theta, references):
    constants = dict(tall_buildings.DEFAULT, **dict(zip(NAMES, theta)))
    out = []
    for tower, direction in references:
        sim = run_prism_with_zone(tower, direction, constants)   # F07-style loop on case_simple.build_prism
        ref = references[(tower, direction)]                     # RANS plane at 2 m (H01 pipeline) or AIJ A/B
        out += [(sim.max_K - ref.max_K) / ref.max_K, (sim.area_K_above_1 - ref.area_K_above_1) / ref.area_K_above_1]
    return np.array(out)


fit = least_squares(residuals, x0=[tall_buildings.DEFAULT[n] for n in NAMES],
                    bounds=([0.002, 0.2, 0.3, 1.0], [0.03, 1.5, 3.0, 2.0]), args=(load_references(),))
# then: Case E and Case D with the fitted constants, scored as in F08 (H03b, H03c)
```

**Decision rule.**
- **H03b and H03c hold:** the calibrated constants go into native batch 2, with `Parameterizations(tall_building=1)`.
- **H03a holds but H03b fails:** the zone is right in isolation, but not in context. That argues for the momentum route (H04), not for more constants.

### H04: momentum relaxation at full scale, at 1 m and against RANS

- **Idea tested:** C1 beyond the screening run.
- **Precondition:** F11's H11a holds.
- **Why:** the screening run covers 11 directions at 2 m against the measurements. Before the method goes native, three questions remain:
  - Does it hold on all 35 runs?
  - Can it reach 1 m within the ceiling?
  - How close is it to RANS on the same cases?
- **Hypotheses:**
  - **H04a (scale).** On all 35 runs at 2 m, the F11 thresholds hold. Change R, sign agreement, FB and per-direction R are recomputed on the full matrix.
  - **H04b (RANS parity, needs H01).** On H01's 11 runs, the relaxed field is within 0.05 of RANS in per-direction R. Over the 2 m plane, the RMS difference from RANS is ≤ 50 % of dtcc-qes's.
  - **H04c (1 m within the ceiling).** A two-level start reaches the 2 m-converged accuracy at 1 m with a native estimate ≤ 3 min per direction for Case E. The start is 400 steps at 2 m, prolonged to 1 m, then relaxed to steady state. The single-level 1 m estimate is about 380 s.
  - **H04d (TVD).** The second-order TVD advection scheme moves the per-direction R by ≥ 0.03 at 1 m. If it does not, first-order upwind is kept, because it is cheaper and more robust.
  - **H04e (coarse correction;** adopted from QES_PHYSICS E5**).** Momentum is relaxed on a 4 m grid, and only the correction is transferred: fine = fine_initial + P(coarse_final − coarse_initial), followed by the 1 m projection.
    - **Target:** within 0.03 of the two-level start in per-direction R, at ≤ 1/3 of its native cost.
    - **No 8 m arm:** Case E's canopy (H̄ ≈ 6 m) would sit inside one cell.
    - **The check** is QES_PHYSICS's consistency test, R(fine_candidate) ≈ coarse_final.
- **Improvement for the app:** the evidence needed to commit native batch 2 to the momentum step, together with its 1 m schedule.
- **Performance:**
  - The prototype needs about 1–2 days on the workstation: 35 runs at 2 m, plus 11 two-level 1 m runs at about 1.5 h each in NumPy.
  - The native estimates are the gates.

```python
# validation/experiments/h04_momentum_scale.py
from dataclasses import replace

from aij import campaigns
from experiments import harness
from experiments.f11_momentum_screen import relax
from proto import two_level

for spec in campaigns.baseline(2.0):                                   # H04a: the full matrix at 2 m
    harness.write("H04", f"{spec.name}-full", relax(spec, "rockle"))

for spec in campaigns.fine_subset(1.0):                                # H04c: two-level start at 1 m
    coarse = relax(replace(spec, resolution=2.0), "rockle", steps=400, keep_fields=True)
    out = two_level.relax_fine(spec, start=coarse["fields"], scheme="upwind")
    out_tvd = two_level.relax_fine(spec, start=coarse["fields"], scheme="tvd")        # H04d
    harness.write("H04", f"{spec.name}-two-level", dict(upwind=out, tvd=out_tvd))
# H04b: compare the 2 m planes with H01's RANS planes on the same 11 specs (RMS over the plane, per-direction R)
```

**Decision rule.**
- **H04a, H04b and H04c hold:** native batch 2 is the momentum step on native multigrid (section 3). The GPU backend becomes an optimisation, not a prerequisite.
- **H04c fails:** ship the momentum step at 2 m only, and make the CUDA backend the route to 1 m.
- **H04b fails but H04a holds:** it beats dtcc-qes but not RANS. It still ships, and its documented accuracy is "between diagnostic and RANS".

### H05: a residual correction on the physics output

- **Idea tested:** D1.
- **Why:**
  - Section 1 of the review shows that morphometric features carry much of the signal.
  - Diff-KNN (Nowak et al. 2025, Fraunhofer-Chalmers) cut coarse-CFD error by 57 % on AIJ Case E with a correction of this kind.
  - A correction learned on many layouts can capture what no hand-made zone does, at an inference cost of milliseconds.
- **Hypotheses.** Training **never** includes AIJ D or E.
  - **H05a.** A gradient-boosted correction of log(K_hf/K_model), trained on high-fidelity CFD of non-AIJ layouts, does two things:
    - it reduces the per-probe RMSE against H01's RANS on AIJ Case E by ≥ 30 %;
    - it improves the wind-tunnel q and R on held-out Cases D and E, with the bootstrap interval above zero.
  - **H05b (residual against end to end).** The same model *without* the dtcc-qes speed-up as an input does worse on AIJ by ≥ 0.05 in R. The physics input is what makes it generalise.
  - **H05c (better baselines).** Applied to F11/H04's field instead of raw dtcc-qes, the correction is smaller (median |log ratio| lower by ≥ 30 %) and generalises better. This is Zhao et al. (2024)'s warning about crude baselines.
- **Improvement for the app:** accuracy closer to the training fidelity, at almost no runtime cost. It is also a path to LES quality (UrbanTALES, or H07) without running LES.
- **Performance:**
  - **Runtime:** feature extraction takes < 1 s per direction (section 1.0.4), and prediction on a 250 × 250 plane about 0.1 s.
  - **Offline:** the corpus, about 3,000 core-hours of RANS (2.0.1), or a licensed LES set.
- **Corpus:**
  - the `industrial_residential` synthetic neighbourhood at 8 directions. The other three families are H09's confirmation set and never enter training;
  - about 200 generated layouts: blocks with random widths, gaps and heights, of which 10 % are towers 2–6 × the mean height;
  - UrbanTALES, if its licence allows.
- **Folds:** cross-validation is grouped by layout, never by point.
- **New dependency:** `uv add --group validate scikit-learn`.

```python
# validation/experiments/h05_residual.py
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import GroupKFold

from proto import morphometry as mm
from proto import tall_buildings

FEATURES = ("K_model", "lp_50", "lf_50", "lp_200", "lf_200", "mean_h_200", "sigma_h_200", "blockage_30",
            "blockage_60", "blockage_120", "tall_distance_over_h", "tall_bearing_cos", "tall_bearing_sin",
            "local_h_over_mean", "zone_flag")


def features(plane_xy, K_model, flags_2m, rows, direction, H, cell=1.0):
    """Per-point features at pedestrian height (N points)."""
    out = dict(K_model=K_model, zone_flag=flags_2m)
    for L in (50, 200):
        m = mm.morphometry(H, direction, L, cell)
        for name in ("lp", "lf") + (("mean_h", "sigma_h") if L == 200 else ()):
            out[f"{name}_{L}"] = sample_raster(m[name], plane_xy)
    for length in (30, 60, 120):
        out[f"blockage_{length}"] = upwind_blockage_points(plane_xy, direction, rows, length)
    out |= tall_geometry(plane_xy, direction, tall_buildings.tall_buildings(rows))
    out["local_h_over_mean"] = sample_raster(H, plane_xy) / max(H[H > 0].mean(), 1.0)
    return np.column_stack([out[f] for f in FEATURES])


def train(X, y, groups, with_model_input=True):
    cols = slice(None) if with_model_input else slice(1, None)            # H05b ablation drops K_model
    model = HistGradientBoostingRegressor(max_iter=600, learning_rate=0.05, max_leaf_nodes=63,
                                          l2_regularization=1.0)
    scores = []
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        model.fit(X[tr, cols], y[tr])
        scores.append(np.sqrt(np.mean((model.predict(X[te, cols]) - y[te]) ** 2)))
    model.fit(X[:, cols], y)
    return model, float(np.mean(scores))


def target(K_hf, K_model, floor=0.02):
    return np.log(np.maximum(K_hf, floor) / np.maximum(K_model, floor))


# Application to AIJ (held out): K_corrected = K_model * exp(model.predict(features(...)))
```

**Protocol.**
- Grouped cross-validation on the corpus chooses the hyperparameters.
- The model is then frozen and applied **once** to AIJ D and E, for H05a and H05b.
- H05c repeats this with the F11/H04 output as the base.

**Decision rule.**
- **H05a and H05b hold:** ship an opt-in `wind.Correction(model_path)` that applies the frozen model to the pedestrian plane. It is versioned with its training corpus and recorded in the result metadata, like the parameterizations.
- **H05a fails:** the corpus does not cover the AIJ morphologies. Report which features fall out of distribution.
- **H05b fails:** the physics input does not help, which would favour pure surrogates. That is unlikely, and would change the review's §6.

### H06: learned parameterization constants

- **Idea tested:** D2. No published precedent was found.
- **Why:**
  - Phase 5 tuned *flags* on *one* case, and the result did not transfer.
  - Calibrating the *physical constants* of the zones jointly over many cases, with leave-one-case-out validation, is the scientifically sound version. Candidates:
    - the Fackrell wake-length coefficients `1.8` and `0.24` (`PolygonWake.cpp:177`);
    - the cavity and rooftop lengths;
    - F07's a-coefficient;
    - F08/H03's four constants.
- **Hypotheses:**
  - **H06a.** In leave-one-case-out validation, the calibrated constants improve the held-out score on *every* held-out case. The training cases are:
    - AIJ A, B and C (H02);
    - the mechanism matrix (H08) and the `industrial_residential` neighbourhood, against their RANS fields (2.0.1). The H09 families stay out;
    - the isolated towers (H03).
  - **H06b.** On the fully held-out AIJ D and E, the calibrated constants beat the defaults with the bootstrap interval above zero, without compression (slope ≥ 0.7).
- **Improvement for the app:** better defaults for every user, derived from data and transparent. It is the opposite of per-project tuning.
- **Performance:**
  - **Runtime:** unchanged.
  - **Search:** offline, about 200 evaluations × every training run at 2 m (~3 min with `--jobs 6`), so about 10 h.
- **Objective,** fixed before the search: J = mean over cases of (R − |FB|), subject to slope ≥ 0.7. It is not q (F01).
- **New dependency:** `uv add --group validate optuna`.

```python
# validation/experiments/h06_constants.py
import optuna

from experiments import harness

SPACE = dict(fackrell_a=(1.2, 2.4), fackrell_b=(0.12, 0.36), cavity_length=(0.6, 1.4),
             rooftop_scale=(0.6, 1.4), canopy_a=(4.0, 14.0), tall_a=(0.006, 0.02))
TRAIN = ("A", "B", "C", "mechanism_canopy", "mechanism_tower", "mechanism_wall", "synthetic_industrial")  # H09 families excluded


def evaluate(constants, cases) -> float:
    """Mean (R - |FB|) over cases; -inf if any case compresses (slope < 0.7)."""
    total = []
    for case in cases:
        comps = run_case_with_constants(case, constants)     # branch exp/constants: wind.Parameterizations(constants=...)
        for c in comps:
            if harness.SCORES["slope"](c.simulated, c.measured) < 0.7:
                return float("-inf")
            total.append(harness.SCORES["r"](c.simulated, c.measured) - abs(harness.SCORES["fb"](c.simulated, c.measured)))
    return sum(total) / len(total)


def leave_one_out():
    results = {}
    for held in TRAIN:
        train = [c for c in TRAIN if c != held]
        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=0))
        study.optimize(lambda t: evaluate({k: t.suggest_float(k, *v) for k, v in SPACE.items()}, train),
                       n_trials=200)
        results[held] = dict(best=study.best_params, held_out=evaluate(study.best_params, [held]),
                             default=evaluate({}, [held]))
    return results
```

**The native change needed.** A branch, `exp/constants`, turns the literals into a `ParameterizationConstants` struct with today's values as defaults. The regression test is bit-identical output at the defaults.

**Decision rule.**
- **H06a and H06b hold:** the calibrated values become new defaults in a native batch. The corpus and the search log are its evidence.
- **H06a holds but H06b fails:** the training set does not represent D and E. Add cases, and do not change the defaults.

### H07: GPU lattice Boltzmann as a detailed tier

- **Idea tested:** the review's tier E, with a hybrid twist.
- **Why:**
  - Decision-grade studies need LES or RANS validated to the guidelines.
  - The CUDA backend is coming. LBM is bandwidth-bound like SOR, simple to port, and gives gusts directly.
  - The question is whether it fits the app's time budget, or only an offline tier.
- **Hypotheses:**
  - **H07a.** LBM-LES at 1 m on Case E, with wall-modelled walls, reaches per-direction R ≥ 0.7 against the thermistors (time-mean scalar speed). It also beats F11/H04's R by ≥ 0.05.
  - **H07b.** It does so in ≤ 5 min per direction on one RTX 4090-class GPU, which would make it an in-app "detailed" mode.
  - **H07c (hybrid).** Starting the LBM from the dtcc-qes (or F11) field instead of a uniform one cuts spin-up by ≥ 50 %. Spin-up is the time until the running means at the 2 m probes stay within 2 %.
  - **H07d.** At 0.5 m (b/32 for Case E's small buildings, per Han et al. 2020), R improves by ≥ 0.05 over 1 m, at ≤ 30 min per direction.
- **Improvement for the app:** a validated detailed mode, or a training-data generator for H05 at LES fidelity. Gust statistics come in both cases.
- **Performance:**
  - **The estimate:** 1 m with a 500 m fetch is about 10⁸ cells × 10⁴–10⁵ steps. At 5 GLUPs/s that is 3–30 min.
  - **H07b** decides whether it is in-app (≤ 5 min) or offline.
- **Design:**
  - **Solver:** solver-agnostic. An adapter wraps XLB (Autodesk; Python, with JAX or Warp) or FluidX3D, which is for research use only. Check both licences.
  - **Voxelisation reuses dtcc-qes:** a run at the LBM resolution gives `cell_flags` and the start field on exactly the dtcc-qes grid.
  - **Probes:** they record time series. The mean vector, the mean scalar speed and GEM come from those.

```python
# validation/experiments/h07_lbm.py
from dataclasses import replace

import numpy as np

from aij import campaigns, runner
from dtcc_qes import comfort, wind
from experiments import harness
from proto import lbm_adapter          # thin wrapper over XLB/FluidX3D: run(mask, init, inflow, probes, steps)


def lbm_case(spec, resolution, start="qes"):
    spec = replace(spec, resolution=resolution, max_iterations=1 if start == "uniform" else spec.max_iterations,
                   vertical="uniform", turbulence=False, max_cells=400_000_000)   # LBM needs cubic cells
    args = runner.inputs(spec)
    result = wind.run(args["city"], args["profile"], **args["run"])          # voxels + start field
    init = result.velocity if start == "qes" else None
    series = lbm_adapter.run(mask=result.solid_mask, init=init, dz=result.dz, profile=args["profile"],
                             probes=args["probes"].xyz - np.asarray(result.origin), seconds=900.0,
                             sample_every_seconds=0.1)
    uref = args["reference_speed"]
    speed = np.linalg.norm(series.velocity, axis=-1)                         # (time, probe)
    std = np.std(series.velocity[..., 0], axis=0)
    return dict(K_vector=np.linalg.norm(series.velocity.mean(axis=0), axis=-1) / uref,
                K_scalar=speed.mean(axis=0) / uref,
                gem=comfort.gust_equivalent_mean(speed.mean(axis=0), std, peak_factor=3.0) / uref,
                spin_up_seconds=series.spin_up(window=60.0, tolerance=0.02),
                wall_seconds=series.wall_seconds, cells=int(result.solid_mask.size))


for label in campaigns.FINE_E_LABELS:
    for state in ("before", "after"):
        spec = campaigns.case_e(label, state)
        for start in ("qes", "uniform"):
            harness.write("H07", f"{label}-{state}-r1-{start}", lbm_case(spec, 1.0, start))
```

Check the keyword arguments of `comfort.gust_equivalent_mean` against its signature (`src/dtcc_qes/comfort.py:137`) before the run.

**Decision rule.**
- **H07a and H07b hold:** an in-app detailed mode on the CUDA backend.
- **H07a holds, H07b fails:** an offline tier, which also generates H05's corpus at LES fidelity.
- **H07c holds:** dtcc-qes earns a role as the initialiser of any detailed solver, IBOFlow included. That is a cheap and concrete integration point within DTCC.

### H08: a mechanism matrix with RANS references

- **Idea tested:** QES_PHYSICS §3.3, adopted as Group 2's development set.
- **Why:** Cases D and E mix every effect, and they are no longer untouched. Controlled flat-ground cases isolate each mechanism, and they give references for developing constants without touching D, E or the confirmation set (H09).
- **Cases.** The 15 configurations of QES_PHYSICS §3.3:

  | Mechanism | Configurations | Count |
  |---|---|---|
  | Canopy arrays | 6 × 6 blocks with H = 10 m and 20 m sides; λp 0.16 and 0.36; aligned and staggered; 0° and 45° | 8 |
  | Tower in canopy | A 30 or 60 m tower in the λp 0.16 aligned array, at 0° and 45° | 4 |
  | Tower on a podium | One 60 m tower on a 40 × 40 × 10 m podium, at 0° | 1 |
  | Wall and corner | One isolated building at 0° and 30°, with transects 0.5, 1 and 2 m from the wall | 2 |

  The empty domain needs no RANS; it is an invariance test (1.0.6).
- **Hypotheses:**
  - **H08a.** On the canopy arrays, dtcc-qes's row-averaged interior K at 2 m exceeds RANS by ≥ 30 %. This is the Case E "before" level error, in isolation.
  - **H08b.** On the tower-in-canopy cases, dtcc-qes underpredicts the strongest speed-ups by ≥ 30 %. The measure is the ten largest K increases over the unchanged array.
  - **H08c.** The F07 (canopy) and F08 (tower) improvements seen on D/E also appear here, with no refit.
- **Use:**
  - development references for F07's column arm, for H03's calibration and for F09's wall and corner check (with origin shifts);
  - **a caution on the wall cases:** RANS with wall functions is not reliable within 0.5–1 m of a wall. The wall transects therefore judge consistency across grids, not near-wall truth.
- **Cost:** 15 RANS runs (2.0.1), plus up to 6 refinements chosen from the geometry before any dtcc-qes comparison. QES_PHYSICS's cap of 45 runs covers H08 and H09 together.

```python
# validation/experiments/mechanisms.py
import numpy as np
from shapely.geometry import box


def canopy(lp, staggered, n=6, side=20.0, height=10.0):
    """(polygon, height) rows of an n x n array with plan density lp."""
    pitch = side / np.sqrt(lp)
    rows = []
    for j in range(n):
        shift = 0.5 * pitch if staggered and j % 2 else 0.0
        for i in range(n):
            x, y = i * pitch + shift, j * pitch
            rows.append((box(x, y, x + side, y + side), height))
    return rows


def with_tower(rows, height, index=None):
    """Replace the block nearest the centre by a tower of ``height`` with the same footprint."""
    centre = np.mean([p.centroid.coords[0] for p, _ in rows], axis=0)
    index = index if index is not None else int(np.argmin([np.hypot(*(np.array(p.centroid.coords[0]) - centre))
                                                          for p, _ in rows]))
    return [(p, height if i == index else h) for i, (p, h) in enumerate(rows)]


MATRIX = ([("canopy", lp, st, d) for lp in (0.16, 0.36) for st in (False, True) for d in (270.0, 225.0)]
          + [("tower", 0.16, h, d) for h in (30.0, 60.0) for d in (270.0, 225.0)]
          + [("podium", 0.16, 60.0, 270.0), ("wall", None, None, 270.0), ("wall", None, None, 240.0)])
```

### H09: an intervention transfer set

- **Idea tested:** QES_PHYSICS §3.2.
- **Why:** the app's key question is "what does this building change?". Cases D and E give a single intervention, and it has already been inspected. Added-tower pairs in three unseen districts test whether intervention skill transfers.
- **Design:**
  - **Geometry:** the `perimeter_neighbourhood`, `slab_estate` and `mixed_downtown` benchmark geometries (`docs/urban-wind-benchmarks.md`), each as is and with one added tower on a recorded clear site.
  - **Directions:** 0°, 90°, 225° and 270°, so 24 RANS runs.
  - **Isolation:** geometry outside the intervention stays byte-identical.
  - **Exclusion:** the three families never enter development or training (H05, H06). The perimeter family is kept out of everything except this confirmation.
- **Hypotheses**, for a candidate promoted from Group 1 (F07, F08 or F11) against the baseline:
  - **H09a.** ΔK MAE against RANS falls by ≥ 20 %, macro-averaged over the three families, and no family gets worse.
  - **H09b.** Strongest-speed-up recall against RANS rises by ≥ 0.10 in every family.
- **The freeze rule:** predictions are frozen before any error is inspected. Once the errors have been viewed, the set is consumed for that candidate.
- **Cost:** 24 RANS runs (2.0.1).

## 3. From experiments to product

Experiments do not ship. Every native change costs a re-qualification (the native policy identity), so the outcomes are grouped into at most three native batches.

| Batch | Content | Triggered by | Product gate |
|---|---|---|---|
| **1: speed** | The new ω or Chebyshev (F02); native multigrid (geometric MG with z-line smoothing, or hypre structured MG), but only once it is needed (F11/H04, or a 0.5 m tier) | F02 H2b; for multigrid, F06 H6a and H6b *and* that need | Case E at 1 m ≤ 15 s end to end, and Case D/E at 0.5 m ≤ 3 min; probe K within 1e-4 of converged SOR; simple case ≤ 5 s |
| **2: physics** | **Either** the momentum step plus k transport (F11 → H04, F10), **or** the canopy background, tall-building zone and smooth edges (F07, F08/H03, F09) | Decision point G1 and H04, or H03 | The experiment's thresholds, rerun on native code at 2 m and 1 m; section 0.1 targets |
| **3: defaults** | Calibrated constants (H06), and a residual correction as an opt-in data file (H05) | H06, H05 | Held-out AIJ improvement; bit-identical output at the old defaults |

Python-only follow-ups need no re-qualification and can ship at any time:
- the preparation-reusing `wind.Session` (F12);
- R16's neighbourhood range and the `grid_sensitive` mask (F03);
- `comfort.assess_ensemble` with shared preparation (F03);
- direction smearing (F04);
- the new metrics (F01).

## 4. Schedule and decisions across the groups

```text
            Group 1 (workstation, in-house)              Group 2 (outside tools, offline)
Week 1      1.0 infrastructure, gate P0                  2.0.1 CFD pipeline; request AIJ A-F data;
            F01, F05, F12, F03 flags (F14 done)          H01 meshing starts (long lead time)
Week 2      F02, F04, F03 ensemble, F13                  H01 runs (cluster); H08 geometry frozen
Week 2-3    F06, F07, F08                                H02 if the data has arrived
Week 3-5    F11 (dev + one night), F09, F10              H01 results -> diagnosis maps
            ── decision point G1 ──
Month 2     native batch 1 (speed)                       G1 = momentum: H04 (scale, 1 m, vs RANS)
                                                         G1 = zones:    H03 (tall-building calibration)
Month 2-3   native batch 2 (physics)                     H08 and H09 RANS runs; corpus for H05/H06
Month 3+    Python follow-ups ship                       H05, H06; H07 once the CUDA backend lands
```

**How Group 1 steers Group 2:**
- **F01** fixes the metrics that every Group 2 gate uses.
- **F11** decides between H04 and H03:
  - if momentum works, H03 is dropped unless the tower effect is still too weak;
  - if it fails, H04 is dropped.
- **F08** decides whether H03 is needed at all. If H8c holds, calibration is only confirmation.
- **F06** decides whether H04 can plan for 1 m on multigrid, or must wait for the GPU backend.
- **F13** predicts which F08 arm survives the projection: imposed speeds or divergence-free kernels.

**H01 runs whatever Group 1 finds.** It is the yardstick for every Group 2 hypothesis, and its long lead time puts it in week 1.

**The rules for both groups:**
- each experiment's cost row (section 0.1) appears next to its accuracy row;
- a result that breaks a hard ceiling is not adopted, however good;
- any change to a hypothesis after the first run is logged here, with its date and reason.

**What success looks like for the app,** if the main line holds (F02, F06, F11 → H04, F04, F03):
- **Speed:** simple cases under 10 s per direction, districts at 2 m in about 30 s, and districts at 1 m in under 3 min.
- **Accuracy:** near RANS, with the tower effect of the right sign.
- **Honesty:** comfort classes with a stated probability, and grid-sensitive receptors flagged.

That would change the review's verdict from "screening only" to "fit for early design decisions, checked by a detailed study before compliance".

## 5. Cross-check with QES_PHYSICS_MODEL_EXPERIMENTS.md

Done on 2026-11-02. Before this section was written, three of that plan's claims were checked against the stored runs or the measured data, using scripts in the session scratchpad (nothing was added to the repo):

| Check | Result |
|---|---|
| Is the existing 73 % sign agreement better than always predicting an increase? | No: 0.729 against 0.735. Balanced accuracy is 0.768 against 0.500, so the model does get directions right; its failure is the magnitude. |
| Does the building input order change the result? | Case E SW (footprint cleaning) and Case D at 0° are bit-identical. Case D at 45° (no cleaning) changes 8 of 78 probes, by at most 4.6e-4 in K. |
| Does a Gaussian expected-speed operator match the thermistors better than the RMS speed? | No (F14): the RMS speed gets q 0.91 and MAE 0.037; the Gaussian E\|U\| gets q 0.85 and MAE 0.048–0.054. |

### What was adopted

| Item | QES_PHYSICS section | Where it is here |
|---|---|---|
| Preparation reuse across directions; cold and warm timing | E0, §2.2 | F12; the timing protocol in 0.1 |
| Stage attribution of the zone contributions | E0, E2-A | F13 |
| Building-order invariance, and the other invariance tests | E2-A, §11 | 1.0.6 (measured) |
| Balanced sign accuracy, strongest-speed-up recall, ΔK MAE and bias, and the trivial controls | §3.4 | Rule 6 in 0.3; F01; every tower gate |
| D and E as development data, with untouched sets for promotion | §3.2 | "How the experiments are grouped"; 0.2 |
| A mechanism matrix with RANS references | §3.3 | H08 |
| Added-tower pairs in three synthetic families as a transfer set | §3.2 | H09; the H05 and H06 corpora changed to match |
| The column momentum balance with layer-wise frontal area; the isotropic control arm | E1 | F07's arms |
| Divergence-free tower kernels; smooth exposure activation; order-independent composition | E2 | F08's arms; F09's arm |
| Physical transition widths; grid-origin shifts; a wall-law tangential initialisation | E3 | F09 |
| An inflow k reference decoupled from the ground roughness | E4 (b) | F10's arm (b) |
| A coarse momentum correction transferred to the fine grid | E5 | H04e |
| A consistent operator pair for the momentum projection | E5 | The F11 projection boundary fix |
| Native multigrid only once a need is shown | §12 | Section 3, batch 1 |
| Peak-RSS caps of 2 GiB (2 m) and 8 GiB (1 m); 4-thread timing | §2.1 | 0.1 |

### Where this document disagrees, or the other plan looks unnecessary or wrong

1. **The sensor quadrature (E4) is unnecessary.**
   - **There is an exact formula.** k-only data gives an isotropic covariance; that covers all of Case E, and the QES-Turb output under an isotropy assumption. For that case the Gaussian expected speed has a closed form, which is exact and cheaper than Gauss–Hermite rules of order 5 to 17. By the plan's own check, order 5 is 4 % off at zero mean.
   - **The question is already answered.** F14 shows that the Gaussian operator fits the Case D thermistors *worse* than the RMS speed, so the observation-model sub-experiment is settled: keep √(U² + 2k).
2. **Its balanced-accuracy gate of "≥ 0.65 absolute" never binds.**
   - The baseline is already 0.768, so only the "+0.05" clause matters (≥ 0.82).
   - **Its framing of the sign is also off.** The plan treats the sign as what is wrong, but the sign is right at 69 % of measured increases and 85 % of decreases. The error is the magnitude, dominated by a cluster of spurious strong wake decreases.
   - ΔK MAE and the mean ΔK bias, which the plan also uses, are the right primary metrics.
   - The same correction applies to `AIJ_VALIDATION_REVIEW.md`. It describes the tower result as a predicted slowdown, which is true of the mean but not of most points.
3. **E1 freezes the eddy diffusivity from the external profile's shear.** That is not the shear inside the canopy, where the column's own shear peaks at roof level. F07's column arm updates K_m from the column's own shear in the same iteration, at no extra cost.
4. **The order-invariance check is worth having, but not as a design driver.** The measured effect is at most 4.6e-4 in K at the AIJ probes, far below every gate. The composition rule should be judged by attribution (F13) and by the tower mechanisms, not by order dependence.
5. **E5's 8 m arm is unlikely to tell us anything about Case E,** whose canopy (H̄ ≈ 6 m) would sit inside one cell. That budget is better spent on 4 m against the full 2 m relaxation (F11).
6. **E5's sequencing, with momentum only after E1/E2 fail, is the wrong order.**
   - F11's screening run costs a few weeks of prototype work and one night of runs. If it works, it makes much of E1/E2's zone engineering redundant, and running it in parallel is cheaper than finding that out after E1–E3.
   - Momentum at 2 m also fits that plan's own 180 s "enhanced mode" by a wide margin; the native estimate is about 26 s.
7. **E3's near-wall gate takes RANS as near-wall truth.** RANS with wall functions does not resolve 0.5–1 m from a wall reliably. Unless wall-resolved LES or tunnel data are available, the wall transects should judge consistency across grids and origins (F09), not physical accuracy.
8. **E0's pass bar of a 20 % saving is low.** Preparation is about 4 of the 7 s per Case E direction at 2 m, so ≥ 40 % is the expected outcome (F12).
9. **The two plans set different fast-tier budgets for Case E at 2 m:** ≤ 12 s (at most 20 s) there, against ≤ 30 s (at most 60 s) here.
   - The tighter one rules out 5–9-member ensembles (F03, F04) unless F12's reuse lands.
   - This is a product decision for the user, not a technical one.
10. **This document covers several experiments that plan lacks:**
    - end-use comfort-class metrics (F01);
    - SOR relaxation (F02);
    - probabilistic classes and grid flags (F03);
    - the direction ensemble (F04);
    - the α null test (F05);
    - learned constants (H06);
    - a GPU LBM tier (H07).

    Its deferral of a training programme matches where H05 sits, late in Group 2.

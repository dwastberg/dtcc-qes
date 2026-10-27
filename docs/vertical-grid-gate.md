# Vertical-grid sensitivity and cost gate

This study compares numerical solutions of the embedded QES model. It does not
establish experimental accuracy or validate a pedestrian comfort criterion.
Stage A's explicit-grid API is unchanged; the study adds no public sampler or
automatic generator.

The decisions below record the original study outcome. The updated
[implementation plan](../DYNAMIC_VERTICAL_GRID.md) supersedes its blanket stop
before Stage B. The subsequent [focused solver diagnosis](vertical-grid-diagnosis.md)
supports a precision remedy candidate and identifies sampling/explicit preview
as the next milestone. The measurements and failed-reference exclusions in
this report are unchanged.

## Reproduction

From the checkout, with the existing development environment:

```sh
cmake -S . -B build/extension -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_OPENMP=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build build/extension --target vertical_grid_study --parallel 8
.venv/bin/python tools/run_vertical_grid_study.py --output build/vertical-grid-study/main
.venv/bin/python tools/run_vertical_grid_study.py --output build/vertical-grid-study/main --summarize
.venv/bin/python -m pytest tests/test_vertical_grid_study.py -q
```

The native executable runs one geometry/grid/wind combination per process.
The Python driver executes workers sequentially, with a fixed shuffled order
and two independent timing repetitions. It writes `raw.json.gz` containing all
pedestrian velocity vectors, masks, coordinates, checkpoints and unsuccessful
budget trials, and `summary.json` containing the assessment. Reassessment uses
the stored raw samples without repeating the solves. Binary SHA-256, compiler,
platform, QES revision, backend and thread count accompany the measurements.
The archived [raw samples](data/vertical-grid-gate/raw.json.gz) and
[assessment](data/vertical-grid-gate/summary.json) were recorded on 2026-10-26.
Use `--output docs/data/vertical-grid-gate --summarize` to reassess that archive;
use a build directory for new measurements to preserve the recorded evidence.

## Declared experiment

All cases use bounds `(0, 0, 0)–(80, 80, 64) m`, `dx = dy = 2 m`, reference
speed 5 m/s at 10 m, roughness length 0.1 m, wall roughness 0.001 m and winds
from 270° and 315°. The sensor is at `(5, 5) m`. Model flags retain the bridge
defaults: rooftop 1, upwind cavity 2, street canyon 1, wake 2, sidewall 1,
street intersection 0 and high rise 0. The tower geometry therefore exercises
the production defaults, including the disabled optional high-rise model.

| Case | Rectangular footprints `(x, y, width, length)` in metres | Heights |
| --- | --- | --- |
| Isolated | `(32, 32, 12, 16)` | 12 m |
| Passage | `(24, 24, 12, 32)`, `(44, 24, 12, 32)` | 12 m; 8 m clear passage |
| Array | `(22, 22, 12, 12)`, `(42, 22, 12, 12)`, `(22, 42, 12, 12)`, `(42, 42, 12, 12)` | 8 m |
| Tower | Same four footprints as array | 24 m at `(42, 42)`; others 8 m |

These compact synthetic domains deliberately hold the physical boundaries
fixed across the five grids. Their boundary clearances are not a proposed
urban CFD domain standard. Neither these geometries nor the approach profiles
are represented as AIJ experiments.

The four explicit uniform grids use 2, 1, 0.5 and 0.25 m layers, respectively
32, 64, 128 and 256 layers. A single hand-built 52-layer grid uses:

- eight 0.5 m layers, through 4 m;
- thicknesses `9/16, 10/16, …, 16/16 m`, reaching 10.25 m;
- fourteen 1 m layers, reaching 24.25 m;
- thicknesses `9/8, 10/8, …, 16/8 m`, reaching 36.75 m;
- twelve 2 m layers, reaching 60.75 m;
- two 1.625 m layers, ending exactly at 64 m.

Every thickness and accumulated face is exactly representable in float32.
Maximum adjacent growth is 1.125. The final thickness decreases to fit the
endpoint. This is one explicit test grid, not an implementation or endorsement
of the proposed automatic growth/roof/upper-cap policy. Roof representation
errors are reported, rather than assuming identical vertical occupancy.

## Sampling and solve acceptance

There are 1,444 fixed horizontal points, at native interior cell centres
`x, y = 3, 5, …, 77 m`. Sampling is at **1.5 m**, using the same staggered-face
averages and float32 operand order as the bridge. Interpolation uses actual
physical centres, interpolates the three velocity components and then computes
their magnitude. An exact-centre request uses only that layer; a contributing
solid cell invalidates a point; out-of-centre-range requests are invalid.
There is no interpolation of flags. Grid comparisons use the intersection of
the five fluid masks and separately report any solid/fluid transitions.
`K = ||mean velocity|| / 5`; it is not mean scalar speed or gust speed.
Magnitude includes all three components, matching `WindResult.speed`.

Every checkpoint starts from zero multipliers and the same parametrized initial
velocity. A derived solver used only by this executable sets its protected
tolerance to -1 to force exactly the requested sweeps. The production solver,
Python tolerance validation and public convergence flag are unchanged. The
native worker checks that the requested work actually ran.

The driver begins with `N = 1,000`, checks `N, 2N, 4N` and doubles N after a
failure, up to `N = 8,000` (32,000 sweeps at the final checkpoint). It repeats
the selected final budget in an independent process. All three checkpoints
must satisfy `max_div * Hmax / 5 <= 1e-3` and
`RMS_div * Hmax / 5 <= 1e-4`; both successive pedestrian velocity-vector
comparisons must satisfy maximum change / 5 `<= 1e-3` and 95th percentile
`<= 5e-4`, with unchanged validity masks. No extra interior cells are removed.
The volume-weighted conservative diagnostic reports the prescribed top band
separately and does not assess the highest physical band, as in Stage 0.

Ten-times tighter residual checks are recorded at every checkpoint as a
precision/error-budget diagnostic. The proposed bounds and automatic defaults
remain provisional; a numerical plateau does not by itself validate a bound.

Preparation includes input/domain construction, the wind profile,
parameterizations and solver allocation. Solve time includes multiplier reset,
RHS formation, requested sweeps and final face correction. Sampling time and
residual-assessment time exclude JSON output. Final-checkpoint time and the
sum of all three stability-demonstration solves are separate quantities.
Peak RSS is measured in each native process, including its arrays and output
buffer before final output, excluding the Python driver. Medians and ranges preserve repeat
variation. Failed grid pairs have their matched-accuracy speed/error and runtime
comparisons withheld; raw residuals and costs remain available for diagnosis.
The budget-search trials add work beyond the three-checkpoint demonstration;
their full costs are retained in the raw archive, not included in a final-solve
runtime ratio. These measurements do not determine the minimum possible solve
budget or promise production runtimes on another machine.

## Results and decision

**Decision: stop before Stage B.** The stretched candidate reduces cost against
uniform 0.5 m layers, but the full fine-grid comparison fails the declared
accuracy gate. The synthetic suite also does not establish a compelling need
for finer layers by the proposed aggregate speed thresholds. Investigate the
solver failure and spatial sensitivity before freezing defaults or adding the
automatic policy.

All 80 final workers completed: four geometries × two winds × five grids × two
repetitions. **76 passed, four failed.** Both repetitions of the 0.25 m tower
case fail for both directions. All 40 repeat pairs have identical sampled
velocity vectors, validity masks, iteration counts and residual diagnostics.
There are 15 additional budget-search trials in the archive.

The host was Apple arm64, macOS 15.7.1, Apple Clang 17, Release, serial
lexicographic SOR with one thread. QES revision is
`e0fb62e9fe5fffc8b4aef8f250f75f929ad27c13`; analysis used Python 3.13.11 and
NumPy 2.5.4. This is a serial cost study; the OpenMP test results below do not
establish OpenMP performance.

### Accuracy and cost

Each accepted 2 m, 1 m, 0.5 m and stretched case passes at checkpoints
1,000/2,000/4,000. Accepted 0.25 m cases require a first checkpoint of 2,000
(array, isolated 315°) or 4,000 (passage, isolated 270°), followed by 2N/4N.

The preparation, RSS and final-solve columns below are medians of the eight
case/wind medians, each based on two independent workers. The 0.25 m solve
range covers only its six accepted case/wind combinations; its two rejected
tower combinations have no matched-accuracy cost claim.

| Grid | Layers / physical cells | Maximum `dx/dz` | Accepted case/wind combinations | Preparation (ms) | Final solve (s) | RSS (MiB) |
| --- | --- | --- | --- | --- | --- | --- |
| Uniform 2 m | 32 / 51,200 | 1 | 8/8 | 1.83 | 0.698 | 9.11 |
| Uniform 1 m | 64 / 102,400 | 2 | 8/8 | 2.92 | 1.415 | 15.39 |
| Uniform 0.5 m | 128 / 204,800 | 4 | 8/8 | 5.45 | 2.836 | 27.31 |
| Uniform 0.25 m | 256 / 409,600 | 8 | 6/8 | 11.16 | 11.42–23.34, accepted subset only | 51.16 |
| Hand-built stretched | 52 / 83,200 | 4 | 8/8 | 2.85 | 1.150 | 13.09 |

At the same accepted budgets, the stretched final solve takes 39.7–41.7% of
the uniform 0.5 m time: about 2.4–2.5 times faster, with about half its measured
RSS. It costs approximately 1.6 times the 2 m solve. Final-checkpoint times are
4N-sweep solves; the complete three-checkpoint demonstration costs approximately
7/4 as much, with exact measurements in the summary. Sampling 1,444 points
takes 10–74 microseconds across the recorded workers; short timings have limited
precision. Two repetitions give an observed range, not a robust performance
guarantee.

### Pedestrian sensitivity

All comparisons below meet the common solve-accuracy criteria. The common
fluid-point counts are 1,396 (isolated), 1,252 (passage) and 1,300 (array and
tower), out of 1,444 points. There are **zero** solid/fluid transitions between
the five grids or successive checkpoints. Uniform grids represent these roofs
exactly; the stretched grid overrepresents 8 m roofs by 0.3125 m and 12/24 m
roofs by 0.25 m. Its differences therefore include roof discretization as well
as changes to the vertical operator and parameterization sampling.

| Case / direction | P95 `abs(delta K)`, 2 m vs 0.5 m | P95 `abs(delta K)`, stretched vs 0.5 m | Peak-speed difference, stretched vs 0.5 m |
| --- | --- | --- | --- |
| Isolated / 270° | 0.02369 | 0.00267 | 0.37% |
| Isolated / 315° | 0.02327 | 0.00157 | 0.41% |
| Passage / 270° | 0.02570 | 0.00454 | 0.38% |
| Passage / 315° | 0.02352 | 0.00383 | 0.56% |
| Array / 270° | 0.02539 | 0.00490 | 0.92% |
| Array / 315° | 0.02420 | 0.00412 | 1.03% |
| Tower / 270° | 0.02466 | 0.00496 | 0.85% |
| Tower / 315° | 0.02414 | 0.00372 | 0.12% |

The stretched candidate reduces the P95 discrepancy against 0.5 m by about
80–93%. However, even the 2 m grid is within the proposed P95 `delta K < 0.05`
and 5% peak-speed thresholds in these synthetic cases: its largest pointwise
`delta K` is 0.04315 and largest peak difference 2.30%. This does not establish
that 2 m cells are adequate for real comfort studies. The cases have aligned
uniform-grid roof heights, fixed coarse horizontal resolution and no measured
reference data. More challenging geometry and experimental comparisons remain
necessary to establish a useful automatic preset.

Small aggregate errors also hide a hotspot-ranking change. In the tower/270°
case, the 0.5 m maximum is at `(57, 41) m`, whereas 2 m and stretched grids
place it at `(37, 35) m`, a 20.9 m separation. On the 0.5 m grid these two
locations have K = 0.79787 and 0.79691, respectively, so the competing peaks
are close. The stretched values are 0.79825 and 0.80463. A sub-1% peak-value
change therefore does not imply a fixed hotspot location. The archive retains
the whole plane and maximum-error locations. In points with reference K < 0.1,
the largest stretched-vs-0.5 m absolute change is 0.00885; relative errors there
are not used as acceptance criteria.

For the six accepted 0.25 m case/wind combinations, 0.5-to-0.25 m P95 changes
are 0.00211–0.00248, with at most 0.19% peak-speed change. Stretched-to-0.25 m
P95 changes are 0.00305–0.00641 and peak changes at most 0.91%. These statistics
exclude the failed tower comparisons; they are numerical sensitivity evidence,
not a fully converged three-dimensional or experimentally validated reference.

### The fine-grid failure

For the 24 m tower, the maximum allowed dimensional residual is
`1e-3 * 5 / 24 = 2.0833e-4 s^-1`. The 0.25 m grid remains above it:

| Sweeps | Maximum residual, 270° (s^-1) | Normalized maximum, 270° | Maximum residual, 315° (s^-1) | Normalized maximum, 315° |
| --- | --- | --- | --- | --- |
| 8,000 | 3.30210e-4 | 1.58501e-3 | 3.26455e-4 | 1.56698e-3 |
| 16,000 | 4.57048e-4 | 2.19383e-3 | 2.70844e-4 | 1.30005e-3 |
| 32,000 | 2.66433e-4 | 1.27888e-3 | 2.69115e-4 | 1.29175e-3 |

The RMS target and velocity-stability checks pass at these checkpoints; the
maximum successive vector change is below `5e-6 * Uref`. Residual maxima
fluctuate rather than falling monotonically with more work. This is an
observed plateau on these cases, not proof of a universal float32 floor or
proof that line relaxation fixes it. The next investigation must distinguish
stencil/face-correction errors, roundoff and conditioning using the same bounds.
Do not relax the target or discard its worst cells to obtain a pass.

Ten-times tighter residual checks pass at all checkpoints in all 16 uniform
2 m workers, 12 of 16 uniform 1 m workers, four of 16 uniform 0.5 m workers,
four of 16 stretched workers and none of the uniform 0.25 m workers. Thus the
stricter subset does not justify freezing the targets across fine grids. Stage
0/A manufactured/injection tests remain correctness evidence, not a substitute
for this coupled urban case.

The separately reported top-band maximum ranges from 0.00550 to 0.28068 s^-1.
It remains an unresolved boundary limitation. Domain-height sensitivity is
required before selecting an automatic preset; this study does not hide it
inside the interior acceptance norm.

### Sampling alignment and revised next steps

An independent analytic flat-profile control gives:

| Uniform layer thickness | Sampled K at 1.5 m | Bias against exact K = 0.60076193 |
| --- | --- | --- |
| 2 m | 0.57569856 | -0.02506337 |
| 1 m | 0.60076193 | 0: exact centre |
| 0.5 m | 0.59808410 | -0.00267783 |
| 0.25 m | 0.60009865 | -0.00066328 |

The 2 m interpolation error is -4.17% of the exact local speed. This is on the
same scale as the observed coarse-to-fine P95 changes and contributes to them;
it does not decompose the disturbed building flow exactly. The 1 m control
demonstrates alignment, not a recommendation to place the evaluation height at
only the second centre. Centre alignment cannot replace resolving building
flow or the planned near-ground layers.

The revised plan is to diagnose operators and precision first (section 5.6),
test a supported remedy, then repeat this gate without changing its acceptance
criteria. Assess feasible centre-aligned fine bands as part of Stage C. Keep
the aspect-8 limit, growth 1.15, roof buffers and upper cap provisional; this
one stretched grid does not select those defaults. Domain-height, finer-x/y,
OpenMP cost and experimental studies remain separate work. Stage B and C are
not implemented by this delivery.

## Tooling validation

The manufactured affine-vector self-test checks staggering, interpolation,
first/last exact centres, zero-weight solid neighbours, both solid flag types,
out-of-centre-range invalidity and rejected nonfinite/out-of-domain heights.
Python assessment tests ensure that stable speed cannot hide rotating vectors,
one bad residual checkpoint or changing validity cannot pass, and failed pairs
receive no matched-accuracy runtime/error statistics.

Recorded checks on this checkout:

- 344 Python tests pass, with the previously documented
  `test_explicit_import_registration` mismatch explicitly deselected. This
  includes 11 study-assessment tests.
- Nine serial and 12 OpenMP native CTests pass, including the new sampler test.
- The new sampler test passes ASan/UBSan. The full prior sanitizer solver suite
  was not repeated for this study-only target; production solver sources did
  not change.
- Serial and OpenMP native symbol audits pass.
- Rebuilt coarse and stretched workers reproduce archived sampled vectors and
  residuals exactly; the two timing repetitions also agree exactly numerically.
- Offline reassessment reproduces both archived files byte-for-byte.
- A wheel rebuild from the source distribution passes artifact checks and an
  isolated explicit-grid smoke solve. Both the Python package and native module
  were verified to load from the extracted wheel, with the checkout's editable
  import redirect disabled. The final source archive includes this report,
  plan, raw data and study tooling.

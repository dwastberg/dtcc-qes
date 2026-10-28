# Turbulence numerical acceptance and cost

This report evaluates the Task 9 implementation gate before DTCC export,
comfort and dataset integration. The gate concerns implementation correctness,
coverage and quantified numerical limitations. It does not validate urban
gusts against observations or certify a comfort criterion. Height remains the
provisional public default; changing it requires a separate, user-approved
decision.

## Reproduce and inspect

The isolated feature branch starts this task at parent revision `2e69e95`.
Task 6 refreshes the complete matrix after parent revision `0d7905a`, so the
source fingerprints include the new DTCC export. Native numerics are unchanged.
Task 7 refreshes it again after `3ee778d`, including the comfort GEM helper
in the source audit. GEM generation and comfort assessment are tested separately;
their costs are outside this native-solve/statistic benchmark.
The timings still measure native solve and Python statistics, not DTCC
conversion; separate export tests verify ordering, masks and serialization.
QES is `dce15d7e3b0a2d2cb0a29898f3882d103f66de71`. The native Python extension
uses Release, AppleClang 17.0.0.17000404, serial execution and no QES file I/O.
The host is an Apple M4 Pro with 48 GiB RAM, macOS 15.7.1 arm64, Python
3.13.11 and NumPy 2.5.4. Dependency versions are fixed by `uv.lock`.
Sanitizer checks use a separate Debug build with AddressSanitizer and
UndefinedBehaviorSanitizer, frame pointers and assertions enabled.

```sh
uv sync --frozen --group reference --reinstall-package dtcc-qes
.venv/bin/python tools/run_turbulence_benchmark.py --self-test \
  --output build/task9-self-test.json
.venv/bin/python tools/run_turbulence_benchmark.py --verify \
  --work-dir build/task9-verification \
  --output docs/data/turbulence-benchmark/verification.json
.venv/bin/python tools/run_turbulence_benchmark.py \
  --host-description 'Apple M4 Pro, 48 GiB RAM' \
  --work-dir build/task9-benchmark \
  --output docs/data/turbulence-benchmark/benchmark.json
```

Native build directories and the audited standalone executable must already
be configured/built as described in
[the implementation audit](turbulence-reference-differences.md). `--verify`
retains each command, exit code, log checksum and log tail. Full logs and
temporary native arrays stay in `build/`. A numerical failure returns a
nonzero exit status; failed convergence is retained and disqualifies that run
from numerical comparisons. Worker crashes retain their request and log and
stop the run. `--resume` reuses a worker only when its configuration and
Python-source/native-binary fingerprint still match.

The committed [summary](data/turbulence-benchmark/benchmark.json) contains the
matrix, timing ranges/medians, convergence/residual diagnostics, method and
domain comparisons, flat-profile errors, scaling checks and source checksums.
Its `raw_runs` entry authenticates the accompanying compressed JSON archive.
Load that archive with `json.load(gzip.open(..., 'rt'))`. It retains each
repetition's measurements; first repetitions also retain sampled raw tensors,
velocity, statistics, coordinates and exclusion lists. JSON `null` denotes an
unavailable float. Native invalid locations are flat C-order `(z,y,x)` indices;
the recorded shape, origin, resolution and z centres recover their positions.
Raw tensors remain unchanged in the API and temporary native archives even
when derived statistics are masked. Committed raw JSON includes invalid
pedestrian tensors and native invalid-tensor witnesses, rather than duplicating
every full three-dimensional field.

The Task 9 Python suite passed **782 tests, with 24 existing opt-in skips**.
Task 6 passes **792 tests with the same 24 skips**, including export ordering,
current-tensor validity and DTCC serialization for both methods. The verification
record retains each suite run. Native code is unchanged; its Task 9 Release
and ASan/UBSan results remain applicable without repeating native checks.
The refreshed matrix passes all 72 configurations/216 repetitions and all
18 scaling pairs. Exact comparisons against parent `0d7905a` match all 216
wind hashes and solver diagnostics, 186 raw-stress hashes and validity records,
and all 62 retained tensor/statistic sample sets. This establishes unchanged
numerical results for the refresh; timing and RSS differences reflect the new
measurements. The verification JSON retains the baseline checksum and counts.

Task 7 passes **862 tests, no skips**, under `-W error` with the Release native
safety/study executables enabled. Its twelve-direction comfort example converges
and retains the QES screening warning and explicit peak/averaging assumptions.
The preceding review at `3ee778d` passed 39/39 native tests in Release and
ASan/UBSan plus the Release symbol audit; native sources are unchanged in Task 7.
The verification record includes the Task 7 commands, coverage and log checksums.
Its full matrix again passes 72 configurations/216 repetitions and 18 scaling
pairs. Exact comparisons with `3ee778d` match 216 wind/diagnostic records,
186 raw-stress/validity records and 62 retained tensor/statistic sample sets.
Only source fingerprints, timings and process memory measurements change.

## Measurement and comparison policy

Each configuration has three fresh Python subprocesses, run serially. Native
`WindRunner.prepare` and `solve` are timed directly; geometry/domain planning
is timed separately. Memory is process high-water RSS, including Python and
imports, sampled after prepare, solve, validity screening and derived arrays.
It is not native allocation size or instantaneous live memory. Medians describe
this host and build; the host was not isolated from unrelated activity.

Python timings include a standalone validity pass, `streamwise_std`, and
`turbulence_intensity`. The intensity property computes standard deviation
again, so its timing already includes that work. Independent benchmark oracles
run afterwards and are excluded from those production timings. The separately
labelled pedestrian sampling/oracle timer includes diagnostic overhead.

The four C2 layouts use the existing `rectangles()` definitions at 2 m
resolution in an explicit 80 × 80 × 64 m domain: 51,200 physical cells.
The synthetic city uses 25 separated 12 × 12 × 8 m blocks over
400 × 400 × 64 m: 1,280,000 physical cells. These identical-grid cases separate
turbulence cost from the additional layers that automatic domains may need.
Mid-rise automatic cases then measure wind-only original grids, wind-only
grown grids, and turbulence on the grown grids. The regenerated case has a
40 m fine band that cannot fit the original wind-only 35 m endpoint.

Solves use double multiplier arithmetic, float32 geometry/returned native
fields, a 20,000-iteration budget and tolerance `1e-7 * speed/5`. Convergence
measures multiplier change. Maximum/RMS divergence and the separate last
solved band are recorded; convergence is not a residual or observational
accuracy certificate. The three-repetition benchmark does not replace the
earlier checkpoint-based wind-grid studies.

Pedestrian comparisons use linear component sampling at 1.5 and 1.75 m, then
full-tensor projection along the sampled three-dimensional mean direction.
C2/domain cases use every interior horizontal centre. The large city uses
every eighth interior centre in x/y; native whole-volume validity and scaling
still check all cells. Changes use a common finite sample set; excluded
indices map to the accompanying `locations_xy`. Relative changes use height
method as denominator, or the base grid for sensitivity/domain comparisons.
Zero denominators have separate counts and absolute changes. No tensor
repair or realizability correction is applied.

Building sensitivity holds horizontal spacing at 2 m and compares uniform
vertical spacings 2, 1, 0.5 m and automatic layers in the same 64 m domain.
This isolates vertical sensitivity, rather than claiming complete spatial
convergence. Flat-profile uniform grids refine x/y/z together on an empty
24 × 24 × 32 m domain; the automatic case uses 2 m x/y spacing.

For the flat centre column, the analytic relation is
`sigma/u*_inflow = 2.5*z/(z+z0)`, with
`u*_inflow = 0.4*Uref/log((zref+z0)/z0)`, `z0=0.1 m` and `zref=10 m`.
The derivative contribution is measured against the square root of linearly
interpolated analytic centre variances; the sampling contribution is that analytic interpolant
minus the analytic value at the requested height. Their sum is the total
error. This separates finite-difference error from sampling without attributing
building-flow errors to the flat analytic relation. Nearest results record
the actual centre height and are evaluated against the relation at that centre.

## Gate evidence

The [verification record](data/turbulence-benchmark/verification.json) retains
the complete commands and outcomes. The initially failing benchmark test was
run before implementing the tool. Its self-test now exercises a real isolated
native solve, zero denominators, invalid-source interpolation and rejection
of failed solves; separate tests inject extraction failures to ensure
convergence alone cannot pass the benchmark.

| Criterion | Evidence |
| --- | --- |
| Ownership, height guards, method-1 bounds and distances | 39/39 Release and 39/39 ASan/UBSan native tests pass, including thin walls, box/plane distance oracles, nonuniform grids, upper bounds, transitions and undersides. |
| Full tensor and oblique manufactured shear | Native rotation/shear regressions and public analytic tests pass at the Task 1A tensor tolerances (`rtol=1e-5`, `atol=1e-7`). These checks use uncapped manufactured tensors, independently of standalone parity. |
| Independent spectral screening | The native classifier agrees with NumPy on 5,000 randomized tensors spanning scales 1e-30 to 1e30; zero mask mismatches, maximum minimum-eigenvalue error divided by spectral radius 1.055e-15. Benchmark volumes and samples receive a separate unnormalized float64 eigensolver check. |
| Domain rules | All 52 domain regressions pass, including ordinary 15/20 m blocks, resolution changes, margin equivalence, operand/face prefix preservation, regeneration, resource limits and explicit-domain rejection. The archived Task 4 control also passes again. |
| Audited standalone parity | All eight audited standalone cases pass the attested reference check; public/native Python parity tests pass. Pristine-upstream differences remain explained in the implementation audit. |
| Native no-I/O safety | Release symbol audit passes. The pre-existing Debug assertion termination symbol limitation remains as documented in the implementation audit; no Debug symbol-audit pass is claimed. |

The measured benchmark verdict, scaling, refinement and coverage evidence
follow below. A raw indefinite tensor is an accounted model limitation, not
an automatic implementation failure; allowing it to produce a finite derived
statistic would fail this gate.

Known departures from pristine QES have separate explanations in the
[reference difference audit](turbulence-reference-differences.md): the corrected
orthogonal rotation restores the oblique covariance; method 1 now measures
bounded distances to exposed voxel faces, preserves the terrain/height minimum,
handles undersides and blends over physical 3H–3.6H heights. The shared
wind fields are unchanged. Method-0 mixing length, TKE and dissipation retain
their audited upstream values; its changed oblique stress comes from the
rotation repair. Method-1 field changes follow the distance repairs. The new
validity mask describes raw tensors and does not silently change them.

<!-- measured-results -->
## Measured verdict

**Numerical implementation gate: PASS.** 72/72 configurations, 216 fresh-process repetitions, and 18/18 whole-volume speed-scaling pairs pass. The finest uniform flat grid is closer than the coarsest at both heights and both directions. All accepted computed native fields are finite; native/Python/independent validity checks agree, and no invalid tensor or contributor produces a finite derived statistic.

Speed scaling checks all raw stress components and TKE ×4, C0·epsilon ×8, velocity and standard deviation ×2, intensity unchanged, and identical computed/validity/cap/zero-speed masks. The tolerance is `rtol=1e-4, atol=1e-7`; finite masks must agree exactly. It covers all four C2 layouts, the synthetic city, cardinal/oblique flat cases, both mid-rise vertical-grid families and the regenerated case. Scaling tests include invalid raw tensors, rather than dropping them with the derived-statistic mask.

Iterations span 1–1836. Maximum interior divergence across all runs is 1.73e-06 s⁻¹; maximum RMS is 1.9066e-07 s⁻¹. The separate last solved band reaches 0.17143 s⁻¹. The upper physical layer remains unassessed by that diagnostic, as in the existing solver contract.

## Identical-grid cost

All times below are median seconds. RSS columns are median MiB high-water values. “TI” includes recomputing σ; the standalone validity pass is an additional measurement, not work automatically done by returning raw Python fields.

| Layout | Method | Cells | Prepare | Solve | Validity | σ | TI | RSS solve | RSS derived |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| isolated | off | 51200 | 0.0010545 | 0.046444 | — | — | — | 209.94 | — |
| isolated | 0 | 51200 | 0.0023198 | 0.059109 | 0.018833 | 0.021239 | 0.021567 | 218.53 | 252.95 |
| isolated | 1 | 51200 | 0.0062437 | 0.059866 | 0.018759 | 0.021808 | 0.021924 | 218.22 | 249.58 |
| passage | off | 51200 | 0.0011303 | 0.05182 | — | — | — | 209.14 | — |
| passage | 0 | 51200 | 0.0022193 | 0.065227 | 0.018554 | 0.020875 | 0.022109 | 219.14 | 244.8 |
| passage | 1 | 51200 | 0.013096 | 0.065845 | 0.018231 | 0.020121 | 0.02068 | 215.67 | 232.19 |
| array | off | 51200 | 0.0010176 | 0.047408 | — | — | — | 207.59 | — |
| array | 0 | 51200 | 0.0023649 | 0.061428 | 0.017884 | 0.020331 | 0.020548 | 214.36 | 243 |
| array | 1 | 51200 | 0.0050091 | 0.060786 | 0.017908 | 0.019998 | 0.020538 | 217.28 | 230.17 |
| tower | off | 51200 | 0.0010213 | 0.053963 | — | — | — | 208.14 | — |
| tower | 0 | 51200 | 0.0020588 | 0.067952 | 0.019005 | 0.020977 | 0.021002 | 215.25 | 227.72 |
| tower | 1 | 51200 | 0.023509 | 0.067988 | 0.01865 | 0.020525 | 0.020816 | 217.27 | 235.03 |
| city | off | 1.28e+06 | 0.023779 | 7.7868 | — | — | — | 399.08 | — |
| city | 0 | 1.28e+06 | 0.051493 | 8.1378 | 0.48138 | 0.55711 | 0.58181 | 636.58 | 729.28 |
| city | 1 | 1.28e+06 | 0.078199 | 8.1695 | 0.4914 | 0.57698 | 0.57777 | 638.25 | 786.19 |

Returned wind is bitwise identical for off/0/1 on each of these explicit grids. Method 1 adds preparation work on these layouts; solve costs are close to method 0. The 110 B/native-cell plus 39 B/physical-cell field estimate is not a peak-memory budget. Double solver storage, extraction copies, Python masks, eigenvalue work and float64 arrays raise measured peaks. Independent benchmark-oracle memory is recorded separately and excluded from the derived-array RSS column. Larger/taller/denser geometries can change wall-search cost substantially.

## Method differences and coverage

Method 1 minus method 0, as absolute P50/P95/max changes on the common finite set. Intensity is dimensionless; σ is m/s. “Excluded” includes solids and invalid/undefined statistics. Every exclusion and any zero denominator has an explicit location/index in JSON.

| Layout | Height | Common | Excluded | Δσ P50/P95/max | ΔTI P50/P95/max | σ relative P95 | TI relative P95 | Zero σ/TI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| isolated | 1.5 | 1396 | 48 | 0/0/0.88015 | 0/0/1.0224 | 0 | 0 | 0/0 |
| isolated | 1.75 | 1396 | 48 | 0/0/1.1872 | 0/0/1.4548 | 0 | 0 | 0/0 |
| passage | 1.5 | 1250 | 194 | 0/0.23608/0.77333 | 0/0.15083/3.2509 | 0.25369 | 0.25369 | 0/0 |
| passage | 1.75 | 1250 | 194 | 0/0.32122/0.9824 | 0/0.20471/3.42 | 0.34188 | 0.34188 | 0/0 |
| array | 1.5 | 1300 | 144 | 0/0.31579/0.71534 | 0/0.12525/1.1837 | 0.33311 | 0.33311 | 0/0 |
| array | 1.75 | 1300 | 144 | 0/0.44007/0.97762 | 0/0.16222/1.5757 | 0.42244 | 0.42244 | 0/0 |
| tower | 1.5 | 1300 | 144 | 0/0.34064/0.83651 | 0/0.15455/1.3594 | 0.35675 | 0.35675 | 0/0 |
| tower | 1.75 | 1300 | 144 | 0/0.47464/1.1145 | 0/0.20305/1.9194 | 0.43594 | 0.43594 | 0/0 |
| city | 1.5 | 609 | 16 | 0/0/0.73225 | 0/0/0.55293 | 0 | 0 | 0/0 |
| city | 1.75 | 609 | 16 | 0/0/0.99343 | 0/0/0.71041 | 0 | 0 | 0/0 |

| Layout | Method | Computed | Capped | Cap % | Invalid | Invalid % | Min λ (m²/s²) | Negative nᵀτn | Materially negative |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| isolated | 0 | 44476 | 913 | 2.0528 | 326 | 0.73298 | -14.752 | 10 | 10 |
| isolated | 1 | 44476 | 492 | 1.1062 | 130 | 0.29229 | -12.394 | 0 | 0 |
| passage | 0 | 43612 | 2023 | 4.6386 | 830 | 1.9031 | -18.039 | 45 | 45 |
| passage | 1 | 43612 | 748 | 1.7151 | 282 | 0.64661 | -13.466 | 14 | 14 |
| array | 0 | 44188 | 817 | 1.8489 | 280 | 0.63366 | -13.398 | 26 | 26 |
| array | 1 | 44188 | 396 | 0.89617 | 40 | 0.090522 | -7.1855 | 0 | 0 |
| tower | 0 | 43900 | 2893 | 6.59 | 1235 | 2.8132 | -26.752 | 73 | 73 |
| tower | 1 | 43900 | 1070 | 2.4374 | 420 | 0.95672 | -22.649 | 2 | 2 |
| city | 0 | 1211724 | 6800 | 0.56118 | 2100 | 0.17331 | -10.067 | 134 | 134 |
| city | 1 | 1211724 | 3750 | 0.30948 | 550 | 0.04539 | -7.3816 | 0 | 0 |

| Layout | Height | Computed/points | Capped 0/1 | Invalid source 0/1 | Invalid interpolant 0/1 | Derived valid 0/1 |
| --- | --- | --- | --- | --- | --- | --- |
| isolated | 1.5 | 1396/1444 | 24/10 | 0/0 | 0/0 | 1396/1396 |
| isolated | 1.75 | 1396/1444 | 24/10 | 0/0 | 0/0 | 1396/1396 |
| passage | 1.5 | 1252/1444 | 46/24 | 2/2 | 0/0 | 1250/1250 |
| passage | 1.75 | 1252/1444 | 46/24 | 2/2 | 0/0 | 1250/1250 |
| array | 1.5 | 1300/1444 | 52/24 | 0/0 | 0/0 | 1300/1300 |
| array | 1.75 | 1300/1444 | 52/24 | 0/0 | 0/0 | 1300/1300 |
| tower | 1.5 | 1300/1444 | 37/19 | 0/0 | 0/0 | 1300/1300 |
| tower | 1.75 | 1300/1444 | 37/19 | 0/0 | 0/0 | 1300/1300 |
| city | 1.5 | 609/625 | 2/0 | 0/0 | 0/0 | 609/609 |
| city | 1.75 | 609/625 | 2/0 | 0/0 | 0/0 | 609/609 |

The passage has two invalid-contributor pedestrian locations for each method at both heights, even though the interpolated tensors pass the spectral screen. They remain excluded. This is observed benchmark data, as well as a manufactured self-test. Whole-volume invalid tensors and negative projections remain present in raw output; zero raw indefinite tensors is deliberately not an acceptance criterion.

## Flat-profile refinement

| Direction/grid | Height | σ/u* | Total error | Derivative part | Sampling part | Nearest z | Nearest error at z |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 270-2 | 1.5 | 1.8237 | -0.52002 | -0.48652 | -0.033493 | 1 | -0.97761 |
| 270-2 | 1.75 | 2.0372 | -0.32762 | -0.29155 | -0.03607 | 1 | -0.97761 |
| 270-1 | 1.5 | 2.7494 | 0.40563 | 0.40563 | 0 | 1.5 | 0.40563 |
| 270-1 | 1.75 | 2.6972 | 0.33232 | 0.33827 | -0.0059473 | 1.5 | 0.40563 |
| 270-0.5 | 1.5 | 2.4277 | 0.083969 | 0.087746 | -0.0037763 | 1.25 | 0.11551 |
| 270-0.5 | 1.75 | 2.4251 | 0.060244 | 0.060244 | 0 | 1.75 | 0.060244 |
| 270-auto | 1.5 | 2.4023 | 0.058596 | 0.058596 | 0 | 1.5 | 0.058596 |
| 270-auto | 1.75 | 2.4086 | 0.043761 | 0.045564 | -0.0018027 | 1.9286 | 0.03634 |
| scaling-flat-270 | 1.5 | 1.8237 | -0.52002 | -0.48652 | -0.033493 | 1 | -0.97761 |
| scaling-flat-270 | 1.75 | 2.0372 | -0.32762 | -0.29155 | -0.03607 | 1 | -0.97761 |
| 225-2 | 1.5 | 1.8237 | -0.52002 | -0.48652 | -0.033493 | 1 | -0.97761 |
| 225-2 | 1.75 | 2.0372 | -0.32762 | -0.29155 | -0.03607 | 1 | -0.97761 |
| 225-1 | 1.5 | 2.7494 | 0.40563 | 0.40563 | 0 | 1.5 | 0.40563 |
| 225-1 | 1.75 | 2.6972 | 0.33232 | 0.33827 | -0.0059473 | 1.5 | 0.40563 |
| 225-0.5 | 1.5 | 2.4277 | 0.083969 | 0.087745 | -0.0037763 | 1.25 | 0.11551 |
| 225-0.5 | 1.75 | 2.4251 | 0.060243 | 0.060243 | 0 | 1.75 | 0.060243 |
| 225-auto | 1.5 | 2.4023 | 0.058596 | 0.058596 | 0 | 1.5 | 0.058596 |
| 225-auto | 1.75 | 2.4086 | 0.04376 | 0.045563 | -0.0018027 | 1.9286 | 0.03634 |
| scaling-flat-225 | 1.5 | 1.8237 | -0.52002 | -0.48652 | -0.033493 | 1 | -0.97761 |
| scaling-flat-225 | 1.75 | 2.0372 | -0.32762 | -0.29155 | -0.03607 | 1 | -0.97761 |

The analytic targets are 2.34375 at 1.5 m and approximately 2.364865 at 1.75 m. Uniform 0.5 m improves on 2 m at both heights; the 1 m intermediate grid is not monotonic because of ground-gradient and centre-placement effects. The automatic grid has smaller flat-profile errors here, but that is not an urban-grid accuracy qualification. All sampled flat points are computed, valid and uncapped; nearest-height bias is not hidden by comparing its output to the requested height. No quantitative urban-gust error budget has been declared, so these results do not establish grid-independent gust accuracy.

## Building vertical sensitivity

| Layout/new dz | Height | Common | Excluded | P95 Δσ | Max Δσ | P95 ΔTI |
| --- | --- | --- | --- | --- | --- | --- |
| isolated-1 | 1.5 | 1396 | 48 | 0.40163 | 1.3935 | 0.15727 |
| isolated-1 | 1.75 | 1396 | 48 | 0.2869 | 1.4337 | 0.15259 |
| isolated-0.5 | 1.5 | 1396 | 48 | 0.26271 | 1.441 | 0.1562 |
| isolated-0.5 | 1.75 | 1396 | 48 | 0.1852 | 1.8581 | 0.22334 |
| isolated-auto | 1.5 | 1396 | 48 | 0.25162 | 1.4408 | 0.18425 |
| isolated-auto | 1.75 | 1396 | 48 | 0.18242 | 1.8605 | 0.21736 |
| passage-1 | 1.5 | 1250 | 194 | 0.40144 | 1.4937 | 0.42922 |
| passage-1 | 1.75 | 1250 | 194 | 0.28672 | 1.5033 | 0.39503 |
| passage-0.5 | 1.5 | 1250 | 194 | 0.26299 | 1.5598 | 0.42462 |
| passage-0.5 | 1.75 | 1250 | 194 | 0.32887 | 1.9816 | 0.50502 |
| passage-auto | 1.5 | 1250 | 194 | 0.26973 | 1.547 | 0.46254 |
| passage-auto | 1.75 | 1250 | 194 | 0.29942 | 1.9595 | 0.52751 |
| array-1 | 1.5 | 1300 | 144 | 0.40295 | 0.93701 | 0.35591 |
| array-1 | 1.75 | 1300 | 144 | 0.28877 | 0.73205 | 0.30239 |
| array-0.5 | 1.5 | 1300 | 144 | 0.2661 | 1.1199 | 0.33548 |
| array-0.5 | 1.75 | 1300 | 144 | 0.31466 | 1.4511 | 0.39044 |
| array-auto | 1.5 | 1300 | 144 | 0.28101 | 1.1173 | 0.37727 |
| array-auto | 1.75 | 1300 | 144 | 0.31532 | 1.3732 | 0.37553 |
| tower-1 | 1.5 | 1300 | 144 | 0.40578 | 0.95026 | 0.39178 |
| tower-1 | 1.75 | 1300 | 144 | 0.29347 | 0.74887 | 0.3288 |
| tower-0.5 | 1.5 | 1300 | 144 | 0.27837 | 1.3033 | 0.36389 |
| tower-0.5 | 1.75 | 1300 | 144 | 0.33767 | 1.7074 | 0.43042 |
| tower-auto | 1.5 | 1300 | 144 | 0.30477 | 1.306 | 0.41634 |
| tower-auto | 1.75 | 1300 | 144 | 0.33049 | 1.5947 | 0.43218 |

These are differences from the 2 m vertical grid, using height mixing length and fixed horizontal spacing. They include roof voxelization changes as well as gradient and sampling effects. No numerical closeness threshold was invented after seeing the data; this table quantifies sensitivity rather than passing a new accuracy claim.

## Automatic-domain cost and taller controls

| Case/grid/domain/method | Cells | Prepare s | Solve s | RSS solve MiB |
| --- | --- | --- | --- | --- |
| midrise-2-auto-None | 23328 | 0.000572 | 0.013454 | 206.16 |
| midrise-2-grown_off-None | 33696 | 0.00077521 | 0.023949 | 206.34 |
| midrise-2-auto-0 | 33696 | 0.001739 | 0.033386 | 211.67 |
| midrise-2-auto-1 | 33696 | 0.020845 | 0.035168 | 215.38 |
| midrise-auto-auto-None | 38880 | 0.00083875 | 0.076638 | 205.08 |
| midrise-auto-grown_off-None | 49248 | 0.0010647 | 0.1024 | 206.33 |
| midrise-auto-auto-0 | 49248 | 0.002157 | 0.11381 | 218.98 |
| midrise-auto-auto-1 | 49248 | 0.032371 | 0.11378 | 215.88 |
| regenerated-auto-grown_off-None | 134784 | 0.0025311 | 0.75635 | 222.84 |
| regenerated-auto-auto-0 | 134784 | 0.0050889 | 0.78845 | 243.95 |
| regenerated-auto-auto-1 | 134784 | 0.22024 | 0.78886 | 243.7 |

Compare `auto-None` with `grown_off-None` to isolate extra-layer cost, then `grown_off-None` with `auto-0`/`auto-1` for turbulence on the same grown grid. The original regenerated wind-only grid is infeasible, and is therefore not assigned a fabricated timing. Its allocation-free rejection and regeneration are covered by domain regressions.

- `domain-midrise-2-auto-0`: base top 52 m; reference 45 m; added layers 8; lower prefix preserved: True; taller top 84 m. Both operands and effective faces of the turbulence base are preserved in the appended-tail control.
- `domain-midrise-2-auto-1`: base top 52 m; reference 45 m; added layers 8; lower prefix preserved: True; taller top 84 m. Both operands and effective faces of the turbulence base are preserved in the appended-tail control.
- `domain-midrise-auto-auto-0`: base top 51.0518 m; reference 45 m; added layers 8; lower prefix preserved: True; taller top 83.1553 m. Both operands and effective faces of the turbulence base are preserved in the appended-tail control.
- `domain-midrise-auto-auto-1`: base top 51.0518 m; reference 45 m; added layers 8; lower prefix preserved: True; taller top 83.1553 m. Both operands and effective faces of the turbulence base are preserved in the appended-tail control.
- `domain-regenerated-auto-auto-0`: base top 51 m; reference 45 m; added layers 0; lower prefix preserved: False; taller top 83.2797 m. Both operands and effective faces of the turbulence base are preserved in the appended-tail control.
- `domain-regenerated-auto-auto-1`: base top 51 m; reference 45 m; added layers 0; lower prefix preserved: False; taller top 83.2797 m. Both operands and effective faces of the turbulence base are preserved in the appended-tail control.

| Base → taller | Height | Common | Excluded | P95 Δwind m/s | P95 Δσ | Max Δσ | P95 ΔTI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| midrise-2-auto-0 | 1.5 | 1012 | 144 | 0.001057 | 0.00030184 | 0.0018802 | 0.001123 |
| midrise-2-auto-0 | 1.75 | 1012 | 144 | 0.001062 | 0.00032879 | 0.0025348 | 0.0012462 |
| midrise-2-auto-1 | 1.5 | 1012 | 144 | 0.001057 | 0.00026383 | 0.0018802 | 0.0010981 |
| midrise-2-auto-1 | 1.75 | 1012 | 144 | 0.001062 | 0.00026431 | 0.0025348 | 0.001147 |
| midrise-auto-auto-0 | 1.5 | 1012 | 144 | 0.0013163 | 0.00032526 | 0.0011457 | 0.0011292 |
| midrise-auto-auto-0 | 1.75 | 1012 | 144 | 0.0013191 | 0.00036623 | 0.0013199 | 0.001373 |
| midrise-auto-auto-1 | 1.5 | 1012 | 144 | 0.0013163 | 0.00029619 | 0.0011457 | 0.0010447 |
| midrise-auto-auto-1 | 1.75 | 1012 | 144 | 0.0013191 | 0.00033033 | 0.0013199 | 0.001164 |
| regenerated-auto-auto-0 | 1.5 | 1012 | 144 | 0.0012592 | 0.00029909 | 0.0010599 | 0.0010395 |
| regenerated-auto-auto-0 | 1.75 | 1012 | 144 | 0.0012618 | 0.00035699 | 0.0015036 | 0.001252 |
| regenerated-auto-auto-1 | 1.5 | 1012 | 144 | 0.0012592 | 0.00027598 | 0.0010599 | 0.00098214 |
| regenerated-auto-auto-1 | 1.75 | 1012 | 144 | 0.0012618 | 0.00030549 | 0.0015036 | 0.0011005 |

| Method | Comparison | Height | Common | P95 Δwind | P95 Δσ | Max Δσ | P95 ΔTI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | regenerated_tall | 1.5 | 1012 | 0.0012545 | 0.00029786 | 0.0010549 | 0.0010371 |
| 0 | regenerated_tall | 1.75 | 1012 | 0.0012571 | 0.00035555 | 0.0014964 | 0.0012452 |
| 0 | preserved_vs_regenerated_tall | 1.5 | 1012 | 4.341e-06 | 1.1574e-06 | 5.0523e-06 | 5.4032e-06 |
| 0 | preserved_vs_regenerated_tall | 1.75 | 1012 | 4.3979e-06 | 1.3023e-06 | 7.2099e-06 | 6.4745e-06 |
| 1 | regenerated_tall | 1.5 | 1012 | 0.0012545 | 0.00027507 | 0.0010549 | 0.00097679 |
| 1 | regenerated_tall | 1.75 | 1012 | 0.0012571 | 0.00030424 | 0.0014964 | 0.0010977 |
| 1 | preserved_vs_regenerated_tall | 1.5 | 1012 | 4.341e-06 | 1.0673e-06 | 5.0523e-06 | 4.8694e-06 |
| 1 | preserved_vs_regenerated_tall | 1.75 | 1012 | 4.3979e-06 | 1.1701e-06 | 7.2099e-06 | 5.5354e-06 |

The regenerated comparisons are separate: the base first had to replace its infeasible wind-only lower grid. Its taller automatic control regenerates upper operands, whereas the appended-tail control preserves every base operand. Neither a small mean-wind change nor the minimum reference margin alone proves turbulence independent of domain top. Domain-dependent reference-plane speed and the cap can also affect stresses. All associated masks, exclusions and zero-denominator accounting remain in JSON.

## Recommendation and remaining limits

Keep **height** as the provisional default. Both implementations meet this numerical gate, and wall distance is a useful explicit option that reduces cap/invalid counts in these layouts. Its voxel-wall model, changed stresses and extra preparation work do not establish better agreement with measured pedestrian gusts. There is no observational basis here to promote either method as physically validated. Default changes require the user’s review and a separate commit.

Task 6 DTCC export preserves raw stress, independent validity and masked derived statistics. Task 7 comfort GEM preserves invalid coverage, explicit modelling assumptions and the screening warning. Task 8 dataset outputs must retain those qualifications. The coarse-grid profile error, building sensitivity, top sensitivity, indefinite tensors and real peak-memory cost remain material limits; downstream integration must not describe this gate as gust validation or comfort certification.

# Physics bug fix results

Work in progress on `fix/physics-bugs`, based on `033df33`.

## Preparation and reassessment

- P0: isolated worktree `/private/tmp/dtcc-qes-physics-bugs`; copied the untracked
  Case A/B measurements. Rebuilt both the original checkout and worktree;
  `SolverOptions.grid_relaxation` is present. No tracked baseline edits existed.
- P1: Python baseline: **2067 passed, 16 skipped, 1 failed, 2 errors**.
  All three failures are the known missing covariance header/production helpers.
  Serial CTest **60/60**, OpenMP **63/63**. Sanitizers are running.
- P2: staggered point reflection captures `solid_mask` and the pressure-corrected
  field. The F1 regression fails before the fix. Use maximum component error:
  a whole-domain average dilutes a local cavity defect below the proposed gate.
- P3: implemented immutable archives, SHA-256 manifests and overwrite refusal;
  its regression passes. Ran P3 before P1 to preserve baseline evidence.
- Fast baseline: `output/archive/baseline-fast-033df33`, **13/13 successful**.
  Full baseline is running in the unchanged original worktree environment.
- Reproduction scripts were untracked/ignored on the original checkout, despite
  the plan implying they were available in the base commit. Copied them locally
  into `tests/physics_reproductions/e2e_review` as test development inputs.
- Separate `.venv-fixes` and validation `--output-root` keep the full baseline's
  loaded extension and cache independent of subsequent fixes.
- Per the user's instruction to proceed without stopping, D2 will use the
  documented deterministic ranking rule; the evidence and selection will be
  recorded here. No upstream issue will be posted.

## F1: cavity facade angle

Corrected wrapping above pi and restored the missing central angular sector.
The angle mapping is shared with direct native tests, including all eight
45-degree normals and normals inside the previously missing sectors.

Maximum component mirror differences (m/s), initial field:

| Building rotation / wind | Cavity off | Before | After |
|---|---:|---:|---:|
| 70 / 200 | 1.29505 | 3.36468 | 1.29505 |
| 20 / 250 | 1.29505 | 1.29505 | 1.29505 |
| 0 / 180 | 1.37817 | 1.37817 | 1.37817 |
| 0 / 185 | 4.62227 | 4.62227 | 4.62227 |

The nonzero cavity-off differences belong to other parameterizations and are
not repaired by this batch. The planned relative gate passes in all four cases.
For 70/200 the final-field maximum decreases from 3.25746 to 0.931594 m/s
(cavity-off 0.931595). Serial **61/61**, OpenMP **64/64** pass before extracting
angle mapping into its independently tested helper; final checks are pending.

Next-step reassessment: F2's break-condition change remains appropriate. Its
regression must also verify tall and touching obstacles to avoid removing the
intended wake termination along with the low-obstacle defect.

F1 Python: **2068 passed, 16 skipped**, only the three known F5 failures remain.
Fast archive: `output/fixes/archive/F1-3b82e6e` (F1 native edits present at run
start; committed as `be78a1c`). Every score change is below 0.00001; no probe
changes by 0.05. No attribution threshold is crossed.

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | -0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | -0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | -0.00000 | -0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00000 | +0.00000 | -0.00000 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | -0.00000 | -0.00000 | 0.00000 |
| 2 m | D-thermistor-K | +0.00000 | +0.00000 | -0.00000 | -0.00000 | 0.00000 |
| 2 m | D-thermistor-K_scalar | +0.00000 | +0.00000 | -0.00000 | -0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K_scalar | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-after-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-after-thermistor-K_scalar | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |

## F2: far wake past low obstacles

Serial **62/62**, OpenMP **65/65**, Python **2068 passed, 16 skipped** with
only the three known F5 failures. Low-obstacle speeds now
0.18063/1.31151/1.87655 m/s versus strict 0.18274/1.31160/1.87657.
Tall and touching controls retain their pre-fix speeds within 0.00002 m/s.
Archive: `output/fixes/archive/F2-acc7a50`. No attribution threshold is crossed.

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K_scalar | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K | +0.00625 | +0.01250 | +0.00650 | +0.01436 | 0.05625 |
| 2 m | E-before-thermistor-K_scalar | +0.00940 | +0.00313 | +0.02049 | +0.01309 | 0.06897 |
| 2 m | E-after-thermistor-K | +0.00938 | -0.00313 | +0.01495 | +0.02787 | 0.08750 |
| 2 m | E-after-thermistor-K_scalar | +0.02500 | +0.01875 | +0.02606 | +0.02764 | 0.10000 |

Tower-effect diagnostic (x3 calculation adapted to archived records rather than
stale precomputed arrays), fast directions, within 30 m:

```text
within 30 m pairs 88 measured 0.27568381500000005 simulated 0.0025303954869942856
upwind pairs 26 measured 0.16237485634615384 simulated -0.08516012073721686
beside pairs 52 measured 0.3624847145192308 simulated 0.10775170422383719
downwind pairs 26 measured 0.3148395101923077 simulated -0.05900466208722093

```

The mean simulated tower effect remains far below the measured +0.276. F3 is
still necessary: its native reproduction gives upstream u=-0.0821 with wake=2
and -0.3653 with wake=3. Proceed with both direction variants as planned.

Full baseline: **74/74 successful**, archive `output/archive/baseline-full-be78a1c`.
The initial archive helper captured Git revision at completion, hence that
suffix; its fingerprint exactly matches `baseline-fast-033df33`
(`9659890f342508a0525065f9e2a8d1fd44b5897636a26bb9646661b8f101ca5b`).
The helper now captures revision at run start. Concurrent timings are execution
logs, not controlled performance comparisons.

## F3: frozen incident reference and direction choice

Both variants pass the required synthetic checks, including isolated references,
repeated calm and turning layer profiles, input-order independence and positive
upstream flow for wakes 2 and 3. Both serial suites pass **63/63**. The F2 final
speed controls moved by 0.00012 m/s through the pressure solve; their tolerance
is now 0.001 m/s, retaining a much smaller threshold than the wake defect.

Archives: `output/fixes/archive/F3-V1-acc7a50` and
`output/fixes/archive/F3-V3-acc7a50`. V3's source patch is retained in
`physics_evidence/F3-V3.patch`; the losing implementation and build constant
are removed from production code. Both variants have all 13 successful runs.

The deterministic D2 ranking selects **V1**:

```text
Required synthetic tests must pass separately for both variants.
A V1 q/R 0.6827956989247311 0.8866287807602937 V3 q/R 0.6827956989247311 0.8866287807602937
B V1 q/R 0.5044642857142857 0.7436538899625231 V3 q/R 0.5044642857142857 0.7436538899625231
D V1 q/R 0.23737373737373738 0.4258845471558165 V3 q/R 0.23737373737373738 0.4258845471558165
E V1 q/R 0.259375 0.49716608957965475 V3 q/R 0.2578125 0.4975727428530609
mean score V1 0.5296677536838803 V3 0.5295232728430561 delta -0.00014448084082423207
Mean initial mirror error V1 0.00039289642250000005 V3 0.0003884099391666667
Decision: V1 (simpler, order-independent tie-break)

```

V1 against F2:

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | -0.00317 | -0.00119 | 0.02564 |
| 2 m | D-thermistor-K | +0.01010 | +0.00000 | -0.00158 | -0.00050 | 0.00855 |
| 2 m | D-thermistor-K_scalar | +0.00000 | +0.00510 | -0.00169 | -0.00044 | 0.00862 |
| 2 m | E-before-thermistor-K | +0.00000 | +0.00000 | +0.00131 | -0.00060 | 0.00937 |
| 2 m | E-before-thermistor-K_scalar | -0.00313 | +0.00000 | -0.00775 | -0.00262 | 0.00940 |
| 2 m | E-after-thermistor-K | +0.00000 | +0.00313 | -0.00161 | -0.00091 | 0.00937 |
| 2 m | E-after-thermistor-K_scalar | +0.00000 | -0.00313 | -0.00341 | -0.00319 | 0.01250 |

V3 against F2:

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | -0.00317 | -0.00119 | 0.02564 |
| 2 m | D-thermistor-K | +0.01010 | +0.00000 | -0.00158 | -0.00050 | 0.00855 |
| 2 m | D-thermistor-K_scalar | +0.00000 | +0.00510 | -0.00169 | -0.00044 | 0.00862 |
| 2 m | E-before-thermistor-K | -0.00312 | +0.00000 | +0.00050 | +0.00073 | 0.00313 |
| 2 m | E-before-thermistor-K_scalar | +0.00000 | +0.00000 | -0.00257 | -0.00054 | 0.00313 |
| 2 m | E-after-thermistor-K | +0.00000 | -0.00312 | -0.00041 | +0.00080 | 0.00313 |
| 2 m | E-after-thermistor-K_scalar | +0.00000 | +0.00000 | -0.00013 | -0.00044 | 0.00313 |

No attribution threshold is crossed. Synthetic per-building frame angles,
10% fallback conditions and local sidewall/roof cell counts and peaks,
including the exposed tandem control, are in `physics_evidence/physics-f3-*-frames.log`.
Both variants leave the tower's mean delta K about +0.0026 (measured +0.276).
The defect was real but does not explain the tower-effect discrepancy.

Next-step reassessment: F4 remains a half-cell modelling tolerance on parameter
faces; original masks must remain intact. Its changes can move the roof point,
so the incident capture stays after geometry preparation, as implemented here.

## F4: facade runs

Smallest-deviation removal is deterministic across rings, bounded by every
original vertex in each merged run, with triangle-contact and edge-crossing
vetoes. Original masks are retained. Changed rings have canonical start vertices;
unchanged rectangles are untouched. The kinked rectangle's entire initial
velocity field equals the plain rectangle on both strict and exposed paths.
Circle, setback, unequal-grid, slot, courtyard and original-mask checks pass.

Serial **64/64**, OpenMP **67/67**, Python **2068 passed, 16 skipped**, with
only the three known F5 failures. Final archive:
`output/fixes/archive/F4-final-2b3de21`. The earlier `F4-0b297b9` is preliminary,
before canonicalizing ring start vertices. All A/B/D archived arrays are
bit-identical to F3. Score changes:

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K_scalar | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K | +0.00000 | +0.00000 | +0.00022 | +0.00168 | 0.00937 |
| 2 m | E-before-thermistor-K_scalar | +0.00313 | +0.00627 | +0.01118 | -0.00131 | 0.00940 |
| 2 m | E-after-thermistor-K | +0.00312 | +0.00000 | +0.00031 | +0.00174 | 0.00313 |
| 2 m | E-after-thermistor-K_scalar | -0.00313 | +0.00625 | +0.00787 | -0.00129 | 0.00937 |

Sensitivity archives are `output/sensitivity/archive/F4-quarter-0b297b9` and
`output/sensitivity/archive/F4-one-2b3de21`. Against half-cell:

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K_scalar | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K | -0.00312 | +0.00000 | +0.00178 | -0.00016 | 0.00000 |
| 2 m | E-before-thermistor-K_scalar | +0.00000 | -0.00313 | -0.01052 | +0.00212 | 0.00313 |
| 2 m | E-after-thermistor-K | -0.00312 | +0.00000 | +0.00056 | -0.00022 | 0.00000 |
| 2 m | E-after-thermistor-K_scalar | +0.00000 | -0.00312 | -0.00594 | +0.00226 | 0.00313 |

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K_scalar | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K | -0.00937 | -0.00625 | -0.01555 | -0.00307 | 0.03750 |
| 2 m | E-before-thermistor-K_scalar | -0.00313 | -0.00313 | -0.00430 | -0.00086 | 0.03448 |
| 2 m | E-after-thermistor-K | -0.00937 | +0.00938 | +0.00188 | -0.00419 | 0.03438 |
| 2 m | E-after-thermistor-K_scalar | -0.00233 | +0.00538 | +0.01111 | +0.00115 | 0.03762 |

No q/R change exceeds 0.02, so D3 remains half-cell. No attribution is required.

Next-step reassessment: F5 ports only spectral scaling. The research production
coupling failed accuracy protections and is excluded. The new 20 m cube test
finds spectral radius/B=3 before F5, independently reproducing the defect.

## F5: spectral stress limiter

Ported only `spectral_limit` unchanged from the research header; production
coupling remains excluded. Early TKE capping is retained. Per-cell double
spectral scales and energy-cap flags drive export and sampling; the two new
activity counters are exposed in Python metadata. Positive scaling preserves
indefinite eigenvalue signs; it is not a realizability repair.

The three cube directions now have maximum spectral radius/B=1 (before: 3).
Cell-by-cell native checks cover spectral and streamwise bounds, tensor shape,
inactive-cell locality, unchanged mean wind, export/probe agreement, counts,
and calm flow. NumPy rotation/scaling oracles, zero, nonfinite and indefinite
cases pass. Serial **65/65**, OpenMP **68/68**. The full Python run exposed four
stale metadata/component-cap assertions; these now check the new counters and
independent eigenvalue bound. The focused runner/oracle suite passes **78/78**;
the full rerun passes **2072 tests, 16 skipped**.

Archive: `output/fixes/archive/F5-2b3de21`. No attribution threshold is crossed:

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | -0.00350 | -0.00955 | +0.05799 | +0.05917 | 0.09028 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00464 | +0.00867 | -0.01775 | +0.03697 | 0.06122 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K_scalar | -0.00135 | +0.00168 | -0.00030 | -0.00230 | 0.00431 |
| 2 m | E-before-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K_scalar | -0.00024 | -0.00160 | +0.02449 | +0.00672 | 0.04389 |
| 2 m | E-after-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-after-thermistor-K_scalar | +0.00000 | +0.00625 | +0.01506 | +0.00797 | 0.04375 |

Comfort example maps and raw arrays: `output/comfort/F4-baseline` and
`output/comfort/F5`. The old Python package and extension were isolated for the
baseline, since current Python metadata requires the new native counters.
Maximum absolute GEM change is **1.356 m/s**, 99th percentile **0**, and
**0.136%** of finite directional map cells change by >0.05 m/s. Non-realizable
share at 1.5 m is zero in every direction both before and after in this example.
The example's 1.5 m centre is its third layer; F6 only changes the first two
layers, so this particular map need not change under F6.

Next-step reassessment (F6): the requested all-layer 2% analytic profile check
cannot hold above the corrected two layers while retaining central differences.
On a 2 m grid at z=5, their log-gradient bias is about 5.7%, versus about 1.7%
at z=9. Tests will use the exact log gradient in the first two layers and the
unchanged discretized derivative elsewhere. This preserves F6's stated scope.

## F6: ground-adjacent derivatives

The shifted-log closure applies to the first two ground layers, using a
wall-function fallback when the upper cell is solid. Roof derivatives are
bit-identical in the reversed-roof manufactured test. Uniform, shifted-log,
linear and oblique profiles pass on uniform and stretched grids, including
an overhang with poisoned solid-cell velocities. The overhang is constructed
at the core boundary: the public flat-ground input rejects nonzero base heights.

**Correction to the plan:** `WINDSGeneralData.cpp` overwrites `z0` with
`parameterizations.wallRoughness` after initially setting it from the inflow.
F6 therefore stores `groundRoughness` from the constructor/profile separately.
Using `z0` failed the manufactured test by 3.7%; the dedicated field passes.
The inherited ground stencil is suppressed before the new one is applied,
so its one-sided difference cannot supply a solid-cell velocity.

Measured sigma/uStar in an empty domain:

| Grid | First centre | sigma/uStar | Second centre | sigma/uStar |
|---|---:|---:|---:|---:|
| 2 m | 1 | 2.27025 | 3 | 2.41672 |
| 1 m | 0.5 | 2.07939 | 1.5 | 2.33932 |
| stretched | 0.25 | 1.78186 | 0.875 | 2.23875 |

All computed layers agree within 2% with the scoped gradient/mixing-length
prediction; intensity decreases monotonically. The first two ground gradients
match the shifted-log analytic derivative to 1e-5 relative error. Linear-shear
oracles explicitly use the log-space model in those layers, not an exact linear
derivative. The κ*d mixing length and higher-layer central differences remain.

Serial **66/66**, OpenMP **69/69**. Five Python analytic assertions still used
central differences in the second ground layer; updated independent formulas
pass the focused suite (**60 passed, 8 skipped**). Full strict release suite
is running on Python 3.13, matching the original checkout.

Archive: `output/fixes/archive/F6-aab96e8`. No attribution threshold is crossed:

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | +0.00000 | +0.00000 | +0.00011 | -0.00075 | 0.00000 |
| 2 m | B-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00000 | +0.00503 | +0.00002 | -0.00100 | 0.00000 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | D-thermistor-K_scalar | -0.01015 | -0.00508 | +0.00049 | +0.00600 | 0.00000 |
| 2 m | E-before-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-before-thermistor-K_scalar | +0.00625 | +0.01875 | -0.00384 | +0.00894 | 0.00000 |
| 2 m | E-after-thermistor-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | E-after-thermistor-K_scalar | +0.01875 | +0.00625 | -0.00114 | +0.00859 | 0.00000 |

The comfort example's GEM maps are bit-identical between F5 and F6: its 1.5 m
sample is the third cell centre. Its full directional maps and raw arrays are
in `output/comfort/F6`. This does not imply unchanged comfort on uniform grids,
where 1.5 m lies in the corrected/interpolated ground layers.

Next-step reassessment: all six fixes are implemented. Proceed to full release
validation, fresh build/sanitizer checks, audited fixture updates, packaging,
version/documentation updates, and the upstream draft. Qualification stays frozen.

## Release validation and final reassessment

The full release archive is `output/fixes/archive/release-165ad02`, compared
against `output/archive/baseline-full-be78a1c`: **74 successful runs**, including
61 freshly solved and 13 matching F6 runs reused; no failed runs. Runtime was
1384 s, with native builds/tests concurrently active, so these timings are not
a controlled performance comparison. Native physics is unchanged after F6;
later changes repair a test's coordinate bounds, identify fixtures, and update
metadata/documentation. The release metadata identifies turbulence numerics v3;
the archived numerical campaign preceded that metadata-only version change.

| Case/quantity | q (2 m / 1 m) | R (2 m / 1 m) |
|---|---:|---:|
| A-K | 0.683 / 0.661 | 0.887 / 0.864 |
| B-K | 0.504 / 0.513 | 0.744 / 0.733 |
| D-split_fibre | 0.273 / 0.273 | 0.546 / 0.550 |
| D-thermistor-K | 0.237 / 0.247 | 0.426 / 0.425 |
| E-before-thermistor-K | 0.161 / 0.159 | 0.515 / 0.500 |
| E-after-thermistor-K | 0.293 / 0.278 | 0.460 / 0.445 |
| A-k | 0.101 / 0.070 | 0.242 / 0.191 |
| B-k | 0.030 / 0.020 | 0.082 / 0.141 |
| D-k | 0.030 / 0.061 | 0.089 / 0.122 |

Full baseline-to-release deltas (k comparisons use `W=0`; the last column is
the share above 0.05 in the displayed normalized quantity, not an error gate):

| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |
|---|---|---:|---:|---:|---:|---:|
| 2 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | A-W | +0.00000 | +0.00000 | -0.00000 | +0.00000 | 0.00000 |
| 2 m | A-k | -0.00350 | -0.00955 | +0.05810 | +0.05842 | 0.09028 |
| 2 m | B-K | +0.00000 | +0.00000 | -0.00000 | +0.00000 | 0.00000 |
| 2 m | B-U | +0.00000 | +0.00000 | -0.00000 | -0.00000 | 0.00000 |
| 2 m | B-W | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 2 m | B-k | +0.00464 | +0.01369 | -0.01773 | +0.03597 | 0.06122 |
| 2 m | D-split_fibre | +0.00000 | +0.00000 | -0.00317 | -0.00119 | 0.02564 |
| 2 m | D-thermistor-K | +0.01010 | +0.00000 | -0.00158 | -0.00050 | 0.00855 |
| 2 m | D-thermistor-K_scalar | -0.01150 | +0.00171 | -0.00149 | +0.00326 | 0.01293 |
| 2 m | E-before-thermistor-K | +0.00234 | +0.00312 | +0.00109 | +0.00963 | 0.04922 |
| 2 m | E-before-thermistor-K_scalar | +0.00849 | +0.02737 | +0.02543 | +0.02380 | 0.10345 |
| 2 m | E-after-thermistor-K | -0.00469 | -0.00469 | +0.00288 | +0.01718 | 0.06484 |
| 2 m | E-after-thermistor-K_scalar | +0.02079 | +0.01873 | +0.02816 | +0.03037 | 0.12274 |
| 2 m | D-k | +0.00000 | -0.06061 | -0.00282 | +0.11429 | 0.00000 |
| 1 m | A-K | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 1 m | A-U | +0.00000 | +0.00000 | +0.00000 | +0.00000 | 0.00000 |
| 1 m | A-W | +0.00000 | +0.00000 | -0.00000 | -0.00000 | 0.00000 |
| 1 m | A-k | -0.00183 | -0.00616 | +0.01946 | +0.05771 | 0.10458 |
| 1 m | B-K | +0.00000 | +0.00000 | +0.00000 | -0.00000 | 0.00000 |
| 1 m | B-U | +0.00000 | +0.00000 | +0.00000 | -0.00000 | 0.00000 |
| 1 m | B-W | +0.00000 | +0.00000 | -0.00000 | +0.00000 | 0.00000 |
| 1 m | B-k | -0.00019 | +0.00883 | +0.00706 | +0.06355 | 0.06931 |
| 1 m | D-split_fibre | -0.03030 | +0.00000 | -0.00259 | -0.00122 | 0.02564 |

Attribution required for D-split_fibre: probes/directions with changes >0.05: 75/0 deg., 76/0 deg.

| 1 m | D-thermistor-K | +0.01010 | +0.00000 | -0.00146 | -0.00052 | 0.00855 |
| 1 m | D-thermistor-K_scalar | +0.00510 | +0.00000 | +0.00458 | +0.00274 | 0.01724 |
| 1 m | E-before-thermistor-K | +0.00078 | +0.00313 | +0.00146 | +0.01190 | 0.05547 |
| 1 m | E-before-thermistor-K_scalar | +0.00593 | +0.00701 | +0.04276 | +0.01739 | 0.11348 |
| 1 m | E-after-thermistor-K | -0.00078 | -0.00156 | +0.00366 | +0.02041 | 0.07187 |
| 1 m | E-after-thermistor-K_scalar | +0.01165 | +0.01706 | +0.03617 | +0.02773 | 0.14139 |
| 1 m | D-k | +0.00000 | +0.03030 | -0.00367 | -0.01645 | 0.00000 |

### Attribution and late comparison-tool correction

The first comparison tables omitted Case D's separately stored split-fibre k
scores. The comparison utility now includes them. Their stepwise changes are:

| Step | delta q | delta FAC2 | delta R | delta FB |
|---|---:|---:|---:|---:|
| F1-3b82e6e | +0.00000 | +0.00000 | -0.00000 | -0.00000 |
| F2-acc7a50 | +0.00000 | +0.00000 | +0.00000 | +0.00000 |
| F3-V1-acc7a50 | +0.00000 | +0.00000 | -0.02569 | -0.00490 |
| F4-final-2b3de21 | +0.00000 | +0.00000 | +0.00000 | +0.00000 |
| F5-2b3de21 | +0.00000 | +0.00000 | +0.00000 | +0.00000 |
| F6-aab96e8 | +0.00000 | -0.06061 | +0.02287 | +0.11919 |

**F3, D-k at 2 m:** R changes from 0.091414 to 0.065725 (−0.025689), crossing
the 0.02 attribution threshold. The largest changes in normalized k are at
probe 33, (−5,−15,2 m), 0.009795 → 0.014025 (measured 0.019131), and probe 32,
(−5,15,2 m), 0.009787 → 0.007773 (measured 0.030426). Probes 30 and 29 change
by −0.000785 and −0.000730. These near-tower changes follow the corrected
incident frames and their local shear; F2→F3 is isolated in the immutable fast
archives. The first change improves an already low value while the second
worsens it, reducing their pooled correlation. F4/F5 leave D-k unchanged;
F6 increases R by 0.02287. This observed regression does not justify restoring
the contaminated reference.

**Release, D split-fibre K at 1 m:** q changes from 10/33 to 9/33, entirely
because probe 59 at 0 degrees moves from 0.23947337 to 0.24264145. Measured
K is 0.18966854 and the absolute tolerance is 0.05: the error crosses from
0.04980483 to 0.05297292. A dedicated historical F2 build reproduces
0.23947349 there, and all its D probe K values are within 1.70e-6 of baseline.
F3 is therefore the responsible wind correction: F4 leaves these rectangles
unchanged, and F5/F6 do not change mean wind. The diagnostic is retained in
`output/attribution/F2-D-1m`, built from `acc7a50`; its native identity is
`c478f1add202b8b1ea6f0037b73403ba202a417d1a97bf1506412c191706e2a2`.
The >0.05 K moves at probes 75/76 are not the reason q loses that hit.

### Final-field magnitude and remaining tower limitation

The following statistics pool matching fluid samples on the **archived
measurement-height planes**, not whole 3D volumes. They measure the norm of
the velocity-vector difference after pressure correction; spatially spread
changes are expected and are not judged against initial parameterization zones.

| Grid | Case | Valid pairs | max vector change (m/s) | p99 (m/s) | share >0.05 m/s |
|---|---|---:|---:|---:|---:|
| 2 m | E | 1582128 | 4.382199 | 0.551513 | 0.083086 |
| 2 m | D | 162168 | 5.791975 | 0.015585 | 0.005833 |
| 2 m | B | 20096 | 0.000010 | 0.000004 | 0.000000 |
| 2 m | A | 19072 | 0.000005 | 0.000002 | 0.000000 |
| 1 m | E | 6334416 | 5.522393 | 0.672287 | 0.090197 |
| 1 m | D | 648525 | 6.640672 | 0.014991 | 0.005815 |
| 1 m | B | 80384 | 0.000021 | 0.000007 | 0.000000 |
| 1 m | A | 76288 | 0.000011 | 0.000003 | 0.000000 |

The all-direction tower diagnostic gives mean ΔK within 30 m of +0.261607
measured versus −0.002496 simulated (352 pairs). The four-direction fast values
reported for F2/F3 above use a different subset. These fixes do not resolve the
missing tower speed-up; the out-of-scope model changes remain deferred.

### Release checks

- Fresh serial CTest: 66/66; fresh OpenMP: 69/69.
- Debug ASan/UBSan: 65 checks passed initially; `ground_gradient` caught an
  out-of-bounds read in the new test's profile initialization. The test confused
  face count with the shorter z-centre vector. Both initialization loops now
  use `d.z.size()`. The rebuilt affected check passes under ASan/UBSan and both
  Release backends; no production source changed. Thus all 66 checks pass.
- Strict Python (`-W error`), Python 3.13: OpenMP **2104 passed**, serial
  **2094 passed, 10 skipped** (OpenMP-specific checks). Earlier 16 permanently
  skipped historical-parity checks now run against the identified current
  backend fixtures. The final metadata-only checks pass: **190 tests**.
- Native symbol audit passes on both Release QES archives and all bridge
  objects. Debug sanitizer objects pass file-I/O/library/device checks; debug
  assertion/diagnostic symbols are intentionally outside the Release-only ban.
- Schema-2 audited embedded snapshots for eight cases on both backends pass
  exact generation/replay and source/archive provenance checks. Historical
  standalone archives remain byte-identical. Public/raw bridge comparisons
  explicitly select the same fixed-relaxation/multiplier stopping settings;
  today's public defaults otherwise differ.
- The 0.1.0b5 sdist and wheel built from it pass the artifact/evidence audit.
  Isolated wheel smoke exercises owned outputs, sampling, both turbulence
  methods, canonical geometry, legacy and adaptive control; the latter reports
  `unqualified_build` as required. Final artifact hashes are recorded below.

The release increments turbulence metadata to `dtcc-qes-turbulence-v3`, names
the spectral/ground fixes and corrects its old standalone-parity wording.
No qualification header/evidence changes, model additions from section 7, or
runtime switches were introduced. The [upstream issue draft](../docs/upstream-physics-issue-draft.md)
contains F1/F3 reproductions and is not submitted.

All archived SHA-256 manifests were rechecked before integration. Raw release
check logs and the full summary are retained in `validation/physics_evidence/release`.

Release artifacts and their SHA-256 manifest are in `build/physics-artifacts/`.
The wheel is built from the unpacked source distribution and installed into an
isolated directory for the runtime smoke test. No package is uploaded.

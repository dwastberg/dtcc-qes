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
the full rerun is pending.

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

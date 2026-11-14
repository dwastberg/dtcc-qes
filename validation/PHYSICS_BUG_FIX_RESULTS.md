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

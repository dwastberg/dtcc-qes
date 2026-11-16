# Precision stagnation: implementation and validation

Date: 2026-11-16. The stopping fix passed its numerical, native, Python,
thread/backend, and packaging checks. **Adaptive requalification was not
promoted:** the current baseline already differs from the last qualified
implementation and three frozen S7 workers. Those differences persist unchanged.

## Implementation

The velocity rule now also stops after eight checks without a new minimum
block change, provided all eight counted checks stay within twice the estimated
arithmetic floor. Existing error-estimate and consecutive-floor stops have
precedence. State resets at every condition; fixed-work solves keep their full
budget. The raw estimate and history remain unchanged.

The result reports `termination="precision_floor"` and
`floor_trigger="stagnation"`. Existing floor stops identify
`floor_trigger="consecutive_checks"`; other terminations report null. Constants
are recorded as `stagnation_checks=8` and `stagnation_floor_factor=2`. The offline
replayer applies the new condition only when these constants are present, so
historical records retain their original stopping semantics.

As with the existing precision-floor outcome, `converged=True` does **not**
certify the requested tolerance: it means further arithmetic-level progress is
unavailable. Fixed work, the multiplier rule and adaptive numerical decisions
are unchanged. The comfort dataset continues to warn and retain available
fields when a solve genuinely reaches its iteration limit.

## Numerical results

The native probe compares multiplier-derived corrections on every fluid face
assessed by the stopping rule, before final output rounding. References use
float64 fixed work until their remaining-change estimate is at most `1e-8`,
then require another 500 iterations to change the assessed faces by at most
`1e-9 U_ref`. Every candidate must stop before the iteration cap and have a
maximum face error at most `0.001 U_ref`.

| Matrix | Cases | New stagnation stops | Largest face error / U_ref |
|---|---:|---:|---:|
| Demo, all 16 directions at 1 m and 2 m | 32 | 3 | 0.000519713 |
| AIJ: 24 distinct Case C configurations and 14 E1 base cases | 38 | 24 | 0.000468208 |

**All 70 cases passed.** The largest reference stability change was below
`9.11e-10 U_ref`. These are numerical-error checks, not a validation of QES's
physical model or gust predictions.

For the reported 570 × 570 × 105, 116-building, 67.5° case:

- Stops at **1,050** iterations instead of **20,000** (94.75% fewer sweeps).
- Maximum assessed-face error is `0.000120916 U_ref`, or **0.000605 m/s** at
  the 5 m/s reference speed, below the **0.005 m/s** tolerance scale.
- The float64 reference uses 3,500 iterations; the additional 500-iteration
  stability difference is `2.44e-13 U_ref`.

Replay of 1,391 archived accuracy histories changes the 87 Case C histories
and leaves the other 1,304 stopping points unchanged. The 87 histories reduce
to 24 distinct configurations; all 24 actual native stopping points match
replay exactly. In E1, all **98 runs × five tolerances** retain the existing
probe accuracy gates (p95 ≤ 0.0025 and maximum ≤ 0.01); 37 stopping points move
earlier. Those tighter-tolerance precision-floor outcomes do not claim to
satisfy the requested error tolerance.

The archived completed 2 m comfort run and the candidate have the same stopping
iteration in all 16 directions. With unchanged iterates, the stopping change
therefore introduces no field/class change for those inputs. At 1 m the old
assessment aborted before producing a complete comfort map. No paired annual
class-invariance claim is made for that grid: the validation establishes the
stated solver error bound, and cells near classification thresholds may change.

Evidence: [numerical summary](data/precision-stagnation/numerical-summary.json),
[accuracy replay](data/precision-stagnation/replay.json),
[E1 replay](data/precision-stagnation/e1-replay.json),
[native/replay agreement](data/precision-stagnation/native-replay-parity.json),
[coarse stopping points](data/precision-stagnation/coarse-stops.json).
Each full-face result has its exact exported geometry/profile input alongside it.

## Tests, compatibility and costs

- Release OpenMP: **69/69** native tests; Release serial: **66/66**;
  Debug ASan/UBSan: **66/66**. All three native symbol audits passed.
- Full isolated Python suites, warnings treated as errors: **2,174 passed on
  each backend**. The real stagnation regression exercises normal and bounded
  execution, fixed-work continuation, serialization and prepared-model reuse.
- The recorded small plateau has identical stopping histories, diagnostics and
  velocity hashes in serial and OpenMP at 1, 2, 4 and 8 threads.
- Against current baseline `7008159`: **509 cases / 5,503 records per backend
  and team**, zero differences; serial/OpenMP and thread parity passed.
- Combined feature baseline comparison passed, including adaptive cases.
- All 16 embedded turbulence fixture arrays remain exactly equal. Their
  provenance was regenerated for the new native identity without changing the
  stored array archives.
- Initial cost samples under concurrent validation were noisy. Three alternating
  baseline/candidate repetitions give median differences of +0.281 ms for
  wind-only calls, +0.691 ms for combined calls, and +0.045 ms for export.
  None crosses the repository's joint 10% / 10 ms review threshold. Reference
  validation was active during timing; these are regression checks, not an
  uncontended speed benchmark.
- Sdist and wheel built from that sdist pass the artifact/evidence audit and
  installed-wheel smoke checks, including the new stagnation trigger. The local
  editable extension was rebuilt to make the fix available to the demo.

The full-suite work also repaired the README test's missing weather mock and
headless plotting setup, used a distinct `comfort_result` variable in the
README, and aligned the cell-limit assertion with the workspace's pre-existing
50-million-cell default.

## Requalification outcome

| Build | Source/arithmetic identity |
|---|---|
| Last qualified (`fe2dcd3`) | `31f6d956fecfa24654a34b7ed43941c38876f38b26d0800ca5868e7b54396f87` |
| Current baseline (`7008159`) | `e130c2fbf47179923862c037a9a370ec17b91788a01f6719cd282506ba43471a` |
| Candidate | `df09ee9d8b82471171868fe441bc082c3a17094ce6e03f84295909e51bba329b` |

The baseline changelog already documents ordinary wind solves as supported and
`pedestrian-v1` as unqualified. The strict comparison against the last qualified
commit reports 659 differing records for each backend/team; comparison against
the current baseline reports zero. This stop-rule fix does not undo those
intervening numerical/model changes.

Both baseline and candidate were also built with their own identity enabled in
**isolated staging copies only**, and all 24 frozen S7 workers were executed.
Both fail the same three workers: `release-online-02`, `-09` and `-20`
(`val_mixed_195`, adaptive/legacy variants). Their fields, diagnostics and
assessment histories differ from the archive. All 24 candidate workers match
the current baseline after the existing elapsed-timestamp exclusion.

The production qualification header remains unchanged. There is **no new
adaptive qualification claim** and no blanket metadata or numerical exception.
Resolving the older model/policy differences requires separate qualification
work; it is not a reason to change the stopping guard or overwrite the archive.

Evidence: [current-baseline parity](data/precision-stagnation/parity.json),
[last-qualified comparison](data/precision-stagnation/last-qualified-parity.json),
[baseline frozen workers](data/precision-stagnation/baseline-policy-all/summary.json),
[candidate frozen workers](data/precision-stagnation/policy-all/summary.json),
[worker baseline/candidate parity](data/precision-stagnation/policy-baseline-parity.json).
Raw worker JSON is gzip-compressed alongside each summary.

## Reproduction

The declaration, initial source manifest, arithmetic identity files, input
checksums, test logs and comparison reports are under
`docs/data/precision-stagnation`. Historical evidence is retained unchanged.
Use fresh output directories for reruns.

Build a Release candidate with tests and OpenMP, then build the standalone probe
with the exact compiler/flags/libraries of its `check_stop_rule` target:

```sh
cmake -S . -B build/stagnation-repro -G "Unix Makefiles" -DCMAKE_BUILD_TYPE=Release \
  -DDTCC_QES_OPENMP=ON -DDTCC_QES_BUILD_TESTS=ON \
  -DPython_EXECUTABLE="$PWD/.venv/bin/python"
cmake --build build/stagnation-repro --target check_stop_rule _qes -j 6
mkdir -p build/stagnation-repro/demo build/stagnation-repro/aij
cp docs/data/precision-stagnation/demo/*.txt build/stagnation-repro/demo/
cp docs/data/precision-stagnation/aij/*.txt build/stagnation-repro/aij/
PYTHONPATH="$PWD" OMP_NUM_THREADS=4 .venv/bin/python tools/validate_precision_stagnation.py \
  --build-dir build/stagnation-repro --probe build/stagnation-repro/precision_probe \
  --output build/stagnation-repro/demo --run-only
PYTHONPATH="$PWD" OMP_NUM_THREADS=4 .venv/bin/python tools/validate_precision_stagnation.py \
  --probe build/stagnation-repro/precision_probe \
  --output build/stagnation-repro/aij --run-only
PYTHONPATH="$PWD" .venv/bin/python tools/replay_precision_stagnation.py \
  --output build/stagnation-repro/replay
```

The CMake commands use a Makefiles generator (the probe builder reads its
`flags.make` and `link.txt`). To refetch geometry instead of using the frozen
inputs, use a fresh output directory and `--export-only`; AIJ export additionally
uses `--suite aij` and the archived `.spec.json` requests plus local AIJ data.

# Solver-control release closure

> Historical stage report: original snippets and identities are preserved. Use the current [migration table](../README.md#api-migration) and [solver guide](solver-control.md) for live calls.

The solver-control refactor closes within the **qualified pedestrian numerical
scope**, with legacy/bounded compatibility retained. This is not a claim of
general urban accuracy, physical validation, grid independence or regulatory
comfort qualification. S8b is explicitly deferred at the user's request.

The release [scope ledger](data/solver-control-s9/scope.json) is machine-readable.
The final [evidence manifest](data/solver-control-s9/manifest.json) binds source,
build, validation and prior-evidence identities. Release validation results and
artifact hashes are published there; compiled packages and full default fields
remain in the recorded build directory. No package upload or default promotion
is part of this closure.

## Completed work and explicit dispositions

| Stage | Delivered outcome |
| --- | --- |
| [S0](solver-control-s0.md) | Frozen baseline, phase contract and bounded study protocol. |
| [S1](solver-control-s1.md) | Owned operator/workspace and begin/advance/observe/diagnose/finalize lifecycle. |
| [S1a](solver-control-s1a.md) | Condition-state reset, model-dependency validation and fresh/reused parity. |
| [S2](solver-control-s2.md) | Compact immutable coefficients, reduced traffic and explicit serial red/black migration. |
| [S3](solver-control-s3.md) | Compiled slab/receptor monitoring, regional diagnostics and bounded history/storage. |
| [S4](solver-control-s4.md) | Cooperative native budgets, Python/dataset controls and usable status/error records. |
| [S5](solver-control-s5.md) | Urban campaigns, tolerance investigation, coherent diagnostics, small qualified references and independently frozen S5c mask repair. The disabled-controls performance target is a recorded non-pass. |
| [S6](solver-control-s6.md) | Method study selects internal 1.90f relaxation for the qualified opt-in policy; default remains 1.78f. |
| [S7](solver-control-s7.md) | Empirically qualified pedestrian-v1, fixed method/build identity and zero false acceptances in the frozen held-out matrix. |
| [S8a](solver-control-s8a.md) | Measured four/eight-direction reuse decision; public prepared-model API deferred because the predeclared benefit gate was not met. |
| S8b | User-directed deferral. No comfort uncertainty propagation or selective directional refinement is delivered. |
| S9 | Isolated source freeze, compatibility/release checks, evidence audit and this scope ledger. |

Historical stage reports and source archives retain their original meanings.
The deliberate S1a reset fix, S2 serial ordering migration and S5c mask repair
remain separate numerical decisions; they are not attributed to S9. Final
default comparisons use the corrected S5c baseline and require exact results,
without a blanket tolerance or broader exception.

## Public execution contract

Defaults remain float32, 500 iterations, tolerance 1e-5, OpenMP ON, red/black
ordering and legacy relaxation 1.78f. Serial builds are supported explicitly.
Float64 multiplier/RHS/correction arithmetic is opt-in; geometry, coefficients
and returned velocity arrays remain float32. Explicit uniform/graded grids
remain supported; automatic grids remain provisional.

`wind.run` accepts flat-ground, validated, non-touching/hole-free LOD0 building
footprints and the existing height/terrain policies. Coordinates use one planar
metre frame with the supported absolute-translation transform convention.
Results own their arrays. Monitoring declares local or world coordinates;
world monitors are compiled against the prepared origin/CRS. Nearest sampling
and explicit component-wise linear height sampling retain their support rules.
Optional algebraic turbulence has height and wall-distance mixing methods;
neither is qualified for pedestrian gust prediction by solver acceptance.

| Mode/status | Meaning |
| --- | --- |
| Legacy, `solver_control=None` | Existing multiplier-change tolerance and iteration cap; `diagnostics.converged` is not a physical or velocity-error guarantee. |
| Bounded | Legacy method with a cooperative native deadline, bounded diagnostics and `accuracy_status='not_assessed'`. |
| Adaptive, accepted | pedestrian-v1 assessed the declared ROI/heights and every required receptor within its frozen numerical/build envelope. Legacy convergence can remain false. |
| Adaptive, unsupported/unaccepted | No qualified acceptance. Unsupported configurations use bounded legacy-method execution and retain the reason/status. |
| `BudgetExhaustedError` | Deadline reached without a completed sweep; carries phase/work/timing evidence instead of a fabricated finite result. |
| `NumericalFailureError` | Adaptive numerical failure with a control record; no accepted or fabricated fallback field. |
| `ConvergenceError` / `UnacceptedResultError` | Opt-in raising contracts for legacy/bounded non-convergence or adaptive non-acceptance respectively. |

Adaptive mode rejects calm wind and `raise_on_nonconvergence=True`; use
`raise_on_unaccepted=True`. Preparation is outside the solve budget. Native
mutex wait, initialization, RHS, sweeps and monitoring are inside it; required
finalization, turbulence and output remain separately timed. Checks occur
after every complete CPU sweep regardless of checkpoint cadence. This is not
an end-to-end wall-time guarantee. There are no Python iteration callbacks,
public warm starts or public resumable iterates.

`QESWindArgs.solver_control` stores normalized control settings. Adaptive dataset
cache identity includes the native policy revision and rejects stale explicit
identities. Dataset health distinguishes legacy convergence from numerical
acceptance, carries assessment scope and retains warnings/limitations. Timing
and budgeted work counts are not advertised as deterministic.

## Qualified envelope and measured cost

The authoritative S7 envelope is 80 × 80 × 32 cells at 2 m x/y, uniform 2 m
layers or the specified 1.2 × 1.03^k graded layers, neutral Uref 2–10 m/s at
10 m with z0=0.1 m, 4–32 rectangular buildings with specified dimensions and
domain margins, default model flags, float32 wind without turbulence. It
requires both 1.5/1.75 m, sufficient ROI support, and every required receptor.
The matching AppleClang 17 arm64 contraction/source identity is required, with
serial or actual OpenMP teams 1–4. Exact dimensions, receptor placement and
all gates are in [S7](solver-control-s7.md); this paragraph does not broaden them.

The frozen native revision is
`d0775583915762bbe2accfcad81d38e21b4c79037ea2dd0fa4c6c7cd5a24fde3`;
the method is `s5c-rb-sor-float-omega-v1-omega-1.90`. S9 changes packaging,
orchestration, verification and documentation, without native arithmetic or
policy parameter changes. New unsupported builds stay unaccepted until
separately qualified; copying the expected identity is not qualification.

S7's held-out accepted cases stop at 225/250 sweeps, with measured full API
times around 0.13–0.14 s on that study host. These are scoped observations.
S5 cadence/thread/deadline studies retain their raw records; 25-sweep adaptive
checkpoints do not reduce per-sweep deadline checks. Tight budgets can exhaust
during initialization or monitoring. S8a's eight-direction reuse saves only
49 ms / 6.9% legacy and 26 ms / 2.5% adaptive in its primary pilot; its separate
replay also misses the unchanged adoption gate. No universal speed claim or
default thread tuning follows from these numbers.

## Unresolved numerical and physical limitations

The original restricted vertical-grid closure remains restricted. Historical
horizontal/near-wall/local sensitivity failures persist. The vertical study's
finest reference exhausts its certification budget; accepted coarser-grid and
alignment comparisons fail added local speed budgets. `sensitivity_budget_pass`,
`alignment_budget_pass` and `comfort_qualified` remain false. The attempted
longer finest-reference follow-up was stopped after the fast-use-case review;
no accepted finest reference or withheld dependent comparison is fabricated.
See [vertical refinement](vertical-refinement.md),
[finest-reference runtime review](finest-reference.md) and
[grid plan](../DYNAMIC_VERTICAL_GRID.md).

S5b's oblique downtown/courtyard hotspots exposed prepared solids relabeled
as canyon fluid. S5c repairs that mask/operator inconsistency separately;
pre-fix failures and counterfactual studies remain archived. Large-city core
fields are still numerically unqualified. A 2,000-sweep benchmark or a small
equation residual alone is not a qualified reference. S7's failed 96 × 80
graded-domain reference remains outside the qualified envelope.

The last solved band retains its prescribed upper-face convention. The
highest physical layer and lateral shell remain unassessed. No boundary
physics is silently changed to improve a gate. The <=5% disabled-controls API
regression review target was missed (roughly +11–15% in confirmation); its
documented non-pass disposition is retained and is not a numerical exemption.

S8b comfort sensitivity is deferred explicitly. Qualified directional bounds,
real-climate validation, mean/GEM distinctions, missing-direction/support
handling and physical/regulatory comfort qualification remain future work.
GPU, multi-right-hand-side kernels, preconditioners, warm starts, per-runner
logging, model/boundary changes and default policy promotion are separate tasks.

## Validation and reproduction

Release validation runs fresh OpenMP/serial native suites, the full Python
suite against the isolated release package, focused ASan/UBSan checks,
forbidden-symbol audits, strict 429-case revision/team/backend comparisons,
installed-wheel runtime checks and sdist/wheel content checks. Existing S7
held-out reference/policy evidence is re-audited; final-build API workers check
the same fixed requests against their published output identities. Finite
campaign smoke runs verify fresh fixtures, unchanged prior outcomes, matching
build reuse and rebuilds after source/toolchain/ABI/package changes. Smoke
campaigns verify orchestration, not numerical accuracy or speed.

The final native counts are **48 OpenMP, 45 serial and six focused ASan/UBSan**.
The full Python suite passes **1,095 tests**, with 16 skips restricted to
historical exact fixtures requiring their recorded ordering/toolchain. Twelve
429-case revision/team/backend comparisons are exact, and all 24 final-build
policy workers match S7's published fields, diagnostics and recorded decisions.
Three real smoke campaigns verify cache reuse and damaged-package rebuilding;
the full Python suite additionally checks source/toolchain/backend/ABI/runtime
changes and failed-build handling. No smoke timing is used as a speed claim.

An initial full Python run passed 1,060 tests but skipped 50 because the staged
environment did not point to already-built native integration executables.
That run and its XML/log are retained. Explicit executable wiring enables the
final full run above; no failing numerical fixture was hidden or reclassified.

The first wheel-build attempt stopped at the frontend's unmet optional Ninja
dependency. It is retained with its source distribution and failure log. The
release helper now defaults to the available Unix Makefiles generator (while
honouring an explicit `CMAKE_GENERATOR`), and artifact retries always use fresh
directories. This build-driver correction changes no runtime or numerical code.

```sh
# New output directory; complete release validation (builds and tests included).
.venv/bin/python tools/validate_solver_release.py --output build/solver-release-check

# Ordinary end-to-end urban campaign; frozen S9 candidate and verified cache.
.venv/bin/python tools/run_urban_benchmarks.py --tier pilot

# Portable final evidence audit; no solver build required.
.venv/bin/python tools/audit_solver_release.py docs/data/solver-control-s9
```

The final evidence includes command/timeout/result records, Python ABI,
compiler/build/OpenMP identities, source-member hashes, package hashes,
per-array default fingerprints, input/output identities, and retained failed
attempts. Worker histories and monitor allocation limits remain explicit;
urban workers retain 30 s timeouts and six-worker/180 s shards. No historical
worker is rerun under an unchanged identity to overwrite a prior outcome.

S9 repairs one packaging-only S8a metadata defect: the original manifest
accidentally included a generated bytecode cache. The original manifest is
preserved as `manifest-s8a-original.json`, and a new `s8a-packaging-metadata-v2`
identity removes only the cache entry. All measured outputs and source archives
retain their previous hashes. The original clock-comparison harness failure
also remains visible. These corrections are not numerical evidence replacement.

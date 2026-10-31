# S6 — Recorded iteration-method decision

S6 is complete for its declared method-selection scope. Select red/black SOR
with the existing internal `1.90f` relaxation option as the **candidate for S7
calibration**. Preserve `1.78f` for every existing public legacy and bounded
call. No public omega parameter, stopping policy, kernel, boundary condition or
preconditioner is added.

The frozen candidate identity is `s5c-rb-sor-float-omega-v1-omega-1.90`.
[method-decision.json](data/solver-control-s6/method-decision.json) binds the
factor, implementation and scope. Changing the method, arithmetic, condition
mask or boundaries requires renewed reference compatibility and calibration.
S7 is still required before any online numerical acceptance can be advertised.

## Protocol and scope

The [main protocol](data/solver-control-s6/protocol.json) was written before
measurements. It limits the study to 43 sequential workers, 30 seconds per
worker and 180 seconds for the study, with no automatic retries. The measured
main run took 46.7 seconds excluding build/test time.

Screen `omega={1.78,1.85,1.90,1.95}` on two S5 reference-compatible fixtures:

- `tower_2m`: four unequal-height buildings, including a 23.7 m tower, with
  shelter, passage and tower-wake receptors; 270° wind.
- `passages_2m`: 20 buildings in a 4×5 arrangement, 12×14 m footprints,
  10–22 m heights, narrow streets and repeated passages; 270° wind.

Both use a 160×160×64 m domain with uniform 2 m cells, 204,800 physical cells,
Uref=5 m/s at 10 m and the canyon model enabled. The held-out condition is the
same 20-building passage morphology at 225°. Its independent float64
500/1000/2000 zero-start triple qualifies under the unchanged S5 reference
gates. The two original references are copied from the portable S5 archive,
not inferred from a previous build directory. These are same-grid numerical
references, not physical validation or a resolution-independence claim.

All runs observe 1.5 and 1.75 m separately, all fixed required receptors, and
the entire valid ROI at each height. ROI maxima include moving pedestrian
error hotspots; full interior mass maxima cover moving volume hotspots.
Sample masks, required-point validity, global residual, interior mass/flux
and the separate top-band mass/flux are retained. The 225° condition was not
used to select the challenger. All three conditions are now method-development
data and **cannot be treated as unseen S7 validation data**.

There are eight screen workers, three held-out reference workers, 18 paired
confirmation workers, six float64 controls and eight explicit-budget workers.
Fixed-work runs have 2,000 sweeps and cadence 25, including the zero iterate.
Three confirmation repetitions alternate default/challenger order by case and
repetition. Builds/tests finish before timing; workers run with four OpenMP
threads and dynamic teams disabled. The archive records the executable,
compiler/cache identity and source-member hashes. The measured platform was
Apple Silicon macOS 15.7.1, Release `-O3`, AppleClang 17 and Homebrew OpenMP.

## Frozen comparison target

A target hit requires every condition below, on both heights where applicable:

| Check | Limit |
| --- | --- |
| Vector error / Uref, maximum across ROI and required receptors | 1e-3 |
| Vector error / Uref, p95 across ROI and required receptors | 5e-4 |
| Changed validity masks / invalid required receptors | zero |
| Interior mass maximum × 23.7 m / 5 m/s | 1e-3 |
| Interior mass RMS × 23.7 m / 5 m/s | 1e-4 |
| Completed-iterate residual maximum / initial RHS maximum | 1e-3 |
| Completed-iterate residual RMS / initial RHS RMS | 1e-4 |

Require three consecutive post-initialization checkpoints and no subsequent
failed gate in the recorded history. Charge the third checkpoint's cumulative
native time with the OpenMP team initialized. This includes model/operator
preparation, condition setup, RHS,
sweeps, all previous residual/mass checks, monitor capture and compact sample
writes. It excludes process launch, initial team creation, mutex contention,
full-volume API
finalization, NumPy output and turbulence. These are **native costs to the
specified compact outputs**, not end-to-end API speedups. The known prescribed
top-band limitation remains separately reported and is not qualified by the
interior target.

The best eligible nondefault screen factor minimizes the geometric mean of its
per-case cost ratio to 1.78. Confirmation permits the scoped opt-in only when
**every** case has a median paired ratio <=0.90 and at least two of three pairs
are faster; all references and all six precision controls must also qualify.
A failure retains 1.78. No threshold is adjusted after seeing a held-out result.
The criterion uses offline reference errors and the complete future tail;
it is deliberately not implementable as an online S7 policy.

## Measured decision

| Case | Default → 1.90 target sweeps | Median paired cost ratio | Median cost reduction |
| --- | ---: | ---: | ---: |
| Tower, 270° | 525 → 250 | 0.505 | 49.5% |
| Passages, 270° | 375 → 200 | 0.599 | 40.1% |
| Passages, 225°, held out | 400 → 200 | 0.554 | 44.6% |

All target iterations are repeatable across the three confirmation repetitions.
The held-out ratios are **1.246, 0.554 and 0.525**: the first pair is slower,
with 0.234 s for the candidate versus 0.187 s for the default. That observation
is retained, and the predeclared median/two-of-three rule still passes. Three
pairs on small cases support this restricted decision, not a latency guarantee
or a universal optimal relaxation factor.

The larger factor 1.95 is not better: screen target sweeps are 275 on both
cases, versus 250/200 for 1.90. More aggressive relaxation does not monotonically
improve cost or the late float32 residual floor.

The main cadence cannot resolve the first 25 sweeps. A separate
[eight-worker diagnostic protocol](data/solver-control-s6/transients/protocol.json)
was frozen before measuring every sweep from 0 through 25 on both screen cases
and all four factors. It cannot choose another challenger or retune the main
criterion. It vetoes an opt-in on selected-factor worker failure, nonfinite
diagnostics or residual/mass growth above 10× initial values. All eight runs
pass this finite risk check, but **early growth is real**:

| Case | 1.78 peak residual/mass maximum growth | 1.90 growth | 1.95 growth |
| --- | ---: | ---: | ---: |
| Tower | 2.42× | 2.80× | 3.06× |
| Passages | 2.30× | 2.91× | 3.56× |

Residual and interior-mass growth agree closely. S7 must allow an initialization
transient; a geometric-decay estimate from the first checkpoints is unsafe.
The unchanged diagnostic values replay under the auditor's explicit nonfinite
check; its original measurement driver is retained in `transients/driver.py`.

Default 1.78 needs substantially more work to damp the slowly decaying error
before reaching the target. Both factors ultimately encounter float32 limits:
late relative residual RMS is about 5.7–7.4e-6 for default confirmation runs,
and 8.5–11.1e-6 for 1.90. Float64 controls reach roughly 1–2e-14 and negligible
late pedestrian drift. Float32 late drift is small but nonzero, and 1.90's
final passage mass maximum is larger than 1.78's despite its earlier target hit.
The recorded tail is consistent with a precision plateau, not proof that the
remaining error is zero. S7 must reject unavailable/unstable tail estimates and
cannot use multiplier updates or stagnation alone as accuracy evidence.

The 50/150 ms budget probes return whole iterates and retain all final checks.
Only 1.90 on passages at 150 ms meets the offline three-checkpoint target;
none of the other seven does. Total native overshoot is 0.70–7.64 ms, including
fresh final diagnostics/output. These probes measure this study harness, not a
new deadline guarantee for the public controller. Public bounded accuracy
continues to be `not_assessed` in every case.

## Implementation, validation and evidence

The production solver and both canyon fixes are byte-identical to S5. Only
`tools/solver_numerics_probe.cpp` differs in the measured source snapshot: it
accepts an optional internal factor/budget, checks the study budget between
whole sweeps, and reports the actual final checkpoint. Its original invocation
and default trajectory remain available. The two default float64 reference
histories match S5 **byte for byte at all 81 checkpoints**, including sample
validity. Constructor validation and both precision kernels remain unchanged.
All six confirmation case/factor groups also reproduce their complete compact
sample histories byte for byte across three repetitions.

The method uses the existing native constructor, for example:

```cpp
SolverState<float> state(op, 1e-5, SweepOrder::RedBlack, 1.90f);
```

This is an internal study/calibration choice. All existing Python APIs still
construct the default 1.78 solver. Setup and memory ownership are unchanged:
there is no preconditioner setup, additional persistent workspace or retained
cross-condition iterate. No claim of stretched/ground/solid operator SPD has
been made. CG, Chebyshev, line preconditioning and multigrid remain optional
separately scoped acceleration candidates, not unfinished S6 requirements.

Validation: **47 native OpenMP tests passed** and **18 focused S6/existing
numerics-tool Python checks passed**. The portable audit replays all reference gates,
method selection, first-target costs, transient checks and default parity.
No full Python/serial/sanitizer suite was rerun for this tools-only stage. S5's
previously documented dataset failures and performance miss remain open.

[manifest.json](data/solver-control-s6/manifest.json) hashes the portable inputs,
full checkpoint results/logs and compact sample arrays. The independent
[verification record](data/solver-control-s6/verification.json) includes all
budget outcomes and kernel-member hashes. The measured source archive is
`3fd915c91de4dda94c56fa44c1c81f3b961e5fdf7f4f297fea1b1984615d5f63`;
its production parent is S5
`f138616b7796f20b3f66e04c2c52f01f6f27c5fcd4122bccc373caf82156adeb`.
Old S0–S5 evidence is unchanged.

Replay without compiling or relying on `build/`:

```sh
.venv/bin/python docs/data/solver-control-s6/complete_solver_s6.py \
  --audit docs/data/solver-control-s6
```

Reproduce in fresh destinations (the existing evidence is never overwritten):

```sh
.venv/bin/python tools/run_solver_method_study.py \
  --output build/solver-control-s6-rerun
.venv/bin/python tools/complete_solver_s6.py \
  --study build/solver-control-s6-rerun \
  --publish build/solver-control-s6-rerun-evidence
```

S7 should now freeze its output contract, supported scope, safeguards and finite
calibration/validation split around the recorded method. Use new held-out
geometries/directions, qualify stretched-grid and large-domain references before
including them, exercise the observed initialization growth and precision
plateaus, and measure full API costs and deadlines. Legacy convergence,
observable qualification and physical/model validation remain separate claims.

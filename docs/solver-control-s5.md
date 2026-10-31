# S5 completion: numerical consistency and measured control costs

**S5 is complete for its declared scope.** S5a's campaigns are published and
independently auditable, S5b supplies coherent diagnostics and qualified small
references, and S5c repairs the diagnosed solid-mask inconsistency. S6's
iteration-method decision is next. Adaptive numerical acceptance, large-urban
reference qualification and full task closure remain open.

The disabled-controls performance review target is **not met**: the new local
confirmation shows 11–15% higher API time than matched S3, and a selected
reverse-order check shows 12.3%. S5's exit criteria explicitly allow a measured,
documented disposition for a missed performance target. We retain the numerical
correction and controls, preserve the failing observations, and carry this cost
into S6's cost-to-quality decision. This is not labeled a performance pass or
used to weaken numerical gates.

## Completion ledger

| Gate | Result |
| --- | --- |
| Preserve/publish five existing campaigns and tolerance study | Complete: original bytes, source/build identities, protocols, driver versions, compact planes, logs and the excluded attempt are retained |
| Cadence screen and paired confirmation | Complete: six screen workers; eighteen confirmation workers including matched S3 controls; 100-sweep cadence selected |
| Thread sensitivity | Complete: actual teams 1/2/4/8, controls off/on; fields identical |
| Real cooperative deadlines | Complete: ten 0.25/0.5/1/2/5 s stops, two real zero-work errors, two exact-work field replays |
| Explain missed performance target | Complete: one six-worker reverse-order follow-up; original results retained; explicit non-pass disposition |
| Completed-iterate residual and cell diagnostics | Complete in S5b; pure, bounded storage and independently tested |
| Diagnose and repair solid-mask discrepancy | Complete in separately frozen S5c; prepared geometry, wall operator and condition eligibility agree on assessed solids |
| Qualified affordable references/cost-error histories | Two independent 500/1000/2000 triples pass; both rechecked on corrected numerics, with 81-frame histories per case |
| Compatibility and numerical differences | Historical 429 cases exact; four of twelve targeted corner cases change as expected; eight targeted controls exact; all fourteen team/backend checks exact |
| Large urban numerical accuracy | Unqualified; this remains explicit and is not a hidden S5 reference pass |
| Top-band convention | Preserved and reported separately; no boundary correction is claimed |

## Numerical correction

The two canyon routines now retain flags 0/2 instead of reclassifying prepared
solids/ground as fluid. Existing fluid model labels and protected cut-cell labels
remain available. All other parameterization writes were reviewed; the native
regression exercises all 384 supported flag-combination/direction combinations
on a small unequal-height corner, checks solid-owned initial/final faces and
wall couplings, and checks repeated solves on uniform/stretched grids in both
precisions. The same test fails against unchanged S5b.

This changes the model's condition mask and the resulting initial field/solve.
It does not add an exclusion to diagnostics. The geometry and operator were
already prepared with these cells solid; their later fluid labels were the
defect. Solver kernels, legacy tolerance, relaxation, default cadence and the
prescribed boundary convention are unchanged.

The S5c native source archive is
`sha256:f138616b7796f20b3f66e04c2c52f01f6f27c5fcd4122bccc373caf82156adeb`.
S5b and all older evidence remain unchanged.

| Core case, 2,000 sweeps | Before maximum divergence, s⁻¹ | After, s⁻¹ | Relabeled assessed solids after |
| --- | ---: | ---: | ---: |
| Downtown 225° | 3.580855 | 0.020754 | 0 |
| Downtown 315° | 3.921691 | 0.017105 | 0 |
| Courtyard 225° | 3.303573 | 0.002808 | 0 |
| Downtown 270° control | 0.016001 | 0.016001 | 0 |

All sixteen S5c diagnostic/reference workers completed under the original
30 s worker / 180 s six-worker-shard caps. Raw records preserve 500- and
2,000-sweep residuals, local/global signed and absolute flux, neighboring row
coefficients/flags, both heights and all required receptors. The large-grid
residuals still decay and do not qualify those cases. Top-band maxima remain
about 0.0455–0.0624 s⁻¹ in these core runs under the unchanged prescribed-face
convention. More iterations or looser tolerance are not presented as repairs.

The historical 429-case matrix contains no attempted solid relabeling and stays
bitwise exact. Twelve added corner cases cover both precisions, two vertical
grids and three directions. Four 225° cases change, each with recorded attempts
to overwrite prepared solids; their velocity, flags and numerical scalar
differences are enumerated. All coordinates, metadata and eight unaffected
corner cases remain exact. Counters exist only in frozen instrumented comparison
builds, not the production library. Candidate outputs remain exact across
OpenMP teams 1/2/4/8 and serial for both matrices.

## Cadence, runtime and performance disposition

The finite API follow-up contains 52 sequential workers: six cadence screen,
eighteen paired confirmation, eight thread, twelve deadline, two exact-work
replay and six selected disposition workers. There were no automatic retries or
budget increases. Source builds/tests preceded accepted measurements.

All cases use the frozen core grids, Uref=5 m/s, 225° wind and float32. Monitoring
keeps the complete ROI, 1.5/1.75 m planes, all sixteen required receptors at each
height, short/long spans, moving hotspots and sixteen summaries. Global mass and
completed-iterate residual scans are not enabled in the public controller.

The predeclared screen rule selects the smallest cadence within 3% of each
case's best API time; otherwise it minimizes the worst normalized case time.
It selected **100 sweeps**. This is a measured recommendation for the declared
scope; the public default remains 25. One screen result had much slower sweeps,
and the three-repeat confirmation also shows variance; all observations are
retained. S7 must account for fresh residual/global-check costs before choosing
its own cadence, as S5b measured approximately 16–34 ms for a residual scan and
95–180 ms for global flux on these core grids.

| 2,000-sweep median API, seconds | Matched S3 | S5 controls off | S5 bounded, cadence 100 | Monitor delta | Off versus S3 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Courtyard 225° | 3.9359 | 4.3858 | 4.8176 | +9.85% | +11.43% |
| Downtown 225° | 6.5225 | 7.4894 | 6.9702 | −6.93% | +14.82% |

All nine fields per case are identical, including full-volume/flag/grid
fingerprints. S3 carries the exact same two canyon corrections, so these timings
do not conflate the numerical fix with controller/diagnostic architecture.
The negative downtown monitor delta is timing variability, not proof that
monitoring is free or improves the solver. The original confirmation satisfies
the 10% median monitor review target on this scope, but three repetitions do not
establish a universal bound.

The selected reversed-order downtown check retains the regression: 7.1847 s
versus 6.3993 s, or +12.27%. Both float32 and float64 sweep object files are
byte-identical between the matched builds; the normalized float32 `advance`
bodies also agree. This narrows the investigation but does not establish that
all API work has identical cost or identify the remaining cause. No speculative
kernel or boundary change is bundled to obtain a passing number. S6 must use
these costs when comparing methods, and the <=5% disabled target remains an
explicit missed review target in the completion record.

Measured median process peak RSS was 519.2/516.0/530.8 MiB for matched S3 /
controls off / bounded courtyard, and 735.1/736.0/746.6 MiB for downtown. These
include Python, preparation, output and sampling; they are not summed native
allocations. Native float32 workspaces were 29,490,432 and 50,823,936 bytes.
The monitors owned 10,635,298 and 10,635,706 bytes, respectively, with the same
values across repetitions. Every bounded confirmation retained sixteen of its
21 checkpoint summaries and explicitly marked history truncation. The original
long-run RSS spread remains in the historical campaign data rather than being
replaced by one universal savings claim.

The disposition worker's original field named `api_cpu_seconds` was evaluated
after output checks and therefore measures pipeline CPU from API entry through
sampling/hashing. Original bytes are retained with this corrected scope; the
current runner labels it `pipeline_cpu_seconds`.

## Actual deadline behavior

All ten 0.25/0.5/1/2/5 s runs reached native `time_limit`, returned whole iterates
and retained `accuracy_status=not_assessed`. The courtyard completed 81/196/444/
884/2400 sweeps; downtown completed 32/115/238/545/1437. Observed positive solve
deadline overshoot ranged approximately 0.42–6.07 ms. Both 1 ns checks raised
zero-completed-work exceptions; they are error outcomes with records, not fields.
The two 0.5 s results are bitwise identical to fresh controls-disabled runs with
exactly their completed work, across velocity/flags/grid fingerprints.

Finalization and output still follow stopping. At the 5 s setting, measured API
times were about 5.14 s and 5.22 s, including prior preparation; finalization
alone cost about 35 ms and 61 ms. This remains a cooperative native solve
budget, not a hard API wall-time guarantee. Fake-clock phase tests continue to
cover deadline precedence and every boundary. Thread-sensitivity workers all
used their requested actual teams and returned identical fields.

## Portable evidence and audit

The [manifest](data/solver-control-s5/manifest.json) covers a
[logical file index](data/solver-control-s5/index.json) and content-addressed
compressed blobs. It retains all original bytes, including the five campaigns'
324 workers/216 comparisons, the tolerance study and the explicitly excluded
interrupted attempt. No historical success/failure or reference gate is rewritten.
Original 500-run and long-run high-level drivers are included under their
recorded hashes; the older driver was recovered by reversing the later CLI
additions and verifying its exact original SHA-256.

Equal original payloads share blobs. Large parity NPZ files split ZIP metadata
from compressed array payloads; concatenation reproduces the original NPZ byte
for byte. This retains complete field comparisons without duplicating them for
each backend/team. Source archives, instrumented source indexes, recipes,
CMake caches, toolchain/package identities, cache attestations, logs, compact
planes, full-volume fingerprints and variance qualifications are preserved.
Full historical volumes were never saved by the urban campaign driver; their
fingerprints remain records, while stored planes are independently replayable.

From a checkout with the published evidence and NumPy installed:

```sh
.venv/bin/python docs/data/solver-control-s5/audit.py
```

The audit checks every compressed/original hash, original fixture/run manifests,
source archive members, all 216 historical plane comparisons, ratios of medians
and medians of paired ratios separately, four reference triples and their saved
cost/error histories, complete revision difference lists and all fourteen
candidate team/backend comparisons. It also checks current-source smoke and
verified-cache reuse outcomes. No native solve or network access is needed.

Original speed/RSS findings retain their scope: local four-thread Release
float32 measurements, three repetitions and synthetic flat-ground cities.
Long-run peak-RSS variability remains visible. These are not physical,
regulatory, grid-independence or pedestrian-comfort validation results.

## Current benchmark commands and verification

The normal one-command runner now uses the published S5c source and S1a/S3
baselines with the same canyon correction. Original unmodified archives remain
selectable through explicit archive arguments for historical reproduction.

```sh
.venv/bin/python tools/run_urban_benchmarks.py --tier smoke
.venv/bin/python tools/run_urban_benchmarks.py --tier pilot
.venv/bin/python tools/run_urban_benchmarks.py --comparison controls
```

Fresh and reused-cache smoke campaigns both complete all twelve workers and
all eight baseline/candidate comparisons with exact fields. The reuse invocation
verifies and reuses both builds; no rebuild is triggered by the changed tier.
Native build caching still checks source/toolchain/ABI/package/dependency identity.

Native OpenMP checks: **47 passed**. Serial: **44 passed**. Focused ASan/UBSan:
**5 passed**. Symbol audit passes. The current focused study/urban-tool tests
pass. The full live Python run has **1,045 passed, 16 skipped and 12 failures**;
all twelve failures are the same dataset-slice tests already reproduced against
frozen S4 in S5b. No dataset code is changed by S5. These failures remain recorded
and are not relabeled as a green full-suite result.

S6 should now freeze a method using the qualified affordable references and
measured costs. Large-core fields remain unqualified until their independent
observable/residual/mass requirements are met; `converged` keeps its legacy
meaning and bounded results retain `not_assessed`.

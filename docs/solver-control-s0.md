# Solver-control S0 baseline and next-step review

S0 is complete against baseline
`bbfd20005e0bd7d7e648438a1bc8d5a9a4358a71`. Solver arithmetic, stopping rules,
storage and backend ordering are unchanged. S1 has not started. The
[interface contract](solver-control-contract.md) and the revised
[implementation plan](../SOLVER_CONTROL_REFACTOR.md) specify the next work.

## Evidence and numerical identity

The [manifest](data/solver-control-s0/manifest.json) identifies three archived
source snapshots: the original baseline, the S0 candidate and the isolated
instrumented candidate. Every snapshot contains per-file hashes. Historic local
OpenMP and float32 accuracy-budget records are preserved byte-for-byte under
`legacy/` as gzip files, with original and compressed hashes. Original
`3f18072` bridge/Python sources and their QES submodule sources are archived
separately; the old API's recorded source hashes were checked against that
revision. Existing reference archives remain unchanged and retain their hashes.

The [comparison record](data/solver-control-s0/parity.json.gz) covers **429
cases**, extended from 426 with stretched-grid float64 and two longer-budget
cases. Every array and numerical diagnostic matches the original baseline
bitwise in serial and OpenMP builds, including teams 1, 2, 4 and 8. Candidate
OpenMP team comparisons also match bitwise. The only allowed revision metadata
addition is `fp_contract`; it is an explicit S0 command-line exception.
Serial/OpenMP comparisons report 888 differing records at each team size,
consistent with their existing different sweep order. Those comparisons become
a required equality gate only after S2's reviewed ordering change.

CMake queries the configured compiler, including supplied configuration flags,
and explicitly pins the mode it reports. On this AppleClang 17 build that mode
is `on`, matching the original driver invocation. The mode is exposed as
`_qes.fp_contract` and in `metadata.versions.native_build.fp_contract`, and is
reserved under the same name in the future control record. GNU uses its own
option query; its behavior is not inferred from the Apple compiler. Other
compiler families report `compiler-default-unverified` until supported.

## Runtime profile

The [protocol](data/solver-control-s0/protocol.json) declares an Apple M4 Pro,
14 cores, Release/OpenMP, 5 m/s at 270 degrees, 0.5 m horizontal spacing and the
actual automatic 92-layer tower grid: **9,420,800 physical cells**. Automatic
grid qualification remains experimental within the closed study's scope.

All 16 workers completed under their individual 30 s limits and the 180 s
matrix cap. Workers ran sequentially, with runtime/team warmup on a small flat
case. API timers exclude imports, warmup, City creation and sampling; they
include preparation, solution, diagnostics and complete output. Builds are
outside the matrix cap. There are two independent process repetitions per
precision for both plain and instrumented 500-sweep runs, single 200-sweep
scaling observations and one 100-sweep turbulence observation per precision.
These are local observations, with limited repetition, not timing guarantees.

| 500 sweeps, four threads | Float32 | Float64 |
| --- | ---: | ---: |
| Plain API median | 5.359 s | 3.110 s |
| Instrumented API median | 5.389 s | 3.362 s |
| Instrumented sweeps median | 4.891 s | 2.874 s |
| Mean cost per sweep, from those medians | 9.782 ms | 5.749 ms |
| Python geometry/grid median | 0.0023 s | 0.0014 s |
| Wind allocation median | 0.0700 s | 0.0616 s |
| Wall/operator setup median | 0.1619 s | 0.1696 s |
| Per-solve validation median | 0.0274 s | 0.0225 s |
| Initialization median | 0.0469 s | 0.0414 s |
| RHS median | 0.0033 s | 0.0126 s |
| Final face copy/correction/mask median, summed | 0.0250 s | 0.0434 s |
| Final divergence median | 0.0353 s | 0.0345 s |
| Native centered-output extraction median | 0.0445 s | 0.0466 s |
| NumPy allocation/copy median | 0.0268 s | 0.0165 s |

Profiling does not reproduce the plain API timing exactly: instrumentation
overhead and run-to-run variation are visible, particularly in float64. Its
outputs and all numerical diagnostics nevertheless match the paired plain
runs bitwise. Use the plain timings for API comparisons, and instrumented
timings to locate costs. Timers are in the archived build only; none were added
to production solvers. Per-pass clocks run on the master after existing
worksharing barriers; pass estimates include scheduling/barrier costs.

Float32 spends approximately **85.4% of sweep time in the two update passes**,
10.2% in the separate change pass and 4.0% copying `lambda_old`. Eliminating
the last two is worthwhile, but those passes alone cannot explain the full
float32/float64 gap. Preserve expression shape and investigate compiler/vector
behavior if that gap persists after S2's low-risk changes.

| Instrumented sweep cost | Float32 | Float64 |
| --- | ---: | ---: |
| One thread, 200 sweeps | 34.870 ms | 21.833 ms |
| Two threads, 200 sweeps | 18.491 ms | 11.835 ms |
| Four threads, median of 500-sweep runs | 9.782 ms | 5.749 ms |
| Eight threads, 200 sweeps | 6.652 ms | 6.040 ms |

The four-thread measurements use a different sweep count, so this is a
per-sweep comparison rather than a matched full-API scaling experiment.
Float64 shows little benefit beyond four threads, while float32 still benefits
at eight. The older blanket claim that the kernel saturates at four threads
must therefore be restricted to the measured float64 path. No default thread
tuning is introduced.

Using 9,202,284 updated cells and modeled logical traffic of 76 B per float32
update and 96 B per float64 update gives approximately **71.5 and 153.7 GB/s**
at four threads. These are effective logical load/store rates, not measured
DRAM bandwidth. They exclude cache-line effects, write allocation and extra
boundary traffic. Hardware memory counters were not collected; bandwidth
limitation remains an engineering hypothesis rather than a demonstrated
hardware measurement.

With turbulence enabled, setup costs 0.285–0.318 s beyond wind setup; the
turbulence run itself costs 0.683–0.687 s. Native output extraction, including
turbulence fields and validity evaluation, costs **1.77–1.97 s** in these
100-sweep runs. That cost persists even if the wind solver stops sooner.

## Allocation and resident memory

These are actual numeric vector sizes from the instrumented model, including
ghosts. The records also retain capacities. They omit small object/container
overheads and distinguish allocation counts from process resident memory.

| Resident vector group | Decimal MB |
| --- | ---: |
| Wind model, including its initial/corrected faces and coefficients | 881.7 |
| Float32 solver workspace | 114.3 |
| Float64 solver workspace | 152.4 |
| Additional turbulence vectors in the measured configuration | 1027.0 |
| Wind output vectors, copied again to NumPy | 150.7 per copy |

The wind model includes 228.6 MB of coefficients, 228.6 MB of cut-cell arrays,
76.2 MB of `mixingLengths` and 232.5 MB of face velocities. With float32 solver
workspace it uses about **105.7 allocated bytes per physical cell**, consistent
with the plan's approximate 104 B estimate after ghost/boundary overhead.

Native high-water RSS at/after NumPy output is 1.22–1.56 GB for wind-only runs
and 2.57–2.70 GB with turbulence. It includes Python, imported libraries,
allocator behavior and transient copies. High-water values are cumulative and
cannot identify the current live size of a phase. The worker's top-level
`peak_rss_bytes` is sampled after hashing and may also include a temporary
full-array byte copy; use the native phase checkpoints when assessing solve
memory. No claim of measured per-array resident memory is made.

## Review of the next steps

Proceed to **S1 phase extraction only** using the frozen contract: condition
inputs include post-parameterization flags; the backend owns workspace;
`observe` is pure; `diagnose` returns fresh six-face summaries; and finalization
supplies both turbulence faces and centered output. Preserve both precisions'
expressions and both existing orders. Partition invariance and early stopping
tests are the primary new numerical tests. Stop for the required review after
S1 parity passes.

After that review, make S1a's condition-state correction a separate behavior
change with a corrected baseline. The original S0 oracle remains available.
S2 should first fuse change measurement, then compact coefficients, then remove
unused allocations and copies. The first item removes about 14% of the measured
float32 sweep cost before secondary effects; broader 2–3x estimates remain
unverified. Guard `Wall::defineWalls`' live volume-fraction access before
removing cut-cell allocation, and preserve coefficient-based divergence
arithmetic. Serial ordering changes remain their own reviewed step.

For this small-building-count wind case, geometry processing is a few
milliseconds and native preparation is a small fraction of a 500-sweep call.
Keep multi-direction orchestration optional until the kernel/control work is
complete. Turbulence setup reuse can help, but its output extraction deserves
separate measurement before claiming a large total speedup.

No adaptive accuracy policy, new reference run, relaxation change, memory
optimization, condition-state correction or solver extraction was implemented
in S0. Validation results are recorded with the completed implementation.

## Validation

| Check | Result |
| --- | --- |
| Revision parity, 429 cases per backend/team | Passed, all arrays and numerical diagnostics bitwise |
| OpenMP Python suite | 953 passed, 18 skipped |
| Serial Python suite | 971 passed |
| Release CTest, OpenMP / serial | 42 / 39 passed |
| OpenMP ASan + UBSan CTest | 42 passed |
| Compiler-mode configuration and focused study/harness tests | 15 passed |
| Native symbol audit | Passed |
| Source archive and wheel artifact checks | Passed |
| Wheel import, contraction provenance, flat solve and owned-output smoke | Passed |
| Frozen source/record audit | Passed |

Packaging used the installed Unix Makefiles backend because Ninja was absent;
no dependency or public build-default change was needed. Compiler execution was
validated on AppleClang 17; a GNU build was not available on this machine.

## Reproduction

```sh
.venv/bin/python tools/compare_native_builds.py --baseline bbfd200 \
  --thread-counts 1 2 4 8 --backend-pair --allow-added-contraction \
  --report build/solver-control-s0/parity.json
.venv/bin/python tools/profile_solver_baseline.py --machine 'Apple M4 Pro'
.venv/bin/python tools/profile_solver_baseline.py --audit
```

The profile's output and work directories must be fresh; use `--output` and
`--work-dir` for a new reproduction without touching this archive. `--plain-package`
selects a separately staged plain build when needed. The three source archives
pin the exact code used for the recorded baseline, candidate and instrumented
build; later changes to audit/report tooling do not alter those snapshots.

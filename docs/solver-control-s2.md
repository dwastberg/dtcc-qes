# S2: solver traffic, ownership and ordering

Implemented 2026-10-29. S2 removes the float32 old-iterate passes, owns and
compacts the prepared operator, allocates optional fields on use, and makes
red/black the default in both CPU builds. Public solver controls and automatic
acceptance remain future work. Implementation stops for review before S3.

## Behavior and ownership

Each float32 update stores its rounded result before measuring change. The
maximum reduction includes every updated cell; the mirrored ground ghost stays
outside the legacy norm. Float64 retains its existing change calculation.
Both precisions retain RHS and current multipliers. Diagnostic fixed-work
studies alone copy the iterate before their final sweep to preserve per-cell
`lambda_update`; production retains no previous-iterate array.

`PoissonOperator` owns its data. It checks every supplied coefficient's size,
finiteness and exact float bits against the `Wall` expressions, including the
unscaled ground/highest-layer shell. Representable operators use one mask byte
per cell and per-layer float tables; masks come from coefficients. Other finite
patterns, including negative zero, select owned explicit arrays. Production
transfers/releases all six setup vectors. Standalone divergence checks and study
probes receive the prepared operator. They retain rounded coefficient-based
area recovery, region exclusions, solid masking and expression order.

Precision-specific relaxation tables preserve the original diagonal sum and
division for the state's relaxation value. Zero-diagonal failure remains a
solve-time error. Compact/explicit dispatch happens outside RHS and sweep loops.
Native checks compare both storage paths through RHS, iterates, norms,
observations, final faces and mass diagnostics, including face masks, stretched
grids, both orders and multiple relaxation values. Ownership checks destroy
setup geometry before inspecting transferred compact and explicit operators.

Cut-cell arrays allocate at cut-cell entry; the active stair-step wall reader
uses its previous default volume fraction of one when storage is absent.
Mixing-length storage allocates at the selected local-mixing method. Both
supported methods, buildings, repeated preparation/conditions and failure
recovery are covered. S1's caller-owned finalization remains in use. NumPy
outputs retain their allocation/copy, `OWNDATA=True`, dtype, layout and lifetime
contract; removing that copy remains a separate follow-up.

## Numerical identity and serial change

The immutable corrected S1a source identity is
`sha256:6fcdfab1abe30e254721495d2fe453f9e4c7eb89be89421df29eb44663e08d76`.
For norm fusion, operator compaction and conditional allocation, **all 429
cases and 3,872 records match S1a bitwise** in serial and OpenMP teams 1/2/4/8.
The separate S1a condition-state, valid wake-free/dependency-rejection and retry
checks also pass.

Final OpenMP still matches S1a OpenMP exactly. New serial matches both candidate
OpenMP and S1a OpenMP, for both precisions and all four teams. Its comparison
with S1a serial has exactly the **888 expected differing records**, the same
complete change set as S1a serial versus OpenMP. The opt-in
`--serial-red-black-migration` policy requires full oracle equality as well as
that exact set; unit tests reject corrupted values even within expected keys.
Normal revision comparison remains strict.

Explicit lexicographic native controls remain available in either build.
Historical study drivers set `DTCC_QES_STUDY_ORDER=legacy`; frozen older workers
ignore the variable and newer workers select the archived order. New study
invocations default to red/black and accept `--lexicographic`/`--red-black`.
Precision probes follow that selection. Small bounded uniform/stretched studies
match S1a diagnostics after norm fusion (8 comparisons); final red/black and
explicit lexicographic trajectories match the respective S1a oracles in both
precisions/builds (16 comparisons). The public sampler is checked against a
current native red/black study in both builds.

Historical exact lexicographic turbulence fixtures remain immutable and are
skipped for the new default order. Their provenance audits remain active; exact
S2 wind/turbulence equality is established by the full S1a OpenMP comparison.
The frozen `finest-reference-v1` schema explicitly retains its old workspace
layout check; new checkpoints include S2 relaxation-table storage. No stopped
reference was resumed and no numerical acceptance decision was added.

## Bounded measurements

The [worker records and derived summary](data/solver-control-s2/performance-summary.json)
use the same tower, 0.5 m horizontal spacing, automatic 92 layers and 9,420,800
physical cells as S0, with Uref=5 m/s and direction 270. Every measured API run
completed exactly its 80-sweep budget; the legacy stopping rule was still used.
Both precisions, OpenMP teams 1/2/4/8, serial controls and turbulence were
measured. Each of five accepted matrices completed 28 workers under 30 s per
worker and 180 s per matrix; builds are excluded. Small unrelated solves warm
the runtime. API timings exclude imports, City creation and sampling.

Plain builds supply API time and process peak RSS. Isolated instrumented source
snapshots supply phase time and retained-vector accounting, with exact paired
output/diagnostic parity. There are two process repetitions at four threads for
wind-only runs and one elsewhere. No competing build/test workload ran during
accepted timing matrices. These are short local observations, with allocator,
clock and instrumentation variation; they establish no timing guarantee or
matched-accuracy claim. Platform/compiler/actual teams and source hashes are
recorded. The CPU model is inherited from S0's Apple M4 Pro record; direct
re-query was unavailable in the sandbox. S2 records 14 CPUs and the platform.

Float32, OpenMP four threads, wind-only medians:

| Stage | Plain API, s | Instrumented ms/sweep | Plain peak RSS, MiB | Wind/operator/workspace arrays, MiB |
| --- | ---: | ---: | ---: | ---: |
| Corrected S1a | 1.249 | 10.731 | 1564.7 | 949.8 |
| Fused norm | 1.148 | 9.393 | 1525.9 | 913.5 |
| Compact operator | 0.787 | 4.699 | 1386.9 | 704.8 |
| Conditional allocation | 0.786 | 4.723 | 1100.2 | 414.1 |
| Final S2 | 0.783 | 5.070 | 1099.2 | 414.1 |

Final float32 sweep time is **2.12× faster**,
full API time **1.59× faster**, retained
wind/operator/workspace arrays **56.4% smaller**
and peak RSS **29.8% lower** than corrected S1a.
The operator itself retains 9,666,048 bytes instead of six coefficient volumes;
float32 workspace is 76,209,408 bytes including its 23,808-byte factor table.
Output copies, model faces and Python/turbulence storage still contribute to
peak RSS. Float64 four-thread API changes from 0.992
to 0.857 s and sweep time from
7.350 to 5.263 ms.

| Precision | OpenMP threads | S1a ms/sweep | Final S2 ms/sweep |
| --- | ---: | ---: | ---: |
| float32 | 1 | 38.578 | 18.303 |
| float32 | 2 | 19.497 | 9.246 |
| float32 | 4 | 10.731 | 5.070 |
| float32 | 8 | 5.612 | 3.854 |
| float64 | 1 | 25.603 | 19.512 |
| float64 | 2 | 13.151 | 9.920 |
| float64 | 4 | 7.350 | 5.263 |
| float64 | 8 | 5.919 | 3.771 |

Four-thread logical effective rates are 65.6→118.1 GB/s for float32 and
120.4→183.9 GB/s for float64 under the declared load/store model. Cached table
reads are included in that logical model. These are **not hardware DRAM
measurements** or proof of a memory-bandwidth bottleneck. The summary preserves
byte formulas and all phases. Serial ordering changes compare equal work,
without claiming equal error. Turbulence/output costs limit API gains: its
four-thread float32 observation changes from 4.122 to 3.611 s.

An initial profiler attempt reported teams from the binding target, which lacks
`_OPENMP`. It failed and is retained under `baseline/`, excluded from all gains.
The corrected profiler reports actual teams from the core. Initial fixture and
working-directory/audit-layout failures are retained under `attempts/`; the
corrected validation logs establish the exit gates.

## Verification and reproducibility

| Check | Result |
| --- | --- |
| Release native, OpenMP / serial | 43 / 40 passed |
| ASan/UBSan native, OpenMP | 43 passed |
| Python suite, each backend | 988 passed, 16 historical-order skips |
| Packaged-wheel condition-state/build tests | 46 passed |
| Native symbol audits, all three builds | Passed |
| Wheel and source-distribution contents/evidence audit | Passed |
| Five accepted profiling matrices | Completed, paired parity passed |
| Preserved S0/S1/S1a manifests, evidence and source snapshots | Unchanged |

The [S2 manifest](data/solver-control-s2/manifest.json) hashes each step's sources,
comparison reports, accepted and rejected profiling records and validation logs.
The final reproducible source identity is:

```text
sha256:931408afbf86a578b978f17dc15b8bb9f8fdccc9522ebe86da8c6c499f13d803
```

This identifies the uncommitted workspace independently of HEAD. No commit is
claimed. The compiler/contraction-specific bitwise contract does not imply
cross-compiler equality or physical/comfort qualification. Every recorded
performance worker also agrees numerically with its S1a trajectory oracle.

Reproduce the final numerical gate from this source snapshot with:

```sh
.venv/bin/python tools/compare_native_builds.py \
  --baseline-archive docs/data/solver-control-s1a/sources.tar.gz \
  --candidate-archive docs/data/solver-control-s2/final-sources.tar.gz \
  --thread-counts 1 2 4 8 --require-backend-parity \
  --serial-red-black-migration --report build/s2-recheck.json
```

## Review before S3

S2's revised gates are satisfied. The next implementation is S3's compiled
pedestrian/receptor monitor, using pure slab observation and the existing mass
regions. Keep both condition flags and coefficient rounding, excluded boundary
bands and validity counts explicit. Check observation/sample parity and bounded
history/overhead against this S2 snapshot. Keep acceptance disabled until the
later method decision and calibration stages. NumPy copy removal and pipelined
color/slab storage remain separate measured follow-ups. Stop here before S3.

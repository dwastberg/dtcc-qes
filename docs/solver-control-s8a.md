# S8a: measured prepared-model reuse decision

S8a is complete with the public reuse API **deferred**. The existing native
runner can reuse preparation correctly, but this finite pilot did not meet
the benefit gate declared before measurement. `wind.run`, the solver,
arithmetic, defaults and S7 policy identity are unchanged.

The [portable evidence](data/solver-control-s8a/manifest.json) contains raw
workers, protocols, sources, allocation diagnostics and an independent audit.
The [audited summary](data/solver-control-s8a/summary.json) derives the decision
from the original workers rather than trusting their initial summary labels.

## Protocol and decision

Use one affordable neighbourhood with 20 rectangular buildings, four rows of
five, heights 10–22 m and 8 m passages. The flat 160 × 160 × 64 m domain
has 80 × 80 × 32 cells at 2 m. Inflow is 5 m/s at 10 m, roughness 0.1 m.
The four-direction sequence is 270°, 0°, 90°, 180°; eight directions append
315°, 45°, 135°, 225°. This is a reuse pilot, not another city-scale benchmark
or an expansion of S7's numerical/physical qualification.

There are three repetitions per sequence/mode/path, alternating fresh/reused
execution order: 24 fresh-process timing workers. Legacy uses a 500-sweep
limit and tolerance 1e-5; adaptive uses a 600-sweep limit, a 5 s cooperative
budget and pedestrian ROI/receptors at both 1.5 and 1.75 m. Workers have a
30 s subprocess deadline and request four OpenMP threads with dynamic teams
disabled. Runs are sequential, with builds and other checks outside timing.

The predeclared gate requires an eight-direction median saving of at least
10% **or** 100 ms in each mode, neither four-direction mode more than 5%
slower, and exact numerical/control parity. Both eight-direction savings
missed this gate. The threshold was not revised after seeing the results.

| Mode | Directions | Fresh median | Reused median | Saving |
| --- | ---: | ---: | ---: | ---: |
| Legacy | 4 | 371.6 ms | 344.8 ms | 26.7 ms / 7.2% |
| Legacy | 8 | 703.5 ms | 655.0 ms | 48.5 ms / 6.9% |
| Adaptive | 4 | 515.2 ms | 515.6 ms | −0.4 ms / −0.1% |
| Adaptive | 8 | 1044.5 ms | 1018.4 ms | 26.1 ms / 2.5% |

These are local three-repetition observations, not statistical confidence
intervals or a universal speed claim. Cross-mode times do not compare equal
work or accuracy: legacy reaches 500 sweeps without convergence; adaptive
accepts after 225/250 sweeps and pays for monitoring/assessment.

## What was timed

The city is already in memory. Each series includes geometry extraction,
domain planning, native preparation, condition initialization/solve, owned
NumPy output transfer, normal public metadata/result construction, linear
sampling at both pedestrian heights, and an uncompressed full-field NPZ
write with `fsync` per direction. Audit fingerprint calculation is also inside
the measured total. Imports and fixture construction are outside it. Outputs
are streamed/discarded; the command accepts only four or eight directions,
and does not accumulate full-volume results for an arbitrary series.

The process-local prototype intercepts `wind.run` preparation only: geometry
and the existing native runner are retained after the first condition. Every
condition still goes through the complete public solve/result path. No warm
start, Python stop loop or new numerical kernel is introduced. It is a
measurement tool, not an application API or thread-safe cache.

Eight-direction median phase times, in milliseconds:

| Phase | Legacy fresh/reused | Adaptive fresh/reused |
| --- | ---: | ---: |
| Geometry extraction | 7.90 / 1.10 | 7.64 / 1.13 |
| Python domain planning | 4.40 / 0.57 | 4.27 / 0.56 |
| Native preparation, including operator | 26.70 / 3.53 | 28.13 / 3.58 |
| Native solve and output transfer | 622.06 / 613.20 | 953.01 / 953.96 |
| Pedestrian sampling | 3.23 / 3.30 | 3.19 / 3.21 |
| NPZ output | 18.89 / 15.24 | 29.62 / 36.16 |

Phase medians are computed independently and need not sum to the median
total; result construction, fingerprinting and teardown also contribute.
Preparation is counted once for reuse and eight times for fresh calls.

A separate legacy-only diagnostic build measures boundary/stencil setup and
immutable operator compression/transfer. Over eight directions these cost
15.47/1.80 ms and 5.24/0.69 ms for fresh/reused respectively. They are
subphases of native preparation. This instrumented build has its own source
identity, does not assess adaptive acceptance, and contributes no primary
speed measurements. All solver kernel sources remain byte-identical.

## Memory and parity

Four isolated profiling workers record actual native object construction:
eight prepared models, operators and float workspaces become one each.
The last prepared model's enumerated flat numeric vectors occupy 7,992,668
bytes, the compact operator 261,888 bytes and workspace 1,698,048 bytes.
These are explicit owned-array counts, not a complete allocator census.

Eight separate untimed `tracemalloc` workers show almost identical traced
peak allocation for fresh/reuse: about 6.22 MB for eight legacy directions
and 15.79 MB for eight adaptive directions. These include audit records and
Python/NumPy outputs, and exclude native model/workspace allocations. The
tracer is disabled for the primary timing workers.

Eight-direction primary process peak RSS ranges are 286–301 MB fresh versus
256–277 MB reused in legacy, and 284–291 MB versus 262–269 MB in adaptive.
RSS includes imports, allocator retention, transient setup and output copies;
the observations do not establish an exact native live-memory saving.

The audit checks 216 condition solves: 144 in primary timing workers, 24 in
native profiling workers and 48 in traced-memory workers. All velocity,
classification, coordinate and sampled-plane fingerprints, diagnostics and
recorded adaptive monitor/checkpoint/assessment decisions match independent
fresh calls. Adaptive acceptance and 225/250-sweep termination reset correctly
for every direction. Only nested checkpoint `elapsed_seconds` stamps are
excluded from equality. The initial harness mistakenly compared these clocks;
its failed summary is retained alongside untouched raw workers. Correcting
the comparator required no numerical or threshold change.

The focused validation suite covers native direction/precision changes,
uniform/graded grids, both turbulence methods, failure/retry, preparation
validation, adaptive controls and concurrency, plus the new evidence/decision
checks: **38 tests pass**. It also verifies that the diagnostic instrumentation
preserves solver sources and existing native arithmetic statements. Because
no public reuse API is adopted, no new lifecycle or model-change contract is
introduced. A future API must still satisfy every lifecycle, snapshot,
ownership, preparation-change and concurrent-call requirement in S8a.

## Reproduce

With the project's dependencies, compiler, CMake and OpenMP runtime installed,
one command builds the frozen sources and reruns the 24-worker timing pilot:

```sh
.venv/bin/python docs/data/solver-control-s8a/reproduce_prepared_wind.py \
  --output build/solver-control-s8a-fresh
```

The output directory must be new. This reruns the finite experiment; timings
and the resulting adoption decision can differ on another machine. To run
the same pilot against the current installed solver without rebuilding:

```sh
.venv/bin/python tools/benchmark_prepared_wind.py \
  --kind prototype --output build/prepared-wind-pilot
```

Audit the published evidence without compiling or importing the solver:

```sh
.venv/bin/python docs/data/solver-control-s8a/audit_prepared_wind.py \
  docs/data/solver-control-s8a
```

The one-command frozen-source replay was also executed successfully: all
144 replayed condition fields/diagnostics/control decisions match the
originals exactly and preserve S7's native policy revision. Its eight-direction
savings are 62 ms / 8.6% legacy and 45 ms / 4.4% adaptive, again below the
same adoption gate. These separate confirmation results are preserved in
the evidence and do not replace the original pilot medians.

The isolated native subphase study is separately reproducible with
`tools/profile_prepared_wind.py --output build/prepared-wind-profile`.
For traced allocations, run a separate worker with `--worker --memory`,
`--mode legacy` or `adaptive`, `--count 4` or `8`, and `--kind fresh` or
`prototype`; set `OMP_NUM_THREADS=4 OMP_DYNAMIC=FALSE` before starting Python.

## Remaining work

Keep native preparation reuse available internally. Reconsider a public API
if a separately bounded larger/geometry-heavy workload or a concrete memory
constraint demonstrates sufficient benefit. Do not infer that larger cities
can be run in one oversized worker from this small pilot.

S8b comfort sensitivity remains conditional and unimplemented. S7's restricted
pedestrian scope, missing-direction/support rules and climate/model limits
still apply. S9 must explicitly close the release scope and preserve the
large-domain/top-band limitations and missed S5 disabled-controls performance
target; completing S8a does not complete all of S8 or the release roadmap.

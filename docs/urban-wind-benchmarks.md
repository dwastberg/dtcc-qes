# Urban wind benchmark suite

The suite measures the normal Python pipeline on neighbourhood-scale geometry.
It compares an archived baseline, the candidate with controls disabled, and
bounded candidate execution. Source builds and network/data acquisition happen
before timed workers. Every worker uses the same frozen geometry, domain frame,
reference wind, coefficient inputs, explicit vertical layers and model defaults.

## Cases

| Case | Buildings | Urban features | Domain / top |
| --- | ---: | --- | --- |
| Perimeter neighbourhood | 160 | Sixteen courtyard blocks, separate frontages, gates, alleys and intersecting streets; heights 15–28 m | 560 × 560 / 100 m |
| Mixed downtown | 97 | Twenty-five blocks, L-shaped offices, setbacks, central plaza and 42–72 m towers mixed with lower frontages | 560 × 560 / 160 m |
| Slab estate | 42 | Thirty-six staggered apartment slabs rotated 22°, open spaces and six low community/retail buildings | 600 × 600 / 120 m |
| Industrial/residential transition | 84 | Warehouses, service yards and offices adjoining housing frontages and taller apartment slabs | 640 × 640 / 120 m |

The frozen [neighbourhood overview](data/urban-wind-benchmarks/neighbourhoods.svg)
shows all four layouts. The [core fixtures](data/urban-wind-benchmarks/core-fixtures/protocol.json)
contain 3,606,400 / 6,272,000 / 5,490,000 / 5,529,600 cells respectively at 2 m
x/y, with both pedestrian heights supported by explicit vertical layers.
The core campaign contains 108 rows in eighteen six-worker shards.

These are deterministic synthetic morphologies. The case JSON and height-shaded
SVG maps expose every footprint, height, open-space receptor and ROI. Courtyards
are represented by separated buildings around open space, keeping footprints
hole-free under the current product geometry contract. Fixed receptors are
chosen before solving with at least 3 m footprint clearance; they are retained
even when a coarse grid gives invalid support. Samples at both 1.5 and 1.75 m
cover the native-center ROI and all fixed receptors. Rotated elongated and
L-shaped footprints exercise substantially more than isolated block flow.

Additional real-city extracts use the same `dtcc-qes-urban-case-v1` JSON schema,
with `synthetic=false`, explicit metre coordinates, origin, CRS, domain, ROI,
building IDs/vertices/positive heights and source/licensing/preprocessing
provenance. At least twenty buildings are required. `--city-case` adds a local
snapshot to the suite. Export/condition a city once, review the SVG and freeze
the input before timing; workers never fetch data. Courtyards, overlapping
parts, terrain flattening and height substitutions must be resolved explicitly
and documented in that snapshot. Synthetic defaults make the suite reproducible
without implying that downloaded or physically validated city cases exist.

## Frozen inputs and workload tiers

`fixtures` validates all geometry through the normal API and freezes float32
solver thickness operands from the current automatic planner. Every backend
then receives their identical explicit faces; generator cost is measured in a
separate preview phase. For coarse tiers the planner uses an explicit 0.2 m
minimum and a declared relaxed aspect-ratio setting to retain pedestrian support.
This is a benchmark grid setting, with no production-grid qualification.
The explicit requested top is set to the exact double sum of those frozen
thicknesses; the original planning bounds are retained. Preparation verifies
that x/y/z, physical faces and solver thicknesses remain bitwise identical to
the planner preview, including float32 accumulation roundoff.

| Tier | x/y spacing | Winds FROM | Repetitions | Iteration cap | Purpose |
| --- | ---: | --- | ---: | ---: | --- |
| smoke | 8 m | 270° | 1 | 8 | Build/run/serialization integration only; thin geometry is unresolved |
| pilot | 4 m | 270° | 3 | 500 | Initial bounded cost screening |
| core | 2 m | 225°, 270°, 315° | 3 | 500 | Realistic urban cost and direction sensitivity |
| scale | 1 m | 225°, 270°, 315° | 3 | 500 | Memory and larger-grid scaling where the explicit guard permits |

Each wind/repetition has baseline, disabled and bounded variants. The bounded
variant starts with a 5 s cooperative solve budget, checkpoint interval 25,
residual collection disabled and sixteen summaries. Iteration/time stops remain
visible. A 40-million-cell guard is explicit; an over-limit case fails planning
and is not automatically coarsened or given a larger budget. Larger studies
require a reviewed protocol, memory guard and worker envelope.

The default CPU campaign is float32/OpenMP with four requested threads (two for
smoke). Actual teams are measured by a small isolated probe appended to both
builds, outside API timing. Original numerical statements remain intact and
the instrumented sources are archived alongside their original archive IDs.
Serial builds provide a control. Float64, uniform-grid and wider thread-count
sensitivity are follow-up matrices with newly frozen protocols, avoiding a
large accidental Cartesian product in the first campaign.

## Reproduction

Run a complete campaign, including builds, frozen inputs, all sequential shards
and a final terminal report, with one command:

```sh
.venv/bin/python tools/run_urban_benchmarks.py
```

The default is the full 4 m pilot: all four neighbourhoods, three repetitions,
baseline/disabled/bounded variants, float32 and four OpenMP threads. It compares
S1a with the frozen S9 release candidate; both carry the same canyon solid-mask
correction. `--comparison controls` uses S3 with that same correction. The
[published S5 comparison identities](data/solver-control-s5/current-comparison.json)
separate these new comparisons from the preserved original S1a/S3→S4 campaigns.
See the [S5 completion report](solver-control-s5.md) for results, the missed
performance review target and remaining accuracy limitations. The
[S9 closure](solver-control-s9.md) records the final candidate, release checks
and explicit S8b deferral. Other campaigns use:

```sh
# Quick integration check: 12 workers, 8 m and eight sweeps.
.venv/bin/python tools/run_urban_benchmarks.py --tier smoke

# Realistic-resolution matrix: 108 workers, 2 m and three wind directions.
.venv/bin/python tools/run_urban_benchmarks.py --tier core

# Compare current controls against S3 with matched numerical correction.
.venv/bin/python tools/run_urban_benchmarks.py --comparison controls

# Longer equal-work comparison; allow monitored solves to reach 2,000 sweeps.
.venv/bin/python tools/run_urban_benchmarks.py --tier core \
  --iterations 2000 --solve-seconds 20
```

`--iterations` overrides the tier's iteration cap for all variants, while legacy
tolerance stopping remains active. `--solve-seconds` overrides only the bounded
variant's native solve budget. Both settings are frozen in every protocol row;
the external 30-second worker and 180-second shard limits stay unchanged. Check
actual completed sweeps before interpreting the result as equal work.

Each invocation creates a fresh directory under `build/urban-benchmarks/`, prints
that path, and saves `results.txt`, `results.json`, `campaign.json`, frozen
fixtures and all per-worker results/logs. `--output PATH` chooses a fresh output
directory. All shards run sequentially; selecting a tier explicitly schedules
the complete campaign. The worker/shard deadlines below remain in force, giving
maximum worker envelopes of six minutes for smoke, eighteen for pilot and
fifty-four for core, excluding builds, fixture preparation and report overhead.
Failed/timed-out workers remain in the final report and cause a nonzero exit.

Builds are cached separately for each source archive under
`build/urban-benchmark-cache/`. Reuse requires matching source contents, backend,
Release build recipe, compiler/CMake identity, platform/SDK, relevant environment
flags, Python executable/ABI/headers, nanobind inputs and instrumentation. The
runner also checks staged package hashes, the instrumented source archive and
the selected compiler/build-tool/OpenMP dependency files, then verifies isolated
imports and the actual native thread team. A changed or damaged entry triggers
a fresh build generation; previous generations are retained. Changes to the
lower-level reporting or fixture code alone do not invalidate native builds
unless the build recipe or instrumentation also changes. Fresh fixtures are generated for every
campaign, so existing fixture hashes need no manual maintenance.

`--rebuild` forces fresh builds; `--backend serial` selects the serial control;
`--baseline-archive` and `--candidate-archive` select other compatible frozen
sources. `--city-case FILE` adds a frozen real-city input. A lock prevents
overlapping build/timing campaigns using the same cache. A first invocation
builds its own verified cache rather than trusting an older manual build.

For individual stages and manually selected shards, use the lower-level driver:

Use the S5 bundle's matched-mask S3 archive for the immediate control-overhead
baseline; its matched-mask S1a archive measures combined storage/traffic/control
changes. The explicit S1a/S3/S4 commands below reproduce the historical campaign
sources and include any declared numerical differences when mixed with newer
sources. Earlier pre-extraction S0 needs its archived driver/adapter and a
review of condition-state/ordering changes; its old measurements are preserved.

```sh
# Freeze geometry and review the generated SVGs before launching workers.
.venv/bin/python tools/benchmark_urban_wind.py fixtures \
  --tier core --output build/urban-core

# Build the exact archives, outside benchmark clocks.
.venv/bin/python tools/benchmark_urban_wind.py builds \
  --baseline-archive docs/data/solver-control-s3/sources.tar.gz \
  --candidate-archive docs/data/solver-control-s4/sources.tar.gz \
  --output build/urban-builds

# Launch one explicitly selected shard. No next shard starts automatically.
.venv/bin/python tools/benchmark_urban_wind.py run \
  --fixtures build/urban-core --builds build/urban-builds/builds.json \
  --shard 0 --output build/urban-core-run-00

# Aggregate compatible completed shards; retain failed/missing work explicitly.
.venv/bin/python tools/benchmark_urban_wind.py aggregate \
  --runs build/urban-core-run-00 build/urban-core-run-01 \
  --output build/urban-core-summary.json
```

Each shard has at most six sequential subprocesses, 30 s per process and 180 s
total. The external limit includes imports and warmup; it is independent of the
native cooperative solve budget. Timeout, zero completed work, failure and
skipped rows remain recorded. No process may claim a usable result after being
killed. A new output directory is required for every fixture/build/run; source,
input and staged package hashes are checked. Editable installs cannot redirect
workers to live workspace modules. No competing builds/tests should run during
an accepted timing shard. The lower-level `run` command launches only one shard;
the high-level runner explicitly schedules every shard in the selected tier.

`run` and `aggregate` print a terminal summary: completed/failed worker counts,
median API and pipeline seconds, process peak RSS in MiB, completed sweep ranges
and stopping reasons. Paired comparisons show candidate/baseline API ratios
(below one is faster), equal-grid/work/full-field counts, pedestrian vector
differences divided by reference speed and validity-mask changes. Difference
columns show the largest value across paired repetitions and sampled heights;
timing ratios are medians of paired ratios. Different completed work is explicit
and field differences do not establish accuracy. The detailed JSON is retained.

Print the summary for an existing run without rerunning its workers:

```sh
.venv/bin/python tools/benchmark_urban_wind.py analyze \
  --output build/urban-core-run-00
```

`analyze` regenerates `comparisons.json` from the stored samples; use the same
driver version when preserving an existing run's manifest. Fixtures pin the
benchmark driver hashes. After updating the script, generate fixtures into a
fresh directory before launching new workers; archived inputs and results stay
unchanged and can still be analyzed or aggregated.

## What the comparisons mean

The API timer includes geometry extraction, grid planning, native preparation,
initialization, solve, mass diagnostics, optional monitoring and NumPy output.
Separate timers cover case loading/City construction, preview, pedestrian
sampling and compressed sample/hash output. The supervisor records full process
wall time; peak RSS includes imports, geometry, native arrays and output. Warmup
uses a small unrelated flat case before the pipeline timer. Dependency/build
versions, actual team, source/module identities, grid hashes and actual sweeps
are recorded. Aggregation reports raw repetitions and descriptive medians/ranges.

Baseline versus disabled execution should have identical grids, completed work,
field hashes and masks under the same trajectory contract. An iteration cap
alone does not prove equal work because tolerance stopping remains active.
Bounded execution can finish a different number of sweeps; compare it on total
cost, completion reason and measured field differences, with counts explicit.
Whole fields are hashed; compact native-center ROI planes and receptor vectors
are retained for independent offline analysis. The suite reports common valid
support, validity changes, vector p95/maximum difference divided by Uref,
speed-factor differences, peaks, mass diagnostics and receptor values.

Baseline differences are not accuracy labels. Qualified time-to-error curves
need an independently accepted compatible same-grid reference for each case,
including geometry/model/grid/condition provenance. Physical validation needs
measurements or an appropriate validated external reference as a separate
study. The first campaign can establish runtime, memory, trajectory preservation
and how budgeted fields differ from baseline. It cannot certify pedestrian
comfort or choose adaptive stopping thresholds. Spatial/domain sensitivity,
empirical branch sensitivity, near-wall support and gust/turbulence validity
remain explicit limits. S5 must also revisit S3's disabled-path timing variation
and costly continuous residual collection using this public API suite.

## Integration evidence

All twelve eight-sweep smoke workers completed, using isolated S3 and S4 builds.
All eight candidate/baseline comparisons retain identical grids, completed work,
full-field hashes and validity masks. The [smoke summary](data/urban-wind-benchmarks/smoke-summary.json)
and raw per-worker planes/logs are retained. A single coarse repetition cannot
estimate representative overhead; timing variation is visible in those records.
No realistic-resolution speedup, accuracy or comfort claim is made from smoke.
The initial failed explicit-top attempt is retained under `attempts/`; generation
now checks exact frozen-grid parity before any worker starts.

The smoke builds use the initial S4 source snapshot archived under its evidence
attempts. Final S4 changes after that snapshot affect the benchmark endpoint
freezer and its regression tests; production native and Python package sources
are identical. Both instrumented build snapshots and their original source IDs
are retained in [build provenance](data/urban-wind-benchmarks/builds/builds.json).
Use the final S4 archive for new campaigns.

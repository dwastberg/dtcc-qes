# Runner progress and ownership diagnostics

The core exposes private observations for investigating the E0 fresh-worker
memory growth and the repeated 1 m reverse-order timeout. These changes preserve
the solver equations, stopping rules and default relaxation factors. They do
not establish the cause of either observation or qualify a new numerical policy.

## Workspace replacement

Changing precision, tolerance or experimental omega releases the obsolete
workspace before constructing its replacement. A failed allocation leaves the
prepared geometry available for another solve. Preparing replacement geometry
continues to preserve the previous geometry until preparation succeeds; its
temporary overlap is required by that existing failure contract.

## Reading progress

For the private native runner, read `runner._progress` from another Python
thread while `prepare` or `solve` releases the GIL. Its separate snapshot lock
does not acquire the main native solver lock. The snapshot contains:

- Operation ID and revision, operation name, current phase and completion flag.
- Completed sweep count, updated atomically after each complete sweep.
- Last fully observed experimental checkpoint and last completed empirical stage.
- Elapsed operation and phase times, plus process-wide tracked ownership.

Phases distinguish native mutex wait, preparation, initialization,
parameterizations, workspace release/allocation, RHS, projection, checkpoint
observation, finalization, flux diagnostics, operator export, postprocessing and
binding output transfer. Failure and successful completion are terminal states.
The snapshot does not expose mutable solver arrays. Production sweeps perform
no Python callbacks and no diagnostic file I/O.

## Ownership accounting

`dtcc_qes._qes._resource_usage()` reports current and peak object counts and
bytes for selected wind-grid buffers, Poisson storage and solver workspaces.
Bytes are vector capacities, rather than estimates from grid dimensions.
`_reset_resource_peaks()` starts a profiling interval with peaks set to current
ownership; it does not reset live counts or release storage.

This is scoped accounting. It excludes building/input geometry, coordinate
arrays, separate turbulence storage, returned Python arrays and construction
temporaries. A return to the starting counts establishes release of the tracked
objects and buffers. It does not prove that every native allocation was freed,
that an allocator returned pages to the OS, or that swapping was absent.

The lifecycle extraction observes the supported `prepare`/`solve` interface.
Completed monitor checkpoints are reported by the normal solver controller;
legacy solves without monitors report checkpoint zero. This does not require
the research Session adapter, candidate relaxation factors or experimental
physics. Per-stage observations are native C++ callbacks and never enter Python
from a sweep. Returned arrays keep independent ownership if preparation is
reused or replaced, or the runner is destroyed.

Binding transfer uses the completed operation's ID, so an older result cannot
replace a newer operation's progress. A transfer exception marks that operation
failed and preserves the prepared runner for another solve.

## Isolated worker diagnostics

The research supervisor enables a Python observer which samples native progress
every 250 ms. Observations are kept separately from answer timing events and
cannot reset a deadline. For `stderr.log`, the accompanying files are:

- `stderr.progress.jsonl`: streamed progress, process ownership and timestamps.
- `stderr.traceback.log`: Python stacks requested before terminating an opted-in
  worker. This is not a native C++ stack trace.
- `stderr.diagnostic.json`: last progress, measured RSS, outcome and clock data,
  also written when the supervisor is interrupted.

The supervisor requests `SIGUSR1` only after the child confirms registration of
its traceback handler. Its fixed diagnostic grace interval follows a failed
deadline and cannot turn that answer into a pass. Final stdout records are
drained after worker exit. Both elapsed and wall-clock durations are recorded;
their difference can expose an interruption or clock adjustment, without
identifying its cause.

## Repeated-preparation measurement

Rebuild the native package explicitly after C++ edits:

```sh
uv sync --frozen --all-groups --reinstall-package dtcc-qes
```

Run either a small control or 16 Case E directions with isolated fresh/reused
workers:

```sh
uv run --no-sync python experiments/run_core_reliability.py --suite smoke --python-trace
uv run --no-sync python experiments/run_core_reliability.py --suite city \
  --output experiments/core_reliability/output/city-memory-v1
```

Each step records tracked native ownership, current/peak RSS and process major
page faults. Optional `--python-trace` records Python allocations after loading
the initial input. It can substantially slow City serialization and validation;
it is disabled by default. Fresh preparation
is explicitly released each step; reused preparation is released after the
sweep. Samples before and after garbage collection distinguish release timing.
Python-traced memory includes retained measurement rows and caches.

These are 20-sweep memory diagnostics with progress and optional tracing. Their elapsed times
cannot qualify E0a's production speedup. Source/native identities prevent mixing
implementations; use a new output directory for a subsequent run. Archived P0
and SOR reports from earlier binaries remain historical evidence and must be
requalified before use as gates for the changed build.

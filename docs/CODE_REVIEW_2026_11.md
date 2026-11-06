# Main source review and cleanup

Review baseline: `2f1911a` (November 2026). Scope covers the Python package,
bindings, native bridge, solver and vendored CPU core, plus their build graph,
tests and validation callers. Historical evidence and raw research files outside
`src/` are retained as audit inputs.

## Findings addressed

| Finding | Change |
| --- | --- |
| Unreachable cut-cell construction used a helper pointer that was never initialized. Cut-cell storage and wall reconciliation remained compiled despite the stair-step-only bridge. | Removed cut-building/cell/edge helpers, their storage, setup branches and turbulence wall hooks. Removed redundant wall-neighbor writes. Retained stair-step coefficients and operation order. |
| OptiX had no enabled backend or vendored implementation, but its mixing, mesh, BVH and ray helpers still compiled. | Removed the backend and its exclusive utility dependency tree. Unsupported mixing codes continue to fail before allocation. |
| Private canyon arguments retained canopy, wake, ordering, checkpoint, target and export experiments with no implementation. Some ancillary arguments were silently ignored. | Replaced the broad option structure with `CanyonOptions`/`CanyonData`. The binding accepts only implemented canyon controls; removed keywords now fail with `TypeError`, even at their old defaults. |
| Unused device methods, canopy virtuals, matrix inverse, fields and disabled design sketches obscured the core interface. | Removed declarations and implementations after checking source, native tests and tool references. |
| Runner cleanup was duplicated between its scope guard and exception handlers; a private phase enum was written but never read. | Kept the scope guard as the cleanup owner and the existing synchronized public progress mechanism. |
| Six standalone canyon helper tests did not inherit ASan/UBSan options. | Linked their build settings to `qesbuild`, so ordinary sanitizer builds instrument them automatically. |
| Four specification readers duplicated strict schema-version checks. | Shared `versioned_mapping`, preserving type-specific construction and error text. |
| Sample classes duplicated stress validity/statistics logic; turbulence configuration imported the result module for numeric helpers. | Shared sample statistics and moved covariance/velocity helpers to the NumPy-only `_statistics` module. |
| `_solve_prepared` combined execution, failure decisions and result assembly; turbulence settings were repeated in three callers. | Extracted result assembly and one native-turbulence adapter, used by execution, preflight and canyon validation. |

The private result model identity is now `protected-canyon-v1`, replacing the
obsolete E0 campaign label. Canyon diagnostic schemas and scientific formulas
are unchanged. Public parameters, defaults and result dataclass fields are
preserved.

## Deliberately retained

- Protected canyon options remain private, active and covered by lifecycle,
  roof/W protection and archived-field checks. Their physical accuracy has not
  been promoted.
- `StreetCanyonModified` serves both the integrated overlays and native
  ring/exposure checks. Inherited non-local mixing is callable through the core
  configuration; the public bridge continues to disable it.
- Explicit/automatic grids, measured/turning profiles and monitoring are active
  features with tests and documented qualification limits. An experimental label
  alone is not evidence of dead code.
- Float32/float64 solver loops, independent audit oracles, plane/probe sampling,
  and footprint geometry paths retain distinctions in rounding, support or
  validation semantics. Combining these would risk numerical or coverage changes.
- Frozen study tools and `docs/data` remain outside the runtime source. Their
  snapshots are immutable reproducibility inputs, including the earlier code.

The review used build/dependency tracing, source-wide identifier/reference and
Python AST scans, focused inspection of lifecycle, geometry, sampling and solver
boundaries, and regression comparisons. Static scans are evidence for specific
removals, not a proof that every callable branch will be used by every client.

## Validation

Evidence is recorded under `build/code-review-20261106/`. The installed project
extension is preserved; tests use explicit isolated packages with editable import
redirects disabled. Numerical comparisons permit the declared source identity/qualification
transition and validated elapsed-time metadata. The combined comparator also
requires an explicit `--monitor-storage-delta -56` for this build: independent
C++ layout probes measure `sizeof(Domain)` as 208 → 152 and `sizeof(Monitor)`
as 720 → 664 bytes. This accounts for two removed empty vector members and a
redundant reference. Only `monitor_bytes` receives that exact adjustment; counts,
arrays, decisions and all other metadata remain strict. The raw comparison that
first identified this storage change is retained. Memory guards continue to use
actual owned storage, including the smaller object.

Completed source/build gates:

- 56 OpenMP and 53 serial native tests pass, with symbol audits.
- 53 Debug ASan/UBSan tests pass, including all six directly instrumented canyon
  helpers. LeakSanitizer is unavailable in this macOS run (`detect_leaks=0`).
- The 429-case matrix matches exactly in 12 comparisons, with 4,774 records per
  comparison, covering OpenMP teams 1/2/4/8 and serial execution.
- Six protected-canyon lifecycle attempts pass 99 checks against the archived
  fields, including failure recovery and complete W/roof protection.
- All 24 frozen S7 policy workers preserve fields and numerical decisions.
- All 27 non-adaptive and four adaptive combined entries match, with the declared
  56-byte storage accounting change.
- Warning-strict Python suites: **1,974 passed, 16 historical skips** for each
  backend (OpenMP 147.00 s; serial 156.27 s).
- Package source decreases from 131 to 108 Python/C++ files and from 23,166 to
  18,191 lines, a net reduction of 4,975 lines including obsolete declarations,
  comments and scaffolding.

The initial native builds caught and resolved a dangling comment during header
cleanup and a test still assigning a removed option. The first canyon archive
check used an incorrect archive directory; the corrected driver passes against
`attempt-004/qualification`. These were build/driver errors, not numerical
failures. The initial strict combined comparison identified the storage change
above; its output and the independent layout measurements are preserved.

The isolated source distribution and wheel pass source-closure, license and
artifact checks. The installed-target wheel accepts the qualified policy, passes
runtime ownership/precision contracts and all 38 canyon/lifecycle tests, and
contains no failure-injection hook. The project environment is unchanged.

Four counterbalanced baseline/wheel cost rounds retain every observation (five
measurements after warmup per worker). Median-of-worker-medians times are:

| Operation | Baseline | Cleanup wheel |
| --- | ---: | ---: |
| Wind only | 5.262 ms | 4.870 ms |
| Combined | 25.866 ms | 25.793 ms |
| Export | 27.150 ms | 26.681 ms |

All pass the existing joint regression threshold of more than 10% and 0.01 s.
These short local checks support absence of a material regression, not a speedup
claim. Requested work, iteration counts and decisions match.

After these gates passed, the production qualification header was advanced from
`660544978f520df395dbc0b29469ea98a82def3753309982f10e0497c64648a8` to
`0065015d928341ecaaefd10728560b683c1e0630175599d554ebe6a6ad3188d8`.
Qualification retains the existing AppleClang 17.0.0.17000404 Release,
contraction-on scope and frozen policy limits. The complete physical AIJ campaign
was not rerun for this cleanup; its earlier evidence remains unchanged.

Final artifacts rebuilt from the promoted main source are recorded separately in
`promoted-artifact-gates.json` and `promoted-runtime.json`. Both pass. The final
wheel passes its qualified-policy/runtime smoke checks and all 38 warning-strict
canyon/lifecycle tests. All 416 packaged source/test/tool/validation files match
the main working tree; the qualification header is the only source change since
the full suites. Final report wording was completed after the artifact snapshot.
The installed project extension remains byte-identical to its pre-review copy.

`final-review.json` indexes the local gate reports and final artifact checksums.
The implementation is recorded in focused native-cleanup, Python-refactor,
validation and qualification commits on `main`.

## CPU-only follow-up

An explicit follow-up audit found no CUDA/GPU implementation, dormant device
hooks or build options in the current runtime source. The earlier cleanup had
already removed the OptiX utilities and unused device declarations. The built
extension links only OpenMP, the C++ runtime and the system library on this macOS
build; its undefined symbols contain no GPU API references.

`tests/test_cpu_only.py` now checks the runtime source and build configuration.
The artifact checker rejects device files and GPU code/build hooks in packaged
runtime sources, including disabled branches and offloading pragmas. Its tests
inject a device payload into a wheel and a device build hook into an sdist to
verify rejection. The default native symbol audit now also rejects GPU API
dependencies. These checks change tests/tools only; the qualified native identity
and runtime implementation are unchanged.

The `QES-Public` submodule is an upstream reference and still contains GPU code.
It is excluded from both the build and the sdist. Historical study snapshots are
preserved as immutable evidence outside the runtime source; they can describe or
contain older GPU code. This audit does not delete upstream reference history.

Validation: 66 focused tests pass with warnings treated as errors. The updated
artifact checker passes against the cleanup wheel and sdist; the core archive,
bridge-object and wheel symbol audits pass with GPU checks enabled. The new
test/tool checks postdate those artifacts, whose runtime sources are unchanged.
Commands, results and dependency output are recorded in
`build/code-review-20261106/cpu-only-review.json` and its referenced logs.

# Physics integration qualification

## Selective integration of sampling and diagnostics — 2026-11-08

Numerical qualification, applicable tests and directed memory review have passed.
Final distribution and merge checkpoints are recorded in the
[scope manifest](data/ready-integration/scope.json).
The target is main `f17db8ee504b2961b55a4f66f85bbbaa261ae142`.

The selected changes add sampling support/provenance, fixed-population
comparisons, actual imported native identities, opt-in turbulence checkpoints,
bounded read-only construction traces, and internal physical geometry and
finite-face integration helpers. They preserve the supported physical defaults.
The incoming-energy and covariance prototypes, physical-pairs V1/V2 runtime
application and reference-sampling policy remain on the research branch.

The isolated candidate uses native qualification identity
`4b2d7e381dce204fbbec240d8ff26bcd3a3d432abf79f30b3accb31c40137de7`,
with AppleClang 17.0.0.17000404, Release arithmetic and contraction on. The
production qualification header matches the tested isolated candidate. Runtime source is
frozen at `a131891`; `4c813fc` adds the strict disabled-monitor compatibility
gate and its rejection tests.

### Accuracy and performance against actual main

The fresh matrix contains 74 conditions at 1 m and 2 m: A, B, three D directions,
and sixteen E directions before and after redevelopment at each resolution.
All 148 workers completed. Every existing probe value, plane array, validity
mask, grid/profile value and numerical diagnostic matches exactly; the 15
measured comparisons at each resolution also have identical scores and coverage.
Only declared diagnostic fields were added to the records.

These are fixed-work regression results. Neither implementation reports
legacy tolerance convergence in any of the 74 conditions. The integration
therefore establishes no improvement in physical accuracy, convergence, or
pedestrian wind comfort acceptance. It preserves the existing answers while
making subsequent investigations more reliable.

The alternating paired runs used four OpenMP threads and one BLAS thread.
Times below are medians of the recorded wind workflow, in seconds; A/B groups
have one condition each. No group exceeds the declared joint review threshold
of 10% and 0.01 seconds. These observations support compatibility and do not
establish a speedup.

| Case/grid | Conditions | Main (s) | Candidate (s) | Change |
| --- | ---: | ---: | ---: | ---: |
| A-2m | 1 | 1.356 | 1.411 | +4.07% |
| B-2m | 1 | 1.479 | 1.451 | -1.89% |
| D-2m | 3 | 3.919 | 3.964 | +1.16% |
| E-2m | 32 | 7.457 | 7.455 | -0.03% |
| A-1m | 1 | 23.718 | 23.882 | +0.69% |
| B-1m | 1 | 25.894 | 26.161 | +1.03% |
| D-1m | 3 | 63.077 | 65.227 | +3.41% |
| E-1m | 32 | 48.861 | 49.647 | +1.61% |

The initial RSS readings flagged A at 1 m (+19.0%), B at 1 m (+13.4%), and two
E-before directions (ENE +12.3%, WSW +15.5%). A directed 16-worker review did not
reproduce these increases: candidate/main median RSS changed by -1.8% for A and
-0.3% for B across three repeats per implementation; the E repeats changed by
-0.7% and +0.05%. Complete returned fields, their sizes and tracked native
ownership agree. During active native/output phases, the in-use malloc-zone
ratios ranged from 0.980 to 1.011 and reserved-space ratios from 0.962 to 1.016.

The evidence supports accepting the integration without a memory implementation
change. System compression and allocator/residency variability are consistent
with the unstable initial readings, but the exact OS cause is not established.
Native counters and malloc statistics do not cover all process memory. Import
and cleanup allocator retention varies; no portable memory bound or reduction
is claimed. See the [memory assessment](data/ready-integration/memory-assessment.json).
The separate three-round small-workload cost comparison also passes its original
thresholds in wind-only, combined and export categories. No individual full-matrix
timing exceeded the material review threshold; their ratios ranged 0.936–1.057.

### Completed release checks

- All 429 cases match across main/candidate OpenMP 1/2/4/8-thread and serial
  builds: 12 comparisons, 4,774 records each, zero numerical differences.
- All 31 feature-intersection cases and 436 arrays match. Corruption controls
  confirm that changed acceptance and undeclared monitor/storage changes fail.
- All 24 frozen S7 policy workers preserve fields, decisions and histories.
- Python/validation testing covers 2,054 passing tests on the installed wheel
  and serial package, combining the full suite with the 34 native-worker tests
  rerun with explicit executable paths. The direct OpenMP coverage has the same
  total, including five separately executed compatibility guard tests. Sixteen
  archived fixtures require historical ordering/toolchains and remain excluded.
- Native CTest passes 58/58 on OpenMP, 55/55 on serial and 55/55 under Debug
  ASan/UBSan. Eighteen Python trace/monitor checks also pass with sanitizers.
  Leak detection is disabled for these macOS sanitizer runs. CPU-only symbol
  audits pass for all three builds.
- The qualification sdist and wheel audits, isolated installed-wheel smoke,
  full Python suite and 429-case wheel/direct-build parity comparison pass.
  The final source distribution and installed wheel use the same checks; their
  hashes and results are recorded separately from the distribution files.

The declared monitor layout change adds 160 inline bytes per allocated receptor
record, including when turbulence diagnostics are disabled. Existing monitor
capacity accounting includes those bytes. The record metadata adds
`turbulence=False`; the compatibility checker requires an explicit option to
permit that addition and rejects enabling or corrupting it. No new physical
policy is qualified by either exception.

Evidence: [scope and remaining gates](data/ready-integration/scope.json),
[complete AIJ comparison](data/ready-integration/full-comparison.json),
[native integration tests](data/ready-integration/native-integration-tests.json),
[test coverage](data/ready-integration/test-coverage.json), and
[source audit](data/ready-integration/source-audit.json).
Artifact identities and durable raw-evidence retrieval are recorded in the
[release evidence index](data/ready-integration/release-artifacts.json).

## Previous main qualification

The supported legacy defaults are preserved. The protected canyon models remain
private experiments; integration does not establish an improvement in physical
accuracy. The existing pedestrian-v1 solver policy is requalified for the native
source/arithmetic identity below, within its unchanged profile, precision,
geometry and thread-team scope.

`0065015d928341ecaaefd10728560b683c1e0630175599d554ebe6a6ad3188d8`

This identity uses AppleClang 17.0.0.17000404, Release arithmetic and contraction
on. Other source/arithmetic identities follow the existing
[requalification procedure](solver-control-requalification.md).

The identity above includes the November source cleanup; its fresh compatibility,
sanitizer, packaging and runtime evidence is recorded in the
[main source review](CODE_REVIEW_2026_11.md). The physical AIJ campaign and release
checks below describe the earlier integration at
`660544978f520df395dbc0b29469ea98a82def3753309982f10e0497c64648a8`; they remain historical evidence.
The cleanup changes no scientific formulas or public defaults.

## Included changes

The clean validation adapters retain canonical probes/stages, shared coverage,
regional diagnostics and reproducible evidence. Controller/sampler extraction
keeps the scientific masks and formulas unchanged. Runner scope cleanup,
workspace replacement, owned outputs, resource accounting and progress snapshots
have standalone coverage. Resource accounting describes tracked ownership rather
than complete process RSS.

The private `legacy`, `horizontal_reference_v1` and `joined_v1` selectors retain
conservative preflight, finite helpers, the original join specification and the
`physical-and-voxel-union-v1` roof protection. Overlays follow the complete legacy
canyon pass; complete W and both roof bands remain protected at initialization.
Unsupported geometry/profiles fall back to legacy. Scoped cleanup permits safe
geometry reuse after success and exceptions. Full diagnostics are opt-in.

Public `Parameterizations.street_canyon` remains 0–1. The private bridge requires
explicit legacy solver control and rejects stacked canopy/wake/stopping
prototypes. Its explicit turbulence allowance covers the original one-way
height-based calculation. Failure injection defaults off and changes native
identity when enabled. See [private validation usage](../validation/CANYON_EXPERIMENT.md).

## Compatibility and physical evidence

The complete 37-condition AIJ matrix uses 74 fresh matched fixed-work answers.
Canonical records/planes, masks, diagnostics, complete velocity/flags/stress/W
hashes and contributor stages exactly reproduce the post-fix archive. Independent
record-only checks reproduce all 15 paired quantities and shared coverage.

Only D 0 degrees activates: 34 buildings and 59,840 changed faces. The other 36
conditions retain bitwise legacy velocity/stress parity. Roof/W and mass guards
pass. D split-fibre MAE remains 0.1704606100 to 0.1770390175 (+3.86%); pooled
thermistor K and scalar-proxy MAE remain +2.29% and +2.54%. This supports regression
coverage, not physical promotion or tolerance-converged accuracy.

## Release checks

- All 429 ordinary cases agree exactly against main at 1/2/4/8 OpenMP threads
  and serial; 4,774 stored records per comparison, 12 comparisons.
- All 27 non-adaptive and four adaptive combined-baseline entries match.
- All 24 frozen S7 policy workers match fields, diagnostics and numerical decisions.
- Full warning-strict suites pass on qualified OpenMP and serial packages:
  1,952 passed and 16 historical toolchain/order skips each.
- The unchanged C source has 56 OpenMP, 53 serial and 53 Debug ASan/UBSan native
  checks passing; six standalone helpers also pass explicitly instrumented checks.
  Symbol audits pass. Six-attempt canyon qualification passes 99 checks.
- Sdist/wheel source, license and immutable evidence audits pass. The actual
  installed-target wheel accepts the qualified policy, preserves public runtime
  contracts and passes 24 canyon/lifecycle checks. Its failure hook is absent.

The focused cost review preserves all observations. A three-round balanced
wheel-to-main comparison meets the unchanged joint 10% and 0.01 s thresholds in
all three categories. An extra direct-build diagnostic retains a flagged aggregate
combined-operation contrast: two rounds were faster and one had a large spike.
Initial failed unpaired measurements and system-load observations are retained;
these timings establish no speedup claim.

Large local integration evidence, build identities and artifact checksums are
indexed separately from the immutable historical solver studies. No stopped
scientific campaign was reopened or its attempt allowance replenished. The AIJ
workers used four native threads and one BLAS thread, recorded RSS and no research
memory cap. Declared deadlines and structural index safeguards remain.

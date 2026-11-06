# Integrating the physics experiment changes

Status: changesets A–D, the complete AIJ comparison and release requalification
are complete and the implementation is committed to `main`, 2026-11-06.
The six implementation commits reproduce the exact qualified source tree.
Excluded research sources are preserved in a named, verified Git stash; large
local evidence still needs durable archival before publication. The installed
native module has not been replaced.

C preserves the protected private canyon implementation and reproduces its
archived qualification, nonuniform roof and D 0° answers. The full Python and
native suites pass on the isolated candidate; ordinary legacy compatibility is
exact. See the C results below and the small [progress index](data/physics-integration/progress.json).

Integrate the reusable validation tools, runner reliability changes and protected
experimental canyon implementation. Preserve the supported legacy physical
defaults. Keep `horizontal_reference_v1` and `joined_v1` private and explicitly
experimental. Integrating their code establishes maintainability and regression
coverage; it does not promote their physical accuracy.

Evidence: [screening history](../JOINT_PHYSICS_SCREENING_PLAN.md),
[roof correction](../experiments/joint_screen/roof_fix/README.md), and
[complete updated AIJ comparison](../experiments/joint_screen/canyon_validation/aij-002/CONCLUSIONS.md).

**1. Freeze the integration scope and preserve the working tree**

Create an isolated integration checkout from the actual target revision. Record
that revision and the current working-tree source manifest before extracting
changes. Preserve all existing tracked and untracked work. The dirty tree mixes
earlier numerical, wake, validation and canyon experiments; it is not one patch
that can safely be included wholesale.

Create a file/hunk inventory assigning each change to one of the changesets
below, an explicit prerequisite, or deferred research. Trace dependencies through
`bindings.cpp`, `wind_runner.cpp`, `WINDSGeneralData.*`, `experiment_types.h` and
the private Python session adapter. Extract the minimum common experiment bridge
needed by the retained features. Do not import canopy or wake-composition models
merely because they currently share these files. Existing supported behavior on
the target revision must be preserved.

Record three distinct references: the target qualified release, the current
installed baseline, and experimental build-008. Their identities are different.
Use the qualified release for release-policy compatibility, historical AIJ
records for baseline predictions, and build-008 archives for experimental
behavior. Declare exact identity differences rather than accepting arbitrary
metadata differences.

Deliverable: a scope manifest listing source hashes, selected hunks, dependencies,
reference artifacts and exclusions. This is the first implementation task.

**2. Changeset A: validation and reproducible evidence**

Include the A/B data adapters and comparisons, canonical stage/probe sampling,
shared-coverage comparisons, regional and reversal diagnostics, source/binary
identity checks, and the bounded worker/reporting machinery used by the canyon
validation. Preserve raw mean-vector quantities separately from turbulence-based
scalar proxies. Retain uncertainty about inferred component conventions.

Keep activation and fallback reporting beside accuracy metrics. Inactive cases
are regression checks, not evidence of improved physics. Record fixed-work and
tolerance-converged results distinctly. Keep failed/timed-out attempts and
immutable baseline records; report errors must not erase worker evidence or
replenish attempts.

Extract reusable code from campaign-specific scripts where necessary, preserving
canonical interpolation and measurement masks. Unit tests must run from a clean
checkout without archived native binaries, `/private/tmp` paths or unrelated
research packages. Give integration campaigns fresh manifests and output roots;
do not reuse the stopped EPA campaign's attempt budget.

Archive policy: version small specifications, scripts, tests, concise reports
and artifact manifests. Keep large fields, binaries and source tarballs in a
durable evidence location with hashes and retrieval instructions before relying
on them for release review. Audit data availability/licensing before committing
reference datasets. Exclude generated caches and `.DS_Store` files. Verify that
sdist tests can resolve every packaged helper and fixture; explicitly separate
external-data integration tests from ordinary unit tests.

Gate: existing parser, paired-coverage, identity, immutable-attempt and reporting
tests pass. Recompute the archived comparison without new native solves and
reproduce the recorded metrics and coverage. Useful starting suites are
`validation/tests/test_case_ab.py`, `tests/test_canyon_aij.py`,
`tests/test_experiment_identity.py`, and the controller tests in
`tests/test_canyon_validation.py`.

**3. Changeset B: runner lifecycle and lightweight diagnostics**

Include scope-based cleanup of temporary solve state, release of obsolete solver
workspaces before replacement, progress snapshots and tracked resource ownership.
Keep progress independent of the main solver lock; observers must not alter
stopping decisions or extend deadlines. Preserve prepared geometry after failed
replacement preparation and preserve ownership of returned arrays.

Keep full fields, per-face write traces and expensive stage captures opt-in.
Ordinary legacy calls must not allocate canyon snapshots. Resource accounting
must continue to describe its coverage rather than claiming to measure all RSS
or to prove absence of every leak. Keep experiment dependencies out of runtime
requirements.

Gate: lifecycle, exception, precision-switch, array ownership and concurrent
progress tests pass, including `tests/test_runner_observability.py`. Default
fields, masks, numerical work and stopping decisions match their reference.
Run the repository's applicable cost checks; diagnose instrumentation overhead
without claiming a speedup from the audited AIJ run times.

**4. Changeset C: protected, private canyon models**

Include the typed `legacy`, `horizontal_reference_v1` and `joined_v1` selectors;
geometry preflight; finite core/wedge helpers; frozen join; physical-and-voxel
roof protection; independent roof/W audits; activation and fallback counters;
and optional write provenance. Retain the original join specification hash and
the separate `physical-and-voxel-union-v1` protection revision.

Preserve these contracts:

- Run the complete legacy canyon pass before an eligible horizontal overlay.
- Leave W initialization and both protected roof bands unchanged.
- Reject unsupported, ambiguous or overlapping supports before overlay writes;
  use documented legacy fallback for unsupported geometry or incident profiles.
- Keep public `Parameterizations.street_canyon` restricted to 0–1. The private
  experimental bridge requires explicit legacy solver control and rejects
  unsupported candidate combinations. Its optional turbulence allowance covers
  only the already-tested standard one-way height-based calculation.
- Clear selectors, temporary pointers, incident profiles, counters and traces
  after success and exceptions. A reused legacy solve must reproduce a fresh one.
- Keep deliberate failure injection confined to validation builds. Include the
  hook configuration in native identity; ordinary distributions have it off.

Organize the existing implementation into maintainable helpers without changing
equations, coefficients, support or evaluation order as part of cleanup. Keep
independent audits independent of the writer's eligibility decisions. Avoid
generalizing the conservative roof-band union to unrelated parameterizations.

Gate: compiled join/roof tests, geometry and audit positive controls, public
input/default tests and private configuration tests pass. Validate active
aligned geometry, oblique fallback, calm/unsupported profiles, ambiguous support,
both signs of physical/voxel roof displacement on nonuniform grids, and reuse
after exceptions. Reuse existing fixtures; add tests only for uncovered contracts.
Run the established six-attempt qualification block on a hook-enabled build,
then verify normal behavior on the hook-disabled release candidate. Make test
collection explicit so frozen source archives are not collected as live tests.

**5. Freeze the combined candidate and run integration acceptance once**

After A–C pass focused checks, freeze their combined source and dependency epoch.
Build isolated Release OpenMP and serial packages plus the sanitizer/test builds
required by the repository. Keep the user's installed module intact. Verify
import paths and hashes before and after execution.

On the hook-disabled OpenMP candidate, repeat the existing complete AIJ matrix:
37 conditions, 74 fresh legacy/joined answers. Use A/B at 1 m and 6,000 sweeps;
D at three 2 m directions and E before/after at sixteen 2 m directions with
2,000 sweeps; retain the existing float32 tolerance, measured inflow, geometry,
probe masks and standard turbulence. Preserve the existing worker deadlines
(A/B 180 s, D 60 s, E 120 s), four native threads, one BLAS thread and sequential
workers. Record RSS with no memory cap. Structural index limits remain; absence
of a research memory cap does not remove public API resource safeguards.

Require the following against the archived post-fix `aij-002` evidence:

| Acceptance check | Required result |
| --- | --- |
| Legacy predictions | Exact canonical samples, planes, masks and numerical diagnostics; whole velocity/stress parity where archived |
| Joined predictions | Reproduce the post-fix model, including D 0° activation and its known accuracy regressions |
| Activation | Same supported cases and fallback reasons; 36 inactive conditions retain parity |
| Roof and W | Zero physical-roof and voxel-roof changes; complete preprojection W equals matched legacy |
| Sampling and conservation | Same eligible observations and sampling; all existing finite, solid/interior/top/flux checks pass |
| Provenance | Complete frozen source/build/input identities and retained outcomes; only explicitly declared metadata changes |

These are compatibility gates, not new physical promotion gates. Do not tune the
candidate to make D improve during integration. If extraction changes numerical
behavior, stop, identify the cause and restore parity or declare a separately
reviewed numerical change before accepting it. A new source epoch invalidates
affected evidence; rerun only the checks it invalidates and account for attempts.

This stage does not resume EPA V1/refinement/transfer, test new wake physics or
repeat resolution/inflow sweeps. Historical fixed-work AIJ answers remain
fixed-work comparisons and do not establish tolerance convergence.

**6. Changeset D: qualify and package the exact supported release**

Native edits change solver-policy identity even if legacy fields are unchanged.
Apply [the existing requalification procedure](solver-control-requalification.md)
to the final hook-disabled source, rather than copying an old qualification hash.
The hook-enabled experimental build cannot establish distributable qualification.

Run the required native CTest/symbol and sanitizer checks, serial/OpenMP and
thread-count comparisons, combined-baseline cases, all 24 frozen policy workers,
and full warning-strict Python tests against the intended isolated packages.
The release procedure's thread matrix is separate from the four-thread AIJ
experiment setting. Scope any identity exceptions to the exact declared pair;
numerical decisions and acceptance histories must match.

Stage the new qualification identity only in an isolated copy until those gates
pass. Build an sdist and a wheel from it, verify artifacts and installed-wheel
runtime behavior, then promote the qualification identity and repeat the required
final artifact checks. Experimental canyon calls remain outside adaptive
pedestrian-policy qualification even when the normal legacy path is requalified.

If requalification fails, the combined native candidate is not release-ready.
Validation-only work can still be integrated independently. Record the failing
gate; do not weaken policy thresholds or silently ship a loss of existing
adaptive support. Revert a dependent changeset in the integration checkout if
needed, preserve its evidence and regenerate qualification for the resulting
source. Never reset or discard the user's original working tree.

Update the current canyon README, which still leads with the superseded roof
failure, to point to the successful protection fix and latest accuracy results.
Update supported/private API documentation and release notes. Preserve historical
reports verbatim. Provide a short evidence index distinguishing current release
qualification, experimental engineering checks and unresolved physical accuracy.

**Deferred changes and follow-up boundaries**

| Item | Integration decision |
| --- | --- |
| Wall-distance mixing length | Retain the existing explicit option and document its measured tradeoffs; no default change or new model port |
| Stale rooftop incident lookup | Separate follow-up patch: prove the current-face/layer reference independently, retain existing wake coupling, then run focused regression checks before deciding whether to include it |
| Roof-only vortex forcing and wake decoupling | Preserve experimental evidence; city boundary failure prevents general adoption |
| Coupled canyon/W forcing, roof wedges, wholesale lateral removal | Preserve reports and reproducibility; do not add supported alternatives |
| E3v vertical diffusion | Keep the specification/formula tests; native implementation and physical qualification are separate work |
| Other canopy, wake-composition and momentum prototypes | Exclude from this integration unless already present on the target; shared infrastructure does not qualify their physics |

The rooftop follow-up must isolate the lookup correction from the two-change
roof-only experiment. Freeze its affected configurations and criteria before
new solves. It is not a dependency of A–D and should not delay their completion.

**Completion and review order**

Prepare separate reviewable changesets in order A → B → C → D, with dependencies
and exclusions explicit. A can land independently; B/C may be reviewed in a
stack but the combined native update reaches the supported main release only
after D passes. No commit, merge or publication is performed by writing this plan.

Integration is complete when a clean checkout builds and tests without scratch
dependencies; normal legacy behavior and qualification are preserved; private
canyon behavior reproduces the archived post-fix results; captures and failure
hooks have the intended defaults; release artifacts pass existing checks; and
the evidence index explains both the retained benefits and the known accuracy
failures. No public physical default changes are part of completion.

**Execution record: validation foundation, 2026-11-06**

Created an isolated checkout at `/private/tmp/dtcc-qes-integration-20261106`
from target `6e205c003cd44ec0ad8a785c0dbd0c402940ed19`. Before extraction,
recorded 2,594 dirty paths and froze 271 live source/document files plus the
tracked patch. The original working tree and installed native binary are retained.

The first reviewable portion of A contains the A/B validation adapters/reporting,
shared paired-coverage metrics, regression guards, explicit external reference
data location and a zero-solve archive verifier. The shared comparison no longer
requires importing the canyon campaign driver. Its compatibility wrapper retains
the historical `joined` report keys. Unrelated E0 application metrics were left
out of the isolated extraction.

Validation results:

- **145 tests pass** in the isolated checkout, covering all `validation/tests`,
  paired-coverage tests and regression guards, with the original external
  reference data explicitly selected and no skipped A/B checks.
- **35 framework/helper tests pass** in the original working tree, including
  canyon controller guards, compiled protection checks, experiment identity and
  shared paired metrics. This also checks compatibility with retained research.
- The extracted verifier exactly reproduces all **15 paired quantities and
  coverage counts across 74 archived records**, with zero new matrix solves.
  It records validation source, reference data and canonical record hashes.
- The staged changeset passes `git diff --cached --check`.

The initial isolated test run found the omitted external A/B spreadsheets and
an extraction namespace error (18 failures, 123 passes, two setup errors). Both
were corrected before the passing run. An initial archive-verifier invocation
also exposed a NumPy comparison mismatch; the corrected verifier passes. These
failures do not qualify a physics result. The validation suites used four small
native smoke answers across the initial and corrected runs; these belong to this
new integration scope, not to a reopened historical campaign.

The snapshot, staged patch, hunk inventory, JUnit results and archive-verification
reports are under `experiments/integration/attempt-001/`. A compact tracked index
is [progress.json](data/physics-integration/progress.json). The source extraction
is staged only in the isolated checkout; no integration commit or merge was made.

Next: finish A's reusable controller/stage-sampler dependency extraction and
clean-checkout tests before B. The original-tree helper pass does not establish
that those remaining research dependencies have already been packaged. B–D and
the fresh native AIJ matrix have not started.

**Execution record: controller/sampler extraction, 2026-11-06**

The reusable implementations now live in `validation/aij/controller.py`,
`evidence.py`, `workers.py` and `stage_sampling.py`. Controllers receive explicit
ordered limits, predecessor maps and frozen identities instead of importing a
physical campaign. Stage reservation remains atomic; failed attempts cannot be
replenished; predecessor checks reject changed identities, incomplete attempts,
failed outcomes and altered/missing evidence. Journaling preserves the worker
report and creates a separate, exclusive supervisor-failure record. Report links
also work when a campaign directory is outside the repository.

The canonical stage sampler retains the original interpolation/fallback
algorithm and exact contributor selection on nonuniform grids. It additionally
rejects malformed coordinates, duplicate/missing projection stages, truncated
capture arrays and changed contributor ordering. Existing experiment imports and
canyon-controller entry points delegate to the shared implementations. Source
identity covers the new shared files. No campaign archive or prototype model is
required to import or unit-test them.

The isolated extraction packages the validation Python modules/tests in the
sdist without adding runtime dependencies or including research campaigns and
validation outputs. `validation/tests` is now a package so the complete API and
validation suites can be collected together despite duplicate test basenames.
Warning-strict testing also found and fixed an existing unclosed reference-file
handle in `cityutil.sha256`; the resulting hashes are unchanged.

Completed checks:

- Full isolated suite: **1,894 passed, 50 skipped**, with warnings treated as
  errors (`tests` and `validation/tests` together). None of the A/B spreadsheet
  tests are skipped. The skipped checks require optional compiled study, monitor
  or safety executables, or exact historical toolchains; native release checks
  remain pending under D.
- Existing experiment/helper compatibility: **61 passed** with warnings treated
  as errors, including the unchanged native audit positive controls.
- Native canonical sampler integration: **two passed**, covering uniform and
  stretched vertical grids using the existing private bridge.
- Source-archive controller/sampler tests: **26 passed** independently of the
  working tree's campaign archives.
- Archived physics comparison: all **15 quantities and coverage counts across
  74 saved records** still reproduce exactly, with zero new matrix solves.
- The isolated staged patch passes whitespace checks. Native sources and the
  installed extension remain unchanged.

The full suite used an isolated copy of this checkout's Python sources with the
unchanged baseline native extension, SHA256 `28dce889bba25eafd81fa02d6895f51de908028045100561ab6fa35fadb5eeef`.
Its editable import redirector was disabled. The baseline extension is an
unqualified research build; two existing test corrections were included to
require its early `unqualified_build` rejection rather than assume qualification.
These corrections preserve the qualified-build assertions and confer no release
qualification. Native smoke/lifecycle tests belong to this integration scope;
no stopped physical campaign or historical attempt budget was reopened.

Preserved intermediate failures include a manufactured probe accidentally placed
in a fallback stencil, combined-suite module-name collision, qualified-build
test assumptions and resource warnings from the reference hash helper. All are
resolved before this checkpoint. Full logs, JUnit records, package/source hashes,
source archive checks and the combined changeset-A patch are preserved under
`experiments/integration/attempt-002/`; the tracked progress index links them.

Changeset A is ready for review in the isolated checkout. The live physical
campaign adapters remain research entry points and keep their original budgets
and stopping decisions. Next is B: runner lifecycle/diagnostics extraction,
followed by C and the complete native/release gates. No merge, installation or
public default change is part of this checkpoint.

**Execution record: runner lifecycle extraction, 2026-11-06**

Changeset B is extracted in `/private/tmp/dtcc-qes-integration-20261106` on top
of A. It includes scoped ownership accounting for wind-grid buffers, Poisson
storage and solver workspaces; release-before-replacement for tolerance and
precision changes; native progress/phase observations; and operation-ID checks
on binding transfer. Parameterization-stage callbacks only report completion.
The supported solver controller now reports completed monitor checkpoints via
an optional native atomic observer. Solver equations, numerical settings,
monitoring cadence and acceptance rules are unchanged.

The extraction does not import experiment option types, Session reuse adapters,
canopy/wake-composition code or canyon models. Standalone lifecycle tests exercise
the supported runner directly. Both failed preparation and numerical failure
retain reusable geometry; transfer failures report a terminal failure; Python
arrays retain independent ownership. The private failure-injection hook from C
is not required by B.

The complete checks pass:

| Check | Result |
| --- | --- |
| Full OpenMP Python/API/validation suite, warnings as errors | **1,934 passed, 16 skipped** |
| Full serial Python/API/validation suite, warnings as errors | **1,934 passed, 16 skipped** |
| OpenMP native CTest | **50/50 passed** |
| Serial native CTest | **47/47 passed** |
| Debug ASan/UBSan native CTest | **47/47 passed**, no sanitizer findings |
| Native symbol audits | OpenMP, serial, sanitizer and untouched parent pass |
| Exact compatibility matrix | **429 cases per build**, all **4,774 stored records** agree in each parent/OpenMP, parent/serial and OpenMP/serial pairing |
| Focused public-call and export cost guard | Passes the existing 10% and 0.01 s joint review threshold in every category |

The 16 skips in each Python suite require the historical lexicographic ordering
and exact archived toolchain. Optional native study, monitor and safety checks
that were skipped in A now run against the newly built test executables. The
six additional lifecycle tests pass on both backends. Their first run exposed
an invalid float32 test tolerance and collection of unrelated retained Python
objects during an ownership assertion; the tests now use supported tolerances
and establish a collected ownership baseline. These were test setup corrections,
not changes to numerical thresholds or memory allowances.

The reference is a fresh Release OpenMP build of the untouched target revision
`6e205c003cd44ec0ad8a785c0dbd0c402940ed19`, with qualified policy identity
`b26d15fdddf75e672f0bf6f9594e6789c9ae49fe5df49c4153001368591df074`.
The new serial/OpenMP candidate has identity
`d860fa1a3191c28756d62d800b72e071ef57efa7c1002da38d66156c297ad2db`.
Comparisons allow only this declared identity pair and backend provenance;
elapsed values are validated and excluded from equality. Fields, masks,
diagnostics and completed numerical work match exactly. The production
qualification header was not promoted; D remains required.

The cost check uses the repository's five observations after warm-up. Parent →
candidate medians are 6.05 → 4.61 ms for wind-only, 26.74 → 24.55 ms for combined
operations and 27.24 → 25.13 ms for export. These small isolated measurements
show no cost-guard regression and do not establish an urban speedup.

`experiments/integration/attempt-003/` preserves the source snapshot, original
hunks, four build identities, build/symbol logs, JUnit results, all matched field
archives and cost observations. Large local evidence directories are ignored by
Git. The small [progress index](data/physics-integration/progress.json) links
the B-only and combined review patches. The installed native extension remains
unchanged; native source edits are confined to the isolated checkout. A parent
archive extraction/configuration failure before compilation is also retained;
it produced no native answer.

Changeset B is ready for review and its supported-controller progress wiring
is retained by C below. The combined native AIJ and release gates follow C. No stopped physical campaign was
reopened, no model was promoted and no public default or installed package was
changed by this step.


**Changeset C implementation results — 2026-11-06**

C is implemented in `/private/tmp/dtcc-qes-integration-20261106`, on top of the
reviewable A/B stack. Native edits remain confined to that checkout. The
original research tree and installed extension are preserved.

The extraction retains typed selectors, conservative geometry/profile preflight,
finite helpers, the original frozen join and `physical-and-voxel-union-v1` roof
protection. Eligible horizontal overlays run after the complete legacy canyon
pass. Independent audits protect both roof bands and complete W initialization.
A minimal private bridge exposes optional stages, W, counters and face traces;
ordinary calls keep legacy defaults without diagnostic snapshots. Scoped cleanup
preserves geometry reuse after success and exceptions. B's completed-checkpoint
observer remains wired to the supported controller.

The clean `validation/aij/canyon.py` adapter and ordinary fixtures import no
research campaign packages. The bridge rejects canopy/wake-composition,
alternative relaxation and checkpoint-stopping controls; those models were not
ported. Public street-canyon values remain 0–1. Standard height-based one-way
turbulence needs an explicit private allowance. Failure injection is available
only in the separately identified hook-enabled validation build. The frozen
specification ships under `validation/specifications/`.

| Check | Result |
| --- | --- |
| Full OpenMP Python/API/validation suite, warnings as errors | **1,952 passed, 16 skipped** |
| Full serial Python/API/validation suite, warnings as errors | **1,952 passed, 16 skipped** |
| OpenMP native CTest | **56/56 passed** |
| Serial native CTest | **53/53 passed** |
| Debug ASan/UBSan native CTest | **53/53 passed**, no findings |
| Separately instrumented standalone helper tests | **6/6 passed**, ASan/UBSan |
| Native symbol audits | OpenMP, serial and sanitizer pass |
| Six-attempt hook qualification | **99/99 checks passed**, five successful answers match archived fields, W, probes and stages exactly; expected exception and subsequent legacy reuse pass |
| Ordinary nonuniform roof archive checks | **54/54 checks passed**, four answers reproduce both roof/grid displacement signs exactly |
| Final D 0° archive comparison | **21/21 checks passed**, both canonical answers and complete velocity/flags/stress/W hashes match |
| Ordinary-path compatibility | **429 cases per candidate backend**, **4,774 stored records per pairing**, exact against untouched main, B and each other |
| Focused default-path cost guard | Passes every category under the existing joint 10% and 0.01 s rule |

The 16 skips retain the exact historical ordering/toolchain requirements. The
native sanitizer runner exercises the actual overlays. The six standalone
helper CMake targets do not inherit core sanitizer flags; each was additionally
compiled and run directly with explicit ASan/UBSan and matching contraction flags.
Their independent corruption/positive controls remain active in Release builds.

The C ordinary Release policy identity is
`660544978f520df395dbc0b29469ea98a82def3753309982f10e0497c64648a8`
on both backends. Compatibility permits only its exact declared pair with main
`b26d15fdddf75e672f0bf6f9594e6789c9ae49fe5df49c4153001368591df074`
or B `d860fa1a3191c28756d62d800b72e071ef57efa7c1002da38d66156c297ad2db`,
validated elapsed-time fields and explicit backend provenance. Numerical fields,
diagnostics, completed work and existing decisions match exactly. Hook identity
is different. The production qualification header remains unchanged; these tests
do not requalify the release.

Fresh B → C median costs are 5.58 → 5.22 ms for wind-only, 25.91 → 26.32 ms for
combined operations and 26.39 → 26.55 ms for export. All five post-warm-up
observations and ranges are retained. These small checks establish no cost-guard
regression and no urban speedup claim.

The D checker initially selected the raw helper's 1,000-sweep/tolerance-1e-4
settings instead of the frozen 2,000-sweep key `b324220abd408a96`. Its control
answer remains under `D-zero`. After correcting that descriptor, a JSON/NumPy
comparison mismatch interrupted reporting before full-field hashes were saved;
the correctly configured control and offline canonical check are retained under
`D-zero-corrected`. The final checker saves hashes first and compares normalized
saved records. Its fresh pair under `D-zero-final` passes all checks. Four D
answers were consumed in total; no native source, numerical rule, measured mask
or stopping setting was tuned to gain parity.

The final joined D answer retains **34 qualified buildings and 59,840 changed
faces**, zero physical/voxel roof violations and zero W changes. Exact archive
reproduction preserves the known accuracy regression. This is engineering
compatibility evidence, not physical promotion or the complete 74-answer matrix.
No stopped campaign or scientific attempt budget was reopened. RSS was recorded
without a research memory cap; declared worker deadlines and structural limits
remain in force.

The isolated source distribution contains all **192 checked source/specification
files** byte-for-byte, including the frozen join, ordinary fixtures and archive
check tools, while excluding experiment outputs and caches. Its extracted Python
source passes **24/24 canyon/lifecycle smoke tests** with the frozen C native
module. This checks source closure; compiling and installing the final wheel
remain D gates. The initial streaming extraction harness read an entry twice and
failed before native execution; the corrected checker reads each entry once in
a fresh directory, without changing the archive or source.

`experiments/integration/attempt-004/` retains the selected-source inventory,
final source tarball and dependency epoch, build identities and native modules,
all test reports, qualification/archive answers, compatibility fields and cost
observations. `C-protected-canyon.patch` isolates C; `A-B-C-combined.patch` applies
cleanly to untouched parent versions of every affected file. The original D
checker variants and intermediate failures remain auditable. The progress
index records hashes and pending gates.

C is ready for review. Next is the frozen combined AIJ matrix in step 5, followed
by D's exact supported-release requalification and wheel/runtime artifact gates.
Legacy remains the default and the canyon models remain private experimental
options throughout that sequence.


**Combined native AIJ acceptance — 2026-11-06**

Step 5 passes on the frozen hook-disabled C candidate: **37 conditions and 74
fresh legacy/joined answers**, with the original A/B 1 m/6,000-sweep and D/E
2 m/2,000-sweep float32 settings. Every canonical record, plane, measurement mask,
numerical diagnostic, complete velocity/flags/stress/W hash and contributor-stage
array reproduces the post-fix `aij-002` archive. All 15 paired quantities and
shared-coverage metrics reproduce exactly when checked independently, without
additional native solves. All 148 archived stage/W files also match their
recorded hashes.

Only D 0° activates (34 buildings, 59,840 changed faces); the other 36 conditions
retain bitwise legacy velocity/stress parity. Physical/voxel roof and W audits,
sampling and mass guards pass throughout. D split-fibre MAE remains
0.1704606100 → 0.1770390175 (+3.86%); pooled D thermistor K and scalar-proxy MAE
remain +2.29% and +2.54%. The engineering extraction adds no accuracy benefit or
physical promotion. Keep legacy as default. These remain historical fixed-work
comparisons, without a tolerance-convergence or performance claim.

All workers meet their existing deadlines at four native threads and one BLAS
thread. RSS is recorded without a memory cap. The exact worker durations, peak
RSS, source/native/input epoch, tickets, outcomes, canonical records, stages and
per-answer checks are preserved in `experiments/integration/attempt-005/`.
`aij/REPORT.md`, `acceptance.json` and `paired-metrics-verification.json` index the
results. Release requalification proceeds separately in `attempt-006` using the
unchanged native policy identity and a separate staging copy.


**Changeset D release requalification — 2026-11-06**

The existing pedestrian-v1 policy is requalified in the isolated integration
checkout for
`660544978f520df395dbc0b29469ea98a82def3753309982f10e0497c64648a8`.
This preserves the policy's existing profile, precision, geometry and thread-team
scope. Experimental canyon calls remain explicitly legacy-controlled and outside
adaptive physical qualification. No physics threshold, equation, coefficient,
measurement mask, public default or stopped campaign allowance changed.

| Gate | Result |
| --- | --- |
| Qualified main versus candidate, OpenMP 1/2/4/8 and serial | **429 cases and 4,774 stored records per comparison**, all **12 comparisons exact** |
| Fresh combined-baseline captures | **27 non-adaptive and four adaptive entries exact** |
| Frozen S7 release policy matrix | **24/24 workers exact** in fields, diagnostics, decisions, histories, methods and monitors |
| Full qualified OpenMP suite, warnings as errors | **1,952 passed, 16 historical skips**, 129.80 s |
| Full qualified serial suite, warnings as errors | **1,952 passed, 16 historical skips**, 143.06 s |
| Native and sanitizer gates | Reuse unchanged C source/build evidence: **56 OpenMP, 53 serial and 53 ASan/UBSan checks**, plus **six explicitly instrumented helpers**; symbol audits pass |
| Isolated corrected sdist and wheel | Full source/license/immutable-evidence audits pass; **194 checked source files** match |
| Actual isolated installed wheel | Correct qualified identity, existing adaptive acceptance and runtime contracts; **24/24 canyon/lifecycle tests pass** |
| Promoted source sdist and wheel | Rebuilt after header promotion; full artifact audits pass again |
| Actual final installed wheel | Correct qualified identity, no failure hook, adaptive/public runtime smoke and **24/24 canyon/lifecycle tests pass** |
| Shipped-wheel focused cost review | Passes all three unchanged thresholds in the bounded balanced comparison; original failures and diagnostic flag retained below |

The C native gates are reused because their implementation and arithmetic inputs
are unchanged. New Release serial/OpenMP builds and their symbol audits were
performed for the exact qualified staging source. Before promotion, the only
existing source difference between the final candidate and the frozen epoch was
the deliberately updated qualification header, which is excluded from the native
identity hash by design. The final source was rebuilt from its own sdist, rather
than substituting a previously built module. Installed-file verification checks
the actual wheel bytes, and runtime probes check import paths as well as policy
support. Editable redirectors are disabled only in the isolated test processes.

Three setup/artifact failures remain in the evidence. The frontend initially
requested absent Ninja and stopped before compilation; the available Unix
Makefiles generator used the same compiler and arithmetic flags without installing
dependencies. The first staging copy had excluded a nested archived fixture
directory named `build`; restoring its original bytes and making a fresh sdist
and wheel fixed the source audit. Finally, uv's macOS system-configuration probe
panicked in the sandbox; the same local wheels were installed outside the sandbox
into `/private/tmp` targets, with no dependency or project-install modification.
The source and thresholds were not changed to bypass these failures.

The initial unpaired cost guard **failed** during broad timing drift. Those
observations remain under `cost-{main,D}.json` and `cost-comparison.json`. A fixed
three-round Latin-square investigation ran main, the direct qualified build and
the actual wheel once in each order position, retaining all five post-warm-up
observations per worker. No process was stopped and no additional timing rounds
were added after seeing its results.

For the actual release wheel versus main, medians of the three worker medians
are **28.15 → 17.19 ms** for wind-only, **94.38 → 89.20 ms** for combined calls and
**112.15 → 92.40 ms** for export. All pass the original joint **>10% and >0.01 s**
review rule. This is the shipped-artifact cost gate; no speedup is claimed.

The diagnostic's broad aggregate `passed` flag remains **false**: its extra
main-versus-direct combined contrast is 94.38 → 107.86 ms and triggers review.
The direct arm was faster in two matched rounds and had one large spike
(561.94 ms versus main's 80.61 ms in the third round); its median paired delta is
-9.37 ms. Identical core compiler flags and numerical work, the variable system
load and the wheel's passing contrast support an inference of timing variation,
rather than a consistent shipped regression. That diagnostic flag and the initial
failed measurements were reviewed and retained, not rewritten as passing data.
`cost-final-assessment.json` records the acceptance scope and rationale explicitly.

After isolated acceptance, only the integration checkout's qualification header
was promoted. `source-change-verification.json` proves no other existing source
file changed. The D review also adds the portable complete-matrix driver and a
small [integration results document](/private/tmp/dtcc-qes-integration-20261106/docs/PHYSICS_INTEGRATION_RESULTS.md).
`D-release-requalification.patch` isolates these additions;
`A-B-C-D-combined.patch` applies cleanly to untouched parent versions of all
**80 affected paths**. No commit or merge was performed.

Final CPython 3.13/macOS 15 arm64 artifacts and exact checksums are indexed in
`experiments/integration/attempt-006/promoted-artifact-results.json`; all source,
binary, build, test, timing, failed-attempt and installed-wheel evidence is under
`attempt-006`, with its hash index in `artifact-index.json`. The installed user
extension retains SHA256
`28dce889bba25eafd81fa02d6895f51de908028045100561ab6fa35fadb5eeef`.
The stack is ready for review. Durable archival of the ignored large evidence is
a remaining pre-release storage step; publication and merging are separate actions.


**Commit integration into main — 2026-11-06**

The implementation is recorded in six ordered commits: AIJ adapters/reports,
controller/sampler extraction, runner lifecycle, frozen canyon helpers, private
canyon integration, then release qualification. The final implementation commit
is `c2ab9acb788972c71d455461e061c5f5f02a4aa2`. Its complete Git tree equals the tested
candidate exactly; committing and fast-forwarding did not change source bytes.
The documentation commits add the original study notes, screening ledger,
integration plan and concise validation/artifact index.

The mixed pre-integration research sources are preserved in stash
`8a4a130a9b6db378b35a7e299a928c3368ad1a4a` based on the original `6e205c0` tree. All
99 selected source files were verified against their original SHA256 values.
Reference data and large experimental evidence remain in place. Excluded native
headers and prototype tests were moved out of the active source tree through the
stash so they cannot alter the qualified native fingerprint or test collection.
No stopped scientific campaign was reopened. No remote publication or package
replacement was performed.

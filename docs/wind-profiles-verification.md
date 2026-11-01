# Wind-profile verification and experimental scope

Measured, power-law and uniform inputs ship as **experimental**. Numerical
verification covers the implementation below. No independent physical or gust
validation was performed. Wind-sector selection and new exposure transfer are
outside this delivery, as required by the revised `WIND_PROFILES.md`.

## Integration with current main, 2026-10-31

The feature incorporates `main` at
`0f7382d9bd938a4082083ff0ef335e53818e7368`, including the S5c solid-mask
correction, S7 adaptive controls, S9 release evidence and updated locked
`dtcc-core` dependency. The historical checks below describe the earlier
feature baseline; their original reports remain unchanged. Current integration
outputs are retained in [main-integration evidence](data/wind-profiles/main-integration/).

The merged candidate passes 1,143 Python tests with 50 skipped in each backend,
46 serial and 49 OpenMP native checks, and the profile/runner/pedestrian-policy
AddressSanitizer/UndefinedBehaviorSanitizer checks. Both 32-case profile
comparison campaigns pass with the previously declared `1e-4` comparison solve
tolerance. Production defaults and numerical comparison thresholds are unchanged.

The native implementation identity changes when adding layer tables. The new
identity is enabled for the existing log-profile policy only after an exact
regression against all 24 frozen S7 release workers: velocity/flag/coordinate
hashes, convergence diagnostics, acceptance decisions, assessment/checkpoint
histories and monitors match. Only the declared source revision and wall-clock
values may differ. Serial/OpenMP source/arithmetic identities agree. Reproduce
that check after building both backends, following the
[isolated requalification procedure](solver-control-requalification.md):

```sh
.venv/bin/python tools/check_policy_compatibility.py \
  --serial build/profiles-serial --openmp build/profiles-openmp \
  --output build/profile-policy-check
```

Experimental layer tables are explicitly excluded from `pedestrian-v1` with
`unqualified_inflow_profile`; they cannot inherit log-profile acceptance based
on reference scalars alone. Native coverage exercises that restriction and
Python/dataset coverage rejects calm profiles using their evaluated reference.
There is no new numerical or physical qualification for experimental families.

The first serial suite in the freshly synchronized environment recorded three
silence-test failures from `pyassimp`'s upstream invalid-escape `SyntaxWarning`
while bytecode generation was disabled. Its normal dependency import/compilation
was completed, then both full suites passed. The initial log is retained; no
product code or assertions were changed to hide the warning.

## Frozen baseline and consumers

The worktree starts from `bbfd20005e0bd7d7e648438a1bc8d5a9a4358a71` plus the
user's pre-existing solver/grid changes, frozen in baseline commit `325b3b1`.
The source checkout was left untouched. Before implementation, the existing
wind, sampling, physics, repeated-condition and dataset checks passed **165 tests**. Existing reference arrays were not regenerated.

| Consumer | Integration |
| --- | --- |
| Public run / preview / `_city` | Canonical reference before geometry; float64 evaluation at final float32 physical cell centres |
| Profile specifications | Immutable arrays/provenance, log-height or linear component interpolation, explicit lower log tail and constant/error upper tail |
| `WindCondition` / bindings / `ModelInputs` | One owned u/v pair per physical layer; transactional narrowing; no native measured/power-law evaluator or Python callbacks |
| `WINDSGeneralData` | Table copy into the legacy physical bands, cleared lower/upper bands, maximum over all physical layers for new-profile velocity limit |
| Building models | Existing roof-level vector sampling/rotation; documented calm-roof orientation and turning limitations |
| Turbulence | Existing solved-speed morphometric log conversion; enabled with explicit non-log caveat |
| Roughness | Remains preparation-time model input; used by measured lower log tails and existing ground/turbulence state |
| Solver monitor / results / datasets | Same declared-reference speed for normalization; NaN speedup when zero |
| Request identity | Complete JSON profile, interpolation/tails, provenance and relevant run roughness |
| Comfort | Existing per-direction reference inputs and exposure utility unchanged |

The native table path writes exactly the bands written by `applyLogProfile`;
no prescribed top-face velocity has been added. `LogProfile.cpp` is unchanged.

## Test gates

The original feature review's full serial Python suite passed **1,083 tests, 50 skipped**; focused
OpenMP checks passed **512 tests, 10 skipped**. Outputs are archived with the
[verification data](data/wind-profiles/).
Those native suites passed **43 serial and 46 OpenMP** checks. AddressSanitizer and
UndefinedBehaviorSanitizer pass the profile, runner-lifecycle and staggered-flux
checks. LeakSanitizer is unsupported by the available macOS runtime, so those
commands set `ASAN_OPTIONS=detect_leaks=0`. The native termination/console/file-I/O
symbol audit and built-wheel artifact/runtime checks also pass.

Focused coverage includes:

- Both component interpolations, knots/midpoints/skipped intervals,
  nonmonotonic speed, interior maxima, 350/10-degree wrap, reversals and calm
  measurements; both lower and upper policies; power-law normalization/ground.
- Immutable copied arrays/nested provenance; invalid arrays/references;
  out-of-range, overflowing and malformed layer tables; JSON round trips.
- Public scalar/profile conflicts, non-log run roughness, default upper hold,
  tail-layer counts and coverage before allocation at physical cell centres.
- Empty-domain layer fields against independent float64 Python formulas, on
  uniform and explicit nonuniform grids with both multiplier precisions;
  expected zero conservative divergence and unchanged fields after correction.
- Raw physical/ghost face initialization, interior-max velocity limits,
  table ownership and atomic validation; repeated/fresh runner equality and
  legacy-log/table family switching after failures.
- Bitwise explicit-log/legacy results, including direction rounding near 360
  degrees; tabulated log controls within float32 rounding. A separate comparison
  against the original checkout's installed extension confirms bitwise velocity
  and cell-flag equality for 24 empty/building, uniform/nonuniform, direction and
  precision combinations.
- Turning through buildings, a calm-at-roof case, more-than-45-degree warning,
  height and wall-distance turbulence for every new family, and metadata caveats.
- Monitor reference normalization, zero-reference solves/NaN speedup,
  dataset/direct equivalence, invalid requests before fetch, distinct shape/tail
  identity, and optional field speedup export without changing legacy defaults.

An existing archive test depends on ignored `.log` files in the source checkout's
urban-benchmark evidence. Those original logs were copied into this worktree
unchanged. No archive fixtures/assertions were altered. They remain ignored;
a fresh checkout of the frozen baseline may need the same optional archived
logs to run that unrelated test. The source-distribution audit also exposed 32
manifest-listed S0 archived inputs omitted from the worktree by the old global
`build/` ignore. They were copied from the original checkout with SHA256 checks
against the frozen manifest. The source-distribution exclusion now targets only
root `/build/**`, retaining historical build evidence under `docs/data/`. No
reference inputs were regenerated or modified.

## Fixed numerical campaign

[serial.json](data/wind-profiles/serial.json) and
[openmp.json](data/wind-profiles/openmp.json) are generated by
`tools/verify_wind_profiles.py`. Reports record the source revision and exact
implementation SHA256, compiler/runtime/backend, geometry, grid, reference,
solver settings, numerical errors and costs.

The campaign includes both an empty domain and a synthetic 10 x 10 x 8 m
block at `(30,25)` in an 80 x 60 x 40 m flat domain. Horizontal spacing is 2 m;
vertical coordinates use either 20 uniform layers or faces
`[0,1,2,3,5,8,12,18,26,40]`. It covers both multiplier precisions and at most
2,000 sweeps. Every fluid cell vector is compared; maximum conservative
divergence is retained. Each comparison now records convergence and mask
agreement, and the overall gate requires **every** baseline, amplitude,
legacy-control and tabulated comparison to converge.

Before execution the script fixes absolute normalized-vector scaling and dense
power-law-tabulation tolerances to **2e-3 m/s** at the 5 m/s baseline. For four
families, two geometries, two grids and both precisions, amplitude factors `.5`,
`2` and `3` are compared with baseline fields. Dense power-law tabulation has
2,001 evenly spaced heights plus the declared reference. It deliberately does
**not** insert solver supports, so interpolation error is exercised. Requested
profile inputs, all comparison stop results and source/configuration hashes are
included in the reports.

The review found that the original campaign checked convergence only for the
baseline. It could report success when higher-amplitude float32 comparisons
stopped at their precision floor. Corrected runs at the default `1e-5` tolerance
are retained in [serial-default-tolerance.json](data/wind-profiles/serial-default-tolerance.json)
and [openmp-default-tolerance.json](data/wind-profiles/openmp-default-tolerance.json).
Numerical comparison tolerances pass, but these reports correctly have
`all_comparisons_converged=false` and `passed=false`. The failed stops include
legacy log controls: this is an existing absolute-tolerance/float32 limitation,
not a newly introduced profile path. No production solver default was changed.

A separate follow-up protocol uses explicit tolerance **1e-4**, with the
numerical comparison criteria unchanged. All 32 cases and their comparisons
converge and pass in each backend. The maximum normalized scaling error is about
**2.9e-5 m/s** and dense-tabulation error about **5.7e-6 m/s**. Legacy controls are
bitwise equal. These are numerical equivalence results, not physical accuracy
thresholds or qualification for arbitrary geometry, shear or turning.

## End-to-end review fixes

The follow-up review against the revised plan corrected these issues:

- Log-transforming knots could collapse distinct neighbouring float64 heights
  and return the wrong value at a knot. Brackets now use physical height and
  stable relative logarithms, including extreme height spans.
- Invalid metadata mappings could be accepted and caller `measurements`
  provenance overwritten. Requested input representations and scaling now
  preserve caller metadata separately and validate it consistently.
- The dataset accepted a generic dictionary but advertised no schema
  discriminator. Its schema now exposes the four validated payload variants,
  strict schema versions and forbidden unknown fields.
- Explicit-log dataset slices used a narrowed reference while direct results
  and monitors used the declared value. They now share the declared reference.
- Preparation repeatedly evaluated and serialized the same physical table.
  It now builds one validated table for preview, native input and metadata.
  Obsolete record/coverage/turning helpers, a redundant native top-plane scan
  on the table path, and an unreachable log metadata branch were removed.
- Signed calm zeros could give a roof direction of minus pi instead of the
  documented `atan2(+0,+0)=0`; Python evaluation now normalizes exact zeros.
- Verification now exercises independent dense interpolation on empty and
  building domains, checks every comparison stop/mask, and retains failed runs.

The compiled feature still has exactly two native kinds: `log` and `layer_table`.
There are no native measured/power-law evaluators, profile knots, sector-transfer
implementations, turning opt-in controls or non-log turbulence rejections.
Historical archived source snapshots are evidence and remain unchanged.

## Measured cost

Five repetitions follow a warm call. Instrumented Python timings sum **all**
profile-evaluator calls made by the public run; native timings cover the field
copy/application before building models, excluding allocation. Reports retain
both medians and the fraction of total public call time. On this arm64 machine,
new-profile native table copying takes about 8 microseconds; Python evaluation
across preparation/metadata checks takes tens of microseconds to about 0.1 ms.
Each run and preview performs one bulk physical-layer evaluation, with scalar
reference evaluation separately. The
combined contribution is a few percent or less of the small synthetic public
call. These machine/case measurements are not a general performance guarantee.

## Reproduction

With the repository Python dependencies and nanobind installed:

```sh
cmake -S . -B build/profiles-serial -DCMAKE_BUILD_TYPE=Release \
  -DDTCC_QES_OPENMP=OFF -DDTCC_QES_BUILD_TESTS=ON \
  -DPython_EXECUTABLE="$(which python)"
cmake --build build/profiles-serial -j 8
ctest --test-dir build/profiles-serial --output-on-failure -j 4
cmake --build build/profiles-serial --target check_native_symbols
```

Use a separate build tree with `-DDTCC_QES_OPENMP=ON` for OpenMP. For Python,
install the matching build into an isolated environment or pair its extension
with this worktree's Python package. Here `.venv` reuses the source checkout's
dependencies without its editable import hook, the serial extension is under
`src/dtcc_qes`, and `build/profiles-openmp-package` holds the OpenMP package:

```sh
.venv/bin/python -m pytest -q
OMP_NUM_THREADS=2 OMP_DYNAMIC=FALSE PYTHONPATH=build/profiles-openmp-package \
  .venv/bin/python -m pytest tests/test_profiles.py -q
.venv/bin/python tools/verify_wind_profiles.py --tolerance 1e-4 --output /tmp/profile-serial.json
OMP_NUM_THREADS=2 OMP_DYNAMIC=FALSE PYTHONPATH=build/profiles-openmp-package \
  .venv/bin/python tools/verify_wind_profiles.py --tolerance 1e-4 --output /tmp/profile-openmp.json
```

Omit `--tolerance 1e-4` to reproduce the retained default-tolerance reports;
they return a failure exit status for unconverged comparisons.

Configure a separate Debug tree with `-DDTCC_QES_ENABLE_SANITIZERS=ON`, build
`check_profiles check_runner check_physics`, then run:

```sh
ASAN_OPTIONS=detect_leaks=0 ctest --test-dir build/profiles-sanitizers \
  -R 'background_profiles|runner_lifecycle|staggered_flux' --output-on-failure
CMAKE_GENERATOR='Unix Makefiles' CMAKE_BUILD_PARALLEL_LEVEL=8 \
  .venv/bin/python -m build --wheel --no-isolation --outdir build/profiles-dist
.venv/bin/python tools/check_artifacts.py build/profiles-dist
```

## Follow-up physical validation

A separate campaign must select independent approach-profile and withheld
observation data, fix geometry/grid/sampling and acceptance criteria before
execution, and vary measurement spacing, tails and grid separately. It must
retain local vector/direction errors, pedestrian speeds, extrema, divergence
and failures. Turbulence remains available with its existing algebraic-model
scope; this implementation does not establish consistency between arbitrary
shear and its morphometric log conversion, or add gust qualification.

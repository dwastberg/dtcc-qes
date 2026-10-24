# Milestone 1 final audit

Audited against the workspace's `MILESTONE1.md`, including its fixed native
safety constraints and acceptance criteria. Implementation steps 1–7 are
present. Local acceptance is verified on macOS arm64 / Apple Clang 17 / Python
3.13. GitHub CI execution and upstream issue submission remain pending.

## Traceability

| Plan item | Implementation and evidence | Status |
| --- | --- | --- |
| 1. Reference baseline | Canonical flat/building cases, pristine full Git revision, compressed arrays and JSON provenance; pristine regeneration matches exactly | Local pass |
| 2. Build and I/O split | scikit-build-core/nanobind, static QES core, Boost headers only; poisoned I/O headers, full symbol audit, wheel/sdist rebuild; macOS extension links only libc++ and libSystem | Local pass; clean Linux job configured |
| 3. Safe embedding | Leveled discard/buffer sink, exceptions, default initialization, explicit ownership and solver diagnostics; seven native CTests, ASan/UBSan, descriptor subprocesses, zero reported leaks | Local pass |
| 4. Runner/bindings | Pimpl, native offset/length validation, strict numeric CPU arrays, GIL release, process mutex, DTCC log forwarding, owned outputs, reference face-to-centre convention | Local pass |
| 5. City/public API | Explicit conditions, measured-height policy, geometry/CRS/transform validation, local origin/domain derivation, flattening metadata, source-ID map, WindResult and VolumeGrid fields | Local pass |
| 6. Physical/lifecycle validation | Exact references; analytic profiles/cardinals/occupancy; independent staggered flux; translation, ordering, immutability, failure recovery and concurrency checks | Local pass, with documented legacy boundary limitation |
| 7. Reproducibility | README, runnable example, pinned DTCC revision and locked build tools, macOS/Linux CPU jobs and separate reference jobs, artifact checker and fresh-environment wheel test | Implementation/local checks complete; remote execution pending |

Final local evidence: **177 Python tests** with warnings treated as errors;
**seven native CTests** in Release and under ASan/UBSan; full native symbol
audit with an empty allowlist; macOS leak report **0 leaks / 0 bytes**. The
complete standalone build succeeds. Pristine and patched executables match
the committed arrays/summaries exactly, and match a separately regenerated
same-host reference directory exactly. A wheel rebuilt from a fresh sdist was
installed into a new environment with all 139 locked runtime packages; all
177 tests and the example pass there. The module and DTCC installation point
to the intended QES/DTCC revisions.

Initial beta verification (`0.1.0b1`): installed serial and OpenMP wheels each
pass **177 Python tests** with warnings treated as errors and run the example.
The serial build passes **seven native CTests**; OpenMP passes **ten**, including
one-, two- and four-thread repeatability. All ten OpenMP tests also pass under
ASan/UBSan. Both native symbol audits pass. The beta sdist builds an OpenMP
wheel; license/source checks pass for the sdist and both wheels. Package metadata,
the native extension and the recorded source revision agree on the beta version
and QES commit.

## Findings corrected during review

- Serial convergence previously accepted the initial sentinel without running
  an iteration for tolerances >= 1. QES fork commit
  `398e9a4e776575f59f747a7a738048229a9ad166` measures at least one iteration.
  This leaves the normal fixture calculations unchanged.
- Near-integer explicit domain extents could round slightly inward. They now
  round upward; huge padding fails before NumPy overflows.
- Reference comparison used to relax coordinates/classifications together with
  velocity and selected exactness from OS/architecture alone. Coordinates,
  spacing and flags now stay exact, and compiler/build provenance selects the
  velocity policy. New tests guard those distinctions.
- macOS CPU CI, reference-regeneration jobs, locked developer build tools,
  distribution checks and the example/documentation were missing. They are now
  included. Development CI wheels explicitly retain nanobind leak warnings.

## Supported-contract decisions and limitations

- Extra input restrictions are intentional and documented: touching buildings
  are rejected along with overlap, source IDs are strings, footprint clearance
  is two cells, and narrow features that collapse in float32 are rejected.
- DTCC transform declarations are treated as absolute local-to-global maps;
  equal translations apply once and conflicting declarations fail. The cell
  ordering decision follows the session's accepted current DTCC meshgrid `xy`
  convention and is isolated/tested. No upstream standardization is claimed.
- Staggered mass conservation is verified on the solved interior. Pristine QES
  retains an uncorrected upper boundary face: the last solved band has about
  `0.0152191 s^-1` maximum divergence. This is guarded separately and retained
  for numerical parity. See [validation details](validation.md). Convergence
  does not mean every returned cell has zero divergence.
- Terrain/cut cells/vegetation/turbulence, multiple conditions, CUDA,
  public wheel publishing and the anisotropic Domain correction remain deferred.

## External acceptance still pending

The workspace has no outer Git remote configured. CI configuration has been
parsed/reviewed and its local equivalents executed,
but GitHub jobs have **not** run. A successful Linux build without I/O headers,
Linux numerical-tolerance confirmation and remote macOS/reference job results
cannot be claimed yet. The QES fork's six embedding commits have been pushed to
`dwastberg/QES-Public` on `dtcc-embed`, and GitHub advertises
`71f8dcb29e8308f4d64bcccafc3d87ee7f0b29bd` as the branch tip. The parent
submodule and `src/dtcc_qes/_qes_revision.txt` pin that commit. Configure the
outer GitHub remote and push the beta commit to run
`.github/workflows/native-build.yml`.

The licensing metadata inconsistency has a concrete
[prepared upstream issue](upstream-license-report.md); submission remains
pending. It does not change this package's GPL-3.0-only metadata/notices.

The original plan is retained in `MILESTONE1.md`. IDE files remain local and
ignored. Work history keeps one outer commit per milestone step, followed by
the beta preparation commit; QES fixes are committed separately on `dtcc-embed`.

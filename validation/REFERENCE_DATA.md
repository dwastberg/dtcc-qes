# AIJ reference data for validation

Validation resolves reference spreadsheets and drawings under `validation/` by
default. Set `DTCC_QES_AIJ_DATA` to a directory containing the `AIJ_A`, `AIJ_B`,
`AIJ_D` and `AIJ_E` subdirectories to use a separately maintained reference copy.
The runner still records the actual source file hashes. This setting changes
file locations, not coordinates, units, measurements or masks.

The A/B spreadsheet tests report a skip when those external files are absent.
An integration acceptance run requires the files and must run those tests without
skips. The data-independent paired-coverage and regression guard tests remain
runnable without A/B spreadsheets. Reference datasets require their own
redistribution review before inclusion in release artifacts.

For example, from a clean checkout with validation dependencies installed:

```sh
env DTCC_QES_AIJ_DATA=/path/to/reference/validation PYTHONPATH=validation \
  python -m pytest tests/test_canyon_aij.py tests/test_validation_regression.py \
  validation/tests -q
```

`tools/check_physics_archive.py ARCHIVE --output NEW_FILE` recomputes the 15
paired metrics and their coverage from a complete saved canyon AIJ campaign.
It reads 74 canonical records and the reference spreadsheets without running a
native solver. It refuses an existing output filename and fails on differing
measurements, IDs, metrics or coverage. The saved report records input record
hashes. Use a separate fresh native comparison to qualify a changed native build.

The reusable campaign controls live in `aij.controller`, with deadline-only
workers in `aij.workers` and serialization/hashing in `aij.evidence`. Callers
provide their own ordered phase limits, predecessor map and frozen identity.
Reservation consumes an attempt even if the worker fails. A later supervisor
failure is recorded separately from the worker report. These helpers do not
define physical acceptance gates or grant additional attempts.

`aij.stage_sampling.StageSampler` captures contributors for the canonical
interpolation and nearest-fluid fallback on uniform or nonuniform vertical
grids. It rejects malformed captures and requires projection samples and methods
to reproduce the final canonical samples. Capture is opt-in and requires the
native experiment bridge; its numerical-independent tests use manufactured
fields. The existing experiment import paths remain compatibility wrappers.

Run the complete available integration suite with both test directories:

```sh
env DTCC_QES_AIJ_DATA=/path/to/reference/validation PYTHONPATH=validation \
  python -m pytest tests validation/tests -q -W error
```

Use an isolated package on `PYTHONPATH` when checking an extracted checkout and
disable its editable import redirector as in `tools/compare_native_builds.py`.
Optional compiled test executables and toolchain-specific archive checks report
explicit skips when unavailable; those checks remain part of native release
qualification.

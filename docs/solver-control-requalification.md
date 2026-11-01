# Native solver requalification

A native edit changes the source/arithmetic identity and disables adaptive
acceptance. Requalification preserves the existing pedestrian-v1 scope and
thresholds; it does not qualify new inflow families or physical accuracy.
`validate_solver_release.py` remains the immutable S9 archive verifier.

1. Freeze source, lock hash, compiler, arithmetic flags and backend configuration
   in a fresh validation directory. Keep the production qualification header
   unchanged. Build fresh Release serial, OpenMP and ASan/UBSan trees; run CTest
   and each build's `check_native_symbols` target. Stage packages with
   `compare_native_builds.stage_package` to exclude editable import redirects.
2. Compare against the preceding qualified commit:
   `tools/compare_native_builds.py --baseline COMMIT --backends openmp serial
   --thread-counts 1 2 4 8 --require-backend-parity --native-consolidation
   --identity-pair OLD NEW`. The identity exception requires the exact declared
   pair. Run the combined baseline's non-adaptive subset with the same pair.
   Numerical arrays, masks, work and decisions must match exactly. The Phase 9
   metadata migration permits only declared native identity/build support,
   newly measured legacy clocks and native exclusion lists. Durations are
   validated separately; no blanket metadata exception is allowed.
3. Copy the frozen candidate to an isolated staging directory. Set only that
   copy's `pedestrian_qualified_revision` to NEW, then rebuild serial/OpenMP.
   The qualification header is excluded from the identity hash: NEW must remain
   unchanged, and the isolated packages must report build support.
4. Run all 24 frozen S7 release workers:

   ```sh
   .venv/bin/python tools/check_policy_compatibility.py \
     --serial ISOLATED_SERIAL --openmp ISOLATED_OPENMP \
     --output FRESH_WORKER_DIRECTORY
   ```

   Exact fields, diagnostics, acceptance, status, reasons, assessment histories,
   checkpoint histories, method and monitors must match. Only declared native
   identity and validated elapsed times differ. Run adaptive combined-baseline
   cases, preflight, excluded profiles/precision/turbulence/thread teams,
   deterministic completed-work deadlines, and the full `pytest -W error` suite
   against both intended isolated packages.
5. Build an isolated sdist and a wheel from that sdist. Run
   `tools/check_artifacts.py` and `tools/wheel_runtime_smoke.py` against the
   installed wheel. Verify the imported path, qualified identity and acceptance.
   Complete the focused public-call, combined and export cost checks.
6. Only after every gate passes, promote NEW in the production qualification
   header. Rebuild release artifacts, verify their source/arithmetic identity
   matches the tested candidate, and repeat artifact/runtime smoke checks.
   Publish the identities and evidence with the change. Failure leaves the
   production identity unchanged and the candidate unqualified.

Historical evidence under `docs/data/` is immutable. An intentional numerical
change requires affected cases, independent correctness criteria and numerical
impact declared before acceptance; a version bump alone is insufficient.

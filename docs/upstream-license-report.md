# Prepared upstream issue: QES build metadata conflicts with source license

Status: prepared locally; not submitted. This checkout has no authenticated
GitHub session. No external issue, comment or message has been sent.

Suggested title: **CMake/CPack says MIT while LICENSE and source headers specify GPL v3**

At QES 2.3.1 commit `dced7ec571487be7538eca17bfc25bb3262fb6d0`, the repository's
`LICENSE` and source-file headers specify GNU GPL version 3. The top-level
CMake/CPack metadata labels the project MIT, which can lead downstream package
metadata to describe a different license from the distributed sources.

Could the build/package metadata be aligned with the intended source license?
The dtcc-qes embedding fork uses `GPL-3.0-only` consistently, preserves the
upstream notices and includes corresponding sources in its source distribution.
This report asks maintainers to confirm/correct the metadata; it does not ask
for a license change.

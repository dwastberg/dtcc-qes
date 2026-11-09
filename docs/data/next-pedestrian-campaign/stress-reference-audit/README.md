# Historical independent-reference and stress audit

These are frozen research results from `8f43c5a`. The corrected inventory is
[reference-audit-004.json.gz](../../surrey-background/reference-audit-004.json.gz):
`Urban_roughness` contains the Suburban three-component reference as well as
Urban adjustment profiles. Presence does not establish condition-matched cluster
inflow. The original report is retained for audit history, with its correction
explicit here. Numeric table exports preserve the source values and per-row units.

Data: Mishra et al., *Tall Building Clusters in Urban Canopies* (2025), Surrey
repository output 991008866202346, associated dataset DOI 10.17605/OSF.IO/5X7WV.
Only numeric summaries are included; raw MAT files and time traces remain external.
No statistical weighting or uncertainty is invented. The optional `mat-io` reader
is needed only to redo the raw-table audit, not for the benchmark or unit tests.

The offline fixed-mean Python alternatives and native helper are analysis tools;
no alternative covariance formulation is exposed or linked into the runtime.

# Frozen research evidence

These compact reports retain their original research identities and conclusions.
They are historical evidence, not results from the corrected production sampler.
Full archives are checksum-indexed in
[historical-archives.json](../reference-integration/historical-archives.json).
Retrieve any indexed file with `git show 54ccb39:path > archive.tar.gz`, verify
its SHA-256, then extract into a fresh directory. Source and build identities in
those archives remain unchanged. The source-only benchmark adapter accepts their
frozen `covariance_model: legacy` key using the production API.

# Qualified reference integration

The three selected changes and their limits are described in
[REFERENCE_INTEGRATION_RESULTS.md](../../REFERENCE_INTEGRATION_RESULTS.md).
`summary.json` contains every gate, the paired impact reports, timings and
physical limitations. `scope.json` pins changed code/test hashes and exclusions.
`native-build-identity.txt` hashes to the promoted policy identity.
`imported-packages.json` verifies the actually staged main/candidate Python sources
against their respective Git commits, independently of the capture harness's
working-tree source snapshot.

`qualification-evidence.tar.gz` contains 448 checksum-indexed files: complete
Surrey runs, paired AIJ records, ordered witness tensors, offline replays,
adaptive records, recipes, logs, build identities and the built wheel/native
modules. Verify the archive SHA-256 in `verification.json`, then every member
against the archive's `manifest.json` before analysis. Extract to a new directory.

The full 684 MiB bundle additionally contains large matrix and feature arrays;
its retained workspace path, SHA-256 and byte count are in `verification.json`.
The repeated thread captures and the 1.3 GiB source distribution are separately
indexed there. These larger local files are not ordinary test dependencies.
The archived recipes reproduce the manufactured matrices and directed checks;
A/B checks require the external spreadsheets specified by their source hashes.
Native libraries correspond to committed source plus the recorded qualification
header; baseline main is an ancestor available in Git.

Earlier scientific archives remain at their research commits. Retrieve indexed
files from `historical-archives.json` using `git show REV:path`, after making
that research revision available locally, and verify the given hash. No previous
research run is overwritten. Original installed and staged packages are retained.

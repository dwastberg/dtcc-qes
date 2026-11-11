# Unified campaign V2 implementation review

The implementation branch starts at main `a833c4d`. It adds explicit physical
energy, compact quality evidence and geometry witnesses without changing the
native numerical identity. The research limiter remains experimental and is
not ported or promoted. The plan's optional PR4 and promotion-only D2 are
explicitly skipped. Existing momentum-campaign balances and failures remain.

## User-visible behavior

- `WindResult.physical_k`, `WindSample.physical_k` and
  `WindPointSample.physical_k` recompute covariance validity and half its trace
  in float64. Computed fluid and contributor coverage apply; unusable values
  are NaN, calm zero is valid, and raw tensors remain untouched.
  `to_dtcc(include_physical_k=True)` adds the field with units and provenance.
- `result.quality_report(sample=None)` returns an immutable schema-v1 snapshot
  of solver qualification, scalar divergence, solve-time turbulence evidence
  and optional existing sampling diagnostics. Strict JSON nulls carry reasons.
  It reads no full fields and introduces no new acceptance thresholds.
- `wind.check_geometry(city, result_or_preview, ...)` gives opt-in physical and
  raster witnesses, point/route evidence, examined scope and mask hashes.
  It uses the existing canonical preparation, checks its mapping against the
  native mask, and uses four-face connectivity. Raster evidence before a solve,
  terrain, roof-crossing layers and mapping disagreements stay unavailable.
  Budget limits never pass; requested IDs are retained. Geometry is unchanged.

## Evidence and implementation decisions

Receipts are in `docs/data/unified-v2/`. Meaningful analytic fixtures cover
rotation, covariance invalidity, current mutations, source-contributor
invalidity, calm zero, export ownership and units, strict JSON, report
immutability, SciPy connectivity parity, oblique and closed gaps, holes,
corner contacts, lost pockets, roof/base boundaries, translated origins,
unsupported terrain and analysis limits. Installed-wheel smoke exercises all
three public features with editable redirects disabled.

The final full suite passed: **1,924 tests passed, 50 skipped** in 91.82 s.
Research verification passed 12 tests and the native covariance executable.
Skips are existing platform, optional-backend and archived-toolchain checks.
No unresolved test failure is accepted.

Archived A/B/D native masks pass at the examined 1.5 m slice. E records 845
narrow-gap warnings and is unavailable because roofs cross the layer. Earlier
E coarse-versus-fine rejection patches are retained and replayed as raster
fixtures, explicitly distinct from physical polygon truth. No new archive wind
solve or automatic geometry repair was performed.

D1 freezes research `4eb119d` identities, tests the actual native spectral
limiter against an independent float64 eigensolver, and replays 4,792 computed
tensors and 813 queries. Combined PSD, no-lost-query and native-oracle gates
pass. Coverage recovers 107 A/B queries; D query coverage is unchanged.
Spectral bounding reduces physical k by up to 5.9781 m²/s² relative to the
component rule. The latter is frame dependent; uniform spectral bounding is
rotation covariant. Those are numerical findings, not predictive gains.
The research incoming-mode energy oracle passes to float32 rounding.
Reproduction sources live in `research/unified_v2/`.

## Runtime and memory

- Physical k at 3M cells: median 0.713 s, p95 0.763 s; 33.9 MB scratch beyond
  the 24 MB output, below the 64 MiB target.
- Default quality report: median 19.4 µs; 6,251 traced allocation bytes, with
  field access explicitly forbidden by a test.
- Raster labels at 1M cells: median 0.411 s, p95 0.414 s; 19.0 MB traced
  allocations including output and queue.
- Feature-off baseline/candidate runs share one native binary and have exact
  velocity/flags. Median delta 0.000100 s (ratio 1.0202) does not exceed both
  specified thresholds, 5% and 0.01 s. Full times and RSS are retained.

## Limits and claims

No predictive accuracy gain, gust/comfort qualification or validated pedestrian
accessibility is claimed. Geometry reports examine horizontal slices over flat
terrain, not general 3D connectivity. Roof-crossing layers are conservatively
unavailable in full; a future localized design can retain more evidence.

No native PR was selected. Its conditional serial/OpenMP paired-build,
sanitizer, expanded release and policy-requalification matrices were not run.
The unchanged native sources require no new adaptive-policy receipt. No
promotion campaign or large-grid experiment was started.

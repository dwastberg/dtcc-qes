# Sampling support and comparison provenance

`WindResult.sample_points` can attach support evidence without changing values,
interpolation, fallback selection or covariance validity:

```python
sample = result.sample_points(points, "linear", frame="global", diagnostics=True)
support = sample.support
print(support.reasons)
```

`support.geometric` requires an in-range stencil with no positive solid weight.
`support.computed`, `support.contributors_valid` and `support.interpolant_valid`
describe separate turbulence checks. They are `None` without turbulence.
An acceptable interpolant can still have an invalid contributing tensor;
`sample.stress_valid` retains that failure. Diagnostics are snapshots independent
of subsequent edits to source arrays or sample masks.

Reasons can coexist: `outside_domain`, `outside_center_range`,
`positive_solid_weight`, `nonfinite_velocity`, `uncomputed_contributor`,
`invalid_contributor_covariance`, `invalid_interpolant` and `nonfinite_stress`.
No reason is inferred from an unvisited, unsupported cell. Finite zero tensors
remain valid. Solid neighbours with zero interpolation weight are excluded.

For a local investigation, add `include_contributors=True`. Details contain up
to eight physical `(i,j,k)` cell indices, centre coordinates in the requested
frame, weights, solid flags, computed flags and covariance validity. Inactive
slots have index -1 and weight zero. `support.to_dict()` creates JSON-compatible
owned values. Normal sampling attaches no diagnostic arrays.

## Validation records and comparisons

New AIJ records use `aij-run-v2`, retaining existing fields and adding
`probes.sampling_provenance`, raw stresses and their validity. Provenance records
requested/actual points, horizontal displacement, height change, method, and
support at both the requested and selected points. A nearest-fluid fallback
does not erase the original requested-point failure. `runner.read_record` and
`runner.load` also read v1; unavailable historical support remains `None`, while
stored coordinates and methods are retained. Existing records are not rewritten.

`compare.paired_sampling_scores` aligns by observation ID and retains the original
parent-valid population. It reports lost and recovered IDs, a common-population
score, unchanged-operator scores, changed-operator scores, and relocated/fallback
scores. Its complete candidate score is unavailable if any parent-valid point
is missing. Unchanged-operator scores require matching actual points and methods,
and the requested physical height in both arms. Unknown historical coordinates
or methods cannot qualify as unchanged. Input measurements use their documented
normalization; each simulation supplies its own scale.

The opt-in `aij.sampling_geometry.summarize_result` reports physical/represented
bounds and roof heights for isolated rectangular ground footprints, and local
bounded voxel passage widths and horizontal physical clearances. General or
overlapping ownership stays explicitly unavailable. `runner.run` accepts
`geometry_diagnostics=True` to save this summary. Geometry diagnostics never
change rasterization.

New run records also identify the actual imported native extension by its path
and SHA256. The execution fingerprint includes that binary even when an editable
installation stores it separately from the Python sources. Older records retain
their original identities; unavailable historical native identity is not inferred.

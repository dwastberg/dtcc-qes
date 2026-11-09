# Fixed mean stress construction results

> Historical research protocol/results, retained from `54ccb39`. Reproduction
> commands with research-only build paths describe that revision. The portable
> tools and current integration qualification are documented in
> [REFERENCE_INTEGRATION_RESULTS.md](../docs/REFERENCE_INTEGRATION_RESULTS.md).


Executed 2026-11-09 under the
[three-arm protocol](FIXED_MEAN_STRESS_REPLAY_PROTOCOL.md). All eighteen
archived mean fields were replayed, covering 6,412 computed source-cell
instances and 4,950 saved observation/height-query instances per arm. All 162
indexed original archive files pass checksum verification. No AIJ, wind or
turbulence solve was launched, and no runtime formulation was changed.

**Bounded-consistent construction repairs the captured validity failures, but
does not improve the measured D turbulence predictions.** In particular it
cannot repair V2's 28.3% Y-origin vertical-variance regression on these fixed
mean fields. E60 is recovered locally; this does not qualify its turbulence
accuracy or the canyon/covariance composition.

## Arithmetic and sampling qualification

The arms are the captured legacy construction, spectral-only bounding of its
post-anisotropy tensor, and the previously specified bounded-consistent
construction with coupled production limiting and spectral bounding. Existing
anisotropy, measured inflow, native gradients and mixing lengths are fixed.
No negative eigenvalue is projected away and the validity tolerance is unchanged.

The legacy arm reproduces raw public stress interpolation and validity masks
exactly at all saved observations and at the selected primary probe locations.
Requested/selected coordinates and contributor weights stay fixed. Newly valid
locations are reported separately from each mean field's legacy-valid score
population. Missing or uncomputed support remains unavailable.

A pure native helper checks all computed captured inputs using the production
constitutive/spectral functions and captured rotation/multiplier values. Its
largest scaled difference from the Python replay is 1.0832e-7, below the frozen
16-float32-epsilon envelope of 1.9073e-6. There are no source-validity
classification disagreements. This is constitutive arithmetic replay; the
guarded native canyon/covariance combination was not enabled.

## Local validity improves

| Construction | Invalid computed source instances | Spectral-bound violations | Lost parent-valid primary probes |
| --- | ---: | ---: | ---: |
| Legacy | 8 | 180 | 0 |
| Spectral only | 3 | 0 | 0 |
| Bounded consistent | 0 | 0 | 0 |

These are the 6,412 captured instances, not a whole-domain rate. A component-wise
bound does not necessarily constrain the tensor's spectral radius, explaining
the separate legacy bound count. Spectral scaling protects an already valid
tensor but cannot generally rehabilitate an indefinite input. Coupled production
limiting addresses the additional pre-bounding failures here.

The remaining spectral-only invalid sources occur in D45 and the legacy
E WSW-after mean field. Bounded consistency eliminates all of them. Primary
recoveries include D45 site 75 in both mean fields, E WSW-after legacy sites
50/57, and E WSW-after V2 sites 57/60. These cohorts supply validity evidence;
those oblique/E measurements do not supply observed three-component variances.

### E60 retains the distinction between contributor and interpolant validity

For the frozen E WSW-after V2 mean field, site 60's legacy interpolant is
positive semidefinite. Nevertheless, 12.5% of its interpolation weight comes
from an invalid source, so the public result correctly remains invalid.
Both replay alternatives make all positive contributors valid and recover the
sample. The interpolated diagonal components change from approximately
(1.0011,1.0151,0.4916) m²/s² to (0.7345,0.9664,0.2491) with spectral-only
bounding and (0.8392,0.9720,0.2722) with bounded consistency.

This is a real validity repair. There is no measured E covariance against
which those alternative values can be accepted as accurate. Its mean velocity
and construction-change prediction remain the same frozen V2 values.

## D accuracy is unchanged by either replay repair

Each D0 mean field retains its 33 measured locations. Under that same mean
field, all three constructions have identical k and diagonal-variance scores.
The common-population V2-versus-legacy changes therefore remain:

| Origin | k RMSE change | xx RMSE change | yy RMSE change | zz RMSE change |
| --- | ---: | ---: | ---: | ---: |
| Reference | -6.697% | -7.515% | -2.982% | -3.662% |
| X+1 m | -7.978% | -8.597% | -3.642% | -9.654% |
| Y+1 m | +0.102% | +3.006% | -1.545% | **+28.301%** |

Negative values indicate improvement. These changes arise from the different
captured mean fields, not from the replay covariance arms. Spatial correlations
and the main failed protections are likewise unchanged by the repairs.

The Y-origin sites 48/58 remain the dominant vertical-variance errors. Their
contributing tensors are already valid, with inactive energy and spectral
bounds. The [manufactured support-edge shear](MANUFACTURED_RECONSTRUCTION_RESULTS.md)
is a plausible general mechanism worth distinguishing from mean-flow physics,
but this replay does not attribute those two measured sites to that particular
manufactured boundary or actor.

## Decision and verification

The validity rationale for coupled limiting remains supported. It does not
resolve missing incoming energy, spatial/component organization, inaccurate
mean flow or the previous A/B correlation failures. Keep the earlier physical
admission decisions. No combined candidate, default change, gust interpretation
or corrective AIJ pilot is justified by this local replay.

Sixteen targeted Python tests and three native covariance/stress/kernel checks
pass. They cover raw arithmetic, fixed populations, positive-weight source
validity, missing support and the reference-export statistical utilities.
The [Surrey reference audit](SURREY_REFERENCE_AUDIT_RESULTS.md) completes the
other authorized prerequisite investigation; no independently eligible
retained-energy reference is admitted.

Evidence and reproduction:
[archive index](../docs/data/next-pedestrian-campaign/stress-reference-audit/README.md),
[stress replay tool](replay_fixed_mean_stress.py), and the immutable
[original V2 archive](../docs/data/physical-canyon-v2/README.md).

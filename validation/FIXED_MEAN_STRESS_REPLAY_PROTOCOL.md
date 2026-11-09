# Fixed mean stress replay protocol

> Historical research protocol/results, retained from `54ccb39`. Reproduction
> commands with research-only build paths describe that revision. The portable
> tools and current integration qualification are documented in
> [REFERENCE_INTEGRATION_RESULTS.md](../docs/REFERENCE_INTEGRATION_RESULTS.md).


2026-11-08. Replay all eighteen frozen physical-canyon-V2 captures. Hold each
captured mean field, native gradient, mixing length, observation coordinate and
anisotropy fixed. There are exactly three arms: captured legacy P0A0C0;
spectral-only P0A0C1 on the captured post-anisotropy tensor; and the already
specified bounded-consistent P1A0C1. No new limiter, coefficients or eigenvalue
repair. Zero new AIJ, wind or turbulence solves.

Check original archive hashes and every computed captured contributor. Require
exact legacy final raw-tensor interpolation and masks at archived observations.
Keep raw finite but indefinite interpolants visible. A positive interpolant
cannot conceal an invalid positive-weight contributor. Missing or uncomputed
support is unavailable, and recoveries are separate from baseline-valid scores.

The pure native helper uses production constitutive/spectral inline functions
and the captured rotation/multiplier values. Compare reconstructed legacy
post-anisotropy, spectral-only and bounded-consistent tensors against the Python
replay within the existing 16 float32-epsilon scaled envelope. Require identical
source validity classifications. This checks constitutive arithmetic, not a
stacked native canyon/covariance solve.

For every arm report finite/source/interpolant validity, eigenvalue minima,
spectral radius relative to the stored bound, half-trace and component values.
Score only the 33 D0 measured vector/variance locations, at all three origins
and both frozen mean formulations, on each mean field's legacy-valid population.
Report k and xx/yy/zz RMSE/correlation independently. Also compare V2 and legacy
means under the same replay arm on the common original valid population.
D oblique thermistor and E observations do not supply measured component
variances; do not substitute their speed measurements for turbulence accuracy.
Preserve E60 recovery and D Y sites 48/58 individually.

Replay all saved height counterparts and observations for coverage, but do not
score unmeasured heights. Check the previous 5% component-error and 0.02
correlation protections diagnostically. A validity repair does not admit a
composition or promote the earlier physically failed covariance mode. These
local captures cannot establish whole-domain stress validity, gust accuracy or
annual pedestrian comfort. Freeze source identities before execution and retain
any failed analysis attempts.

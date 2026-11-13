# Wake comfort assessment, 2026-11-13

The registered M2 candidate does not pass C4. Keep `wake=2`, vector comfort
speed and `pedestrian-v1` as the defaults. This is a rejection of the proposed
switch on the available evidence, not a completed tower-remedy study.

## C1: reproducible baseline

`run_wake_validation.py --no-run` now assesses the stored W4 fields through
`comfort.assess`: 150,000 deterministic Weibull quantile hours, 16 equal sectors
and all 16 registered dominant-sector rotations. The discrete-hour level search
reproduces 6.75/7.80/9.25 m/s before and 5.60/6.50/7.75 m/s after.
The weight is 3; the paired 4,000-probe-resample bootstrap uses seed 20261113.
Its maximum is recomputed across all rotations in each resample. Missing runs,
nonfinite fields and mismatched paired sampling cannot yield a complete report.
Height mismatch warnings are retained. M2's registration was committed in
`dcb2337` before this implementation or its first assessment run.

The JSON report records exact agreement, optimistic/conservative shares, mean
absolute class error, Spearman rank correlation (average ranks for ties), missed
and false safety warnings, every climate's cost, worst-rotation interval, probe
classes, run keys and native identities. These are development-case results;
M2 was designed using these observations and is not independently confirmed.

The W4 inputs retain their historical fixed-work settings and native identities.
They are not presented as fresh runs under the current adaptive stop rule.
No native physics or identity-bearing product source changes in this work.

## C2: comparator decision and limits

F14 already established that the AIJ thermistor agrees more closely with RMS
speed than with a Gaussian time-mean magnitude. Retain the RMS comparator for
AIJ thermistor validation. The review's fast-half 9% difference is an additional
instrument observation, not a newly discovered RMS result.

A validation-only Gaussian mean-speed estimator now integrates E|U| with
standard-deviation ratios 2.4:1.9:1.25 in the horizontal mean-flow frame and
variance sum 2k. A one-dimensional Laplace-transform quadrature avoids a large
three-dimensional tensor. Tests check zero turbulence, rotation, Jensen bounds,
NaN propagation and convergence with quadrature order. Both estimates are
reported for A/B/D/E and the Gaussian estimate is included in C1.

For product comfort, retain the existing mean-vector comparator. The
[City of London guideline](https://www.cityoflondon.gov.uk/assets/Services-Environment/wind-microclimate-guidelines.pdf)
requires time-averaged mean and gust measurements and separate mean/GEM
assessments; it does not define RMS as a substitute for the mean. The
[NEN catalogue](https://www.nen.nl/en/nen-8100-2006-nl-107592) does not expose
sufficient text to settle the norm/averaging convention. Thus the sources do
not justify promoting RMS or the model-dependent Gaussian expectation to a
new criterion default. The Gaussian calculation is sensitivity evidence, not
a claim of NEN compliance. C2's precise NEN interpretation remains open;
no `scalar_mean` public option is introduced.

## C3: cavity and direction diagnostics

The frozen E2 spurious-decrease group contains 89 probe-direction pairs. Its
intersection with the measured Case E-after windy tenth is **15 of 135**.
The join uses probe IDs and direction labels, not row positions alone. The
original manifest hash, the intersecting IDs and a portable copy of the join
inputs are archived in `docs/data/wake-comfort/`. Reproduce the join with:

```
.venv/bin/python validation/check_wake_cavity_overlap.py docs/data/wake-comfort/cavity-mask.json
```

This establishes overlap, not a causal share of wake=3 error. The earlier
75% near-cavity attribution was measured on wake=2 and cannot be transferred
numerically to wake=3. The review's 78/135 tower corner-stream classification
is geometric evidence, also not an additive causal attribution.

`run_wake_flanks.py` implements the declared H4 diagnostic at all 16 Case E-after
directions for wake=3: two new flank solves per direction, at ±5°, and the
unweighted mean of the centre and flanks. Flanks retain the centre's numerical
settings and probe sampling. They have distinct run keys; observations are
compared only at the centre. This tests sensitivity, not an independently
validated angular-averaging remedy. It does not qualify Case E-before or wake=2.

The H4 run changes windy-tail bias from −24.546% to −24.529%, while the
share more than 20% too slow rises from 64.44% to 65.19%. Overall MAE changes
from 0.13295 to 0.13065 K. There is no useful windy-tail remedy in this stencil.
All 32 flanks reached the registered 2,000-sweep cap without meeting the legacy
multiplier-change tolerance (as did the centre runs); this is a comparison at
the W4 work budget, not convergence qualification. Native identities and
solver diagnostics are archived with the flank summary.

## Work still required before a default switch

- C2: obtain an authoritative NEN definition of the speed statistic.
- C3: port and parity-check the research cavity attribution against the split
  wake implementation; run the H2 shelter/shadow ablations. Causal shares remain
  unestablished. F13 must accompany the tower investigation.
- C4: M2 fails; F08/F13 on both wake codes remain the separate tower-remedy work.
  E0d's research P0 result is encouraging but is not current wake=3 parity.
  No literature constant has been tuned to D or E here.
- C5: Hamburg request remains unsent; no agreement signed and Michelstadt
  remains untouched. The project-lead draft in the research checkout needs
  sender details and explicit authorization before sending.
- C6/C7: conditional on a passing remedy and independent confirmation; neither
  a new policy qualification nor a default switch is justified yet.

The active worktree and historical `build/fabel-wake` are retained. Deleting
these or the research checkout's untracked draft would discard material still
needed by the research work; cleanup is deferred until after integration.

## Recorded C1 decision table

| State | Scale | M2 T [95% interval] | Missed risk, M2 / default | Cost gate |
|---|---:|---|---|---|
| before | 6.75 | -0.7125 [-0.7625, -0.5375] | 0 / 0 of 0 | pass |
| before | 7.80 | -0.3375 [-0.4000, -0.2000] | 0 / 0 of 0 | pass |
| before | 9.25 | -0.1125 [-0.1750, 0.0500] | 0 / 0 of 1 | fail |
| after | 5.60 | -0.2750 [-0.4000, 0.0500] | 3 / 3 of 3 | fail |
| after | 6.50 | 0.0375 [-0.2250, 0.3500] | 4 / 4 of 7 | fail |
| after | 7.75 | -0.0875 [-0.2250, 0.2000] | 3 / 2 of 20 | fail |

M2 also fails the windy-tenth slow-share gate in both Case E states. All 18
original W4 gates still pass. Candidate failure is recorded separately from
the wake model regression gates; a successful harness exit does not approve M2.

Evidence: [C1 and W4 summary](../docs/data/wake-comfort/c1-summary.json),
[H4 flank summary](../docs/data/wake-comfort/flanks-summary.json).

Verification: 337 tests passed, 5 skipped across the validation suite and
comfort/wake product tests; the final focused wake suite passed 9 tests.
The four warnings are dependency deprecations from laspy.

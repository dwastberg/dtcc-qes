# Reference sampling and validity integration

Target: `main` at `eef9c6c`; research preserved at `54ccb39`.
The integration is selective. It contains the portable Surrey/reference audit
and frozen-mean analysis tools, declared-height reference sampling with float64
accumulation and explicit support telemetry, and the boolean PSD certificate
with unchanged classifier fallback. No new covariance, incoming-energy or canyon
runtime formulation is included.

## Declared numerical change and acceptance

Reference interpolation intentionally changes friction velocity, the cap and
potentially capped stress, energy, dissipation and their derivatives. Existing
mean velocity, geometry, projection work and solver decisions must remain exact
against main. Turbulence-disabled outputs must remain exact. Morphometry,
roughness, displacement, rotation-height policy, gradients and closure equations
remain fixed. Reference targets below the first centre now fail planning with
a first-layer refinement message; empty/nonfinite fluid support fails explicitly.
The conservative existing upper-layer/15 m domain margin is retained.

Acceptance requires independent manufactured point/vector/refinement tests,
mixed-mask and exact-centre support tests, a direct independent reduction of
production metadata, frozen Surrey cap/stress replay, and a fresh Surrey
benchmark comparison. The stress-validity shortcut must agree exactly with the
original classifier on boundary/random inputs and extracted raw tensors. It
must not alter any tensor or tolerance. End-to-end performance is measured
separately from classifier microbenchmarks.

Release gates are the applicable full warning-strict Python/validation suites,
native OpenMP/serial/sanitizer checks and symbol audits, the existing 429-case
matrix at 1/2/4/8 threads plus serial (with only the declared turbulence change
against main), combined feature checks, 24 frozen adaptive policy workers, and
isolated sdist/wheel installation and runtime checks. Native identity is promoted
only after qualification. Historical reports remain identified as research
results; larger immutable evidence is indexed by revision and SHA-256 rather
than imported into main.

## Integration decision and scope

The three changes are ready for integration. Implementation commits are
`292f659` (portable tools), `f81d905` (reference correction), and `87a48fb`
(equivalent validity extraction). The qualified native identity is
`04c8ce764b2014e3f671bede5b69f6e8782006f446b0470571911024733fa9ed`
with AppleClang 17, Release, floating-point contraction on, and normal canyon
failure hooks off. Both serial and OpenMP builds have that identity. Native
qualification was first enabled only in an isolated source copy and promoted
in production after the applicable gates passed.

The main comparison found that reference sampling was still the face-based
lookup/float32 reduction. The certificate existed only on research and was
wired into a failed optional covariance model there. Surrey protocols also
passed `covariance_model: legacy`, unsupported by main. The integration ports
these tools through a strict legacy-only adapter and existing evidence utilities,
then enables the certificate directly in legacy output extraction. Offline
alternative covariance equations are confined to validation code and a test-only
header; they are absent from the runtime and public settings.

The turbulence numerics identifier is now `dtcc-qes-turbulence-v2`, so dataset
request identities reject the older numerical epoch. This identifier records
the reference correction. Physical-pairs V2 canyon application, incoming energy,
bounded-consistent runtime covariance, gradient smoothing, actor composition and
rotation-height changes remain excluded.

## Corrected estimator and support

Production interpolates U/V/W components between physical cell centres at the
declared height, takes each complete column's vector magnitude, then averages
in float64. Existing face-pair addition, final float32 scalar export, sorted
float32 morphometry, z0/d formulas, friction logarithm and conservative upper
margin are preserved. The ground ghost never participates. Exact-centre
requests use one source. A solid/terrain positive-weight source excludes its
column. Nonfinite velocity in complete fluid support, no complete columns, and
out-of-centre support produce explicit errors. Below-first-centre requests fail
both Python planning and native preparation with a first-layer refinement
message; adding layers above the domain cannot fix that support problem.

`result.metadata['turbulence']['reference']['sampling']` records physical
zero-based lower/upper indices, heights, weights, valid/excluded columns,
float64 mean and the sampling/accumulation policy. No per-cell array is added.
Native support tests cover mixed roof/terrain masks, exact-centre collapse,
turning vectors, nonfinite inputs, empty support and 45,056-column reduction.
The production probe repeats the 48 independent manufactured field/grid/face
perturbations, including the curved-field second-order result.

## Numerical, physical and cost results

- The 429-case matrix passes the declared impact audit on main/candidate pairs
  at 1/2/4/8 OpenMP threads and serial. Mean fields, coordinates, flags,
  computed populations, mixing lengths, solver work and diagnostics are exact.
  Only declared reference-dependent turbulence arrays/scalars and support
  metadata differ. Candidate fields are exact across all thread/backend pairs.
  The auditor has rejection tests for mean-flow, morphology, finite-support
  and computed-population changes.
- The certificate alone preserves all 4,783 stored records exactly against the
  saved corrected-sampler build before optimization, apart from its declared
  native identity. Boundary/random/sanitizer tests retain the original Jacobi
  classifier fallback and tolerance. Raw tensors are never changed by validity
  classification.
- All 31 combined feature intersections pass the same impact audit, including
  four adaptive intersections. All 24 frozen S7 workers preserve exact fields,
  work, assessments, histories, reasons and acceptance; only the declared
  identity and pre-existing disabled-monitor metadata exception apply.
- The fresh Surrey background benchmark completes all 26 solves; the geometry
  benchmark completes all ten workers. All numerical/geometry/support guards
  pass. All six directly comparable reference speeds and all sampled stresses
  equal the frozen corrected-reference predictions exactly. The earlier
  coarse/fine street reference-speed discrepancy falls from 1.5539% to 0.0114%,
  and the cap discrepancy from 3.1320% to 0.0227%. Fine street developed physical
  k remains 4.3704 times measured. Shifted-array strict turbulence scores retain
  ten invalid-source probes on each grid and remain incomplete.
- Portable offline replay reproduces the four reference arms without new flow
  solves. The independent fixed-mean stress helper reproduces the 18 historical
  mean captures and their source-validity decisions. Those alternative closure
  analyses retain their failed physical acceptance status.
- Five fresh paired AIJ conditions at 2 m (A, B, D 0 degrees, E WSW before/after)
  preserve whole mean-field hashes, every canonical mean probe, grids and solver
  diagnostics exactly. These ten workers use matched fixed work and remain
  non-converged; this is a directed check, not a full AIJ validation rerun.
- Three balanced cost rounds retain 15 measurements per arm/category after
  warmups. Median public-call time is 4.89 to 4.69 ms for wind-only, 24.56 to
  10.97 ms for combined turbulence, and 25.81 to 25.90 ms for export. None
  exceeds the existing joint 10% and 0.01 s regression threshold. The 55.3%
  combined-call reduction is specific to this small fixed-work case. The
  single paired AIJ native timings are also lower but do not establish a
  general urban-model speedup. Paired RSS changes range approximately -2% to
  +4.7%; no new per-cell storage is introduced.

### Additional invalid-source witnesses are an accepted limitation

The reference correction intentionally changes the legacy cap. Directed A loses
one formerly valid strict stress sample (site 1015, z=34 m), and E-after loses
one (site 60, z=2 m). Invalid sample counts change 41 to 42 and 2 to 3,
respectively. B remains 28; D and E-before remain zero. Both newly rejected
interpolants are PSD; positive-weight source covariances are indefinite. These
samples are kept in the population and marked incomplete rather than dropped
from an accuracy score.

Four ordered recaptures preserve the directed whole mean hashes and show exact
unchanged gradients, mixing lengths, viscosity, rotation and uncapped energy.
Independent constitutive replay reproduces validity exactly (maximum scaled
anisotropy reconstruction error 2.25e-8). All three witness source tensors are
PSD after anisotropy in both arms. Final component clipping produces corrected
minimum eigenvalues -0.20858/-0.06373 in A and -0.33596 in E, whereas the previous
source values were positive. Lower capped internal energy and the lower component
bound expose the existing component-cap defect; the boolean shortcut is exactly
equivalent and does not cause it.

This numerical correction does not qualify covariance physics or pedestrian
comfort accuracy. The additional invalid-source witnesses are documented as a
real coverage regression. Keeping an incorrect reference height to hide the
component-cap defect would not repair that defect. Covariance construction and
capping remain the next physical investigation, using these frozen witnesses.

## Release verification and evidence

The warning-strict full suites pass 2,100 tests on each serial/OpenMP package;
16 archived lexicographic/toolchain fixtures skip on each. External A/B data and
explicit native executable paths were supplied, closing the other collection
skips. The five later impact-auditor tests pass separately; the 48-case focused
portable/audit suite and 39 installed-wheel checks pass. Native CTest passes
61 OpenMP, 58 serial and 58 Debug ASan/UBSan checks, including the new certificate
and support/manufactured checks. All three native symbol audits pass.

An isolated sdist and a wheel built from that sdist pass the CPU-only,
source/license and immutable-evidence artifact checker. Build dependencies use
the existing Python environment and Unix Makefiles; no runtime dependency was
added. The actually installed isolated wheel has the exact qualified source
identity, accepts the frozen adaptive policy and matches every field in the
429-case compiled-candidate matrix. After qualification promotion, a rebuilt
release wheel repeats artifact and runtime checks. Its packaged production
source matches promoted source byte for byte, including the qualification header.
The user's original installation is preserved.

The compact [qualification summary](data/reference-integration/summary.json),
[evidence index](data/reference-integration/verification.json) and frozen native
build identity record the exact inputs, outcomes, artifacts and checksums.
Historical larger research archives are separately indexed by Git revision and
SHA-256; importing them is unnecessary for ordinary unit tests. Current native
captures and strict witness records are retained without modifying earlier
research evidence.

The rebuilt installed release wheel passes the complete warning-strict suite:
**2,105 passed, 16 historical toolchain/order skips, zero failures**. The increase
from 2,100 includes the five impact-auditor rejection tests added during review.
Its 429-case arrays match the compiled candidate exactly after rebuilding.
Production source after identity promotion passes all 61 native checks again
and the qualified runtime smoke check. The selected stack was fast-forwarded into local `main` at `9b97ecc`.
Post-merge checks verify every declared changed-code hash, every native policy
build input and the compact research checksums against the qualified candidate.
Running main's runtime smoke tool against the rebuilt, installed release wheel
passes with the exact qualified identity and adaptive acceptance enabled. The
[merged-main verification](data/reference-integration/merged-main-verification.json)
records the source commit and actual imported module. The subsequent audit
commit changes documentation/evidence only. The research checkout, its unrelated
files and the user's original installed package are preserved. No remote push
was requested or performed.

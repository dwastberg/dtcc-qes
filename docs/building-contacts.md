# Touching and overlapping buildings

Touching and overlapping footprints need both height-preserving geometry
preparation and parameterizations that respect exposed walls. Removing the
Python contact rejection alone exposes dependence on how a building is split
into source polygons. Even a gap that passes that rejection can disappear on
the numerical grid.

This work concerns generic building geometry: terraces, extensions, height
steps, towers on podiums, courtyards and disconnected multipart footprints.
Its acceptance fixtures are synthetic. AIJ conversion, case runs, parameter
tuning and measurement validation belong to separate work.

## Current behavior

`wind.run` and `wind.preview_grid` accept `footprints=wind.Footprints(...)`
for touching, overlapping, multipart and holed LOD0 footprints. The default
`footprints=None` retains strict disjoint, hole-free Surface input. Building
parts and nested buildings remain unsupported. Strict inputs with gaps smaller
than a grid cell record `near_contacts` and log one diagnostic per request.

```python
from dtcc_qes import wind

policy = wind.Footprints(min_detail=0.5, exposed_faces=True, fallback="error")
preview = wind.preview_grid(city, footprints=policy)
result = wind.run(city, 5.0, 270.0, footprints=policy)
```

`min_detail` is a positive cleaning tolerance in metres, independent of the grid.
The default is 0.5 m; 0.01 m is useful for precise input. `exposed_faces=False`
retains canonical geometry and ring handling while disabling the exposure rules.
`fallback="tallest"` accepts a failed wall partition at the largest resolved
source height and records volume accounting; the default raises instead.
Source mappings and cleaning details are in `result.metadata["footprints"]`;
final solids are also in `result.metadata["solids"]`. Preview carries the same
footprint metadata in `preview.domain["footprints"]`.

The solid mask is assembled from the union of building occupancies. Empirical
parameterizations also use each source polygon's edges, dimensions, centroid
and height. Equal solid masks therefore do not imply equal parameterizations
or equal velocities. Exact equivalence is tested for equivalent
canonical solids, rather than for arbitrary geometries sharing a solid mask.

## Reproduce the baseline

With this checkout's Python package and native extension installed:

```sh
uv run --frozen python tools/contact_artifacts.py \
  --footprints baseline --exposed-faces off \
  --output build/contact-artifacts.json
```

The baseline mode temporarily bypasses only the adapter's contact rejection
for each synchronous solve. Ring, height, precision, domain and native input
checks remain active. The bypass is restored when the solve returns or raises.
Run the tool in its own process; it temporarily replaces a module function and
is not intended for concurrent use within an application.

The tool prints a table and writes JSON containing every rectangular prism in
input order, the settings, comparison metrics, solver diagnostics, effective
grid, parameterization settings, package/native versions, source hashes and
native binary hash. Each distinct geometry is solved once per invocation.

For a quick execution check rather than a numerical baseline:

```sh
uv run --frozen python tools/contact_artifacts.py \
  --case split --resolution 4 --iterations 2 \
  --output build/contact-smoke.json
```

`--case` may be repeated to select comparisons. `--footprints strict` exercises
the actual public contract and records rejected contacting inputs in the JSON;
it does not bypass the check. `--footprints resolve`, `--min-detail`, and
`--exposed-faces on` configure the resolved comparison. Resolve mode uses
the public pipeline; exposure-on is available in resolve mode. Baseline and strict modes require exposure-off. `min-detail` is recorded as
null in baseline/strict mode because neither performs footprint cleaning.

The complete baseline uses a 240 × 120 × 100 m domain and a uniform 1 m grid.
Wind comes from 270° at 5 m/s, referenced at 10 m with roughness length 0.1 m.
Building parameterizations retain their defaults. All solves use float32 and
a maximum of 1500 iterations with tolerance equal to float32 epsilon.
This is a fixed-budget artifact experiment: convergence and actual iteration
counts are recorded, and every comparison reports whether its iteration counts
match. These results do not establish convergence or physical accuracy.

At each native horizontal cell centre, velocity is interpolated vertically to
2 m before computing speed. Differences are absolute speed differences divided
by 5 m/s. Maximum and RMS are computed over all common valid fluid samples,
including the prescribed boundary region. Solid-mask equality and changed
fluid parameterization flags are checked over the full three-dimensional grid.
The JSON also records whole-volume velocity hashes and exact flag equality.

## Synthetic geometry

The reference block occupies x = 60–100 m, y = 50–70 m, at height 10 m.
The across-flow split divides it at x = 80 m; the parallel split divides it at
y = 60 m. The subcell-gap example translates the eastern half 0.3 m east;
the separated control translates it 3 m east. The near-equal-roof example
lowers the eastern half to 9.9 m. The overlap example covers the whole block
with a 6 m prism and places a 10 m eastern half over it; its partitioned
counterpart removes the overlap from the lower prism. The inset example moves
the eastern half's two y edges inward by 0.05 m. The two stepped examples use
6 m and 10 m halves in opposite upstream/downstream arrangements.

Reversed fixtures reverse input order, preserving all physical coordinates.
The fixtures and their exact ordered coordinates are in the tool and in the
saved JSON. Their masks are measured, not assumed: changing resolution can
change whether a narrow gap is represented by fluid cells.

## Recorded baseline

The reproducible run is saved in
[`data/building-contacts/baseline.json`](data/building-contacts/baseline.json).
The table below is generated from that artifact. The earlier scratch numbers
in `BUILDING_UPDATE.md` lacked a complete saved recipe and are historical
observations, not exact numerical regression targets for this run.

| Comparison | Max Δspeed / Uref | RMS Δspeed / Uref | Same solid mask |
| --- | ---: | ---: | :---: |
| `split` | 0.459622 | 0.018239 | yes |
| `split_reversed` | 0.135232 | 0.013124 | yes |
| `split_parallel` | 0.523073 | 0.030338 | yes |
| `subcell_gap` | 0.456174 | 0.018897 | yes |
| `gap_order` | 0.590180 | 0.018523 | yes |
| `separated_order` | 0.000000 | 0.000000 | yes |
| `near_equal_roofs` | 0.460659 | 0.018043 | yes |
| `overlap_partition` | 0.135212 | 0.009651 | yes |
| `overlap_order` | 0.000000 | 0.000000 | yes |
| `inset` | 0.038883 | 0.001031 | yes |
| `step_down` | 0.200651 | 0.015739 | no |
| `step_up` | 0.399173 | 0.021248 | no |

## Python preparation pipeline

The adapter resolves each source height before cleaning flat copies,
then consumes height-preserving cells from dtcc-core. Multipart sources are
expanded into separate Surfaces before cleaning to preserve disconnected
components, holes and original source attribution without an upstream change.
Fallbacks either raise or explicitly use the maximum resolved source height;
the latter does not assume that Core's fallback height is always the maximum.

`prepare_footprints` returns sources and cleaned cells in a float64 anchor frame.
It records excluded and covered components, including partial exclusions within
a multipart source. Cleaning failures name original sources and retain the
upstream error as their cause. Fallbacks are identified by the explicit block
outcome. Their volume accounting integrates the original upper envelope within
the output footprint, counting overlap once; it does not measure material lost
outside that footprint. Fallback counts are per block, not per output polygon.

After the effective vertical grid is known, `finalize_footprints` unions cells
in the same cleaned block with the same represented roof. It accepts final
`effective_faces`, global `origin`, horizontal `resolution`, physical
`shape=(nz, ny, nx)`, and the explicit flattening policy `terrain`. Ground checks
use all original sources, including covered and excluded ones. It checks domain
clearance and float32 geometry, permits contact, and rejects shared area before
and after narrowing. It returns current-bridge arrays and metadata mapping every
source to its final solid indices, together with represented roofs and errors.

Ring winding, starting vertices and component order are deterministic. Exact
redundant vertices are removed, while shared boundaries retain identical
T-junction vertices on both sides. Equal-roof split and single-block fixtures
produce identical native geometry arrays. No geometry is snapped to the grid.

Finalization emits building vertex offsets and ring vertex offsets into one
shared closed-ring array. Outer rings are clockwise and holes counter-clockwise.
The native bridge checks topology again after float32 conversion. Every native
face loop and downstream canyon search respects ring boundaries; jumps between
rings are never faces. Courtyard walls can seed parameterizations. The outer
ring supplies the vertex-average centroid, and net area supplies wake dimensions.

Grid planning and finalization iterate until the planner's geometry and heights
match the final solids. This also gives turbulence the finalized mean building
height. An unstable automatic-grid dependency raises an error recommending
explicit vertical faces after at most 16 passes, rather than silently planning
for a different collection of buildings. Neither preview nor geometry
preparation allocates native wind arrays.

## Native exposure rule

For a candidate seed, project its position onto the source face segment. Trace
that face's outward unit normal through grid cells using a deterministic DDA;
when both grid boundaries are reached together, advance both indices. At a grid
boundary the ray starts on the outward side using `nextafter`. Skip cells whose
centres lie in the original source footprint, using the same float32 even-odd
rule as rasterization. The first outside centre must be fluid in the initial
solid mask. Own solid ahead of the wall blocks the ray rather than being
skipped, so unresolved courtyards and concave notches cannot expose walls by
tracing through another part of the same source. This decision uses neither
mutable parameterization flags nor the
cell's input-building ownership. It is evaluated at each vertical level, so a
wall shared below a neighbor's roof can become exposed above it.

Upwind cavity and wake test staggered samples; sidewall tests its originating
upwind corner and its velocity samples, restoring eligibility at each level.
Wake and canyon searches skip source-footprint cells before reaching fluid and
stop at a solid neighbor. Canyon searches cannot reuse a stale downstream face.
Rooftop support must belong to the source footprint for holed solids and in
exposure mode. Collinear shared topology nodes remain in mask membership but do
not split canonical parameterization faces, with exposure either on or off.

Compatibility is checked on named fixtures. A fluid gap alone is not a universal
promise of bitwise equivalence between exposure modes: corner eligibility and
other parameterization interactions can also change. The default strict
single-ring path keeps legacy parameterization behavior; safety checks for
bounds and nonfinite wake lengths also protect that path. Its existing reference
fixtures remain unchanged. No upstream changes are required beyond the existing
dtcc-core revision pinned in the lockfile.

The model remains empirical. These synthetic checks establish geometry handling,
mask consistency and deterministic numerical behavior; they do not establish
physical accuracy at height steps.

## Dataset integration

The dataset adapter shares preparation, grid stabilization and the native solve
with the in-memory API. Each request cleans exactly once; automatic-grid
planning reuses the prepared footprints until the canonical geometry stabilizes,
then solves once. The public strict mode retains its existing behavior.

Fetched geometry is copied into global EPSG:3006 coordinates. Original source
base elevations and measured/estimated height selection are retained. Ground is
determined before cleaning copies are flattened: explicit 3D bounds take
precedence, then valid terrain elevations, then original footprint elevations.
The query rectangle and cleaned extents are combined before padding once by at
least three effective horizontal cells. Explicit ground/top limits, roof
clearance and resource checks remain in force.

Dataset defaults are `Footprints(min_detail=args.min_building_detail,
exposed_faces=True, fallback="tallest")`. Source holes and cleaned-region
courtyards are filled internally; returned cell holes remain intact because they
can contain a taller tower. Multipart components and distinct source heights
survive preparation. Tallest-height fallback applies only to a reported wall
partition failure. Other cleaning, geometry, height, grid and solver failures
propagate. Fallback counts and excluded-source/component counts appear in dataset
health; fallback use also produces a context warning.

The realization's `preparation` uses schema version 2 and pipeline
`canonical-cells-v1`. Its `footprints` record contains source/component/part/solid
mappings, covered and excluded sources, fallback reasons and volume accounting.
`dtcc_core` records the pinned dependency revision. Legacy `blocks` and
`block_height_policy` records are removed. Shared simulation provenance also
retains the complete footprint record.

`filled_courtyards` and `source_courtyard_filled_area` measure original source
holes exactly. `courtyard_policy` measures occupied area and void area in the
input union **after source-hole filling**, and cleaned occupied area. Its net
area change also includes conditioning and exclusions. The pinned Core API does
not separately report holes filled after conditioning, so
`conditioned_region_filled_area` is explicitly `null`; it is not inferred from
net area change. No second cleaning pass or upstream changes are needed.

Dataset regression tests use fetched-city mocks and synthetic geometry. They
cover stepped overlaps, podium/tower mask occupancy, source and region filling,
multipart preservation, measured-first heights, ground/transforms, cleaned
bounds, fallbacks/exclusions, error propagation, field/slice products and direct
shared-pipeline parity. No live fetch or AIJ case run is required.

The dataset migration passed 959 tests in the complete Python suite, including
63 dataset tests. The OpenMP dataset/contact subset passed 78 tests with two
threads. Native regression checks passed in serial (40), OpenMP (43) and
address/undefined-behavior sanitizer (40) configurations. These results are saved
in [`dataset-verification.json`](data/building-contacts/dataset-verification.json).
Earlier baseline and resolved comparison artifacts below retain their original
capture counts and provenance.

## Checks

`tests/test_contact_artifacts.py` exercises the metric on manufactured data,
checks mask and iteration mismatches, runs small native comparisons, verifies
strict-mode rejection, and checks restoration of the contact rejection after
both successful and failed solves. Existing adapter tests guard the public
contract. No AIJ data is needed by the tool or these tests.

The serial Release extension built with Apple Clang 17 passed 160 tests across
`test_contact_artifacts.py`, `test_city_adapter.py`, `test_wind.py` and
`test_runner.py`. The complete recorded baseline contains 15 successful solves
and 12 comparisons; every comparison used 1500 iterations on both sides.
All recorded source hashes and the native binary hash were checked against the
worktree and build before generating the report table. The 3 m-gap order control
has exactly equal velocities and flags. None of these fixed-budget solves met
the requested float32-epsilon tolerance.

The completed Python pipeline passed 335 tests across footprint preparation,
the baseline tool, city adapter, wind, runner, dataset, vertical-grid and preview
suites. The added checks exercise multipart components and holes, fallbacks,
source accounting, shared junctions, float32 edge collapse/overlap, and final
faces from uniform, explicit and automatic grids with turbulence enabled. A
native bridge smoke solve accepts the finalized simple-ring arrays. The updated
dependency lockfile also passes `uv lock --check --offline`.


## Public and native integration checks

The full Python suite and serial/OpenMP native suites cover public opt-in and
strict contracts, exact equivalent-solid comparisons, overlap partitioning,
input permutations, corner and oblique contacts, courtyard masks, multipart
sources, turbulence/grid consistency and isolated reference parity. Native
`building_contacts` checks partially hidden walls at multiple heights, oblique
normals, initial-mask isolation, blocked wake/canyon/cavity propagation, collinear
parameterization faces, ring validation and near-closure vertices. It exercises
courtyards with both exposure settings and the modified canyon implementation.
Sanitizer builds check these paths with address and undefined-behavior checks.

The final serial run is saved in [`resolved.json`](data/building-contacts/resolved.json),
using `--footprints resolve --exposed-faces on --min-detail .01` with the
same 1 m grid and 1500-iteration budget as the baseline. Source, staged Python
and binary hashes were audited. All eight equivalent-canonical/order comparisons
have bit-identical full-volume velocities and flags. The subcell-gap, inset
and stepped comparisons remain geometry-sensitivity results, not equivalence
requirements or evidence of physical accuracy.

| Comparison | Max Δspeed / Uref | RMS Δspeed / Uref |
| --- | ---: | ---: |
| `split` | 0.000000 | 0.000000 |
| `split_reversed` | 0.000000 | 0.000000 |
| `split_parallel` | 0.000000 | 0.000000 |
| `subcell_gap` | 0.457082 | 0.013609 |
| `gap_order` | 0.000000 | 0.000000 |
| `separated_order` | 0.000000 | 0.000000 |
| `near_equal_roofs` | 0.000000 | 0.000000 |
| `overlap_partition` | 0.000000 | 0.000000 |
| `overlap_order` | 0.000000 | 0.000000 |
| `inset` | 0.139919 | 0.005366 |
| `step_down` | 0.491000 | 0.019312 |
| `step_up` | 0.464477 | 0.022478 |

Final verification: **949 Python tests**, **40 serial native checks**,
**43 OpenMP native checks**, and **40 address/undefined sanitizer checks** passed.
The OpenMP Python subset passed 131 tests and skipped eight existing serial-only
reference fixtures. See [`verification.json`](data/building-contacts/verification.json).
No AIJ cases or measurement validation were run. All experimental solves reached
the fixed iteration budget without meeting float32-epsilon tolerance.

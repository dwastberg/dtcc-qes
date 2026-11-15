# AIJ Case C: city-block validation

Case C now uses the same City construction, measured-profile inflow, RunSpec identity,
process-isolated runner, probe sampling, provenance and agreement metrics as Cases A/B.
The baseline comprises all nine combinations of centre height and wind direction.

## Run

```sh
uv run --group validate python validation/run_validation.py --campaign c_smoke --case C --jobs 2
uv run --group validate python validation/run_validation.py --campaign c_baseline --case C --jobs 2
uv run --group validate python validation/report_validation.py --only c
uv run --group validate pytest validation/tests/test_case_c.py -q
```

Additional campaigns are prepared, but are not required to execute the baseline:

| Campaign | Runs | Purpose |
|---|---:|---|
| `c_smoke` | 9 | All states/directions, 4 m |
| `c_baseline` | 9 | All states/directions, 1 m |
| `c_grid` | 18 | All states/directions at 4 and 2 m; compare with baseline |
| `c_fine` | 9 | Optional 0.5 m refinement with raised cell cap |
| `c_convergence` | 36 | 2/1 m probe histories and float64 endpoints, turbulence off |
| `c_sensitivity` | 81 | Nine separate changes across the nine baseline configurations |

Use `--list` to inspect run specifications before execution. The fine campaign can
require substantial memory; use one job. Sensitivity changes cover power/log inflows,
linear interpolation, larger domain/top, uniform layers, street canyon off, wake code 1
and rooftop code 2. Convergence and sensitivity evidence from A/B does not establish
convergence for C; these campaigns are prepared for that separate assessment.

Records and sampled planes go to `output/runs/C/<key>.{json,npz}`. Reporting writes
`output/report/{headline_c.md,case_c.json,c_scatter.png}`. Use `--resolution 4` or `2`
with the report command for a coarse baseline. Reports exclude missing/stale runs,
join measurements by point ID, and show finite-pair coverage. JSON includes the RMS
speed proxy separately, the no-building control, source and native provenance.
`build_cities.py` also writes `aij_c_0H`, `aij_c_1H`, and `aij_c_2H` Cities and maps.

## Workbook audit

Source: `AIJ_C/CaseC(City_blocks).xls`, resolved through `DTCC_QES_AIJ_DATA` when set.
The workbook itself remains the source of every numerical measurement.

- `Geometry`: embedded drawings, with three labels in row 31: Case 0H, Case 1H,
  Case 2H. The embedded compressed WMF figures were extracted and their polygon
  outlines inspected. The official measurement-layout image confirms the pitch.
- `Inflow!B3:E18`: 16 heights in mm and m, mean speed in m/s and streamwise RMS
  fluctuation sigma_u. Heights span 0.01–1.2 m in the tunnel. The other two variances
  are absent, so total k is unavailable; the reader returns NaN, not an isotropic estimate.
- `Results(0_deg)`, `Results(22.5_deg)`, `Results(45_deg)`, each `B3:H122`:
  point ID, x/y/z in model metres, and speed ratios for 0H/1H/2H.
  All three sheets share 120 distinct IDs and coordinates, giving 1,080 observations.
  The absent IDs are 1, 2, 3, 34, 35, 36, 37, 46, 55, 100, 101, 102.
- Every probe is at model z = 0.02 m. The sheet explicitly normalizes speed by
  the approach velocity **at the same height**, here 2.434 m/s (`Inflow!D4`).
  The cube-height speed 3.654 m/s is not this workbook's denominator.
- The official dataset documentation identifies thermistor mean scalar speed.
  These are not signed velocity components or vector magnitudes, unlike A/B.

## Geometry and conventions

The array has eight surrounding 0.20 m cubes, on a 0.40 m pitch, with centres at
x,y = -0.40, 0, +0.40 m. The central footprint is also 0.20 × 0.20 m;
its height is zero (omit the building), 0.20 m, or 0.40 m. There are no extra
upstream blocks or roughness elements in the City.

As in A/B, scale is chosen to put the pedestrian probes at 2 m: multiply model
metres by 100, preserving wind-tunnel speeds. Full-scale blocks are 20 m wide,
the pitch is 40 m, central heights are 0/20/40 m, and the array spans [-50,50] m.
All 120 probes are outside the buildings, with minimum wall distance 5 m.
No synthetic probes are inserted into the vacant centre of the 0H configuration.

The workbook coordinates are retained. Wind at 0 degrees flows toward +x;
positive angles are interpreted as turning toward **-y**, so meteorological
azimuth = 270 + angle: 270, 292.5, 315 degrees. This is a data-derived sign
choice, rather than copying the Case D angle mapping. For the 45-degree sheet,
mean absolute ratio differences between reflection pairs are:

| Centre | Reflect about y=-x | Reflect about y=+x |
|---|---:|---:|
| 0H | 0.0444 | 0.2145 |
| 1H | 0.0422 | 0.3174 |
| 2H | 0.0536 | 0.3304 |

The much closer symmetry about y=-x supports this choice independently of the
solver. The sign is tested against the source measurements. The convention must
be revisited if a replacement dataset changes the coordinate frame.

## Numerical setup and interpretation

The baseline uses the measured inflow with the A/B log-height interpolation and
fitted lower log tail, turbulence enabled, float32, and 6,000 iterations at 1 m.
Fixed-work budgets are inherited from A/B: 1,000/2,000/6,000/16,000 at
4/2/1/0.5 m. These budgets remain provisional for Case C until its convergence
campaign is assessed.

The horizontal domain is [-170,170] m in both directions, a 120 m margin around
the array. Symmetric padding accommodates oblique winds. All three centre-height
states share the same vertical grid: nominal top 200 m, uniform layers through
80 m, then growth 1.15 capped at four times the fine spacing. Roofs at 20 and 40 m
lie on vertical faces. The profile is held constant above its last measurement
at 120 m. Domain expansion is an explicit sensitivity variant; the baseline's
120 m margin does not establish downstream-boundary independence.

Scores use the existing D=0.25, W=0.05 hit-rate tolerances, FAC2, correlation,
fractional bias and error metrics. The no-building control is K=1 at every probe.
QES mean-vector magnitude and the thermistor's mean scalar speed are different
quantities. The separately reported sqrt(|U|²+2k) is an RMS proxy, not an exact
mean-scalar correction; invalid turbulence probes are excluded and their count
is retained. No turbulence validation, reverse-flow recall, direction-error or
reattachment-length score can be derived from these scalar measurements.

## Initial execution (2026-11-15)

Executed all nine 4 m smoke runs and all nine 1 m baseline runs using revision
`4c7a8dab3689` with the Case C adapter changes in this working tree. All completed
without execution failures; all 120 probes in every run were sampled without fallback.
The 1 m runs used 13.3 million cells each, approximately 2.8–3.4 GiB peak memory,
and completed the nine-run campaign in 192 seconds with two workers.

The mean-vector-versus-scalar hit rates span 0.092–0.450; these initial results
show substantial disagreement with the measurements. The complete table is in
[the generated baseline report](output/report/headline_c.md), with a
[comparison plot](output/report/c_scatter.png). This is a completed baseline,
not a claim of validated predictive accuracy or numerical convergence.
The fine, convergence and sensitivity campaigns have been configured but not run.

Verification: `validation/tests` passed 198 tests, with 5 skipped; `git diff --check`
passed. Both smoke and baseline reports contain nine current records, zero missing
and zero stale records. City/probe geometry maps were also inspected.

## Sources

- [Official Case C dataset and documentation](https://zenodo.org/records/15401792):
  geometry dimensions, instrumentation and original experiment attribution.
- [Official measurement layout](https://zenodo.org/records/15401792/files/MP-z-caseC.png):
  block locations and street width.
- Local workbook: all values, coordinates and normalization; reflection audit above
  is calculated directly from its 45-degree result sheet.

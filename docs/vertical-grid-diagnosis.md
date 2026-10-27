# Focused vertical-grid solver diagnosis

The diagnostic milestone in section 5.6 of
[the implementation plan](../DYNAMIC_VERTICAL_GRID.md) is complete locally on
2026-10-26. On the focused tower fixture, the excessive interior residual is
already present in the float multiplier solution. Study-only double-precision
refinement reduces it substantially on both CPU node orderings. This supports
testing a precision remedy before line relaxation. B1 sampling and explicit
preview are next; this delivery does not add either API or a production solver
option.

The archived [raw runs](data/vertical-grid-diagnosis/raw.json.gz) and
[summary](data/vertical-grid-diagnosis/summary.json) include all diagnostic
checkpoints, pedestrian samples, worst-cell details, source/binary SHA-256
hashes, compiler, backend and thread count. These are numerical diagnostics,
not experimental or comfort validation, and carry no performance claim.

## Reproduction

Use the development environment and serial/OpenMP configurations described in
[the validation guide](validation.md). For an existing checkout:

```sh
cmake -S . -B build/extension -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_OPENMP=OFF -DCMAKE_BUILD_TYPE=Release
cmake -S . -B build/openmp -DPython_EXECUTABLE="$PWD/.venv/bin/python" -DDTCC_QES_BUILD_TESTS=ON -DDTCC_QES_OPENMP=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build/extension --target vertical_grid_study --parallel 8
cmake --build build/openmp --target vertical_grid_study --parallel 8
.venv/bin/python tools/run_vertical_grid_diagnosis.py --output build/vertical-grid-diagnosis/reproduction
.venv/bin/python tools/run_vertical_grid_diagnosis.py --output build/vertical-grid-diagnosis/reproduction --summarize
ctest --test-dir build/extension -R 'study_' --output-on-failure
ctest --test-dir build/openmp -R 'study_' --output-on-failure
```

On macOS, configuring OpenMP may also require
`-DOpenMP_ROOT="$(brew --prefix libomp)"`. A different executable can be supplied
with `--worker`; repeat that argument to inspect multiple backends. To reassess
the stored archive without solving, use
`--output docs/data/vertical-grid-diagnosis --summarize`. Use a build directory
for new solves to preserve the archived evidence. The worker's ordinary
four-argument study mode retains its existing output contract; the optional
`--diagnose` argument adds inspection at every checkpoint and a precision probe
after the last checkpoint.

## Controlled comparison

The geometry, 270° wind, 5 m/s reference speed, inflow, model flags and
80 × 80 × 64 m domain are exactly the tower configuration in
[the original study](vertical-grid-gate.md). Horizontal spacing is 2 m.

| Grid | Physical layers | Baseline sweeps, each restarted from zero | Interior fluid cells |
| --- | --- | --- | --- |
| Uniform 0.5 m control | 128 | 2,000 / 4,000 / 8,000 | 178,488 |
| Uniform 0.25 m failing fixture | 256 | 8,000 / 16,000 / 32,000 | 359,864 |

Both serial lexicographic and two-thread OpenMP red-black production solvers
run these fixed budgets. Production stopping rules and numerical code are
unchanged. The same interior definition, normalized maximum/RMS bounds
`1e-3 / 1e-4`, and two successive velocity-stability checks from the original
study apply. No additional cells are excluded. Top-band residuals remain
separate. There are 1,300 valid pedestrian sample points at 1.5 m.

Both 0.5 m controls pass the full baseline acceptance check; both 0.25 m
configurations fail it. At the final baseline checkpoints, serial/red-black
pedestrian vector differences are at most `1.39e-6 * Uref` (0.5 m) and
`4.22e-6 * Uref` (0.25 m), with identical masks. Similar pedestrian fields do
not override the failed interior residual criteria.

The final controls use the same larger budgets on both backends. An exploratory
OpenMP control at 1,000 sweeps had normalized RMS residual `1.8703e-4`, above
the bound, although serial passes at that budget. This is why a serial sweep
budget cannot be assumed to certify red-black iteration. That exploratory run
motivated the final control budget; it is not one of the four archived runs.

## What the inspection measures

The derived study solver exposes its existing multipliers, previous
multipliers and RHS through read-only accessors. Inspection reconstructs the
CPU face correction independently, both with the production float operand
order and with operands widened before subtraction, multiplication and
addition. It evaluates flux before/after solid-face zeroing. Its independently
accumulated maximum, volume-weighted RMS and cell count must match the bridge's
conservative-divergence helper or the worker fails.

For the current `alpha1 = alpha2 = 1` solvers, let `Aλ` be the six-neighbour
operator in difference form and `D0` the conservative initial divergence.
The double diagnostic compares:

```text
predicted corrected divergence = D0 + 0.5 * Aλ
stored-RHS stencil residual   = 0.5 * (Aλ - R_float)
RHS construction/rounding gap  = D0 + 0.5 * R_float
```

The stencil residual plus RHS gap equals the prediction. The corrected face
flux is evaluated separately from these expressions. All arithmetic in this
inspection is independent of the float SOR update, and the production
divergence helper already uses double arithmetic on stored float arrays.
Merely changing a residual diagnostic to double cannot repair the field.

The archive records maximum/RMS values, maximum locations, boundary/solid
adjacency groups and the eight worst stored-flux cells. Each worst-cell record
includes coordinates, flag, neighbour flags, six coefficients, multiplier,
last update, multiplier ULP, RHS and residual decomposition.

## Findings

Across the archived baseline checkpoints:

- Float reconstruction matches every assessed stored face exactly.
- The double corrected-flux and stencil predictions agree to roundoff.
- Solid-face zeroing has zero effect on the assessed conservative flux.
- RHS rounding and final face-correction roundoff are much smaller than the
  failing interior residuals. Widening only the face correction leaves those
  maxima essentially unchanged.

At 32,000 serial sweeps, the 0.25 m maximum is at `(43, 41, 13.875) m`, adjacent
to the tower. The multiplier is approximately `-37.82045`, its ULP is
`3.81470e-6`, and its last update is `-2.28882e-5` (six ULPs). The stored-flux
residual is `2.66433e-4 s^-1`; the stored-RHS stencil residual is
`2.66552e-4 s^-1`, with a `-1.19209e-7 s^-1` RHS gap. The maximum RHS gap
anywhere is `4.61681e-7 s^-1`. Cells away from solids also have large residuals,
so the finding is not confined to one wall face.

The red-black 0.25 m maximum is at `(41, 47, 18.875) m`, also beside the tower,
and is `3.34263e-4 s^-1`. Neither maximum lies in the prescribed top band.
This finds no stencil/face inconsistency explaining the plateau on these
fixtures; it does not establish correctness for every geometry or boundary.

## Study-only precision experiment

Starting from the final float multipliers, the probe performs 100 and 1,000
additional SOR sweeps using double multipliers, a double RHS formed from the
same initial velocities, and double updates. It retains the original float
geometry and coefficients, relaxation value, bottom mirror and fixed lateral/
top multipliers. It uses lexicographic or red-black node order to match the
backend; the probe itself runs serially, including its red-black passes.
It then reconstructs corrected velocities in double and also assesses those
velocities after casting the completed face corrections to float.

| Backend / grid | Baseline final max divergence | After 1,000 double sweeps, float faces | After 1,000 double sweeps, double faces |
| --- | --- | --- | --- |
| Serial / 0.5 m | `7.53403e-5` | `6.55651e-7` | `2.11480e-9` |
| Red-black / 0.5 m | `8.65459e-5` | `6.55651e-7` | `3.95113e-9` |
| Serial / 0.25 m | `2.66433e-4` | `3.55393e-6` | `3.55615e-6` |
| Red-black / 0.25 m | `3.34263e-4` | `6.94394e-6` | `6.72421e-6` |

All values are dimensional maxima in s⁻¹. The base maximum bound is
`2.08333e-4 s^-1`; the ten-times tighter maximum bound is `2.08333e-5 s^-1`.
At the final probe snapshot all four float-face fields meet both tighter
maximum and RMS bounds. Maximum pedestrian vector changes from their original
float fields are below `1.84e-5 * Uref` (about `9.2e-5 m/s`). This is much
smaller than the declared iterative velocity-stability threshold.

The top-band residual is not repaired: it remains approximately
`0.141 s^-1` on 0.5 m layers and `0.281 s^-1` on 0.25 m layers. Taller-domain
sensitivity remains required before preset selection.

## Decision and limits

The evidence supports a precision-related limitation in the multiplier/update
path for these float solves. A higher-precision multiplier/RHS/update option
with float output faces is a remedy candidate. Line relaxation is not the next
remedy established by this diagnosis; conditioning and cost may still matter
in other cases or in a from-zero solve.

This warm-start experiment is not a complete replacement solver, a from-zero
convergence study or the full common acceptance gate. Snapshot residuals and
small changes from the baseline do not provide two successive certified
velocity-stability comparisons. The summary deliberately reports baseline
acceptance separately from probe residual bounds. The original failed tower
references remain excluded. There is no universal float32 floor, validated
aspect limit, selected automatic preset or physical-accuracy claim here.

Proceed to B1 sampling and explicit preview. If C2 needs the precision remedy,
implement it separately and opt-in, test from zero on both CPU backends, rerun
the full matched-accuracy gate and measure memory/runtime. Keep the legacy
solver path and public stopping rule intact unless an independently validated
change is deliberately selected.

## Validation

The new native self-test uses a manufactured `λ = x²` field, whose corrected
divergence is exactly one, to check the stencil/flux relation. It detects a
deliberately perturbed face, checks both solid flags and both sides of a solid
face, and verifies residual reduction by the double refinement while preserving
fixed boundary multipliers. Routine CTest does not execute the expensive tower
study.

- Python suite: 344 passed; the pre-existing dataset-registration contract
  mismatch is explicitly deselected.
- Serial native suite: 10/10 passed; OpenMP native suite: 13/13 passed.
- ASan/UBSan native suite: 10/10 passed, including the new diagnostic self-test.
- Serial and OpenMP no-I/O symbol audits passed.
- Archived summary reproduces byte-for-byte from the raw data. Recorded source
  and binary hashes match the measured inputs; five overlapping serial
  checkpoints match the original study's velocities and residual diagnostics
  exactly.
- Source/wheel artifact checks passed, including the new diagnostic sources,
  report and archived data. A serial wheel rebuilt from the source distribution
  passes an isolated explicit-grid smoke test with zero divergence; both Python
  and native modules were verified to load from the extracted wheel.

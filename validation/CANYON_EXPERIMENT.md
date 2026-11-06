# Private protected canyon validation

The canyon implementation is experimental and defaults to legacy. Public
`Parameterizations.street_canyon` remains restricted to 0–1. The private selectors
are `legacy`, `horizontal_reference_v1` and `joined_v1`; integration does not
establish improved physical accuracy or change any public default.

`joined_v1` retains the frozen join specification in
`specifications/canyon-join-v1.json` and its original SHA256. Roof protection is
versioned separately as `physical-and-voxel-union-v1`. Both horizontal modes
preserve the complete legacy W initialization and the union of physical-height
and voxel-height roof bands. Projection can change those regions afterward;
the protection contract applies to initialization.

The native preflight restricts overlays to supported flat, equal-height,
matching-span rectangular canyons with normal, noncalm flow. Ambiguous,
overlapping, oblique and otherwise unsupported supports retain legacy behavior.
Joined mode also rejects a collapsed join band or turning/reversed incident
profiles below the roof. Metadata records activation counts and fallback reasons.
An inactive condition provides fallback evidence, rather than accuracy evidence
for the overlay.

All calls require explicit legacy solver control. Active models require the
frozen standard parameterization flags. The optional turbulence allowance admits
only the unchanged one-way height-based QES-Turb calculation. Stacked canopy,
wake-composition, alternative relaxation and checkpoint-stopping operations are
rejected before state attachment. Compatibility arguments in the private native
binding do not implement those prototype models.

From a checkout with validation dependencies and an isolated native package:

```python
from aij import campaigns, runner
from aij.canyon import CanyonSession

# Use the baseline descriptor for matched fixed-work validation. Raw case
# helpers have different default solver settings.
spec = next(s for s in campaigns.baseline() if s.case == "D" and s.direction == 270.)
args = runner.inputs(spec)
session = CanyonSession()
try:
    result, stages = session.run(args, model="joined_v1",
        capture=True, trace=False, baseline_turbulence=True)
finally:
    session.close()
```

Place `validation` and the isolated package directory on `PYTHONPATH`; prevent
editable import redirects as in `tools/compare_native_builds.py`. Never replace
the installed package merely to run a research comparison. Set
`DTCC_QES_AIJ_DATA` to the external reference data directory when needed.

The adapter caches geometry only. Every solve resets inflow, model state and
multipliers. Returned metadata is independent of later calls. `capture=False`
omits the full W snapshot; `stages=False` omits canonical contributor capture;
roof-write tracing defaults off. Ordinary public calls allocate none of these
diagnostic snapshots. Independent native audits still distinguish physical roof,
voxel roof and complete W violations during active validation calls.

`DTCC_QES_CANYON_TEST_HOOKS` defaults off. A separate hook-enabled build exposes
the deliberate exception used by `tools/qualify_canyon.py`. Its identity differs
from the ordinary build and it is never a distributable qualification build.
The six-attempt block tests aligned activation, oblique fallback, an exception
after state attachment and final legacy reuse. Unit/native tests cover both
signs of roof/grid displacement, independent audit corruption controls, formula
limits and supported-controller lifecycle behavior.

`tools/check_canyon_archive.py` performs optional engineering archive checks.
It consumes fresh answers and refuses an existing output directory. The
off-face check compares both nonuniform-grid roof representations. The D check
selects the frozen baseline key and compares canonical records/planes plus full
velocity, flags, stress and W hashes. These compatibility checks preserve the
known D accuracy regressions and confer no physical promotion. The historical
AIJ matrix uses capped fixed work; it is not tolerance-converged qualification.

Native source edits invalidate the existing solver-policy identity. The normal
path requires the repository's release requalification procedure; experimental
canyon calls remain outside adaptive pedestrian-policy acceptance.

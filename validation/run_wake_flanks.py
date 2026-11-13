"""C3 H4 diagnostic: Case E after, wake=3, fixed centre +/-5 degree stencil.

Run with OMP_NUM_THREADS=8 python validation/run_wake_flanks.py.
The 32 flank records are separate from the W4 baseline. No measurement is
assigned to a flank; only the three-direction mean is compared to centre data.
"""
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
from aij import campaigns, runner, tables
import run_wake_validation as wake

OUTPUT = Path(__file__).resolve().parent / 'output' / 'wake-flanks'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    specs = campaigns.baseline(2., parameterizations=campaigns.WAKE3)
    centres = [s for s in specs if s.case == 'E' and s.state == 'after']
    rows = []
    for centre in centres:
        base = runner.load(wake.RUNS / 'E', centre.key)
        if base is None:
            raise ValueError('Missing registered centre run')
        flanks = []
        for offset in (-5., 5.):
            spec = replace(centre, direction=(centre.direction + offset) % 360)
            path = OUTPUT / f'{spec.key}.json'
            if path.exists():
                record = runner.read_record(json.loads(path.read_text()))
            else:
                record, _ = runner.run(spec)
                path.write_text(json.dumps(record, default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x.item()))
            flanks.append(record)
        scalar = np.array([r['probes']['K_scalar_wake_rule'] for r in [flanks[0], base, flanks[1]]], float)
        rows.append(dict(label=centre.label, direction=centre.direction, centre_key=centre.key,
            flank_keys=[r['key'] for r in flanks],
            native_identities=[r['native'] for r in [base, *flanks]],
            diagnostics=[r['diagnostics'] for r in [base, *flanks]], centre=scalar[1].tolist(), averaged=scalar.mean(axis=0).tolist(),
            range=np.ptp(scalar, axis=0).tolist()))
        print(centre.label, flush=True)
    target = tables.load_results_e('after')
    by_label = {r['label']: r for r in rows}
    m = target.values
    result = dict(stencil_degrees=[-5, 0, 5], state='after', wake=3, rows=rows, scores={})
    for key in ('centre', 'averaged'):
        s = np.array([by_label[label][key] for label in target.labels]).T
        valid = np.isfinite(s) & np.isfinite(m)
        top = valid & (m >= np.nanpercentile(m, 90))
        result['scores'][key] = dict(mean_bias=float(np.mean(s[valid]-m[valid])),
            mae=float(np.mean(abs(s[valid]-m[valid]))),
            top_decile=float(s[top].mean()/m[top].mean()-1),
            top_decile_over_20pct_slow=float(np.mean(s[top]<.8*m[top])))
    (OUTPUT/'summary.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

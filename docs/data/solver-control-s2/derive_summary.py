"""Derive S2 medians and logical-byte estimates from immutable worker records."""
from pathlib import Path
import json
import statistics

root = Path(__file__).resolve().parent
stages = ['baseline-corrected','norm','operator','allocation','ordering']
records = {s:json.loads((root/s/'summary.json').read_text()) for s in stages}
output = dict(protocol=dict(iterations=80,physical_cells=9420800,updated_cells=318*318*91,
    native_build=records['ordering']['runs'][0]['build'],cpu_count=14,
    host_identity='Apple M4 Pro from preserved S0 protocol; S2 records platform and CPU count; direct CPU-brand re-query unavailable in sandbox.',
    model='Logical coefficient, RHS, neighbor/self/output reads/writes, old-iterate passes when present, ground mirror, and compact mask/factor lookups. Counts table reads even when cached; assumes shared mask-index reuse; excludes cache-line/write-allocation effects and control overhead. Effective GB/s is not measured DRAM bandwidth.'),
    stages={},cross_stage_numerical_parity=[])
N = 320*320*93
plane = 320*320
updates = 318*318*91
for stage,doc in records.items():
    assert doc['completed'] and doc['parity_passed']
    groups = []
    for backend in ('openmp','serial'):
        for precision in ('float32','float64'):
            size = 4 if precision == 'float32' else 8
            compact = stage in ('operator','allocation','ordering')
            logical = updates*(24+9*size+(1+size if compact else 0))+2*size*plane
            if stage == 'baseline-corrected' and precision == 'float32':
                logical += 2*size*N+2*size*(N-plane)
            for threads in ((1,2,4,8) if backend == 'openmp' else (1,)):
                for turb in ((False,True) if backend == 'openmp' and threads == 4 else (False,)):
                    rr = [r for r in doc['runs'] if r['backend'] == backend and r['precision'] == precision
                          and r['requested_threads'] == threads and r['turbulence'] == turb]
                    plain = [r for r in rr if not r['instrumented']]
                    prof = [r for r in rr if r['instrumented']]
                    seconds = statistics.median(r['profile']['seconds']['sweeps']/r['iterations'] for r in prof)
                    groups.append(dict(backend=backend,precision=precision,threads=threads,turbulence=turb,
                        repeats=len(plain),api_seconds=statistics.median(r['timing']['api_seconds'] for r in plain),
                        native_prepare_seconds=statistics.median(r['timing']['native_prepare_including_boundary'] for r in plain),
                        sweep_seconds=seconds,logical_bytes_per_sweep=logical,effective_logical_gb_per_second=logical/seconds/1e9,
                        peak_rss_bytes=statistics.median(r['peak_rss_bytes'] for r in plain),
                        wind_operator_workspace_bytes=sum(prof[0]['profile']['array_bytes'].values()),
                        operator_owned_bytes=prof[0]['profile']['array_bytes']['operator.owned'],
                        solver_workspace_bytes=prof[0]['profile']['array_bytes']['solver.workspace']))
    output['stages'][stage] = dict(matrix_elapsed_seconds=doc['elapsed_seconds'],groups=groups)
    for r in doc['runs']:
        reference_backend = 'openmp' if stage == 'ordering' and r['backend'] == 'serial' else r['backend']
        reference = next(b for b in records['baseline-corrected']['runs'] if b['backend'] == reference_backend
                         and b['precision'] == r['precision'] and b['turbulence'] == r['turbulence'])
        passed = r['output_sha256'] == reference['output_sha256'] and r['diagnostics'] == reference['diagnostics']
        output['cross_stage_numerical_parity'].append(dict(stage=stage,record=r['record'],reference_backend=reference_backend,passed=passed))
assert all(r['passed'] for r in output['cross_stage_numerical_parity'])
(root/'performance-summary.json').write_text(json.dumps(output,indent=2)+'\n')
for stage in stages:
    r = next(r for r in output['stages'][stage]['groups'] if r['precision'] == 'float32' and r['backend'] == 'openmp'
             and r['threads'] == 4 and not r['turbulence'])
    print(stage,'API',round(r['api_seconds'],4),'sweep ms',round(r['sweep_seconds']*1000,3),
          'RSS MiB',round(r['peak_rss_bytes']/2**20,1),'arrays MiB',round(r['wind_operator_workspace_bytes']/2**20,1))

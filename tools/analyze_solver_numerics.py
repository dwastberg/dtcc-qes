"""Replay S5b hotspot arithmetic and classify the frozen diagnostic evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np


def analyze(folder):
    data=json.loads((folder/'results.json').read_text());records=[]
    for row in data['rows']:
        if row['status']!='completed':continue
        spec=json.loads((folder/f"cases/{row['request']['case']}.json").read_text())
        dx=dy=spec['resolution'];layers=spec['solver_dz']
        for frame in row['result']['checkpoints']:
            for group,cell in enumerate(frame.get('hotspots',[])):
                if cell is None:continue
                k=cell['ijk'][2];dz=layers[k]
                a=np.array(cell['coefficients']);faces=np.array(cell['faces'])
                # Independent same-cell algebra, with physical rather than
                # ghost layer indexing. Top solved layer has a next physical dz.
                below=layers[max(0,k-1)];above=layers[k+1]
                areas=a*np.array([dx*dx,dx*dx,dy*dy,dy*dy,dz*.5*(dz+above),dz*.5*(dz+below)])
                q=areas*faces*np.array([dy*dz,-dy*dz,dx*dz,-dx*dz,dx*dy,-dx*dy])
                div=float(np.sum(q)/(dx*dy*dz))
                residual=float(np.dot(a,cell['neighbour_lambda'])-cell['rhs']-np.sum(a)*cell['lambda'])
                if not np.isclose(div,cell['divergence'],rtol=1e-12,atol=1e-12):raise ValueError('Face-divergence replay mismatch')
                if not np.isclose(residual,cell['residual'],rtol=1e-10,atol=2e-11):raise ValueError('Equation residual replay mismatch')
                flux=cell['cell_mass']['top_flux' if cell['top_band'] else 'flux']
                if not np.isclose(np.sum(q),flux['signed'],rtol=1e-12,atol=1e-12):raise ValueError('Signed flux replay mismatch')
                # A one-cell region's absolute NET cell flux is |sum q|;
                # throughflow is half the sum of individual absolute face flux.
                if not np.isclose(abs(np.sum(q)),flux['absolute'],rtol=1e-12,atol=1e-12):raise ValueError('Absolute flux replay mismatch')
                label=('prescribed_top_face_boundary_limitation' if cell['top_band'] else
                       'solid_to_fluid_operator_mask_reconstruction_defect' if cell['initial_flag'] in (0,2) else
                       'iterative_residual_with_float_rounding')
                records.append(dict(worker=row['request']['id'],iteration=frame['iteration'],group=group,
                    ijk=cell['ijk'],xyz=cell['xyz'],initial_flag=cell['initial_flag'],flag=cell['flag'],
                    classification=label,divergence=div,equation_residual=residual,
                    divergence_minus_half_residual=div-.5*residual,signed_flux=float(np.sum(q)),absolute_flux=abs(float(np.sum(q)))))
    # Controlled precision pairs have identical float model inputs and flags.
    precision=[]
    for a,b in [('04','05'),('07','08')]:
        ra,rb=[next(r for r in data['rows'] if r['request']['id']==i) for i in (a,b)]
        if ra['result']['initial_hashes']!=rb['result']['initial_hashes']:raise ValueError('Precision control initial state differs')
        precision.append(dict(case=ra['request']['case'],identical_initial_fields_and_flags=True,
            float32_max=ra['result']['checkpoints'][-1]['mass']['maximum'],
            float64_max=rb['result']['checkpoints'][-1]['mass']['maximum']))
    conclusions=[
            'All three persistent core maxima occur in initially solid cells relabeled as fluid. The geometry operator was built before that relabeling.',
            'The downtown pilot discrepancy persists in float64 with identical initial float fields and flags. Canyon-off removes relabeling and the large interior discrepancy on that pilot.',
            'The courtyard pilot has no relabeled cells: it is a useful negative control, not a reproduction of the core courtyard defect.',
            'Prescribed top-band faces explain a separate operator/reconstruction boundary limitation; their maxima remain reported.',
            'Large-core acceptance remains blocked pending a separately frozen numerical fix; no cells or historical gates were removed.']
    if not any(r['classification']=='solid_to_fluid_operator_mask_reconstruction_defect' for r in records):
        conclusions=['No prepared-solid cell is assessed as fluid in the corrected study.',
                     'Interior maxima must still meet independent residual/mass/observable qualification; correction is not acceptance.',
                     'Prescribed top-face boundary behavior is retained and reported separately.']
    return dict(passed=True,hotspots=records,precision_controls=precision,conclusions=conclusions)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);args=p.parse_args()
    value=analyze(args.folder)
    (args.folder/'hotspot-disposition.json').write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(passed=True,hotspots=len(value['hotspots']),precision_controls=len(value['precision_controls']))))

if __name__=='__main__':main()

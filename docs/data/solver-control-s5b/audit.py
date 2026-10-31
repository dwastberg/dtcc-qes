"""Verify and independently replay the portable S5b study (no native solve)."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tarfile

ROOT=Path(__file__).resolve().parent

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def main():
    driver=load('s5b_driver',ROOT/'analysis-driver.py')
    result=driver.audit(ROOT)
    with tarfile.open(ROOT/'implementation-sources.tar.gz') as archive:
        index=json.loads((ROOT/'implementation-source-index.json').read_text())
        for name,sha in index.items():
            assert hashlib.sha256(archive.extractfile(name).read()).hexdigest()==sha,name
    replay=load('s5b_analysis',ROOT/'analyze_solver_numerics.py').analyze(ROOT)
    assert replay==json.loads((ROOT/'hotspot-disposition.json').read_text())
    parity=json.loads((ROOT/'parity.json').read_text())
    assert parity['passed'] and not parity['ordering_migration'] and len(parity['comparisons'])==12
    assert all(not row['differences'] for row in parity['comparisons'])
    assert all(row['cases']==429 for row in parity['comparisons'] if row['kind']=='revision')
    value=json.loads((ROOT/'results.json').read_text())
    assert value['completed'] and len(value['rows'])==16 and all(r['status']=='completed' for r in value['rows'])
    assert len(value['references'])==2 and all(r['accepted'] for r in value['references'])
    # Replay every saved history comparison; no field is called reference error
    # unless its independent zero-start triple passed qualification.
    curves=json.loads((ROOT/'cost-error-curves.json').read_text())['curves']
    import numpy as np
    for ref in value['references']:
        rows=[r for r in value['rows'] if r['request']['case']==ref['case']]
        longest=max(rows,key=lambda r:r['request']['iterations'])
        with np.load(ROOT/f"{longest['request']['id']}.npz") as saved:frames=saved['samples']
        entries=[c for c in curves if c['case']==ref['case']]
        assert len(entries)==len(frames)==81
        for frame,entry in zip(frames,entries):
            assert entry['heights']==driver.compare_samples(frame,frames[-1],longest['result']['plane_points'])
            assert entry['comparison_label']=='reference_error'
    print(json.dumps(result|dict(hotspot_replay=True,cost_error_replay=True,strict_parity=True,implementation_sources=len(index))))

if __name__=='__main__':main()

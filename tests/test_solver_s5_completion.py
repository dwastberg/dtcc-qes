"""S5 evidence integrity, deterministic cadence selection and change attribution."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[1]

def module(name):
    import sys
    sys.path.insert(0,str(ROOT/'tools'))
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def test_cadence_selection_respects_each_case(tmp_path,monkeypatch):
    study=module('complete_solver_s5')
    times=[[1.2,1.01,1.],[1.4,1.,1.02]]
    rows=[dict(request=dict(case=c,cadence=k),api_seconds=times[n][i]) for n,c in enumerate(study.CASES) for i,k in enumerate([25,50,100])]
    monkeypatch.setattr(study,'execute',lambda *args:rows)
    study.screen(tmp_path)
    assert json.loads((tmp_path/'selection.json').read_text())['cadence']==50
    rows[4]['api_seconds']=1.2
    study.screen(tmp_path)
    assert json.loads((tmp_path/'selection.json').read_text())['cadence']==100


def test_original_blob_integrity_and_cache_bound(tmp_path):
    publish=module('publish_solver_s5');data=b'unchanged original protocol\n';sha=hashlib.sha256(data).hexdigest()
    blob=tmp_path/'blob.gz';blob.write_bytes(gzip.compress(data,mtime=0))
    (tmp_path/'index.json').write_text(json.dumps(dict(files={'original':dict(sha256=sha,bytes=len(data),blob='blob.gz')})))
    evidence=publish.Evidence(tmp_path)
    assert evidence.read('original')==data
    assert evidence.read.cache_info().maxsize==16
    blob.write_bytes(gzip.compress(b'changed evidence',mtime=0))
    with pytest.raises(ValueError,match='Changed original'):publish.Evidence(tmp_path).read('original')


def parity_fixture(tmp_path,*,hit=True,geometry_change=False):
    data={f'native/c{i}/velocity':np.array([float(i)],dtype=np.float32) for i in range(429)}
    data.update({f'native/c{i}/x':np.array([1.],dtype=np.float32) for i in range(429)})
    changed={k:v.copy() for k,v in data.items()};changed['native/c0/'+('x' if geometry_change else 'velocity')][0]=9
    counts={f'native/c{i}':0 for i in range(429)}
    candidate_counts=dict(counts);candidate_counts['native/c0']=1 if hit else 0
    for label in ['baseline','candidate']:
        for backend in ['openmp','serial']:
            for team in ([1,2,4,8] if label=='candidate' and backend=='openmp' else [1]):
                p=tmp_path/f'{label}-{backend}-{team}.npz';np.savez_compressed(p,**(changed if label=='candidate' else data))
                p.with_suffix('.counts.json').write_text(json.dumps(candidate_counts if label=='candidate' else counts))
    (tmp_path/'builds.json').write_text('{}')


def test_all_changed_cases_need_observed_solid_guard(tmp_path):
    study=module('check_condition_mask_parity');parity_fixture(tmp_path)
    study.analyze(tmp_path)
    report=json.loads((tmp_path/'parity.json').read_text())
    assert report['passed'] and report['changed_cases']==1 and report['unchanged_cases']==428


def test_unaffected_case_cannot_change(tmp_path):
    study=module('check_condition_mask_parity');parity_fixture(tmp_path,hit=False)
    with pytest.raises(ValueError,match='Unexplained changed case'):study.analyze(tmp_path)


def test_observed_guard_does_not_allow_geometry_changes(tmp_path):
    study=module('check_condition_mask_parity');parity_fixture(tmp_path,geometry_change=True)
    with pytest.raises(ValueError,match='Changed geometry'):study.analyze(tmp_path)

def test_segmented_original_npz_is_lossless_and_extractable(tmp_path):
    publish=module('publish_solver_s5')
    source=tmp_path/'original.npz';np.savez_compressed(source,velocity=np.arange(18,dtype=np.float32).reshape(6,3))
    data=source.read_bytes();parts=[data[:47],data[47:91],data[91:]]
    names=[]
    for i,part in enumerate(parts):
        name=f'part-{i}.gz';(tmp_path/name).write_bytes(gzip.compress(part,mtime=0));names.append(name)
    (tmp_path/'index.json').write_text(json.dumps(dict(files={'parity/original.npz':dict(sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),segments=names)})))
    assert publish.Evidence(tmp_path).read('parity/original.npz')==data
    publish.extract(tmp_path,'parity',tmp_path/'expanded')
    assert (tmp_path/'expanded/original.npz').read_bytes()==data
    with np.load(tmp_path/'expanded/original.npz') as value:np.testing.assert_array_equal(value['velocity'],np.arange(18,dtype=np.float32).reshape(6,3))

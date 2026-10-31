"""Reject changed checkpoint provenance and support relocatable data audits."""
import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest
from test_vertical_refinement import study

spec=importlib.util.spec_from_file_location('refinement_audit',Path(__file__).parents[1]/'tools/audit_vertical_refinement.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


@pytest.mark.parametrize('change',['task','input','identity','content'])
def test_changed_execution_cannot_reuse_checkpoint(change):
    task=study.tasks('openmp')[0]
    manifest=dict(configurations={task['family']:dict(layers_input=[.5]*128)})
    request=dict(study_identity=study.fingerprint(manifest),task=task,sweeps=8000,
        input_sha256=hashlib.sha256(study.input_text(task,manifest['configurations']).encode()).hexdigest())
    run=dict(marker='original')
    saved=dict(request=copy.deepcopy(request),run=run,run_sha256=study.fingerprint(run))
    if change=='task':saved['request']['task']['extent']=240
    if change=='input':saved['request']['input_sha256']='wrong'
    if change=='identity':saved['request']['study_identity']='wrong'
    if change=='content':saved['run']['marker']='changed'
    with pytest.raises(ValueError,match='identity/content'):
        audit.validate_saved(saved,task,8000,manifest,study,'openmp')


def test_checkpoint_identity_uses_study_relative_tail():
    task=study.tasks('openmp')[0]
    tail=audit.origin_tail('openmp',task,8000)
    assert tail.parts==('openmp','checkpoints','vertical','split-2','160','270','0.5','008000.json.gz')
    original=Path('/original/absolute/study')/tail
    assert original.parts[-len(tail.parts):]==tail.parts

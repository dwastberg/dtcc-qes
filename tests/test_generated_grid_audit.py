"""Reject altered pilot checkpoint inputs and content before reusing them."""

from fixtures.support import load_tool
import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest
from fixtures.generated_grid_pilot import study

audit=load_tool('pilot_audit', Path(__file__).parents[1]/'tools/audit_generated_grid_pilot.py')


@pytest.mark.parametrize('change',['task','input','identity','content'])
def test_checkpoint_reuse_rejects_changed_execution(change):
    task=study.tasks()[0]
    manifest=dict(configurations={'generated':dict(layers_input=[.5]*128)})
    request=dict(study_identity=study.fingerprint(manifest),task=task,sweeps=8000,
        input_sha256=hashlib.sha256(study.input_text(task,manifest['configurations']).encode()).hexdigest())
    run=dict(marker='original')
    saved=dict(request=copy.deepcopy(request),run=run,run_sha256=study.fingerprint(run))
    if change=='task': saved['request']['task']['extent']=160
    if change=='input': saved['request']['input_sha256']='wrong'
    if change=='identity': saved['request']['study_identity']='wrong'
    if change=='content': saved['run']['marker']='changed'
    with pytest.raises(ValueError,match='identity/content'):
        audit.validate_saved(saved,task,8000,manifest,study,'openmp')

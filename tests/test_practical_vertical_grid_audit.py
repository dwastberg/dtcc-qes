"""Saved practical-grid evidence must reproduce without installed wind packages."""
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from fixtures.practical_vertical_grid import study

ROOT=Path(__file__).resolve().parents[1]/'docs/data/practical-vertical-grid'


def test_saved_decisions_preserve_unqualified_status():
    result=study.audit(ROOT)
    assert result['integrity_pass']
    assert not result['requires_native_extension']
    assert not result['automatic_preset_selected']
    assert not result['comfort_qualified']
    summary=study.read(ROOT/'summary.json')
    for run in summary['runs']:
        if run['status']=='completed':
            assert not run['strict_reference_certified']
            assert not run['comfort_qualified']


def test_case_tampering_is_rejected(tmp_path):
    root=tmp_path/'archive'
    shutil.copytree(ROOT,root)
    executions=study.read(root/'executions.json')
    execution=next(e for e in executions if e['status']=='completed')
    path=root/'cases'/(execution['task']['id']+'.json.gz')
    content=json.loads(gzip.decompress(path.read_bytes()))
    content['diagnostics']['max_divergence']=0
    study.atomic_json(path,content)
    with pytest.raises(ValueError,match='Case content changed'):
        study.audit(root)


def test_isolated_archive_has_no_extension_or_parent_reference_dependency(tmp_path):
    root=tmp_path/'archive'
    shutil.copytree(ROOT,root)
    script=root/'sources/tools/run_practical_vertical_grid.py'
    bootstrap='''
import importlib.abc, runpy, sys
class BlockWindPackages(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('dtcc_qes', 'dtcc_core'):
            raise ImportError('Wind package import blocked for data-only audit')
sys.meta_path.insert(0, BlockWindPackages())
sys.path.insert(0, sys.argv[1])
sys.argv = [sys.argv[2], '--audit', '--output', sys.argv[3]]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
    result=subprocess.run([str(Path(sys.executable).absolute()),'-c',bootstrap,
        str(script.parent),str(script),str(root)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0, result.stderr
    assert json.loads(result.stdout)['integrity_pass']

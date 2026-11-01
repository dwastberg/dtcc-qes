"""Execute current user examples with real solves and a mocked city fetch."""
import ast
import json
from pathlib import Path
import re
import runpy
import sys

import numpy as np
import pytest
from dtcc_qes import wind,comfort
from fixtures.datasets import source_city,fetched

ROOT=Path(__file__).resolve().parents[1]
pytestmark=pytest.mark.usefixtures("dtcc_logger")
CURRENT_DOCS=["README.md","docs/wind-profiles.md","docs/wind-comfort.md",
              "docs/precision-and-horizontal-verification.md","docs/solver-control.md"]


@pytest.mark.parametrize("document",CURRENT_DOCS)
def test_current_python_snippets(document,fetched,caplog):
    from dtcc_core.model import City
    scope=dict(wind=wind,comfort=comfort,city=City(),np=np)
    content=(ROOT/document).read_text().split("## Historical S5–S9 milestone notes")[0]
    for i,code in enumerate(re.findall(r"```python\n(.*?)```",content,re.S)):
        exec(compile(code,f"{document}:snippet-{i+1}","exec"),scope)
    warnings=[r.message for r in caplog.records if r.name=="dtcc-qes" and r.levelname=="WARNING"]
    assert not warnings,warnings


@pytest.mark.parametrize("script",["simple_wind_demo.py","medium_city.py"])
def test_plotting_demos_run_without_gui(script,tmp_path):
    target=tmp_path/(script+".png")
    runpy.run_path(str(ROOT/'demo'/script))["main"](
        ["--no-show","--resolution","2","--save",str(target)])
    assert target.stat().st_size>1000


def test_network_demo_uses_current_dataset_request(fetched):
    result=runpy.run_path(str(ROOT/'demo/wind_dataset.py'))["main"](
        ["--bounds","0","0","30","24","--resolution","2","--no-show"])
    assert fetched and result.field("speedup").values.size


def test_dataset_cli_profile_and_turbulence_payloads(fetched,tmp_path,monkeypatch):
    payload=tmp_path/'profile.json'
    payload.write_text(json.dumps(wind.UniformProfile(5,270).to_dict()))
    monkeypatch.setattr(sys,"argv",["city_dataset.py","0","0","30","24","--product","slice",
        "--profile",str(payload),"--turbulence","height","--slice-sampling","linear","--slice-height","1.75"])
    result=runpy.run_path(str(ROOT/'examples/city_dataset.py'))["main"]()
    assert result.field("streamwise_std").unit=="m/s"


def test_live_callers_use_current_python_arguments():
    removed={"wind_speed","wind_direction","reference_height","roughness_length","tolerance",
             "max_iterations","solver_precision","solver_control","raise_on_nonconvergence","raise_on_unaccepted"}
    violations=[]
    for folder in ("src/dtcc_qes","tools","examples","demo"):
        for path in (ROOT/folder).glob('*.py'):
            if path.name=="feature_merge_baseline.py":
                continue  # Explicit old/new archive adapter, exercised separately.
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ("run","preview_grid") and isinstance(node.func.value,ast.Name) and node.func.value.id=="wind":
                    bad={k.arg for k in node.keywords}&removed
                    if bad or len(node.args)>2:
                        violations.append((str(path.relative_to(ROOT)),node.lineno,sorted(bad)))
    assert not violations,violations

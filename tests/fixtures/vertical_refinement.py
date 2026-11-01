"""Checks for systematic subdivision, native alignment and honest scope gates."""

from fixtures.support import load_tool


import copy


import importlib.util


from pathlib import Path


import sys


import numpy as np


import pytest


from fixtures.joint_grid_verification import manufactured


_tools = Path(__file__).parents[2] / "tools"


study = load_tool("vertical_refinement", _tools / "run_vertical_refinement.py")


sys.path.insert(0, str(_tools))




def documents():
    frozen = {
        f"{f}/270/{h}/{r}": [0 if f == "auto" else 1]
        for f in ("auto", "uniform-0.5")
        for h in study.HEIGHTS
        for r in ("all", "away4m")
    }
    docs = {}
    refs = {}

    def make(task):
        run = manufactured(task)
        run.update(
            cells=92, peak_rss_bytes=100, roof_errors=[0.1], solver_workspace_bytes=100
        )
        for c in run["checkpoints"]:
            c["solve_seconds"] = 1
        return run

    for backend in study.BACKENDS:
        base = make(dict(family="base"))
        docs[backend] = dict(runs=[make(t) for t in study.tasks(backend)], attempts=[])
        refs[backend] = dict(
            base=base, joint=dict(metadata=dict(frozen_critical_indices=frozen))
        )
    configs = {f: dict(sampling={}) for f in ("base", *study.FAMILIES)}
    return docs, refs, configs

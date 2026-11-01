"""Keep the bounded vertical pilot honest about local failures and scope."""

from fixtures.support import load_tool


import copy


import importlib.util


from pathlib import Path


import sys


import numpy as np


import pytest


from fixtures.joint_grid_verification import manufactured


_tools = Path(__file__).parents[2] / "tools"


study = load_tool("generated_pilot", _tools / "run_generated_grid_pilot.py")


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
    for backend in study.BACKENDS:
        runs = []
        reference = []
        for task in study.tasks():
            run = manufactured(task)
            run.update(cells=92, peak_rss_bytes=100, roof_errors=[0.1])
            for c in run["checkpoints"]:
                c["solve_seconds"] = 1
            runs.append(run)
            other = copy.deepcopy(run)
            other["task"] = task | dict(
                family="uniform-0.5", id=f"joint/{task['extent']}/uniform-0.5/270/0.5"
            )
            other["cells"] = 128
            reference.append(other)
        docs[backend] = dict(runs=runs, attempts=[])
        refs[backend] = dict(
            runs=reference, metadata=dict(frozen_critical_indices=frozen)
        )
    return docs, refs

"""The precision-reference gate must protect subsequent grid comparisons."""

from fixtures.support import load_tool


import copy


import importlib.util


from pathlib import Path


import sys


import pytest


from fixtures.auto_grid_controls import native_run


_tools = Path(__file__).parents[2] / "tools"


study = load_tool("precision_verification", _tools / "run_precision_verification.py")


sys.path.insert(0, str(_tools))




def precision_document():
    runs = []
    for task in study.tasks("precision"):
        run = native_run()
        run.update(
            task=task,
            start="zero",
            precision=task["precision"],
            solver_workspace_bytes=100,
        )
        runs.append(run)
    return dict(metadata=dict(phase="precision"), runs=runs)

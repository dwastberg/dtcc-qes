"""Prevent false closure and unsafe reuse in the joint spatial study."""

from fixtures.support import load_tool


import copy


import importlib.util


import json


import os


from pathlib import Path


import subprocess


import sys


import numpy as np


import pytest


from fixtures.auto_grid_controls import native_run


from fixtures.precision_verification import precision_document


_tools = Path(__file__).parents[2] / "tools"


study = load_tool("joint_grid_verification", _tools / "run_joint_grid_verification.py")


sys.path.insert(0, str(_tools))


precompute = load_tool(
    "joint_precompute", _tools / "precompute_joint_checkpoints.py"
)
audit = load_tool("joint_audit", _tools / "audit_joint_grid_verification.py")


def manufactured(task):
    run = native_run()
    run.update(
        task=task,
        start="zero",
        precision="float64",
        disabled_mask=0,
        solver_workspace_bytes=100,
        z_faces=[0, 64],
    )
    for c in run["checkpoints"]:
        for plane in c["planes"]:
            plane["flags"] = [[1, 1]] * len(plane["velocity"])
    run["profile_planes"] = copy.deepcopy(run["checkpoints"][0]["planes"])
    run["initial_planes"] = copy.deepcopy(run["profile_planes"])
    return run


def joint_documents():
    refs = {
        "verification": dict(
            runs=[manufactured(t) for t in study.previous_tasks("verification")]
        )
    }
    frozen = {
        f"{f}/{w}/{h}/{r}": [0]
        for f in study.FAMILIES
        for w in study.DIRECTIONS
        for h in study.HEIGHTS
        for r in ("all", "away4m")
    }
    doc = dict(
        metadata=dict(frozen_critical_indices=frozen),
        runs=[manufactured(t) for t in study.tasks()],
        attempts=[],
    )
    return doc, refs

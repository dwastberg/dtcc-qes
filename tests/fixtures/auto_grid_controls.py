"""Independent checks of the C2 collocation and acceptance decisions."""

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


_tools = Path(__file__).parents[2] / "tools"


controls = load_tool("auto_grid_controls", _tools / "run_auto_grid_controls.py")


sys.path.insert(0, str(_tools))




def native_run(control="base"):
    n = len(controls.POINTS) ** 2
    return dict(
        geometry="tower",
        family="auto",
        control=control,
        direction=270,
        repeat=0,
        backend="manufactured",
        threads=1,
        hmax=23.7,
        layers=64,
        cells=102400,
        resolution=2,
        roof_errors=[0],
        peak_rss_bytes=1000000,
        prep_seconds=0.1,
        planning_seconds=0.001,
        sample_x=controls.POINTS.tolist(),
        sample_y=controls.POINTS.tolist(),
        checkpoints=[
            dict(
                iterations=iteration,
                max_divergence=1e-6,
                rms_divergence=1e-7,
                solve_seconds=1.0,
                sampling_seconds=0.001,
                top_band_max_divergence=0.1,
                planes=[
                    dict(height=height, velocity=[[5.0, 0.0, 0.0]] * n)
                    for height in controls.HEIGHTS
                ],
            )
            for iteration in (1000, 2000, 4000)
        ],
    )


def document(runs):
    return dict(
        metadata=dict(
            repeats=1, geometries=["tower"], directions=[270], families=["auto"]
        ),
        runs=runs,
    )


@pytest.fixture
def worker():
    executable = Path(
        os.environ.get(
            "DTCC_QES_STUDY_EXECUTABLE", "build/extension/vertical_grid_study"
        )
    )
    if not executable.exists():
        pytest.skip(
            "Build vertical_grid_study or set DTCC_QES_STUDY_EXECUTABLE for worker integration"
        )
    return executable.resolve()

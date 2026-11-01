"""Height sampling checks independent of the urban flow parameterizations."""

from fixtures.results import wind_result

from dataclasses import replace


import gzip


import json


from pathlib import Path


import os


import subprocess


import tracemalloc


import numpy as np


import pytest


from dtcc_qes import _qes, wind


def manufactured():
    faces = np.array([0, 0.5, 1.25, 2.25, 4.25, 7.25], dtype=np.float32)
    centres = np.float32(0.5) * (faces[:-1] + faces[1:])
    x, y = np.arange(4, dtype=np.float32) + 0.5, np.arange(3, dtype=np.float32) + 0.5
    z, yy, xx = np.meshgrid(centres, y, x, indexing="ij")
    velocity = np.stack(
        (1 + 2 * z + 0.25 * xx, -2 + 0.5 * z - 0.5 * yy, 3 - 0.75 * z), axis=-1
    )
    return wind_result(
        velocity=velocity,
        x=x,
        y=y,
        z=centres,
        cell_flags=np.ones(z.shape, dtype=np.int32),
        origin=(1e9, -2e9, 100),
        crs="EPSG:3006",
        resolution=1,
        diagnostics=wind.SolveDiagnostics(1, 0, 1e-5, True),
        metadata={},
        z_faces=faces,
    )

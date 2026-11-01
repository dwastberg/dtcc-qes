from fixtures.results import wind_result
from copy import deepcopy


import json


import subprocess


import sys


import numpy as np


import pytest


from dtcc_core import builder, datasets


from dtcc_core.model import (
    Bounds,
    Building,
    City,
    FieldSlice,
    GeometryType,
    Raster,
    Surface,
    Transform,
    VolumeGrid,
)


from dtcc_qes import wind


from dtcc_qes.datasets import QESWindArgs, _field_slice


from dtcc_qes._dataset_city import prepare_city, _source_city


pytestmark = pytest.mark.usefixtures("dtcc_logger")


def building(name, x=10.0, y=10.0, width=6.0, height=6.0, holes=False):
    obj = Building(id=name)
    obj.estimated_height = height
    vertices = np.array(
        [[x, y, 0], [x + width, y, 0], [x + width, y + width, 0], [x, y + width, 0]],
        dtype=float,
    )
    interior = (
        [
            np.array(
                [
                    [x + 1, y + 1, 0],
                    [x + 2, y + 1, 0],
                    [x + 2, y + 2, 0],
                    [x + 1, y + 2, 0],
                ],
                dtype=float,
            )
        ]
        if holes
        else []
    )
    obj.add_geometry(Surface(vertices=vertices, holes=interior), GeometryType.LOD0)
    return obj


@pytest.fixture
def source_city():
    city = City(transform=Transform(srs="EPSG:3006"))
    city.add_building(building("a"))
    return city


@pytest.fixture
def fetched(monkeypatch, source_city):
    calls = []

    def fetch(**kwargs):
        calls.append(kwargs)
        return source_city

    monkeypatch.setattr(datasets, "city", fetch)
    return calls


def request(**kwargs):
    return dict(
        bounds=[0, 0, 30, 24], horizontal_padding=6.0, vertical_clearance=6.0, **kwargs
    )


def realization(obj):
    return obj.provenance.processing_steps[-1]


def coded_result(*, speed=5.0):
    z, y, x = np.indices((2, 4, 3))
    codes = (100 * z + 10 * y + x).astype(np.float32)
    velocity = np.stack([codes, codes + 1000, codes + 2000], axis=-1)
    from dtcc_qes.profiles import _profile_record

    return wind_result(
        velocity=velocity,
        x=np.arange(3) + 0.5,
        y=np.arange(4) + 0.5,
        z=np.arange(2) + 0.5,
        cell_flags=codes.astype(np.int32) + 3,
        origin=(300000, 6400000, 50),
        crs="EPSG:3006",
        resolution=1.0,
        diagnostics=wind.SolveDiagnostics(1, 0, 1e-5, True),
        metadata={
            "profile": _profile_record(wind.LogProfile(speed, 270), None),
            "domain": {"effective_bounds": (300000, 6400000, 50, 300003, 6400004, 52)},
        },
    )

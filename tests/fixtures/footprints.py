"""Geometry preparation against the pinned Core cleaning implementation."""

from copy import deepcopy


from dataclasses import FrozenInstanceError


from types import SimpleNamespace


import numpy as np


import pytest


from shapely.geometry import Polygon, box


from shapely.ops import unary_union


from dtcc_core.model import (
    Building,
    BuildingPart,
    City,
    GeometryType,
    MultiSurface,
    Surface,
)


from dtcc_qes import wind


from dtcc_qes import _footprints


from dtcc_qes._footprints import prepare_footprints, merge_roof_cells


from dtcc_qes.footprints import Footprints


def surface(polygon, z=0):
    return Surface(
        vertices=np.c_[
            polygon.exterior.coords, np.full(len(polygon.exterior.coords), z)
        ],
        holes=[np.c_[h.coords, np.full(len(h.coords), z)] for h in polygon.interiors],
    )


def building(name, polygon, height, z=0):
    value = Building(id=name)
    value.measured_height = height
    value.add_geometry(surface(polygon, z), GeometryType.LOD0)
    return value


def city(*buildings):
    value = City()
    value.add_buildings(list(buildings))
    return value


def prepare(value, **kwargs):
    return prepare_footprints(value, settings=Footprints(min_detail=0.01, **kwargs))


def finalize(prepared, **kwargs):
    from dtcc_qes._footprints import finalize_footprints

    defaults = dict(
        effective_faces=np.arange(0, 41),
        origin=(-20, -20, 0),
        shape=(40, 60, 80),
        resolution=1,
    )
    return finalize_footprints(prepared, **(defaults | kwargs))

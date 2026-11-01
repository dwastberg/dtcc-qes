"""Turbulence domain growth, prefix preservation and native margin equivalence."""

import json


import numpy as np


import pytest


from dtcc_core.model import Building, City, GeometryType, Surface


from dtcc_qes import _qes, wind


from dtcc_qes import _city


from dtcc_qes.vertical_grid import effective_faces


from fixtures.cases import FLAT, ONE_BUILDING


from runner_cases import inputs


pytestmark = pytest.mark.usefixtures("dtcc_logger")


def blocks(heights=(15, 15, 15, 15), *, base=0, width=12):
    city = City()
    for i, height in enumerate(heights):
        x, y = 22 + (i % 2) * 20, 22 + (i // 2) * 20
        building = Building(id=str(i))
        building.measured_height = float(height)
        building.add_geometry(
            Surface(
                vertices=np.array(
                    [
                        [x, y, base],
                        [x, y + width, base],
                        [x + width, y + width, base],
                        [x + width, y, base],
                    ],
                    dtype=float,
                )
            ),
            GeometryType.LOD0,
        )
        city.add_building(building)
    return city


def assert_margin(preview, reference):
    assert preview.z_faces.dtype == np.float32
    assert len(preview.z_faces) >= 4
    assert preview.z_faces[-4] >= reference and preview.z_faces[-1] >= 15
    record = preview.domain["turbulence"]
    assert record["reference_height"] == reference
    assert record["effective_top"] == float(preview.z_faces[-1])
    assert record["required_top"] <= record["effective_top"]
    json.dumps(preview.domain, allow_nan=False)

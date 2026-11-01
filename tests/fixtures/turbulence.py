"""Public turbulence fields, analytic statistics and conservative stress sampling."""

from fixtures.results import turbulence_fields

from dataclasses import FrozenInstanceError, replace


import json


import numpy as np


import pytest


from dtcc_qes import _qes, wind


from dtcc_qes import result as result_module


from fixtures.cities import city_case


from fixtures.cases import FLAT, ONE_BUILDING


from fixtures.turbulence_cases import CASES as TURBULENCE_CASES


from fixtures.sampling import manufactured


pytestmark = pytest.mark.usefixtures("dtcc_logger")


def solve(case=ONE_BUILDING, **options):
    city, condition, grid, solver = city_case(case)
    updates = {
        k: options.pop(k)
        for k in ("speed", "direction", "reference_height", "roughness_length")
        if k in options
    }
    if updates:
        condition["profile"] = replace(condition["profile"], **updates)
    return wind.run(
        city,
        **(condition | grid | solver | dict(turbulence=wind.Turbulence()) | options),
    )


def synthetic():
    result = manufactured()
    shape = result.cell_flags.shape
    stress = np.zeros((*shape, 6), dtype=np.float32)
    stress[..., 0], stress[..., 3], stress[..., 5] = 4, 2, 1
    fields = turbulence_fields(
        stress=stress,
        tke=np.ones(shape, dtype=np.float32),
        co_eps=np.ones(shape, dtype=np.float32),
        mixing_length=np.ones(shape, dtype=np.float32),
        computed=np.ones(shape, dtype=bool),
        capped=np.zeros(shape, dtype=bool),
        stress_valid=np.ones(shape, dtype=bool),
        friction_velocity=0.2,
        reference_speed=5,
        reference_height=10,
        roughness_length=0.1,
        displacement_height=0,
    )
    return replace(result, turbulence=fields)


def uniform_synthetic():
    source = synthetic()
    nz = len(source.z)
    return replace(
        source,
        z=np.arange(nz, dtype=np.float32) + 0.5,
        z_faces=np.arange(nz + 1, dtype=np.float32),
    )

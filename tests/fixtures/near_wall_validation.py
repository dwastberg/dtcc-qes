"""Independent point-reconstruction checks before interpreting urban probes."""

import copy


from itertools import product


from pathlib import Path


import sys


import numpy as np


import pytest


sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))


from near_wall_sampling import difference, interpolate, reconstruct


sys.path.pop(0)


def patch(spacing, point, function):
    faces = np.arange(0, 4 + spacing / 2, spacing)
    centres = (faces[:-1] + faces[1:]) / 2
    cells = [
        dict(position=list(p), flag=1, velocity=function(*p))
        for p in product(centres, repeat=3)
    ]
    components = []
    for c in range(3):
        axes = [faces if d == c else centres for d in range(3)]
        components.append(
            [
                dict(position=list(p), flags=[1, 1], value=function(*p)[c])
                for p in product(*axes)
            ]
        )
    # Match the bridge: averages of float32 face operands, stored in float32.
    for row in cells:
        p = row["position"]
        row["velocity"] = [
            float(
                np.float32(0.5)
                * (
                    np.float32(
                        function(
                            *[v - spacing / 2 if d == c else v for d, v in enumerate(p)]
                        )[c]
                    )
                    + np.float32(
                        function(
                            *[v + spacing / 2 if d == c else v for d, v in enumerate(p)]
                        )[c]
                    )
                )
            )
            for c in range(3)
        ]
    return dict(local_point=point, query_flag=1, cells=cells, faces=components)

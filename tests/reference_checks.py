"""Numerical policy shared by the binding and public API reference checks."""

import platform
import sys
import numpy as np
from dtcc_qes import _qes


def assert_reference_velocity(actual, expected):
    # Exact on the recorded Apple Clang 17 / arm64 / Release toolchain.
    # Other compiler/libm implementations may round float32 profiles and SOR
    # updates differently. Classification and coordinate tests stay exact.
    reference_toolchain = (sys.platform == "darwin" and platform.machine() == "arm64"
                           and _qes.compiler_id == "AppleClang"
                           and _qes.compiler_version.split(".")[0] == "17"
                           and _qes.build_type == "Release")
    if reference_toolchain:
        np.testing.assert_array_equal(actual, expected)
    else:
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=2e-5)

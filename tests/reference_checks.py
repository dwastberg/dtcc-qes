"""Numerical policy shared by the binding and public API reference checks."""

import platform
import sys
import numpy as np
from dtcc_qes import _qes


def assert_reference_velocity(actual, expected):
    # Frozen fixtures use lexicographic ordering. S2 defaults to red/black in
    # both builds; its exact trajectory is checked by the S1a OpenMP oracle.
    # Other compiler/libm implementations may round float32 profiles and SOR
    # updates differently. Classification and coordinate tests stay exact.
    reference_toolchain = (sys.platform == "darwin" and platform.machine() == "arm64"
                           and _qes.compiler_id == "AppleClang"
                           and _qes.compiler_version.split(".")[0] == "17"
                           and _qes.build_type == "Release"
                           and getattr(_qes,"cpu_sweep_order", "red_black" if _qes.openmp_enabled else "lexicographic") == "lexicographic")
    if reference_toolchain:
        np.testing.assert_array_equal(actual, expected)
    else:
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=2e-5)

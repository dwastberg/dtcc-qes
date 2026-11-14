"""Historical standalone and current embedded regression fixture locations."""
import json
import os
import platform
from pathlib import Path
import pytest
from dtcc_qes import _qes
from fixtures.cases import REFERENCE_DIR

DIRECTORY = Path(os.environ.get("DTCC_QES_TURBULENCE_REFERENCE_DIR", REFERENCE_DIR / "turbulence"))
UPSTREAM_REVISION = "dced7ec571487be7538eca17bfc25bb3262fb6d0"


def physics_directory():
    return DIRECTORY / "audited-physics" / ("openmp" if _qes.openmp_enabled else "serial")


def physics_reference(name):
    path = physics_directory() / f"{name}.npz"
    metadata = json.loads(path.with_suffix(".json").read_text())
    toolchain = metadata["toolchain"]
    if any(toolchain[key] != getattr(_qes, key) for key in
           ("compiler_id", "compiler_version", "build_type", "cpu_sweep_order", "openmp_enabled")) or (
           toolchain["machine"] != platform.machine() or toolchain["platform"] != platform.platform()):
        pytest.skip("Exact embedded fixtures require their recorded toolchain and backend")
    assert metadata["native_identity"] == _qes.solver_policy_revision
    return path

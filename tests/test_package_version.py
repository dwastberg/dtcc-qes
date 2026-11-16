"""The version recorded in results must be the version the package declares."""
from pathlib import Path
import tomllib

import dtcc_qes

ROOT = Path(__file__).resolve().parents[1]


def test_module_version_matches_pyproject():
    # __version__ is written into dataset provenance and run metadata, so a
    # release that bumps only pyproject.toml mislabels every result it produces.
    declared = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert dtcc_qes.__version__ == declared

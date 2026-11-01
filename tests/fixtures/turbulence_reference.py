"""Exact audited standalone parity; independent correctness remains mandatory."""

import json


import hashlib


import os


import platform


from dataclasses import asdict


from pathlib import Path


import numpy as np


import pytest


from dtcc_qes import _qes


from fixtures.cases import REFERENCE_DIR


from fixtures.turbulence_cases import CASES


from runner_cases import inputs


DIRECTORY = Path(
    os.environ.get("DTCC_QES_TURBULENCE_REFERENCE_DIR", REFERENCE_DIR / "turbulence")
)


UPSTREAM_REVISION = "dced7ec571487be7538eca17bfc25bb3262fb6d0"

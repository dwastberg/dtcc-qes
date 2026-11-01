"""Meaningful checks of candidate error budgets and spatial support handling."""

from fixtures.support import load_tool


import importlib.util


from pathlib import Path


import sys


import pytest


TOOLS = Path(__file__).resolve().parents[2] / "tools"


study = load_tool("practical_vertical_grid", TOOLS / "run_practical_vertical_grid.py")


sys.path.insert(0, str(TOOLS))

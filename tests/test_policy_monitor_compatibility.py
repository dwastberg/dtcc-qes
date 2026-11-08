"""The release gate must reject changes beyond disabled diagnostic metadata."""
from pathlib import Path

import pytest

from fixtures.support import load_tool


gate = load_tool("check_policy_compatibility", Path(__file__).parents[1] / "tools/check_policy_compatibility.py")


def test_disabled_monitor_addition_requires_explicit_permission():
    frozen = {"region": [0, 10, 0, 10], "history_limit": 16}
    current = {**frozen, "turbulence": False}
    assert not gate.monitor_compatible(current, frozen)
    assert gate.monitor_compatible(current, frozen, True)
    assert "turbulence" not in frozen and "turbulence" in current
    assert not gate.monitor_compatible({**current, "history_limit": 15}, frozen, True)
    assert not gate.monitor_compatible({**current, "unknown": False}, frozen, True)


@pytest.mark.parametrize("value", [True, 0, None, "false"])
def test_monitor_exception_does_not_hide_enabling_or_corrupting_diagnostics(value):
    assert not gate.monitor_compatible({"turbulence": value}, {}, True)

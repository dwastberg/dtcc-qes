"""Check independent raw-face auditing detects extraction errors."""

from fixtures.support import load_tool
import copy
import importlib.util
from pathlib import Path

import pytest

from fixtures.near_wall_validation import patch

audit=load_tool("near_wall_audit", Path(__file__).parents[1]/"tools/audit_near_wall_validation.py")


def test_native_component_audit_detects_wrong_face_and_incident_flag():
    p=patch(.5,[1,1.5,1.75],lambda x,y,z:[x*x,y+z,z*z])
    assert audit.check_patch(p)>0
    q=copy.deepcopy(p)
    q["faces"][0][0]["value"]+=1
    with pytest.raises(ValueError,match="averaging"):
        audit.check_patch(q)
    q=copy.deepcopy(p)
    q["faces"][0][0]["flags"][1]=0
    with pytest.raises(ValueError,match="flag"):
        audit.check_patch(q)


def test_missing_face_is_not_silently_ignored():
    p=patch(1,[1,1,1],lambda x,y,z:[x,y,z])
    p["faces"][0].pop(0)
    with pytest.raises((KeyError,ValueError)):
        audit.check_patch(p)

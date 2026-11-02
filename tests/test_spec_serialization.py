"""Versioned immutable feature specifications survive strict JSON round trips."""
import json

import pytest

from dtcc_qes.wind import Parameterizations, Turbulence, VerticalGrid


@pytest.mark.parametrize("value", [Turbulence(), Turbulence("wall_distance"),
    VerticalGrid.from_faces([0,1,2,4]), VerticalGrid.auto(growth_rate=1.1, upper_layer_cap=8),
    Parameterizations(), Parameterizations(high_rise=1, wake=1, wall_roughness=0.01)])
def test_spec_json_roundtrip_is_owned_and_strict(value):
    payload = value.to_dict()
    assert type(value).from_dict(json.loads(json.dumps(payload))) == value
    payload["unknown"] = True
    with pytest.raises(ValueError):
        type(value).from_dict(payload)
    assert "unknown" not in value.to_dict()
    for version in (None, True, 1.0, 2):
        with pytest.raises(ValueError, match="schema_version"):
            type(value).from_dict(dict(value.to_dict(), schema_version=version))


def test_explicit_grid_payload_mutation_does_not_change_spec():
    grid = VerticalGrid.from_faces([0,1,2,4])
    payload = grid.to_dict()
    payload["faces"][1] = 100
    assert grid.faces == (0,1,2,4)

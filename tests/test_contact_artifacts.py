"""Check the synthetic baseline's metrics and contact-check isolation."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from dtcc_qes import _city, wind

_spec = importlib.util.spec_from_file_location(
    "contact_artifacts", Path(__file__).parents[1] / "tools/contact_artifacts.py"
)
contacts = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = contacts
_spec.loader.exec_module(contacts)

pytestmark = pytest.mark.usefixtures("dtcc_logger")


def args(**overrides):
    return SimpleNamespace(
        **(
            dict(
                footprints="baseline",
                exposed_faces="off",
                min_detail=0.5,
                resolution=4.0,
                iterations=3,
                height=2.0,
                case=["split", "separated_order"],
            )
            | overrides
        )
    )


def snapshot(plane, flags, valid=None, iterations=10):
    plane = np.asarray(plane, dtype=np.float64)
    return dict(
        plane=plane,
        flags=np.asarray(flags),
        valid=np.ones(plane.shape[:-1], dtype=bool) if valid is None else np.asarray(valid),
        metadata=dict(diagnostics=dict(iterations=iterations), velocity_sha256=contacts.digest(plane)),
    )


def test_metric_is_speed_difference_on_common_fluid_samples():
    # Opposite vectors have the same speed. Invalid points and solids must not
    # inflate the speed metric or the changed-fluid-flag count.
    a = snapshot([[[3, 4, 0], [3, 4, 0], [999, 0, 0]]], [[[1, 1, 0]]], [[True, True, False]])
    b = snapshot([[[-3, -4, 0], [0, 0, 0], [0, 0, 0]]], [[[4, 1, 2]]], [[True, True, False]])
    row = contacts.compare(a, b)
    assert row["max_speed_difference_over_reference"] == 1
    assert row["rms_speed_difference_over_reference"] == pytest.approx(np.sqrt(0.5))
    assert row["common_fluid_samples"] == 2
    assert row["same_solid_mask"]
    assert row["changed_fluid_flags"] == 1
    assert not row["velocity_bit_identical"]


def test_mask_and_iteration_mismatches_are_visible():
    a = snapshot([[[1, 0, 0]]], [[[1]]])
    b = snapshot([[[1, 0, 0]]], [[[0]]], iterations=11)
    row = contacts.compare(a, b)
    assert not row["same_solid_mask"]
    assert row["solid_mask_changed_cells"] == 1
    assert not row["same_iterations"]


def test_empty_common_sample_is_an_error():
    value = snapshot([[[0, 0, 0]]], [[[0]]], [[False]])
    with pytest.raises(ValueError, match="no common fluid"):
        contacts.compare(value, value)


def test_baseline_solves_contacts_and_restores_public_contract():
    original = _city.reject_intersections
    # Resolve the 3 m gap with fluid cells; at 4 m this is another subcell case.
    document = contacts.run(args(resolution=1.0))
    assert _city.reject_intersections is original
    assert document["settings"]["contact_check_bypassed"]
    assert len(document["comparisons"]) == 2
    split, separated = document["comparisons"]
    assert split["same_solid_mask"] and split["same_iterations"]
    assert split["changed_fluid_flags"] > 0
    assert separated["velocity_bit_identical"] and separated["flags_bit_identical"]
    assert separated["max_speed_difference_over_reference"] == 0
    assert document["provenance"]["source_sha256"]["tools/contact_artifacts.py"]
    json.dumps(document, allow_nan=False)
    with pytest.raises(ValueError, match="overlapping or touching"):
        wind.preview_grid(contacts.make_city(contacts.fixtures()["split"]))


def test_contact_bypass_restored_after_solve_failure(monkeypatch):
    original = _city.reject_intersections

    def fail(*a, **kw):
        assert _city.reject_intersections is not original
        raise RuntimeError("deliberate solve failure")

    monkeypatch.setattr(wind, "run", fail)
    with pytest.raises(RuntimeError, match="deliberate"):
        contacts.solve(contacts.fixtures()["split"], args())
    assert _city.reject_intersections is original


def test_strict_mode_reports_contact_rejections_and_solves_disjoint_inputs():
    document = contacts.run(args(footprints="strict"))
    assert not document["settings"]["contact_check_bypassed"]
    assert document["comparisons"][0]["status"] == "rejected"
    assert document["comparisons"][1]["status"] == "compared"


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"exposed_faces": "on"}, "Exposure on requires resolve"),
    ],
)
def test_unimplemented_modes_are_not_silently_ignored(overrides, message):
    with pytest.raises(ValueError, match=message):
        contacts.run(args(**overrides))


def test_cli_writes_json_and_terminal_table(tmp_path, capsys):
    output = tmp_path / "baseline.json"
    assert (
        contacts.main(["--case", "split", "--iterations", "2", "--resolution", "4", "--output", str(output)])
        == 0
    )
    document = json.loads(output.read_text())
    assert document["schema_version"] == 1
    assert document["comparisons"][0]["status"] == "compared"
    assert "max dU/Uref" in capsys.readouterr().out

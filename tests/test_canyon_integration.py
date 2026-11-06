"""Private selector, lifecycle and ordinary-build contracts without study archives."""
import json
from pathlib import Path
import sys

import numpy as np
import pytest
from dtcc_qes import _qes, wind
from fixtures.canyon import fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
from aij.canyon import CanyonSession, native_mass, mass_gate
from aij.evidence import file_hash


def bits(a, b):
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def test_private_legacy_is_identical_to_public_default():
    args = fixture(); session = CanyonSession()
    try:
        private, stages = session.run(args)
        public = wind.run(args["city"], args["profile"], **args["run"])
        assert bits(private.velocity, public.velocity)
        assert bits(private.cell_flags, public.cell_flags)
        assert stages["final_bitwise_parity"]
        assert private.metadata["experiment"]["canyon_changed_faces"] == 0
        assert private.solver["record"] is None
    finally: session.close()


@pytest.mark.parametrize("model", ["horizontal_reference_v1", "joined_v1"])
def test_active_horizontal_modes_preserve_W_roof_and_stage_coverage(model):
    session = CanyonSession(); args = fixture()
    try:
        legacy, old = session.run(args)
        candidate, new = session.run(args, model=model, trace=True)
        e = candidate.metadata["experiment"]
        assert e["canyon_qualified"] == 1 and e["canyon_changed_faces"] > 0
        assert e["canyon_roof_changes"] == e["canyon_voxel_roof_changes"] == e["canyon_W_changes"] == 0
        assert e["canyon_roof_trace"].shape == (0, 13)
        assert bits(e["canyon_initial_w"], legacy.metadata["experiment"]["canyon_initial_w"])
        assert np.isfinite(candidate.velocity).all() and candidate.diagnostics.converged
        assert np.array_equal(old["method"], new["method"])
        assert bits(old["velocity"][:3], new["velocity"][:3])
        assert all(mass_gate(native_mass(candidate,5.), native_mass(legacy,5.),5.,e["boundary_flux_area"]).values())
        assert session.preparations == 1 and e["cache_hit"]
        restored, _ = session.run(args)
        assert bits(restored.velocity, legacy.velocity)
        assert restored.metadata["experiment"]["canyon_qualified"] == 0
    finally: session.close()


def test_oblique_fallback_keeps_complete_legacy_field():
    session = CanyonSession(); args = fixture(oblique=True)
    try:
        legacy, _ = session.run(args)
        candidate, _ = session.run(args, model="joined_v1")
        assert bits(legacy.velocity, candidate.velocity)
        assert candidate.metadata["experiment"]["canyon_fallback"] > 0
        assert candidate.metadata["experiment"]["canyon_changed_faces"] == 0
    finally: session.close()


@pytest.mark.parametrize("kwargs", [dict(canyon_model="invented"), dict(omega=1.9),
    dict(checkpoints=[1]), dict(wake_composition=1), dict(building_order=1),
    dict(canopy_factors=np.array([1.],dtype=np.float32)), dict(export_projection=True),
    dict(canopy_shape=[0, 0, 0]), dict(canopy_origin=[0., 0.]), dict(canopy_pitch=20.),
    dict(canopy_taper=10.), dict(canopy_occupied=None), dict(checkpoint_layers=[0, 1]),
    dict(target_velocity=None), dict(target_mass=[]), dict(boundary_flux_area=0.),
    dict(boundary_flux_tolerance=1e-4), dict(export_limit_bytes=1024),
    dict(export_mixing_length=False), dict(wake_attribution=False), dict(wake_event_limit=100000)])
def test_invalid_or_stacked_options_cannot_contaminate_reused_runner(kwargs):
    session = CanyonSession(); args = fixture()
    try:
        baseline, _ = session.run(args)
        condition = wind._native_condition(session.prepared.domain["profile"])
        options = wind._native_solver(args["run"]["solver"])
        with pytest.raises(ValueError if "canyon_model" in kwargs else TypeError):
            session.runner._solve_experiment(condition, options, **kwargs)
        restored, _ = session.run(args)
        assert bits(baseline.velocity, restored.velocity)
    finally: session.close()


def test_specification_and_ordinary_hook_defaults():
    root = Path(__file__).resolve().parents[1]
    spec = root / "validation/specifications/canyon-join-v1.json"
    assert json.loads(spec.read_text())["fitting"] is False
    assert file_hash(spec) in (root / "src/qes_core/dtcc/api/canyon_types.h").read_text()
    assert not hasattr(_qes.WindRunner(), "_test_canyon_failure")
    with pytest.raises(ValueError): wind.Parameterizations(street_canyon=2)


@pytest.mark.parametrize("height", [10., 11.5])
def test_nonuniform_grid_protects_both_sides_of_roof_representation(height):
    args = fixture(height=height, nonuniform=True); session = CanyonSession()
    try:
        legacy, old = session.run(args)
        candidate, new = session.run(args, model="joined_v1", trace=True)
        e = candidate.metadata["experiment"]
        assert e["canyon_qualified"] == 1 and e["canyon_changed_faces"] > 0
        assert e["canyon_roof_changes"] == e["canyon_voxel_roof_changes"] == e["canyon_W_changes"] == 0
        assert bits(e["canyon_initial_w"], legacy.metadata["experiment"]["canyon_initial_w"])
        assert candidate.diagnostics.converged and legacy.diagnostics.converged
        assert np.array_equal(old["method"], new["method"])
    finally: session.close()


@pytest.mark.parametrize("method", ["height", "wall_distance"])
def test_turbulence_allowance_is_explicit_and_limited_to_standard_method(method):
    args = fixture(); args["run"]["turbulence"] = wind.Turbulence(method)
    session = CanyonSession()
    try:
        with pytest.raises(ValueError): session.run(args, model="joined_v1")
        if method == "height":
            result, _ = session.run(args, model="joined_v1", baseline_turbulence=True)
            assert result.metadata["experiment"]["canyon_changed_faces"] > 0
        else:
            with pytest.raises(ValueError): session.run(args, model="joined_v1", baseline_turbulence=True)
    finally: session.close()


def test_private_selection_cannot_inherit_bounded_or_adaptive_control():
    args = fixture(); session = CanyonSession()
    try:
        session.run(args)
        control = wind.Solver(max_solve_seconds=10, monitor=wind.MonitorSpec((0, 80, 0, 60)))
        condition = wind._native_condition(session.prepared.domain["profile"])
        options = wind._native_solver(args["run"]["solver"])
        with pytest.raises(TypeError, match="incompatible function arguments"):
            session.runner._solve_experiment(condition, options, control=control._native((0,0,0),None))
        args["run"]["solver"] = control
        with pytest.raises(ValueError, match="explicit legacy"):
            session.run(args, model="joined_v1")
    finally: session.close()


def test_turning_subroof_profile_falls_back_without_writes():
    args = fixture(); session = CanyonSession()
    try:
        session.run(args)
        condition = wind._native_condition(session.prepared.domain["profile"])
        options = wind._native_solver(args["run"]["solver"])
        condition.profile_kind = _qes.ProfileKind.layer_table
        condition.layer_u = [5.] * session.prepared.grid.nz
        condition.layer_v = [2.] * 4 + [0.] * (session.prepared.grid.nz - 4)
        baseline = session.runner._solve_experiment(condition, options, canyon_capture=True)
        candidate = session.runner._solve_experiment(condition, options, canyon_model="joined_v1", canyon_capture=True)
        assert bits(baseline["velocity"], candidate["velocity"])
        assert candidate["experiment"]["canyon_changed_faces"] == 0
        assert candidate["experiment"]["canyon_fallback_reasons"]["unsupported_incident_profile"] == 1
    finally: session.close()

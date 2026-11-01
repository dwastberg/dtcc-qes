from fixtures.oracles import covariance, assert_turbulence_archive
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

DIRECTORY = Path(os.environ.get("DTCC_QES_TURBULENCE_REFERENCE_DIR", REFERENCE_DIR / "turbulence"))
UPSTREAM_REVISION = "dced7ec571487be7538eca17bfc25bb3262fb6d0"


@pytest.mark.parametrize("spec", CASES.values(), ids=CASES)
def test_bound_runner_turbulence_matches_audited_reference(spec):
    directory = DIRECTORY / "audited"
    metadata = json.loads((directory / f"{spec.case.name}.json").read_text())
    assert metadata["qes"]["revision"] == _qes.qes_revision
    assert not metadata["qes"]["modified"]
    toolchain = metadata["toolchain"]
    if (toolchain["compiler_id"] != _qes.compiler_id
            or toolchain["compiler_version"] != _qes.compiler_version
            or toolchain["build_type"] != _qes.build_type
            or toolchain["machine"] != platform.machine()
            or toolchain["platform"] != platform.platform() or _qes.cpu_sweep_order != "lexicographic"):
        pytest.skip("Archived exact fixtures require lexicographic ordering and their recorded toolchain; "
                    "S2 red/black parity is checked against the immutable S1a OpenMP oracle")
    grid, model, condition, solver, arrays = inputs(spec.case)
    settings = _qes.TurbulenceSettings()
    settings.enabled = True
    settings.mixing_length_method = spec.method
    runner = _qes.WindRunner()
    layers = np.asarray(spec.dz_layers, dtype=np.float64) if spec.dz_layers else None
    runner.prepare(grid, model, **arrays, turbulence=settings, dz_layers=layers)
    result = runner.solve(condition, solver)
    assert result["diagnostics"]["converged"]
    with np.load(directory / f"{spec.case.name}.npz") as reference:
        for axis in ("x", "y", "z"):
            np.testing.assert_array_equal(result[axis], reference[axis])
        np.testing.assert_array_equal(result["velocity"], np.stack([reference[key] for key in ("u", "v", "w")], axis=-1))
        np.testing.assert_array_equal(result["cell_flags"], reference["icell"])
        fields = result["turbulence"]
        assert_turbulence_archive(fields,reference,fields["state"]>0)


@pytest.mark.parametrize("baseline", ["upstream", "audited"])
@pytest.mark.parametrize("spec", CASES.values(), ids=CASES)
def test_reference_provenance_and_uncomputed_values(baseline, spec):
    directory = DIRECTORY / baseline
    path = directory / f"{spec.case.name}.npz"
    if baseline == "upstream" and spec.upstream_exclusion:
        assert not path.exists() and not path.with_suffix(".json").exists()
        return
    metadata = json.loads(path.with_suffix(".json").read_text())
    assert metadata["baseline"] == baseline and metadata["schema_version"] == 1
    expected = UPSTREAM_REVISION if baseline == "upstream" else _qes.qes_revision
    assert metadata["qes"]["revision"] == expected and metadata["qes"]["modified"] is False
    assert metadata["qes"]["verified_files"] > 0
    assert len(metadata["qes"]["tree"]) == 40
    assert len(metadata["qes"]["source_manifest_sha256"]) == 64
    assert metadata["archive_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(metadata["executable_sha256"]) == 64
    assert metadata["solver_summary"]["converged"]
    assert metadata["case"] == spec.case.name
    assert metadata["case_definition"] == json.loads(json.dumps({
        "case": asdict(spec.case), "mixing_length_method": spec.method, "dz_layers": spec.dz_layers}))
    assert metadata["upstream_exclusions"] == {
        name: item.upstream_exclusion for name, item in CASES.items() if item.upstream_exclusion}
    assert metadata["build_options"] == {
        "ENABLE_OPENMP": "OFF", "QES_ENABLE_IO": "ON", "QES_ENABLE_CUDA": "OFF",
        "QES_ENABLE_OPTIX": "OFF", "QES_BUILD_EXECUTABLES": "ON",
        "CMAKE_POSITION_INDEPENDENT_CODE": "ON", "CMAKE_CXX_STANDARD": "17"}
    assert metadata["stress_components"] == ["txx", "txy", "txz", "tyy", "tyz", "tzz"]
    with np.load(path) as reference:
        shape = (spec.case.grid.nz, spec.case.grid.ny, spec.case.grid.nx)
        computed = reference["computed"].astype(bool)
        assert computed.shape == shape and reference["computed"].dtype == np.uint8
        assert not computed[-1].any() and not computed[:,(0,-1),:].any() and not computed[:,:,(0,-1)].any()
        assert not computed[np.isin(reference["icell"], (0,2))].any()
        for name in ("stress", "tke", "co_eps", "mixing_length"):
            assert reference[name].dtype == np.float32
            assert reference[name].shape == ((*shape,6) if name == "stress" else shape)
            assert np.isfinite(reference[name]).all()
            assert np.all(reference[name][~computed] == 0)
        if spec.dz_layers:
            np.testing.assert_array_equal(reference["dz_array"][1:], np.float32(spec.dz_layers))
        if spec.case.buildings:
            # QES marks wall cells in the uncomputed last column, too.
            assert ((reference["iturbflag"] > 0) & ~computed).any()


@pytest.mark.parametrize("name", [name for name,spec in CASES.items() if not spec.upstream_exclusion])
def test_upstream_differences_are_confined_to_named_repairs(name):
    spec = CASES[name]
    with np.load(DIRECTORY / "upstream" / f"{name}.npz") as before, np.load(DIRECTORY / "audited" / f"{name}.npz") as after:
        # These shared cases do not exercise the fork's earlier vertical-RHS
        # correction. Preserve exact wind, geometry and coverage assertions.
        unaffected = ("x", "y", "z", "u", "v", "w", "icell", "x_face", "y_face", "z_face",
                      "u_face", "v_face", "w_face", "icellflag_full", "dz_array", "computed", "iturbflag")
        if spec.method == 0:
            unaffected += ("tke", "co_eps", "mixing_length")
        if name == "flat":
            unaffected += ("stress",)
        for field in unaffected:
            np.testing.assert_array_equal(after[field], before[field])
        if name != "flat":
            assert not np.array_equal(after["stress"], before["stress"])
        if spec.method == 1:
            for field in ("tke", "co_eps", "mixing_length"):
                assert not np.array_equal(after[field], before[field])


def test_oblique_flat_stress_has_the_analytic_streamwise_covariance():
    with np.load(DIRECTORY / "audited" / "flat_oblique.npz") as after, np.load(DIRECTORY / "upstream" / "flat_oblique.npz") as before:
        for k in range(1, after["z"].size-1):
            velocity = np.array([after["u"][k,10,10],after["v"][k,10,10],0.0],dtype=np.float64)
            n = velocity / np.linalg.norm(velocity)
            gradient = np.hypot(after["u"][k+1,10,10]-after["u"][k-1,10,10],
                                after["v"][k+1,10,10]-after["v"][k-1,10,10]) / 4.0
            expected=covariance(n,after["mixing_length"][k,10,10],gradient)
            np.testing.assert_allclose(after["stress"][k,10,10], expected, rtol=1e-5, atol=1e-7)
        # At z=9 m the upstream swapped anisotropy gives sigma 20% too low.
        project = lambda s: 0.5*(s[0]+2*s[1]+s[3])
        actual = np.sqrt(project(after["stress"][4,10,10]))
        original = np.sqrt(project(before["stress"][4,10,10]))
        assert original / actual == pytest.approx(0.8, rel=1e-6)

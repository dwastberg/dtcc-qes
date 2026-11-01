"""Unit checks for the native build parity harness (the builds themselves are not run)."""

from fixtures.support import load_tool

import importlib.util
import io
from pathlib import Path
import tarfile

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
harness = load_tool("compare_native_builds", ROOT / "tools/compare_native_builds.py")


def save(path, **values):
    np.savez(path, _module=np.array(str(path)), **values)
    return path


def test_identical_results_ignore_module_path(tmp_path):
    a = save(tmp_path / "a.npz", v=np.arange(4, dtype=np.float32))
    b = save(tmp_path / "b.npz", v=np.arange(4, dtype=np.float32))
    assert harness.compare_results(a, b) == ([], 1)


def test_bit_dtype_shape_and_key_differences_are_reported(tmp_path):
    v = np.array([0.0, 1.0], dtype=np.float32)
    a = save(tmp_path / "a.npz", bits=v, dtype=v, shape=v, only_a=v)
    b = save(tmp_path / "b.npz", bits=np.array([-0.0, 1.0], dtype=np.float32), dtype=v.astype(np.float64),
             shape=v.reshape(2, 1), only_b=v)
    problems, _ = harness.compare_results(a, b)
    assert problems == ["only in one result: only_a", "only in one result: only_b",
                        "differs: bits", "differs: dtype", "differs: shape"]


def test_store_flattens_nested_results():
    out = {}
    harness.store(out, "case", dict(velocity=np.zeros(3), diagnostics=dict(iterations=5), turbulence=None))
    assert set(out) == {"case/velocity", "case/scalars", "case/diagnostics/scalars"}
    assert str(out["case/diagnostics/scalars"]) == '{"iterations": 5}'


def test_clock_filter_keeps_work_decisions_shape_and_availability(tmp_path):
    def capture(seconds,native=True,iteration=25):
        out={}
        harness.store(out,"public/case",dict(metadata=dict(
            timings=dict(public_call_seconds=seconds,city_preparation_seconds=seconds/2,
                native=dict(solve_seconds=seconds) if native else None,scopes=dict(public_call="nested")),
            solver=dict(spec=dict(max_solve_seconds=60.),record=dict(
                termination_reason="iteration_limit",timings=dict(solve_seconds=seconds),
                history=[dict(elapsed_seconds=seconds,iteration=iteration,error=.1)])))))
        return out
    a=save(tmp_path/"a.npz",**capture(1.))
    assert not harness.compare_results(a,save(tmp_path/"b.npz",**capture(2.)))[0]
    assert harness.compare_results(a,save(tmp_path/"b.npz",**capture(2.,native=False)))[0]
    assert harness.compare_results(a,save(tmp_path/"b.npz",**capture(2.,iteration=50)))[0]
    assert '"max_solve_seconds": 60.0' in str(capture(1.)["public/case/metadata/solver/spec/scalars"])


@pytest.mark.parametrize("duration",[-1,float("nan"),float("inf"),True,"1"])
def test_public_and_native_clocks_reject_invalid_values(duration):
    report=dict(public_call_seconds=duration,city_preparation_seconds=None,native=None,scopes={})
    with pytest.raises(ValueError,match="Invalid timing"):
        harness.store({},"public/case/metadata/timings",report)
    with pytest.raises(ValueError,match="Invalid timing"):
        harness.store({},"public/case/metadata/solver/record/timings",dict(solve_seconds=duration))


def test_s0_provenance_exception_is_narrow_and_opt_in(tmp_path):
    key = "public/case/metadata/versions/native_build/scalars"
    a = save(tmp_path / "a.npz", **{key: np.array('{"openmp_enabled": true}')})
    b = save(tmp_path / "b.npz", **{key: np.array('{"fp_contract": "on", "openmp_enabled": true}')})
    assert harness.compare_results(a, b)[0]
    assert not harness.compare_results(a, b, allow_added_contraction=True)[0]
    b = save(tmp_path / "b.npz", **{key: np.array('{"fp_contract": "on", "openmp_enabled": false}')})
    assert harness.compare_results(a, b, allow_added_contraction=True)[0]


def test_backend_pair_keeps_numerical_diagnostics_strict(tmp_path):
    def record(backend, enabled, iterations):
        out = {}
        harness.store(out, "public/case", dict(metadata=dict(model=dict(backend=backend),
            versions=dict(native_build=dict(openmp_enabled=enabled, fp_contract="on"))),
            diagnostics=dict(iterations=iterations)))
        return out
    a = save(tmp_path / "a.npz", **record("serial CPU", False, 10))
    b = save(tmp_path / "b.npz", **record("OpenMP CPU", True, 10))
    assert not harness.compare_results(a, b, backend_pair=True)[0]
    b = save(tmp_path / "b.npz", **record("OpenMP CPU", True, 11))
    assert harness.compare_results(a, b, backend_pair=True)[0] == ["differs: public/case/diagnostics/scalars"]


def test_solver_environment_backend_exception_keeps_precision_strict(tmp_path):
    def record(backend, enabled, precision="float32"):
        out = {}
        harness.store(out, "public/case", dict(metadata=dict(solver=dict(
            spec=dict(precision=precision), record=None,
            environment=dict(backend=backend, precision=precision,
                native_build=dict(openmp_enabled=enabled, fp_contract="on"))))))
        return out
    a = save(tmp_path/"a.npz", **record("serial CPU", False))
    b = save(tmp_path/"b.npz", **record("OpenMP CPU", True))
    assert harness.compare_results(a,b)[0]
    assert not harness.compare_results(a,b,backend_pair=True)[0]
    b = save(tmp_path/"b.npz", **record("OpenMP CPU", True, "float64"))
    assert harness.compare_results(a,b,backend_pair=True)[0] == [
        "differs: public/case/metadata/solver/environment/scalars",
        "differs: public/case/metadata/solver/spec/scalars"]


@pytest.mark.parametrize("corruption", [None, "serial_value", "openmp_value", "new_key", "missing_key"])
def test_ordering_migration_requires_the_complete_oracle(tmp_path, corruption):
    serial = save(tmp_path/"serial.npz", velocity=np.array([1.,2.]), flags=np.array([1,1]))
    openmp = save(tmp_path/"openmp.npz", velocity=np.array([3.,4.]), flags=np.array([1,1]))
    candidate_serial = dict(velocity=np.array([3.,4.]), flags=np.array([1,1]))
    candidate_openmp = dict(candidate_serial)
    if corruption == "serial_value": candidate_serial["velocity"] = np.array([3.,5.])
    if corruption == "openmp_value": candidate_openmp["velocity"] = np.array([3.,5.])
    if corruption == "new_key": candidate_serial["unexpected"] = np.array(1)
    if corruption == "missing_key": del candidate_serial["flags"]
    a = save(tmp_path/"candidate-serial.npz", **candidate_serial)
    b = save(tmp_path/"candidate-openmp.npz", **candidate_openmp)
    result = harness.compare_ordering_migration(serial,openmp,a,b)
    assert result["passed"] == (corruption is None)
    assert result["expected_serial_differences"] == ["differs: velocity"]
    # Strict revision comparison stays strict even for the intended change.
    assert harness.compare_results(serial,a)[0]


def source_archive(path, names):
    with tarfile.open(path, 'w:gz') as archive:
        for name in names:
            info = tarfile.TarInfo(name)
            info.size = 1
            archive.addfile(info, io.BytesIO(b'\n'))
    return path


def test_source_archive_identity_and_cache(tmp_path):
    path = source_archive(tmp_path/'sources.tar.gz',
                          ['CMakeLists.txt', 'pyproject.toml', 'src/qes_core/CMakeLists.txt'])
    first = harness.export_archive(path, tmp_path/'work')
    assert first == harness.export_archive(path, tmp_path/'work')
    assert first[2].startswith('sha256:') and len(first[2]) == 71
    path = source_archive(path, ['CMakeLists.txt', 'pyproject.toml', 'src/qes_core/CMakeLists.txt', 'new.cpp'])
    assert harness.export_archive(path, tmp_path/'work') != first


def test_staged_package_disables_only_its_editable_redirector(tmp_path):
    tree=tmp_path/'tree';(tree/'src/dtcc_qes').mkdir(parents=True)
    (tree/'src/dtcc_qes/__init__.py').write_text('')
    binary=tmp_path/'_qes.fake.so';binary.write_bytes(b'probe')
    package=tmp_path/'package';harness.stage_package(tree,binary,package)
    class Redirector:
        def __init__(self,name): self.known_source_files={name:'somewhere'}
    import sys
    qes,dependency=Redirector('dtcc_qes.wind'),Redirector('dtcc_core')
    old=sys.meta_path[:]
    try:
        sys.meta_path.extend([qes,dependency])
        exec((package/'sitecustomize.py').read_text(),{})
        assert qes not in sys.meta_path and dependency in sys.meta_path
    finally:
        sys.meta_path[:]=old


def test_incomplete_and_escaping_source_archives_are_rejected(tmp_path):
    path = source_archive(tmp_path/'sources.tar.gz', ['CMakeLists.txt'])
    with pytest.raises(ValueError, match='omits pyproject.toml'):
        harness.export_archive(path, tmp_path/'work')
    source_archive(path, ['../../escaped.txt'])
    with pytest.raises(tarfile.FilterError):
        harness.export_archive(path, tmp_path/'work')
    assert not (tmp_path/'escaped.txt').exists()

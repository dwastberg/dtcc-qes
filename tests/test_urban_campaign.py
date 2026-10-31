"""Campaign orchestration and safe reuse of independently cached solver builds."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
try:
    import run_urban_benchmarks as runner
finally:
    sys.path.pop(0)


@pytest.fixture
def fake_builds(tmp_path, monkeypatch):
    built = []
    dependency = tmp_path / "libomp"
    dependency.write_bytes(b"runtime-v1")

    def export(archive, work):
        tree = work / "tree"
        tree.mkdir(parents=True)
        return tree, "test", "sha256:" + runner.benchmark.digest(archive)

    def archive(path, files, tree):
        path.write_bytes(b"instrumented sources")
        return dict(sha256=runner.benchmark.digest(path), files={})

    def build(tree, directory, backend):
        built.append(backend)
        directory.mkdir()
        return directory / "_qes.so"

    def stage(tree, module, package):
        package.mkdir()
        (package / "module.py").write_text("cached package")

    monkeypatch.setattr(runner.native, "export_archive", export)
    monkeypatch.setattr(runner.benchmark, "instrument_team_probe", lambda tree: None)
    monkeypatch.setattr(runner, "archive_files", archive)
    monkeypatch.setattr(runner, "source_files", lambda tree: [])
    monkeypatch.setattr(runner.native, "build", build)
    monkeypatch.setattr(runner.native, "stage_package", stage)
    monkeypatch.setattr(runner, "verify_package", lambda *args: None)
    monkeypatch.setattr(runner, "dependency_files", lambda directory: {str(dependency): runner.file_identity(dependency)})
    source = tmp_path / "source.tar.gz"
    source.write_bytes(b"source-v1")
    return SimpleNamespace(source=source, cache=tmp_path / "cache", built=built, dependency=dependency)


def test_build_reuse_and_changed_source_toolchain_backend(fake_builds):
    f = fake_builds
    first, decision = runner.cached_build(f.source, "openmp", f.cache, {"compiler": "v1"})
    assert not decision["reused"]
    second, decision = runner.cached_build(f.source, "openmp", f.cache, {"compiler": "v1"})
    assert decision["reused"] and first == second and len(f.built) == 1
    runner.cached_build(f.source, "serial", f.cache, {"compiler": "v1"})
    runner.cached_build(f.source, "openmp", f.cache, {"compiler": "v2"})
    f.source.write_bytes(b"source-v2")
    runner.cached_build(f.source, "openmp", f.cache, {"compiler": "v1"})
    assert len(f.built) == 4


@pytest.mark.parametrize("damage", ["package", "runtime", "sources", "manifest", "schema", "import", "force"])
def test_damaged_or_forced_cache_rebuilds_without_deleting_previous_build(fake_builds, monkeypatch, damage):
    f = fake_builds
    first, decision = runner.cached_build(f.source, "openmp", f.cache, {})
    if damage == "package":
        (Path(first["package"]) / "module.py").write_text("edited")
    elif damage == "runtime":
        f.dependency.write_bytes(b"runtime-v2")
    elif damage == "sources":
        Path(first["instrumented_archive"]).unlink()
    elif damage == "manifest":
        (f.cache / "builds" / decision["key"] / "current.json").write_text("{broken")
    elif damage == "schema":
        manifest = f.cache / "builds" / decision["key"] / "current.json"
        record = json.loads(manifest.read_text())
        record["dependencies"] = []
        runner.benchmark.write(manifest, record)
    elif damage == "import":
        def verify(package, backend):
            if str(package) == first["package"]:
                raise RuntimeError("cannot load cached extension")
        monkeypatch.setattr(runner, "verify_package", verify)
    second, decision = runner.cached_build(f.source, "openmp", f.cache, {}, rebuild=damage == "force")
    assert not decision["reused"] and len(f.built) == 2
    assert second["package"] != first["package"]
    assert Path(first["package"]).exists()


def test_failed_build_is_not_promoted_to_reusable_cache(fake_builds, monkeypatch):
    f = fake_builds
    def fail(*args):
        raise RuntimeError("compiler failed")
    monkeypatch.setattr(runner.native, "build", fail)
    with pytest.raises(RuntimeError, match="compiler failed"):
        runner.cached_build(f.source, "openmp", f.cache, {})
    assert not list(f.cache.rglob("current.json"))
    assert list(f.cache.rglob("build.log"))


def test_python_abi_change_creates_a_new_cache_generation(fake_builds):
    f=fake_builds
    first,_=runner.cached_build(f.source,'openmp',f.cache,{'python':{'soabi':'cpython-313'}})
    second,decision=runner.cached_build(f.source,'openmp',f.cache,{'python':{'soabi':'cpython-314'}})
    assert not decision['reused'] and first['package']!=second['package']
    assert Path(first['package']).exists()


def test_cache_lock_rejects_concurrent_campaigns_and_releases_after_failure(tmp_path):
    with pytest.raises(ValueError):
        with runner.campaign_lock(tmp_path):
            with pytest.raises(RuntimeError, match="Another benchmark"):
                with runner.campaign_lock(tmp_path):
                    pytest.fail("Acquired the same campaign lock twice")
            raise ValueError("interrupted")
    with runner.campaign_lock(tmp_path):
        pass


@pytest.mark.parametrize("failed", [False, True])
def test_campaign_runs_all_shards_and_reports_incomplete_work(tmp_path, monkeypatch, failed):
    args = SimpleNamespace(output=tmp_path / "campaign", cache_dir=tmp_path / "cache",
        baseline_archive=tmp_path / "baseline", candidate_archive=tmp_path / "candidate", comparison="overall",
        backend="openmp", tier="pilot", rebuild=False, city_case=[], iterations=2000, solve_seconds=20.)
    monkeypatch.setattr(runner, "build_context", lambda: {})
    monkeypatch.setattr(runner, "cached_build", lambda *a, **kw: ({"package": str(tmp_path)}, {"reused": True}))
    commands=[]
    monkeypatch.setattr(runner.subprocess, "run", lambda command, **kw: commands.append(command))
    monkeypatch.setattr(runner.benchmark, "check_inputs", lambda folder:
        dict(rows=list(range(12)), shards=2, total_shard_seconds=180))
    shards = []
    def run(request):
        shards.append(request.shard)
        runner.benchmark.write(request.output / "summary.json", dict(elapsed_seconds=1., results=[
            dict(status="failed" if failed and request.shard == 0 else "completed")]))
    def aggregate(request):
        assert len(request.runs) == 2
        runner.benchmark.write(request.output, dict(rows=2))
        print("Final benchmark results")
    monkeypatch.setattr(runner.benchmark, "run", run)
    monkeypatch.setattr(runner.benchmark, "aggregate", aggregate)
    assert runner.campaign(args) == (1 if failed else 0)
    assert shards == [0, 1]
    assert commands[0][commands[0].index('--iterations')+1]=='2000'
    assert commands[0][commands[0].index('--solve-seconds')+1]=='20.0'
    state = json.loads((args.output / "campaign.json").read_text())
    assert state["status"] == ("incomplete" if failed else "completed")
    assert (args.output / "results.txt").read_text().strip() == "Final benchmark results"
    assert (args.output / "results.json").exists()


def test_package_probe_rejects_import_redirection(tmp_path):
    # No package and no isolation shim: an installed/editable dtcc_qes must never
    # be mistaken for a valid cache entry, even if it imports successfully.
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
        runner.verify_package(tmp_path, "openmp")

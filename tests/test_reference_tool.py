import importlib.util
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reference_tool", ROOT / "tools/make_reference.py")
reference_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference_tool)


@pytest.mark.parametrize("field", ["x", "dz_array", "icell", "u"])
def test_cross_platform_tolerance_only_relaxes_velocity(field):
    path = ROOT / "tests/fixtures/reference/flat.npz"
    with np.load(path) as stored:
        arrays = {name: stored[name].copy() for name in reference_tool.COMPARED_ARRAYS}
    if field == "icell":
        arrays[field].flat[0] += 1
        tolerance = 2
    else:
        arrays[field].flat[0] += 1e-5
        tolerance = 2e-5
    problems = reference_tool.compare("flat", arrays, path, 0, tolerance)
    assert bool(problems) is (field != "u")


def test_turbulence_xml_preserves_explicit_layers_and_method(tmp_path):
    spec = reference_tool.TURBULENCE_CASES["building_nonuniform_wall"]
    path = tmp_path / "input.xml"
    reference_tool.write_xml(spec.case, path, turbulence=True, method=spec.method, dz_layers=spec.dz_layers)
    tree = ElementTree.parse(path)
    assert tree.findtext("turbParams/method") == "1"
    assert tree.findtext("simulationParameters/verticalStretching") == "1"
    layers = [float(node.text) for node in tree.findall("simulationParameters/dz_value")]
    assert tuple(layers) == spec.dz_layers
    assert tree.findtext("simulationParameters/cellSize") == "2.0 2.0 0.125"
    reference_tool.write_xml(spec.case, path)
    tree = ElementTree.parse(path)
    assert tree.find("turbParams") is None
    assert tree.findtext("simulationParameters/verticalStretching") == "0"
    assert not tree.findall("simulationParameters/dz_value")


def test_baseline_and_method_selection_exclude_unsafe_upstream_cases():
    upstream = reference_tool.select_turbulence_cases([], "upstream", None)
    assert len(upstream) == 5 and all(not spec.upstream_exclusion for spec in upstream)
    assert len(reference_tool.select_turbulence_cases([], "audited", None)) == 8
    selected = reference_tool.select_turbulence_cases([], "audited", 1)
    assert len(selected) == 3 and all(spec.method == 1 for spec in selected)
    with pytest.raises(ValueError, match="Unsafe or unqualified"):
        reference_tool.select_turbulence_cases(["building_thin_wall"], "upstream", 1)
    with pytest.raises(ValueError, match="different mixing method"):
        reference_tool.select_turbulence_cases(["flat"], "audited", 1)


def test_turbulence_requires_an_explicit_baseline():
    with pytest.raises(SystemExit) as error:
        reference_tool.main(["--turbulence"])
    assert error.value.code == 2


@pytest.fixture
def source_repo(tmp_path, monkeypatch):
    source = tmp_path / "repository"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "core.cpp").write_text("int value = 1;\n")
    subprocess.run(["git", "-C", str(source), "add", "core.cpp"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Reference test",
                    "-c", "user.email=reference@example.invalid", "commit", "-qm", "test source"], check=True)
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(reference_tool, "QES_SUBMODULE", source)
    return source, revision


def test_stamped_export_is_verified_against_git_bytes(source_repo, tmp_path):
    repository, revision = source_repo
    source = reference_tool.export_pristine_qes(revision, tmp_path / "export")
    metadata = reference_tool.verified_source(source, revision)
    assert metadata["modified"] is False and metadata["verified_files"] == 1
    assert len(metadata["source_manifest_sha256"]) == 64
    (source / "core.cpp").write_text("int value = 2;\n")
    with pytest.raises(ValueError, match="was modified"):
        reference_tool.verified_source(source, revision)


def test_clean_revision_rejects_untracked_source(source_repo):
    source, revision = source_repo
    reference_tool.verified_source(source, revision)
    (source / "extra.h").write_text("// untracked\n")
    with pytest.raises(ValueError, match="must be clean at"):
        reference_tool.verified_source(source, revision)


def test_export_file_mode_is_verified(source_repo, tmp_path):
    repository, revision = source_repo
    source = reference_tool.export_pristine_qes(revision, tmp_path / "export")
    (source / "core.cpp").chmod(0o755)
    with pytest.raises(ValueError, match="changed file mode"):
        reference_tool.verified_source(source, revision)


@pytest.mark.parametrize("extraction_fails", [False, True])
def test_export_closes_archive_pipe_and_reaps_process(source_repo, tmp_path, monkeypatch, extraction_fails):
    _, revision = source_repo
    popen, run = subprocess.Popen, reference_tool.run
    archives = []

    def track_archive(command, **kwargs):
        process = popen(command, **kwargs)
        if "archive" in command:
            archives.append(process)
        return process

    def extract(command, **kwargs):
        if extraction_fails and command[0] == "tar":
            raise subprocess.CalledProcessError(1, command)
        return run(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", track_archive)
    monkeypatch.setattr(reference_tool, "run", extract)
    destination = tmp_path / "export"
    if extraction_fails:
        with pytest.raises(subprocess.CalledProcessError):
            reference_tool.export_pristine_qes(revision, destination)
        assert not (destination / ".qes-revision").exists()
    else:
        reference_tool.export_pristine_qes(revision, destination)
        reference_tool.verified_source(destination, revision)
    assert len(archives) == 1
    assert archives[0].stdout.closed
    assert archives[0].poll() is not None


def test_revision_stamp_cannot_override_git_head(source_repo):
    source, revision = source_repo
    (source / ".qes-revision").write_text(revision + "\n")
    subprocess.run(["git", "-C", str(source), "add", ".qes-revision"], check=True)
    subprocess.run(["git", "-C", str(source), "-c", "user.name=Reference test",
                    "-c", "user.email=reference@example.invalid", "commit", "-qm", "different revision"], check=True)
    with pytest.raises(ValueError, match="must be clean at"):
        reference_tool.verified_source(source, revision)


def test_wrong_revision_is_rejected(source_repo):
    source, revision = source_repo
    with pytest.raises(ValueError, match="must be clean at"):
        reference_tool.verified_source(source, "0" * 40)


@pytest.mark.parametrize("tamper", ["binary", "source", "flags"])
def test_existing_executable_requires_matching_attestation(tmp_path, monkeypatch, tamper):
    source = {"revision": "a" * 40, "source_manifest_sha256": "original"}
    build_info = {"toolchain": {}, "build_options": {"ENABLE_OPENMP": "OFF"}}
    monkeypatch.setattr(reference_tool, "verified_source", lambda *_: source.copy())
    monkeypatch.setattr(reference_tool, "turbulence_build_info", lambda *_: build_info.copy())
    binary = tmp_path / "qesWinds"
    binary.write_bytes(b"original")
    reference_tool.attest_build(binary, tmp_path, tmp_path, "a" * 40, existing=False)
    reference_tool.attest_build(binary, tmp_path, tmp_path, "a" * 40, existing=True)
    if tamper == "binary":
        binary.write_bytes(b"changed")
    elif tamper == "source":
        source["source_manifest_sha256"] = "changed"
    else:
        build_info["build_options"]["ENABLE_OPENMP"] = "ON"
    with pytest.raises(ValueError, match="build attestation"):
        reference_tool.attest_build(binary, tmp_path, tmp_path, "a" * 40, existing=True)


def test_turbulence_comparison_remains_exact_with_wind_tolerances(tmp_path):
    with np.load(ROOT / "tests/fixtures/reference/flat.npz") as stored:
        arrays = {name: stored[name].copy() for name in reference_tool.COMPARED_ARRAYS}
    for name in reference_tool.TURBULENCE_ARRAYS:
        arrays[name] = np.zeros((1,), dtype=np.float32)
    path = tmp_path / "fixture.npz"
    np.savez(path, **arrays)
    arrays["stress"][0] = 1e-6
    problems = reference_tool.compare("flat", arrays, path, 1, 1, turbulence=True)
    assert len(problems) == 1 and "stress" in problems[0]


@pytest.mark.parametrize("field", ["case", "schema_version", "case_definition", "stress_components",
                                   "upstream_exclusions", "archive_sha256"])
def test_turbulence_check_rejects_misleading_metadata(field):
    archive = ROOT / "tests/fixtures/reference/turbulence/audited/one_building.npz"
    metadata = json.loads(archive.with_suffix(".json").read_text())
    provenance = metadata.copy()
    spec = reference_tool.TURBULENCE_CASES["one_building"]
    assert reference_tool.compare_turbulence_metadata(metadata, provenance, spec, archive) == []
    if field == "case_definition":
        metadata[field]["case"]["buildings"][0]["height"] += 1
    elif field == "stress_components":
        metadata[field] = list(reversed(metadata[field]))
    else:
        metadata[field] = None
    problems = reference_tool.compare_turbulence_metadata(metadata, provenance, spec, archive)
    assert len(problems) == 1 and field in problems[0]

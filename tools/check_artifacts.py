"""Verify the licenses and corresponding build sources in release artifacts."""

import argparse
import gzip
import hashlib
import io
import json
from email.parser import BytesParser
from pathlib import Path
import tarfile
import zipfile


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_metadata(data):
    metadata = BytesParser().parsebytes(data)
    require(metadata.get("License-Expression") == "GPL-3.0-only", "Missing GPL-3.0-only metadata")
    requirements = metadata.get_all("Requires-Dist", [])
    require(any(item.startswith("dtcc-core") for item in requirements), "Missing DTCC runtime dependency")
    require(any(item.startswith("numpy") for item in requirements), "Missing NumPy runtime dependency")
    require(not any(item.startswith("nanobind") for item in requirements), "nanobind must be build-only")


def check_wheel(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        check_metadata(archive.read(metadata))
        prefix = metadata.rsplit("/", 1)[0] + "/licenses/"
        for name in ("LICENSE", "NOTICE", "src/qes_core/LICENSE"):
            require(prefix + name in names, f"Wheel omits {name}")
        require(b"GNU GENERAL PUBLIC LICENSE" in archive.read(prefix + "LICENSE"), "Wrong root license")
        require(b"QES-Winds" in archive.read(prefix + "NOTICE"), "Missing QES attribution")
        require(any(name.startswith("dtcc_qes/_qes.") and name.endswith((".so", ".pyd")) for name in names),
                "Wheel omits native extension")
        for name in ("wind.py", "result.py", "_city.py", "vertical_grid.py", "_auto_grid.py",
                     "_turbulence_domain.py", "turbulence.py", "comfort.py", "datasets.py",
                     "_dataset_city.py", "solver_control.py", "profiles.py", "_qes_revision.txt"):
            require("dtcc_qes/" + name in names, f"Wheel omits {name}")
        require(len(archive.read("dtcc_qes/_qes_revision.txt").strip()) == 40, "Missing source revision")


def check_sdist(path):
    with tarfile.open(path) as archive:
        members = {name.split("/", 1)[1]: name for name in archive.getnames() if "/" in name}
        for name in (
            "LICENSE", "NOTICE", "README.md", "pyproject.toml", "uv.lock", "CMakeLists.txt",
            "src/qes_core/LICENSE", "src/qes_core/PROVENANCE.md", "src/qes_core/CMakeLists.txt",
            "docs/solver-control-contract.md", "docs/solver-control-s0.md", "docs/solver-control-s1.md",
            "docs/solver-control-s1a.md", "tests/test_condition_state.py",
            "tools/profile_solver_baseline.py", "tools/solver_profile_hooks.h",
            "tests/test_solver_baseline_profile.py", "docs/data/solver-control-s0/manifest.json",
            "src/qes_core/solver/solver.h", "src/qes_core/solver/solver.cpp",
            "src/qes_core/solver/cpu_float32.cpp", "src/qes_core/solver/cpu_float64.cpp",
            "src/qes_core/solver/mass_diagnostics.h", "tests/native/check_solver_phases.cpp",
            "src/qes_core/qes/Domain.cpp",
            "src/qes_core/winds/WindModelInputs.h", "src/qes_core/winds/LogProfile.cpp",
            "src/qes_core/winds/LayerProfile.cpp", "src/qes_core/winds/LayerProfile.h",
            "src/qes_core/dtcc/api/profile_types.h", "src/dtcc_qes/profiles.py",
            "WIND_PROFILES.md", "docs/wind-profiles.md", "tests/test_profiles.py",
            "tests/native/check_profiles.cpp", "tools/verify_wind_profiles.py", "examples/wind_profiles.py",
            "tools/check_wind_profile_policy.py", "docs/wind-profiles-verification.md",
            "src/cpp/bindings.cpp", "src/qes_core/dtcc/wind_runner.cpp", "src/qes_core/dtcc/model_inputs.cpp",
            "src/dtcc_qes/datasets.py", "src/dtcc_qes/_dataset_city.py", "tests/test_datasets.py",
            "tests/test_dataset_vertical_grid.py", "examples/city_dataset.py",
            "src/qes_core/dtcc/divergence.cpp", "src/qes_core/dtcc/divergence.h",
            "src/qes_core/dtcc/api/stress_validity.h", "tests/native/check_turbulence.cpp",
            "src/qes_core/dtcc/turbulence.h", "src/qes_core/dtcc/turbulence.cpp",
            "tools/check_stress_validity.py",
            "docs/turbulence-reference-differences.md",
            "tests/test_turbulence_reference.py", "tests/fixtures/turbulence_cases.py",
            "src/dtcc_qes/_turbulence_domain.py", "tests/test_turbulence_domain.py",
            "src/dtcc_qes/turbulence.py", "tests/test_turbulence.py",
            "tools/check_turbulence_domain.py", "docs/data/turbulence-domain/control.json",
            "tools/run_turbulence_benchmark.py", "tests/test_turbulence_benchmark.py",
            "docs/turbulence-benchmark.md", "docs/data/turbulence-benchmark/benchmark.json",
            "docs/data/turbulence-benchmark/benchmark-runs.json.gz",
            "docs/data/turbulence-benchmark/verification.json",
            "tests/native/check_precision.cpp",
            "tests/test_precision.py", "tests/test_precision_verification.py", "tools/run_precision_verification.py",
            "tools/audit_precision_verification.py", "tools/plot_precision_verification.py",
            "docs/data/precision-remedy/audit.json", "docs/data/precision-remedy/verification.png",
            "docs/precision-and-horizontal-verification.md",
            "tools/run_joint_grid_verification.py", "tools/audit_joint_grid_verification.py",
            "tools/precompute_joint_checkpoints.py",
            "tools/plot_joint_grid_verification.py", "tests/test_joint_grid_verification.py",
            "docs/joint-grid-verification.md", "docs/data/joint-grid-verification/audit.json",
            "docs/data/joint-grid-verification/execution-environment.json",
            "docs/data/joint-grid-verification/verification.png", "docs/data/joint-grid-verification/figure.json",
            "docs/data/joint-grid-verification/baseline-sources/tools/vertical_grid_study.cpp",
            "docs/data/joint-grid-verification/serial/manifest.json",
            "docs/data/joint-grid-verification/serial/raw.json.gz",
            "docs/data/joint-grid-verification/serial/summary.json",
            "docs/data/joint-grid-verification/openmp/manifest.json",
            "docs/data/joint-grid-verification/openmp/raw.json.gz",
            "docs/data/joint-grid-verification/openmp/summary.json",
            "docs/data/precision-remedy/serial/raw.json.gz", "docs/data/precision-remedy/serial/summary.json",
            "docs/data/precision-remedy/openmp/raw.json.gz", "docs/data/precision-remedy/openmp/summary.json",
            "docs/data/lateral-horizontal-verification/serial/raw.json.gz",
            "docs/data/lateral-horizontal-verification/serial/summary.json",
            "docs/data/lateral-horizontal-verification/openmp/raw.json.gz",
            "docs/data/lateral-horizontal-verification/openmp/summary.json",
            "src/dtcc_qes/vertical_grid.py", "tests/test_vertical_grid.py", "tests/native/check_vertical_grid.cpp",
            "src/dtcc_qes/wind.py", "src/dtcc_qes/_qes_revision.txt", "tests/fixtures/reference/flat.npz",
            "tests/fixtures/reference/one_building.npz", "tests/native/check_physics.cpp",
            "tests/native/check_openmp.cpp", "demo/simple_wind_demo.py", "demo/medium_city.py",
            "tools/check_native_symbols.py", "tools/make_reference.py", "tools/check_artifacts.py",
            "examples/single_building.py", "docs/validation.md", "docs/upstream-license-report.md",
            "docs/milestone1-audit.md", "docs/stagea-validation.md",
            "docs/stageb1-validation.md", "tests/test_sampling.py", "tests/test_grid_preview.py",
            "examples/vertical_grid.py",
            "src/dtcc_qes/_auto_grid.py", "tests/test_auto_grid.py",
            "examples/automatic_vertical_grid.py", "docs/stagec1-validation.md",
            "tools/run_auto_grid_controls.py", "tests/test_auto_grid_controls.py",
            "tools/plot_auto_grid_controls.py", "docs/data/auto-grid-controls/horizontal-sensitivity.png",
            "docs/stagec2-controls.md",
            "docs/data/auto-grid-controls/serial/raw.json.gz",
            "docs/data/auto-grid-controls/serial/summary.json",
            "docs/data/auto-grid-controls/openmp/raw.json.gz",
            "docs/data/auto-grid-controls/openmp/summary.json",
            "tools/run_horizontal_sensitivity.py", "tests/test_horizontal_sensitivity.py",
            "tools/continue_horizontal_sensitivity.py",
            "tools/plot_horizontal_sensitivity.py", "docs/data/horizontal-sensitivity/initialization.png",
            "docs/stagec2b-horizontal-sensitivity.md",
            "docs/data/horizontal-sensitivity/serial/raw.json.gz",
            "docs/data/horizontal-sensitivity/serial/summary.json",
            "docs/data/horizontal-sensitivity/openmp/raw.json.gz",
            "docs/data/horizontal-sensitivity/openmp/summary.json",
            "DYNAMIC_VERTICAL_GRID.md", "SOLVER_CONTROL_REFACTOR.md", "docs/vertical-grid-gate.md",
            "tools/run_practical_vertical_grid.py", "tests/test_practical_vertical_grid.py",
            "tests/test_practical_vertical_grid_audit.py",
            "docs/data/practical-vertical-grid/protocol.json",
            "docs/data/practical-vertical-grid/references.json.gz",
            "docs/data/practical-vertical-grid/executions.json",
            "docs/data/practical-vertical-grid/summary.json", "docs/data/practical-vertical-grid/audit.json",
            "docs/data/practical-vertical-grid/cases/generated-2000.json.gz",
            "docs/data/practical-vertical-grid/cases/uniform-2000.json.gz",
            "docs/data/vertical-grid-gate/raw.json.gz", "docs/data/vertical-grid-gate/summary.json",
            "tools/vertical_grid_study.cpp", "tools/run_vertical_grid_study.py",
            "tools/vertical_grid_diagnostics.cpp", "tools/vertical_grid_diagnostics.h",
            "tools/run_vertical_grid_diagnosis.py", "docs/vertical-grid-diagnosis.md",
            "docs/data/vertical-grid-diagnosis/raw.json.gz",
            "docs/data/vertical-grid-diagnosis/summary.json",
            "tests/test_vertical_grid_study.py",
            "src/dtcc_qes/comfort.py", "tests/test_comfort.py", "examples/wind_comfort.py",
            "docs/wind-comfort.md",
            "docs/near-wall-validation.md", "tools/near_wall_probe.cpp",
            "tools/build_near_wall_probe.py", "tools/near_wall_sampling.py",
            "tools/run_near_wall_validation.py", "tools/audit_near_wall_validation.py",
            "tools/diagnose_sidewall_transition.py", "tools/plot_near_wall_validation.py",
            "tests/test_near_wall_validation.py", "tests/test_near_wall_audit.py",
            "docs/data/near-wall-validation/manifest.json",
            "docs/data/near-wall-validation/protocol.md",
            "docs/data/near-wall-validation/summary.json",
            "docs/data/near-wall-validation/audit.json",
            "docs/data/near-wall-validation/instrumented-check.json",
            "docs/data/near-wall-validation/sidewall-transition.json",
            "docs/data/near-wall-validation/sidewall-transition.png",
            "docs/data/near-wall-validation/point-comparison.png",
            "docs/data/near-wall-validation/figures.json",
            "docs/generated-grid-pilot.md", "tools/run_generated_grid_pilot.py",
            "tools/audit_generated_grid_pilot.py", "tools/plot_generated_grid_pilot.py",
            "tests/test_generated_grid_pilot.py", "tests/test_generated_grid_audit.py",
            "docs/data/generated-grid-pilot/manifest.json",
            "docs/data/generated-grid-pilot/protocol.md",
            "docs/data/generated-grid-pilot/raw.json.gz",
            "docs/data/generated-grid-pilot/summary.json",
            "docs/data/generated-grid-pilot/audit.json",
            "docs/data/generated-grid-pilot/execution-environment.json",
            "docs/vertical-refinement.md", "tools/run_vertical_refinement.py",
            "tools/audit_vertical_refinement.py", "tools/plot_vertical_refinement.py",
            "tools/diagnose_vertical_initialization.py",
            "tests/test_vertical_refinement.py", "tests/test_vertical_refinement_audit.py",
            "docs/data/vertical-refinement/manifest.json",
            "docs/data/vertical-refinement/protocol.md",
            "docs/data/vertical-refinement/raw.json.gz",
            "docs/data/vertical-refinement/summary.json",
            "docs/data/vertical-refinement/audit.json",
            "docs/data/vertical-refinement/execution-environment.json",
            "docs/data/vertical-refinement/initialization.json",
            "docs/finest-reference.md", "tools/run_finest_reference.py",
            "tools/audit_finest_reference.py",
            "tests/test_finest_reference.py", "tests/test_finest_reference_audit.py",
            "docs/data/finest-reference/manifest.json",
            "docs/data/finest-reference/protocol.md",
            "docs/data/finest-reference/input.txt",
            "docs/data/finest-reference/summary.json",
            "docs/data/finest-reference/audit.json",
            "tools/benchmark_grid_planning.py",
            "docs/data/finest-reference/planning-timings.json",
            "docs/data/finest-reference/interruption.json",
            "docs/data/finest-reference/retry-supervision.json",
            "docs/data/finest-reference/costs.json",
            "docs/data/finest-reference/status.json",
            "docs/data/finest-reference/runtime-review-stop.json",
            "docs/data/finest-reference/runtime-review.json",
            "tools/benchmark_fast_wind.py",
            "docs/data/finest-reference/runtime-cases/float32.json",
            "docs/data/finest-reference/runtime-cases/float32.log",
            "docs/data/finest-reference/runtime-cases/float64.json",
            "docs/data/finest-reference/runtime-cases/float64.log",
        ):
            require(name in members, f"Source distribution omits {name}")
        shared = ("flat", "flat_oblique", "one_building", "building_oblique", "building_wall")
        for baseline, cases in {
            "upstream": shared,
            "audited": (*shared, "building_thin_wall", "building_nonuniform", "building_nonuniform_wall"),
        }.items():
            for case in cases:
                for suffix in ("npz", "json"):
                    name = f"tests/fixtures/reference/turbulence/{baseline}/{case}.{suffix}"
                    require(name in members, f"Source distribution omits {name}")
        control = json.loads(archive.extractfile(members["docs/data/turbulence-domain/control.json"]).read())
        require(control["passed"], "Turbulence domain control did not pass")
        # Evidence is checked against the source snapshots archived with it,
        # so later refactors of the live sources do not invalidate it.
        for name, expected in control["source_sha256"].items():
            snapshot = "docs/data/turbulence-domain/sources/" + name
            require(snapshot in members, f"Source distribution omits {snapshot}")
            actual = hashlib.sha256(archive.extractfile(members[snapshot]).read()).hexdigest()
            require(actual == expected, f"Turbulence domain control snapshot differs for {name}")
        benchmark = json.loads(archive.extractfile(members["docs/data/turbulence-benchmark/benchmark.json"]).read())
        require(benchmark["benchmark_passed"], "Turbulence benchmark did not pass")
        for name, expected in benchmark["source_sha256"].items():
            snapshot = "docs/data/turbulence-benchmark/sources/" + name
            require(snapshot in members, f"Source distribution omits {snapshot}")
            actual = hashlib.sha256(archive.extractfile(members[snapshot]).read()).hexdigest()
            require(actual == expected, f"Turbulence benchmark snapshot differs for {name}")
        raw = "docs/data/turbulence-benchmark/" + benchmark["raw_runs"]["file"]
        require(hashlib.sha256(archive.extractfile(members[raw]).read()).hexdigest() ==
                benchmark["raw_runs"]["sha256"], "Turbulence benchmark raw evidence checksum differs")
        verification = json.loads(archive.extractfile(members["docs/data/turbulence-benchmark/verification.json"]).read())
        require(verification["passed"], "Turbulence verification did not pass")
        revision = archive.extractfile(members["src/dtcc_qes/_qes_revision.txt"]).read().decode().strip()
        require(verification["qes_revision"] == benchmark["environment"]["qes_revision"] == revision,
                "Turbulence evidence has a different QES revision")
        study = "docs/data/near-wall-validation/"
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        evidence = list(manifest["references_sha256"])
        evidence.extend(study + "sources/" + name for name in manifest["source_sha256"])
        evidence.extend(study + "cases/" + task["id"] + ".json.gz" for task in manifest["tasks"])
        for name in evidence:
            require(name in members, f"Source distribution omits study evidence {name}")
        study = "docs/data/generated-grid-pilot/"
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        summary = json.load(archive.extractfile(members[study + "summary.json"]))
        audit = json.load(archive.extractfile(members[study + "audit.json"]))
        evidence = list(manifest["references_sha256"])
        evidence.extend(study + "sources/" + name for name in manifest["source_sha256"])
        if summary["complete"]:
            evidence.extend(study + name for name in ("pilot.png", "figure.json"))
        for backend in audit["backends"].values():
            evidence.extend(c["path"] for c in backend["checkpoints"])
        for backend in manifest["binaries"]:
            for task in manifest["tasks"]:
                name = study + backend + "/cases/" + task["id"] + ".json.gz"
                if not summary["complete"] and name not in members:
                    continue
                require(name in members, f"Source distribution omits pilot case {name}")
                record = json.loads(gzip.decompress(archive.extractfile(members[name]).read()))
                for run in [record["run"], *record["attempts"]]:
                    if run is None and not summary["complete"]:
                        continue
                    require(run is not None, "Complete pilot contains an unfinished case")
                    evidence.extend(origin["path"] for origin in run["checkpoint_origins"])
        for name in evidence:
            require(name in members, f"Source distribution omits pilot evidence {name}")
        study = "docs/data/vertical-refinement/"
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        summary = json.load(archive.extractfile(members[study + "summary.json"]))
        audit = json.load(archive.extractfile(members[study + "audit.json"]))
        evidence = list(manifest["references_sha256"])
        evidence.extend(study + "sources/" + name for name in manifest["source_sha256"])
        if summary["complete"]:
            evidence.extend(study + name for name in ("refinement.png", "figure.json"))
        for backend in audit["backends"].values():
            evidence.extend(study + c["path"] for c in backend["checkpoints"])
        for backend, tasks in manifest["task_matrix"].items():
            for task in tasks:
                name = study + backend + "/cases/" + task["id"] + ".json.gz"
                if not summary["complete"] and name not in members:
                    continue
                require(name in members, f"Source distribution omits refinement case {name}")
                record = json.loads(gzip.decompress(archive.extractfile(members[name]).read()))
                for run in [record["run"], *record["attempts"]]:
                    if run is None and not summary["complete"]:
                        continue
                    require(run is not None, "Complete refinement study contains unfinished case")
                    evidence.extend(origin["path"] for origin in run["checkpoint_origins"])
        for name in evidence:
            require(name in members, f"Source distribution omits refinement evidence {name}")
        diagnosis = json.load(archive.extractfile(members[study + "initialization.json"]))
        for name in diagnosis["source_sha256"]:
            required = study + "initialization-sources/" + name
            require(required in members, f"Source distribution omits initialization source {required}")
        for name in diagnosis["input_sha256"]:
            require(name in members, f"Source distribution omits initialization evidence {name}")
        study = "docs/data/finest-reference/"
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        status = json.load(archive.extractfile(members[study + "status.json"]))
        require(status["state"] == "stopped_for_runtime_review" and not status["complete"]
                and not status["reference_usable"], "Stopped study must not qualify a reference")
        evidence = list(manifest["references_sha256"])
        evidence.extend(study + "sources/" + name for name in manifest["source_sha256"])
        for name in evidence:
            require(name in members, f"Source distribution omits finest-reference evidence {name}")
        study = "docs/data/solver-control-s0/"
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        summary = json.load(archive.extractfile(members[study + "summary.json"]))
        require(summary["completed"] and summary["parity_passed"], "Incomplete solver-control baseline profile")
        for name, sha in manifest["files"].items():
            require(study + name in members, f"Source distribution omits solver-control baseline {name}")
            require(hashlib.sha256(archive.extractfile(members[study + name]).read()).hexdigest() == sha,
                    f"Solver-control baseline evidence changed: {name}")
        study = "docs/data/solver-control-s1/"
        require(study + "manifest.json" in members, "Source distribution omits S1 manifest")
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        for name, sha in manifest["files"].items():
            require(study + name in members, f"Source distribution omits S1 evidence {name}")
            require(hashlib.sha256(archive.extractfile(members[study + name]).read()).hexdigest() == sha,
                    f"S1 evidence changed: {name}")
        with tarfile.open(fileobj=io.BytesIO(archive.extractfile(members[study + "sources.tar.gz"]).read())) as snapshot:
            for name, sha in manifest["sources"].items():
                require(hashlib.sha256(snapshot.extractfile(name).read()).hexdigest() == sha,
                        f"S1 source snapshot changed: {name}")
        parity = json.loads(gzip.decompress(archive.extractfile(members[study + "parity.json.gz"]).read()))
        strict = [r for r in parity["comparisons"] if r["kind"] in ("revision", "team")]
        require(len(strict) == 8 and all(not r["differences"] for r in strict), "S1 bitwise comparison failed")
        require(all(r["cases"] == 429 for r in strict if r["kind"] == "revision"), "S1 comparison matrix incomplete")
        study = "docs/data/solver-control-s1a/"
        require(study + "manifest.json" in members, "Source distribution omits S1a manifest")
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        for name, sha in manifest["files"].items():
            require(study + name in members, f"Source distribution omits S1a evidence {name}")
            require(hashlib.sha256(archive.extractfile(members[study + name]).read()).hexdigest() == sha,
                    f"S1a evidence changed: {name}")
        with tarfile.open(fileobj=io.BytesIO(archive.extractfile(members[study + "sources.tar.gz"]).read())) as snapshot:
            for name, sha in manifest["sources"].items():
                require(hashlib.sha256(snapshot.extractfile(name).read()).hexdigest() == sha,
                        f"S1a source snapshot changed: {name}")
        changes = json.loads(gzip.decompress(archive.extractfile(members[study + "changes-from-s1.json.gz"]).read()))
        for record in changes["comparisons"]:
            if record["kind"] == "revision":
                require(record["differences"] == manifest["expected_changed_records"][record["backend"]],
                        "S1a changed records differ from the reviewed condition-state correction")
            elif record["kind"] == "team":
                require(not record["differences"], "S1a differs between OpenMP teams")
        parity = json.loads(gzip.decompress(archive.extractfile(members[study + "baseline-parity.json.gz"]).read()))
        strict = [r for r in parity["comparisons"] if r["kind"] in ("revision", "team")]
        require(parity["passed"] and len(strict) == 8 and all(not r["differences"] for r in strict),
                "Corrected S1a baseline comparison failed")
        require(parity["baseline_revision"] == "sha256:" + manifest["files"]["sources.tar.gz"],
                "S1a comparison used a different corrected source snapshot")
        require(all(r["cases"] == 429 for r in strict if r["kind"] == "revision"), "S1a comparison matrix incomplete")
        study = "docs/data/solver-control-s2/"
        for name in ("docs/solver-control-s2.md", "tools/profile_solver_s2.py", "tools/check_solver_study_parity.py",
                     "tests/test_solver_s2_profile.py", study + "manifest.json"):
            require(name in members, f"Source distribution omits S2 source/evidence {name}")
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        require(manifest["baseline_source_id"] == "sha256:6fcdfab1abe30e254721495d2fe453f9e4c7eb89be89421df29eb44663e08d76",
                "S2 used a different corrected baseline")
        for name, sha in manifest["files"].items():
            require(study + name in members, f"Source distribution omits S2 evidence {name}")
            require(hashlib.sha256(archive.extractfile(members[study + name]).read()).hexdigest() == sha,
                    f"S2 evidence changed: {name}")
        for name, index in manifest["sources"].items():
            with tarfile.open(fileobj=io.BytesIO(archive.extractfile(members[study + name]).read())) as snapshot:
                for path, sha in index["files"].items():
                    require(hashlib.sha256(snapshot.extractfile(path).read()).hexdigest() == sha,
                            f"S2 source snapshot changed: {name}/{path}")
        for stage in ("baseline-corrected", "norm", "operator", "allocation", "ordering"):
            summary = json.load(archive.extractfile(members[study + stage + "/summary.json"]))
            require(summary["completed"] and summary["parity_passed"], f"S2 profile incomplete: {stage}")
        for stage in ("norm", "operator", "allocation"):
            parity = json.loads(gzip.decompress(archive.extractfile(members[study + stage + "-parity.json.gz"]).read()))
            strict = [r for r in parity["comparisons"] if r["kind"] in ("revision", "team")]
            require(parity["passed"] and len(strict) == 8 and all(not r["differences"] for r in strict),
                    f"S2 strict numerical gate failed: {stage}")
        parity = json.loads(gzip.decompress(archive.extractfile(members[study + "ordering-parity.json.gz"]).read()))
        migration = [r for r in parity["comparisons"] if r["kind"] == "ordering_migration"]
        require(parity["passed"] and parity["ordering_migration"] and len(migration) == 4
                and all(r["passed"] and r["exact_serial_change_set"] for r in migration),
                "S2 serial ordering migration failed")
        for stage in ("norm", "ordering"):
            parity = json.loads(gzip.decompress(archive.extractfile(members[study + stage + "-study-parity.json.gz"]).read()))
            require(parity["passed"] and all(r["passed"] for r in parity["comparisons"]),
                    f"S2 study/lexicographic gate failed: {stage}")
        study = "docs/data/solver-control-s3/"
        for name in ("docs/solver-control-s3.md", "src/qes_core/dtcc/api/monitor_types.h",
                     "src/qes_core/dtcc/monitor.h", "src/qes_core/dtcc/monitor.cpp",
                     "tests/native/check_monitor.cpp", "tests/test_monitor.py",
                     "tools/solver_monitor_probe.cpp", "tools/profile_solver_monitor.py", study + "manifest.json"):
            require(name in members, f"Source distribution omits S3 source/evidence {name}")
        manifest = json.load(archive.extractfile(members[study + "manifest.json"]))
        require(manifest["baseline_source_id"] == "sha256:931408afbf86a578b978f17dc15b8bb9f8fdccc9522ebe86da8c6c499f13d803",
                "S3 used a different S2 baseline")
        for name, sha in manifest["files"].items():
            require(study + name in members, f"Source distribution omits S3 evidence {name}")
            require(hashlib.sha256(archive.extractfile(members[study + name]).read()).hexdigest() == sha,
                    f"S3 evidence changed: {name}")
        with tarfile.open(fileobj=io.BytesIO(archive.extractfile(members[study + "sources.tar.gz"]).read())) as snapshot:
            for name, sha in manifest["sources"].items():
                require(hashlib.sha256(snapshot.extractfile(name).read()).hexdigest() == sha,
                        f"S3 source snapshot changed: {name}")
        parity = json.loads(gzip.decompress(archive.extractfile(members[study + "parity.json.gz"]).read()))
        require(parity["passed"] and not parity["ordering_migration"]
                and parity["baseline_revision"] == manifest["baseline_source_id"]
                and parity["candidate"] == manifest["source_id"], "S3 strict baseline/candidate identity failed")
        require(len(parity["comparisons"]) == 12 and all(not r["differences"] for r in parity["comparisons"]),
                "S3 revision/team/backend comparison failed")
        require(all(r["cases"] == 429 for r in parity["comparisons"] if r["kind"] == "revision"),
                "S3 comparison matrix incomplete")
        summary = json.load(archive.extractfile(members[study + "profile/summary.json"]))
        require(summary["completed"] and summary["parity_passed"], "S3 bounded overhead matrix incomplete")
        for name in ("src/qes_core/dtcc/api/control_types.h", "src/qes_core/dtcc/api/diagnostic_types.h",
                     "src/qes_core/dtcc/solver_control.h", "src/qes_core/dtcc/solver_control.cpp",
                     "src/cpp/control_bindings.h", "src/dtcc_qes/solver_control.py", "tests/test_solver_control.py",
                     "tests/native/check_solver_control.cpp", "tools/benchmark_urban_wind.py", "tools/urban_wind_cases.py",
                     "docs/urban-wind-benchmarks.md", "docs/solver-control-s4.md"):
            require(name in members, f"Source distribution omits S4 source/documentation {name}")
        for name in (
            "SOLVER_CONTROL_REFACTOR.md", "docs/solver-control-s5.md", "docs/solver-control-s6.md",
            "docs/solver-control-s7.md", "docs/solver-control-s8a.md", "docs/solver-control-s9.md",
            "src/qes_core/dtcc/api/policy_types.h", "src/qes_core/dtcc/pedestrian_policy.h",
            "src/qes_core/dtcc/pedestrian_policy.cpp", "src/qes_core/dtcc/pedestrian_qualification.h",
            "tests/native/check_equation_residual.cpp", "tests/native/check_pedestrian_policy.cpp",
            "tests/test_adaptive_control.py", "tests/test_solver_policy_audit.py",
            "tests/test_urban_campaign.py", "tests/test_prepared_wind_study.py", "tests/test_solver_release.py",
            "tools/run_urban_benchmarks.py", "tools/reproduce_solver_policy.py", "tools/audit_solver_policy.py",
            "tools/benchmark_prepared_wind.py", "tools/reproduce_prepared_wind.py", "tools/audit_prepared_wind.py",
            "tools/validate_solver_release.py", "tools/audit_solver_release.py", "tools/wheel_runtime_smoke.py",
            "tools/publish_solver_release.py",
            "docs/data/solver-control-s9/scope.json",
        ):
            require(name in members, f"Source distribution omits final solver-control source/documentation {name}")
        for stage in ('s5', 's6', 's7', 's8a'):
            require(f'docs/data/solver-control-{stage}/manifest.json' in members, f"Source distribution omits {stage} evidence")
        require(not any(name.startswith((".idea/", "build/", ".venv/", ".pytest_cache/")) for name in members),
                "Private build/environment/cache files in sdist")
        require(not any(name.startswith("QES-Public/") for name in members),
                "Reference-only QES-Public submodule in sdist")
        require(not any("__pycache__" in name.split("/") or name.endswith(".pyc") for name in members),
                "Python bytecode caches in sdist")
        check_metadata(archive.extractfile(members["PKG-INFO"]).read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Artifact paths or directories")
    args = parser.parse_args()
    artifacts = []
    for path in args.paths:
        artifacts.extend(sorted(path.glob("*.whl")) + sorted(path.glob("*.tar.gz")) if path.is_dir() else [path])
    require(bool(artifacts), "No artifacts found")
    for path in artifacts:
        (check_wheel if path.suffix == ".whl" else check_sdist)(path)
        print(f"Artifact check passed: {path.name}")


if __name__ == "__main__":
    main()

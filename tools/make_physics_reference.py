"""Embedded regression snapshots; these are not independent standalone oracles.

Invoked by make_reference.py --embedded-physics [--check]. Independent physics
checks live in check_ground_gradient, check_spectral_cap and check_symmetry.
"""
from dataclasses import asdict
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))


def generate(names, output=None, reference_dir=None, check=False):
    from dtcc_qes import _qes
    from fixtures.turbulence_cases import CASES
    from fixtures.turbulence_reference import physics_directory
    from runner_cases import inputs

    directory = Path((reference_dir if check else output) or physics_directory())
    if not check:
        directory.mkdir(parents=True, exist_ok=True)
    source_paths = [ROOT / "CMakeLists.txt"]
    for folder in ("src/qes_core", "src/cpp"):
        source_paths.extend(p for p in (ROOT / folder).rglob("*")
                            if p.is_file() and (p.suffix in (".h", ".cpp") or p.name == "CMakeLists.txt"))
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(source_paths)}
    for name in names or CASES:
        spec = CASES[name]
        grid, model, condition, solver, arrays = inputs(spec.case)
        settings = _qes.TurbulenceSettings()
        settings.enabled = True
        settings.mixing_length_method = spec.method
        runner = _qes.WindRunner()
        layers = np.asarray(spec.dz_layers, dtype=np.float64) if spec.dz_layers else None
        runner.prepare(grid, model, **arrays, turbulence=settings, dz_layers=layers)
        result = runner.solve(condition, solver)
        assert result["diagnostics"]["converged"], name
        fields = result["turbulence"]
        computed = fields["state"] > 0
        archive = {key: result[key] for key in ("x", "y", "z")}
        archive.update({key: result["velocity"][..., i] for i, key in enumerate(("u", "v", "w"))})
        archive.update(icell=result["cell_flags"], computed=computed.astype(np.uint8),
                       state=fields["state"])
        for key in ("stress", "tke", "co_eps", "mixing_length"):
            archive[key] = fields[key].copy()
            archive[key][~computed] = 0
        path = directory / f"{name}.npz"
        if check:
            with np.load(path) as reference:
                assert set(reference.files) == set(archive)
                for key, value in archive.items():
                    np.testing.assert_array_equal(value, reference[key], err_msg=f"{name}/{key}")
            metadata = json.loads(path.with_suffix(".json").read_text())
            assert metadata["archive_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
            assert metadata["native_identity"] == _qes.solver_policy_revision
            assert metadata["sources"] == sources
        else:
            np.savez_compressed(path, **archive)
            metadata = dict(schema_version=2, baseline="audited-physics", generator="embedded WindRunner",
                            case_definition=asdict(spec), grid_relaxation=False,
                            stop_rule="multiplier_change",
                            native_identity=_qes.solver_policy_revision,
                            solver_policy_build_supported=_qes.solver_policy_build_supported,
                            qes_origin_revision=_qes.qes_revision,
                            revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                            sources=sources, executable_sha256=hashlib.sha256(Path(_qes.__file__).read_bytes()).hexdigest(),
                            archive_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            toolchain={key: getattr(_qes, key) for key in
                                       ("compiler_id", "compiler_version", "build_type", "cpu_sweep_order", "openmp_enabled")},
                            solver_summary={key: result["diagnostics"][key] for key in ("converged", "iterations")})
            metadata["toolchain"].update(machine=platform.machine(), platform=platform.platform())
            path.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(f"{'checked' if check else 'wrote'} {path}")
    return 0

"""Six private lifecycle attempts, with optional immutable archived-field checks.

Requires a hook-enabled isolated package. Does not open any physical campaign.
"""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import resource
import sys
import threading
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "validation"), str(ROOT / "tests")]
from aij.canyon import CanyonSession, mass_gate, native_mass
from aij.evidence import file_hash, write_json
from aij.sampling import probe_sample
from fixtures.canyon import fixture

SEQUENCE = (("legacy-aligned", "legacy", False),
            ("reference-aligned", "horizontal_reference_v1", False),
            ("joined-aligned", "joined_v1", False),
            ("joined-oblique", "joined_v1", True),
            ("expected-failure", "joined_v1", None),
            ("legacy-reused", "legacy", False))


def bits(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes()


def identity():
    from dtcc_qes import _qes
    paths = [*sorted((ROOT / "src").rglob("*.cpp")), *sorted((ROOT / "src").rglob("*.h")),
             *sorted((ROOT / "src/dtcc_qes").glob("*.py")),
             *sorted((ROOT / "validation/aij").glob("*.py")),
             ROOT / "tests/fixtures/canyon.py", ROOT / "CMakeLists.txt", Path(__file__).resolve()]
    return dict(native_sha256=file_hash(_qes.__file__), policy=_qes.solver_policy_revision,
                sources={str(p.relative_to(ROOT)):file_hash(p) for p in paths})


def require_identity(frozen):
    if identity() != frozen: raise ValueError("Changed canyon qualification epoch")


def run(output, archive):
    from dtcc_qes import _qes, wind
    if not hasattr(_qes.WindRunner(), "_test_canyon_failure"):
        raise ValueError("Qualification requires the validation-only failure hook")
    output.mkdir(parents=True, exist_ok=False)
    frozen = identity()
    write_json(output / "manifest.json", dict(identity=frozen, attempts=6,
        deadline_per_attempt_seconds=60, memory_cap=None, archive=str(archive) if archive else None))
    session = CanyonSession()
    attempts, checks, packets, records = [], {}, {}, {}
    try:
        for name, model, oblique in SEQUENCE:
            require_identity(frozen)
            attempts.append(dict(name=name, status="started"))
            write_json(output / "attempts.json", attempts)
            folder = output / name; folder.mkdir()
            timer = threading.Timer(60., lambda: os._exit(124)); timer.daemon = True
            timer.start(); started = perf_counter()
            try:
                if oblique is None:
                    condition = wind._native_condition(session.prepared.domain["profile"])
                    options = wind._native_solver(fixture()["run"]["solver"])
                    try: session.runner._test_canyon_failure(condition, options)
                    except RuntimeError as error:
                        checks[name] = str(error) == "canyon validation: deliberate failure after state attachment"
                        write_json(folder / "expected-exception.json", dict(message=str(error), expected=checks[name]))
                    else: checks[name] = False
                else:
                    args = fixture(oblique=oblique)
                    result, stages = session.run(args, model=model, trace=True)
                    e = result.metadata["experiment"]; probes = probe_sample(result, args["probes"].xyz)
                    packet = dict(velocity=result.velocity, cell_flags=result.cell_flags, xyz=args["probes"].xyz,
                        initial_W=e["canyon_initial_w"], probe_velocity=probes["velocity"],
                        probe_method=probes["method"].astype("U20"), stage_velocity=stages["velocity"],
                        stage_method=stages["method"].astype("U20"))
                    np.savez(folder / "fields.npz", **packet)
                    record = dict(model=model, diagnostics=asdict(result.diagnostics),
                        counters={k:v for k,v in e.items() if k.startswith("canyon_") and k not in ("canyon_initial_w","canyon_roof_trace")},
                        mass=native_mass(result,5.), boundary_area=e["boundary_flux_area"],
                        stages=stages["stages"], stage_parity=stages["final_bitwise_parity"],
                        threads=e["actual_threads"], preparations=session.preparations,
                        fields_sha256=file_hash(folder / "fields.npz"))
                    write_json(folder / "worker.json", record)
                    packets[name], records[name] = packet, record
                    local = dict(finite=bool(np.isfinite(result.velocity).all()), converged=result.diagnostics.converged,
                        threads=e["actual_threads"]==4, stage_parity=stages["final_bitwise_parity"],
                        roof=e["canyon_roof_changes"]==0, voxel_roof=e["canyon_voxel_roof_changes"]==0,
                        W_overlay=e["canyon_W_changes"]==0, trace_empty=e["canyon_roof_trace"].size==0,
                        reuse=session.preparations==1)
                    if archive:
                        with np.load(archive / name / "fields.npz") as old:
                            local.update({"archive_"+k:bits(old[k],v) for k,v in packet.items()})
                    if name in ("reference-aligned","joined-aligned"):
                        parent = packets["legacy-aligned"]; old = records["legacy-aligned"]
                        local.update(active=e["canyon_qualified"]==1 and e["canyon_changed_faces"]>0,
                            W=bits(packet["initial_W"],parent["initial_W"]),
                            coverage=np.array_equal(packet["stage_method"],parent["stage_method"]),
                            pre_canyon=bits(packet["stage_velocity"][:3],parent["stage_velocity"][:3]),
                            mass=all(mass_gate(record["mass"],old["mass"],5.,record["boundary_area"]).values()))
                    if name == "legacy-reused":
                        local.update(legacy=bits(packet["velocity"],packets["legacy-aligned"]["velocity"]),
                            clean_counters=e["canyon_qualified"]==e["canyon_changed_faces"]==0)
                    if name == "joined-oblique": local["inactive"] = e["canyon_qualified"]==e["canyon_changed_faces"]==0
                    checks.update({name+":"+key:bool(value) for key,value in local.items()})
                require_identity(frozen)
                attempts[-1].update(status="completed" if all(checks.values()) else "gate_failed",
                                   seconds=perf_counter()-started,
                                   peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform=="darwin" else 1024))
                write_json(output / "attempts.json", attempts)
            finally: timer.cancel()
            if not all(checks.values()): break
    finally:
        session.close()
        write_json(output / "report.json", dict(passed=len(attempts)==6 and all(checks.values()),
            attempts=attempts, checks=checks, physical_promotion=False))
    if len(attempts)!=6 or not all(checks.values()): raise ValueError("Canyon qualification gate failed")
    print(f"Six attempts pass {len(checks)} checks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), None if args.archive is None else args.archive.resolve())

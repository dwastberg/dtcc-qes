"""Engineering parity for off-face fixtures or the previously active D 0° case."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import threading

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "validation"), str(ROOT / "tests")]
from aij import campaigns, runner
from aij.canyon import CanyonSession, native_mass
from aij.evidence import write_json, file_hash
from aij.sampling import probe_sample
from fixtures.canyon import fixture
from rerun_regression import accuracy


def hash_array(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def run(root, archive, kind):
    from dtcc_qes import wind, _qes
    root.mkdir(parents=True, exist_ok=False)
    write_json(root / "manifest.json", dict(kind=kind, archive=archive,
        native_sha256=file_hash(_qes.__file__), policy=_qes.solver_policy_revision,
        deadline_seconds=60, memory_cap=None, answers=4 if kind=="offface" else 2))
    checks, attempts = {}, []
    descriptors = [(h,m) for h in (10.,11.5) for m in ("legacy","joined_v1")] if kind=="offface" else [(None,m) for m in ("legacy","joined_v1")]
    for height, model in descriptors:
        name = f"H{height:g}-{model}" if height is not None else model
        attempts.append(dict(name=name,status="started")); write_json(root/"attempts.json",attempts)
        timer=threading.Timer(60.,lambda:os._exit(124)); timer.daemon=True; timer.start()
        session = CanyonSession()
        try:
            if kind=="offface":
                args = fixture(height=height,nonuniform=True)
                result, stages = session.run(args,model=model,trace=True)
                probes = probe_sample(result,args["probes"].xyz)
                packet = dict(velocity=result.velocity,cell_flags=result.cell_flags,xyz=args["probes"].xyz,
                    initial_W=result.metadata["experiment"]["canyon_initial_w"],probe_velocity=probes["velocity"],
                    probe_method=probes["method"].astype("U20"),stage_velocity=stages["velocity"],stage_method=stages["method"].astype("U20"))
                with np.load(archive / name / "fields.npz") as old:
                    local={k:old[k].dtype==v.dtype and old[k].shape==v.shape and old[k].tobytes()==v.tobytes() for k,v in packet.items()}
                folder=root/name;folder.mkdir();np.savez(folder/"fields.npz",**packet)
            else:
                spec=next(s for s in campaigns.baseline() if s.case=="D" and s.direction==270.)
                if spec.key!="b324220abd408a96":raise ValueError("Changed frozen D 0-degree baseline descriptor")
                args=runner.inputs(spec); original=wind.run; captured=[]
                def solve(city,profile,**settings):
                    settings["max_cells"]=int(np.iinfo(np.int32).max)
                    result,stages=session.run(dict(args,city=city,profile=profile,run=settings),
                        model=model,trace=True,baseline_turbulence=True)
                    captured.append((result,stages));return result
                try:
                    wind.run=solve;record,planes=runner.run(spec)
                finally:wind.run=original
                if len(captured)!=1:raise ValueError("Canonical assembly must use one native answer")
                result,stages=captured.pop();folder=root/model;folder.mkdir()
                path=runner.write(record,planes,folder)
                record=json.loads(path.read_text())
                raw_hashes=dict(full_velocity=hash_array(result.velocity),full_flags=hash_array(result.cell_flags),
                    full_stress=hash_array(result.turbulence.stress),initial_W=hash_array(result.metadata['experiment']['canyon_initial_w']))
                write_json(folder/'full-field-hashes.json',raw_hashes)
                previous=archive/model/spec.case/(spec.key+".json")
                old=json.loads(previous.read_text());e=old["canyon_validation"]
                local=dict(canonical=accuracy(record,old,path.with_suffix('.npz'),previous.with_suffix('.npz'))['passed'],
                    full_velocity=hash_array(result.velocity)==e['full_velocity_sha256'],
                    full_flags=hash_array(result.cell_flags)==e['full_flags_sha256'],
                    full_stress=hash_array(result.turbulence.stress)==e['full_stress_sha256'],
                    initial_W=hash_array(result.metadata['experiment']['canyon_initial_w'])==e['initial_W_sha256'])
            e=result.metadata['experiment']
            local.update(roof=e['canyon_roof_changes']==0,voxel_roof=e['canyon_voxel_roof_changes']==0,
                         W=e['canyon_W_changes']==0,stage_parity=stages['final_bitwise_parity'],threads=e['actual_threads']==4)
            if model!='legacy':local['active']=e['canyon_changed_faces']>0
            checks.update({name+':'+k:bool(v) for k,v in local.items()})
            write_json(folder/'verification.json',dict(checks=local,diagnostics=asdict(result.diagnostics),
                mass=native_mass(result,args['reference_speed']),
                counters={k:v for k,v in e.items() if k.startswith('canyon_') and k not in ('canyon_initial_w','canyon_roof_trace')},
                peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024)))
            attempts[-1]['status']='completed' if all(local.values()) else 'gate_failed'
            write_json(root/'attempts.json',attempts)
            write_json(root/'report.json',dict(passed=all(checks.values()),checks=checks,attempts=attempts))
            if not all(local.values()):raise ValueError('Archive parity failed; preserve this attempt')
        finally:
            session.close();timer.cancel()
    print(f"{kind}: {len(attempts)} archived answers reproduced exactly")


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--kind',choices=('offface','D'),required=True)
    args=parser.parse_args();run(args.output.resolve(),args.archive.resolve(),args.kind)

"""Bounded raw-face diagnosis; preserve all historical scope failures.

Run from the checkout. Summaries audit saved data and source snapshots without
requiring a worker executable. Execution/resume additionally checks binaries.
"""
import os
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np

from near_wall_sampling import difference, reconstruct
from run_joint_grid_verification import atomic_json, fingerprint, read
from run_precision_verification import gate, input_text
from run_auto_grid_controls import HEIGHTS, POINTS, collocate

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("docs/data/near-wall-validation")
METHODS = ("centred", "staggered")
LOCATIONS = [[27,21], [21,23], [51,35]]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def references():
    paths = [Path("docs/data")/folder/backend/"raw.json.gz"
             for folder in ("joint-grid-verification", "lateral-horizontal-verification")
             for backend in ("serial", "openmp")]
    docs = {str(p): read(p) for p in paths}
    runs = {(backend, r["task"]["family"], r["task"]["direction"], r["task"]["resolution"]): r
            for path, doc in docs.items() for backend in (Path(path).parent.name,)
            for r in doc["runs"] if r["task"]["extent"] == 160}
    configs = read(Path("docs/data/joint-grid-verification/serial/manifest.json"))["configurations"]
    paths += [Path("docs/data/joint-grid-verification")/b/"summary.json" for b in ("serial","openmp")]
    paths += [Path("docs/data/joint-grid-verification/serial/manifest.json")]
    return runs, configs, {str(p): digest(p) for p in paths}


def tasks(refs):
    result = []
    for backend in ("serial", "openmp"):
        for family in ("auto", "uniform-0.5"):
            for wind in (270, 315):
                for r in (1, .5, .25):
                    result.append(dict(backend=backend, family=family, direction=wind,
                        resolution=r, extent=160, disabled=0, sweeps=0))
        for disabled in (16, 31):
            for r in (1, .5, .25):
                result.append(dict(backend=backend, family="auto", direction=270,
                    resolution=r, extent=160, disabled=disabled, sweeps=0))
        for r in (1, .5):
            ref = refs[backend,"auto",270,r]
            if not gate(ref)["accepted"]:
                raise ValueError("Solved diagnosis requires accepted archived checkpoints")
            result.append(dict(backend=backend, family="auto", direction=270,
                resolution=r, extent=160, disabled=0, sweeps=ref["checkpoints"][-1]["iterations"]))
    return [t | dict(id=f"{t['backend']}/{t['family']}/{t['direction']}/{t['resolution']:g}/{t['disabled']}/{t['sweeps']}") for t in result]


def native_input(task, configs):
    values = input_text(task, configs).split()
    values[8] = str(task["disabled"])
    return " ".join(values)+"\n"


def resources(task, configs):
    nx=int(task["extent"]/task["resolution"])
    nz=len(configs[task["family"]]["layers_input"])
    arrays=(100 if task["sweeps"] else 84)*nx*nx*(nz+1)+24*(nx+1)**2*(nz+2)+24*nx*nx
    return dict(physical_cells=nx*nx*nz,estimated_array_bytes=arrays,
                estimated_process_bytes=int(1.25*arrays+64*1024**2))


def numeric_plane(plane):
    return np.array([v if v is not None else [np.nan]*3 for v in plane["velocity"]])


def validate(run, task, refs, configs):
    expected_backend = "serial_lexicographic" if task["backend"] == "serial" else "openmp_red_black"
    if (run["backend"] != expected_backend or run["iterations"] != task["sweeps"]
        or run["start"] != "zero" or run["disabled_mask"] != task["disabled"]
        or run["resolution"] != task["resolution"] or run["direction"] != task["direction"]
        or run["origin"] != [-40,-40] or run["extent"] != [160,160]
        or run["cells"] != int(160/task["resolution"])**2*len(configs[task["family"]]["layers_input"])):
        raise ValueError("Native diagnostic scope mismatch")
    np.testing.assert_array_equal(np.array(run["z_faces"], np.float32),
                                  np.array(configs[task["family"]]["expected_faces"], np.float32))
    ref = refs.get((task["backend"],task["family"],task["direction"],task["resolution"]))
    parity = dict(archived_reference=False, max_plane_difference=0.)
    if ref is not None and task["disabled"] == 0:
        if not gate(ref)["accepted"]:
            raise ValueError("Historical reference failed solve gate")
        for stage, content in run["stages"].items():
            expected = ref["checkpoints"][-1]["planes"] if stage == "final" else ref[stage+"_planes"]
            for a,b in zip(content["planes"], expected, strict=True):
                assert a["height"] == b["height"] and a["flags"] == b["flags"]
                av,bv=numeric_plane(a),numeric_plane(b)
                np.testing.assert_allclose(av,bv,rtol=0,atol=5e-9,equal_nan=True)
                parity["max_plane_difference"]=max(parity["max_plane_difference"],float(np.nanmax(abs(av-bv))))
        if task["sweeps"]:
            for key in ("max_divergence","rms_divergence"):
                np.testing.assert_allclose(run[key],ref["checkpoints"][-1][key],rtol=2e-9,atol=1e-14)
            assert run["assessed_cells"] == ref["checkpoints"][-1]["assessed_cells"]
        parity["archived_reference"]=True
    # Independently reconstruct the original point sampler from raw centred
    # patches and compare it with the native plane + historical collocator.
    nx=int(160/task["resolution"])
    axis=(np.arange(nx,dtype=np.float32)+np.float32(.5))*np.float32(task["resolution"])-40
    indices=set()
    for p in POINTS:
        hi=int(np.searchsorted(axis,p)); indices.add(hi)
        if axis[hi] != p: indices.add(hi-1)
    axis=axis[sorted(indices)]
    parity["max_patch_reconstruction_difference"]=0.
    for content in run["stages"].values():
        if len(content["patches"]) != 6:
            raise ValueError("Missing point patches")
        for patch, (h,p) in zip(content["patches"], [(h,p) for h in HEIGHTS for p in LOCATIONS], strict=True):
            assert patch["local_point"] == [p[0]+40,p[1]+40,h]
            plane, = [a for a in content["planes"] if a["height"] == h]
            points=collocate(plane["velocity"],axis,axis)
            index=list(POINTS).index(p[1])*len(POINTS)+list(POINTS).index(p[0])
            centre=reconstruct(patch,"centred")
            if centre is None or points[index] is None:
                raise ValueError("Unavailable fixed diagnostic point")
            delta=float(np.max(abs(centre-points[index])))
            if delta>5e-7:
                raise ValueError("Raw patch does not reproduce original sampler")
            parity["max_patch_reconstruction_difference"]=max(parity["max_patch_reconstruction_difference"],delta)
    return parity


def execute(task, manifest, refs, configs, output):
    case=output/"cases"/(task["id"]+".json.gz")
    identity=fingerprint(manifest)
    request=dict(identity=identity,task=task,input_sha256=hashlib.sha256(native_input(task,configs).encode()).hexdigest())
    if case.exists():
        saved=read(case)
        if saved["request"]!=request or fingerprint(saved["run"])!=saved["run_sha256"]:
            raise ValueError("Changed cached diagnostic")
        validate(saved["run"],task,refs,configs)
        return
    print("START",task["id"],flush=True)
    executable=manifest["binaries"][task["backend"]]["path"]
    proc=subprocess.run([executable,str(task["direction"]),str(task["sweeps"]),"60000000"],
                        env=os.environ | {"DTCC_QES_STUDY_ORDER": "legacy"}, input=native_input(task,configs),text=True,capture_output=True,check=True,timeout=7200)
    if proc.stderr: raise ValueError(proc.stderr)
    run=json.loads(proc.stdout)
    parity=validate(run,task,refs,configs)
    atomic_json(case,dict(request=request,run=run,run_sha256=fingerprint(run),parity=parity))
    print("DONE",task["id"],"RSS",run["peak_rss_bytes"],"solve",run["solve_seconds"],flush=True)


def summarize(output):
    manifest=read(output/"manifest.json")
    if digest(output/"protocol.md")!=manifest["protocol_sha256"]:
        raise ValueError("Changed frozen protocol")
    for path,sha in manifest["source_sha256"].items():
        if digest(output/"sources"/path)!=sha:
            raise ValueError("Changed archived source snapshot")
    for path,sha in manifest["references_sha256"].items():
        if digest(path)!=sha: raise ValueError("Changed reference archive")
    refs,configs,_=references()
    if configs!=manifest["configurations"]: raise ValueError("Changed frozen layers")
    runs={}; parity=[]
    for task in manifest["tasks"]:
        path=output/"cases"/(task["id"]+".json.gz")
        if not path.exists(): continue
        saved=read(path)
        request=dict(identity=fingerprint(manifest),task=task,input_sha256=hashlib.sha256(native_input(task,configs).encode()).hexdigest())
        if saved["request"]!=request or saved["run_sha256"]!=fingerprint(saved["run"]):
            raise ValueError("Diagnostic identity/content mismatch")
        check=validate(saved["run"],task,refs,configs)
        if check!=saved["parity"]: raise ValueError("Parity changed")
        parity.append(dict(task=task,**check))
        runs[task["id"]]=saved["run"]
    points=[]; comparisons=[]; decomposition=[]
    taskmap={t["id"]:t for t in manifest["tasks"]}
    for key,run in runs.items():
        t=taskmap[key]
        for stage,content in run["stages"].items():
            for p in content["patches"]:
                vectors={method:reconstruct(p,method) for method in METHODS}
                points.append(dict(task=t,stage=stage,point=[p["local_point"][0]-40,p["local_point"][1]-40,p["local_point"][2]],
                    vectors={m:None if v is None else v.tolist() for m,v in vectors.items()},
                    sampler_difference=difference(vectors["centred"],vectors["staggered"])))
    for backend in ("serial","openmp"):
        for family in ("auto","uniform-0.5"):
            for wind in (270,315):
                for disabled in (0,16,31):
                    for stage in ("profile","initial","final"):
                        for a,b in ((1,.5),(.5,.25)):
                            # Final rows use solved runs; initialization rows use independent probes.
                            chosen=[]
                            for r in (a,b):
                                ts=[t for t in manifest["tasks"] if t["backend"]==backend and t["family"]==family
                                    and t["direction"]==wind and t["disabled"]==disabled and t["resolution"]==r
                                    and bool(t["sweeps"])==(stage=="final") and t["id"] in runs]
                                if len(ts)==1: chosen.append(ts[0])
                            if len(chosen)!=2: continue
                            aa,bb=[runs[t["id"]]["stages"][stage]["patches"] for t in chosen]
                            for j,(pa,pb) in enumerate(zip(aa,bb,strict=True)):
                                for method in METHODS:
                                    av,bv=reconstruct(pa,method),reconstruct(pb,method)
                                    row=dict(backend=backend,family=family,direction=wind,disabled=disabled,
                                        stage=stage,spacing=[a,b],point=[pa["local_point"][0]-40,pa["local_point"][1]-40,pa["local_point"][2]],
                                        method=method,**difference(av,bv))
                                    comparisons.append(row)
                                    if stage=="final" and av is not None and bv is not None:
                                        ia,ib=[reconstruct(runs[t["id"]]["stages"]["initial"]["patches"][j],method) for t in chosen]
                                        di,df=ib-ia,bv-av
                                        decomposition.append(row | dict(initial_vector_change=di.tolist(),final_vector_change=df.tolist(),
                                            projection_correction_change=(df-di).tolist()))
    cross=[]
    for t in manifest["tasks"]:
        if t["backend"]!="serial" or t["id"] not in runs: continue
        mates=[q for q in manifest["tasks"] if q["backend"]=="openmp" and q["id"] in runs and
               all(t[k]==q[k] for k in ("family","direction","resolution","disabled")) and bool(t["sweeps"])==bool(q["sweeps"])]
        if not mates: continue
        other=runs[mates[0]["id"]]
        for stage in ("profile","initial"):
            if runs[t["id"]]["stages"][stage]!=other["stages"][stage]:
                raise ValueError("CPU initial raw-face/support mismatch")
        delta=0.
        if t["sweeps"]:
            for pa,pb in zip(runs[t["id"]]["stages"]["final"]["patches"],other["stages"]["final"]["patches"],strict=True):
                for method in METHODS:
                    delta=max(delta,float(np.linalg.norm(reconstruct(pa,method)-reconstruct(pb,method))/5))
        cross.append(dict(task=t["id"],initial_exact=True,max_final_vector_difference_over_Uref=delta))
    # Versioned region correction; retain the immutable historical summaries.
    regions=[]
    for backend in ("serial","openmp"):
        old=read(Path("docs/data/joint-grid-verification")/backend/"summary.json")
        for r in old["comparisons"]:
            regions.append(dict(backend=backend,comparison=r["comparison"],family=r["family"],direction=r["direction"],
                height=r["height"],region=r["region"],regional_budget_pass=r["within_budget"] and r["solid_fluid_transitions"]==0,
                mandatory_full_region_checks_pass=r["local_checks_within_budget"],
                full_region_qualified=r["combined_within_budget"] if r["region"]=="all" else None))
    result=dict(schema="near-wall-v1",complete=len(runs)==len(manifest["tasks"]),cases=len(runs),
        parity=parity,points=points,comparisons=comparisons,decomposition=decomposition,cross_backend=cross,
        regional_summary_v2=regions,peak_rss_bytes=max((r["peak_rss_bytes"] for r in runs.values()),default=0),
        final_solve_seconds=sum(r["solve_seconds"] for r in runs.values()),
        public_sampler_changed=False,new_grid_qualified=False,new_sampler_qualified=False)
    atomic_json(output/"summary.json",result)
    print("SUMMARY",result["cases"],"complete",result["complete"],flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    parser.add_argument("--summarize",action="store_true")
    parser.add_argument("--only",nargs="+",help="Pilot IDs within the complete predeclared matrix")
    args=parser.parse_args()
    if args.summarize:
        summarize(args.output); return
    refs,configs,hashes=references()
    sources=[Path(__file__).relative_to(ROOT) if Path(__file__).is_absolute() else Path(__file__),
             Path("tools/near_wall_sampling.py"),Path("tools/near_wall_probe.cpp"),Path("tools/build_near_wall_probe.py"),
             Path("tests/test_near_wall_validation.py")]
    legacy=read(Path("docs/data/joint-grid-verification/serial/manifest.json"))["metadata"]["source_sha256"]
    sources+= [Path(p).relative_to(ROOT) if Path(p).is_absolute() else Path(p) for p in legacy]
    binaries={b:dict(path=str((Path("build/near-wall/bin")/b).resolve()),sha256=digest(Path("build/near-wall/bin")/b),
                    build_record=read(Path("build/near-wall/bin")/(b+".build.json"))) for b in ("serial","openmp")}
    matrix=tasks(refs)
    if args.only and not set(args.only)<={t["id"] for t in matrix}:
        parser.error("Unknown pilot task")
    manifest=dict(schema="near-wall-v1",tasks=matrix,configurations=configs,references_sha256=hashes,
        source_sha256={str(p):digest(p) for p in sorted(set(sources))},binaries=binaries,
        allocation_ceiling=60000000,probe_workers=2,solved_workers=1,
        resources={t["id"]:resources(t,configs) for t in matrix},
        protocol_commit="3d479af",protocol_sha256=digest("docs/near-wall-validation.md"),
        scope="point vectors; fixed z; initial 1/.5/.25; accepted 1/.5 final parity; no new sampler qualification")
    path=args.output/"manifest.json"
    if path.exists():
        previous=read(path)
        # The protocol report may gain results after completion. Its initial
        # version remains snapshotted and immutable for resuming this matrix.
        manifest["protocol_sha256"]=previous["protocol_sha256"]
        if previous!=manifest: raise ValueError("Changed study input/source/binary; use a new output directory")
    else:
        for p in sorted(set(sources)):
            dest=args.output/"sources"/p; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(p.read_bytes())
        dest=args.output/"protocol.md"; dest.write_bytes(Path("docs/near-wall-validation.md").read_bytes())
        atomic_json(path,manifest)
    selected=[t for t in manifest["tasks"] if not args.only or t["id"] in args.only]
    probes=[t for t in selected if not t["sweeps"]]
    solved=[t for t in selected if t["sweeps"]]
    # One solve at a time; two preparation-only workers in a separate pool.
    def solve_all():
        for t in sorted(solved,key=lambda t:t["backend"]): execute(t,manifest,refs,configs,args.output)
    with ThreadPoolExecutor(max_workers=2) as pool, ThreadPoolExecutor(max_workers=1) as solve_pool:
        pending=[pool.submit(execute,t,manifest,refs,configs,args.output) for t in probes]
        pending.append(solve_pool.submit(solve_all))
        for future in as_completed(pending): future.result()
    summarize(args.output)


if __name__=="__main__":
    main()

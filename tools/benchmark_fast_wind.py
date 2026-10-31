"""Bounded normal-API timing; no fixed-sweep certification or budget escalation."""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter
import numpy as np
from run_joint_grid_verification import atomic_json, read
from run_horizontal_sensitivity import digest

ROOT=Path('docs/data/finest-reference')


def worker(precision, output):
    from run_auto_grid_controls import make_city, rectangles
    from dtcc_qes import wind, _qes
    city=make_city(rectangles('tower'));spec=wind.VerticalGrid.auto()
    options=dict(resolution=.5,bounds=(-40,-40,0,120,120,64),vertical_grid=spec,max_cells=40000000)
    start=perf_counter();preview=wind.preview_grid(city,**options);planning=perf_counter()-start
    start=perf_counter()
    result=wind.run(city,5,270,solver_precision=precision,**options)
    elapsed=perf_counter()-start
    atomic_json(output,dict(status='completed',precision=precision,backend=_qes.cpu_backend,
        build_type=_qes.build_type,compiler=_qes.compiler_version,
        extension_sha256=digest(_qes.__file__),cells=preview.cell_count,layers=len(preview.z),
        planning_seconds=planning,api_run_seconds=elapsed,diagnostics=asdict(result.diagnostics),
        requested_max_iterations=500,tolerance=1e-5,
        scope='Normal API, early-stop rule enabled; no claim of accepted residuals, pedestrian stability or comfort accuracy'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',choices=('float32','float64'))
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.worker:return worker(args.worker,args.output)
    root=ROOT/'runtime-cases';root.mkdir(parents=True,exist_ok=True);rows=[]
    for precision in ('float32','float64'):
        output=root/(precision+'.json');log=root/(precision+'.log')
        command=[str(Path(sys.executable).absolute()),str(Path(__file__).absolute()),'--worker',precision,'--output',str(output)]
        start=perf_counter()
        with log.open('w') as stream:
            try:
                subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,check=True,timeout=30,
                    env=os.environ | {'OMP_NUM_THREADS':'2','OMP_DYNAMIC':'FALSE'})
                row=read(output)
            except subprocess.TimeoutExpired:
                row=dict(status='timeout',precision=precision,wall_limit_seconds=30);atomic_json(output,row)
            except subprocess.CalledProcessError as error:
                row=dict(status='failed',precision=precision,exit_code=error.returncode);atomic_json(output,row)
        rows.append(row | dict(process_elapsed_seconds=perf_counter()-start,log=str(log)))
        print(rows[-1],flush=True)
    paths=['tools/benchmark_fast_wind.py','src/cpp/wind_runner.cpp','src/cpp/precision_solver.cpp',
        'src/cpp/bindings.cpp','src/dtcc_qes/wind.py','src/dtcc_qes/_auto_grid.py']
    atomic_json(ROOT/'runtime-review.json',dict(utc=datetime.now(timezone.utc).isoformat(),
        platform=platform.platform(),numpy=np.__version__,cpu_count=os.cpu_count(),runs=rows,
        per_case_wall_limit_seconds=30,source_sha256={p:digest(p) for p in paths},
        scope='Two bounded timing diagnostics on installed Release backend; imports and City construction excluded from API timer. No accuracy qualification. No adaptive escalation.'))


if __name__=='__main__':main()

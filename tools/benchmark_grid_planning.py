"""Time layer selection and preview separately from native allocation/solving."""
from datetime import datetime, timezone
import argparse
from pathlib import Path
import platform
from time import perf_counter
import numpy as np
from run_auto_grid_controls import make_city, rectangles
from run_joint_grid_verification import atomic_json, read
from run_horizontal_sensitivity import digest
from dtcc_qes import wind
from dtcc_qes._auto_grid import generate_auto_layers


def measure(function, repetitions=30):
    start=perf_counter();function();first=perf_counter()-start
    times=[]
    for _ in range(repetitions):
        start=perf_counter();function();times.append(perf_counter()-start)
    return dict(first_ms=first*1000,median_ms=float(np.median(times)*1000),
                p95_ms=float(np.percentile(times,95)*1000),repetitions=repetitions)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('docs/data/finest-reference/planning-timings.json'))
    args=parser.parse_args();spec=wind.VerticalGrid.auto();rows={}
    for count in (4,1000,100000):
        heights=np.resize(np.array([7.9,7.9,7.9,23.7]),count)
        rows[f'layer_generation_{count}_heights']=measure(lambda:generate_auto_layers(
            spec._automatic,resolution=.5,top=64,heights=heights))
    for count,rects,reps in ((4,rectangles('tower'),30),(1000,
        [[5+(i%25)*2,5+(i//25)*2,1,1,23.7 if i%4==3 else 7.9] for i in range(1000)],5)):
        city=make_city(rects)
        rows[f'preview_{count}_buildings']=measure(lambda:wind.preview_grid(city,resolution=.5,
            bounds=(-40,-40,0,120,120,64),vertical_grid=spec,max_cells=40000000),reps)
    source=Path('docs/data/vertical-refinement/raw.json.gz')
    run=next(r for r in read(source)['openmp']['runs'] if r['task']['family']=='split-4')
    rows['historical_native_preparation']=dict(cells=run['cells'],seconds=run['prep_seconds'],
        source=str(source),source_sha256=digest(source),scope='Array allocation, geometry/physics initialization and solver workspace; not layer selection')
    paths=[Path('tools/benchmark_grid_planning.py'),Path('src/dtcc_qes/_auto_grid.py'),Path('src/dtcc_qes/vertical_grid.py'),
           Path('src/dtcc_qes/wind.py'),Path('src/dtcc_qes/_city.py')]
    doc=dict(utc=datetime.now(timezone.utc).isoformat(),platform=platform.platform(),numpy=np.__version__,
        source_sha256={str(p):digest(p) for p in paths},measurements=rows,
        scope='Imports and City construction excluded; preview includes geometry extraction/checks. Synthetic fixtures; four distinct heights in layer-only stress test. Shared host with validation worker active; not a hardware-independent guarantee.')
    atomic_json(args.output,doc)
    for name,row in rows.items():print(name,row)


if __name__=='__main__':main()

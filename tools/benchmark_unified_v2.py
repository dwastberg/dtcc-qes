"""Repeatable engineering receipts; no wind campaign or physical claims."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
import tracemalloc
import numpy as np
from dtcc_qes._statistics import _physical_k


def measure(call, repetitions=5):
    times=[]
    for _ in range(repetitions):
        start=time.perf_counter(); value=call(); times.append(time.perf_counter()-start)
        del value
    tracemalloc.start()
    value=call()
    _, peak=tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return dict(raw_seconds=times, median_seconds=float(np.median(times)),
                p95_seconds=float(np.percentile(times,95)), peak_traced_bytes=peak,
                self_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    stress=np.zeros((3_000_000,6),np.float32);stress[:,[0,3,5]]=[4,2,1]
    covered=np.ones(3_000_000,bool)
    receipt=dict(schema_version=1, physical_k=measure(lambda:_physical_k(stress,covered)),
        input_bytes=stress.nbytes+covered.nbytes,output_bytes=covered.size*8,
        sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                 (Path('src/dtcc_qes/_statistics.py'),Path('src/dtcc_qes/result.py'))})
    receipt['physical_k']['scratch_bytes']=receipt['physical_k']['peak_traced_bytes']-receipt['output_bytes']
    args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()

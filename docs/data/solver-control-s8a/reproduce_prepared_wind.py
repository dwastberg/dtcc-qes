"""Build the frozen S8a sources and rerun the finite 24-worker timing pilot.

Needs the project's Python dependencies, CMake/compiler and an OpenMP runtime.
The measured reuse decision is machine dependent; no fixed speedup is asserted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from compare_native_builds import stage_package


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    here=Path(__file__).resolve().parent
    ap.add_argument('--evidence',type=Path,default=here if (here/'manifest.json').exists() else here.parent/'docs/data/solver-control-s8a')
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();evidence=args.evidence.resolve();out=args.output.resolve()
    archive=evidence/'sources.tar.gz';manifest=json.loads((evidence/'manifest.json').read_text())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['files']['sources.tar.gz']:raise ValueError('Changed S8a sources')
    out.mkdir(parents=True,exist_ok=False);tree=out/'tree';tree.mkdir()
    with tarfile.open(archive) as a:a.extractall(tree,filter='data')
    for label,cmd in [('configure',['cmake','-S',str(tree),'-B',str(out/'native'),'-DCMAKE_BUILD_TYPE=Release',f'-DPython_EXECUTABLE={sys.executable}','-DDTCC_QES_OPENMP=ON']),
                      ('build',['cmake','--build',str(out/'native'),'--target','_qes','-j8'])]:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        (out/f'{label}.log').write_text(r.stdout+r.stderr);r.check_returncode()
    stage_package(tree,next((out/'native').glob('_qes*.so')),out/'package')
    subprocess.run([sys.executable,str(tree/'tools/benchmark_prepared_wind.py'),'--kind','prototype','--output',str(out/'study')],
        check=True,timeout=180,env=os.environ|{'PYTHONPATH':str(out/'package'),'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
    print((out/'study/summary.json').read_text())


if __name__=='__main__':main()

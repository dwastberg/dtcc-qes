"""Installed-wheel API and feature-off comparison using one native binary.

Run with the project interpreter. Its editable import redirects are bypassed
by the isolated (-S) workers, which load only the extracted wheel and explicit
third-party site-packages. The baseline Python sources come from git main.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

WORKER = r'''
import sys,json,time,hashlib,resource
sys.path[:0]=[sys.argv[1],sys.argv[2]]
import numpy as np
from dtcc_core.model import Building,City,GeometryType,Surface
from dtcc_qes import wind,_qes
city=City();building=Building(id='probe');building.measured_height=8
building.add_geometry(Surface(vertices=np.array([[30,24,0],[30,34,0],[40,34,0],[40,24,0]],float)),GeometryType.LOD0)
city.add_building(building)
options=dict(profile=wind.LogProfile(5,270),resolution=2,bounds=(0,0,0,80,60,40))
times=[]
for i in range(4):
    started=time.perf_counter();result=wind.run(city,**options);times.append(time.perf_counter()-started)
arrays={name:hashlib.sha256(getattr(result,name).tobytes()).hexdigest() for name in ('velocity','cell_flags')}
if sys.argv[3]=='candidate':
    result=wind.run(city,**options,turbulence=wind.Turbulence())
    sample=result.sample_points([[5,5,1.5]],'linear',diagnostics=True)
    assert np.isfinite(sample.physical_k).all()
    report=result.quality_report(sample).to_dict();json.dumps(report,allow_nan=False)
    grid=result.to_dtcc(include_physical_k=True)
    assert 'physical_k' in {field.name for field in grid.fields}
    assert wind.check_geometry(city,result).to_dict()['status']=='no_issue_in_examined_scope'
print(json.dumps(dict(seconds=times,arrays=arrays,
    array_bytes=result.velocity.nbytes+result.cell_flags.nbytes,
    peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    package_path=wind.__file__,native_path=_qes.__file__,policy_revision=_qes.solver_policy_revision)))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='qes-v2-wheel-') as temp:
        staging=Path(temp);candidate=staging/'candidate';baseline=staging/'baseline'
        with zipfile.ZipFile(args.wheel) as archive:archive.extractall(candidate)
        package=baseline/'dtcc_qes';package.mkdir(parents=True)
        files=subprocess.run(['git','ls-tree','-r','--name-only','main','src/dtcc_qes'],check=True,capture_output=True,text=True).stdout.splitlines()
        for file in files:
            if not file.endswith('.py'):continue
            target=baseline/str(Path(file).relative_to('src'));target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(subprocess.run(['git','show','main:'+file],check=True,capture_output=True).stdout)
        native=next((candidate/'dtcc_qes').glob('_qes*.so'));shutil.copy2(native,package/native.name)
        worker=staging/'worker.py';worker.write_text(WORKER)
        data={'baseline':[],'candidate':[]};order=[]
        import numpy as np
        for epoch in range(5):
            for arm in (('baseline','candidate') if epoch%2==0 else ('candidate','baseline')):
                root=baseline if arm=='baseline' else candidate;order.append([epoch,arm])
                completed=subprocess.run([sys.executable,'-S',str(worker),str(root),sysconfig.get_paths()['purelib'],arm],
                    check=True,text=True,capture_output=True,timeout=120)
                data[arm].append(json.loads(completed.stdout.splitlines()[-1]))
        assert all(row['arrays']==data['baseline'][0]['arrays'] for rows in data.values() for row in rows)
        for arm,rows in data.items():
            times=np.concatenate([row['seconds'] for row in rows])
            data[arm]=dict(raw=rows,median_seconds=float(np.median(times)),p95_seconds=float(np.percentile(times,95)))
        difference=data['candidate']['median_seconds']-data['baseline']['median_seconds']
        ratio=data['candidate']['median_seconds']/data['baseline']['median_seconds']
        receipt=dict(schema_version=1,wheel_sha256=hashlib.sha256(args.wheel.read_bytes()).hexdigest(),
            epoch_order=order,results=data,median_difference_seconds=difference,median_ratio=ratio,
            regression_threshold_exceeded=bool(difference>.01 and ratio>1.05),
            feature_off_arrays_exact=True,native_binary_shared=True,installed_wheel_smoke='passed')
        args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
        print(json.dumps({k:v for k,v in receipt.items() if k not in ('results','epoch_order')},indent=2))

if __name__=='__main__':main()

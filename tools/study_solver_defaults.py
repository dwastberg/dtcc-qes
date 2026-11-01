"""Reproduce the predeclared two-city accuracy/latency selection for Solver defaults.

Run from the repository root with a staged package and OMP_NUM_THREADS=2.
Writes all reference checks, repetitions and candidates under build/.
"""
from pathlib import Path
import json,sys,time
import numpy as np
sys.path.insert(0,'tools')
from compare_native_builds import make_city,BLOCKS
from dtcc_qes import wind,_qes
root=Path('build/feature-merge-baseline')
criteria=json.loads((root/'final-focused-costs-old.json').read_text())['default_study']
report=dict(criteria=criteria,backend=_qes.cpu_backend,threads=2,cities={},candidates=[])
cities={'towers':make_city([(22,22,12,12,7.9),(42,22,12,12,7.9),(22,42,12,12,7.9),(42,42,12,12,23.7)]),'six_blocks':make_city(BLOCKS)}
refs={}
def solve(city,tol,limit,precision='float32'):
 return wind.run(city,speed=5,direction=270,bounds=(0,0,0,160,160,64),solver=wind.Solver(tolerance=tol,max_iterations=limit,precision=precision))
def error(a,b):
 valid=a.valid&b.valid
 delta=np.linalg.norm(a.velocity[valid]-b.velocity[valid],axis=-1)/5
 return dict(p95_K=float(np.percentile(delta,95)),max_K=float(delta.max()),valid_cells=int(valid.sum()))
for name,city in cities.items():
 a=solve(city,1e-7,20000,'float64');b=solve(city,1e-8,30000,'float64')
 assert a.diagnostics.converged and b.diagnostics.converged
 metric=error(a.sample(1.5,method='linear'),b.sample(1.5,method='linear'))
 assert metric['p95_K']<=criteria['stability_p95_K'] and metric['max_K']<=criteria['stability_max_K']
 report['cities'][name]=dict(reference_iterations=a.diagnostics.iterations,tighter_iterations=b.diagnostics.iterations,stability=metric)
 refs[name]=b
for tol,limit in [(1e-4,1000),(1e-5,500),(1e-5,1000),(1e-6,2000),(float(np.finfo(np.float32).eps),4000)]:
 row=dict(tolerance=tol,max_iterations=limit,cities={},passed=True)
 for name,city in cities.items():
  a=solve(city,tol,limit)
  metric=error(a.sample(1.5,method='linear'),refs[name].sample(1.5,method='linear'))
  elapsed=[]
  for i in range(5):
   start=time.perf_counter();r=solve(city,tol,limit);elapsed.append(time.perf_counter()-start)
   assert r.diagnostics.iterations==a.diagnostics.iterations
  passed=metric['p95_K']<=criteria['candidate_p95_K'] and metric['max_K']<=criteria['candidate_max_K']
  row['passed'] &= passed
  row['cities'][name]=dict(error=metric,passed=passed,converged=a.diagnostics.converged,iterations=a.diagnostics.iterations,seconds=elapsed,median_seconds=float(np.median(elapsed)))
 row['combined_median_seconds']=sum(c['median_seconds'] for c in row['cities'].values())
 report['candidates'].append(row)
 (root/'phase5-default-study.json').write_text(json.dumps(report,indent=2)+'\n')
passing=[r for r in report['candidates'] if r['passed']]
assert passing,'No candidate passes the declared error limits'
report['winner']=min(passing,key=lambda r:r['combined_median_seconds'])
(root/'phase5-default-study.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report['winner'],indent=2))

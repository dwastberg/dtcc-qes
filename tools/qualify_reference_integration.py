"""Strict impact audit for the declared reference-estimator correction."""
import argparse
import json
from pathlib import Path
import numpy as np
from compare_native_builds import _native_consolidation_metadata, compare_results


def compare_impact(baseline, candidate):
    with np.load(baseline) as a, np.load(candidate) as b:
        left={k:a[k] for k in a.files}; right={k:b[k] for k in b.files}
    identities=[str(d['_policy_revision']) for d in (left,right)]
    _native_consolidation_metadata(left,right,identities)
    differences=[]; declared=[]
    additions=set(right)-set(left)
    for key in sorted(additions):
        if key.endswith(('/turbulence/reference_sampling/scalars',
                         '/metadata/turbulence/reference/sampling/scalars')):
            declared.append(dict(key=key,kind='reference_support_metadata'))
        else: differences.append('Unexpected added field: '+key)
    differences += ['Missing field: '+k for k in sorted(set(left)-set(right))]
    for key in sorted(set(left)&set(right)-{'_module'}):
        a,b=left[key],right[key]
        if a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes(): continue
        changed=None
        if '/turbulence/' in key and key.rsplit('/',1)[-1] in ('stress','tke','co_eps','capped','state','stress_valid'):
            if a.shape!=b.shape or a.dtype!=b.dtype: differences.append('Changed array contract: '+key);continue
            if key.endswith('/state') and not np.array_equal(a>0,b>0):
                differences.append('Changed computed population: '+key);continue
            finite=np.isfinite(a)&np.isfinite(b)
            if not np.array_equal(np.isfinite(a),np.isfinite(b)):
                differences.append('Changed finite support: '+key);continue
            changed=dict(kind='reference_dependent_array',changed_entries=int(np.count_nonzero(a[finite]!=b[finite])),
                         maximum_absolute_change=float(np.max(np.abs(a[finite].astype(float)-b[finite].astype(float)),initial=0)))
        elif key.endswith('/scalars'):
            x,y=json.loads(str(a)),json.loads(str(b));allowed=set()
            if key.endswith('/metadata/turbulence/scalars'):
                if y['numerics_version']!='dtcc-qes-turbulence-v2' or x['numerics_version']!='dtcc-qes-turbulence-v1':
                    differences.append('Unexpected numerical version: '+key);continue
                if y['audited_fixes']!=x['audited_fixes'][:2]+['declared_height_vector_reference','float64_reference_mean']+x['audited_fixes'][2:]:
                    differences.append('Unexpected audited fixes: '+key);continue
                allowed={'numerics_version','audited_fixes'}
            elif key.endswith('/metadata/turbulence/reference/scalars'): allowed={'speed','friction_velocity'}
            elif key.endswith('/metadata/turbulence/cap/scalars'): allowed={'value','capped_cells'}
            elif key.endswith('/metadata/turbulence/validity/scalars'): allowed={'invalid_stress_cells'}
            elif key.endswith('/turbulence/scalars'):
                allowed={'reference_speed','friction_velocity','capped_cells','invalid_stress_cells'}
            actual={k for k in set(x)|set(y) if x.get(k)!=y.get(k)}
            if actual and actual<=allowed:
                changed=dict(kind='reference_dependent_scalars',fields={k:dict(before=x.get(k),after=y.get(k)) for k in sorted(actual)})
        if changed: declared.append(dict(key=key,**changed))
        else: differences.append('Undeclared change: '+key)
    return dict(passed=not differences,identities=identities,records=len(left)-1,
                differences=differences,declared_changes=declared)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--equivalent',action='store_true')
    a=p.parse_args()
    if a.equivalent:
        with np.load(a.baseline) as x,np.load(a.candidate) as y:
            pair=[str(x['_policy_revision']),str(y['_policy_revision'])]
        differences,records=compare_results(a.baseline,a.candidate,native_consolidation=True,identity_pair=pair)
        result=dict(passed=not differences,differences=differences,records=records,identities=pair)
    else: result=compare_impact(a.baseline,a.candidate)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='declared_changes'}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__': main()

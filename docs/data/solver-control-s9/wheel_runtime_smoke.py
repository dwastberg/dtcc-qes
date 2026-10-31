"""Exercise the actually installed release wheel with project dependencies."""
import argparse
import json
from pathlib import Path
import sys


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--expected-package',type=Path,required=True)
    args=ap.parse_args()
    # A dependency environment may contain an editable dtcc-qes finder. Do not
    # let it hide a broken or incomplete installed wheel.
    sys.meta_path[:]=[f for f in sys.meta_path if not any(
        n=='dtcc_qes' or n.startswith('dtcc_qes.') for attr in ('known_source_files','known_wheel_files')
        for n in getattr(f,attr,{}))]
    import numpy as np
    import dtcc_qes
    from dtcc_qes import wind,_qes
    from dtcc_core.model import Building,City,Surface,GeometryType
    root=args.expected_package.resolve()
    assert all(Path(m.__file__).resolve().is_relative_to(root) for m in (dtcc_qes,wind,_qes))
    city=City()
    for i,(x,y,h) in enumerate([(22,22,7.9),(42,22,7.9),(22,42,7.9),(42,42,23.7)]):
        b=Building(id=str(i));b.measured_height=h
        b.add_geometry(Surface(vertices=np.array([[x,y,0],[x,y+12,0],[x+12,y+12,0],[x+12,y,0],[x,y,0]],float)),GeometryType.LOD0)
        city.add_building(b)
    monitor=wind.MonitorSpec((0,80,0,80),receptors=tuple(wind.Receptor(f'h{h}',27,21,h) for h in [1.5,1.75]),history_limit=8)
    result=wind.run(city,5,270,bounds=(0,0,0,160,160,64),max_iterations=600,
        solver_control=wind.SolverControl(5,monitor,mode='adaptive'))
    supported=_qes.compiler_id=='AppleClang' and _qes.compiler_version.startswith('17.') and sys.platform=='darwin'
    if supported:assert result.control['accepted'] and not result.diagnostics.converged
    assert result.control['policy_revision']==_qes.solver_policy_revision
    assert len(result.control['checkpoint_history'])<=8 and len(result.control['assessment_history'])<=8
    assert result.velocity.flags.owndata and result.cell_flags.flags.owndata
    assert result.sample(1.5,method='linear').velocity.shape==(80,80,3)
    json.dumps(result.metadata,allow_nan=False)
    small=dict(bounds=(0,0,0,24,24,32),max_iterations=2)
    legacy=wind.run(City(),5,270,solver_precision='float64',**small)
    assert legacy.control is None and legacy.velocity.dtype==np.float32
    for method in ['height','wall_distance']:
        r=wind.run(City(),5,45,turbulence=wind.Turbulence(method),**small)
        assert r.turbulence is not None and r.turbulence.stress.flags.owndata
    try:wind.run(City(),5,270,solver_control=wind.SolverControl(1e-12,wind.MonitorSpec((0,24,0,24))),**small)
    except wind.BudgetExhaustedError as e:assert e.record['iterations']==0
    else:raise AssertionError('Expected zero-work budget exhaustion')
    print(json.dumps(dict(passed=True,package=str(root),module=str(_qes.__file__),policy_revision=_qes.solver_policy_revision,
        adaptive_accepted=result.control['accepted'],actual_threads=result.control['actual_threads'],checks=['owned_output','sampling','adaptive_vs_legacy_status','history_bounds','float64','two_turbulence_methods','zero_work_error'])))


if __name__=='__main__':main()

"""Exercise the actually installed release wheel with project dependencies."""
from dataclasses import replace
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
    result=wind.run(city, bounds=(0,0,0,160,160,64), solver=replace(wind.Solver(max_solve_seconds=5, monitor=monitor, policy="pedestrian-v1"), max_iterations=600), speed=5, direction=270)
    supported = _qes.solver_policy_build_supported
    if supported:assert result.solver["record"]['accepted'] and not result.diagnostics.converged
    else:assert not result.solver["record"]['accepted'] and result.solver["record"]['assessment_reason']=='unqualified_build'
    assert result.solver["record"]['policy_revision']==_qes.solver_policy_revision
    qualification=result.qualification
    assert qualification['solver']['assessment']==('accepted' if supported else 'not_assessed')
    assert qualification['solver']['legacy_converged']==result.diagnostics.converged
    assert 'qualification' not in result.metadata
    assert result.metadata['timings']['public_call_seconds']>=result.metadata['timings']['city_preparation_seconds']>=0
    assert result.metadata['timings']['native']==result.solver['record']['timings']
    json.dumps(qualification,allow_nan=False)
    assert len(result.solver["record"]['checkpoint_history'])<=8 and len(result.solver["record"]['assessment_history'])<=8
    assert result.velocity.flags.owndata and result.cell_flags.flags.owndata
    assert result.sample(1.5,method='linear').velocity.shape==(80,80,3)
    json.dumps(result.metadata,allow_nan=False)
    # Exercise the shipped canonical module and ring bridge, including a podium hole.
    low = Building(id="podium"); low.measured_height = 6
    low.add_geometry(Surface(vertices=np.array([[4,4,0],[4,20,0],[20,20,0],[20,4,0]], float)), GeometryType.LOD0)
    high = Building(id="tower"); high.measured_height = 12
    high.add_geometry(Surface(vertices=np.array([[8,8,0],[8,16,0],[16,16,0],[16,8,0]], float)), GeometryType.LOD0)
    stepped = City(); stepped.add_buildings([low, high])
    canonical = wind.run(stepped, bounds=(0,0,0,24,24,32), resolution=1, footprints=wind.Footprints(min_detail=.01), solver=wind.Solver(max_iterations=2), speed=5, direction=270)
    assert canonical.metadata["footprints"]["counts"]["solids"] == 2
    assert np.isfinite(canonical.velocity).all()
    assert canonical.solid_mask[3,12,12] and canonical.solid_mask[9,12,12]
    assert canonical.solid_mask[3,6,6] and not canonical.solid_mask[9,6,6]
    small=dict(bounds=(0,0,0,24,24,32))
    legacy=wind.run(City(), **small, solver=wind.Solver(precision='float64', max_iterations=2), speed=5, direction=270)
    assert legacy.solver["record"] is None and legacy.velocity.dtype==np.float32
    for method in ['height','wall_distance']:
        r=wind.run(City(), turbulence=wind.Turbulence(method), solver=wind.Solver(max_iterations=2), **small, speed=5, direction=45)
        assert r.turbulence is not None and r.turbulence.stress.flags.owndata
    try:wind.run(City(), **small, solver=wind.Solver(max_solve_seconds=1e-12, monitor=wind.MonitorSpec((0,24,0,24))), speed=5, direction=270)
    except wind.BudgetExhaustedError as e:assert e.record['iterations']==0
    else:raise AssertionError('Expected zero-work budget exhaustion')
    print(json.dumps(dict(passed=True,package=str(root),module=str(_qes.__file__),policy_revision=_qes.solver_policy_revision,
        adaptive_accepted=result.solver["record"]['accepted'],actual_threads=result.solver["record"]['actual_threads'],checks=['owned_output','sampling','adaptive_vs_legacy_status','derived_qualification','nested_timings','history_bounds','float64','two_turbulence_methods','zero_work_error','canonical_footprints_with_partition_hole'])))


if __name__=='__main__':main()

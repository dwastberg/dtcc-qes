"""Urban morphology, frozen geometry, strict sampling and comparison semantics."""
import importlib.util
import argparse
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
try:
    import urban_wind_cases as cases
    import benchmark_urban_wind as benchmark
finally:
    sys.path.pop(0)


@pytest.mark.parametrize('name',cases.NAMES)
def test_neighbourhoods_are_repeatable_disjoint_and_have_open_receptors(name,tmp_path):
    case=cases.make_case(name)
    assert case==cases.make_case(name)
    assert len(case['buildings'])>=40 and len({b['height'] for b in case['buildings']})>=5
    polygons=[Polygon(b['vertices']) for b in case['buildings']]
    for i,p in enumerate(polygons):
        assert p.is_valid and p.area>0
        assert all(p.distance(q)>0 for q in polygons[i+1:])
    occupied=unary_union(polygons)
    assert all(occupied.distance(Point(p))>=3 for p in case['receptors'])
    path=tmp_path/'case.json';cases.write_case(case,path)
    assert path.with_suffix('.svg').exists()
    assert json.loads(path.read_text())==case


def test_probe_instrumentation_preserves_all_existing_statements(tmp_path):
    runner=tmp_path/'src/qes_core/dtcc/wind_runner.cpp';runner.parent.mkdir(parents=True)
    binding=tmp_path/'src/cpp/bindings.cpp';binding.parent.mkdir(parents=True)
    runner.write_text('original numerical statements\n');binding.write_text('module {\n  m.doc() = "old";\n}\n')
    old=runner.read_text();benchmark.instrument_team_probe(tmp_path)
    assert runner.read_text().startswith(old)
    assert '  m.doc() = "old";' in binding.read_text()
    with pytest.raises(ValueError,match='already instrumented'): benchmark.instrument_team_probe(tmp_path)


def test_frozen_operand_faces_have_matching_requested_bounds():
    from dtcc_qes import wind
    spec=cases.make_case('mixed_downtown')
    auto=wind.preview_grid(cases.city(spec),bounds=tuple(spec['bounds']),resolution=8,
        vertical_grid=wind.VerticalGrid.auto(min_layer_thickness=.2,max_aspect_ratio=40),max_cells=40_000_000)
    spec.update(solver_dz=auto.solver_dz.tolist(),resolution=8,max_cells=40_000_000)
    spec['bounds'][5]=float(np.sum(auto.solver_dz.astype(float)))
    explicit=wind.preview_grid(cases.city(spec),**benchmark.frozen_options(spec,wind))
    for name in ('x','y','z','z_faces','solver_dz'):
        np.testing.assert_array_equal(getattr(auto,name),getattr(explicit,name))


def test_comparison_reports_support_changes_and_never_claims_reference_accuracy(tmp_path,capsys):
    rows=[]
    for i,variant in enumerate(('baseline','disabled','bounded')):
        request=dict(id=str(i),case='urban',direction=270,repeat=0,variant=variant,speed=5)
        rows.append(dict(status='completed',request=request,grid_sha256={'x':'same'},shape=[2,2,2],
            diagnostics={'iterations':2 if variant=='bounded' else 8},timing={'api_seconds':1},field_sha256={'v':variant}))
        data={}
        for n in (0,1):
            data[f'velocity{n}']=np.full((2,2,3),i,dtype=float)
            data[f'valid{n}']=np.ones((2,2),bool)
            if variant=='bounded': data[f'valid{n}'][0,0]=False
        np.savez(tmp_path/f'{i}.npz',**data)
    benchmark.write(tmp_path/'summary.json',{'results':rows})
    benchmark.analyze(tmp_path)
    result=json.loads((tmp_path/'comparisons.json').read_text())
    assert all(r['reference_qualification']=='not_assessed' for r in result['comparisons'])
    bounded=result['comparisons'][1]
    assert not bounded['same_completed_work'] and bounded['planes'][0]['validity_changes']==1
    assert bounded['planes'][0]['common_valid']==3
    report=capsys.readouterr().out
    assert '3/3 workers completed' in report
    assert 'Same work' in report and '0/1' in report
    assert 'p95 dU/Uref' in report and 'Mask changes' in report
    assert 'accuracy is not assessed' in report


def test_aggregate_prints_real_archived_results_without_changing_them(tmp_path,capsys):
    runs=[ROOT/f'docs/data/urban-wind-benchmarks/smoke-run-0{i}' for i in (0,1)]
    before={p:benchmark.digest(p) for folder in runs for p in folder.iterdir() if p.is_file()}
    output=tmp_path/'aggregate.json'
    benchmark.aggregate(SimpleNamespace(runs=runs,output=output))
    report=capsys.readouterr().out
    assert '12/12 workers completed' in report
    assert all(name in report for name in cases.NAMES)
    assert all(column in report for column in ('API s','Pipeline s','RSS MiB','Sweeps','Stops','API/base'))
    assert 'iteration_limit' in report and 'Equal fields' in report
    assert str(output) in report
    result=json.loads(output.read_text())
    assert result['rows']==12 and len(result['medians'])==12
    assert all(benchmark.digest(p)==sha for p,sha in before.items())


def test_failed_shard_prints_failures_without_suggesting_success(tmp_path,capsys):
    results=[dict(status=status,request=dict(id=str(i),case='urban',direction=270,repeat=0,variant=variant))
             for i,(status,variant) in enumerate((('timeout','baseline'),('failed','disabled'),
                                                ('budget_exhausted_zero_work','bounded')))]
    benchmark.write(tmp_path/'summary.json',dict(results=results,elapsed_seconds=60.))
    benchmark.analyze(tmp_path)
    report=capsys.readouterr().out
    assert '0/3 workers completed; shard elapsed 60.00 s' in report
    assert 'timeout=1' in report and 'failed=1' in report and 'budget_exhausted_zero_work=1' in report
    assert 'API/base' not in report and 'Equal fields' not in report
    assert json.loads((tmp_path/'comparisons.json').read_text())['comparisons']==[]


@pytest.mark.parametrize('value',['0','-1','nan','inf'])
def test_invalid_solve_budgets_are_rejected(value):
    with pytest.raises(argparse.ArgumentTypeError): benchmark.positive_seconds(value)


@pytest.mark.parametrize('value',['0','-1'])
def test_nonpositive_iteration_caps_are_rejected(value):
    with pytest.raises(argparse.ArgumentTypeError): benchmark.positive_iterations(value)

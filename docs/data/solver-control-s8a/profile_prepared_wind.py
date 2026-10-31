"""Isolated diagnostic build for S8a preparation subphases and allocation counts.

Production sources and arithmetic are unchanged. This diagnostic build has a
different source identity and is used ONLY for legacy phase/memory attribution.
It never assesses adaptive acceptance or contributes end-to-end speed claims.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

from benchmark_prepared_wind import write
from compare_native_builds import stage_package
from profile_solver_baseline import inventory, replace_once

ROOT=Path(__file__).resolve().parents[1]
PARENT='9fea55965c617631378047467ec9c449f2cfa978a2d59756a1062b8e19e9360c'


def instrument(tree):
    def edit(name, changes):
        p=tree/name
        value=p.read_text()
        for old,new in changes: value=replace_once(value,old,new)
        p.write_text(value)
    edit('src/qes_core/winds/WINDSGeneralData.cpp', [
        ('  wall->defineWalls(this);','  solver_profile::mark("boundary_coefficients");\n  wall->defineWalls(this);'),
        ('  wall->solverCoefficients(this);','  wall->solverCoefficients(this);\n  solver_profile::mark("idle");')])
    arrays=inventory((tree/'src/qes_core/winds/WINDSGeneralData.h').read_text(),'wind','prepared->data->')
    edit('src/qes_core/dtcc/wind_runner.cpp',[
        ('    poisson = std::make_unique<solver::PoissonOperator>(*data,solver::CoefficientOwnership::Take);',
         '    solver_profile::mark("operator_compression");\n'
         '    poisson = std::make_unique<solver::PoissonOperator>(*data,solver::CoefficientOwnership::Take);\n'
         '    solver_profile::mark("idle");\n'
         '    solver_profile::passes["operator_objects"] += 1;\n'
         '    solver_profile::bytes["operator"] = poisson->storage_bytes();'),
        ('  impl_.swap(prepared);',arrays+'\n  solver_profile::passes["prepared_objects"] += 1;\n'
         '  solver_profile::resident("prepared");\n  impl_.swap(prepared);'),
        ('      state.phase = Impl::Phase::Solving;',
         '      solver_profile::bytes["workspace"] = workspace.workspace_bytes();\n      state.phase = Impl::Phase::Solving;'),
        ('      state.solver = std::make_unique<solver::SolverState<float>>(*state.poisson,tolerance,solver::default_order(),relaxation);',
         '    {\n      solver_profile::passes["float_workspace_objects"] += 1;\n'
         '      state.solver = std::make_unique<solver::SolverState<float>>(*state.poisson,tolerance,solver::default_order(),relaxation);\n    }'),
        ('  return result;','  solver_profile::resident("native_output");\n  return result;')])
    hook='''  m.def("_s8a_profile", [] {
    nb::dict result, seconds, bytes, capacities, objects, rss;
    for (const auto &v : solver_profile::seconds) seconds[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::bytes) bytes[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::capacity_bytes) capacities[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::passes) objects[v.first.c_str()] = v.second;
    for (const auto &v : solver_profile::rss) rss[v.first.c_str()] = v.second;
    result["seconds"] = seconds; result["array_bytes"] = bytes;
    result["array_capacity_bytes"] = capacities; result["object_allocations"] = objects;
    result["peak_rss_bytes_at_phase"] = rss;
    return result;
  });
  m.def("_core_grid_shape"'''
    edit('src/cpp/bindings.cpp',[('  m.def("_core_grid_shape"',hook)])
    shutil.copyfile(ROOT/'tools/solver_profile_hooks.h',tree/'tools/solver_profile_hooks.h')
    with (tree/'CMakeLists.txt').open('a') as f:
        f.write('\ntarget_compile_options(qesbuild INTERFACE -include "${CMAKE_CURRENT_SOURCE_DIR}/tools/solver_profile_hooks.h")\n'
                'target_compile_options(_qes PRIVATE -include "${CMAKE_CURRENT_SOURCE_DIR}/tools/solver_profile_hooks.h")\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    write(out/'protocol.json',dict(parent_source_sha256=PARENT,workers=4,timeout_seconds=30,
        scope='Legacy only, 4/8 fresh and reused directions; independently instrumented build for subphase timing and object/array allocation attribution, not primary speed evidence.',
        phases='Boundary classification and stencil coefficients; immutable operator compression/transfer. These two subphases are included in native preparation, not added to it.',
        allocation='Count constructed prepared models, operators, float workspaces; inspect owned flat numeric vectors and operator/workspace bytes. Not malloc event accounting. Python allocation measured separately using tracemalloc.'))
    parent=ROOT/'docs/data/solver-control-s7/release-sources.tar.gz'
    if hashlib.sha256(parent.read_bytes()).hexdigest()!=PARENT: raise ValueError('Changed S7 parent')
    tree=out/'tree';tree.mkdir()
    with tarfile.open(parent) as a:a.extractall(tree,filter='data')
    # Match the live Python wrapper used for the primary pilot. Record changes.
    changes={}
    for rel in ['src/dtcc_qes/wind.py','src/dtcc_qes/result.py','src/dtcc_qes/solver_control.py']:
        before=(tree/rel).read_bytes();after=(ROOT/rel).read_bytes()
        if before!=after:changes[rel]=dict(before=hashlib.sha256(before).hexdigest(),after=hashlib.sha256(after).hexdigest())
        (tree/rel).write_bytes(after)
    write(out/'python-overlay.json',changes)
    instrument(tree)
    index={p.relative_to(tree).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in tree.rglob('*') if p.is_file()}
    write(out/'source-index.json',index)
    with tarfile.open(out/'instrumented-sources.tar.gz','w:gz') as a:
        for rel in sorted(index):a.add(tree/rel,arcname=rel,recursive=False)
    for label,cmd in [('configure',['cmake','-S',str(tree),'-B',str(out/'native'),'-DCMAKE_BUILD_TYPE=Release',f'-DPython_EXECUTABLE={sys.executable}','-DDTCC_QES_OPENMP=ON']),
                      ('build',['cmake','--build',str(out/'native'),'--target','_qes','-j8'])]:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
        (out/f'{label}.log').write_text(r.stdout+r.stderr);r.check_returncode()
    stage_package(tree,next((out/'native').glob('_qes*.so')),out/'package')
    for count in [4,8]:
        for kind in ['fresh','prototype']:
            path=out/f'legacy-{count}-{kind}.json'
            r=subprocess.run([sys.executable,str(ROOT/'tools/benchmark_prepared_wind.py'),'--worker','--kind',kind,'--count',str(count),'--output',str(path)],
                capture_output=True,text=True,timeout=30,env=os.environ|{'PYTHONPATH':str(out/'package'),'OMP_NUM_THREADS':'4','OMP_DYNAMIC':'FALSE'})
            path.with_suffix('.log').write_text(r.stdout+r.stderr);r.check_returncode()
    shutil.copyfile(out/'native/CMakeCache.txt',out/'CMakeCache.txt')
    shutil.copyfile(out/'native/solver-policy-identity.txt',out/'solver-policy-identity.txt')


if __name__=='__main__':main()

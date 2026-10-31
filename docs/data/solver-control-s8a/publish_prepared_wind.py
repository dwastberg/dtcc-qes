"""Publish finite S8a measurement evidence without copying build trees/binaries."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

from audit_prepared_wind import summarize, audit, sha
from benchmark_prepared_wind import write
from profile_prepared_wind import PARENT

ROOT=Path(__file__).resolve().parents[1]
TOOLS=['benchmark_prepared_wind.py','profile_prepared_wind.py','audit_prepared_wind.py','reproduce_prepared_wind.py','publish_prepared_wind.py']


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--study',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();study=args.study.resolve();out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    if list(out.iterdir()):raise ValueError('Refusing to replace existing evidence')
    for source,destination in [('pilot-study','primary'),('profile','profile'),('memory','memory')]:
        for path in (study/source).iterdir():
            if path.is_file() and path.suffix in ('.json','.log','.txt','.gz'):
                target=out/destination/path.name;target.parent.mkdir(exist_ok=True)
                shutil.copyfile(path,target)
    # Keep the original clock-comparison failure visible; canonical decision is
    # independently rederived from the raw workers with only elapsed stamps excluded.
    write(out/'summary.json',summarize(out/'primary'))
    write(out/'protocol-addendum.json',dict(
        decision_gate_unchanged=True,additional_workers=dict(profile=4,memory=8),
        correction='Initial summary mistakenly compared adaptive checkpoint elapsed_seconds. Raw workers unchanged; recursive exclusion of only elapsed_seconds restores exact fields/diagnostics/control parity. Original summary retained at primary/summary.json. No numerical or threshold changes.',
        instrumentation='Separate legacy-only source build; constructor, operator and float workspace object counts, owned flat numeric vector bytes/capacities and phase RSS. Not complete malloc-event accounting.',
        memory='Separate untimed tracemalloc workers. Primary timing workers have tracing disabled. Native high-water RSS includes imports, transient setup and output copies.',
        output='One uncompressed full-field NPZ with fsync per condition, streamed and removed. Primary end-to-end timings include fingerprint calculation for the audit.',
        scope='Single affordable 20-building neighbourhood, four/eight fixed directions, current local machine. Reuse parity is not new physical or numerical policy qualification.',
        production_changes='None. Public reuse API deferred by predeclared measured gate. S8b/S9 remain separate.'))
    tree=study/'published-tree';tree.mkdir(exist_ok=False)
    parent=ROOT/'docs/data/solver-control-s7/release-sources.tar.gz'
    if sha(parent)!=PARENT:raise ValueError('Changed S7 source archive')
    with tarfile.open(parent) as a:a.extractall(tree,filter='data')
    overlays={}
    for rel in ['src/dtcc_qes/wind.py','src/dtcc_qes/result.py','src/dtcc_qes/solver_control.py']:
        original=(tree/rel).read_bytes();current=(ROOT/rel).read_bytes()
        if original!=current:overlays[rel]=dict(before=hashlib.sha256(original).hexdigest(),after=hashlib.sha256(current).hexdigest(),scope='Usage docstrings only; carried forward from end of S7')
        (tree/rel).write_bytes(current)
    write(out/'source-parent.json',dict(s7_release_source_sha256=PARENT,python_overlays=overlays))
    for name in TOOLS:
        shutil.copyfile(ROOT/'tools'/name,tree/'tools'/name)
        shutil.copyfile(ROOT/'tools'/name,out/name)
    for name in ['compare_native_builds.py','profile_solver_baseline.py']:
        shutil.copyfile(tree/'tools'/name,out/name)
    shutil.copyfile(ROOT/'tests/test_prepared_wind_study.py',tree/'tests/test_prepared_wind_study.py')
    index={p.relative_to(tree).as_posix():sha(p) for p in tree.rglob('*') if p.is_file()}
    with tarfile.open(out/'sources.tar.gz','w:gz') as a:
        for name in sorted(index):a.add(tree/name,arcname=name,recursive=False)
    profile_index=json.loads((out/'profile/source-index.json').read_text())
    files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    write(out/'manifest.json',dict(stage='S8a',files=files,sources={'sources.tar.gz':index,'profile/instrumented-sources.tar.gz':profile_index}))
    print(json.dumps(audit(out),indent=2))


if __name__=='__main__':main()

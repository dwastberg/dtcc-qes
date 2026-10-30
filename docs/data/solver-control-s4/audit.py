"""Verify S4 evidence and source identity locally or inside a built sdist."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--sdist',type=Path)
args=parser.parse_args()
outer=None
if args.sdist:
    outer=tarfile.open(args.sdist)
    members={m.name.split('/',1)[1]:m for m in outer.getmembers() if m.isfile() and '/' in m.name}
    def read(name): return outer.extractfile(members['docs/data/solver-control-s4/'+name]).read()
else:
    root=Path(__file__).resolve().parent
    def read(name): return (root/name).read_bytes()
manifest=json.loads(read('manifest.json'))
for name,sha in manifest['files'].items():
    assert hashlib.sha256(read(name)).hexdigest()==sha,name
source=read('sources.tar.gz')
assert 'sha256:'+hashlib.sha256(source).hexdigest()==manifest['source_id']
with tarfile.open(fileobj=io.BytesIO(source)) as archive:
    for name,sha in manifest['sources'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest()==sha,name
        if outer:
            assert hashlib.sha256(outer.extractfile(members[name]).read()).hexdigest()==sha,('sdist source',name)
parity=json.loads(gzip.decompress(read('parity.json.gz')))
assert parity['passed'] and not parity['ordering_migration']
assert parity['candidate']==manifest['source_id'] and parity['baseline_revision']==manifest['baseline_source_id']
assert len(parity['comparisons'])==12 and all(not r['differences'] for r in parity['comparisons'])
assert all(r['cases']==429 for r in parity['comparisons'] if r['kind']=='revision')
print(json.dumps(dict(passed=True,evidence_files=len(manifest['files']),source_id=manifest['source_id'])))
if outer: outer.close()

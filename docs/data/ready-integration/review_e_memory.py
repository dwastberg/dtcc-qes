"""One directed repeat of each of the two flagged E conditions, after A/B review."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

WORK = Path(__file__).resolve().parent
FULL = WORK / 'full-comparison'
report = json.loads((FULL / 'report.json').read_text())
manifest = json.loads((FULL / 'manifest.json').read_text())
assert report['regression_passed']
assert json.loads((WORK / 'post-full-checks-status.json').read_text())['stage'] == 'memory_review_complete_pending_assessment'
flagged = [p for p in report['pairs'] if p['case'] == 'E' and p['rss']['candidate'] > 1.10*p['rss']['main']]
assert len(flagged) == 2, 'Reassess the directed protocol if the complete flag set differs'
folder = WORK / 'memory-review-e'
folder.mkdir(exist_ok=False)
protocol = dict(workers=4, conditions=flagged,
                purpose='Repeat the two >10% E RSS outliers with phase ownership/allocator observations',
                source_driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                worker_driver_sha256=hashlib.sha256((WORK / 'memory_review.py').read_bytes()).hexdigest())
(folder / 'protocol.json').write_text(json.dumps(protocol, indent=2) + '\n')
rows = []
for number, pair in enumerate(flagged):
    spec = next(j['spec'] for j in manifest['jobs'] if j['key'] == pair['key'])
    # Reverse the original candidate/main order for the first repeat; retain
    # both orders across the two conditions.
    for arm in (('main', 'candidate') if number == 0 else ('candidate', 'main')):
        job = dict(id=f"E-{spec['label']}-{arm}", case='E', arm=arm, spec=spec, key=pair['key'])
        source = manifest['arms'][arm]
        env = dict(os.environ, PYTHONPATH=f"{source['package']}:{source['source']}/validation",
                   OMP_NUM_THREADS='4', OMP_DYNAMIC='FALSE', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
        output = folder / (job['id'] + '.json')
        (folder / (job['id'] + '-before-vm-stat.txt')).write_text(subprocess.check_output(['vm_stat'], text=True))
        with (folder / (job['id'] + '.log')).open('x') as log:
            subprocess.run([sys.executable, str(WORK / 'memory_review.py'), '--worker', json.dumps(job), '--output', str(output)],
                           env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180, check=True)
        (folder / (job['id'] + '-after-vm-stat.txt')).write_text(subprocess.check_output(['vm_stat'], text=True))
        rows.append(json.loads(output.read_text()))
        print(job['id'], rows[-1]['peak_rss_bytes'], flush=True)
comparisons = []
for pair in flagged:
    selected = {r['job']['arm']: r for r in rows if r['job']['key'] == pair['key']}
    main, candidate = selected['main'], selected['candidate']
    comparisons.append(dict(key=pair['key'], original_rss=pair['rss'],
        repeated_rss={arm:r['peak_rss_bytes'] for arm,r in selected.items()},
        fields_identical=main['field_hashes'] == candidate['field_hashes'],
        returned_bytes_identical=main['field_bytes'] == candidate['field_bytes']))
assert all(row['fields_identical'] and row['returned_bytes_identical'] for row in comparisons)
(folder / 'report.json').write_text(json.dumps(dict(workers=4, comparisons=comparisons,
    status='complete_pending_assessment'), indent=2) + '\n')

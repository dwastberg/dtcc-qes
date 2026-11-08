"""Exact feature-intersection check with independently measured layout migration."""
from copy import deepcopy
import json
from pathlib import Path
import numpy as np

WORK = Path(__file__).resolve().parent


def compare(main, candidate, layout, identities):
    errors = []
    for key in ('lock_sha256', 'backend', 'omp_num_threads', 'compiler'):
        if main[key] != candidate[key]: errors.append(key)
    if [main['policy_revision'], candidate['policy_revision']] != identities:
        errors.append('policy identity')
    a, b = deepcopy(main['cases']), candidate['cases']
    for row in a.values():
        solver = row['metadata']['solver'];record = solver['record']
        if record is None: continue
        for monitor in (solver['spec']['monitor'], record['monitor']):
            assert 'turbulence' not in monitor
            monitor['turbulence'] = False
        if record['policy']:
            assert record['policy_revision'] == identities[0]
            record['policy_revision'] = identities[1]
        monitor = record['monitor']
        delta = layout['candidate']['monitor'] - layout['main']['monitor']
        delta += (layout['candidate']['receptor_record'] - layout['main']['receptor_record']) * len(monitor['receptors']) * monitor['history_limit']
        record['monitor_bytes'] += delta
    errors += [f'metadata/{name}' for name in set(a) | set(b) if a.get(name) != b.get(name)]
    return errors


if __name__ == '__main__':
    roots = [WORK / ('combined-' + arm) for arm in ('main', 'candidate')]
    a, b = [json.loads((p / 'manifest.json').read_text()) for p in roots]
    q = json.loads((WORK / 'qualification-source.json').read_text())
    layout = json.loads((WORK / 'monitor-layout.json').read_text())
    differences = compare(a, b, layout, [q['old'], q['new']])
    arrays = 0
    for name in a['cases']:
        with np.load(roots[0] / (name + '.npz')) as x, np.load(roots[1] / (name + '.npz')) as y:
            if set(x.files) != set(y.files): differences.append(name + '/array_keys')
            for key in set(x.files) & set(y.files):
                arrays += 1
                if x[key].dtype != y[key].dtype or x[key].shape != y[key].shape or x[key].tobytes() != y[key].tobytes():
                    differences.append(name + '/' + key)
    # Corruption controls must remain rejected by these precise migrations.
    corrupted = deepcopy(b)
    corrupted['cases']['adaptive']['metadata']['solver']['record']['accepted'] = not corrupted['cases']['adaptive']['metadata']['solver']['record']['accepted']
    assert compare(a, corrupted, layout, [q['old'], q['new']])
    corrupted = deepcopy(b)
    corrupted['cases']['adaptive']['metadata']['solver']['record']['monitor']['turbulence'] = True
    assert compare(a, corrupted, layout, [q['old'], q['new']])
    corrupted = deepcopy(b)
    corrupted['cases']['adaptive']['metadata']['solver']['record']['monitor_bytes'] += 1
    assert compare(a, corrupted, layout, [q['old'], q['new']])
    report = dict(passed=not differences, cases=len(a['cases']), arrays=arrays, differences=differences,
        layout=layout, identity_pair=[q['old'], q['new']], corruption_controls_passed=True,
        declared_additions=['monitor turbulence=False', '160 inline bytes per allocated receptor record'])
    (WORK / 'combined-comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    assert report['passed']

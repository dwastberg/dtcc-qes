"""Replay the guarded floor rule on the accuracy archive and the E1 stop-rule study."""
import argparse
import json
from pathlib import Path

from validation.aij import stop_rule


def candidate(history):
    return dict(history, stagnation_checks=8, stagnation_floor_factor=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('docs/data/precision-stagnation'))
    parser.add_argument('--runs', type=Path, default=Path('validation/output/runs'))
    parser.add_argument('--accuracy', type=Path, default=Path('validation/output/accuracy'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    seen = {}
    for path in args.accuracy.glob('runs*/*/*.json'):
        row = json.loads(path.read_text())
        history = row.get('stop_estimate')
        if history and history['rule'] == 'velocity' and not history['history_truncated']:
            seen[(path.parents[1].name, row['name'])] = row['spec'], history
    changes = []
    for (tag, name), (spec, history) in seen.items():
        old = stop_rule.replay(history, history['tolerance'])
        new = stop_rule.replay(candidate(history), history['tolerance'])
        assert (old[0] or history['iterations'][-1]) == history['iterations'][-1]
        if old != new:
            changes.append(dict(tag=tag, name=name, old=old, new=new, spec=spec))
    (args.output / 'replay.json').write_text(json.dumps(
        dict(histories=len(seen), changed=len(changes), changes=changes), indent=2) + '\n')

    rows, missing = [], []
    for base in stop_rule.bases():
        reference_spec = stop_rule.reference_run(base)
        omegas = stop_rule.OMEGAS + (stop_rule.HIGH_OMEGAS if base.resolution == 1 else ())
        specs = [stop_rule.study_run(base, omega) for omega in omegas]
        records = stop_rule.load(args.runs, [reference_spec, *specs])
        reference = records.get(reference_spec.key)
        if reference is None:
            missing.append(reference_spec.name)
            continue
        for spec in specs:
            run = records.get(spec.key)
            if run is None:
                missing.append(spec.name)
                continue
            old = stop_rule.analyse_run(run, reference)
            run['stop_estimate'] = candidate(run['stop_estimate'])
            new = stop_rule.analyse_run(run, reference)
            rows.append(dict(name=spec.name, old=old['stops'], new=new['stops']))
    passed = bool(rows) and not missing and all(
        value.get('g2', False) for row in rows for value in row['new'].values())
    (args.output / 'e1-replay.json').write_text(json.dumps(
        dict(runs=len(rows), missing=missing, passed=passed, rows=rows), indent=2, allow_nan=False) + '\n')
    print(f'Accuracy histories: {len(seen)}, changed: {len(changes)}; E1 runs: {len(rows)}, passed: {passed}')
    if not seen or not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

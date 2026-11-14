"""Compare archived AIJ runs without loading or recomputing a native result."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import numpy as np
from aij import campaigns, compare, metrics


def comparisons(archive, resolution):
    specs = campaigns.ab_baseline(resolution) + campaigns.baseline(resolution)
    records = compare.load_records(Path(archive) / 'runs', specs)
    result = {c.name: c for c in (compare.isolated(records, 'A') + compare.isolated(records, 'B')
                                  + compare.case_d(records) + compare.case_e_comparisons(records))}
    extra = compare.split_fibre_extras(records)
    if extra and 'k' in extra:
        result['D-k'] = replace(result['D-split_fibre'], name='D-k', quantity='k',
                               simulated=np.asarray(extra['k']['simulated'])[:, None],
                               measured=np.asarray(extra['k']['measured'])[:, None], options={'w': 0.})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--full', action='store_true')
    args = parser.parse_args()
    print('| Grid | Comparison | delta q | delta FAC2 | delta R | delta FB | share abs(delta K)>0.05 |')
    print('|---|---|---:|---:|---:|---:|---:|')
    for resolution in ((2., 1.) if args.full else (2.,)):
        old, new = comparisons(args.before, resolution), comparisons(args.after, resolution)
        for name, a in old.items():
            if name not in new:
                raise ValueError(f'Missing comparison {name}')
            b = new[name]
            if not np.array_equal(a.ids, b.ids) or a.labels != b.labels:
                raise ValueError(f'Probe alignment changed: {name}')
            sa, sb = a.scores(), b.scores()
            changes = [sb.get(k, np.nan)-sa.get(k, np.nan) for k in ('hit_rate','fac2','r','fb')]
            valid = np.isfinite(a.simulated) & np.isfinite(b.simulated)
            share = np.mean(np.abs(b.simulated[valid]-a.simulated[valid])>.05) if valid.any() else np.nan
            print(f'| {resolution:g} m | {name} | ' + ' | '.join(f'{x:+.5f}' for x in changes) + f' | {share:.5f} |')
            if changes[0]<-.02 or changes[2]<-.02:
                moved = np.argwhere(valid & (np.abs(b.simulated-a.simulated)>.05))
                print(f'\nAttribution required for {name}: probes/directions with changes >0.05: ' +
                      ', '.join(f'{a.ids[i]}/{a.labels[j]}' for i,j in moved) + '\n')


if __name__ == '__main__':
    main()

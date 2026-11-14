"""Magnitude changes on archived measurement-height planes (not whole volumes)."""
import argparse
from collections import defaultdict
import json
import numpy as np
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    args = parser.parse_args()
    groups = defaultdict(list)
    for path in sorted((args.before / 'runs').rglob('*.json')):
        other = args.after / path.relative_to(args.before)
        if not other.exists():
            raise ValueError(f'Missing matched run {other}')
        spec = json.loads(path.read_text())['spec']
        assert spec == json.loads(other.read_text())['spec']
        with np.load(path.with_suffix('.npz')) as a, np.load(other.with_suffix('.npz')) as b:
            for axis in ('x', 'y'):
                np.testing.assert_array_equal(a[axis], b[axis])
            keep = a['valid'] & b['valid']
            delta = np.linalg.norm(a['velocity'].astype(float) - b['velocity'], axis=-1)
            groups[(spec['resolution'], spec['case'])].append(delta[keep & np.isfinite(delta)])
    print('| Grid | Case | Valid pairs | max vector change (m/s) | p99 (m/s) | share >0.05 m/s |')
    print('|---|---|---:|---:|---:|---:|')
    for (resolution, case), parts in sorted(groups.items(), reverse=True):
        delta = np.concatenate(parts)
        print(f'| {resolution:g} m | {case} | {len(delta)} | {delta.max():.6f} | '
              f'{np.quantile(delta, .99):.6f} | {np.mean(delta > .05):.6f} |')


if __name__ == '__main__':
    main()

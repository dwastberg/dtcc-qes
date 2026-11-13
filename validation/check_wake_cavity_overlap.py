"""Join the frozen research E2 spurious-decrease stratum to the W4 windy tenth.

Usage: python validation/check_wake_cavity_overlap.py PATH_TO_E2_MANIFEST
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from aij import tables


def overlap(masks, measurement):
    if list(measurement.ids) != masks['probe_ids']:
        raise ValueError('E2 probe order differs from AIJ measurements')
    top = measurement.values >= np.nanpercentile(measurement.values, 90)
    pairs = {(int(measurement.ids[i]), label) for i, j in zip(*np.where(top))
             for label in [measurement.labels[j]]}
    frozen = {(int(p['probe_id']), p['label']) for p in masks['frozen_full_spurious_pairs']}
    return dict(windy_pairs=len(pairs), frozen_spurious_pairs=len(frozen),
                overlap_count=len(pairs & frozen), overlap_pairs=sorted(pairs & frozen))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    args = parser.parse_args()
    payload = args.manifest.read_bytes()
    masks = json.loads(payload)['configuration']['masks']
    result = overlap(masks, tables.load_results_e('after'))
    result['manifest_sha256'] = hashlib.sha256(payload).hexdigest()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

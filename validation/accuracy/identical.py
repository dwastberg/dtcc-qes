"""Bit-identity of two stored run sets: python identical.py TAG_A TAG_B  ('' is the released baseline).

Compares, for every run stored in both, the probe velocities of the record and the 2 m plane arrays.
"""
import json
import sys

import numpy as np

import common


def main(a, b):
    da, db = (common.OUT / (f"runs-{t}" if t else "runs") for t in (a, b))
    compared, different, worst = 0, [], 0.0
    for path in sorted(da.glob("*/*.json")):
        other = db / path.parent.name / path.name
        if not other.exists():
            continue
        compared += 1
        ra, rb = json.loads(path.read_text()), json.loads(other.read_text())
        va = np.array(ra["probes"]["velocity"], dtype=float)
        vb = np.array(rb["probes"]["velocity"], dtype=float)
        pa, pb = np.load(path.with_suffix(".npz")), np.load(other.with_suffix(".npz"))
        same = np.array_equal(va, vb, equal_nan=True) and all(
            np.array_equal(pa[k], pb[k], equal_nan=True) for k in ("velocity", "valid") if k in pa.files)
        if not same:
            different.append(ra["name"])
            worst = max(worst, float(np.nanmax(np.abs(va - vb))))
    print(f"{compared} runs compared; {len(different)} differ" + (f" (largest probe difference {worst:.3g} m/s)" if different else ""))
    for name in different[:10]:
        print("  ", name)
    return not different


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)

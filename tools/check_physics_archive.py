"""Recompute the archived canyon comparison without importing a campaign driver.

Run with validation dependencies and DTCC_QES_AIJ_DATA pointing to the reference
data directory. This reads records only; it never prepares or solves native wind.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validation"))
from aij import CASE_A_XLS, CASE_B_XLS, CASE_D_XLS, CASE_E_XLS, campaigns, compare, metrics
from rerun_regression import equal_values


def verify(root):
    reference = json.loads((root / "analysis-001/report.json").read_text())
    specs = campaigns.ab_baseline() + campaigns.baseline()
    records = {model: compare.load_records(root / model, specs)
               for model in ("legacy", "joined_v1")}
    comparisons = {}
    for model, rows in records.items():
        quantities = ([c for case in "AB" for c in compare.isolated(rows, case)]
                      + compare.case_d(rows) + compare.case_e_comparisons(rows))
        comparisons[model] = {c.name: c for c in quantities}
    checked = []
    for archived in reference["pooled"]:
        name = archived["name"]
        before, after = [comparisons[m][name] for m in ("legacy", "joined_v1")]
        if not equal_values(before.ids.tolist(), after.ids.tolist()):
            raise ValueError(f"Changed IDs: {name}")
        if not equal_values(before.measured.tolist(), after.measured.tolist()):
            raise ValueError(f"Changed measurements: {name}")
        actual = metrics.paired_scores(before.simulated, after.simulated,
                                      before.measured, before.options)
        actual["joined_count"] = actual.pop("candidate_count")
        actual["joined"] = actual.pop("candidate")
        expected = {k: v for k, v in archived.items() if k != "name"}
        if not equal_values(actual, expected):
            raise ValueError(f"Archived paired metrics/coverage differ: {name}")
        checked.append(name)
    if len(checked) != 15 or len(set(checked)) != 15:
        raise ValueError("Expected all 15 distinct quantities")
    paths = sorted(p for model in records for p in (root / model).rglob("*.json"))
    if len(paths) != 74:
        raise ValueError("Expected all 74 canonical records")
    return dict(passed=True, quantities=checked, native_solves=0,
                source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in [Path(__file__).resolve(), ROOT / "validation/rerun_regression.py",
                                         *sorted((ROOT / "validation/aij").glob("*.py"))]},
                data_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (CASE_A_XLS, CASE_B_XLS, CASE_D_XLS, CASE_E_XLS)},
                records={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in paths},
                reference_sha256=hashlib.sha256((root / "analysis-001/report.json").read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.archive.resolve())
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    print(f"Verified {len(result['quantities'])} quantities and 74 records; zero native solves")

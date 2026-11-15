"""Candidate against parent on the stored runs of two variants: python compare_variant.py CANDIDATE_TAG [PARENT_TAG] [cases]

Paired differences (candidate minus parent) with 95 % intervals, primary scalar quantity for thermistors,
the common vector gate quantities for A, B and the Case D split fibre. ``wake=3`` only.
"""
import sys

import numpy as np

import common
import data
import score

SECOND = "--second-grid" in sys.argv
if SECOND:
    sys.argv.remove("--second-grid")


def grid(case):
    return (common.SECOND_GRID if SECOND else common.GRID)[case]

THERMISTOR = (("D", None), ("E", "before"), ("E", "after"), ("C", "0H"), ("C", "1H"), ("C", "2H"))


def verdict(value, worse_is_positive=True, tolerance=0.0):
    v, low, high = value
    if not np.isfinite(low):
        return "n/a"
    if worse_is_positive:
        return "worse" if low > tolerance else "better" if high < 0 else "no resolved change"
    return "worse" if high < -tolerance else "better" if low > 0 else "no resolved change"


def thermistor(candidate, parent, cases):
    out = ["| Dataset | n | Hits gained / lost | Δq | ΔMAE [95 %] | ΔR [95 %] | Δ|bias| [95 %] | Largest |ΔK| at a probe | MAE reading |",
           "|---|---|---|---|---|---|---|---|---|"]
    for case, state in THERMISTOR:
        if case not in cases:
            continue
        c = data.load(case, state, 3, grid(case), getter=common.stored(candidate))
        p = data.load(case, state, 3, grid(case), getter=common.stored(parent))
        q = c.primary
        d = score.paired(c.sim[q], p.sim[q], c.measured, c.extras["groups"])
        gained, lost = score.hit_transitions(c.sim[q], p.sim[q], c.measured)
        out.append(f"| {case}{' ' + state if state else ''} | {d['hits'][1]} | +{gained} / −{lost} | {d['q'][0]:+.3f} | {score.fmt(d['MAE'], 4)} | "
                   f"{score.fmt(d['R'], 4)} | {score.fmt(d['abs_bias'], 4)} | {np.nanmax(np.abs(c.sim[q] - p.sim[q])):.3f} | {verdict(d['MAE'])} |")
    return out


def vector(candidate, parent, cases):
    out = ["| Dataset | Points | Magnitude hits gained / lost | Δ vector RMSE [95 %] | ΔMAE U | ΔMAE V | ΔMAE W | U sign errors parent → candidate | Reading |",
           "|---|---|---|---|---|---|---|---|---|"]
    for case in ("A", "B", "D"):
        if case not in cases:
            continue
        c = data.load(case, None, 3, grid(case), getter=common.stored(candidate))
        p = data.load(case, None, 3, grid(case), getter=common.stored(parent))
        measured = c.extras["measured_velocity"][:, 0, :]
        mask = np.isfinite(measured).any(-1)
        cv, pv = c.velocity[:, 0, :], p.velocity[:, 0, :]

        def function(rows, cols):
            keep = mask[rows]
            a = score.vector_stats(cv[rows][keep], measured[rows][keep])
            b = score.vector_stats(pv[rows][keep], measured[rows][keep])
            return {k: a[k] - b[k] for k in a}
        d = score.interval(function, c.extras["groups"], 1)
        magnitude = np.where(mask, np.sqrt(np.nansum(measured ** 2, -1)), np.nan)[:, None]
        gained, lost = score.hit_transitions(np.linalg.norm(cv, axis=1)[:, None], np.linalg.norm(pv, axis=1)[:, None], magnitude)
        sp, sc = score.sign_errors(pv[mask, 0], measured[mask, 0]), score.sign_errors(cv[mask, 0], measured[mask, 0])
        out.append(f"| {case} | {mask.sum()} | +{gained} / −{lost} | {score.fmt(d['vector_RMSE'], 4)} | {d['MAE_U'][0]:+.4f} | "
                   f"{d['MAE_V'][0]:+.4f} | {d['MAE_W'][0]:+.4f} | {sp['wrong']} → {sc['wrong']} of {sp['n']} | {verdict(d['vector_RMSE'], tolerance=0.02)} |")
    return out


if __name__ == "__main__":
    candidate = sys.argv[1]
    parent = sys.argv[2] if len(sys.argv) > 2 else ""
    cases = sys.argv[3] if len(sys.argv) > 3 else "ABCDE"
    print(f"Candidate `{candidate}` against parent `{parent or 'released build'}`, `wake=3`.\n")
    print("\n".join(vector(candidate, parent, cases)) + "\n")
    print("\n".join(thermistor(candidate, parent, cases)))

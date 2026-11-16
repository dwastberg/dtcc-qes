"""Replay the velocity stop rule, and candidate changes to it, on stored run histories (STOP_RULE_STALL_INVESTIGATION.md).

A rule that only adds a stop condition can only stop a run earlier, so a stored history up to the actual stop
is enough to show which runs it would change. The replay of the current rule must reproduce every stored stop.
Run from the repository root: python validation/replay_stop_rule.py
"""
import json, glob, collections, numpy as np
FIRST, PASSES, TOL_DEFAULT = 4, 2, 1e-3
def replay(e, floor_scale=1.0, stagnation=None):
    it = e["iterations"]; ch = np.array(e["change"], float); fl = np.array(e["floor"], float) * floor_scale
    est = np.array(e["estimate"], float); tol = e["tolerance"]
    p = fp = 0; best = np.inf; since = 0
    for n in range(len(it)):
        counted = n + 1 >= FIRST
        p = p + 1 if counted and est[n] <= tol else 0
        fp = fp + 1 if counted and ch[n] <= fl[n] else 0
        if p >= PASSES: return it[n], "velocity_estimate"
        if fp >= PASSES: return it[n], "precision_floor"
        if stagnation:
            factor, window = stagnation
            if ch[n] < best: best, since = ch[n], 0
            else: since += 1
            if counted and since >= window and ch[n] <= factor * fl[n]: return it[n], "stagnation"
    return it[-1], e["termination"]
seen = {}
for f in glob.glob('validation/output/accuracy/runs*/*/*.json'):
    r = json.load(open(f)); e = r.get("stop_estimate")
    if not e or e.get("rule") != "velocity" or e.get("history_truncated"): continue
    seen[(f.split('/')[3], r["name"])] = (r["spec"], e)
mismatch = sum(1 for spec, e in seen.values() if replay(e)[0] != e["iterations"][-1])
print(f"{len(seen)} stored runs; the replay of the current rule reproduces the stop sweep of {len(seen) - mismatch}\n")
rules = {"floor factor 9 (now 6)": dict(floor_scale=1.5), "floor factor 12": dict(floor_scale=2.0),
         "stagnation: no new minimum in 8 checks and change ≤ 2 × floor": dict(stagnation=(2.0, 8)),
         "stagnation: no new minimum in 8 checks and change ≤ 3 × floor": dict(stagnation=(3.0, 8)),
         "stagnation: no new minimum in 12 checks and change ≤ 2 × floor": dict(stagnation=(2.0, 12))}
print("| Rule | Case C 1 m wake=3 (87 runs): stop sweep median (max) | Still capped | Other runs stopped earlier than today | Largest change of stop sweep among them |")
print("|---|---|---|---|---|")
for name, kw in rules.items():
    c_stops, c_capped, earlier, worst = [], 0, 0, 0
    for (tag, run), (spec, e) in seen.items():
        w = dict(spec.get("parameterizations", {})).get("wake", 2)
        stop, term = replay(e, **kw)
        if spec["case"] == "C" and spec.get("resolution") == 1.0 and w == 3:
            c_stops.append(stop); c_capped += term == "iteration_limit"
        elif stop < e["iterations"][-1]:
            earlier += 1; worst = max(worst, e["iterations"][-1] - stop)
    print(f"| {name} | {np.median(c_stops):.0f} ({max(c_stops)}) | {c_capped} | {earlier} | {worst} sweeps |")

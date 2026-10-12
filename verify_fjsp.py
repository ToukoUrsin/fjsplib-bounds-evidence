#!/usr/bin/env python3
"""Standalone FJSP schedule checker (Python stdlib only).

Usage: python3 verify_fjsp.py INSTANCE.txt INSTANCE.json SCHEDULE.json [CLAIMED_MAKESPAN]

INSTANCE.txt  = ScheduleOpt flexible-jobshop/instances/fjsp/<family>/<name>.txt (Brandimarte format,
                machines 1-based); INSTANCE.json = flexible-jobshop/instances/json/<name>.json.
SCHEDULE.json = {"operations":[{"operation":i,"machine":m,"start":s,"end":e},...]} with global
                operation ids in job order and 0-based machines (as in the JSON instance).
Checks: every operation scheduled exactly once; machine eligible with the instance duration
(end-start == duration) in BOTH instance encodings; every job precedence (text chains and JSON
precedence list); no overlap on any machine; makespan = max end (== claimed if given).
"""
import json, sys

def parse_txt(path):
    tok = open(path).read().split()
    n_jobs, n_mach = int(tok[0]), int(tok[1]); p = 3
    modes, prec, op = [], [], 0
    for j in range(n_jobs):
        n_ops = int(tok[p]); p += 1
        for k in range(n_ops):
            m = int(tok[p]); p += 1
            d = {}
            for _ in range(m):
                d[int(tok[p]) - 1] = int(tok[p + 1]); p += 2
            modes.append(d)
            if k > 0: prec.append((op - 1, op))
            op += 1
    assert p == len(tok), "trailing tokens"
    return n_mach, modes, prec

def parse_json(path):
    d = json.load(open(path)); modes = {}
    for r in d["operations"]:
        modes.setdefault(r["operation"], {})[r["machine"]] = r["duration"]
    n = max(modes) + 1
    return [modes[i] for i in range(n)], [(r["before"], r["after"]) for r in d["precedences"]]

def main():
    txt, js, sol = sys.argv[1:4]
    claimed = int(sys.argv[4]) if len(sys.argv) > 4 else None
    n_mach, tm, tp = parse_txt(txt)
    jm, jp = parse_json(js)
    assert tm == jm, "text/json mode tables differ"
    assert sorted(tp) == sorted(jp), "text/json precedences differ"
    ops = json.load(open(sol))["operations"]
    by = {}
    for r in ops:
        i = r["operation"]; assert i not in by, f"duplicate op {i}"; by[i] = r
    assert sorted(by) == list(range(len(tm))), "missing/extra operations"
    for i, r in by.items():
        m, s, e = r["machine"], r["start"], r["end"]
        assert isinstance(s, int) and isinstance(e, int) and s >= 0, f"op {i} bad times"
        assert m in tm[i], f"op {i} machine {m} not eligible"
        assert e - s == tm[i][m], f"op {i} duration {e-s} != {tm[i][m]}"
    for a, b in tp:
        assert by[a]["end"] <= by[b]["start"], f"precedence {a}->{b} violated"
    per = {}
    for i, r in by.items(): per.setdefault(r["machine"], []).append((r["start"], r["end"], i))
    for m, L in per.items():
        L.sort()
        for x, y in zip(L, L[1:]):
            assert x[1] <= y[0], f"overlap on machine {m}: ops {x[2]},{y[2]}"
    cmax = max(r["end"] for r in ops)
    if claimed is not None: assert cmax == claimed, f"makespan {cmax} != claimed {claimed}"
    print(json.dumps({"valid": True, "makespan": cmax, "operations": len(ops), "precedences": len(tp),
                      "mode_rows": sum(len(x) for x in tm), "machines_used": len(per), "machines": n_mach}))

if __name__ == "__main__":
    main()

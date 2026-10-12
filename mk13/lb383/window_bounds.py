"""Necessary resource-window inequalities, integer arithmetic witness export.

For operations forced onto machine set S, minimum durations and job-derived
heads/tails imply a minimum processing overlap in [a,b). Sum <= |S|*(b-a).
This is a relaxation only: absence of a violated inequality is inconclusive.
"""
import argparse
import collections
import json
from pathlib import Path

import numpy as np

from check_schedule import read_text


def prepare(path):
    options, arcs, nm = read_text(path)
    n = len(options)
    durations = [min(x.values()) for x in options]
    pred, succ = collections.defaultdict(list), collections.defaultdict(list)
    for a,b in arcs: pred[b].append(a); succ[a].append(b)
    order, left = [], {i:len(pred[i]) for i in range(n)}
    ready = [i for i in range(n) if not left[i]]
    while ready:
        op = ready.pop(); order.append(op)
        for nxt in succ[op]:
            left[nxt] -= 1
            if not left[nxt]: ready.append(nxt)
    assert len(order)==n
    head, tail = [0]*n, [0]*n
    for op in order: head[op] = max((head[p]+durations[p] for p in pred[op]),default=0)
    for op in reversed(order): tail[op] = max((tail[s]+durations[s] for s in succ[op]),default=0)
    sets = {frozenset(x) for x in options}
    sets.add(frozenset(range(nm)))
    groups = []
    for machines in sorted(sets,key=lambda s:(len(s),sorted(s))):
        forced = [i for i,x in enumerate(options) if set(x)<=machines]
        if len(forced)>len(machines): groups.append((machines,forced))
    return options, durations, head, tail, groups


def screen(path,T):
    options,durations,head,tail,groups=prepare(path)
    for op,d in enumerate(durations):
        if head[op]+d+tail[op]>T:
            return {'kind':'critical_path','operation':op,'head':head[op],'duration':d,'tail':tail[op],'target':T}
    tightest=None
    for machines,forced in groups:
        h=np.array([head[i] for i in forced],dtype=np.int64)
        d=np.array([durations[i] for i in forced],dtype=np.int64)
        latest_end=np.array([T-tail[i] for i in forced],dtype=np.int64)
        # Full breakpoint endpoints for individual overlap functions.
        endpoints=sorted({0,T}|set(h.tolist())|set((h+d).tolist())|set(latest_end.tolist())|set((latest_end-d).tolist()))
        ends=np.array(endpoints,dtype=np.int64)
        for a in endpoints[:-1]:
            bs=ends[ends>a]
            overlap=np.maximum(0,np.minimum(np.minimum(d[:,None],bs[None,:]-a),np.minimum(h[:,None]+d[:,None]-a,bs[None,:]-(latest_end-d)[:,None])))
            energy=overlap.sum(axis=0)
            violation=energy-len(machines)*(bs-a)
            index=int(np.argmax(violation)); v=int(violation[index]); b=int(bs[index])
            if tightest is None or v>tightest['violation']:
                tightest={'kind':'resource_window','target':T,'machines':sorted(machines),'a':a,'b':b,'energy':int(energy[index]),'capacity':len(machines)*(b-a),'violation':v,'operations':[{'operation':op,'head':head[op],'duration':durations[op],'latest_end':T-tail[op],'minimum_overlap':int(overlap[k,index])} for k,op in enumerate(forced) if overlap[k,index]>0]}
            if v>0:return tightest
    return tightest


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);a=ap.parse_args()
    records=json.loads(Path('results/20261006-baseline/live-records.json').read_text())
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    report=[]
    for row in records:
        name=row['instance'];T=row['upper_bound']-1
        result=screen(Path('instances')/(name+'.txt'),T)
        (out/(name+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        summary={'instance':name,'target':T,'proved_infeasible':result is not None and (result['kind']=='critical_path' or result['violation']>0),'tightest_violation':result.get('violation') if result else None}
        report.append(summary);print(json.dumps(summary),flush=True)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')

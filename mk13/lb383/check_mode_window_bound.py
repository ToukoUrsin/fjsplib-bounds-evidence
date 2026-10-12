"""Fresh integer regeneration and independent HiGHS MIP check of mode cuts.

This checks an executable lower-bound argument, not a formal SAT proof.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import highspy
import numpy as np
from scipy.sparse import coo_matrix
from mode_windows import rebuild,context
from check_schedule import read_text,check
from window_bounds import prepare
from ortools.sat.python import cp_model


def run(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    source=json.loads(Path(a.cuts).read_text());T=source['target'];cuts=source['cuts']
    unary_proof=source.get('unary_proof')
    options,arcs,nm,head,tail=context(a.instance,T,unary_proof)
    modes=[(i,m) for i,o in enumerate(options) for m in o];index={t:k for k,t in enumerate(modes)}
    rows=[];lo=[];up=[]
    for i,o in enumerate(options):rows.append({index[i,m]:1 for m in o});lo.append(1);up.append(1)
    for m in range(nm):rows.append({index[i,m]:o[m] for i,o in enumerate(options) if m in o});lo.append(-highspy.kHighsInf);up.append(T)
    for cut in cuts:
        m,left,right=cut['machine'],cut['a'],cut['b'];terms=[]
        for i,o in enumerate(options):
            if m not in o or head[i]+o[m]+tail[i]>T:continue
            dd=o[m];latest=T-tail[i]-dd
            c=min(max(0,min(s+dd,right)-max(s,left)) for s in (head[i],latest))
            if c:terms.append([i,c])
        assert terms==cut['coefficients']
        rows.append({index[i,m]:c for i,c in terms});lo.append(-highspy.kHighsInf);up.append(right-left)
    cl=np.zeros(len(modes));cu=np.ones(len(modes))
    for k,(i,m) in enumerate(modes):
        if head[i]+options[i][m]+tail[i]>T:cu[k]=0
    rr=[];cc=[];vv=[]
    for r,row in enumerate(rows):
        for c,v in row.items():rr.append(r);cc.append(c);vv.append(v)
    matrix=coo_matrix((vv,(rr,cc)),shape=(len(rows),len(modes))).tocsc()
    model=highspy.HighsLp();model.num_col_=len(modes);model.num_row_=len(rows)
    model.col_cost_=np.zeros(len(modes));model.col_lower_=cl;model.col_upper_=cu
    model.row_lower_=lo;model.row_upper_=up;model.integrality_=[highspy.HighsVarType.kInteger]*len(modes)
    model.a_matrix_.format_=highspy.MatrixFormat.kColwise;model.a_matrix_.start_=matrix.indptr;model.a_matrix_.index_=matrix.indices;model.a_matrix_.value_=matrix.data
    h=highspy.Highs();h.setOptionValue('threads',a.workers);h.setOptionValue('time_limit',a.seconds)
    h.setOptionValue('mip_rel_gap',0.);h.setOptionValue('mip_abs_gap',0.);h.setOptionValue('log_to_console',False)
    h.setOptionValue('log_file',str(out/'highs.log'));h.passModel(model);h.run();status=h.getModelStatus()
    r=dict(instance=Path(a.instance).stem,target=T,cuts=len(cuts),independent_highs_status=h.modelStatusToString(status),
           highs_seconds=h.getRunTime(),highs_version=h.version(),seconds_limit=a.seconds,workers=a.workers,
           input_sha256=hashlib.sha256(Path(a.instance).read_bytes()).hexdigest(),cuts_sha256=hashlib.sha256(Path(a.cuts).read_bytes()).hexdigest(),
           scope='Necessary integer assignment/energy model, regenerated from original input; solver certificate only, no formal proof')
    if a.cpsat:
        cp,_=rebuild(a.instance,T,cuts,unary_proof);s=cp_model.CpSolver();s.parameters.num_search_workers=a.workers
        s.parameters.max_time_in_seconds=a.seconds;s.parameters.random_seed=a.seed
        s.parameters.log_search_progress=True;s.parameters.log_to_stdout=False
        with (out/'cpsat.log').open('w') as f:
            s.log_callback=lambda line:(f.write(line+'\n'),f.flush());st=s.solve(cp)
        r.update(regenerated_cpsat_status=s.status_name(st),cpsat_seconds=s.wall_time)
    r['independently_reproduced_infeasible']=status==highspy.HighsModelStatus.kInfeasible
    if a.cpsat:r['two_solvers_infeasible']=r['independently_reproduced_infeasible'] and r['regenerated_cpsat_status']=='INFEASIBLE'
    # An altered energy coefficient must fail mathematical regeneration.
    if cuts:
        changed=copy.deepcopy(cuts);changed[0]['coefficients'][0][1]+=1
        try:rebuild(a.instance,T,changed,unary_proof)
        except AssertionError:r['changed_coefficient_negative_rejected']=True
        else:raise AssertionError('coefficient corruption accepted')
    (out/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('instance');p.add_argument('--cuts',required=True);p.add_argument('--out',required=True)
    p.add_argument('--seconds',type=float,default=300);p.add_argument('--workers',type=int,default=4);p.add_argument('--seed',type=int,default=301)
    p.add_argument('--cpsat',action='store_true');run(p.parse_args())

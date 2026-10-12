"""Independent JSON endpoint-mode prefix inequalities.

Choose the actual first/last modes jointly. A first-machine prefix whose tail
is at least Q has processing <=T-Q. A last-machine suffix whose minimum head
is at least H has processing <=T-H. Minimum middle-chain times are regenerated
from all original JSON modes; feasible schedules always satisfy these rows.
"""
import argparse,hashlib,itertools,json,pathlib,time
import highspy,numpy as np
from scipy.sparse import coo_matrix
from ortools.sat.python import cp_model

def original(path):
    data=json.loads(pathlib.Path(path).read_text());options={};succ={};incoming=set()
    for r in data['operations']:
        options.setdefault(r['operation'],{})[r['machine']]=r['duration']
    for r in data['precedences']:
        i,j=r['before'],r['after'];assert i not in succ and j not in incoming;succ[i]=j;incoming.add(j)
    jobs=[]
    for i in sorted(options):
        if i in incoming:continue
        c=[i]
        while c[-1] in succ:c.append(succ[c[-1]])
        jobs.append(c)
    assert sorted(i for c in jobs for i in c)==list(range(len(options)))
    return options,jobs

def necessary_rows(path,T):
    opts,jobs=original(path);choices=[];tails=[];heads=[]
    for j,c in enumerate(jobs):
        middle=sum(min(opts[i].values()) for i in c[1:-1])
        for m,p in opts[c[0]].items():
            for n,q in opts[c[-1]].items():
                choices.append((j,m,n,p,q));tails.append(middle+q);heads.append(p+middle)
    rows=[];rhs=[];metadata=[]
    for j in range(len(jobs)):
        rows.append({k:1 for k,x in enumerate(choices) if x[0]==j});rhs.append(1);metadata.append(('job',j))
    for m in sorted({x[1] for x in choices}):
        for Q in sorted({tails[k] for k,x in enumerate(choices) if x[1]==m}):
            rows.append({k:x[3] for k,x in enumerate(choices) if x[1]==m and tails[k]>=Q});rhs.append(T-Q);metadata.append(('first_tail',m,Q))
    for n in sorted({x[2] for x in choices}):
        for H in sorted({heads[k] for k,x in enumerate(choices) if x[2]==n}):
            rows.append({k:x[4] for k,x in enumerate(choices) if x[2]==n and heads[k]>=H});rhs.append(T-H);metadata.append(('last_head',n,H))
    return choices,rows,rhs,metadata,jobs

def cp_rows(choices,rows,rhs,njobs,seconds):
    model=cp_model.CpModel();x=[model.new_bool_var('mode'+str(k)) for k in range(len(choices))]
    for r,(row,b) in enumerate(zip(rows,rhs)):
        expr=sum(v*x[k] for k,v in row.items())
        if r<njobs:model.add(expr==b)
        else:model.add(expr<=b)
    s=cp_model.CpSolver();s.parameters.max_time_in_seconds=seconds;s.parameters.num_search_workers=4
    status=s.solve(model);return {'status':s.status_name(status),'seconds':s.wall_time}

def highs_rows(choices,rows,rhs,njobs,seconds,out,integral=True):
    rr=[];cc=[];vv=[]
    for r,row in enumerate(rows):
        for c,v in row.items():rr.append(r);cc.append(c);vv.append(v)
    matrix=coo_matrix((vv,(rr,cc)),shape=(len(rows),len(choices))).tocsc();lp=highspy.HighsLp();lp.num_col_=len(choices);lp.num_row_=len(rows)
    lp.col_cost_=np.zeros(len(choices));lp.col_lower_=np.zeros(len(choices));lp.col_upper_=np.ones(len(choices));lp.row_lower_=np.r_[np.ones(njobs),np.full(len(rows)-njobs,-highspy.kHighsInf)];lp.row_upper_=rhs
    if integral:lp.integrality_=[highspy.HighsVarType.kInteger]*len(choices)
    lp.a_matrix_.format_=highspy.MatrixFormat.kColwise;lp.a_matrix_.start_=matrix.indptr;lp.a_matrix_.index_=matrix.indices;lp.a_matrix_.value_=matrix.data
    h=highspy.Highs();h.setOptionValue('threads',4);h.setOptionValue('time_limit',seconds);h.setOptionValue('mip_rel_gap',0.0);h.setOptionValue('log_to_console',False);h.setOptionValue('log_file',str(out));h.passModel(lp);h.run()
    return {'status':h.modelStatusToString(h.getModelStatus()),'seconds':h.getRunTime(),'version':h.version(),'columns':len(choices),'rows':len(rows),'nonzeros':matrix.nnz}

def donor_rows(choices,rows,rhs,njobs,donor):
    by={r['operation']:r for r in donor['operations']};selected=[]
    # Caller supplies actual original job endpoints separately.
    return by

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('instance');ap.add_argument('--target',type=int,required=True);ap.add_argument('--seconds',type=float,default=120);ap.add_argument('--out',required=True);ap.add_argument('--witness');a=ap.parse_args()
    out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True);choices,rows,rhs,metadata,jobs=necessary_rows(a.instance,a.target)
    result={'target':a.target,'input_sha256':hashlib.sha256(pathlib.Path(a.instance).read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'scope':'Necessary joint first/last-mode inequalities from original public JSON; integral solver status only, no formal proof log','cp':cp_rows(choices,rows,rhs,len(jobs),a.seconds),'highs':highs_rows(choices,rows,rhs,len(jobs),a.seconds,out/'highs.log')}
    if a.witness:
        w=json.loads(pathlib.Path(a.witness).read_text());by={r['operation']:r for r in w['operations']};T=w['makespan'];c,r,b,md,j=necessary_rows(a.instance,T);selected=[int(by[j[x[0]][0]]['machine']==x[1] and by[j[x[0]][-1]]['machine']==x[2]) for x in c]
        assert all(sum(v*selected[k] for k,v in row.items())==bb if ii<len(j) else sum(v*selected[k] for k,v in row.items())<=bb for ii,(row,bb) in enumerate(zip(r,b)))
        result['original211_witness_all_rows_pass']=True;result['checked_rows']=len(r)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)

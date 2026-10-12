# Textbook FJSP decision model: is there a schedule with makespan <= T?  (OR-Tools CP-SAT)
import sys, time, json
from ortools.sat.python import cp_model
def parse(path):
    tok=open(path).read().split(); n=int(tok[0]); M=int(tok[1]); p=3; jobs=[]
    for _ in range(n):
        k=int(tok[p]); p+=1; ops=[]
        for _ in range(k):
            a=int(tok[p]); p+=1; ops.append([(int(tok[p+2*i])-1,int(tok[p+2*i+1])) for i in range(a)]); p+=2*a
        jobs.append(ops)
    return M,jobs
path,T,secs,w=sys.argv[1],int(sys.argv[2]),float(sys.argv[3]),int(sys.argv[4])
M,jobs=parse(path); m=cp_model.CpModel(); mach=[[] for _ in range(M)]
for ops in jobs:
    prev=None
    for alts in ops:
        lo=min(d for _,d in alts); hi=max(d for _,d in alts)
        s=m.NewIntVar(0,T,''); e=m.NewIntVar(0,T,''); dur=m.NewIntVar(lo,hi,'')
        m.NewIntervalVar(s,dur,e,'')
        lits=[]
        for mc,d in alts:
            l=m.NewBoolVar(''); lits.append(l)
            mach[mc].append(m.NewOptionalIntervalVar(s,d,e,l,''))
            m.Add(dur==d).OnlyEnforceIf(l)
        m.AddExactlyOne(lits)
        if prev is not None: m.Add(prev<=s)
        prev=e
for L in mach:
    if L: m.AddNoOverlap(L)
sv=cp_model.CpSolver(); sv.parameters.max_time_in_seconds=secs; sv.parameters.num_workers=w
t=time.time(); st=sv.Solve(m)
print(json.dumps({"instance":path,"T":T,"status":sv.StatusName(st),"wall":round(time.time()-t,2),"workers":w}),flush=True)

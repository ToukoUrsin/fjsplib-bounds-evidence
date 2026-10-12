"""Necessary assignment energy windows using each option's actual duration.

Every original schedule maps to one master assignment. A feasible master is
inconclusive; admitted INFEASIBLE requires regenerated integer coefficients.
"""
import argparse
import json
import time
import subprocess
import sys
from pathlib import Path
import numpy as np
from ortools.sat.python import cp_model
from check_schedule import read_text,check
from window_bounds import prepare


def coefficients(options,head,tail,T,m):
    ids=[i for i,o in enumerate(options) if m in o and head[i]+o[m]+tail[i]<=T]
    d=np.array([options[i][m] for i in ids],dtype=np.int64)
    h=np.array([head[i] for i in ids],dtype=np.int64)
    latest=T-np.array([tail[i] for i in ids],dtype=np.int64)-d
    points=sorted({0,T}|set(h)|set(h+d)|set(latest)|set(latest+d))
    points=[int(v) for v in points if 0<=v<=T]
    left=np.array([a for a in points for b in points if a<b],dtype=np.int64)
    right=np.array([b for a in points for b in points if a<b],dtype=np.int64)
    matrix=np.maximum(0,np.minimum(np.minimum(d[None,:],(right-left)[:,None]),
                      np.minimum(h[None,:]+d[None,:]-left[:,None],right[:,None]-latest[None,:])))
    return ids,left,right,matrix.astype(np.int16)


def context(instance,T,unary_proof=None):
    options,arcs,nm=read_text(instance);_,d,head,tail,_=prepare(instance)
    if unary_proof:
        from probe_unary_dp import replay
        source=json.loads(Path(unary_proof).read_text())
        assert source['target']==T
        assert not replay(instance,source), 'Unary proof already refutes this horizon'
        final=source['final_propagation']
        options=[{int(m):dd for m,dd in opts.items()} for opts in final['remaining_modes']]
        head=final['head'];tail=[T-end for end in final['latest_end']]
    return options,arcs,nm,head,tail


def rebuild(instance,T,cuts,unary_proof=None):
    options,arcs,nm,head,tail=context(instance,T,unary_proof)
    model=cp_model.CpModel();x={(i,m):model.new_bool_var(f'x{i}_{m}') for i,o in enumerate(options) for m in o}
    for i,o in enumerate(options):
        model.add_exactly_one([x[i,m] for m in o])
        for m,dd in o.items():
            if head[i]+dd+tail[i]>T:model.add(x[i,m]==0)
    for m in range(nm):model.add(sum(o[m]*x[i,m] for i,o in enumerate(options) if m in o)<=T)
    for cut in cuts:
        m,a,b=cut['machine'],cut['a'],cut['b'];terms=[]
        for i,o in enumerate(options):
            if m not in o or head[i]+o[m]+tail[i]>T:continue
            dd=o[m];latest=T-tail[i]-dd
            c=min(max(0,min(s+dd,b)-max(s,a)) for s in (head[i],latest))
            if c:terms.append([i,c])
        assert cut['coefficients']==terms,'Coefficient mismatch'
        model.add(sum(c*x[i,m] for i,c in terms)<=b-a)
    assert not model.validate(),model.validate()
    return model,x


def run(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True);begin=time.monotonic()
    T=a.target;options,arcs,nm,head,tail=context(a.instance,T,a.unary_proof)
    model,x=rebuild(a.instance,T,[],a.unary_proof);cuts=[];seen=set();report=[];relaxed=None;timing_cores=[];unary_cores=[]
    if a.initial_cuts:
        source=json.loads(Path(a.initial_cuts).read_text());assert source['target']==T
        assert source.get('unary_proof')==a.unary_proof
        model,x=rebuild(a.instance,T,source['cuts'],a.unary_proof);cuts=list(source['cuts'])
        seen={(c['machine'],c['a'],c['b']) for c in cuts}
        for r in source.get('timing_cores',[]):
            evidence=json.loads(Path(r['file']).read_text())
            assert evidence['target']==T and evidence['admitted_core'] and evidence['fresh_hard_status']=='INFEASIBLE'
            assert r['core']==evidence['core']
            if all((i,m) in x for i,m in r['core']):
                model.add_bool_or([x[i,m].Not() for i,m in r['core']])
            timing_cores.append(r)
        for r in source.get('unary_cores',[]):
            from shrink_unary_core import verify
            evidence=json.loads(Path(r['file']).read_text());verify(a.instance,evidence)
            assert evidence['target']==T and evidence['core']==r['core']
            if all((i,m) in x for i,m in r['core']):
                model.add_bool_or([x[i,m].Not() for i,m in r['core']])
            unary_cores.append(r)
    by_machine={m:coefficients(options,head,tail,T,m) for m in range(nm)}
    for i,m in a.fix_mode:
        assert i in range(len(options)) and m in options[i]
        model.add(x[i,m]==1)
    if a.fix_schedule:
        w=json.loads(Path(a.fix_schedule).read_text());check(a.instance,w);assert w['makespan']<=T
        for r in w['operations']:model.add(x[r['operation'],r['machine']]==1)
    status=None
    for iteration in range(a.iterations):
        remaining=a.total_seconds-(time.monotonic()-begin)
        if remaining<=0:break
        solver=cp_model.CpSolver();solver.parameters.num_search_workers=a.workers
        solver.parameters.max_time_in_seconds=min(a.seconds,remaining);solver.parameters.random_seed=a.seed+iteration
        st=solver.solve(model);status=solver.status_name(st)
        row=dict(iteration=iteration,status=status,seconds=solver.wall_time,cuts_before=len(cuts));report.append(row)
        if st not in (cp_model.OPTIMAL,cp_model.FEASIBLE):break
        chosen=[next(m for m in o if solver.boolean_value(x[i,m])) for i,o in enumerate(options)]
        added=0;worst=0
        for m,(ids,left,right,c) in by_machine.items():
            selected=np.array([chosen[i]==m for i in ids],dtype=bool);energy=c[:,selected].sum(axis=1,dtype=np.int64)
            v=energy-(right-left)
            if len(v)==0:continue
            k=int(np.argmax(v));violation=int(v[k]);worst=max(worst,violation)
            if violation<=0:continue
            key=(m,int(left[k]),int(right[k]));assert key not in seen
            terms=[[i,int(c[k,j])] for j,i in enumerate(ids) if c[k,j]>0]
            model.add(sum(dd*x[i,m] for i,dd in terms)<=key[2]-key[1]);seen.add(key);added+=1
            cuts.append(dict(machine=m,a=key[1],b=key[2],coefficients=terms,separating_violation=violation))
        row.update(added=added,worst_violation=worst);print(json.dumps(row),flush=True)
        (out/'progress.json').write_text(json.dumps(report,indent=2)+'\n')
        if not added:
            relaxed=chosen
            if a.unary_core_seconds:
                from shrink_unary_core import shrink,verify
                remaining=a.total_seconds-(time.monotonic()-begin)
                if remaining<=0:break
                ur=shrink(a.instance,T,chosen,min(a.unary_core_seconds,remaining))
                if ur['admitted_core']:
                    verify(a.instance,ur)
                    f=out/f'unary-core-{iteration}.json';f.write_text(json.dumps(ur,indent=2)+'\n')
                    core=ur['core'];model.add_bool_or([x[i,m].Not() for i,m in core])
                    unary_cores.append(dict(file=str(f),core=core));relaxed=None
                    row['unary_core_size']=len(core)
                    print(json.dumps(dict(iteration=iteration,unary_core_size=len(core),tests=ur['tests'])),flush=True)
                    if time.monotonic()-begin<a.total_seconds:continue
                else:
                    row['unary_fixed_point']=True
            if a.timing_core_seconds:
                assert a.hint
                remaining=a.total_seconds-(time.monotonic()-begin)
                if remaining<=0:break
                assignment_file=out/f'assignment-{iteration}.json';assignment_file.write_text(json.dumps(chosen)+'\n')
                folder=out/f'timing-{iteration}'
                cmd=[sys.executable,'src/mode_timing_core.py',a.instance,'--hint',a.hint,'--assignments',str(assignment_file),
                     '--target',str(T),'--out',str(folder),'--seconds',str(min(a.timing_core_seconds,remaining/2)),
                     '--seed',str(a.seed+iteration)]
                subprocess.run(cmd,check=True);tr=json.loads((folder/'result.json').read_text());row['timing_status']=tr['status']
                if tr.get('admitted_core'):
                    core=tr['core'];model.add_bool_or([x[i,m].Not() for i,m in core]);timing_cores.append(dict(file=str(folder/'result.json'),core=core))
                    row['timing_core_size']=len(core);relaxed=None
                    if time.monotonic()-begin<a.total_seconds:continue
                elif tr.get('objective') is not None:
                    w=json.loads((folder/'schedule.json').read_text());check(a.instance,w)
                    (out/'schedule.json').write_text(json.dumps(w,indent=2)+'\n')
                    row['objective']=w['makespan']
            break
    result=dict(instance=Path(a.instance).stem,target=T,scope=('Conditional fixed-mode ' if a.fix_mode else '')+'Necessary consistent-assignment mode-dependent energetic-window relaxation only',
                status=status,elapsed=time.monotonic()-begin,seconds_limit=a.seconds,total_seconds_limit=a.total_seconds,
                workers=a.workers,seed=a.seed,cuts=cuts,iterations=report,relaxed_assignment=relaxed,
                fixed_modes=a.fix_mode,unary_proof=a.unary_proof,
                windows_per_machine={m:len(v[1]) for m,v in by_machine.items()},admitted_infeasible=False,
                timing_cores=timing_cores,unary_cores=unary_cores,schedule_feasibility_established=(out/'schedule.json').exists())
    if status=='INFEASIBLE' and not timing_cores and not unary_cores:
        checkmodel,checkx=rebuild(a.instance,T,cuts,a.unary_proof)
        for i,m in a.fix_mode:checkmodel.add(checkx[i,m]==1)
        checker=cp_model.CpSolver();checker.parameters.num_search_workers=1;checker.parameters.max_time_in_seconds=a.seconds
        st=checker.solve(checkmodel);result.update(independent_regenerated_status=checker.status_name(st),recheck_seconds=checker.wall_time,
                                                 admitted_infeasible=st==cp_model.INFEASIBLE and not a.fix_mode,
                                                 admitted_conditional_infeasible=st==cp_model.INFEASIBLE and bool(a.fix_mode))
    if a.fix_schedule:
        ids={r['operation']:r for r in w['operations']};checked=0
        for m,(operations,left,right,c) in by_machine.items():
            selected=np.array([ids[i]['machine']==m for i in operations],dtype=bool);energy=c[:,selected].sum(axis=1,dtype=np.int64)
            assert np.all(energy<=right-left);checked+=len(left)
        result['original_witness_windows_checked']=checked
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('cuts','iterations','relaxed_assignment')}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('instance');p.add_argument('--target',type=int,required=True);p.add_argument('--out',required=True)
    p.add_argument('--seconds',type=float,default=20);p.add_argument('--total-seconds',type=float,default=180)
    p.add_argument('--workers',type=int,default=4);p.add_argument('--iterations',type=int,default=100)
    p.add_argument('--seed',type=int,default=241);p.add_argument('--fix-schedule')
    p.add_argument('--initial-cuts');p.add_argument('--hint');p.add_argument('--timing-core-seconds',type=float,default=0)
    p.add_argument('--unary-proof',help='Replay failed-literal unary certificates and use their sound bounds')
    p.add_argument('--unary-core-seconds',type=float,default=0)
    p.add_argument('--fix-mode',nargs=2,type=int,action='append',default=[],metavar=('OPERATION','MACHINE'))
    run(p.parse_args())

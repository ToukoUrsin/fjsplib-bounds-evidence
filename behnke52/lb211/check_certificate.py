"""Stdlib semantic replay of every necessary endpoint-prefix coefficient."""
import argparse,copy,hashlib,json,pathlib

def replay(instance,cert):
    b=pathlib.Path(instance).read_bytes();assert cert['input_sha256']==hashlib.sha256(b).hexdigest()
    data=json.loads(b);opts={};succ={};incoming=set()
    for row in data['operations']:
        i,m,d=row['operation'],row['machine'],row['duration'];assert d>0 and (i,m) not in opts;opts[i,m]=d
    for row in data['precedences']:
        i,j=row['before'],row['after'];assert i not in succ and j not in incoming;succ[i]=j;incoming.add(j)
    opids={i for i,m in opts};jobs=[]
    for root in sorted(opids-incoming):
        c=[root]
        while c[-1] in succ:c.append(succ[c[-1]])
        jobs.append(c)
    assert sorted(i for c in jobs for i in c)==list(range(len(opids)))
    T=cert['target'];assert type(T) is int and T>=0
    middle=[sum(min(d for (op,m),d in opts.items() if op==i) for i in c[1:-1]) for c in jobs]
    choices=[tuple(c) for c in cert['choices']]
    expected={(j,m,n,p,q) for j,c in enumerate(jobs) for (op,m),p in opts.items() if op==c[0] for (end,n),q in opts.items() if end==c[-1]}
    assert len(choices)==len(set(choices)) and set(choices)==expected,'altered/omitted original mode pair'
    tail=[middle[j]+q for j,m,n,p,q in choices];head=[middle[j]+p for j,m,n,p,q in choices]
    expected_metadata={('job',j) for j in range(len(jobs))}
    expected_metadata|={('first_tail',m,tail[k]) for k,(j,m,n,p,q) in enumerate(choices)}
    expected_metadata|={('last_head',n,head[k]) for k,(j,m,n,p,q) in enumerate(choices)}
    metadata=[tuple(row) for row in cert['metadata']]
    assert len(metadata)==len(set(metadata)) and set(metadata)==expected_metadata
    assert len(cert['rows'])==len(cert['rhs'])==len(metadata)
    coefficients=0
    for md,entries,rhs in zip(metadata,cert['rows'],cert['rhs']):
        row=dict(entries);assert len(row)==len(entries) and all(type(k) is int and type(v) is int for k,v in entries)
        if md[0]=='job':
            wanted={k:1 for k,c in enumerate(choices) if c[0]==md[1]};right=1
        elif md[0]=='first_tail':
            _,m,Q=md;wanted={k:c[3] for k,c in enumerate(choices) if c[1]==m and tail[k]>=Q};right=T-Q
        else:
            _,n,H=md;wanted={k:c[4] for k,c in enumerate(choices) if c[2]==n and head[k]>=H};right=T-H
        assert row==wanted,'wrong coefficient or original-mode membership'
        assert rhs==right,'wrong capacity/head/tail arithmetic'
        coefficients+=len(row)
    return {'jobs':len(jobs),'original_operations':len(opids),'original_mode_rows':len(opts),'joint_mode_columns':len(choices),'necessary_rows':len(metadata),'integer_coefficients_checked':coefficients,'target':T,'scope':'Every coefficient regenerated semantically from original JSON. Solver infeasibility remains engine-certified, not a formal proof trace.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('instance');ap.add_argument('certificate');ap.add_argument('--out',required=True);ap.add_argument('--controls',action='store_true');a=ap.parse_args()
    cert=json.loads(pathlib.Path(a.certificate).read_text());result=replay(a.instance,cert)
    if a.controls:
        controls=[]
        for name in ('coefficient','rhs','duration','mode_coverage','input_hash'):
            bad=copy.deepcopy(cert)
            if name=='coefficient':bad['rows'][0][0][1]+=1
            if name=='rhs':bad['rhs'][-1]-=1
            if name=='duration':bad['choices'][0][3]+=1
            if name=='mode_coverage':bad['choices'].pop()
            if name=='input_hash':bad['input_sha256']='0'*64
            try:replay(a.instance,bad)
            except AssertionError:controls.append(name)
            else:raise AssertionError(('forged certificate accepted',name))
        result['negative_controls_rejected']=controls
    pathlib.Path(a.out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

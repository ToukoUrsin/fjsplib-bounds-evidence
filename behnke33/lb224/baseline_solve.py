"""Pinned CP-SAT baseline with original JSON inputs and exported witnesses."""
import argparse
import collections
import hashlib
import json
import random
import time
from pathlib import Path

import ortools
from ortools.sat.python import cp_model


def load(path):
    data = json.loads(Path(path).read_text())
    options = collections.defaultdict(list)
    for row in data['operations']:
        options[row['operation']].append((row['machine'], row['duration']))
    assert set(options) == set(range(len(options)))
    arcs = [(x['before'], x['after']) for x in data['precedences']]
    return data, dict(options), arcs


def greedy(options, arcs, seed, trials=100):
    rng = random.Random(seed)
    pred, succ = collections.defaultdict(list), collections.defaultdict(list)
    for a, b in arcs:
        pred[b].append(a); succ[a].append(b)
    best = None
    for trial in range(trials):
        remaining = {i: len(pred[i]) for i in options}
        ready = [i for i in options if not pred[i]]
        ends, available, rows = {}, collections.defaultdict(int), []
        while ready:
            op = rng.choice(ready) if trial else min(ready)
            ready.remove(op)
            release = max((ends[x] for x in pred[op]), default=0)
            finish, machine, start = min((max(available[m], release)+d, m, max(available[m], release)) for m, d in options[op])
            rows.append({'operation': op, 'machine': machine, 'start': start, 'end': finish})
            ends[op] = finish; available[machine] = finish
            for nxt in succ[op]:
                remaining[nxt] -= 1
                if remaining[nxt] == 0: ready.append(nxt)
        assert len(rows) == len(options), 'cyclic precedence graph'
        schedule = {'makespan': max(ends.values()), 'operations': sorted(rows, key=lambda x: x['operation'])}
        if best is None or schedule['makespan'] < best['makespan']: best = schedule
    return best


def run(a):
    data, options, arcs = load(a.instance)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    donor = greedy(options, arcs, a.seed)
    if a.hint:
        donor = json.loads(Path(a.hint).read_text())
    donor['instance'] = data['instance']
    (out/'greedy.json').write_text(json.dumps(donor, indent=2)+'\n')
    horizon = a.target if a.target is not None else donor['makespan']
    model = cp_model.CpModel()
    starts, ends, choices, machine_intervals, all_intervals = {}, {}, {}, collections.defaultdict(list), []
    duration_vars, machine_work = {}, collections.defaultdict(list)
    for op, opts in options.items():
        starts[op] = model.new_int_var(0, horizon, f's{op}')
        ends[op] = model.new_int_var(0, horizon, f'e{op}')
        duration = model.new_int_var_from_domain(cp_model.Domain.from_values(sorted(set(d for _, d in opts))), f'd{op}')
        duration_vars[op] = duration
        all_intervals.append(model.new_interval_var(starts[op], duration, ends[op], f'i{op}'))
        lits = []
        for k, (machine, dur) in enumerate(opts):
            lit = model.new_bool_var(f'x{op}_{k}'); choices[op,k] = lit; lits.append(lit)
            iv = model.new_optional_interval_var(starts[op], dur, ends[op], lit, f'i{op}_{k}')
            machine_intervals[machine].append(iv)
            machine_work[machine].append(dur*lit)
        model.add_exactly_one(lits)
        if a.strengthen:
            model.add(duration == sum(d*choices[op,k] for k, (_,d) in enumerate(opts)))
    for before, after in arcs: model.add(ends[before] <= starts[after])
    for intervals in machine_intervals.values(): model.add_no_overlap(intervals)
    if a.cumulative: model.add_cumulative(all_intervals, [1]*len(all_intervals), len(machine_intervals))
    makespan = model.new_int_var(0, horizon, 'makespan')
    model.add_max_equality(makespan, list(ends.values()))
    subset_count = 0
    if a.strengthen:
        for terms in machine_work.values(): model.add(sum(terms) <= makespan)
        eligibility = {op: frozenset(m for m,_ in opts) for op,opts in options.items()}
        for group in sorted(set(eligibility.values()), key=lambda x:(len(x),sorted(x))):
            forced = [op for op,machines in eligibility.items() if machines <= group]
            energy = sum(min(d for _,d in options[op]) for op in forced)
            if len(group)>1 and len(forced)>len(group) and energy >= 0.4*horizon*len(group):
                model.add_cumulative([all_intervals[op] for op in forced], [1]*len(forced), len(group))
                subset_count += 1
    idle_budget = None
    if a.idle_cuts:
        assert a.target is not None, 'Idle cuts require a fixed target'
        assert all(len(set(d for _,d in opts))==1 for opts in options.values()), 'Requires machine-independent durations'
        total_work = sum(opts[0][1] for opts in options.values())
        nm = len(machine_intervals)
        idle_budget = nm*horizon-total_work
        if idle_budget < 0:
            model.add(False)
        elif idle_budget < horizon:
            for machine, terms in machine_work.items():
                model.add(sum(terms) >= horizon-idle_budget)
                early, late = [], []
                for op,opts in options.items():
                    for k,(m,_) in enumerate(opts):
                        if m != machine: continue
                        first = model.new_bool_var(f'early{op}_{k}')
                        last = model.new_bool_var(f'late{op}_{k}')
                        model.add_implication(first,choices[op,k])
                        model.add(starts[op] <= idle_budget).only_enforce_if(first)
                        model.add_implication(last,choices[op,k])
                        model.add(ends[op] >= horizon-idle_budget).only_enforce_if(last)
                        early.append(first); late.append(last)
                model.add_bool_or(early); model.add_bool_or(late)
    if a.target is None: model.minimize(makespan)
    if donor['makespan'] <= horizon:
        for row in donor['operations']:
            op = row['operation']; model.add_hint(starts[op], row['start']); model.add_hint(ends[op], row['end'])
            for k, (m, _) in enumerate(options[op]): model.add_hint(choices[op,k], int(m == row['machine']))
    validation = model.validate()
    assert not validation, validation
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = a.seconds
    solver.parameters.num_search_workers = a.workers
    solver.parameters.random_seed = a.seed
    solver.parameters.log_search_progress = True
    solver.parameters.log_to_stdout = False
    log = (out/'solver.log').open('w')
    solver.log_callback = lambda line: (log.write(line+'\n'), log.flush())
    t0 = time.monotonic(); status = solver.solve(model); elapsed = time.monotonic()-t0
    log.close()
    result = {'instance': data['instance'], 'status': solver.status_name(status), 'target': a.target,
              'seconds_limit': a.seconds, 'workers': a.workers, 'seed': a.seed, 'cumulative': a.cumulative,
              'strengthen': a.strengthen, 'subset_cumulatives': subset_count,
              'idle_cuts': a.idle_cuts, 'idle_budget': idle_budget,
              'ortools': ortools.__version__, 'elapsed': elapsed, 'solver_wall_time': solver.wall_time,
              'input_sha256': hashlib.sha256(Path(a.instance).read_bytes()).hexdigest(),
              'greedy_makespan': donor['makespan'], 'objective': None, 'best_bound': solver.best_objective_bound,
              'operations': len(options), 'modes': sum(map(len, options.values())), 'response': solver.response_stats()}
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        rows = []
        for op, opts in options.items():
            machine = next(m for k, (m, _) in enumerate(opts) if solver.boolean_value(choices[op,k]))
            rows.append({'operation': op, 'machine': machine, 'start': solver.value(starts[op]), 'end': solver.value(ends[op])})
        schedule = {'instance': data['instance'], 'makespan': solver.value(makespan), 'operations': rows}
        result['objective'] = schedule['makespan']
        (out/'schedule.json').write_text(json.dumps(schedule, indent=2)+'\n')
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('instance'); ap.add_argument('--out', required=True)
    ap.add_argument('--seconds', type=float, default=600); ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--seed', type=int, default=1); ap.add_argument('--target', type=int)
    ap.add_argument('--hint'); ap.add_argument('--cumulative', action='store_true')
    ap.add_argument('--strengthen', action='store_true')
    ap.add_argument('--idle-cuts', action='store_true')
    run(ap.parse_args())

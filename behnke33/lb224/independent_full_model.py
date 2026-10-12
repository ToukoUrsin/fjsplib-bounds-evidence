"""Independent original all-mode CP-SAT feasibility model.

This intentionally omits the baseline model's mandatory duration interval and
duration variable.  Each selected optional mode interval directly links the
shared start/end variables, so exactly-one selection gives the operation's
duration.  It is used as a formulation check for a fixed makespan.
"""
import argparse, collections, hashlib, json, time
from pathlib import Path
import ortools
from ortools.sat.python import cp_model


def solve(instance, target, seconds, workers, seed, out, hint=None):
    data = json.loads(Path(instance).read_text())
    options = collections.defaultdict(list)
    for row in data["operations"]:
        options[row["operation"]].append((row["machine"], row["duration"]))
    arcs = [(r["before"], r["after"]) for r in data["precedences"]]
    model = cp_model.CpModel()
    starts, ends, choices = {}, {}, {}
    machine_intervals = collections.defaultdict(list)
    machine_work = collections.defaultdict(list)
    for op in sorted(options):
        starts[op] = model.new_int_var(0, target, f"s{op}")
        ends[op] = model.new_int_var(0, target, f"e{op}")
        lits = []
        for k, (machine, duration) in enumerate(options[op]):
            lit = model.new_bool_var(f"x{op}_{k}")
            choices[op, k] = lit
            lits.append(lit)
            iv = model.new_optional_interval_var(
                starts[op], duration, ends[op], lit, f"op{op}_m{machine}_{k}"
            )
            machine_intervals[machine].append(iv)
            machine_work[machine].append(duration * lit)
        model.add_exactly_one(lits)
    for before, after in arcs:
        model.add(ends[before] <= starts[after])
    for intervals in machine_intervals.values():
        model.add_no_overlap(intervals)
    for terms in machine_work.values():
        model.add(sum(terms) <= target)
    if hint:
        donor = json.loads(Path(hint).read_text())
        if donor["makespan"] <= target:
            for row in donor["operations"]:
                op = row["operation"]
                model.add_hint(starts[op], row["start"])
                model.add_hint(ends[op], row["end"])
                for k, (machine, _duration) in enumerate(options[op]):
                    model.add_hint(choices[op, k], int(machine == row["machine"]))
    validation = model.validate()
    assert not validation, validation
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = seed
    solver.parameters.log_search_progress = True
    solver.parameters.log_to_stdout = False
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    log = (out / "solver.log").open("w")
    solver.log_callback = lambda line: (log.write(line + "\n"), log.flush())
    t0 = time.monotonic(); status = solver.solve(model); elapsed = time.monotonic() - t0
    log.close()
    result = {
        "instance": data["instance"], "target": target,
        "status": solver.status_name(status), "elapsed": elapsed,
        "solver_wall_time": solver.wall_time, "seconds_limit": seconds,
        "workers": workers, "seed": seed, "ortools": ortools.__version__,
        "operations": len(options), "modes": sum(map(len, options.values())),
        "input_sha256": hashlib.sha256(Path(instance).read_bytes()).hexdigest(),
        "response": solver.response_stats(),
        "formulation": "shared start/end plus selected optional mode intervals; no mandatory duration variable",
    }
    if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
        rows = []
        for op, opts in options.items():
            k = next(k for k in range(len(opts)) if solver.boolean_value(choices[op, k]))
            rows.append({"operation": op, "machine": opts[k][0], "start": solver.value(starts[op]), "end": solver.value(ends[op])})
        schedule = {"instance": data["instance"], "makespan": max(r["end"] for r in rows), "operations": rows}
        result["objective"] = schedule["makespan"]
        (out / "schedule.json").write_text(json.dumps(schedule, indent=2) + "\n")
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("instance"); ap.add_argument("--target", type=int, required=True)
    ap.add_argument("--seconds", type=float, default=60); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1); ap.add_argument("--out", required=True)
    ap.add_argument("--hint")
    a = ap.parse_args(); solve(a.instance, a.target, a.seconds, a.workers, a.seed, a.out, a.hint)

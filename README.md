# FJSPLib bound evidence: behnke60, mk13, behnke52, behnke33

Schedules, checkers and lower-bound models for four FJSPLib instances, compared with
`flexible-jobshop/solutions/bks.json` in [ScheduleOpt/benchmarks](https://github.com/ScheduleOpt/benchmarks)
(main `057ebda2`, 12 October 2026). Instance files in `instances/` are unchanged copies from that repository.

| Instance | Listed LB/UB | New | Evidence |
|---|---|---|---|
| behnke60 | 397 / 402 | UB 397 (closed) | `behnke60/behnke60_schedule_397.json` |
| mk13 | 382 / 390 | UB 383, LB 383 (closed) | `mk13/mk13_schedule_383.json`, `mk13/lb383/` |
| behnke52 | 210 / 212 | UB 211, LB 211 (closed) | `behnke52/behnke52_schedule_211.json`, `behnke52/lb211/` |
| behnke33 | 223 / 224 | LB 224 (closed) | `behnke33/lb224/` |

## Schedules

JSON with `operation` (global index in job order, as in `instances/json`), `machine` (0-based), `start`, `end`.
`verify_fjsp.py` (standard library only) reads both the `fjsp/*.txt` and the `json` instance and checks that
every operation appears once, machine eligibility, machine-dependent durations, all job precedences, no overlap
on any machine, and the makespan:

```bash
python3 verify_fjsp.py instances/behnke60.txt instances/behnke60.json behnke60/behnke60_schedule_397.json 397
python3 verify_fjsp.py instances/mk13.txt     instances/mk13.json     mk13/mk13_schedule_383.json 383
python3 verify_fjsp.py instances/behnke52.txt instances/behnke52.json behnke52/behnke52_schedule_211.json 211
```

Corrupted copies (objective, duration, machine, start, missing and duplicate operation) are rejected.

## Lower bounds

All are solver results (OR-Tools CP-SAT 9.15.6755, HiGHS 1.13.0) on models built from the original instance, not
formal proof traces. `reproduce.sh` reruns everything (`pip install -r requirements.txt` first); the cold rerun
output is in `cold-rerun-2026-10-12.log` and the `rerun*` folders.

- **behnke33, makespan <= 223 infeasible** with two separately written full models:
  `baseline_solve.py --strengthen` (optional mode intervals, NoOverlap, precedences, machine-load rows;
  INFEASIBLE in 57 s, 4 workers) and `independent_full_model.py` (shared start/end variables, exactly one mode
  interval per operation; INFEASIBLE in 22 s, 1 worker).
- **behnke52, makespan <= 210 infeasible** via a relaxation that every schedule satisfies (`prefix_bound.py`):
  each job uses one first-operation mode and one last-operation mode. First operations assigned to the same
  machine whose minimum remaining tail is >= Q must all finish by T - Q, so their total work on that machine is
  at most T - Q; symmetrically for last operations with minimum head >= H. Middle durations are at least their minima. These 282 integer rows over 800
  first/last mode pairs have no solution at T = 210 (CP-SAT INFEASIBLE 7 s, HiGHS Infeasible 30 s); the 211
  schedule satisfies every row. `check_certificate.py` regenerates all 21,256 coefficients from the JSON instance
  with the standard library and rejects 5 forged variants.
- **mk13, makespan <= 382 infeasible** via a mode-assignment relaxation (`check_mode_window_bound.py`): one mode
  per operation, modes with head + duration + tail > T removed (heads/tails from minimum durations along the job),
  machine load <= T, plus one energetic cut on machine index 8 (0-based) over window [0, 368] whose coefficients are each
  operation's minimum overlap with the window. CP-SAT INFEASIBLE (3 s) and HiGHS Infeasible (25 s); coefficients are
  regenerated from the instance and a changed coefficient is rejected.

Contact: Touko Ursin, touko.ursin@gmail.com

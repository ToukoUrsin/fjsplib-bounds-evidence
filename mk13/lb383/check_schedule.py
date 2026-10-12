"""Independent checker: reads original fajsp text, never imports the producer."""
import argparse
import collections
import json
from pathlib import Path


def read_text(path):
    rows = [list(map(int, row.split())) for row in Path(path).read_text().splitlines() if row.strip()]
    n, p, m = rows[0]
    assert len(rows) == 1 + p + n
    precedences = []
    for row in rows[1:1+p]:
        assert len(row) == 3 and 0 <= row[0] < n and 0 <= row[1] < n
        precedences.append(tuple(row[:2]))
    options = []
    for row in rows[1+p:]:
        assert len(row) == 1 + 2*row[0] and row[0] > 0
        opts = dict(zip(row[1::2], row[2::2]))
        assert len(opts) == row[0]
        assert all(0 <= machine < m and duration > 0 for machine, duration in opts.items())
        options.append(opts)
    return options, precedences, m


def check(instance, schedule):
    options, arcs, m = read_text(instance)
    assert schedule['instance'] == Path(instance).stem, 'instance name'
    rows = schedule['operations']
    assert len(rows) == len(options), 'operation count'
    by_id = {x['operation']: x for x in rows}
    assert set(by_id) == set(range(len(options))), 'missing or duplicate operations'
    ends, machines = {}, collections.defaultdict(list)
    for op, row in by_id.items():
        machine, start = row['machine'], row['start']
        assert type(start) is int and start >= 0, 'nonnegative integral start'
        assert type(machine) is int and machine in options[op], 'ineligible machine'
        end = start + options[op][machine]
        assert row['end'] == end, 'wrong duration'
        ends[op] = end
        machines[machine].append((start, end, op))
    for before, after in arcs:
        assert ends[before] <= by_id[after]['start'], 'precedence'
    for intervals in machines.values():
        intervals.sort()
        for left, right in zip(intervals, intervals[1:]):
            assert left[1] <= right[0], 'machine overlap'
    makespan = max(ends.values())
    assert makespan == schedule['makespan'], 'wrong objective'
    return {'valid': True, 'makespan': makespan, 'operations': len(options), 'precedences': len(arcs), 'machines': m}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('instance')
    ap.add_argument('schedule')
    a = ap.parse_args()
    print(json.dumps(check(a.instance, json.loads(Path(a.schedule).read_text()))))

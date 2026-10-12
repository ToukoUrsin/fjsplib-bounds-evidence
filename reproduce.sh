#!/bin/bash
# Re-checks everything in this folder. Schedules: stdlib only. Lower bounds: pip install -r requirements.txt
set -u
I=instances
echo "== schedules (stdlib checker)"
python3 verify_fjsp.py $I/behnke60.txt $I/behnke60.json behnke60/behnke60_schedule_397.json 397
python3 verify_fjsp.py $I/mk13.txt     $I/mk13.json     mk13/mk13_schedule_383.json 383
python3 verify_fjsp.py $I/behnke52.txt $I/behnke52.json behnke52/behnke52_schedule_211.json 211
echo "== behnke33: makespan <= 223 (two separate full models)"
(cd behnke33/lb224 && python3 baseline_solve.py ../../$I/behnke33.json --out rerun-strengthened --seconds 600 --workers 4 --seed 570223 --target 223 --strengthen >/dev/null 2>&1; python3 -c "import json;d=json.load(open('rerun-strengthened/result.json'));print('strengthened',d.get('status'),d.get('seconds') or d.get('elapsed'))")
(cd behnke33/lb224 && python3 independent_full_model.py ../../$I/behnke33.json --target 223 --seconds 600 --workers 1 --seed 570335 --out rerun-independent >/dev/null 2>&1; python3 -c "import json;d=json.load(open('rerun-independent/result.json'));print('independent',d.get('status'),d.get('seconds') or d.get('elapsed'))")
echo "== behnke52: necessary endpoint/prefix rows at horizon 210"
(cd behnke52/lb211 && python3 prefix_bound.py ../../$I/behnke52.json --target 210 --seconds 120 --witness witness211.json --out rerun-prefix210 >/dev/null 2>&1; cat rerun-prefix210/result.json; echo; python3 check_certificate.py ../../$I/behnke52.json necessary-prefix-certificate210.json --out rerun-check --controls 2>&1 | tail -3)
echo "== mk13: mode-window energetic relaxation at horizon 382"
(cd mk13/lb383 && python3 check_mode_window_bound.py ../../$I/mk13.fajsp.txt --cuts cuts382.json --out rerun --seconds 300 --workers 4 --cpsat --seed 302 >/dev/null 2>&1; cat rerun/result.json)

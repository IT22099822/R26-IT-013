"""Unit tests for the snapshot parsers in services/dropout_service.py.
Run from the backend repo root:  python tests/test_c4_snapshot.py"""
import os, sys, types
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)
db = types.ModuleType("db"); dbs = types.ModuleType("db.supabase"); dbs.supabase = None
sys.modules["db"] = db; sys.modules["db.supabase"] = dbs     # parsers need no database
from services.dropout_service import parse_bkt_avg, parse_n_gaps  # noqa: E402

results = []


def check(uid, desc, ok, got):
    results.append(ok); print(f"{uid:5s} {'PASS' if ok else 'FAIL'}  {desc}  -> {got}")


snap = {"F01": 0.9, "F02": 0.5, "F03": 0.4}
check("SP1", "jsonb snapshot as decoded dict (what Supabase returns) -> real mean", abs(parse_bkt_avg(snap) - 0.6) < 1e-9, parse_bkt_avg(snap))
check("SP2", "same snapshot as JSON text (CSV export) -> same mean", abs(parse_bkt_avg('{"F01": 0.9, "F02": 0.5, "F03": 0.4}') - 0.6) < 1e-9, parse_bkt_avg('{"F01": 0.9, "F02": 0.5, "F03": 0.4}'))
check("SP3", "empty / missing snapshot -> 0.2 prior", [parse_bkt_avg(x) for x in (None, {}, "", "{}")] == [0.2] * 4, [parse_bkt_avg(x) for x in (None, {}, "", "{}")])
check("SP4", "malformed snapshot -> 0.2, no crash", [parse_bkt_avg(x) for x in ("not json", {"F01": "x"}, [1, 2])] == [0.2] * 3, [parse_bkt_avg(x) for x in ("not json", {"F01": "x"}, [1, 2])])
check("SP5", "gaps as text[] list (what Supabase returns) -> count", parse_n_gaps(["F01", "F03"]) == 2, parse_n_gaps(["F01", "F03"]))
check("SP6", "gaps as '{F01,F03}' text (CSV export) -> same count", parse_n_gaps("{F01,F03}") == 2, parse_n_gaps("{F01,F03}"))
check("SP7", "no gaps -> 0", [parse_n_gaps(x) for x in (None, [], "", "{}")] == [0] * 4, [parse_n_gaps(x) for x in (None, [], "", "{}")])
print(f"\n{sum(results)}/{len(results)} passed")

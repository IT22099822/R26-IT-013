"""Unit tests for services/weekly_agg.py (calculate_weekly_stats) with an in-memory Supabase stub.
Covers the NULL avg_quiz_score crash and the same-week re-run comparison.
Run from the backend repo root:  python tests/test_weekly_agg_unit.py"""
import os as _os, sys as _sys
_ROOT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)   # run from any folder: imports resolve from the repo root
import asyncio, copy, logging, sys, types
from datetime import date, datetime, timedelta
import pytz
COLOMBO = pytz.timezone("Asia/Colombo")

class _Res:
    def __init__(self, data): self.data = data
class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.mode, self.payload = db, table, [], "select", None
        self._order, self._limit, self._conflict = None, None, None
    def select(self, *a, **k): self.mode = "select"; return self
    def update(self, payload): self.mode = "update"; self.payload = payload; return self
    def upsert(self, payload, on_conflict=None):
        self.mode = "upsert"; self.payload = payload; self._conflict = on_conflict.split(","); return self
    def eq(self, k, v): self.filters.append(lambda r: r.get(k) == v); return self
    def lt(self, k, v): self.filters.append(lambda r: r.get(k) is not None and r.get(k) < v); return self
    def gte(self, k, v): self.filters.append(lambda r: r.get(k) is not None and r.get(k) >= v); return self
    def lte(self, k, v): self.filters.append(lambda r: r.get(k) is not None and r.get(k) <= v); return self
    def order(self, col, desc=False): self._order = (col, desc); return self
    def limit(self, n): self._limit = n; return self
    def execute(self):
        tbl = self.db.setdefault(self.table, [])
        if self.mode == "upsert":
            for r in tbl:
                if all(r.get(c) == self.payload.get(c) for c in self._conflict):
                    r.update(copy.deepcopy(self.payload)); return _Res([self.payload])
            tbl.append(copy.deepcopy(self.payload)); return _Res([self.payload])
        rows = [r for r in tbl if all(f(r) for f in self.filters)]
        if self.mode == "update":
            for r in rows: r.update(copy.deepcopy(self.payload))
            return _Res(rows)
        if self._order: rows = sorted(rows, key=lambda r: r[self._order[0]], reverse=self._order[1])
        if self._limit: rows = rows[: self._limit]
        return _Res(copy.deepcopy(rows))
class FakeSupabase:
    def __init__(self): self.db = {}
    def table(self, name): return _Query(self.db, name)

supabase = FakeSupabase()
db_pkg = types.ModuleType("db"); db_mod = types.ModuleType("db.supabase"); db_mod.supabase = supabase
sys.modules["db"] = db_pkg; sys.modules["db.supabase"] = db_mod
cfg = types.ModuleType("config"); cfg.PILOT_START_DATE = date(2026, 4, 22)   # same value as config.py
sys.modules["config"] = cfg

# Capture weekly_agg's per-student error log so a swallowed exception counts as a failure
errors = []
class _Catch(logging.Handler):
    def emit(self, record): errors.append(record.getMessage())
logging.getLogger("services.weekly_agg").addHandler(_Catch())

import services.weekly_agg as wa  # noqa: E402

results = []
def check(uid, desc, ok, got):
    results.append(ok); print(f"{uid:5s} {'PASS' if ok else 'FAIL'}  {desc}  -> {got}")

now = datetime.now(COLOMBO)
CUR = wa.get_week_number(now)
IN_WEEK = (wa.get_last_monday(now) + timedelta(hours=1)).isoformat()

def student(sid):
    return dict(student_id=sid, active=True, last_login_at=None, bkt_mastery={"F01": 0.6},
                irt_theta=0.1, current_gaps=["F02"])
def quiz(sid, score):
    return dict(student_id=sid, score_pct=score, taken_at=IN_WEEK, abandoned=False)
def prev_row(sid, week, avg):
    return dict(student_id=sid, week_number=week, avg_quiz_score=avg)
def run():
    errors.clear(); asyncio.run(wa.calculate_weekly_stats())
def row(sid, week=CUR):
    return next((r for r in supabase.db.get("weekly_stats", []) if r["student_id"] == sid and r["week_number"] == week), None)

supabase.db = {
    "students": [student(s) for s in ("null_prev", "rerun", "null_quiz", "first_week", "drop")],
    "sessions": [], "unit_progress": [dict(student_id="null_prev", node_id="F01", completed=False,
                                           video_watch_pct=50, audio_play_count=1, scroll_depth_pct=80,
                                           revisit_count=0, total_time_sec=300)],
    "question_attempts": [],
    "quiz_results": [quiz("null_prev", 60), quiz("rerun", 80), quiz("null_quiz", 70), quiz("null_quiz", None),
                     quiz("drop", 60)],
    "weekly_stats": [prev_row("null_prev", CUR - 1, None),
                     prev_row("rerun", CUR - 1, 50.0), prev_row("rerun", CUR, 90.0),  # CUR row = an earlier run this week
                     prev_row("drop", CUR - 1, 80.0)],
}
run()

r = row("null_prev")
check("WA1", "previous week avg_quiz_score is NULL: no error logged", not any("null_prev" in e for e in errors),
      [e for e in errors if "null_prev" in e] or "no error")
check("WA2", "previous week NULL: this week's row is still written", r is not None and r["avg_quiz_score"] == 60.0,
      r and r["avg_quiz_score"])
fv = next(s for s in supabase.db["students"] if s["student_id"] == "null_prev").get("vark_feature_vector")
check("WA3", "previous week NULL: vark_feature_vector is still rebuilt", bool(fv) and "F01" in fv, fv)
r = row("rerun")
check("WA4", "same-week re-run compares with the previous week (50), not this week's own row (90)",
      r is not None and r["score_trend"] == "improving", r and r["score_trend"])
r = row("null_quiz")
check("WA5", "a quiz with NULL score_pct is left out of the mean", r is not None and r["avg_quiz_score"] == 70.0,
      r and r["avg_quiz_score"])
r = row("first_week")
check("WA6", "no previous week and no quizzes: row written, trend flat",
      r is not None and r["avg_quiz_score"] == 0.0 and r["score_trend"] == "flat", r and (r["avg_quiz_score"], r["score_trend"]))
r = row("drop")
check("WA7", "80 -> 60 is labelled declining", r is not None and r["score_trend"] == "declining", r and r["score_trend"])
check("WA8", "no 'Weekly agg failed' errors for any student", not errors, errors or "none")

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

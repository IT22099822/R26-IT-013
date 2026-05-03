"""Unit tests for C4 (dropout_service.py, coordinator.py) with an in-memory Supabase stub.
Run from the backend repo root:  python tests/test_c4_unit.py"""
import os as _os, sys as _sys
_ROOT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)   # run from any folder: imports and ml_models/ resolve from the repo root
import asyncio, copy, sys, types
from datetime import datetime, timedelta
import pytz
COLOMBO = pytz.timezone("Asia/Colombo")

class _Res:
    def __init__(self, data): self.data = data
class _Not:
    def __init__(self, q): self.q = q
    def is_(self, col, val): self.q.filters.append(lambda r: r.get(col) is not None); return self.q
class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.mode, self.payload = db, table, [], "select", None
        self._order, self._limit = None, None
        self.not_ = _Not(self)
    def select(self, *a, **k): self.mode = "select"; return self
    def insert(self, payload): self.mode = "insert"; self.payload = payload; return self
    def update(self, payload): self.mode = "update"; self.payload = payload; return self
    def eq(self, k, v): self.filters.append(lambda r: r.get(k) == v); return self
    def is_(self, col, val): self.filters.append(lambda r: r.get(col) is None); return self
    def gte(self, k, v): self.filters.append(lambda r: r.get(k) is not None and r.get(k) >= v); return self
    def lte(self, k, v): self.filters.append(lambda r: r.get(k) is not None and r.get(k) <= v); return self
    def in_(self, k, vs): self.filters.append(lambda r: r.get(k) in vs); return self
    def order(self, col, desc=False): self._order = (col, desc); return self
    def limit(self, n): self._limit = n; return self
    def execute(self):
        tbl = self.db.setdefault(self.table, [])
        if self.mode == "insert":
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

from services.dropout_service import DropoutService  # noqa: E402
from services.coordinator import CoordinatorService, RISK_THRESHOLD, COOLDOWN_DAYS  # noqa: E402
ds, co = DropoutService(), CoordinatorService()
results = []
def check(uid, desc, ok, got):
    results.append(ok); print(f"{uid:5s} {'PASS' if ok else 'FAIL'}  {desc}  -> {got}")
def wk(week, **kw):
    base = dict(student_id="s1", week_number=week, sessions_count=4, total_time_min=120, units_completed=2,
                quizzes_attempted=3, avg_quiz_score=70.0, completion_velocity=1.0, quiz_abandon_rate=0.1,
                skip_rate=0.05, days_since_login=1, max_login_gap_days=2, bkt_mastery_snapshot='{"F01":0.9,"F02":0.5}',
                current_gaps_snapshot='{"F03","F04"}', irt_theta_snapshot=0.3, score_trend="flat",
                engagement_level="green")
    base.update(kw); return base
def reset(students=None, weekly=None):
    supabase.db.clear()
    supabase.db["students"] = students or [dict(student_id="s1", dropout_risk_score=None, intervention_group="treatment",
                                               risk_trend=None, primary_risk_reason=None, last_intervention_at=None)]
    supabase.db["weekly_stats"] = weekly or []
    supabase.db["coordinator_decisions"] = []; supabase.db["interventions"] = []

# --- dropout_service: feature construction --------------------------------------------
rows = [wk(3, sessions_count=1, total_time_min=30, avg_quiz_score=40.0), wk(2, sessions_count=3, total_time_min=90, avg_quiz_score=60.0), wk(1)]
_, v = ds._build_feature_row(rows)
check("UT1", "1-week deltas use previous week", (v["sessions_count_delta"], v["total_time_min_delta"], v["avg_quiz_score_delta"]) == (-2, -60, -20.0),
      (v["sessions_count_delta"], v["total_time_min_delta"], v["avg_quiz_score_delta"]))
check("UT2", "2-week deltas use week two back", (v["sessions_count_delta2"], v["total_time_min_delta2"], v["avg_quiz_score_delta2"]) == (-3, -90, -30.0),
      (v["sessions_count_delta2"], v["total_time_min_delta2"], v["avg_quiz_score_delta2"]))
check("UT3", "snapshots parsed (bkt_avg, n_gaps, theta)", (round(v["bkt_avg"], 3), v["n_gaps"], v["irt_theta"]) == (0.7, 2, 0.3),
      (round(v["bkt_avg"], 3), v["n_gaps"], v["irt_theta"]))
_, v1 = ds._build_feature_row([wk(1)])
check("UT4", "first week: deltas 0, defaults safe", v1["sessions_count_delta"] == 0 and v1["sessions_count_delta2"] == 0 and v1["sustained_silence"] == 0,
      (v1["sessions_count_delta"], v1["sessions_count_delta2"], v1["sustained_silence"]))
_, vs = ds._build_feature_row([wk(5, sessions_count=0), wk(4, sessions_count=0)])
check("UT5", "two silent weeks -> sustained_silence=1", vs["sustained_silence"] == 1, vs["sustained_silence"])
_, ve = ds._build_feature_row([wk(1, bkt_mastery_snapshot="{}", current_gaps_snapshot=None, irt_theta_snapshot=None)])
check("UT6", "empty snapshots -> bkt 0.2, gaps 0, theta 0", (ve["bkt_avg"], ve["n_gaps"], ve["irt_theta"]) == (0.2, 0, 0.0), (ve["bkt_avg"], ve["n_gaps"], ve["irt_theta"]))
row, _ = ds._build_feature_row(rows)
check("UT7", "feature row matches model's 21 inputs, in order", len(row) == 21 == len(ds.feature_names), len(row))

# --- dropout_service: scoring, trend, reason --------------------------------------------
reset(weekly=rows)
s1 = asyncio.run(ds.score_student("s1")); st = supabase.db["students"][0]
check("UT8", "score in [0,1] written with reason; first trend 'stable'",
      0 <= s1 <= 1 and st["dropout_risk_score"] == round(s1, 4) and st["risk_trend"] == "stable" and bool(st["primary_risk_reason"]),
      (round(s1, 4), st["risk_trend"], st["primary_risk_reason"]))
supabase.db["students"][0]["dropout_risk_score"] = round(s1 - 0.20, 4)
asyncio.run(ds.score_student("s1"))
check("UT9", "score up by > 0.05 -> 'increasing'", supabase.db["students"][0]["risk_trend"] == "increasing", supabase.db["students"][0]["risk_trend"])
supabase.db["students"][0]["dropout_risk_score"] = round(s1 - 0.03, 4)
asyncio.run(ds.score_student("s1"))
check("UT10", "change within 0.05 -> 'stable'", supabase.db["students"][0]["risk_trend"] == "stable", supabase.db["students"][0]["risk_trend"])
reset(weekly=[])
check("UT11", "no weekly rows -> no score (None)", asyncio.run(ds.score_student("s1")) is None, None)

# --- coordinator: three gates -------------------------------------------------------------
def stu(**kw):
    d = dict(student_id="s1", intervention_group="treatment", dropout_risk_score=0.85, risk_trend="increasing",
             primary_risk_reason="quiz scores dropped week-over-week", last_intervention_at=None); d.update(kw); return [d]
reset(stu(intervention_group="control", dropout_risk_score=0.10), [wk(1)])
r = asyncio.run(co.evaluate_dropout_intervention("s1"))
check("UT12", "control group suppressed first, even at low risk", r == "suppressed_control" and supabase.db["coordinator_decisions"][0]["final_decision"] == "intervention_suppressed_control_group" and not supabase.db["interventions"], r)
reset(stu(last_intervention_at=(datetime.now(COLOMBO) - timedelta(days=COOLDOWN_DAYS - 1)).isoformat()), [wk(1)])
r = asyncio.run(co.evaluate_dropout_intervention("s1"))
check("UT13", "messaged 13 days ago -> cooldown", r == "suppressed_cooldown" and not supabase.db["interventions"], r)
reset(stu(dropout_risk_score=RISK_THRESHOLD), [wk(1)])
r = asyncio.run(co.evaluate_dropout_intervention("s1"))
check("UT14", "risk exactly 0.70 -> no action (strictly above required)", r == "no_action_below_threshold", r)
reset(stu(last_intervention_at=(datetime.now(COLOMBO) - timedelta(days=COOLDOWN_DAYS + 1)).isoformat()), [wk(1)])
r = asyncio.run(co.evaluate_dropout_intervention("s1")); iv = supabase.db["interventions"]
check("UT15", "all gates pass -> pending intervention, logged, timestamp set",
      r == "intervention_triggered" and len(iv) == 1 and iv[0]["message_sent"] is None and iv[0]["trigger_criteria"]["week_number"] == 1
      and supabase.db["coordinator_decisions"][-1]["final_decision"] == "intervention_triggered" and supabase.db["students"][0]["last_intervention_at"] is not None, r)
reset(stu(dropout_risk_score=None), [wk(1)])
r = asyncio.run(co.evaluate_dropout_intervention("s1"))
check("UT16", "no risk score yet -> nothing evaluated or logged", r is None and not supabase.db["coordinator_decisions"], r)

# --- coordinator: recovery check -----------------------------------------------------------
now = datetime.now(COLOMBO); sent = now - timedelta(days=8)
reset(stu())
supabase.db["interventions"] = [dict(intervention_id="i1", student_id="s1", sent_at=sent.isoformat(), recovery_checked=None),
                                dict(intervention_id="i2", student_id="s1", sent_at=(now - timedelta(days=2)).isoformat(), recovery_checked=None)]
supabase.db["sessions"] = [dict(session_id="x", student_id="s1", login_at=(sent + timedelta(days=2)).isoformat())]
supabase.db["quiz_results"] = [dict(quiz_result_id="q", student_id="s1", taken_at=(sent + timedelta(days=9)).isoformat())]
supabase.db["unit_progress"] = [dict(id="u", student_id="s1", completed=True, completed_at=(sent + timedelta(days=3)).isoformat())]
checked, later = asyncio.run(co.check_recovery())
i1 = supabase.db["interventions"][0]
check("UT17", "recovery = (login + quiz + unit within 7 days)/3; quiz after day 7 ignored",
      round(i1["recovery_score"], 4) == 0.6667 and i1["login_within_7days"] and not i1["quiz_within_7days"] and i1["unit_within_7days"], i1["recovery_score"])
check("UT18", "intervention sent < 7 days ago left for later", (checked, later) == (1, 1) and supabase.db["interventions"][1].get("recovery_checked") is None, (checked, later))

print(f"\n{sum(results)}/{len(results)} passed"); sys.exit(0 if all(results) else 1)

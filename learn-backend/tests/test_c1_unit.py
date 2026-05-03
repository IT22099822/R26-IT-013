"""Unit tests for C1 v2 (services/vark_classifier.py) with an in-memory Supabase stub
and the real deployed ml_models/vark_model.pkl (trained by vark_train_v2.py).
Run from the backend repo root:  python tests/test_c1_unit.py"""
import asyncio, copy, json, pickle, sys, types, warnings
import os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
os.chdir(ROOT)   # so ml_models/vark_model.pkl resolves from any working directory
warnings.filterwarnings("ignore")


class _Res:
    def __init__(self, data): self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.mode, self.payload = db, table, [], "select", None
    def select(self, *a, **k): self.mode = "select"; return self
    def update(self, payload): self.mode = "update"; self.payload = payload; return self
    def eq(self, k, v): self.filters.append(lambda r: r.get(k) == v); return self
    def execute(self):
        tbl = self.db.setdefault(self.table, [])
        rows = [r for r in tbl if all(f(r) for f in self.filters)]
        if self.mode == "update":
            for r in rows: r.update(copy.deepcopy(self.payload))
            return _Res(rows)
        return _Res(copy.deepcopy(rows))


class FakeSupabase:
    def __init__(self): self.db = {}
    def table(self, name): return _Query(self.db, name)


supabase = FakeSupabase()
db_pkg = types.ModuleType("db"); db_mod = types.ModuleType("db.supabase"); db_mod.supabase = supabase
sys.modules["db"] = db_pkg; sys.modules["db.supabase"] = db_mod

from services.vark_classifier import VarkClassifierService, FEATURE_NAMES, HIGH_CONFIDENCE_THRESHOLD  # noqa: E402

svc = VarkClassifierService()
saved = pickle.load(open("ml_models/vark_model.pkl", "rb"))
results = []


def check(uid, desc, ok, got):
    results.append(ok); print(f"{uid:5s} {'PASS' if ok else 'FAIL'}  {desc}  -> {got}")


# realistic per-lesson behaviour (varies lesson to lesson, like real learners)
VISUAL = ([0.95, 0.9, 0.85, 1.0, 0.7, 0.8, 0.92, 0.6], [0, 1, 0, 2, 1, 0, 0, 1])
MIXED = ([0.6, 0.7, 0.5, 0.4, 0.75, 0.55, 0.62, 0.48], [1, 2, 1, 1, 2, 2, 0, 1])


def fv(videos, audios, as_text=True, n=None):
    pairs = list(zip(videos, audios))[: n or len(videos)]
    nodes = {f"N{i:02d}": {"video_watch_pct": v, "audio_play_count": a, "scroll_depth_pct": 0.65,
                           "revisit_count": 0, "total_time_sec": 900} for i, (v, a) in enumerate(pairs)}
    return json.dumps(nodes) if as_text else nodes


def attempts(sid, per_type=(7, 10)):
    rows = []
    for vt in "VARK":
        c, t = per_type
        rows += [dict(student_id=sid, correct=(k < c), vark_type_served=vt, skipped=False) for k in range(t)]
    return rows


def reset(label, vec, att=None):
    supabase.db.clear()
    supabase.db["students"] = [dict(student_id="s1", vark_questionnaire_label=label, active_vark_label=label,
                                    vark_feature_vector=vec)]
    supabase.db["question_attempts"] = att if att is not None else attempts("s1")


def proba(row):
    X = svc.scaler.transform([row]) if svc.scaler is not None else [row]
    p = svc.model.predict_proba(X)[0]
    return str(svc.model.classes_[p.argmax()]), float(p.max())


# ---- feature construction
reset("R", fv([0.9, 0.9, 0.9, 0.9], [2, 2, 2, 2]),
      [dict(student_id="s1", correct=True, vark_type_served="V", skipped=False),
       dict(student_id="s1", correct=True, vark_type_served="V", skipped=False),
       dict(student_id="s1", correct=False, vark_type_served="V", skipped=False),
       dict(student_id="s1", correct=False, vark_type_served="K", skipped=False),
       dict(student_id="s1", correct=True, vark_type_served="A", skipped=True),
       dict(student_id="s1", correct=True, vark_type_served=None, skipped=False)])
row, lab = svc._build_feature_vector("s1")
check("UT1", "22 features built, same names/order as the trained model (v2)",
      len(row) == 22 and FEATURE_NAMES == saved["feature_names"] and svc.feature_version == 2, len(row))
check("UT2", "video/audio aggregates (avg, max, completion>0.8, audio mean, audio rate)", row[:5] == [0.9, 0.9, 1.0, 2.0, 1.0], row[:5])
check("UT3", "per-type accuracy; skipped & untagged ignored; no data -> 0.5",
      [round(x, 4) for x in row[9:13]] == [0.6667, 0.5, 0.5, 0.0], [round(x, 4) for x in row[9:13]])
check("UT4", "per-lesson shares (heavy video, 2+ audio) computed", (row[13], row[19]) == (1.0, 1.0), (row[13], row[19]))
reset("R", fv(*VISUAL, n=2))
check("UT5", "fewer than 3 lessons visited -> no prediction", svc._build_feature_vector("s1") == (None, None), "None")
reset("R", None)
check("UT6", "no feature vector yet -> no prediction", svc._build_feature_vector("s1") == (None, None), "None")

# ---- decision policy
reset("V", fv(*VISUAL))
pl, pc = proba(svc._build_feature_vector("s1")[0])
out = asyncio.run(svc.recalculate("s1"))
check("UT7", "behaviour agrees with questionnaire -> keep label", pl == "V" and out == "V", (pl, round(pc, 3), out))
reset("R", fv(*VISUAL))
pl, pc = proba(svc._build_feature_vector("s1")[0])
out = asyncio.run(svc.recalculate("s1"))
check("UT8", "disagree with confidence above threshold -> behavioural label", pl == "V" and pc > HIGH_CONFIDENCE_THRESHOLD and out == "V"
      and supabase.db["students"][0]["active_vark_label"] == "V", (pl, round(pc, 3), out))
reset("R", fv(*MIXED))
pl, pc = proba(svc._build_feature_vector("s1")[0])
out = asyncio.run(svc.recalculate("s1"))
check("UT9", "disagree with confidence at/below threshold -> keep questionnaire", pl != "R" and pc <= HIGH_CONFIDENCE_THRESHOLD and out == "R",
      (pl, round(pc, 3), out))
reset("R", fv(*VISUAL, n=2))
out = asyncio.run(svc.recalculate("s1"))
check("UT10", "thin data -> label left unchanged, None returned", out is None and supabase.db["students"][0]["active_vark_label"] == "R", out)
saved_model = svc.model; svc.model = None
reset("R", fv(*VISUAL))
out = asyncio.run(svc.recalculate("s1")); svc.model = saved_model
check("UT11", "model not loaded -> skipped safely", out is None and supabase.db["students"][0]["active_vark_label"] == "R", out)

# ---- the 0.7 threshold itself, with a stub model so the confidence is exact
import numpy as _np
class _StubModel:
    classes_ = _np.array(["A", "K", "R", "V"])
    def __init__(self, p_v): self.p_v = p_v
    def predict_proba(self, X):
        rest = (1 - self.p_v) / 3
        return _np.array([[rest, rest, rest, self.p_v]])
saved_model, saved_scaler = svc.model, svc.scaler
svc.scaler = None
check("UT14", "deployed override threshold is 0.7", HIGH_CONFIDENCE_THRESHOLD == 0.7, HIGH_CONFIDENCE_THRESHOLD)
svc.model = _StubModel(0.65); reset("R", fv(*VISUAL))
out = asyncio.run(svc.recalculate("s1"))
check("UT15", "disagree at confidence 0.65 (overrode under old 0.6) -> keep questionnaire", out == "R"
      and supabase.db["students"][0]["active_vark_label"] == "R", out)
svc.model = _StubModel(0.75); reset("R", fv(*VISUAL))
out = asyncio.run(svc.recalculate("s1"))
check("UT16", "disagree at confidence 0.75 -> behavioural label", out == "V"
      and supabase.db["students"][0]["active_vark_label"] == "V", out)
svc.model, svc.scaler = saved_model, saved_scaler

# ---- serving-format robustness (was a defect in v1)
reset("R", fv(*VISUAL, as_text=False))   # what a json/jsonb column returns through the client
row_d, _ = svc._build_feature_vector("s1")
reset("R", fv(*VISUAL))
row_t, _ = svc._build_feature_vector("s1")
check("UT12", "feature vector as decoded JSON (dict) gives the same features as text", row_d is not None and row_d == row_t, "same" if row_d == row_t else row_d)
reset("R", "not json")
check("UT13", "malformed feature vector -> no prediction, no crash", svc._build_feature_vector("s1") == (None, None), "None")

n_ok = sum(results)
print(f"\n{n_ok}/{len(results)} passed")

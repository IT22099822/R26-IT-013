import json
import os
import pickle
import logging

from db.supabase import supabase

logger = logging.getLogger(__name__)

# Place dropout_model_terminal.pkl (produced by dropout_model.py) here:
#   lean-back-zip/ml_models/dropout_model_terminal.pkl
# Using the TERMINAL model, not the proxy model, as the source for
# dropout_risk_score — it outputs a single "will actually drop out"
# probability, which is what this field is meant to represent. The
# proxy model's 3-class (green/yellow/red) output doesn't map cleanly
# onto one risk score, so it isn't used here.
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml_models", "dropout_model_terminal.pkl")

# The proxy model IS now used, but for something deliberately different
# and lightweight — see engagement_dip_score in score_student() below.
# Loading it is optional: if this file isn't present, core risk scoring
# still works fine, since this indicator was always meant to be an
# addition, never a dependency.
PROXY_MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml_models", "dropout_model_proxy.pkl")

RISK_TREND_THRESHOLD = 0.05  # minimum change in score to call it a real trend, not noise

# Direction each feature needs to move in to be "concerning" — used for
# the primary_risk_reason heuristic below. True = higher is worse.
CONCERNING_IF_HIGH = {
    'days_since_login', 'max_login_gap_days', 'quiz_abandon_rate', 'skip_rate',
    'n_gaps', 'sustained_silence',
}
CONCERNING_IF_LOW = {
    'sessions_count', 'total_time_min', 'units_completed', 'quizzes_attempted',
    'avg_quiz_score', 'completion_velocity', 'bkt_avg', 'irt_theta',
}
CONCERNING_IF_NEGATIVE = {
    'score_trend_num', 'sessions_count_delta', 'total_time_min_delta',
    'avg_quiz_score_delta', 'sessions_count_delta2', 'total_time_min_delta2',
    'avg_quiz_score_delta2',
}

FEATURE_READABLE = {
    'sessions_count': 'low session count',
    'total_time_min': 'low time spent',
    'units_completed': 'few units completed',
    'quizzes_attempted': 'few quizzes attempted',
    'avg_quiz_score': 'low quiz scores',
    'completion_velocity': 'slow completion pace',
    'quiz_abandon_rate': 'high quiz abandonment',
    'skip_rate': 'high question skip rate',
    'days_since_login': 'long time since last login',
    'max_login_gap_days': 'large gap between logins',
    'bkt_avg': 'low overall mastery',
    'n_gaps': 'unresolved knowledge gaps',
    'irt_theta': 'low estimated ability',
    'score_trend_num': 'declining quiz scores',
    'sessions_count_delta': 'sessions dropped week-over-week',
    'total_time_min_delta': 'time spent dropped week-over-week',
    'avg_quiz_score_delta': 'quiz scores dropped week-over-week',
    'sessions_count_delta2': 'sessions declining over 2 weeks',
    'total_time_min_delta2': 'time spent declining over 2 weeks',
    'avg_quiz_score_delta2': 'quiz scores declining over 2 weeks',
    'sustained_silence': 'no activity for 2+ consecutive weeks',
}


def parse_bkt_avg(s):
    """Mean mastery across nodes in a weekly bkt_mastery_snapshot.
    weekly_stats.bkt_mastery_snapshot is a jsonb column, so the Supabase
    client returns it as an already-decoded dict; CSV exports (used for
    training) give it as a JSON string. Accept both; 0.2 (the BKT prior)
    when empty or unusable."""
    if isinstance(s, str):
        if not s or s == '{}':
            return 0.2
        try:
            s = json.loads(s)
        except json.JSONDecodeError:
            return 0.2
    if not isinstance(s, dict) or not s:
        return 0.2
    try:
        return sum(float(v) for v in s.values()) / len(s)
    except (TypeError, ValueError):
        return 0.2


def parse_n_gaps(s):
    """Number of gaps in current_gaps_snapshot: a text[] column (list from
    the Supabase client) or a '{F01,F02}' string from CSV exports."""
    if not s:
        return 0
    if isinstance(s, (list, tuple)):
        return len([x for x in s if str(x).strip()])
    inner = str(s).strip().strip('{}')
    if not inner:
        return 0
    return len([x for x in inner.split(',') if x.strip()])


class DropoutService:
    def __init__(self):
        self.model = None
        self.feature_names = None
        self.proxy_model = None
        self.proxy_feature_names = None
        self._proxy_red_index = None
        self._load()

    def _load(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
            self.model = data["model"]
            self.feature_names = data["feature_names"]
            logger.info(f"Dropout model loaded from {MODEL_PATH}")
        except FileNotFoundError:
            logger.error(f"dropout_model_terminal.pkl not found at {MODEL_PATH} — "
                         f"dropout scoring disabled until it's deployed")
        except Exception as e:
            logger.error(f"Failed to load dropout model: {e}")

        try:
            with open(PROXY_MODEL_PATH, "rb") as f:
                proxy_data = pickle.load(f)
            self.proxy_model = proxy_data["model"]
            self.proxy_feature_names = proxy_data["feature_names"]
            self._proxy_red_index = list(self.proxy_model.classes_).index("red")
            logger.info(f"Proxy engagement model loaded from {PROXY_MODEL_PATH}")
        except FileNotFoundError:
            logger.warning(f"dropout_model_proxy.pkl not found — engagement_dip_score "
                            f"will be skipped (optional; core risk scoring is unaffected)")
        except Exception as e:
            logger.error(f"Failed to load proxy engagement model: {e}")

    def _build_feature_row(self, rows):
        """rows: last up-to-3 weekly_stats rows for one student, ordered
        MOST RECENT FIRST. Reconstructs the exact feature set
        dropout_model.py trained on, including the 1-week and 2-week
        deltas and the sustained_silence flag."""
        cur = rows[0]
        prev1 = rows[1] if len(rows) > 1 else None
        prev2 = rows[2] if len(rows) > 2 else None

        bkt_avg = parse_bkt_avg(cur.get("bkt_mastery_snapshot"))
        n_gaps = parse_n_gaps(cur.get("current_gaps_snapshot"))
        irt_theta = cur.get("irt_theta_snapshot") or 0.0
        trend_map = {"improving": 1, "flat": 0, "declining": -1}
        score_trend_num = trend_map.get(cur.get("score_trend"), 0)

        def delta(field, ref):
            if ref is None:
                return 0.0
            return (cur.get(field) or 0) - (ref.get(field) or 0)

        sessions_count = cur.get("sessions_count") or 0
        prev1_sessions = (prev1.get("sessions_count") or 0) if prev1 else None
        sustained_silence = int(sessions_count == 0 and prev1_sessions == 0) if prev1 else 0

        values = {
            'sessions_count': sessions_count,
            'total_time_min': cur.get("total_time_min") or 0,
            'units_completed': cur.get("units_completed") or 0,
            'quizzes_attempted': cur.get("quizzes_attempted") or 0,
            'avg_quiz_score': cur.get("avg_quiz_score") or 0,
            'completion_velocity': cur.get("completion_velocity") or 0,
            'quiz_abandon_rate': cur.get("quiz_abandon_rate") or 0,
            'skip_rate': cur.get("skip_rate") or 0,
            'days_since_login': cur.get("days_since_login") or 0,
            'max_login_gap_days': cur.get("max_login_gap_days") or 0,
            'bkt_avg': bkt_avg,
            'n_gaps': n_gaps,
            'irt_theta': irt_theta,
            'score_trend_num': score_trend_num,
            'sessions_count_delta': delta("sessions_count", prev1),
            'total_time_min_delta': delta("total_time_min", prev1),
            'avg_quiz_score_delta': delta("avg_quiz_score", prev1),
            'sessions_count_delta2': delta("sessions_count", prev2),
            'total_time_min_delta2': delta("total_time_min", prev2),
            'avg_quiz_score_delta2': delta("avg_quiz_score", prev2),
            'sustained_silence': sustained_silence,
        }
        return [values[f] for f in self.feature_names], values

    def _explain(self, values):
        """Walks the model's globally most-important features and
        returns the first one where THIS student's value looks
        concerning — a simple, explainable heuristic rather than a
        proper per-instance method like SHAP (which would add a new
        dependency; worth revisiting later if that precision matters)."""
        ranked = sorted(zip(self.feature_names, self.model.feature_importances_),
                         key=lambda x: -x[1])
        for fname, _ in ranked:
            v = values[fname]
            concerning = (
                (fname in CONCERNING_IF_HIGH and v > 0) or
                (fname in CONCERNING_IF_LOW and v <= 0) or
                (fname in CONCERNING_IF_NEGATIVE and v < 0)
            )
            if concerning:
                return FEATURE_READABLE.get(fname, fname)
        return FEATURE_READABLE.get(ranked[0][0], ranked[0][0])

    async def score_student(self, student_id: str):
        """Scores one student's latest weekly_stats row, writes
        dropout_risk_score/risk_trend/primary_risk_reason back to
        students. Returns the new score, or None if there wasn't
        enough data or the model isn't loaded."""
        if self.model is None:
            logger.error(f"Dropout scoring skipped for {student_id}: model not loaded")
            return None

        rows = supabase.table("weekly_stats").select("*").eq(
            "student_id", student_id
        ).order("week_number", desc=True).limit(3).execute().data

        if not rows:
            return None

        row, values = self._build_feature_row(rows)
        new_score = float(self.model.predict_proba([row])[0][1])
        reason = self._explain(values)

        old = supabase.table("students").select("dropout_risk_score").eq(
            "student_id", student_id
        ).execute().data
        old_score = old[0]["dropout_risk_score"] if old and old[0].get("dropout_risk_score") is not None else None

        if old_score is None:
            trend = "stable"
        elif new_score > old_score + RISK_TREND_THRESHOLD:
            trend = "increasing"
        elif new_score < old_score - RISK_TREND_THRESHOLD:
            trend = "decreasing"
        else:
            trend = "stable"

        supabase.table("students").update({
            "dropout_risk_score": round(new_score, 4),
            "risk_trend": trend,
            "primary_risk_reason": reason,
        }).eq("student_id", student_id).execute()

        # Lightweight, admin-facing-only indicator from the proxy model —
        # NEVER feeds coordinator.py's intervention logic, and failure
        # here should never break real risk scoring, hence the separate
        # try/except and the fact this runs after the real update above.
        if self.proxy_model is not None:
            try:
                proxy_row = [values[f] for f in self.proxy_feature_names]
                dip_score = float(self.proxy_model.predict_proba([proxy_row])[0][self._proxy_red_index])
                supabase.table("students").update({
                    "engagement_dip_score": round(dip_score, 4)
                }).eq("student_id", student_id).execute()
            except Exception as e:
                logger.error(f"Engagement-dip scoring failed for {student_id} (non-critical): {e}")

        return new_score


dropout_service = DropoutService()
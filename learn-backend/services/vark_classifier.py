import json
import os
import pickle
import logging

from db.supabase import supabase

logger = logging.getLogger(__name__)

# Place vark_model.pkl (produced by vark_train_v2.py) here, relative to
# the backend root — create the folder if it doesn't exist yet:
#   lean-back-zip/ml_models/vark_model.pkl
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "ml_models", "vark_model.pkl")

MIN_NODES_VISITED = 3          # matches vark_train_v2.py's exclusion threshold —
                                # a thinner feature vector isn't trustworthy
HIGH_CONFIDENCE_THRESHOLD = 0.7  # only lean behavioral over questionnaire when the
                                  # classifier is genuinely confident. Raised from 0.6:
                                  # in 10x5 repeated CV the model agrees with the
                                  # questionnaire 82.8% of the time above 0.7 (56% of
                                  # learners) vs 78.6% above 0.6, and the 20,000-learner
                                  # policy simulation showed fewer wrong overrides

# v1 features (13) — still used if an old v1 vark_model.pkl is deployed
FEATURE_NAMES_V1 = [
    'avg_video_watch_pct', 'max_video_watch_pct', 'video_completion_rate',
    'avg_audio_play_count', 'audio_engagement_rate',
    'avg_scroll_depth_pct', 'avg_revisit_count', 'avg_total_time_sec',
    'n_nodes_visited',
    'acc_V', 'acc_A', 'acc_R', 'acc_K',
]
# v2 adds 9 per-lesson distribution features (see vark_train_v2.py)
FEATURE_NAMES = FEATURE_NAMES_V1 + [
    'share_video_heavy', 'share_video_light',
    'median_video_watch_pct', 'std_video_watch_pct',
    'share_audio_none', 'share_audio_once', 'share_audio_2plus', 'share_audio_3plus',
    'share_low_media',
]


def _as_dict(value):
    """vark_feature_vector may arrive as a JSON string (text column / CSV
    export) or as an already-decoded dict (json/jsonb column through the
    Supabase client). Accept both; return None for anything unusable."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _std(values):
    n = len(values)
    mean = sum(values) / n
    return (sum((v - mean) ** 2 for v in values) / n) ** 0.5   # population SD, same as numpy .std()


class VarkClassifierService:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.model_name = None
        self.feature_version = 1
        self._load()

    def _load(self):
        try:
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
            self.model = data["model"]
            self.scaler = data.get("scaler")
            self.model_name = data["model_name"]
            self.feature_version = data.get("feature_version", 1)
            logger.info(f"VARK classifier loaded ({self.model_name}, feature v{self.feature_version}) from {MODEL_PATH}")
        except FileNotFoundError:
            logger.error(f"vark_model.pkl not found at {MODEL_PATH} — "
                         f"VARK classification disabled until it's deployed")
        except Exception as e:
            logger.error(f"Failed to load VARK model: {e}")

    def _build_feature_vector(self, student_id: str):
        """Rebuilds the EXACT feature vector vark_train_v2.py used — must
        stay in sync with that script if the feature set ever changes."""
        student = supabase.table("students").select(
            "vark_feature_vector,vark_questionnaire_label"
        ).eq("student_id", student_id).execute().data

        if not student or not student[0].get("vark_feature_vector"):
            return None, None

        fv = _as_dict(student[0]["vark_feature_vector"])
        if fv is None:
            return None, None

        if len(fv) < MIN_NODES_VISITED:
            return None, None

        videos = [v.get("video_watch_pct") or 0 for v in fv.values()]
        audios = [v.get("audio_play_count") or 0 for v in fv.values()]
        scrolls = [v.get("scroll_depth_pct") or 0 for v in fv.values()]
        revisits = [v.get("revisit_count") or 0 for v in fv.values()]
        times = [v.get("total_time_sec") or 0 for v in fv.values()]
        n = len(fv)

        attempts = supabase.table("question_attempts").select(
            "correct,vark_type_served,skipped"
        ).eq("student_id", student_id).execute().data

        vark_totals = {vt: [0, 0] for vt in ["V", "A", "R", "K"]}
        for a in attempts:
            if a.get("skipped") or not a.get("vark_type_served"):
                continue
            vt = a["vark_type_served"]
            if vt not in vark_totals:
                continue
            vark_totals[vt][1] += 1
            if a.get("correct"):
                vark_totals[vt][0] += 1
        vark_acc = {vt: (c / t if t > 0 else 0.5) for vt, (c, t) in vark_totals.items()}

        row = [
            sum(videos) / n, max(videos), sum(1 for v in videos if v > 0.8) / n,
            sum(audios) / n, sum(1 for a_ in audios if a_ > 0) / n,
            sum(scrolls) / n, sum(revisits) / n, sum(times) / n,
            n,
            vark_acc["V"], vark_acc["A"], vark_acc["R"], vark_acc["K"],
        ]
        if self.feature_version >= 2:
            row += [
                sum(1 for v in videos if v > 0.7) / n,
                sum(1 for v in videos if v < 0.5) / n,
                _median(videos),
                _std(videos),
                sum(1 for a_ in audios if a_ == 0) / n,
                sum(1 for a_ in audios if a_ == 1) / n,
                sum(1 for a_ in audios if a_ >= 2) / n,
                sum(1 for a_ in audios if a_ >= 3) / n,
                sum(1 for v, a_ in zip(videos, audios) if v < 0.5 and a_ <= 1) / n,
            ]
        return row, student[0].get("vark_questionnaire_label")

    async def recalculate(self, student_id: str):
        """Predicts active_vark_label for one student and writes it back.
        Returns the label written, or None if there wasn't enough data
        or the model isn't loaded."""
        if self.model is None:
            logger.error(f"VARK recalculate skipped for {student_id}: model not loaded")
            return None

        row, questionnaire_label = self._build_feature_vector(student_id)
        if row is None:
            return None  # not enough behavior data yet — leave as-is

        X = [row]
        if self.scaler is not None:
            X = self.scaler.transform(X)

        probs = self.model.predict_proba(X)[0]
        classes = self.model.classes_
        best_idx = probs.argmax()
        predicted_label = str(classes[best_idx])
        confidence = float(probs[best_idx])

        # Policy: agree -> use it; disagree + confidence > 0.7 ->
        # lean behavioral; disagree + low confidence -> keep questionnaire
        # label. (Mismatch/confidence aren't persisted as separate columns
        # yet — that needs a schema addition; flagging here rather than
        # silently reusing vark_feature_vector, which weekly_agg.py fully
        # overwrites every week and would silently lose this data.)
        if predicted_label == questionnaire_label:
            active_label = questionnaire_label
        elif confidence > HIGH_CONFIDENCE_THRESHOLD:
            active_label = predicted_label
        else:
            active_label = questionnaire_label

        supabase.table("students").update({
            "active_vark_label": active_label
        }).eq("student_id", student_id).execute()

        return active_label


vark_classifier_service = VarkClassifierService()

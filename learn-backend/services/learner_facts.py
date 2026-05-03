"""Real, per-learner progress facts shared by the weekly intervention message
and the dropout coach chat.

Everything here is computed from the learner's own rows using the same math
the live services run (services/bkt.py, services/irt.py), so any number the
LLM is given is a number the platform can actually stand behind. The LLM is
never asked to estimate or invent progress figures."""
import logging

from db.supabase import supabase
from services.bkt import BKTService

logger = logging.getLogger(__name__)

VARK_FULL_NAME = {"V": "Visual", "A": "Auditory", "R": "Reading/Writing", "K": "Kinesthetic"}
BKT_PARAMS = BKTService.DEFAULT_PARAMS
DEFAULT_THRESHOLD = BKTService.DEFAULT_MASTERY_THRESHOLD
MAX_QUESTIONS = 25          # beyond this, "about N" stops being a useful message


def bkt_after_correct(p: float, params: dict = BKT_PARAMS) -> float:
    """One correct answer through the live BKT update (same as BKTService.update)."""
    num = p * (1 - params["p_s"])
    den = num + (1 - p) * params["p_g"]
    post = num / den
    return round(post + (1 - post) * params["p_t"], 4)


def questions_to_mastery(p: float, threshold: float = DEFAULT_THRESHOLD,
                         params: dict = BKT_PARAMS, cap: int = MAX_QUESTIONS) -> int:
    """How many more correct answers in a row take mastery from p to the
    unlock threshold, under the deployed BKT parameters. 0 if already there;
    `cap` if it would take longer than that (reported as 'cap or more')."""
    n = 0
    while p < threshold and n < cap:
        p = bkt_after_correct(p, params)
        n += 1
    return n


def _pct(x) -> int:
    return int(round((x or 0) * 100))


def build_learner_facts(student: dict) -> dict:
    """student: a full `students` row. Returns plain, interpreted facts — no
    raw model internals such as theta values. The IRT projection is added by
    build_learner_facts_async (it needs the event loop)."""
    sid = student["student_id"]
    raw_label = student.get("active_vark_label") or student.get("vark_questionnaire_label") or "R"
    mastery = student.get("bkt_mastery") or {}
    mastered = student.get("nodes_mastered") or []
    gaps = student.get("current_gaps") or []

    nodes = supabase.table("content_nodes").select(
        "node_id,skill_name,mastery_threshold").execute().data or []
    by_id = {n["node_id"]: n for n in nodes}

    def skill(node_id):
        n = by_id.get(node_id) or {}
        p = mastery.get(node_id, BKT_PARAMS["p_l0"])
        thr = n.get("mastery_threshold") if n.get("mastery_threshold") is not None else DEFAULT_THRESHOLD
        return {"node_id": node_id, "name": n.get("skill_name") or node_id,
                "mastery_pct": _pct(p), "questions_to_master": questions_to_mastery(p, thr)}

    active_id = student.get("current_active_node")
    active = skill(active_id) if active_id and active_id not in mastered else None

    weekly = supabase.table("weekly_stats").select(
        "week_number,sessions_count,quizzes_attempted,avg_quiz_score,units_completed,engagement_level"
    ).eq("student_id", sid).order("week_number", desc=True).limit(1).execute().data
    wk = weekly[0] if weekly else {}

    return {
        "learning_style": VARK_FULL_NAME.get(raw_label, "Reading/Writing"),
        "lessons_completed": len(mastered),
        "lessons_total": len(nodes) or 35,
        "recently_completed": [by_id.get(n, {}).get("skill_name", n) for n in mastered[-3:]][::-1],
        "active_lesson": active,
        "weak_skills": [skill(g) for g in gaps[:3]],
        "last_week": {
            "sessions": wk.get("sessions_count", 0) or 0,
            "quizzes": wk.get("quizzes_attempted", 0) or 0,
            "avg_quiz_score": round(wk["avg_quiz_score"]) if wk.get("avg_quiz_score") is not None else None,
            "lessons_completed": wk.get("units_completed", 0) or 0,
            "engagement": wk.get("engagement_level") or "unknown",
        },
        "days_since_login": student.get("days_since_last_login"),
        "projection": None,
        "risk_reason": student.get("primary_risk_reason") or None,
        "risk_trend": student.get("risk_trend") or None,
    }


async def build_learner_facts_async(student: dict) -> dict:
    """Same as build_learner_facts, for callers already inside an event loop
    (FastAPI routes, the weekly pipeline)."""
    facts = build_learner_facts(student)
    try:
        from services.irt import irt_service
        proj = await irt_service.project_improvement(student["student_id"], "easy", 10)
        if proj and proj.get("delta", 0) > 0:
            facts["projection"] = {"count": 10, "band": "easy", "scale_pct": round(proj["delta"] / 8 * 100)}
    except Exception as e:
        logger.warning(f"ability projection unavailable for {student['student_id']}: {e}")
    return facts


def _qtm(n: int) -> str:
    return f"{n}+" if n >= MAX_QUESTIONS else str(n)


def facts_to_text(f: dict) -> str:
    """The facts as plain lines for an LLM prompt."""
    lw = f["last_week"]
    lines = [
        f"- Learning style: {f['learning_style']}",
        f"- Lessons completed: {f['lessons_completed']} of {f['lessons_total']}",
    ]
    if f["recently_completed"]:
        lines.append(f"- Most recently completed: {', '.join(f['recently_completed'])}")
    if f["active_lesson"]:
        a = f["active_lesson"]
        lines.append(f"- Current lesson: {a['name']} (mastery {a['mastery_pct']}%; about "
                     f"{_qtm(a['questions_to_master'])} more correct answers to master it)")
    for g in f["weak_skills"]:
        lines.append(f"- Weak skill: {g['name']} (mastery {g['mastery_pct']}%; about "
                     f"{_qtm(g['questions_to_master'])} more correct answers to master it)")
    score = f"{lw['avg_quiz_score']}% average quiz score" if lw["avg_quiz_score"] is not None else "no quiz score"
    lines.append(f"- Last week: {lw['sessions']} sessions, {lw['quizzes']} quizzes, {score}, "
                 f"{lw['lessons_completed']} lessons completed; engagement {lw['engagement']}")
    if f["days_since_login"] is not None:
        lines.append(f"- Days since last login: {f['days_since_login']}")
    if f["projection"]:
        p = f["projection"]
        lines.append(f"- If they answer {p['count']} easy questions correctly, their ability score "
                     f"rises by about {p['scale_pct']}% of the full scale")
    if f["risk_reason"]:
        lines.append(f"- Main reason the platform flagged them: {f['risk_reason']}"
                     + (f" (trend: {f['risk_trend']})" if f["risk_trend"] else ""))
    return "\n".join(lines)

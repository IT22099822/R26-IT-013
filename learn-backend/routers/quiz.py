from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from db.supabase import supabase
from routers.deps import get_current_student
import logging
import math


logger = logging.getLogger(__name__)


def apply_relative_difficulty(questions: list, theta: float):
    """Difficulty label RELATIVE to this student's actual ability, not a
    fixed universal cutoff — 'easy' means 'easy for you given what we
    know about you'. Mutates each question dict in place. Used
    everywhere questions get returned to the frontend — the standard
    practice set, generated on-demand practice, and generated post-test
    retakes — so this can't silently drift out of sync across the three
    call sites the way it did before this was extracted."""
    for q in questions:
        diff = q.get("difficulty_tag")
        if diff is None or diff == 0:
            q["relative_difficulty"] = "unrated"
        else:
            p_correct = 1.0 / (1.0 + math.exp(-(theta - diff)))
            if p_correct > 0.70:
                q["relative_difficulty"] = "easy"
            elif p_correct < 0.40:
                q["relative_difficulty"] = "hard"
            else:
                q["relative_difficulty"] = "medium"
router = APIRouter()


# ─── Models ───────────────────────────────────────────────────────────────────

class AttemptRequest(BaseModel):
    session_id: str
    question_id: str
    node_id: str
    selected_option: str
    time_taken_sec: Optional[int] = None
    skipped: Optional[bool] = False


class SubmitRequest(BaseModel):
    session_id: str
    node_id: str
    attempt_number: Optional[int] = 1
    score_pct: float
    correct_count: int
    total_questions: int
    time_taken_sec: Optional[int] = None


class AbandonRequest(BaseModel):
    session_id: str
    node_id: str


class AnchorAnswerItem(BaseModel):
    question_id: str
    selected_option: str
    time_taken_sec: Optional[int] = None


class AnchorSubmitRequest(BaseModel):
    session_id: str
    node_id: str
    test_type: str
    answers: List[AnchorAnswerItem]


# ─── Shared select columns ────────────────────────────────────────────────────

QUESTION_COLS = (
    "question_id,question_text,"
    "option_a,option_b,option_c,option_d,"
    "difficulty_tag,vark_type,"
    "image_url,question_audio_url"
)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{node_id}")
async def get_quiz(node_id: str, student=Depends(get_current_student)):
    node = supabase.table("content_nodes").select("questions_ready").eq("node_id", node_id).execute()
    if not node.data or not node.data[0].get("questions_ready"):
        return {"questions": [], "ready": False}

    questions = supabase.table("questions").select(QUESTION_COLS)\
        .eq("node_id", node_id)\
        .eq("question_type", "practice")\
        .eq("status", "published")\
        .execute()

    # Order practice questions by fit to this student — NOT a filter,
    # still returns every question, just puts the best-matched ones
    # first. Anchor/post-test are untouched on purpose: those are the
    # fixed measurement instruments the IRT calibration pipeline
    # depends on staying consistent across students.
    target_difficulty = student.get("current_target_difficulty")
    if target_difficulty is None:
        target_difficulty = 0.0
    theta = student.get("irt_theta")
    if theta is None:
        theta = 0.0
    vark_label = student.get("active_vark_label") or student.get("vark_questionnaire_label")

    def fit_score(q):
        diff = q.get("difficulty_tag")
        diff_gap = abs(diff - target_difficulty) if diff is not None else 999.0
        vark_mismatch = 0 if (vark_label and q.get("vark_type") == vark_label) else 1
        return (diff_gap, vark_mismatch)

    ordered = sorted(questions.data, key=fit_score)
    apply_relative_difficulty(ordered, theta)

    return {"questions": ordered, "ready": True}


@router.post("/attempt")
async def record_attempt(body: AttemptRequest, student=Depends(get_current_student)):
    question = supabase.table("questions")\
        .select("correct_option,difficulty_tag,vark_type")\
        .eq("question_id", body.question_id)\
        .execute()
    if not question.data:
        raise HTTPException(status_code=404, detail="Question not found")

    q = question.data[0]
    correct = body.selected_option.upper() == q["correct_option"].upper()

    try:
        supabase.table("question_attempts").insert({
            "student_id": student["student_id"],
            "session_id": body.session_id,
            "question_id": body.question_id,
            "node_id": body.node_id,
            "correct": correct,
            "selected_option": body.selected_option,
            "correct_option": q["correct_option"],
            "time_taken_sec": body.time_taken_sec,
            "skipped": body.skipped,
            "difficulty_tag": q["difficulty_tag"],
            "vark_type_served": q["vark_type"],
            "attempted_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.warning(f"Duplicate attempt ignored: {e}")

    supabase.table("interaction_log").insert({
        "student_id": student["student_id"],
        "session_id": body.session_id,
        "event_type": "question_attempt",
        "entity_id": body.question_id,
        "value": 1.0 if correct else 0.0,
        "metadata": {"node_id": body.node_id, "difficulty_tag": q["difficulty_tag"]}
    }).execute()

    try:
        from services.bkt import bkt_service
        from services.irt import irt_service
        await bkt_service.update(student["student_id"], body.node_id, int(correct))
        await irt_service.update(student["student_id"], q["difficulty_tag"] or 0.0, int(correct))
    except Exception as e:
        logger.error(f"BKT/IRT update failed: {e}")

    return {"correct": correct, "correct_option": q["correct_option"]}


@router.post("/submit")
async def submit_quiz(body: SubmitRequest, student=Depends(get_current_student)):
    supabase.table("quiz_results").insert({
        "student_id": student["student_id"],
        "session_id": body.session_id,
        "node_id": body.node_id,
        "attempt_number": body.attempt_number,
        "score_pct": body.score_pct,
        "correct_count": body.correct_count,
        "total_questions": body.total_questions,
        "time_taken_sec": body.time_taken_sec,
        "completed": True,
        "abandoned": False,
        "taken_at": datetime.utcnow().isoformat()
    }).execute()

    supabase.table("interaction_log").insert({
        "student_id": student["student_id"],
        "session_id": body.session_id,
        "event_type": "quiz_submit",
        "entity_id": body.node_id,
        "value": body.score_pct,
        "metadata": {}
    }).execute()

    if body.score_pct >= 70:
        supabase.table("unit_progress").upsert({
            "student_id": student["student_id"],
            "node_id": body.node_id,
            "completed": True,
            "completed_at": datetime.utcnow().isoformat()
        }, on_conflict="student_id,node_id").execute()

    return {"status": "submitted", "score_pct": body.score_pct}


@router.post("/abandon")
async def abandon_quiz(body: AbandonRequest, student=Depends(get_current_student)):
    supabase.table("quiz_results").insert({
        "student_id": student["student_id"],
        "session_id": body.session_id,
        "node_id": body.node_id,
        "completed": False,
        "abandoned": True,
        "taken_at": datetime.utcnow().isoformat()
    }).execute()

    supabase.table("interaction_log").insert({
        "student_id": student["student_id"],
        "session_id": body.session_id,
        "event_type": "quiz_abandon",
        "entity_id": body.node_id,
        "value": None,
        "metadata": {}
    }).execute()

    return {"status": "abandoned"}


class PracticeRequestBody(BaseModel):
    difficulty_band: str  # 'easy' | 'just_right' | 'hard' | 'impossible'
    count: Optional[int] = 5


@router.post("/{node_id}/practice-request")
async def request_practice(node_id: str, body: PracticeRequestBody, student=Depends(get_current_student)):
    """On-demand practice at a difficulty the student explicitly picks
    — not a fixed universal 'hard', but hard/easy/etc. relative to
    their own current ability."""
    from services.question_generator import question_generator_service

    if body.difficulty_band not in ("easy", "just_right", "hard", "impossible"):
        raise HTTPException(status_code=400, detail="Invalid difficulty_band")

    theta = student.get("irt_theta") or 0.0
    vark_label = student.get("active_vark_label") or student.get("vark_questionnaire_label")

    try:
        generated = await question_generator_service.generate_questions(
            node_id=node_id, question_type="practice", band=body.difficulty_band,
            count=min(max(body.count or 5, 1), 10), theta=theta, vark_label=vark_label
        )
    except Exception as e:
        logger.error(f"On-demand practice generation failed: {e}")
        generated = []

    apply_relative_difficulty(generated, theta)
    return {"questions": generated, "generation_failed": len(generated) == 0}


@router.get("/{node_id}/anchor")
async def get_anchor_questions(
    node_id: str,
    test_type: str = "pre",
    student=Depends(get_current_student)
):
    existing = supabase.table("anchor_scores")\
        .select("attempt_number")\
        .eq("student_id", student["student_id"])\
        .eq("node_id", node_id)\
        .eq("test_type", test_type)\
        .execute()

    attempt_numbers = [r.get("attempt_number", 1) for r in existing.data] if existing.data else []
    max_attempt = max(attempt_numbers) if attempt_numbers else 0
    next_attempt = max_attempt + 1

    # Pre-test is a one-time diagnostic before the lesson — retaking it
    # doesn't make pedagogical sense, so this restriction stays.
    if test_type == "pre" and max_attempt >= 1:
        return {"questions": [], "already_done": True}

    q_type = "anchor" if test_type == "pre" else "post_test"

    if test_type == "post" and max_attempt >= 1:
        # Retake — generate fresh questions instead of reusing the real
        # calibrated pool. Targeted at "just right" for this student's
        # CURRENT ability, not a fixed universal difficulty.
        from services.question_generator import question_generator_service
        theta = student.get("irt_theta") or 0.0
        vark_label = student.get("active_vark_label") or student.get("vark_questionnaire_label")
        try:
            generated = await question_generator_service.generate_questions(
                node_id=node_id, question_type="post_test", band="just_right",
                count=5, theta=theta, vark_label=vark_label
            )
        except Exception as e:
            logger.error(f"Post-test question generation failed: {e}")
            generated = []
        if not generated:
            return {"questions": [], "already_done": False, "generation_failed": True}
        apply_relative_difficulty(generated, theta)
        return {"questions": generated, "already_done": False, "attempt_number": next_attempt}

    # First attempt (or any pre-test) — the real, calibrated pool
    questions = supabase.table("questions").select(QUESTION_COLS)\
        .eq("node_id", node_id)\
        .eq("question_type", q_type)\
        .eq("status", "published")\
        .execute()

    return {"questions": questions.data, "already_done": False, "attempt_number": next_attempt}


@router.post("/anchor-submit")
async def submit_anchor(body: AnchorSubmitRequest, student=Depends(get_current_student)):
    from services.bkt import bkt_service
    from services.irt import irt_service

    existing = supabase.table("anchor_scores").select("attempt_number")\
        .eq("student_id", student["student_id"]).eq("node_id", body.node_id)\
        .eq("test_type", body.test_type).execute()
    prior_attempts = [r.get("attempt_number", 1) for r in existing.data] if existing.data else []
    this_attempt = (max(prior_attempts) if prior_attempts else 0) + 1

    rows = []
    feedback = []
    for a in body.answers:
        question = supabase.table("questions")\
            .select("correct_option,difficulty_tag,explanation")\
            .eq("question_id", a.question_id)\
            .execute()
        if not question.data:
            continue
        q = question.data[0]
        correct = a.selected_option.upper() == q["correct_option"].upper()
        rows.append({
            "student_id": student["student_id"],
            "node_id": body.node_id,
            "test_type": body.test_type,
            "question_id": a.question_id,
            "correct": correct,
            "time_taken_sec": a.time_taken_sec,
            "taken_at": datetime.utcnow().isoformat(),
            "attempt_number": this_attempt,
        })
        # Feedback (answer reveal + explanation) is only ever built for
        # retake attempts (attempt_number > 1) using generated
        # questions — attempt 1's real calibrated pool stays
        # feedback-free, protecting the IRT calibration it's used for.
        if body.test_type == "post" and this_attempt > 1:
            feedback.append({
                "question_id": a.question_id,
                "correct": correct,
                "selected_option": a.selected_option.upper(),
                "correct_option": q["correct_option"].upper(),
                "explanation": q.get("explanation") or "",
            })

    if rows:
        supabase.table("anchor_scores").insert(rows).execute()

    supabase.table("interaction_log").insert({
        "student_id": student["student_id"],
        "session_id": body.session_id,
        "event_type": "anchor_submit",
        "entity_id": body.node_id,
        "value": None,
        "metadata": {"test_type": body.test_type, "count": len(rows)}
    }).execute()

    field = "anchor_done" if body.test_type == "pre" else "posttest_done"
    supabase.table("unit_progress").upsert({
        "student_id": student["student_id"],
        "node_id": body.node_id,
        field: True
    }, on_conflict="student_id,node_id").execute()

    # Pre-test only feeds BKT mastery — a student who already knows the
    # material coming in should start above the flat 0.2 default, not
    # get treated identically to someone who's never seen it. Post-test
    # deliberately does NOT touch mastery, preserving it as an
    # independent outcome check on whether practice-driven mastery
    # actually predicts real performance.
    if body.test_type == "pre" and rows:
        for r in rows:
            try:
                await bkt_service.update(student["student_id"], body.node_id, int(r["correct"]))
            except Exception as e:
                logger.error(f"BKT update from anchor failed: {e}")

    # Both pre AND post feed ability — a question with known difficulty
    # and a known right/wrong outcome is genuine ability evidence
    # regardless of which screen it came from. This was the actual gap:
    # anchor answers were recorded but never reached the ability
    # calculation at all. irt_service.update() recomputes from the full
    # stored history internally, so one call (not one per question) is
    # correct and sufficient here.
    if rows:
        try:
            await irt_service.update(student["student_id"], 0.0, 0)
        except Exception as e:
            logger.error(f"IRT update from anchor failed: {e}")

    if body.test_type == "post":
        score_pct = (sum(1 for r in rows if r["correct"]) / len(rows) * 100) if rows else 0.0
        from services.learning_guide import learning_guide_service
        try:
            summary = await learning_guide_service.module_complete_message(
                student["student_id"], body.node_id, score_pct
            )
        except Exception as e:
            logger.error(f"module_complete_message failed: {e}")
            summary = {"mastery": 0.0, "is_mastered": False, "newly_unlocked": [], "message": None}

        # The exact mastery+outcome pairing threshold_recommendation.py
        # needs — nothing else captures this. Wrapped separately so a
        # logging failure can never affect the actual response.
        try:
            supabase.table("interaction_log").insert({
                "student_id": student["student_id"],
                "session_id": body.session_id,
                "event_type": "post_test_complete",
                "entity_id": body.node_id,
                "value": score_pct,
                "metadata": {"mastery_at_post_test": summary["mastery"], "score_pct": score_pct}
            }).execute()
        except Exception as e:
            logger.error(f"post_test_complete logging failed: {e}")

        return {
            "score_pct": round(score_pct, 1),
            "correct_count": sum(1 for r in rows if r["correct"]),
            "total_questions": len(rows),
            "attempt_number": this_attempt,
            "feedback": feedback if this_attempt > 1 else None,
            **summary,
        }

    return {"status": "logged"}
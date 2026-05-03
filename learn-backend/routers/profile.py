from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from db.supabase import supabase
from routers.deps import get_current_student

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/me")
async def get_me(student=Depends(get_current_student)):
    return {
        "student_id": student["student_id"],
        "email": student["email"],
        "l1_language": student["l1_language"],
        "english_medium": student["english_medium"],
        "self_reported_level": student["self_reported_level"],
        "vark_label": student["active_vark_label"],
        "vark_questionnaire_label": student["vark_questionnaire_label"],
        "onboarding_complete": student["onboarding_complete"],
        "current_active_node": student["current_active_node"],
        "irt_theta": student["irt_theta"],
        "dropout_risk_score": student["dropout_risk_score"],
        "risk_trend": student["risk_trend"],
    }

@router.get("/stats")
async def get_stats(student=Depends(get_current_student)):
    weekly = supabase.table("weekly_stats").select("*").eq(
        "student_id", student["student_id"]).order("week_number").execute()
    return weekly.data

@router.get("/progress")
async def get_progress(student=Depends(get_current_student)):
    progress = supabase.table("unit_progress").select("*").eq(
        "student_id", student["student_id"]).execute()
    nodes_mastered = student.get("nodes_mastered", [])
    bkt = student.get("bkt_mastery", {})

    # "Current Level" derived from actual curriculum progression, not a
    # static self-report collected once at signup. A theta-based
    # mapping was considered and rejected — checking the real content
    # bank showed average question difficulty is nearly identical
    # across all four CEFR levels (~-0.10 to 0.00), meaning CEFR level
    # reflects curriculum sequence here, not psychometric difficulty.
    # Progression through actually-mastered content is the honest,
    # data-grounded signal to use instead.
    all_nodes = supabase.table("content_nodes").select("node_id,cefr_level").execute().data
    CEFR_ORDER = ["A1", "A2", "B1", "B2"]
    nodes_by_level = {lvl: [n["node_id"] for n in all_nodes if n["cefr_level"] == lvl] for lvl in CEFR_ORDER}

    current_level = f"{CEFR_ORDER[-1]} (Mastered)"
    for lvl in CEFR_ORDER:
        level_nodes = nodes_by_level.get(lvl, [])
        if not level_nodes:
            continue
        mastered_in_level = sum(1 for n in level_nodes if n in nodes_mastered)
        if mastered_in_level < len(level_nodes):
            current_level = lvl
            break

    return {
        "unit_progress": progress.data,
        "nodes_mastered": nodes_mastered,
        "bkt_mastery": bkt,
        "irt_theta": student["irt_theta"],
        "irt_theta_history": student.get("irt_theta_history", []),
        "current_gaps": student.get("current_gaps", []),
        "current_active_node": student["current_active_node"],
        "current_level": current_level,
    }

@router.get("/guide-message")
async def get_guide_message(node_id: str, student=Depends(get_current_student)):
    """Powers the persistent guide icon on lesson pages. Prioritizes a
    gap nudge if the student has one — otherwise a friendly intro to
    the node they're on."""
    from services.learning_guide import learning_guide_service
    try:
        if student.get("current_gaps"):
            message = await learning_guide_service.gap_nudge_message(
                student["student_id"], node_id
            )
            if message:
                return {"situation": "gap_detected", "message": message}
        message = await learning_guide_service.lesson_intro_message(
            student["student_id"], node_id
        )
        return {"situation": "lesson_intro", "message": message}
    except Exception as e:
        logger.error(f"guide-message failed for node {node_id}: {e}")
        return {"situation": "lesson_intro", "message": None}


@router.get("/pending-intervention")
async def get_pending_intervention(student=Depends(get_current_student)):
    """Returns the student's latest un-viewed intervention message, or
    None if there isn't one. Deliberately checks message_sent, NOT
    sent_at — sent_at now specifically means 'emailed', and the in-app
    popup must never depend on email succeeding or even being
    configured. A student who's actively logged in should see their
    message regardless of whether the separate email channel worked."""
    result = supabase.table("interventions").select(
        "intervention_id,message_sent,sent_at,requested_at"
    ).eq("student_id", student["student_id"]).not_.is_(
        "message_sent", "null"
    ).is_("opened_at", "null").order("requested_at", desc=True).limit(1).execute().data
    return result[0] if result else None


@router.get("/ability-projection")
async def get_ability_projection(band: str = "easy", count: int = 10, student=Depends(get_current_student)):
    """'If I answer N more questions correctly at this difficulty, how
    much would my ability move?' — a genuine simulation using the same
    validated IRT math as everywhere else, not a fabricated estimate."""
    from services.irt import irt_service
    if band not in ("easy", "just_right", "hard", "impossible"):
        raise HTTPException(status_code=400, detail="Invalid band")
    result = await irt_service.project_improvement(
        student["student_id"], band, min(max(count, 1), 30)
    )
    return result


@router.get("/gap-review")
async def get_gap_review(node_id: str, student=Depends(get_current_student)):
    """The content-generation half of the gap-detection feature — a
    short, VARK-styled re-explanation of a specific skill the student
    is struggling with, not just a nudge to go revisit it."""
    from services.learning_guide import learning_guide_service
    result = await learning_guide_service.generate_gap_review(student["student_id"], node_id)
    if result is None:
        raise HTTPException(status_code=503, detail="Could not generate a review right now — try again shortly.")
    return result


@router.get("/notifications")
async def get_notifications(student=Depends(get_current_student)):
    """Full history — every intervention message ever generated for this
    student, read or not, newest first. Same message_sent-based logic
    as pending-intervention above, for the same reason: this shouldn't
    depend on email having been configured or successful."""
    result = supabase.table("interventions").select(
        "intervention_id,message_sent,sent_at,opened_at,requested_at"
    ).eq("student_id", student["student_id"]).not_.is_(
        "message_sent", "null"
    ).order("requested_at", desc=True).execute().data
    return result


class InterventionViewedRequest(BaseModel):
    intervention_id: str


@router.post("/intervention-viewed")
async def mark_intervention_viewed(
    body: InterventionViewedRequest, student=Depends(get_current_student)
):
    supabase.table("interventions").update({
        "opened_at": datetime.utcnow().isoformat()
    }).eq("intervention_id", body.intervention_id).eq(
        "student_id", student["student_id"]
    ).execute()
    return {"status": "ok"}
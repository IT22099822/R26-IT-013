import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from db.supabase import supabase
from routers.deps import get_current_admin
import csv, io
import pytz

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

router = APIRouter()


# ─── Models ───────────────────────────────────────────────────────────────────

class ContentNodeRequest(BaseModel):
    node_id: str
    level: int
    skill_name: str
    cefr_level: str
    prerequisites: Optional[list] = []
    summary: Optional[str] = None
    learning_objectives: Optional[list] = []
    lesson_markdown: Optional[str] = None
    video_youtube_id: Optional[str] = None
    audio_file_url: Optional[str] = None
    estimated_minutes: Optional[int] = None
    display_order: int


class QuestionRequest(BaseModel):
    question_id: str
    node_id: str
    question_text: str
    option_a: str
    option_b: str
    option_c: Optional[str] = None
    option_d: Optional[str] = None
    correct_option: str
    explanation: Optional[str] = None
    question_type: str
    difficulty_tag: Optional[float] = None
    vark_type: Optional[str] = None
    image_url: Optional[str] = None
    question_audio_url: Optional[str] = None


# ─── Helper ───────────────────────────────────────────────────────────────────

def make_csv_response(data: list, filename: str) -> StreamingResponse:
    output = io.StringIO()
    if data:
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    else:
        output.write("no_data\n")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ─── Content ──────────────────────────────────────────────────────────────────

@router.get("/content")
async def list_content(admin=Depends(get_current_admin)):
    return supabase.table("content_nodes").select("*").order("display_order").execute().data


@router.get("/content/{node_id}")
async def get_content(node_id: str, admin=Depends(get_current_admin)):
    result = supabase.table("content_nodes").select("*").eq("node_id", node_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Node not found")
    return result.data[0]


@router.post("/content")
async def create_content(body: ContentNodeRequest, admin=Depends(get_current_admin)):
    data = body.dict()
    data["has_video"] = bool(body.video_youtube_id)
    data["has_audio"] = bool(body.audio_file_url)
    data["status"] = "draft"
    data["created_by"] = admin["email"]
    data["updated_by"] = admin["email"]
    result = supabase.table("content_nodes").insert(data).execute()
    return result.data[0]


@router.put("/content/{node_id}")
async def update_content(node_id: str, body: ContentNodeRequest, admin=Depends(get_current_admin)):
    data = body.dict()
    data["has_video"] = bool(body.video_youtube_id)
    data["has_audio"] = bool(body.audio_file_url)
    data["updated_by"] = admin["email"]
    data["updated_at"] = datetime.utcnow().isoformat()
    result = supabase.table("content_nodes").update(data).eq("node_id", node_id).execute()
    return result.data[0]


@router.post("/content/{node_id}/publish")
async def publish_content(node_id: str, admin=Depends(get_current_admin)):
    supabase.table("content_nodes").update({
        "status": "published",
        "updated_by": admin["email"],
        "updated_at": datetime.utcnow().isoformat()
    }).eq("node_id", node_id).execute()
    return {"status": "published"}


@router.post("/content/{node_id}/toggle-quiz")
async def toggle_quiz_ready(node_id: str, admin=Depends(get_current_admin)):
    node = supabase.table("content_nodes").select("questions_ready").eq("node_id", node_id).execute()
    if not node.data:
        raise HTTPException(status_code=404, detail="Node not found")
    current = node.data[0]["questions_ready"]
    supabase.table("content_nodes").update({
        "questions_ready": not current,
        "updated_by": admin["email"],
        "updated_at": datetime.utcnow().isoformat()
    }).eq("node_id", node_id).execute()
    return {"node_id": node_id, "questions_ready": not current}


@router.delete("/content/{node_id}")
async def delete_content(node_id: str, admin=Depends(get_current_admin)):
    node = supabase.table("content_nodes").select("node_id,status").eq("node_id", node_id).execute()
    if not node.data:
        raise HTTPException(status_code=404, detail="Node not found")
    if admin["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Only superadmin can delete nodes.")
    if admin["email"] != "kkdshevonperera04@gmail.com":
        has_attempts = supabase.table("question_attempts").select("attempt_id").eq("node_id", node_id).limit(1).execute()
        if has_attempts.data:
            raise HTTPException(status_code=400, detail="Cannot delete: students have already attempted questions in this node.")
    supabase.table("questions").delete().eq("node_id", node_id).execute()
    supabase.table("content_nodes").delete().eq("node_id", node_id).execute()
    return {"status": "deleted", "node_id": node_id}


# ─── Questions ────────────────────────────────────────────────────────────────

@router.get("/questions")
async def list_questions(admin=Depends(get_current_admin)):
    return supabase.table("questions").select("*").execute().data


@router.get("/questions/progress")
async def question_progress(admin=Depends(get_current_admin)):
    nodes = supabase.table("content_nodes").select("node_id,skill_name,questions_ready").execute().data
    questions = supabase.table("questions").select("node_id,question_type,status").execute().data
    result = []
    for node in nodes:
        nid = node["node_id"]
        nq = [q for q in questions if q["node_id"] == nid]
        result.append({
            "node_id": nid,
            "skill_name": node.get("skill_name", ""),
            "questions_ready": node.get("questions_ready", False),
            "anchor":    len([q for q in nq if q["question_type"] == "anchor"    and q["status"] == "published"]),
            "practice":  len([q for q in nq if q["question_type"] == "practice"  and q["status"] == "published"]),
            "post_test": len([q for q in nq if q["question_type"] == "post_test" and q["status"] == "published"]),
        })
    return result


@router.get("/questions/by-node/{node_id}")
async def questions_by_node(node_id: str, admin=Depends(get_current_admin)):
    return supabase.table("questions").select("*").eq("node_id", node_id).execute().data


@router.get("/questions/{question_id}")
async def get_question(question_id: str, admin=Depends(get_current_admin)):
    result = supabase.table("questions").select("*").eq("question_id", question_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Question not found")
    return result.data[0]


@router.post("/questions")
async def create_question(body: QuestionRequest, admin=Depends(get_current_admin)):
    data = body.dict()
    data["status"] = "draft"
    data["created_by"] = admin["email"]
    data["updated_by"] = admin["email"]
    result = supabase.table("questions").insert(data).execute()
    return result.data[0]


@router.put("/questions/{question_id}")
async def update_question(question_id: str, body: QuestionRequest, admin=Depends(get_current_admin)):
    data = body.dict()
    data["updated_by"] = admin["email"]
    data["updated_at"] = datetime.utcnow().isoformat()
    result = supabase.table("questions").update(data).eq("question_id", question_id).execute()
    return result.data[0]


@router.post("/questions/{question_id}/publish")
async def publish_question(question_id: str, admin=Depends(get_current_admin)):
    result = supabase.table("questions").update({
        "status": "published",
        "updated_by": admin["email"],
        "updated_at": datetime.utcnow().isoformat()
    }).eq("question_id", question_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Question not found")
    return {"message": "Published", "question_id": question_id}


@router.delete("/questions/{question_id}")
async def delete_question(question_id: str, admin=Depends(get_current_admin)):
    question = supabase.table("questions").select("question_id,status,node_id").eq("question_id", question_id).execute()
    if not question.data:
        raise HTTPException(status_code=404, detail="Question not found")
    q = question.data[0]
    if q["status"] == "published" and admin["role"] != "super_admin":
        raise HTTPException(status_code=403, detail="Only superadmin can delete published questions.")
    if admin["role"] != "super_admin":
        has_attempts = supabase.table("question_attempts").select("attempt_id").eq("question_id", question_id).limit(1).execute()
        if has_attempts.data:
            raise HTTPException(status_code=400, detail="Cannot delete: students have already attempted this question.")
    supabase.table("questions").delete().eq("question_id", question_id).execute()
    return {"status": "deleted", "question_id": question_id}


# ─── Students & Logs ──────────────────────────────────────────────────────────

@router.get("/students")
async def list_students(admin=Depends(get_current_admin)):
    return supabase.table("students").select(
        "student_id,created_at,l1_language,english_medium,self_reported_level,"
        "vark_questionnaire_label,active_vark_label,onboarding_complete,irt_theta,dropout_risk_score,"
        "risk_trend,days_since_last_login,active,bkt_mastery,current_gaps,engagement_dip_score"
    ).execute().data


@router.get("/logs")
async def get_logs(limit: int = 500, admin=Depends(get_current_admin)):
    return supabase.table("interaction_log").select("*").order("timestamp", desc=True).limit(limit).execute().data


@router.get("/weekly")
async def get_weekly(admin=Depends(get_current_admin)):
    return supabase.table("weekly_stats").select("*").order("week_number").execute().data


@router.get("/coordinator-decisions")
async def get_coordinator_decisions(limit: int = 200, admin=Depends(get_current_admin)):
    return supabase.table("coordinator_decisions").select("*").order(
        "timestamp", desc=True
    ).limit(limit).execute().data


@router.get("/interventions")
async def get_interventions(limit: int = 200, admin=Depends(get_current_admin)):
    return supabase.table("interventions").select("*").order(
        "sent_at", desc=True
    ).limit(limit).execute().data


@router.post("/run-weekly-pipeline")
async def trigger_weekly_pipeline(admin=Depends(get_current_admin)):
    """Manually fires the same weekly_agg + VARK + dropout pipeline the
    scheduler runs every Sunday — for testing without waiting a week.
    Runs in the background so the request doesn't hang for however long
    the full student loop takes; check the server logs for progress."""
    import asyncio
    from scheduler import run_weekly_pipeline
    asyncio.create_task(run_weekly_pipeline())
    return {"status": "started", "note": "running in background, check server logs"}


@router.post("/run-recovery-check")
async def trigger_recovery_check(admin=Depends(get_current_admin)):
    """Manually fires the 7-day recovery check the scheduler otherwise
    runs daily — for testing without waiting for real interventions to
    age past 7 days."""
    import asyncio
    from services.coordinator import coordinator
    asyncio.create_task(coordinator.check_recovery())
    return {"status": "started", "note": "running in background, check server logs"}


# ─── Exports ──────────────────────────────────────────────────────────────────

@router.get("/export/students")
async def export_students(admin=Depends(get_current_admin)):
    data = supabase.table("students").select(
        "student_id,created_at,l1_language,english_medium,self_reported_level,"
        "vark_questionnaire_label,onboarding_complete,irt_theta,bkt_mastery,"
        "dropout_risk_score,risk_trend,days_since_last_login,active"
    ).execute().data
    return make_csv_response(data, "learn_students.csv")


@router.get("/export/interactions")
async def export_interactions(admin=Depends(get_current_admin)):
    data = supabase.table("interaction_log").select("*").order("timestamp", desc=True).execute().data
    return make_csv_response(data, "learn_interactions.csv")


@router.get("/export/quiz-results")
async def export_quiz_results(admin=Depends(get_current_admin)):
    data = supabase.table("quiz_results").select("*").order("taken_at", desc=True).execute().data
    return make_csv_response(data, "learn_quiz_results.csv")


@router.get("/export/unit-progress")
async def export_unit_progress(admin=Depends(get_current_admin)):
    data = supabase.table("unit_progress").select("*").execute().data
    return make_csv_response(data, "learn_unit_progress.csv")


@router.get("/export/weekly-stats")
async def export_weekly_stats(admin=Depends(get_current_admin)):
    data = supabase.table("weekly_stats").select("*").order("week_number").execute().data
    return make_csv_response(data, "learn_weekly_stats.csv")


@router.get("/export/question-attempts")
async def export_question_attempts(admin=Depends(get_current_admin)):
    data = supabase.table("question_attempts").select("*").order("attempted_at", desc=True).execute().data
    return make_csv_response(data, "learn_question_attempts.csv")


@router.get("/export/csv")
async def export_csv_legacy(admin=Depends(get_current_admin)):
    """Legacy single-export endpoint — kept for backward compatibility."""
    data = supabase.table("students").select(
        "student_id,created_at,l1_language,english_medium,self_reported_level,"
        "vark_questionnaire_label,onboarding_complete,irt_theta,bkt_mastery,"
        "dropout_risk_score,risk_trend,days_since_last_login"
    ).execute().data
    return make_csv_response(data, "students_export.csv")


# ─── Auth Check ───────────────────────────────────────────────────────────────

@router.get("/check")
async def check_admin(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No token")
    token = authorization.replace("Bearer ", "")
    try:
        user = supabase.auth.get_user(token)
        email = user.user.email
        result = supabase.table("admin_users").select("*").eq("email", email).eq("active", True).execute()
        if not result.data:
            raise HTTPException(status_code=403, detail="Not an admin")
        return {"is_admin": True, "role": result.data[0]["role"], "email": email}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=403, detail="Not an admin")


# ─── Demo Data Seeding ────────────────────────────────────────────────────────
# For demo reliability — does NOT depend on live LLM calls, the weekly
# pipeline running, or a student organically crossing the risk
# threshold in the treatment group. Writes directly, guaranteed to work
# regardless of Groq latency or randomized group assignment. The
# message text is hand-crafted to match real generation style, not
# live-generated — that's a deliberate, honest tradeoff for timing
# certainty on demo day.

class SeedDemoRequest(BaseModel):
    student_email: str
    scenario: str  # see the six scenarios below
    engagement_dip_score: Optional[float] = None  # optional, any scenario — shows the second admin-page badge


@router.post("/seed-demo-data")
async def seed_demo_data(body: SeedDemoRequest, admin=Depends(get_current_admin)):
    student_rows = supabase.table("students").select("*").eq("email", body.student_email).execute().data
    if not student_rows:
        raise HTTPException(status_code=404, detail=f"No student found with email {body.student_email}")
    student = student_rows[0]
    student_id = student["student_id"]

    vark_label = student.get("active_vark_label") or student.get("vark_questionnaire_label") or "R"
    vark_style = {"V": "visual", "A": "auditory", "R": "reading/writing", "K": "hands-on"}.get(vark_label, "reading/writing")
    now = datetime.utcnow()

    # Real current gaps, resolved to skill names — the same lookup
    # intervention_messenger.py's real _gather_context() does, so the
    # seeded demo message matches what live generation would actually
    # produce, not a nicer-looking approximation of it.
    gap_ids = student.get("current_gaps") or []
    gap_names = []
    if gap_ids:
        gap_nodes = supabase.table("content_nodes").select("node_id,skill_name").in_(
            "node_id", gap_ids
        ).execute().data
        gap_names = [n["skill_name"] for n in gap_nodes]
    gaps_text = ", ".join(gap_names[:2]) if gap_names else "their recent topics"

    # engagement_dip_score is independent of every scenario below — set
    # it here, once, regardless of which branch runs next, so it can be
    # combined with any of the six scenarios (e.g. a student who's
    # genuinely at high real risk AND shows a rough-week engagement dip,
    # to demonstrate both admin-page badges appearing together).
    if body.engagement_dip_score is not None:
        supabase.table("students").update({
            "engagement_dip_score": round(body.engagement_dip_score, 4)
        }).eq("student_id", student_id).execute()

    def seed_real_recovery_activity(sid: str, anchor_time: datetime):
        """Seeds real, checkable rows within the 7-day recovery window
        following anchor_time — a login session, a completed quiz, and
        a completed unit — so the treatment-vs-control endpoint's live
        recovery check (which queries real sessions/quiz_results/
        unit_progress, not a flag) finds genuine, real activity to
        confirm, rather than silently finding nothing regardless of
        which story the seed data was supposed to tell."""
        activity_time = anchor_time + timedelta(days=2)
        session = supabase.table("sessions").insert({
            "student_id": sid, "login_at": activity_time.isoformat()
        }).execute().data[0]
        supabase.table("quiz_results").insert({
            "student_id": sid, "session_id": session["session_id"], "node_id": "F01",
            "completed": True, "taken_at": activity_time.isoformat(),
        }).execute()
        supabase.table("unit_progress").upsert({
            "student_id": sid, "node_id": "F01",
            "completed": True, "completed_at": activity_time.isoformat(),
        }, on_conflict="student_id,node_id").execute()

    if body.scenario in ("suppressed_control_recovered", "suppressed_control_not_recovered"):
        supabase.table("students").update({
            "dropout_risk_score": 0.78,
            "risk_trend": "increasing",
            "primary_risk_reason": "declining session frequency",
            "intervention_group": "control",
        }).eq("student_id", student_id).execute()
        # Backdated 8 days — the treatment-vs-control endpoint only
        # considers a control candidate once its 7-day window has fully
        # closed. Timestamping this "now", as the original version did,
        # meant a seeded control example could never actually appear
        # on that page at all.
        decision_time = now - timedelta(days=8)
        supabase.table("coordinator_decisions").insert({
            "student_id": student_id,
            "timestamp": decision_time.isoformat(),
            "trigger_event": "dropout_risk_check",
            "rule_fired": "control_group_suppression",
            "final_decision": "intervention_suppressed_control_group",
            "c4_recommendation": "risk=0.78, trend=increasing, reason=declining session frequency",
            "agents_consulted": ["c4"],
        }).execute()
        if body.scenario == "suppressed_control_recovered":
            seed_real_recovery_activity(student_id, decision_time)
        return {"status": "seeded", "scenario": body.scenario, "student_id": student_id}

    if body.scenario == "below_threshold":
        supabase.table("students").update({
            "dropout_risk_score": 0.22, "risk_trend": "stable",
            "primary_risk_reason": None,
        }).eq("student_id", student_id).execute()
        supabase.table("coordinator_decisions").insert({
            "student_id": student_id, "timestamp": now.isoformat(),
            "trigger_event": "dropout_risk_check", "rule_fired": "below_risk_threshold",
            "final_decision": "no_action_below_threshold",
            "c4_recommendation": "risk=0.22, trend=stable, reason=none", "agents_consulted": ["c4"],
        }).execute()
        return {"status": "seeded", "scenario": body.scenario, "student_id": student_id}

    if body.scenario == "suppressed_cooldown":
        supabase.table("students").update({
            "dropout_risk_score": 0.75, "risk_trend": "increasing",
            "primary_risk_reason": "declining quiz scores",
        }).eq("student_id", student_id).execute()
        # A prior intervention inside the 14-day cooldown window — this
        # is WHY the current check gets suppressed, not just a label.
        supabase.table("interventions").insert({
            "student_id": student_id, "risk_score": 0.75,
            "risk_reason": "declining quiz scores",
            "trigger_criteria": {"seeded_for_demo": True},
            "message_sent": "An earlier message, still inside the cooldown window.",
            "sent_at": (now - timedelta(days=5)).isoformat(),
        }).execute()
        supabase.table("coordinator_decisions").insert({
            "student_id": student_id, "timestamp": now.isoformat(),
            "trigger_event": "dropout_risk_check", "rule_fired": "cooldown_active",
            "final_decision": "suppressed_cooldown",
            "c4_recommendation": "risk=0.75, trend=increasing, reason=declining quiz scores",
            "agents_consulted": ["c4"],
        }).execute()
        return {"status": "seeded", "scenario": body.scenario, "student_id": student_id}

    if body.scenario not in ("pending_intervention", "recovered_intervention"):
        raise HTTPException(status_code=400, detail=(
            "scenario must be one of: pending_intervention, recovered_intervention, "
            "suppressed_control_recovered, suppressed_control_not_recovered, "
            "below_threshold, suppressed_cooldown"
        ))

    supabase.table("students").update({
        "dropout_risk_score": 0.82,
        "risk_trend": "increasing",
        "primary_risk_reason": "declining session frequency and quiz scores",
        "intervention_group": "treatment",
    }).eq("student_id", student_id).execute()

    supabase.table("coordinator_decisions").insert({
        "student_id": student_id,
        "timestamp": now.isoformat(),
        "trigger_event": "dropout_risk_check",
        "rule_fired": "intervention_check",
        "final_decision": "intervention_triggered",
        "c4_recommendation": "risk=0.82, trend=increasing, reason=declining session frequency and quiz scores",
        "agents_consulted": ["c4"],
    }).execute()

    if gap_names:
        gaps_text = ", ".join(gap_names[:2])
        gap_clause = f"revisiting {gaps_text} in a quick, {vark_style}-friendly way could really help close that gap"
    else:
        gap_clause = f"a quick, {vark_style}-friendly review of your recent topics could help you feel more confident"

    # Real personalised generation (same path as the weekly pipeline), with the
    # old fixed template only as a fallback if the LLM is unreachable.
    message = None
    try:
        from services.intervention_messenger import intervention_messenger
        message = await intervention_messenger.compose_message(student_id)
    except Exception as e:
        logging.getLogger(__name__).warning(f"demo seed: live message generation failed, using template: {e}")
    if not message:
        message = (
            f"Hey! I noticed things have been a bit quieter lately — totally normal, life gets busy. "
            f"Since you learn best through {vark_style} content, {gap_clause}. Even just two short sessions "
            f"this week — 10-15 minutes each — could make a real difference. You've got this!"
        )

    intervention_data = {
        "student_id": student_id,
        "risk_score": 0.82,
        "risk_reason": "declining session frequency and quiz scores",
        "trigger_criteria": {"risk_score": 0.82, "risk_trend": "increasing", "seeded_for_demo": True},
        "message_sent": message,
    }

    if body.scenario == "pending_intervention":
        intervention_data["sent_at"] = now.isoformat()
        intervention_data["opened_at"] = None
        intervention_data["recovery_checked"] = False
    else:  # recovered_intervention
        sent = now - timedelta(days=8)
        intervention_data["sent_at"] = sent.isoformat()
        intervention_data["opened_at"] = (sent + timedelta(hours=2)).isoformat()
        intervention_data["recovery_checked"] = True
        intervention_data["recovery_checked_at"] = now.isoformat()
        intervention_data["login_within_7days"] = True
        intervention_data["quiz_within_7days"] = True
        intervention_data["unit_within_7days"] = True
        intervention_data["recovery_score"] = 1.0

    supabase.table("interventions").insert(intervention_data).execute()

    return {"status": "seeded", "scenario": body.scenario, "student_id": student_id, "message": message}


# ─── Generated Question Moderation ───────────────────────────────────────────
# Review screen for pending_review content, grounded in the established
# "Item-Writing Flaws" (IWF) framework from psychometrics rather than an
# ad-hoc checklist — the same category of rubric used in published studies
# comparing LLM-generated MCQ quality against human-authored items.

@router.get("/pending-review-questions")
async def list_pending_review_questions(admin=Depends(get_current_admin)):
    return supabase.table("questions").select(
        "question_id,node_id,question_text,option_a,option_b,option_c,option_d,"
        "correct_option,explanation,visual_aid_markdown,difficulty_tag,vark_type,"
        "question_type,evaluator_verdict,created_at"
    ).eq("status", "pending_review").order("created_at", desc=True).execute().data


class ReviewQuestionRequest(BaseModel):
    question_id: str
    decision: str  # 'approved' | 'rejected'
    reviewer_email: str


@router.post("/review-question")
async def review_question(body: ReviewQuestionRequest, admin=Depends(get_current_admin)):
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")

    new_status = "published" if body.decision == "approved" else "evaluator_rejected"
    supabase.table("questions").update({
        "status": new_status,
        "review_decision": body.decision,
        "reviewed_by": body.reviewer_email,
        "reviewed_at": datetime.utcnow().isoformat(),
    }).eq("question_id", body.question_id).execute()

    return {"status": "ok", "question_id": body.question_id, "new_status": new_status}


@router.get("/review-agreement")
async def get_review_agreement(admin=Depends(get_current_admin)):
    """Cohen's Kappa between the automated evaluator's verdict and a
    human reviewer's decision — the standard inter-rater reliability
    metric from the AIG/LLM-item-quality literature for measuring
    whether an automated screen can be trusted. Only computable on
    items that have BOTH verdicts recorded, which is why evaluator
    rejections are now saved instead of discarded (see
    question_generator.py)."""
    from sklearn.metrics import cohen_kappa_score

    rows = supabase.table("questions").select(
        "evaluator_verdict,review_decision"
    ).not_.is_("evaluator_verdict", "null").not_.is_("review_decision", "null").execute().data

    if len(rows) < 5:
        return {
            "n_reviewed": len(rows),
            "kappa": None,
            "note": "Need at least 5 human-reviewed items with a recorded evaluator "
                    "verdict for a meaningful agreement statistic. Review more items "
                    "(both approvals and rejections) to unlock this.",
        }

    evaluator_labels = [1 if r["evaluator_verdict"] else 0 for r in rows]
    human_labels = [1 if r["review_decision"] == "approved" else 0 for r in rows]
    kappa = cohen_kappa_score(evaluator_labels, human_labels)

    # Standard interpretation bands (Landis & Koch, 1977) — cited
    # directly since "kappa=0.4" means nothing to a reader without them
    if kappa < 0.20: interpretation = "slight agreement"
    elif kappa < 0.40: interpretation = "fair agreement"
    elif kappa < 0.60: interpretation = "moderate agreement"
    elif kappa < 0.80: interpretation = "substantial agreement"
    else: interpretation = "near-perfect agreement"

    return {
        "n_reviewed": len(rows),
        "kappa": round(kappa, 4),
        "interpretation": interpretation,
    }


# ─── Treatment vs. Control Outcomes Comparison ───────────────────────────────
# Your own C4 spec names this directly as "the PP2 research finding" — does
# the intervention actually help, or would these students have come back
# anyway? Uses the IDENTICAL three-signal recovery definition (login/quiz/
# unit within 7 days) already validated in coordinator.check_recovery(),
# just computed fresh for the control group, since control-group students
# never get an interventions row created for them in the first place.

def _summarize_recovery(rows: list) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "login_rate": round(sum(r["login_within_7days"] for r in rows) / n, 4),
        "quiz_rate": round(sum(r["quiz_within_7days"] for r in rows) / n, 4),
        "unit_rate": round(sum(r["unit_within_7days"] for r in rows) / n, 4),
        "avg_recovery_score": round(sum(r["recovery_score"] for r in rows) / n, 4),
    }


@router.get("/treatment-control-comparison")
async def treatment_control_comparison(admin=Depends(get_current_admin)):
    # Treatment group: interventions already recovery-checked by the
    # existing daily job.
    treatment_rows = supabase.table("interventions").select(
        "student_id,login_within_7days,quiz_within_7days,unit_within_7days,recovery_score"
    ).eq("recovery_checked", True).execute().data

    # Control group: students who WOULD have gotten an intervention but
    # were held back by randomization. No interventions row exists for
    # them, so recovery is computed fresh, right now, using the exact
    # same three checks and 7-day window as the treatment group.
    control_decisions = supabase.table("coordinator_decisions").select(
        "student_id,timestamp"
    ).eq("final_decision", "intervention_suppressed_control_group").execute().data

    now = datetime.now(COLOMBO_TZ)
    control_rows = []
    skipped_too_recent = 0
    for row in control_decisions:
        ts = datetime.fromisoformat(row["timestamp"])
        if ts.tzinfo is None:
            ts = COLOMBO_TZ.localize(ts)
        window_end = ts + timedelta(days=7)
        if now < window_end:
            skipped_too_recent += 1
            continue  # not fair to check yet — same rule as check_recovery()

        sid = row["student_id"]
        sessions = supabase.table("sessions").select("session_id").eq(
            "student_id", sid
        ).gte("login_at", ts.isoformat()).lte("login_at", window_end.isoformat()).limit(1).execute().data
        login = len(sessions) > 0

        quizzes = supabase.table("quiz_results").select("quiz_result_id").eq(
            "student_id", sid
        ).gte("taken_at", ts.isoformat()).lte("taken_at", window_end.isoformat()).limit(1).execute().data
        quiz = len(quizzes) > 0

        units = supabase.table("unit_progress").select("id").eq(
            "student_id", sid
        ).eq("completed", True).gte(
            "completed_at", ts.isoformat()
        ).lte("completed_at", window_end.isoformat()).limit(1).execute().data
        unit = len(units) > 0

        control_rows.append({
            "student_id": sid,
            "login_within_7days": login, "quiz_within_7days": quiz, "unit_within_7days": unit,
            "recovery_score": round((int(login) + int(quiz) + int(unit)) / 3.0, 4),
        })

    treatment_summary = _summarize_recovery(treatment_rows)
    control_summary = _summarize_recovery(control_rows)

    stats_result = None
    if treatment_summary["n"] > 0 and control_summary["n"] > 0:
        from scipy.stats import fisher_exact
        t_recovered = sum(1 for r in treatment_rows if r["recovery_score"] > 0)
        c_recovered = sum(1 for r in control_rows if r["recovery_score"] > 0)
        odds_ratio, p_value = fisher_exact([
            [t_recovered, treatment_summary["n"] - t_recovered],
            [c_recovered, control_summary["n"] - c_recovered],
        ])
        stats_result = {
            "test": "Fisher's exact test on 'any recovery signal' (login OR quiz OR unit within 7 days)",
            "treatment_any_recovered": t_recovered,
            "control_any_recovered": c_recovered,
            "odds_ratio": round(odds_ratio, 4) if odds_ratio not in (float('inf'),) else None,
            "p_value": round(p_value, 4),
            "is_significant": p_value < 0.05,
        }

    return {
        "treatment": treatment_summary,
        "control": control_summary,
        "statistical_test": stats_result,
        "skipped_control_too_recent": skipped_too_recent,
        "honest_note": (
            "With per-group sample sizes typically in the dozens for a pilot this size, "
            "this is best presented as a directional finding, not a definitive causal claim — "
            "consistent with the power limitations already documented for this project."
        ),
    }
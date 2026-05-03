from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from db.supabase import supabase
from routers.deps import get_current_student
import random



router = APIRouter()



class ProfileRequest(BaseModel):
    l1_language: str
    english_medium: bool
    self_reported_level: str



class VARKRequest(BaseModel):
    scores: dict
    label: str



class DiagnosticRequest(BaseModel):
    answers: list



@router.get("/status")
async def onboarding_status(student=Depends(get_current_student)):
    return {
        "onboarding_complete": student["onboarding_complete"],
        "onboarding_step": student["onboarding_step"]
    }



@router.post("/consent")
async def save_consent(student=Depends(get_current_student)):
    from datetime import datetime
    supabase.table("students").update({
        "consent_given": True,
        "consent_at": datetime.utcnow().isoformat(),
        "onboarding_step": "profile"
    }).eq("student_id", student["student_id"]).execute()
    return {"status": "ok", "next_step": "profile"}



@router.post("/profile")
async def save_profile(body: ProfileRequest, student=Depends(get_current_student)):
    supabase.table("students").update({
        "l1_language": body.l1_language,
        "english_medium": body.english_medium,
        "self_reported_level": body.self_reported_level,
        "onboarding_step": "vark"
    }).eq("student_id", student["student_id"]).execute()
    return {"status": "ok", "next_step": "vark"}



@router.post("/vark")
async def save_vark(body: VARKRequest, student=Depends(get_current_student)):
    # Assign intervention group randomly at onboarding completion
    intervention_group = random.choice(["treatment", "control"])

    supabase.table("students").update({
        "vark_questionnaire_label": body.label,
        "vark_questionnaire_scores": body.scores,
        "active_vark_label": body.label,
        "onboarding_step": "complete",
        "onboarding_complete": True,
        "intervention_group": intervention_group   # Change 9
    }).eq("student_id", student["student_id"]).execute()
    return {"status": "ok", "next_step": "complete"}



@router.post("/diagnostic")
async def save_diagnostic(body: DiagnosticRequest, student=Depends(get_current_student)):
    """
    Kept for backwards compatibility — not called by any active flow.
    The per-node anchor flow in /quiz/{node_id}/anchor replaces this.
    """
    from datetime import datetime


    anchor_questions = supabase.table("questions").select("*").eq("question_type", "anchor").execute().data
    anchor_map = {q["question_id"]: q for q in anchor_questions}


    total_score = 0
    records = []
    for ans in body.answers:
        q = anchor_map.get(ans["question_id"])
        if not q:
            continue
        correct = ans["selected_option"] == q["correct_option"]
        if correct:
            total_score += 1
        records.append({
            "student_id": student["student_id"],
            "test_type": "pre",
            "node_id": q["node_id"],
            "correct": correct,
            "time_taken_sec": ans.get("time_taken_sec"),
            "taken_at": datetime.utcnow().isoformat()
        })


    if records:
        supabase.table("anchor_scores").insert(records).execute()


    pre_score = round(total_score / len(body.answers), 4) if body.answers else 0.0


    supabase.table("students").update({
        "pre_test_overall": pre_score,
        "onboarding_step": "complete",
        "onboarding_complete": True
    }).eq("student_id", student["student_id"]).execute()


    return {"status": "ok", "pre_test_score": pre_score}
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
from db.supabase import supabase
from routers.deps import get_current_student

router = APIRouter()

class GoogleAuthRequest(BaseModel):
    access_token: str

class HeartbeatRequest(BaseModel):
    session_id: str

class LogoutRequest(BaseModel):
    session_id: str

@router.post("/google")
async def google_auth(body: GoogleAuthRequest):
    user_resp = supabase.auth.get_user(body.access_token)
    if not user_resp or not user_resp.user:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = user_resp.user
    auth_user_id = str(user.id)
    email = user.email

    existing = supabase.table("students").select("*").eq("auth_user_id", auth_user_id).execute()

    if existing.data:
        student = existing.data[0]
        session = supabase.table("sessions").insert({
            "student_id": student["student_id"],
            "login_at": datetime.utcnow().isoformat(),
        }).execute().data[0]

        supabase.table("interaction_log").insert({
            "student_id": student["student_id"],
            "session_id": session["session_id"],
            "event_type": "login",
            "entity_id": None,
            "value": None,
            "metadata": {}
        }).execute()

        supabase.table("students").update({
            "last_login_at": datetime.utcnow().isoformat()
        }).eq("student_id", student["student_id"]).execute()

        return {
            "status": "returning",
            "student_id": student["student_id"],
            "session_id": session["session_id"],
            "onboarding_complete": student["onboarding_complete"],
            "onboarding_step": student["onboarding_step"],
            "access_token": body.access_token
        }
    else:
        new_student = supabase.table("students").insert({
            "auth_user_id": auth_user_id,
            "email": email,
            "onboarding_step": "consent",
            "onboarding_complete": False,
        }).execute().data[0]

        session = supabase.table("sessions").insert({
            "student_id": new_student["student_id"],
            "login_at": datetime.utcnow().isoformat(),
        }).execute().data[0]

        supabase.table("interaction_log").insert({
            "student_id": new_student["student_id"],
            "session_id": session["session_id"],
            "event_type": "login",
            "entity_id": None,
            "value": None,
            "metadata": {}
        }).execute()

        return {
            "status": "new",
            "student_id": new_student["student_id"],
            "session_id": session["session_id"],
            "onboarding_complete": False,
            "onboarding_step": "consent",
            "access_token": body.access_token
        }

@router.post("/logout")
async def logout(body: LogoutRequest, student=Depends(get_current_student)):
    now = datetime.utcnow().isoformat()
    session = supabase.table("sessions").select("*").eq("session_id", body.session_id).execute().data
    if session:
        login_at = datetime.fromisoformat(session[0]["login_at"])
        duration = int((datetime.utcnow() - login_at).total_seconds())
        supabase.table("sessions").update({
            "logout_at": now,
            "duration_seconds": duration,
            "completed": True
        }).eq("session_id", body.session_id).execute()

    supabase.table("interaction_log").insert({
        "student_id": student["student_id"],
        "session_id": body.session_id,
        "event_type": "logout",
        "entity_id": None,
        "value": None,
        "metadata": {}
    }).execute()

    return {"status": "logged_out"}

@router.post("/heartbeat")
async def heartbeat(body: HeartbeatRequest, student=Depends(get_current_student)):
    supabase.table("sessions").update({
        "last_heartbeat_at": datetime.utcnow().isoformat()
    }).eq("session_id", body.session_id).execute()
    return {"status": "ok"}
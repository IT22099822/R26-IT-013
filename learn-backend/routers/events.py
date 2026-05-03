from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from db.supabase import supabase
from routers.deps import get_current_student
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class EventRequest(BaseModel):
    session_id: str
    event_type: str
    entity_id: Optional[str] = None
    value: Optional[float] = None
    metadata: Optional[dict] = {}

class ScrollRequest(BaseModel):
    session_id: str
    node_id: str
    scroll_pct: float

class VideoRequest(BaseModel):
    session_id: str
    node_id: str
    event_type: str
    value: Optional[float] = 0.0

class AudioRequest(BaseModel):
    session_id: str
    node_id: str
    event_type: str
    value: Optional[float] = 0.0

def log_interaction(student_id, session_id, event_type, entity_id=None, value=None, metadata={}):
    # Logging must never be able to take down the endpoint it's attached
    # to — an empty/invalid session_id (e.g. localStorage cleared, or a
    # frontend bug bypassing the tracker's own guard) would otherwise
    # crash on the UUID column with an unhandled exception, exactly like
    # what happened here: a broken analytics call bounced a student out
    # of a quiz that had already loaded successfully.
    if not session_id:
        logger.warning(f"log_interaction skipped: empty session_id "
                        f"(student={student_id}, event={event_type})")
        return
    try:
        supabase.table("interaction_log").insert({
            "student_id": student_id,
            "session_id": session_id,
            "event_type": event_type,
            "entity_id": entity_id,
            "value": value,
            "metadata": metadata,
            "timestamp": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"log_interaction failed (student={student_id}, "
                     f"event={event_type}, session={session_id}): {e}")

@router.post("/log")
async def log_event(event: EventRequest, student=Depends(get_current_student)):
    log_interaction(student["student_id"], event.session_id, event.event_type,
                    event.entity_id, event.value, event.metadata)

    if event.event_type == "question_attempt":
        try:
            from services.bkt import bkt_service
            from services.irt import irt_service
            node_id = event.metadata.get("node_id")
            difficulty = event.metadata.get("difficulty_tag", 0.0)
            await bkt_service.update(student["student_id"], node_id, int(event.value))
            await irt_service.update(student["student_id"], difficulty, int(event.value))
        except Exception as e:
            logger.error(f"BKT/IRT update failed: {e}")

    if event.event_type == "audio_play":
        _increment_unit_field(student["student_id"], event.entity_id, "audio_play_count")

    if event.event_type == "audio_complete":
        supabase.table("unit_progress").update({"audio_complete": True}).eq(
            "student_id", student["student_id"]).eq("node_id", event.entity_id).execute()

    if event.event_type == "login":
        supabase.table("students").update({
            "last_login_at": datetime.utcnow().isoformat()
        }).eq("student_id", student["student_id"]).execute()

    return {"status": "logged"}

@router.post("/scroll")
async def log_scroll(body: ScrollRequest, student=Depends(get_current_student)):
    log_interaction(student["student_id"], body.session_id, "scroll_milestone",
                    body.node_id, body.scroll_pct)
    supabase.table("unit_progress").upsert({
        "student_id": student["student_id"],
        "node_id": body.node_id,
        "scroll_depth_pct": body.scroll_pct
    }, on_conflict="student_id,node_id").execute()
    return {"status": "logged"}

@router.post("/video")
async def log_video(body: VideoRequest, student=Depends(get_current_student)):
    log_interaction(student["student_id"], body.session_id, body.event_type,
                    body.node_id, body.value)
    if body.event_type == "video_complete":
        supabase.table("unit_progress").upsert({
            "student_id": student["student_id"],
            "node_id": body.node_id,
            "video_watch_pct": 1.0
        }, on_conflict="student_id,node_id").execute()
    elif body.event_type == "video_pause":
        supabase.table("unit_progress").upsert({
            "student_id": student["student_id"],
            "node_id": body.node_id,
            "video_watch_pct": body.value
        }, on_conflict="student_id,node_id").execute()
    elif body.event_type == "video_replay":
        result = supabase.table("unit_progress").select("video_replay_count").eq(
            "student_id", student["student_id"]).eq("node_id", body.node_id).execute()
        count = result.data[0]["video_replay_count"] + 1 if result.data else 1
        supabase.table("unit_progress").upsert({
            "student_id": student["student_id"],
            "node_id": body.node_id,
            "video_replay_count": count
        }, on_conflict="student_id,node_id").execute()
    return {"status": "logged"}

@router.post("/audio")
async def log_audio(body: AudioRequest, student=Depends(get_current_student)):
    log_interaction(student["student_id"], body.session_id, body.event_type,
                    body.node_id, body.value)
    if body.event_type == "audio_play":
        _increment_unit_field(student["student_id"], body.node_id, "audio_play_count")
    if body.event_type == "audio_complete":
        supabase.table("unit_progress").upsert({
            "student_id": student["student_id"],
            "node_id": body.node_id,
            "audio_complete": True
        }, on_conflict="student_id,node_id").execute()
    return {"status": "logged"}

def _increment_unit_field(student_id, node_id, field):
    result = supabase.table("unit_progress").select(field).eq(
        "student_id", student_id).eq("node_id", node_id).execute()
    current = result.data[0][field] + 1 if result.data and result.data[0][field] else 1
    supabase.table("unit_progress").upsert({
        "student_id": student_id,
        "node_id": node_id,
        field: current
    }, on_conflict="student_id,node_id").execute()
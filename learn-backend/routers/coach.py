"""LEARN Coach chat endpoint (Dropout Risk Prediction follow-up).

POST /coach/chat
  body: {"messages": [{"role": "user"|"assistant", "content": str}, ...],
         "intervention_id": optional str}
  Send an empty messages list to get the coach's opening message.
  returns: {"reply", "facts", "actions", "safety"}"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db.supabase import supabase
from routers.deps import get_current_student
from services.coach import MAX_CHARS, clean_history, coach_service, suggested_actions
from services.learner_facts import build_learner_facts_async

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatTurn] = []
    intervention_id: Optional[str] = None


@router.post("/chat")
async def chat(body: ChatRequest, student=Depends(get_current_student)):
    sid = student["student_id"]
    raw = [t.model_dump() for t in body.messages]
    if raw and raw[-1]["role"] == "user" and len(raw[-1]["content"]) > MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"Please keep messages under {MAX_CHARS} characters.")
    history = clean_history(raw)
    if history and history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="The last message must be from the learner.")
    if coach_service.rate_limited(sid):
        raise HTTPException(status_code=429, detail="You've sent a lot of messages. Take a short break and try again in a few minutes.")

    # The check-in message the learner is replying to, only if it is theirs
    intervention_message = None
    if body.intervention_id:
        rows = supabase.table("interventions").select("message_sent").eq(
            "intervention_id", body.intervention_id).eq("student_id", sid).execute().data
        if rows:
            intervention_message = rows[0].get("message_sent")

    facts = await build_learner_facts_async(student)
    try:
        out = coach_service.reply(facts, history, intervention_message)
    except Exception as e:
        logger.error(f"coach reply failed for {sid}: {e}")
        raise HTTPException(status_code=503, detail="The coach can't reply right now. Please try again in a moment.")

    if history:
        coach_service.log(sid, body.intervention_id, "user", history[-1]["content"])
    coach_service.log(sid, body.intervention_id, "assistant", out["reply"])
    return {"reply": out["reply"], "safety": out["safety"], "facts": facts, "actions": suggested_actions(facts)}

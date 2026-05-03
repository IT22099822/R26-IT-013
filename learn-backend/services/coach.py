"""LEARN Coach: a chat window for learners the dropout model has flagged (or
anyone who opens it). Every reply is grounded in the learner's real progress
facts from services/learner_facts.py and generated through Groq.

Design choices:
- Stateless: the browser sends the recent turns with each request, so a
  failed save never breaks the chat. Turns are logged best-effort to the
  coach_messages table (see sql/coach_messages.sql) for research and audit.
- Only 'user' and 'assistant' roles are accepted from the client, so a
  learner cannot inject system instructions.
- A message that signals a personal crisis gets a fixed, safe reply without
  calling the LLM."""
import logging
import re
import time
from collections import defaultdict, deque

from groq import Groq

from config import settings
from db.supabase import supabase
from services.learner_facts import facts_to_text

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"     # same Groq model as the other LLM features
MAX_TOKENS = 700                  # gpt-oss counts its (low-effort) reasoning in this budget
TEMPERATURE = 0.6
MAX_TURNS = 12                    # most recent turns sent to the model
MAX_CHARS = 1000                  # per learner message
RATE_LIMIT = 30                   # messages per learner ...
RATE_WINDOW_SEC = 600             # ... per 10 minutes

CRISIS_PATTERN = re.compile(
    r"\b(kill(ing)? myself|suicid\w*|end(ing)? my life|want to die|self[- ]?harm\w*|hurt(ing)? myself)\b", re.I)
CRISIS_REPLY = (
    "I'm really sorry you're feeling this way, and I'm glad you said something. "
    "I'm only a study assistant, so please talk to someone who can support you properly right now: "
    "a friend or family member you trust, SLIIT's student counselling service, or the "
    "1926 National Mental Health Helpline in Sri Lanka. If you are in immediate danger, call 1990 or go to "
    "the nearest hospital. Your English studies can wait. You matter more."
)

STYLE_TIPS = {
    "Visual": "suggest the lesson videos, diagrams and colour-coded notes",
    "Auditory": "suggest listening to the audio, reading aloud and talking examples through",
    "Reading/Writing": "suggest reading the lesson text and writing short example sentences",
    "Kinesthetic": "suggest hands-on practice: doing quiz questions and trying sentences out",
}


def system_prompt(facts: dict, intervention_message: str = None) -> str:
    sent = (f'\nThe platform recently sent the learner this check-in message:\n"{intervention_message}"\n'
            if intervention_message else "")
    return f"""You are LEARN Coach, a friendly English-learning coach inside the LEARN platform, a SLIIT research platform for Sri Lankan undergraduates learning English.

You can see this learner's real progress data:
{facts_to_text(facts)}
{sent}
Rules:
- Use ONLY the numbers in the data above. Never invent scores, counts, percentages or dates. If asked something the data does not show, say you can't see that.
- Talk about their English learning, motivation, study planning and how to use this platform. If they go off-topic, answer briefly and kindly steer back.
- Be warm, encouraging and specific. Never shame or guilt them. If they say they want to quit, respond with empathy, ask what is making it hard, offer a lighter plan, and respect their choice.
- When useful, give ONE small, concrete next step (for example: "answer about 3 more Present Simple questions correctly to master it").
- Their learning style is {facts['learning_style']}: {STYLE_TIPS.get(facts['learning_style'], '')}.
- Keep replies short: 2 to 5 sentences, plain friendly English suitable for an English learner. No tables, no headings.
- You are an AI coach, not a human or a teacher; say so if asked. Do not give medical, legal or financial advice."""


def suggested_actions(facts: dict) -> list:
    """Deterministic buttons built from the facts, not from the LLM."""
    actions = []
    if facts.get("active_lesson"):
        a = facts["active_lesson"]
        actions.append({"label": f"Continue {a['name']}", "href": f"/learn/{a['node_id']}"})
    for g in facts.get("weak_skills", [])[:1]:
        actions.append({"label": f"Review {g['name']}", "href": f"/learn/{g['node_id']}"})
    actions.append({"label": "See my progress", "href": "/progress"})
    return actions


def clean_history(messages: list) -> list:
    """Keep only well-formed user/assistant turns, newest MAX_TURNS, each trimmed."""
    out = []
    for m in messages or []:
        role, content = m.get("role"), (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:MAX_CHARS]})
    return out[-MAX_TURNS:]


class CoachService:
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)
        self._hits = defaultdict(deque)

    def rate_limited(self, student_id: str, now: float = None) -> bool:
        now = time.time() if now is None else now
        q = self._hits[student_id]
        while q and now - q[0] > RATE_WINDOW_SEC:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return True
        q.append(now)
        return False

    def _llm(self, messages: list) -> str:
        r = self.client.chat.completions.create(
            model=MODEL, messages=messages, max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE, reasoning_effort="low")
        return (r.choices[0].message.content or "").strip()

    def reply(self, facts: dict, history: list, intervention_message: str = None) -> dict:
        """history: cleaned turns. Empty history -> opening message."""
        if history and history[-1]["role"] == "user" and CRISIS_PATTERN.search(history[-1]["content"]):
            return {"reply": CRISIS_REPLY, "safety": True}
        msgs = [{"role": "system", "content": system_prompt(facts, intervention_message)}]
        if not history:
            msgs.append({"role": "user", "content": (
                "(The learner just opened the coach. Greet them in 2-3 sentences: mention one real piece of "
                "their progress, one specific next step with its number, and ask how their studying is going.)")})
        else:
            msgs += history
        text = self._llm(msgs)
        if not text:
            raise RuntimeError("empty reply from model")
        return {"reply": text, "safety": False}

    def log(self, student_id: str, intervention_id, role: str, content: str):
        try:
            supabase.table("coach_messages").insert({
                "student_id": student_id, "intervention_id": intervention_id,
                "role": role, "content": content[:4000]}).execute()
        except Exception as e:   # logging must never break the chat
            logger.warning(f"coach_messages log failed (table missing?): {e}")


coach_service = CoachService()

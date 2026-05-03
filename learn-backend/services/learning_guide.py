import logging
import json
import re

from groq import Groq

from config import settings
from db.supabase import supabase

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 200
TEMPERATURE = 0.7

VARK_FULL_NAME = {"V": "Visual", "A": "Auditory", "R": "Reading/Writing", "K": "Hands-on"}


class LearningGuideService:
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)

    def _vark_label(self, student: dict) -> str:
        raw = student.get("active_vark_label") or student.get("vark_questionnaire_label") or "R"
        return VARK_FULL_NAME.get(raw, "Reading/Writing")

    def _skill_names(self, node_ids: list) -> list:
        if not node_ids:
            return []
        rows = supabase.table("content_nodes").select("node_id,skill_name").in_(
            "node_id", node_ids
        ).execute().data
        return [r["skill_name"] for r in rows]

    def find_newly_unlocked(self, student_id: str, just_completed_node_id: str) -> list:
        """Nodes that become available now that just_completed_node_id is
        mastered — only ones causally connected to THIS completion (it's
        one of their prerequisites), not just anything already unlocked
        for unrelated reasons."""
        student = supabase.table("students").select("nodes_mastered").eq(
            "student_id", student_id
        ).execute().data[0]
        nodes_mastered = student.get("nodes_mastered") or []

        all_nodes = supabase.table("content_nodes").select("node_id,skill_name,prerequisites").execute().data
        unlocked = []
        for n in all_nodes:
            if n["node_id"] in nodes_mastered:
                continue
            prereqs = n.get("prerequisites") or []
            if just_completed_node_id not in prereqs:
                continue
            if all(p in nodes_mastered for p in prereqs):
                unlocked.append(n["skill_name"])
        return unlocked

    async def _call_llm(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            reasoning_effort="low",  # short natural-language message generation
            # needs no deep chain-of-thought; gpt-oss defaults to "medium"
            # which would otherwise silently eat into the token budget.
        )
        return response.choices[0].message.content.strip()

    async def module_complete_message(self, student_id: str, node_id: str, score_pct: float) -> dict:
        """Called right after a post-test finishes. Returns the mastery
        state AND a personalized coaching message referencing the
        student's actual history — the 'do you remember when we...'
        continuity the guide is meant to provide."""
        student = supabase.table("students").select(
            "active_vark_label,vark_questionnaire_label,bkt_mastery,nodes_mastered,current_gaps"
        ).eq("student_id", student_id).execute().data[0]

        node = supabase.table("content_nodes").select(
            "skill_name,cefr_level,prerequisites"
        ).eq("node_id", node_id).execute().data[0]

        mastery = student.get("bkt_mastery", {}).get(node_id, 0.0)
        vark_full = self._vark_label(student)
        prior_related = self._skill_names(node.get("prerequisites") or [])
        gap_names = self._skill_names(student.get("current_gaps") or [])
        newly_unlocked = self.find_newly_unlocked(student_id, node_id)

        prompt = f"""You are a warm, encouraging AI learning guide for an English learner on an adaptive learning platform.

The student just completed: "{node['skill_name']}" ({node['cefr_level']} level)
Post-test score: {score_pct:.0f}%
Mastery of this topic: {mastery*100:.0f}%
Learning style: {vark_full}
{"This built on skills they already mastered: " + ", ".join(prior_related) if prior_related else ""}
{"They still have some gaps worth revisiting: " + ", ".join(gap_names) if gap_names else ""}
{"This unlocks: " + ", ".join(newly_unlocked) if newly_unlocked else ""}

Write a short (2-4 sentence), SPECIFIC message (not generic) that reacts HONESTLY to how THIS specific attempt actually went — do not celebrate a score below 50%, even if standing mastery from earlier practice is high. That combination (low score, high mastery) is a genuine, worth-naming discrepancy, not something to paper over:
- If the score is 70%+: genuinely congratulate them, referencing the actual skill by name
- If the score is 50-70%: acknowledge solid effort without overselling it
- If the score is below 50%: do NOT congratulate or say "mastered" — honestly acknowledge this attempt was tough, without shame, and note that practice mastery and this test result don't fully agree, which is worth a closer look
- If there's a related prior skill, briefly connect the dots (e.g. "Remember when we worked on X? This built directly on that.")
- Clearly states one next step — a newly unlocked lesson if one exists AND the score was good, otherwise suggest revisiting a gap or this lesson's material again
- Matches a {vark_full} learning style in tone

Output only the message text, no preamble, no quotation marks."""

        try:
            message = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"module_complete_message LLM call failed: {e}")
            message = f"Great work completing {node['skill_name']}! Keep going."

        return {
            "mastery": mastery,
            "is_mastered": node_id in (student.get("nodes_mastered") or []),
            "newly_unlocked": newly_unlocked,
            "message": message,
        }

    async def generate_gap_review(self, student_id: str, node_id: str) -> dict:
        """Generates a short, VARK-styled review explanation for a
        specific skill gap — the actual content-generation half of the
        original TAF's Knowledge Gap Predictor novelty claim
        ('automatically create review lessons... generate exact content
        needed to fill each student's specific gaps'), which previously
        only existed as a short nudge message (gap_nudge_message above),
        not actual explanatory content. Includes a lightweight
        automated quality check before returning anything, matching
        the same review-before-serving principle already applied to
        generated questions — scaled to what a short explanation
        actually needs, not copied wholesale from the question rubric."""
        student = supabase.table("students").select(
            "active_vark_label,vark_questionnaire_label"
        ).eq("student_id", student_id).execute().data[0]
        node = supabase.table("content_nodes").select(
            "skill_name,cefr_level,summary"
        ).eq("node_id", node_id).execute().data[0]

        vark_raw = student.get("active_vark_label") or student.get("vark_questionnaire_label") or "R"
        vark_full = VARK_FULL_NAME.get(vark_raw, "Reading/Writing")

        vark_instruction = {
            "V": "Include a small, genuinely useful markdown table (2-4 rows) breaking down the key pattern — do not leave this out.",
            "K": "Frame the explanation around one real, practical situation (texting a friend, ordering food, a quick work message) that shows the pattern in use.",
        }.get(vark_raw, "")

        prompt = f"""You are writing a short review explanation for an undergraduate Sri Lankan ESL student who is struggling with this specific skill: "{node['skill_name']}" ({node['cefr_level']} level).

Skill summary: {node.get('summary', '')}
Learning style to favor: {vark_full}
{vark_instruction}

Write a short (3-5 sentence) explanation that re-teaches the core idea plainly, as if explaining it for the first time to someone who found the original lesson confusing — not a summary of what they already saw, an actual re-explanation using different, simpler words or a different example.

Respond with ONLY a JSON object, no markdown fences, no extra text:
{{"explanation": "...", "visual_aid_markdown": null}}"""

        try:
            raw = await self._call_llm(prompt)
            cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw.strip(), flags=re.MULTILINE)
            content = json.loads(cleaned)
        except Exception as e:
            logger.error(f"generate_gap_review failed for node {node_id}: {e}")
            return None

        # Lightweight quality check — scaled to what a short explanation
        # actually needs (factually sound, genuinely re-explains rather
        # than just repeating the original wording), not the full
        # question-bank IWF rubric, which checks things (distractor
        # plausibility, answer-key correctness) that don't apply here.
        check_prompt = f"""Review this English-skill explanation for a struggling student.
Skill: {node['skill_name']}
Explanation: {content.get('explanation', '')}

Check: is this factually correct, and does it actually explain the concept clearly (not just vague or circular)?
Respond with ONLY: {{"pass": true/false}}"""
        try:
            check_raw = await self._call_llm(check_prompt)
            check_cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', check_raw.strip(), flags=re.MULTILINE)
            check_result = json.loads(check_cleaned)
            if not check_result.get("pass", False):
                logger.warning(f"Gap review for node {node_id} failed quality check, not returning it")
                return None
        except Exception as e:
            logger.error(f"Gap review quality check failed for node {node_id}: {e} — not returning unverified content")
            return None

        return {
            "node_id": node_id,
            "skill_name": node["skill_name"],
            "explanation": content.get("explanation", ""),
            "visual_aid_markdown": content.get("visual_aid_markdown") or None,
        }


        student = supabase.table("students").select(
            "active_vark_label,vark_questionnaire_label,current_gaps"
        ).eq("student_id", student_id).execute().data[0]
        gap_names = self._skill_names(student.get("current_gaps") or [])
        if not gap_names:
            return None
        vark_full = self._vark_label(student)

        prompt = f"""You are a warm, encouraging AI learning guide for an English learner.

The student has a gap worth revisiting: "{gap_names[0]}"
Learning style: {vark_full}

Write a short (2-3 sentence), gentle nudge that:
- Kindly points out that revisiting "{gap_names[0]}" first could help, without sounding critical
- Frames it as helpful, not a failure
- Matches a {vark_full} learning style in tone

Output only the message text, no preamble, no quotation marks."""

        try:
            return await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"gap_nudge_message LLM call failed: {e}")
            return f"It might help to revisit {gap_names[0]} before continuing."

    async def lesson_intro_message(self, student_id: str, node_id: str) -> str:
        student = supabase.table("students").select(
            "active_vark_label,vark_questionnaire_label"
        ).eq("student_id", student_id).execute().data[0]
        node = supabase.table("content_nodes").select(
            "skill_name,cefr_level,prerequisites"
        ).eq("node_id", node_id).execute().data[0]
        vark_full = self._vark_label(student)
        prior = self._skill_names(node.get("prerequisites") or [])

        prompt = f"""You are a warm, encouraging AI learning guide for an English learner.

The student is starting: "{node['skill_name']}" ({node['cefr_level']} level)
Learning style: {vark_full}
{"They just came from: " + ", ".join(prior) if prior else ""}

Write a short (2-3 sentence) friendly welcome that:
- Introduces this new topic with genuine warmth
- If relevant, briefly connects it to what they just finished
- Encourages them to explore the lesson in whatever format works best for them (video, audio, reading, or practice)

Output only the message text, no preamble, no quotation marks."""

        try:
            return await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"lesson_intro_message LLM call failed: {e}")
            return f"Welcome to {node['skill_name']}! Explore it in whatever way suits you best."


learning_guide_service = LearningGuideService()
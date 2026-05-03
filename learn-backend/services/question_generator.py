import json
import logging
import re
import uuid

from groq import Groq

from config import settings
from db.supabase import supabase

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.8  # a bit more variety than the guide messages — these
                    # shouldn't feel identical attempt to attempt
MAX_TOKENS = 3000

# Offsets from the student's current ability (theta), not raw absolute
# numbers — "just right" means centered at their actual 50%-success
# point, not a fixed universal value. Clamped to the valid IRT range.
DIFFICULTY_BAND_OFFSETS = {
    "easy": -1.5,
    "just_right": 0.0,
    "hard": 1.0,
    "impossible": 2.5,
}
VARK_FULL_NAME = {"V": "Visual", "A": "Auditory", "R": "Reading/Writing", "K": "Hands-on"}


class QuestionGeneratorService:
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)

    def resolve_target_difficulty(self, theta: float, band: str) -> float:
        offset = DIFFICULTY_BAND_OFFSETS.get(band, 0.0)
        return round(min(max(theta + offset, -4.0), 4.0), 2)

    def _get_exemplars(self, node_id: str, question_type: str, target_difficulty: float, limit: int = 3):
        """Real, genuinely-calibrated questions (never the placeholder
        difficulty_tag=0 ones) closest to the target difficulty, used
        as few-shot examples so the LLM matches your actual content
        style and difficulty scale, not a guess at what B1-level means."""
        rows = supabase.table("questions").select(
            "question_text,option_a,option_b,option_c,option_d,correct_option,difficulty_tag"
        ).eq("node_id", node_id).eq("question_type", question_type).eq(
            "status", "published"
        ).neq("difficulty_tag", 0).execute().data
        rows.sort(key=lambda q: abs(q["difficulty_tag"] - target_difficulty))
        return rows[:limit]

    def _build_prompt(self, node, exemplars, target_difficulty, band, count, question_type, vark_label):
        vark_full = VARK_FULL_NAME.get(vark_label, "Reading/Writing")
        band_desc = {
            "easy": "clearly easier than the examples below — basic, straightforward recall",
            "just_right": "roughly the same difficulty as the examples below",
            "hard": "clearly harder than the examples below — requires careful attention to detail",
            "impossible": "genuinely challenging, exam-level, with subtle distractors — a real stretch",
        }.get(band, "similar difficulty to the examples below")

        # VARK-specific content shaping — not exclusive to that type
        # (every question is still answerable and useful for anyone),
        # just emphasized differently. Reading/Writing gets no special
        # instruction since standard question style already suits it.
        vark_instruction = {
            "V": "Since this student learns best visually: for EVERY question, include a compact markdown table (2-4 rows) in the 'visual_aid_markdown' field that breaks down the CORRECT sentence's grammar structure — e.g. columns for the relevant part (Subject/Verb/etc.), the actual word, and why it takes that form. This table is always constructible for a grammar question, so do not leave it null.",
            "K": "Since this student learns best hands-on: frame the question as a real, practical situation (texting a friend, ordering food, writing a quick work email) that still tests the exact same grammar concept — not an abstract fill-in-the-blank drill.",
        }.get(vark_label, "")

        examples_text = ""
        for i, ex in enumerate(exemplars, 1):
            examples_text += f"""
Example {i}:
Question: {ex['question_text']}
A) {ex['option_a']}
B) {ex['option_b']}
C) {ex['option_c']}
D) {ex['option_d']}
Correct answer: {ex['correct_option']}
"""

        visual_aid_example = (
            '"visual_aid_markdown": "| Part | Word | Why |\\\\n|---|---|---|\\\\n| Subject | cat | singular |\\\\n| Verb | sits | matches singular subject |"'
            if vark_label == "V"
            else '"visual_aid_markdown": null'
        )

        return f"""You are writing English grammar practice questions for undergraduate Sri Lankan ESL students.

Skill: {node['skill_name']} ({node['cefr_level']} level)
Question type: {question_type}
Target difficulty: {band_desc}
Learning style to favor in phrasing: {vark_full}
{vark_instruction}
{examples_text if examples_text else "(No calibrated examples available for this difficulty range — use your best judgment for the CEFR level.)"}

Generate exactly {count} NEW multiple-choice questions on this skill, at the target difficulty described above. Each question needs exactly 4 options (A-D), one correct answer, and a short (1-2 sentence) explanation of why the correct answer is right — written for a student who just got it wrong, not a generic textbook explanation.

Respond with ONLY a JSON array, no markdown code fences, no extra text, in exactly this format:
[
  {{
    "question_text": "...",
    "option_a": "...",
    "option_b": "...",
    "option_c": "...",
    "option_d": "...",
    "correct_option": "A",
    "explanation": "...",
    {visual_aid_example}
  }}
]"""

    def _parse_json_response(self, text: str) -> list:
        cleaned = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.MULTILINE)
        return json.loads(cleaned)

    def _is_truthy_verdict(self, value) -> bool:
        """Normalizes overall_pass across whatever form the LLM emits it
        in. Critical to get right: bool("false") is True in Python, so
        trusting a raw truthiness check on a string value could silently
        let a FAILING verdict through as a pass — the more dangerous
        direction of this class of bug, since it lets bad content
        through undetected rather than just being overly cautious."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() == "true"
        return False

    async def _evaluate_questions(self, candidates: list, band: str) -> tuple:
        """Automated screening pass before anything reaches a student —
        the LLM-critique item-screening approach from the AIG literature
        (e.g. automated item evaluation via LLM-generated critiques).
        This is NOT a substitute for eventual empirical recalibration
        from real response data (that's what graduates a question's
        status to 'published' and gives it full IRT weight) — it's a
        cheap, immediate quality gate that catches obviously broken
        answer keys or implausible distractors before they ever reach
        a student, batched into one call rather than one per question
        to keep generation latency reasonable.

        Returns (passed, failed) — BOTH lists, not just the survivors.
        Failed items are no longer silently discarded: saving them (as
        'evaluator_rejected', see generate_questions below) is what
        makes genuine human-AI agreement analysis possible later —
        Cohen's Kappa between this automated verdict and a human
        admin's review decision can only be computed if both verdicts
        exist for the same items, which requires keeping the ones this
        gate rejects, not just the ones it lets through."""
        if not candidates:
            return [], []

        items_text = ""
        for i, q in enumerate(candidates):
            items_text += f"""
Item {i}:
Question: {q['question_text']}
A) {q['option_a']}
B) {q['option_b']}
C) {q['option_c']}
D) {q['option_d']}
Stated correct answer: {q['correct_option']}
"""
        prompt = f"""You are reviewing multiple-choice questions for content quality before they're shown to a student.
{items_text}
For EACH item, check ONLY:
1. Is the stated correct answer definitely, unambiguously correct?
2. Are the three distractors clearly wrong (not accidentally also correct, not nonsensical)?

Do NOT judge whether the difficulty matches any target level — that can only be confirmed with real student response data, not by inspection, and is assessed separately.

Respond with ONLY a JSON array, one object per item in order, no markdown, no extra text:
[{{"index": 0, "overall_pass": true/false}}]"""

        try:
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.0,  # deterministic for a checking task, not a creative one
                reasoning_effort="low",  # a yes/no sanity check needs no deep chain-of-thought
            )
            verdicts = self._parse_json_response(response.choices[0].message.content)
            # LLMs are inconsistent about emitting JSON numbers as actual
            # numbers vs. quoted strings — int() normalizes either case.
            # Without this, a string index like "0" would never match the
            # integer 0 from enumerate() below, silently failing every
            # single question regardless of the actual verdict.
            passed_indices = {int(v["index"]) for v in verdicts if self._is_truthy_verdict(v.get("overall_pass"))}
            passed = [q for i, q in enumerate(candidates) if i in passed_indices]
            failed = [q for i, q in enumerate(candidates) if i not in passed_indices]
            if not passed:
                logger.warning(f"Evaluator passed 0 of {len(candidates)} questions — raw verdicts: {verdicts}")
            return passed, failed
        except Exception as e:
            logger.error(f"Question evaluation pass failed, discarding this batch to be safe: {e}")
            return [], []

    async def generate_questions(self, node_id: str, question_type: str, band: str,
                                  count: int, theta: float, vark_label: str = None) -> list:
        # Defensive normalization — every VARK check below does exact,
        # case-sensitive comparison against uppercase 'V'/'A'/'K'. If
        # this ever arrived lowercase or with stray whitespace, ALL of
        # those checks would silently fail together, not just the
        # visual aid one — the whole prompt would quietly degrade to
        # the generic Reading/Writing default for every student.
        vark_label = vark_label.strip().upper() if isinstance(vark_label, str) and vark_label.strip() else None

        logger.info(f"[QGEN] Starting generation: node={node_id} type={question_type} "
                    f"band={band} count={count} theta={theta} vark_label={vark_label!r}")

        node = supabase.table("content_nodes").select(
            "skill_name,cefr_level"
        ).eq("node_id", node_id).execute().data[0]

        target_difficulty = self.resolve_target_difficulty(theta, band)
        exemplars = self._get_exemplars(node_id, question_type, target_difficulty)
        logger.info(f"[QGEN] target_difficulty={target_difficulty}, found {len(exemplars)} real exemplars")

        prompt = self._build_prompt(node, exemplars, target_difficulty, band, count, question_type, vark_label)
        logger.info(f"[QGEN] vark_instruction active: {vark_label in ('V', 'K')} (label={vark_label!r})")

        response = self.client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            reasoning_effort="low",  # gpt-oss defaults to "medium", which was
            # silently burning a chunk of the token budget on internal
            # chain-of-thought before ever producing the actual JSON —
            # this is templated content generation, not a task that
            # benefits from deep reasoning.
        )
        raw = response.choices[0].message.content
        logger.info(f"[QGEN] Raw LLM response length: {len(raw)} chars")

        try:
            generated = self._parse_json_response(raw)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"[QGEN] Failed to parse generated questions JSON: {e}. Raw: {raw[:500]}")
            return []

        logger.info(f"[QGEN] Parsed {len(generated)} candidate questions")
        if vark_label == "V":
            has_visual = sum(1 for q in generated if q.get("visual_aid_markdown"))
            logger.info(f"[QGEN] Visual aid check: {has_visual}/{len(generated)} candidates "
                        f"actually included visual_aid_markdown")

        rows_to_insert = []
        for i, q in enumerate(generated):
            required = ['question_text', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_option']
            if not all(k in q and q[k] for k in required):
                logger.warning(f"[QGEN] Skipping malformed generated question at index {i}: {q}")
                continue
            rows_to_insert.append({
                "question_id": f"{node_id}-GEN-{question_type[:4].upper()}-{uuid.uuid4().hex[:8]}",
                "node_id": node_id,
                "question_type": question_type,
                "question_text": q["question_text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q["option_c"],
                "option_d": q["option_d"],
                "correct_option": q["correct_option"].upper()[:1],
                "explanation": q.get("explanation", ""),
                "visual_aid_markdown": q.get("visual_aid_markdown") or None,
                "difficulty_tag": target_difficulty,
                "vark_type": vark_label,
                "source": "generated",
                "status": "pending_review",
            })

        if not rows_to_insert:
            logger.warning("[QGEN] No valid rows survived field validation — returning empty")
            return []

        # Screening gate — nothing reaches a student without passing this.
        # Failed items are now saved too (status='evaluator_rejected',
        # never served to anyone) specifically so a human reviewer can
        # later check the automated evaluator's judgment against their
        # own — see the admin moderation endpoints for the resulting
        # Cohen's Kappa agreement calculation.
        passed, failed = await self._evaluate_questions(rows_to_insert, band)

        for q in passed:
            q["status"] = "pending_review"
            q["evaluator_verdict"] = True
        for q in failed:
            q["status"] = "evaluator_rejected"
            q["evaluator_verdict"] = False

        all_rows = passed + failed
        if not all_rows:
            logger.warning(f"[QGEN] Evaluation produced nothing to save for node {node_id}")
            return []

        inserted = supabase.table("questions").insert(all_rows).execute().data
        logger.info(f"[QGEN] Inserted {len(passed)} passed + {len(failed)} rejected "
                    f"(rejected are saved for review, never served to students). "
                    f"visual_aid_markdown present on passed: {[bool(q.get('visual_aid_markdown')) for q in inserted if q.get('status') == 'pending_review']}")
        # Only ever return the passed, servable questions to the caller
        return [q for q in inserted if q.get("status") == "pending_review"]


question_generator_service = QuestionGeneratorService()
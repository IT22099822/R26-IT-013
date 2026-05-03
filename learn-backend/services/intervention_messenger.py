import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from groq import Groq

from config import settings
from db.supabase import supabase
from services.learner_facts import build_learner_facts_async, facts_to_text

logger = logging.getLogger(__name__)

MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 220
TEMPERATURE = 0.7

VARK_FULL_NAME = {"V": "Visual", "A": "Auditory", "R": "Reading/Writing", "K": "Kinesthetic"}


class InterventionMessenger:
    def __init__(self):
        self.client = Groq(api_key=settings.groq_api_key)

    async def _gather_context(self, student_id: str):
        """Real per-learner facts (lessons completed, last week's activity,
        weak skills with how many more correct answers each needs, the IRT
        projection) from services/learner_facts.py, the same facts the coach
        chat uses. Never raw model internals such as theta values."""
        student = supabase.table("students").select("*").eq("student_id", student_id).execute().data
        if not student:
            return None
        facts = await build_learner_facts_async(student[0])
        facts["email"] = student[0].get("email")
        return facts

    def _build_motivation_prompt(self, ctx: dict) -> str:
        focus = (ctx["weak_skills"][0] if ctx["weak_skills"] else ctx["active_lesson"])
        focus_text = (f"{focus['name']} (about {focus['questions_to_master']} more correct answers to master it)"
                      if focus else "their recent topics")
        return f"""You are helping an undergraduate Sri Lankan student learn English who is at risk of dropping out of an online course.

Student facts (all real, from the platform):
{facts_to_text(ctx)}

Write a short, warm, supportive message (3-4 sentences) that:
- Does not shame or guilt the student
- Mentions their real progress using the facts above (for example lessons completed)
- Suggests one specific next step: {focus_text}, quoting that number exactly
- Proposes one small, realistic action for this week (e.g., two short sessions)
- Matches a {ctx['learning_style']} learning style in tone
- Uses ONLY numbers that appear in the facts above; never invent any other figure

Output only the message text, no preamble, no quotation marks, no explanation."""

    async def _call_llm(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            reasoning_effort="low",
        )
        return response.choices[0].message.content.strip()

    async def compose_message(self, student_id: str):
        """One personalised message for one student, or None if there is no
        context. Used by the weekly pipeline below and by the admin demo seeder,
        so a seeded demo shows exactly what live generation produces."""
        ctx = await self._gather_context(student_id)
        if ctx is None:
            return None
        return await self._call_llm(self._build_motivation_prompt(ctx))

    async def generate_pending_messages(self):
        """Finds every intervention still missing a message and fills
        it in. Only sets message_sent here — NOT sent_at. sent_at means
        actually delivered by email (see send_pending_emails below), not
        just generated. Keeping these separate means a delivery failure
        doesn't force wasteful LLM re-generation on retry."""
        pending = supabase.table("interventions").select(
            "intervention_id,student_id"
        ).is_("message_sent", "null").execute().data

        sent, failed = 0, 0
        for row in pending:
            try:
                ctx = await self._gather_context(row["student_id"])
                if ctx is None:
                    continue
                prompt = self._build_motivation_prompt(ctx)
                message = await self._call_llm(prompt)

                supabase.table("interventions").update({
                    "message_sent": message,
                }).eq("intervention_id", row["intervention_id"]).execute()
                sent += 1
            except Exception as e:
                failed += 1
                logger.error(f"Message generation failed for intervention "
                             f"{row['intervention_id']} (student {row['student_id']}): {e}")

        logger.info(f"Intervention messages generated: {sent}, {failed} failed, "
                    f"{len(pending) - sent - failed} skipped (no context)")
        return sent, failed

    def _send_email(self, to_email: str, subject: str, body: str):
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.gmail_address
        msg["To"] = to_email

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.gmail_address, settings.gmail_app_password)
            server.sendmail(settings.gmail_address, [to_email], msg.as_string())

    async def send_pending_emails(self):
        """Actually delivers every intervention that has a generated
        message but hasn't been emailed yet. This is also the step that
        reaches students who AREN'T logging in — the in-app popup alone
        can never reach the exact students it's meant for."""
        if not settings.gmail_address or not settings.gmail_app_password:
            logger.info("Email delivery skipped: GMAIL_ADDRESS/GMAIL_APP_PASSWORD not configured")
            return 0, 0

        pending = supabase.table("interventions").select(
            "intervention_id,student_id,message_sent"
        ).not_.is_("message_sent", "null").is_("sent_at", "null").execute().data

        sent, failed = 0, 0
        for row in pending:
            try:
                student = supabase.table("students").select("email").eq(
                    "student_id", row["student_id"]
                ).execute().data
                if not student or not student[0].get("email"):
                    failed += 1
                    continue

                self._send_email(
                    to_email=student[0]["email"],
                    subject="A quick note about your English learning progress",
                    body=row["message_sent"],
                )

                supabase.table("interventions").update({
                    "sent_at": datetime.utcnow().isoformat(),
                }).eq("intervention_id", row["intervention_id"]).execute()
                sent += 1
            except Exception as e:
                failed += 1
                logger.error(f"Email delivery failed for intervention "
                             f"{row['intervention_id']} (student {row['student_id']}): {e}")

        logger.info(f"Intervention emails: {sent} sent, {failed} failed, "
                    f"{len(pending) - sent - failed} skipped (no email on file)")
        return sent, failed


intervention_messenger = InterventionMessenger()
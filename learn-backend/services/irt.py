from scipy.optimize import minimize_scalar
from math import log, exp
from datetime import datetime
from db.supabase import supabase
from services.question_generator import DIFFICULTY_BAND_OFFSETS

# Generated-but-not-yet-empirically-validated questions still count
# toward ability — excluding them entirely would mean on-demand
# personalized practice never affects the student's actual profile,
# which defeats the point. But their difficulty_tag is the LLM's
# stated TARGET, not a measured value (the "cold-start problem" in the
# automatic item generation literature), so they get reduced influence
# until real response data lets them be empirically recalibrated —
# the same anchor-based approach already used for the real question
# bank, extended to generated items once enough responses exist. Once
# recalibrated, a question's status flips to 'published' and it
# carries full weight like any other question.
PUBLISHED_WEIGHT = 1.0
UNVALIDATED_WEIGHT = 0.3


class IRTService:

    async def _gather_weighted_responses(self, student_id: str) -> list:
        """Shared by update() and project_improvement() so both use
        identical response-gathering and weighting logic — extracted
        specifically to avoid this fairly complex logic silently
        drifting out of sync between the two call sites."""
        practice_rows = supabase.table("question_attempts").select(
            "correct,difficulty_tag,question_id"
        ).eq("student_id", student_id).execute().data

        anchor_rows = supabase.table("anchor_scores").select(
            "correct,question_id").eq("student_id", student_id).execute().data

        all_qids = list({r["question_id"] for r in practice_rows + anchor_rows if r.get("question_id")})
        status_lookup = {}
        difficulty_lookup = {}
        if all_qids:
            for q in supabase.table("questions").select(
                "question_id,difficulty_tag,status"
            ).in_("question_id", all_qids).execute().data:
                status_lookup[q["question_id"]] = q.get("status")
                difficulty_lookup[q["question_id"]] = q.get("difficulty_tag")

        responses = []
        for r in practice_rows:
            diff = r.get("difficulty_tag")
            if diff is None:
                diff = difficulty_lookup.get(r.get("question_id"))
            responses.append({
                "correct": r["correct"], "difficulty_tag": diff,
                "status": status_lookup.get(r.get("question_id"), "published"),
            })
        for r in anchor_rows:
            responses.append({
                "correct": r["correct"],
                "difficulty_tag": difficulty_lookup.get(r["question_id"]),
                "status": status_lookup.get(r["question_id"], "published"),
            })
        return responses

    def _fit_theta(self, responses: list) -> float:
        def neg_log_likelihood(theta_val):
            ll = 0.0
            for resp in responses:
                if resp["difficulty_tag"] is None:
                    continue
                weight = PUBLISHED_WEIGHT if resp["status"] == "published" else UNVALIDATED_WEIGHT
                p = 1 / (1 + exp(-(theta_val - resp["difficulty_tag"])))
                ll += weight * (log(p + 1e-10) if resp["correct"] else log(1 - p + 1e-10))
            return -ll
        result = minimize_scalar(neg_log_likelihood, bounds=(-4, 4), method="bounded")
        return round(result.x, 4)

    async def update(self, student_id: str, b: float, correct: int):
        student = supabase.table("students").select(
            "irt_theta,irt_theta_history").eq("student_id", student_id).execute().data[0]

        responses = await self._gather_weighted_responses(student_id)
        new_theta = self._fit_theta(responses)

        history = student.get("irt_theta_history") or []
        history.append({"date": datetime.utcnow().isoformat(), "theta": new_theta})

        supabase.table("students").update({
            "irt_theta": new_theta,
            "irt_theta_history": history,
            "current_target_difficulty": new_theta
        }).eq("student_id", student_id).execute()

        return new_theta

    async def project_improvement(self, student_id: str, band: str, count: int) -> dict:
        """Answers 'if I answer N more [band]-difficulty questions
        correctly, how much would my ability actually move?' — by
        re-running the EXACT SAME real MLE fit used by update() above,
        with N hypothetical correct responses appended to the student's
        REAL existing history. This is a genuine projection using
        already-validated math, not a fabricated or hand-waved estimate.
        Never writes anything — pure read-only simulation."""
        student = supabase.table("students").select("irt_theta").eq(
            "student_id", student_id).execute().data
        current_theta = (student[0].get("irt_theta") if student else None) or 0.0

        responses = await self._gather_weighted_responses(student_id)

        offset = DIFFICULTY_BAND_OFFSETS.get(band, 0.0)
        hypothetical_difficulty = round(min(max(current_theta + offset, -4.0), 4.0), 2)

        hypothetical_responses = responses + [
            {"correct": True, "difficulty_tag": hypothetical_difficulty, "status": "published"}
            for _ in range(max(count, 0))
        ]

        projected_theta = self._fit_theta(hypothetical_responses)

        return {
            "current_theta": current_theta,
            "projected_theta": projected_theta,
            "delta": round(projected_theta - current_theta, 4),
            "band": band,
            "count": count,
        }


irt_service = IRTService()
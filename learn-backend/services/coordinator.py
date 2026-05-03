from db.supabase import supabase
from datetime import datetime, timedelta
import logging
import pytz

logger = logging.getLogger(__name__)
COLOMBO_TZ = pytz.timezone("Asia/Colombo")

RISK_THRESHOLD = 0.7   # matches the documented C4 spec; worth revisiting
                        # once real production data lets you tune this
                        # against an actual precision/recall curve
COOLDOWN_DAYS = 14      # don't message the same student more than once
                        # per this window, even if they stay high-risk


class CoordinatorService:
    async def log_only(self, student_id: str, event):
        try:
            supabase.table("coordinator_decisions").insert({
                "student_id": student_id,
                "timestamp": datetime.utcnow().isoformat(),
                "trigger_event": event.event_type,
                "rule_fired": "pilot_log_only",
                "final_decision": "no_action",
                "output_served": None
            }).execute()
        except Exception as e:
            logger.error(f"Coordinator log failed: {e}")

    async def should_intervene(self, student_id: str) -> bool:
        # Kept for any other trigger types that just need the group gate
        # alone. The dropout-risk flow uses evaluate_dropout_intervention()
        # below instead, which folds this same check into a fuller sequence.
        try:
            result = supabase.table("students").select(
                "intervention_group"
            ).eq("student_id", student_id).execute().data

            if not result:
                return False

            group = result[0].get("intervention_group")
            if group == "control":
                supabase.table("coordinator_decisions").insert({
                    "student_id": student_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "trigger_event": "dropout_risk_high",
                    "rule_fired": "intervention_check",
                    "final_decision": "intervention_suppressed_control_group",
                    "output_served": None
                }).execute()
                return False

            return True

        except Exception as e:
            logger.error(f"Coordinator intervention check failed for {student_id}: {e}")
            return False

    def _summarize_c4(self, risk_score, risk_trend, risk_reason):
        if risk_score is None:
            return "no risk score available"
        return f"risk={risk_score:.2f}, trend={risk_trend or 'unknown'}, reason={risk_reason or 'unspecified'}"

    async def _log_decision(self, student_id, trigger_event, rule_fired, final_decision,
                             output_served=None, agents_consulted=None,
                             c1_recommendation=None, c2_recommendation=None,
                             c3_recommendation=None, c4_recommendation=None,
                             override_reason=None):
        try:
            supabase.table("coordinator_decisions").insert({
                "student_id": student_id,
                "timestamp": datetime.utcnow().isoformat(),
                "trigger_event": trigger_event,
                "rule_fired": rule_fired,
                "agents_consulted": agents_consulted or [],
                "c1_recommendation": c1_recommendation,
                "c2_recommendation": c2_recommendation,
                "c3_recommendation": c3_recommendation,
                "c4_recommendation": c4_recommendation,
                "final_decision": final_decision,
                "output_served": output_served,
                "override_reason": override_reason,
            }).execute()
        except Exception as e:
            logger.error(f"Coordinator decision log failed: {e}")

    async def evaluate_dropout_intervention(self, student_id: str):
        """The real decision logic, run once per student per week right
        after dropout_service.score_student() writes their fresh
        dropout_risk_score. Checks group -> cooldown -> risk threshold
        in sequence; logs every outcome (even 'no action') for a full
        audit trail; creates a PENDING intervention row (message_sent
        stays NULL) when all three pass. Writing the actual message is
        a separate step — the LLM call — kept out of this function on
        purpose so 'decide who' and 'decide what to say' stay separable.
        """
        try:
            student = supabase.table("students").select(
                "intervention_group,dropout_risk_score,"
                "risk_trend,primary_risk_reason,last_intervention_at"
            ).eq("student_id", student_id).execute().data

            if not student:
                return None
            s = student[0]

            group = s.get("intervention_group")
            risk_score = s.get("dropout_risk_score")
            risk_trend = s.get("risk_trend")
            risk_reason = s.get("primary_risk_reason")
            c4_summary = self._summarize_c4(risk_score, risk_trend, risk_reason)

            # Gate 1: control group is always suppressed
            if group == "control":
                await self._log_decision(
                    student_id, trigger_event="dropout_risk_check",
                    rule_fired="control_group_suppression",
                    agents_consulted=["c4"], c4_recommendation=c4_summary,
                    final_decision="intervention_suppressed_control_group",
                )
                return "suppressed_control"

            # No risk score yet (brand new student) — nothing to evaluate,
            # and not worth logging noise for every new signup every week
            if risk_score is None:
                return None

            # Gate 2: cooldown — don't message the same student repeatedly
            if s.get("last_intervention_at"):
                try:
                    last = datetime.fromisoformat(s["last_intervention_at"])
                    if last.tzinfo is None:
                        last = COLOMBO_TZ.localize(last)
                    now = datetime.now(COLOMBO_TZ)
                    days_since = (now - last).days
                    if days_since < COOLDOWN_DAYS:
                        await self._log_decision(
                            student_id, trigger_event="dropout_risk_check",
                            rule_fired="cooldown_active",
                            agents_consulted=["c4"], c4_recommendation=c4_summary,
                            final_decision="suppressed_cooldown",
                        )
                        return "suppressed_cooldown"
                except Exception:
                    pass  # malformed timestamp — don't let cooldown parsing block a real decision

            # Gate 3: risk threshold
            if risk_score <= RISK_THRESHOLD:
                await self._log_decision(
                    student_id, trigger_event="dropout_risk_check",
                    rule_fired="below_risk_threshold",
                    agents_consulted=["c4"], c4_recommendation=c4_summary,
                    final_decision="no_action_below_threshold",
                )
                return "no_action_below_threshold"

            # All gates passed — create a pending intervention.
            weekly_row = supabase.table("weekly_stats").select("*").eq(
                "student_id", student_id
            ).order("week_number", desc=True).limit(1).execute().data
            trigger_criteria = weekly_row[0] if weekly_row else {}

            supabase.table("interventions").insert({
                "student_id": student_id,
                "risk_score": risk_score,
                "risk_reason": risk_reason,
                "message_sent": None,  # filled in by the LLM step, next
                "trigger_criteria": trigger_criteria,
                "requested_at": datetime.now(COLOMBO_TZ).isoformat(),
            }).execute()

            await self._log_decision(
                student_id, trigger_event="dropout_risk_check",
                rule_fired="intervention_triggered",
                agents_consulted=["c4"], c4_recommendation=c4_summary,
                final_decision="intervention_triggered",
                output_served="pending_message_generation",
            )

            supabase.table("students").update({
                "last_intervention_at": datetime.now(COLOMBO_TZ).isoformat()
            }).eq("student_id", student_id).execute()

            return "intervention_triggered"

        except Exception as e:
            logger.error(f"Coordinator evaluate_dropout_intervention failed for {student_id}: {e}")
            return None


    async def check_recovery(self):
        """Scans interventions sent >=7 days ago that haven't been
        recovery-checked yet, and records whether the student actually
        re-engaged in the 7 days after. Runs on its OWN daily schedule,
        not tied to the weekly Sunday pipeline — 'sent_at + 7 days' can
        land on any day of the week, so a weekly-only check would miss
        or badly delay most of these."""
        now = datetime.now(COLOMBO_TZ)
        cutoff = now - timedelta(days=7)

        pending = supabase.table("interventions").select(
            "intervention_id,student_id,sent_at"
        ).is_("recovery_checked", "null").not_.is_("sent_at", "null").execute().data

        checked = due_later = 0
        for row in pending:
            try:
                sent_at = datetime.fromisoformat(row["sent_at"])
                if sent_at.tzinfo is None:
                    sent_at = COLOMBO_TZ.localize(sent_at)
                if sent_at > cutoff:
                    due_later += 1
                    continue  # not 7 days out yet

                window_end = sent_at + timedelta(days=7)
                sid = row["student_id"]

                sessions = supabase.table("sessions").select("session_id").eq(
                    "student_id", sid
                ).gte("login_at", sent_at.isoformat()).lte(
                    "login_at", window_end.isoformat()
                ).limit(1).execute().data
                login_within_7days = len(sessions) > 0

                quizzes = supabase.table("quiz_results").select("quiz_result_id").eq(
                    "student_id", sid
                ).gte("taken_at", sent_at.isoformat()).lte(
                    "taken_at", window_end.isoformat()
                ).limit(1).execute().data
                quiz_within_7days = len(quizzes) > 0

                units = supabase.table("unit_progress").select("id").eq(
                    "student_id", sid
                ).eq("completed", True).gte(
                    "completed_at", sent_at.isoformat()
                ).lte("completed_at", window_end.isoformat()).limit(1).execute().data
                unit_within_7days = len(units) > 0

                recovery_score = round(
                    (int(login_within_7days) + int(quiz_within_7days) + int(unit_within_7days)) / 3.0, 4
                )

                supabase.table("interventions").update({
                    "login_within_7days": login_within_7days,
                    "quiz_within_7days": quiz_within_7days,
                    "unit_within_7days": unit_within_7days,
                    "recovery_score": recovery_score,
                    "recovery_checked": True,
                    "recovery_checked_at": now.isoformat(),
                }).eq("intervention_id", row["intervention_id"]).execute()
                checked += 1
            except Exception as e:
                logger.error(f"Recovery check failed for intervention {row['intervention_id']}: {e}")

        logger.info(f"Recovery check: {checked} checked, {due_later} not yet due (< 7 days since sent)")
        return checked, due_later


coordinator = CoordinatorService()
import logging

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.supabase import supabase
from services.weekly_agg import calculate_weekly_stats
from services.vark_classifier import vark_classifier_service
from services.dropout_service import dropout_service
from services.coordinator import coordinator
from services.intervention_messenger import intervention_messenger

logger = logging.getLogger(__name__)
COLOMBO_TZ = pytz.timezone("Asia/Colombo")


async def run_weekly_pipeline():
    """The full weekly chain: aggregate stats, then recompute active_vark_label
    and dropout_risk_score for every active student. Runs Sunday midnight
    Asia/Colombo — matches weekly_agg.py's own timezone.

    Each step is wrapped individually so one student's failure doesn't
    stop the rest of the run, and VARK/dropout scoring is skipped
    entirely if calculate_weekly_stats() itself fails — no point scoring
    against stats that didn't actually update this week.
    """
    logger.info("Weekly pipeline starting")

    try:
        await calculate_weekly_stats()
        logger.info("calculate_weekly_stats() complete")
    except Exception as e:
        logger.error(f"calculate_weekly_stats failed, aborting rest of pipeline: {e}")
        return

    students = supabase.table("students").select("student_id").eq("active", True).execute().data

    vark_ok = vark_fail = 0
    for s in students:
        try:
            if await vark_classifier_service.recalculate(s["student_id"]) is not None:
                vark_ok += 1
        except Exception as e:
            vark_fail += 1
            logger.error(f"VARK recalculate failed for {s['student_id']}: {e}")
    logger.info(f"VARK recalculation: {vark_ok} updated, {vark_fail} failed, "
                f"{len(students) - vark_ok - vark_fail} skipped (insufficient data)")

    dropout_ok = dropout_fail = 0
    for s in students:
        try:
            if await dropout_service.score_student(s["student_id"]) is not None:
                dropout_ok += 1
        except Exception as e:
            dropout_fail += 1
            logger.error(f"Dropout scoring failed for {s['student_id']}: {e}")
    logger.info(f"Dropout scoring: {dropout_ok} updated, {dropout_fail} failed, "
                f"{len(students) - dropout_ok - dropout_fail} skipped (no weekly_stats yet)")

    coord_triggered = coord_fail = 0
    for s in students:
        try:
            result = await coordinator.evaluate_dropout_intervention(s["student_id"])
            if result == "intervention_triggered":
                coord_triggered += 1
        except Exception as e:
            coord_fail += 1
            logger.error(f"Coordinator evaluation failed for {s['student_id']}: {e}")
    logger.info(f"Coordinator: {coord_triggered} interventions triggered, {coord_fail} failed")

    try:
        msg_sent, msg_failed = await intervention_messenger.generate_pending_messages()
        logger.info(f"Intervention messages: {msg_sent} generated, {msg_failed} failed")
    except Exception as e:
        logger.error(f"Intervention message generation failed: {e}")

    try:
        email_sent, email_failed = await intervention_messenger.send_pending_emails()
        logger.info(f"Intervention emails: {email_sent} delivered, {email_failed} failed")
    except Exception as e:
        logger.error(f"Intervention email delivery failed: {e}")

    logger.info("Weekly pipeline complete")


scheduler = AsyncIOScheduler(timezone=COLOMBO_TZ)
scheduler.add_job(
    run_weekly_pipeline,
    trigger=CronTrigger(day_of_week="sun", hour=0, minute=0, timezone=COLOMBO_TZ),
    id="weekly_pipeline",
    replace_existing=True,
)
scheduler.add_job(
    coordinator.check_recovery,
    # Daily, not weekly — an intervention's 7-day recovery window can
    # close on any day, so a Sunday-only check would miss or badly
    # delay most of these. Offset from midnight so it doesn't
    # coincide with the weekly pipeline's own Sunday run.
    trigger=CronTrigger(hour=2, minute=0, timezone=COLOMBO_TZ),
    id="recovery_check",
    replace_existing=True,
)
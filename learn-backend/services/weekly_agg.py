import pytz
from datetime import datetime, timedelta
from statistics import mean
from db.supabase import supabase
import logging


logger = logging.getLogger(__name__)
COLOMBO_TZ = pytz.timezone("Asia/Colombo")


def get_last_monday(now):
    days_back = now.weekday()
    return (now - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)


def get_last_sunday(now):
    return get_last_monday(now) + timedelta(days=6, hours=23, minutes=59, seconds=59)


def get_week_number(now):
    from config import PILOT_START_DATE
    pilot_start = datetime(PILOT_START_DATE.year, PILOT_START_DATE.month, PILOT_START_DATE.day, tzinfo=COLOMBO_TZ)
    delta = now - pilot_start
    return max(1, delta.days // 7 + 1)


def compute_engagement_level(sessions_count: int, units_completed: int) -> str:
    # Change 4: multi-level risk taxonomy
    if sessions_count >= 3 and units_completed >= 2:
        return "green"
    elif sessions_count >= 1 and units_completed >= 1:
        return "yellow"
    else:
        return "red"


async def calculate_weekly_stats():
    now_local = datetime.now(COLOMBO_TZ)
    week_start = get_last_monday(now_local)
    week_end = get_last_sunday(now_local)


    students = supabase.table("students").select("*").eq("active", True).execute().data


    for student in students:
        sid = student["student_id"]
        try:
            ws = week_start.isoformat()
            we = week_end.isoformat()


            sessions = supabase.table("sessions").select("*").eq("student_id", sid).gte(
                "login_at", ws).lte("login_at", we).execute().data


            quizzes = supabase.table("quiz_results").select("*").eq("student_id", sid).gte(
                "taken_at", ws).lte("taken_at", we).execute().data


            units_done = supabase.table("unit_progress").select("node_id").eq(
                "student_id", sid).eq("completed", True).gte(
                "completed_at", ws).lte("completed_at", we).execute().data


            attempts = supabase.table("question_attempts").select("skipped").eq(
                "student_id", sid).gte("attempted_at", ws).lte("attempted_at", we).execute().data


            # A quiz row can have a NULL score_pct; leave those out of the mean
            scores = [q["score_pct"] for q in quizzes if q.get("score_pct") is not None]
            this_score = mean(scores) if scores else 0.0

            # Compare with the most recent EARLIER week. Without .lt(), a second run in
            # the same week (scheduled + manual) found this week's own row and
            # compared the week with itself.
            current_week = get_week_number(now_local)
            prev_week = supabase.table("weekly_stats").select("avg_quiz_score").eq(
                "student_id", sid).lt("week_number", current_week).order(
                "week_number", desc=True).limit(1).execute().data
            # Older weekly_stats rows can hold a NULL avg_quiz_score: treat it like no previous week
            prev_score = (prev_week[0]["avg_quiz_score"] if prev_week else None) or 0.0


            if this_score > prev_score + 5:
                trend = "improving"
            elif this_score < prev_score - 5:
                trend = "declining"
            else:
                trend = "flat"


            total_time = sum(s.get("duration_seconds") or 0 for s in sessions) / 60
            abandoned = sum(1 for q in quizzes if q.get("abandoned"))
            skipped = sum(1 for a in attempts if a.get("skipped"))
            skip_rate = skipped / len(attempts) if attempts else 0.0
            abandon_rate = abandoned / len(quizzes) if quizzes else 0.0


            # Max login gap
            login_times = sorted([s["login_at"] for s in sessions])
            max_gap = 0
            for i in range(1, len(login_times)):
                a = datetime.fromisoformat(login_times[i-1])
                b = datetime.fromisoformat(login_times[i])
                gap = (b - a).days
                max_gap = max(max_gap, gap)


            days_since = 0
            if student.get("last_login_at"):
                try:
                    last = datetime.fromisoformat(student["last_login_at"])
                    if last.tzinfo is None:
                        last = COLOMBO_TZ.localize(last)
                    days_since = (now_local - last).days
                except:
                    pass


            sessions_count = len(sessions)
            units_completed = len(units_done)

            # Change 4: compute engagement label
            engagement_level = compute_engagement_level(sessions_count, units_completed)

            # Changes 1, 2, 3: snapshot current student state for C4 temporal analysis
            bkt_mastery_snapshot = student.get("bkt_mastery") or {}
            irt_theta_snapshot   = student.get("irt_theta") or 0.0
            current_gaps_snapshot = student.get("current_gaps") or []

            stats = {
                "student_id": sid,
                "week_number": current_week,
                "week_start": week_start.date().isoformat(),
                "week_end": week_end.date().isoformat(),
                "sessions_count": sessions_count,
                "total_time_min": round(total_time, 2),
                "login_frequency": sessions_count,
                "units_completed": units_completed,
                "quizzes_attempted": len(quizzes),
                "avg_quiz_score": round(this_score, 2),
                "score_trend": trend,
                "completion_velocity": units_completed / 7,
                "quiz_abandon_rate": round(abandon_rate, 4),
                "skip_rate": round(skip_rate, 4),
                "days_since_login": days_since,
                "max_login_gap_days": max_gap,
                # New C4 fields
                "engagement_level":        engagement_level,
                "bkt_mastery_snapshot":    bkt_mastery_snapshot,
                "irt_theta_snapshot":      irt_theta_snapshot,
                "current_gaps_snapshot":   current_gaps_snapshot,
            }


            supabase.table("weekly_stats").upsert(
                stats, on_conflict="student_id,week_number").execute()


            supabase.table("students").update({
                "days_since_last_login": days_since
            }).eq("student_id", sid).execute()


            # Rebuild vark_feature_vector
            unit_rows = supabase.table("unit_progress").select("*").eq("student_id", sid).execute().data
            feature_vector = {}
            for row in unit_rows:
                feature_vector[row["node_id"]] = {
                    "video_watch_pct": row.get("video_watch_pct"),
                    "audio_play_count": row.get("audio_play_count"),
                    "scroll_depth_pct": row.get("scroll_depth_pct"),
                    "revisit_count": row.get("revisit_count"),
                    "total_time_sec": row.get("total_time_sec")
                }
            supabase.table("students").update({
                "vark_feature_vector": feature_vector
            }).eq("student_id", sid).execute()


        except Exception as e:
            logger.error(f"Weekly agg failed for {sid}: {e}")
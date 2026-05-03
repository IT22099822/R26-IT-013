from db.supabase import supabase
import logging

logger = logging.getLogger(__name__)

class BKTService:
    # Tracks per-skill mastery (0-1) using Bayesian Knowledge Tracing
    DEFAULT_MASTERY_THRESHOLD = 0.95  # unlock bar, from our spec
    DEFAULT_PARAMS = {"p_l0": 0.2179, "p_t": 0.2159, "p_g": 0.1936, "p_s": 0.0907}  # from parameter recovery, not real-data tuned

    async def update(self, student_id: str, node_id: str, correct: int):
        # Runs on every answer: Bayesian mastery update, then refreshes gaps + checks unlock
        student = supabase.table("students").select(
            "bkt_mastery,current_gaps,nodes_mastered"
        ).eq("student_id", student_id).execute().data[0]

        # Per-node threshold if set, else the 0.95 default above
        node_row = supabase.table("content_nodes").select(
            "mastery_threshold"
        ).eq("node_id", node_id).execute().data
        threshold = (
            node_row[0]["mastery_threshold"]
            if node_row and node_row[0].get("mastery_threshold") is not None
            else self.DEFAULT_MASTERY_THRESHOLD
        )

        p_ln = student["bkt_mastery"].get(node_id, self.DEFAULT_PARAMS["p_l0"])
        params = self.DEFAULT_PARAMS

        # Bayes' rule: revise belief given this one answer, accounting for guess/slip
        if correct:
            numerator = p_ln * (1 - params["p_s"])
            denominator = (p_ln * (1 - params["p_s"]) + (1 - p_ln) * params["p_g"])
        else:
            numerator = p_ln * params["p_s"]
            denominator = (p_ln * params["p_s"] + (1 - p_ln) * (1 - params["p_g"]))

        p_ln_given = numerator / denominator
        p_ln1 = p_ln_given + (1 - p_ln_given) * params["p_t"]  # + small boost just for practicing
        p_ln1 = round(p_ln1, 4)

        mastery_map = student["bkt_mastery"]
        mastery_map[node_id] = p_ln1
        update_data = {"bkt_mastery": mastery_map}

        # Re-checks ALL gaps, not just this node's, so fixed ones actually clear
        existing_gaps = student.get("current_gaps") or []
        still_valid_old_gaps = [g for g in existing_gaps if mastery_map.get(g, 0.2) < 0.5]
        new_gaps_for_this_node = await self.find_upstream_gaps(node_id, student_id)
        merged_gaps = list(dict.fromkeys(still_valid_old_gaps + new_gaps_for_this_node))
        update_data["current_gaps"] = merged_gaps

        # Unlocks the node the first time mastery crosses the threshold
        nodes_mastered = student.get("nodes_mastered") or []
        newly_mastered = False
        if p_ln1 >= threshold and node_id not in nodes_mastered:
            nodes_mastered = nodes_mastered + [node_id]
            update_data["nodes_mastered"] = nodes_mastered
            newly_mastered = True

        supabase.table("students").update(update_data).eq("student_id", student_id).execute()
        return {"mastery": p_ln1, "newly_mastered": newly_mastered, "threshold_used": threshold}

    async def find_upstream_gaps(self, node_id: str, student_id: str):
        # Flags any prerequisite still below 50% mastery
        node = supabase.table("content_nodes").select("prerequisites").eq("node_id", node_id).execute()
        student = supabase.table("students").select("bkt_mastery").eq("student_id", student_id).execute().data[0]
        gaps = []
        if node.data and node.data[0].get("prerequisites"):
            for prereq in node.data[0]["prerequisites"]:
                mastery = student["bkt_mastery"].get(prereq, 0.2)
                if mastery < 0.5:
                    gaps.append(prereq)
        return gaps

bkt_service = BKTService()
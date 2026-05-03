"""Next-answer prediction accuracy for Knowledge Gap Predictor (BKT) and Difficulty
Optimization (IRT), evaluated on learners the fitted models never saw.

Every prediction uses ONLY the answers a learner gave BEFORE the question being predicted.
BKT uses the deployed parameters from services/bkt.py; the live update rule is replayed
answer by answer. IRT theta is the same 1PL maximum-likelihood fit as services/irt.py,
recomputed online on a grid. The mastery-conditioned IRT model (theta - b plus BKT mastery)
is fitted on 80% of learners and scored on the remaining 20%.

Usage (from the backend repo root):
    python scripts/eval_next_answer_accuracy.py path/to/question_attempts.csv
The CSV is the synthetic cohort's question_attempts export (same columns as the table).
Results are printed and written to eval_next_answer_accuracy.json next to the CSV."""
import json, os, sys
import numpy as np, pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, accuracy_score, log_loss, balanced_accuracy_score, f1_score

CSV = sys.argv[1] if len(sys.argv) > 1 else "question_attempts.csv"
P = dict(p_l0=0.2179, p_t=0.2159, p_g=0.1936, p_s=0.0907)   # services/bkt.py DEFAULT_PARAMS
GRID = np.linspace(-4, 4, 321)                                # services/irt.py fits theta in [-4, 4]

d = pd.read_csv(CSV)
d["row"] = np.arange(len(d))
d = d[~d.skipped.astype(bool)].sort_values(["student_id", "attempted_at", "row"], kind="mergesort").reset_index(drop=True)
d["y"] = d.correct.astype(str).str.lower().isin(["true", "1"]).astype(int)

bkt_p, mastery_pre, theta_pre = [], [], []
for _, g in d.groupby("student_id", sort=False):
    m, ll, seen = {}, np.zeros_like(GRID), 0
    for node, y, b in zip(g.node_id.values, g.y.values, g.difficulty_tag.values):
        pL = m.get(node, P["p_l0"])
        mastery_pre.append(pL)
        bkt_p.append(pL * (1 - P["p_s"]) + (1 - pL) * P["p_g"])      # BKT P(correct) before the answer
        theta_pre.append(GRID[np.argmax(ll)] if seen else 0.0)       # live theta starts at 0
        if y: num = pL * (1 - P["p_s"]); den = num + (1 - pL) * P["p_g"]
        else: num = pL * P["p_s"];       den = num + (1 - pL) * (1 - P["p_g"])
        post = num / den; m[node] = post + (1 - post) * P["p_t"]     # same update as services/bkt.py
        p = 1 / (1 + np.exp(-(GRID - b))); ll += np.log(p + 1e-10) if y else np.log(1 - p + 1e-10); seen += 1
d["bkt_p"], d["mastery_pre"], d["theta_pre"] = bkt_p, mastery_pre, theta_pre
d["theta_minus_b"] = d.theta_pre - d.difficulty_tag
d["irt_p"] = 1 / (1 + np.exp(-d.theta_minus_b))
clip = np.clip(d.mastery_pre, 1e-4, 1 - 1e-4); d["logit_mastery"] = np.log(clip / (1 - clip))

tr, te = next(GroupShuffleSplit(1, test_size=0.2, random_state=42).split(d, d.y, d.student_id))
A, B = d.iloc[tr], d.iloc[te]
def rep(name, y, p):
    pr = (p >= 0.5).astype(int)
    return dict(model=name, accuracy=round(accuracy_score(y, pr), 4), balanced_accuracy=round(balanced_accuracy_score(y, pr), 4),
                auc=round(roc_auc_score(y, p), 4), macro_f1=round(f1_score(y, pr, average='macro'), 4), log_loss=round(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)), 4))
F = ["theta_minus_b", "logit_mastery"]
mc = LogisticRegression(max_iter=1000).fit(A[F], A.y)
out = dict(data=os.path.basename(CSV), n_test_learners=int(B.student_id.nunique()), n_test_answers=int(len(B)),
           results=[rep('Majority baseline (always "correct")', B.y, np.full(len(B), A.y.mean())),
                    rep("BKT, deployed parameters", B.y, B.bkt_p.values),
                    rep("IRT 1PL, deployed (theta - b)", B.y, B.irt_p.values),
                    rep("Mastery-conditioned IRT (theta - b + BKT mastery)", B.y, mc.predict_proba(B[F])[:, 1])],
           mastery_conditioned_coefficients=dict(zip(F, np.round(mc.coef_[0], 4).tolist()), intercept=round(float(mc.intercept_[0]), 4)))
print(f"Held-out: {out['n_test_learners']} learners, {out['n_test_answers']} answers")
for r in out["results"]:
    print(f"  {r['model']:52s} accuracy {r['accuracy']:.1%}  AUC {r['auc']:.3f}  macro-F1 {r['macro_f1']:.3f}  balanced acc {r['balanced_accuracy']:.1%}")
json.dump(out, open(os.environ.get("EVIDENCE_OUT", "eval_next_answer_accuracy.json"), "w"), indent=1)

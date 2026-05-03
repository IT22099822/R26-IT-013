#!/usr/bin/env python3
"""Recommends a per-node mastery threshold via empirical (contrasting
groups) standard-setting: fits a logistic relationship between a
student's BKT mastery at post-test time and whether they actually got
a good post-test score, per node, then finds the mastery level where
P(good outcome) crosses a target confidence bar.

This does NOT replace the flat 0.95 default automatically — it
produces a recommendation per node. Applying it means setting
content_nodes.mastery_threshold to the recommended value yourself.

Usage:
    python threshold_recommendation.py
    (expects mastery_outcomes.csv: node_id, mastery_at_post_test, score_pct)

Getting mastery_outcomes.csv from real production data:
    SELECT entity_id AS node_id,
           (metadata->>'mastery_at_post_test')::float AS mastery_at_post_test,
           (metadata->>'score_pct')::float AS score_pct
    FROM interaction_log
    WHERE event_type = 'post_test_complete';
"""

import csv
import math
from collections import defaultdict

from scipy.optimize import minimize

PASS_SCORE = 70.0          # what counts as a "good" post-test outcome
TARGET_CONFIDENCE = 0.80   # recommend the mastery level giving this P(pass)

# A power analysis (synthetic, moderate-correlation assumption drawn
# from general educational measurement literature — NOT a claim about
# any specific real node) found that at n=15 responses, recovered
# thresholds vary wildly (std dev ~0.20, individual estimates ranging
# from ~0 to ~1 — essentially noise). Stability (std dev < 0.03) only
# sets in around n=150-250. This number moves if your real data turns
# out noisier or cleaner than that assumption — treat it as a floor,
# not a guarantee.
MIN_RESPONSES_PER_NODE = 150


def fit_logistic(mastery_vals, passed_vals):
    """Fits P(pass) = 1 / (1 + exp(-(a*mastery + b))) via MLE."""
    def neg_log_likelihood(params):
        a, b = params
        ll = 0.0
        for m, y in zip(mastery_vals, passed_vals):
            z = a * m + b
            if z > 700:
                p = 1 - 1e-12
            elif z < -700:
                p = 1e-12
            else:
                p = 1 / (1 + math.exp(-z))
            p = min(max(p, 1e-12), 1 - 1e-12)
            ll += math.log(p) if y else math.log(1 - p)
        return -ll

    result = minimize(neg_log_likelihood, [1.0, 0.0], method='Nelder-Mead')
    return result.x[0], result.x[1]


def recommend_threshold(a, b, target_confidence):
    if a == 0:
        return None
    logit_target = math.log(target_confidence / (1 - target_confidence))
    m = (logit_target - b) / a
    return round(min(max(m, 0.0), 1.0), 4)


def main():
    with open('mastery_outcomes.csv') as f:
        rows = list(csv.DictReader(f))

    by_node = defaultdict(list)
    for r in rows:
        by_node[r['node_id']].append((
            float(r['mastery_at_post_test']),
            float(r['score_pct']) >= PASS_SCORE
        ))

    results = []
    for node_id, data in by_node.items():
        n = len(data)
        if n < MIN_RESPONSES_PER_NODE:
            results.append({'node_id': node_id, 'n': n, 'recommended_threshold': '',
                             'slope': '', 'intercept': '',
                             'note': f'insufficient data (<{MIN_RESPONSES_PER_NODE})'})
            continue

        mastery_vals = [d[0] for d in data]
        passed_vals = [1 if d[1] else 0 for d in data]
        if len(set(passed_vals)) < 2:
            results.append({'node_id': node_id, 'n': n, 'recommended_threshold': '',
                             'slope': '', 'intercept': '',
                             'note': 'no variance in outcomes (all pass or all fail)'})
            continue

        a, b = fit_logistic(mastery_vals, passed_vals)
        threshold = recommend_threshold(a, b, TARGET_CONFIDENCE)
        results.append({'node_id': node_id, 'n': n,
                         'recommended_threshold': threshold,
                         'slope': round(a, 4), 'intercept': round(b, 4), 'note': ''})

    with open('recommended_thresholds.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['node_id', 'n', 'recommended_threshold',
                                           'slope', 'intercept', 'note'])
        w.writeheader()
        w.writerows(results)

    print(f"Analyzed {len(by_node)} nodes")
    for r in results:
        print(r)
    print("\nSaved recommended_thresholds.csv")


if __name__ == '__main__':
    main()
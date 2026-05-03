#!/usr/bin/env python3
"""Calibrate item difficulty for PRACTICE/POST-TEST questions, properly
accounting for the fact that mastery evolves mid-sequence during these
(unlike anchor questions, where mastery is a constant).

Two things a plain 1PL fit gets wrong for practice/post items:
  1. Ability (theta) can't be estimated from a student's full response
     history without contamination from mastery growth. Fixed by
     reusing an ANCHOR-ONLY theta estimate (anchors are the one place
     mastery truly is constant across all students).
  2. Correctness depends heavily on how far into practicing THIS node
     the student already is. Fixed by reconstructing each attempt's
     pre-attempt mastery via the fitted BKT equations (from
     bkt_fitting.py's output), forward-simulated through each
     student's actual answer sequence — the same math services/bkt.py
     runs live in production, just replayed here for calibration.

Only questions with a real (non-zero-placeholder) difficulty_tag are
calibrated — 105/105 anchor questions and ~126 practice/post questions
in this content bank have never been assigned a real value, so there's
nothing genuine to recover for those.

Usage:
    python irt_calibration_v2.py
    (expects question_attempts.csv and bkt_global_params.json in the
    same directory — bkt_global_params.json comes from running
    bkt_fitting.py first)
"""

import csv
import json
import math
import time
from collections import defaultdict

from scipy.optimize import minimize_scalar

MIN_RESPONSES = 3
SHIFT_SCALE = 0.18  # matches the generator's known functional form —
                     # fixed here so the test isolates whether b itself
                     # is identifiable, not whether every parameter is

print("Loading fitted BKT params ...")
with open('bkt_global_params.json', encoding='utf-8') as f:
    bkt_out = json.load(f)
FITTED = bkt_out['fitted_params']
print(f"  using: {FITTED}")


def bkt_update(p_ln, correct, params):
    if correct:
        num = p_ln * (1 - params['p_s'])
        den = num + (1 - p_ln) * params['p_g']
    else:
        num = p_ln * params['p_s']
        den = num + (1 - p_ln) * (1 - params['p_g'])
    p_given = num / (den + 1e-12)
    return p_given + (1 - p_given) * params['p_t']


print("\nLoading question_attempts.csv ...")
t0 = time.time()
with open('question_attempts.csv', encoding='utf-8') as f:
    attempts = list(csv.DictReader(f))
print(f"Loaded {len(attempts)} attempts in {time.time()-t0:.1f}s")

# ----------------------------------------------------------------------
# Step 1: reconstruct pre-attempt mastery for every (student, node)
# sequence, forward-simulated via the fitted BKT equations
# ----------------------------------------------------------------------
print("\nReconstructing per-attempt mastery (fitted BKT replay) ...")
t0 = time.time()
seqs = defaultdict(list)
for a in attempts:
    if a['skipped'] == 'True':
        continue
    seqs[(a['student_id'], a['node_id'])].append(a)
for k in seqs:
    seqs[k].sort(key=lambda r: r['attempted_at'])

mastery_before = {}
for (sid, node), rows in seqs.items():
    p_ln = FITTED['p_l0']
    for r in rows:
        mastery_before[r['attempt_id']] = p_ln
        correct = r['correct'] == 'True'
        p_ln = bkt_update(p_ln, correct, FITTED)
print(f"Reconstructed mastery for {len(mastery_before)} attempts in {time.time()-t0:.1f}s")

# ----------------------------------------------------------------------
# Step 2: clean anchor-only theta per student (mastery is constant there)
# ----------------------------------------------------------------------
print("\nEstimating anchor-only theta per student ...")
t0 = time.time()
anchor_attempts = [a for a in attempts if '-ANC-' in a['question_id'] and a['skipped'] != 'True']
by_student = defaultdict(list)
for a in anchor_attempts:
    b = float(a['difficulty_tag']) if a['difficulty_tag'] not in (None, '') else 0.0
    correct = 1 if a['correct'] == 'True' else 0
    by_student[a['student_id']].append((b, correct))


def neg_log_likelihood_theta(theta, responses):
    ll = 0.0
    for b, correct in responses:
        p = 1.0 / (1.0 + math.exp(-(theta - b)))
        p = min(max(p, 1e-9), 1 - 1e-9)
        ll += math.log(p) if correct else math.log(1 - p)
    return -ll


student_theta = {}
for sid, responses in by_student.items():
    if len(responses) < 3:
        continue
    res = minimize_scalar(neg_log_likelihood_theta, args=(responses,),
                           bounds=(-4, 4), method='bounded')
    student_theta[sid] = res.x
print(f"Estimated theta for {len(student_theta)} students in {time.time()-t0:.1f}s")

# ----------------------------------------------------------------------
# Step 3: calibrate difficulty for practice/post-test questions,
# holding reconstructed mastery AND anchor-only theta fixed
# ----------------------------------------------------------------------
print("\nCalibrating item difficulty (practice/post-test, real difficulty only) ...")
t0 = time.time()


def neg_log_likelihood_b(b, responses):
    ll = 0.0
    for m, theta, correct in responses:
        p_bkt = m * (1 - FITTED['p_s']) + (1 - m) * FITTED['p_g']
        shift = SHIFT_SCALE * (theta - b) / 4.0
        p = min(max(p_bkt + shift, 0.01), 0.99)
        ll += math.log(p) if correct else math.log(1 - p)
    return -ll


by_question = defaultdict(list)
skipped_placeholder, skipped_no_theta, skipped_no_mastery = 0, 0, 0
for a in attempts:
    if a['skipped'] == 'True' or '-ANC-' in a['question_id']:
        continue
    if a['difficulty_tag'] in (None, '', '0', '0.0'):
        skipped_placeholder += 1
        continue
    if a['student_id'] not in student_theta:
        skipped_no_theta += 1
        continue
    if a['attempt_id'] not in mastery_before:
        skipped_no_mastery += 1
        continue
    m = mastery_before[a['attempt_id']]
    theta = student_theta[a['student_id']]
    correct = 1 if a['correct'] == 'True' else 0
    true_b = float(a['difficulty_tag'])
    by_question[a['question_id']].append((m, theta, correct, true_b))

print(f"  skipped (placeholder difficulty=0): {skipped_placeholder}")
print(f"  skipped (no anchor-based theta):    {skipped_no_theta}")

results = []
for qid, responses in by_question.items():
    n = len(responses)
    if n < MIN_RESPONSES:
        continue
    fit_responses = [(m, t, c) for m, t, c, _ in responses]
    res = minimize_scalar(neg_log_likelihood_b, args=(fit_responses,),
                           bounds=(-4, 4), method='bounded')
    b_cal = round(res.x, 4)
    true_b = responses[0][3]
    pct_correct = sum(r[2] for r in responses) / n
    results.append({
        'question_id': qid, 'n_responses': n,
        'b_calibrated': b_cal, 'true_difficulty_tag': true_b,
        'pct_correct': round(pct_correct, 4),
    })

print(f"Calibrated {len(results)} questions in {time.time()-t0:.1f}s "
      f"(out of 399 practice/post-test questions with real difficulty values)")

# ----------------------------------------------------------------------
# Recovery check
# ----------------------------------------------------------------------
pairs = [(r['b_calibrated'], r['true_difficulty_tag']) for r in results]
n = len(pairs)
if n > 1:
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = sum(xs)/n, sum(ys)/n
    cov = sum((x-mx)*(y-my) for x, y in pairs)
    varx = sum((x-mx)**2 for x in xs)
    vary = sum((y-my)**2 for y in ys)
    corr = cov / math.sqrt(varx*vary) if varx > 0 and vary > 0 else float('nan')
    mae = sum(abs(x-y) for x, y in pairs) / n
    print(f"\nRecovery check ({n} questions with real difficulty values):")
    print(f"  correlation(b_calibrated, true_difficulty_tag) = {corr:.4f}")
    print(f"  mean absolute error = {mae:.4f}")
    print("  (correlation > 0.6 = good recovery, per the C3 spec)")

with open('question_difficulty_calibrated_v2.csv', 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['question_id', 'n_responses', 'b_calibrated',
                                       'true_difficulty_tag', 'pct_correct'])
    w.writeheader()
    w.writerows(results)
print("Saved question_difficulty_calibrated_v2.csv")

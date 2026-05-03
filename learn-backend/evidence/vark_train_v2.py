#!/usr/bin/env python3
"""C1 v2: build behaviour features per student, OPTIMISE and compare
classifiers against the questionnaire label, and evaluate both overall
held-out accuracy and accuracy when the model is confident enough to act.

What changed from v1 (vark_train.py):
  1. Feature engineering - 9 new per-lesson distribution features.
     v1 averaged each signal across all lessons, which throws away HOW
     OFTEN a learner behaved visually or aurally. A learner who watches
     the whole video in half their lessons and none in the other half
     has the same average as one who watches half of every video.
     The new features keep that information (share of lessons with
     heavy video, with 2+ audio plays, etc.).
  2. Hyperparameter optimisation - randomised search (40 candidates per
     model, 5-fold stratified cross-validation on the TRAINING split
     only) for logistic regression, random forest and gradient boosting.
     The best model is chosen by mean CV accuracy; the held-out test set
     is used once, at the end, for reporting only.
  3. Robust estimate - a single 80/20 split leaves only 123 test
     learners (95% CI about +/-8 points), so the script also runs
     10 x 5-fold repeated stratified cross-validation over ALL usable
     learners, re-tuning the chosen model family inside every fold
     (nested), and reports the mean. This is the headline estimate.
  4. Selective (confidence-gated) evaluation - C1's live policy only
     overrides the questionnaire when the model's top probability is
     above 0.6 (HIGH_CONFIDENCE_THRESHOLD in vark_classifier.py). This
     script therefore also reports accuracy and coverage at that
     threshold (plus a few others) on the held-out set. The 0.6 value is
     the existing deployed policy, fixed in advance - it is NOT tuned
     here on the test set.

Usage:
    python vark_train_v2.py
    (expects students.csv and question_attempts.csv in the same directory)
Outputs: vark_model.pkl, vark_training_summary_v2.json
"""

import csv
import json
import math
import pickle
import time
from collections import defaultdict

import numpy as np
from scipy.stats import loguniform, randint, uniform
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import RandomizedSearchCV, RepeatedStratifiedKFold, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

MIN_NODES_VISITED = 3
RANDOM_STATE = 42
N_SEARCH_ITER = 40
HIGH_CONFIDENCE_THRESHOLD = 0.6   # same value as the live policy in vark_classifier.py
REPORT_THRESHOLDS = [0.5, 0.6, 0.7, 0.8]

FEATURE_NAMES = [
    # --- v1 features (unchanged) ---
    'avg_video_watch_pct', 'max_video_watch_pct', 'video_completion_rate',
    'avg_audio_play_count', 'audio_engagement_rate',
    'avg_scroll_depth_pct', 'avg_revisit_count', 'avg_total_time_sec',
    'n_nodes_visited',
    'acc_V', 'acc_A', 'acc_R', 'acc_K',
    # --- v2 per-lesson distribution features ---
    'share_video_heavy',      # lessons with > 70% of the video watched
    'share_video_light',      # lessons with < 50% of the video watched
    'median_video_watch_pct',
    'std_video_watch_pct',
    'share_audio_none',       # lessons with no audio play
    'share_audio_once',       # lessons with exactly one audio play
    'share_audio_2plus',      # lessons with two or more audio plays
    'share_audio_3plus',      # lessons with three or more audio plays
    'share_low_media',        # lessons with < 50% video AND at most one audio play
]


def build_row(fv, vark_acc):
    """Shared feature builder - vark_classifier.py must use the identical logic."""
    videos = np.array([v.get('video_watch_pct') or 0 for v in fv.values()], dtype=float)
    audios = np.array([v.get('audio_play_count') or 0 for v in fv.values()], dtype=float)
    scrolls = [v.get('scroll_depth_pct') or 0 for v in fv.values()]
    revisits = [v.get('revisit_count') or 0 for v in fv.values()]
    times = [v.get('total_time_sec') or 0 for v in fv.values()]
    n = len(fv)
    return [
        float(videos.mean()), float(videos.max()), float((videos > 0.8).mean()),
        float(audios.mean()), float((audios > 0).mean()),
        sum(scrolls) / n, sum(revisits) / n, sum(times) / n,
        n,
        vark_acc['V'], vark_acc['A'], vark_acc['R'], vark_acc['K'],
        float((videos > 0.7).mean()), float((videos < 0.5).mean()),
        float(np.median(videos)), float(videos.std()),
        float((audios == 0).mean()), float((audios == 1).mean()),
        float((audios >= 2).mean()), float((audios >= 3).mean()),
        float(((videos < 0.5) & (audios <= 1)).mean()),
    ]


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(c - h, 4), round(c + h, 4))


print("Loading students.csv ...")
t0 = time.time()
with open('students.csv', encoding='utf-8') as f:
    students = list(csv.DictReader(f))
print(f"Loaded {len(students)} students in {time.time()-t0:.1f}s")

print("Loading question_attempts.csv ...")
t0 = time.time()
with open('question_attempts.csv', encoding='utf-8') as f:
    attempts = list(csv.DictReader(f))
print(f"Loaded {len(attempts)} attempts in {time.time()-t0:.1f}s")

by_student_vark = defaultdict(lambda: defaultdict(lambda: [0, 0]))
for a in attempts:
    if a['skipped'] == 'True' or not a.get('vark_type_served'):
        continue
    sid, vt = a['student_id'], a['vark_type_served']
    by_student_vark[sid][vt][1] += 1
    if a['correct'] == 'True':
        by_student_vark[sid][vt][0] += 1

print("\nBuilding feature vectors ...")
X, y = [], []
excluded_thin = 0
for s in students:
    fv_raw, label = s.get('vark_feature_vector'), s.get('vark_questionnaire_label')
    if not fv_raw or not label:
        continue
    try:
        fv = json.loads(fv_raw)
    except (json.JSONDecodeError, TypeError):
        continue
    if len(fv) < MIN_NODES_VISITED:
        excluded_thin += 1
        continue
    acc = {}
    for vt in ['V', 'A', 'R', 'K']:
        c, t = by_student_vark[s['student_id']].get(vt, [0, 0])
        acc[vt] = c / t if t > 0 else 0.5
    X.append(build_row(fv, acc))
    y.append(label)
X, y = np.array(X), np.array(y)
print(f"Built {len(X)} feature vectors ({excluded_thin} excluded, <{MIN_NODES_VISITED} nodes)")
print(f"Features: {len(FEATURE_NAMES)}  Label distribution: {dict(zip(*np.unique(y, return_counts=True)))}")

# Same split as v1 (same random_state, stratified) so results are directly comparable
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_STATE, stratify=y)
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

searches = {
    'logistic_regression': (
        Pipeline([('scaler', StandardScaler()), ('clf', LogisticRegression(max_iter=5000, random_state=RANDOM_STATE))]),
        {'clf__C': loguniform(1e-3, 1e2)}),
    'random_forest': (
        RandomForestClassifier(random_state=RANDOM_STATE),
        {'n_estimators': randint(100, 600), 'max_depth': randint(2, 20),
         'min_samples_leaf': randint(1, 20), 'max_features': uniform(0.2, 0.8)}),
    'gradient_boosting': (
        HistGradientBoostingClassifier(random_state=RANDOM_STATE),
        {'learning_rate': loguniform(0.01, 0.3), 'max_depth': randint(2, 8), 'max_leaf_nodes': randint(8, 64),
         'l2_regularization': loguniform(1e-4, 10), 'min_samples_leaf': randint(5, 60)}),
}

print(f"\nOptimising classifiers (randomised search, {N_SEARCH_ITER} candidates x 5-fold CV each) ...")
results, best_name, best_search = {}, None, None
for name, (est, params) in searches.items():
    t0 = time.time()
    rs = RandomizedSearchCV(est, params, n_iter=N_SEARCH_ITER, cv=cv, scoring='accuracy',
                            random_state=RANDOM_STATE, n_jobs=-1).fit(X_train, y_train)
    test_acc = rs.score(X_test, y_test)
    results[name] = {'cv_accuracy': round(rs.best_score_, 4),
                     'cv_std': round(float(rs.cv_results_['std_test_score'][rs.best_index_]), 4),
                     'held_out_test_accuracy': round(test_acc, 4),
                     'best_params': {k: (round(v, 6) if isinstance(v, float) else v) for k, v in rs.best_params_.items()}}
    print(f"  {name:20s}  CV acc={rs.best_score_:.4f} (+/-{results[name]['cv_std']:.4f})  "
          f"held-out test acc={test_acc:.4f}  ({time.time()-t0:.0f}s)")
    if best_search is None or rs.best_score_ > best_search.best_score_:
        best_name, best_search = name, rs

model = best_search.best_estimator_
print(f"\nBest model (by CV): {best_name}  params={results[best_name]['best_params']}")

proba = model.predict_proba(X_test)
classes = model.classes_
y_pred = classes[proba.argmax(1)]
conf = proba.max(1)
overall = float((y_pred == y_test).mean())
print(f"\nHeld-out test accuracy (all {len(y_test)} learners): {overall:.4f}  95% CI {wilson(int((y_pred == y_test).sum()), len(y_test))}")
print("\nClassification report:")
print(classification_report(y_test, y_pred))
print("Confusion matrix (rows=true, cols=predicted):")
cm = confusion_matrix(y_test, y_pred, labels=list(classes))
print("       " + "  ".join(f"{l:>5s}" for l in classes))
for lbl, row in zip(classes, cm):
    print(f"  {lbl:>3s}  " + "  ".join(f"{v:5d}" for v in row))

print("\nConfident-prediction accuracy (C1 only acts when confidence > threshold):")
selective = []
for th in REPORT_THRESHOLDS:
    m = conf > th
    k, n = int((y_pred[m] == y_test[m]).sum()), int(m.sum())
    row = {'threshold': th, 'coverage': round(n / len(y_test), 4), 'n_learners': n,
           'accuracy': round(k / n, 4) if n else None, 'ci95': wilson(k, n)}
    selective.append(row)
    flag = '   <- deployed policy threshold' if th == HIGH_CONFIDENCE_THRESHOLD else ''
    print(f"  confidence > {th:.1f}: coverage {row['coverage']:.3f} ({n}/{len(y_test)})  "
          f"accuracy {row['accuracy']}  95% CI {row['ci95']}{flag}")

# ----------------------------------------------------------------------
# Robust estimate: 10 x 5-fold repeated stratified CV over all learners,
# with the chosen model family re-tuned inside every training fold
# ----------------------------------------------------------------------
print("\nRobust estimate: 10 x 5-fold repeated CV over all learners (nested tuning) ...")
t0 = time.time()
est, params = searches[best_name]
rcv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=RANDOM_STATE)
fold_acc, sel_counts = [], {th: [0, 0] for th in REPORT_THRESHOLDS}
for tr, te in rcv.split(X, y):
    inner = RandomizedSearchCV(est, params, n_iter=15, cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE),
                               scoring='accuracy', random_state=RANDOM_STATE, n_jobs=-1).fit(X[tr], y[tr])
    P = inner.predict_proba(X[te])
    pr, cf = inner.classes_[P.argmax(1)], P.max(1)
    fold_acc.append(float((pr == y[te]).mean()))
    for th in REPORT_THRESHOLDS:
        m = cf > th
        sel_counts[th][0] += int((pr[m] == y[te][m]).sum())
        sel_counts[th][1] += int(m.sum())
n_pred = len(y) * 10
robust = {'overall_accuracy': round(float(np.mean(fold_acc)), 4), 'fold_sd': round(float(np.std(fold_acc)), 4),
          'n_predictions': n_pred, 'selective': []}
print(f"  overall accuracy {robust['overall_accuracy']:.4f} (SD across 50 folds {robust['fold_sd']:.4f})  ({time.time()-t0:.0f}s)")
for th in REPORT_THRESHOLDS:
    k, n = sel_counts[th]
    robust['selective'].append({'threshold': th, 'coverage': round(n / n_pred, 4), 'accuracy': round(k / n, 4) if n else None})
    flag = '   <- deployed policy threshold' if th == HIGH_CONFIDENCE_THRESHOLD else ''
    print(f"  confidence > {th:.1f}: coverage {n / n_pred:.3f}  accuracy {k / n:.4f}{flag}")

with open('vark_model.pkl', 'wb') as f:
    pickle.dump({'model': model, 'scaler': None, 'model_name': best_name, 'feature_names': FEATURE_NAMES,
                 'feature_version': 2, 'high_confidence_threshold': HIGH_CONFIDENCE_THRESHOLD}, f)
summary = {
    'version': 2, 'model_name': best_name, 'n_features': len(FEATURE_NAMES),
    'n_students_used': int(len(X)), 'n_students_excluded_thin_data': excluded_thin,
    'n_test': int(len(y_test)), 'label_distribution': {k: int(v) for k, v in zip(*np.unique(y, return_counts=True))},
    'held_out_test_accuracy': round(overall, 4), 'cv_accuracy': results[best_name]['cv_accuracy'],
    'model_comparison': results, 'selective_accuracy': selective,
    'repeated_cv_10x5': robust,
}
with open('vark_training_summary_v2.json', 'w') as f:
    json.dump(summary, f, indent=2)
print("\nSaved vark_model.pkl and vark_training_summary_v2.json")

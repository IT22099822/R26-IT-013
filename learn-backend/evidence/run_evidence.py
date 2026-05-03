"""LEARN R26-IT-013: re-runs every model evaluation behind the numbers on our slides.

Usage (from the learn-backend folder):
    python evidence/run_evidence.py "C:\\path\\to\\dummy_data_output_734"

The data folder is the 734-learner synthetic cohort (students.csv, question_attempts.csv,
bkt_global_params.json). Nothing in it is changed: scripts run in a temporary copy.
Sections:
  1  Automated tests               (tests/run_all.py)
  2  Learning Style Detection      10 x 5 repeated cross-validation, baseline vs optimised
  3  Knowledge Gap + Difficulty    next-answer accuracy on 124 held-out learners
  4  Difficulty Optimization       difficulty recovery against the known true difficulty
  5  Dropout Risk Prediction       needs its own training script and data (see message)
"""
import contextlib, io, os, shutil, subprocess, sys, tempfile, time, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None

def banner(n, title):
    print("\n" + "=" * 78 + f"\n {n}  {title}\n" + "=" * 78, flush=True)

def need(*names):
    missing = [f for f in names if not os.path.exists(os.path.join(DATA, f))]
    if missing:
        print(f"  SKIPPED: {', '.join(missing)} not found in {DATA}"); return False
    return True

def workdir(*names):
    d = tempfile.mkdtemp(prefix="learn_evidence_")
    for f in names: shutil.copy(os.path.join(DATA, f), d)
    return d

if not DATA or not os.path.isdir(DATA):
    print(__doc__); sys.exit(1)
start = time.time()
print(f"LEARN evidence run  |  data: {DATA}")

# 1 -------------------------------------------------------------------------
banner(1, "Automated tests")
subprocess.run([sys.executable, os.path.join(REPO, "tests", "run_all.py")], cwd=REPO)

# 2 -------------------------------------------------------------------------
banner(2, "Learning Style Detection: 10 x 5 repeated stratified cross-validation")
if need("students.csv", "question_attempts.csv"):
    import numpy as np
    from sklearn.model_selection import RepeatedStratifiedKFold, GridSearchCV, StratifiedKFold
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import f1_score, confusion_matrix
    wd = workdir("students.csv", "question_attempts.csv"); cwd = os.getcwd(); os.chdir(wd)
    src = open(os.path.join(HERE, "vark_train_v2.py"), encoding="utf-8").read().split("# Same split as v1")[0]
    g = {}
    with contextlib.redirect_stdout(io.StringIO()): exec(src, g)
    os.chdir(cwd)
    X, y = g["X"], g["y"]
    labels = sorted(set(y))
    maj = max(labels, key=lambda c: (y == c).mean())
    print(f"  learners with enough behaviour: {len(y)}   classes: {', '.join(labels)}")
    print(f"  majority-class baseline (always '{maj}'): {(y == maj).mean():.1%}")
    from scipy.stats import loguniform
    from sklearn.model_selection import RandomizedSearchCV
    RS = g["RANDOM_STATE"]   # same seed and procedure as vark_train_v2.py's robust estimate
    rcv = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=RS)
    TH = [0.5, 0.6, 0.7, 0.8]
    for name, cols, tune in [("Baseline: 13 features, default logistic regression", list(range(13)), False),
                             ("Optimised: 22 features, logistic regression re-tuned inside every fold (deployed)", list(range(22)), True)]:
        accs, f1s, sel = [], [], {t: [0, 0] for t in TH}
        cm = np.zeros((len(labels), len(labels)), int)
        for tr, te in rcv.split(X, y):
            pipe = Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression(max_iter=5000, random_state=RS))])
            if tune:
                pipe = RandomizedSearchCV(pipe, {"clf__C": loguniform(1e-3, 1e2)}, n_iter=15,
                                          cv=StratifiedKFold(5, shuffle=True, random_state=RS),
                                          scoring="accuracy", random_state=RS, n_jobs=-1)
            pipe.fit(X[tr][:, cols], y[tr]); P = pipe.predict_proba(X[te][:, cols]); cl = pipe.classes_
            pr, cf = cl[P.argmax(1)], P.max(1)
            accs.append((pr == y[te]).mean()); f1s.append(f1_score(y[te], pr, average="macro"))
            cm += confusion_matrix(y[te], pr, labels=labels)
            for t in TH:
                m = cf > t; sel[t][0] += (pr[m] == y[te][m]).sum(); sel[t][1] += m.sum()
        n = len(y) * 10
        print(f"\n  {name}")
        print(f"    accuracy {np.mean(accs):.1%} (sd {np.std(accs):.1%})   macro-F1 {np.mean(f1s):.3f}")
        for t in TH:
            print(f"    when confidence > {t}: accuracy {sel[t][0] / sel[t][1]:.1%} on {sel[t][1] / n:.1%} of learners")
        if tune:
            print("    confusion matrix, all 50 folds (rows = questionnaire label, columns = predicted):")
            print("          " + "".join(f"{c:>7s}" for c in labels))
            for i, c in enumerate(labels):
                print(f"      {c:>3s} " + "".join(f"{v:7d}" for v in cm[i]))
    shutil.rmtree(wd, ignore_errors=True)

# 3 -------------------------------------------------------------------------
banner(3, "Knowledge Gap Predictor + Difficulty Optimization: next-answer accuracy, held-out learners")
if need("question_attempts.csv"):
    os.environ["EVIDENCE_OUT"] = os.path.join(tempfile.gettempdir(), "learn_eval_next_answer.json")
    subprocess.run([sys.executable, os.path.join(REPO, "scripts", "eval_next_answer_accuracy.py"), os.path.join(DATA, "question_attempts.csv")])

# 4 -------------------------------------------------------------------------
banner(4, "Difficulty Optimization: recovering the true difficulty of each question")
if need("question_attempts.csv", "bkt_global_params.json"):
    wd = workdir("question_attempts.csv", "bkt_global_params.json")
    out = subprocess.run([sys.executable, os.path.join(HERE, "irt_calibration_mastery_conditioned.py")],
                         cwd=wd, capture_output=True, text=True)
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    print("\n".join("  " + l for l in lines[-12:]) if out.returncode == 0 else out.stderr[-1500:])
    shutil.rmtree(wd, ignore_errors=True)

# 5 -------------------------------------------------------------------------
banner(5, "Dropout Risk Prediction")
print("  The deployed model's numbers (ROC-AUC 0.643, accuracy 79.0%, recall 0.40) come from its")
print("  own training script and the final 6,345-row cohort; run that script to reproduce them.")
print(f"\nDone in {time.time() - start:.0f} s.")

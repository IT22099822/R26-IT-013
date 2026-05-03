"""Unit tests for the Difficulty Optimization component: services/irt.py (IRTService) and
apply_relative_difficulty() from routers/quiz.py, with an in-memory Supabase stub.
Run from the backend repo root:  python tests/test_c3_irt_unit.py"""
import os as _os, sys as _sys
_ROOT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)   # run from any folder: imports and ml_models/ resolve from the repo root
import asyncio, copy, math, sys, types


class _Res:
    def __init__(self, d): self.data = d


class _Q:
    def __init__(self, db, t): self.db, self.t, self.f, self.mode, self.payload = db, t, [], 'select', None
    def select(self, *a, **k): return self
    def eq(self, k, v): self.f.append(lambda r: r.get(k) == v); return self
    def in_(self, k, vs): self.f.append(lambda r: r.get(k) in vs); return self
    def update(self, p): self.mode = 'update'; self.payload = p; return self
    def execute(self):
        rows = [r for r in self.db.setdefault(self.t, []) if all(f(r) for f in self.f)]
        if self.mode == 'update':
            self.db.setdefault('_writes', []).append((self.t, copy.deepcopy(self.payload)))
            for r in rows: r.update(copy.deepcopy(self.payload))
            return _Res(rows)
        return _Res(copy.deepcopy(rows))


class FakeSupabase:
    def __init__(self): self.db = {}
    def table(self, n): return _Q(self.db, n)


sb = FakeSupabase()
m = types.ModuleType('db.supabase'); m.supabase = sb; sys.modules['db'] = types.ModuleType('db'); sys.modules['db.supabase'] = m
qg = types.ModuleType('services.question_generator')
qg.DIFFICULTY_BAND_OFFSETS = {'easy': -1.5, 'just_right': 0.0, 'hard': 1.0, 'impossible': 2.5}   # as in services/question_generator.py
sys.modules['services.question_generator'] = qg
from services.irt import IRTService, PUBLISHED_WEIGHT, UNVALIDATED_WEIGHT  # noqa: E402
import ast as _ast, math as _math  # noqa: E402
# apply_relative_difficulty() lives in routers/quiz.py, which needs FastAPI to import;
# compile just that function from the real source file instead.
_src = open(_os.path.join(_ROOT, "routers", "quiz.py"), encoding="utf-8").read()
_fn = [n for n in _ast.parse(_src).body if isinstance(n, _ast.FunctionDef) and n.name == "apply_relative_difficulty"][0]
_ns = {"math": _math}; exec(compile(_ast.Module(body=[_fn], type_ignores=[]), "routers/quiz.py", "exec"), _ns)
apply_relative_difficulty = _ns["apply_relative_difficulty"]

svc = IRTService(); results = []


def check(uid, desc, ok, got):
    results.append(ok); print(f'{uid:5s} {"PASS" if ok else "FAIL"}  {desc}  -> {got}')


def P(theta, b): return 1 / (1 + math.exp(-(theta - b)))


def resp(pairs, status='published'): return [{'correct': c, 'difficulty_tag': b, 'status': status} for b, c in pairs]


def seed(theta, practice, anchors=(), questions=()):
    sb.db.clear()
    sb.db['students'] = [dict(student_id='s1', irt_theta=theta, irt_theta_history=[])]
    sb.db['question_attempts'] = [dict(student_id='s1', **p) for p in practice]
    sb.db['anchor_scores'] = [dict(student_id='s1', **a) for a in anchors]
    sb.db['questions'] = [dict(q) for q in questions]


# ---- response model and ability estimation
check('UT1', 'P(correct)=0.5 when theta=b and increases with theta-b', abs(P(0.7, 0.7) - 0.5) < 1e-12 and P(1, 0) > P(0, 0) > P(-1, 0), f'{P(1,0):.3f} > {P(0,0):.3f} > {P(-1,0):.3f}')
hi = svc._fit_theta(resp([(b, True) for b in (-1, 0, 1, 2)] * 3)); lo = svc._fit_theta(resp([(b, False) for b in (-1, 0, 1, 2)] * 3))
check('UT2', 'theta stays inside [-4, 4] for all-correct and all-wrong histories', -4 <= lo < -3.9 and 3.9 < hi <= 4, (lo, hi))
mixed = resp([(-1, True), (-0.5, True), (0, True), (0.5, False), (1, True), (1.5, False), (2, False), (0, True)])
grid = max((x / 1000 for x in range(-4000, 4001)), key=lambda t: sum(math.log(P(t, r['difficulty_tag'])) if r['correct'] else math.log(1 - P(t, r['difficulty_tag'])) for r in mixed))
th = svc._fit_theta(mixed)
check('UT3', 'bounded MLE agrees with a fine grid search of the log-likelihood', abs(th - grid) < 0.01, (th, round(grid, 3)))
th_none = svc._fit_theta(mixed + [{'correct': True, 'difficulty_tag': None, 'status': 'published'}])
check('UT4', 'responses without a difficulty value are ignored', th_none == th, th_none)

# ---- student-relative difficulty labels
qs = [dict(id=k, difficulty_tag=0.5) for k in range(3)] + [dict(id=3, difficulty_tag=0), dict(id=4, difficulty_tag=None)]
labs = []
for t in (2.0, 0.5, -1.0):
    q = [dict(qs[0])]; apply_relative_difficulty(q, t); labs.append(q[0]['relative_difficulty'])
check('UT5', 'same item (b=0.5) is easy / medium / hard for theta 2.0 / 0.5 / -1.0', labs == ['easy', 'medium', 'hard'], labs)
q = [dict(qs[3]), dict(qs[4])]; apply_relative_difficulty(q, 1.0)
check('UT6', 'items with placeholder difficulty 0 or no difficulty are "unrated"', [x['relative_difficulty'] for x in q] == ['unrated', 'unrated'], [x['relative_difficulty'] for x in q])
b70 = 1.0 - math.log(0.70 / 0.30); b40 = 1.0 - math.log(0.40 / 0.60)
q = [dict(difficulty_tag=b70 - 1e-6), dict(difficulty_tag=b70 + 1e-6), dict(difficulty_tag=b40 - 1e-6), dict(difficulty_tag=b40 + 1e-6)]
apply_relative_difficulty(q, 1.0)
check('UT7', 'thresholds: P>0.70 easy, 0.40-0.70 medium, P<0.40 hard (just either side of each cut)', [x['relative_difficulty'] for x in q] == ['easy', 'medium', 'medium', 'hard'], [x['relative_difficulty'] for x in q])

# ---- generated-content weighting
base = [(-1.0, True), (-0.5, True), (0.0, True), (0.0, False), (0.5, True), (0.5, False), (1.0, True), (1.0, False), (1.5, False), (2.0, False)]
t_base = svc._fit_theta(resp(base))
bad = {'correct': True, 'difficulty_tag': 3.5}   # generated item tagged very hard, answered correctly (actually easy)
t_full = svc._fit_theta(resp(base) + [dict(bad, status='published')])
t_down = svc._fit_theta(resp(base) + [dict(bad, status='pending_review')])
check('UT8', f'mislabelled generated item moves theta less at weight {UNVALIDATED_WEIGHT} than at {PUBLISHED_WEIGHT}', abs(t_down - t_base) < abs(t_full - t_base),
      f'base {t_base:.2f}; full weight {t_full:.2f}; weight 0.3 {t_down:.2f}')

# ---- gathering, update and projection through the service (stubbed database)
practice = [dict(correct=c, difficulty_tag=b, question_id=f'P{k}') for k, (b, c) in enumerate(base)]
anchors = [dict(correct=True, question_id='A1'), dict(correct=False, question_id='A2')]
questions = [dict(question_id=f'P{k}', difficulty_tag=b, status='published') for k, (b, _) in enumerate(base)] + \
            [dict(question_id='A1', difficulty_tag=-0.5, status='published'), dict(question_id='A2', difficulty_tag=1.2, status='published')]
seed(0.0, practice, anchors, questions)
g = asyncio.run(svc._gather_weighted_responses('s1'))
check('UT9', 'anchor answers are gathered with their question difficulty; practice and anchors combined', len(g) == 12 and {(r['difficulty_tag'], r['correct']) for r in g[-2:]} == {(-0.5, True), (1.2, False)}, len(g))
seed(0.0, practice, anchors, [q for q in questions if q['question_id'] != 'A2'])
g = asyncio.run(svc._gather_weighted_responses('s1'))
check('UT10', 'a question missing from the bank defaults to status "published" (full weight)', g[-1]['status'] == 'published' and g[-1]['difficulty_tag'] is None, g[-1])
seed(0.0, practice, anchors, questions)
new = asyncio.run(svc.update('s1', 0.5, 1)); s = sb.db['students'][0]
check('UT11', 'update() refits theta from full history, stores it, appends history, sets target difficulty = theta',
      s['irt_theta'] == new and s['current_target_difficulty'] == new and len(s['irt_theta_history']) == 1, new)
seed(new, practice, anchors, questions)
hard = asyncio.run(svc.project_improvement('s1', 'hard', 10)); easy = asyncio.run(svc.project_improvement('s1', 'easy', 10))
check('UT12', '10 hypothetical correct answers move theta more at "hard" than at "easy"', hard['delta'] > easy['delta'] > 0, f"hard +{hard['delta']:.2f}, easy +{easy['delta']:.2f}")
check('UT13', 'project_improvement() is read-only (no database writes)', not sb.db.get('_writes'), 'no writes')
n = sum(results); print(f'\n{n}/{len(results)} passed')

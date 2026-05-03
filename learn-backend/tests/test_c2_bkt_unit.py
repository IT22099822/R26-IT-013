"""Unit tests UT1-UT10 (thesis Table 5.3) for services/bkt.py.

Runs the REAL BKTService.update() / find_upstream_gaps() code with the
Supabase client replaced by an in-memory stub, so no database is needed.

Usage (from the backend repo root):
    python tests/test_c2_bkt_unit.py
"""
import os as _os, sys as _sys
_ROOT = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")
_sys.path.insert(0, _ROOT)
_os.chdir(_ROOT)   # run from any folder: imports and ml_models/ resolve from the repo root
import asyncio, copy, sys, types

# ---- in-memory stand-in for db.supabase -----------------------------------
class _Res:
    def __init__(self, data): self.data = data
class _Query:
    def __init__(self, db, table): self.db, self.table, self.filters, self.payload, self.mode = db, table, [], None, "select"
    def select(self, cols): self.mode = "select"; return self
    def update(self, payload): self.mode = "update"; self.payload = payload; return self
    def eq(self, k, v): self.filters.append((k, v)); return self
    def execute(self):
        rows = [r for r in self.db[self.table] if all(r.get(k) == v for k, v in self.filters)]
        if self.mode == "update":
            for r in rows: r.update(copy.deepcopy(self.payload))
            return _Res(rows)
        return _Res(copy.deepcopy(rows))
class FakeSupabase:
    def __init__(self): self.db = {"students": [], "content_nodes": []}
    def table(self, name): return _Query(self.db, name)

supabase = FakeSupabase()
db_pkg = types.ModuleType("db"); db_mod = types.ModuleType("db.supabase"); db_mod.supabase = supabase
sys.modules["db"] = db_pkg; sys.modules["db.supabase"] = db_mod

from services.bkt import BKTService  # noqa: E402  (imported after the stub on purpose)
svc = BKTService()

def reset(mastery=None, gaps=None, mastered=None, nodes=None):
    supabase.db["students"] = [{"student_id": "s1", "bkt_mastery": dict(mastery or {}),
                                "current_gaps": list(gaps or []), "nodes_mastered": list(mastered or [])}]
    supabase.db["content_nodes"] = nodes or [{"node_id": "N", "mastery_threshold": None, "prerequisites": []}]
def student(): return supabase.db["students"][0]
def run(node, correct): return asyncio.run(svc.update("s1", node, correct))

results = []
def check(uid, desc, ok, got):
    results.append(ok); print(f"{uid:5s} {'PASS' if ok else 'FAIL'}  {desc}  -> {got}")

reset(); r = run("N", 1); check("UT1", "new node, correct", r["mastery"] == 0.6604, r["mastery"])
reset(); r = run("N", 0); check("UT2", "new node, incorrect", r["mastery"] == 0.2397, r["mastery"])
reset({"N": 0.5}); r = run("N", 1); check("UT3", "mastery 0.5, correct", r["mastery"] == 0.8624, r["mastery"])
reset({"N": 0.5}); r = run("N", 0); check("UT4", "mastery 0.5, incorrect", r["mastery"] == 0.2952, r["mastery"])
reset(); s = [run("N", 1) for _ in range(3)]
check("UT5", "three correct from new", [x["mastery"] for x in s] == [0.6604, 0.9226, 0.9862]
      and [x["newly_mastered"] for x in s] == [False, False, True] and student()["nodes_mastered"] == ["N"],
      [x["mastery"] for x in s])
reset(nodes=[{"node_id": "N", "mastery_threshold": 0.90, "prerequisites": []}]); s = [run("N", 1) for _ in range(2)]
check("UT6", "node threshold 0.90", [x["newly_mastered"] for x in s] == [False, True], [x["mastery"] for x in s])
two = [{"node_id": "N", "mastery_threshold": None, "prerequisites": ["P"]},
       {"node_id": "P", "mastery_threshold": None, "prerequisites": []}]
reset({"P": 0.30}, nodes=two); run("N", 1)
check("UT7", "prerequisite at 0.30 flagged", "P" in student()["current_gaps"], student()["current_gaps"])
reset({"X": 0.30}, gaps=["X"]); run("N", 1)
check("UT8", "unrelated gap at 0.30 retained", student()["current_gaps"] == ["X"], student()["current_gaps"])
reset({"X": 0.60}, gaps=["X"]); run("N", 1)
check("UT9", "gap risen to 0.60 removed", student()["current_gaps"] == [], student()["current_gaps"])
reset({"N": 0.99}, mastered=["N"]); r = run("N", 1)
check("UT10", "already mastered not added twice", student()["nodes_mastered"] == ["N"] and not r["newly_mastered"],
      student()["nodes_mastered"])

print(f"\n{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)

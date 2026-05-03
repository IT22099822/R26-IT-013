"""Runs every unit test file in this folder and prints one summary line per file.
Run from the backend repo root:  python tests/run_all.py"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
files = sorted(f for f in os.listdir(HERE) if f.startswith("test_") and f.endswith(".py"))
total_ok = total = 0
for f in files:
    out = subprocess.run([sys.executable, os.path.join(HERE, f)], capture_output=True, text=True)
    m = re.search(r"(\d+)/(\d+) passed", out.stdout)
    if m:
        ok, n = int(m.group(1)), int(m.group(2))
        total_ok += ok; total += n
        print(f"{f:28s} {ok}/{n} passed")
    else:
        print(f"{f:28s} ERROR\n{out.stdout[-800:]}{out.stderr[-1500:]}")
        total += 1
print(f"\nAll tests: {total_ok}/{total} passed")
sys.exit(0 if total_ok == total else 1)

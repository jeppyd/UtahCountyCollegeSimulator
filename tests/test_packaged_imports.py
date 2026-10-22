"""The Windows app leaves out pyarrow, duckdb and pandas (packaging/ucsim.spec `excludes`): building and running a
world must not import them. (A pyarrow import in engine/places.py once broke the packaged app's self-test.)"""
import subprocess
import sys

CODE = """
import sys
for m in ("pyarrow", "duckdb", "pandas"):
    sys.modules[m] = None            # importing these now raises ImportError, as in the packaged app
from ucsim.engine.runner import new_simulation
from ucsim.engine import placement
sim = new_simulation(scale=0.02, seed=3)
sim.run_days(1)
placement.place(sim, sim.systems["activity"].snapshot)
print("ok")
"""


def test_world_runs_without_excluded_packages():
    r = subprocess.run([sys.executable, "-c", CODE], capture_output=True, text=True, timeout=600)
    assert r.returncode == 0 and r.stdout.strip().endswith("ok"), r.stderr[-3000:]

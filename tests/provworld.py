"""One small world run long enough for weekly and monthly systems, shared by the provenance and trace tests."""
from functools import lru_cache

from ucsim.engine.runner import new_simulation


@lru_cache(maxsize=1)
def world():
    sim = new_simulation(scale=0.03, seed=21)
    sim.run_days(40)
    return sim

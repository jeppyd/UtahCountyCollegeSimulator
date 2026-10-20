"""Speed budget (ucsim/perf.py, config/perf_budget.json): a simulated day, and each system in it, stays within the
recorded budget, normalized for the machine. Set UCSIM_SKIP_SPEED=1 to skip (e.g. on a busy machine)."""
import os

import pytest

from ucsim import perf


@pytest.mark.skipif(os.environ.get("UCSIM_SKIP_SPEED") == "1", reason="UCSIM_SKIP_SPEED=1")
def test_day_within_speed_budget():
    budget = perf.load_budget()
    assert budget, "no speed budget recorded: run python scripts/perf.py --update"
    m = perf.measure()
    problems = perf.check(m, budget)
    if problems:          # one retry: a background process can slow a single measurement
        m = perf.measure()
        problems = perf.check(m, budget)
    assert not problems, ("slower than the speed budget — optimize, or if the cost is worth it record a new budget "
                          "(python scripts/perf.py --update \"why\") and say so in docs/HANDOFF.md: " + "; ".join(problems))


def test_check_flags_a_slow_system():
    budget = {"norm_per_day": 10.0, "norm_systems": {"a": 2.0, "b": 0.5}}
    ok = {"norm_per_day": 10.0, "norm_systems": {"a": 2.4, "b": 0.6, "new": 0.5}}
    assert perf.check(ok, budget) == []
    slow = {"norm_per_day": 16.0, "norm_systems": {"a": 6.0, "b": 0.5, "new": 2.0}}
    msgs = perf.check(slow, budget)
    assert any("day takes" in x for x in msgs) and any("'a'" in x for x in msgs) and any("'new'" in x for x in msgs)

import pytest

from ucsim.engine.runner import fork, new_simulation

SCALE = 0.04
DAYS = 21


@pytest.fixture(scope="session")
def fresh():
    """A just-built world (no days simulated)."""
    return new_simulation(scale=SCALE, seed=7)


@pytest.fixture(scope="session")
def ran():
    """A world simulated for three weeks."""
    sim = new_simulation(scale=SCALE, seed=11)
    sim.run_days(DAYS)
    return sim


@pytest.fixture(scope="session")
def paired():
    """Baseline + a forked intervention universe after a short burn-in."""
    base = new_simulation(scale=SCALE, seed=13)
    base.run_days(3)
    alt = fork(base, [{"preset": "rent_up_20"}, {"preset": "new_dating_app"}])
    for _ in range(10):
        base.step_day()
        alt.step_day()
    return base, alt

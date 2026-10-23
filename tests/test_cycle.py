"""Menstrual cycle (engine/systems/cycle.py): only women of the right age cycle, the clock advances and wraps, effects
are small and vary by person, and hormonal birth control flattens them."""
import copy

import numpy as np

from ucsim.engine.runner import new_simulation


def test_only_women_of_cycling_age_have_a_cycle(ran):
    P = ran.w.P
    present = P["present"].astype(bool)
    on = P["cycle_day"] > 0
    assert not (on & P.is_("sex", "M")).any()
    assert not (on & P["pregnant"].astype(bool)).any()
    women = present & P.is_("sex", "F") & (P["age"] >= 18) & (P["age"] <= 40) & ~P["pregnant"].astype(bool)
    assert on[women].mean() > 0.8
    assert (P["cycle_day"][on] <= P["cycle_length"][on]).all()
    assert (P.is_("cycle_phase", "none") == ~on).all()
    # phases are spread across the population (every phase present among naturally cycling women)
    natural = on & ~P["hormonal_contraception"].astype(bool)
    for ph in ("period", "follicular", "fertile window", "luteal", "premenstrual"):
        assert P.is_("cycle_phase", ph)[natural].mean() > 0.03, ph


def test_clock_advances_and_wraps(ran):
    sim = copy.deepcopy(ran)
    P = sim.w.P
    before = P["cycle_day"].copy()
    sim.step_day()
    after = P["cycle_day"]
    both = (before > 0) & (after > 0)
    assert ((after[both] == before[both] + 1) | (after[both] == 1)).all()
    wrapped = both & (after == 1)
    assert wrapped.any()
    lengths = P["cycle_length"][(after > 0) & ~P["hormonal_contraception"].astype(bool)]
    assert 26 <= lengths.mean() <= 32 and lengths.min() >= 21


def test_sensitivity_is_skewed_and_birth_control_is_plausible(ran):
    P = ran.w.P
    women = P["present"].astype(bool) & P.is_("sex", "F")
    s = P["cycle_sensitivity"][women]
    assert np.median(s) < 0.15 and 0.12 < (s > 0.4).mean() < 0.3 and (s > 0.85).mean() < 0.08
    assert (P["cycle_sensitivity"][P.is_("sex", "M")] == 0).all()
    on = P["cycle_day"] > 0
    hc = P["hormonal_contraception"].astype(bool)
    assert 0.08 < hc[on].mean() < 0.45
    assert not (hc & P.is_("cycle_phase", "fertile window")).any()


def test_mood_term_is_small_and_follows_sensitivity(ran):
    sim = copy.deepcopy(ran)
    sim.step_day()
    P = sim.w.P
    emo = sim.systems["emotion"]
    mood = emo.contrib["mood"]["cycle"]
    assert (mood <= 0).all() and mood.min() > -0.2
    assert (mood[P.is_("sex", "M")] == 0).all()
    pms = P.is_("cycle_phase", "premenstrual") & ~P["hormonal_contraception"].astype(bool)
    s = P["cycle_sensitivity"]
    assert abs(mood[pms].mean()) < 0.05                          # on average a small dip
    if (pms & (s > 0.7)).any() and (pms & (s < 0.1)).any():
        assert mood[pms & (s > 0.7)].mean() < mood[pms & (s < 0.1)].mean() - 0.03
    assert "cycle" in emo.contrib["fatigue"] and "cycle" in emo.contrib["anxiety"]


def test_desire_rises_in_fertile_window_and_falls_on_period(ran):
    P = ran.w.P
    cyc = ran.systems["cycle"]
    ids = np.arange(P.n)
    d = cyc.desire(ids)
    natural = ~P["hormonal_contraception"].astype(bool)
    assert d[P.is_("cycle_phase", "fertile window") & natural].mean() > 0.1
    assert d[P.is_("cycle_phase", "period") & natural].mean() < -0.1
    assert (d[P.is_("sex", "M")] == 0).all()


def test_deterministic():
    a = new_simulation(scale=0.02, seed=5).run_days(5)
    b = new_simulation(scale=0.02, seed=5).run_days(5)
    assert np.array_equal(a.w.P["cycle_day"], b.w.P["cycle_day"])
    assert np.array_equal(a.w.P["mood"], b.w.P["mood"])

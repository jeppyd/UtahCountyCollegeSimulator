"""Physical intimacy (engine/systems/intimacy.py): limits shape the pace, dealbreakers can end things, and the
system is deterministic."""
import numpy as np

from ucsim.engine.runner import new_simulation
from ucsim.engine.state import EdgeStore


def _unmarried_couples(sim):
    P = sim.w.P
    part = P["partner_id"]
    ids = np.where((part >= 0) & (np.arange(P.n) < part) & P["present"])[0]
    j = part[ids].astype(np.int64)
    I = sim.systems["intimacy"]
    stage = I.stage_index(P["rel_status"][ids])
    keep = (stage >= 0) & (stage <= 2)
    return ids[keep], j[keep], stage[keep]


def test_survey_variables_are_drawn(fresh):
    P = fresh.w.P
    young = P["present"].astype(bool) & (P["age"] < 36)
    sex = P["ok_stage_sex"][young]
    assert 0.6 < (sex == 3).mean() < 0.95                   # most think sex belongs in marriage
    touch = P["ok_stage_touch"][young]
    assert (P["ok_stage_naked"][young] >= touch).all()        # the ladder is monotone per person
    men = young & P.is_("sex", "M") & P.is_("activity", "active")
    women = young & P.is_("sex", "F") & P.is_("activity", "active")
    assert (P["porn_use"][men] > 0).mean() > 2 * (P["porn_use"][women] > 0).mean()
    married = P.is_("rel_status", "married")
    assert (P["sexual_satisfaction"][~married] == 0).all()


def test_escalation_respects_limits_on_average(ran):
    sim = ran
    P = sim.w.P
    I = sim.systems["intimacy"]
    a, b, stage = _unmarried_couples(sim)
    lvl = P["intimacy_level"][a].astype(int)
    lim = np.minimum(I.allowed(a, stage), I.allowed(b, stage))
    assert (P["intimacy_level"][a] == P["intimacy_level"][b]).all()
    assert (lvl <= lim).mean() > 0.7                           # most couples stay within both partners' limits
    # the steps taken: a step past someone's line was far less likely, week for week, than one within both
    D = sim.decisions
    rows = np.flatnonzero(D.t["kind"][: D.t.n] == D.kind_id["intimacy_step"])
    assert len(rows) > 0
    fid = D.factor_id["intimacy_step.within_lines"]
    codes, vals = D.t["f_code"][rows], D.t["f_val"][rows].astype(float)
    within = (np.where(codes == fid, vals, 0).sum(1) > 0)
    prob = D.t["prob"][rows].astype(float)
    assert within.any() and (~within).any()
    assert prob[within].mean() > 2 * prob[~within].mean()


def test_dealbreaker_can_end_a_relationship():
    sim = new_simulation(scale=0.03, seed=5)
    P, E = sim.w.P, sim.w.E
    I = sim.systems["intimacy"]
    a, b, _ = _unmarried_couples(sim)
    assert len(a) > 5
    # make the partner's porn use a firm dealbreaker for a, true of b, and the couple close to telling everything
    P.cols["db_watches_porn"][a] = 4
    P.cols["porn_use"][b] = 3
    P.cols["relationship_commitment"][a] = 0.0
    eix = E.find(EdgeStore.make_keys(a, b))
    E.cols["disclosure"][eix] = 1.0
    E.cols["closeness"][eix] = 0.0
    for _ in range(42):          # six weeks: each couple takes its weekly turn on its own day
        I.couples_week()
        sim.w.day += 1
    L = sim.log
    t = L.cols["type"][: L.n]
    assert (t == sim.reg.event_ids["dealbreaker_found"]).sum() > 0
    D = sim.decisions
    rows = D.t["kind"][: D.t.n] == D.kind_id["dealbreaker_reaction"]
    assert rows.sum() > 0
    ended = (D.t["outcome"][: D.t.n][rows] == 0).sum()
    assert ended > 0
    assert (P["partner_id"][a] != b).sum() >= ended


def test_intimacy_is_deterministic():
    out = []
    for _ in range(2):
        sim = new_simulation(scale=0.02, seed=3)
        sim.run_days(15)
        L = sim.log
        out.append((sim.w.P["intimacy_level"].copy(), L.cols["type"][: L.n].copy()))
    assert np.array_equal(out[0][0], out[1][0])
    assert np.array_equal(out[0][1], out[1][1])

"""The cognitive and social layers added in iteration 5: mind, memory, coping, plans, routines, cultures,
perception, accounting, uncertainty and panel analysis."""
import copy

import numpy as np

from ucsim.analysis.accounting import stocks, yearly_report
from ucsim.analysis.inner import inner_life
from ucsim.analysis.panel import cross_lagged
from ucsim.engine.memory import MemoryStore
from ucsim.engine.runner import fork
from ucsim.engine.state import EdgeStore
from ucsim.engine.systems.mind import MOTIVES
from ucsim.engine.uncertainty import decompose, sample, uncertain_params
from ucsim.registry import EVIDENCE_LEVELS, ParamSet, get_registry


def test_motives_drives_and_priorities_are_bounded(ran):
    P = ran.w.P
    pres = P["present"].astype(bool)
    for m in MOTIVES:
        c, d = P[f"cares_{m}"][pres], P[f"drive_{m}"][pres]
        assert np.all((c >= 0) & (c <= 1)) and np.all((d >= 0) & (d <= c + 1e-6)), m
    # drive = importance × unmet, so the top priority is the largest drive
    D = np.stack([P[f"drive_{m}"] for m in MOTIVES])
    assert np.array_equal(np.argmax(D, axis=0)[pres], P["top_priority"][pres])


def test_perception_differs_from_reality_but_tracks_it(ran):
    P = ran.w.P
    pres = P["present"].astype(bool)
    r = np.corrcoef(P["perceived_support"][pres], P["support_actual"][pres])[0, 1]
    assert 0.15 < r < 0.9            # related, but not the same thing
    assert np.abs(P["perceived_support"][pres] - P["support_actual"][pres]).mean() > 0.05
    E = ran.w.E
    seen = (E["n_inter"] > 3) & ((E["bel_lh"] != 0) | (E["bel_hl"] != 0))
    assert seen.any() and np.all(np.abs(E["bel_lh"]) <= 1) and np.all(np.abs(E["bel_hl"]) <= 1)


def test_expectation_learning_moves_toward_outcomes(fresh):
    sim = copy.deepcopy(fresh)
    P = sim.w.P
    mind = sim.systems["mind"]
    ids = np.where(P["present"])[0][:50]
    before = P["expect_accept"][ids].copy()
    for _ in range(5):
        mind.learn_ask(ids, np.zeros(len(ids), bool))
    assert np.all(P["expect_accept"][ids] < before)
    low = P["expect_accept"][ids].copy()
    mind.learn_ask(ids, np.ones(len(ids), bool))
    assert np.all(P["expect_accept"][ids] > low)


def test_memory_encoding_forgetting_and_cap():
    reg = get_registry()
    mem = MemoryStore(reg)
    code = reg.event_ids["rejected"]
    for d in range(60):
        mem.encode(np.array([d]), np.array([1]), code, np.array([2]), d)
    assert mem.n == 60 and np.all(mem["valence"].astype(float) < 0)
    st_old, st_new = mem.strength(400)[0], mem.strength(400)[-1]
    assert st_new > st_old                       # recency
    mem.prune(400, decay=0.5, per_agent=10)
    assert mem.n <= 10
    rows = mem.recall(1, 400, 0.5, k=3)
    before = mem["rehearsal"][rows].copy()
    mem.recall(1, 400, 0.5, k=3, rehearse=False)
    assert np.array_equal(mem["rehearsal"][rows], before)   # reading does not rehearse


def test_inner_life_is_read_only(ran):
    sim = copy.deepcopy(ran)
    P = sim.w.P
    i = int(np.where(P["present"].astype(bool) & (P["n_memories"] > 0))[0][0])
    snap = (sim.memory["rehearsal"].copy(), sim.memory.n, P["expect_accept"].copy(), sim.systems["plans"].n)
    d = inner_life(sim, i)
    assert d["motives"] and d["beliefs"] and "coping" in d and "footprint" in d
    assert np.array_equal(sim.memory["rehearsal"], snap[0]) and sim.memory.n == snap[1]
    assert np.array_equal(P["expect_accept"], snap[2]) and sim.systems["plans"].n == snap[3]


def test_coping_episodes_have_strategies_and_causes(ran):
    log = ran.log
    started = np.where(log["type"] == ran.reg.event_ids["coping_started"])[0]
    assert len(started) > 0
    strat = log["value"][started].astype(int)
    assert set(strat.tolist()) <= {1, 2, 3, 4, 5}
    P = ran.w.P
    active = P["coping_strategy"] > 0
    assert np.all(P.internal["cope_start"][: P.n][active] >= 0)


def test_intentions_ledger_is_consistent(ran):
    pl = ran.systems["plans"]
    P = ran.w.P
    assert pl.n > 0
    row = P.internal["plan_row"][: P.n]
    has = row >= 0
    assert np.all(pl["status"][row[has]] == 0)                       # active rows only
    assert np.all(pl["agent"][row[has]] == np.where(has)[0])
    assert np.all(P["intention"][has] == pl["kind"][row[has]])
    done = pl["status"] > 0
    assert np.all(pl["end"][done] >= pl["start"][done])


def test_routines_and_cultures_exist(ran):
    P = ran.w.P
    pres = P["present"].astype(bool)
    assert P["routine_strength"][pres].mean() > 0.05
    C = ran.w.meta["culture"]
    for k in ("unit_social", "cx_social", "cx_relig", "ward_warmth"):
        assert np.all(np.isfinite(C[k]))
    assert np.all((C["cx_relig"] >= 0) & (C["cx_relig"] <= 1))


def test_relationship_history_columns(ran):
    E = ran.w.E
    for c in ("disclosure", "support", "hurt"):
        assert np.all(E[c] >= 0)
    assert np.all(E["disclosure"] <= 1) and np.all(E["hurt"] <= 1)
    assert (E["shared"] > 0).any()


def test_paired_universes_stay_identical_without_intervention(fresh):
    base = copy.deepcopy(fresh)
    twin = fork(base, [])
    for _ in range(4):
        base.step_day()
        twin.step_day()
    for c in ("mood", "loneliness", "expect_social", "perceived_support", "coping_strategy", "intention", "drive_connection"):
        assert np.array_equal(base.w.P[c], twin.w.P[c]), c
    assert base.memory.n == twin.memory.n and base.systems["plans"].n == twin.systems["plans"].n


def test_accounting_balances_people_present(ran):
    sim = copy.deepcopy(ran)
    cps = [{"day": sim.w.day, "stocks": stocks(sim)}]
    sim.run_days(10)
    cps.append({"day": sim.w.day, "stocks": stocks(sim)})
    row = yearly_report(sim, cps)[0]
    assert row["balance"]["serving_missionaries"]["residual"] == 0


def test_uncertainty_draws_respect_ranges_and_evidence():
    reg = get_registry()
    assert {"structural", "speculative"} <= set(EVIDENCE_LEVELS)
    params = uncertain_params(reg)
    assert any(p["dist"] == "choice" for p in params)   # an alternative mechanism form is in play
    draws = sample(params, 5, seed=3)
    base = ParamSet(reg)
    for p in params:
        assert draws[0][p["key"]] == base(p["key"])     # draw 0 = point values
        for d in draws[1:]:
            if p["dist"] == "choice":
                assert d[p["key"]] in p["options"]
            else:
                assert p["lo"] - 1e-9 <= d[p["key"]] <= p["hi"] + 1e-9
    # decomposition: pure seed noise is all stochastic; pure draw shifts are all parametric
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, (8, 6))
    assert decompose(noise)["share_stochastic"] > 0.7
    shift = np.repeat(rng.normal(0, 1, (8, 1)), 6, axis=1)
    assert decompose(shift)["share_parametric"] > 0.99


def test_cross_lagged_recovers_direction():
    rng = np.random.default_rng(1)
    T, N = 12, 400
    X = np.zeros((T, N))
    Y = np.zeros((T, N))
    a, b = rng.normal(0, 1, N), rng.normal(0, 1, N)       # stable between-person differences
    for t in range(T):
        X[t] = a + rng.normal(0, 1, N)
        Y[t] = b + (0.5 * (X[t - 1] - a) if t else 0) + rng.normal(0, 1, N)
    r = cross_lagged(X, Y)
    assert r["x_to_y"] > 0.2 and abs(r["y_to_x"]) < 0.1


def test_edge_store_append_insert_keeps_rows_and_index():
    rng = np.random.default_rng(0)
    E = EdgeStore(capacity=32)
    ref = {}
    for _ in range(40):
        a, b = rng.integers(0, 200, 25), rng.integers(0, 200, 25)
        ok = a != b
        k = EdgeStore.make_keys(a[ok], b[ok])
        idx = E.upsert(k)                     # upsert may grow (replace) the column arrays: index after it
        E.cols["liking"][idx] = (k % 89).astype(np.float32)
        ref.update({int(x): float(x % 89) for x in k})
    # rows keep their values where they were added; the sorted index finds every key
    assert len(E) == len(ref) and len(np.unique(E.key_array)) == len(ref)
    assert np.all(np.diff(E._sorted) > 0) and (E.find(E.key_array) == np.arange(len(E))).all()
    assert np.allclose(E["liking"], [ref[int(x)] for x in E.key_array])
    gone = np.zeros(len(E), bool)
    gone[::3] = True
    keep = E.key_array[~gone].copy()
    E.remove(gone)                            # compaction rebuilds the index
    assert (E.key_array == keep).all() and (E.find(keep) == np.arange(len(keep))).all()


def test_attribution_threshold_tightens_with_more_parameters_and_loosens_with_draws():
    from ucsim.engine.uncertainty import _critical_rho
    assert _critical_rho(12, 82) > _critical_rho(12, 5) > 0.5
    assert _critical_rho(40, 82) < _critical_rho(12, 82) < 1

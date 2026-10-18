"""Provenance: how much of the record carries its reasons, and whether those reasons are the model's own terms."""
import numpy as np
import pytest
from provworld import world
from scipy.special import expit

from ucsim.analysis.trace import coverage
from ucsim.engine.ledger import CAUSE_ID, CONSTRAINT
from ucsim.engine.provenance import (MECH_BASE, ROLE_CODE, VAR_BASE, note_info, place_ref, split_place, split_state,
                                     state_ref, total)
from ucsim.engine.state import CTX_ID, EdgeStore
from ucsim.registry import get_registry


@pytest.fixture(scope="module")
def sim():
    return world()


def test_coverage_thresholds(sim):
    """Before this work 27–30% of events had any recorded reason; now nearly every salient event does."""
    c = coverage(sim)
    h = c["headline"]
    assert h["salient_any"] >= 0.9, h
    assert h["other_any_excl"] >= 0.7, h            # the rest, without the bookkeeping event type added for plans
    assert h["salient_several"] >= 0.3, h           # a web, not only a chain
    by = {r["type"]: r for r in c["types"]}
    # the event types that never had a reason before
    for t in ("new_friend", "asked_out", "job_found", "illness", "faith_challenge", "coping_started", "plan_abandoned"):
        if t in by:
            assert by[t]["any"] >= 0.95, (t, by[t])
    for t in ("breakup_initiated", "breakup_received"):
        if t in by:
            assert by[t]["any"] >= 0.95 and by[t]["typed"] >= 0.95, (t, by[t])


def test_every_recorded_factor_is_declared(sim):
    """Every decision kind and factor a system records has plain words in config/decisions/*.yaml."""
    D = sim.decisions
    reg = get_registry()
    T = D.t
    assert T.n > 100
    used_kinds = {D.kinds[k] for k in np.unique(T["kind"])}
    for k in used_kinds:
        spec = reg.decisions[k]
        assert spec.get("label") and spec.get("outcomes") and spec.get("units"), k
    codes = np.unique(T["f_code"][T["f_code"] >= 0])
    for c in codes:
        kind, fid = D.factor_names[c].split(".", 1)
        fs = (reg.decisions[kind].get("factors") or {}).get(fid)
        assert fs is not None, f"{kind}.{fid} is recorded but not declared"
        assert fs.get("label"), f"{kind}.{fid} has no label"
    # and everything declared has words for at least one direction
    for kind, spec in reg.decisions.items():
        for fid, fs in (spec.get("factors") or {}).items():
            assert fs.get("label"), (kind, fid)


def test_decision_terms_add_up_to_the_models_probability(sim):
    """For yes/no decisions without multipliers, base + Σ factors (the terms actually added) gives the probability the
    model used, to float16 precision — the ledger records the formula, not a reconstruction."""
    D = sim.decisions
    T = D.t
    checked = 0
    for kind in ("accept_date", "get_engaged", "mission_call", "depression_onset", "conceive"):
        if kind not in D.kind_id:
            continue
        ids = T["id"][T["kind"] == D.kind_id[kind]][:200]
        spec = D.vocab[kind]
        for did in ids:
            d = D.get(int(did))      # the total is summed over every term, also those beyond the K kept for display
            p_yes = expit(d["total"])
            p = p_yes if d["outcome"] == spec["outcomes"][0] else 1 - p_yes
            assert abs(p - d["prob"]) < 0.02 + 0.02 * p, (kind, d)
            checked += 1
    assert checked > 20


def test_total_sums_in_the_models_order():
    a = np.array([0.1, 0.2], np.float32)
    b = np.array([1e-8, 3.0], np.float32)
    assert np.array_equal(total(0.5, {"a": a, "b": b}), 0.5 + a + b)


def test_constraints_are_couldnt(sim):
    D = sim.decisions
    fv = D.t["f_val"].astype(np.float32)
    cons = np.abs(fv) >= CONSTRAINT - 1
    # constraints are stored as −99 and only for declared constraint factors
    for r, c in zip(*np.nonzero(cons)):
        kind, fid = D.factor_names[int(D.t["f_code"][r, c])].split(".", 1)
        assert (D.vocab[kind]["factors"][fid]).get("kind") == "constraint"


def test_a_friendship_points_at_where_they_met(sim):
    """A new friendship's typed causes name where the two first met (the tie's origin) and where most of their time
    together went; an introducer, when there was one, is a cause too."""
    log, E, C = sim.log, sim.w.E, sim.causes
    nf = np.flatnonzero(log["type"] == sim.reg.event_ids["new_friend"])
    assert len(nf) > 20
    met_note = ROLE_CODE["met_at"]
    checked = intro = together = 0
    for e in nf:
        rows = C.of(int(e))
        if not rows:
            continue                       # the other person's copy: its parent is the first copy
        a, b = int(log["a"][e]), int(log["b"][e])
        ix = int(E.find(EdgeStore.make_keys(np.array([a]), np.array([b])))[0])
        if ix < 0:
            continue
        met = [r for r in rows if r["note"] == met_note]
        assert met, rows
        oc, op = int(E["origin_ctx"][ix]), int(E["origin_place"][ix])
        r = met[0]
        if oc == CTX_ID["occasion"]:
            assert r["kind"] == "occasion" and r["ref"] == op
        else:
            assert r["kind"] == "place" and r["ref"] == int(place_ref(oc, op))
        if E["introducer"][ix] >= 0:
            assert any(r["kind"] == "person" and r["ref"] == int(E["introducer"][ix]) and r["note"] == ROLE_CODE["introduced"]
                       for r in rows)
            intro += 1
        together += any(r["note"] == ROLE_CODE["time_together"] for r in rows)
        checked += 1
    assert checked >= 20
    assert together >= 0.5 * checked        # ties formed early may not have hours credited to a context yet
    # the mirror copy points at the first copy
    second = nf[log["cause"][nf] >= 0]
    assert len(second) and np.all(log["type"][log["cause"][second]] == sim.reg.event_ids["new_friend"])


def test_time_together_columns_are_consistent(sim):
    E = sim.w.E
    has = E["top_h"] > 0
    assert has.mean() > 0.3
    assert np.all(E["top_h"][has] <= E["hours"][has] + 1e-3)
    assert np.all(E["alt_h"] >= 0)
    assert np.all(E["alt_h"][has] <= E["top_h"][has] + 1e-3)


def test_breakups_say_who_ended_it_and_why(sim):
    log, C = sim.log, sim.causes
    got = np.flatnonzero(log["type"] == sim.reg.event_ids["breakup_received"])
    if not len(got):
        pytest.skip("no breakups in this short run")
    for e in got[:20]:
        rows = C.of(int(e))
        ended = [r for r in rows if r["note"] == ROLE_CODE["ended_by"]]
        assert ended and ended[0]["kind"] == "person" and ended[0]["ref"] == int(log["b"][e])
        first = [r for r in rows if r["note"] == ROLE_CODE["mirror"]]
        assert first and log["type"][first[0]["ref"]] == sim.reg.event_ids["breakup_initiated"]
    init = np.flatnonzero(log["type"] == sim.reg.event_ids["breakup_initiated"])
    has_dec = log["decision"][init] >= 0
    assert has_dec.mean() > 0.5          # weekly breakups carry their decision; departures carry the departure


def test_feelings_behind_an_episode_are_snapshotted(sim):
    """A depressive episode records the mood terms pulling mood down that week (as mechanism terms) and the hardest
    recent events — not today's decomposition, which may have changed by the time someone asks."""
    log, C = sim.log, sim.causes
    eps = np.flatnonzero(log["type"] == sim.reg.event_ids["depressive_episode_start"])
    if not len(eps):
        pytest.skip("no episodes in this short run")
    n_mech = 0
    for e in eps[:30]:
        for r in C.of(int(e)):
            if r["kind"] == "state" and MECH_BASE <= r["note"] < MECH_BASE + 10000:
                info = note_info(sim, r["note"])
                assert info["type"] == "mechanism" and info["mechanism"].startswith("mood.")
                var, who = split_state(sim, r["ref"])
                assert who == int(log["a"][e]) and var in sim.w.P
                assert r["weight"] < 0           # pulling mood down
                n_mech += 1
    assert n_mech > 0


def test_note_and_ref_codes_round_trip(sim):
    assert note_info(sim, ROLE_CODE["met_at"])["link"] == "met_at"
    assert note_info(sim, VAR_BASE + 0)["type"] == "variable"
    ref = int(state_ref(sim, "loneliness", 12345))
    assert split_state(sim, ref) == ("loneliness", 12345)
    assert split_place(int(place_ref(CTX_ID["ward"], 7))) == ("ward", 7)
    assert split_place(int(place_ref(CTX_ID["hangout"], -1))) == ("hangout", -1)
    assert CAUSE_ID["tie"] >= 0


def test_plans_have_beginnings_and_reasons(sim):
    """Intentions start with a recorded choice (why this plan), and plans given up point back at that beginning and
    say what changed."""
    log, C = sim.log, sim.causes
    formed = np.flatnonzero(log["type"] == sim.reg.event_ids["intention_formed"])
    assert len(formed) > 50 and np.all(log["decision"][formed] >= 0)
    ab = np.flatnonzero(log["type"] == sim.reg.event_ids["plan_abandoned"])
    if len(ab):
        assert np.all(log["type"][log["cause"][ab][log["cause"][ab] >= 0]] == sim.reg.event_ids["intention_formed"])
        roles = {r["note"] for e in ab[:40] for r in C.of(int(e))}
        assert roles & {ROLE_CODE["target_gone"], ROLE_CODE["priorities"], ROLE_CODE["around_then"]}

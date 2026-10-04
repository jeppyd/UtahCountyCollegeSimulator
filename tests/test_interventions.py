"""Interventions, paired universes and counterfactual attribution."""
import copy

import numpy as np

from ucsim.analysis.explain import compare_universes
from ucsim.engine.interventions import expand, load_presets
from ucsim.engine.runner import divergence, fork


def test_every_preset_expands_to_valid_atoms():
    for pid in load_presets():
        atoms = expand(pid)
        assert atoms, pid
        for a in atoms:
            assert a["target_type"] in ("world", "param", "agent", "venue"), (pid, a)
            if a["target_type"] != "venue":
                assert "target" in a and "value" in a, (pid, a)


def test_param_targets_exist_in_registry(fresh):
    params = fresh.w.params
    for pid in load_presets():
        for a in expand(pid):
            if a["target_type"] == "param":
                assert a["target"] in params.values, (pid, a["target"])


def test_fork_is_identical_without_intervention(fresh):
    base = copy.deepcopy(fresh)
    twin = fork(base, [])
    for _ in range(3):
        base.step_day()
        twin.step_day()
    d = divergence(base, twin)
    assert d["any_state_diff"] == 0.0
    assert d["friendship_jaccard_distance"] == 0.0


def test_world_intervention_changes_environment(paired):
    base, alt = paired
    assert alt.w.env["rent_shock"] > base.w.env["rent_shock"] * 1.1
    assert alt.w.env["app_appeal"] > base.w.env["app_appeal"]
    assert alt.w.params("romance.app.rate") > base.w.params("romance.app.rate")


def test_intervention_does_not_leak_into_baseline(paired):
    base, _ = paired
    assert base.w.env["rent_shock"] == 1.0


def test_paired_universes_diverge_and_attribution_adds_up(paired):
    base, alt = paired
    d = divergence(base, alt)
    assert d["any_state_diff"] > 0
    cmp = compare_universes(base, alt)
    assert cmp["n"] > 0
    for s, row in cmp["states"].items():
        parts = sum(t["delta"] for t in row["terms"]) + row.get("events_delta", 0) + row.get("noise_delta", 0)
        assert abs(parts - row["delta"]) < 0.02, s


def test_agent_intervention_targets_only_cohort(fresh):
    base = copy.deepcopy(fresh)
    spec = {"target_type": "agent", "target": "porn_use", "op": "set", "value": 0,
            "population": {"var": "sex", "op": "eq", "value": "M"}}
    alt = fork(base, [spec])
    alt.step_day()
    base.step_day()
    P0, P1 = base.w.P, alt.w.P
    men = P1.is_("sex", "M")
    assert (P1["porn_use"][men] == 0).all() or np.mean(P1["porn_use"][men] == 0) > 0.95
    women = ~men & P1["present"].astype(bool)
    assert np.mean(P0["porn_use"][women] == P1["porn_use"][women]) > 0.9

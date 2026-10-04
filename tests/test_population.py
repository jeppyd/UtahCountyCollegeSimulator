"""Synthetic population: registry conformance, plausible margins, household/ward structure."""
import numpy as np

from ucsim.registry import get_registry


def test_every_registered_person_variable_has_a_column(fresh):
    P = fresh.w.P
    reg = get_registry()
    for k, v in reg.variables.items():
        if v.entity == "person":
            assert k in P, k
            assert len(P[k]) == P.n


def test_values_within_declared_ranges_and_categories(fresh):
    P = fresh.w.P
    reg = get_registry()
    for k, v in reg.variables.items():
        if v.entity != "person" or k not in P:
            continue
        x = P[k]
        if v.dtype == "cat":
            assert x.max(initial=0) < len(v.categories), k
        elif v.range and v.dtype in ("f4", "f8"):
            lo, hi = v.range
            xx = x[np.isfinite(x)]
            assert xx.min(initial=lo) >= lo - 1e-6 and xx.max(initial=hi) <= hi + 1e-6, (k, xx.min(), xx.max())


def test_no_nans_in_core_states(fresh):
    P = fresh.w.P
    for k in ("mood", "loneliness", "stress", "faith_belief", "age", "extraversion", "neuroticism"):
        assert np.isfinite(P[k]).all(), k


def test_population_margins_are_plausible(fresh):
    P = fresh.w.P
    stu = P["school"] > 0
    byu = P.is_("school", "BYU")
    assert byu.sum() > 1.5 * P.is_("school", "UVU").sum()
    female = P.is_("sex", "F")
    assert 0.4 < female[stu].mean() < 0.6
    lds = P["lds_member"].astype(bool)
    assert lds[byu].mean() > 0.95
    age = P["age"][stu]
    assert 17 <= np.median(age) <= 24
    married = P.is_("rel_status", "married")
    assert 0.12 < married[byu].mean() < 0.40


def test_spouses_are_mutual_and_coresident(fresh):
    P = fresh.w.P
    pid = P["partner_id"]
    m = P.is_("rel_status", "married") & (pid >= 0)
    i = np.where(m)[0]
    assert len(i) > 0
    assert (pid[pid[i]] == i).all()
    assert (P["unit_id"][i] == P["unit_id"][pid[i]]).mean() > 0.95


def test_housing_and_wards_assigned(fresh):
    P = fresh.w.P
    present = P["present"].astype(bool)
    assert (P["unit_id"][present] >= 0).mean() > 0.97
    lds_active = present & P["lds_member"].astype(bool) & P.is_("activity", "active")
    assert (P["ward_id"][lds_active] >= 0).mean() > 0.95


def test_no_mixed_sex_singles_apartments(fresh):
    P = fresh.w.P
    single_students = (P["school"] > 0) & ~P.isin("rel_status", ["married"]) & (P["unit_id"] >= 0)
    unit = P["unit_id"][single_students]
    sex = P["sex"][single_students]
    order = np.argsort(unit)
    u, s = unit[order], sex[order]
    same_unit = u[1:] == u[:-1]
    assert (s[1:][same_unit] == s[:-1][same_unit]).mean() > 0.97


def test_seed_reproducibility():
    from ucsim.population.build import build_world
    a = build_world(scale=0.02, seed=3)
    b = build_world(scale=0.02, seed=3)
    c = build_world(scale=0.02, seed=4)
    for k in ("age", "extraversion", "faith_belief", "unit_id"):
        assert np.array_equal(a.P[k], b.P[k]), k
    assert not np.array_equal(a.P["extraversion"][:200], c.P["extraversion"][:200])

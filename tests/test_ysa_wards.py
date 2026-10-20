"""Real Provo YSA wards (population/ysa_wards.py): the listing loads, units near listed buildings get their ward,
small wards merge within a stake, and the built world names them."""
import numpy as np

from ucsim.population import ysa_wards
from ucsim.population.structure import ward_name


def test_listing_and_merge():
    rows = ysa_wards.listing()["rows"]
    assert len(rows) > 400
    keys, idx = ysa_wards.real_wards()
    r = rows[0]
    got = ysa_wards.unit_wards(np.array([r["lon"]]), np.array([r["lat"]]))
    assert got[0] >= 0 and keys[got[0]][0] == r["stake"]
    groups = ysa_wards.merge_plan(np.full(len(keys), 7), 20)
    for g in groups:
        assert len({keys[i][0] for i in g}) == 1                # never across stakes
    assert sorted(i for g in groups for i in g) == list(range(len(keys)))
    assert ysa_wards.group_name([idx[keys[0]]])[1].endswith("Ward")


def test_world_has_named_real_wards(fresh):
    W, P = fresh.w.wards, fresh.w.P
    real = [k for k in range(len(W["kind"])) if W["stake"][k]]
    assert real and all("Stake" in ward_name(W, k) for k in real)
    members = np.isin(P["ward_id"], real)
    assert (P["lds_member"][members]).all()
    single = members & ~np.isin(P["ward_id"], [k for k in real if W["kind"][k] == "married_student"])
    assert not P.is_("rel_status", "married")[single].any()

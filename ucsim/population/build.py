"""Assemble a complete initial World (population + geography + institutions + seed network)."""
from __future__ import annotations

import datetime as dt
import time

import numpy as np
import polars as pl

from ..engine.state import CTX_ID, EdgeStore, PersonTable, Tie
from ..engine.world import World
from ..registry import ParamSet, get_registry
from .sampling import load_priors
from .structure import (BYU, GEO, UVU, HousingAssigner, build_fhe_groups, build_units, build_wards,
                        build_workplaces, km, pair_couples, seed_network)
from .synth import Synthesizer, load_world_cfg, zscore


def build_world(scale: float | None = None, seed: int = 1, verbose: bool = False, overrides: dict | None = None) -> World:
    t0 = time.time()
    reg = get_registry()
    cfg = load_world_cfg()
    scale = scale or cfg["default_scale"]
    rng = np.random.default_rng([seed, 1])
    pop = cfg["population"]
    est = int(80000 * scale * 1.3) + 1000
    P = PersonTable(reg, capacity=est)
    sy = Synthesizer(reg, scale, seed)
    s = lambda x: int(round(x * scale))  # noqa: E731
    byu = sy.people(P, "byu_student", s(pop["byu"]["students"]), "BYU")
    uvu = sy.people(P, "uvu_student", s(pop["uvu"]["students"]), "UVU")
    ya = sy.people(P, "young_adult", s(pop["young_adults"]), "none")
    fac_b = sy.people(P, "faculty", s(pop["faculty"] * 0.6), "BYU")
    fac_u = sy.people(P, "faculty", s(pop["faculty"] * 0.4), "UVU")
    staff = sy.people(P, "staff", s(pop["staff"]), "BYU")
    comm = sy.people(P, "community", s(pop["community"]), "none")
    for g in (fac_b, fac_u, staff, comm):
        P.cols["enrolled"][g] = False
        P.cols["class_standing"][g] = 0
    P.cols["school"][fac_b] = P.code("school", "BYU")
    P.cols["school"][fac_u] = P.code("school", "UVU")
    P.cols["school"][staff] = P.code("school", "BYU")
    if verbose:
        print(f"  persons {P.n} ({time.time() - t0:.1f}s)")

    # ---- literature bridge: extraversion ↔ social activity (cross-survey link, r≈0.3 assumption)
    ids = np.arange(P.n)
    ev = zscore(P["social_events_month"])
    P["extraversion"] = zscore(0.88 * P["extraversion"] + 0.35 * ev)
    P["social_skill"] = zscore(0.85 * P["social_skill"] + 0.2 * ev)

    # ---- couples
    day0 = 0
    pairs = []
    young = np.where(np.isin(P["role"], [P.code("role", r) for r in ("byu_student", "uvu_student", "young_adult")]))[0]
    married_pairs = pair_couples(P, young, rng, "married")
    paired = np.zeros(P.n, bool)
    for a, b in married_pairs:
        paired[a] = paired[b] = True
    left = young[(P["rel_status"][young] == P.code("rel_status", "married")) & ~paired[young]]
    # most leftover married students get a (non-student) spouse agent
    if len(left):
        n_sp = len(left)
        sp_sex = np.where(P["sex"][left] == P.code("sex", "M"), "F", "M")
        gay = P["orientation"][left] == P.code("orientation", "gay")
        sp_sex = np.where(gay, np.where(sp_sex == "M", "F", "M"), sp_sex)
        sp_age = P["age"][left] + np.where(sp_sex == "F", -1.2, 1.2) + rng.normal(0, 1.5, n_sp)
        act = P["activity"][left].astype(int) - 1
        act = np.where((rng.random(n_sp) < 0.2) & (act >= 0), rng.integers(0, 3, n_sp), act)
        spouses = sy.people(P, "spouse", n_sp, "none", extra={
            "sex": sp_sex, "age": np.clip(sp_age, 18.5, 45), "rel": np.full(n_sp, "married"),
            "lds": (P["lds_member"][left] & (rng.random(n_sp) < 0.96)).astype(int), "activity": np.maximum(act, 0)})
        P.cols["enrolled"][spouses] = False
        P.cols["class_standing"][spouses] = 0
        married_pairs += list(zip(left.tolist(), spouses.tolist()))
    for status in ("engaged", "dating"):
        pp = pair_couples(P, young, rng, status)
        pairs += [(a, b, status) for a, b in pp]
        done = np.zeros(P.n, bool)
        for a, b in pp:
            done[a] = done[b] = True
        orphan = young[(P["rel_status"][young] == P.code("rel_status", status)) & ~done[young]]
        P.cols["rel_status"][orphan] = P.code("rel_status", "single")
    pairs += [(a, b, "married") for a, b in married_pairs]
    met = load_priors()["tables"]["met_spouse"]
    met_ctx = {"Dating app": "app", "Same ward": "ward", "Set up by friend/family": "gathering",
               "Grew up together": "family", "Same Classes": "class", "Other": "venue"}
    met_names = list(met)
    met_p = np.array([met[k] for k in met_names])
    met_p /= met_p.sum()
    keys, init_rows = [], []
    for a, b, status in pairs:
        P.cols["partner_id"][a], P.cols["partner_id"][b] = b, a
        months = {"dating": rng.gamma(2.0, 2.5), "engaged": rng.uniform(5, 12), "married": rng.uniform(4, 60)}[status]
        start = day0 - int(months * 30.4)
        P.cols["rel_start_day"][[a, b]] = start
        if status in ("engaged", "married"):
            eng = day0 - int(rng.uniform(0, 3.5) * 30.4) if status == "engaged" else start + int(rng.uniform(3, 10) * 30.4)
            P.cols["engaged_day"][[a, b]] = eng
        if status == "married":
            wed = start + int(rng.uniform(7, 14) * 30.4)
            wed = min(wed, day0 - 10)
            P.cols["married_day"][[a, b]] = wed
            for x in (a, b):
                P.cols["age_at_marriage"][x] = P.cols["age"][x] - (day0 - wed) / 365.25
        keys.append((a, b))
        ctx = met_ctx[met_names[rng.choice(len(met_names), p=met_p)]] if status == "married" else rng.choice(
            ["ward", "class", "gathering", "app", "fhe", "venue"], p=[0.25, 0.15, 0.25, 0.15, 0.1, 0.1])
        init_rows.append((status, start, ctx))
    if keys:
        ka = np.array([k[0] for k in keys])
        kb = np.array([k[1] for k in keys])
        ek = EdgeStore.make_keys(ka, kb)
        status_arr = np.array([r[0] for r in init_rows])
        flags = np.where(status_arr == "married", Tie.SPOUSE | Tie.ROMANTIC | Tie.DATED | Tie.KISSED,
                         Tie.ROMANTIC | Tie.DATED | Tie.KISSED).astype(np.uint32)
        flags |= Tie.PREEXISTING
        start_arr = np.array([r[1] for r in init_rows])
        dur = np.maximum(day0 - start_arr, 1)
        E0 = EdgeStore(capacity=max(1 << 16, int(P.n * 12)))
        E0._insert(np.unique(ek), {})
        idx = E0.find(ek)
        E0.cols["flags"][idx] = flags
        E0.cols["stage"][idx] = 4
        E0.cols["liking"][idx] = np.clip(rng.normal(0.75, 0.1, len(idx)), 0, 1)
        E0.cols["closeness"][idx] = np.clip(rng.normal(0.8, 0.08, len(idx)), 0, 1)
        E0.cols["trust"][idx] = np.clip(rng.normal(0.75, 0.1, len(idx)), 0, 1)
        E0.cols["att_lh"][idx] = np.clip(rng.normal(0.7, 0.12, len(idx)), -1, 1)
        E0.cols["att_hl"][idx] = np.clip(rng.normal(0.7, 0.12, len(idx)), -1, 1)
        E0.cols["hours"][idx] = dur * 2.5
        E0.cols["hours_leisure"][idx] = dur * 2.0
        E0.cols["n_inter"][idx] = (dur * 2).astype(np.int32)
        E0.cols["first_day"][idx] = start_arr - rng.integers(7, 120, len(idx))
        E0.cols["last_day"][idx] = day0 - 1
        E0.cols["dates"][idx] = np.minimum(dur // 4, 2000).astype(np.int16)
        E0.cols["origin_ctx"][idx] = np.array([CTX_ID[r[2]] for r in init_rows], dtype=np.uint8)
        E0.cols["chemistry"][idx] = np.clip(rng.normal(1.0, 0.5, len(idx)), -3, 3)
    else:
        E0 = EdgeStore(capacity=max(1 << 16, int(P.n * 12)))
    if verbose:
        print(f"  couples {len(pairs)} ({time.time() - t0:.1f}s)")

    # ---- housing
    units, cx = build_units(scale, rng)
    H = HousingAssigner(P, units, rng)
    unit_of = np.full(P.n, -1, dtype=np.int64)
    married = P.is_("rel_status", "married")
    school = P["school"]
    role = P["role"]
    is_role = lambda *names: np.isin(role, [P.code("role", x) for x in names])  # noqa: E731
    anchor_of = lambda i: BYU if school[i] == P.code("school", "BYU") else UVU  # noqa: E731
    # married couples (both agents) -> married housing near their school
    couples = [(a, b) for a, b, st in pairs if st == "married"]
    for anchor_school, anchor in ((1, BYU), (2, UVU), (0, BYU)):
        grp = [np.array([a, b]) for a, b in couples
               if (school[a] if school[a] else school[b]) == anchor_school]
        if not grp:
            continue
        cand = (units.unit_type == 3) | ((units.unit_type == 2) & (units.capacity <= 4)) | \
               ((units.unit_type == 1) & ~units.contracted)
        if anchor_school == 1:
            out = H.place_groups(grp, units.married_only, anchor, 1.5)
            rest = [g for g, u in zip(grp, out) if u < 0]
            for g, u in zip(grp, out):
                if u >= 0:
                    unit_of[g] = u
            grp = rest
        out = H.place_groups(grp, cand & ~units.married_only, anchor, 2.5 if anchor_school else 4.0)
        for g, u in zip(grp, out):
            unit_of[g] = u
    # faculty/staff/community (and their unmodelled families) -> family homes
    fam_people = np.where(is_role("faculty", "staff", "community") | (married & (unit_of < 0)))[0]
    out = H.place_groups([np.array([i]) for i in fam_people], units.unit_type == 4, BYU, 6.0)
    unit_of[fam_people] = out
    for i in fam_people:
        if unit_of[i] >= 0:
            H.free[unit_of[i]] = 0  # whole home
    # living with parents (local families)
    single = ~married
    byu_stu = is_role("byu_student") & single
    uvu_stu = is_role("uvu_student") & single
    ya_s = is_role("young_adult") & single
    wp = np.zeros(P.n, bool)
    wp |= byu_stu & P["family_local"] & (rng.random(P.n) < load_world_cfg()["population"]["byu"]["with_parents_share"] / 0.45)
    wp |= uvu_stu & (P["family_local"] | P.internal["live_parents_pref"][: P.n]) & (rng.random(P.n) < 0.62)
    wp |= ya_s & P["family_local"] & (rng.random(P.n) < 0.4)
    wp_ids = np.where(wp)[0]
    out = H.place_groups([np.array([i]) for i in wp_ids], units.unit_type == 4, UVU, 8.0)
    unit_of[wp_ids] = out
    for i in wp_ids:
        if unit_of[i] >= 0:
            H.free[unit_of[i]] = 0
    # BYU single students: freshmen -> halls; others -> contracted apartments
    fresh = P.is_("class_standing", "freshman")
    for sex_label, sex_code in (("F", 1), ("M", 2)):
        sx = P.is_("sex", sex_label)
        f_ids = np.where(byu_stu & fresh & sx & (unit_of < 0))[0]
        f_ids = f_ids[rng.random(len(f_ids)) < 0.75]
        dorm = units.unit_type == 0
        unit_of[f_ids] = H.fill_beds(f_ids, dorm, BYU, 1.0, sex_code)
        rest = np.where(byu_stu & sx & (unit_of < 0))[0]
        key = (P["activity"][rest] * 10 + P["class_standing"][rest]).astype(float)
        unit_of[rest] = H.fill_beds(rest, units.contracted & (units.unit_type != 0), BYU, 0.9, sex_code, key)
        rest = np.where(byu_stu & sx & (unit_of < 0))[0]
        unit_of[rest] = H.fill_beds(rest, (units.unit_type == 1) | (units.unit_type == 2), BYU, 1.2, sex_code, key[:0] if False else None)
        # UVU singles and young adults: non-contracted apartments, house shares
        for grp_mask, anchor, lam in ((uvu_stu, UVU, 1.6), (ya_s, (-111.68, 40.26), 3.0)):
            ids_ = np.where(grp_mask & sx & (unit_of < 0))[0]
            apt_first = rng.random(len(ids_)) < 0.65
            for sub, types in ((ids_[apt_first], [1, 2]), (ids_[~apt_first], [1, 2, 4])):
                key = (3 - P["activity"][sub]).astype(float)
                unit_of[sub] = H.fill_beds(sub, ~units.contracted & np.isin(units.unit_type, types) & ~units.married_only,
                                           anchor, lam, sex_code, key)
            ids_ = np.where(grp_mask & sx & (unit_of < 0))[0]
            unit_of[ids_] = H.fill_beds(ids_, ~units.contracted & np.isin(units.unit_type, [1, 2, 4]) & ~units.married_only,
                                        anchor, lam * 2, sex_code)
    # leftovers (stock exhausted): any non-married unit
    left = np.where(unit_of < 0)[0]
    for sex_label, sex_code in (("F", 1), ("M", 2)):
        ids_ = left[P["sex"][left] == P.code("sex", sex_label)]
        unit_of[ids_] = H.fill_beds(ids_, ~units.married_only, BYU, 5.0, sex_code)
    if verbose:
        print(f"  housing placed {np.mean(unit_of >= 0):.3f} ({time.time() - t0:.1f}s)")
    occupants = np.bincount(unit_of[unit_of >= 0], minlength=len(units))
    # rents: per-bed for student shares, whole-unit for couples/families
    d_byu = km(units.lon, units.lat, *BYU)
    per_bed = np.clip(rng.lognormal(np.log(480), 0.18, len(units)) * (1 + 0.35 * (units.quality - 0.5)) * (1 + 0.12 * (d_byu < 1.2)), 280, 1100)
    unit_rent = np.where(units.unit_type == 0, per_bed * units.capacity * 0.95,
                         np.where(units.unit_type == 3, rng.normal(800, 80, len(units)),
                                  np.where(units.unit_type == 4, rng.normal(1900, 350, len(units)), per_bed * units.capacity)))
    married_unit = np.zeros(len(units), bool)
    married_unit[unit_of[(unit_of >= 0) & married]] = True
    unit_rent = np.where(married_unit & (units.unit_type != 3), np.clip(rng.normal(1250, 220, len(units)) * (0.85 + 0.3 * units.quality), 750, 2400), unit_rent)
    units.rent_total = unit_rent.astype(np.float32)
    units.occupants = occupants
    has = unit_of >= 0
    u = np.maximum(unit_of, 0)
    P["unit_id"] = np.where(has, unit_of, -1)
    P["household_id"] = np.where(has, unit_of, -1)
    jitter = lambda k: rng.normal(0, 0.00012, k)  # noqa: E731
    P["home_lon"] = np.where(has, units.lon[u] + jitter(P.n), BYU[0] + rng.normal(0, 0.03, P.n))
    P["home_lat"] = np.where(has, units.lat[u] + jitter(P.n), BYU[1] + rng.normal(0, 0.03, P.n))
    P["complex_id"] = np.where(has, units.complex_id[u], -1)
    P["city"] = np.where(has, units.city[u], 2).astype(np.uint8)
    adults = np.maximum(occupants[u], 1)
    share = np.where(units.unit_type[u] == 0, unit_rent[u] / units.capacity[u], unit_rent[u] / adults)
    share = np.where(married & has, unit_rent[u] / 2, share)
    is_home_with_parents = has & wp & (units.unit_type[u] == 4) & ~married
    share = np.where(is_home_with_parents, 0, share)
    P["rent"] = np.where(has, share, 0).astype(np.float32)
    living = np.select(
        [units.unit_type[u] == 0, is_home_with_parents, (units.unit_type[u] == 3) | (married & has & (units.unit_type[u] != 4)),
         has & (units.unit_type[u] == 4) & ~is_home_with_parents & (married | is_role("faculty", "staff", "community")),
         has & units.contracted[u], has & np.isin(units.unit_type[u], [2, 4])],
        ["dorm", "with_parents", "married_housing", "family_home", "contracted", "house_share"], "apartment")
    P["living"] = P.codes("living", living)
    anchor_lon = np.where(school == P.code("school", "UVU"), UVU[0], BYU[0])
    anchor_lat = np.where(school == P.code("school", "UVU"), UVU[1], BYU[1])
    dist = km(P["home_lon"], P["home_lat"], anchor_lon, anchor_lat)
    P["dist_campus_km"] = dist
    P["commute_min"] = np.where(dist < 1.5, dist * 13, np.where(P["owns_car"], 6 + dist * 2.4, 10 + dist * 4.5))
    # family homes: one household per unit for faculty etc.

    # ---- wards & FHE
    mh = pl.read_parquet(GEO / "meetinghouses.parquet")
    wards = build_wards(P, units, mh["lon"].to_numpy(), mh["lat"].to_numpy(), rng, unit_of)
    fhe = build_fhe_groups(P, unit_of, wards["kind"], rng)
    P.add_internal("fhe_group", np.int32, -1)
    P.internal["fhe_group"][: P.n] = fhe
    # bishops: older active married men (faculty/community) assigned to wards
    cand = np.where(is_role("faculty", "community", "staff") & P.is_("sex", "M") & P.is_("activity", "active") & married)[0]
    rng.shuffle(cand)
    nb = min(len(cand), len(wards["kind"]))
    wards["bishop"] = np.full(len(wards["kind"]), -1, dtype=np.int64)
    wards["bishop"][:nb] = cand[:nb]
    if verbose:
        print(f"  wards {len(wards['kind'])} fhe groups {fhe.max() + 1} ({time.time() - t0:.1f}s)")

    # ---- workplaces
    venues = pl.read_parquet(GEO / "venues.parquet")
    employers = build_workplaces(P, venues, rng, scale)

    # ---- seed network
    E = seed_network(P, E0, unit_of, rng, day0)
    # ward co-membership flag on existing ties
    lo, hi = E.endpoints()
    w = P["ward_id"]
    same_ward = (w[lo] >= 0) & (w[lo] == w[hi])
    E.cols["flags"][: E.n] |= np.where(same_ward, Tie.WARD, 0).astype(np.uint32)
    if verbose:
        print(f"  edges {E.n} ({time.time() - t0:.1f}s)")

    params = ParamSet(reg, overrides)
    world = World(reg=reg, params=params, cfg=cfg, scale=scale, seed=seed,
                  start_date=dt.date.fromisoformat(cfg["start_date"]), P=P, E=E, units=units, complexes=cx,
                  wards=wards, employers=employers, venues=venues, meetinghouses=mh)
    world.meta["build_seconds"] = time.time() - t0
    world.meta["synthesizer"] = sy
    return world


if __name__ == "__main__":
    import sys
    w = build_world(float(sys.argv[1]) if len(sys.argv) > 1 else 0.3, verbose=True)
    print("agents", w.P.n, "edges", w.E.n, "seconds", round(w.meta["build_seconds"], 1))

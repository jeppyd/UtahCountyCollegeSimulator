"""Couples, housing, wards, workplaces and the seed social network."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

from ..engine.state import CTX_ID, EdgeStore, PersonTable, Tie

GEO = Path(__file__).resolve().parents[1] / "geo" / "data"
BYU = (-111.6493, 40.2500)
UVU = (-111.7129, 40.2773)
KX = 111.32 * np.cos(np.radians(40.26))
KY = 111.32


def km(lon1, lat1, lon2, lat2):
    return np.hypot((np.asarray(lon1) - lon2) * KX, (np.asarray(lat1) - lat2) * KY)


@dataclass
class Units:
    lon: np.ndarray
    lat: np.ndarray
    capacity: np.ndarray
    rent_total: np.ndarray
    contracted: np.ndarray
    sex_restriction: np.ndarray     # 0 none, 1 F, 2 M
    married_only: np.ndarray
    unit_type: np.ndarray           # 0 dorm, 1 apartment, 2 house_room, 3 married_apartment, 4 family_home
    complex_id: np.ndarray
    city: np.ndarray                # 0 Provo, 1 Orem, 2 other
    quality: np.ndarray
    kind_src: np.ndarray            # dwelling kind code: 0 house 1 small_multi 2 apartment 3 mobile 4 dorm 5 married
    occupants: list = field(default_factory=list)

    def __len__(self):
        return len(self.lon)


UNIT_TYPES = ["dorm", "apartment", "house_room", "married_apartment", "family_home"]


def build_units(scale: float, rng: np.random.Generator) -> tuple[Units, pl.DataFrame]:
    dw = pl.read_parquet(GEO / "dwellings.parquet")
    cx = pl.read_parquet(GEO / "complexes.parquet")
    kind_code = {"house": 0, "small_multi": 1, "apartment": 2, "mobile_home": 3}
    k = dw["kind"].replace_strict(kind_code, return_dtype=pl.Int8).to_numpy()
    d_byu = dw["dist_byu"].to_numpy()
    d_uvu = dw["dist_uvu"].to_numpy()
    student_zone = (d_byu < 2.8) | (d_uvu < 2.5)
    # Thinning keeps spatial density patterns at reduced scale.
    q = np.where(student_zone & (k >= 1), min(1.0, scale * 1.15), min(1.0, scale * 0.45))
    keep = rng.random(len(k)) < q
    dw = dw.filter(pl.Series(keep))
    k = k[keep]
    cid = dw["complex_id"].fill_null(-1).to_numpy().astype(np.int32)
    contracted_cx = cx["contracted"].to_numpy()
    married_cx = cx["married_only"].to_numpy()
    lon = dw["lon"].to_numpy().astype(np.float64)
    lat = dw["lat"].to_numpy().astype(np.float64)
    contracted = np.where(cid >= 0, contracted_cx[np.maximum(cid, 0)], False)
    value = dw["value_per_unit"].fill_null(np.nan).to_numpy()
    qv = np.where(np.isfinite(value), value, np.nanmedian(value))
    quality = (np.argsort(np.argsort(qv)) / max(1, len(qv) - 1)).astype(np.float32)
    city = dw["city"].replace_strict({"Provo": 0, "Orem": 1}, default=2, return_dtype=pl.Int8).to_numpy()
    n = len(lon)
    cap = np.where(k == 2, np.where(contracted, rng.choice([4, 6], n, p=[0.45, 0.55]), rng.choice([2, 3, 4], n, p=[0.3, 0.35, 0.35])),
                   np.where(k == 1, rng.choice([2, 3, 4, 5], n), np.where(k == 0, rng.choice([4, 5, 6, 7, 8], n), 3)))
    utype = np.where(k == 2, 1, np.where(k == 1, 2, np.where(k == 0, 4, 4)))
    # BYU halls & married complexes from the special complex rows
    extra = []
    for row in cx.filter(pl.col("kind").is_in(["byu_dorm", "married"])).iter_rows(named=True):
        n_units = max(1, int(round(row["units"] * scale)))
        bpu = 2 if row["name"].startswith("Helaman") else (6 if row["name"].startswith("Heritage") else 2)
        ang = rng.uniform(0, 2 * np.pi, n_units)
        rad = np.sqrt(rng.uniform(0, 1, n_units)) * 0.0022
        for i in range(n_units):
            extra.append((row["lon"] + rad[i] * np.cos(ang[i]) * 1.3, row["lat"] + rad[i] * np.sin(ang[i]),
                          bpu if row["kind"] == "byu_dorm" else 4, row["kind"] == "byu_dorm", row["kind"] == "married",
                          0 if row["kind"] == "byu_dorm" else 3, row["complex_id"], 4 if row["kind"] == "byu_dorm" else 5))
    if extra:
        ex = np.array(extra, dtype=object)
        lon = np.concatenate([lon, ex[:, 0].astype(float)])
        lat = np.concatenate([lat, ex[:, 1].astype(float)])
        cap = np.concatenate([cap, ex[:, 2].astype(int)])
        contracted = np.concatenate([contracted, ex[:, 3].astype(bool)])
        married_only = np.concatenate([np.zeros(n, bool), ex[:, 4].astype(bool)])
        utype = np.concatenate([utype, ex[:, 5].astype(int)])
        cid = np.concatenate([cid, ex[:, 6].astype(np.int32)])
        k = np.concatenate([k, ex[:, 7].astype(int)])
        quality = np.concatenate([quality, np.full(len(ex), 0.45, np.float32)])
        city = np.concatenate([city, np.zeros(len(ex), np.int8)])
    else:
        married_only = np.zeros(n, bool)
    m = len(lon)
    units = Units(lon=lon, lat=lat, capacity=cap.astype(np.uint8), rent_total=np.zeros(m, np.float32),
                  contracted=contracted.astype(bool), sex_restriction=np.zeros(m, np.uint8),
                  married_only=married_only, unit_type=utype.astype(np.uint8), complex_id=cid.astype(np.int32),
                  city=city.astype(np.int8), quality=quality, kind_src=k.astype(np.int8))
    return units, cx


class HousingAssigner:
    """Initial placement. Utility ∝ −distance to anchor + noise, with hard constraints
    (BYU contracted housing for single undergrads, single-sex units, married-only housing)."""

    def __init__(self, P: PersonTable, units: Units, rng):
        self.P, self.U, self.rng = P, units, rng
        self.free = units.capacity.astype(np.int32).copy()
        self.hh_of_unit = np.full(len(units), -1, dtype=np.int64)
        self.used = np.zeros(len(units), bool)

    def _score(self, cand, anchor, lam):
        d = km(self.U.lon[cand], self.U.lat[cand], *anchor)
        return -d / lam + self.rng.gumbel(size=len(cand)), d

    def place_groups(self, groups: list[np.ndarray], cand_mask: np.ndarray, anchor, lam: float,
                     sex_code: int | None = None, whole_unit: bool = True):
        """Assign each group (household / roommate set) to one unit. Returns unit per group."""
        cand = np.where(cand_mask & ~self.used)[0]
        out = np.full(len(groups), -1, dtype=np.int64)
        if len(cand) == 0:
            return out
        score, _ = self._score(cand, anchor, lam)
        order = cand[np.argsort(-score)]
        caps = self.free[order]
        sizes = np.array([len(g) for g in groups])
        # greedy: walk units in preference order; give each the next group that fits
        gi = 0
        gorder = np.argsort(-sizes, kind="stable") if not whole_unit else np.arange(len(groups))
        ptr = 0
        for u, c in zip(order, caps):
            if gi >= len(gorder):
                break
            g = gorder[gi]
            if sizes[g] <= c:
                out[g] = u
                self.used[u] = True
                self.free[u] -= sizes[g]
                if sex_code is not None:
                    self.U.sex_restriction[u] = sex_code
                gi += 1
            ptr += 1
        return out

    def fill_beds(self, people: np.ndarray, cand_mask: np.ndarray, anchor, lam: float, sex_code: int,
                  sort_key: np.ndarray | None = None) -> np.ndarray:
        """Fill single-sex units bed by bed with similar people (roommate homophily)."""
        unit_of = np.full(len(people), -1, dtype=np.int64)
        if len(people) == 0:
            return unit_of
        cand = np.where(cand_mask & ~self.used & ((self.U.sex_restriction == 0) | (self.U.sex_restriction == sex_code)))[0]
        if len(cand) == 0:
            return unit_of
        score, _ = self._score(cand, anchor, lam)
        order = cand[np.argsort(-score)]
        porder = np.argsort(sort_key + self.rng.uniform(0, 0.3, len(people))) if sort_key is not None else self.rng.permutation(len(people))
        pi = 0
        for u in order:
            c = int(self.free[u])
            if c <= 0:
                continue
            take = porder[pi: pi + c]
            unit_of[take] = u
            self.free[u] -= len(take)
            self.used[u] = True
            self.U.sex_restriction[u] = sex_code
            pi += len(take)
            if pi >= len(people):
                break
        return unit_of


def pair_couples(P: PersonTable, ids: np.ndarray, rng, status: str) -> list[tuple[int, int]]:
    """Pair agents in `status` (married/engaged/dating) among themselves (compatible orientation, age, school)."""
    sel = ids[P["rel_status"][ids] == P.code("rel_status", status)]
    sex = P["sex"][sel]
    orient = P["orientation"][sel]
    gay = orient == P.code("orientation", "gay")
    pairs = []
    used = np.zeros(P.n, bool)
    # opposite-sex couples
    men = sel[(sex == P.code("sex", "M")) & ~gay]
    women = sel[(sex == P.code("sex", "F")) & ~gay]
    key_m = P["age"][men] - 1.5 + 0.8 * rng.standard_normal(len(men)) + 10 * P["school"][men] + 3 * P["activity"][men]
    key_w = P["age"][women] + 0.8 * rng.standard_normal(len(women)) + 10 * P["school"][women] + 3 * P["activity"][women]
    men = men[np.argsort(key_m)]
    women = women[np.argsort(key_w)]
    # rank-match within the overlapping quantiles
    k = min(len(men), len(women))
    if k:
        im = np.round(np.linspace(0, len(men) - 1, k)).astype(int)
        iw = np.round(np.linspace(0, len(women) - 1, k)).astype(int)
        for a, b in zip(men[im], women[iw]):
            if not used[a] and not used[b]:
                pairs.append((int(a), int(b)))
                used[a] = used[b] = True
    # same-sex couples
    for s in ("M", "F"):
        g = sel[gay & (sex == P.code("sex", s))]
        g = g[~used[g]]
        g = rng.permutation(g)
        for i in range(0, len(g) - 1, 2):
            pairs.append((int(g[i]), int(g[i + 1])))
            used[g[i]] = used[g[i + 1]] = True
    return pairs


def build_wards(P: PersonTable, units: Units, meet_lon, meet_lat, rng, unit_of: np.ndarray):
    """Assign congregations. Returns ward table arrays and sets P['ward_id']."""
    n = P.n
    lds = P["lds_member"]
    married = P.is_("rel_status", "married")
    school = P["school"]
    role = P["role"]
    student = np.isin(role, [P.code("role", "byu_student"), P.code("role", "uvu_student")])
    has_unit = unit_of >= 0
    hlon = np.where(has_unit, units.lon[np.maximum(unit_of, 0)], P["home_lon"])
    hlat = np.where(has_unit, units.lat[np.maximum(unit_of, 0)], P["home_lat"])
    ward_kind, ward_lon, ward_lat, ward_mh = [], [], [], []
    ward_of = np.full(n, -1, dtype=np.int32)
    young = P["age"] < 31

    def chunk(mask, size, kind, campus_meet):
        idx = np.where(mask)[0]
        if len(idx) == 0:
            return
        # order along a space-filling-ish key so wards are geographically contiguous;
        # keep members of the same unit/complex together
        key = (np.round(hlat[idx] * 400) * 1000 + np.round(hlon[idx] * 400)) * 1e7 + unit_of[idx]
        idx = idx[np.argsort(key, kind="stable")]
        k = max(1, int(round(len(idx) / size)))
        bounds = np.linspace(0, len(idx), k + 1).astype(int)
        for b0, b1 in zip(bounds[:-1], bounds[1:]):
            members = idx[b0:b1]
            if len(members) == 0:
                continue
            wid = len(ward_kind)
            ward_of[members] = wid
            ward_kind.append(kind)
            cx, cy = float(np.mean(hlon[members])), float(np.mean(hlat[members]))
            if campus_meet:
                lx, ly = BYU[0] + rng.normal(0, 0.0025), BYU[1] + rng.normal(0, 0.0025)
                mh = -1
            else:
                d = km(meet_lon, meet_lat, cx, cy)
                mh = int(np.argmin(d))
                lx, ly = float(meet_lon[mh]), float(meet_lat[mh])
            ward_lon.append(lx)
            ward_lat.append(ly)
            ward_mh.append(mh)

    byu_single = lds & ~married & (school == P.code("school", "BYU")) & student
    chunk(byu_single, 180, "byu_ysa", True)
    ysa = lds & ~married & young & ~byu_single & (ward_of < 0)
    chunk(ysa, 150, "ysa", False)
    mstud = lds & married & young & (ward_of < 0)
    chunk(mstud, 170, "married_student", False)
    fam = lds & (ward_of < 0)
    chunk(fam, 220, "family", False)
    P["ward_id"] = ward_of
    return {"kind": np.array(ward_kind), "lon": np.array(ward_lon), "lat": np.array(ward_lat),
            "meetinghouse": np.array(ward_mh)}


def build_fhe_groups(P: PersonTable, unit_of: np.ndarray, ward_kind: np.ndarray, rng) -> np.ndarray:
    """FHE groups in YSA wards: pair a men's apartment with a women's apartment (BYU tradition)."""
    fhe = np.full(P.n, -1, dtype=np.int32)
    wid = P["ward_id"]
    gid = 0
    for w in np.where(np.isin(ward_kind, ["byu_ysa", "ysa"]))[0]:
        members = np.where(wid == w)[0]
        if len(members) == 0:
            continue
        units_m = {}
        for i in members:
            units_m.setdefault(int(unit_of[i]) if unit_of[i] >= 0 else -int(i) - 10, []).append(i)
        groups_m, groups_f = [], []
        for u, mem in units_m.items():
            (groups_m if P["sex"][mem[0]] == P.code("sex", "M") else groups_f).append(mem)
        rng.shuffle(groups_m)
        rng.shuffle(groups_f)
        for a, b in zip(groups_m, groups_f):
            fhe[np.array(a + b)] = gid
            gid += 1
        for rest in groups_m[len(groups_f):] + groups_f[len(groups_m):]:
            fhe[np.array(rest)] = gid
            gid += 1
    return fhe


JOB_TYPES = ["none", "campus", "food_retail", "tech", "health", "office", "sales", "trades", "teaching", "faculty", "staff"]


def build_workplaces(P: PersonTable, venues: pl.DataFrame, rng, scale: float):
    """Create employers (department/store-sized work groups) and assign employed agents."""
    sites = pl.read_parquet(GEO / "work_sites.parquet")
    emp_lon, emp_lat, emp_type, emp_name = [], [], [], []
    job = np.zeros(P.n, dtype=np.uint8)
    employer = np.full(P.n, -1, dtype=np.int32)
    role = P["role"]
    employed = P["employed"]
    r = lambda name: P.code("role", name)  # noqa: E731

    def new_emp(lon, lat, t, name):
        emp_lon.append(lon)
        emp_lat.append(lat)
        emp_type.append(t)
        emp_name.append(name)
        return len(emp_lon) - 1

    def assign(people, jt, size, site_fn, name_fn):
        people = rng.permutation(people)
        for i in range(0, len(people), size):
            grp = people[i: i + size]
            lon, lat = site_fn()
            e = new_emp(lon, lat, jt, name_fn(len(emp_lon)))
            employer[grp] = e
            job[grp] = JOB_TYPES.index(jt)

    rest_v = venues.filter(pl.col("vtype").is_in(["restaurant", "cafe", "soda_shop", "dessert", "cinema_theatre", "gym"]))
    vlon, vlat, vname = rest_v["lon"].to_numpy(), rest_v["lat"].to_numpy(), rest_v["name"].to_list()
    slon, slat = sites["lon"].to_numpy(), sites["lat"].to_numpy()
    vi = iter(rng.permutation(len(vlon)).tolist() * 50)
    si = iter(rng.permutation(len(slon)).tolist() * 50)

    def campus(c):
        return lambda: (c[0] + rng.normal(0, 0.003), c[1] + rng.normal(0, 0.003))

    def venue_site():
        j = next(vi)
        return float(vlon[j]), float(vlat[j])

    def office_site():
        j = next(si)
        return float(slon[j]), float(slat[j])

    byu = (role == r("byu_student")) & employed
    uvu = (role == r("uvu_student")) & employed
    stu = np.where(byu | uvu)[0]
    u = rng.random(len(stu))
    is_byu = np.isin(stu, np.where(byu)[0])
    campus_job = np.where(is_byu, u < 0.48, u < 0.18)
    assign(stu[campus_job & is_byu], "campus", 18, campus(BYU), lambda k: f"BYU campus dept {k}")
    assign(stu[campus_job & ~is_byu], "campus", 15, campus(UVU), lambda k: f"UVU campus dept {k}")
    rest = stu[~campus_job]
    u2 = rng.random(len(rest))
    assign(rest[u2 < 0.45], "food_retail", 12, venue_site, lambda k: "")
    assign(rest[(u2 >= 0.45) & (u2 < 0.68)], "tech", 20, office_site, lambda k: f"Tech/office {k}")
    assign(rest[(u2 >= 0.68) & (u2 < 0.80)], "health", 15, office_site, lambda k: f"Clinic {k}")
    assign(rest[(u2 >= 0.80) & (u2 < 0.90)], "office", 12, office_site, lambda k: f"Office {k}")
    assign(rest[u2 >= 0.90], "sales", 15, office_site, lambda k: f"Sales floor {k}")
    other = np.where(employed & np.isin(role, [r("young_adult"), r("spouse"), r("community")]))[0]
    u3 = rng.random(len(other))
    assign(other[u3 < 0.25], "food_retail", 12, venue_site, lambda k: "")
    assign(other[(u3 >= 0.25) & (u3 < 0.55)], "tech", 25, office_site, lambda k: f"Tech/office {k}")
    assign(other[(u3 >= 0.55) & (u3 < 0.70)], "health", 15, office_site, lambda k: f"Clinic {k}")
    assign(other[(u3 >= 0.70) & (u3 < 0.85)], "office", 15, office_site, lambda k: f"Office {k}")
    assign(other[u3 >= 0.85], "trades", 12, office_site, lambda k: f"Trades crew {k}")
    fac = np.where(role == r("faculty"))[0]
    fac_school = P["school"][fac]
    assign(fac[fac_school == P.code("school", "BYU")], "faculty", 12, campus(BYU), lambda k: f"BYU department {k}")
    assign(fac[fac_school != P.code("school", "BYU")], "faculty", 12, campus(UVU), lambda k: f"UVU department {k}")
    staff = np.where(role == r("staff"))[0]
    assign(staff, "staff", 15, campus(BYU), lambda k: f"University office {k}")
    # restaurant employers take the venue's name
    names = np.array(emp_name, dtype=object)
    for e in np.where(names == "")[0]:
        d = km(vlon, vlat, emp_lon[e], emp_lat[e])
        names[e] = vname[int(np.argmin(d))]
    P["employer_id"] = employer
    P["job_type"] = job
    return {"lon": np.array(emp_lon), "lat": np.array(emp_lat), "type": np.array(emp_type), "name": names}


def seed_network(P: PersonTable, E: EdgeStore, unit_of: np.ndarray, rng, day0: int):
    """Pre-existing ties at simulation start (returning students arrive with friends).

    Ties are drawn from shared foci (unit, ward, school×area, origin) with a degree
    that rises with extraversion; strengths are drawn by stage. Freshmen arrive with
    few ties (mostly high-school friends who also came)."""
    n = P.n
    ids = np.arange(n)
    fresh = P.is_("class_standing", "freshman")
    E_ = P["extraversion"]
    mean_friends = np.where(fresh, 2.0, 9.0) * np.exp(0.25 * E_) * np.where(P["role"] >= P.code("role", "faculty"), 0.7, 1.0)
    k = rng.poisson(mean_friends)
    src = np.repeat(ids, k)
    # focus selection for each stub
    focus = rng.choice(4, len(src), p=[0.25, 0.30, 0.30, 0.15])
    dst = np.full(len(src), -1, dtype=np.int64)

    def pick_within(group_key, stubs):
        g = group_key[src[stubs]]
        order = np.argsort(group_key, kind="stable")
        sorted_keys = group_key[order]
        lo = np.searchsorted(sorted_keys, g, side="left")
        hi = np.searchsorted(sorted_keys, g, side="right")
        size = hi - lo
        ok = (size > 1) & (g >= 0)
        r_ = lo + (rng.random(len(stubs)) * np.maximum(size, 1)).astype(np.int64)
        out = np.where(ok, order[np.minimum(r_, len(order) - 1)], -1)
        return out

    complex_key = np.where(P["complex_id"] >= 0, P["complex_id"].astype(np.int64), -1)
    ward_key = P["ward_id"].astype(np.int64)
    sa_key = (P["school"].astype(np.int64) * 100 + P["study_area"]) * np.where(P["enrolled"], 1, -1)
    org_key = P["school"].astype(np.int64) * 10 + P["origin_region"]
    for f, key in enumerate([complex_key, ward_key, sa_key, org_key]):
        stubs = np.where(focus == f)[0]
        dst[stubs] = pick_within(key, stubs)
    ok = (dst >= 0) & (dst != src)
    src, dst = src[ok], dst[ok]
    # age-gap filter (friends usually close in age)
    ok = np.abs(P["age"][src] - P["age"][dst]) < 6
    src, dst = src[ok], dst[ok]
    keys = EdgeStore.make_keys(src, dst)
    keys = np.unique(keys)
    keys = keys[E.find(keys) < 0]  # partners/spouses already have their own tie
    m = len(keys)
    stage = rng.choice([2, 3, 4], m, p=[0.5, 0.35, 0.15]).astype(np.uint8)
    hours = np.select([stage == 2, stage == 3, stage == 4], [rng.uniform(30, 80, m), rng.uniform(80, 220, m), rng.uniform(220, 600, m)])
    first = day0 - rng.integers(60, 1500, m)
    init = {
        "stage": stage, "hours": hours, "hours_leisure": hours * 0.8, "liking": np.clip(0.25 + 0.15 * stage + rng.normal(0, 0.1, m), -1, 1),
        "closeness": np.clip(0.15 + 0.17 * (stage - 1) + rng.normal(0, 0.06, m), 0, 1),
        "trust": np.clip(0.3 + 0.12 * stage + rng.normal(0, 0.08, m), 0, 1), "n_inter": (hours * 1.5).astype(np.int32),
        "first_day": first.astype(np.int32), "last_day": (day0 - rng.integers(1, 30, m)).astype(np.int32),
        "flags": np.full(m, Tie.PREEXISTING, np.uint32), "origin_ctx": np.full(m, CTX_ID["preexisting"], np.uint8),
    }
    E._insert(keys, init)
    # Roommates & household members know each other
    occ = unit_of
    has = occ >= 0
    order = np.argsort(occ[has], kind="stable")
    members = np.where(has)[0][order]
    u_sorted = occ[members]
    starts = np.flatnonzero(np.r_[True, u_sorted[1:] != u_sorted[:-1]])
    ends = np.r_[starts[1:], len(u_sorted)]
    a_list, b_list = [], []
    for s0, e0 in zip(starts, ends):
        mem = members[s0:e0]
        if len(mem) < 2:
            continue
        for i in range(len(mem)):
            for j in range(i + 1, len(mem)):
                a_list.append(mem[i])
                b_list.append(mem[j])
    if a_list:
        rk = EdgeStore.make_keys(np.array(a_list), np.array(b_list))
        idx = E.upsert(rk)
        new_fresh = (E["first_day"][idx] == 0) & (E["n_inter"][idx] == 0)
        E.cols["flags"][idx] |= Tie.ROOMMATE
        E.cols["first_day"][idx] = np.where(new_fresh, day0 - rng.integers(0, 120, len(idx)), E["first_day"][idx])
        E.cols["last_day"][idx] = day0 - 1
        E.cols["hours"][idx] += np.where(new_fresh, rng.uniform(5, 60, len(idx)), 0)
        E.cols["hours_leisure"][idx] += np.where(new_fresh, rng.uniform(3, 40, len(idx)), 0)
        E.cols["n_inter"][idx] += np.where(new_fresh, rng.integers(5, 80, len(idx)), 0).astype(np.int32)
        E.cols["liking"][idx] = np.where(new_fresh, np.clip(rng.normal(0.2, 0.2, len(idx)), -0.6, 0.8), E["liking"][idx])
        E.cols["stage"][idx] = np.maximum(E["stage"][idx], 1)
        E.cols["origin_ctx"][idx] = np.where(new_fresh, CTX_ID["unit"], E["origin_ctx"][idx])
    return E

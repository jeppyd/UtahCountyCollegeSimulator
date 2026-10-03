"""Clubs, intramural teams and institute classes: small groups that meet weekly.

Shared foci are among the strongest drivers of tie formation (Feld 1981; Kossinets & Watts 2006):
a weekly club, an intramural team or an institute class puts the same 10-30 people together
week after week, so acquaintances can become friends (and sometimes dates). Membership is
chosen from traits (extraversion, fitness, religiosity, conscientiousness), refreshed each
semester with churn; meetings happen only while that school's term is in session.

Group locations are approximate: BYU intramurals at the Richards Building fields, UVU
intramurals at the Student Life & Wellness Center, institute classes at the Orem Institute
of Religion next to UVU, clubs on each campus.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

BYU = (-111.6493, 40.2500)
UVU = (-111.7129, 40.2773)
PLACES = {
    ("team", 1): ("BYU Intramurals (Richards Building fields)", -111.6553, 40.2493),
    ("team", 2): ("UVU Student Life & Wellness Center", -111.7156, 40.2794),
    ("institute", 2): ("Orem Institute of Religion (approx.)", -111.7165, 40.2765),
}
CLUBS = {
    1: ["Ballroom Dance Club", "Pre-Med Society", "Hiking & Backpacking Club", "Data Science Club", "Entrepreneurship Club",
        "Y-Serve volunteer group", "Spanish Conversation Club", "Women in STEM", "Chess Club", "Improv Comedy Troupe",
        "Pickleball Club", "Rock Climbing Club", "Film Society", "Photography Club", "Board Game Night",
        "Pre-Law Society", "Folk Dance Club", "Ski & Snowboard Club", "Investment Club", "Korean Culture Club",
        "Swing Dance Club", "Writing Circle", "Robotics Club", "Choir (University Chorale)", "Running Club"],
    2: ["Ballroom Dance Club", "Pre-Health Club", "Outdoor Adventure Club", "Esports Club", "Entrepreneurship Club",
        "Service Council", "Latinx Student Union", "Women in Tech", "Chess Club", "Theatre Club",
        "Pickleball Club", "Climbing Club", "Anime Club", "Photography Club", "Board Game Club",
        "Pre-Law Society", "Aviation Club", "Ski & Snowboard Club", "Finance Club", "Cybersecurity Club",
        "Latter-day Saint Student Association", "Creative Writing Club", "Robotics Club", "Concert Choir", "Running Club"],
}
# faith and secular student groups for non-members (illustrative names), tagged with the affiliation they serve
FAITH_CLUBS = {
    1: [("Interfaith Student Association", "*")],
    2: [("Catholic Newman Club", "Catholic"), ("Christian Fellowship", "Protestant"), ("Muslim Student Association", "Muslim"),
        ("Secular Student Alliance", "Nonreligious"), ("Interfaith Student Council", "*")],
}
SPORTS = ["basketball", "volleyball", "flag football", "soccer", "ultimate frisbee", "pickleball", "softball", "dodgeball"]
KIND_SIZE = {"club": 22, "team": 9, "institute": 24}
ATTEND = {"club": 0.62, "team": 0.78, "institute": 0.66}


class Groups:
    def __init__(self, sim):
        self.sim = sim

    # ------------------------------------------------------------------ setup
    def init(self):
        w = self.sim.w
        P = w.P
        P.add_internal("grp_checked", bool, False)
        first = not w.groups
        if first:
            self._build_table()
        self._index()
        if first:
            self.assign(np.where(P["present"])[0])

    def _build_table(self):
        w = self.sim.w
        P = w.P
        rng = np.random.default_rng([w.seed, 707])
        enrolled = P["enrolled"]
        rows = []

        def add(kind, school, name, lon, lat, faith=""):
            # meets Tue-Thu (Monday is family home evening); clubs and institute some afternoons
            wd = int(rng.integers(1, 4))
            block = 2 if kind == "team" or rng.random() < 0.6 else 1
            rows.append((kind, school, name, lon, lat, wd, block, faith))

        for s, (cx, cy) in ((1, BYU), (2, UVU)):
            n_stu = int((enrolled & (P["school"] == s)).sum())
            names = CLUBS[s]
            n_clubs = max(6, int(round(n_stu * 0.28 / KIND_SIZE["club"])))
            for k in range(n_clubs):
                nm = names[k % len(names)] + ("" if k < len(names) else f" · section {k // len(names) + 1}")
                add("club", s, nm, cx + rng.normal(0, 0.0025), cy + rng.normal(0, 0.002))
            for nm, faith in FAITH_CLUBS[s]:
                add("club", s, nm, cx + rng.normal(0, 0.0025), cy + rng.normal(0, 0.002), faith)
            share = 0.20 if s == 1 else 0.10
            n_teams = max(4, int(round(n_stu * share / KIND_SIZE["team"])))
            pname, px, py = PLACES[("team", s)]
            for k in range(n_teams):
                add("team", s, f"{'BYU' if s == 1 else 'UVU'} intramural {SPORTS[k % len(SPORTS)]} team {k // len(SPORTS) + 1}",
                    px + rng.normal(0, 0.0006), py + rng.normal(0, 0.0005))
        lds_ya = P["lds_member"] & P.is_("activity", "active") & ((P["school"] == 2) | P.is_("role", "young_adult"))
        n_inst = max(3, int(round(lds_ya.sum() * 0.3 / KIND_SIZE["institute"])))
        iname, ix, iy = PLACES[("institute", 2)]
        topics = ["Book of Mormon", "Eternal Family", "Jesus Christ and the Everlasting Gospel", "Foundations of the Restoration",
                  "New Testament", "Preparing for Marriage", "Doctrine & Covenants", "Teachings of the Living Prophets"]
        for k in range(n_inst):
            add("institute", 2, f"{topics[k % len(topics)]} (section {k // len(topics) + 1})", ix, iy)
        cols = list(zip(*rows))
        w.groups = {"kind": np.array(cols[0]), "school": np.array(cols[1], np.int8), "name": list(cols[2]),
                    "lon": np.array(cols[3]), "lat": np.array(cols[4]), "weekday": np.array(cols[5], np.int8),
                    "block": np.array(cols[6], np.int8), "faith": np.array(cols[7], dtype=object)}

    def _index(self):
        G = self.sim.w.groups
        faith = np.asarray(G.get("faith", np.full(len(G["kind"]), "", dtype=object)), dtype=object)
        self.by = {(k, s): np.where((G["kind"] == k) & (G["school"] == s) & (faith == ""))[0]
                   for k in ("club", "team", "institute") for s in (1, 2)}
        self.faith_clubs = [(int(g), faith[g], int(G["school"][g])) for g in np.where(faith != "")[0]]

    def assign(self, ids: np.ndarray):
        """Decide club/team/institute membership for `ids` (new arrivals, or everyone at the start)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        if len(ids) == 0:
            return
        rng = sim.streams.gen("groups_assign", w.day, int(ids[0]) % 991)
        z = sim.z
        E, C = z("extraversion")[ids], z("conscientiousness")[ids]
        stu = P["enrolled"][ids]
        sch = P["school"][ids].astype(int)
        married = P.is_("rel_status", "married")[ids]
        kids = P["children"][ids] > 0
        busy = np.clip(P["work_hours"][ids] / 40, 0, 1.5)
        p_club = expit(-1.2 + 0.45 * E + 0.3 * C - 0.6 * married - 0.8 * kids - 0.6 * busy) * stu
        p_team = expit(-1.9 + 0.35 * E + 0.35 * np.log1p(P["workouts_week"][ids]) - 0.7 * married - 0.8 * kids
                       + 0.4 * P.is_("sex", "M")[ids] - 0.5 * busy) * stu * np.where(sch == 1, 1.0, 0.55)
        act = P.is_("activity", "active")[ids]
        ya = P.is_("role", "young_adult")[ids] & ~married
        p_inst = np.where(P["lds_member"][ids] & ((stu & (sch == 2)) | ya),
                          np.where(act, 0.32, 0.06) * np.where(married, 0.5, 1.0), 0.0)
        for col, prob, kind in (("club_id", p_club, "club"), ("team_id", p_team, "team"), ("institute_class", p_inst, "institute")):
            join = rng.random(len(ids)) < prob
            out = np.full(len(ids), -1, np.int32)
            for s in (1, 2):
                pool = self.by[(kind, s if kind != "institute" else 2)]
                m = join & ((sch == s) if kind != "institute" else (s == 2))
                if m.any() and len(pool):
                    out[m] = rng.choice(pool, m.sum())
            P.cols[col][ids] = np.where(join, out, -1)
        # non-members: faith and secular student groups (matching tradition first, then interfaith)
        non = stu & ~P["lds_member"][ids]
        if non.any() and self.faith_clubs:
            cats = P.specs["affiliation"].categories
            aff = np.array([cats[int(a)] for a in P["affiliation"][ids]], dtype=object)
            orl = P["own_religiosity"][ids]
            u = rng.random(len(ids))
            for g, faith, s in self.faith_clubs:
                boost = 1.0 + 0.5 * w.env.get("interfaith_welcome", 0.0)
                if faith == "*":
                    m = non & (sch == s) & (u < 0.05 * boost)
                elif faith == "Nonreligious":
                    m = non & (sch == s) & (aff == faith) & (u < (0.12 + 0.2 * sim.z("openness")[ids].clip(0, 1)) * boost)
                else:
                    m = non & (sch == s) & (aff == faith) & (u < (0.15 + 0.4 * orl) * boost)
                P.cols["club_id"][ids[m]] = g
        self._count(ids)
        P.internal["grp_checked"][ids] = True

    def _count(self, ids):
        P = self.sim.w.P
        P.cols["n_groups"][ids] = ((P["club_id"][ids] >= 0).astype(np.uint8) + (P["team_id"][ids] >= 0)
                                   + (P["institute_class"][ids] >= 0))

    # ------------------------------------------------------------------ dynamics
    def daily(self):
        """Newcomers decide on joining; at each semester start, some members quit and others join."""
        sim, w = self.sim, self.sim.w
        P = w.P
        new = np.where(P["present"] & ~P.internal["grp_checked"][: P.n])[0]
        if len(new):
            self.assign(new)
        if w.day > 0 and (sim.cal.term_start("BYU", w.day) or sim.cal.term_start("UVU", w.day)):
            rng = sim.streams.gen("groups_churn", w.day)
            pres = np.where(P["present"])[0]
            redo = pres[rng.random(len(pres)) < 0.3]
            for col in ("club_id", "team_id", "institute_class"):
                P.cols[col][redo] = -1
            self.assign(redo)
        # people who leave school drop their campus groups
        gone = np.where(~P["enrolled"] & ((P["club_id"] >= 0) | (P["team_id"] >= 0)))[0]
        if len(gone):
            P.cols["club_id"][gone] = -1
            P.cols["team_id"][gone] = -1
            self._count(gone)

    def meeting(self, b: int, wd: int, free: np.ndarray, u: np.ndarray):
        """Members whose group meets now and who show up: (ids, kind_index, group_id)."""
        w = self.sim.w
        P, G, env = w.P, w.groups, w.env
        out = []
        for k, (col, kind) in enumerate((("team_id", "team"), ("club_id", "club"), ("institute_class", "institute"))):
            g = P[col]
            m = (g >= 0) & free
            if not m.any():
                out.append((np.empty(0, np.int64), np.empty(0, np.int64)))
                continue
            idx = np.where(m)[0]
            gi = g[idx]
            term = np.where(G["school"][gi] == 1, bool(env["term_BYU"]), bool(env["term_UVU"]))
            now = (G["weekday"][gi] == wd) & (G["block"][gi] == b) & term & (not env["holiday"])
            p = ATTEND[kind] * (1 - 0.5 * P["fatigue"][idx]) * (1 - 0.5 * P["depressive_episode"][idx]) * ~P["ill"][idx]
            go = now & (u[idx] < p)
            out.append((idx[go], gi[go].astype(np.int64)))
            free[idx[go]] = False
        return out

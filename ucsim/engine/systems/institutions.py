"""Institutions with constraints: organizations with capacity, budget, hours, eligibility, priorities and delays, that
run their own events and adapt.

Design notes (parameters in config/mechanisms/16_institutions.yaml; occasion kinds in config/occasions/40_institutions.yaml)
* One table of institutions: clubs, teams and institute classes (w.groups), wards, the two counseling centers, employers
  and apartment complexes; each row has capacity, budget, weekly hours, a priority rule and a response delay, and a
  weekly state (demand, served, waitlist, utilization) kept as history for the Institution tool.
* Clubs and teams hold a social every four weeks on their own night (an open occasion for members). When turnout stays
  low three socials running, the officers adapt — add food while the budget lasts, move to another night, or recruit —
  and when a social overflows its room they cap it. Each is an institution decision and an event.
* Wards: an activities committee plans a monthly activity (with food while the budget lasts) and a service project
  every quarter. Members who want to talk with their bishop (to repent, or about pornography) are seen that week —
  bishops make time for them (romance._confessions and intimacy ask `bishop_gate`); the meetings are counted.
  Afterwards (`counsel`): premarital sex means a few weeks without a temple recommend (often without the sacrament,
  and some stay away from church meanwhile); ongoing issues mean a follow-up about once a month.
* Counseling (BYU CAPS, UVU Student Health Services' counseling): enrolled students in a depressive episode or under
  heavy strain may seek help (decision `seek_counseling`); sessions per week are limited, the waitlist is ordered by
  crisis first and then by wait; people seen get weekly sessions for a few weeks (relief through the coping system);
  some give up waiting.
* Employers: schedule flexibility by kind of job (a shift can be swapped for an occasion: occasions asks
  `shift_flex`), and job openings by season (campus jobs at semester start, retail before Christmas; economy reads
  `openings`).
* Complexes: management runs a monthly resident event (free food) in larger complexes while the budget allows.
Capacities and budgets are mechanism parameters, so a What-if can change them like any other number.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..ledger import STATUS_ID, Table
from ..provenance import link
from ucsim.population.structure import ward_name

KINDS = ("club", "team", "institute", "ward", "counseling", "employer", "complex")
KIND_ID = {k: i for i, k in enumerate(KINDS)}
ACTIONS = ("add_food", "change_night", "recruit", "cap", "skip_food", "held_activity", "service_project", "resident_event")
ACTION_ID = {k: i for i, k in enumerate(ACTIONS)}
FLEX = {"campus": 0.5, "faculty": 0.6, "staff": 0.4, "tech": 0.5, "office": 0.35, "food_retail": 0.3, "sales": 0.2,
        "health": 0.15, "trades": 0.2}
CENTERS = [  # approximate locations: BYU CAPS (Wilkinson Student Center), UVU counseling (Student Center)
    {"name": "BYU Counseling and Psychological Services", "school": "BYU", "lon": -111.6475, "lat": 40.2486},
    {"name": "UVU Student Health Services (counseling)", "school": "UVU", "lon": -111.7140, "lat": 40.2780},
]


class Institutions:
    def __init__(self, sim):
        self.sim = sim
        self.T = Table({"kind": (np.int8, -1), "ref": (np.int32, -1), "capacity": (np.float32, -1), "budget": (np.float32, 0),
                        "hours": (np.float32, 0), "delay": (np.int16, 0), "weekday": (np.int8, -1), "food": (np.bool_, False),
                        "low_runs": (np.int16, 0), "demand": (np.float32, 0), "served": (np.float32, 0),
                        "waitlist": (np.int32, 0), "utilization": (np.float32, 0), "last_occ": (np.int64, -1),
                        "last_adapt": (np.int32, -10_000)}, capacity=1 << 10)
        self.hist = Table({"inst": (np.int64, -1), "day": (np.int32, -1), "demand": (np.float32, 0), "served": (np.float32, 0),
                           "waitlist": (np.int32, 0), "utilization": (np.float32, 0), "attended": (np.int32, -1)}, capacity=1 << 12)
        self.dec = Table({"inst": (np.int64, -1), "day": (np.int32, -1), "action": (np.int8, -1), "officer": (np.int32, -1),
                          "why": (np.float32, 0), "event": (np.int64, -1), "occasion": (np.int64, -1)}, capacity=1 << 10)
        self.names: dict[int, str] = {}
        # counseling queue: one row per request
        self.q = Table({"person": (np.int32, -1), "center": (np.int64, -1), "asked": (np.int32, -1), "crisis": (np.bool_, False),
                        "start": (np.int32, -1), "sessions": (np.int16, 0), "done": (np.int32, -1), "gave_up": (np.bool_, False),
                        "decision": (np.int64, -1), "event": (np.int64, -1)}, capacity=1 << 10)
        self._bishop_used: dict[int, int] = {}
        self._bishop_week = -1

    # ------------------------------------------------------------------ setup
    def init(self):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        P.add_internal("bishop_wait_since", np.int32, -1)
        for c, dt, f in (("recommend_hold_until", np.int32, -1), ("sacrament_hold", np.bool_, False),
                         ("church_shy", np.bool_, False), ("bishop_next", np.int32, -1), ("bishop_issue", np.int8, 0),
                         ("bishop_followups", np.int16, 0)):
            P.add_internal(c, dt, f)
        T = self.T
        G = w.groups
        ng = len(G["kind"])
        if ng:
            kinds = np.array([KIND_ID.get(str(k), KIND_ID["club"]) for k in G["kind"]], np.int8)
            ids = T.append(ng, kind=kinds, ref=np.arange(ng), capacity=p("institutions.group.room"),
                           budget=p("institutions.group.budget"), hours=2.0, weekday=np.asarray(G["weekday"], np.int8))
            for k, i in enumerate(ids.tolist()):
                self.names[i] = str(G["name"][k])
        nw = len(w.wards["kind"])
        if nw:
            ids = T.append(nw, kind=KIND_ID["ward"], ref=np.arange(nw), budget=p("institutions.ward.budget"),
                           hours=p("institutions.ward.bishop_hours"),
                           capacity=np.floor(p("institutions.ward.bishop_hours") * 3 * (1 - p("institutions.ward.other_interviews"))),
                           weekday=np.where(np.char.find(np.asarray(w.wards["kind"], str), "ysa") >= 0, 0, 2).astype(np.int8),
                           delay=7)
            for k, i in enumerate(ids.tolist()):
                self.names[i] = ward_name(w.wards, k)
        for k, c in enumerate(CENTERS):
            cap = p(f"institutions.counseling.{c['school'].lower()}_sessions") * w.scale
            i = int(T.append(1, kind=KIND_ID["counseling"], ref=k, capacity=max(cap, 1.0), hours=40, delay=1)[0])
            self.names[i] = c["name"]
        E = w.employers
        ne = len(E["type"])
        if ne:
            ids = T.append(ne, kind=KIND_ID["employer"], ref=np.arange(ne), hours=40,
                           capacity=np.array([FLEX.get(str(t), 0.3) for t in E["type"]], np.float32))
            for k, i in enumerate(ids.tolist()):
                self.names[i] = str(E["name"][k])
        cx = w.complexes
        pres = P["present"][: P.n].astype(bool) & (P["complex_id"][: P.n] >= 0)
        n_res = np.bincount(P["complex_id"][: P.n][pres], minlength=cx.height)
        big = np.flatnonzero(n_res[: cx.height] >= p("institutions.complex.min_residents") * max(w.scale / 0.15, 0.2))
        if len(big):
            ids = T.append(len(big), kind=KIND_ID["complex"], ref=big, budget=p("institutions.complex.budget"), weekday=4)
            for k, i in zip(big.tolist(), ids.tolist()):
                self.names[i] = str(cx["name"][k])
        self._row = {(int(T["kind"][j]), int(T["ref"][j])): j for j in range(T.n)}

    def row(self, kind: str, ref: int) -> int:
        return self._row.get((KIND_ID[kind], int(ref)), -1)

    # ------------------------------------------------------------------ planning (start of day)
    def plan_day(self):
        sim, w = self.sim, self.sim.w
        day = w.day
        self._bishop_day(day)
        book = getattr(sim, "book", None)
        if book is None:
            return
        wd = sim.cal.weekday(day)
        T = self.T
        if sim.cal.date(day).month in (1, 9) and sim.cal.date(day).day == 1:      # budgets renew each semester
            T.cols["budget"][: T.n] = np.where(np.isin(T["kind"], [KIND_ID["club"], KIND_ID["team"], KIND_ID["institute"]]),
                                               sim.p("institutions.group.budget"),
                                               np.where(T["kind"] == KIND_ID["ward"], sim.p("institutions.ward.budget"),
                                                        np.where(T["kind"] == KIND_ID["complex"], sim.p("institutions.complex.budget"),
                                                                 T["budget"])))
        week = day // 7
        in_term = not (sim.cal.no_class("BYU", day) and sim.cal.no_class("UVU", day))
        # club and team socials: every four weeks on the group's night, in term
        g = np.flatnonzero(np.isin(T["kind"], [KIND_ID["club"], KIND_ID["team"], KIND_ID["institute"]]) & (T["weekday"] == wd)
                           & ((week + T["ref"]) % 4 == 0))
        if in_term:
            for j in g.tolist():
                self._social(j, day)
        # ward activities: monthly on the ward's night; service projects on a Saturday each quarter
        wr = np.flatnonzero((T["kind"] == KIND_ID["ward"]) & (T["weekday"] == wd) & ((week + T["ref"]) % 4 == 1))
        for j in wr.tolist():
            self._ward_activity(j, day)
        if wd == 5:
            sp = np.flatnonzero((T["kind"] == KIND_ID["ward"]) & ((week + T["ref"]) % 13 == 3))
            for j in sp.tolist():
                self._event(j, day, "service_project", "ward", 9 * 60, ACTION_ID["service_project"])
        # complexes: a resident event every four weeks on a Friday
        if wd == 4:
            cx = np.flatnonzero((T["kind"] == KIND_ID["complex"]) & ((week + T["ref"]) % 4 == 2)
                                & (T["budget"] >= sim.p("institutions.complex.cost")))
            for j in cx.tolist():
                T.cols["budget"][j] -= sim.p("institutions.complex.cost")
                self._event(j, day, "resident_event", "complex", 17 * 60, ACTION_ID["resident_event"])

    def _where(self, j: int) -> tuple[float, float]:
        w = self.sim.w
        k, ref = KINDS[int(self.T["kind"][j])], int(self.T["ref"][j])
        if k in ("club", "team", "institute"):
            return float(w.groups["lon"][ref]), float(w.groups["lat"][ref])
        if k == "ward":
            return float(w.wards["lon"][ref]), float(w.wards["lat"][ref])
        if k == "complex":
            return float(w.complexes["lon"][ref]), float(w.complexes["lat"][ref])
        return np.nan, np.nan

    def _event(self, j: int, day: int, kind: str, org_kind: str, start: int, action: int, food=None) -> int:
        sim = self.sim
        book = sim.book
        lon, lat = self._where(j)
        spec = book.vocab[kind]
        oid = int(book.plan(kind, day, start, int(spec.get("dur", 90)), org_kind=org_kind, org_id=int(self.T["ref"][j]),
                            lon=lon, lat=lat, origin="institution", open_=True, label=self.names.get(int(self.T.ids[j])),
                            capacity=int(self.T["capacity"][j]) if org_kind == "group" else -1)[0])
        self.T.cols["last_occ"][j] = oid
        return oid

    def _social(self, j: int, day: int):
        p = self.sim.p
        T = self.T
        food = bool(T["food"][j]) and T["budget"][j] >= p("institutions.group.food_cost")
        if food:
            T.cols["budget"][j] -= p("institutions.group.food_cost")
        h, m = (int(x) for x in str(self.sim.w.groups["start"][int(T["ref"][j])] or "19:00").split(":")[:2]) \
            if isinstance(self.sim.w.groups["start"][int(T["ref"][j])], str) else (19, 0)
        self._event(j, day, "club_social_food" if food else "club_social", "group", h * 60 + m, -1)

    def _ward_activity(self, j: int, day: int):
        p = self.sim.p
        T = self.T
        food = T["budget"][j] >= p("institutions.ward.activity_cost")
        if food:
            T.cols["budget"][j] -= p("institutions.ward.activity_cost")
        self._event(j, day, "ward_activity" if food else "ward_activity_plain", "ward", 19 * 60, ACTION_ID["held_activity"])

    # ------------------------------------------------------------------ end of day: attendance and adaptation
    def end_of_day(self):
        sim, w = self.sim, self.sim.w
        day = w.day
        T = self.T
        O = sim.book.occ
        lo = np.flatnonzero(T["last_occ"] >= 0)
        if len(lo):
            od = O.get("day", T["last_occ"][lo], default=-1)
            today = lo[od == day]
            for j in today.tolist():
                self._after(j, day)
        self._counseling(day)
        if sim.cal.weekday(day) == 6:
            self._snapshot(day)

    def _members(self, j: int) -> np.ndarray:
        P = self.sim.w.P
        k, ref = KINDS[int(self.T["kind"][j])], int(self.T["ref"][j])
        col = {"club": "club_id", "team": "team_id", "institute": "institute_class", "ward": "ward_id", "complex": "complex_id"}[k]
        return np.flatnonzero((P[col][: P.n] == ref) & P["present"][: P.n].astype(bool))

    def officer(self, j: int) -> int:
        mem = self._members(j)
        if not len(mem):
            return -1
        z = self.sim.z
        return int(mem[np.argmax(z("extraversion")[mem] + z("conscientiousness")[mem])])

    def _after(self, j: int, day: int):
        sim, w = self.sim, self.sim.w
        p = sim.p
        T = self.T
        O = sim.book.occ
        oid = int(T["last_occ"][j])
        came = int(O.get("n_came", [oid], default=0)[0])
        mem = self._members(j)
        n = max(len(mem), 1)
        T.cols["demand"][j] = n
        T.cols["served"][j] = came
        T.cols["utilization"][j] = came / max(T["capacity"][j], 1) if T["capacity"][j] > 0 else came / n
        self.hist.append(1, inst=T.ids[j], day=day, demand=n, served=came, utilization=T["utilization"][j], attended=came)
        if KINDS[int(T["kind"][j])] not in ("club", "team", "institute"):
            return
        share = came / n
        T.cols["low_runs"][j] = T["low_runs"][j] + 1 if share < p("institutions.group.low_share") else 0
        cap = T["capacity"][j]
        action = -1
        if cap > 0 and came >= cap:
            action = ACTION_ID["cap"]
        elif T["low_runs"][j] >= 3 and day - T["last_adapt"][j] > 50:
            if not T["food"][j] and T["budget"][j] >= 2 * p("institutions.group.food_cost"):
                action = ACTION_ID["add_food"]
                T.cols["food"][j] = True
            elif sim.streams.uniform("inst_adapt", day, 1, int(T.ids[j]))[0] < 0.5:
                action = ACTION_ID["change_night"]
                T.cols["weekday"][j] = (int(T["weekday"][j]) + 2) % 7 if (int(T["weekday"][j]) + 2) % 7 != 6 else 3
            else:
                action = ACTION_ID["recruit"]
                self._recruit(j, day)
            T.cols["low_runs"][j] = 0
        if action >= 0:
            T.cols["last_adapt"][j] = day
            off = self.officer(j)
            if off >= 0:
                ev = sim.emit("club_changed_plans", np.array([off]), value=float(action), mech="institutions.group",
                              causes=[("occasion", np.array([oid]), 1.0)])
                link(sim, ev, "institution", np.array([int(T.ids[j])]), 1.0, "organization")
                evid = int(ev[0])
            else:
                evid = -1
            self.dec.append(1, inst=T.ids[j], day=day, action=action, officer=off, why=share, event=evid, occasion=oid)

    def _recruit(self, j: int, day: int):
        """Officers recruit at a booth: a few students of the same school with no group join."""
        sim, w = self.sim, self.sim.w
        P = w.P
        k, ref = KINDS[int(self.T["kind"][j])], int(self.T["ref"][j])
        col = {"club": "club_id", "team": "team_id", "institute": "institute_class"}[k]
        sch = int(w.groups["school"][ref])
        cand = np.flatnonzero(P["present"][: P.n].astype(bool) & P["enrolled"][: P.n] & (P[col][: P.n] < 0)
                              & (P["school"][: P.n].astype(int) == sch))
        if not len(cand):
            return
        z = sim.z("extraversion")[cand]
        u = sim.streams.uniform("inst_recruit", day, len(cand), int(self.T.ids[j]))
        pick = cand[np.argsort(-(z + 2 * u))[: max(2, int(6 * max(w.scale / 0.15, 0.3)))]]
        P.cols[col][pick] = ref
        sim.emit("joined_group", pick, value=float(ref), mech="institutions.group")

    def _snapshot(self, day: int):
        T = self.T
        rows = np.flatnonzero(np.isin(T["kind"], [KIND_ID["counseling"], KIND_ID["ward"]]))
        if len(rows):
            self.hist.append(len(rows), inst=T.ids[rows], day=day, demand=T["demand"][rows], served=T["served"][rows],
                             waitlist=T["waitlist"][rows], utilization=T["utilization"][rows])

    # ------------------------------------------------------------------ bishops
    def bishop_gate(self, people: np.ndarray, why: str = "confession") -> np.ndarray:
        """Who meets their bishop: everyone who asks. A bishop makes time for members who want to talk (after church or
        an evening that week), so there is no queue; the ward's row counts the meetings. Returns a bool mask."""
        sim, w = self.sim, self.sim.w
        P = w.P
        people = np.asarray(people, np.int64)
        if not len(people):
            return np.zeros(0, bool)
        day = w.day
        if day // 7 != self._bishop_week:
            self._bishop_week, self._bishop_used = day // 7, {}
        ward = P["ward_id"][people].astype(np.int64)
        P.internal["bishop_wait_since"][people] = -1
        T = self.T
        for wd_, k in zip(*np.unique(ward[ward >= 0], return_counts=True)):
            self._bishop_used[int(wd_)] = self._bishop_used.get(int(wd_), 0) + int(k)
            j = self.row("ward", int(wd_))
            if j >= 0:
                T.cols["served"][j] = self._bishop_used[int(wd_)]
                T.cols["demand"][j] = self._bishop_used[int(wd_)]
                T.cols["waitlist"][j] = 0
                T.cols["utilization"][j] = 0.0
        return np.ones(len(people), bool)

    ISSUES = {"porn": 1, "masturbation": 2, "sex": 3}

    def in_followup(self, n: int) -> np.ndarray:
        """Who is already meeting their bishop regularly (they don't need to ask again)."""
        return self.sim.w.P.internal["bishop_next"][:n] >= 0

    def counsel(self, ids: np.ndarray, issue: str, cause=None):
        """What follows a talk with the bishop (institutions.bishop): after premarital sex the temple recommend is
        held for a few weeks, often the sacrament too, and some go to church less meanwhile; every ongoing issue gets
        roughly monthly follow-ups."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        ids = np.asarray(ids, np.int64)
        if not len(ids):
            return
        day = w.day
        I = P.internal
        code = self.ISSUES[issue]
        I["bishop_issue"][ids] = np.maximum(I["bishop_issue"][ids], code)
        I["bishop_followups"][ids] = 0
        I["bishop_next"][ids] = day + self._gap(ids, "bishop_gap")
        if issue != "sex":
            return
        weeks = np.round(p("institutions.bishop.hold_weeks") * (0.75 + 1.25 * sim.u("recommend_hold")[ids])).astype(int)
        weeks = np.maximum(weeks, 1)
        I["recommend_hold_until"][ids] = np.maximum(I["recommend_hold_until"][ids], day + 7 * weeks)
        sac = sim.u("sacrament_hold")[ids] < p("institutions.bishop.sacrament_share")
        I["sacrament_hold"][ids[sac]] = True
        I["church_shy"][ids[sac]] = sim.u("church_shy")[ids[sac]] < p("institutions.bishop.skip_share")
        P.cols["temple_recommend"][ids] = False
        sim.emit("recommend_withheld", ids, value=weeks.astype(float), cause=cause, mech="institutions.bishop")

    def _gap(self, ids: np.ndarray, stream: str) -> np.ndarray:
        g = self.sim.p("institutions.bishop.followup_days")
        return np.round(g * (0.75 + 0.5 * self.sim.u(stream)[ids])).astype(np.int32)

    def _bishop_day(self, day: int):
        """Holds that run out and the follow-up meetings that fall due today."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        I = P.internal
        hold = I["recommend_hold_until"][:n]
        done = np.flatnonzero((hold >= 0) & (hold <= day))
        if len(done):
            still = P["premarital_sex_current"][done].astype(bool)
            hold[done[still]] = day + 28                      # still sexually active: the hold goes on
            ok = done[~still]
            hold[ok] = -1
            I["sacrament_hold"][ok] = False
            I["church_shy"][ok] = False
            back = ok[P["lds_member"][ok] & (P["activity"][ok] == 3) & P["present"][ok]]
            if len(back):
                P.cols["temple_recommend"][back] = True
                sim.emit("recommend_restored", back, mech="institutions.bishop")
        due = np.flatnonzero((I["bishop_next"][:n] >= 0) & (I["bishop_next"][:n] <= day))
        if not len(due):
            return
        iss = I["bishop_issue"][due]
        ongoing = np.select([iss == 1, iss == 2, iss == 3],
                            [P["porn_use"][due] >= 1, P["masturbation"][due] >= 1, P["premarital_sex_current"][due].astype(bool)],
                            False)
        ongoing |= (iss == 3) & (hold[due] >= 0)                  # check in until the recommend is back
        go = P["present"][due] & P["lds_member"][due] & (I["bishop_followups"][due] < p("institutions.bishop.max_followups"))
        stop = due[~(go & ongoing)]
        I["bishop_next"][stop] = -1
        I["bishop_issue"][stop] = 0
        meet = due[go & ongoing]
        if not len(meet):
            return
        self.bishop_gate(meet, "followup")
        sim.emit("bishop_followup", meet, value=I["bishop_issue"][meet].astype(float), mech="institutions.bishop")
        I["bishop_followups"][meet] += 1
        P.cols["bishop_meetings"][meet] = np.minimum(P["bishop_meetings"][meet] + 1, 10)
        I["bishop_next"][meet] = day + self._gap(meet, "bishop_gap2")

    # ------------------------------------------------------------------ counseling
    def _counseling(self, day: int):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        if sim.cal.weekday(day) != 0:            # intake and sessions are planned weekly (Mondays)
            return
        T, Q = self.T, self.q
        centers = np.flatnonzero(T["kind"] == KIND_ID["counseling"])
        n = P.n
        open_q = (Q["done"] < 0) & ~Q["gave_up"]
        in_q = np.zeros(n, bool)
        in_q[Q["person"][open_q]] = True
        # 1 who seeks help this week
        sch = P["school"][:n].astype(int)
        elig = P["present"][:n].astype(bool) & P["enrolled"][:n] & np.isin(sch, [1, 2]) & ~in_q
        need = P["coping_need"][:n]
        dep = P["depressive_episode"][:n].astype(float)
        cand = np.flatnonzero(elig & ((dep > 0) | (need > 0.55)))
        if len(cand):
            Tm = {"depression": p("institutions.counseling.seek_depression") * dep[cand],
                  "strain": p("institutions.counseling.seek_strain") * (need[cand] - 0.5),
                  "openness": 0.3 * sim.z("openness")[cand],
                  "stigma": -0.4 * sim.z("conformity")[cand]}
            base = p("institutions.counseling.seek_base")
            pr = expit(base + sum(Tm.values()))
            go = sim.streams.uniform("inst_seek", day, len(cand)) < pr
            if go.any():
                ids = cand[go]
                did = sim.decisions.record("seek_counseling", day, ids, "sought", {k: v[go] for k, v in Tm.items()},
                                           base=base, prob=pr[go])
                ev = sim.emit("sought_counseling", ids, mech="institutions.counseling", decision=did,
                              cause=P.internal["cope_event"][ids] if "cope_event" in P.internal else None)
                ctr = centers[np.clip(sch[ids] - 1, 0, len(centers) - 1)]
                crisis = (dep[ids] > 0) & (P["mood"][ids] < 0.25)
                Q.append(len(ids), person=ids, center=T.ids[ctr], asked=day, crisis=crisis, decision=did, event=ev)
        # 2 sessions: people in care get one a week; free slots take the waitlist (crisis first, then longest wait)
        Q = self.q
        for c in centers.tolist():
            cap = int(round(T["capacity"][c]))
            cid = int(T.ids[c])
            care = np.flatnonzero((Q["center"] == cid) & (Q["start"] >= 0) & (Q["done"] < 0))
            wait = np.flatnonzero((Q["center"] == cid) & (Q["start"] < 0) & (Q["done"] < 0) & ~Q["gave_up"])
            gone = ~P["present"][Q["person"][care]].astype(bool) | ~P["enrolled"][Q["person"][care]]
            Q.cols["done"][care[gone]] = day
            care = care[~gone]
            free = max(cap - len(care), 0)
            order = wait[np.lexsort((Q["asked"][wait], ~Q["crisis"][wait]))]
            take = order[:free]
            Q.cols["start"][take] = day
            if len(take):
                ppl = Q["person"][take].astype(np.int64)
                ev = sim.emit("counseling_started", ppl, value=(day - Q["asked"][take]).astype(float), mech="institutions.counseling",
                              cause=Q["event"][take])
                link(sim, ev, "institution", np.full(len(take), cid), 1.0, "organization")
            care = np.r_[care, take]
            if len(care):
                ppl = Q["person"][care].astype(np.int64)
                Q.cols["sessions"][care] += 1
                sim.emit("counseling_session", ppl, mech="institutions.counseling")
                P.cols["coping_relief"][ppl] = np.clip(P["coping_relief"][ppl] + p("institutions.counseling.relief"), 0, 1)
                fin = care[Q["sessions"][care] >= int(p("institutions.counseling.course"))]
                Q.cols["done"][fin] = day
            still = order[free:]
            waited = day - Q["asked"][still]
            quit_ = sim.streams.uniform("inst_giveup", day, len(still), cid) < expit(-4.0 + 0.5 * waited / 7)
            Q.cols["gave_up"][still[quit_]] = True
            if quit_.any():
                ev = sim.emit("gave_up_waiting", Q["person"][still[quit_]].astype(np.int64), value=waited[quit_].astype(float),
                              mech="institutions.counseling", cause=Q["event"][still[quit_]])
                link(sim, ev, "institution", np.full(int(quit_.sum()), cid), 1.0, "organization")
            T.cols["demand"][c] = len(care) + len(still) - int(quit_.sum())
            T.cols["served"][c] = len(care)
            T.cols["waitlist"][c] = len(still) - int(quit_.sum())
            T.cols["utilization"][c] = len(care) / max(cap, 1)

    # ------------------------------------------------------------------ employers
    def shift_flex(self, people, day) -> np.ndarray:
        """Whether each person's employer would let them swap today's shift (by kind of job; the same answer for the
        same person and day in both worlds)."""
        from ...analysis.query import hash_uniform
        w = self.sim.w
        P = w.P
        people = np.atleast_1d(np.asarray(people, np.int64))
        emp = P["employer_id"][people].astype(np.int64)
        flex = getattr(self, "_flex", None)
        if flex is None or len(flex) != len(w.employers["type"]):
            flex = self._flex = np.array([FLEX.get(str(t), 0.3) for t in w.employers["type"]], np.float32)
        f = np.where(emp >= 0, flex[np.maximum(emp, 0)], 0.0) * self.sim.p("institutions.employer.flex_scale")
        return hash_uniform(people * 1000 + np.asarray(day, np.int64), "shift_swap") < f

    def openings(self, day: int) -> float:
        """How many jobs are open now relative to usual: campus jobs at semester start, retail before Christmas, few in
        early summer when students leave."""
        m = self.sim.cal.date(day).month
        p = self.sim.p
        return {8: p("institutions.employer.semester_start"), 9: p("institutions.employer.semester_start"),
                1: p("institutions.employer.semester_start"), 11: p("institutions.employer.holiday_retail"),
                12: p("institutions.employer.holiday_retail"), 5: p("institutions.employer.early_summer")}.get(m, 1.0)

    # ------------------------------------------------------------------ reading
    def describe(self, j: int) -> dict:
        T = self.T
        return {"id": int(T.ids[j]), "kind": KINDS[int(T["kind"][j])], "ref": int(T["ref"][j]), "name": self.names.get(int(T.ids[j]), "?"),
                "capacity": float(T["capacity"][j]), "budget": round(float(T["budget"][j]), 2), "hours": float(T["hours"][j]),
                "delay": int(T["delay"][j]), "weekday": int(T["weekday"][j]), "food": bool(T["food"][j]),
                "demand": float(T["demand"][j]), "served": float(T["served"][j]), "waitlist": int(T["waitlist"][j]),
                "utilization": round(float(T["utilization"][j]), 3)}

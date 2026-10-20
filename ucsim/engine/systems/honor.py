"""BYU's Honor Code and ecclesiastical endorsement (config/policies/campus.yaml).

Weekly, each BYU student whose behaviour breaks the Honor Code in a way the model simulates (coffee or tea, alcohol,
premarital sex, same-sex dating) may be reported to the Honor Code Office. Reports are rare and quiet (an anonymous
tip, seldom a confrontation; reporters are seen as snitches) and lean toward same-sex romance and alcohol rather than
coffee; living with roommates in contracted housing raises the odds a little. The office decides: a warning (most cases), probation (until the end of
the next term without a new report), suspension or, rarely, dismissal. Suspended and dismissed students leave BYU:
they transfer to UVU or stop studying. After a report many stop the behaviour.

The ecclesiastical endorsement is renewed once a year, on each student's own date; a bishop may decline it for
members who no longer attend, and leaving the Church withdraws it at once. Without one a student can't enroll for the next term.

World switches: `honor_enforcement` (0 = not enforced … 1 = today) and `endorsement_required`. Randomness comes from
this system's own streams; the decisions and events carry the factors and causes.
"""
from __future__ import annotations

import numpy as np

KINDS = ("", "coffee or tea", "alcohol", "premarital sex", "same-sex dating")
OUTCOMES = ("warning", "probation", "suspension", "dismissal")


class Honor:
    def __init__(self, sim):
        self.sim = sim
        self.reports = 0            # running totals (for /api/policies)
        self.outcomes = {o: 0 for o in OUTCOMES}
        self.withdrawn = 0
        self.left = {"transferred_to_uvu": 0, "stopped": 0}
        self._last_scan = -1        # the last log row scanned for resignations

    # ------------------------------------------------------------------ helpers
    def _byu_students(self) -> np.ndarray:
        P = self.sim.w.P
        return (P["school"] == P.code("school", "BYU")) & P.is_("role", "byu_student") & P["present"]

    def _sync(self):
        """BYU students start in good standing with a current endorsement; everyone else is n/a."""
        P = self.sim.w.P
        byu = self._byu_students()
        st, en = P.cols["honor_standing"], P.cols["endorsement"]
        n = P.n
        st[:n][byu & (st[:n] == 0)] = P.code("honor_standing", "good")
        en[:n][byu & (en[:n] == 0)] = P.code("endorsement", "current")
        st[:n][~byu & np.isin(st[:n], [1, 2, 3])] = 0          # no longer a BYU student: the code no longer covers them
        en[:n][~byu & (en[:n] == 1)] = 0

    def init(self):
        self.sim.w.P.add_internal("honor_probation_until", np.int32, -1)
        self._sync()
        self._last_scan = self.sim.log.n

    # ------------------------------------------------------------------ weekly: reports and outcomes
    def weekly(self):
        sim, w = self.sim, self.sim.w
        P, p, env = w.P, sim.p, w.env
        self._sync()
        self._resignations()
        enforce = float(env.get("honor_enforcement", 1.0))
        if enforce <= 0:
            return
        byu = self._byu_students() & P["enrolled"]
        ids = np.flatnonzero(byu)
        if not len(ids):
            return
        # which simulated violations each student has right now
        partner = P["partner_id"][ids]
        same_sex = (partner >= 0) & P.isin("rel_status", ["dating", "engaged"])[ids] & \
            (P["sex"][np.where(partner >= 0, partner, ids)] == P["sex"][ids])
        V = np.stack([P["coffee"][ids] >= 1, P["alcohol"][ids] >= 1, P["premarital_sex_current"][ids].astype(bool), same_sex], axis=1)
        rates = np.array([p("honor.report.rate_coffee"), p("honor.report.rate_alcohol"), p("honor.report.rate_sex"),
                          p("honor.report.rate_same_sex")])
        lam = (V * rates).sum(axis=1)
        if not lam.any():
            return
        near = 1 + p("honor.report.roommates") * P.isin("living", ["dorm", "contracted"])[ids]
        careful = 1.3 - 0.6 * np.clip(sim.z("conscientiousness")[ids], 0, 1.5) / 1.5
        prob = 1 - np.exp(-enforce * lam * near * careful)
        hit = sim.u("honor_report")[ids] < prob
        if not hit.any():
            return
        r = ids[hit]
        Vr, lr = V[hit], (V * rates)[hit]
        kind = 1 + np.argmax(lr, axis=1)                       # the main thing they were reported for
        P.cols["honor_reports"][r] = np.minimum(P["honor_reports"][r].astype(int) + 1, 20)
        rep = sim.emit("honor_reported", r, value=kind.astype(float), mech="honor.report")
        self.reports += len(r)
        self._decide(r, kind, rep)
        # after a report many stop what they were reported for
        stop = sim.u("honor_quit")[r] < p("honor.report.quit_after")
        s = r[stop]
        if len(s):
            P.cols["coffee"][s[Vr[stop, 0]]] = 0
            P.cols["alcohol"][s[Vr[stop, 1]]] = 0
            P.cols["premarital_sex_current"][s[Vr[stop, 2]]] = False
            P.cols["chastity_commitment"][s] = np.clip(P["chastity_commitment"][s] + 0.1, 0, 1)

    def _decide(self, r: np.ndarray, kind: np.ndarray, rep: np.ndarray):
        """The Honor Code Office's decision for each reported student (a recorded choice with its reasons)."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        k = len(r)
        prior = np.maximum(P["honor_reports"][r].astype(float) - 1, 0)
        onp = P.is_("honor_standing", "probation")[r].astype(float)
        serious = np.isin(kind, [3, 4]).astype(float)
        U = np.zeros((k, 4))
        U[:, 1] = p("honor.outcome.base_probation") + p("honor.outcome.repeat") * prior + p("honor.outcome.kind_serious") * serious
        U[:, 2] = p("honor.outcome.base_suspension") + p("honor.outcome.repeat") * prior + p("honor.outcome.on_probation") * onp
        U[:, 3] = p("honor.outcome.base_dismissal") + 1.5 * p("honor.outcome.repeat") * prior + p("honor.outcome.on_probation") * onp
        G = sim.streams.gen("honor_outcome", w.day).gumbel(size=(P.n, 4))[r]
        ch = np.argmax(U + G, axis=1)
        ex = np.exp(U - U.max(axis=1, keepdims=True))
        prob = ex / ex.sum(axis=1, keepdims=True)
        sel = U[np.arange(k), ch]
        F = {"base": np.select([ch == 0, ch == 1, ch == 2, ch == 3], [0.0 * sel, np.full(k, p("honor.outcome.base_probation")),
                                                                     np.full(k, p("honor.outcome.base_suspension")), np.full(k, p("honor.outcome.base_dismissal"))]),
             "repeat": np.where(ch > 0, p("honor.outcome.repeat") * prior, 0.0),
             "on_probation": np.where(ch >= 2, p("honor.outcome.on_probation") * onp, 0.0),
             "kind": np.where(ch == 1, p("honor.outcome.kind_serious") * serious, 0.0)}
        did = sim.decisions.record("honor_outcome", w.day, r, [OUTCOMES[c] for c in ch], F, prob=prob[np.arange(k), ch])
        for c, name in enumerate(OUTCOMES):
            m = ch == c
            if not m.any():
                continue
            self.outcomes[name] += int(m.sum())
            who = r[m]
            if name == "warning":
                if (P["honor_standing"][who] != P.code("honor_standing", "probation")).any():
                    keep = who[P["honor_standing"][who] != P.code("honor_standing", "probation")]
                    P.cols["honor_standing"][keep] = P.code("honor_standing", "warned")
                sim.emit("honor_warning", who, cause=rep[m], decision=did[m], mech="honor.outcome")
            elif name == "probation":
                P.cols["honor_standing"][who] = P.code("honor_standing", "probation")
                P.internal["honor_probation_until"][who] = self._probation_end()
                sim.emit("honor_probation", who, cause=rep[m], decision=did[m], mech="honor.outcome")
            else:
                P.cols["honor_standing"][who] = P.code("honor_standing", "suspended" if name == "suspension" else "dismissed")
                ev = sim.emit("honor_suspended", who, cause=rep[m], decision=did[m], mech="honor.outcome")
                self._leave(who, ev)

    def _probation_end(self) -> int:
        """Probation lasts until the end of the next BYU term (the day its last exam ends)."""
        sim, w = self.sim, self.sim.w
        cal = sim.cal
        d = cal.date(w.day)
        terms = [t for t in cal.real.terms_between(d, d.replace(year=d.year + 1)) if t.school == "BYU" and t.finals_end >= d]
        t = terms[1] if len(terms) > 1 else (terms[0] if terms else None)
        return (t.finals_end - cal.start).days if t else w.day + 120

    # ------------------------------------------------------------------ leaving BYU
    def _leave(self, who: np.ndarray, cause: np.ndarray):
        """Out of BYU: transfer to UVU (enrolled at UVU's next term start) or stop studying."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        if not len(who):
            return
        amb = sim.z("academic_ability")[who] if "academic_ability" in P else np.zeros(len(who))
        money = P["financial_stress"][who] - 0.5
        F = {"base": np.full(len(who), p("honor.outcome.transfer_uvu")), "ambition": 0.5 * amb, "money": -1.0 * money}
        u = sum(F.values())
        pr = 1 / (1 + np.exp(-u))
        go = sim.u("honor_transfer")[who] < pr
        did = sim.decisions.record("after_byu", w.day, who, np.where(go, "transferred_to_uvu", "stopped").tolist(), F,
                                   prob=np.where(go, pr, 1 - pr))
        P.cols["enrolled"][who] = False
        t = who[go]
        if len(t):
            P.cols["school"][t] = P.code("school", "UVU")
            P.cols["role"][t] = P.code("role", "uvu_student")
        s = who[~go]
        if len(s):
            P.cols["role"][s] = P.code("role", "young_adult")
            sim.systems["lifecourse"].schedule_stay(s)
        P.cols["endorsement"][who] = 0
        self.left["transferred_to_uvu"] += int(go.sum())
        self.left["stopped"] += int((~go).sum())
        sim.emit("left_byu", who, value=go.astype(float), cause=cause, decision=did, mech="honor.outcome")

    # ------------------------------------------------------------------ the endorsement
    def _resignations(self):
        """Leaving the Church withdraws the endorsement at once (new resigned_membership events since last week)."""
        sim, w = self.sim, self.sim.w
        P, log, reg = w.P, sim.log, sim.reg
        if not bool(w.env.get("endorsement_required", True)) or "resigned_membership" not in reg.event_ids:
            self._last_scan = log.n
            return
        lo, hi = max(self._last_scan, 0), log.n
        self._last_scan = hi
        if hi <= lo:
            return
        rows = lo + np.flatnonzero(log["type"][lo:hi] == reg.event_ids["resigned_membership"])
        if not len(rows):
            return
        who = log["a"][rows]
        ok = P.is_("endorsement", "current")[who] & self._byu_students()[who]
        self._withdraw(who[ok], cause=rows[ok])

    def _withdraw(self, who: np.ndarray, cause=None):
        sim, P = self.sim, self.sim.w.P
        if not len(who):
            return
        P.cols["endorsement"][who] = P.code("endorsement", "withdrawn")
        self.withdrawn += len(who)
        sim.emit("endorsement_withdrawn", who, cause=cause, mech="honor.endorsement")

    def daily(self):
        """On BYU's fall start: yearly renewals. On any BYU term start: students without an endorsement can't enroll,
        and probations that have run their course end."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        d = w.day
        start = sim.cal.term_start("BYU", d)
        # probation ends after its term with no new report
        until = P.internal["honor_probation_until"][: P.n]
        done = np.flatnonzero(P.is_("honor_standing", "probation") & (until >= 0) & (until < d))
        if len(done):
            P.cols["honor_standing"][done] = P.code("honor_standing", "good")
            until[done] = -1
            sim.emit("honor_standing_restored", done, mech="honor.outcome")
        if not bool(w.env.get("endorsement_required", True)):
            return
        byu = self._byu_students()
        # yearly renewal on each student's own date (the anniversary of their last interview)
        due = byu & ((d + (np.arange(P.n, dtype=np.int64) * 2654435761) % 365) % 365 == 0)
        if due.any():
            lds = due & P["lds_member"] & P.is_("endorsement", "current")
            dec = np.where(P.is_("activity", "inactive"), p("honor.endorsement.decline_inactive"),
                           np.where(P.is_("activity", "less_active"), p("honor.endorsement.decline_less_active"), 0.0))
            u = sim.u("endorsement_renewal")
            declined = np.flatnonzero(lds & (u < dec))
            renewed = np.flatnonzero(due & P.is_("endorsement", "current") & ~np.isin(np.arange(P.n), declined))
            if len(renewed):
                sim.emit("endorsement_renewed", renewed, mech="honor.endorsement")
            self._withdraw(declined)
        if not start:
            return
        self._sync()
        byu = self._byu_students()
        # no endorsement, no enrollment (a rare exception on petition)
        out = np.flatnonzero(byu & P.is_("endorsement", "withdrawn"))
        if len(out):
            exc = sim.u("endorsement_exception")[out] < p("honor.endorsement.exception_rate")
            self._leave(out[~exc], None)

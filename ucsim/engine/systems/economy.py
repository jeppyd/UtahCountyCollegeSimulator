"""Monthly finances, employment dynamics and the labor-market response to shocks."""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..provenance import latest_event, link, place_ref, state_ref
from ..state import CTX_ID


class Economy:
    def __init__(self, sim):
        self.sim = sim
        self.expenses = np.zeros(0)

    def init(self):
        w = self.sim.w
        P = w.P
        P.add_internal("scholarship", np.float32, 0.0)
        P.add_internal("last_hardship", np.int32, -10000)
        P.add_internal("work_pref", np.float32, 0.0)
        self.assign_scholarships(np.arange(P.n))
        self._compute(update_balances=False)

    def assign_scholarships(self, ids):
        """Share of tuition covered by scholarships/grants (merit at BYU, need-based Pell common at UVU)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        P.internal["work_pref"][ids] = P["work_hours"][ids]  # hours chosen before any financial strain
        rng = np.random.default_rng([w.seed, 61, len(ids), int(ids[0]) if len(ids) else 0])
        gpa = np.nan_to_num(P["gpa"][ids], nan=3.4)
        byu = P["school"][ids] == 1
        p_merit = np.clip((gpa - 3.3) * 0.6, 0, 0.55)
        p_need = np.where(P["parent_income"][ids] <= 5, 0.55, 0.12)
        merit = rng.random(len(ids)) < np.where(byu, p_merit, p_merit * 0.5)
        need = rng.random(len(ids)) < np.where(byu, p_need * 0.6, p_need)
        share = np.clip(merit * rng.choice([0.5, 1.0], len(ids)) + need * 0.6, 0, 1)
        P.internal["scholarship"][ids] = share

    def _compute(self, update_balances: bool):
        sim, w = self.sim, self.sim.w
        P, env = w.P, w.env
        n = P.n
        present = P["present"]
        income = P["wage"] * P["work_hours"] * 4.33 * env.get("wage_index", 1.0) * P["employed"] + P["parental_support"]
        # married couples pool income (both agents) — non-agent spouses of faculty/community add a typical income
        part = P["partner_id"]
        married = P.is_("rel_status", "married")
        has_p = married & (part >= 0)
        pooled = np.where(has_p, (income + income[np.maximum(part, 0)]) / 2, income)
        pooled = np.where(married & (part < 0), income + 2500, pooled)
        tuition = np.where(P["enrolled"], np.where(P["school"] == 1, env["tuition_byu"], env["tuition_uvu"]) / 4.0, 0.0)
        tuition = tuition * (P["credits_term"] / 13).clip(0.4, 1.2) * (1 - P.internal["scholarship"][:n])
        rent = P["rent"] * env.get("rent_index", 1.0) * env.get("rent_shock", 1.0)
        food = 330 + 30 * P.internal["eat_out_month"][:n] * 0.5
        car = 260 * P["owns_car"]
        dating = 18 * P["dates_30d"]
        kids = 450.0 * P["children"].astype(np.float64)
        other = 140.0
        expenses = rent + tuition + food + car + dating + kids + other
        self.expenses = expenses
        P["monthly_income"] = pooled.astype(np.float32)
        P["rent_burden"] = np.where(pooled > 50, rent / np.maximum(pooled, 1), np.where(rent > 0, 2.0, 0.0)).clip(0, 3).astype(np.float32)
        if update_balances:
            net = pooled - expenses
            sav = P["savings"] + np.where(present, net, 0)
            short = np.where(sav < 0, -sav, 0.0)
            # shortfalls: well-off parents top up young single children; students borrow (federal loans);
            # anything left becomes credit-card debt and a hardship event
            parents = (P["parent_income"] >= 10) & (P["age"] < 26) & ~married
            cover = np.where(parents, 0.6 * short, 0)
            short = short - cover
            loan = np.where(P["enrolled"], np.minimum(short, 900), 0)
            short = short - loan
            cc = short
            last = P.internal["last_hardship"][:n]
            hardship = present & (cc > 50) & (w.day - last > 180)
            P.internal["last_hardship"][:n] = np.where(hardship, w.day, last)
            P["debt"] = (P["debt"] + loan + cc).astype(np.float32)
            P["savings"] = np.maximum(sav, 0).astype(np.float32)
            # pay down debt when there is a buffer
            pay = np.minimum(P["debt"], np.maximum(P["savings"] - 2 * expenses, 0) * 0.3)
            P["debt"] = (P["debt"] - pay).astype(np.float32)
            P["savings"] = (P["savings"] - pay).astype(np.float32)
            if hardship.any():
                ids = np.where(hardship)[0]
                ev = sim.emit("financial_hardship", ids, mech="economy.budget")
                self._why_short(ev, ids, rent, tuition, expenses, pooled)

    def monthly(self):
        sim, w = self.sim, self.sim.w
        P, p, env = w.P, sim.p, w.env
        n = P.n
        self._compute(update_balances=True)
        present = P["present"]
        u = sim.u("job")
        ur = env["unemployment"]
        # job loss hazard rises non-linearly with unemployment
        h_loss = p("economy.job_loss.base") * (ur / 0.032) ** 1.5
        lose = present & P["employed"] & ~np.isin(P["job_type"], [9, 10]) & (u < h_loss)
        D = sim.decisions
        if lose.any():
            ids = np.where(lose)[0]
            employer = place_ref(CTX_ID["work"], P["employer_id"][ids])
            P.cols["employed"][ids] = False
            P.cols["work_hours"][ids] = 0
            P.internal["shift_mask"][ids] = 0
            # a flat monthly hazard scaled by local unemployment (log scale: the two parts add up)
            did = D.record("job_loss", w.day, ids, "lost", {"unemployment": np.full(len(ids), 1.5 * np.log(ur / 0.032))},
                           base=float(np.log(p("economy.job_loss.base"))), prob=h_loss)
            ev = sim.emit("job_lost", ids, mech="economy.job_loss", decision=did)
            link(sim, ev, "place", employer, 1.0, "employer")
        # job search: driven by financial stress; finding rate falls with unemployment
        # people actively coping with money strain, or intending to find work, look too (coping.py, plans.py)
        coping_money = sim.systems["coping"].money_coping()
        trying = coping_money
        plans = sim.systems.get("plans")
        if plans is not None:
            trying = trying | plans.wants_work()
        seeking = present & ~P["employed"] & (P["age"] < 65) & ((P["financial_stress"] > 0.5) | ~P["enrolled"] | trying) & ~P.is_("role", "faculty")
        h_find = expit(p("economy.job_find.base") + 2.0 * (P["financial_stress"] - 0.4) + 0.5 * trying) * (0.032 / ur) ** 0.8
        inst = sim.systems.get("institutions")
        if inst is not None:      # seasonal openings (campus jobs at semester start, holiday retail)
            h_find = np.clip(h_find * inst.openings(w.day), 0, 1)
        find = seeking & (sim.u("job_find") < h_find)
        if find.any():
            ids = np.where(find)[0]
            P.cols["employed"][ids] = True
            hours = np.where(P["enrolled"][ids], 12 + 10 * sim.u("hrs")[ids], 30 + 12 * sim.u("hrs")[ids])
            P.cols["work_hours"][ids] = hours
            P.cols["wage"][ids] = np.maximum(P["wage"][ids], 13 + 6 * sim.u("wg")[ids])
            emp = w.employers
            P.cols["employer_id"][ids] = (sim.u("emp")[ids] * len(emp["type"])).astype(int)
            sim.systems["activity"].assign_shifts(ids)
            # why the search paid off this month: money pressure and actively looking (a plan to find work, or coping
            # with money strain), with the job market multiplying the chance
            plan_ev = plans.formed_event(ids, "find_work") if plans is not None else np.full(len(ids), -1, np.int64)
            cope_ev = np.where(coping_money[ids], P.internal["cope_event"][ids], -1)
            did = D.record("job_search", w.day, ids, "found",
                           {"money": 2.0 * (P["financial_stress"][ids] - 0.4), "trying": 0.5 * trying[ids],
                            "job_market": np.full(len(ids), 0.8 * np.log(0.032 / ur))},
                           base=p("economy.job_find.base"), prob=h_find[ids],
                           refs={"trying": ("event", np.where(plan_ev >= 0, plan_ev, cope_ev)),
                                 "money": ("state", state_ref(sim, "financial_stress", ids))})
            ev = sim.emit("job_found", ids, mech="economy.job_find", decision=did,
                          cause=latest_event(sim, ids, ("job_lost", "quit_job", "graduation"), w.day - 120))
            link(sim, ev, "event", plan_ev, 0.6, "intention")
            link(sim, ev, "event", cope_ev, 0.6, "coping")
            link(sim, ev, "place", place_ref(CTX_ID["work"], P["employer_id"][ids]), 1.0, "employer")
        # students with little money pressure and heavy coursework quit to focus on school
        q = p("economy.quit.base") * (1 + 2 * P["academic_pressure"])
        quit_ = present & P["employed"] & P["enrolled"] & (P["financial_stress"] < 0.3) & ~np.isin(P["job_type"], [9, 10]) & (sim.u("quit") < q)
        if quit_.any():
            ids = np.where(quit_)[0]
            employer = place_ref(CTX_ID["work"], P["employer_id"][ids])
            P.cols["employed"][ids] = False
            P.cols["work_hours"][ids] = 0
            P.internal["shift_mask"][ids] = 0
            did = D.record("quit_job", w.day, ids, "quit", {"school": np.log1p(2 * P["academic_pressure"][ids])},
                           base=float(np.log(p("economy.quit.base"))), prob=q[ids],
                           refs={"school": ("state", state_ref(sim, "academic_pressure", ids))})
            ev = sim.emit("quit_job", ids, mech="economy.quit", decision=did)
            link(sim, ev, "place", employer, 1.0, "employer")
        # financial stress pushes students to work more (crowding out study)
        thr = p("economy.work_more.threshold")
        more = present & P["employed"] & P["enrolled"] & ((P["financial_stress"] > thr) | (trying & (P["financial_stress"] > thr - 0.15))) & (P["work_hours"] < 32)
        if more.any():
            ids = np.where(more)[0]
            P.cols["work_hours"][ids] += 3
            sim.systems["activity"].assign_shifts(ids)
        # …and cut back once the pressure is off (back toward the hours they started with)
        less = present & P["employed"] & P["enrolled"] & (P["financial_stress"] < thr - 0.25) & (P["work_hours"] > P.internal["work_pref"][:n] + 1)
        if less.any():
            ids = np.where(less)[0]
            P.cols["work_hours"][ids] = np.maximum(P["work_hours"][ids] - 2, P.internal["work_pref"][ids])
            sim.systems["activity"].assign_shifts(ids)
        # annual raise in January
        self._raise()

    def _why_short(self, ev, ids, rent, tuition, expenses, income):
        """Running out of money: the month's shortfall, as the shares of spending that rent and tuition took and how
        far income fell short, plus a job lost in the last two months."""
        sim = self.sim
        exp_ = np.maximum(expenses[ids], 1.0)
        link(sim, ev, "state", state_ref(sim, "rent", ids), np.clip(rent[ids] / exp_, 0, 1), "rent")
        t = np.asarray(tuition)[ids]
        m = t > 0
        link(sim, ev[m], "state", state_ref(sim, "credits_term", ids[m]), np.clip(t[m] / exp_[m], 0, 1), "tuition")
        short = np.clip(1 - income[ids] / exp_, 0, 1)
        m = short > 0.05
        link(sim, ev[m], "state", state_ref(sim, "monthly_income", ids[m]), short[m], "income")
        link(sim, ev, "event", latest_event(sim, ids, ("job_lost",), sim.w.day - 62), 1.0, "after")

    def _raise(self):
        w = self.sim.w
        P, env = w.P, w.env
        if w.date.month == 12:
            P["wage"] = (P["wage"] * (1.03 * env.get("wage_index", 1.0) / max(env.get("wage_index", 1.0), 1e-9))).astype(np.float32)

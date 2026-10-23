"""Sleep: who is asleep each hour, what wakes them, how much they slept.

Sleep is one of the hour's free-time options (engine/systems/activity.py): its pull rises with the hours someone has
been awake (sleep pressure) and with their body clock's night (a 24-hour sleepiness curve shifted by their
chronotype, the night-owl lean), and it rises earlier when tomorrow starts early. What they're in the middle of (a
party, a partner, a game) competes through its own pull to carry on, so a good night keeps people up (Borbély's two
processes; Kroese et al. 2014 on bedtime procrastination).

Once in bed, stress and worry can keep them awake for an hour or more. Asleep, they wake on their own after their
usual amount (plus some catch-up after short nights), or to an alarm set for the first class, shift or church
meeting: whether they get up when it rings depends on conscientiousness, how short the night was and their mood;
sleeping through it means missing what started meanwhile. Daytime naps are short.

What they actually slept in the 24 hours of the simulated day (6 am to 6 am) becomes `sleep_hours`, which the rest of
the model already reads (fatigue, mood, grades). Times are absolute minutes (day × 1440 + minute of the day, where the
day's minutes run 360 … 1800).
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from .. import clock

# sleepiness by circadian hour (clock hour − chronotype), for a typical young adult: high from about 11 pm to 6 am,
# lowest in the late morning and the early evening (the "forbidden zone" before habitual bedtime), a dip after lunch
CIRC = np.array([1.2, 1.8, 2.4, 2.8, 3.0, 3.0, 2.0, 0.8, -0.5, -1.5, -2.0, -2.0,
                 -1.9, -1.5, -1.4, -1.6, -2.1, -2.2, -2.2, -2.1, -1.6, -0.9, -0.2, 0.5])
PREP = 50                   # minutes between the alarm and the start of the first commitment (getting ready, travel)
NAP_FROM, NAP_TO = 9 * 60, 19 * 60      # going to sleep between these clock times is a nap


def curve(table: np.ndarray, hour) -> np.ndarray:
    """A 24-hour table read at (fractional, wrapping) clock hours."""
    h = np.mod(np.asarray(hour, np.float64), 24.0)
    i0 = np.floor(h).astype(np.int64)
    f = h - i0
    return table[i0] * (1 - f) + table[(i0 + 1) % 24] * f


class Sleep:
    def __init__(self, sim):
        self.sim = sim

    def init(self):
        P = self.sim.w.P
        for c, dt, fill in (("asleep", bool, False), ("in_bed", bool, False), ("chrono_set", bool, False),
                            ("out_late", bool, False), ("woke_today", bool, False)):
            P.add_internal(c, dt, fill)
        for c in ("sleep_on", "awake_since", "wake_at", "alarm_at", "alarm_for", "night_on"):
            P.add_internal(c, np.int64, -1)
        for c in ("slept_min", "sleep_debt"):
            P.add_internal(c, np.float32, 0.0)
        P.add_internal("first_next", np.int32, -1)     # tomorrow's first commitment (minute of tomorrow), −1 none
        self._chronotype(np.arange(P.n))
        # the world starts at 6 am with everyone present asleep since their usual bedtime
        self._settle_asleep(np.flatnonzero(P["present"][: P.n]))

    # ------------------------------------------------------------------ setup
    def _chronotype(self, ids: np.ndarray):
        sim = self.sim
        P, p = sim.w.P, sim.p
        if not len(ids):
            return
        z = lambda v: sim.z(v)[ids]      # noqa: E731
        married = P.is_("rel_status", "married")[ids]
        kids = P["children"][ids] > 0
        rng = sim.streams.gen("chronotype", 0, int(ids[0]) % 9973)
        tau = (p("sleep.chronotype.age") * (21 - P["age"][ids]) / 10 - p("sleep.chronotype.consc") * z("conscientiousness")
               + p("sleep.chronotype.sensation") * z("sensation_seeking") + p("sleep.chronotype.extra") * z("extraversion")
               + p("sleep.chronotype.gaming") * P["gaming"][ids] + p("sleep.chronotype.phone") * z("social_media_hours")
               - p("sleep.chronotype.married") * married - p("sleep.chronotype.kids") * kids
               + p("sleep.chronotype.sd") * rng.standard_normal(len(ids)))
        P["chronotype"][ids] = np.clip(tau, -4, 5).astype(np.float32)
        P.internal["chrono_set"][ids] = True

    def _need(self, ids: np.ndarray) -> np.ndarray:
        """Hours of sleep the body asks for: a little more than the person's usual sleep_hours (their habit, from
        ProvoStats), which already reflects the nights cut short by alarms and late nights (sleep.wake.need_gap)."""
        base = self.sim.w.P.internal["sleep_base"][ids].astype(np.float64)
        return np.clip(base + self.sim.p("sleep.wake.need_gap"), 4.5, 10.5)

    def _settle_asleep(self, ids: np.ndarray):
        """Put people to bed at their usual time last night (the world's first morning, arrivals)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        if not len(ids):
            return
        need = self._need(ids)
        now = self.now(0)
        wake = now + (60 + 60 * np.clip(P["chronotype"][ids], -2, 4) + 20 * sim.streams.normal("sleep_start", w.day, P.n)[ids])
        on = wake - 60 * need
        P.internal["asleep"][ids] = True
        P.internal["in_bed"][ids] = False
        P.internal["sleep_on"][ids] = on.astype(np.int64)
        P.internal["night_on"][ids] = on.astype(np.int64)
        P.internal["wake_at"][ids] = np.maximum(wake, now + 15).astype(np.int64)
        P.internal["awake_since"][ids] = -1
        P.internal["alarm_at"][ids] = -1
        P["bedtime"][ids] = np.clip((on - (w.day - 1) * 1440) / 60, 18, 34).astype(np.float32)

    # ------------------------------------------------------------------ time
    def now(self, b: int) -> int:
        """Absolute minute at the start of hour step b today."""
        return int(self.sim.w.day * 1440 + clock.START[b])

    def first_commitment(self, day: int) -> np.ndarray:
        """Minute of `day` each person's first fixed commitment starts (class, shift, church), −1 if none."""
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        wd = sim.cal.weekday(day)
        first = np.full(n, 10 ** 6, np.int64)
        # shifts
        s = P.internal["shift_start"][:n, wd].astype(np.int64)
        has = (s >= 0) & P["employed"][:n] & (not sim.cal.holiday(day))
        first = np.where(has, np.minimum(first, s), first)
        # classes
        acad = sim.systems.get("academics")
        if acad is not None and wd < 5 and len(acad.sec_days) and not sim.cal.holiday(day):
            secs = acad.stu_secs[:n] if acad.stu_secs.shape[0] >= n else None
            if secs is not None:
                ok = secs >= 0
                ss = np.maximum(secs, 0)
                cs, _ = sim.systems["activity"].class_times(ss.ravel())
                cs = cs.reshape(ss.shape).astype(np.int64)
                meets = ok & ((acad.sec_days[ss] & np.uint8(1 << wd)) > 0)
                cls = {s_: bool(sim.cal.term(s_, day)) and not sim.cal.no_class(s_, day) for s_ in ("BYU", "UVU")}
                term = np.where(P["school"][:n] == 1, cls["BYU"], cls["UVU"])
                meets &= (term & P["enrolled"][:n])[:, None]
                c_first = np.where(meets, cs, 10 ** 6).min(axis=1)
                first = np.minimum(first, c_first)
        # church
        if wd == 6:
            f = sim.systems["faith"]
            go = (P["lds_member"][:n] & (P.internal["attend_prob"][:n] >= 0.5)) if day != w.day else (
                f.attending_today[:n] | f.attending_other[:n])
            first = np.where(go, np.minimum(first, f.meeting_start(np.arange(n))), first)
        return np.where(first < 10 ** 6, first, -1).astype(np.int32)

    # ------------------------------------------------------------------ the day
    def plan_day(self):
        """Morning: today's alarms (for those still asleep) and tomorrow's first commitment (for tonight's bedtimes)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        new = np.flatnonzero(~P.internal["chrono_set"][:n])
        if len(new):
            self._chronotype(new)
            P.internal["awake_since"][new] = self.now(0)
            P["bedtime"][new] = 23.5
            P["wake_time"][new] = 7.5
        first = self.first_commitment(w.day)
        asleep = P.internal["asleep"][:n] | P.internal["in_bed"][:n]
        has = asleep & (first >= 0)
        start = w.day * 1440 + first.astype(np.int64)
        P.internal["alarm_for"][:n] = np.where(has, start, -1)
        P.internal["alarm_at"][:n] = np.where(has, start - PREP, -1)
        P.internal["first_next"][:n] = self.first_commitment(w.day + 1)
        P.internal["woke_today"][:n] = False

    def resting(self) -> np.ndarray:
        """In bed (asleep, or lying awake trying to sleep)."""
        P = self.sim.w.P
        return P.internal["asleep"][: P.n] | P.internal["in_bed"][: P.n]

    def step(self, b: int) -> np.ndarray:
        """Start of hour b: alarms and natural waking, those lying awake falling asleep; returns who is in bed now."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        I = P.internal
        t0 = self.now(b)
        t1 = t0 + 60
        pres = P["present"][:n]
        asleep, in_bed = I["asleep"][:n], I["in_bed"][:n]
        # ---- natural waking
        wake = asleep & (I["wake_at"][:n] < t1)
        # ---- alarms ringing this hour (before they would wake on their own)
        ring = asleep & ~wake & (I["alarm_at"][:n] >= 0) & (I["alarm_at"][:n] < t1)
        got_up = np.zeros(n, bool)
        if ring.any():
            r = np.flatnonzero(ring)
            slept_h = (I["alarm_at"][r] - I["sleep_on"][r]) / 60
            need = self._need(r)
            depressed = P["depressive_episode"][r] if "depressive_episode" in P.cols else 0
            works = I["shift_start"][r, int(w.env["weekday"])] >= 0
            work_first = works & (np.abs(I["shift_start"][r, int(w.env["weekday"])].astype(np.int64) + w.day * 1440
                                         - I["alarm_for"][r]) < 5)
            pu = expit(p("sleep.wake.base") + p("sleep.wake.consc") * sim.z("conscientiousness")[r]
                       + p("sleep.wake.shift") * work_first - p("sleep.wake.debt") * np.clip(need - slept_h, 0, 6)
                       - p("sleep.wake.depressed") * depressed)
            up = sim.streams.gen("alarm", w.day, b).random(len(r)) < pu
            got_up[r[up]] = True
            # snooze: it rings again next hour, until half an hour after the thing has started
            snooze = r[~up]
            nxt = I["alarm_at"][snooze] + 60
            I["alarm_at"][snooze] = np.where(nxt < I["alarm_for"][snooze] + 30, nxt, -1)
        woke = (wake | got_up) & pres
        if woke.any():
            k = np.flatnonzero(woke)
            at = np.where(got_up[k], I["alarm_at"][k], I["wake_at"][k])
            at = np.clip(at, t0, t1)
            I["slept_min"][k] += (at - t0).astype(np.float32)
            I["asleep"][k] = False
            I["awake_since"][k] = at
            I["alarm_at"][k] = -1
            main = ~I["woke_today"][k] & ((I["sleep_on"][k] == I["night_on"][k]))
            P["wake_time"][k[main]] = ((at[main] - w.day * 1440) / 60).astype(np.float32)
            I["woke_today"][k[main]] = True
        # ---- still asleep the whole hour
        still = I["asleep"][:n] & pres & ~woke
        I["slept_min"][:n][still] += 60
        # ---- lying awake: fall asleep this hour?
        lying = in_bed & ~I["asleep"][:n] & pres
        if lying.any():
            self._try_sleep(np.flatnonzero(lying), b)
        return self.resting()

    def to_bed(self, ids: np.ndarray, b: int):
        """Those who chose sleep this hour go to bed (and may fall asleep within it)."""
        P = self.sim.w.P
        if not len(ids):
            return
        P.internal["in_bed"][ids] = True
        self._try_sleep(ids, b)

    def _try_sleep(self, ids: np.ndarray, b: int):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        I = P.internal
        t0 = self.now(b)
        awake_h = (t0 - I["awake_since"][ids]) / 60
        coffee = P["coffee"][ids] > 0 if "coffee" in P.cols else np.zeros(len(ids), bool)
        pf = expit(p("sleep.onset.base") - p("sleep.onset.stress") * (P["stress"][ids] - 0.4)
                   - p("sleep.onset.anxiety") * (P["anxiety"][ids] - 0.3) - p("sleep.onset.caffeine") * coffee
                   + p("sleep.onset.tired") * (awake_h - 16) / 4)
        rng = sim.streams.gen("fall_asleep", w.day, b)
        ok = rng.random(len(ids)) < pf
        a = ids[ok]
        if not len(a):
            return
        on = np.full(len(a), t0 + 30, np.int64)
        I["asleep"][a] = True
        I["in_bed"][a] = False
        I["sleep_on"][a] = on
        I["slept_min"][a] += 30
        mod = int(clock.START[b]) % 1440
        nap = NAP_FROM <= mod < NAP_TO
        if nap:
            hrs = 1.0 + rng.random(len(a))
        else:
            need = self._need(a)
            hrs = need + p("sleep.wake.catch_up") * np.clip(I["sleep_debt"][a], 0, 6) + 0.5 * rng.standard_normal(len(a))
            hrs = np.clip(hrs, 4.0, 12.5)
            I["night_on"][a] = on
            # hours after midnight of the evening before (minutes of the day already run past 1440 after midnight;
            # going to bed after 6 am, after a night up, is the previous evening's bedtime too)
            late_morning = (on - w.day * 1440) < 9 * 60
            P["bedtime"][a] = np.clip(np.where(late_morning, (on - (w.day - 1) * 1440) / 60, (on - w.day * 1440) / 60), 18, 34).astype(np.float32)
            # tomorrow's alarm (after midnight it is still "tomorrow": the next simulated day)
            fn = I["first_next"][a].astype(np.int64)
            al = np.where(fn >= 0, (w.day + 1) * 1440 + fn, -1)
            I["alarm_for"][a] = al
            I["alarm_at"][a] = np.where(al >= 0, al - PREP, -1)
        I["wake_at"][a] = (on + 60 * hrs).astype(np.int64)

    def utility(self, idx: np.ndarray, b: int) -> np.ndarray:
        """The pull of going to bed this hour for `idx` (activity's sleep option)."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        I = P.internal
        mid = self.now(b) + 30
        awake_h = (mid - I["awake_since"][idx]) / 60
        hour = clock.HOUR[b] + 0.5
        C = curve(CIRC, hour - P["chronotype"][idx])
        fn = I["first_next"][idx].astype(np.int64)
        # the next morning's alarm: tomorrow's first commitment (for the small hours, still "tomorrow")
        nxt = np.where(fn >= 0, (w.day + 1) * 1440 + fn - PREP, -1)
        avail = (nxt - mid) / 60
        short = np.where(fn >= 0, np.clip(self._need(idx) - avail, -2, 4), -1.0)
        proc = np.clip(sim.z("social_media_hours")[idx] - sim.z("self_control")[idx], 0, None) / 2
        # a nap takes more than ordinary tiredness: mostly the short-sleepers and the run-down
        m = clock.START[b] % 1440 + 30
        nap = (m >= NAP_FROM) & (m < NAP_TO)
        return (p("sleep.choice.base") - p("sleep.choice.nap") * nap + p("sleep.choice.debt") * np.clip(I["sleep_debt"][idx], 0, 6)
                + p("sleep.choice.pressure") * (awake_h - 16) / 2 + p("sleep.choice.circadian") * C
                + p("sleep.choice.alarm") * short + p("sleep.choice.fatigue") * P["fatigue"][idx]
                + p("sleep.choice.ill") * P["ill"][idx] - p("sleep.choice.procrastinate") * proc)

    def end_of_day(self):
        """6 am: what they slept in the day just ended becomes sleep_hours; debt carries over."""
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        I = P.internal
        pres = P["present"][:n]
        need = self._need(np.arange(n))
        slept = I["slept_min"][:n] / 60
        newborn = I["newborn_until"][:n] > w.day if "newborn_until" in I else np.zeros(n, bool)
        hours = np.where(pres, np.clip(slept - 1.2 * newborn + sim.nudge("sleep"), 0, 14), need)
        P["sleep_hours"] = np.clip(hours, 0, 14).astype(np.float32)
        I["sleep_debt"][:n] = np.clip(0.6 * I["sleep_debt"][:n] + (need - hours), 0, 12).astype(np.float32)
        a = 1 / 7
        P["late_nights_week"] = ((1 - a) * P["late_nights_week"][:n] + a * 7 * I["out_late"][:n]).astype(np.float32)
        I["slept_min"][:n] = 0
        I["out_late"][:n] = False
        # people away (travelling, home for the holidays) aren't simulated hour by hour: they come back rested
        gone = ~pres
        I["asleep"][:n][gone] = False
        I["in_bed"][:n][gone] = False
        I["awake_since"][:n][gone] = self.now(0) + 1440

"""The mind: a bridge between state and behavior.

Before this layer, each behavioral subsystem turned state straight into action
(``loneliness × traits → visit a friend``). The mind inserts the steps people actually go through,
kept explicit, vectorized and inspectable:

    traits / identity ─► how much each concern matters (cares_*)            between-person, slow
    felt states       ─► how fulfilled each concern feels (sat)              within-person
                      ─► drives = cares × unmet; the top priority            shared currency for behavior
    experience        ─► expectations (asks accepted, warmth of people),     learned (Rescorla–Wagner)
                         academic confidence (mastery experiences)
    the network       ─► what they *perceive*: support available, what       can be wrong, and behavior
                         friends believe, whether a crush likes them back     follows the perception

Behavior reads drives, expectations and perceptions (activity choice, reaching out, hosting, asking out,
studying, faith influence). Coping (coping.py), memory (memory.py) and intentions (plans.py) build on
these pieces.

Evidence: the motive set is a structural choice (informed by self-determination theory's relatedness /
competence and the fundamental-motives literature); expectation learning, self-efficacy, perceived
support, the liking gap, projection and pluralistic ignorance are established findings whose strengths
here are hypothetical and carry ranges (config/mechanisms/07_mind.yaml).
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit, logit

from ..core import pair_normal
from ..state import CTX_ID

MOTIVES = ["connection", "partnership", "achievement", "security", "faith", "rest", "fun", "health"]
MOTIVE_LABEL = {"connection": "friends & belonging", "partnership": "love & partnership", "achievement": "school & career",
                "security": "money & security", "faith": "faith & integrity", "rest": "rest", "fun": "fun & novelty",
                "health": "fitness & health"}
# activity codes (activity.ACT) that count as fun outings, workouts and social events
_FUN = (6, 7, 8, 9, 12)          # gathering, date, venue, outdoors, club
_SOCIAL = (6, 10, 12)            # gathering, ward activity, club/team
_GYM = 5
# contexts whose interaction quality teaches people what to expect from social situations
SOCIAL_CTX = ("gathering", "venue", "dance", "hangout", "complex", "club", "team", "fhe", "unit", "outdoors")


class Mind:
    def __init__(self, sim):
        self.sim = sim
        self.cares_mean: dict[str, float] = {}

    # ------------------------------------------------------------------ setup
    def init(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        for c, dt, f in (("fun_today", np.uint8, 0), ("gym_today", np.uint8, 0), ("social_today", np.bool_, False),
                         ("fun_week", np.float32, 2.0), ("gym_week", np.float32, 1.0), ("social_pref", np.float32, 5.0),
                         ("soc_v_sum", np.float32, 0.0), ("soc_v_n", np.float32, 0.0), ("lens", np.float32, 0.0),
                         ("mind_ready", np.bool_, False)):
            P.add_internal(c, dt, f)
        self.social_ctx = np.zeros(32, bool)
        for c in SOCIAL_CTX:
            if c in CTX_ID:
                self.social_ctx[CTX_ID[c]] = True
        self.setup(np.arange(P.n))

    def setup(self, ids: np.ndarray):
        """Starting values for people entering the world (the initial population or new arrivals)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        if len(ids) == 0:
            return
        z = sim.z
        P.internal["social_pref"][ids] = P["social_events_month"][ids]
        P.internal["fun_week"][ids] = 1.0 + 0.25 * np.clip(P["social_events_month"][ids], 0, 20)
        P.internal["gym_week"][ids] = np.clip(P["workouts_week"][ids], 0, 7)
        # a stable personal lens on social support (some people read the same network as warmer than others)
        P.internal["lens"][ids] = pair_normal(w.seed, ids, ids, 4401, directed=True)
        noise = pair_normal(w.seed, ids, np.full(len(ids), 7), 4402, directed=True)
        P.cols["expect_accept"][ids] = expit(0.45 + 0.35 * z("attractiveness")[ids] - 0.35 * z("rejection_sensitivity")[ids]
                                             + 0.2 * z("extraversion")[ids] + 0.3 * noise)
        P.cols["expect_social"][ids] = expit(0.9 + 0.35 * z("extraversion")[ids] - 0.45 * z("social_anxiety")[ids]
                                             - 0.2 * z("neuroticism")[ids] + 0.25 * noise)
        gpa = np.nan_to_num(P["gpa"][ids], nan=3.3)
        P.cols["self_eff_academic"][ids] = expit(0.3 + 0.6 * z("academic_ability")[ids] + 0.25 * z("conscientiousness")[ids]
                                                 - 0.25 * z("neuroticism")[ids] + 0.6 * (gpa - 3.3)
                                                 + 0.3 * pair_normal(w.seed, ids, np.full(len(ids), 9), 4403, directed=True))
        P.cols["rumination"][ids] = expit(-0.4 + 0.9 * z("neuroticism")[ids] - 0.2 * z("self_control")[ids]
                                          + 0.3 * pair_normal(w.seed, ids, np.full(len(ids), 11), 4404, directed=True))
        P.cols["social_events_month"][ids] = np.clip(P["social_events_month"][ids], 0, 40)
        self._cares(ids, blend=1.0)
        P.internal["mind_ready"][ids] = True
        if w.E.n and len(ids) == P.n:
            self.weekly_perception()

    # ------------------------------------------------------------------ motives
    def _cares(self, ids: np.ndarray, blend: float):
        """How much each concern matters: slow targets from traits, values and circumstances."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        z = lambda v: sim.z(v)[ids]  # noqa: E731
        married = P.is_("rel_status", "married")[ids]
        partnered = P.isin("rel_status", ["dating", "engaged", "married"])[ids]
        kids = P["children"][ids] > 0
        lds_active = P["lds_member"][ids] & (P["activity"][ids] == 3)
        age = P["age"][ids]
        age_norm = np.clip((age - 19.5) / 3, 0, 1) * np.clip((31 - age) / 5, 0, 1)
        sp = P.internal["social_pref"][ids]
        sp_z = (np.log1p(sp) - 1.7) / 0.6
        enrolled = P["enrolled"][ids]
        tgt = {
            "connection": 0.45 + 0.45 * z("extraversion") + 0.2 * z("agreeableness") + 0.2 * z("attachment_anxiety")
            - 0.25 * z("attachment_avoidance") + 0.15 * sp_z,
            "partnership": -1.0 + 1.1 * (P["wants_relationship"][ids] - 2.5) / 1.5
            + p("mind.importance.marriage_norm") * lds_active * age_norm * w.env.get("marriage_norm", 1.0) + 1.2 * partnered,
            "achievement": -0.1 + 0.5 * z("conscientiousness") + 0.25 * z("academic_ability") + 0.4 * enrolled,
            "security": -0.3 - 0.3 * z("parent_income") + 0.6 * married + 0.5 * kids + 0.2 * z("neuroticism") + 0.15 * z("conscientiousness"),
            "faith": np.where(P["lds_member"][ids], -2.2 + 3.0 * P["religious_identity"][ids] + 1.5 * P["faith_belief"][ids],
                              -2.5 + 4.0 * P["own_religiosity"][ids]),
            "rest": 0.3 + 0.25 * z("neuroticism") - 0.15 * z("conscientiousness") + 0.4 * kids,
            "fun": -0.1 + 0.45 * z("sensation_seeking") + 0.25 * z("openness") + 0.25 * z("extraversion") + 0.2 * sp_z - 0.3 * married,
            "health": -1.5 + 0.9 * np.log1p(P["workouts_week"][ids]) + 0.2 * z("conscientiousness") + 0.4 * P["sports"][ids],
        }
        for m in MOTIVES:
            col = P.cols[f"cares_{m}"]
            nb = self.sim.nudge(f"cares:{m}")   # a What-if that changes what people value
            target = np.clip(expit(tgt[m] + (nb[ids] if not np.isscalar(nb) else nb)), 0.02, 0.98)
            col[ids] = (1 - blend) * col[ids] + blend * target

    def satisfactions(self) -> dict[str, np.ndarray]:
        """How fulfilled each concern feels (0-1), read from felt states and recent experience."""
        w = self.sim.w
        P, env = w.P, w.env
        n = P.n
        in_couple = P.isin("rel_status", ["dating", "engaged", "married"])
        in_term = P["enrolled"] & np.where(P["school"] == 1, bool(env.get("term_BYU")), bool(env.get("term_UVU")))
        rs = np.nan_to_num(P["relationship_satisfaction"], nan=0.6)
        lds = P["lds_member"]
        ident = np.where(lds, P["religious_identity"], P["own_religiosity"])
        practice = np.where(lds, 0.6 * P["attend_rate"] + 0.4 * np.clip(P["private_practice"], 0, 1), P["service_attend"])
        cf, ch = P["cares_fun"], P["cares_health"]
        return {
            "connection": 1 - P["loneliness"],
            "partnership": np.where(in_couple, 0.35 + 0.65 * rs, 1 - P["romantic_longing"]),
            "achievement": np.where(in_term, np.clip(1 - P["academic_pressure"] + 0.4 * (P["self_eff_academic"] - 0.5), 0, 1),
                                    np.where(P["employed"] | P["enrolled"], 0.7, 0.45)),
            "security": 1 - P["financial_stress"],
            "faith": np.clip(1.0 - P["guilt"] - 0.5 * np.clip(ident - practice, 0, 1) - 0.4 * P["outsider"] * ident, 0, 1),
            "rest": 1 - P["fatigue"],
            # outings and gym visits per week relative to the person's own appetite (most exercise happens outside
            # the gym blocks the model tracks, so the reference scales with their survey workout habit)
            "fun": np.clip(P.internal["fun_week"][:n] / (1.5 + 6.0 * cf), 0, 1),
            "health": np.clip(0.3 + 0.7 * P.internal["gym_week"][:n] / (0.15 + 0.3 * P["workouts_week"] * (0.5 + ch)), 0, 1),
        }

    # ------------------------------------------------------------------ observation hooks (called by other systems)
    def observe_block(self, act: np.ndarray, ctype: np.ndarray, fresh: np.ndarray | None = None,
                      social: np.ndarray | None = None):
        """Activity system: what everyone did this block (outings, workouts, social events). `fresh` marks people who
        started something new this block (an outing that carries on into the late evening counts once); `social`
        marks people at a social occasion (a dinner, a party, a dance)."""
        P = self.sim.w.P
        n = P.n
        new = np.ones(n, bool) if fresh is None else fresh
        P.internal["fun_today"][:n] += (np.isin(act, _FUN) & new).astype(np.uint8)
        P.internal["gym_today"][:n] += ((act == _GYM) & new).astype(np.uint8)
        soc = np.isin(act, _SOCIAL) | (ctype == CTX_ID["dance"])
        P.internal["social_today"][:n] |= soc if social is None else (soc | social)

    def observe_interactions(self, a: np.ndarray, b: np.ndarray, ctx: np.ndarray, v: np.ndarray):
        """Encounters: valence of interactions in social settings, to learn what people are like."""
        P = self.sim.w.P
        soc = self.social_ctx[ctx]
        if not soc.any():
            return
        n = P.n
        x = np.r_[a[soc], b[soc]]
        vv = np.r_[v[soc], v[soc]]
        P.internal["soc_v_sum"][:n] += np.bincount(x, weights=vv, minlength=n)[:n]
        P.internal["soc_v_n"][:n] += np.bincount(x, minlength=n)[:n]

    # ------------------------------------------------------------------ daily
    def daily(self):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        new = np.where(P["present"] & ~P.internal["mind_ready"][:n])[0]
        if len(new):
            self.setup(new)
        a7, a30 = 1 / 7, 1 / 30
        P.internal["fun_week"][:n] = (1 - a7) * P.internal["fun_week"][:n] + P.internal["fun_today"][:n] * a7 * 7
        P.internal["gym_week"][:n] = (1 - a7) * P.internal["gym_week"][:n] + P.internal["gym_today"][:n] * a7 * 7
        pres = P["present"]
        P["social_events_month"] = np.where(pres, (1 - a30) * P["social_events_month"] + 30 * a30 * P.internal["social_today"][:n],
                                            P["social_events_month"]).astype(np.float32)
        # what people are like: learn the warmth of social situations from today's interactions
        cnt = P.internal["soc_v_n"][:n]
        has = cnt > 0
        if has.any():
            m = P.internal["soc_v_sum"][:n][has] / cnt[has]
            signal = 0.5 + 0.5 * np.tanh(m)
            cur = P["expect_social"][has]
            # socially anxious people weigh the bad moments more (attention bias to social threat)
            sa = np.clip(sim.z("social_anxiety")[has], 0, None)
            alpha = p("mind.expect_social.alpha") * np.minimum(cnt[has], 4) / 4 * np.where(signal < cur, 1 + p("mind.expect_social.threat_bias") * sa, 1.0)
            P.cols["expect_social"][np.where(has)[0]] = np.clip(cur + alpha * (signal - cur), 0.02, 0.98)
        for c in ("fun_today", "gym_today", "soc_v_sum", "soc_v_n"):
            P.internal[c][:n] = 0
        self.last_social = P.internal["social_today"][:n].copy()
        P.internal["social_today"][:n] = False
        self.update_drives()

    def update_drives(self):
        """Felt fulfilment → drives (importance × unmet) → top priority."""
        P = self.sim.w.P
        n = P.n
        pres = P["present"]
        sat = self.satisfactions()
        P["sat_fun"] = sat["fun"].astype(np.float32)
        P["sat_health"] = sat["health"].astype(np.float32)
        D = np.zeros((len(MOTIVES), n), np.float32)
        for k, m in enumerate(MOTIVES):
            d = P[f"cares_{m}"] * (1 - np.clip(sat[m], 0, 1))
            P[f"drive_{m}"] = d.astype(np.float32)
            D[k] = d
        P["top_priority"] = np.argmax(D, axis=0).astype(np.uint8)
        self.cares_mean = {m: float(P[f"cares_{m}"][pres].mean()) if pres.any() else 0.5 for m in MOTIVES}

    def drives(self) -> np.ndarray:
        P = self.sim.w.P
        return np.stack([P[f"drive_{m}"] for m in MOTIVES])

    def social_pull(self):
        """(approach, withdraw, style): how strongly the connection drive pushes someone toward people or away.

        Replaces the old loneliness × trait split (Cacioppo & Hawkley 2009's approach/withdraw response) with the
        same split mediated by motive importance and learned expectations: lonely people who still expect
        warmth reach out; those who have learned to expect coldness pull back."""
        sim, P, p = self.sim, self.sim.w.P, self.sim.p
        style = expit(p("activity.loneliness_response.extraversion") * sim.z("extraversion")
                      - p("activity.loneliness_response.social_anxiety") * sim.z("social_anxiety")
                      - p("activity.loneliness_response.neuroticism") * sim.z("neuroticism")
                      + p("activity.loneliness_response.base"))
        drive = P["drive_connection"] / 0.55        # ≈ loneliness for someone who cares an average amount
        ex = P["expect_social"]
        approach = drive * style * (0.4 + 0.85 * ex)
        withdraw = drive * (1 - style) * (1.6 - 1.0 * ex)
        cop = self.sim.systems.get("coping")
        if cop is not None:
            a_c, w_c = cop.social_bias()
            approach, withdraw = approach + a_c, withdraw + w_c
        return approach, withdraw, style

    # ------------------------------------------------------------------ weekly
    def weekly(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        ids = np.where(P["present"])[0]
        self._cares(ids, blend=sim.p("mind.importance.drift"))
        self.update_drives()            # importance moved: keep drives consistent with it
        self.weekly_perception()
        self.weekly_memory()

    def weekly_memory(self):
        """Forget what has faded; summarize what each person still carries (count, tone, negative load)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        decay = sim.p("memory.forgetting.decay")
        sim.memory.prune(w.day, decay)
        cnt, tone, load = sim.memory.per_agent(P.n, w.day, decay)
        P["n_memories"] = cnt
        P["memory_tone"] = np.clip(tone, -1, 1).astype(np.float32)
        if "neg_load" in P.internal:
            P.internal["neg_load"][: P.n] = load

    def weekly_perception(self):
        """Perceived vs actual support, and perceived vs actual friends' belief (pluralistic ignorance)."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        n = P.n
        if E.n == 0:
            return
        lo, hi = E.endpoints()
        pres = P["present"]
        st = E["stage"]
        clo = E["closeness"].astype(np.float64)
        lik = np.clip(E["liking"], 0, 1).astype(np.float64)
        # first time through, intimacy is assumed to follow closeness (later it is earned through disclosure)
        disc = E["disclosure"]
        fresh = (disc == 0) & (st >= 2)
        if fresh.any():
            E.cols["disclosure"][np.where(fresh)[0]] = (clo[fresh] ** 2).astype(np.float32)
        # ---- support: actual (close, warm, present ties; past help counts) and perceived (through a personal lens)
        m = (st >= 3) & pres[lo] & pres[hi]
        wt = clo[m] * lik[m] * (1 + 0.5 * np.clip(E["support"][m], 0, 2))
        raw = np.bincount(lo[m], weights=wt, minlength=n) + np.bincount(hi[m], weights=wt, minlength=n)
        actual = 1 - np.exp(-raw / 1.2)
        P["support_actual"] = actual.astype(np.float32)
        bias = (-p("mind.perceived_support.neuroticism") * sim.z("neuroticism")
                - p("mind.perceived_support.attachment") * sim.z("attachment_anxiety")
                - p("mind.perceived_support.loneliness") * (P["loneliness"] - 0.33)
                + p("mind.perceived_support.lens") * P.internal["lens"][:n])
        r = p("mind.perceived_support.reality")
        lens = r * logit(np.clip(actual, 0.03, 0.97)) + (1 - r) * 0.4 + bias
        P["perceived_support"] = np.where(pres, expit(lens), P["perceived_support"]).astype(np.float32)
        # ---- what friends believe: expressed belief (concealment toward the local norm) vs real belief (confided)
        belief = P["faith_belief"].astype(np.float64)
        lds = P["lds_member"]
        pressure = 0.35 + 0.55 * P["perceived_norm"]
        lam = p("mind.pluralistic_ignorance.concealment")
        # only the deviant side conceals: doubters present more belief than they hold; the devout do not understate
        expressed = np.where(lds, belief + lam * (1 - P["moral_autonomy"]) * np.clip(pressure - belief, 0, None), belief)
        f = (st >= 2) & pres[lo] & pres[hi]
        c = clo[f] + 0.05
        d = np.clip(E["disclosure"][f], 0, 1).astype(np.float64)
        a_, b_ = lo[f], hi[f]
        seen_b = d * belief[b_] + (1 - d) * expressed[b_]   # what a_ sees of b_
        seen_a = d * belief[a_] + (1 - d) * expressed[a_]
        num = np.bincount(a_, weights=c * seen_b, minlength=n) + np.bincount(b_, weights=c * seen_a, minlength=n)
        tru = np.bincount(a_, weights=c * belief[b_], minlength=n) + np.bincount(b_, weights=c * belief[a_], minlength=n)
        den = np.bincount(a_, weights=c, minlength=n) + np.bincount(b_, weights=c, minlength=n)
        has = den > 0
        P["perceived_friend_belief"] = np.where(has, num / np.maximum(den, 1e-9), belief).astype(np.float32)
        P["friend_belief_actual"] = np.where(has, tru / np.maximum(den, 1e-9), belief).astype(np.float32)

    # ------------------------------------------------------------------ romantic perception (called by encounters/romance)
    def init_beliefs(self, eix: np.ndarray, lo: np.ndarray, hi: np.ndarray):
        """New acquaintances: a first read of the other's interest — projection of one's own attraction,
        the liking gap with strangers, and men's tendency to over-read women's interest."""
        E = self.sim.w.E
        for src, dst, col in ((lo, hi, "bel_lh"), (hi, lo, "bel_hl")):
            own = np.where(src == lo, E["att_lh"][eix], E["att_hl"][eix])
            E.cols[col][eix] = np.clip(self._read(src, dst, own, own * 0.0, np.zeros(len(eix))), -1, 1)

    def _read(self, src, dst, own, signal, n_inter):
        P, p = self.sim.w.P, self.sim.p
        pi = p("mind.romantic_perception.projection")
        gap = -p("mind.romantic_perception.liking_gap") * np.exp(-n_inter / 8.0)
        male_over = p("mind.romantic_perception.male_overperception") * (P.is_("sex", "M")[src] & P.is_("sex", "F")[dst])
        return (1 - pi) * signal + pi * own + gap + male_over

    def update_beliefs(self, idx: np.ndarray, a: np.ndarray, b: np.ndarray, eta: float, block: int = 0, noisy: bool = True):
        """Each interaction is a noisy signal of the other's real attraction; beliefs move toward the read."""
        sim, w = self.sim, self.sim.w
        E = w.E
        if len(idx) == 0:
            return
        rng = sim.streams.gen("belief", w.day, block)
        n_inter = E["n_inter"][idx].astype(float)
        for src, dst in ((a, b), (b, a)):
            own = E.attraction_from(idx, src)
            actual = E.attraction_from(idx, dst)
            sd = 0.35 * np.exp(0.3 * sim.z("social_anxiety")[src]) if noisy else 0.0
            signal = actual + sd * rng.standard_normal(len(idx))
            cur = E.belief_from(idx, src)
            E.set_belief_from(idx, src, np.clip(cur + eta * (self._read(src, dst, own, signal, n_inter) - cur), -1, 1).astype(np.float32))

    def reveal(self, idx: np.ndarray, src: np.ndarray, dst: np.ndarray, weight: float = 1.0):
        """A clear signal (a yes, a no, a kiss): src's belief moves to dst's actual attraction."""
        E = self.sim.w.E
        cur = E.belief_from(idx, src)
        actual = E.attraction_from(idx, dst)
        E.set_belief_from(idx, src, (cur + weight * (actual - cur)).astype(np.float32))

    # ------------------------------------------------------------------ learning hooks
    def learn_ask(self, askers: np.ndarray, accepted: np.ndarray):
        """Rescorla–Wagner update of the expected chance of a yes; rejection-sensitive people learn more from a no."""
        sim, P, p = self.sim, self.sim.w.P, self.sim.p
        if len(askers) == 0:
            return
        cur = P["expect_accept"][askers]
        rs = np.clip(sim.z("rejection_sensitivity")[askers], 0, None)
        alpha = np.where(accepted, p("mind.expect_accept.alpha"), p("mind.expect_accept.alpha") * (1 + p("mind.expect_accept.rs_asymmetry") * rs))
        P.cols["expect_accept"][askers] = np.clip(cur + alpha * (accepted.astype(float) - cur), 0.03, 0.97)

    def learn_grades(self, ids: np.ndarray, term_gpa: np.ndarray):
        """Mastery experience: confidence moves toward where this term's grades placed them among classmates."""
        sim, P, p = self.sim, self.sim.w.P, self.sim.p
        if len(ids) < 2:
            return
        rank = np.argsort(np.argsort(term_gpa)) / max(len(ids) - 1, 1)
        cur = P["self_eff_academic"][ids]
        new = cur + p("mind.self_efficacy.alpha") * (rank - cur) - 0.02 * sim.z("neuroticism")[ids]
        P.cols["self_eff_academic"][ids] = np.clip(new, 0.02, 0.98)

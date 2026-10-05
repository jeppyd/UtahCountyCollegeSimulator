"""Structured interventions: the changes a What-if makes to its world.

An intervention changes the world at a time, for a population, with a ramp:

    {"id": "tuition_up", "name": "BYU tuition +20%", "target_type": "world", "target": "tuition_byu",
     "op": "mul", "value": 1.2, "start_day": 30, "duration_days": null, "ramp_days": 0,
     "population": null, "confidence": "hypothetical", "description": "..."}

target_type
  world    – an environment variable (env[...]): policy switches, norms, prices, weather (re-applied daily; reverts)
  param    – a mechanism parameter "<mechanism id>.<param>" (re-applied daily; reverts when the duration ends)
  agent    – a person variable for a filtered population (applied once at start; a lasting change to who people are)
  offset   – a persistent nudge on a channel for a filtered population while active (ramp and duration honoured,
             population re-evaluated weekly): a composed feeling (state units), church attendance / dating motivation /
             practice adoption / motive importance (logit), free-time choices (utility), sleep or study (hours)
  event    – inject a registered event type (an impulse: appraisal, feelings, memories, coping) into a cohort
  shock    – a custom event with its own label and effects on feelings ("Helaman Halls burned down")
  close    – close a housing complex (residents are rehoused under the housing rules) or venues; reopens at the end
  place    – change a complex's rent, beds, quality or contracted status
  practice – a new behavior that spreads by social contagion ("beards catch on at BYU"), with feelings for adopters
  venue    – adds a new venue (a new business opening) {"vtype": ..., "lon": ..., "lat": ..., "name": ...}

Interventions never touch the shared registry; parameter changes live in the run's ParamSet. Every random choice an
intervention makes uses its own stream or a stable hash, so the Original universe's draws never move.
"""
from __future__ import annotations

import copy
import zlib
from pathlib import Path

import numpy as np
import yaml

PRESETS = Path(__file__).resolve().parents[1] / "config" / "interventions.yaml"

STATES = ("mood", "stress", "loneliness", "anxiety", "belonging", "self_esteem", "guilt", "fatigue", "purpose",
          "financial_stress", "academic_pressure", "romantic_longing")
CHOICE_OPTIONS = ("home", "campus", "gym", "eat_out", "outdoors", "dance", "visit_friends", "complex_hangout")
MOTIVES = ("connection", "partnership", "achievement", "security", "faith", "rest", "fun", "health")
ADOPTABLE = ("coffee", "alcohol", "pickleball", "dating_app")
# offset channel -> (units, plausible bound on |value|, what it moves)
OFFSET_CHANNELS: dict[str, tuple[str, float, str]] = {
    **{s: ("state", 0.25, f"the felt {s.replace('_', ' ')} (0–1 scale), every night") for s in STATES},
    "attend": ("logit", 3.0, "probability of attending church next Sunday (LDS members)"),
    "dating": ("logit", 3.0, "dating motivation (asking out, accepting, app use)"),
    **{f"adopt:{k}": ("logit", 4.0, f"weekly chance of taking up {k.replace('_', ' ')}") for k in ADOPTABLE},
    **{f"cares:{m}": ("logit", 2.0, f"how much people care about {m} (motive importance, drifts weekly)") for m in MOTIVES},
    **{f"choice:{o}": ("utility", 3.0, f"free-time pull toward {o.replace('_', ' ')}") for o in CHOICE_OPTIONS},
    "sleep": ("hours", 3.0, "nightly sleep hours"),
    "study": ("hours", 15.0, "weekly study-hours target (enrolled students in term)"),
}
# registered event types that are pure impulses (safe to inject without the emitting system's bookkeeping)
INJECTABLE = ("family_crisis", "death_in_family", "car_accident", "financial_hardship", "hosted_gathering",
              "spiritual_experience", "faith_challenge", "exam_failure", "academic_success", "illness",
              "bishop_confession", "ghosted")
VISITED_VTYPES = ("restaurant", "cafe", "soda_shop", "dessert", "gym", "park", "trailhead", "overlook", "dance",
                  "cinema_theatre", "museum", "recreation", "stadium")


def load_presets() -> dict:
    return yaml.safe_load(PRESETS.read_text(encoding="utf-8"))["interventions"]


def expand(spec: dict | str) -> list[dict]:
    """A preset id or a spec dict -> list of atomic intervention dicts (presets may bundle several)."""
    presets = load_presets()
    if isinstance(spec, str):
        spec = {"preset": spec}
    if "preset" in spec:
        base = copy.deepcopy(presets[spec["preset"]])
        overrides = {k: v for k, v in spec.items() if k != "preset"}
        parts = base.pop("parts", None)
        if parts:
            out = []
            for p in parts:
                q = {**{k: v for k, v in base.items() if k not in ("parts",)}, **p, **overrides}
                q.setdefault("id", spec["preset"])
                out.append(q)
            return out
        base.update(overrides)
        base.setdefault("id", spec["preset"])
        return [base]
    return [spec]


class InterventionManager:
    def __init__(self, sim, specs: list):
        self.sim = sim
        self.items: list[dict] = []
        self._applied_agent: set[int] = set()   # one-shot items already started
        self._ended: set[int] = set()            # closures / place changes already reverted
        self._masks: dict[int, tuple[int, int, np.ndarray]] = {}   # item -> (day, n, population mask)
        self._revert: dict[int, dict] = {}
        self.practices: dict[int, dict] = {}     # item -> {"adopted": bool[n], "history": [(day, share, n_scope)]}
        self.exposed: dict[int, int] = {}        # item -> people reached (for the receipt)
        self._base_params = dict(sim.p.values)
        self._bias_day = -1
        self._bias_cache: dict[str, object] = {}
        for s in specs:
            for atom in expand(s):
                self.add(atom)

    def add(self, atom: dict) -> dict:
        atom.setdefault("start_day", 0)
        atom.setdefault("ramp_days", 0)
        atom.setdefault("duration_days", None)
        atom.setdefault("op", "set")
        self.items.append(atom)
        self._bias_day = -1
        return atom

    # ------------------------------------------------------------------ helpers
    def _ramp(self, it, day) -> float:
        s = it["start_day"]
        if day < s:
            return 0.0
        dur = it.get("duration_days")
        if dur is not None and day >= s + dur:
            return 0.0
        r = it.get("ramp_days") or 0
        return 1.0 if r <= 0 else min(1.0, (day - s + 1) / r)

    def _over(self, it, day) -> bool:
        dur = it.get("duration_days")
        return dur is not None and day >= it["start_day"] + dur

    @staticmethod
    def _combine(base, op, value, frac):
        if op == "set":
            if isinstance(base, (bool, np.bool_)) or isinstance(value, bool):
                return value if frac >= 0.5 else base
            return base + (value - base) * frac
        if op == "add":
            return base + value * frac
        if op == "mul":
            return base * (1 + (value - 1) * frac)
        raise ValueError(op)

    def _population(self, k: int, it: dict, include_absent: bool = False, refresh_days: int = 7) -> np.ndarray:
        """The item's population mask, re-evaluated weekly (arrivals, moves and status changes are picked up)."""
        from ..analysis.query import evaluate_filter
        sim = self.sim
        n = sim.w.P.n
        d0, n0, m = self._masks.get(k, (-999, -1, None))
        if m is None or n0 != n or sim.w.day - d0 >= refresh_days:
            m = evaluate_filter(sim.w, it.get("population"), sim=sim, include_absent=include_absent)
            self._masks[k] = (sim.w.day, n, m)
        return m

    def _pick(self, k: int, it: dict, mask: np.ndarray, tag: str = "pick") -> np.ndarray:
        share = float(it.get("share", 1.0))
        if share >= 1.0:
            return np.where(mask)[0]
        from ..analysis.query import hash_uniform
        u = hash_uniform(np.arange(len(mask)), f"whatif:{it.get('id', k)}:{k}:{tag}")
        return np.where(mask & (u < share))[0]

    # ------------------------------------------------------------------ daily application (06:00)
    def apply_world(self, env_base: dict, env: dict, day: int):
        for it in self.items:
            if it.get("target_type") != "world":
                continue
            f = self._ramp(it, day)
            if f > 0:
                env[it["target"]] = self._combine(env.get(it["target"], env_base.get(it["target"], 0.0)), it["op"], it["value"], f)

    def apply_params(self, day: int):
        p = self.sim.p
        touched = {}
        for it in self.items:
            if it.get("target_type") != "param":
                continue
            key = it["target"]
            f = self._ramp(it, day)
            base = touched.get(key, self._base_params[key])
            touched[key] = self._combine(base, it["op"], float(it["value"]), f) if f > 0 else base
        for k, v in touched.items():
            p.values[k] = v

    def apply_agents(self, day: int):
        """One-shot and recurring items: agent changes, venues, injected events and shocks, closures, place changes,
        practice seeding; and the end of anything with a duration."""
        sim = self.sim
        for k, it in enumerate(self.items):
            tt = it.get("target_type")
            if tt in ("world", "param", "offset") or day < it["start_day"]:
                continue
            if self._over(it, day):
                if tt in ("close", "place") and k in self._applied_agent and k not in self._ended:
                    self._end(k, it)
                    self._ended.add(k)
                continue
            if tt in ("event", "shock") and it.get("repeat_every"):
                every = max(int(it["repeat_every"]), 1)
                if (day - it["start_day"]) % every == 0:
                    self._inject(k, it, tag=f"r{day}")
                continue
            if k in self._applied_agent:
                continue
            self._applied_agent.add(k)
            if tt == "venue":
                sim.systems["activity"].add_venue(it["value"])
            elif tt == "agent":
                self._agent(k, it)
            elif tt in ("event", "shock"):
                self._inject(k, it)
            elif tt == "close":
                self._close(k, it)
            elif tt == "place":
                self._place(k, it)
            elif tt == "practice":
                self._seed_practice(k, it)

    def _agent(self, k, it):
        sim = self.sim
        P = sim.w.P
        ids = self._pick(k, it, self._population(k, it))
        col = P.cols[it["target"]]
        spec = P.specs[it["target"]]
        cur = col[ids].astype(np.float64)
        value = float(it["value"]) if not isinstance(it["value"], bool) else float(it["value"])
        new = self._combine(cur, it["op"], value, 1.0)
        if spec.range and spec.dtype in ("f4", "f8", "u1", "i2", "i4"):
            new = np.clip(new, spec.range[0], spec.range[1])
        if np.issubdtype(col.dtype, np.integer):
            new = np.rint(new)
        col[ids] = new.astype(col.dtype)
        self.exposed[k] = int(len(ids))
        sim.log.emit("intervention_exposure", sim.w.day, ids, value=k)   # log only: no memory, so no bookkeeping confound

    def _inject(self, k, it, tag: str = "pick"):
        """Impulse events into a cohort: a log-only exposure root, then the event with appraisal, effects, memory."""
        sim = self.sim
        ids = self._pick(k, it, self._population(k, it, refresh_days=1), tag)
        if not len(ids):
            return
        root = sim.log.emit("intervention_exposure", sim.w.day, ids, value=k)
        salt = 991 + (zlib.crc32(f"{it.get('id')}:{k}".encode()) & 0xFFFF)
        if it["target_type"] == "event":
            sim.emit(it["target"], ids, cause=root, mech="whatif.inject", scale=float(it.get("severity", 1.0)), salt=salt)
        else:
            effects = [{"var": e["var"], "mag": float(e["mag"]), "half_life": float(e.get("half_life", 14)),
                        "delay": int(e.get("delay", 0)), "sd": float(e.get("sd", 0.35)), "mods": e.get("mods") or {}}
                       for e in it.get("effects", [])]
            sim.emit("whatif_shock", ids, cause=root, mech="whatif.inject", value=k, effects=effects,
                     motive=it.get("motive"), valence=it.get("valence"), salience=float(it.get("salience", 0.55)),
                     scale=float(it.get("severity", 1.0)), salt=salt)
        self.exposed[k] = self.exposed.get(k, 0) + int(len(ids))

    # ------------------------------------------------------------------ places
    @staticmethod
    def _ref(target: str) -> tuple[str, object]:
        kind, _, rest = str(target).partition(":")
        return kind, (int(rest) if rest.lstrip("-").isdigit() else rest)

    def _close(self, k, it):
        sim = self.sim
        kind, ref = self._ref(it["target"])
        if kind == "complex":
            U = sim.w.units
            units = np.where(U.complex_id == ref)[0]
            self._revert[k] = {"kind": "complex", "units": units, "capacity": U.capacity[units].copy()}
            U.capacity[units] = 0
            P = sim.w.P
            res = np.where(np.isin(P["unit_id"], units))[0]
            self.exposed[k] = int(len(res))
            if len(res):
                root = sim.log.emit("intervention_exposure", sim.w.day, res, value=k)
                housing = sim.systems["housing"]
                married = P.is_("rel_status", "married")[res]
                partner = P["partner_id"][res]
                done = set()
                for j, i in enumerate(res):          # couples move together
                    if married[j] and partner[j] >= 0 and int(i) not in done:
                        pair = np.array([i, partner[j]])
                        done.update(int(x) for x in pair)
                        housing.place(pair, married=True, reason="moved", cause=int(root[j]))
                singles = np.array([i for j, i in enumerate(res) if int(i) not in done], dtype=np.int64)
                if len(singles):
                    housing.place(singles, reason="moved", cause=int(root[0]))
        elif kind in ("venue", "venue_type"):
            act = sim.systems["activity"]
            vids = np.array([ref]) if kind == "venue" else np.where(act.v_type == ref)[0]
            vids = vids[(vids >= 0) & (vids < len(act.v_type))]
            self._revert[k] = {"kind": "venue", "vids": vids, "types": act.v_type[vids].copy()}
            act.v_type = act.v_type.astype(object)
            act.v_type[vids] = "closed"
            act._build_trees()
            self.exposed[k] = int(len(vids))

    def _place(self, k, it):
        sim = self.sim
        kind, ref = self._ref(it["target"])
        if kind != "complex":
            return
        U = sim.w.units
        units = np.where(U.complex_id == ref)[0]
        attr = it.get("attr", "rent")
        col = {"rent": "rent_total", "beds": "capacity", "quality": "quality", "contracted": "contracted"}[attr]
        arr = getattr(U, col)
        self._revert[k] = {"kind": "place", "units": units, "col": col, "values": arr[units].copy()}
        if attr == "contracted":
            arr[units] = bool(it["value"])
        else:
            new = self._combine(arr[units].astype(np.float64), it.get("op", "mul"), float(it["value"]), 1.0)
            if attr == "beds":
                new = np.clip(np.rint(new), 0, 255)
            arr[units] = new.astype(arr.dtype)
        P = sim.w.P
        res = np.where(np.isin(P["unit_id"], units) & P["present"])[0]
        if attr == "rent" and len(res):
            sim.systems["housing"]._update_rent(res)
        self.exposed[k] = int(len(res))

    def _end(self, k, it):
        sim = self.sim
        r = self._revert.get(k)
        if not r:
            return
        if r["kind"] == "complex":
            sim.w.units.capacity[r["units"]] = r["capacity"]
        elif r["kind"] == "venue":
            act = sim.systems["activity"]
            act.v_type[r["vids"]] = r["types"]
            act._build_trees()
        elif r["kind"] == "place":
            getattr(sim.w.units, r["col"])[r["units"]] = r["values"]
            if r["col"] == "rent_total":
                P = sim.w.P
                res = np.where(np.isin(P["unit_id"], r["units"]) & P["present"])[0]
                if len(res):
                    sim.systems["housing"]._update_rent(res)

    # ------------------------------------------------------------------ practices (new behaviors that spread)
    def _practice_state(self, k) -> dict:
        n = self.sim.w.P.n
        st = self.practices.setdefault(k, {"adopted": np.zeros(n, bool), "history": []})
        if len(st["adopted"]) < n:
            st["adopted"] = np.concatenate([st["adopted"], np.zeros(n - len(st["adopted"]), bool)])
        return st

    def _seed_practice(self, k, it):
        sim = self.sim
        st = self._practice_state(k)
        scope = self._population(k, it)
        from ..analysis.query import hash_uniform
        u = hash_uniform(np.arange(len(scope)), f"whatif:{it.get('id', k)}:{k}:seed")
        seed = scope & (u < float(it.get("seed_share", 0.02)))
        st["adopted"] |= seed
        if seed.any():
            sim.log.emit("whatif_practice", sim.w.day, np.where(seed)[0], value=k, mech="whatif.practice")
        st["history"].append((sim.w.day, float(st["adopted"][scope].mean()) if scope.any() else 0.0, int(scope.sum())))

    def weekly_practices(self):
        """Weekly adoption and quitting, the norms system's complex contagion through friendships."""
        from scipy.special import expit
        sim = self.sim
        day = sim.w.day
        P = sim.w.P
        for k, it in enumerate(self.items):
            if it.get("target_type") != "practice" or day < it["start_day"] or k not in self._applied_agent:
                continue
            st = self._practice_state(k)
            scope = self._population(k, it) & P["present"]
            adopted = st["adopted"]
            if self._over(it, day):     # the behavior fades once the change ends (e.g. a ban returns)
                adopted &= sim.u(f"whatif_p{k}_end") > 0.25
                st["history"].append((day, float(adopted[scope].mean()) if scope.any() else 0.0, int(scope.sum())))
                continue
            cnt, frac = sim.systems["norms"]._peer(adopted)
            thr = sim.p("norms.contagion.threshold")
            peer = float(it.get("peer", 1.0)) * (sim.p("norms.contagion.peer") * np.log1p(cnt) * np.clip(cnt / thr, 0, 1) + 0.8 * frac)
            att = np.full(P.n, float(it.get("base", -4.0)))
            for var, w in (it.get("traits") or {}).items():
                if var in P.specs and P.specs[var].dtype not in ("cat",):
                    att += float(w) * sim.z(var)
            hz = expit(att + peer) * 0.05 * self._ramp(it, day)
            new = scope & ~adopted & (sim.u(f"whatif_p{k}_adopt") < hz)
            quit_ = adopted & (sim.u(f"whatif_p{k}_quit") < float(it.get("quit", 0.005)))
            adopted |= new
            adopted &= ~quit_
            if new.any():
                sim.log.emit("whatif_practice", day, np.where(new)[0], value=k, mech="whatif.practice")
            st["history"].append((day, float(adopted[scope].mean()) if scope.any() else 0.0, int(scope.sum())))
        self._bias_day = -1

    # ------------------------------------------------------------------ persistent nudges
    def bias(self, channel: str):
        """Σ value · ramp · [in population] over offset items on this channel, plus practice adopters' feelings.
        Returns 0.0 when nothing targets the channel (the Original universe pays nothing)."""
        day = self.sim.w.day
        n = self.sim.w.P.n
        if self._bias_day != day:
            self._bias_cache = {}
            self._bias_day = day
        if channel in self._bias_cache and (np.isscalar(self._bias_cache[channel]) or len(self._bias_cache[channel]) == n):
            return self._bias_cache[channel]
        out = 0.0
        for k, it in enumerate(self.items):
            tt = it.get("target_type")
            if tt == "offset" and it.get("target") == channel:
                f = self._ramp(it, day)
                if f > 0:
                    m = self._population(k, it)
                    if float(it.get("share", 1.0)) < 1.0:
                        mm = np.zeros(n, bool)
                        mm[self._pick(k, it, m)] = True
                        m = mm
                    out = out + float(it["value"]) * f * m
            elif tt == "practice" and k in self.practices and day >= it["start_day"]:
                for e in it.get("effects_while") or []:
                    if e.get("var") == channel:
                        st = self._practice_state(k)
                        out = out + float(e.get("value", 0.0)) * st["adopted"][:n]
        self._bias_cache[channel] = out
        return out

    def choice_bias(self, idx: np.ndarray) -> np.ndarray | float:
        cols = [self.bias(f"choice:{o}") for o in CHOICE_OPTIONS]
        if all(np.isscalar(c) and c == 0.0 for c in cols):
            return 0.0
        out = np.zeros((len(idx), len(CHOICE_OPTIONS)))
        for j, c in enumerate(cols):
            out[:, j] = c[idx] if not np.isscalar(c) else c
        return out

    def summary(self) -> list[dict]:
        return [dict(it) for it in self.items]

    def report(self) -> list[dict]:
        """Per-item reach and practice curves, for the What-if receipt and overview."""
        out = []
        for k, it in enumerate(self.items):
            r = {"k": k, "name": it.get("name"), "target_type": it.get("target_type"), "target": it.get("target"),
                 "reached": self.exposed.get(k)}
            if k in self.practices:
                r["practice"] = {"label": it.get("label") or it.get("name"),
                                 "history": [{"day": d, "share": s, "n": m} for d, s, m in self.practices[k]["history"]]}
            out.append(r)
        return out

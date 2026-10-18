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
  social   – a social action (engine/systems/social_actions.py): {"action": invite | series | reschedule | introduce |
             ride | reach_out | job_offer, ...}, arranged by the world editor (people still decide) or done "as" a person
             (only people they know, only when they're free, only what they can afford); lowered once on its start day
             into occasions, invitations, rides, ties and jobs, with the cause ("action", item index)

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
        self.practices: dict[int, dict] = {}     # item -> {"adopted": bool[n], "history": [(day, share, n_scope)]}
        self.exposed: dict[int, int] = {}        # item -> people reached (for the receipt)
        self._active_place: set[int] = set()     # close/place items in effect now
        self._units_of: dict[int, np.ndarray] = {}
        self._vids_of: dict[int, np.ndarray] = {}
        self._base_unit: dict[int, tuple[int, bool]] = {}   # unit -> original (capacity, contracted)
        self._base_vtype: dict[int, str] = {}                # venue -> original type
        self._venue_added: dict[int, int] = {}               # venue item -> the venue it opened
        self._removed_venues: set[int] = set()
        self._next_due: dict[int, int] = {}                  # repeating events: next firing day
        self._base_params = dict(sim.p.values)
        self._bias_day = -1
        self._bias_cache: dict[str, object] = {}
        self.social_results: dict[int, dict] = {}            # social action -> what happened (or why it was refused)
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
        """The item's population mask, re-evaluated weekly (arrivals, moves and status changes are picked up).
        Items marked `freeze_population` keep the group they had on their start day (e.g. the residents of a complex
        the same plan closes), padded for later arrivals."""
        from ..analysis.query import evaluate_filter
        sim = self.sim
        n = sim.w.P.n
        d0, n0, m = self._masks.get(k, (-999, -1, None))
        if m is not None and it.get("freeze_population"):
            if len(m) < n:
                m = np.concatenate([m, np.zeros(n - len(m), bool)])
                self._masks[k] = (d0, n, m)
            return m
        if m is None or n0 != n or sim.w.day - d0 >= refresh_days:
            m = evaluate_filter(sim.w, it.get("population"), sim=sim, include_absent=include_absent)
            self._masks[k] = (sim.w.day, n, m)
            if it.get("target_type") == "offset":
                self.exposed[k] = int(m.sum())
        return m

    def _scope(self, k: int, it: dict) -> np.ndarray:
        """Population mask with the item's stable random `share` applied."""
        m = self._population(k, it)
        share = float(it.get("share", 1.0))
        if share >= 1.0:
            return m
        from ..analysis.query import hash_uniform
        return m & (hash_uniform(np.arange(len(m)), f"whatif:{it.get('id', k)}:{k}:pick") < share)

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
        # groups that must be fixed before today's closures move anyone (residents of a complex this plan closes)
        for k, it in enumerate(self.items):
            if it.get("freeze_population") and k not in self._masks and day >= it["start_day"]:
                self._population(k, it)
        places_changed = False
        for k, it in enumerate(self.items):
            tt = it.get("target_type")
            if tt in ("world", "param", "offset") or day < it["start_day"]:
                continue
            if self._over(it, day):
                if k in self._applied_agent and k not in self._ended:
                    self._ended.add(k)
                    if tt in ("close", "place"):
                        self._active_place.discard(k)
                        self._end_relative(k, it)
                        places_changed = True
                    elif tt == "venue" and k in self._venue_added:
                        self._removed_venues.add(self._venue_added[k])    # a pop-up closes when its time is up
                        places_changed = True
                continue
            if tt in ("event", "shock") and it.get("repeat_every"):
                every = max(int(it["repeat_every"]), 1)
                due = self._next_due.get(k, it["start_day"])
                if day >= due:            # catch up if a start phase was missed (e.g. applied mid-day)
                    self._inject(k, it, tag=f"r{day}")
                    while due <= day:
                        due += every
                    self._next_due[k] = due
                continue
            if k in self._applied_agent:
                continue
            self._applied_agent.add(k)
            if tt == "venue":
                act = sim.systems["activity"]
                self._venue_added[k] = len(act.v_name)
                act.add_venue(it["value"])
            elif tt == "agent":
                self._agent(k, it)
            elif tt in ("event", "shock"):
                self._inject(k, it)
            elif tt == "close":
                self._start_place(k, it)
                self._recompute_places()       # capacity must be gone before residents are rehoused
                places_changed = False
                self._rehouse(k, it)
            elif tt == "place":
                self._start_place(k, it)
                places_changed = True
            elif tt == "practice":
                self._seed_practice(k, it)
            elif tt == "social":
                self._social(k, it)
        if places_changed:
            self._recompute_places()

    def _social(self, k, it):
        """Lower a social action into the occasions system; a refusal (no longer free, no longer affordable) is kept
        with its reason for the receipt."""
        res = self.sim.systems["occasions"].apply_action(k, it)
        self.social_results[k] = res
        self.exposed[k] = int(res.get("invitations", 1 if res.get("ok") else 0))
        return res

    def apply_now(self, k: int) -> dict:
        """Apply one-shot item k right away (a social action added from the workbench) instead of at the next start
        of day."""
        it = self.items[k]
        if k in self._applied_agent or it.get("target_type") != "social":
            return self.social_results.get(k, {})
        self._applied_agent.add(k)
        return self._social(k, it)

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
    # Closures, bed counts and contracted status are recomputed from each unit's / venue's original value and the
    # changes active now, so overlapping changes compose and ending one restores exactly what the others leave.
    # Rent and quality are relative (×, +) and undone relative to the current value, so market drift survives.
    @staticmethod
    def _ref(target: str) -> tuple[str, object]:
        kind, _, rest = str(target).partition(":")
        return kind, (int(rest) if rest.lstrip("-").isdigit() else rest)

    def _start_place(self, k, it):
        sim = self.sim
        U = sim.w.units
        kind, ref = self._ref(it["target"])
        if kind == "complex":
            units = np.where(U.complex_id == ref)[0]
            self._units_of[k] = units
            for u in units.tolist():
                if u not in self._base_unit:
                    self._base_unit[u] = (int(U.capacity[u]), bool(U.contracted[u]))
            attr = it.get("attr") if it["target_type"] == "place" else None
            if attr == "rent":
                U.rent_total[units] = (U.rent_total[units] * float(it["value"])).astype(U.rent_total.dtype)
                self._update_residents_rent(units)
            elif attr == "quality":
                U.quality[units] = (U.quality[units] + float(it["value"])).astype(U.quality.dtype)
            P = sim.w.P
            self.exposed[k] = int((np.isin(P["unit_id"], units) & P["present"]).sum())
        elif kind in ("venue", "venue_type"):
            act = sim.systems["activity"]
            vt = act.v_type
            vids = np.array([ref]) if kind == "venue" else np.array([v for v in range(len(vt)) if self._base_vtype.get(v, str(vt[v])) == ref])
            vids = vids[(vids >= 0) & (vids < len(vt))].astype(int)
            self._vids_of[k] = vids
            for v in vids.tolist():
                self._base_vtype.setdefault(v, str(vt[v]))
            self.exposed[k] = int(len(vids))
        self._active_place.add(k)

    def _end_relative(self, k, it):
        U = self.sim.w.units
        units = self._units_of.get(k)
        if units is None or it["target_type"] != "place":
            return
        attr = it.get("attr")
        if attr == "rent" and float(it["value"]) > 0:
            U.rent_total[units] = (U.rent_total[units] / float(it["value"])).astype(U.rent_total.dtype)
            self._update_residents_rent(units)
        elif attr == "quality":
            U.quality[units] = (U.quality[units] - float(it["value"])).astype(U.quality.dtype)

    def _update_residents_rent(self, units):
        P = self.sim.w.P
        res = np.where(np.isin(P["unit_id"], units) & P["present"])[0]
        if len(res):
            self.sim.systems["housing"]._update_rent(res)

    def _recompute_places(self):
        sim = self.sim
        U = sim.w.units
        if self._base_unit:
            units = np.fromiter(self._base_unit.keys(), dtype=np.int64)
            cap = np.array([self._base_unit[u][0] for u in units.tolist()], dtype=np.float64)
            con = np.array([self._base_unit[u][1] for u in units.tolist()], dtype=bool)
            closed = np.zeros(len(units), bool)
            pos = {u: i for i, u in enumerate(units.tolist())}
            for k in sorted(self._active_place):
                it = self.items[k]
                us = self._units_of.get(k)
                if us is None:
                    continue
                idx = np.array([pos[u] for u in us.tolist()], dtype=np.int64)
                if it["target_type"] == "close":
                    closed[idx] = True
                elif it.get("attr") == "beds":
                    cap[idx] = cap[idx] * float(it["value"])
                elif it.get("attr") == "contracted":
                    con[idx] = bool(it["value"])
            U.capacity[units] = np.where(closed, 0, np.clip(np.rint(cap), 0, 255)).astype(U.capacity.dtype)
            U.contracted[units] = con
        if self._base_vtype or self._removed_venues:
            act = sim.systems["activity"]
            act.v_type = act.v_type.astype(object)
            for v, t in self._base_vtype.items():
                act.v_type[v] = t
            for k in self._active_place:
                if self.items[k]["target_type"] == "close" and k in self._vids_of:
                    act.v_type[self._vids_of[k]] = "closed"
            for v in self._removed_venues:
                act.v_type[v] = "closed"
            act._build_trees()

    def _rehouse(self, k, it):
        """Everyone living in a closed complex (including those away) moves, under the normal housing rules."""
        sim = self.sim
        units = self._units_of.get(k)
        if units is None:
            return
        P = sim.w.P
        res = np.where(np.isin(P["unit_id"], units))[0]
        if not len(res):
            return
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
        singles = np.array([i for i in res.tolist() if int(i) not in done], dtype=np.int64)
        if len(singles):
            housing.place(singles, reason="moved", cause=int(root[0]))

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
        scope = self._scope(k, it)
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
            scope = self._scope(k, it) & P["present"]
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
                    out = out + float(it["value"]) * f * self._scope(k, it)
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
            if k in self.social_results:
                r["social"] = self.social_results[k]
            if k in self.practices:
                r["practice"] = {"label": it.get("label") or it.get("name"),
                                 "history": [{"day": d, "share": s, "n": m} for d, s, m in self.practices[k]["history"]]}
            out.append(r)
        return out

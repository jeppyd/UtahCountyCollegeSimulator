"""The What-if plan: the structured answer an LLM gives, how it is validated, and how it becomes engine changes.

A plan is a short story plus a list of changes. Each change has a `kind` (world, nudge, event, shock, trait, param,
close, place, practice, venue), a target and the details that kind needs, who it applies to and when. The validator
is the gatekeeper: it fixes what it safely can (case of labels, clipping to bounds), rejects what it can't, counts
who is affected, and writes a plain-language receipt. Only a validated plan is ever lowered into interventions.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

import numpy as np

from ..engine.interventions import INJECTABLE, MOTIVES, OFFSET_CHANNELS, STATES, VISITED_VTYPES
from .levers import BETTER_CHANNEL, TRAIT_OK, WORLD_LEVERS, Z_RELATIVE, persistence

KINDS = ("world", "nudge", "event", "shock", "trait", "param", "close", "place", "practice", "venue")

_EFFECT = {"type": "object", "properties": {"var": {"type": "string", "enum": list(STATES)}, "mag": {"type": "number"},
                                            "half_life_days": {"type": "number"}, "delay_days": {"type": "number"}},
           "required": ["var", "mag", "half_life_days"], "additionalProperties": False}
CHANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "label": {"type": "string", "description": "Short card title, e.g. 'Alcohol allowed by the Church'"},
        "why": {"type": "string", "description": "One sentence: how this change follows from the request"},
        "target": {"type": "string", "description": "world key | channel | event type | variable id | mechanism.param | complex:<id> | venue:<id> | venue_type:<type>"},
        "op": {"type": "string", "enum": ["set", "add", "mul"]},
        "value": {"type": ["number", "boolean", "null"]},
        "who": {"type": ["object", "null"], "description": "Population filter (see catalog §11); null = everyone present"},
        "share": {"type": ["number", "null"], "description": "Stable random fraction of `who` (0–1)"},
        "start_offset_days": {"type": "integer", "description": "Days from today (0 = starts today)"},
        "ramp_days": {"type": "integer"},
        "duration_days": {"type": ["integer", "null"], "description": "null = permanent"},
        "repeat_every_days": {"type": ["integer", "null"]},
        "severity": {"type": ["number", "null"]},
        "event_label": {"type": ["string", "null"]},
        "story": {"type": ["string", "null"]},
        "motive": {"type": ["string", "null"], "enum": [*MOTIVES, None]},
        "valence": {"type": ["number", "null"]},
        "salience": {"type": ["number", "null"]},
        "effects": {"type": "array", "items": _EFFECT},
        "attr": {"type": ["string", "null"], "enum": ["rent", "beds", "quality", "contracted", None]},
        "practice_label": {"type": ["string", "null"]},
        "seed_share": {"type": ["number", "null"]},
        "base": {"type": ["number", "null"]},
        "traits": {"type": "array", "items": {"type": "object", "properties": {"var": {"type": "string"}, "weight": {"type": "number"}},
                                              "required": ["var", "weight"], "additionalProperties": False}},
        "peer": {"type": ["number", "null"]},
        "quit": {"type": ["number", "null"]},
        "effects_while": {"type": "array", "items": {"type": "object", "properties": {"var": {"type": "string", "enum": list(STATES)}, "value": {"type": "number"}},
                                                     "required": ["var", "value"], "additionalProperties": False}},
        "venue": {"type": ["object", "null"], "properties": {"name": {"type": "string"}, "vtype": {"type": "string"},
                                                             "lon": {"type": "number"}, "lat": {"type": "number"}}},
    },
    "required": ["kind", "label", "why"],
}
PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Headline for this What-if, ≤ 60 characters"},
        "reply": {"type": "string", "description": "Your message to the user: how you read the request, what you changed and why, what you couldn't model. Friendly, plain, 2–6 sentences."},
        "changes": {"type": "array", "items": CHANGE_SCHEMA},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "not_modeled": {"type": "array", "items": {"type": "object", "properties": {"aspect": {"type": "string"}, "approximation": {"type": "string"}},
                                                   "required": ["aspect", "approximation"], "additionalProperties": False}},
        "expectations": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"}, "variable": {"type": ["string", "null"]}, "direction": {"type": "string", "enum": ["up", "down", "unclear"]},
            "who": {"type": ["object", "null"]}}, "required": ["text", "direction"]}},
        "questions": {"type": "array", "items": {"type": "string"}, "description": "Only when the request is genuinely ambiguous"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["title", "reply", "changes", "assumptions", "not_modeled", "expectations", "confidence"],
}


def strict_schema(schema: dict | None = None) -> dict:
    """OpenAI-style strict variant (Codex, LM Studio): every property required (optional ones nullable), no open objects
    (filters travel as JSON strings: `who_json`)."""
    def conv(s):
        s = copy.deepcopy(s)
        t = s.get("type")
        if t == "object" or (isinstance(t, list) and "object" in t):
            props = s.get("properties")
            if not props:   # an open object → a JSON string
                return {"type": ["string", "null"] if isinstance(t, list) else "string", "description": (s.get("description", "") + " (JSON-encoded)").strip()}
            new = {}
            for k, v in props.items():
                key = f"{k}_json" if v.get("type") in ("object", ["object", "null"]) and not v.get("properties") else k
                cv = conv(v)
                if k not in s.get("required", []):
                    ty = cv.get("type")
                    if isinstance(ty, str) and ty != "array":
                        cv["type"] = [ty, "null"]
                    if "enum" in cv and None not in cv["enum"]:
                        cv["enum"] = [*cv["enum"], None]
                new[key] = cv
            s["properties"] = new
            s["required"] = list(new)
            s["additionalProperties"] = False
            if isinstance(t, list):
                s["type"] = "object"
            return s
        if t == "array":
            s["items"] = conv(s["items"])
        return s
    return conv(schema or PLAN_SCHEMA)


def unstrict(plan: dict) -> dict:
    """Undo strict_schema's encoding: `who_json` strings back to objects, drop nulls."""
    def fix(x):
        if isinstance(x, dict):
            out = {}
            for k, v in x.items():
                if k.endswith("_json"):
                    try:
                        v = json.loads(v) if isinstance(v, str) and v.strip() else None
                    except json.JSONDecodeError:
                        pass     # keep the raw string: the validator rejects it instead of widening to "everyone"
                    k = k[:-5]
                if v is None:
                    continue
                out[k] = fix(v)
            return out
        if isinstance(x, list):
            return [fix(v) for v in x]
        return x
    return fix(plan)


# ---------------------------------------------------------------------- validation
class Problems:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []


def _num(x, default=None):
    try:
        f = float(x)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def _clip(name, x, lo, hi, prob: Problems):
    if x < lo or x > hi:
        y = min(max(x, lo), hi)
        prob.warnings.append(f"{name} {x:g} clipped to {y:g} (allowed {lo:g}–{hi:g})")
        return y
    return x


def _int_ok(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def check_filter(f, sim, prob: Problems, path="who"):
    """Validate and normalize a population filter; returns the cleaned filter (or None, with an error recorded).
    Anything that passes here is a filter the engine can evaluate."""
    if f is None or f == {}:
        return None
    if isinstance(f, str):
        try:
            f = json.loads(f)
        except json.JSONDecodeError:
            prob.errors.append(f"{path}: not a filter object")
            return None
    if not isinstance(f, dict):
        prob.errors.append(f"{path}: not a filter object")
        return None
    P = sim.w.P
    reg = sim.reg
    for key in ("and", "or"):
        if key in f:
            if not isinstance(f[key], list) or not f[key]:
                prob.errors.append(f"{path}.{key} must be a non-empty list")
                return None
            parts = [check_filter(g, sim, prob, f"{path}.{key}[{i}]") for i, g in enumerate(f[key])]
            if any(x is None for x in parts):
                prob.errors.append(f"{path}.{key}: every part must be a valid filter")
                return None
            return {key: parts}
    if "not" in f:
        inner = check_filter(f["not"], sim, prob, f"{path}.not")
        return {"not": inner} if inner is not None else None
    if f.get("all") is True:
        return {"all": True}
    if "ids" in f:
        raw = f["ids"] if isinstance(f["ids"], list) else []
        ids = sorted({int(i) for i in raw if _int_ok(i) and 0 <= int(i) < P.n})
        if not ids:
            prob.errors.append(f"{path}.ids: no valid person ids")
            return None
        return {"ids": ids}
    if "friends_of" in f:
        inner = check_filter(f["friends_of"], sim, prob, f"{path}.friends_of")
        if inner is None:
            return None
        return {"friends_of": inner, "min_stage": int(min(max(_num(f.get("min_stage"), 3), 1), 4)), "exclude": bool(f.get("exclude", True))}
    if "share" in f and "household" not in f:
        sh = _num(f["share"])
        if sh is None or sh <= 0:
            prob.errors.append(f"{path}.share must be a number above 0")
            return None
        inner = check_filter(f.get("of"), sim, prob, f"{path}.of") if f.get("of") is not None else None
        if f.get("of") is not None and inner is None:
            return None
        return {"share": min(sh, 1.0), "of": inner, "salt": str(f.get("salt", "share"))[:40]}
    if "recent_event" in f:
        if not isinstance(f["recent_event"], str) or f["recent_event"] not in reg.events:
            prob.errors.append(f"{path}.recent_event: unknown event type {f['recent_event']!r}")
            return None
        return {"recent_event": f["recent_event"], "days": int(min(max(_num(f.get("days"), 90), 1), 3650))}
    if "household" in f:
        inner = check_filter(f["household"], sim, prob, f"{path}.household")
        op = f.get("share", ">=")
        v = _num(f.get("value"), 0.5)
        if inner is None or op not in (">=", ">", "<=", "<"):
            prob.errors.append(f"{path}.household needs an inner filter and share one of >=, >, <=, <")
            return None
        return {"household": inner, "share": op, "value": min(max(v, 0.0), 1.0)}
    if "transition" in f:
        prob.errors.append(f"{path}: transition filters aren't supported in What-if plans (use recent_event)")
        return None
    var = f.get("var")
    if not isinstance(var, str) or var not in P.specs:
        prob.errors.append(f"{path}: unknown variable {var!r}")
        return None
    op = f.get("op", "eq")
    from ..analysis.query import OPS
    if not isinstance(op, str) or op not in OPS:
        prob.errors.append(f"{path}: unknown op {op!r}")
        return None
    out = {"var": var, "op": op}
    if op in ("isnull", "notnull"):
        return out
    val = f.get("value")
    spec = P.specs[var]
    if spec.dtype == "cat":
        cats = list(spec.categories)
        low = {c.lower(): c for c in cats}

        def fixlab(v):
            if isinstance(v, str):
                if v in cats:
                    return v
                if v.lower() in low:
                    return low[v.lower()]
                prob.errors.append(f"{path}: '{v}' is not a {var} label (labels: {', '.join(cats)})")
                return None
            if _int_ok(v) and 0 <= int(v) < len(cats):
                return cats[int(v)]
            prob.errors.append(f"{path}: bad {var} value {v!r}")
            return None
        if op in ("in", "notin"):
            vals = [fixlab(v) for v in (val if isinstance(val, list) else [val])]
            if not vals or any(v is None for v in vals):
                return None
            out["value"] = vals
        elif op in ("eq", "ne"):
            v = fixlab(val[0] if isinstance(val, list) and val else val)
            if v is None:
                return None
            out["value"] = v
        else:
            prob.errors.append(f"{path}: op '{op}' does not apply to categorical {var}")
            return None
        return out
    if spec.dtype == "bool":
        if op not in ("eq", "ne"):
            prob.errors.append(f"{path}: use eq/ne with true/false for {var}")
            return None
        v = val[0] if isinstance(val, list) and val else val
        out["value"] = (v.lower() in ("true", "yes", "1")) if isinstance(v, str) else bool(v)
        return out
    if op == "between":
        if not (isinstance(val, list) and len(val) == 2 and all(_num(v) is not None for v in val)):
            prob.errors.append(f"{path}: between needs [lo, hi]")
            return None
        out["value"] = [float(min(val)), float(max(val))]
        return out
    if op in ("in", "notin"):
        vals = [float(v) for v in (val if isinstance(val, list) else [val]) if _num(v) is not None]
        if not vals:
            prob.errors.append(f"{path}: {op} needs a list of numbers for {var}")
            return None
        out["value"] = vals
        return out
    x = _num(val[0] if isinstance(val, list) and val else val)
    if x is None:
        prob.errors.append(f"{path}: {var} needs a number")
        return None
    if op in ("quantile_ge", "quantile_le"):
        if 1 < x <= 100:
            prob.warnings.append(f"{path}: quantile {x:g} read as {x / 100:g}")
            x = x / 100
        if not 0 <= x <= 1:
            prob.errors.append(f"{path}: quantiles must be between 0 and 1")
            return None
    out["value"] = int(x) if float(x).is_integer() and op not in ("quantile_ge", "quantile_le") else float(x)
    return out


def count_who(sim, who, prob: Problems | None = None) -> int:
    """People a filter selects now; a filter the engine can't evaluate is an error (never silently accepted)."""
    from ..analysis.query import evaluate_filter
    try:
        return int(evaluate_filter(sim.w, who, sim=sim).sum())
    except Exception as e:  # noqa: BLE001
        if prob is not None:
            prob.errors.append(f"the group can't be evaluated: {e}")
        return -1


_FRIENDLY = {("sex", "M"): "men", ("sex", "F"): "women", ("lds_member", True): "LDS members", ("lds_member", False): "non-members",
             ("enrolled", True): "enrolled", ("enrolled", False): "not enrolled", ("present", True): "here"}
_LINKS = {"complex_id": ("complex", "residents of"), "ward_id": ("ward", "members of"), "employer_id": ("employer", "employees of"),
          "club_id": ("club", "members of"), "team_id": ("team", "members of"), "institute_class": ("institute", "students in"),
          "congregation_id": ("congregation", "attendees of"), "major_id": ("major", "students of")}


def friendly_who(sim, f, index=None) -> str:
    """A filter in words: 'enrolled BYU students · men', 'residents of Helaman Halls', 'friends of (…)'."""
    if f is None:
        return "everyone"
    reg = sim.reg
    if "and" in f:
        parts = [friendly_who(sim, g, index) for g in f["and"]]
        # "BYU" + "enrolled" reads as "enrolled BYU students"
        if "BYU" in parts and "enrolled" in parts:
            parts = [p for p in parts if p not in ("BYU", "enrolled")] + ["enrolled BYU students"]
        if "UVU" in parts and "enrolled" in parts:
            parts = [p for p in parts if p not in ("UVU", "enrolled")] + ["enrolled UVU students"]
        return " · ".join(parts)
    if "or" in f:
        return " or ".join(friendly_who(sim, g, index) for g in f["or"])
    if "not" in f:
        return "not " + friendly_who(sim, f["not"], index)
    if f.get("all"):
        return "everyone"
    if "ids" in f:
        if index is not None and len(f["ids"]) <= 4:
            return ", ".join(index.person_row(i)["label"] for i in f["ids"])
        return f"{len(f['ids'])} specific people"
    if "friends_of" in f:
        return f"{'close ' if f.get('min_stage', 3) >= 4 else ''}friends of {friendly_who(sim, f['friends_of'], index)}"
    if "share" in f and "household" not in f:
        return f"a random {round(100 * float(f['share']))}% of {friendly_who(sim, f.get('of'), index)}"
    if "recent_event" in f:
        ev = reg.events.get(f["recent_event"])
        return f"people who recently had '{ev.label if ev else f['recent_event']}'"
    if "household" in f or "transition" in f:
        from ..analysis.query import describe_filter
        return describe_filter(f)
    var, op, val = f.get("var"), f.get("op", "eq"), f.get("value")
    if var in _LINKS and op == "eq" and index is not None:
        kind, verb = _LINKS[var]
        r = index.get(f"{kind}:{val}")
        if r:
            return f"{verb} {r['label']}"
    if op == "eq" and not isinstance(val, (list, dict)) and (var, val) in _FRIENDLY:
        return _FRIENDLY[(var, val)]
    v = reg.variables.get(var)
    lab = (v.label if v else var).lower() if var else "?"
    if var == "school" and op == "eq":
        return str(val)
    if op == "eq":
        return f"{lab}: {str(val).replace('_', ' ')}" if not isinstance(val, bool) else (lab if val else f"not {lab}")
    if op == "ne":
        return f"{lab} not {str(val).replace('_', ' ')}"
    if op in ("in", "notin"):
        vals = " or ".join(str(x).replace("_", " ") for x in (val or []))
        return f"{lab}: {vals}" if op == "in" else f"{lab} not {vals}"
    if op == "quantile_ge":
        return f"top {round(100 * (1 - float(val)))}% by {lab}"
    if op == "quantile_le":
        return f"bottom {round(100 * float(val))}% by {lab}"
    if op == "between":
        return f"{lab} {val[0]}–{val[1]}"
    sym = {"lt": "<", "le": "≤", "gt": ">", "ge": "≥"}.get(op, op)
    return f"{lab} {sym} {val}"


def _describe_who(sim, who, index=None) -> str:
    from ..analysis.query import describe_filter
    if who is None:
        return "everyone"
    try:
        return friendly_who(sim, who, index)
    except Exception:  # noqa: BLE001
        pass
    s = describe_filter(who)
    # name entities instead of raw ids where we can
    if index is not None:
        for kind, col in (("complex", "complex_id"), ("ward", "ward_id"), ("employer", "employer_id"), ("club", "club_id"),
                          ("team", "team_id"), ("institute", "institute_class"), ("congregation", "congregation_id"), ("major", "major_id")):
            if col in s:
                import re
                for m in re.finditer(rf"{col} eq (\d+)", s):
                    r = index.get(f"{kind}:{m.group(1)}")
                    if r:
                        s = s.replace(m.group(0), f"{'members of' if kind not in ('complex',) else 'residents of'} {r['label']}")
    if "ids" in (who or {}) and index is not None and len(who["ids"]) <= 4:
        s = ", ".join(index.person_row(i)["label"] for i in who["ids"])
    return s


def validate(plan: dict, sim, index=None) -> dict:
    """→ {plan (normalized), changes: [receipt rows], errors, warnings, ok}"""
    prob = Problems()
    if not isinstance(plan, dict):
        return {"plan": {"title": "", "reply": "", "changes": [], "assumptions": [], "not_modeled": [], "expectations": [], "questions": [],
                         "confidence": "medium"}, "changes": [], "errors": ["the answer wasn't a plan object"], "warnings": [], "ok": False}
    out = {"title": str(plan.get("title") or "Your What-if")[:80], "reply": str(plan.get("reply") or ""),
           "assumptions": [str(x) for x in plan.get("assumptions") or []][:12],
           "not_modeled": [x for x in plan.get("not_modeled") or [] if isinstance(x, dict)][:12],
           "expectations": [], "questions": [str(x) for x in plan.get("questions") or []][:5],
           "confidence": plan.get("confidence") if plan.get("confidence") in ("high", "medium", "low") else "medium",
           "changes": []}
    rows = []
    P = sim.w.P
    changes = plan.get("changes") or []
    if not isinstance(changes, list):
        prob.errors.append("changes must be a list")
        changes = []
    if len(changes) > 16:
        prob.warnings.append(f"{len(changes)} changes — only the first 16 kept")
        changes = changes[:16]
    for j, ch in enumerate(changes):
        cp = Problems()
        try:
            c, row = _check_change(ch, j, sim, cp, index)
        except Exception as e:  # noqa: BLE001 — a malformed change is reported, never fatal
            c, row = None, {"label": str(ch.get("label", "?"))[:70] if isinstance(ch, dict) else "?", "kind": ch.get("kind") if isinstance(ch, dict) else "?",
                            "why": "", "summary": "", "who": "", "n": None}
            cp.errors.append(f"couldn't read this change ({type(e).__name__}: {e})")
        if c is not None and not cp.errors:
            out["changes"].append(c)
            row["ok"] = True
        else:
            row["ok"] = False
        row["errors"], row["warnings"] = cp.errors, cp.warnings
        prob.errors += [f"change {j + 1} ({ch.get('label', ch.get('kind', '?')) if isinstance(ch, dict) else '?'}): {e}" for e in cp.errors]
        prob.warnings += [f"change {j + 1}: {w}" for w in cp.warnings]
        rows.append(row)
    for e in plan.get("expectations") or []:
        if not isinstance(e, dict) or not e.get("text"):
            continue
        ee = {"text": str(e["text"])[:200], "direction": e.get("direction") if e.get("direction") in ("up", "down", "unclear") else "unclear"}
        v = e.get("variable")
        if isinstance(v, str) and v in P.specs and P.specs[v].dtype in ("f4", "f8", "u1", "i2", "bool"):
            ee["variable"] = v
            wp = Problems()
            w = check_filter(e.get("who"), sim, wp, "expectation.who")
            if w is not None and not wp.errors:
                ee["who"] = w
        out["expectations"].append(ee)
    if not out["changes"] and not prob.errors:
        prob.errors.append("the plan has no changes")
    return {"plan": out, "changes": rows, "errors": prob.errors, "warnings": prob.warnings,
            "ok": not prob.errors and bool(out["changes"])}


def _check_change(ch, j, sim, prob: Problems, index):
    reg = sim.reg
    P = sim.w.P
    if not isinstance(ch, dict):
        prob.errors.append("not an object")
        return None, {"label": "?", "kind": "?"}
    kind = ch.get("kind")
    label = str(ch.get("label") or kind or "change")[:70]
    row = {"label": label, "why": str(ch.get("why") or "")[:300], "kind": kind, "summary": "", "who": "everyone", "n": None}
    if not isinstance(kind, str) or kind not in KINDS:
        prob.errors.append(f"unknown kind {kind!r}")
        return None, row
    target = ch.get("target")
    if kind in ("world", "nudge", "event", "trait", "param", "close", "place") and not isinstance(target, str):
        prob.errors.append(f"target must be a text id, got {target!r}")
        return None, row
    c = {"kind": kind, "label": label, "why": row["why"]}
    start = int(max(0, min(_num(ch.get("start_offset_days"), 0), 3650)))
    c["start_offset_days"] = start
    c["ramp_days"] = int(max(0, min(_num(ch.get("ramp_days"), 0), 730)))
    dur = _num(ch.get("duration_days"))
    c["duration_days"] = None if not dur or dur <= 0 else int(max(1, min(dur, 3650)))
    if c["duration_days"] and kind == "trait":
        prob.warnings.append("trait changes are permanent; the duration was dropped (use a nudge for something temporary)")
        c["duration_days"] = None
    if c["duration_days"] and kind in ("event", "shock") and not _num(ch.get("repeat_every_days")):
        c["duration_days"] = None     # a one-off event has no duration; its effects fade by their own half-lives
    if kind in ("nudge", "event", "shock", "trait", "practice"):
        who = check_filter(ch.get("who"), sim, prob)
        if prob.errors:
            return None, row
        c["who"] = who
        sh = _num(ch.get("share"))
        if sh is not None and sh <= 0:
            prob.errors.append("share must be above 0 (leave it out to include everyone in the group)")
            return None, row
        if sh is not None and sh < 1:
            c["share"] = sh
        n = count_who(sim, who, prob)
        if prob.errors:
            return None, row
        if "share" in c and n >= 0:
            n = int(round(n * c["share"]))
        row["n"] = n
        row["who"] = _describe_who(sim, who, index) + (f" (a random {round(100 * c['share'])}%)" if "share" in c else "")
        if n == 0:
            prob.warnings.append("nobody matches this group right now (it may fill later, e.g. after the summer)")
    op = ch.get("op") or "set"
    if op not in ("set", "add", "mul"):
        prob.errors.append(f"op must be set, add or mul, got {op!r}")
        return None, row
    val = ch.get("value")
    when = f"from day +{start}" if start else "from today"
    if c["duration_days"]:
        when += f" for {c['duration_days']} days"
    if c["ramp_days"]:
        when += f", phasing in over {c['ramp_days']} days"

    if kind == "world":
        if target not in WORLD_LEVERS:
            close = [k for k in WORLD_LEVERS if target and (target in k or k in str(target))]
            prob.errors.append(f"'{target}' is not a world lever" + (f" (did you mean {', '.join(close)}?)" if close else ""))
            return None, row
        t, lo, hi, what, timing = WORLD_LEVERS[target]
        if t == "bool":
            if op != "set" or not isinstance(val, (bool, int, float)):
                prob.errors.append(f"{target} is true/false: use op set with true or false")
                return None, row
            val, op = bool(val), "set"
            row["summary"] = f"{what.split(':')[0]} → {'yes' if val else 'no'}"
        else:
            v = _num(val)
            if v is None or op not in ("set", "add", "mul"):
                prob.errors.append(f"{target} needs a number and op set/add/mul")
                return None, row
            base = sim.systems["environment"].base.get(target, 0.0)
            res = v if op == "set" else base + v if op == "add" else base * v
            res2 = _clip(f"{target} result", res, lo, hi, prob)
            v = res2 if op == "set" else (res2 - base) if op == "add" else (res2 / base if base else 1.0)
            val = v
            row["summary"] = f"{target.replace('_', ' ')}: {base:g} → {res2:g}"
        row["detail"] = timing
        c.update(target=target, op=op, value=val)
    elif kind == "nudge":
        if target not in OFFSET_CHANNELS:
            prob.errors.append(f"'{target}' is not a nudge channel")
            return None, row
        units, bound, what = OFFSET_CHANNELS[target]
        v = _num(val)
        if v is None:
            prob.errors.append("a nudge needs a numeric value")
            return None, row
        v = _clip(f"nudge {target}", v, -bound, bound, prob)
        c.update(target=target, op="add", value=v)
        row["summary"] = f"{'+' if v >= 0 else ''}{v:g} {units} on {what}"
    elif kind == "event":
        if target not in INJECTABLE:
            prob.errors.append(f"'{target}' can't be injected (injectable: {', '.join(INJECTABLE)}); use a shock instead")
            return None, row
        sev = _clip("severity", _num(ch.get("severity"), 1.0), 0.25, 4.0, prob)
        rep = ch.get("repeat_every_days")
        c.update(target=target, severity=sev, repeat_every_days=int(max(1, _num(rep))) if _num(rep) else None)
        row["summary"] = f"'{reg.events[target].label}' happens to them" + (f", every {c['repeat_every_days']} days" if c["repeat_every_days"] else "") + (f" (severity ×{sev:g})" if sev != 1 else "")
    elif kind == "shock":
        effs = []
        for e in ch.get("effects") or []:
            if not isinstance(e, dict) or e.get("var") not in STATES or _num(e.get("mag")) is None:
                prob.errors.append(f"bad effect {e!r} (var must be one of {', '.join(STATES)})")
                continue
            effs.append({"var": e["var"], "mag": _clip(f"effect on {e['var']}", float(e["mag"]), -0.3, 0.3, prob),
                         "half_life": _clip("half-life", _num(e.get("half_life_days", e.get("half_life")), 14), 1, 365, prob),
                         "delay": int(max(0, min(_num(e.get("delay_days", e.get("delay")), 0), 60)))})
        if not effs:
            prob.errors.append("a shock needs 1–6 effects on feelings")
            return None, row
        effs = effs[:6]
        from ..engine.memory import VALENCE_W
        implied = float(np.tanh(8 * sum(VALENCE_W.get(e["var"], 0) * e["mag"] for e in effs)))
        valence = _num(ch.get("valence"), implied)
        if valence * implied < -0.05:
            prob.warnings.append(f"valence {valence:g} disagrees with its effects; using {implied:+.2f}")
            valence = implied
        motive = ch.get("motive") if ch.get("motive") in MOTIVES else None
        if motive is None:
            prob.warnings.append("no motive given: the shock won't be appraised by what people care about")
        story = str(ch.get("story") or "{a} felt " + label.lower())[:140]
        if "{a}" not in story:
            story = "{a}: " + story
        rep = ch.get("repeat_every_days")
        c.update(event_label=str(ch.get("event_label") or label)[:60], story=story, motive=motive,
                 valence=_clip("valence", valence, -1, 1, prob), salience=_clip("salience", _num(ch.get("salience"), 0.55), 0.3, 0.85, prob),
                 effects=effs, severity=_clip("severity", _num(ch.get("severity"), 1.0), 0.25, 4.0, prob),
                 repeat_every_days=int(max(1, _num(rep))) if _num(rep) else None)
        row["summary"] = f"“{c['event_label']}”: " + ", ".join(f"{e['var'].replace('_', ' ')} {e['mag']:+g} (fades over ~{e['half_life']:g} d)" for e in effs)
    elif kind == "trait":
        v = reg.variables.get(target)
        if v is None or getattr(v, "entity", "person") != "person":
            prob.errors.append(f"unknown person variable '{target}'")
            return None, row
        cls = persistence(v)
        if cls not in TRAIT_OK or v.dtype in ("cat", "str"):
            hint = {"composed": f"use a nudge on '{target}'", "computed": "change its drivers instead", "identity": "identity can't be changed",
                    "inert": "no mechanism reads it, so changing it does nothing", "structural": "structural states need events, closures or world levers"}.get(cls, "")
            prob.errors.append(f"'{target}' can't be changed directly ({cls}): {hint}")
            return None, row
        if target in BETTER_CHANNEL:
            prob.warnings.append(f"'{target}' relaxes back; nudge '{BETTER_CHANNEL[target]}' lasts")
        if target in Z_RELATIVE and c.get("who") is None:
            prob.warnings.append(f"'{target}' is read relative to everyone: shifting everyone washes out within a week")
        if v.dtype == "bool":
            if op != "set":
                prob.errors.append(f"{target} is true/false: use op set")
                return None, row
            val = bool(val)
        else:
            fv = _num(val)
            if fv is None or op not in ("set", "add", "mul"):
                prob.errors.append(f"{target} needs a number and op set/add/mul")
                return None, row
            if op == "set" and v.range:
                fv = _clip(target, fv, v.range[0], v.range[1], prob)
            val = fv
        c.update(target=target, op=op, value=val)
        row["summary"] = f"{v.label}: {op} {val}"
    elif kind == "param":
        base = sim.p.base.get(target) if hasattr(sim.p, "base") else None
        if base is None:
            base = sim.p.values.get(target)
        if base is None:
            mech = str(target).rsplit(".", 1)[0]
            hint = f" (params of {mech}: {', '.join(reg.mechanisms[mech].params)})" if mech in reg.mechanisms else ""
            prob.errors.append(f"unknown parameter '{target}'{hint}")
            return None, row
        mid, pn = target.rsplit(".", 1)
        spec = reg.mechanisms[mid].params[pn]
        if spec.get("structural"):
            prob.errors.append(f"'{target}' selects a model form; it isn't a What-if lever")
            return None, row
        fv = _num(val)
        if fv is None or op not in ("set", "add", "mul"):
            prob.errors.append(f"{target} needs a number and op set/add/mul")
            return None, row
        res = fv if op == "set" else base + fv if op == "add" else base * fv
        r = spec.get("range")
        if r:
            width = r[1] - r[0]
            lo, hi = r[0] - width, r[1] + width
            if res < r[0] or res > r[1]:
                prob.warnings.append(f"{target} = {res:.3g} is outside its evidence range [{r[0]}, {r[1]}]")
            res2 = _clip(f"{target}", res, lo, hi, prob)
            fv = res2 if op == "set" else (res2 - base) if op == "add" else (res2 / base if base else 1.0)
            res = res2
        c.update(target=target, op=op, value=fv)
        row["summary"] = f"{reg.mechanisms[mid].label} · {pn}: {base:g} → {res:.3g} ({reg.mechanisms[mid].evidence})"
    elif kind == "close":
        ok, desc = _check_place_ref(target, sim, index, allow_types=True)
        if not ok:
            prob.errors.append(desc)
            return None, row
        c.update(target=target)
        row["summary"] = f"{desc} closes" + (f" for {c['duration_days']} days" if c["duration_days"] else "")
        if target.startswith("complex:"):
            U = sim.w.units
            units = np.where(U.complex_id == int(target.split(":")[1]))[0]
            row["n"] = int(np.isin(P["unit_id"], units).sum())
            row["who"] = "its residents (rehoused)"
    elif kind == "place":
        if not str(target).startswith("complex:"):
            prob.errors.append("place changes need target complex:<id>")
            return None, row
        ok, desc = _check_place_ref(target, sim, index)
        if not ok:
            prob.errors.append(desc)
            return None, row
        attr = ch.get("attr")
        if attr not in ("rent", "beds", "quality", "contracted"):
            prob.errors.append("attr must be rent, beds, quality or contracted")
            return None, row
        if attr == "contracted":
            c.update(target=target, attr=attr, op="set", value=bool(val))
        else:
            fv = _num(val)
            if fv is None:
                prob.errors.append(f"{attr} needs a number")
                return None, row
            op = {"rent": "mul", "beds": "mul", "quality": "add"}[attr]
            fv = _clip(attr, fv, *{"rent": (0.3, 3), "beds": (0, 3), "quality": (-1, 1)}[attr], prob)
            c.update(target=target, attr=attr, op=op, value=fv)
        row["summary"] = f"{desc}: {attr} {c['op']} {c['value']}"
    elif kind == "practice":
        lab = str(ch.get("practice_label") or label)[:50]
        traits = {}
        raw_traits = ch.get("traits") or []
        if isinstance(raw_traits, dict):
            raw_traits = [{"var": k_, "weight": w_} for k_, w_ in raw_traits.items()]
        for t in raw_traits if isinstance(raw_traits, list) else []:
            if isinstance(t, dict) and isinstance(t.get("var"), str) and t["var"] in P.specs and P.specs[t["var"]].dtype not in ("cat", "str") and _num(t.get("weight")) is not None:
                traits[t["var"]] = _clip(f"weight of {t['var']}", float(t["weight"]), -1.5, 1.5, prob)
            else:
                prob.warnings.append(f"ignored trait {t!r}")
        ew = [{"var": e["var"], "value": _clip(f"while-adopted {e['var']}", float(e["value"]), -0.1, 0.1, prob)}
              for e in ch.get("effects_while") or [] if isinstance(e, dict) and e.get("var") in STATES and _num(e.get("value")) is not None]
        c.update(practice_label=lab, seed_share=_clip("seed_share", _num(ch.get("seed_share"), 0.02), 0, 0.5, prob),
                 base=_clip("base", _num(ch.get("base"), -4.0), -8, 0, prob), traits=traits,
                 peer=_clip("peer", _num(ch.get("peer"), 1.0), 0, 3, prob), quit=_clip("quit", _num(ch.get("quit"), 0.005), 0, 0.1, prob),
                 effects_while=ew)
        row["summary"] = f"“{lab}” can spread ({round(100 * c['seed_share'])}% start)" + ("; adopters feel " + ", ".join(f"{e['var'].replace('_', ' ')} {e['value']:+g}" for e in ew) if ew else "")
    elif kind == "venue":
        v = ch.get("venue") or {}
        if not isinstance(v, dict) or v.get("vtype") not in VISITED_VTYPES:
            prob.errors.append(f"venue.vtype must be one of {', '.join(VISITED_VTYPES)}")
            return None, row
        lon, lat = _num(v.get("lon")), _num(v.get("lat"))
        if lon is None or lat is None or not (-111.8 <= lon <= -111.6 and 40.2 <= lat <= 40.35):
            prob.errors.append("venue lon/lat must be inside Provo/Orem")
            return None, row
        c.update(venue={"name": str(v.get("name") or label)[:60], "vtype": v["vtype"], "lon": lon, "lat": lat})
        row["summary"] = f"{c['venue']['name']} ({v['vtype'].replace('_', ' ')}) opens"
    row["when"] = when
    return c, row


def _check_place_ref(target, sim, index, allow_types=False) -> tuple[bool, str]:
    kind, _, rid = str(target).partition(":")
    if kind == "complex" and rid.isdigit():
        U = sim.w.units
        c = int(rid)
        if not (U.complex_id == c).any():
            return False, f"complex {c} has no units in this world"
        name = sim.w.complexes["name"][c] if c < sim.w.complexes.height else f"complex {c}"
        return True, str(name)
    if kind == "venue" and rid.isdigit():
        act = sim.systems["activity"]
        v = int(rid)
        if not 0 <= v < len(act.v_name):
            return False, f"venue {v} doesn't exist"
        if str(act.v_type[v]) not in VISITED_VTYPES:
            return False, f"{act.v_name[v]} is a {act.v_type[v]}, which nobody visits in the model — closing it changes nothing"
        return True, act.v_name[v]
    if kind == "venue_type" and allow_types:
        if rid not in VISITED_VTYPES:
            return False, f"venue type '{rid}' isn't visited in the model (visited: {', '.join(VISITED_VTYPES)})"
        return True, f"every {rid.replace('_', ' ')}"
    return False, f"'{target}' is not a place reference (complex:<id>, venue:<id>{', venue_type:<type>' if allow_types else ''})"


# ---------------------------------------------------------------------- lowering
def plan_id(plan: dict) -> str:
    return "wi" + hashlib.sha1(json.dumps(plan, sort_keys=True, default=str).encode()).hexdigest()[:8]


def lower(plan: dict, today: int, pid: str) -> list[dict]:
    """A validated plan → intervention atoms (small: the full plan is kept server-side)."""
    atoms = []
    for k, c in enumerate(plan["changes"]):
        a = {"id": f"{pid}:{k}", "plan": pid, "name": plan["title"], "label": c["label"], "start_day": today + c["start_offset_days"],
             "ramp_days": c["ramp_days"], "duration_days": c["duration_days"], "confidence": "speculative"}
        kind = c["kind"]
        if kind in ("world", "param"):
            a.update(target_type=kind, target=c["target"], op=c["op"], value=c["value"])
        elif kind == "trait":
            a.update(target_type="agent", target=c["target"], op=c["op"], value=c["value"], population=c.get("who"))
        elif kind == "nudge":
            a.update(target_type="offset", target=c["target"], op="add", value=c["value"], population=c.get("who"))
        elif kind == "event":
            a.update(target_type="event", target=c["target"], severity=c["severity"], population=c.get("who"))
            if c.get("repeat_every_days"):
                a["repeat_every"] = c["repeat_every_days"]
        elif kind == "shock":
            a.update(target_type="shock", target=c["event_label"], story=c["story"], motive=c["motive"], valence=c["valence"],
                     salience=c["salience"], effects=c["effects"], severity=c["severity"], population=c.get("who"))
            if c.get("repeat_every_days"):
                a["repeat_every"] = c["repeat_every_days"]
        elif kind == "close":
            a.update(target_type="close", target=c["target"])
        elif kind == "place":
            a.update(target_type="place", target=c["target"], attr=c["attr"], op=c["op"], value=c["value"])
        elif kind == "practice":
            a.update(target_type="practice", target=c["practice_label"], label=c["practice_label"], seed_share=c["seed_share"],
                     base=c["base"], traits=c["traits"], peer=c["peer"], quit=c["quit"], effects_while=c["effects_while"],
                     population=c.get("who"))
        elif kind == "venue":
            a.update(target_type="venue", value=c["venue"])
        if "share" in c:
            a["share"] = c["share"]
        atoms.append(a)
    # groups defined by where people live keep the people who lived there on the start day, when the same plan
    # closes a complex (nudges, practices and repeating events would otherwise find it empty once residents move)
    if any(a["target_type"] == "close" and str(a.get("target", "")).startswith("complex:") for a in atoms):
        for a in atoms:
            persistent = a["target_type"] in ("offset", "practice") or (a["target_type"] in ("event", "shock") and a.get("repeat_every"))
            if persistent and "complex_id" in json.dumps(a.get("population") or {}):
                a["freeze_population"] = True
    # same-day order: who-filters see the world before places change (residents of a burned complex are still there)
    order = {"close": 2, "place": 1}
    return sorted(atoms, key=lambda a: (a["start_day"], order.get(a["target_type"], 0)))

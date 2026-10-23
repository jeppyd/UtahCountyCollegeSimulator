"""Turning recorded exchanges into words: content plans, each person's communication style, and the deterministic
wording every view falls back on (analysis/phone.py, the scene player, the dating app).

The engine decides *what* is communicated (engine/systems/social.py: the act, its topic, the reason given or kept
back, the occasion and time it refers to). A content plan is that meaning in a form a writer can use — one entry per
line, with the speaker, the act, the slots it may mention (a time, a place, a reason, an occasion) and what it is
licensed to say (an invitation, an acceptance, an apology, a promise, a disclosure). The wording here is picked from
small banks by a hash of the line (the same words every time, nothing drawn, no model), then shaped by the speaker's
style. A model may re-word a plan (llm/talk/dialogue.py) but never add to it.

Style (`style`) is a stable *presentation* setting per person — brevity, warmth, emoji, lowercase, exclamation,
formality — from their personality traits plus a fixed per-person hash. It is labelled style, not a validated trait,
and it changes no behavior. It never depends on sex or religion.
"""
from __future__ import annotations

import hashlib
import json
import zlib

import numpy as np

from ..engine import clock
from ..engine.systems import social as S
from .person import synthetic_name

STYLE_NOTE = ("How someone writes (short or chatty, emoji, lowercase) is a presentation setting from their personality "
              "and a fixed per-person mix — it isn't a measured trait and it never changes what they do.")
SCHEMA = 3          # bump when plans or banks change (cached wording keyed on it)

REASON_WORDS = {"work": "I'm working", "class": "I have class then", "clash": "I already have something then",
                "ill": "I'm sick", "far": "I can't get over there tonight", "tired": "I'm wiped out tonight",
                "exam": "I have a test to study for", "partner": "I have plans with my person",
                "hurt": "I can't tonight", "not_feeling_it": "I can't tonight", "none": "I can't tonight"}
REASON_SHORT = {"work": "work", "class": "class", "clash": "another thing", "ill": "being sick", "far": "getting there",
                "tired": "being tired", "exam": "studying", "partner": "plans", "hurt": "", "not_feeling_it": "", "none": ""}
OCC_WORDS = {"dinner": "dinner", "gathering": "a get-together", "game_night": "game night", "party": "a party",
             "movie_night": "movie night", "hangout": "a hangout", "study_group": "a study group", "date": "a date"}
TOPIC_SMALL = {
    "class": (["how's {course} going for you?", "did you get the reading done?", "this class is going to be the death of me",
               "are you ready for the next assignment?"],
              ["honestly I'm behind 😅", "it's fine, kind of a lot", "pretty good actually", "barely, ha"]),
    "work": (["busy shift?", "how's work been?", "are you on all weekend again?"],
             ["it's been nonstop", "not bad today", "yeah, same as always", "slow, which is nice"]),
    "home": (["did anyone take out the trash?", "what are you up to tonight?", "is there any food left?",
              "how was your day?"],
             ["not it 😂", "nothing much, homework", "there's leftovers", "long but good"]),
    "church": (["good to see you", "how was your week?", "are you going to the activity?"],
               ["good to see you too!", "pretty good, you?", "maybe, depends on homework"]),
    "occasion": (["this is fun", "how do you know everyone here?", "did you try the food?"],
                 ["right? glad I came", "a few people, mostly through friends", "yes, so good"]),
    "outing": (["this was a good idea", "we should do this more often", "how's your week been?"],
               ["agreed", "for real", "busy, but this helps"]),
    "fitness": (["you here every day?", "leg day?"], ["trying to be", "unfortunately"]),
    "team": (["good game today", "are you coming to practice?"], ["thanks! you too", "yeah, see you there"]),
    "club": (["good to see you here", "are you coming next week?"], ["you too!", "I think so"]),
    "exam": (["are you ready for finals?", "how's studying going?", "I'm so not ready for this test"],
             ["not even close", "slowly", "same, it's bad"]),
    "none": (["how's it going?", "hey! how are you?", "what's new?"], ["good! you?", "not bad", "same old, you?"]),
}
WARM = (["you're the best, you know that?", "I'm really glad we're friends", "okay that was hilarious"],
        ["stop 😂 you too", "same, seriously", "I can't breathe 😂"])
TENSE = (["can we not do this right now", "that's not really fair", "okay, whatever"],
         ["I didn't mean it like that", "okay. sorry.", "fine"])


# ------------------------------------------------------------------------------------------------------------ style
def _h(*key) -> int:
    return zlib.crc32(repr(key).encode())


def style(sim, i: int) -> dict:
    """A person's stable writing style (see the module docstring)."""
    P = sim.w.P
    i = int(i)
    u = [((_h(int(sim.w.seed), i, k) % 1000) / 1000.0) for k in range(6)]
    ext = float(np.clip(P["extraversion"][i], -2.5, 2.5)) if "extraversion" in P else 0.0
    agr = float(np.clip(P["agreeableness"][i], -2.5, 2.5)) if "agreeableness" in P else 0.0
    con = float(np.clip(P["conscientiousness"][i], -2.5, 2.5)) if "conscientiousness" in P else 0.0
    age = float(P["age"][i]) if "age" in P else 21.0
    c = lambda x: float(np.clip(x, 0.0, 1.0))   # noqa: E731
    return {"brevity": c(0.5 - 0.12 * ext + 0.4 * (u[0] - 0.5)),
            "warmth": c(0.55 + 0.12 * agr + 0.3 * (u[1] - 0.5)),
            "emoji": c(0.35 + 0.08 * ext + 0.5 * (u[2] - 0.5) - 0.02 * max(age - 24, 0)),
            "lowercase": u[3] < 0.45 - 0.05 * con,
            "exclaim": c(0.4 + 0.12 * ext + 0.3 * (u[4] - 0.5)),
            "formality": c(0.3 + 0.1 * con + 0.3 * (u[5] - 0.5) + 0.015 * max(age - 24, 0))}


def style_words(st: dict) -> str:
    bits = ["short texts" if st["brevity"] > 0.62 else "chatty" if st["brevity"] < 0.38 else "medium-length texts",
            "lots of emoji" if st["emoji"] > 0.55 else "few emoji" if st["emoji"] < 0.25 else "some emoji",
            "all lowercase" if st["lowercase"] else "proper capitals",
            "warm" if st["warmth"] > 0.62 else "matter-of-fact" if st["warmth"] < 0.4 else ""]
    return ", ".join(b for b in bits if b)


APP_CHAT = [("so what are you studying?", ["honestly still figuring it out, you?", "nursing! it's a lot but I love it", "business, for now haha"]),
            ("what do you do for fun?", ["hiking when it's not freezing, you?", "honestly mostly board games lol", "I'm always down for a good movie"]),
            ("how was your weekend?", ["pretty chill, yours?", "busy! but fun", "lowkey just caught up on sleep haha"]),
            ("where are you from originally?", ["out of state, so Provo is still new", "born and raised here haha", "kind of all over"]),
            ("ok important question: favorite place to eat around here?", ["oh that's hard. anywhere with tacos", "anywhere with good fries",
                                                                           "I'll eat anything honestly"])]
SOFT_ACTS = {"decline_explained", "decline_brief", "late_reply", "apologize", "clarify", "ask_clarify", "disclose", "deflect",
             "support", "reassure", "promise", "date_no", "plan_change", "checkin_again"}
SOFT_EMOJI = ["🙁", "😅", "🙏"]


def shape(text: str, st: dict, key, channel: str = "text") -> str:
    """Apply a style to a line deterministically (never adds words that carry meaning)."""
    t = text.strip()
    if not t:
        return t
    spoken = channel == "in_person"
    if not spoken:
        if st["lowercase"]:
            t = t[0].lower() + t[1:] if not t[:2].isupper() else t
            t = t.replace(" I ", " i ").replace(" I'", " i'") if st["formality"] < 0.3 else t
        else:
            t = t[0].upper() + t[1:]
        if st["exclaim"] > 0.6 and t.endswith(".") and _h(key, "ex") % 2 == 0:
            t = t[:-1] + "!"
        if st["lowercase"] and t.endswith(".") and st["formality"] < 0.45:
            t = t[:-1]
        if st["emoji"] > 0.55 and not any(ord(ch) > 0x2000 for ch in t) and _h(key, "em") % 3 == 0:
            act = key[-1] if isinstance(key, tuple) and key and isinstance(key[-1], str) else ""
            bank = SOFT_EMOJI if act in SOFT_ACTS else ["🙂", "😊", "🙌", "😄"]
            t = t + " " + bank[_h(key, "e2") % len(bank)]
    else:
        t = t[0].upper() + t[1:]
    return t


def pick(options: list[str], st: dict | None, *key) -> str:
    """A line from a bank, the same one every time for the same moment; terse writers lean to the shorter options."""
    if not options:
        return ""
    if st is not None and len(options) > 2:
        ordered = sorted(options, key=len)
        n = len(ordered)
        lo = 0 if st["brevity"] > 0.5 else n // 3
        hi = (2 * n + 2) // 3 if st["brevity"] > 0.5 else n
        options = ordered[lo:max(hi, lo + 1)]
    return options[zlib.crc32(repr(key).encode()) % len(options)]


# --------------------------------------------------------------------------------------------------------- the plans
def _first(sim, i) -> str:
    return synthetic_name(sim.w.P, int(i)).split()[0]


def occ_slots(sim, oid: int) -> dict:
    """What a line about an occasion may mention: its kind, weekday, start time, place and host."""
    if oid is None or int(oid) < 0:
        return {}
    O = sim.book.occ
    p = O.pos([int(oid)])[0]
    if p < 0:
        return {}
    kind = sim.book.kinds[int(O.cols["kind"][p])]
    day = int(O.cols["day"][p])
    org = int(O.cols["organizer"][p])
    out = {"what": OCC_WORDS.get(kind, kind.replace("_", " ")), "kind": kind, "occ_day": day,
           "weekday": sim.cal.date(day).strftime("%A"), "time": clock.hhmm(int(O.cols["start"][p])) if O.cols["start"][p] >= 0 else None,
           "start": int(O.cols["start"][p]),
           "host": _first(sim, org) if org >= 0 else None, "host_id": org if org >= 0 else None}
    try:
        out["place"] = sim.systems["occasions"].place_label(int(oid))
    except Exception:  # noqa: BLE001
        out["place"] = None
    return out


def _when(sim, slots: dict, said_day: int) -> str:
    d = slots.get("occ_day")
    if d is None:
        return ""
    t = slots.get("time") or ""
    if d == said_day:
        return f"tonight at {t}" if t and slots.get("start", 0) >= 17 * 60 else f"today at {t}" if t else "today"
    if d == said_day + 1:
        return f"tomorrow at {t}" if t else "tomorrow"
    return f"{slots['weekday']} at {t}" if t else slots["weekday"]


def line(speaker, to, act: str, channel: str, day: int, block: int, slots: dict | None = None, *, ref=None, ex=None,
         msg=None, inv=None, kind: str = "line", licensed: dict | None = None, absent: bool = False, note: str = "") -> dict:
    """One planned line (or an absence, or a stage direction)."""
    return {"speaker": None if speaker is None else int(speaker), "to": None if to is None or to < 0 else int(to), "act": act,
            "channel": channel, "day": int(day), "block": int(block), "slots": slots or {}, "ref": ref, "ex": ex,
            "msg": msg, "inv": inv, "kind": kind, "licensed": licensed or {}, "absent": absent, "note": note}


def lid(spec: dict) -> str:
    """A stable id for a planned line (the same exchange has the same id on every phone)."""
    if spec.get("ex") is not None:
        return f"x{spec['ex']}" + (f".{spec['sub']}" if spec.get("sub") else "")
    if spec.get("msg") is not None:
        return f"m{spec['msg']}"
    if spec.get("inv") is not None:
        return f"i{spec['inv']}.{spec['act']}"
    return "s" + hashlib.sha1(json.dumps([spec["speaker"], spec["act"], spec["day"], spec["block"], spec["slots"]],
                                         sort_keys=True, default=str).encode()).hexdigest()[:10]


def content_key(specs: list[dict]) -> str:
    """Hash of what a group of lines means (not their wording): the cache key's content part."""
    keep = [{k: s.get(k) for k in ("speaker", "to", "act", "channel", "day", "block", "slots", "licensed", "absent", "kind")}
            for s in specs]
    return hashlib.sha1(json.dumps([SCHEMA, keep], sort_keys=True, default=str).encode()).hexdigest()[:16]


# ------------------------------------------------------------------------------------------- deterministic wording
def fallback(sim, spec: dict, styles: dict | None = None) -> str:
    """The structured, accurate wording of a planned line (no model)."""
    styles = styles if styles is not None else {}
    sp = spec.get("speaker")
    st = styles.get(sp) if sp is not None else None
    if st is None and sp is not None:
        st = styles[sp] = style(sim, sp)
    a = spec["act"]
    sl = spec.get("slots") or {}
    key = (lid(spec), a)
    to = _first(sim, spec["to"]) if spec.get("to") is not None else ""
    when = sl.get("when") or ""
    what = sl.get("what") or "it"
    reason = sl.get("reason") or "none"
    if spec.get("kind") == "stage":
        return sl.get("text") or ""
    if spec.get("absent"):
        return sl.get("text") or ""
    t = ""
    if a == "invite":
        t = pick([f"want to come to {what} {when}?", f"{what} {when}, you should come!", f"are you free {when}? we're doing {what}",
                  f"{what} at my place {when}, come!"] if sl.get("at_home") else
                 [f"want to come to {what} {when}?", f"{what} {when}, you should come!", f"are you free {when}? {what}"], st, *key)
    elif a == "accept":
        t = pick(["yes!! I'll be there", "count me in", "I'm in", "for sure", "yes, sounds fun", "see you then!"], st, *key)
    elif a == "maybe":
        t = pick(["maybe? I'll let you know", "I'll try to make it", "possibly!"], st, *key)
    elif a == "decline_explained":
        r = REASON_WORDS.get(reason, "I can't tonight")
        extra = " next time for sure though" if sl.get("promise") else ""
        t = pick([f"ahh {r}, sorry!{extra}", f"I wish, {r}.{extra}", f"can't, {r} 😕{extra}", f"{r}, so I can't make it.{extra}"],
                 st, *key)
    elif a == "decline_brief":
        t = pick(["can't tonight, sorry!", "I can't make it", "not tonight, sorry", "can't, sorry"], st, *key)
    elif a == "no_answer":
        t = ""
    elif a == "checkin":
        t = pick(["hey! how's your week going?", "how are you doing?", "hiii how's life", "thinking about you, how are things?",
                  "hey stranger, how are you?", "how's everything going?"], st, *key)
    elif a == "checkin_again":
        t = pick(["hey, just checking in again, no pressure", "hope your week's going okay!", "thinking about you, hope all is well"],
                 st, *key)
    elif a == "ask_clarify" and sl.get("topic") == "silence":
        t = pick(["hey, is everything okay? haven't heard from you", "did I do something? just want to make sure we're good",
                  "hey, you okay? you've been quiet"], st, *key)
    elif a == "ask_clarify" and sl.get("channel_text"):
        t = pick(["hey, I heard you all got together, would love an invite next time!", "saw you guys hung out, I'd love to come next time",
                  "hey! looked like fun the other night. include me next time?"], st, *key)
    elif a == "ask_clarify":
        host = f"{sl['host']}'s" if sl.get("host") else "yours"
        t = pick([f"can I ask you something? I heard about {what} at {host} and kind of felt left out",
                  "hey, did I miss something? I heard you all got together", "honest question, is everything good between us?"],
                 st, *key)
    elif a == "reply":
        t = pick(["good! busy but good. you?", "so good to hear from you!", "honestly kind of a week haha. you?",
                  "I'm good! been a busy week", "aw thanks for checking in", "pretty good! what about you?"], st, *key)
    elif a == "late_reply":
        t = pick(["sorry, just saw this! been a crazy week", "ahh sorry I'm so bad at texting, I'm good! you?",
                  "sorry for the slow reply! I'm doing okay"], st, *key) if sl.get("apology") else \
            pick(["good! sorry, just saw this", "hey! doing alright", "just seeing this, all good here"], st, *key)
    elif a == "clarify" and sl.get("topic") == "silence":
        r = REASON_WORDS.get(reason)
        t = pick([f"no, all good! {r} a lot lately, sorry" if reason not in ("none", "not_feeling_it") else "no, all good! sorry, it's been a week",
                  "we're totally good, I've just been swamped"], st, *key)
    elif a == "clarify" and sl.get("revealed_belief"):
        t = pick(["honestly I figured you weren't interested, you'd said no a bunch", "I thought you didn't want to come, you kept saying no",
                  "oh, I assumed you were over it, you'd turned me down a few times"], st, *key)
    elif a == "clarify":
        rs = REASON_SHORT.get(reason, "")
        t = pick([f"hey, I've been saying no a lot because of {rs}, not because I don't want to come. I'd love to next time"
                  if rs else "I know I've said no a lot lately. it's not you, I'd love to come next time",
                  f"just so you know, it's been {rs}, I really do want to hang out" if rs else "I really do want to hang out, it's just been a lot"],
                 st, *key)
    elif a == "reassure":
        t = pick(["oh! I totally thought you weren't interested, glad you said something. you're always invited",
                  "of course! we'd love to have you"] if sl.get("held") else
                 ["of course! we'd love to have you", "no worries at all, you're always welcome", "ahh we miss you, come next time!"], st, *key)
    elif a == "apologize":
        t = pick(["ah I'm sorry, it was really last minute", "sorry, that wasn't on purpose, I should've texted you",
                  "I'm sorry, I didn't think about it"], st, *key)
    elif a == "disclose":
        t = pick(["honestly not great. it's been a really rough few weeks", "kind of struggling lately, not gonna lie",
                  "I've been having a hard time, if I'm honest"], st, *key)
    elif a == "deflect":
        t = pick(["I'm good! just busy", "fine! you know how it is", "doing okay, just tired"], st, *key)
    elif a == "support":
        t = pick(["I'm really sorry. I'm here if you want to talk", "that sounds really hard. want to get food this week?",
                  "thank you for telling me. I'm here for you"], st, *key)
    elif a == "opener":
        t = pick(["hey! how's your week going?", "hi! fellow {school} student?".format(school=sl.get("school") or "Provo"),
                  "hey :) what are you up to this weekend?", "hi! your profile made me smile"], st, *key)
    elif a == "app_reply":
        t = pick(["hey! sorry, just seeing this. pretty good, you?", "hi! not bad, slow week. you?"] if sl.get("late") else
                 ["hey! pretty good, you?", "hi! good, what about you?", "haha hi :) good week so far"], st, *key)
    elif a == "app_chat":
        # one question and its answer per chatting day (both lines share the exchange, so they stay a pair)
        pair = (min(spec["speaker"], spec["to"] or 0), max(spec["speaker"], spec["to"] or 0))
        q, answers = APP_CHAT[(_h(*pair, "q") + spec["day"]) % len(APP_CHAT)]      # a new question each day
        t = pick(answers, st, *key) if spec.get("sub") == 2 else q
    elif a == "ask_date":
        t = pick([f"would you want to get {sl.get('date_words') or 'dinner'} sometime?", "want to grab food this week?",
                  "would you want to go out sometime?"], st, *key)
    elif a == "date_yes":
        t = pick(["yes! I'd like that", "sure, sounds fun :)", "I'd love that", "yes, I'm free this week"], st, *key)
    elif a == "date_no":
        t = pick(["that's really nice of you, but I don't think so", "I'm flattered, but I don't think we're a match",
                  "thank you for asking! I'm going to pass though"], st, *key)
    elif a == "plan_change":
        t = pick([f"so sorry, we have to cancel {what}", f"change of plans, {what} is off, sorry!"], st, *key)
    elif a == "news":
        t = sl.get("text") or ""
    elif a == "invite_group":
        t = pick([f"{what} {when}! who's in?", f"doing {what} {when}, come!", f"anyone free {when}? {what}"], st, *key)
    elif a in ("small_talk", "warm_moment", "tension", "introduce", "plans_talk", "avoid_talk"):
        t = sl.get("line") or ""
    elif a == "reassure_late":
        t = sl.get("line") or ""
    else:
        t = sl.get("line") or ""
    return shape(t, st, key, spec.get("channel", "text")) if st is not None else t


def in_person_lines(sim, row: dict) -> list[dict]:
    """An in-person exchange as a few planned lines (the act is one record; the lines realize it)."""
    a, b = row["speaker"], row["to"]
    act = row["act_name"]
    topic = row["topic_name"]
    day, block = row["day"], row["block"]
    ex = row["id"]
    key = (ex,)
    out = []
    sl = {"topic": topic}

    def L(sp, to, kind_act, text, sub, **lic):
        s = line(sp, to, kind_act, "in_person", day, block, {**sl, "line": text}, ex=ex, licensed=lic)
        s["sub"] = sub
        out.append(s)

    if act in ("small_talk", "warm_moment", "tension"):
        bank = TOPIC_SMALL.get(topic, TOPIC_SMALL["none"])
        if act == "warm_moment":
            bank = WARM
        elif act == "tension":
            bank = TENSE
        if topic == "plans" and row.get("occ"):
            o = row["occ"]
            q = f"you're coming to {o.get('host') + chr(39) + 's ' if o.get('host') else ''}{o.get('what', 'it')} {o.get('when', '')}?".replace("  ", " ")
            L(a, b, "plans_talk", q, 1, plans=True)
            L(b, a, "plans_talk", pick(["yeah! see you there", "planning on it", "I said yes, so yes"], None, *key, "p"), 2, plans=True)
            return out
        L(a, b, act, pick(bank[0], None, *key, "q").replace("{course}", "this class"), 1)
        L(b, a, act, pick(bank[1], None, *key, "r"), 2)
        if act == "warm_moment" or (row.get("tone") or 0) > 1.4:
            out.append({**line(None, None, "stage", "in_person", day, block, {"text": "They both laugh."}, ex=ex, kind="stage"), "sub": 3})
        if act == "tension":
            out.append({**line(None, None, "stage", "in_person", day, block, {"text": "It goes quiet for a second."}, ex=ex, kind="stage"), "sub": 3})
    elif act == "introduce":
        A, B = _first(sim, a), _first(sim, b)
        host = (row.get("occ") or {}).get("host")
        L(a, b, "introduce", f"hi, I'm {A}", 1, names=True)
        L(b, a, "introduce", f"Nice to meet you, {B}!" if not host else f"{B}! How do you know {host}?", 2, names=True)
        if host:
            L(a, b, "introduce", pick(["we're in the same ward", "through friends", "we've known each other a while"], None, *key, "h"), 3)
    elif act == "avoid":
        txt = {"left_out": f"{_first(sim, a)} thinks about bringing up being left out, and doesn't.",
               "silence": f"{_first(sim, a)} almost asks why {_first(sim, b)} never texted back. They talk about something else."}.get(
            topic, f"{_first(sim, a)} lets it go for now.")
        out.append({**line(None, None, "stage", "in_person", day, block, {"text": txt}, ex=ex, kind="stage"), "sub": 1})
    return out


def label_act(act: str) -> str:
    return {"decline_explained": "said no, with a reason", "decline_brief": "said no", "no_reply": "no reply",
            "late_reply": "answered late", "ask_clarify": "asked about it", "clarify": "explained",
            "reassure": "reassured them", "disclose": "told them how they're really doing", "deflect": "said they're fine",
            "withdraw": "pulled back", "avoid": "didn't bring it up", "promise": "said next time for sure",
            "opener": "sent the first message", "app_reply": "answered", "ask_date": "asked them out",
            "date_yes": "said yes", "date_no": "said no", "fade": "stopped talking"}.get(act, act.replace("_", " "))

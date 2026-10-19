"""The wording checker: a model's answer may only say what the cited claims support.

An answer is {"sentences": [{"text", "claims": [ids]}]}. Each sentence gets a verdict {ok, reasons}:
* it cites at least one claim, and every cited id exists;
* every number in it (digits, spelled-out numbers, percentages, "half", "a third"…) matches a value in a cited claim
  within the precision it is stated at ("about"/"around"… loosens that to ±10%);
* every person or place name in it belongs to a cited claim (its subject or refs), and no other person's name appears;
* causal wording (because, so, led to, caused, made them…, due to, causal "since", which is why…) needs a cited
  `cause` claim, or a `measurement` that is a decomposition share of at least CAUSE_SHARE;
* feeling and level words (lonely, very stressed, happy, close, devout…) need a cited claim on that field whose value
  is in the range the words mean (and about the person the sentence names), or a group count whose definition is that
  feeling (`licenses: [field]`);
* in an interview only the interviewee's own perceptions, beliefs and facts may be cited — never someone else's
  hidden state.
Deterministic and model-free; tests/data/talk_cases.json measures it (catch rate and false-alarm rate).
"""
from __future__ import annotations

import re

CAUSE_SHARE = 0.2
INTERVIEW_KINDS = ("perception", "belief")

# ---------------------------------------------------------------------------------------------- causal wording
_TEMPORAL_SINCE = (r"then|last|early|late|the (?:start|beginning|end|fall|spring|summer|winter)|\d|day|week|month|year|"
                   r"january|february|march|april|may|june|july|august|september|october|november|december|"
                   r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|fall|spring|summer|winter|arriving|moving|"
                   r"starting|they (?:arrived|moved|started|began)|(?:he|she|i|we) (?:arrived|moved|started|began)")
CAUSAL = [
    r"\bbecause\b", r"\bdue to\b", r"\bowing to\b", r"\bthanks to\b", r"\bas a result\b", r"\bresult(?:ed|s)? (?:of|in)\b",
    r"\b(?:led|lead|leads|leading) to\b", r"\bcaus(?:e|ed|es|ing)\b", r"\b(?:which|that)(?:'s| is| was) why\b",
    r"\bthat's why\b", r"\bthis is why\b", r"\bwhy (?:she|he|they|i|we)\b", r"\btherefore\b", r"\bhence\b",
    r"\bcontribut(?:ed|es|ing) to\b", r"\btrigger(?:ed|s)?\b", r"\bdr(?:ove|iven by)\b",
    r"\b(?:made|makes|making) (?:him|her|them|me|us|people|everyone|everybody)\b", r"\bso that\b",
    r"(?:^|[,;]\s*|\band\s+)so\b(?!\s+(?:much|many|far|long|few|little|very|often|that\b))",
    rf"\bsince\b(?!\s+(?:{_TEMPORAL_SINCE}))",
]
_CAUSAL_RE = [re.compile(p, re.I) for p in CAUSAL]

# ---------------------------------------------------------------------------------------------- feeling and level words
# (phrase regex, field, low, high): the field's value (its own scale, see ucsim/scales.py) must lie in [low, high].
# Longer phrases come first; a matched phrase is consumed so "very lonely" isn't read again as "lonely".
NEG = r"(?:not|n't|never|no longer|isn't|wasn't|aren't|doesn't feel|don't feel|didn't feel)\s+(?:\w+\s+)?"
FEELINGS: list[tuple[str, str, float, float]] = [
    (NEG + r"(?:at all )?lonely", "loneliness", 0.0, 0.22),
    (r"(?:very|extremely|deeply|really|so|terribly|incredibly) lonely|lonely most days|isolated", "loneliness", 0.55, 1.0),
    (r"(?:a (?:little|bit)|somewhat|sometimes|occasionally|now and then|a little bit) lonely|lonely now and then",
     "loneliness", 0.1, 0.6),
    (r"lonely|loneliness is high", "loneliness", 0.28, 1.0),
    (NEG + r"stressed", "stress", 0.0, 0.3),
    (r"(?:very|extremely|really|so|incredibly) stressed|stressed out|overwhelmed|under a lot of (?:stress|pressure)",
     "stress", 0.58, 1.0),
    (r"(?:a (?:little|bit)|somewhat|slightly|mildly) stressed", "stress", 0.1, 0.5),
    (r"stressed", "stress", 0.33, 1.0),
    (r"\bcalm\b|relaxed|at ease", "stress", 0.0, 0.3),
    (r"(?:very|extremely|really|so) anxious", "anxiety", 0.6, 1.0),
    (r"anxious|worried", "anxiety", 0.38, 1.0),
    (r"(?:very|extremely|really|so|deeply) guilty", "guilt", 0.58, 1.0),
    (r"guilty", "guilt", 0.33, 1.0),
    (r"happy together|happily (?:married|dating)|(?:a )?happy (?:marriage|relationship)", "relationship_satisfaction", 0.62, 1.0),
    (r"unhappy together|(?:an )?unhappy (?:marriage|relationship)|struggling together", "relationship_satisfaction", 0.0, 0.42),
    (r"(?:very|extremely|really|so) happy|thrilled|elated|doing great", "mood", 0.78, 1.0),
    (r"unhappy|miserable|\bdown\b|\bsad\b|in a low place|feeling low", "mood", 0.0, 0.42),
    (r"\bhappy\b|cheerful|in a good mood", "mood", 0.58, 1.0),
    (r"left out|(?:doesn't|don't|didn't) fit in|out of place|(?:doesn't|don't) belong", "belonging", 0.0, 0.42),
    (r"\bbelongs?\b|fits? in|feels? at home", "belonging", 0.58, 1.0),
    (r"(?:very|really|so) close|closest", "closeness", 0.7, 1.0),
    (r"drifted apart|distant|not close", "closeness", 0.0, 0.32),
    (r"\bclose (?:to|with)\b|(?:are|were|became|'re) close\b", "closeness", 0.45, 1.0),
    (r"devout|strong (?:believer|faith|testimony)|believes? (?:strongly|deeply|firmly)|fully believes?", "faith_belief", 0.72, 1.0),
    (r"doubt(?:s|ing|ed)?|questioning (?:their|his|her|my) faith|lost (?:their|his|her|my) faith", "faith_belief", 0.0, 0.55),
    (r"insecure|low self-esteem", "self_esteem", 0.0, 0.42),
    (r"\bconfident\b|self-assured", "self_esteem", 0.58, 1.0),
]
_FEEL_RE = [(re.compile(rf"(?<!\w){p}(?!\w)", re.I), f, lo, hi) for p, f, lo, hi in FEELINGS]

# ---------------------------------------------------------------------------------------------- numbers
_WORDNUM = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
    "eighteen nineteen twenty".split())}
_WORDNUM.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
                 "hundred": 100, "a hundred": 100, "thousand": 1000, "a thousand": 1000, "a dozen": 12, "dozen": 12})
_FRACTIONS = {"half": 0.5, "a third": 1 / 3, "one third": 1 / 3, "two thirds": 2 / 3, "two-thirds": 2 / 3,
              "a quarter": 0.25, "one quarter": 0.25, "three quarters": 0.75, "three-quarters": 0.75, "a fifth": 0.2,
              "one in four": 0.25, "one in five": 0.2, "one in three": 1 / 3, "one in ten": 0.1}
_HEDGE = re.compile(r"\b(?:about|around|roughly|nearly|almost|approximately|some|close to|just over|just under|over|under|"
                    r"more than|less than|fewer than|at least)\s*$", re.I)
_NUM_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(\s*(?:%|percent\b))?")
_WORD_RE = re.compile(r"(?<!\w)(" + "|".join(sorted((re.escape(k) for k in [*_FRACTIONS, *_WORDNUM] if k not in ("zero", "one")),
                                                    key=len, reverse=True))
                      + r")(?:[- ](one|two|three|four|five|six|seven|eight|nine))?(\s*(?:%|percent\b))?(?!\w)", re.I)


def numbers_in(text: str) -> list[dict]:
    """Numbers stated in a sentence: {value, percent, decimals, hedged, text}."""
    out = []
    taken = []
    for m in _FRACTIONS_RE.finditer(text):
        out.append({"value": _FRACTIONS[m.group(0).lower()], "percent": False, "decimals": 2, "hedged": True,
                    "fraction": True, "text": m.group(0)})
        taken.append(m.span())
    for m in _NUM_RE.finditer(text):
        v = float(m.group(1).replace(",", "") + (m.group(2) or ""))
        out.append({"value": v, "percent": bool(m.group(3)), "decimals": len(m.group(2) or "") - (1 if m.group(2) else 0),
                    "hedged": bool(_HEDGE.search(text[:m.start()])), "text": m.group(0)})
    for m in _WORD_RE.finditer(text):
        if any(a <= m.start() < b for a, b in taken):
            continue
        w = m.group(1).lower()
        if w in _FRACTIONS:
            continue
        v = _WORDNUM[w] + (_WORDNUM[m.group(2).lower()] if m.group(2) else 0)
        out.append({"value": float(v), "percent": bool(m.group(3)), "decimals": 0,
                    "hedged": bool(_HEDGE.search(text[:m.start()])), "text": m.group(0)})
    return out


_FRACTIONS_RE = re.compile(r"(?<!\w)(" + "|".join(sorted(map(re.escape, _FRACTIONS), key=len, reverse=True)) + r")(?!\w)", re.I)


def claim_numbers(c: dict) -> list[float]:
    vals = []
    for k in ("value", "share", "count", "n"):
        v = c.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            vals.append(float(v))
    vals += [float(x) for x in c.get("numbers", []) if isinstance(x, (int, float))]
    for n in numbers_in(c.get("text", "")):
        vals.append(n["value"] / 100 if n["percent"] else n["value"])
        if n["percent"]:
            vals.append(n["value"])
    return vals


def number_ok(n: dict, vals: list[float]) -> bool:
    """A stated number matches a claim value at the precision it is stated (a share may be stated as a percent)."""
    x = n["value"]
    tol = 0.5 * 10 ** (-n["decimals"]) + 1e-9
    for c in vals:
        cands = [c]
        if 0 < abs(c) <= 1:
            cands.append(c * 100)
        for cand in cands:
            if n.get("fraction"):
                if abs(x - c) <= 0.04 or abs(x * 100 - c) <= 4:
                    return True
                continue
            t = max(tol, 0.1 * abs(cand) + tol) if n["hedged"] else tol
            if abs(cand - x) <= t:
                return True
    return False


# ---------------------------------------------------------------------------------------------- names
def _ref_names(c: dict) -> list[str]:
    out = []
    for r in [c.get("subject") or {}, *(c.get("refs") or [])]:
        nm = (r or {}).get("name")
        if nm:
            out.append(nm)
    return out


def _person_ids(c: dict) -> set:
    out = set()
    for r in [c.get("subject") or {}, *(c.get("refs") or [])]:
        if (r or {}).get("kind") == "person":
            out.add(r.get("id"))
    return out


def _mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(name)}(?:'s)?(?!\w)", text) is not None


def _first(name: str) -> str:
    return name.split()[0]


# ---------------------------------------------------------------------------------------------- the checker
class Checker:
    """Checks sentences against a fact sheet. `claims`: id -> claim. `known_names`: name -> Ref for every person or
    place the checker should recognize (the fact sheet's own names are added automatically). `name_parts`: (first
    names, last names) of the world's synthetic names, to catch invented people."""

    def __init__(self, claims: dict, known_names: dict | None = None, mode: str = "ask", self_id=None,
                 name_parts: tuple[set, set] | None = None):
        self.claims = claims
        self.mode = mode
        self.self_id = self_id
        names = dict(known_names or {})
        for c in claims.values():
            for r in [c.get("subject") or {}, *(c.get("refs") or [])]:
                if (r or {}).get("name"):
                    names.setdefault(r["name"], r)
        self.names = names
        if name_parts is None:
            from ...analysis.person import FIRST_F, FIRST_M, LAST
            name_parts = (set(FIRST_F) | set(FIRST_M), set(LAST))
        self.firsts, self.lasts = name_parts

    def check(self, sentence: dict) -> dict:
        text = str(sentence.get("text", "")).strip()
        ids = [str(x) for x in (sentence.get("claims") or [])]
        reasons: list[str] = []
        cited = [self.claims[i] for i in ids if i in self.claims]
        missing = [i for i in ids if i not in self.claims]
        if missing:
            reasons.append(f"cites claims that don't exist: {', '.join(missing[:4])}")
        if not cited:
            reasons.append("doesn't cite any fact")
            return {"text": text, "claims": ids, "ok": False, "reasons": reasons}
        # interview: only what this person perceives or believes, or facts about themselves
        if self.mode == "interview":
            for c in cited:
                subj = c.get("subject") or {}
                own = subj.get("kind") == "person" and subj.get("id") == self.self_id
                if c.get("kind") not in INTERVIEW_KINDS and not own:
                    reasons.append(f"uses something they couldn't know ({c.get('id')}: another person's inner state)")
        # numbers
        vals = [v for c in cited for v in claim_numbers(c)]
        for n in numbers_in(text):
            if not number_ok(n, vals):
                reasons.append(f"the number \"{n['text'].strip()}\" isn't in the cited facts")
        # names
        cited_names = {nm for c in cited for nm in _ref_names(c)}
        cited_firsts = {_first(nm) for nm in cited_names}
        named_people: set = set()
        for nm, ref in self.names.items():
            if _mentions(text, nm):
                if nm not in cited_names:
                    reasons.append(f"names {nm}, who isn't in the cited facts")
                elif (ref or {}).get("kind") == "person":
                    named_people.add(ref.get("id"))
        for m in re.finditer(r"(?<!\w)([A-Z][a-z]+)(?:\s+([A-Z][a-z]+))?(?!\w)", text):
            first, last = m.group(1), m.group(2)
            full = f"{first} {last}" if last else None
            if full and (full in self.names or full in cited_names):
                continue
            if first in self.firsts and (last is None or last in self.lasts):
                if full and last in self.lasts and full not in cited_names:
                    reasons.append(f"names {full}, who isn't in the cited facts")
                elif last is None and first not in cited_firsts and any(_first(k) == first for k in self.names):
                    reasons.append(f"names {first}, who isn't in the cited facts")
                elif last is None and first in cited_firsts:
                    for nm in cited_names:
                        if _first(nm) == first and (self.names.get(nm) or {}).get("kind") == "person":
                            named_people.add(self.names[nm].get("id"))
        if self.mode == "interview" and re.search(r"(?<!\w)(?:I|I'm|I've|I'd|me|my|myself)(?!\w)", text):
            named_people.add(self.self_id)
        # causal wording
        for rx in _CAUSAL_RE:
            m = rx.search(text)
            if m:
                ok = any(c.get("kind") == "cause" or (c.get("kind") == "measurement" and float(c.get("share") or 0) >= CAUSE_SHARE)
                         for c in cited)
                if not ok:
                    reasons.append(f"says \"{m.group(0).strip(' ,;')}\" without a cited cause")
                break
        # feeling and level words
        rest = text
        for rx, field, lo, hi in _FEEL_RE:
            m = rx.search(rest)
            if not m:
                continue
            rest = rest[:m.start()] + " " * (m.end() - m.start()) + rest[m.end():]
            if any(field in (c.get("licenses") or ()) for c in cited):
                continue                    # a group count defined by this feeling ("lonely" = loneliness ≥ 0.5)
            on = [c for c in cited if c.get("field") == field and isinstance(c.get("value"), (int, float))]
            if named_people:
                about = [c for c in on if (c.get("subject") or {}).get("id") in named_people
                         or _person_ids(c) & named_people]
                if on and not about:
                    reasons.append(f"\"{m.group(0)}\" is about someone else in the cited facts")
                    continue
                on = about or on
            if not on:
                reasons.append(f"\"{m.group(0)}\" isn't backed by a cited fact about {field.replace('_', ' ')}")
            elif not any(lo <= float(c["value"]) <= hi for c in on):
                c = on[0]
                band = f" ({c['band']})" if c.get("band") else ""
                reasons.append(f"\"{m.group(0)}\" overstates or understates it: {field.replace('_', ' ')} is "
                               f"{float(c['value']):.2f}{band}")
        return {"text": text, "claims": ids, "ok": not reasons, "reasons": reasons}

    def check_all(self, answer: dict) -> list[dict]:
        return [self.check(s) for s in (answer or {}).get("sentences", []) if str(s.get("text", "")).strip()]


def repair_note(verdicts: list[dict]) -> str:
    """The checker's reasons, as the repair round's instructions."""
    lines = []
    for k, v in enumerate(verdicts):
        if not v["ok"]:
            lines.append(f"- sentence {k + 1} \"{v['text'][:160]}\": " + "; ".join(v["reasons"]))
    return "\n".join(lines)

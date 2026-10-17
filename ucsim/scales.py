"""What a variable's numbers mean, for people reading the workstation: the scale's ends in words, the survey answer
each step stands for, and how to read standardized traits. Served with the registry (`VarSpec.to_dict()["scale"]`).

Sources, in order: survey answer wording (`ingest/survey_spec.py`, matched through the variable's `copula
<survey>.<item>` init), the hand-written words below, then generic rules by range and units."""
from __future__ import annotations

import re
from functools import lru_cache

# Low and high ends of 0–1 (and other) scales, in words.
ENDS = {
    "mood": ("very unhappy", "very happy"),
    "stress": ("calm", "overwhelmed"),
    "loneliness": ("not lonely", "extremely lonely"),
    "anxiety": ("at ease", "extremely anxious"),
    "belonging": ("feels like an outsider", "fully belongs"),
    "self_esteem": ("very low confidence", "very high confidence"),
    "guilt": ("no guilt", "overwhelming guilt"),
    "fatigue": ("fully rested", "exhausted"),
    "purpose": ("aimless", "strong sense of purpose"),
    "financial_stress": ("no money worries", "severe money stress"),
    "academic_pressure": ("no pressure", "crushing pressure"),
    "romantic_longing": ("no longing", "intense longing"),
    "life_satisfaction": ("completely dissatisfied", "completely satisfied"),
    "outsider": ("feels part of the mainstream", "feels like a complete outsider"),
    "faith_belief": ("doesn't believe", "fully believes"),
    "faith_certainty": ("very unsure", "completely certain"),
    "religious_identity": ("not part of who they are", "central to who they are"),
    "institutional_trust": ("no trust in church leaders", "complete trust"),
    "orthodoxy": ("rejects specific teachings", "accepts every teaching"),
    "moral_autonomy": ("standards are never optional", "own conscience overrides standards"),
    "history_struggle": ("no struggle", "severe struggle"),
    "lgbtq_tension": ("no tension", "severe tension"),
    "family_expectation": ("no family pressure", "strong family expectation"),
    "chastity_commitment": ("no commitment", "complete commitment"),
    "dating_motivation": ("not interested in dating", "very eager to date"),
    "relationship_satisfaction": ("very unhappy together", "very happy together"),
    "relationship_commitment": ("ready to leave", "fully committed"),
    "ward_belonging": ("an outsider in the ward", "fully at home in the ward"),
    "roommate_cohesion": ("roommates dislike each other", "roommates are close"),
    "coping_need": ("coping fine", "barely coping"),
    "rumination": ("lets things go", "dwells on everything"),
    "routine_strength": ("no routine", "very settled week"),
    "expect_social": ("expects coldness", "expects warmth"),
    "self_eff_academic": ("doubts they can do it", "sure they can do it"),
    "perceived_support": ("no one to turn to", "plenty of support"),
    "support_actual": ("no real support", "plenty of support"),
    "porn_incongruence": ("no distress", "severe distress"),
    "perceived_friend_belief": ("thinks friends don't believe", "thinks friends fully believe"),
    "friend_belief_actual": ("friends don't believe", "friends fully believe"),
    "coping_relief": ("no relief", "full relief"),
    "memory_tone": ("mostly painful memories", "mostly happy memories"),
    "practice_habit": ("no habit", "fully automatic"),
    "private_practice": ("no prayer or study", "devoted daily practice"),
    "own_religiosity": ("doesn't matter to them", "central to their life"),
    "home_faith_culture": ("not observant", "very observant"),
}
# Shares and probabilities: shown as percentages.
PERCENT = re.compile(r"(^|_)(rate|share|prob)($|_)|attend$")
PERCENT_DESC = re.compile(r"\b(share|probability|chance|rate) of\b|\bshare of\b", re.I)


@lru_cache(maxsize=1)
def _survey_levels() -> dict[str, list[str]]:
    """'<survey>.<item>' -> the answer wording for each code 0..k-1 (question metadata only, never responses)."""
    try:
        from .ingest.survey_spec import SPEC
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for survey, spec in SPEC.items():
        for entry in (spec.get("vars") or {}).values():
            if len(entry) >= 3 and entry[1] == "ord" and isinstance(entry[2], dict) and entry[2].get("levels"):
                for alias in {survey, survey.replace("-", "_"), survey.split("-")[0]}:    # copula names use short forms
                    out[f"{alias}.{entry[0]}"] = list(entry[2]["levels"])
    return out


def _levels_for(v) -> list[str] | None:
    if v.ordinal:
        return list(v.ordinal)
    m = re.match(r"\s*copula\s+([\w]+\.[\w]+)", v.init or "")
    if not m or "reversed" in (v.init or ""):
        return None
    lv = _survey_levels().get(m.group(1))
    if lv and v.range and v.range[0] == 0 and v.range[1] == len(lv) - 1:
        return lv
    return None


def scale_of(v) -> dict | None:
    """{min, max, low, high, levels?, percent?, z?, note?} for a numeric person variable, else None."""
    if v.dtype in ("bool", "cat", "str") or v.categories or v.id.endswith("_id") or v.id.endswith("_day"):
        return None
    lo, hi = (v.range or [None, None])[:2]
    out: dict = {"min": lo, "max": hi}
    if v.units == "z":
        out.update(z=True, low="far below average", high="far above average",
                   note="A standard score: 0 is the average student; −1 and +1 are lower or higher than about 5 in 6 people; ±2 is rare.")
        return out
    levels = _levels_for(v)
    if levels:
        out.update(levels=levels, low=levels[0], high=levels[-1],
                   note=f"Survey answer scale: {lo:g} = “{levels[0]}” … {hi:g} = “{levels[-1]}”. In-between values are averages or "
                        "drift between answers." if lo is not None else None)
        return out
    if lo == 0 and hi == 1 and (PERCENT.search(v.id) or PERCENT_DESC.search(v.desc or "") or v.label.lower().endswith(" rate")
                                or "mean attendance" in (v.desc or "")):
        out.update(percent=True, low="0%", high="100%")
        return out
    if v.id in ENDS:
        out["low"], out["high"] = ENDS[v.id]
    elif v.id.startswith(("cares_", "imp_")):
        out["low"], out["high"] = "doesn't matter to them", "matters most"
    elif v.id.startswith("drive_"):
        out["low"], out["high"] = "no pull right now", "strongest pull"
    elif v.id.startswith(("sat_", "expect_")):
        out["low"], out["high"] = "none", "fully"
    elif lo is not None and hi is not None and not v.units and v.dtype in ("f4", "f8") and hi <= 10 and not v.id.startswith("gpa"):
        out["low"], out["high"] = "lowest", "highest"
    if lo == 0 and hi == 1 and "low" in out:
        out["note"] = f"0 = {out['low']}, 1 = {out['high']}. A model scale, not a percentage: compare groups and worlds, or read it as " \
                      "very low (<0.2), low, moderate (0.4–0.6), high, very high (>0.8)."
    elif "low" in out and lo is not None:
        out["note"] = f"{lo:g} = {out['low']}, {hi:g} = {out['high']}."
    return out if ("low" in out or v.units) else None

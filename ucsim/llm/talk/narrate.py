"""Narrate a scene: a model tells an occasion, a date or two people's history as prose, from the scene's beats
(analysis/script.py). The beats are what the simulation recorded; the model writes the words, small detail and
thoughts, and the checker holds it to the beats: every passage cites beat ids that exist, names only people in the
scene, and the whole covers most of what happened. One repair round, like Ask and Interviews; passages that still fail
are dropped and shown as removed.
"""
from __future__ import annotations

import json
import re

from . import jobs, llm

FIRST_NAMES = None


def _first_names() -> set[str]:
    global FIRST_NAMES
    if FIRST_NAMES is None:
        from ...analysis.person import FIRST_F, FIRST_M
        FIRST_NAMES = set(FIRST_F) | set(FIRST_M)
    return FIRST_NAMES


def fact_sheet(sim, ref: dict, pov: int | None = None) -> dict:
    """The scene as numbered beats plus a sketch of each person in it."""
    from ...analysis import script as SC
    from ...analysis.person import headline
    sc = SC.occasion_script(sim, int(ref["id"])) if ref["kind"] == "occasion" else SC.pair_script(sim, int(ref["a"]), int(ref["b"]))
    beats = []
    for k, b in enumerate(sc.get("beats", [])):
        who = (b.get("speaker") or b.get("who") or {}).get("name")
        beats.append({"id": f"b{k + 1}", "kind": b["kind"], "time": b.get("time"), "date": b.get("date"), "who": who,
                      "text": b.get("text"), "line": b.get("line"), "why": b.get("why") or None, "channel": b.get("channel")})
    people = []
    ids = [p["id"] for p in sc.get("cast", [])] or [x for x in (sc.get("a", {}).get("id"), sc.get("b", {}).get("id")) if x is not None]
    from ...analysis.person import synthetic_name
    P = sim.w.P
    for i in ids[:16]:
        i = int(i)
        mood = []
        ext = float(sim.z("extraversion")[i])
        mood.append("outgoing" if ext > 0.7 else "reserved" if ext < -0.7 else "")
        mood.append("happy lately" if P["mood"][i] > 0.68 else "low lately" if P["mood"][i] < 0.4 else "")
        mood.append("lonely" if P["loneliness"][i] > 0.5 else "")
        mood.append("stressed" if P["stress"][i] > 0.6 else "")
        people.append({"id": i, "sketch": f"{synthetic_name(P, i)}: {headline(sim, i)}"
                                          + "".join(f"; {m}" for m in mood if m)})
    title = sc.get("title") or (f"{sc['a']['name']} & {sc['b']['name']}" if sc.get("a") else "A scene")
    pov_name = None
    if pov is not None:
        from ...analysis.person import synthetic_name
        pov_name = synthetic_name(sim.w.P, int(pov))
    return {"title": title, "when": " · ".join(x for x in (sc.get("weekday"), sc.get("date"), sc.get("time")) if x),
            "place": sc.get("place"), "beats": beats, "people": people, "pov": pov_name, "script": sc}


class BeatChecker:
    """Each passage must cite real beats and name only people who are in the scene."""

    def __init__(self, sheet: dict):
        self.ids = {b["id"] for b in sheet["beats"]}
        txt = " ".join(str(v) for b in sheet["beats"] for v in (b["who"], b["text"]) if v) + " " + " ".join(p["sketch"] for p in sheet["people"])
        self.allowed = {w for w in re.findall(r"[A-Z][a-z]+", txt)}
        self.important = {b["id"] for b in sheet["beats"] if b["kind"] not in ("note", "stage")}

    def check_all(self, ans: dict) -> list[dict]:
        out = []
        for s in (ans or {}).get("sentences", []):
            text, cl = str(s.get("text", "")), [str(c) for c in s.get("claims", [])]
            reasons = []
            if not cl:
                reasons.append("cites no beat")
            bad = [c for c in cl if c not in self.ids]
            if bad:
                reasons.append(f"cites beats that don't exist: {', '.join(bad[:4])}")
            strangers = sorted({w for w in re.findall(r"\b[A-Z][a-z]+\b", text) if w in _first_names() and w not in self.allowed})
            if strangers:
                reasons.append(f"names someone who isn't in the scene: {', '.join(strangers)}")
            out.append({"text": text, "claims": cl, "ok": not reasons, "reasons": reasons})
        return out

    def coverage(self, verdicts: list[dict]) -> float:
        told = {c for v in verdicts if v["ok"] for c in v["claims"]}
        return len(told & self.important) / max(len(self.important), 1)


def start(ws, ref: dict, pov: int | None = None, u: str = "base") -> jobs.Job:
    def work(job: jobs.Job) -> dict:
        with ws.lock:
            sheet = fact_sheet(ws.sim(u), ref, pov)
        if not sheet["beats"]:
            raise jobs.TalkError("nothing has happened in this scene yet")
        checker = BeatChecker(sheet)
        lines = "\n".join(json.dumps({k: v for k, v in b.items() if v not in (None, "")}, ensure_ascii=False) for b in sheet["beats"])
        ppl = "\n".join(f"- {p['sketch']}" for p in sheet["people"])
        prompt = (f"## The scene: {sheet['title']}" + (f" ({sheet['when']})" if sheet["when"] else "")
                  + (f", {sheet['place']}" if sheet["place"] else "")
                  + (f"\nPoint of view: {sheet['pov']}" if sheet["pov"] else "")
                  + f"\n\n## The people\n{ppl}\n\n## The beats (cite their ids)\n{lines}\n\nWrite it as JSON {{\"sentences\": [...]}}.")
        job.step("start", f"Telling {sheet['title']}")
        system = llm.prompt_file("talk_narrate.md")
        ans = jobs.ask_model(job, "narrate", "answer", system, prompt, llm.ANSWER_SCHEMA)
        v = checker.check_all(ans)
        if any(not x["ok"] for x in v) or checker.coverage(v) < 0.6:
            job.step("fix", "Some passages strayed from what happened — asking for a fix")
            fix = (prompt + "\n\n## Your previous answer\n```json\n" + json.dumps(ans, ensure_ascii=False)[:12000] + "\n```\n"
                   + "Problems:\n" + "\n".join(f"- \"{x['text'][:80]}\": {'; '.join(x['reasons'])}" for x in v if not x["ok"])
                   + (f"\n- it leaves out too much of what happened (covers {checker.coverage(v):.0%} of the beats)" if checker.coverage(v) < 0.6 else "")
                   + "\nReturn the complete corrected story.")
            try:
                v2 = checker.check_all(jobs.ask_model(job, "narrate", "repair", system, fix, llm.ANSWER_SCHEMA))
                if sum(x["ok"] for x in v2) >= sum(x["ok"] for x in v) or checker.coverage(v2) > checker.coverage(v):
                    v = v2
            except jobs.TalkError as e:
                job.step("note", f"The repair attempt failed ({e}); keeping what passed")
        job.step("done", "The story is ready")
        beats = {b["id"]: b for b in sheet["beats"]}
        return {"title": sheet["title"], "when": sheet["when"], "place": sheet["place"],
                "passages": [{"text": x["text"], "beats": x["claims"]} for x in v if x["ok"]],
                "removed": [{"text": x["text"], "reasons": x["reasons"]} for x in v if not x["ok"]],
                "coverage": round(checker.coverage(v), 2), "beats": beats,
                "note": "Written by a model from the scene's recorded beats: what happens is the simulation's; the words, "
                        "small details and thoughts are the model's."}
    label = f"{ref.get('kind')}:{ref.get('id', '')}{ref.get('a', '')}-{ref.get('b', '')}"
    return jobs.start("narrate", label, work)

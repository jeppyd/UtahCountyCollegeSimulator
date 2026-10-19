"""Background jobs for Ask the world and Interviews (start / poll / cancel), like the What-if compiler's.

Both run the same tail: the model answers citing claim ids → the checker judges every sentence → one repair round with
the checker's reasons → sentences that still fail are dropped and shown as "removed: reason". Interviews also pass a
safety screen (no self-harm methods, no clinical advice, no generated theology).
"""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid

from . import llm
from .check import Checker, repair_note

# sentences an interview never says, whatever the facts
SAFETY = [
    (re.compile(r"\b(?:overdos\w*|pills? to|hang(?:ing)? myself|cut(?:ting)? myself|jump(?:ing)? off|kill(?:ing)? myself|"
                r"end(?:ing)? (?:my|it) (?:life|all)|suicide method|how to die)\b", re.I),
     "safe messaging: no talk of ways to self-harm"),
    (re.compile(r"\b(?:you should (?:take|try|start|stop) (?:\w+ )?(?:medication|meds|pills|antidepressants)|dosage|"
                r"diagnos(?:e|is|ed) (?:you|yourself)|you have (?:depression|anxiety disorder))\b", re.I),
     "no medical or clinical advice"),
    (re.compile(r"\b(?:god wants|the lord wants|heavenly father wants|the doctrine (?:says|teaches)|the scriptures? (?:say|teach)s?|"
                r"the prophet (?:said|says|teaches)|the church teaches)\b", re.I),
     "no generated theology"),
]


class Job:
    def __init__(self, kind: str, question: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind, self.question = kind, question
        self.state = "queued"
        self.steps: list[dict] = []
        self.result: dict | None = None
        self.error: str | None = None
        self.started = time.time()
        self.finished: float | None = None
        self.cancel = threading.Event()
        self.backend = ""

    def step(self, kind: str, text: str):
        if self.steps and self.steps[-1]["text"] == text:
            return
        self.steps.append({"t": round(time.time() - self.started, 1), "kind": kind, "text": str(text)[:400]})

    def view(self) -> dict:
        return {"id": self.id, "kind": self.kind, "state": self.state, "steps": self.steps[-40:], "result": self.result,
                "error": self.error, "backend": self.backend,
                "elapsed": round((self.finished or time.time()) - self.started, 1)}


JOBS: dict[str, Job] = {}


def start(kind: str, question: str, work) -> Job:
    """Run work(job) in the background; it returns the result dict."""
    job = Job(kind, question)
    JOBS[job.id] = job
    for k in list(JOBS)[:-40]:
        JOBS.pop(k, None)

    def go():
        job.state = "running"
        try:
            job.result = work(job)
            job.state = "cancelled" if job.cancel.is_set() else "done"
        except Cancelled:
            job.state, job.error = "cancelled", "cancelled"
        except TalkError as e:
            job.state, job.error = "error", str(e)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            job.state, job.error = "error", f"{e!r}"
        finally:
            job.finished = time.time()
    threading.Thread(target=go, daemon=True).start()
    return job


class Cancelled(Exception):
    pass


class TalkError(Exception):
    pass


def ask_model(job: Job, feature: str, stage: str, system: str, prompt: str, schema: dict) -> dict:
    if job.cancel.is_set():
        raise Cancelled()
    obj, err, which = llm.complete(feature, stage, system, prompt, schema, job.step, job.cancel)
    job.backend = which
    if job.cancel.is_set() or err == "cancelled":
        raise Cancelled()
    if obj is None:
        raise TalkError(err or "no answer came back")
    return obj


def claims_block(claims: dict) -> str:
    return "\n".join(json.dumps({"id": c["id"], "kind": c["kind"], "text": c["text"]}, ensure_ascii=False) for c in claims.values())


def safety(verdicts: list[dict]) -> list[dict]:
    for v in verdicts:
        for rx, why in SAFETY:
            if rx.search(v["text"]):
                v["ok"] = False
                v["reasons"] = [*v["reasons"], why]
    return verdicts


def checked_answer(job: Job, feature: str, system: str, prompt: str, checker: Checker, screen: bool = False) -> dict:
    """Answer → check → one repair round → drop what still fails."""
    job.step("tool", "Writing the answer")
    ans = ask_model(job, feature, "answer", system, prompt, llm.ANSWER_SCHEMA)
    v = checker.check_all(ans)
    if screen:
        v = safety(v)
    repaired = False
    if any(not x["ok"] for x in v):
        bad = sum(not x["ok"] for x in v)
        job.step("fix", f"{bad} sentence{'s' if bad != 1 else ''} didn't match the facts — asking for a fix")
        fix = (prompt + "\n\n## Your previous answer\n```json\n" + json.dumps(ans, ensure_ascii=False)[:8000] + "\n```\n"
               "The checker found these problems:\n" + repair_note(v)
               + "\nReturn the complete corrected answer. Fix or leave out each sentence with a problem; keep the rest.")
        try:
            ans2 = ask_model(job, feature, "repair", system, fix, llm.ANSWER_SCHEMA)
            v2 = checker.check_all(ans2)
            if screen:
                v2 = safety(v2)
            if sum(x["ok"] for x in v2) >= sum(x["ok"] for x in v):
                v, repaired = v2, True
        except TalkError as e:
            job.step("note", f"The repair attempt failed ({e}); keeping what passed")
    kept = [x for x in v if x["ok"]]
    removed = [{"text": x["text"], "reasons": x["reasons"]} for x in v if not x["ok"]]
    return {"sentences": kept, "removed": removed, "repaired": repaired}


def refs_of(claims: dict, sentences: list[dict]) -> list[dict]:
    """Every person, place and event the kept sentences rest on (unique, in order)."""
    seen, out = set(), []
    for s in sentences:
        for cid in s["claims"]:
            c = claims.get(cid)
            if not c:
                continue
            for r in [c.get("subject") or {}, *(c.get("refs") or [])]:
                if r.get("kind") in ("person", "place", "event", "decision", "tie") and (r["kind"], str(r["id"])) not in seen:
                    seen.add((r["kind"], str(r["id"])))
                    out.append(r)
    return out


def finish(job: Job, claims: dict, out: dict, **extra) -> dict:
    for s in out["sentences"]:
        s["refs"] = refs_of(claims, [s])
    return {**out, "claims": list(claims.values()), "refs": refs_of(claims, out["sentences"]), "backend": job.backend,
            "seconds": round(time.time() - job.started, 1), **extra}

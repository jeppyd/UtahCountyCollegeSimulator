"""Wording conversations and texts with a model, held to their content plans (analysis/dialogue.py).

A request names a window of planned lines (a text thread's days, a group chat, an app conversation, an in-person
conversation). The plan is built under the world lock (fast); the model is called without it. The model returns one
text per planned line id. `DialogueChecker` judges each line on *meaning*, not on JSON shape or ids: the right
polarity (a no stays a no), no reason that was kept back, no names, numbers, days or times the plan doesn't give, no
invitation, promise, apology-for-something, accusation, secret, relationship or diagnosis the plan doesn't license, no
psychological narration. One repair round with the reasons; lines that still fail fall back to the structured wording
(and say so). A real line id never makes an unsupported sentence pass.

Accepted wording is cached once per (world lineage, content key, schema): every phone, the scene and the app show the
same words; reopening or switching perspective never rerolls them; a branch whose content differs gets its own key and
can never show another branch's words. Jobs run one at a time from a bounded priority queue (visible live scenes
first), are deduplicated by key and can be cancelled; a failed or missing model leaves the structured wording.
"""
from __future__ import annotations

import heapq
import itertools
import json
import re
import threading
import time
import traceback
from collections import OrderedDict

from . import jobs, llm

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["lines"], "properties": {
    "lines": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "text"],
                                          "properties": {"id": {"type": "string"}, "text": {"type": "string"}}}}}}
CACHE_MAX = 600
QUEUE_MAX = 24
CACHE: "OrderedDict[tuple, dict]" = OrderedDict()
_lock = threading.Lock()
_heap: list = []
_jobs: dict[tuple, "Job"] = {}
_seq = itertools.count()
_worker: threading.Thread | None = None
_wake = threading.Event()

ACCEPT_RX = re.compile(r"\b(i'?ll be there|count me in|i'?m in\b|see you (there|then)|i can make it|sounds good, i'?ll come|"
                       r"yes+!*|i'?d love (to|that)|sure thing)\b", re.I)
DECLINE_RX = re.compile(r"\b(can'?t|cannot|won'?t (make|be able)|not going to make|no thanks|i'?ll pass|going to pass|"
                        r"don'?t think so|not interested)\b", re.I)
INVITE_RX = re.compile(r"\b(come over|want to come|wanna come|you should come|are you free|join us|come hang|come by|"
                       r"let'?s (get|grab|go|hang|do)|we should (get|grab|go|hang|do))\b", re.I)
PROMISE_RX = re.compile(r"\b(i promise|promise|next time for sure|i'?ll (definitely |totally )?come next time|"
                        r"next time,? (i|for sure)|rain ?check)\b", re.I)
REASON_WORDS = {"work": r"\b(work|working|shift|job)\b", "class": r"\b(class|lecture|lab)\b",
                "ill": r"\b(sick|ill|fever|cold)\b", "exam": r"\b(test|exam|midterm|final|study|studying)\b",
                "far": r"\b(ride|far|drive|bus|car)\b", "partner": r"\b(boyfriend|girlfriend|fianc|husband|wife)\b",
                "tired": r"\b(tired|exhausted|wiped|dead tonight)\b", "clash": r"\b(already have|other plans|something else|another thing)\b"}
SECRET_RX = re.compile(r"\b(secret|pregnan\w*|engaged|fianc\w*|boyfriend|girlfriend|married|broke up|breakup|crush|"
                       r"mission call|divorc\w*|cheat\w*|affair)\b", re.I)
DIAGNOSIS_RX = re.compile(r"\b(depress\w*|anxiety|panic attack\w*|therap\w*|counsel\w*|medication|meds|diagnos\w*|"
                          r"suicid\w*|self[- ]harm)\b", re.I)
ACCUSE_RX = re.compile(r"\b(you always|you never|you ignored|you'?re ignoring|on purpose|you excluded|you left me out|"
                       r"you don'?t care|you lied)\b", re.I)
PSYCH_RX = re.compile(r"\b(i feel (rejected|abandoned|invalidated)|my attachment|my anxiety|projecting|"
                      r"i'?m processing|triggered|boundaries)\b", re.I)
FUTURE_RX = re.compile(r"\b(tomorrow|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|"
                       r"this weekend|weekend|next month)\b", re.I)
NUMBER_WORDS = re.compile(r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|hundred|thousand)\b", re.I)


# ------------------------------------------------------------------------------------------------------------ checker
class DialogueChecker:
    """Judge each model line against its planned line (see the module docstring)."""

    def __init__(self, specs: list[dict], names: dict[int, str], allowed_names: set[str]):
        from ...analysis.dialogue import lid
        self.specs = {lid(s): s for s in specs if s.get("kind") != "stage" and not s.get("absent")}
        self.names = names
        self.allowed = {n.lower() for n in allowed_names}

    def check_line(self, sid: str, text: str) -> list[str]:
        from ...analysis.person import FIRST_F, FIRST_M
        s = self.specs.get(sid)
        if s is None:
            return ["isn't a planned line"]
        t = str(text or "").strip()
        why: list[str] = []
        if not t:
            return ["empty"]
        if len(t) > 240:
            why.append("too long for one message")
        act = s["act"]
        sl = s.get("slots") or {}
        lic = s.get("licensed") or {}
        low = t.lower()
        # polarity: a no stays a no, a yes stays a yes
        if act in ("decline_explained", "decline_brief", "date_no") and ACCEPT_RX.search(t) and not DECLINE_RX.search(t):
            why.append("turns a no into a yes")
        if act in ("accept", "date_yes") and DECLINE_RX.search(t):
            why.append("turns a yes into a no")
        # reasons: a brief no keeps its reason private; an explained no gives only its own reason
        reason = sl.get("reason") or "none"
        for r, rx in REASON_WORDS.items():
            if re.search(rx, low) and not (act == "decline_explained" and r == reason) and not (act == "clarify" and r == reason) \
                    and not (act == "small_talk" and sl.get("topic") in (r, "exam" if r == "exam" else "", "work" if r == "work" else "",
                                                                          "class" if r == "class" else "")):
                why.append(f"gives a reason the record doesn't ({r})" if act != "decline_brief" else "says why, but they kept their reason to themselves")
                break
        # invitations, promises, accusations, secrets, diagnoses
        if INVITE_RX.search(t) and not (lic.get("invite") or act in ("invite", "invite_group", "ask_date")):
            why.append("makes an invitation nobody made")
        if PROMISE_RX.search(t) and not lic.get("promise"):
            why.append("makes a promise that wasn't made")
        if ACCUSE_RX.search(t):
            why.append("makes an accusation that wasn't made")
        if SECRET_RX.search(t) and not (lic.get("news") and re.search(lic["news"].split("_")[0][:5], low)):
            why.append("mentions a relationship or secret that isn't in the record")
        if DIAGNOSIS_RX.search(t):
            why.append("names a condition or treatment the record doesn't give")
        if PSYCH_RX.search(t):
            why.append("narrates their psychology out loud")
        # names, numbers, days and times must come from the plan
        firsts = set(FIRST_F) | set(FIRST_M)
        for w in re.findall(r"\b[A-Z][a-z]+\b", t):
            if w in firsts and w.lower() not in self.allowed:
                why.append(f"names someone who isn't part of it ({w})")
                break
        allowed_nums = set(re.findall(r"\d+", " ".join(str(v) for v in (sl.get("time"), sl.get("when"), sl.get("school")) if v)))
        nums = set(re.findall(r"\d+", t))
        if nums - allowed_nums:
            why.append(f"gives a number the record doesn't ({', '.join(sorted(nums - allowed_nums))})")
        if NUMBER_WORDS.search(t) and not sl.get("time"):
            why.append("gives a count the record doesn't")
        when = (sl.get("when") or "").lower()
        for m in FUTURE_RX.findall(t):
            m = m.lower()
            ok = m in when or (m == "tonight" and "tonight" in when) or (act == "ask_date" and m in ("this weekend", "weekend")) \
                or (act in ("small_talk",) and m in ("tonight", "weekend", "this weekend"))
            if not ok:
                why.append(f"sets a time the record doesn't ({m})")
                break
        if act == "disclose" and not re.search(r"\b(hard|rough|struggl|not great|not good|down|tough|bad)\w*", low):
            why.append("doesn't say they're having a hard time (that's what they told)")
        if act == "deflect" and re.search(r"\b(struggl|hard time|rough|not great|not okay|depress)\w*", low):
            why.append("tells what they kept to themselves")
        return why

    def check_all(self, ans: dict) -> dict[str, dict]:
        out = {}
        for item in (ans or {}).get("lines", []):
            sid, text = str(item.get("id", "")), str(item.get("text", ""))
            if sid in out:
                continue
            reasons = self.check_line(sid, text)
            out[sid] = {"text": text.strip(), "ok": not reasons, "reasons": reasons}
        return out


# ------------------------------------------------------------------------------------------------------------- cache
def lineage(sim) -> str:
    return str(getattr(sim, "lineage", None) or f"seed{sim.w.seed}")


def cached(key: tuple) -> dict | None:
    with _lock:
        hit = CACHE.get(key)
        if hit is not None:
            CACHE.move_to_end(key)
        return hit


def store(key: tuple, value: dict):
    with _lock:
        CACHE[key] = value
        CACHE.move_to_end(key)
        while len(CACHE) > CACHE_MAX:
            CACHE.popitem(last=False)


def clear():
    with _lock:
        CACHE.clear()


def apply(sim, specs: list[dict], key: tuple | None) -> tuple[list[str], str]:
    """The words for each planned line: the accepted model wording when cached, else the structured wording."""
    from ...analysis import dialogue as D
    hit = cached(key) if key is not None else None
    styles: dict = {}
    out = []
    for s in specs:
        sid = D.lid(s)
        t = (hit or {}).get("lines", {}).get(sid)
        out.append(t if t else D.fallback(sim, s, styles))
    return out, ("model" if hit else "structured")


# ------------------------------------------------------------------------------------------------------------- queue
class Job(jobs.Job):
    def __init__(self, key: tuple, label: str, priority: int, build):
        super().__init__("dialogue", label)
        self.key, self.priority, self.build = key, priority, build


def status(key: tuple) -> dict:
    """What's known about wording for this key, without starting anything."""
    if cached(key) is not None:
        c = cached(key)
        return {"state": "done", "backend": c.get("backend"), "removed": c.get("removed", 0)}
    with _lock:
        j = _jobs.get(key)
    if j is None:
        return {"state": "none"}
    return {"state": j.state, "job": j.id, "error": j.error, "steps": j.steps[-3:]}


def request(key: tuple, label: str, build, priority: int = 1) -> dict:
    """Queue wording for a plan (deduplicated by key). `build()` returns (specs, names, allowed_names, context) and is
    called by the worker under the caller's own locking (it must take the world lock itself, briefly)."""
    if cached(key) is not None:
        return status(key)
    global _worker
    with _lock:
        j = _jobs.get(key)
        if j is not None and j.state in ("queued", "running"):
            j.priority = min(j.priority, priority)
            return {"state": j.state, "job": j.id}
        j = Job(key, label, priority, build)
        _jobs[key] = j
        jobs.JOBS[j.id] = j
        heapq.heappush(_heap, (priority, next(_seq), key))
        # bounded: drop the least urgent queued requests beyond the limit
        queued = [x for x in _heap if _jobs.get(x[2]) is not None and _jobs[x[2]].state == "queued"]
        if len(queued) > QUEUE_MAX:
            for _, _, k in sorted(queued)[QUEUE_MAX:]:
                dj = _jobs.pop(k, None)
                if dj is not None:
                    dj.state, dj.error = "cancelled", "dropped: too many requests queued"
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, daemon=True)
            _worker.start()
    _wake.set()
    return {"state": "queued", "job": j.id}


def cancel(key: tuple | None = None, job_id: str | None = None) -> bool:
    with _lock:
        for k, j in list(_jobs.items()):
            if (key is not None and k == key) or (job_id is not None and j.id == job_id):
                j.cancel.set()
                if j.state == "queued":
                    j.state, j.error = "cancelled", "cancelled"
                return True
    return False


def _next() -> "Job | None":
    with _lock:
        while _heap:
            _, _, k = heapq.heappop(_heap)
            j = _jobs.get(k)
            if j is not None and j.state == "queued":
                j.state = "running"
                return j
    return None


def _run():
    while True:
        j = _next()
        if j is None:
            _wake.wait(timeout=30)
            _wake.clear()
            if not _heap:
                return
            continue
        try:
            res = realize(j)
            if res is not None and not j.cancel.is_set():
                store(j.key, res)
                j.result = {"lines": len(res["lines"]), "removed": res["removed"], "backend": res["backend"]}
                j.state = "done"
            elif j.cancel.is_set():
                j.state, j.error = "cancelled", "cancelled"
        except jobs.Cancelled:
            j.state, j.error = "cancelled", "cancelled"
        except jobs.TalkError as e:
            j.state, j.error = "error", str(e)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            j.state, j.error = "error", f"{e!r}"
        finally:
            j.finished = time.time()


def wait_idle(timeout: float = 10.0):
    """Tests: wait until the queue is empty."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        with _lock:
            busy = any(j.state in ("queued", "running") for j in _jobs.values())
        if not busy:
            return True
        time.sleep(0.02)
    return False


def realize(job: Job) -> dict | None:
    """Plan → model → check → one repair → fallback for what still fails."""
    from ...analysis import dialogue as D
    if llm.load().get("dialogue_backend") == "off" and llm.FAKE is None:
        raise jobs.TalkError("model wording is turned off (Settings → Models)")
    specs, names, allowed, context = job.build()           # takes the world lock briefly, itself
    todo = [s for s in specs if s.get("kind") != "stage" and not s.get("absent")]
    if not todo:
        return {"lines": {}, "removed": 0, "backend": "none", "t": time.time()}
    checker = DialogueChecker(specs, names, allowed)
    plan = [{"id": D.lid(s), "speaker": names.get(s["speaker"], "?"), "to": names.get(s["to"]) if s.get("to") is not None else "the chat",
             "channel": s["channel"], "act": s["act"], "meaning": D.label_act(s["act"]),
             "may_mention": {k: v for k, v in (s.get("slots") or {}).items() if k in ("when", "what", "time", "weekday", "host", "reason", "topic", "place", "school") and v},
             "licensed": {k: v for k, v in (s.get("licensed") or {}).items() if v},
             "draft": s.get("_draft")} for s in todo]
    prompt = (f"## Context\n{json.dumps(context, ensure_ascii=False)}\n\n## Lines to write (one text per id, same order)\n"
              + "\n".join(json.dumps(x, ensure_ascii=False) for x in plan)
              + "\n\nReply as JSON {\"lines\": [{\"id\": ..., \"text\": ...}]}.")
    system = llm.prompt_file("talk_dialogue.md")
    job.step("start", f"Writing {len(todo)} lines")
    ans = jobs.ask_model(job, "dialogue", "answer", system, prompt, SCHEMA)
    v = checker.check_all(ans)
    bad = [x for x in plan if not v.get(x["id"], {}).get("ok")]
    if bad:
        job.step("fix", f"{len(bad)} line{'s' if len(bad) != 1 else ''} said something the record doesn't — asking for a fix")
        fix = (prompt + "\n\n## Your previous lines\n" + json.dumps(ans, ensure_ascii=False)[:8000]
               + "\n\nThese lines have problems; rewrite only them:\n"
               + "\n".join(f"- {x['id']}: {'; '.join(v.get(x['id'], {}).get('reasons') or ['missing'])}" for x in bad))
        try:
            v2 = checker.check_all(jobs.ask_model(job, "dialogue", "repair", system, fix, SCHEMA))
            for sid, r in v2.items():
                if r["ok"] and not v.get(sid, {}).get("ok"):
                    v[sid] = r
        except jobs.TalkError as e:
            job.step("note", f"The repair attempt failed ({e}); the structured wording stays for those lines")
    lines = {sid: r["text"] for sid, r in v.items() if r["ok"] and sid in checker.specs}
    removed = [{"id": sid, "text": r["text"], "reasons": r["reasons"]} for sid, r in v.items() if not r["ok"]]
    job.step("done", f"{len(lines)} of {len(todo)} lines worded by the model")
    return {"lines": lines, "removed": len(removed), "rejected": removed[:20], "backend": job.backend or "model", "t": time.time()}


"""Ask the world: the model picks query tools, the simulator runs them and builds facts, the model answers citing
them, and the checker keeps only what the facts support. Read-only: nothing here changes a world."""
from __future__ import annotations

import json

import numpy as np

from . import facts as F
from . import jobs, llm
from .check import Checker

MAX_CALLS = 4


def context(sim, sensitive: bool) -> str:
    """What the model needs to pick lookups: today, the tools, the filter language, measures and common event types."""
    from ...analysis import query
    P, reg = sim.w.P, sim.reg
    vars_ = [f"{v.id} ({v.label})" for v in reg.person_vars()
             if v.id in P.cols and "filter" in (v.flags or []) and (sensitive or not F.is_sensitive(reg, v.id))]
    log = sim.log
    cnt = np.bincount(log["type"][: log.n], minlength=len(reg.event_names)) if log.n else np.zeros(len(reg.event_names))
    common = [reg.event_names[k] for k in np.argsort(-cnt)[:80] if cnt[k] > 0]
    common = [t for t in common if sensitive or not F.event_sensitive(sim, t)]
    tools = "\n".join(f"- {k}: {t['desc']} Arguments: " + json.dumps(t["args"], ensure_ascii=False) for k, t in F.TOOLS.items())
    return (f"Today is {sim.cal.date(sim.w.day)} (day {sim.w.day} of the simulation; day 0 was {sim.cal.date(0)}). "
            f"{int(P['present'][: P.n].sum()):,} people are present.\n\n## Tools\n{tools}\n\n## Filter language\n"
            f"{(query.__doc__ or '').split('A filter is JSON:', 1)[-1].strip()}\n\n## Measures (var names)\n"
            + ", ".join(vars_) + "\n\n## Common event types\n" + ", ".join(common))


def _args(call: dict) -> dict:
    a = call.get("args")
    if isinstance(a, dict):
        return a
    try:
        a = json.loads(call.get("args_json") or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return a if isinstance(a, dict) else {}


def start(ws, question: str, mentions: list | None = None, u: str = "base") -> jobs.Job:
    ts = llm.load()
    sensitive = bool(ts.get("sensitive"))

    def work(job: jobs.Job) -> dict:
        system = llm.prompt_file("talk_ask.md")
        with ws.lock:
            sim = ws.sim(u)
            ctx = context(sim, sensitive)
        ment = "".join(f"\n- {m.get('kind')} {m.get('id')}" + (f" ({m['label']})" if m.get("label") else "") for m in (mentions or [])[:12])
        p1 = (f"{ctx}\n\n## Question\n{question}\n" + (f"\nThe user pointed at:{ment}\n" if ment else "")
              + "\nStep 1: choose the lookups (JSON {\"calls\": [...]}).")
        job.step("start", "Choosing what to look up")
        plan = jobs.ask_model(job, "ask", "tools", system, p1, llm.TOOLS_SCHEMA)
        sheet, used, notes = F.Sheet(), [], []
        for call in (plan.get("calls") or [])[:MAX_CALLS]:
            name, args = str(call.get("tool", "")), _args(call)
            job.step("tool", f"Looking up: {name.replace('_', ' ')}")
            try:
                with ws.lock:
                    got = F.run_tool(ws, name, args, u=u, sensitive=sensitive)
                sheet.merge(got)
                used.append({"tool": name, "args": args, "facts": len(got.claims)})
            except Exception as e:  # noqa: BLE001 — a bad lookup is reported, it doesn't end the answer
                notes.append(f"{name}: {e}")
                used.append({"tool": name, "args": args, "error": str(e)})
        if not sheet.claims:
            raise jobs.TalkError("None of the lookups found anything" + (f" ({'; '.join(notes)[:300]})" if notes else ""))
        checker = Checker(sheet.claims)
        p2 = (f"## Question\n{question}\n\n## Facts (cite their ids)\n{jobs.claims_block(sheet.claims)}\n"
              + (f"\nLookups that failed: {'; '.join(notes)}\n" if notes else "") + "\nStep 2: answer as JSON {\"sentences\": [...]}.")
        out = jobs.checked_answer(job, "ask", system, p2, checker)
        job.step("done", "Answer ready")
        return jobs.finish(job, sheet.claims, out, tools_used=used, question=question, u=u)
    return jobs.start("ask", question, work)

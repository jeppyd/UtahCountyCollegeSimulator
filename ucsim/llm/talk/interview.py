"""Interviews: one simulated person answers in the first person from their own dossier (what they feel, believe,
see in others, remember and chose). Observational only: building the dossier never changes the world and never
rehearses a memory. Sensitive fields stay out unless the owner turns them on. The same person can be interviewed in
the What-if world (u="alt")."""
from __future__ import annotations

from . import facts as F
from . import jobs, llm
from .check import Checker


def start(ws, i: int, question: str, history: list | None = None, u: str = "base") -> jobs.Job:
    ts = llm.load()
    sensitive = bool(ts.get("sensitive"))

    def work(job: jobs.Job) -> dict:
        with ws.lock:
            sim = ws.sim(u)
            if not (0 <= i < sim.w.P.n) or not sim.w.P["present"][i]:
                raise jobs.TalkError("that person isn't in this world now")
            sheet = F.dossier(sim, i, sensitive=sensitive)
            me = F.person_ref(sim, i)
            differs = F.view_vs_truth(sim, i)
            checker = Checker(sheet.claims, mode="interview", self_id=i)
        convo = "".join(f"\nQ: {h.get('q', '')}\nA: {h.get('a', '')}" for h in (history or [])[-6:])
        prompt = (f"You are {me['name']}." + (f"\n\n## The conversation so far{convo}" if convo else "")
                  + f"\n\n## What you know about your own life (cite the ids)\n{jobs.claims_block(sheet.claims)}"
                  f"\n\n## The interviewer asks\n{question}\n\nAnswer as JSON {{\"sentences\": [...]}}.")
        job.step("start", f"Asking {me['name']}")
        out = jobs.checked_answer(job, "interview", llm.prompt_file("talk_interview.md"), prompt, checker, screen=True)
        job.step("done", "Answer ready")
        return jobs.finish(job, sheet.claims, out, person=me, differs=differs, question=question, u=u,
                           sensitive_included=sensitive)
    return jobs.start("interview", question, work)

"""The What-if compiler: turns a request (+ tagged entities + conversation) into a validated plan, in the background.

Flow: build the context pack (guide + catalog, written once per registry) → write the request context (today, the
running What-if, what the user pointed at, the conversation) → ask the configured backend → validate → if the plan has
errors, ask once more with the errors → hand back plan + receipt. Progress steps stream into the job as they happen.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path

from ..registry import get_registry
from . import backends
from .levers import catalog_markdown
from .plan import PLAN_SCHEMA, check_filter, count_who, strict_schema, validate, Problems

GUIDE = Path(__file__).with_name("prompts") / "guide.md"
HOME = Path(os.environ.get("UCSIM_HOME", Path.home() / ".ucsim"))
SETTINGS_FILE = HOME / "llm.json"
DEFAULTS = {"backend": "claude", "claude_model": "", "claude_effort": "", "codex_model": "",
            "openai_url": "http://localhost:1234/v1", "openai_model": "", "openai_key": "lm-studio",
            "use_subscription": True, "use_tools": True, "max_turns": 40, "timeout": 600}
BACKENDS = ("claude", "codex", "openai")


# ---------------------------------------------------------------------- settings
def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            s.update({k: v for k, v in json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).items() if k in DEFAULTS})
    except Exception:  # noqa: BLE001
        pass
    if os.environ.get("UCSIM_LLM_BACKEND") in BACKENDS:
        s["backend"] = os.environ["UCSIM_LLM_BACKEND"]
    return s


def save_settings(new: dict) -> dict:
    s = load_settings()
    for k, v in new.items():
        if k in DEFAULTS:
            s[k] = type(DEFAULTS[k])(v) if not isinstance(DEFAULTS[k], bool) else bool(v)
    if s["backend"] not in BACKENDS:
        s["backend"] = "claude"
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, indent=2), encoding="utf-8")
    return s


def status() -> dict:
    s = load_settings()
    claude_v = backends.version("claude")
    codex_v = backends.version("codex")
    models = backends.openai_models(s["openai_url"]) if s["backend"] == "openai" else []
    try:
        import mcp  # noqa: F401
        has_mcp = True
    except ImportError:
        has_mcp = False
    ready = {"claude": bool(claude_v), "codex": bool(codex_v), "openai": bool(models)}
    return {"settings": s, "claude": claude_v, "codex": codex_v, "openai_models": models, "mcp": has_mcp,
            "ready": ready[s["backend"]], "api_key_in_env": bool(os.environ.get("ANTHROPIC_API_KEY"))}


# ---------------------------------------------------------------------- the context pack
_pack_lock = threading.Lock()


def pack_dir() -> Path:
    """Guide + catalog on disk (system.md, AGENTS.md for Codex, catalog.md), rebuilt when the registry changes."""
    reg = get_registry()
    md = GUIDE.read_text(encoding="utf-8") + "\n\n" + catalog_markdown(reg)
    h = hashlib.sha1(md.encode()).hexdigest()[:10]
    d = HOME / "whatif_pack" / h
    with _pack_lock:
        if not (d / "system.md").exists():
            d.mkdir(parents=True, exist_ok=True)
            (d / "system.md").write_text(md, encoding="utf-8")
            (d / "AGENTS.md").write_text(md, encoding="utf-8")
            (d / "catalog.md").write_text(catalog_markdown(reg), encoding="utf-8")
            (d / "plan_schema.json").write_text(json.dumps(PLAN_SCHEMA, indent=1), encoding="utf-8")
    return d


def compact_system(text: str) -> str:
    """For small local models: the guide and catalog with only the mechanism parameters that look relevant."""
    md = (pack_dir() / "system.md").read_text(encoding="utf-8")
    words = {w for w in re.findall(r"[a-z]{4,}", text.lower())} - {"what", "would", "happen", "with", "that", "they", "from", "have", "were", "there"}
    out, in_params, kept = [], False, 0
    for line in md.splitlines():
        if line.startswith("## 6."):
            in_params = True
        elif line.startswith("## 7."):
            in_params = False
        if in_params and line.startswith("- `"):
            if kept < 40 and any(w in line.lower() for w in words):
                out.append(line)
                kept += 1
            continue
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------- request context
def world_context(ws) -> str:
    b = ws.base
    w = b.w
    P = w.P
    cal = b.cal
    pres = P["present"].astype(bool)
    terms = []
    for school in ("BYU", "UVU"):
        t = cal.term(school, w.day)
        terms.append(f"{school}: {t} (progress {cal.term_progress(school, w.day):.0%})" if t else f"{school}: on break")
    byu = int((pres & (P["school"] == 1) & P["enrolled"]).sum())
    uvu = int((pres & (P["school"] == 2) & P["enrolled"]).sum())
    lds = int((pres & P["lds_member"]).sum())
    lines = ["## The world right now",
             f"- Today is day {w.day}: {w.date} ({w.date.strftime('%A')}), {cal.season(w.day)}. Terms: {'; '.join(terms)}.",
             f"- Scale {w.scale} (each simulated person stands for ~{1 / w.scale:.0f} real people). Present: {int(pres.sum())} people — {byu} BYU and {uvu} UVU enrolled students, {lds} LDS members.",
             ]
    if ws.alt is not None:
        alt = ws.alt
        lines.append("\n## A What-if is already running")
        lines.append(f"Split on day {getattr(alt, 'meta_fork_day', '?')}. Its changes so far:")
        seen = set()
        for it in alt.interventions:
            key = (it.get("name"), it.get("label"), it.get("target_type"), str(it.get("target")))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- [{it.get('name') or it.get('id')}] {it.get('label') or ''} — {it.get('target_type')} {it.get('target', '')} {it.get('op', '')} {it.get('value', '') if not isinstance(it.get('value'), dict) else ''}".rstrip())
        diff = {k: v for k, v in alt.w.env.items() if k in alt.systems["environment"].base and v != ws.base.w.env.get(k)}
        if diff:
            lines.append("World levers that differ from the Original right now: " + ", ".join(f"{k}={v}" for k, v in diff.items()))
    return "\n".join(lines)


def mentions_context(index, mentions: list[dict]) -> str:
    if not mentions:
        return ""
    lines = ["\n## What the user pointed at (exact entities — use these refs and filters)"]
    for m in mentions[:20]:
        ref = m.get("ref") or f"{m.get('kind')}:{m.get('id')}"
        r = index.get(ref) or m
        who = r.get("who")
        bits = [f"- **{r.get('label', ref)}** — `{ref}` · {r.get('sub', '')}"]
        if r.get("n") is not None:
            bits.append(f"· {r['n']} people now")
        if who:
            bits.append(f"· who: `{json.dumps(who)}`")
        if ref.startswith(("complex:", "venue:", "venue_type:")):
            bits.append("· usable as a `close`/`place` target")
        lines.append(" ".join(bits))
    return "\n".join(lines)


def history_context(history: list[dict]) -> str:
    if not history:
        return ""
    lines = ["\n## The conversation so far"]
    for h in history[-8:]:
        if h.get("role") == "user":
            lines.append(f"User: {h.get('text', '')}")
        elif h.get("role") == "assistant" and h.get("plan"):
            lines.append("Your previous plan (revise this; return the complete plan):\n```json\n" + json.dumps(h["plan"], indent=0)[:12000] + "\n```")
        elif h.get("role") == "assistant":
            lines.append(f"You: {h.get('text', '')[:1500]}")
    return "\n".join(lines)


def build_prompt(ws, index, text: str, mentions: list[dict], history: list[dict], mode: str) -> str:
    parts = [world_context(ws), mentions_context(index, mentions), history_context(history),
             "\n## The request",
             f"Mode: {'add these changes to the running What-if' if mode == 'add' and ws.alt is not None else 'a new What-if (it will replace any running one)'}.",
             f"User: {text.strip()}",
             "\nThink it through as the guide describes, check your plan with the tools if you have them, then return the plan as structured output."]
    return "\n".join(p for p in parts if p)


# ---------------------------------------------------------------------- tools (shared by MCP and the local tool loop)
def run_tool(ws, index, name: str, args: dict) -> dict:
    sim = ws.alt or ws.base
    if name == "search_entities":
        rows = index.search(str(args.get("query", "")), args.get("kinds") or None, limit=int(args.get("limit", 8)))
        return {"results": [{k: r.get(k) for k in ("ref", "label", "sub", "n", "who")} for r in rows]}
    if name == "describe_entity":
        r = index.get(str(args.get("ref", "")))
        return r or {"error": "not found"}
    if name == "count_people":
        prob = Problems()
        who = check_filter(args.get("who"), sim, prob)
        if prob.errors:
            return {"errors": prob.errors}
        from ..analysis.query import describe_filter
        return {"n": count_who(sim, who), "present": int(sim.w.P["present"].sum()), "who": describe_filter(who), "normalized": who}
    if name == "validate_plan":
        plan = args.get("plan") or {}
        if isinstance(plan, str):
            try:
                plan = json.loads(plan)
            except json.JSONDecodeError:
                return {"ok": False, "errors": ["plan is not valid JSON"]}
        v = validate(plan, sim, index)
        return {"ok": v["ok"], "errors": v["errors"], "warnings": v["warnings"],
                "changes": [{k: r.get(k) for k in ("label", "summary", "who", "n", "ok")} for r in v["changes"]]}
    return {"error": f"unknown tool {name}"}


# ---------------------------------------------------------------------- jobs
class Job:
    def __init__(self, text: str, mentions: list, history: list, mode: str):
        self.id = uuid.uuid4().hex[:12]
        self.text, self.mentions, self.history, self.mode = text, mentions, history, mode
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
        self.steps.append({"t": round(time.time() - self.started, 1), "kind": kind, "text": text})

    def view(self) -> dict:
        return {"id": self.id, "state": self.state, "steps": self.steps[-60:], "result": self.result, "error": self.error,
                "backend": self.backend, "elapsed": round((self.finished or time.time()) - self.started, 1)}


JOBS: dict[str, Job] = {}


def start(ws, index_fn, text: str, mentions: list, history: list, mode: str, server_url: str) -> Job:
    job = Job(text, mentions, history, mode)
    JOBS[job.id] = job
    for k in list(JOBS)[:-30]:
        JOBS.pop(k, None)
    threading.Thread(target=_run, args=(job, ws, index_fn, server_url), daemon=True).start()
    return job


def _run(job: Job, ws, index_fn, server_url: str):
    s = load_settings()
    job.backend = s["backend"]
    job.state = "running"
    try:
        with ws.lock:
            index = index_fn()
            prompt = build_prompt(ws, index, job.text, job.mentions, job.history, job.mode)
        pack = pack_dir()
        job.step("start", {"claude": "Sending your idea to Claude (your subscription)", "codex": "Sending your idea to Codex (your ChatGPT plan)",
                           "openai": "Sending your idea to your local model"}[s["backend"]])
        res = _ask(job, ws, index, s, pack, prompt, server_url)
        attempts = 1
        while res.get("plan") is not None and attempts < 3:
            with ws.lock:
                v = validate(res["plan"], ws.alt or ws.base, index)
            if v["ok"]:
                break
            if job.cancel.is_set():
                raise backends.Cancelled()
            job.step("fix", f"The plan had {len(v['errors'])} problem{'s' if len(v['errors']) != 1 else ''} — asking for a fix")
            fix = (prompt + "\n\n## Your previous answer had problems\n```json\n" + json.dumps(res["plan"])[:12000] + "\n```\nErrors:\n"
                   + "\n".join(f"- {e}" for e in v["errors"]) + "\nReturn the complete corrected plan.")
            res = _ask(job, ws, index, s, pack, fix, server_url)
            attempts += 1
        if res.get("plan") is None:
            job.error = res.get("error") or "no plan came back"
            job.state = "error" if job.error != "cancelled" else "cancelled"
            return
        with ws.lock:
            v = validate(res["plan"], ws.alt or ws.base, index)
        from .plan import plan_id
        pid = plan_id(v["plan"])
        job.result = {"plan_id": pid, "plan": v["plan"], "receipt": v["changes"], "errors": v["errors"], "warnings": v["warnings"],
                      "ok": v["ok"], "notes": res.get("text", ""), "meta": res.get("meta", {}), "request": job.text}
        ws.plans[pid] = {"plan": v["plan"], "receipt": v["changes"], "request": job.text, "created": time.time(), "mentions": job.mentions}
        job.step("done", "Plan ready" if v["ok"] else "Plan ready, with problems to look at")
        job.state = "done"
    except backends.Cancelled:
        job.state, job.error = "cancelled", "cancelled"
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job.state, job.error = "error", f"{e!r}"
    finally:
        job.finished = time.time()


def _ask(job: Job, ws, index, s: dict, pack: Path, prompt: str, server_url: str) -> dict:
    if s["backend"] == "claude":
        mcp_cfg = None
        # the desktop build has no separate Python to run the tool server; Claude then works from the catalog alone
        if s.get("use_tools", True) and not getattr(sys, "frozen", False):
            try:
                import mcp  # noqa: F401
                mcp_cfg = pack / f"mcp_{job.id}.json"
                mcp_cfg.write_text(json.dumps({"mcpServers": {"ucsim": {
                    "command": backends.python_exe(), "args": ["-m", "ucsim.llm.mcp_server"],
                    "env": {"UCSIM_URL": server_url, "UCSIM_JOB": job.id, "PYTHONPATH": str(backends.ROOT)}}}}), encoding="utf-8")
            except ImportError:
                job.step("note", "Tip: `pip install mcp` lets Claude look things up and check its plan while it works.")
        try:
            return backends.run_claude(prompt, PLAN_SCHEMA, pack, s, job.step, job.cancel, mcp_cfg)
        finally:
            if mcp_cfg is not None:
                mcp_cfg.unlink(missing_ok=True)
    if s["backend"] == "codex":
        return backends.run_codex(prompt, strict_schema(), pack, s, job.step, job.cancel)

    def tool_fn(name, args):
        with ws.lock:
            return run_tool(ws, index, name, args)
    return backends.run_openai(compact_system(job.text), prompt, strict_schema(), s, job.step, job.cancel, tool_fn)

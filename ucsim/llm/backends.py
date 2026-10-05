"""Ways to reach a model without an API key.

* `claude`  — Claude Code in headless mode (`claude -p`), signed in with a Claude Pro/Max subscription. Streams its
  steps, loads the guide + catalog as an appended system prompt, uses the simulator's own tools over MCP, and returns
  the plan as schema-checked JSON.
* `codex`   — OpenAI Codex CLI (`codex exec`), signed in with ChatGPT Plus. Reads the guide + catalog from AGENTS.md.
* `openai`  — any OpenAI-compatible local server (LM Studio, Ollama): a small tool loop, then a schema-constrained answer.

Every backend returns {"plan": dict|None, "text": str, "error": str|None, "meta": {...}} and reports progress through
`on_step(kind, text)`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_NAMES = ("search_entities", "describe_entity", "count_people", "validate_plan")
_help_cache: dict[str, str] = {}


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _help(exe: str) -> str:
    if exe not in _help_cache:
        try:
            _help_cache[exe] = subprocess.run([exe, "--help"], capture_output=True, text=True, timeout=20,
                                              stdin=subprocess.DEVNULL).stdout
        except Exception:  # noqa: BLE001
            _help_cache[exe] = ""
    return _help_cache[exe]


def version(cmd: str) -> str | None:
    exe = which(cmd)
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else "installed"
    except Exception:  # noqa: BLE001
        return "installed"


def _child_env(drop_api_key: bool) -> dict:
    env = dict(os.environ)
    if drop_api_key:
        # an API key in the environment would make Claude Code bill the key instead of the subscription
        env.pop("ANTHROPIC_API_KEY", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _describe_tool(name: str, inp: dict) -> str:
    short = name.split("__")[-1]
    if short == "Read":
        return f"Reading {Path(str(inp.get('file_path', ''))).name}"
    if short in ("Grep", "Glob"):
        return f"Searching the catalog for “{inp.get('pattern', '')}”"
    if short == "search_entities":
        return f"Looking up “{inp.get('query', '')}”"
    if short == "describe_entity":
        return f"Checking {inp.get('ref', 'a place')}"
    if short == "count_people":
        return "Counting who would be affected"
    if short == "validate_plan":
        n = len((inp.get("plan") or {}).get("changes") or [])
        return f"Checking a draft plan ({n} change{'s' if n != 1 else ''})"
    if short == "StructuredOutput":
        return "Writing up the plan"
    return f"Using {short}"


class Cancelled(Exception):
    pass


def _pump(proc: subprocess.Popen, cancel: threading.Event, timeout: float, on_line):
    """Read stdout lines until EOF, cancellation or timeout (killing the process on the latter two)."""
    t0 = time.time()
    done = threading.Event()

    def watchdog():
        while not done.wait(0.25):
            if cancel.is_set() or time.time() - t0 > timeout:
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                return
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        for line in proc.stdout:
            on_line(line)
    finally:
        done.set()
    proc.wait()
    if cancel.is_set():
        raise Cancelled()
    if time.time() - t0 > timeout:
        raise TimeoutError(f"no answer within {int(timeout)} s")


# ---------------------------------------------------------------------- Claude Code
def run_claude(prompt: str, schema: dict, pack: Path, settings: dict, on_step, cancel: threading.Event, mcp_config: Path | None) -> dict:
    exe = which(settings.get("claude_path") or "claude")
    if not exe:
        return {"plan": None, "text": "", "error": "Claude Code isn't installed or isn't on PATH (install it and run `claude` once to sign in).", "meta": {}}
    h = _help(exe)
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--json-schema", json.dumps(schema, separators=(",", ":"))]
    sysfile = pack / "system.md"
    if "--append-system-prompt-file" in h:
        cmd += ["--append-system-prompt-file", str(sysfile)]
    else:
        cmd += ["--append-system-prompt", sysfile.read_text(encoding="utf-8")]
    allowed = ["Read", "Grep", "Glob"]
    if mcp_config is not None:
        cmd += ["--mcp-config", str(mcp_config), "--strict-mcp-config"]
        allowed += [f"mcp__ucsim__{t}" for t in TOOL_NAMES]
    cmd += ["--tools", "Read,Grep,Glob", "--allowedTools", ",".join(allowed), "--permission-mode", "dontAsk",
            "--max-turns", str(int(settings.get("max_turns", 40))), "--add-dir", str(ROOT / "docs")]
    if "--no-session-persistence" in h:
        cmd.append("--no-session-persistence")
    if settings.get("claude_model"):
        cmd += ["--model", settings["claude_model"]]
    if settings.get("claude_effort") and "--effort" in h:
        cmd += ["--effort", settings["claude_effort"]]
    if "--restricted" in h:
        cmd.append("--restricted")
    proc = subprocess.Popen(cmd, cwd=str(pack), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", env=_child_env(settings.get("use_subscription", True)), bufsize=1)
    err_lines: list[str] = []
    threading.Thread(target=lambda: err_lines.extend(proc.stderr.readlines()), daemon=True).start()
    proc.stdin.write(prompt)
    proc.stdin.close()
    final: dict = {}
    notes: list[str] = []

    def on_line(line: str):
        line = line.strip()
        if not line.startswith("{"):
            return
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            return
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            on_step("start", f"Claude is reading the catalog ({d.get('model', 'default model')})")
        elif t == "assistant":
            for b in d.get("message", {}).get("content", []):
                if b.get("type") == "tool_use":
                    on_step("tool", _describe_tool(b.get("name", ""), b.get("input") or {}))
                elif b.get("type") == "text" and b.get("text", "").strip():
                    notes.append(b["text"].strip())
                    on_step("note", b["text"].strip()[:400])
                elif b.get("type") == "thinking" and (b.get("thinking") or "").strip():
                    on_step("think", b["thinking"].strip()[:400])
        elif t == "result":
            final.update(d)
    try:
        _pump(proc, cancel, float(settings.get("timeout", 600)), on_line)
    except Cancelled:
        return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
    except TimeoutError as e:
        return {"plan": None, "text": "\n".join(notes), "error": str(e), "meta": {}}
    meta = {k: final.get(k) for k in ("num_turns", "duration_ms", "session_id", "subtype", "stop_reason", "terminal_reason")}
    meta["model"] = next(iter((final.get("modelUsage") or {}).keys()), None)
    if not final:
        tail = "".join(err_lines[-12:]).strip()
        hint = " (is Claude Code signed in? run `claude` once in a terminal)" if "login" in tail.lower() or "auth" in tail.lower() or not tail else ""
        return {"plan": None, "text": "\n".join(notes), "error": f"Claude Code ended without an answer{hint}. {tail[-600:]}", "meta": meta}
    plan = final.get("structured_output")
    if plan is None and isinstance(final.get("result"), str):
        plan = _json_from_text(final["result"])
    err = None
    if final.get("is_error") or plan is None:
        err = f"Claude Code: {final.get('subtype') or 'error'} — {str(final.get('result') or '')[:500]}"
    return {"plan": plan, "text": "\n".join(notes), "error": err if plan is None else None, "meta": meta}


def _json_from_text(s: str):
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        s = s[s.find("{"):]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        return json.loads(s[i:j + 1])
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------- Codex CLI
def run_codex(prompt: str, schema: dict, pack: Path, settings: dict, on_step, cancel: threading.Event) -> dict:
    exe = which(settings.get("codex_path") or "codex")
    if not exe:
        return {"plan": None, "text": "", "error": "Codex CLI isn't installed or isn't on PATH (install it and run `codex login`).", "meta": {}}
    schema_file = pack / "plan_schema_strict.json"
    schema_file.write_text(json.dumps(schema), encoding="utf-8")
    out_file = pack / f"codex_last_{os.getpid()}_{threading.get_ident()}.txt"
    cmd = [exe, "exec", "--json", "--output-schema", str(schema_file), "-o", str(out_file), "--sandbox", "read-only",
           "--skip-git-repo-check", "-C", str(pack)]
    if settings.get("codex_model"):
        cmd += ["-m", settings["codex_model"]]
    cmd.append("-")
    proc = subprocess.Popen(cmd, cwd=str(pack), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", env=_child_env(False), bufsize=1)
    proc.stdin.write(prompt)
    proc.stdin.close()
    tail: list[str] = []

    def on_line(line: str):
        tail.append(line)
        del tail[:-20]
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            return
        item = d.get("item") or d.get("msg") or {}
        typ = item.get("type") or d.get("type", "")
        if "command" in str(typ):
            on_step("tool", f"Reading: {str(item.get('command', ''))[:120]}")
        elif "reasoning" in str(typ) and item.get("text"):
            on_step("think", str(item["text"])[:400])
        elif "agent_message" in str(typ) and item.get("text"):
            on_step("note", str(item["text"])[:400])
        elif d.get("type") == "thread.started":
            on_step("start", "Codex is reading the catalog")
    try:
        _pump(proc, cancel, float(settings.get("timeout", 600)), on_line)
    except Cancelled:
        return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
    except TimeoutError as e:
        return {"plan": None, "text": "", "error": str(e), "meta": {}}
    text = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
    out_file.unlink(missing_ok=True)
    plan = _json_from_text(text)
    if plan is None:
        return {"plan": None, "text": text, "error": "Codex ended without a plan. " + "".join(tail)[-600:], "meta": {}}
    from .plan import unstrict
    return {"plan": unstrict(plan), "text": "", "error": None, "meta": {"backend": "codex"}}


# ---------------------------------------------------------------------- OpenAI-compatible (LM Studio, Ollama)
def _post(url: str, body: dict, key: str, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key or 'local'}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def openai_models(base_url: str) -> list[str]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=3) as r:
            return [m.get("id") for m in json.loads(r.read().decode()).get("data", [])]
    except Exception:  # noqa: BLE001
        return []


OPENAI_TOOLS = [
    {"type": "function", "function": {"name": "search_entities", "description": "Find people, places, groups or model concepts by name; returns exact refs and ready-made `who` filters.",
                                      "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "kinds": {"type": "array", "items": {"type": "string"}}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "count_people", "description": "Count how many people a `who` filter selects right now.",
                                      "parameters": {"type": "object", "properties": {"who": {"type": "object"}}, "required": ["who"]}}},
    {"type": "function", "function": {"name": "validate_plan", "description": "Check a draft plan; returns errors to fix and warnings.",
                                      "parameters": {"type": "object", "properties": {"plan": {"type": "object"}}, "required": ["plan"]}}},
]


def run_openai(system: str, prompt: str, schema: dict, settings: dict, on_step, cancel: threading.Event, tool_fn) -> dict:
    base = (settings.get("openai_url") or "http://localhost:1234/v1").rstrip("/")
    key = settings.get("openai_key") or "lm-studio"
    model = settings.get("openai_model") or (openai_models(base) or [""])[0]
    if not model:
        return {"plan": None, "text": "", "error": f"No model is loaded at {base} (start LM Studio's server and load a model).", "meta": {}}
    timeout = float(settings.get("timeout", 600))
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    on_step("start", f"Asking {model} at {base}")
    try:
        for _ in range(int(settings.get("openai_tool_rounds", 6))):
            if cancel.is_set():
                return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
            r = _post(base + "/chat/completions", {"model": model, "messages": msgs, "tools": OPENAI_TOOLS, "temperature": 0.3}, key, timeout)
            m = r["choices"][0]["message"]
            calls = m.get("tool_calls") or []
            if not calls:
                if m.get("content"):
                    on_step("note", str(m["content"])[:400])
                break
            msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": calls})
            for c in calls:
                fn = c.get("function", {})
                args = fn.get("arguments")
                try:
                    args = json.loads(args) if isinstance(args, str) else (args or {})
                except json.JSONDecodeError:
                    args = {}
                on_step("tool", _describe_tool(fn.get("name", ""), args))
                res = tool_fn(fn.get("name", ""), args)
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": json.dumps(res)[:6000]})
        msgs.append({"role": "user", "content": "Now give the final plan as JSON matching the schema."})
        on_step("tool", "Writing up the plan")
        r = _post(base + "/chat/completions", {"model": model, "messages": msgs, "temperature": 0.2,
                                               "response_format": {"type": "json_schema", "json_schema": {"name": "whatif_plan", "strict": True, "schema": schema}}},
                  key, timeout)
        txt = r["choices"][0]["message"].get("content") or ""
    except urllib.error.URLError as e:
        return {"plan": None, "text": "", "error": f"Couldn't reach {base}: {e}", "meta": {}}
    except Exception as e:  # noqa: BLE001
        return {"plan": None, "text": "", "error": f"Local model error: {e!r}", "meta": {}}
    plan = _json_from_text(txt)
    if plan is None:
        return {"plan": None, "text": txt, "error": "The local model didn't return a valid plan.", "meta": {"model": model}}
    from .plan import unstrict
    return {"plan": unstrict(plan), "text": "", "error": None, "meta": {"model": model, "backend": "openai"}}


def python_exe() -> str:
    return sys.executable

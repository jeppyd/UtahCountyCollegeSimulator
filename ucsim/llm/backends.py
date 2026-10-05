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
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL_NAMES = ("search_entities", "describe_entity", "count_people", "validate_plan")
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._:\[\]-]{1,64}$")     # model names: never anything a shell could interpret
EFFORTS = ("low", "medium", "high", "xhigh", "max")
_help_cache: dict[str, str] = {}


WINDOWS = os.name == "nt"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if WINDOWS else 0
_version_cache: dict[str, tuple[float, str | None]] = {}


def which(cmd: str) -> str | None:
    return shutil.which(cmd)


def resolve_cli(name: str, override: str | None = None) -> tuple[list[str] | None, str | None]:
    """The argv prefix that launches a CLI. npm's Windows launchers (claude.cmd, codex.cmd) run through cmd.exe, which
    mangles JSON arguments and can execute text in them, so they are resolved to `node <script.js>` instead."""
    exe = which(override or name)
    if not exe:
        return None, None
    if WINDOWS and exe.lower().endswith((".cmd", ".bat")):
        try:
            text = Path(exe).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        m = re.search(r'%~?dp0%?\\?([^"%\r\n]+?\.(?:c?js|mjs))', text)
        base = Path(exe).parent
        if m:
            script = (base / m.group(1).lstrip("\\/")).resolve()
            node = base / "node.exe"
            node = str(node) if node.exists() else which("node")
            if script.exists() and node:
                return [node, str(script)], None
        native = base / f"{name}.exe"
        if native.exists():
            return [str(native)], None
        return None, (f"Found {Path(exe).name}, an npm launcher that can't be run safely from the simulator. Install "
                      f"{'Claude Code with its native installer' if name == 'claude' else name + ' so that ' + name + '.exe is on PATH'}, "
                      f"or set the path to the real program in settings.")
    return [exe], None


def _spawn(argv: list[str], **kw) -> subprocess.Popen:
    """Start a CLI in its own process group (so Stop can end it and anything it starts), without a console window."""
    if WINDOWS:
        kw["creationflags"] = kw.get("creationflags", 0) | subprocess.CREATE_NEW_PROCESS_GROUP | _NO_WINDOW
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(argv, **kw)


def _kill_tree(proc: subprocess.Popen):
    if proc.poll() is not None:
        return
    try:
        if WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=10, creationflags=_NO_WINDOW)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except Exception:  # noqa: BLE001
        pass
    try:
        proc.kill()
    except Exception:  # noqa: BLE001
        pass


def _run_quick(argv: list[str], timeout: float = 20) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                              encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    except Exception:  # noqa: BLE001
        return None


def _help(argv: list[str]) -> str:
    key = " ".join(argv)
    if key not in _help_cache:
        out = _run_quick([*argv, "--help"])
        _help_cache[key] = out.stdout if out else ""
    return _help_cache[key]


def version(cmd: str, override: str | None = None) -> str | None:
    """Installed version (cached for a minute: the status panel asks often)."""
    hit = _version_cache.get(cmd)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    argv, err = resolve_cli(cmd, override)
    v = None
    if argv:
        out = _run_quick([*argv, "--version"])
        txt = ((out.stdout or out.stderr) if out else "").strip()
        v = txt.splitlines()[0] if txt else "installed"
    elif err:
        v = None
    _version_cache[cmd] = (time.time(), v)
    return v


def _child_env(drop_api_key: bool) -> dict:
    env = dict(os.environ)
    if drop_api_key:
        # an API key in the environment would make Claude Code bill the key instead of the subscription
        env.pop("ANTHROPIC_API_KEY", None)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def _describe_tool(name: str, inp) -> str:
    inp = inp if isinstance(inp, dict) else {}
    short = str(name).split("__")[-1]
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
        plan = inp.get("plan")
        if isinstance(plan, str):
            try:
                plan = json.loads(plan)
            except json.JSONDecodeError:
                plan = None
        n = len(plan.get("changes") or []) if isinstance(plan, dict) else 0
        return f"Checking a draft plan ({n} change{'s' if n != 1 else ''})"
    if short == "StructuredOutput":
        return "Writing up the plan"
    return f"Using {short}"


class Cancelled(Exception):
    pass


def _feed_stdin(proc: subprocess.Popen, text: str):
    """Write the prompt without blocking the reader (a CLI that exits early must not hide its own error)."""
    def go():
        try:
            proc.stdin.write(text)
            proc.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
    threading.Thread(target=go, daemon=True).start()


def _pump(proc: subprocess.Popen, cancel: threading.Event, timeout: float, on_line):
    """Read stdout lines until EOF, cancellation or timeout. The process (and anything it started) is killed on cancel,
    on timeout and on any unexpected error, so nothing is left running."""
    t0 = time.time()
    done = threading.Event()

    def watchdog():
        while not done.wait(0.25):
            if cancel.is_set() or time.time() - t0 > timeout:
                _kill_tree(proc)
                try:
                    proc.stdout.close()
                except Exception:  # noqa: BLE001
                    pass
                return
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        for line in proc.stdout:
            try:
                on_line(line)
            except Exception:  # noqa: BLE001 — one odd event must not orphan the process
                traceback.print_exc()
    except (ValueError, OSError):
        pass    # stdout closed by the watchdog
    finally:
        done.set()
        if proc.poll() is None and (cancel.is_set() or time.time() - t0 > timeout):
            _kill_tree(proc)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
    if cancel.is_set():
        raise Cancelled()
    if time.time() - t0 > timeout:
        raise TimeoutError(f"no answer within {int(timeout)} s")


# ---------------------------------------------------------------------- Claude Code
def run_claude(prompt: str, schema: dict, pack: Path, settings: dict, on_step, cancel: threading.Event, mcp_config: Path | None) -> dict:
    argv, why = resolve_cli("claude", settings.get("claude_path") or None)
    if not argv:
        return {"plan": None, "text": "", "error": why or "Claude Code isn't installed or isn't on PATH (install it and run `claude` once to sign in).", "meta": {}}
    h = _help(argv)
    cmd = [*argv, "-p", "--output-format", "stream-json", "--verbose", "--json-schema", json.dumps(schema, separators=(",", ":"))]
    sysfile = pack / "system.md"
    # the -file form is hidden from --help in current versions ("--append-system-prompt[-file]"); the guide + catalog
    # (~80 KB) must never go on the command line (Windows caps it at 32 KB)
    if "system-prompt-file" in h or "system-prompt[-file]" in h or not h:
        cmd += ["--append-system-prompt-file", str(sysfile)]
    elif not WINDOWS:
        cmd += ["--append-system-prompt", sysfile.read_text(encoding="utf-8")]
    else:
        return {"plan": None, "text": "", "error": "This Claude Code version is too old for the simulator: update it (`claude update`).", "meta": {}}
    allowed = ["Read", "Grep", "Glob"]
    if mcp_config is not None:
        cmd += ["--mcp-config", str(mcp_config), "--strict-mcp-config"]
        allowed += [f"mcp__ucsim__{t}" for t in TOOL_NAMES]
    cmd += ["--tools", "Read,Grep,Glob", "--allowedTools", ",".join(allowed), "--permission-mode", "dontAsk",
            "--max-turns", str(int(settings.get("max_turns", 40))), "--add-dir", str(ROOT / "docs")]
    if "--no-session-persistence" in h:
        cmd.append("--no-session-persistence")
    if settings.get("claude_model") and SAFE_TOKEN.match(str(settings["claude_model"])):
        cmd += ["--model", settings["claude_model"]]
    if settings.get("claude_effort") in EFFORTS and "--effort" in h:
        cmd += ["--effort", settings["claude_effort"]]
    if "--restricted" in h:
        cmd.append("--restricted")
    try:
        proc = _spawn(cmd, cwd=str(pack), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      text=True, encoding="utf-8", errors="replace", env=_child_env(settings.get("use_subscription", True)), bufsize=1)
    except OSError as e:
        return {"plan": None, "text": "", "error": f"Couldn't start Claude Code: {e}", "meta": {}}
    err_lines: list[str] = []
    threading.Thread(target=lambda: err_lines.extend(proc.stderr.readlines()), daemon=True).start()
    _feed_stdin(proc, prompt)
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
    argv, why = resolve_cli("codex", settings.get("codex_path") or None)
    if not argv:
        return {"plan": None, "text": "", "error": why or "Codex CLI isn't installed or isn't on PATH (install it and run `codex login`).", "meta": {}}
    import uuid
    tag = uuid.uuid4().hex[:10]
    schema_file = pack / f"codex_schema_{tag}.json"       # per job: concurrent compiles never share a file
    out_file = pack / f"codex_last_{tag}.txt"
    try:
        schema_file.write_text(json.dumps(schema), encoding="utf-8")
        cmd = [*argv, "exec", "--json", "--output-schema", str(schema_file), "-o", str(out_file), "--sandbox", "read-only",
               "--skip-git-repo-check", "-C", str(pack)]
        if settings.get("codex_model") and SAFE_TOKEN.match(str(settings["codex_model"])):
            cmd += ["-m", settings["codex_model"]]
        cmd.append("-")
        try:
            proc = _spawn(cmd, cwd=str(pack), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace", env=_child_env(False), bufsize=1)
        except OSError as e:
            return {"plan": None, "text": "", "error": f"Couldn't start Codex: {e}", "meta": {}}
        _feed_stdin(proc, prompt)
        return _codex_read(proc, out_file, settings, on_step, cancel)
    finally:
        schema_file.unlink(missing_ok=True)
        out_file.unlink(missing_ok=True)


def _codex_read(proc, out_file: Path, settings: dict, on_step, cancel: threading.Event) -> dict:
    tail: list[str] = []

    def on_line(line: str):
        tail.append(line)
        del tail[:-20]
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            return
        item = d.get("item") or d.get("msg") or {}
        item = item if isinstance(item, dict) else {}
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
    deadline = time.time() + float(settings.get("timeout", 600))     # one budget for the whole conversation

    def left() -> float:
        rest = deadline - time.time()
        if rest <= 0:
            raise TimeoutError(f"no answer within {int(float(settings.get('timeout', 600)))} s")
        return rest
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    on_step("start", f"Asking {model} at {base}")
    try:
        for _ in range(int(settings.get("openai_tool_rounds", 6))):
            if cancel.is_set():
                return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
            r = _post(base + "/chat/completions", {"model": model, "messages": msgs, "tools": OPENAI_TOOLS, "temperature": 0.3}, key, left())
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
                try:
                    res = tool_fn(fn.get("name", ""), args if isinstance(args, dict) else {})
                except Exception as e:  # noqa: BLE001 — a bad tool call goes back to the model, it doesn't end the compile
                    res = {"error": f"{type(e).__name__}: {e}"}
                msgs.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": json.dumps(res)[:6000]})
        if cancel.is_set():
            return {"plan": None, "text": "", "error": "cancelled", "meta": {}}
        msgs.append({"role": "user", "content": "Now give the final plan as JSON matching the schema."})
        on_step("tool", "Writing up the plan")
        r = _post(base + "/chat/completions", {"model": model, "messages": msgs, "temperature": 0.2,
                                               "response_format": {"type": "json_schema", "json_schema": {"name": "whatif_plan", "strict": True, "schema": schema}}},
                  key, left())
        txt = r["choices"][0]["message"].get("content") or ""
    except TimeoutError as e:
        return {"plan": None, "text": "", "error": str(e), "meta": {}}
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
